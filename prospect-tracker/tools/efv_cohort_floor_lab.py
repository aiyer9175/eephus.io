# eFV cohort / full-pool floor lab (LANE I4 + I5, 2026-08-07b).
#
# WHY THIS FILE EXISTS. Two questions the audit plan opened and nothing in the repo
# can answer today:
#
#   I4. data/xfv_eval.json evals.full_pool_km.pooled_oos has the hitter consensus at
#       0.3002 and the shipped blend at 0.2787, a delta of -0.0215 on n = 1792. That
#       is larger in magnitude than any margin eFV wins by anywhere, and it appears in
#       no weak-cell list and no headline. Nobody has ever derived a floor for that
#       cell, so nobody knows whether it is a loss or noise.
#
#   I5. data/xfv_scoreboard_eval.json weak_cells lists nine negative cells and gates
#       none of them. The scoreboard's own basis note says to check the margin against
#       mde95_model_vs_consensus (0.044) before quoting a cell, but 0.044 is the POOLED
#       floor; a 46-row tier cell has a far larger floor of its own and nobody has
#       measured it.
#
# ESTIMATOR. The shipped paired bootstrap, imported not reimplemented: this module
# pulls ridge_fit / ridge_pred / ols_fit / wrho straight out of tools/efv_mde_lab.py so
# the primitives are bit-identical to the floor that gates production. The whole pool
# (train AND test) is resampled and the ridge + consensus OLS are refit on every draw.
# MDE95 one-sided = 1.645 * sd(delta), the convention in docs/EFV_GATE_STANDARD.md.
#
# THE TRAP THIS LAB IS BUILT AGAINST. Any change that makes a floor SMALLER looks like
# progress and is usually power laundering. The `nullcov` mode exists so that the one
# estimator variant this lab introduces (restricting the delta to a cohort cell) has to
# earn its numbers under a null where the truth is known by construction, BEFORE any
# cell floor is quoted. Registration: docs/efv-2026-08-07b/COHORT_FLOORS.md part 0.
#
# Run: python tools/efv_cohort_floor_lab.py repro          reproduce every plan number
#      python tools/efv_cohort_floor_lab.py carveout       is full-pool rho a debut statistic
#      python tools/efv_cohort_floor_lab.py cost
#      python tools/efv_cohort_floor_lab.py nullcov        coverage check, no writes
#      python tools/efv_cohort_floor_lab.py fullpool [B]   I4 floor
#      python tools/efv_cohort_floor_lab.py cells [B]      I5 per-cell floors
#      python tools/efv_cohort_floor_lab.py mechanism      I4 debut-margin decomposition
#      python tools/efv_cohort_floor_lab.py all [B]        everything + write the ledger
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np   # noqa: E402  after the thread-count pins, as in efv_mde_lab.py

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                          # noqa: E402  read-only
import efv_lab_runner as LAB                                   # noqa: E402  read-only
# The shipped bootstrap primitives. Imported, never copied: a floor measured with a
# private reimplementation of the ridge would not be comparable to data/xfv_mde_floor.json.
from efv_mde_lab import ridge_fit, ridge_pred, ols_fit, wrho    # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_cohort_floors.json"
SEED = 20260807
SIDES = ("hit", "pit")
Z95_ONE = 1.645
Z95_TWO = 1.96


# --------------------------------------------------------------------- pools
def load_pool(side: str, pool: str = "full") -> dict:
    """One eFV eval pool as numpy arrays, matching efv_model.run().

    pool='full'    -> `full` in efv_model.run:2515, debuted + busts minus recent busts.
                      This is the frame evals.full_pool_km is computed on.
    pool='debuted' -> `deb` in efv_model.run:2514, the debuted_km frame.
    """
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    if pool == "full":
        rows = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    else:
        rows = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(rows, "target_censored", side)
    keys, mono = E._feature_spec(side)
    return {
        "side": side, "pool": pool, "keys": list(keys), "mono": mono,
        "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "deb": np.array([r["kind"] == "debuted" for r in prep], dtype=bool),
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


def load_cellpool(side: str) -> dict:
    """The SCOREBOARD's pool, so the cell floors attach to the cells that are actually
    published. tools/efv_scoreboard.py:_forward_read reads efv_lab_runner.data_for,
    which overrides is_ifa / is_college / is_hs from the acquisition cohort; that makes
    it a slightly different frame from efv_model._prep and it is the frame the weak-cell
    margins were measured on, so it is the frame their floors must be measured on.
    """
    rows = LAB.data_for(side)
    keys = E._feature_spec(side)[0]
    return {
        "side": side, "keys": list(keys),
        "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in rows], dtype=float),
        "y": np.array([r["target_censored"] for r in rows], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in rows]), 1e-3, None),
        "fv": np.array([r["fv"] for r in rows], dtype=float),
        "dy": np.array([r["decision_year"] for r in rows], dtype=int),
        "coh": np.array([r["cohort"] for r in rows], dtype=object),
        "tier": np.array([LAB._tier(r["fv"]) for r in rows], dtype=int),
        "lam": E.blend_lambda(side),
        "n": len(rows),
    }


# --------------------------------------------------------------------- one pass
def chain(D, sel=None, years=None, lam=None, min_test=15, min_train=60, extra=()):
    """Forward-chained consensus + blend on one pool.

    Identical in structure to efv_mde_lab.chain (which reproduces efv_model._run_eval)
    with two additions: configurable fold floors, so the scoreboard's 50/12 convention
    can be reproduced exactly, and `extra`, a tuple of per-row tag array names carried
    through to the output so a cell can be cut after the chain runs.
    """
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"] if lam is None else lam
    if sel is None:
        sel = np.arange(D["n"])
    X, y, w, fv, dy = D["X"][sel], D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    tags = {k: D[k][sel] for k in extra}
    C, B, T, W, YR = [], [], [], [], []
    TG = {k: [] for k in extra}
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < min_test or len(tr) < min_train:
            continue
        o = ols_fit(fv[tr], y[tr])
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = ridge_pred(rg, X[te])
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(y[te])
        W.append(w[te])
        YR.append(np.full(len(te), yr))
        for k in extra:
            TG[k].append(tags[k][te])
    if not B:
        return None
    out = {"cons": np.concatenate(C), "blend": np.concatenate(B),
           "y": np.concatenate(T), "w": np.concatenate(W), "yr": np.concatenate(YR)}
    for k in extra:
        out[k] = np.concatenate(TG[k])
    return out


def delta_of(r, mask=None, weighted=True):
    if r is None:
        return float("nan")
    idx = slice(None) if mask is None else mask
    c, b, y = r["cons"][idx], r["blend"][idx], r["y"][idx]
    if len(y) < 8 or len(set(b.tolist())) < 2 or len(set(c.tolist())) < 2 or len(set(y.tolist())) < 2:
        return float("nan")
    w = r["w"][idx] if weighted else None
    return wrho(b, y, w) - wrho(c, y, w)


def legs_of(r, mask=None, weighted=True):
    idx = slice(None) if mask is None else mask
    c, b, y = r["cons"][idx], r["blend"][idx], r["y"][idx]
    w = r["w"][idx] if weighted else None
    return {"n": int(len(y)), "consensus": round(wrho(c, y, w), 5),
            "blend": round(wrho(b, y, w), 5),
            "delta": round(wrho(b, y, w) - wrho(c, y, w), 5)}


def summarize(draws, point):
    a = np.array(draws, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 20:
        return {"B_used": int(len(a)), "point_delta": round(float(point), 5),
                "sd": None, "mde95_onesided": None, "verdict": "UNMEASURABLE"}
    sd = float(a.std(ddof=1))
    mde1 = Z95_ONE * sd
    return {
        "B_used": int(len(a)),
        "point_delta": round(float(point), 5),
        "boot_mean_delta": round(float(a.mean()), 5),
        "sd": round(sd, 5),
        "mde95_onesided": round(mde1, 4),
        "mde95_twosided": round(Z95_TWO * sd, 4),
        "ci95": [round(float(np.percentile(a, 2.5)), 5),
                 round(float(np.percentile(a, 97.5)), 5)],
        "p_gt_0": round(float((a > 0).mean()), 4),
        "margin_over_floor": round(abs(float(point)) / mde1, 3) if mde1 > 0 else None,
        "resolvable": bool(abs(float(point)) >= mde1),
        "verdict": ("RESOLVABLE " + ("WIN" if point > 0 else "LOSS")
                    if abs(float(point)) >= mde1 else "NULL"),
    }


# --------------------------------------------------------------------- repro
def repro():
    print("=== REPRO: every number lane I4 / I5 asserts, from the artifacts ===")
    out = {}
    for side, art in (("hit", "xfv_eval.json"), ("pit", "xfv_eval_pitcher.json")):
        d = json.loads((ROOT / "data" / art).read_text(encoding="utf-8"))
        for cut in ("debuted_km", "full_pool_km"):
            p = d["evals"][cut]["pooled_oos"]
            base, bl = p["baseline"], p["blend"]
            out[f"{side}.{cut}"] = {
                "n": base["n"], "n_effective": base.get("n_effective"),
                "consensus": base["spearman"], "blend": bl["spearman"],
                "delta": round(bl["spearman"] - base["spearman"], 4),
                "source": f"data/{art} evals.{cut}.pooled_oos",
            }
            print(f"  {side} {cut:<14} n={base['n']:<5} n_eff={base.get('n_effective')} "
                  f"cons={base['spearman']:.4f} blend={bl['spearman']:.4f} "
                  f"delta={bl['spearman']-base['spearman']:+.4f}")
    print("\n  REPLICA on the same frames (this lab's chain, shipped primitives):")
    rep = {}
    for side in SIDES:
        for pool, cut in (("debuted", "debuted_km"), ("full", "full_pool_km")):
            D = load_pool(side, pool)
            r = chain(D)
            lg = legs_of(r, weighted=True)
            rep[f"{side}.{cut}"] = lg
            a = out[f"{side}.{cut}"]
            print(f"  {side} {cut:<14} n={lg['n']:<5} cons={lg['consensus']:.4f} "
                  f"blend={lg['blend']:.4f} delta={lg['delta']:+.4f}   "
                  f"[artifact delta {a['delta']:+.4f}, gap {lg['delta']-a['delta']:+.5f}]")
    sb = json.loads((ROOT / "data" / "xfv_scoreboard_eval.json").read_text(encoding="utf-8"))
    print("\n  weak cells, verbatim from data/xfv_scoreboard_eval.json weak_cells:")
    for c in sb["weak_cells"]:
        print(f"    {c['cell']:<36} {c['metric']:<16} n={c['n']:<5} margin={c['margin']:+.4f}")
    eb = json.loads((ROOT / "data" / "xfv_driver_elite_band.json").read_text(encoding="utf-8"))
    elite = {}
    for s in SIDES:
        b = eb["arms"][s]["b_elite_eval"]
        elite[s] = {"n_scored": b["n_scored"], "delta": b["delta"],
                    "mde95_onesided": b["mde95_onesided"],
                    "floor_over_margin": round(b["mde95_onesided"] / abs(b["delta"]), 2),
                    "source": "data/xfv_driver_elite_band.json arms.%s.b_elite_eval" % s}
        print(f"  ELITE BAND {s}: n={b['n_scored']} delta={b['delta']:+.5f} "
              f"MDE95={b['mde95_onesided']} -> floor is "
              f"{elite[s]['floor_over_margin']}x the margin, unresolvable CONFIRMED")
    return {"artifact": out, "replica": rep, "weak_cells": sb["weak_cells"], "elite_band": elite}


# --------------------------------------------------------------------- carve-out
def carveout():
    """Does EFV_GATE_STANDARD.md:110-133 reach the full_pool_km SPEARMAN cut?

    The carve-out bans the full-pool debut/no-debut AUC for any candidate that can
    sense a missing MiLB block, because missingness is a near-deterministic proxy for
    the AUC LABEL. The registered test (COHORT_FLOORS.md 0.3) is whether full-pool
    Spearman is majority that same debut/no-debut contrast, and whether the shipped
    feature spec carries the sensor.
    """
    print("=== CARVE-OUT: is full_pool_km Spearman a disguised debut/no-debut statistic ===")
    out = {}
    for side in SIDES:
        D = load_pool(side, "full")
        r = chain(D, extra=("deb",))
        deb = r["deb"]
        y = r["y"]
        nb, nd = int((~deb).sum()), int(deb.sum())
        # informative pair mass. Bust rows are tied at target 0, so bust-bust pairs
        # carry no ordering at all and must leave the denominator.
        p_bd = nb * nd
        p_dd = nd * (nd - 1) // 2
        p_bb = nb * (nb - 1) // 2
        share = p_bd / (p_bd + p_dd)
        keys = D["keys"]
        sensor = [k for k in keys if "missing" in k]
        row = {
            "n_scored": int(len(y)),
            "n_bust": nb, "n_debuted": nd,
            "bust_target_all_zero": bool(np.all(y[~deb] == 0.0)),
            "n_debuted_with_zero_target": int((y[deb] == 0.0).sum()),
            "pairs_bust_x_debuted": int(p_bd),
            "pairs_debuted_x_debuted": int(p_dd),
            "pairs_bust_x_bust_uninformative": int(p_bb),
            "informative_pair_share_that_is_debut_margin": round(share, 4),
            "feature_spec": keys,
            "missingness_sensor_in_spec": sensor,
        }
        # empirical strength of the sensor as a proxy for the label
        if sensor:
            k = sensor[0]
            col = D["X"][:, keys.index(k)]
            m1, m0 = col > 0.5, col <= 0.5
            row["sensor"] = {
                "name": k,
                "n_fires": int(m1.sum()),
                "debut_rate_when_fires": round(float(D["deb"][m1].mean()), 4) if m1.any() else None,
                "debut_rate_when_not": round(float(D["deb"][m0].mean()), 4) if m0.any() else None,
            }
        row["carveout_reaches_this_cut"] = bool(share > 0.50 and sensor)
        out[side] = row
        print(f"  {side}: n={row['n_scored']} busts={nb} debuted={nd}")
        print(f"       bust targets all exactly 0: {row['bust_target_all_zero']}; "
              f"debuted rows also at 0: {row['n_debuted_with_zero_target']}")
        print(f"       informative pairs that are BUST x DEBUTED: {share:.1%} "
              f"({p_bd:,} of {p_bd + p_dd:,}); {p_bb:,} more pairs are tied-at-0 and carry nothing")
        print(f"       missingness sensor in the shipped spec: {sensor or 'NONE'}")
        if sensor:
            s = row["sensor"]
            print(f"       {s['name']} fires on {s['n_fires']} rows; debut rate "
                  f"{s['debut_rate_when_fires']} when it fires vs {s['debut_rate_when_not']} when not")
        print(f"       -> CARVE-OUT REACHES THIS CUT: {row['carveout_reaches_this_cut']}")
    return out


# --------------------------------------------------------------------- mechanism
def mechanism():
    """I4 registered mechanism test: split the full-pool delta into a debut-margin leg
    and a within-debuted rank leg, on the SAME full-pool forward chain."""
    print("=== MECHANISM: where does the full-pool delta live ===")
    out = {}
    for side in SIDES:
        D = load_pool(side, "full")
        r = chain(D, extra=("deb",))
        deb = r["deb"]

        def _auc(score, lab):
            lab = np.asarray(lab, dtype=bool)
            if lab.all() or (~lab).all():
                return None
            o = np.argsort(score, kind="mergesort")
            s = np.asarray(score, dtype=float)[o]
            rk = np.empty(len(s), dtype=float)
            rk[o] = np.arange(1, len(s) + 1, dtype=float)
            i = 0
            so = s
            while i < len(so):
                j = i
                while j + 1 < len(so) and so[j + 1] == so[i]:
                    j += 1
                if j > i:
                    rk[o[i:j + 1]] = (i + j) / 2.0 + 1
                i = j + 1
            npos, nneg = int(lab.sum()), int((~lab).sum())
            return (rk[lab].sum() - npos * (npos + 1) / 2.0) / (npos * nneg)

        auc_c = _auc(r["cons"], deb)
        auc_b = _auc(r["blend"], deb)
        within = legs_of(r, mask=deb, weighted=True)
        pooled = legs_of(r, weighted=True)
        out[side] = {
            "pooled_full": pooled,
            "debut_margin_auc": {"n": int(len(deb)), "n_debuted": int(deb.sum()),
                                 "consensus": round(auc_c, 5), "blend": round(auc_b, 5),
                                 "delta": round(auc_b - auc_c, 5)},
            "within_debuted_rho_on_fullpool_fit": within,
        }
        print(f"  {side}: pooled full-pool rho delta {pooled['delta']:+.4f} "
              f"(cons {pooled['consensus']:.4f} blend {pooled['blend']:.4f})")
        print(f"       debut/no-debut AUC delta      {auc_b - auc_c:+.4f} "
              f"(cons {auc_c:.4f} blend {auc_b:.4f})")
        print(f"       within-debuted rho delta      {within['delta']:+.4f} "
              f"on n={within['n']} (same full-pool fit)")

        # DIAGNOSTIC PROBE, not a ship proposal: drop the missingness sensor and refit,
        # plus a row-permuted twin of the same column (gate standard section 2.2).
        keys = D["keys"]
        sens = [k for k in keys if "missing" in k]
        if sens:
            k = sens[0]
            j = keys.index(k)
            D2 = dict(D)
            D2["X"] = np.delete(D["X"], j, axis=1)
            D2["keys"] = [x for x in keys if x != k]
            r2 = chain(D2, extra=("deb",))
            lg2 = legs_of(r2, weighted=True)
            rng = np.random.default_rng(SEED)
            D3 = dict(D)
            Xp = D["X"].copy()
            Xp[:, j] = Xp[rng.permutation(D["n"]), j]
            D3["X"] = Xp
            r3 = chain(D3, extra=("deb",))
            lg3 = legs_of(r3, weighted=True)
            auc2 = _auc(r2["blend"], r2["deb"]) - _auc(r2["cons"], r2["deb"])
            auc3 = _auc(r3["blend"], r3["deb"]) - _auc(r3["cons"], r3["deb"])
            out[side]["sensor_probe"] = {
                "note": "DIAGNOSTIC ONLY, not a ship proposal",
                "sensor": k,
                "shipped": {"rho_delta": pooled["delta"], "auc_delta": round(auc_b - auc_c, 5)},
                "sensor_dropped": {"rho_delta": lg2["delta"], "auc_delta": round(auc2, 5)},
                "sensor_row_permuted": {"rho_delta": lg3["delta"], "auc_delta": round(auc3, 5)},
            }
            print(f"       PROBE drop {k}: rho delta {lg2['delta']:+.4f}, auc delta {auc2:+.4f}")
            print(f"       PROBE permute {k}: rho delta {lg3['delta']:+.4f}, auc delta {auc3:+.4f}")
    return out


# --------------------------------------------------------------------- ties
def ties(seeds: int = 12):
    """The registered mechanism test came back FALSE, so this is the follow-up:
    is the full-pool consensus rho inflated by a TIE BLOCK the blend does not have?

    The consensus leg is `max(0.0, a + b*FV)` (efv_model._run_eval:1481). In the full
    pool that clamp collapses every low-FV row onto EXACTLY 0.0, and the full-pool
    target collapses every bust onto EXACTLY 0.0 too. Two aligned tie blocks are worth
    Spearman that neither leg earned by ordering anything: inside a tie block a rater
    makes no claim, so it cannot be scored wrong. The blend breaks that block, because
    the model term is continuous, so it is scored on orderings the consensus is excused
    from.

    Control (gate standard section 2.2): add pure noise far below the smallest real gap
    to the consensus leg. It carries ZERO information; it only breaks exact ties. If the
    consensus rho falls when its ties are broken by noise, the published 0.3002 is a
    tie-structure number and the head-to-head is not on comparable footing.
    """
    print("=== TIE STRUCTURE: is the full-pool consensus rho a tie-block artifact ===")
    out = {}
    for side in SIDES:
        row = {}
        for pool in ("full", "debuted"):
            D = load_pool(side, pool)
            r = chain(D, extra=("deb",))
            c, b, y, w = r["cons"], r["blend"], r["y"], r["w"]
            zero = c <= 1e-12
            nuniq_c = int(len(np.unique(np.round(c, 9))))
            nuniq_b = int(len(np.unique(np.round(b, 9))))
            # largest tie block in each leg
            _, cnt_c = np.unique(np.round(c, 9), return_counts=True)
            _, cnt_b = np.unique(np.round(b, 9), return_counts=True)
            # tie-broken control, averaged over seeds
            base_c = wrho(c, y, w)
            base_b = wrho(b, y, w)
            jit = []
            scale = 1e-9 * max(1.0, float(np.ptp(c)))
            for s in range(seeds):
                g = np.random.default_rng(SEED + 7000 + s)
                jit.append(wrho(c + g.normal(0, scale, len(c)), y, w))
            jit = float(np.mean(jit))
            row[pool] = {
                "n": int(len(y)),
                "consensus_distinct_values": nuniq_c,
                "consensus_largest_tie_block": int(cnt_c.max()),
                "consensus_rows_clamped_to_zero": int(zero.sum()),
                "clamped_rows_that_are_busts": int((~r["deb"][zero]).sum()) if zero.any() else 0,
                "blend_distinct_values": nuniq_b,
                "blend_largest_tie_block": int(cnt_b.max()),
                "consensus_rho": round(base_c, 5),
                "consensus_rho_ties_broken_by_noise": round(jit, 5),
                "consensus_tie_credit": round(base_c - jit, 5),
                "blend_rho": round(base_b, 5),
                "delta_as_published": round(base_b - base_c, 5),
                "delta_at_equal_resolution": round(base_b - jit, 5),
            }
            v = row[pool]
            print(f"  {side} {pool:<8} n={v['n']:<5} cons has {nuniq_c} distinct values, "
                  f"largest tie block {v['consensus_largest_tie_block']} "
                  f"({v['consensus_rows_clamped_to_zero']} clamped to 0, "
                  f"{v['clamped_rows_that_are_busts']} of them busts); blend has {nuniq_b}")
            print(f"           cons rho {base_c:.4f} -> {jit:.4f} when pure noise breaks its "
                  f"ties (tie credit {base_c - jit:+.4f})")
            print(f"           delta as published {base_b - base_c:+.4f} -> "
                  f"{base_b - jit:+.4f} at equal resolution")
        out[side] = row
    return out


# --------------------------------------------------------------------- cost
def cost():
    rng = np.random.default_rng(SEED)
    for pool in ("full", "debuted"):
        D = {s: load_pool(s, pool) for s in SIDES}
        t0 = time.time()
        for _ in range(3):
            for s in SIDES:
                chain(D[s], rng.integers(0, D[s]["n"], D[s]["n"]))
        per = (time.time() - t0) / 3
        print(f"  {pool:<8} n={[D[s]['n'] for s in SIDES]} per replicate {per:.3f}s "
              f"-> B=500 {per*500/60:.1f} min, B=1000 {per*1000/60:.1f} min")


# --------------------------------------------------------------------- I4
def fullpool(B: int = 600, verbose: bool = True):
    """The I4 floor: paired bootstrap of the full-pool model-vs-consensus rho delta."""
    if verbose:
        print(f"=== I4 FULL-POOL FLOOR (B={B}) ===")
    D = {s: load_pool(s, "full") for s in SIDES}
    pt = {s: chain(D[s]) for s in SIDES}
    point = {s: {"w": delta_of(pt[s], weighted=True),
                 "u": delta_of(pt[s], weighted=False)} for s in SIDES}
    rng = np.random.default_rng(SEED)
    draws = {s: {"w": [], "u": []} for s in SIDES}
    t0 = time.time()
    for i in range(B):
        for s in SIDES:
            r = chain(D[s], rng.integers(0, D[s]["n"], D[s]["n"]))
            draws[s]["w"].append(delta_of(r, weighted=True))
            draws[s]["u"].append(delta_of(r, weighted=False))
        if verbose and (i + 1) % 50 == 0:
            print(f"  {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    out = {}
    for s in SIDES:
        out[s] = {
            "n_scored": int(len(pt[s]["y"])),
            "legs_weighted": legs_of(pt[s], weighted=True),
            "legs_unweighted": legs_of(pt[s], weighted=False),
            "weighted": summarize(draws[s]["w"], point[s]["w"]),
            "unweighted": summarize(draws[s]["u"], point[s]["u"]),
        }
        if verbose:
            for k in ("weighted", "unweighted"):
                v = out[s][k]
                print(f"  {s} {k:<11} delta={v['point_delta']:+.5f} sd={v['sd']} "
                      f"MDE95={v['mde95_onesided']} -> {v['verdict']} "
                      f"(|margin|/floor {v['margin_over_floor']})")
    out["elapsed_s"] = round(time.time() - t0, 1)
    out["B"] = int(B)
    return out


# --------------------------------------------------------------------- I5
CELLS = [
    # (key, side, kind, value, published_margin, published_n) from
    # data/xfv_scoreboard_eval.json weak_cells
    ("hit.fv_tier.55", "hit", "tier", 55, -0.2271, 46),
    ("hit.fv_tier.60", "hit", "tier", 60, -0.0209, 34),
    ("hit.cohort.hs", "hit", "coh", "hs", -0.0182, 201),
    ("hit.cohort.other", "hit", "coh", "other", -0.0195, 170),
    ("pit.fv_tier.50", "pit", "tier", 50, -0.0508, 101),
    ("pit.cohort.college", "pit", "coh", "college", -0.0023, 324),
    ("pit.cohort.hs", "pit", "coh", "hs", -0.0211, 190),
    # not in the plan's list of nine, but it is in weak_cells and it is cheap to close.
    # The era cells run the WIDER protocol (2016-2023, floors 60/10) and are UNWEIGHTED
    # by construction: tools/efv_scoreboard.py:_side_block passes weighted=False so the
    # cell reproduces efv_model._era_split.
    ("pit.era.<=2018", "pit", "era", "<=2018", -0.0202, 132),
]


def cells(B: int = 600, verbose: bool = True):
    """The I5 floors: one paired bootstrap per side, every cell read off each draw.

    Cells share the draw on purpose. They are computed from the same refit forward
    chain, so a single bootstrap gives every cell its own floor at the cost of one.
    """
    if verbose:
        print(f"=== I5 PER-CELL FLOORS (B={B}) ===")
    D = {s: load_cellpool(s) for s in SIDES}
    ERA_YEARS = tuple(range(2016, 2024))

    def _pass(s, sel=None):
        """Both scoreboard protocols on ONE resample: the pooled read
        (tools/efv_scoreboard.py:_side_block -> _forward_read(SCORED_YEARS, 50, 12)) and
        the wider era read (_forward_read(2016-2023, 60, 10))."""
        return (chain(D[s], sel, min_train=50, min_test=12, extra=("coh", "tier")),
                chain(D[s], sel, years=ERA_YEARS, min_train=60, min_test=10,
                      extra=("coh", "tier")))   # `yr` is always emitted by chain()

    pt = {s: _pass(s) for s in SIDES}
    mine = {s: [c for c in CELLS if c[1] == s] for s in SIDES}

    def _pick(rr, kind):
        return rr[1] if kind == "era" else rr[0]

    def _mask(r, kind, val):
        if r is None:
            return None
        if kind == "coh":
            return r["coh"] == val
        if kind == "tier":
            return r["tier"] == val
        return np.array([LAB._era(int(y)) == val for y in r["yr"]], dtype=bool)

    # era cells are UNWEIGHTED by construction; every other cell is pair-weighted.
    def _wt(kind):
        return kind != "era"

    point = {}
    for key, s, kind, val, _m, _n in CELLS:
        r = _pick(pt[s], kind)
        m = _mask(r, kind, val)
        point[key] = {"w": delta_of(r, m, _wt(kind)), "u": delta_of(r, m, False),
                      "n": int(m.sum()), "legs": legs_of(r, m, _wt(kind))}
    rng = np.random.default_rng(SEED)
    draws = {k: {"w": [], "u": [], "n": []} for k, *_ in CELLS}
    t0 = time.time()
    for i in range(B):
        for s in SIDES:
            sel = rng.integers(0, D[s]["n"], D[s]["n"])
            rr = _pass(s, sel)
            for key, _s, kind, val, _m, _n in mine[s]:
                r = _pick(rr, kind)
                if r is None:
                    continue
                m = _mask(r, kind, val)
                draws[key]["w"].append(delta_of(r, m, _wt(kind)))
                draws[key]["u"].append(delta_of(r, m, False))
                draws[key]["n"].append(int(m.sum()))
        if verbose and (i + 1) % 50 == 0:
            print(f"  {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)

    out = {}
    for key, s, kind, val, pub_margin, pub_n in CELLS:
        sw = summarize(draws[key]["w"], point[key]["w"])
        su = summarize(draws[key]["u"], point[key]["u"])
        nn = np.array(draws[key]["n"], dtype=float)
        out[key] = {
            "side": s, "cut": kind, "value": val,
            "published": {"margin": pub_margin, "n": pub_n,
                          "source": "data/xfv_scoreboard_eval.json weak_cells"},
            "replica": {"n": point[key]["n"], **point[key]["legs"]},
            "weighted": sw, "unweighted": su,
            "boot_cell_n": {"mean": round(float(nn.mean()), 1),
                            "p05": round(float(np.percentile(nn, 5)), 1),
                            "p95": round(float(np.percentile(nn, 95)), 1)} if len(nn) else None,
            "adjudicable_vs_published_margin": bool(
                sw["mde95_onesided"] is not None and abs(pub_margin) >= sw["mde95_onesided"]),
        }
        if verbose:
            print(f"  {key:<24} n={point[key]['n']:<5} pub_margin={pub_margin:+.4f} "
                  f"replica={sw['point_delta']:+.4f} MDE95={sw['mde95_onesided']} "
                  f"-> {'ADJUDICATED' if out[key]['adjudicable_vs_published_margin'] else 'NULL, CLOSED'}")
    out["_elapsed_s"] = round(time.time() - t0, 1)
    out["_B"] = int(B)
    return out


def archetype_bounds():
    """The two head-to-head archetype cells, closed by a LOWER BOUND on their floor.

    Registered in COHORT_FLOORS.md 0.2 item 2: sqrt-n scaling of the measured
    common-set floor ignores refit variance and cell-composition variance, both
    strictly positive, so it UNDER-states the true cell floor. Admissible only to
    CLOSE a cell, never to open one or certify a win.
    """
    h = json.loads((ROOT / "data" / "xfv_headtohead_gap.json").read_text(encoding="utf-8"))
    base_n = h["basis"]["scored_rows"]
    base_mde = h["mde95"]
    sb = json.loads((ROOT / "data" / "xfv_scoreboard_eval.json").read_text(encoding="utf-8"))
    out = {"basis": {"pool_n": base_n, "pool_mde95_onesided": base_mde,
                     "source": "data/xfv_headtohead_gap.json",
                     "method": "sqrt(n_pool / n_cell) scaling; LOWER BOUND on the cell floor",
                     "admissible_for": "closing a cell only"}}
    print("=== ARCHETYPE CELLS: conservative floor LOWER BOUND ===")
    for c in sb["weak_cells"]:
        if not c["cell"].startswith("head_to_head.archetype.") or c["metric"] != "spearman":
            continue
        lb = base_mde * math.sqrt(base_n / c["n"])
        out[c["cell"]] = {
            "n": c["n"], "margin": c["margin"],
            "floor_lower_bound": round(lb, 4),
            "closed_by_lower_bound": bool(abs(c["margin"]) < lb),
            "floor_over_margin_at_least": round(lb / abs(c["margin"]), 2) if c["margin"] else None,
        }
        print(f"  {c['cell']:<40} n={c['n']:<5} margin={c['margin']:+.4f} "
              f"floor >= {lb:.4f} -> "
              f"{'NULL, CLOSED' if abs(c['margin']) < lb else 'NOT CLOSED BY THE BOUND'}")
    return out


# --------------------------------------------------------------------- coverage
def nullcov(S: int = 120, B: int = 200, n: int = 700, verbose: bool = True):
    """NOMINAL COVERAGE CHECK for the cell-restricted paired bootstrap.

    The registered gate (COHORT_FLOORS.md 0.2): no estimator variant may contribute a
    number until it covers at >= 95% under a null where the truth is known by
    construction.

    Construction. S independent synthetic datasets, each with the same skeleton as the
    real eval: a forward chain over cohort-years, a consensus column `fv` that carries
    the real signal, and k model features that are noisy copies of fv plus pure noise.
    The model therefore has NO information the consensus lacks, so the true delta is a
    fixed constant of the design (not necessarily zero: a noisy blend degrades the rank,
    which is exactly the regime a losing cell sits in). The truth is the Monte-Carlo mean
    of the point delta across the S datasets. For a subset of datasets the full paired
    bootstrap runs and its 95% percentile interval is checked against that truth.

    Reported for the POOLED delta and for a CELL-RESTRICTED delta (a random 20% tag),
    because the cell restriction is the only estimator variant this lab introduces.
    """
    if verbose:
        print(f"=== NULL COVERAGE CHECK (S={S} datasets, B={B}, n={n}) ===")
    k, nyr = 4, 6
    rng = np.random.default_rng(SEED + 1)

    def make(seed):
        g = np.random.default_rng(seed)
        fv = np.round(g.normal(45, 5, n) / 5) * 5
        y = np.maximum(0.0, 0.35 * (fv - 40) + g.normal(0, 3.0, n))
        X = np.column_stack([fv + g.normal(0, 4.0, n) for _ in range(k)])
        dy = g.integers(2014, 2014 + nyr, n)
        w = np.ones(n)
        tag = g.random(n) < 0.20
        return {"X": X, "y": y, "w": w, "fv": fv, "dy": dy, "tag": tag,
                "lam": 0.7, "n": n}

    years = tuple(range(2014, 2014 + nyr))

    def one(D, sel=None):
        return chain(D, sel, years=years, min_test=12, min_train=50, extra=("tag",))

    pts_p, pts_c = [], []
    for s in range(S):
        D = make(SEED + 1000 + s)
        r = one(D)
        pts_p.append(delta_of(r))
        pts_c.append(delta_of(r, r["tag"]))
    truth_p = float(np.nanmean(pts_p))
    truth_c = float(np.nanmean(pts_c))
    sd_true_p = float(np.nanstd(pts_p, ddof=1))
    sd_true_c = float(np.nanstd(pts_c, ddof=1))
    if verbose:
        print(f"  TRUTH pooled: mean delta {truth_p:+.5f}, sampling sd {sd_true_p:.5f}")
        print(f"  TRUTH cell  : mean delta {truth_c:+.5f}, sampling sd {sd_true_c:.5f}")

    n_check = min(40, S)
    cov_p = cov_c = 0
    sds_p, sds_c = [], []
    for s in range(n_check):
        D = make(SEED + 1000 + s)
        dp, dc = [], []
        for _ in range(B):
            sel = rng.integers(0, n, n)
            r = one(D, sel)
            dp.append(delta_of(r))
            dc.append(delta_of(r, r["tag"]))
        for arr, truth, sds, hit in ((dp, truth_p, sds_p, "p"), (dc, truth_c, sds_c, "c")):
            a = np.array(arr, dtype=float)
            a = a[np.isfinite(a)]
            sds.append(float(a.std(ddof=1)))
            lo, hi = np.percentile(a, 2.5), np.percentile(a, 97.5)
            if lo <= truth <= hi:
                if hit == "p":
                    cov_p += 1
                else:
                    cov_c += 1
    out = {
        "design": {"S_datasets": S, "B": B, "n_rows": n, "k_features": k,
                   "folds": nyr, "cell_share": 0.20,
                   "null": "model features are noisy copies of the consensus column, "
                           "so the model carries no information the consensus lacks"},
        "pooled": {"true_mean_delta": round(truth_p, 5),
                   "true_sampling_sd": round(sd_true_p, 5),
                   "mean_bootstrap_sd": round(float(np.mean(sds_p)), 5),
                   "sd_ratio_boot_over_true": round(float(np.mean(sds_p)) / sd_true_p, 3),
                   "coverage_95": round(cov_p / n_check, 3),
                   "n_checked": n_check},
        "cell_restricted": {"true_mean_delta": round(truth_c, 5),
                            "true_sampling_sd": round(sd_true_c, 5),
                            "mean_bootstrap_sd": round(float(np.mean(sds_c)), 5),
                            "sd_ratio_boot_over_true": round(float(np.mean(sds_c)) / sd_true_c, 3),
                            "coverage_95": round(cov_c / n_check, 3),
                            "n_checked": n_check},
    }
    out["pooled"]["passes"] = bool(out["pooled"]["coverage_95"] >= 0.90)
    out["cell_restricted"]["passes"] = bool(out["cell_restricted"]["coverage_95"] >= 0.90)
    out["verdict"] = ("PASS" if out["cell_restricted"]["passes"] and out["pooled"]["passes"]
                      else "FAIL, cell floors may not be quoted")
    if verbose:
        for kk in ("pooled", "cell_restricted"):
            v = out[kk]
            print(f"  {kk:<16} boot sd {v['mean_bootstrap_sd']:.5f} vs true "
                  f"{v['true_sampling_sd']:.5f} (ratio {v['sd_ratio_boot_over_true']}), "
                  f"coverage {v['coverage_95']:.0%} -> {'PASS' if v['passes'] else 'FAIL'}")
        print(f"  VERDICT: {out['verdict']}")
    return out


# --------------------------------------------------------------------- driver
def run_all(B: int = 600):
    t0 = time.time()
    rp = repro()
    print()
    co = carveout()
    print()
    mech = mechanism()
    print()
    tie = ties()
    print()
    nc = nullcov()
    print()
    if nc["verdict"] != "PASS":
        print("COVERAGE CHECK FAILED: cell floors will be written but flagged unusable.")
    fp = fullpool(B)
    print()
    cl = cells(B)
    print()
    ab = archetype_bounds()
    mf = json.loads((ROOT / "data" / "xfv_mde_floor.json").read_text(encoding="utf-8"))
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_cohort_floor_lab.py all",
        "registration": "docs/efv-2026-08-07b/COHORT_FLOORS.md part 0 "
                        "(written before any fit; pre-registration is dated in-file)",
        "lane": "I4 (full-pool hitter loss) + I5 (per-cohort-cell floors)",
        "estimator": ("paired bootstrap over the WHOLE pool, train and test resampled "
                      "together, consensus OLS and weighted ridge refit on every draw. "
                      "Primitives imported from tools/efv_mde_lab.py, not reimplemented. "
                      "MDE95 one-sided = 1.645 * sd(delta)."),
        "seed": SEED,
        "basis": {
            "scored_years": list(E.SCORED_YEARS),
            "lambda": {s: E.blend_lambda(s) for s in SIDES},
            "pooled_floor_for_reference": {
                "weighted": {s: mf["weighted"][s]["mde95_onesided"] for s in SIDES},
                "unweighted": {s: mf["unweighted"][s]["mde95_onesided"] for s in SIDES},
                "source": "data/xfv_mde_floor.json",
            },
        },
        "reproduction": rp,
        "carveout_test": co,
        "null_coverage_check": nc,
        "i4_full_pool": fp,
        "i4_mechanism": mech,
        "i4_tie_structure": tie,
        "i5_cells": cl,
        "i5_archetype_bounds": ab,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote", OUT_PATH)
    return out


# =========================================================================== #
# WAVE 2 (LANE B, 2026-08-07b): the five weak cells wave 1 never floored.
#
# data/xfv_scoreboard_eval.json weak_cells has SIXTEEN rows. Wave 1 measured eleven
# and its Part 6 ledger says "eleven weak cells ... ALL NULL, ALL CLOSED". The five
# below had no floor of any kind:
#
#   capture.curve_area                  war_capture      n=3678  -0.0081
#   head_to_head.archetype.college_arm  auc_contributor  n=244   -0.0564
#   head_to_head.archetype.hs_arm       auc_contributor  n=144   -0.0246
#   pit.era.<=2018                      auc_contributor  n=132   -0.0101
#   head_to_head.archetype.hs_bat       auc_contributor  n=168   -0.0039
#
# Registration: docs/efv-2026-08-07b/COHORT_FLOORS.md PART 0B, written in full
# (criteria, controls, coverage band, multiplicity rule) before this block existed.
#
# TWO ESTIMATORS EVERYWHERE, because the brief requires it and they can disagree:
#   E1 refit-inclusive  = the shipped gate protocol, whole pool resampled, refit per draw
#   E2 fits-held-fixed  = shipped OOS grades frozen, scored rows resampled
# E1 governs the verdict; a disagreement is reported, not resolved silently.
#
# Run: python tools/efv_cohort_floor_lab.py capture [B]   Q4 only
#      python tools/efv_cohort_floor_lab.py capcontrols   K1-K6, no floor
#      python tools/efv_cohort_floor_lab.py eracells [B]  Q5a
#      python tools/efv_cohort_floor_lab.py archcells [B] Q5b
#      python tools/efv_cohort_floor_lab.py capcov        capture coverage gate
#      python tools/efv_cohort_floor_lab.py waveb [B]     everything + merge the ledger
# =========================================================================== #

Z99_ONE = 2.326          # one-sided alpha 0.01 = Bonferroni at k = 5 cells
BONF_K = 5


def auc_of(score, label):
    """Tie-corrected rank AUC, the same construction efv_scoreboard / source_backtest
    score their auc_contributor cells with."""
    lab = np.asarray(label, dtype=bool)
    s = np.asarray(score, dtype=float)
    npos, nneg = int(lab.sum()), int((~lab).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    o = np.argsort(s, kind="mergesort")
    rk = np.empty(len(s), dtype=float)
    rk[o] = np.arange(1, len(s) + 1, dtype=float)
    ss = s[o]
    i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        if j > i:
            rk[o[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return float((rk[lab].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def summarize2(draws, point):
    """summarize() plus the multiplicity numbers Part 0B.6 registered."""
    s = summarize(draws, point)
    if s.get("sd") is None:
        s["mde_bonferroni_k5"] = None
        s["survives_bonferroni_k5"] = None
        return s
    sd = s["sd"]
    s["mde_bonferroni_k5"] = round(Z99_ONE * sd, 4)
    s["survives_bonferroni_k5"] = bool(abs(s["point_delta"]) >= Z99_ONE * sd)
    s["bonferroni_k"] = BONF_K
    s["verdict"] = ("RESOLVABLE " + ("WIN" if s["point_delta"] > 0 else "LOSS")
                    if s["resolvable"] else "NULL")
    return s


def combined_verdict(e1, e2):
    r1, r2 = bool(e1.get("resolvable")), bool(e2.get("resolvable"))
    if r1 and r2:
        return "RESOLVABLE " + ("WIN" if e1["point_delta"] > 0 else "LOSS")
    if r1 != r2:
        return ("CONTESTED (E1 refit-inclusive %s, E2 fits-fixed %s; E1 governs)"
                % ("resolves" if r1 else "NULL", "resolves" if r2 else "NULL"))
    return "NULL, CLOSED"


# --------------------------------------------------------------- Q4: capture pool
def load_capture():
    """The pool source_backtest.py:641-681 builds its capture curve on, rebuilt from
    first principles so it can be resampled and refit.

    Pool = every eFV-matrix row with a consensus FV that the forward chain scores
    (kind bust + bust_recent dropped, exactly efv_model.oos_grades:881).

    OUTCOME (`cw`): source_backtest gives a row the UNIVERSE's FULL CAREER WAR when the
    player is in timeseries/debuts, and the matrix's first-six-season label otherwise.
    Two different outcome variables in one pool. Reproduced here because the published
    -0.0081 is computed that way; K5 recomputes the delta on one definition.
    """
    import source_backtest as SB
    uni = SB._load_universe(SB.DATA_DIR)
    uni_war = {p.get("player_key"): float(SB._outcome(p)["war"]) for p in uni}
    from efv_dataset import matrix_path
    pools = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
        by_key = {r["player_key"]: r for r in full}
        prep = E._prep(full, "target_censored", side)
        keys, _m = E._feature_spec(side)
        cw, cw_src = [], []
        for r in prep:
            k = r["player_key"]
            if k in uni_war:
                cw.append(uni_war[k])
                cw_src.append(1)                      # universe career WAR
            else:
                m = by_key.get(k) or {}
                t = m.get("target_resolved")
                cw.append(float(t) if t is not None else float(m.get("target_censored") or 0.0))
                cw_src.append(0)                      # matrix first-six-season label
        pools[side] = {
            "side": side, "keys": list(keys),
            "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
            "y": np.array([r["target"] for r in prep], dtype=float),
            "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
            "fv": np.array([r["fv"] for r in prep], dtype=float),
            "dy": np.array([r["decision_year"] for r in prep], dtype=int),
            "cw": np.array(cw, dtype=float),
            "cw_universe": np.array(cw_src, dtype=bool),
            "y6": np.array([r["target"] for r in prep], dtype=float),
            "lam": E.blend_lambda(side),
            "n": len(prep),
        }
    return pools


def cap_pass(P, sel=None):
    """One forward-chained oos_grades pass over both sides, concatenated in the SAME
    order source_backtest sees (side, then cohort year, then pool order), because the
    published statistic sorts with a STABLE sort and that order breaks its ties.

    Mirrors efv_model.oos_grades exactly: full-pool train frame, 15/60 fold floors,
    linear output calibration, model leg floored at -2, consensus leg at 0.
    """
    B, F, W, S, U, Y6 = [], [], [], [], [], []
    for si, side in enumerate(SIDES):
        D = P[side]
        s = np.arange(D["n"]) if sel is None else sel[side]
        X, y, w, fv, dy = D["X"][s], D["y"][s], D["w"][s], D["fv"][s], D["dy"][s]
        cw, cu, y6 = D["cw"][s], D["cw_universe"][s], D["y6"][s]
        lam = D["lam"]
        for yr in E.SCORED_YEARS:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            o = ols_fit(fv[tr], y[tr])
            rg = ridge_fit(X[tr], y[tr], w[tr])
            if o is None or rg is None:
                continue
            cal = E._fit_linear_calibration(
                list(zip(ridge_pred(rg, X[tr]).tolist(), y[tr].tolist())))
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            mod = np.maximum(-2.0, a + b * ridge_pred(rg, X[te]))
            B.append((1 - lam) * cons + lam * mod)
            F.append(fv[te])
            W.append(cw[te])
            U.append(cu[te])
            Y6.append(y6[te])
            S.append(np.full(len(te), si))
    if not B:
        return None
    return {"efv": np.concatenate(B), "cons": np.concatenate(F),
            "war": np.concatenate(W), "side": np.concatenate(S),
            "universe_war": np.concatenate(U), "war6": np.concatenate(Y6)}


def cap_area(score, war, tiebreak=None):
    """source_backtest.py:673-679 `area` and `top20`, vectorized.

    `area` = mean over k of (WAR in the top k) / (total WAR). tiebreak=None reproduces
    the shipped STABLE sort (input order decides inside a tie block); passing an array
    resolves ties by that array instead, which is control K3.
    """
    n = len(score)
    if n < 2:
        return float("nan"), float("nan")
    if tiebreak is None:
        o = np.argsort(-np.asarray(score, dtype=float), kind="stable")
    else:
        o = np.lexsort((np.asarray(tiebreak, dtype=float), -np.asarray(score, dtype=float)))
    ww = np.maximum(0.0, np.asarray(war, dtype=float)[o])
    cum = np.concatenate([[0.0], np.cumsum(ww)])
    tot = cum[-1] or 1.0
    return float(cum[1:].sum() / n / tot), float(cum[max(1, int(round(0.2 * n)))] / tot)


def cap_delta(r, mask=None, warkey="war", tb=None):
    if r is None:
        return float("nan")
    idx = slice(None) if mask is None else mask
    war = r[warkey][idx]
    if len(war) < 30 or np.maximum(0.0, war).sum() <= 0:
        return float("nan")
    t = None if tb is None else tb[idx]
    return cap_area(r["efv"][idx], war, t)[0] - cap_area(r["cons"][idx], war, t)[0]


def capture(B: int = 2000, verbose: bool = True):
    """Q4: the curve_area floor under BOTH estimators."""
    if verbose:
        print(f"=== Q4 capture.curve_area FLOOR (B={B}) ===")
    P = load_capture()
    pt = cap_pass(P)
    n = len(pt["war"])
    a_x, t_x = cap_area(pt["efv"], pt["war"])
    a_c, t_c = cap_area(pt["cons"], pt["war"])
    point = a_x - a_c
    sb = json.loads((ROOT / "data" / "xfv_scoreboard_eval.json").read_text(encoding="utf-8"))
    pub = sb["top20_capture"]
    if verbose:
        print(f"  published  n={pub['pool_n']} efv={pub['curve_area']['efv']} "
              f"cons={pub['curve_area']['consensus']} margin={pub['curve_area']['margin']:+.4f}")
        print(f"  replica    n={n} efv={a_x:.4f} cons={a_c:.4f} margin={point:+.5f}  "
              f"(top20 {t_x:.4f} / {t_c:.4f})")

    # ---- E1 refit-inclusive
    rng = np.random.default_rng(SEED + 400)
    d1 = []
    t0 = time.time()
    for i in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in SIDES}
        d1.append(cap_delta(cap_pass(P, sel)))
        if verbose and (i + 1) % 250 == 0:
            print(f"  E1 {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    e1 = summarize2(d1, point)

    # ---- E2 fits-held-fixed
    rng2 = np.random.default_rng(SEED + 401)
    d2 = []
    for _ in range(B):
        s = rng2.integers(0, n, n)
        sub = {k: pt[k][s] for k in ("efv", "cons", "war")}
        d2.append(cap_area(sub["efv"], sub["war"])[0] - cap_area(sub["cons"], sub["war"])[0])
    e2 = summarize2(d2, point)

    out = {
        "cell": "capture.curve_area",
        "published": {"n": pub["pool_n"], "efv": pub["curve_area"]["efv"],
                      "consensus": pub["curve_area"]["consensus"],
                      "margin": pub["curve_area"]["margin"],
                      "source": "data/xfv_scoreboard_eval.json top20_capture.curve_area"},
        "replica": {"n": n, "efv_area": round(a_x, 5), "consensus_area": round(a_c, 5),
                    "margin": round(point, 5),
                    "efv_top20": round(t_x, 5), "consensus_top20": round(t_c, 5),
                    "gap_vs_published": round(point - pub["curve_area"]["margin"], 6)},
        "e1_refit_inclusive": e1,
        "e2_fits_held_fixed": e2,
        "combined_verdict": combined_verdict(e1, e2),
        "elapsed_s": round(time.time() - t0, 1),
        "B": int(B),
    }
    if verbose:
        for k, lab in (("e1_refit_inclusive", "E1 refit"), ("e2_fits_held_fixed", "E2 fixed")):
            v = out[k]
            print(f"  {lab:<9} delta={v['point_delta']:+.5f} sd={v['sd']} "
                  f"MDE95={v.get('mde95_onesided')} bonf={v.get('mde_bonferroni_k5')} "
                  f"-> {v['verdict']} (|margin|/floor {v.get('margin_over_floor')})")
        print(f"  COMBINED: {out['combined_verdict']}")
    return out


# --------------------------------------------------------------- Q4 controls
def capcontrols(R: int = 400, verbose: bool = True):
    """K1-K6, registered in COHORT_FLOORS.md 0B.4. All six reported whatever they say."""
    if verbose:
        print(f"=== Q4 CONTROLS K1-K6 (R={R}) ===")
    P = load_capture()
    r = cap_pass(P)
    n = len(r["war"])
    war = r["war"]
    tot = float(np.maximum(0.0, war).sum())
    rng = np.random.default_rng(SEED + 500)
    out = {}

    # ---- K1 permutation null
    noinfo = (n + 1) / (2.0 * n)
    perm = [cap_area(rng.permutation(r["efv"]), war)[0] for _ in range(R)]
    permc = [cap_area(rng.permutation(r["cons"]), war)[0] for _ in range(R)]
    out["k1_permutation_null"] = {
        "R": R, "no_information_value_(n+1)/2n": round(noinfo, 5),
        "efv_board_permuted_mean": round(float(np.mean(perm)), 5),
        "efv_board_permuted_sd": round(float(np.std(perm, ddof=1)), 5),
        "consensus_board_permuted_mean": round(float(np.mean(permc)), 5),
        "efv_point_area": round(cap_area(r["efv"], war)[0], 5),
        "abs_gap_to_no_information": round(abs(float(np.mean(perm)) - noinfo), 5),
        "passes": bool(abs(float(np.mean(perm)) - noinfo) < 0.01),
    }

    # ---- K2 exact rank identity
    def ident(score):
        o = np.argsort(-np.asarray(score, dtype=float), kind="stable")
        rank = np.empty(n, dtype=float)
        rank[o] = np.arange(1, n + 1, dtype=float)
        return (n + 1) / n - float((np.maximum(0.0, war) * rank).sum()) / (n * tot), rank
    ia, rank_x = ident(r["efv"])
    ic, rank_c = ident(r["cons"])
    out["k2_rank_identity"] = {
        "statement": "area = (n+1)/n - sum_i war_i * rank_i / (n * total_war)",
        "efv_direct": round(cap_area(r["efv"], war)[0], 9),
        "efv_identity": round(ia, 9),
        "consensus_direct": round(cap_area(r["cons"], war)[0], 9),
        "consensus_identity": round(ic, 9),
        "max_abs_error": round(max(abs(ia - cap_area(r["efv"], war)[0]),
                                   abs(ic - cap_area(r["cons"], war)[0])), 12),
        "passes": bool(max(abs(ia - cap_area(r["efv"], war)[0]),
                           abs(ic - cap_area(r["cons"], war)[0])) < 1e-9),
    }

    # ---- K3 tie-resolution control
    ucn, ccn = np.unique(np.round(r["cons"], 6), return_counts=True)
    uxn, cxn = np.unique(np.round(r["efv"], 9), return_counts=True)
    tb_c = [cap_area(r["cons"], war, rng.random(n))[0] for _ in range(R)]
    tb_x = [cap_area(r["efv"], war, rng.random(n))[0] for _ in range(R)]
    pub_c = cap_area(r["cons"], war)[0]
    pub_x = cap_area(r["efv"], war)[0]
    sd_c = float(np.std(tb_c, ddof=1))
    out["k3_tie_resolution"] = {
        "R": R,
        "consensus_distinct_values": int(len(ucn)),
        "consensus_largest_tie_block": int(ccn.max()),
        "consensus_rows_inside_a_tie": int(ccn[ccn > 1].sum()),
        "efv_distinct_values": int(len(uxn)),
        "efv_largest_tie_block": int(cxn.max()),
        "consensus_area_as_published": round(pub_c, 5),
        "consensus_area_random_tiebreak_mean": round(float(np.mean(tb_c)), 5),
        "consensus_area_random_tiebreak_sd": round(sd_c, 6),
        "consensus_area_random_tiebreak_max": round(float(np.max(tb_c)), 5),
        "consensus_tie_credit": round(pub_c - float(np.mean(tb_c)), 5),
        "consensus_z_vs_random_tiebreak": (round((pub_c - float(np.mean(tb_c))) / sd_c, 2)
                                           if sd_c > 0 else None),
        "efv_area_as_published": round(pub_x, 5),
        "efv_area_random_tiebreak_mean": round(float(np.mean(tb_x)), 5),
        "efv_tie_credit": round(pub_x - float(np.mean(tb_x)), 5),
        "margin_as_published": round(pub_x - pub_c, 5),
        "margin_at_equal_resolution": round(float(np.mean(tb_x)) - float(np.mean(tb_c)), 5),
        "share_of_margin_that_is_tie_credit": round(
            (pub_c - float(np.mean(tb_c))) / abs(pub_x - pub_c), 4) if pub_x != pub_c else None,
    }

    # ---- K4 cross-side pooling
    k4 = {"pooled_margin": round(pub_x - pub_c, 5)}
    for si, side in enumerate(SIDES):
        m = r["side"] == si
        k4[side] = {"n": int(m.sum()),
                    "efv_area": round(cap_area(r["efv"][m], war[m])[0], 5),
                    "consensus_area": round(cap_area(r["cons"][m], war[m])[0], 5),
                    "margin": round(cap_delta(r, m), 5)}
    k4["loss_survives_within_side"] = bool(all(k4[s]["margin"] < 0 for s in SIDES))
    out["k4_cross_side_pooling"] = k4

    # ---- K5 outcome definition
    nu = int(r["universe_war"].sum())
    both = r["universe_war"]
    out["k5_outcome_definition"] = {
        "rows_on_universe_career_war": nu,
        "rows_on_matrix_six_season_label": int(n - nu),
        "corr_career_vs_six_season_on_shared_rows": round(
            float(np.corrcoef(war[both], r["war6"][both])[0, 1]), 4),
        "mean_career_war_on_shared_rows": round(float(war[both].mean()), 3),
        "mean_six_season_label_on_shared_rows": round(float(r["war6"][both].mean()), 3),
        "margin_as_published_mixed_outcome": round(pub_x - pub_c, 5),
        "margin_on_six_season_label_everywhere": round(cap_delta(r, warkey="war6"), 5),
        "loss_survives_single_outcome": bool(cap_delta(r, warkey="war6") < 0),
        # same rows, one variable changed: the universe subpool under each definition
        "universe_rows_only": {
            "n": nu,
            "margin_on_career_war": round(cap_delta(r, both, "war"), 5),
            "margin_on_six_season_label": round(cap_delta(r, both, "war6"), 5),
        },
        # the 2,032 rows the universe does not cover carry a six-season label of exactly
        # zero, every one of them, so they contribute no WAR to either board and act only
        # as rank ballast. Emitted as a number, not a NaN, because NaN is not valid JSON.
        "matrix_rows_only": {
            "n": int(n - nu),
            "total_six_season_war": round(float(np.maximum(0.0, r["war6"][~both]).sum()), 4),
            "total_capture_war_as_published": round(
                float(np.maximum(0.0, war[~both]).sum()), 4),
            "margin_undefined_reason": ("these rows carry zero total WAR under either "
                                        "definition, so a capture curve over them alone "
                                        "has no denominator"),
        },
    }

    # ---- K6 top-reordering
    contrib = np.maximum(0.0, war) * (rank_x - rank_c) / (n * tot)
    dec = np.clip(((rank_c - 1) * 10 // n).astype(int), 0, 9)
    buckets = []
    for d in range(10):
        m = dec == d
        buckets.append({
            "consensus_rank_decile": d + 1,
            "n": int(m.sum()),
            "war_share": round(float(np.maximum(0.0, war[m]).sum() / tot), 4),
            "contribution_to_margin": round(float(-contrib[m].sum()), 5),
            "mean_rank_move_efv_minus_cons": round(float((rank_x[m] - rank_c[m]).mean()), 1),
        })
    order = np.argsort(contrib)[::-1]          # largest positive contrib = worst for eFV
    worst = [{"consensus_rank": int(rank_c[i]), "efv_rank": int(rank_x[i]),
              "war": round(float(war[i]), 2),
              "cost_to_margin": round(float(-contrib[i]), 5)} for i in order[:10]]
    best = [{"consensus_rank": int(rank_c[i]), "efv_rank": int(rank_x[i]),
             "war": round(float(war[i]), 2),
             "gain_to_margin": round(float(-contrib[i]), 5)} for i in order[-10:]]
    hyb = {}
    for q in (0.05, 0.10, 0.20, 0.50):
        cut = max(1, int(round(q * n)))
        # consensus order for the top q%, eFV order below (and the mirror). Ranks are
        # spliced directly, which is exactly what "take this board's order here" means.
        # the board is built as a SCORE, not a rank splice, so the sort is unambiguous
        big = float(n * 10)
        s_top_cons = np.where(rank_c <= cut, big - rank_c, -rank_x)
        s_top_efv = np.where(rank_x <= cut, big - rank_x, -rank_c)
        hyb[f"top{int(q*100)}pct"] = {
            "cut_rows": cut,
            "consensus_top_then_efv_margin": round(
                cap_area(s_top_cons, war)[0] - cap_area(r["cons"], war)[0], 5),
            "efv_top_then_consensus_margin": round(
                cap_area(s_top_efv, war)[0] - cap_area(r["cons"], war)[0], 5),
        }
    top_deciles = sum(b["contribution_to_margin"] for b in buckets[:2])
    out["k6_top_reordering"] = {
        "hypothesis": ("eFV re-orders the TOP of the board in a way that helps rank "
                       "correlation and hurts value capture"),
        "identity": "margin = -(1/(n*tot)) * sum_i war_i * (rank_efv_i - rank_cons_i)",
        "attribution_sums_to_margin": round(float(-contrib.sum()), 5),
        "by_consensus_rank_decile": buckets,
        "top_two_deciles_contribution": round(top_deciles, 5),
        "top_two_deciles_share_of_margin": round(top_deciles / (pub_x - pub_c), 4),
        "worst_10_rows_for_efv": worst,
        "best_10_rows_for_efv": best,
        "worst_10_rows_share_of_margin": round(
            sum(w["cost_to_margin"] for w in worst) / (pub_x - pub_c), 4),
        "hybrid_boards": hyb,
    }
    if verbose:
        k = out["k1_permutation_null"]
        print(f"  K1 permuted eFV board area {k['efv_board_permuted_mean']} vs "
              f"no-info {k['no_information_value_(n+1)/2n']} -> "
              f"{'PASS' if k['passes'] else 'FAIL'}")
        print(f"  K2 rank identity max err {out['k2_rank_identity']['max_abs_error']} -> "
              f"{'PASS' if out['k2_rank_identity']['passes'] else 'FAIL'}")
        k = out["k3_tie_resolution"]
        print(f"  K3 consensus has {k['consensus_distinct_values']} distinct values, "
              f"{k['consensus_rows_inside_a_tie']} of {n} rows inside a tie block "
              f"(largest {k['consensus_largest_tie_block']})")
        print(f"     consensus area {k['consensus_area_as_published']} published vs "
              f"{k['consensus_area_random_tiebreak_mean']} at random tie-break "
              f"(z={k['consensus_z_vs_random_tiebreak']}); margin "
              f"{k['margin_as_published']:+.5f} -> {k['margin_at_equal_resolution']:+.5f}")
        k = out["k4_cross_side_pooling"]
        print(f"  K4 within-side margins: hit {k['hit']['margin']:+.5f} (n={k['hit']['n']}), "
              f"pit {k['pit']['margin']:+.5f} (n={k['pit']['n']}); "
              f"survives within side: {k['loss_survives_within_side']}")
        k = out["k5_outcome_definition"]
        print(f"  K5 {k['rows_on_universe_career_war']} rows on CAREER WAR, "
              f"{k['rows_on_matrix_six_season_label']} on the 6-season label; margin on one "
              f"definition {k['margin_on_six_season_label_everywhere']:+.5f}")
        u = k["universe_rows_only"]
        print(f"     universe rows alone (n={u['n']}): career WAR "
              f"{u['margin_on_career_war']:+.5f} vs 6-season label "
              f"{u['margin_on_six_season_label']:+.5f}")
        k = out["k6_top_reordering"]
        print(f"  K6 attribution sums to {k['attribution_sums_to_margin']:+.5f} "
              f"(margin {pub_x - pub_c:+.5f}); top two consensus deciles carry "
              f"{k['top_two_deciles_share_of_margin']:.0%} of it")
        for b in k["by_consensus_rank_decile"]:
            print(f"     decile {b['consensus_rank_decile']:>2} n={b['n']:<4} "
                  f"war_share={b['war_share']:.3f} contrib={b['contribution_to_margin']:+.5f} "
                  f"mean_move={b['mean_rank_move_efv_minus_cons']:+.1f}")
        for q, v in k["hybrid_boards"].items():
            print(f"     hybrid {q:<10} consensus-top-then-efv {v['consensus_top_then_efv_margin']:+.5f}"
                  f"   efv-top-then-consensus {v['efv_top_then_consensus_margin']:+.5f}")
    return out


# --------------------------------------------------------------- Q4 coverage gate
def capcov(S: int = 100, B: int = 200, n: int = 900, verbose: bool = True):
    """Nominal coverage check for the CAPTURE-AREA bootstrap, two-sided per 0B.5.

    Same synthetic null as wave 1's nullcov (model features are noisy copies of the
    consensus column, so the model carries no information the consensus lacks), with
    the capture-area delta substituted for the rank delta. Registered pass band:
    coverage_95 >= 0.90 AND sd_ratio_boot_over_true <= 1.60.
    """
    if verbose:
        print(f"=== Q4 COVERAGE GATE (S={S} datasets, B={B}, n={n}) ===")
    k, nyr = 4, 6
    years = tuple(range(2014, 2014 + nyr))
    rng = np.random.default_rng(SEED + 600)

    def make(seed):
        g = np.random.default_rng(seed)
        fv = np.round(g.normal(45, 5, n) / 5) * 5
        y = np.maximum(0.0, 0.35 * (fv - 40) + g.normal(0, 3.0, n))
        X = np.column_stack([fv + g.normal(0, 4.0, n) for _ in range(k)])
        return {"one": {"X": X, "y": y, "w": np.ones(n), "fv": fv,
                        "dy": g.integers(2014, 2014 + nyr, n),
                        "cw": y, "cw_universe": np.zeros(n, dtype=bool), "y6": y,
                        "lam": 0.7, "n": n}}

    def one(D, sel=None):
        # cap_pass with a single synthetic side and the synthetic fold calendar
        P = D
        Bv, F, W = [], [], []
        Dd = P["one"]
        s = np.arange(n) if sel is None else sel["one"]
        X, y, w, fv, dy = Dd["X"][s], Dd["y"][s], Dd["w"][s], Dd["fv"][s], Dd["dy"][s]
        cw = Dd["cw"][s]
        for yr in years:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 12 or len(tr) < 50:
                continue
            o = ols_fit(fv[tr], y[tr])
            rg = ridge_fit(X[tr], y[tr], w[tr])
            if o is None or rg is None:
                continue
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            mod = ridge_pred(rg, X[te])
            Bv.append((1 - Dd["lam"]) * cons + Dd["lam"] * mod)
            F.append(fv[te])
            W.append(cw[te])
        if not Bv:
            return float("nan")
        b, f, ww = np.concatenate(Bv), np.concatenate(F), np.concatenate(W)
        return cap_area(b, ww)[0] - cap_area(f, ww)[0]

    pts = [one(make(SEED + 2000 + s)) for s in range(S)]
    truth = float(np.nanmean(pts))
    sd_true = float(np.nanstd(pts, ddof=1))
    n_check = min(40, S)
    cov, sds = 0, []
    for s in range(n_check):
        D = make(SEED + 2000 + s)
        d = [one(D, {"one": rng.integers(0, n, n)}) for _ in range(B)]
        a = np.array(d, dtype=float)
        a = a[np.isfinite(a)]
        sds.append(float(a.std(ddof=1)))
        lo, hi = np.percentile(a, 2.5), np.percentile(a, 97.5)
        if lo <= truth <= hi:
            cov += 1
    ratio = float(np.mean(sds)) / sd_true if sd_true > 0 else None
    out = {
        "design": {"S_datasets": S, "B": B, "n_rows": n, "k_features": k, "folds": nyr,
                   "statistic": "capture curve_area delta (eFV board minus consensus board)",
                   "null": "model features are noisy copies of the consensus column"},
        "true_mean_delta": round(truth, 5),
        "true_sampling_sd": round(sd_true, 5),
        "mean_bootstrap_sd": round(float(np.mean(sds)), 5),
        "sd_ratio_boot_over_true": round(ratio, 3) if ratio else None,
        "coverage_95": round(cov / n_check, 3),
        "n_checked": n_check,
        "registered_band": {"coverage_95_min": 0.90, "sd_ratio_max": 1.60,
                            "source": "COHORT_FLOORS.md 0B.5"},
    }
    out["passes_undercoverage_guard"] = bool(out["coverage_95"] >= 0.90)
    out["passes_overwidth_guard"] = bool(ratio is not None and ratio <= 1.60)
    out["verdict"] = ("PASS" if out["passes_undercoverage_guard"] and out["passes_overwidth_guard"]
                      else ("FAIL LOW, no floor quotable" if not out["passes_undercoverage_guard"]
                            else "OVER-WIDE, NULLs downgraded"))
    if verbose:
        print(f"  truth {truth:+.5f} sd {sd_true:.5f}; boot sd {np.mean(sds):.5f} "
              f"(ratio {out['sd_ratio_boot_over_true']}), coverage {out['coverage_95']:.0%} "
              f"-> {out['verdict']}")
    return out


# --------------------------------------------------------------- Q5a: era AUC cell
def eracells(B: int = 2000, verbose: bool = True):
    """pit.era.<=2018 auc_contributor: the one never-floored cell that lives on the
    scoreboard's own era chain, so it gets the same refit-inclusive treatment wave 1
    gave the spearman cells."""
    if verbose:
        print(f"=== Q5a pit.era.<=2018 auc_contributor FLOOR (B={B}) ===")
    ERA_YEARS = tuple(range(2016, 2024))
    CONTRIB = 3.0                # xfv_scoreboard_eval.json protocol.labels.contributor_war
    D = load_cellpool("pit")

    def _run(sel=None):
        return chain(D, sel, years=ERA_YEARS, min_train=60, min_test=10, extra=("coh", "tier"))

    def _auc_delta(r):
        if r is None:
            return float("nan"), 0, (float("nan"), float("nan"))
        m = np.array([LAB._era(int(y)) == "<=2018" for y in r["yr"]], dtype=bool)
        if m.sum() < 20:
            return float("nan"), int(m.sum()), (float("nan"), float("nan"))
        lab = r["y"][m] >= CONTRIB
        if lab.all() or (~lab).all():
            return float("nan"), int(m.sum()), (float("nan"), float("nan"))
        ab = auc_of(r["blend"][m], lab)
        ac = auc_of(r["cons"][m], lab)
        return ab - ac, int(m.sum()), (ab, ac)

    pt = _run()
    point, n_cell, legs = _auc_delta(pt)
    rng = np.random.default_rng(SEED + 700)
    d1 = []
    t0 = time.time()
    for i in range(B):
        d1.append(_auc_delta(_run(rng.integers(0, D["n"], D["n"])))[0])
        if verbose and (i + 1) % 250 == 0:
            print(f"  E1 {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    e1 = summarize2(d1, point)

    m = np.array([LAB._era(int(y)) == "<=2018" for y in pt["yr"]], dtype=bool)
    cb, cc, cy = pt["blend"][m], pt["cons"][m], pt["y"][m]
    rng2 = np.random.default_rng(SEED + 701)
    d2 = []
    for _ in range(B):
        s = rng2.integers(0, n_cell, n_cell)
        lab = cy[s] >= CONTRIB
        d2.append(auc_of(cb[s], lab) - auc_of(cc[s], lab) if lab.any() and not lab.all()
                  else float("nan"))
    e2 = summarize2(d2, point)
    out = {
        "cell": "pit.era.<=2018", "metric": "auc_contributor",
        "published": {"n": 132, "efv": 0.774, "consensus": 0.7841, "margin": -0.0101,
                      "source": "data/xfv_scoreboard_eval.json weak_cells"},
        "replica": {"n": n_cell, "efv": round(legs[0], 5), "consensus": round(legs[1], 5),
                    "margin": round(point, 5), "n_contributor": int((cy >= CONTRIB).sum())},
        "e1_refit_inclusive": e1, "e2_fits_held_fixed": e2,
        "combined_verdict": combined_verdict(e1, e2),
        "B": int(B), "elapsed_s": round(time.time() - t0, 1),
    }
    if verbose:
        print(f"  replica n={n_cell} efv={legs[0]:.4f} cons={legs[1]:.4f} margin={point:+.5f}")
        for k, lab in (("e1_refit_inclusive", "E1 refit"), ("e2_fits_held_fixed", "E2 fixed")):
            v = out[k]
            print(f"  {lab:<9} sd={v.get('sd')} MDE95={v.get('mde95_onesided')} "
                  f"bonf={v.get('mde_bonferroni_k5')} -> {v['verdict']}")
        print(f"  COMBINED: {out['combined_verdict']}")
    return out


# --------------------------------------------------------------- Q5b: archetype cells
ARCH_CELLS = ("hs_bat", "hs_arm", "college_arm")


def load_arch():
    """The archetype pool the scoreboard's head_to_head.archetype cells sit on.

    source_backtest.py:740-750 scores archetypes on ONE ROW PER PLAYER, the latest
    PRE-DEBUT read on which every scored source plus the consensus graded him. Rebuilt
    here so the eFV matrix pool underneath can be resampled and refit, which is what
    wave 1's sqrt(n) LOWER BOUND could not do.
    """
    import source_backtest as SB
    uni = SB._load_universe(SB.DATA_DIR)
    years = SB._resolved_years(uni, SB.date.today().year)
    raters = list(SB.SCORED_SOURCES) + [SB.CONSENSUS_KEY]
    latest = {}
    for p in uni:
        k = p.get("player_key")
        if k is None:
            continue
        out = SB._outcome(p)
        arch = SB._archetype(p)
        if arch is None:
            continue
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if not (g and all(rr in g for rr in raters)):
                continue
            dy = out.get("debut_year")
            if dy is not None and y > dy:
                continue
            if k not in latest or y > latest[k]["year"]:
                latest[k] = {"year": y, "cons": float(g[SB.CONSENSUS_KEY]),
                             "war": float(out["war"]),
                             "contrib": bool(out["contributor"]), "arch": arch}
    from efv_dataset import matrix_path
    pools = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
        prep = E._prep(full, "target_censored", side)
        keys, _m = E._feature_spec(side)
        pools[side] = {
            "side": side, "keys": list(keys),
            "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
            "y": np.array([r["target"] for r in prep], dtype=float),
            "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
            "fv": np.array([r["fv"] for r in prep], dtype=float),
            "dy": np.array([r["decision_year"] for r in prep], dtype=int),
            "arch": [latest.get(r["player_key"]) for r in prep],
            "lam": E.blend_lambda(side),
            "n": len(prep),
        }
    return pools, len(latest)


def arch_pass(P, sel=None):
    """One forward-chained oos_grades pass, scored on the archetype rows the resampled
    players own. Mirrors efv_mde_lab._h2h_pass."""
    G, C, W, L, A = [], [], [], [], []
    for side in SIDES:
        D = P[side]
        s = np.arange(D["n"]) if sel is None else sel[side]
        X, y, w, fv, dy = D["X"][s], D["y"][s], D["w"][s], D["fv"][s], D["dy"][s]
        rows = [D["arch"][i] for i in s]
        lam = D["lam"]
        for yr in E.SCORED_YEARS:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            o = ols_fit(fv[tr], y[tr])
            rg = ridge_fit(X[tr], y[tr], w[tr])
            if o is None or rg is None:
                continue
            cal = E._fit_linear_calibration(
                list(zip(ridge_pred(rg, X[tr]).tolist(), y[tr].tolist())))
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            mod = np.maximum(-2.0, a + b * ridge_pred(rg, X[te]))
            grade = (1 - lam) * cons + lam * mod
            for j, i in enumerate(te):
                rr = rows[i]
                if rr is None:
                    continue
                G.append(grade[j])
                C.append(rr["cons"])
                W.append(rr["war"])
                L.append(rr["contrib"])
                A.append(rr["arch"])
    if not G:
        return None
    return {"efv": np.array(G), "cons": np.array(C), "war": np.array(W),
            "lab": np.array(L, dtype=bool), "arch": np.array(A, dtype=object)}


def archcells(B: int = 1200, verbose: bool = True):
    """Q5b: a REAL cluster paired bootstrap for the three archetype cells, both metrics.

    This replaces wave 1's sqrt(n_pool / n_cell) LOWER BOUND, which was a rescale of a
    different instrument's SPEARMAN floor and could not touch the AUC rows at all.
    """
    if verbose:
        print(f"=== Q5b ARCHETYPE CELLS, real cluster bootstrap (B={B}) ===")
    P, n_players = load_arch()
    pt = arch_pass(P)
    sb = json.loads((ROOT / "data" / "xfv_scoreboard_eval.json").read_text(encoding="utf-8"))
    pub = {}
    for c in sb["weak_cells"]:
        if c["cell"].startswith("head_to_head.archetype."):
            pub[(c["cell"].split(".")[-1], c["metric"])] = c

    def stats(r, arch):
        m = r["arch"] == arch
        if m.sum() < 20:
            return None
        lab = r["lab"][m]
        if lab.all() or (~lab).all():
            return None
        return {
            "n": int(m.sum()),
            "auc_efv": auc_of(r["efv"][m], lab), "auc_cons": auc_of(r["cons"][m], lab),
            "rho_efv": wrho(r["efv"][m], r["war"][m], None),
            "rho_cons": wrho(r["cons"][m], r["war"][m], None),
        }

    point = {a: stats(pt, a) for a in ARCH_CELLS}
    rng = np.random.default_rng(SEED + 800)
    draws = {(a, m): [] for a in ARCH_CELLS for m in ("auc", "rho")}
    t0 = time.time()
    for i in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in SIDES}
        r = arch_pass(P, sel)
        for a in ARCH_CELLS:
            st = stats(r, a) if r is not None else None
            draws[(a, "auc")].append(st["auc_efv"] - st["auc_cons"] if st else float("nan"))
            draws[(a, "rho")].append(st["rho_efv"] - st["rho_cons"] if st else float("nan"))
        if verbose and (i + 1) % 200 == 0:
            print(f"  E1 {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)

    out = {"basis": {"archetype_players_with_all_sources": n_players,
                     "protocol": ("one row per player, latest PRE-DEBUT all-source common "
                                  "read (source_backtest.py:740-750); cluster paired "
                                  "bootstrap resampling the eFV matrix pool and refitting "
                                  "the forward chain on every draw"),
                     "replica_note": ("the published eFV leg is rounded to 0.1 FV by the "
                                      "display remap at source_backtest.py:588, which adds "
                                      "ties; this replica uses the raw OOS score, so the "
                                      "replica eFV leg runs 0.002-0.003 HIGH")}}
    for a in ARCH_CELLS:
        st = point[a]
        cell = {}
        for mi, (metric, key_e, key_c, mkey) in enumerate(
                (("auc_contributor", "auc_efv", "auc_cons", "auc"),
                 ("spearman", "rho_efv", "rho_cons", "rho"))):
            p = float(st[key_e] - st[key_c])
            e1 = summarize2(draws[(a, mkey)], p)
            # E2: fits fixed, resample the cell's own rows
            m = pt["arch"] == a
            ee, cc, ww, ll = pt["efv"][m], pt["cons"][m], pt["war"][m], pt["lab"][m]
            nn = int(m.sum())
            # deterministic offset. Python string hashing is randomized per process
            # (PYTHONHASHSEED), so seeding off it made this block irreproducible.
            rng2 = np.random.default_rng(SEED + 810 + ARCH_CELLS.index(a) * 10 + mi)
            d2 = []
            for _ in range(B):
                s = rng2.integers(0, nn, nn)
                if mkey == "auc":
                    lb = ll[s]
                    d2.append(auc_of(ee[s], lb) - auc_of(cc[s], lb)
                              if lb.any() and not lb.all() else float("nan"))
                else:
                    d2.append(wrho(ee[s], ww[s], None) - wrho(cc[s], ww[s], None))
            e2 = summarize2(d2, p)
            pb = pub.get((a, metric))
            cell[metric] = {
                "published": ({"n": pb["n"], "efv": pb["efv"], "consensus": pb["consensus"],
                               "margin": pb["margin"]} if pb else None),
                "replica": {"n": st["n"], "efv": round(float(st[key_e]), 5),
                            "consensus": round(float(st[key_c]), 5), "margin": round(p, 5)},
                "e1_refit_inclusive": e1, "e2_fits_held_fixed": e2,
                "combined_verdict": combined_verdict(e1, e2),
            }
            if verbose:
                pm = pb["margin"] if pb else float("nan")
                print(f"  {a:<12} {metric:<16} n={st['n']:<4} pub={pm:+.4f} "
                      f"replica={p:+.5f} E1 MDE95={e1.get('mde95_onesided')} "
                      f"E2 MDE95={e2.get('mde95_onesided')} -> {cell[metric]['combined_verdict']}")
        out[a] = cell
    out["selection_control"] = arch_selection_control(pt, point)
    out["_B"] = int(B)
    out["_elapsed_s"] = round(time.time() - t0, 1)
    return out


def arch_selection_control(pt, point, R: int = 4000, verbose: bool = True):
    """UNREGISTERED CONTROL, added after the run because one cell resolved (rule D).

    Eight archetype statistics were tested and exactly one clears its own floor. The
    dumbest explanation for one clearing cell out of eight is SELECTION: a cell of that
    size, drawn at random from the same board, would produce a margin at least that
    large some of the time. This draws random subsets of the SAME size, without
    replacement, from all six archetypes on the same fixed fits, and asks how often.

    This control can only weaken the lane's single positive finding. That is the point.
    """
    rng = np.random.default_rng(SEED + 900)
    n = len(pt["war"])
    res = {"pool_rows_all_archetypes": int(n),
           "note": ("UNREGISTERED, added after the run; it can only weaken the one "
                    "resolvable cell, never strengthen it"),
           "whole_pool_auc_delta": round(float(
               auc_of(pt["efv"], pt["lab"]) - auc_of(pt["cons"], pt["lab"])), 5)}
    for a in ARCH_CELLS:
        st = point[a]
        if st is None:
            continue
        k = st["n"]
        obs = float(st["auc_efv"] - st["auc_cons"])
        d = []
        for _ in range(R):
            s = rng.choice(n, size=k, replace=False)
            lb = pt["lab"][s]
            if lb.all() or (~lb).all():
                continue
            d.append(auc_of(pt["efv"][s], lb) - auc_of(pt["cons"][s], lb))
        arr = np.array(d, dtype=float)
        res[a] = {
            "cell_n": k, "observed_auc_delta": round(obs, 5),
            "random_subset_mean": round(float(arr.mean()), 5),
            "random_subset_sd": round(float(arr.std(ddof=1)), 5),
            "share_of_random_subsets_at_least_this_negative": round(
                float((arr <= obs).mean()), 4),
            "share_at_least_this_extreme_either_side": round(
                float((np.abs(arr - arr.mean()) >= abs(obs - arr.mean())).mean()), 4),
        }
        if verbose:
            v = res[a]
            print(f"  SELECTION {a:<12} n={k:<4} observed {obs:+.5f}; random {k}-row subsets "
                  f"mean {v['random_subset_mean']:+.5f} sd {v['random_subset_sd']:.5f}; "
                  f"{v['share_of_random_subsets_at_least_this_negative']:.1%} at least this negative")
    return res


# --------------------------------------------------------------- wave 2 driver
def waveb(B: int = 2000):
    """Run Q4 + Q5 and MERGE into the existing wave-1 ledger.

    Merge, not rewrite: wave 1's blocks cost 209s and are not this lane's to re-derive.
    The one wave-1 block this lane does touch is `i5_archetype_bounds`, which gets a
    LOWER BOUND label stamped into every row (brief requirement) and a pointer to the
    real bootstrap that supersedes it.
    """
    t0 = time.time()
    cov = capcov()
    print()
    if cov["verdict"].startswith("FAIL LOW"):
        print("COVERAGE FAILED LOW: capture floors will be written but flagged unquotable.")
    q4 = capture(B)
    print()
    ctl = capcontrols()
    print()
    q5a = eracells(B)
    print()
    q5b = archcells(max(600, B // 2))
    print()
    old = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    ab = old.get("i5_archetype_bounds") or {}
    for k, v in ab.items():
        if k == "basis":
            v["floor_kind"] = "LOWER BOUND (sqrt-n rescale of a different instrument, NO bootstrap)"
            v["superseded_by"] = "waveb_q5b_archetype_cells (real cluster paired bootstrap)"
            continue
        if isinstance(v, dict):
            v["floor_kind"] = "LOWER BOUND (NO bootstrap was run for this cell in wave 1)"
            v["floor_lower_bound_label"] = "LOWER BOUND, admissible only to CLOSE a cell"
            v["superseded_by"] = "waveb_q5b_archetype_cells"

    # Wave 1 asserted its sqrt(n) number was a LOWER BOUND on the true cell floor.
    # Q5b measured those same floors directly, so the claim is now checkable.
    bc = {"claim": ("COHORT_FLOORS.md 0.2 item 2: sqrt(n_pool/n_cell) rescaling ignores "
                    "refit and composition variance, so it is a LOWER BOUND on the cell floor"),
          "test": "compare it to the measured E1 refit-inclusive spearman floor for the same cell"}
    for a in ARCH_CELLS:
        cellk = "head_to_head.archetype." + a
        lb = (ab.get(cellk) or {}).get("floor_lower_bound")
        real = (((q5b.get(a) or {}).get("spearman") or {}).get("e1_refit_inclusive") or {}
                ).get("mde95_onesided")
        if lb is None or real is None:
            continue
        bc[cellk] = {"wave1_claimed_lower_bound": lb, "measured_e1_floor": real,
                     "bound_over_measured": round(lb / real, 2),
                     "is_actually_a_lower_bound": bool(lb <= real)}
    bc["verdict"] = ("the sqrt(n) bound is NOT a lower bound; it OVERSTATES the measured "
                     "floor, which is the permissive direction for a NULL"
                     if any(isinstance(v, dict) and v.get("is_actually_a_lower_bound") is False
                            for v in bc.values())
                     else "the sqrt(n) bound held as a lower bound")

    old["waveb"] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_cohort_floor_lab.py waveb",
        "lane": "wave 2 Lane B: the five weak_cells rows wave 1 never floored",
        "registration": "docs/efv-2026-08-07b/COHORT_FLOORS.md PART 0B "
                        "(written in full before this code existed)",
        "correction_to_wave_1": ("Part 6 row I5-a says 'eleven weak cells ... ALL NULL, ALL "
                                 "CLOSED'. weak_cells has SIXTEEN rows. Five had no floor of "
                                 "any kind and are floored here."),
        "estimators": {
            "e1_refit_inclusive": ("the shipped gate protocol: whole per-side pool resampled, "
                                   "consensus OLS + weighted ridge + linear output calibration "
                                   "refit on every draw. GOVERNS the verdict."),
            "e2_fits_held_fixed": "shipped OOS grades frozen, scored rows resampled only.",
            "note": "the two can disagree; a disagreement is reported as CONTESTED, not resolved.",
        },
        "multiplicity": {"k_cells": BONF_K, "bonferroni_one_sided_z": Z99_ONE,
                         "rule": "every cell carries mde_bonferroni_k5 and a survives flag"},
        "seed": SEED,
        "coverage_gate": cov,
        "q4_capture_curve_area": q4,
        "q4_controls": ctl,
        "q5a_pit_era_auc": q5a,
        "q5b_archetype_cells": q5b,
        "wave1_sqrt_bound_check": bc,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(old, indent=1), encoding="utf-8")
    print("wrote", OUT_PATH)
    return old["waveb"]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "repro"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if mode == "repro":
        repro()
    elif mode == "carveout":
        carveout()
    elif mode == "mechanism":
        mechanism()
    elif mode == "ties":
        ties()
    elif mode == "cost":
        cost()
    elif mode == "nullcov":
        nullcov(arg or 120)
    elif mode == "fullpool":
        fullpool(arg or 600)
    elif mode == "cells":
        cells(arg or 600)
    elif mode == "arch":
        archetype_bounds()
    elif mode == "all":
        run_all(arg or 600)
    elif mode == "capture":
        capture(arg or 2000)
    elif mode == "capcontrols":
        capcontrols(arg or 400)
    elif mode == "capcov":
        capcov(arg or 100)
    elif mode == "eracells":
        eracells(arg or 2000)
    elif mode == "archcells":
        archcells(arg or 1200)
    elif mode == "waveb":
        waveb(arg or 2000)
    else:
        print(__doc__ or "unknown mode")


if __name__ == "__main__":
    main()

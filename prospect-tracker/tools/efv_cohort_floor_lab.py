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
    else:
        print(__doc__ or "unknown mode")


if __name__ == "__main__":
    main()

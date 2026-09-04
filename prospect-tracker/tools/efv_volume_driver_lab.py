# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""VOLUME AND CUMULATIVE-STAT eFV DRIVERS: the owner's 2026-09-04 ask, swept and gated.

The question as asked: "what amount of players who hit 200+ hits in a single Minor League
season went on to be stars/superstars? -> 200+ hits eFV driver. Sweep and check for all
examples or combinations of cumulative stats that could potentially correlate."

So this lab does two separate things and never lets one borrow the other's authority.

PART 1, DESCRIPTIVE. For every threshold candidate it reports support, the star rate, the
bust rate and the mean label inside and outside the cell. That answers the question
literally. It is NOT evidence that the feature belongs in the model: the pool is already
selected on consensus FV, so a cell can look excellent purely because good prospects get
more playing time, which is the confound the whole family is exposed to.

PART 2, GATED. Every candidate is added to the SHIPPED feature set and scored as an
incremental forward-chained pooled-rho margin against the incumbent, under
docs/EFV_GATE_STANDARD.md: E_cond primary with E_refit beside it, a permutation null, the
per-fold signs, and Holm across the whole sweep because this is a many-cell search. A
candidate ships only if it clears its own floor after Holm. Nothing here ships anything;
the artifact is the record.

WHY THIS FAMILY IS NOT THE CLOSED ONE. The do-not-reopen ledger closes 39 feature arms
(26 free `_vec` keys, 13 `_extras` arms), all of them RATE or TOOL features. Volume is a
different quantity: a rate says how well a player performed, a volume says how much
opportunity he converted, and durability plus organizational trust are real signals that
no rate carries. The standing rule "do not open a third feature lane without new labels"
is also satisfied rather than dodged: the eWAR label epoch (2026-09-04) replaced the
label, which is the registered condition for re-sweeping.

LEAKAGE. The season eligibility rule is mirrored from efv_dataset._milb_features, cutoff
repair included: a season is readable only once the decision date is at or after Oct 1 of
that year, because MiLB regular seasons end in September. Getting this wrong is what made
P(bust | milb_season == cutoff year) 95.6 percent in the 2026-07-24 audit. MLB rows are
excluded; this is a MINOR league volume family.

Run:
    python tools/efv_volume_driver_lab.py                 # both parts, both sides
    python tools/efv_volume_driver_lab.py --describe-only # part 1 only, fast
    python tools/efv_volume_driver_lab.py --side hit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds                    # noqa: E402  READ ONLY
import efv_model as E                       # noqa: E402  READ ONLY
import milb_history as mh                   # noqa: E402  READ ONLY

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_volume_driver_eval.json"
SEED = 20260807
SIDES = ("hit", "pit")

# Label cuts for the descriptive part. first-6yr WAR, the shipped label.
STAR_WAR = 10.0        # ~2 WAR/yr over the window: a good regular or better
SUPERSTAR_WAR = 20.0
BUST_WAR = 0.5


# ------------------------------------------------------------------ eligible seasons
def eligible_seasons(mlbam: int | None, decision_year: int, cutoff: str | None,
                     group: str) -> list[dict]:
    """Every MiLB season row readable at the decision point, newest first.

    Mirrors efv_dataset._milb_features exactly, including the AS-OF REPAIR: a season is
    only readable once the decision date is at or after Oct 1 of that year. Deviating
    from this is the documented way to manufacture a label proxy.
    """
    if not mlbam:
        return []
    first_season = decision_year - 1
    if cutoff:
        try:
            _cy, _cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
            first_season = min(first_season, _cy if _cm >= 10 else _cy - 1)
        except (ValueError, IndexError):
            pass
    out = []
    for season in range(first_season, 2013, -1):
        rows = [r for r in (mh.player_index(season, group).get(int(mlbam)) or [])
                if r.get("level") != "MLB"]
        if rows:
            out.append({"season": season, "rows": rows})
    return out


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def volumes(seasons: list[dict], side: str) -> dict:
    """Career-to-date totals and single-season maxima, summed across levels in a season."""
    per_season = []
    for s in seasons:
        agg: dict[str, float] = {}
        for r in s["rows"]:
            if side == "pit":
                agg["ip"] = agg.get("ip", 0.0) + _f(r.get("ip"))
                agg["so"] = agg.get("so", 0.0) + _f(r.get("so"))
                agg["bb"] = agg.get("bb", 0.0) + _f(r.get("bb"))
                agg["bf"] = agg.get("bf", 0.0) + _f(r.get("bf"))
                agg["g"] = agg.get("g", 0.0) + _f(r.get("g") or r.get("games"))
            else:
                for k in ("pa", "ab", "h", "hr", "sb", "bb", "so", "doubles", "triples"):
                    agg[k] = agg.get(k, 0.0) + _f(r.get(k))
        if side == "hit":
            agg["xbh"] = agg.get("doubles", 0.0) + agg.get("triples", 0.0) + agg.get("hr", 0.0)
            singles = agg.get("h", 0.0) - agg["xbh"]
            agg["tb"] = (singles + 2 * agg.get("doubles", 0.0) + 3 * agg.get("triples", 0.0)
                         + 4 * agg.get("hr", 0.0))
        per_season.append(agg)
    out: dict[str, float] = {"milb_seasons": float(len(per_season))}
    keys = (("ip", "so", "bb", "bf", "g") if side == "pit"
            else ("pa", "ab", "h", "hr", "sb", "bb", "so", "xbh", "tb"))
    for k in keys:
        vals = [a.get(k, 0.0) for a in per_season]
        out[f"career_{k}"] = float(sum(vals))
        out[f"max_{k}"] = float(max(vals)) if vals else 0.0
    return out


# ------------------------------------------------------------------ the candidate grid
def candidates(side: str) -> list[dict]:
    """Each candidate is a named function of the volume dict -> float."""
    C: list[dict] = []

    def add(name, fn, kind, why):
        C.append({"name": name, "fn": fn, "kind": kind, "why": why})

    # THE MISSINGNESS CONTROL, and it is first on purpose. About 31 percent of hitter rows
    # have no readable MiLB season at the decision point, and every volume feature reads
    # 0.0 for them. Since career volume turns out to correlate NEGATIVELY with the label, a
    # missing row is scored as if it were a fast-moving low-volume prospect, so missingness
    # alone could produce the whole family's signal. This indicator is swept beside the
    # volume features so the artifact can say which of the two is doing the work; the
    # ledger's rule that full-pool AUC is inadmissible for missingness-sensing candidates
    # is the same lesson in a different place.
    add("milb_readable", (lambda v: 1.0 if v["milb_seasons"] > 0 else 0.0), "control",
        "CONTROL: does the row have any readable MiLB season at all")

    if side == "hit":
        for t in (120, 140, 160, 180, 200):
            add(f"max_h_ge_{t}", (lambda v, t=t: 1.0 if v["max_h"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ hits")
        for t in (15, 20, 25, 30, 35):
            add(f"max_hr_ge_{t}", (lambda v, t=t: 1.0 if v["max_hr"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ home runs")
        for t in (20, 30, 40, 50):
            add(f"max_sb_ge_{t}", (lambda v, t=t: 1.0 if v["max_sb"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ steals")
        for t in (400, 500, 550):
            add(f"max_pa_ge_{t}", (lambda v, t=t: 1.0 if v["max_pa"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ plate appearances (durability and trust)")
        for t in (250, 300):
            add(f"max_tb_ge_{t}", (lambda v, t=t: 1.0 if v["max_tb"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ total bases")
        for t in (1000, 1500, 2000):
            add(f"career_pa_ge_{t}", (lambda v, t=t: 1.0 if v["career_pa"] >= t else 0.0),
                "threshold", f"{t}+ career MiLB plate appearances before the decision")
        for k in ("max_h", "max_hr", "max_sb", "max_pa", "max_tb", "max_xbh",
                  "career_h", "career_hr", "career_sb", "career_pa", "career_tb",
                  "milb_seasons"):
            add(k, (lambda v, k=k: float(v[k])), "continuous", f"{k} as a level")
        add("hr_per_500pa_peak",
            (lambda v: 500.0 * v["max_hr"] / v["max_pa"] if v["max_pa"] >= 200 else 0.0),
            "derived", "peak power VOLUME normalised to a full season, zero when thin")
        add("pwr_and_playing_time",
            (lambda v: 1.0 if (v["max_hr"] >= 25 and v["max_pa"] >= 500) else 0.0),
            "combination", "25+ HR AND 500+ PA in the same season: the gated combination")
        add("hits_and_speed",
            (lambda v: 1.0 if (v["max_h"] >= 140 and v["max_sb"] >= 30) else 0.0),
            "combination", "140+ hits AND 30+ steals in one season")
    else:
        for t in (100, 130, 150):
            add(f"max_ip_ge_{t}", (lambda v, t=t: 1.0 if v["max_ip"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ innings (workload and health)")
        for t in (120, 150, 180):
            add(f"max_so_ge_{t}", (lambda v, t=t: 1.0 if v["max_so"] >= t else 0.0), "threshold",
                f"a single MiLB season of {t}+ strikeouts")
        for t in (300, 400, 500):
            add(f"career_ip_ge_{t}", (lambda v, t=t: 1.0 if v["career_ip"] >= t else 0.0),
                "threshold", f"{t}+ career MiLB innings before the decision")
        for k in ("max_ip", "max_so", "max_bf", "career_ip", "career_so", "career_bf",
                  "milb_seasons"):
            add(k, (lambda v, k=k: float(v[k])), "continuous", f"{k} as a level")
        add("so_per_150ip_peak",
            (lambda v: 150.0 * v["max_so"] / v["max_ip"] if v["max_ip"] >= 50 else 0.0),
            "derived", "peak strikeout VOLUME normalised to a full season, zero when thin")
        add("workload_and_missing_bats",
            (lambda v: 1.0 if (v["max_ip"] >= 130 and v["max_so"] >= 150) else 0.0),
            "combination", "130+ IP AND 150+ K in the same season")
    return C


# ------------------------------------------------------------------ pool assembly
def build_pool(side: str, readable_only: bool = False) -> dict:
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    keys, _mono = E._feature_spec(side)
    group = "pitching" if side == "pit" else "hitting"
    by_key = {r["player_key"]: r for r in raw}
    vols, miss = [], 0
    for r in prep:
        src = by_key.get(r.get("player_key")) or {}
        seasons = eligible_seasons(src.get("mlbam_id"), int(r["decision_year"]),
                                   src.get("cutoff"), group)
        if not seasons:
            miss += 1
        vols.append(volumes(seasons, side))
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    if readable_only:
        keep = np.flatnonzero(np.array([v["milb_seasons"] > 0 for v in vols]))
        X, y, w, fv, dy = X[keep], y[keep], w[keep], fv[keep], dy[keep]
        vols = [vols[i] for i in keep]
    return {
        "side": side, "keys": list(keys), "X": X, "y": y, "w": w, "fv": fv, "dy": dy,
        "vols": vols, "n": len(y), "lam": E.blend_lambda(side),
        "rows_without_milb": miss, "readable_only": bool(readable_only),
    }


# ------------------------------------------------------------------ part 1: descriptive
def describe(P: dict, cands: list[dict]) -> list[dict]:
    y = P["y"]
    out = []
    pool_star = float((y >= STAR_WAR).mean())
    for c in cands:
        v = np.array([c["fn"](x) for x in P["vols"]], dtype=float)
        if c["kind"] in ("threshold", "combination"):
            m = v > 0.5
            n_in = int(m.sum())
            if n_in == 0:
                out.append({"name": c["name"], "kind": c["kind"], "why": c["why"],
                            "support": 0, "note": "NO SUPPORT: no row in the pool clears it"})
                continue
            yi, yo = y[m], y[~m]
            out.append({
                "name": c["name"], "kind": c["kind"], "why": c["why"],
                "support": n_in, "support_share": round(n_in / len(y), 4),
                "mean_label_in": round(float(yi.mean()), 3),
                "mean_label_out": round(float(yo.mean()), 3) if len(yo) else None,
                "star_rate_in": round(float((yi >= STAR_WAR).mean()), 4),
                "star_rate_out": round(float((yo >= STAR_WAR).mean()), 4) if len(yo) else None,
                "star_rate_pool": round(pool_star, 4),
                "superstar_rate_in": round(float((yi >= SUPERSTAR_WAR).mean()), 4),
                "bust_rate_in": round(float((yi <= BUST_WAR).mean()), 4),
                "bust_rate_out": round(float((yo <= BUST_WAR).mean()), 4) if len(yo) else None,
                "star_lift_vs_pool": (round(float((yi >= STAR_WAR).mean()) / pool_star, 3)
                                      if pool_star > 0 else None),
            })
        else:
            fin = np.isfinite(v)
            out.append({
                "name": c["name"], "kind": c["kind"], "why": c["why"],
                "support": int(fin.sum()),
                "spearman_with_label": round(float(M.wrho(v[fin], y[fin], P["w"][fin])), 5),
                "nonzero_share": round(float((v != 0).mean()), 4),
            })
    return out


# ------------------------------------------------------------------ part 2: gated add
def chain_with(P, extra=None, sel=None, years=None):
    """The shipped forward chain, optionally with one extra column appended to X."""
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = P["lam"]
    if sel is None:
        sel = np.arange(P["n"])
    X = P["X"] if extra is None else np.column_stack([P["X"], extra])
    X, y, w, fv, dy = X[sel], P["y"][sel], P["w"][sel], P["fv"][sel], P["dy"][sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = M.ols_fit(fv[tr], y[tr])
        rg = M.ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = M.ridge_pred(rg, X[te])
        YR.append(np.full(len(te), yr))
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(y[te])
        W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def _margin(parts, sel=None):
    if parts is None:
        return None
    _yr, cons, blend, tgt, w = parts
    if sel is not None:
        cons, blend, tgt, w = cons[sel], blend[sel], tgt[sel], w[sel]
    return float(M.wrho(blend, tgt, w)) - float(M.wrho(cons, tgt, w))


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = round(running, 5)
    return out


def gate(P: dict, cands: list[dict], B_cond: int, B_perm: int, verbose=True) -> dict:
    rng = np.random.default_rng(SEED)
    base_parts = chain_with(P)
    base = _margin(base_parts)
    n_te = len(base_parts[3])
    results, pvals = [], {}
    t0 = time.time()
    for i, c in enumerate(cands):
        v = np.array([c["fn"](x) for x in P["vols"]], dtype=float)
        if np.allclose(v, v[0]):
            results.append({"name": c["name"], "skipped": "constant in this pool"})
            continue
        sd = v.std()
        vz = (v - v.mean()) / sd if sd > 0 else v
        parts = chain_with(P, extra=vz)
        m = _margin(parts)
        if m is None:
            results.append({"name": c["name"], "skipped": "no fold survived"})
            continue
        delta = m - base
        cond = []
        for _ in range(B_cond):
            s = rng.integers(0, n_te, n_te)
            a, b = _margin(parts, s), _margin(base_parts, s)
            if a is not None and b is not None:
                cond.append(a - b)
        cond = np.array([x for x in cond if np.isfinite(x)], dtype=float)
        null = []
        for j in range(B_perm):
            r2 = np.random.default_rng(SEED + 7919 * (i + 1) + j)
            pv = vz[r2.permutation(len(vz))]
            mm = _margin(chain_with(P, extra=pv))
            if mm is not None:
                null.append(mm - base)
        null = np.array(null, dtype=float)
        p = float((np.abs(null) >= abs(delta)).mean()) if len(null) else 1.0
        pvals[c["name"]] = p
        folds = {}
        for yr in E.SCORED_YEARS:
            a = _margin(chain_with(P, extra=vz, years=(yr,)))
            b = _margin(chain_with(P, years=(yr,)))
            if a is not None and b is not None:
                folds[str(yr)] = round(a - b, 5)
        results.append({
            "name": c["name"], "kind": c["kind"], "why": c["why"],
            "margin_base": round(base, 5), "margin_with": round(m, 5),
            "delta": round(delta, 5),
            "E_cond_ci95": ([round(float(np.percentile(cond, 2.5)), 5),
                             round(float(np.percentile(cond, 97.5)), 5)] if len(cond) else None),
            "E_cond_floor_mde95": (round(1.96 * float(cond.std(ddof=1)), 5)
                                   if len(cond) > 1 else None),
            "clears_own_floor": (bool(len(cond) > 1 and abs(delta) >= 1.96 * cond.std(ddof=1))),
            "permutation_p": round(p, 4),
            "permutation_B": int(len(null)),
            "folds_positive": sum(1 for x in folds.values() if x > 0),
            "folds_total": len(folds),
            "per_fold_delta": folds,
        })
        if verbose:
            print(f"  [{i+1}/{len(cands)}] {c['name']:24} delta {delta:+.5f} "
                  f"p={p:.3f}  {time.time()-t0:.0f}s", flush=True)
    adj = holm(pvals)
    for r in results:
        if r.get("name") in adj:
            r["holm_p"] = adj[r["name"]]
            r["SHIPPABLE"] = bool(r.get("clears_own_floor") and adj[r["name"]] < 0.05
                                  and r.get("delta", 0) > 0)
    return {"baseline_margin": round(base, 5), "n_candidates": len(cands),
            "holm_family_size": len(pvals), "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", choices=["hit", "pit", "both"], default="both")
    ap.add_argument("--describe-only", action="store_true")
    ap.add_argument("--b-cond", type=int, default=1000)
    ap.add_argument("--b-perm", type=int, default=200)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    sides = SIDES if a.side == "both" else (a.side,)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_volume_driver_lab.py",
        "asked_by": "owner, 2026-09-04: volume and cumulative-stat eFV drivers",
        "label_basis": "eWAR v2 (the 2026-09-04 label epoch)",
        "star_definition": {"star_war": STAR_WAR, "superstar_war": SUPERSTAR_WAR,
                            "bust_war": BUST_WAR,
                            "note": "first-6yr WAR on the shipped censored label"},
        "leakage_rule": ("season readable only when the decision date is at or after Oct 1 "
                         "of that season; mirrored from efv_dataset._milb_features"),
        "sides": {},
    }
    for side in sides:
        t0 = time.time()
        cands = candidates(side)
        blk = {}
        for scope in ("full_pool", "readable_only"):
            P = build_pool(side, readable_only=(scope == "readable_only"))
            print(f"=== {side} / {scope}: {P['n']} rows, {len(cands)} candidates, "
                  f"{P['rows_without_milb']} rows with no readable MiLB season "
                  f"({time.time()-t0:.0f}s)", flush=True)
            b = {"n_rows": P["n"], "rows_without_milb": P["rows_without_milb"],
                 "descriptive": describe(P, cands)}
            if not a.describe_only:
                b["gated"] = gate(P, cands, a.b_cond, a.b_perm)
            blk[scope] = b
        blk["scope_note"] = (
            "full_pool scores every debuted row and reads a missing MiLB history as zero "
            "volume; readable_only drops those rows. A candidate that only works in "
            "full_pool is sensing missingness, not volume.")
        out["sides"][side] = blk
    if not a.no_write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

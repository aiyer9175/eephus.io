# pbust thin-sample lane -- SCRATCH GATE LAB (lane: pbust).
#
# PRE-REGISTERED QUESTION
#   Is the served p_bust on PROVISIONAL (thin-sample, source-ungraded, low-level)
#   rows miscalibrated against realized outcomes, and can a population-conditional
#   bust curve be fit that beats the incumbent OUT OF FOLD under the repo's
#   measurement standard (docs/EFV_GATE_STANDARD.md)?
#
# POPULATION (identical to the served one, by construction)
#   source-UNGRADED as of the cohort season (no snapshot FV on or before Y)
#   x never MLB-exposed on or before Y
#   x primary-level exposure >= the served grade floor (80 PA hit / 90 BF pit)
#   x primary level in DSL/CPX/A/A+/AA/AAA
#
# LABEL  bust = first-6-MLB-season summed bWAR < 3.0  (Clemens bucket 0 = < 0.5
#   WAR/season talent over the 6-season control window, value_framework_config.yaml).
#   Never reached MLB -> bust with CERTAINTY (exact, WAR-free).
#   Reached MLB but absent from career_war -> UNKNOWN; the headline labeling calls
#   every unknown a NON-bust, the most conservative possible choice against the
#   hypothesis (it can only lower the measured bust rate).
#
# GATES
#   G1  defect: empirical bust rate - incumbent p_bust > 0 in the affected band,
#       paired-bootstrap CI95 excluding 0, on >= 4 independent cohort years.
#   G2  candidate beats incumbent OOF (leave-one-cohort-year-out log loss + Brier).
#   G3  ZERO-INFORMATION control: the same fit on a ROW-PERMUTED grade column must
#       not match the candidate. Plus the covariate-free CONSTANT head (the ablation
#       that killed BUCKET-AGE-HEAD) -- if a constant matches the curve, the honest
#       ship is a flat offset, not a grade curve.
#   G4  permutation null band on the label.
#   G5  the fitted curve is nonincreasing in grade (no served inversion).
from __future__ import annotations

import json
import math
import random
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import milb_history as mh                                   # noqa: E402
_raw = mh.player_index
mh.player_index = lru_cache(maxsize=128)(_raw)              # type: ignore[assignment]

import value_framework as vf                                # noqa: E402
import efv_ungraded as eu                                   # noqa: E402
from efv_dataset import matrix_path                         # noqa: E402
from prospect_path import _fit_ridge, _fit_linear_calibration   # noqa: E402
import cohort as co                                         # noqa: E402

PRIMARY_YEARS = (2015, 2016, 2017, 2018)   # >= 8 seasons of outcome (97.8% of
                                           # eventual DSL/CPX debuts observed)
SENSITIVITY_YEARS = (2019,)
BAND_MIN = 32.5            # "affected band": where the incumbent curve starts to
                           # move off the org-filler asymptote
EPS = 1e-6


# --------------------------------------------------------------------------- data
def load():
    rows = json.loads((HERE / "cohort_scored.json").read_text(encoding="utf-8"))
    mlbs = co.mlb_seasons_by_id()
    for r in rows:
        # first-6-MLB-season playing time (for the unknown-label bound tightening)
        seas = mlbs.get(r["mlbam"]) or {}
        post = {y: e for y, e in seas.items() if y > r["year"]}
        if post:
            dy = min(post)
            r["mlb_pt6"] = sum(e for y, e in post.items() if dy <= y <= dy + 5)
        else:
            r["mlb_pt6"] = 0.0
    return rows


import os
# PRIMARY labeling. "pt_rule" is the accurate one and is VALIDATED, not assumed:
# among the 1,144 cohort rows with a KNOWN first-6yr WAR, 0 of the 487 with fewer
# than 300 first-6-MLB-season PA/BF reached war6 >= 3.0 (max 1.58; still 0/639 at
# a 500 threshold). So an unknown-WAR row under 300 PA/BF is a bust with
# certainty. The >= 300 unknowns stay labelled NON-bust, which still understates
# the truth (63.9% of the KNOWN >= 300 rows are busts) -- i.e. pt_rule remains a
# LOWER bound on the real bust rate.
PRIMARY_VARIANT = os.environ.get("PBUST_LABEL", "pt_rule")


def label_variant(r, variant: str):
    """1 = bust, 0 = non-bust, None = drop."""
    if r["outcome"] == "no_mlb":
        return 1
    if r["outcome"] == "mlb_war":
        return r["bust"]
    # mlb_no_war -> unknown
    if variant == "conservative":       # HEADLINE: every unknown is a NON-bust
        return 0
    if variant == "pt_rule":            # unknown with a trivial MLB career -> bust
        return 1 if r["mlb_pt6"] < 300 else 0
    if variant == "upper":              # every unknown is a bust
        return 1
    if variant == "drop":
        return None
    raise ValueError(variant)


@lru_cache(maxsize=8)
def train_rows(side: str):
    is_pit = side == "pit"
    rows = [r for r in json.loads(matrix_path(side).read_text(encoding="utf-8"))
            if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    return eu._prep(rows, side)


def fit_from(data, side):
    ridge = _fit_ridge(data, eu._keys(side))
    raw = [(eu._predict_clipped(ridge, r["feats"]), r["target"]) for r in data]
    cal = _fit_linear_calibration(raw)
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    return ridge, a, b


def regrade(rows, fits):
    """Re-derive the served provisional grade for every cohort row under `fits`."""
    out = []
    for r in rows:
        ridge, a, b = fits[r["side"]]
        war = max(-2.0, a + b * eu._predict_clipped(ridge, r["feats"]))
        g = eu._grade(war, r["side"])
        if r["expo"] < (eu._MIN_EXPO_BF if r["side"] == "pit" else eu._MIN_EXPO_PA):
            g = min(g, eu._SUBFLOOR_GRADE)
        out.append(g)
    return out


# ------------------------------------------------------------------- incumbent
@lru_cache(maxsize=8192)
def incumbent_pbust(grade_r: float, is_pit: bool) -> float:
    p = vf.p_bucket_given_fv(grade_r, is_pit)
    return float(p[0]) if p else 0.5


def inc(g, is_pit):
    return incumbent_pbust(round(g, 1), is_pit)


# ------------------------------------------------------------------- candidate
def fit_logistic(xs, ys, l2=1e-3, iters=400):
    """Newton-IRLS logistic on a single centred covariate. Returns (a, b)."""
    a, b = 0.0, 0.0
    for _ in range(iters):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            z = a + b * x
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            w = max(p * (1 - p), 1e-9)
            d = p - y
            g0 += d
            g1 += d * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        g0 += l2 * a
        g1 += l2 * b
        h00 += l2
        h11 += l2
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da = (h11 * g0 - h01 * g1) / det
        db = (h00 * g1 - h01 * g0) / det
        a -= da
        b -= db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return a, b


def cand_predict(a, b, g):
    z = a + b * (g - 30.0)
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def logloss(ps, ys):
    return -sum(y * math.log(max(p, EPS)) + (1 - y) * math.log(max(1 - p, EPS))
                for p, y in zip(ps, ys)) / max(1, len(ys))


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / max(1, len(ys))


# --------------------------------------------------------------------------- G1
def g1_table(rows, grades, variant="conservative"):
    """Per (side, cohort year) empirical bust rate vs incumbent in the affected band."""
    out = {}
    for side in ("hit", "pit"):
        for y in PRIMARY_YEARS:
            sel = [(g, r) for g, r in zip(grades, rows)
                   if r["side"] == side and r["year"] == y and g >= BAND_MIN]
            ys = [label_variant(r, variant) for _g, r in sel]
            keep = [(g, yy) for (g, _r), yy in zip(sel, ys) if yy is not None]
            if len(keep) < 20:
                out[(side, y)] = {"n": len(keep)}
                continue
            emp = sum(yy for _g, yy in keep) / len(keep)
            incum = sum(inc(g, side == "pit") for g, _ in keep) / len(keep)
            out[(side, y)] = {"n": len(keep), "emp": emp, "inc": incum, "gap": emp - incum}
    return out


# --------------------------------------------------------------------------- run
def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    rng = random.Random(20260725)
    allrows = load()
    rows = [r for r in allrows if r["year"] in PRIMARY_YEARS]
    print(f"cohort rows (primary years {PRIMARY_YEARS}): {len(rows)}")

    base_fits = {s: fit_from(train_rows(s), s) for s in ("hit", "pit")}
    grades = regrade(rows, base_fits)
    for i, g in enumerate(grades):
        rows[i]["grade_refit"] = g

    report = {"n_cohort": len(rows), "primary_years": list(PRIMARY_YEARS),
              "band_min": BAND_MIN, "bootstrap_B": B}

    # ---- label-variant sensitivity on the headline rate ----------------------
    lv = {}
    for variant in ("conservative", "pt_rule", "upper", "drop"):
        for side in ("hit", "pit"):
            sel = [(g, r) for g, r in zip(grades, rows)
                   if r["side"] == side and g >= BAND_MIN]
            ys = [label_variant(r, variant) for _g, r in sel]
            keep = [(g, y) for (g, _r), y in zip(sel, ys) if y is not None]
            lv[f"{variant}/{side}"] = {
                "n": len(keep),
                "emp_bust": round(sum(y for _g, y in keep) / max(1, len(keep)), 4),
                "incumbent": round(sum(inc(g, side == "pit") for g, _ in keep) / max(1, len(keep)), 4),
            }
    report["label_variants_affected_band"] = lv

    # ---- G1 per split --------------------------------------------------------
    t = g1_table(rows, grades)
    report["g1_splits"] = {f"{s}/{y}": {k: (round(v, 4) if isinstance(v, float) else v)
                                        for k, v in d.items()} for (s, y), d in t.items()}

    # ---- paired bootstrap: resample TRAIN and TEST, refit every draw ---------
    tr = {s: train_rows(s) for s in ("hit", "pit")}
    by_year = {}
    for i, r in enumerate(rows):
        by_year.setdefault((r["side"], r["year"]), []).append(i)
    boot_gap = {s: [] for s in ("hit", "pit")}
    boot_ll = {"inc": [], "cand": [], "const": [], "perm": []}
    for d in range(B):
        fits = {}
        for s in ("hit", "pit"):
            samp = [tr[s][rng.randrange(len(tr[s]))] for _ in range(len(tr[s]))]
            try:
                fits[s] = fit_from(samp, s)
            except Exception:
                fits[s] = base_fits[s]
        # stratified (side x cohort-year) resample of the test cohort
        idx = []
        for key, ii in by_year.items():
            idx += [ii[rng.randrange(len(ii))] for _ in range(len(ii))]
        sub = [rows[i] for i in idx]
        gs = regrade(sub, fits)
        for s in ("hit", "pit"):
            sel = [(g, r) for g, r in zip(gs, sub) if r["side"] == s and g >= BAND_MIN]
            if len(sel) < 20:
                continue
            ys = [label_variant(r, "conservative") for _g, r in sel]
            emp = sum(ys) / len(ys)
            incu = sum(inc(g, s == "pit") for g, _ in sel) / len(sel)
            boot_gap[s].append(emp - incu)
        # OOF (leave-one-cohort-year-out) log loss on this draw
        ll = {k: [] for k in boot_ll}
        for hold in PRIMARY_YEARS:
            for s in ("hit", "pit"):
                trn = [(g, r) for g, r in zip(gs, sub) if r["side"] == s and r["year"] != hold]
                tst = [(g, r) for g, r in zip(gs, sub) if r["side"] == s and r["year"] == hold]
                if len(trn) < 200 or len(tst) < 50:
                    continue
                ytr = [label_variant(r, "conservative") for _g, r in trn]
                yte = [label_variant(r, "conservative") for _g, r in tst]
                a, b = fit_logistic([g - 30.0 for g, _ in trn], ytr)
                pc = [cand_predict(a, b, g) for g, _ in tst]
                pi = [inc(g, s == "pit") for g, _ in tst]
                k = sum(ytr) / len(ytr)
                pk = [k] * len(tst)
                # zero-information control: row-permuted grade column (train + test)
                gp = [g for g, _ in trn]
                rng.shuffle(gp)
                ap, bp = fit_logistic([g - 30.0 for g in gp], ytr)
                gpt = [g for g, _ in tst]
                rng.shuffle(gpt)
                pp = [cand_predict(ap, bp, g) for g in gpt]
                ll["cand"].append(logloss(pc, yte))
                ll["inc"].append(logloss(pi, yte))
                ll["const"].append(logloss(pk, yte))
                ll["perm"].append(logloss(pp, yte))
        for k in boot_ll:
            if ll[k]:
                boot_ll[k].append(sum(ll[k]) / len(ll[k]))
        if (d + 1) % 100 == 0:
            print(f"  boot {d+1}/{B}", flush=True)

    def ci(v, lo=2.5, hi=97.5):
        if not v:
            return None
        v = sorted(v)
        return {"mean": round(sum(v) / len(v), 5),
                "lo95": round(v[int(lo / 100 * (len(v) - 1))], 5),
                "hi95": round(v[int(hi / 100 * (len(v) - 1))], 5), "B": len(v)}

    report["g1_bootstrap_gap"] = {s: ci(boot_gap[s]) for s in boot_gap}
    report["g2_oof_logloss"] = {k: ci(v) for k, v in boot_ll.items()}
    d_ci = ci([i - c for i, c in zip(boot_ll["inc"], boot_ll["cand"])])
    report["g2_delta_inc_minus_cand"] = d_ci
    report["g3_delta_inc_minus_const"] = ci([i - c for i, c in zip(boot_ll["inc"], boot_ll["const"])])
    report["g3_delta_cand_minus_const"] = ci([c - k for c, k in zip(boot_ll["cand"], boot_ll["const"])])
    report["g3_delta_inc_minus_perm"] = ci([i - p for i, p in zip(boot_ll["inc"], boot_ll["perm"])])

    # ---- G4 permutation null on the LABEL (point fits, no refit needed) ------
    null = []
    for _ in range(400):
        for s in ("hit", "pit"):
            sel = [(g, r) for g, r in zip(grades, rows) if r["side"] == s]
            ys = [label_variant(r, "conservative") for _g, r in sel]
            rng.shuffle(ys)
            per_fold = []
            for hold in PRIMARY_YEARS:
                trn = [(g, y) for (g, r), y in zip(sel, ys) if r["year"] != hold]
                tst = [(g, y) for (g, r), y in zip(sel, ys) if r["year"] == hold]
                if len(trn) < 200 or len(tst) < 50:
                    continue
                a, b = fit_logistic([g - 30.0 for g, _ in trn], [y for _g, y in trn])
                pc = [cand_predict(a, b, g) for g, _ in tst]
                yte = [y for _g, y in tst]
                k = sum(y for _g, y in trn) / len(trn)
                per_fold.append(logloss([k] * len(tst), yte) - logloss(pc, yte))
            if per_fold:
                null.append(sum(per_fold) / len(per_fold))
    null.sort()
    report["g4_label_permutation_null_const_minus_cand"] = {
        "p50": round(null[len(null) // 2], 5),
        "p95": round(null[int(0.95 * (len(null) - 1))], 5),
        "p99": round(null[int(0.99 * (len(null) - 1))], 5), "n": len(null)}

    # ---- final point fit (the shippable head) --------------------------------
    head = {}
    for s in ("hit", "pit"):
        sel = [(g, r) for g, r in zip(grades, rows) if r["side"] == s]
        ys = [label_variant(r, "conservative") for _g, r in sel]
        a, b = fit_logistic([g - 30.0 for g, _ in sel], ys)
        head[s] = {"a": round(a, 6), "b": round(b, 6), "n": len(sel),
                   "n_bust": sum(ys),
                   "monotone_nonincreasing": b <= 0}
    report["head"] = head
    report["g5_monotone"] = all(h["monotone_nonincreasing"] for h in head.values())

    # ---- band-threshold sweep of the raw defect (point estimate) -------------
    sweep = {}
    for thr in (20, 30, 32.5, 35, 37.5, 40, 42.5):
        for s in ("hit", "pit"):
            sel = [(g, r) for g, r in zip(grades, rows) if r["side"] == s and g >= thr]
            if len(sel) < 20:
                continue
            ys = [label_variant(r, "conservative") for _g, r in sel]
            yp = [label_variant(r, "pt_rule") for _g, r in sel]
            sweep[f"grade>={thr}/{s}"] = {
                "n": len(sel),
                "emp_conservative": round(sum(ys) / len(ys), 4),
                "emp_pt_rule": round(sum(yp) / len(yp), 4),
                "incumbent": round(sum(inc(g, s == "pit") for g, _ in sel) / len(sel), 4),
                "candidate": round(sum(cand_predict(head[s]["a"], head[s]["b"], g)
                                       for g, _ in sel) / len(sel), 4),
            }
    report["defect_band_sweep"] = sweep

    # ---- OOF calibration table (leave-one-cohort-year-out, point fit) --------
    cal_tab = {}
    for s in ("hit", "pit"):
        buckets = {}
        for hold in PRIMARY_YEARS:
            trn = [(g, r) for g, r in zip(grades, rows) if r["side"] == s and r["year"] != hold]
            tst = [(g, r) for g, r in zip(grades, rows) if r["side"] == s and r["year"] == hold]
            ytr = [label_variant(r, "conservative") for _g, r in trn]
            a, b = fit_logistic([g - 30.0 for g, _ in trn], ytr)
            for (g, r) in tst:
                y = label_variant(r, "conservative")
                bkt = ("20-30" if g < 30 else "30-35" if g < 35 else "35-40" if g < 40
                       else "40-45" if g < 45 else "45+")
                d = buckets.setdefault(bkt, {"n": 0, "obs": 0, "inc": 0.0, "cand": 0.0})
                d["n"] += 1
                d["obs"] += y
                d["inc"] += inc(g, s == "pit")
                d["cand"] += cand_predict(a, b, g)
        cal_tab[s] = {k: {"n": v["n"], "observed": round(v["obs"] / v["n"], 4),
                          "incumbent": round(v["inc"] / v["n"], 4),
                          "candidate_oof": round(v["cand"] / v["n"], 4)}
                      for k, v in sorted(buckets.items())}
    report["oof_calibration"] = cal_tab

    # ---- served-vs-candidate curve table -------------------------------------
    tab = []
    for g in [20, 24, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48]:
        row = {"grade": g}
        for s in ("hit", "pit"):
            row[f"inc_{s}"] = round(inc(g, s == "pit"), 3)
            row[f"cand_{s}"] = round(cand_predict(head[s]["a"], head[s]["b"], g), 3)
        tab.append(row)
    report["curve"] = tab

    (HERE / "gate_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1)[:6000])


if __name__ == "__main__":
    main()

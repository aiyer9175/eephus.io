"""INDEPENDENT re-derivation of the biometric lane. Written from scratch against
efv_lab_runner.run_variant semantics (which DOES pass KM sample weights)."""
import sys, json
import numpy as np
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
import os; os.chdir(r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
sys.path.insert(0, "tools")
import efv_lab_runner as LAB

BIO = json.load(open("tools/_arch_bio_feat.json"))
FOLDS = (2018, 2019, 2020, 2021, 2022, 2023)

def load(side):
    rows = [dict(r) for r in LAB.data_for(side)]
    for r in rows:
        b = BIO.get(side + "|" + r["player_key"]) or {}
        r["bio"] = {"bmi": b.get("bmi"), "h": b.get("h"), "w": b.get("w"),
                    "frame": b.get("frame"), "athl": b.get("athl"), "lev": b.get("levers_num")}
    return rows

def zfit(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 30: return None
    return float(np.mean(v)), float(np.std(v)) or 1.0

def zap(z, x):
    return 0.0 if (z is None or x is None) else (x - z[0]) / z[1]

def block(kind, tr, te):
    if kind == "none": return [], [ {} for _ in tr], [{} for _ in te]
    if kind in ("bmi", "linear"):
        zb = zfit([r["bio"]["bmi"] for r in tr]); zh = zfit([r["bio"]["h"] for r in tr])
        zw = zfit([r["bio"]["w"] for r in tr])
        def mk(rows):
            out = []
            for r in rows:
                b = r["bio"]
                d = {"_bmi": zap(zb, b["bmi"]), "_miss": 1.0 if b["bmi"] is None else 0.0}
                if kind == "linear":
                    d["_h"] = zap(zh, b["h"]); d["_w"] = zap(zw, b["w"])
                out.append(d)
            return out
        names = ["_bmi", "_miss"] + (["_h", "_w"] if kind == "linear" else [])
        return names, mk(tr), mk(te)
    if kind == "frame":
        zf = zfit([r["bio"]["frame"] for r in tr]); za = zfit([r["bio"]["athl"] for r in tr])
        zl = zfit([r["bio"]["lev"] for r in tr])
        def mk(rows):
            return [{"_fr": zap(zf, r["bio"]["frame"]), "_at": zap(za, r["bio"]["athl"]),
                     "_lv": zap(zl, r["bio"]["lev"]),
                     "_frmiss": 1.0 if r["bio"]["frame"] is None else 0.0} for r in rows]
        return ["_fr", "_at", "_lv", "_frmiss"], mk(tr), mk(te)
    raise ValueError(kind)

def run(rows, kind, side, use_weights=True, folds=FOLDS, want_coef=False):
    lam = blend_lambda(side); keys = list(_feature_spec(side)[0])
    P, T, PK = [], [], []
    coefs = {}
    for yr in folds:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50: continue
        names, Btr, Bte = block(kind, tr, te)
        allk = keys + names
        trf = [{"feats": {**tr[i]["feats"], **Btr[i]},
                "target": tr[i]["target_censored"],
                **({"weight": tr[i]["weight"]} if use_weights else {})} for i in range(len(tr))]
        rg = _fit_ridge(trf, allk)
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        if not (rg and ols): continue
        if want_coef and names:
            coefs[yr] = {n: round(rg["w"][allk.index(n)], 4) for n in names}
        for i, r in enumerate(te):
            p = _predict(rg, {**r["feats"], **Bte[i]})
            c = max(0.0, _pred_ols(ols, r["fv"]))
            P.append(lam * p + (1 - lam) * c); T.append(r["target_censored"]); PK.append(r["player_key"])
    return {"n": len(P), "rho": _spearman(P, T), "pred": P, "truth": T, "pk": PK, "coef": coefs}

if __name__ == "__main__":
    for side in ("hit", "pit"):
        rows = load(side)
        for uw in (False, True):
            b = run(rows, "none", side, uw)
            line = "%s weights=%-5s base rho=%.4f n=%d" % (side, uw, b["rho"], b["n"])
            for k in ("bmi", "linear", "frame"):
                c = run(rows, k, side, uw, want_coef=True)
                line += "  | %s %+.4f" % (k, c["rho"] - b["rho"])
                if uw and k == "linear":
                    print("    coef(linear,%s):" % side, c["coef"])
            print(line)

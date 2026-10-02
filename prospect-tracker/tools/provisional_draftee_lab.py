# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PV-10 lab: the provisional v2 draftee head (players with no pro line).

Pre-declaration: docs/provisional-v2/PV10_DRAFTEE_HEAD_PREDECLARED.md (committed before
this lab joined any first grade to a draft record). Spec: PROVISIONAL_V2.md section 3
("Draftees with no pro line") and section 5 (PV-10).

What it asks, of the 2017 to 2025 draft classes, forward-chained: on the day the draft
closes, does a pedigree-only head order who a label source grades by the next preseason
lists better than draft order itself (T1), and does it place the first FV a source assigns
better than a constant on that source's scale (T2)?

Reads: .cache/draft_bonus (the statsapi draft records), the MiLB line cache and the label-
source opinions through provisional_v2.Inputs (prospects.db read only). Never reads WAR.
No stratum is named after a consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md), and no
FV-value distribution of the labels is reported.

Writes one block, pv10_draftee, labelled BACKCAST, into data/provisional_v2_eval.json
(provisional_v2.EVAL_PATH, resolved at call time so the test harness redirects it);
provisional_v2.build carries the block forward when it rewrites the file. Nothing is
served and no page reads the block.

Run: python tools/provisional_draftee_lab.py           write the block
     python tools/provisional_draftee_lab.py --print   print it, write nothing
"""
from __future__ import annotations

import datetime
import json
import math
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import provisional_v2 as P  # noqa: E402

BLOCK = "pv10_draftee"
PREDECLARATION = "docs/provisional-v2/PV10_DRAFTEE_HEAD_PREDECLARED.md"
PREDECLARED_COMMIT = "17bcae23"
CLASSES = list(range(2017, 2026))
#: Last day of each draft (public calendar), the DRAFT frame's anchor.
DRAFT_END = {2017: "2017-06-14", 2018: "2018-06-06", 2019: "2019-06-05", 2020: "2020-06-11",
             2021: "2021-07-13", 2022: "2022-07-19", 2023: "2023-07-11", 2024: "2024-07-16",
             2025: "2025-07-14"}
SIGNED_MMDD = "08-02"   # the day after the latest signing deadline of the nine classes
ROUND_NUM = {"1C": 1.5, "CB-A": 1.5, "PPI": 1.5, "CB-B": 2.5, "2C": 2.5, "SUP-2": 2.5,
             "SUP-3": 3.5, "4C": 4.5}
PED0 = ["d_logpick", "d_round", "d_logslot", "d_hs", "d_jc", "d_age", "d_logrank", "d_ranked", "pitcher"]
PED1 = PED0 + ["d_logbonus", "d_bonus_over_slot", "d_signed"]
MIN_TRAIN_CLASSES = 2
LR_C = 1.0


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round_num(r):
    if r in ROUND_NUM:
        return ROUND_NUM[r]
    try:
        return float(int(r))
    except (TypeError, ValueError):
        return None


def load_picks(cache_dir=None) -> dict[int, list[dict]]:
    """class -> one record per drafted player (draft-day and post-signing fields)."""
    cache = Path(cache_dir) if cache_dir is not None else P.CACHE_DIR
    out = {}
    for y in CLASSES:
        d = json.loads((cache / "draft_bonus" / f"{y}.json").read_text(encoding="utf-8"))
        rows = []
        for rd in d["drafts"]["rounds"]:
            for p in rd["picks"]:
                pe = p.get("person") or {}
                if not pe.get("id"):
                    continue
                sc = ((p.get("school") or {}).get("schoolClass") or "").upper()
                pos = ((pe.get("primaryPosition") or {}).get("abbreviation") or "").upper()
                rows.append({"mlbam": int(pe["id"]), "name": pe.get("fullName"), "pick": p.get("pickNumber"),
                             "round": _round_num(p.get("pickRound")), "slot": _f(p.get("pickValue")),
                             "bonus": _f(p.get("signingBonus")), "rank": p.get("rank"),
                             "hs": (1.0 if sc.startswith("HS") else 0.0) if sc else None,
                             "jc": (1.0 if "JC" in sc else 0.0) if sc else None,
                             "birth": pe.get("birthDate"), "pitcher": 1.0 if pos in ("P", "TWP") else 0.0})
        out[y] = rows
    return out


def _age(birth, anchor):
    try:
        b = datetime.date.fromisoformat(birth)
    except (TypeError, ValueError):
        return None
    return (datetime.date.fromisoformat(anchor) - b).days / 365.25


def _features(r, anchor):
    slot, bonus = r.get("slot"), r.get("bonus")
    return {"d_logpick": math.log(r["pick"]) if r.get("pick") else None, "d_round": r.get("round"),
            "d_logslot": math.log(slot) if slot and slot > 0 else None,
            "d_hs": r.get("hs"), "d_jc": r.get("jc"), "d_age": _age(r.get("birth"), anchor),
            "d_logrank": math.log(r["rank"]) if r.get("rank") else None,
            "d_ranked": 1.0 if r.get("rank") else 0.0, "pitcher": r["pitcher"],
            "d_logbonus": math.log(bonus) if bonus and bonus > 0 else None,
            "d_bonus_over_slot": (bonus / slot) if bonus and bonus > 0 and slot and slot > 0 else None,
            "d_signed": 1.0 if bonus and bonus > 0 else 0.0}


def frame_anchor(frame, y):
    if frame == "DRAFT":
        return DRAFT_END[y]
    if frame == "SIGNED":
        return f"{y}-{SIGNED_MMDD}"
    return f"{y}-10-15"   # NOLINE_OCT


def window_end(window, y):
    return f"{y + 1}-04-15" if window == "PRE" else f"{y + 1}-10-15"


def build_frame(inp, picks, as_of, frame):
    """One row per (class, drafted player) in the frame's universe, with the labels of every set."""
    import pandas as pd
    _ev, first = P.opinions_as_of(inp, as_of)
    pro = {}
    for (m, season, _side) in inp.lines:
        pro[m] = min(season, pro.get(m, 9999))
    for m, ss in inp.mlb_seasons.items():
        if ss:
            pro[m] = min(min(ss), pro.get(m, 9999))
    rows, counts = [], {}
    for y in CLASSES:
        A = frame_anchor(frame, y)
        c = {"drafted": 0, "out_pro_line_before_class": 0, "out_opinion_on_or_before_anchor": 0}
        if frame == "NOLINE_OCT":
            c["out_line_in_class_season"] = 0
        for r in picks[y]:
            m = r["mlbam"]
            c["drafted"] += 1
            if pro.get(m, 9999) < y:
                c["out_pro_line_before_class"] += 1
                continue
            if frame == "NOLINE_OCT" and pro.get(m, 9999) <= y:
                c["out_line_in_class_season"] += 1
                continue
            fa = first.get((m, "ANY"))
            if fa and fa[0] <= A:
                c["out_opinion_on_or_before_anchor"] += 1
                continue
            row = {"mlbam": m, "y": y, "anchor": A, "pick": r.get("pick"), **_features(r, A)}
            for s in P.SETS:
                fg = first.get((m, s))
                for w in ("PRE", "G12"):
                    hit = bool(fg and A < fg[0] <= window_end(w, y))
                    row[f"{w}_{s}"] = 1 if hit else 0
                    row[f"FV1_{w}_{s}"] = fg[1] if hit else None
            rows.append(row)
        c["universe"] = c["drafted"] - sum(v for k, v in c.items() if k.startswith("out_"))
        counts[str(y)] = c
    df = pd.DataFrame(rows)
    for col in PED1:
        df[col] = df[col].astype(float)
    return df, counts


def usable_classes(src_days, frame, set_, window, as_of):
    """PV-06's capture guard on this lab's windows: (classes kept, {class: reason})."""
    keep, dropped = [], {}
    vols = {src: [] for src in P.SETS[set_]}
    for y in CLASSES:
        end = window_end(window, y)
        if end > as_of:
            continue
        A = frame_anchor(frame, y)
        short = []
        for src in P.SETS[set_]:
            v = sum(n for (s, d), n in src_days.items() if s == src and A < d <= end)
            prior = sorted(x for x in vols[src] if x > 0)
            if prior:
                k = len(prior)
                med = prior[k // 2] if k % 2 else (prior[k // 2 - 1] + prior[k // 2]) / 2
                if v < P.CAPTURE_FLOOR * med:
                    short.append(f"{src} {v} rows against an earlier median of {med:g}")
            vols[src].append(v)
        if short:
            dropped[y] = "label capture gap: " + "; ".join(short)
        else:
            keep.append(y)
    return keep, dropped


def _fit_gbm(tr, cols, lab):
    import lightgbm as lgb
    if tr[lab].sum() < 5 or tr[lab].sum() == len(tr):
        return float(tr[lab].mean())
    return lgb.LGBMClassifier(**P.PARAMS).fit(tr[cols], tr[lab])


def _fit_lr(tr, cols, lab):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if tr[lab].sum() < 5 or tr[lab].sum() == len(tr):
        return float(tr[lab].mean())
    use = [c for c in cols if tr[c].notna().any()]
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=LR_C, max_iter=2000))
    return (m.fit(tr[use], tr[lab]), use)


def _predict(model, te, cols):
    import numpy as np
    if isinstance(model, float):
        return np.full(len(te), model)
    if isinstance(model, tuple):
        m, use = model
        return m.predict_proba(te[use])[:, 1]
    return model.predict_proba(te[cols])[:, 1]


def _nulls(te):
    import numpy as np
    pick = te["pick"].astype(float).values
    rank = te["d_logrank"].values
    rk = np.where(np.isnan(rank), 1000.0 + pick, np.exp(rank))
    return -pick, -rk


def _ci(xs):
    import numpy as np
    return [round(float(np.percentile(xs, 2.5)), 4), round(float(np.percentile(xs, 97.5)), 4)]


def _pooled_t1(y, p, pnull, ids, extra=None):
    """Pooled AUC / AP with cluster-bootstrap CI95 and paired deltas against the draft-order null."""
    from sklearn.metrics import average_precision_score, roc_auc_score
    out = P._clf(y, p)
    out["null_draft_order_auc"] = P._clf(y, pnull).get("auc")
    out["null_draft_order_ap"] = P._clf(y, pnull).get("ap")
    if "auc" not in out:
        return out
    a, ap, da, dap = [], [], [], []
    for idx in P._cluster_boot(ids):
        yy = y[idx]
        if yy.min() == yy.max():
            continue
        am, an = roc_auc_score(yy, p[idx]), roc_auc_score(yy, pnull[idx])
        pm, pn = average_precision_score(yy, p[idx]), average_precision_score(yy, pnull[idx])
        a.append(am)
        ap.append(pm)
        da.append(am - an)
        dap.append(pm - pn)
    out.update({"auc_ci95": _ci(a), "ap_ci95": _ci(ap),
                "auc_minus_draft_order": round(out["auc"] - out["null_draft_order_auc"], 4),
                "auc_minus_draft_order_ci95": _ci(da),
                "ap_minus_draft_order": round(out["ap"] - out["null_draft_order_ap"], 4),
                "ap_minus_draft_order_ci95": _ci(dap), "boot_b": len(a)})
    if extra:
        out.update(extra)
    return out


def t1_head(df, src_days, frame, set_, window, as_of, cols=PED0, compare_cols=None):
    """Forward-chained T1: each test class scored by models trained on earlier usable classes
    whose window was closed at the test class's anchor."""
    import numpy as np
    lab = f"{window}_{set_}"
    keep, dropped = usable_classes(src_days, frame, set_, window, as_of)
    by_class, Y, PM, PN, PR, PL, PC, ID = {}, [], [], [], [], [], [], []
    for t in keep:
        A = frame_anchor(frame, t)
        train = [c for c in keep if c < t and window_end(window, c) <= A]
        if len(train) < MIN_TRAIN_CLASSES:
            continue
        tr, te = df[df.y.isin(train)], df[df.y == t]
        if te.empty:
            continue
        p = _predict(_fit_gbm(tr, cols, lab), te, cols)
        plr = _predict(_fit_lr(tr, cols, lab), te, cols)
        pn, prk = _nulls(te)
        y = te[lab].values.astype(int)
        m = P._clf(y, p)
        m.update({"null_draft_order_auc": P._clf(y, pn).get("auc"), "null_predraft_rank_auc": P._clf(y, prk).get("auc"),
                  "logistic_auc": P._clf(y, plr).get("auc"), "brier_raw": P._brier(y, p),
                  "brier_train_rate": P._brier(y, np.full(len(y), float(tr[lab].mean()))),
                  "sum_p": round(float(p.sum()), 1), "train_classes": train})
        if compare_cols is not None:
            pc = _predict(_fit_gbm(tr, compare_cols, lab), te, compare_cols)
            m["compare_auc"] = P._clf(y, pc).get("auc")
            PC.append(pc)
        by_class[str(t)] = m
        for acc, v in ((Y, y), (PM, p), (PN, pn), (PR, prk), (PL, plr), (ID, te.mlbam.values)):
            acc.append(v)
    if not Y:
        return {"label": lab, "test_classes": [], "classes_left_out": {str(k): v for k, v in dropped.items()}}
    y, p, pn = np.concatenate(Y), np.concatenate(PM), np.concatenate(PN)
    prk, plr, ids = np.concatenate(PR), np.concatenate(PL), np.concatenate(ID)
    pooled = _pooled_t1(y, p, pn, ids)
    pooled.update({"null_predraft_rank_auc": P._clf(y, prk).get("auc"), "logistic_auc": P._clf(y, plr).get("auc"),
                   "brier_raw": P._brier(y, p),
                   "class_mean_auc": round(float(np.mean([b["auc"] for b in by_class.values() if "auc" in b])), 4),
                   "class_mean_null_draft_order_auc": round(float(np.mean(
                       [b["null_draft_order_auc"] for b in by_class.values() if b.get("null_draft_order_auc")])), 4)})
    out = {"label": lab, "window": _window_rule(frame, window), "features": list(cols),
           "test_classes": [int(t) for t in by_class], "classes_left_out": {str(k): v for k, v in dropped.items()},
           "pooled": pooled, "by_class": by_class}
    if compare_cols is not None:
        pc = np.concatenate(PC)
        out["compare"] = {"features": list(compare_cols),
                          "pooled_compare": _pooled_t1(y, pc, pn, ids),
                          "model_minus_compare": _paired_delta(y, p, pc, ids)}
    return out


def _paired_delta(y, p1, p2, ids):
    from sklearn.metrics import average_precision_score, roc_auc_score
    da, dap = [], []
    for idx in P._cluster_boot(ids):
        yy = y[idx]
        if yy.min() == yy.max():
            continue
        da.append(roc_auc_score(yy, p1[idx]) - roc_auc_score(yy, p2[idx]))
        dap.append(average_precision_score(yy, p1[idx]) - average_precision_score(yy, p2[idx]))
    return {"auc": round(float(roc_auc_score(y, p1) - roc_auc_score(y, p2)), 4), "auc_ci95": _ci(da),
            "ap": round(float(average_precision_score(y, p1) - average_precision_score(y, p2)), 4), "ap_ci95": _ci(dap)}


def t2_head(df, src_days, set_, as_of):
    """Forward-chained level head: ridge on PED0 against the training rows' mean."""
    import pandas as pd
    lab, g = f"FV1_PRE_{set_}", f"PRE_{set_}"
    keep, dropped = usable_classes(src_days, "DRAFT", set_, "PRE", as_of)
    parts, by_class = [], {}
    for i, t in enumerate(keep):
        if i < MIN_TRAIN_CLASSES:
            continue
        tr = df[df.y.isin(keep[:i]) & (df[g] == 1) & df[lab].notna()]
        te = df[(df.y == t) & (df[g] == 1) & df[lab].notna()].copy()
        if te.empty or len(tr) < 30:
            continue
        te["_pred"] = P.predict_t2(P.fit_t2(tr, PED0, lab), te)
        te["_const"] = float(tr[lab].mean())
        by_class[str(t)] = {"n": int(len(te)), "n_train": int(len(tr)),
                            "mae": round(float((te._pred - te[lab]).abs().mean()), 3),
                            "mae_const": round(float((te._const - te[lab]).abs().mean()), 3)}
        parts.append(te)
    if not parts:
        return {"test_classes": [], "classes_left_out": {str(k): v for k, v in dropped.items()}}
    r = pd.concat(parts)
    return {"scale": P.T2_HEADS[set_]["scale"], "features": list(PED0), "estimator": f"ridge alpha {P.RIDGE_ALPHA}",
            "label": f"{set_} first FV inside the PRE window", "test_classes": [int(t) for t in by_class],
            "classes_left_out": {str(k): v for k, v in dropped.items()},
            "pooled": P._reg(r[lab].values, r["_pred"].values, r["_const"].values, r.mlbam.values),
            "by_side": {s: {"n": int((r.pitcher == v).sum()),
                            "mae": round(float((r[r.pitcher == v]._pred - r[r.pitcher == v][lab]).abs().mean()), 3),
                            "mae_const": round(float((r[r.pitcher == v]._const - r[r.pitcher == v][lab]).abs().mean()), 3)}
                        for s, v in (("hit", 0.0), ("pit", 1.0)) if (r.pitcher == v).any()},
            "by_class": by_class}


def _window_rule(frame, window):
    a = {"DRAFT": "the last day of the draft", "SIGNED": "Aug 2 of the draft year",
         "NOLINE_OCT": "Oct 15 of the draft year"}[frame]
    end = "Apr 15 of the next year" if window == "PRE" else "Oct 15 of the next year"
    return f"first grade after {a} and on or before {end}"


def verdict(block):
    pr = block["DRAFT"]["T1"]["ANY_PRE"].get("pooled") or {}
    lo_a = (pr.get("auc_minus_draft_order_ci95") or [None])[0]
    lo_p = (pr.get("ap_minus_draft_order_ci95") or [None])[0]
    if lo_a is not None and lo_p is not None and lo_a > 0 and lo_p > 0:
        sel = ("the head orders who is graded better than draft order (AUC and AP deltas over the "
               "draft-order null both with CI95 above 0)")
    else:
        sel = ("draft order is the head: the fitted pedigree head does not beat a zero-fit pick-order "
               "rank on both AUC and AP with CI95 above 0, so no fitted head is proposed")
    lev = {}
    for s, h in block["DRAFT"]["T2"].items():
        p = h.get("pooled") or {}
        hi = (p.get("mae_minus_const_ci95") or [None, None])[1]
        lev[s] = ("below the constant (MAE minus constant CI95 below 0)" if hi is not None and hi < 0
                  else "no level claim: MAE minus constant CI95 does not sit below 0")
    return {"rule": "pre-declared, section 5 of " + PREDECLARATION, "selection": sel, "level": lev}


def run(as_of: str | None = None, *, data_dir=None, cache_dir=None, db_path=None, inp=None) -> dict:
    as_of = as_of or datetime.date.today().isoformat()
    warnings.filterwarnings("ignore", category=UserWarning)
    inp = inp or P.Inputs(data_dir=data_dir, cache_dir=cache_dir, db_path=db_path)
    picks = load_picks(cache_dir)
    frames, counts = {}, {}
    for fr in ("DRAFT", "SIGNED", "NOLINE_OCT"):
        frames[fr], counts[fr] = build_frame(inp, picks, as_of, fr)
    d, sd = frames["DRAFT"], inp.src_days
    block = {
        "label": "BACKCAST", "generated_at": P._now_iso(), "as_of": as_of,
        "producer": "tools/provisional_draftee_lab.py", "predeclaration": PREDECLARATION,
        "predeclared_commit": PREDECLARED_COMMIT,
        "label_note": ("development read of the PV-10 draftee head (players with no pro line), forward-chained "
                       "on the 2017 to 2025 draft classes: each test class is scored only by models trained on "
                       "earlier classes. It adjudicates nothing and nothing is served from it."),
        "reads_no_war": True, "served": False, "feeds_efv": False,
        "params": dict(P.PARAMS), "features_ped0": list(PED0), "features_ped1": list(PED1),
        "draft_end": {str(k): v for k, v in DRAFT_END.items()}, "capture_floor": P.CAPTURE_FLOOR,
        "universe": counts,
        "DRAFT": {"T1": {f"{s}_{w}": t1_head(d, sd, "DRAFT", s, w, as_of)
                         for s, w in (("ANY", "PRE"), ("FG", "PRE"), ("MLBP", "PRE"), ("ANY", "G12"))},
                  "T2": {s: t2_head(d, sd, s, as_of) for s in ("FG", "MLBP")}},
        "SIGNED": {"T1": {"ANY_PRE": t1_head(frames["SIGNED"], sd, "SIGNED", "ANY", "PRE", as_of,
                                             cols=PED1, compare_cols=PED0)}},
        "NOLINE_OCT": {"T1": {"ANY_PRE": t1_head(frames["NOLINE_OCT"], sd, "NOLINE_OCT", "ANY", "PRE", as_of)}},
        "identity_coverage": inp.identity_coverage,
    }
    block["verdict"] = verdict(block)
    return block


def persist(block, eval_path=None) -> Path:
    path = Path(eval_path) if eval_path is not None else P.EVAL_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"schema": P.SCHEMA, "model_id": P.MODEL_ID}
    doc[BLOCK] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    P._write_json(path, doc)
    return path


if __name__ == "__main__":
    b = run()
    if "--print" not in sys.argv:
        print("wrote", persist(b))
    print(json.dumps({k: b[k] for k in ("universe", "verdict")}, indent=1))
    for fr in ("DRAFT", "SIGNED", "NOLINE_OCT"):
        for k, h in b[fr]["T1"].items():
            print(fr, k, json.dumps(h.get("pooled")))
    for k, h in b["DRAFT"]["T2"].items():
        print("T2", k, json.dumps(h.get("pooled")))

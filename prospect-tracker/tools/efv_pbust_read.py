# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-17: score the P(bust) chip (efv_v2_model "DS-17") by Brier and log loss on the
development frames, calibration reported by side.

ARMS, fixed before the read (each fitted per fold on earlier rows only):
  consensus     logistic of REACHED on the consensus percentile alone (the reference)
  reached_head  the REACHED/timing head V2's order index uses (fit_timing_head, the
                frame's candidates, the DS-06 admission rule inside the fold)
  chip          reached_head plus the FG-vs-Pipeline spread when the admission rule
                admits it inside the fold: THE CHIP
  spread_forced reached_head plus the spread whenever enough training rows observe it
                (a diagnostic of the spread's own calibration value; never served)

FRAMES (development, spent; adjudicate nothing):
  lv_dev      list vintages 2017 to 2019 (V2's scored folds), each fitted on labelled
              list-vintage rows before V with every player in the V frame left out;
              REACHED is R3 (a debut inside V..V+3), outcome-blind ids.
  vm_oos_dev  the v1 matrices, decision years 2017 to 2024, forward-chained; REACHED is
              the matrix's debuted-versus-never split (recent busts left out).

STATISTICS. Brier and log loss of P(bust) against the realized bust flag (lower is
better), AUC for context; paired player-clustered bootstrap B 1000 (the claim seed) on
each arm's difference from the reference and on the chip's difference from the head;
calibration of every arm by side (calibration below: in the large, logistic
recalibration intercept and slope, a reliability table over equal-count ranges of the
predicted probability).

NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025+ debut cohorts (R-VM); the
spread may not be credited on R-LV (bug B9a). Nothing is grouped by consensus-FV level.

WRITES data/efv_v2_pbust_eval.json (development). efv_progress copies each frame into
data/efv_progress.json as a development row (table only: its raters carry an AUC for
reaching the majors, not a Spearman); tools/efv_arm_ledger.py counts the reads as probes.

Run:  python tools/efv_pbust_read.py            (writes the artifact)
      python tools/efv_pbust_read.py --dry-run  (prints, writes nothing)
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_labels as L  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_progress as P  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402
import efv_v2_assemble as ASM  # noqa: E402

OUT = H.DATA_DIR / "efv_v2_pbust_eval.json"
B = 1000
SEED = SB._CLAIM_SEED
ARMS = ("consensus", "reached_head", "chip", "spread_forced")
LV_FOLDS = tuple(ASM.DEV_FOLDS)
VM_YEARS = tuple(y for y in V1.SCORED_YEARS if y >= H.V2_FIRST_SCORED_YEAR)
FRAME_META = {
    "lv_dev": {"frame_version": "lv1_pbust", "reached": "R3 (a debut inside V..V+3)",
               "tilt": ""},
    "vm_oos_dev": {"frame_version": "v1_oos_pbust",
                   "reached": "the v1 matrix split: debuted versus never (recent busts out)",
                   "tilt": ("TILTED toward any head that reads level: a debuted matrix "
                            "row is read just before its debut, so its level at the read "
                            "foretells the debut. ")},
}


# ---------------------------------------------------------------------------
# scores (the read's, not the model's: the model never clips a prediction)

def brier(p_bust, bust) -> float:
    p, y = np.asarray(p_bust, dtype=np.float64), np.asarray(bust, dtype=np.float64)
    return float(np.mean((p - y) ** 2))


def log_loss(p_bust, bust, eps: float = 1e-12) -> float:
    p = np.clip(np.asarray(p_bust, dtype=np.float64), eps, 1.0 - eps)
    y = np.asarray(bust, dtype=np.float64)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def calibration(p_bust, bust, n_ranges: int = 10) -> dict:
    """Calibration of predicted P(bust) against the realized bust flag: calibration in
    the large (mean predicted minus observed), the logistic recalibration intercept and
    slope (y ~ a + b * logit(p); a calibrated forecast reads a 0, b 1), and a
    reliability table over equal-count ranges of the PREDICTED probability with the
    expected calibration error. Never by grade level."""
    p = np.clip(np.asarray(p_bust, dtype=np.float64), 1e-9, 1 - 1e-9)
    y = np.asarray(bust, dtype=np.float64)
    n = p.size
    lg = np.log(p / (1 - p))
    ab = H._logistic(np.column_stack([np.ones(n), lg]), y, np.zeros(n),
                   np.array([H._OFFSET_EPS, H._OFFSET_EPS]))
    order = np.argsort(p, kind="mergesort")
    parts = np.array_split(order, min(int(n_ranges), max(1, n)))
    table, ece = [], 0.0
    for ix in parts:
        if ix.size == 0:
            continue
        mp, my = float(p[ix].mean()), float(y[ix].mean())
        ece += ix.size / n * abs(mp - my)
        table.append({"n": int(ix.size), "p_lo": round(float(p[ix].min()), 4),
                      "p_hi": round(float(p[ix].max()), 4),
                      "mean_predicted": round(mp, 4), "observed": round(my, 4)})
    return {"n": int(n), "mean_predicted": round(float(p.mean()), 4),
            "observed": round(float(y.mean()), 4),
            "in_the_large": round(float(p.mean() - y.mean()), 4),
            "recal_intercept": round(float(ab[0]), 4), "recal_slope": round(float(ab[1]), 4),
            "ece": round(ece, 4), "reliability": table}


def _guards() -> dict:
    g = ASM._guards()
    if max(VM_YEARS) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise F.ReservedFrameError("a vm year reaches the R-VM cohorts")
    if set(LV_FOLDS) & set(F.RESERVED_LV) or max(LV_FOLDS) > max(F.DEV_VINTAGES):
        raise F.ReservedFrameError(f"a list-vintage fold is reserved: {LV_FOLDS}")
    g.update({"lv_folds": list(LV_FOLDS), "vm_years": list(VM_YEARS)})
    return g


def _fold_preds(train, test, side, frame) -> tuple[dict, dict]:
    """{arm: [p_bust per test row]} and a receipt of the fold's fits."""
    head = H.fit_timing_head(
        train, side, ids_outcome_blind=frame == "lv",
        absence_admitted=frame == "lv" and H.absence_admitted(side),
        candidates=H.timing_candidates(
            side, ids_outcome_blind=frame == "lv",
            absence_admitted=frame == "lv" and H.absence_admitted(side)))
    models = {
        "consensus": H.fit_pbust(train, side, frame=frame, consensus_only=True),
        "reached_head": H.fit_pbust(train, side, frame=frame, timing=head, spread="off"),
        "chip": H.fit_pbust(train, side, frame=frame, timing=head, spread="admit"),
        "spread_forced": H.fit_pbust(train, side, frame=frame, timing=head, spread="force"),
    }
    preds = {a: [p["p_bust"] for p in H.predict_pbust(m, test)] for a, m in models.items()}
    chip = models["chip"]
    rec = {"n_train": len(train), "n_test": len(test),
           "n_test_with_spread": sum(1 for r in test if r.get(H.PBUST_SPREAD_KEY) is not None),
           "head_keys": (models["reached_head"]["timing"] or {}).get("keys"),
           "head_alpha": H._akey((models["reached_head"]["timing"] or {}).get("alpha",
                                                                              math.inf)),
           "spread_admission": chip["spread_admission"],
           "spread_admitted": chip["spread_used"],
           "c_spread_chip": round(chip["c_spread"], 6),
           "c_spread_forced": round(models["spread_forced"]["c_spread"], 6),
           "n_spread_train": chip["n_spread_train"]}
    return preds, rec


def _lv_rows() -> dict[str, list[dict]]:
    frames = ASM.build_frames()
    out = {}
    for side in F.SIDES:
        rows = H.lv_training_rows(side, frames[side])
        pairs = {}
        for V, (frows, _labs) in frames[side].items():
            for r in frows:
                g = r.get("grades") or {}
                pairs[(r["player_key"], int(V))] = (g.get("fangraphs"), g.get("mlb_pipeline"))
        sp = H.spread_values([pairs.get((r["player_key"], r["decision_year"])) for r in rows],
                             [r["decision_year"] for r in rows])
        for r, s in zip(rows, sp):
            r[H.PBUST_SPREAD_KEY] = s
        out[side] = {"rows": rows,
                     "frame_keys": {V: {r["player_key"] for r in frames[side][V][0]}
                                    for V in LV_FOLDS}}
    return out


def _vm_rows() -> dict[str, list[dict]]:
    from efv_dataset import matrix_path
    out = {}
    for side in F.SIDES:
        raw = {r["player_key"]: r
               for r in json.loads(matrix_path(side).read_text(encoding="utf-8"))}
        rows = [r for r in H.matrix_training_rows(side)
                if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
        sp = H.spread_values([(raw[r["player_key"]].get("fv_fangraphs"),
                               raw[r["player_key"]].get("fv_mlb_pipeline")) for r in rows],
                             [r["decision_year"] for r in rows])
        for r, s in zip(rows, sp):
            r[H.PBUST_SPREAD_KEY] = s
        out[side] = rows
    return out


def _collect(frame: str, data) -> dict:
    """Out-of-fold predictions for every arm: rows [(side, player, year, bust)] and
    {arm: array}, plus per-fold receipts."""
    keys, preds, receipts = [], {a: [] for a in ARMS}, {}
    for side in F.SIDES:
        if frame == "lv":
            rows, fk = data[side]["rows"], data[side]["frame_keys"]
            folds = [(V, [r for r in rows if r["decision_year"] < V
                          and r["player_key"] not in fk[V]],
                      [r for r in rows if r["decision_year"] == V]) for V in LV_FOLDS]
        else:
            rows = data[side]
            folds = [(y, [r for r in rows if r["decision_year"] < y],
                      [r for r in rows if r["decision_year"] == y]) for y in VM_YEARS]
        for yr, tr, te in folds:
            H._check_scored_year(yr)
            if len(te) < H.MIN_TEST_ROWS or len(tr) < H.MIN_TRAIN_ROWS:
                continue
            pr, rec = _fold_preds(tr, te, side, frame)
            receipts[f"{side}|{yr}"] = rec
            for a in ARMS:
                preds[a] += pr[a]
            keys += [(side, r["player_key"], int(yr), 1.0 - float(r["reached"]),
                      r.get(H.PBUST_SPREAD_KEY) is not None) for r in te]
    return {"keys": keys, "preds": {a: np.asarray(v, float) for a, v in preds.items()},
            "folds": receipts}


def _auc(p, y) -> float | None:
    p, y = np.asarray(p, float), np.asarray(y, float)
    pos, neg = p[y == 1], p[y == 0]
    if not pos.size or not neg.size:
        return None
    from scipy.stats import rankdata
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def _metrics(p, y) -> dict:
    return {"brier": brier(p, y), "log_loss": log_loss(p, y), "auc": _auc(p, y)}


def _score(col: dict) -> dict:
    keys = col["keys"]
    y = np.asarray([k[3] for k in keys], float)
    side = np.asarray([k[0] for k in keys])
    players = np.asarray([k[1] for k in keys])
    subsets = {"both": np.arange(y.size), "hit": np.where(side == "hit")[0],
               "pit": np.where(side == "pit")[0]}
    point = {s: {a: _metrics(col["preds"][a][ix], y[ix]) for a in ARMS}
             for s, ix in subsets.items()}
    uniq, inv = np.unique(players, return_inverse=True)
    members = [np.where(inv == i)[0] for i in range(uniq.size)]
    rng = np.random.default_rng(SEED)
    comps = (("reached_head", "consensus"), ("chip", "consensus"),
             ("chip", "reached_head"), ("spread_forced", "reached_head"))
    boot = {s: {f"{a}_minus_{b}": {m: [] for m in ("brier", "log_loss", "auc")}
                for a, b in comps} for s in subsets}
    for _ in range(B):
        ix = np.concatenate([members[i] for i in rng.integers(0, uniq.size, uniq.size)])
        for s in subsets:
            jx = ix if s == "both" else ix[side[ix] == s]
            yy = y[jx]
            m = {a: _metrics(col["preds"][a][jx], yy) for a in ARMS}
            for a, b in comps:
                for k in ("brier", "log_loss", "auc"):
                    if m[a][k] is not None and m[b][k] is not None:
                        boot[s][f"{a}_minus_{b}"][k].append(m[a][k] - m[b][k])
    deltas = {}
    for s in subsets:
        deltas[s] = {}
        for a, b in comps:
            d = {}
            for k in ("brier", "log_loss", "auc"):
                pa, pb = point[s][a][k], point[s][b][k]
                v = boot[s][f"{a}_minus_{b}"][k]
                d[k] = {"delta": None if pa is None or pb is None else round(pa - pb, 5),
                        "ci95": ([round(float(x), 5) for x in np.percentile(v, [2.5, 97.5])]
                                 if v else None)}
            deltas[s][f"{a}_minus_{b}"] = d
    calib = {s: {a: calibration(col["preds"][a][ix], y[ix]) for a in ARMS}
             for s, ix in subsets.items() if s != "both"}
    rnd = {s: {a: {k: (None if v is None else round(v, 5)) for k, v in m.items()}
               for a, m in pa.items()} for s, pa in point.items()}
    return {"n": int(y.size), "n_by_side": {s: int(ix.size) for s, ix in subsets.items()
                                            if s != "both"},
            "n_players": int(uniq.size), "bust_rate": round(float(y.mean()), 4),
            "point": rnd, "deltas": deltas, "calibration_by_side": calib,
            "n_with_spread": int(sum(1 for k in keys if k[4]))}


def _where(ci) -> str:
    if not ci:
        return "no interval"
    lo, hi = ci
    return "above zero" if lo > 0 else ("below zero" if hi < 0 else "spans zero")


def _progress_frame(fid: str, sc: dict, window: list[int]) -> dict:
    pt, dl = sc["point"]["both"], sc["deltas"]["both"]
    cb, cl = dl["chip_minus_consensus"]["brier"], dl["chip_minus_consensus"]["log_loss"]
    ca = dl["chip_minus_consensus"]["auc"]
    return {
        "frame_version": FRAME_META[fid]["frame_version"],
        "window": window, "n": sc["n"], "n_by_side": sc["n_by_side"],
        "outcome": "bust flag: not " + FRAME_META[fid]["reached"],
        "raters": {"efv": {"spearman": None, "auc": pt["chip"]["auc"], "n": sc["n"]},
                   "prospx_consensus": {"spearman": None, "auc": pt["consensus"]["auc"],
                                        "n": sc["n"]}},
        "deltas": {"vs_prospx_consensus": {"auc": {
            "delta": ca["delta"], "ci95": ca["ci95"], "mde95": None, "estimator": None,
            "ci95_estimator": "paired, player-clustered, B 1000",
            "reading": f"development only; CI95 {_where(ca['ci95'])}"}}},
        "verdict": (f"development only; {'tilted; ' if FRAME_META[fid]['tilt'] else ''}"
                    f"P(bust) Brier chip minus consensus-only CI95 {_where(cb['ci95'])}"),
        "note": (f"DS-17 P(bust) chip read (REACHED head plus the FG-vs-Pipeline spread "
                 f"when admitted): Brier {pt['chip']['brier']} against consensus-only "
                 f"{pt['consensus']['brier']} (delta {cb['delta']}, CI95 {cb['ci95']}); "
                 f"log loss {pt['chip']['log_loss']} against {pt['consensus']['log_loss']} "
                 f"(delta {cl['delta']}, CI95 {cl['ci95']}). The AUC is for reaching the "
                 f"majors, not the WAR label. {FRAME_META[fid]['tilt']}Spent frame, not a "
                 f"claim."),
    }


#: Which arm the served chip may use (DS_F). WRITTEN AFTER THIS READ FIRST RAN, and
#: disclosed as such in the artifact: the chip (the REACHED head, plus the spread where
#: admitted) serves only if its Brier beats the consensus-only arm with a CI95 below zero
#: on the list-vintage frame, the one frame whose read date and ids are outcome-blind.
#: Otherwise the served P(bust) is the consensus-only arm. vm_oos_dev cannot decide it:
#: a debuted matrix row is read just before its debut, so level at the read foretells
#: the debut there and flatters any head that reads level.
SERVING_RULE = ("serve the chip only if its Brier minus the consensus-only arm has a CI95 "
                "below zero on lv_dev (both sides pooled); otherwise serve the "
                "consensus-only arm")


def serving_arm(scores: dict) -> dict:
    d = scores["lv_dev"]["deltas"]["both"]["chip_minus_consensus"]["brier"]
    ci = d.get("ci95")
    arm = "chip" if (ci and ci[1] < 0) else "consensus"
    return {"arm": arm, "rule": SERVING_RULE, "rule_written_after_read": True,
            "lv_dev_brier_chip_minus_consensus": d}


def run() -> dict:
    t0 = time.time()
    guards = _guards()
    lv = _collect("lv", _lv_rows())
    vm = _collect("vm", _vm_rows())
    scores = {"lv_dev": _score(lv), "vm_oos_dev": _score(vm)}
    folds = {"lv_dev": lv["folds"], "vm_oos_dev": vm["folds"]}
    windows = {"lv_dev": [min(LV_FOLDS), max(LV_FOLDS)],
               "vm_oos_dev": [min(VM_YEARS), max(VM_YEARS)]}
    probes = {}
    for fid, sc in scores.items():
        for s in ("hit", "pit"):
            for a in ("reached_head", "chip", "spread_forced"):
                d = sc["deltas"][s][f"{a}_minus_consensus"] if a != "spread_forced" \
                    else sc["deltas"][s]["spread_forced_minus_reached_head"]
                tag = f"DS-17:{fid}.{s}.{a}"
                probes[tag] = {"tag": tag, "verdict": "READ", "ci95": d["brier"]["ci95"],
                               "reason": f"Brier delta {d['brier']['delta']}"}
    admitted = {fid: sorted(k for k, r in f.items() if r["spread_admitted"])
                for fid, f in folds.items()}
    serving = serving_arm(scores)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    mv = P.current_model_version(commit=commit)
    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_pbust_read.py",
        "model_id": H.PBUST_MODEL_ID,
        "role": "development",
        "adjudicates": False,
        "item": "DS-17, docs/efv-v2/DRIVER_SYSTEM_V2.md",
        "reserved_guard": guards,
        "label": {"id": mv.get("label"), "provider": L.provider(),
                  "resolved_through": L.resolved_through()},
        "code": {"commit": commit},
        "arms": {"consensus": "logistic of REACHED on the consensus percentile alone",
                 "reached_head": "the V2 REACHED/timing head (admission rule inside the fold)",
                 "chip": "reached_head plus the FG-vs-Pipeline spread when admitted in the fold",
                 "spread_forced": "reached_head plus the spread always (diagnostic, never served)"},
        "spread": ("|within-(side, year) percentile of Pipeline minus that of FanGraphs|, "
                   "rows carrying both grades only (FanGraphs from list vintage 2017); may "
                   "not be credited on R-LV (bug B9a)"),
        "spread_admitted_folds": admitted,
        "serving": serving,
        "frames_scored": scores,
        "folds": folds,
        "frames": {fid: _progress_frame(fid, sc, windows[fid]) for fid, sc in scores.items()},
        "probes": probes,
        "n_probes": len(probes),
        "elapsed_s": round(time.time() - t0, 1),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    doc = run()
    for fid, sc in doc["frames_scored"].items():
        print(fid, "n", sc["n"], "bust rate", sc["bust_rate"])
        for s in ("hit", "pit", "both"):
            print("  ", s, {a: (m["brier"], m["log_loss"], m["auc"])
                            for a, m in sc["point"][s].items()})
            for k, d in sc["deltas"][s].items():
                print("     ", k, "brier", d["brier"], "logloss", d["log_loss"])
        for s, c in sc["calibration_by_side"].items():
            print("   calib", s, {a: (m["in_the_large"], m["recal_slope"], m["ece"])
                                  for a, m in c.items()})
    print("spread admitted", doc["spread_admitted_folds"])
    print("serving", doc["serving"]["arm"])
    if not args.dry_run:
        OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

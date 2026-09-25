# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-11 (bug B6): grade the served eFV overlays out of sample.

efv_score.run_live applies overlays to the model leg that efv_model.oos_grades never
applied (efv_overlays.py lists all seven). This read applies each GRADEABLE model-leg
overlay (efv_overlays.GRADED: injury, age, role) inside oos_grades, through the same
two functions run_live uses, with every input read AS OF the row's read
(efv_overlays.asof_inputs), and scores the result against the six-season label.

THE FRAME. eFV v1's own out-of-sample pool: the v1 training matrices, every decision
year in efv_model.SCORED_YEARS scored by a fit on earlier years (debuted rows and
resolved busts, recent busts left out, as oos_grades does), restricted to the rows with
a MiLB block, which is the population the live board scores (run_live abstains on a row
without one) and the only rows an overlay can reach. Decision years stop at 2024, so no
2025+ debut cohort (R-VM) is read; no list vintage is read at all (R-LV untouched).
Development only: a spent frame, adjudicates nothing.

THE STATISTIC (owner answer DS-Q3). Primary: the size-weighted mean over (side, decision
year) groups of the Spearman correlation between the scored object and the label.
Secondary: pooled Spearman per side. Paired player-clustered bootstrap, B 1000, the
claim seed. Two objects: the scored object (rank_war, the guarded blend oos_grades
scores) and the board object (the model leg, which the served grade maps from).

THE RULE (efv_overlays.DISPOSITION_RULE) was fixed before this read ran and is copied
into the artifact. Overlays with no as-of input (Statcast+, the S-XLINE lean) cannot be
graded and leave the grade as chips by that rule; the dispersion and side-fairness maps
cannot reorder a side and are retired from the V2 grade.

WRITES data/efv_overlay_oos_eval.json (development). efv_progress copies its frame into
data/efv_progress.json as a development row; tools/efv_arm_ledger.py counts its reads as
probes.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): groups are (side, decision year) only;
nothing is grouped, counted or averaged by consensus-FV level.

Run:  python tools/efv_overlay_oos_read.py            (writes the artifact)
      python tools/efv_overlay_oos_read.py --dry-run  (prints, writes nothing)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_labels as L  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_overlays as OV  # noqa: E402
import efv_progress as P  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402
from efv_dataset import matrix_path  # noqa: E402

OUT = OV.EVAL_PATH
B = 1000
SEED = SB._CLAIM_SEED
MODEL_ID = "efv_v1_overlays"
FRAME_ID = "vm_oos_dev"
FRAME_VERSION = "v1_oos_block"
#: The arms, fixed before the read: each gradeable overlay alone, then all together.
ARMS: dict[str, tuple[str, ...]] = {**{k: (k,) for k in OV.GRADED}, "all": OV.GRADED}


def _guards() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    if max(V1.SCORED_YEARS) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise F.ReservedFrameError("a scored decision year reaches the R-VM cohorts")
    return {"decision_years": list(V1.SCORED_YEARS),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "list_vintages_read": [], "reserved_lv": sorted(F.RESERVED_LV)}


def _rho(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.size < 3 or x.std() == 0 or y.std() == 0:
        return None
    rx, ry = rankdata(x), rankdata(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def _within(score, y, grp, ix) -> float | None:
    """Size-weighted mean of per-group Spearman over the rows ix (grp labels)."""
    tot, wsum = 0.0, 0
    g = grp[ix]
    for u in np.unique(g):
        m = ix[g == u]
        r = _rho(score[m], y[m])
        if r is None:
            continue
        tot += r * m.size
        wsum += m.size
    return (tot / wsum) if wsum else None


def _stats(objs: dict, y, grp, side_arr, ix) -> dict:
    out = {}
    for name, sc in objs.items():
        rec = {"within": _within(sc, y, grp, ix)}
        for s in ("hit", "pit"):
            m = ix[side_arr[ix] == s]
            rec[f"within_{s}"] = _within(sc, y, grp, m)
            rec[f"pooled_{s}"] = _rho(sc[m], y[m])
        out[name] = rec
    return out


def _side_rows(side: str) -> tuple[list[dict], dict]:
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    return full, {d["player_key"]: d for d in V1._prep(full, "target_censored", side)}


def run() -> dict:
    t0 = time.time()
    guards = _guards()
    events = OV.il_events()
    keys, y, grp, sides, objs, fires, n_by_side = [], [], [], [], {}, {}, {}
    per_side = {}
    for side in ("hit", "pit"):
        full, prep = _side_rows(side)
        inputs = OV.asof_inputs(full, events)
        legs_off: dict = {}
        off = V1.oos_grades(side, legs=legs_off)
        arm_scores, arm_legs = {}, {}
        for arm, ovs in ARMS.items():
            lg: dict = {}
            arm_scores[arm] = V1.oos_grades(side, overlays=ovs, overlay_inputs=inputs, legs=lg)
            arm_legs[arm] = lg
        rows = [k for k in off
                if V1._has_milb_block(prep[k]["feats"])
                and int(prep[k]["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
        n_by_side[side] = len(rows)
        per_side[side] = {"rows": rows, "off": off, "legs_off": legs_off,
                          "arm_scores": arm_scores, "arm_legs": arm_legs, "prep": prep}
        fires[side] = {arm: sum(1 for k in rows
                                if arm_legs[arm][k]["model_war"] != legs_off[k]["model_war"])
                       for arm in ARMS}
        keys += [f"{side}:{k}" for k in rows]
        y += [prep[k]["target"] for k in rows]
        grp += [f"{side}|{prep[k]['decision_year']}" for k in rows]
        sides += [side] * len(rows)
    y = np.asarray(y, float)
    grp = np.asarray(grp)
    side_arr = np.asarray(sides)

    def col(fn):
        vals = []
        for side in ("hit", "pit"):
            ps = per_side[side]
            vals += [fn(ps, k) for k in ps["rows"]]
        return np.asarray(vals, float)

    objs["consensus"] = col(lambda ps, k: ps["prep"][k]["fv"])
    objs["off"] = col(lambda ps, k: ps["off"][k])
    objs["off_model_leg"] = col(lambda ps, k: ps["legs_off"][k]["model_war"])
    for arm in ARMS:
        objs[arm] = col(lambda ps, k, a=arm: ps["arm_scores"][a][k])
        objs[f"{arm}_model_leg"] = col(lambda ps, k, a=arm: ps["arm_legs"][a][k]["model_war"])

    n = y.size
    ix_all = np.arange(n)
    point = _stats(objs, y, grp, side_arr, ix_all)
    # player-clustered bootstrap (a player_key appears once per side)
    players = np.asarray([k.split(":", 1)[1] for k in keys])
    uniq, inv = np.unique(players, return_inverse=True)
    members = [np.where(inv == i)[0] for i in range(uniq.size)]
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(B):
        pick = rng.integers(0, uniq.size, uniq.size)
        ix = np.concatenate([members[p] for p in pick])
        boots.append(_stats(objs, y, grp, side_arr, ix))

    def delta(a, b, stat):
        pa, pb = point[a][stat], point[b][stat]
        if pa is None or pb is None:
            return None
        ds = [bt[a][stat] - bt[b][stat] for bt in boots
              if bt[a][stat] is not None and bt[b][stat] is not None]
        lo, hi = (np.percentile(ds, [2.5, 97.5]) if ds else (None, None))
        return {"delta": round(pa - pb, 5),
                "ci95": [round(float(lo), 4), round(float(hi), 4)] if ds else None,
                "n_boot": len(ds)}

    def reading(d):
        if not d or d.get("ci95") is None:
            return "development only; no interval"
        lo, hi = d["ci95"]
        where = "above zero" if lo > 0 else ("below zero" if hi < 0 else "spans zero")
        return f"development only; CI95 {where}"

    stats_all = ["within", "within_hit", "within_pit", "pooled_hit", "pooled_pit"]
    overlays = {}
    arms_out = {}
    for arm in ARMS:
        blk = {"overlays": list(ARMS[arm]),
               "fires": fires["hit"][arm] + fires["pit"][arm],
               "fires_by_side": {s: fires[s][arm] for s in ("hit", "pit")},
               "scored_object": {st: delta(arm, "off", st) for st in stats_all},
               "board_object": {st: delta(f"{arm}_model_leg", "off_model_leg", st)
                                for st in stats_all},
               "vs_consensus": {st: delta(arm, "consensus", st) for st in stats_all}}
        arms_out[arm] = blk
        if arm in OV.OVERLAYS:
            overlays[arm] = {s: {"fires": fires[s][arm],
                                 "within": blk["scored_object"][f"within_{s}"],
                                 "pooled": blk["scored_object"][f"pooled_{s}"],
                                 "board_within": blk["board_object"][f"within_{s}"]}
                             for s in ("hit", "pit")}
    for name in OV.OVERLAYS:
        overlays.setdefault(name, None)
    disp = {k: OV.decide(k, overlays.get(k)) for k in OV.OVERLAYS}

    def rater(name):
        return {"spearman": None if point[name]["within"] is None
                else round(point[name]["within"], 4), "auc": None, "n": int(n)}

    def leg(a, b, key):
        d = delta(a, b, "within")
        return {"spearman": {"delta": d["delta"], "ci95": d["ci95"], "mde95": None,
                             "estimator": None,
                             "ci95_estimator": "paired, player-clustered, B 1000",
                             "reading": reading(d),
                             "key": f"frames.{FRAME_ID}.deltas.{key}.spearman"}}

    frame = {
        "frame_version": FRAME_VERSION,
        "window": [min(V1.SCORED_YEARS), max(V1.SCORED_YEARS)],
        "n": int(n), "n_by_side": n_by_side,
        "statistic": ("size-weighted mean of within-(side, decision year) Spearman "
                      "(owner answer DS-Q3 primary)"),
        "outcome": "six-season WAR label (target_censored), v1's own training label",
        "raters": {"efv": rater("all"), "efv_v1": rater("off"),
                   "prospx_consensus": rater("consensus")},
        "deltas": {"vs_prospx_consensus": leg("all", "consensus", "vs_prospx_consensus"),
                   "vs_efv_v1": leg("all", "off", "vs_efv_v1"),
                   "efv_v1_vs_prospx_consensus": leg("off", "consensus",
                                                     "efv_v1_vs_prospx_consensus")},
        "verdict": reading(delta("all", "off", "within")),
        "note": ("DS-11 overlay read: eFV v1 WITH the gradeable served overlays (injury, "
                 "age, reliever ceiling) against v1 without them, on v1's own "
                 "forward-chained pool, rows with a MiLB block; within-(side, decision "
                 "year) Spearman; spent frame, not a claim"),
    }
    probes = {}
    for arm, blk in arms_out.items():
        for s in ("hit", "pit"):
            d = blk["scored_object"][f"within_{s}"]
            tag = f"DS-11:{s}.overlay.{arm}"
            probes[tag] = {"tag": tag, "verdict": "READ", "ci95": (d or {}).get("ci95"),
                           "reason": (f"fires on {blk['fires_by_side'][s]} rows; delta "
                                      f"{(d or {}).get('delta')}")}
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    mv = P.current_model_version(commit=commit)
    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_overlay_oos_read.py",
        "model_id": MODEL_ID,
        "role": "development",
        "adjudicates": False,
        "item": "DS-11 (bug B6), docs/efv-v2/DRIVER_SYSTEM_V2.md",
        "reserved_guard": guards,
        "label": {"id": mv.get("label"), "provider": L.provider(),
                  "resolved_through": L.resolved_through()},
        "code": {"commit": commit},
        "rule": OV.DISPOSITION_RULE,
        "rule_fixed_before_read": True,
        "registry": OV.OVERLAYS,
        "arms": arms_out,
        "overlays": overlays,
        "dispositions": disp,
        "on_grade": sorted(k for k, d in disp.items() if d["on_grade"]),
        "to_chips": sorted(k for k, d in disp.items() if d["disposition"] == "chip"),
        "retired": sorted(k for k, d in disp.items() if d["disposition"] == "retired"),
        "served_now": ("unchanged: eFV v1's board keeps every overlay until DS-02 serves V2 "
                       "(owner answer DS-Q1); the dispositions are what that step applies"),
        "point": {k: {kk: (None if vv is None else round(vv, 5)) for kk, vv in v.items()}
                  for k, v in point.items()},
        "frames": {FRAME_ID: frame},
        "probes": probes,
        "n_probes": len(probes),
        "elapsed_s": round(time.time() - t0, 1),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    doc = run()
    for arm, blk in doc["arms"].items():
        so = blk["scored_object"]
        print(f"{arm:6s} fires {blk['fires_by_side']}  within {so['within']}  "
              f"hit {so['within_hit']}  pit {so['within_pit']}")
    for k, d in doc["dispositions"].items():
        print(f"{k:14s} {d['disposition']:8s} {d['why']}")
    f = doc["frames"][FRAME_ID]
    print("raters", json.dumps(f["raters"]))
    if not args.dry_run:
        OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

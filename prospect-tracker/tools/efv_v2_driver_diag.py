# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_W2_DRIVER_DIAG: why the admitted drivers subtract (a DIAGNOSIS, not an arm).

Owner, 2026-10-08 (decisions EW2-1 to EW2-5): "We really need to fix eFV and find more
drivers so that it isn't just reliant on hit tool". EW2-1 asks for a driver-subtraction
diagnosis beside wave 2's screening. EFV3_C03 found the driver-permuted twins read about
+0.01 above V2 on both development frames (V2 minus consensus -0.0116 lv_dev, -0.0101
vm_dev on the frozen fWAR label); this tool says which driver, head, subgroup and label
change carry that gap. It admits nothing, removes nothing, writes no ledger row and moves
no served number; its artifact is a development diagnosis under data/_labs/.

FRAMES. Exactly the DS-16 development frames, built by tools/efv_v2_model_class_screen
.build_inputs (its guards, its per-fold training and test rows, its V2 base refit at the
P5 weights, data/efv_v2_assembly.json sha256 35fe32c7...): lv_dev at list vintages 2017 to
2019 (W3) and vm_dev at frame version vm2 (debut years 2017 to 2023, career WAR to date).
NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025 and later debut cohorts
(R-VM); the screen's guards run before any fit and every variant fold re-checks its rows.

THE FOUR PARTS.

 1. Per driver, per side: leave-one-out (V2 with that driver withheld from its head) and
    leave-one-in (V2's machinery with that driver the ONLY candidate), each refit per fold
    at the registered weights, within (side, vintage) delta against V2 and against PROSPX
    consensus, efv_v2_stat.paired_delta, E_cond, B 2000, seed 20260906. A driver is a
    (head, key) pair (level_rank sits in both hitter heads). Admission (DS-06) is per key
    and the penalty is chosen on the admitted keys only, so withholding a key no fold
    admitted reproduces V2 exactly; such rows are marked identical and not bootstrapped.
    Two head rows (skill head alone, timing head alone) sit beside them. Leave-one-in of
    a pitcher TIMING driver relaxes the DS-Q2 rule (pitchers take the consensus order
    when no pitcher skill driver is admitted), which would otherwise make it consensus by
    construction; the row says so.
 2. Per driver: the slope sign and size on the eWAR v2 label and on the frozen fWAR
    label, as the DS-06 admission statistic (the t of the driver in y ~ 1 + u_c + z(x)
    per training vintage) and as one pooled partial slope (percentile points of the
    target per SD of the driver, given the consensus percentile). lv: the same frame rows
    labelled by efv_labels.labels_for_frame on each provider's WAR table (a provider-only
    switch, RESOLVED_THROUGH held). vm (the matrices the served production fit trains
    on): the epoch lab's arm matrices (data/_labs/fwar_epoch_arms, E0 = the eWAR label as
    served before the epoch, F1 = the shipped settings with only the WAR series reverted
    to eWAR, Estar = all epoch settings) beside the current served matrices.
 3. Which subgroup carries V2's gap to consensus: the within delta inside each cell of
    side, list year, level at list, position family (hitters), age band and archetype
    (efv_strata, the only module that defines a cell; never a consensus-FV cell), plus the
    exact additive split of the frame delta over its (side, vintage) groups and the
    rows V2 moved, by the direction it moved them.
 4. The served board at the 10-04 refit (c40c0dd0): the current served rows' order
    re-scored at the pre-refit weights (the production heads do not depend on the
    weights, so this isolates the refit exactly), and the realized change between the
    served artifact before (94ec6875) and after (44856cdd) the post-epoch rebuild; each
    says whether the order moved toward or away from consensus and by how many rows.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): no statistic here is grouped, counted or
averaged by consensus-FV level; the strata are efv_strata's cells, which carry none.

Run:  python -u tools/efv_v2_driver_diag.py --check   (frames, counts, base parity)
      python -u tools/efv_v2_driver_diag.py --epoch-arms-dir <dir with the arm matrices>
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
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

import efv_strata as ST  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402
import efv_v2_model_class_screen as MCS  # noqa: E402

OUT_PATH = H.DATA_DIR / "_labs" / "efv_v2_driver_diag.json"
TOOL = "tools/efv_v2_driver_diag.py"
ITEM = "EFV3_W2_DRIVER_DIAG"
NOTE = "development diagnosis on spent frames; admits nothing, removes nothing, not a claim"
FRAMES = MCS.FRAMES
FRAME_KIND = MCS.FRAME_KIND
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
CONS = MCS.CONS
V2_KEY = MCS.V2_KEY
VAR_KEY = "efv_v2_variant"
#: the 10-04 P5 refit and the served artifacts on either side of the post-epoch rebuild
REFIT_COMMIT = "c40c0dd0"
SERVED_BEFORE = "94ec6875"
SERVED_AFTER = "44856cdd"
ASSEMBLY_REL = "prospect-tracker/data/efv_v2_assembly.json"
XFV_REL = "prospect-tracker/data/xfv.json"
#: a stratum cell is scored at the scoreboard matrix's floors (lane D E3-Q4 = A)
CELL_FLOOR_ROWS = SB.ARCH_MIN_N
CELL_FLOOR_CLUSTERS = 20
STRATA_DIMS: tuple[str, ...] = ("side", "list_year", "level_at_list", "position_family",
                                "age_band", "archetype")
#: a row counts as moved when V2's within-group percentile differs from consensus's by
#: at least this much (one twentieth of the group)
MOVE_PCT = 0.05
EPOCH_ARMS = ("E0", "F1", "Estar")
EWAR_PROVIDER = "ewar_v2"
SIDE_LETTER = {"H": "hit", "P": "pit"}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                           text=True, encoding="utf-8", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _git_json(rev: str, rel: str) -> dict | None:
    txt = _git("show", f"{rev}:{rel}")
    if not txt:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def _is_under_data(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(H.DATA_DIR.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# part 1: the variant fit (fit_v2 with a restricted candidate list)
# ---------------------------------------------------------------------------

def candidate_units(side: str, kind: str, absent_ok: bool | None = None) -> list[tuple[str, str]]:
    """Every (head, key) V2 offers on this side and frame kind: the skill candidates and
    the timing candidates fit_v2 passes (lv: outcome-blind ids, protection and, when the
    balance report admits it, the absence flag; vm: neither)."""
    ob = kind == "lv"
    ab = ob and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    return ([("skill", k) for k in H.skill_candidates(side)]
            + [("timing", k) for k in H.timing_candidates(side, ids_outcome_blind=ob,
                                                          absence_admitted=ab)])


def fit_variant(train: list[dict], side: str, kind: str, weights: dict, *,
                drop=(), only=None, heads=("skill", "timing"), dsq2: bool = True,
                absent_ok: bool | None = None) -> dict:
    """fit_v2 on one fold with the candidate list restricted: `drop` withholds (head, key)
    units, `only` keeps just those units, `heads` keeps whole heads. With no restriction
    the heads, weights and order are fit_v2's own (asserted per fold by the caller).
    dsq2=False lets a pitcher timing head fit with no admitted skill driver (leave-one-in
    of a pitcher timing driver only)."""
    if kind not in ("lv", "vm"):
        raise ValueError(f"kind must be lv or vm, got {kind!r}")
    H._check_years({int(r["decision_year"]) for r in train})
    if kind == "lv":
        bad = sorted({int(r["decision_year"]) for r in train} & set(F.RESERVED_LV))
        if bad:
            raise F.ReservedFrameError(f"a training row sits at a reserved list vintage: {bad}")
    ob = kind == "lv"
    ab = ob and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    drop = {tuple(u) for u in drop}
    only = None if only is None else {tuple(u) for u in only}

    def keep(head, k):
        return (head in heads and (head, k) not in drop
                and (only is None or (head, k) in only))
    sc = tuple(k for k in H.skill_candidates(side) if keep("skill", k))
    tc = tuple(k for k in H.timing_candidates(side, ids_outcome_blind=ob, absence_admitted=ab)
               if keep("timing", k))
    skill = H.fit_skill_head(train, side, candidates=sc) if sc else None
    timing = None
    why = None
    if side == "pit" and dsq2 and not H.head_usable(skill):
        why = "owner DS-Q2: no pitcher skill driver admitted, consensus order"
    elif tc:
        timing = H.fit_timing_head(train, side, ids_outcome_blind=ob, absence_admitted=ab,
                                   candidates=tc)
    w = weights[side]
    w_s = float(w["w_skill"]) if H.head_usable(skill) else 0.0
    w_t = float(w["w_time"]) if H.head_usable(timing) else 0.0
    return {"model_id": "efv_v2_driver_diag_variant", "side": side, "frame": kind,
            "skill": skill, "timing": timing, "w_skill": w_s, "w_time": w_t,
            "consensus_only": w_s <= 0 and w_t <= 0, "consensus_only_reason": why,
            "war_map": None, "n_train": len(train),
            "skill_candidates": list(sc), "timing_candidates": list(tc)}


def _admitted(m: dict, head: str) -> list[str]:
    h = m.get(head)
    if not H.head_usable(h):
        return []
    return [k for k, b in zip(h.get("keys") or [], h.get("beta") or []) if abs(b) > 0]


def variant_orders(inputs: dict, fid: str, side: str, spec: dict, *, log=print) -> tuple[dict, dict]:
    """The variant's order index on every scored row of one side of one frame, fold by
    fold, with the per-fold receipt (admitted keys per head)."""
    fr = inputs["frames"][fid]
    kind = FRAME_KIND[fid]
    orders, receipts = {}, {}
    for fold in fr["folds"]:
        blk = fr["by_side"][side].get(fold)
        if blk is None:
            continue
        m = fit_variant(blk["train"], side, kind, inputs["weights"],
                        absent_ok=inputs.get("absent_ok"), **spec)
        pred = {p["player_key"]: float(p["order_idx"]) for p in H.predict_v2(m, blk["test"])}
        for c in blk["scored"]:
            orders[(side, fold, c["key"])] = pred[c["key"]]
        receipts[str(fold)] = {"skill": _admitted(m, "skill"), "timing": _admitted(m, "timing"),
                               "w_skill": m["w_skill"], "w_time": m["w_time"],
                               "consensus_only": m["consensus_only"]}
    return orders, receipts


def base_orders(inputs: dict, fid: str) -> dict:
    fr = inputs["frames"][fid]
    out = {}
    for side in F.SIDES:
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            for c in blk["scored"]:
                out[(side, fold, c["key"])] = float(c["grades"][V2_KEY])
    return out


def base_admission(inputs: dict, fid: str) -> dict:
    """{side: {fold: {head: [admitted keys]}}} of the V2 base fit."""
    fr = inputs["frames"][fid]
    out: dict = {}
    for side in F.SIDES:
        out[side] = {}
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            m = blk["v2_model"]
            out[side][str(fold)] = {"skill": _admitted(m, "skill"),
                                    "timing": _admitted(m, "timing"),
                                    "w_skill": m["w_skill"], "w_time": m["w_time"],
                                    "consensus_only": m["consensus_only"]}
    return out


def _rows_with(inputs: dict, fid: str, orders: dict, side: str | None = None) -> list[dict]:
    """The frame's scored rows with VAR_KEY = the variant's order where it has one and
    V2's order elsewhere; side restricts the rows."""
    out = []
    for c in MCS.scored_rows(inputs, fid):
        if side is not None and c["side"] != side:
            continue
        o = orders.get((c["side"], int(c["year"]), c["key"]), c["grades"][V2_KEY])
        out.append(dict(c, grades=dict(c["grades"], **{VAR_KEY: float(o)})))
    return out


def _within(rows, a, b, *, B, seed) -> dict:
    d = MCS.within_delta_only(rows, a, b, B=B, seed=seed)
    return {k: d.get(k) for k in ("n", "a", "b", "delta", "ci95", "mde95", "p_gt_0", "status")}


def base_deltas(inputs: dict, *, B: int, seed: int) -> dict:
    """V2 minus consensus, within, per frame and per side (the DS-16 numbers on these
    rows)."""
    out = {}
    for fid in FRAMES:
        rows = MCS.scored_rows(inputs, fid)
        out[fid] = {"all": _within(rows, V2_KEY, CONS, B=B, seed=seed)}
        for side in F.SIDES:
            out[fid][side] = _within([c for c in rows if c["side"] == side], V2_KEY, CONS,
                                     B=B, seed=seed)
    return out


def variant_specs(side: str, kind: str, absent_ok: bool | None) -> list[dict]:
    """Every variant of part 1 on one side and frame kind: per unit leave-one-out and
    leave-one-in, then the two single-head rows."""
    units = candidate_units(side, kind, absent_ok)
    out = []
    for head, key in units:
        out.append({"id": f"loo:{head}.{key}", "kind": "leave_one_out", "head": head,
                    "key": key, "spec": {"drop": [(head, key)]}})
    for head, key in units:
        relax = side == "pit" and head == "timing"
        out.append({"id": f"loi:{head}.{key}", "kind": "leave_one_in", "head": head,
                    "key": key, "spec": {"only": [(head, key)], "dsq2": not relax},
                    "dsq2_relaxed": relax})
    out.append({"id": "head:skill_only", "kind": "head", "head": "skill", "key": None,
                "spec": {"heads": ("skill",)}})
    out.append({"id": "head:timing_only", "kind": "head", "head": "timing", "key": None,
                "spec": {"heads": ("timing",), "dsq2": False},
                "dsq2_relaxed": side == "pit"})
    return out


def driver_table(inputs: dict, base: dict, *, B: int = B_DEFAULT, seed: int = SEED,
                 log=print) -> dict:
    """Part 1. {fid: {side: [variant rows]}}; each row carries the within delta against V2
    and against consensus on its side and on the whole frame, the per-fold deltas
    against V2 and the folds that admitted the unit."""
    out: dict = {}
    t0 = time.time()
    for fid in FRAMES:
        kind = FRAME_KIND[fid]
        adm = base_admission(inputs, fid)
        v2o = base_orders(inputs, fid)
        out[fid] = {}
        for side in F.SIDES:
            # the unrestricted variant must reproduce the V2 base exactly
            o0, _ = variant_orders(inputs, fid, side, {}, log=log)
            diff = [k for k, v in o0.items() if v != v2o[k]]
            if diff:
                raise RuntimeError(f"{fid} {side}: the unrestricted variant differs from V2 "
                                   f"on {len(diff)} rows; nothing scored")
            rows_out = []
            for vs in variant_specs(side, kind, inputs.get("absent_ok")):
                head, key = vs["head"], vs["key"]
                adm_folds = ([f for f, a in adm[side].items() if key in a.get(head, [])]
                             if key else None)
                row = {"id": vs["id"], "kind": vs["kind"], "head": head, "key": key,
                       "base_admitted_folds": adm_folds,
                       "dsq2_relaxed": bool(vs.get("dsq2_relaxed"))}
                if vs["kind"] == "leave_one_out" and not adm_folds:
                    row.update(identical_to_v2=True,
                               note="no fold admitted this driver; withholding it reproduces V2",
                               vs_v2={"side": {"delta": 0.0}, "all": {"delta": 0.0}},
                               vs_consensus={"side": base[fid][side], "all": base[fid]["all"]})
                    rows_out.append(row)
                    continue
                orders, rec = variant_orders(inputs, fid, side, vs["spec"], log=log)
                same = all(orders[k] == v2o[k] for k in orders)
                row["folds"] = rec
                if same:
                    row.update(identical_to_v2=True,
                               note="the variant's order equals V2's on every row",
                               vs_v2={"side": {"delta": 0.0}, "all": {"delta": 0.0}},
                               vs_consensus={"side": base[fid][side], "all": base[fid]["all"]})
                    rows_out.append(row)
                    continue
                rows_side = _rows_with(inputs, fid, orders, side)
                rows_all = _rows_with(inputs, fid, orders)
                row["identical_to_v2"] = False
                row["vs_v2"] = {"side": _within(rows_side, VAR_KEY, V2_KEY, B=B, seed=seed),
                                "all": _within(rows_all, VAR_KEY, V2_KEY, B=B, seed=seed)}
                row["vs_consensus"] = {"side": _within(rows_side, VAR_KEY, CONS, B=B, seed=seed),
                                       "all": _within(rows_all, VAR_KEY, CONS, B=B, seed=seed)}
                row["per_fold_vs_v2"] = MCS.fold_deltas(rows_side, VAR_KEY, V2_KEY)
                rows_out.append(row)
                log(f"  {fid} {side} {vs['id']}: vs V2 {row['vs_v2']['side'].get('delta')} "
                    f"CI {row['vs_v2']['side'].get('ci95')}; vs consensus "
                    f"{row['vs_consensus']['side'].get('delta')} ({round(time.time() - t0, 1)} s)")
            out[fid][side] = rows_out
    return out


# ---------------------------------------------------------------------------
# part 2: slopes on two labels
# ---------------------------------------------------------------------------

def pooled_partial_slope(rows: list[dict], key: str, *, target: str = "u_y",
                         has_block_only: bool = True, min_rows: int = H.ADMIT_MIN_ROWS) -> dict:
    """The pooled partial slope of the driver: OLS of y on [1, u_c, z(x)] over every
    training vintage's rows at once, u_c and u_y the within-vintage percentiles, z(x) the
    driver standardized within its vintage (no-block or unobserved rows at the has-block
    mean, as the heads see them). y is u_y (skill) or REACHED (timing). Only vintages
    where at least min_rows rows OBSERVE the driver enter, as in the admission rule."""
    H._check_years({int(r["decision_year"]) for r in rows})
    if not rows:
        return {"n": 0, "slope": None, "se": None, "t": None}
    u_c, u_y = H._percentiles(rows)
    means = H.has_block_means(rows)
    ys, ucs, zs = [], [], []
    vint = []
    for yr in sorted({int(r["decision_year"]) for r in rows}):
        ix = [i for i, r in enumerate(rows) if int(r["decision_year"]) == yr
              and (r["v2"]["has_block"] or not has_block_only)]
        if sum(1 for i in ix if rows[i]["v2"].get(key) is not None) < min_rows:
            continue
        x = np.array([H.v2_vector(rows[i]["v2"], (key,), means)[0] for i in ix])
        if float(x.std()) <= 0:
            continue
        zs += ((x - x.mean()) / x.std()).tolist()
        ucs += u_c[ix].tolist()
        ys += (u_y[ix] if target == "u_y"
               else np.array([rows[i]["reached"] for i in ix], dtype=np.float64)).tolist()
        vint.append(yr)
    n = len(ys)
    if n < min_rows:
        return {"n": n, "slope": None, "se": None, "t": None, "vintages": vint}
    X = np.column_stack([np.ones(n), np.asarray(ucs), np.asarray(zs)])
    y = np.asarray(ys)
    XtX = X.T @ X
    b = np.linalg.solve(XtX, X.T @ y)
    r = y - X @ b
    var = float(r @ r) / (n - 3) * float(np.linalg.inv(XtX)[2, 2])
    se = math.sqrt(var) if var > 0 else None
    return {"n": n, "slope": _rnd(b[2], 6), "se": _rnd(se, 6),
            "t": None if not se else _rnd(b[2] / se, 4), "vintages": vint,
            "units": ("target percentile points per SD of the driver" if target == "u_y"
                      else "REACHED probability per SD of the driver (linear)")}


def slope_rows(rows: list[dict], units: list[tuple[str, str]]) -> dict:
    """{head.key: {admission (DS-06 per-vintage t, sign, mean |t|), pooled slope}} on one
    label's training rows."""
    out = {}
    for head, key in units:
        tgt = "u_y" if head == "skill" else "reached"
        hb = head == "skill"
        chk = H.admission_for_key(rows, key, target=tgt, has_block_only=hb)
        out[f"{head}.{key}"] = {
            "head": head, "key": key, "target": tgt,
            "rows": "has_block" if hb else "all",
            "t_by_vintage": chk["t_by_vintage"], "per_vintage_signs": chk["per_vintage_signs"],
            "sign": chk["sign"], "mean_abs_t": chk["mean_abs_t"],
            "admitted_on_all_vintages": chk["admitted"], "reason": chk["reason"],
            "pooled": pooled_partial_slope(rows, key, target=tgt, has_block_only=hb)}
    return out


def _sign_word(a, b) -> str:
    if a is None or b is None:
        return "not comparable"
    if a == 0 or b == 0:
        return "zero on one label"
    return "same sign" if (a > 0) == (b > 0) else "SIGN FLIP"


def compare_labels(a: dict, b: dict, a_name: str, b_name: str) -> dict:
    """Per unit: the pooled slope and mean |t| on both labels, the change and the sign
    relation."""
    out = {}
    for u in a:
        pa, pb = (a[u].get("pooled") or {}), ((b.get(u) or {}).get("pooled") or {})
        sa, sb_ = pa.get("slope"), pb.get("slope")
        out[u] = {f"slope_{a_name}": sa, f"slope_{b_name}": sb_,
                  f"t_{a_name}": pa.get("t"), f"t_{b_name}": pb.get("t"),
                  f"mean_abs_t_{a_name}": a[u].get("mean_abs_t"),
                  f"mean_abs_t_{b_name}": (b.get(u) or {}).get("mean_abs_t"),
                  f"sign_{a_name}": a[u].get("sign"), f"sign_{b_name}": (b.get(u) or {}).get("sign"),
                  "change": (None if sa is None or sb_ is None else _rnd(sb_ - sa, 6)),
                  "pooled_sign_relation": _sign_word(sa, sb_)}
    return out


def slope_table(lv_rows: dict, vm_rows: dict, absent_ok: bool | None = None) -> dict:
    """Part 2. lv_rows / vm_rows: {label name: {side: training rows}}. lv compares the
    eWAR v2 and fWAR labels on the same frame rows; vm compares every matrix set given
    (the current served matrices, E0, F1, Estar when present)."""
    out = {"lv": {"labels": {}, "compare": {}}, "vm": {"labels": {}, "compare": {}}}
    for kind, by_label in (("lv", lv_rows), ("vm", vm_rows)):
        for name, by_side in by_label.items():
            if name.startswith("_"):
                out[kind][name] = by_side
                continue
            out[kind]["labels"][name] = {}
            for side, rows in by_side.items():
                units = candidate_units(side, kind, absent_ok)
                out[kind]["labels"][name][side] = {
                    "n_rows": len(rows),
                    "decision_years": sorted({int(r["decision_year"]) for r in rows}),
                    "slopes": slope_rows(rows, units)}
    lv_l = out["lv"]["labels"]
    if "ewar_v2" in lv_l and "fwar" in lv_l:
        out["lv"]["compare"]["ewar_v2_to_fwar"] = {
            s: compare_labels(lv_l["ewar_v2"][s]["slopes"], lv_l["fwar"][s]["slopes"],
                              "ewar", "fwar") for s in lv_l["fwar"]}
    vm_l = out["vm"]["labels"]
    for a, b, name in (("E0", "current", "E0_to_current"), ("F1", "Estar", "F1_to_Estar")):
        if a in vm_l and b in vm_l:
            out["vm"]["compare"][name] = {
                s: compare_labels(vm_l[a][s]["slopes"], vm_l[b][s]["slopes"], "ewar", "fwar")
                for s in vm_l[b]}
    return out


# ---------------------------------------------------------------------------
# part 3: which subgroup carries the gap
# ---------------------------------------------------------------------------

def group_split(rows: list[dict], a_key: str = V2_KEY, b_key: str = CONS) -> dict:
    """The exact additive split of the frame's within delta over its (side, vintage)
    groups: contribution_g = n_g x (rho_a,g - rho_b,g) / N over the kept groups. The
    contributions sum to the frame delta."""
    sel, a, b, y, codes = MCS._arrays(rows, a_key, b_key)
    keep = S.kept_groups(codes)
    total_n = int(np.isin(codes, keep).sum())
    out, tot = {}, 0.0
    for g in keep:
        idx = np.flatnonzero(codes == g)
        ra = S._rho(a[idx], y[idx])
        rb = S._rho(b[idx], y[idx])
        if ra is None or rb is None:
            continue
        c = idx.size * (ra - rb) / total_n
        tot += c
        out[str(g)] = {"n": int(idx.size), "rho_a": _rnd(ra), "rho_b": _rnd(rb),
                       "delta": _rnd(ra - rb), "contribution": _rnd(c)}
    return {"groups": out, "sum_of_contributions": _rnd(tot), "n_kept": total_n}


def _pct_in_groups(rows: list[dict], key: str) -> np.ndarray:
    return H.within_pct([c["grades"][key] for c in rows], [c["group"] for c in rows])


def moved_rows(rows: list[dict], min_move: float = MOVE_PCT) -> dict:
    """Rows V2 moved up, moved down or left in place against consensus (within-group
    percentile change of at least min_move), with each set's mean outcome percentile
    minus its consensus percentile. A driver that helps moves up rows whose outcome
    beats their consensus place and down rows whose outcome trails it."""
    if not rows:
        return {}
    u_v = _pct_in_groups(rows, V2_KEY)
    u_c = _pct_in_groups(rows, CONS)
    u_y = H.within_pct([c["outcome"]["war"] for c in rows], [c["group"] for c in rows])
    mv = u_v - u_c
    out = {"min_move": min_move}
    for name, m in (("up", mv >= min_move), ("down", mv <= -min_move),
                    ("in_place", np.abs(mv) < min_move)):
        n = int(m.sum())
        out[name] = {"n": n,
                     "mean_move": _rnd(mv[m].mean()) if n else None,
                     "mean_outcome_minus_consensus_pct": _rnd((u_y - u_c)[m].mean()) if n else None,
                     "mean_outcome_minus_v2_pct": _rnd((u_y - u_v)[m].mean()) if n else None}
    out["n"] = len(rows)
    return out


def strata_table(inputs: dict, cells: dict, *, B: int = B_DEFAULT, seed: int = SEED,
                 log=print) -> dict:
    """Part 3. cells: {fid: {(side, year, key): {dimension: cell}}}. Per frame: the
    group split, the moved rows (all and per side), and per dimension and cell the
    within delta V2 minus consensus (E_cond, B, seed; the cell's own (side, vintage)
    groups of at least 20 rows; else the pooled delta after the frame's identical map,
    computed once on the whole frame), at the scoreboard matrix's cell floors."""
    out = {}
    for fid in FRAMES:
        rows = MCS.scored_rows(inputs, fid)
        cmap = cells.get(fid) or {}
        mapped = {}
        for key in (V2_KEY, CONS):
            mp = S.map_scores([c["grades"][key] for c in rows], [c["group"] for c in rows],
                              [c["grades"][CONS] for c in rows])
            mapped[key] = {(c["side"], int(c["year"]), c["key"]): float(v) for c, v in zip(rows, mp)}
        doc = {"group_split": group_split(rows),
               "moved": {"all": moved_rows(rows),
                         **{s: moved_rows([c for c in rows if c["side"] == s]) for s in F.SIDES}},
               "dimensions": {}}
        for dim in STRATA_DIMS:
            by_cell: dict = {}
            for c in rows:
                cell = (cmap.get((c["side"], int(c["year"]), c["key"])) or {}).get(dim)
                if cell is None:
                    continue
                by_cell.setdefault(str(cell), []).append(c)
            dd = {}
            for cell in sorted(by_cell):
                sel = by_cell[cell]
                codes = np.asarray([str(c["group"]) for c in sel])
                keep = S.kept_groups(codes)
                rec = {"n": len(sel), "n_players": len({c["key"] for c in sel}),
                       "n_by_side": MCS._n_side(sel),
                       "groups_20plus": [str(g) for g in keep]}
                if len(sel) < CELL_FLOOR_ROWS:
                    rec.update(statistic=None, status=f"below the {CELL_FLOOR_ROWS}-row cell floor")
                    dd[cell] = rec
                    continue
                if keep.size:
                    d = S.paired_delta([c["key"] for c in sel], [c["group"] for c in sel],
                                       [c["outcome"]["war"] for c in sel],
                                       [bool(c["outcome"]["contributor"]) for c in sel],
                                       [c["grades"][V2_KEY] for c in sel],
                                       [c["grades"][CONS] for c in sel],
                                       [c["grades"][CONS] for c in sel], statistic="within",
                                       B=B, seed=seed, floor_rows=CELL_FLOOR_ROWS,
                                       floor_clusters=CELL_FLOOR_CLUSTERS)
                    rec["statistic"] = "within"
                else:
                    ks = [(c["side"], int(c["year"]), c["key"]) for c in sel]
                    d = S.paired_delta([c["key"] for c in sel], [c["group"] for c in sel],
                                       [c["outcome"]["war"] for c in sel],
                                       [bool(c["outcome"]["contributor"]) for c in sel],
                                       [mapped[V2_KEY][k] for k in ks],
                                       [mapped[CONS][k] for k in ks],
                                       [c["grades"][CONS] for c in sel], statistic="pooled",
                                       B=B, seed=seed, premapped=True,
                                       floor_rows=CELL_FLOOR_ROWS,
                                       floor_clusters=CELL_FLOOR_CLUSTERS)
                    rec["statistic"] = "pooled after the frame's identical map"
                rec.update({k: d.get(k) for k in ("a", "b", "delta", "ci95", "mde95",
                                                   "p_gt_0", "status")})
                rec["moved"] = moved_rows(sel)
                dd[cell] = rec
            doc["dimensions"][dim] = dd
            log(f"  strata {fid} {dim}: {len(dd)} cells")
        out[fid] = doc
    return out


def lv_cells(inputs: dict, frames: dict) -> dict:
    """{(side, V, key): cells} for lv_dev from the efv_vintage_frame rows."""
    by = {}
    for side in F.SIDES:
        for V, (rows, _labs) in frames[side].items():
            if int(V) not in inputs["frames"]["lv_dev"]["folds"]:
                continue
            for r in rows:
                by[(side, int(V), r["player_key"])] = r
    out = {}
    for c in MCS.scored_rows(inputs, "lv_dev"):
        fr = by.get((c["side"], int(c["year"]), c["key"]))
        if fr is None:
            continue
        cells = ST.assign("lv_dev", {**fr, "side": c["side"], "vintage": int(c["year"])}, None)
        out[(c["side"], int(c["year"]), c["key"])] = cells
    return out


def vm_cells(inputs: dict, records: dict, milb_of: dict) -> dict:
    """{(side, year, key): cells} for vm_dev: the matrix row's outcome-blind MiLB block
    and the universe record's position and birth date, as tools/efv_matrix.rows_from_vm
    builds them."""
    out = {}
    for c in MCS.scored_rows(inputs, "vm_dev"):
        rec = records.get(c["key"]) or {}
        srow = {"year": int(c["year"]), "grades": c.get("grades") or {}, "side": c["side"],
                "milb": milb_of.get(c["key"]), "position": rec.get("position"),
                "birth_date": rec.get("birth_date")}
        out[(c["side"], int(c["year"]), c["key"])] = ST.assign("vm2", srow, rec)
    return out


# ---------------------------------------------------------------------------
# the weights: the same fold heads at the pre-refit weights and at scaled weights
# ---------------------------------------------------------------------------

WEIGHT_SCALES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5)


def weight_table(inputs: dict, w_before: dict, *, B: int = B_DEFAULT, seed: int = SEED) -> dict:
    """A diagnosis of the combiner weights, selected nowhere (the registered DS-08 weights
    stand): V2's fold heads are fitted without the weights, so V2 at other weights is a
    re-weighting of the stored fold predictions (u_c, e_skill, e_time) with no refit.
    (a) the pre-refit weights (the eWAR v2 DS-08 weights, before c40c0dd0) against V2 at
    the P5 weights and against consensus, with intervals; (b) the P5 weights scaled by k
    (k 0 is the consensus order), within delta against consensus, point values only."""
    out = {"what": ("V2's fold heads re-weighted without a refit; a diagnosis, selected "
                    "nowhere; the registered weights stand"),
           "weights_p5": inputs["weights"], "weights_pre_refit": w_before,
           "pre_refit": {}, "scale": {"k": list(WEIGHT_SCALES), "frames": {}}}
    for fid in FRAMES:
        o = MCS.rescore_v2(inputs, fid, w_before)
        rows_all = _rows_with(inputs, fid, o)
        blk = {}
        for part, rows in (("all", rows_all),) + tuple(
                (s, [c for c in rows_all if c["side"] == s]) for s in F.SIDES):
            blk[part] = {"vs_v2": _within(rows, VAR_KEY, V2_KEY, B=B, seed=seed),
                         "vs_consensus": _within(rows, VAR_KEY, CONS, B=B, seed=seed)}
        out["pre_refit"][fid] = blk
        curve = {}
        for k in WEIGHT_SCALES:
            wk = {s: {"w_skill": k * float(inputs["weights"][s]["w_skill"]),
                      "w_time": k * float(inputs["weights"][s]["w_time"])} for s in F.SIDES}
            rk = _rows_with(inputs, fid, MCS.rescore_v2(inputs, fid, wk))
            curve[str(k)] = {part: _within(rows, VAR_KEY, CONS, B=0, seed=seed).get("delta")
                             for part, rows in (("all", rk),) + tuple(
                                 (s, [c for c in rk if c["side"] == s]) for s in F.SIDES)}
        out["scale"]["frames"][fid] = curve
    return out


# ---------------------------------------------------------------------------
# part 4: the served board at the 10-04 refit
# ---------------------------------------------------------------------------

def _rank_in_group(vals: np.ndarray) -> np.ndarray:
    """1 = highest; ties share their mean rank."""
    order = np.argsort(-vals, kind="mergesort")
    ranks = np.empty(vals.size)
    ranks[order] = np.arange(1, vals.size + 1, dtype=np.float64)
    for u in np.unique(vals):
        m = vals == u
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    return ranks


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 3:
        return None
    return SB._corr_np(np, SB._ranks_np(np, a), SB._ranks_np(np, b))


def order_vs_consensus(groups: dict, before_key: str, after_key: str) -> dict:
    """groups: {group: [{key, cons, before, after}]}. Per group and in total: the
    Spearman of each order with consensus, the mean absolute rank gap to consensus, rows
    whose rank changed, rows whose gap to the consensus rank shrank, grew or held, and
    rows whose grade (the group's consensus value at the order's rank, DS-07) changed or
    equals the consensus grade."""
    out = {"groups": {}, "total": {}}
    tot = {"n": 0, "rank_changed": 0, "closer": 0, "farther": 0, "same_gap": 0,
           "grade_changed": 0, "grade_eq_consensus_before": 0, "grade_eq_consensus_after": 0,
           "gap_sum_before": 0.0, "gap_sum_after": 0.0, "max_rank_move": 0.0}
    rho_w = {"before": 0.0, "after": 0.0}
    for g, rows in sorted(groups.items()):
        cons = np.array([r["cons"] for r in rows], dtype=np.float64)
        bef = np.array([r[before_key] for r in rows], dtype=np.float64)
        aft = np.array([r[after_key] for r in rows], dtype=np.float64)
        rc, rb, ra = _rank_in_group(cons), _rank_in_group(bef), _rank_in_group(aft)
        gb, ga = np.abs(rb - rc), np.abs(ra - rc)
        grade_b = H.output_map(bef, [g] * len(rows), cons)
        grade_a = H.output_map(aft, [g] * len(rows), cons)
        rho_b, rho_a = _spearman(bef, cons), _spearman(aft, cons)
        n = len(rows)
        rec = {"n": n, "spearman_with_consensus_before": _rnd(rho_b),
               "spearman_with_consensus_after": _rnd(rho_a),
               "mean_abs_rank_gap_before": _rnd(gb.mean(), 3),
               "mean_abs_rank_gap_after": _rnd(ga.mean(), 3),
               "rank_changed": int((rb != ra).sum()),
               "closer_to_consensus_rank": int((ga < gb).sum()),
               "farther_from_consensus_rank": int((ga > gb).sum()),
               "same_gap": int((ga == gb).sum()),
               "max_rank_move": _rnd(np.abs(ra - rb).max(), 1),
               "grade_changed": int((np.abs(grade_a - grade_b) > 1e-9).sum()),
               "grade_eq_consensus_before": int((np.abs(grade_b - cons) < 1e-9).sum()),
               "grade_eq_consensus_after": int((np.abs(grade_a - cons) < 1e-9).sum())}
        out["groups"][str(g)] = rec
        tot["n"] += n
        tot["rank_changed"] += rec["rank_changed"]
        tot["closer"] += rec["closer_to_consensus_rank"]
        tot["farther"] += rec["farther_from_consensus_rank"]
        tot["same_gap"] += rec["same_gap"]
        tot["grade_changed"] += rec["grade_changed"]
        tot["grade_eq_consensus_before"] += rec["grade_eq_consensus_before"]
        tot["grade_eq_consensus_after"] += rec["grade_eq_consensus_after"]
        tot["gap_sum_before"] += float(gb.sum())
        tot["gap_sum_after"] += float(ga.sum())
        tot["max_rank_move"] = max(tot["max_rank_move"], float(np.abs(ra - rb).max()))
        if rho_b is not None and rho_a is not None:
            rho_w["before"] += rho_b * n
            rho_w["after"] += rho_a * n
    n = tot["n"]
    if n:
        tb, ta = rho_w["before"] / n, rho_w["after"] / n
        out["total"] = {
            "n": n, "rank_changed": tot["rank_changed"],
            "closer_to_consensus_rank": tot["closer"],
            "farther_from_consensus_rank": tot["farther"], "same_gap": tot["same_gap"],
            "grade_changed": tot["grade_changed"],
            "grade_eq_consensus_before": tot["grade_eq_consensus_before"],
            "grade_eq_consensus_after": tot["grade_eq_consensus_after"],
            "mean_abs_rank_gap_before": _rnd(tot["gap_sum_before"] / n, 3),
            "mean_abs_rank_gap_after": _rnd(tot["gap_sum_after"] / n, 3),
            "max_rank_move": _rnd(tot["max_rank_move"], 1),
            "spearman_with_consensus_before": _rnd(tb),
            "spearman_with_consensus_after": _rnd(ta),
            "direction": ("toward consensus" if ta > tb else
                          "away from consensus" if ta < tb else "unchanged")}
    return out


def served_rows(doc: dict) -> dict:
    """{group: [{key, cons, order, u_c, e_skill, e_time}]} of the V2-graded rows of a
    served data/xfv.json."""
    out: dict = {}
    for k, v in ((doc or {}).get("by_player") or {}).items():
        if v.get("grade_basis") != "efv_v2" or not isinstance(v.get("efv_v2"), dict):
            continue
        e = v["efv_v2"]
        g = e.get("group")
        if not g or v.get("consensus_fv") is None:
            continue
        out.setdefault(f"{g[0]}|{g[1]}", []).append(
            {"key": k, "cons": float(v["consensus_fv"]), "order": float(e["order_idx"]),
             "u_c": float(e["u_c"]), "e_skill": float(e["e_skill"]), "e_time": float(e["e_time"])})
    return out


def board_move(current: dict, w_before: dict, w_after: dict, *,
               before_doc: dict | None = None, after_doc: dict | None = None) -> dict:
    """Part 4. (a) counterfactual: the current served rows re-ordered at the pre-refit
    weights (u_c + w_skill e_skill + w_time e_time; the production heads are fitted
    without the weights, so the heads are the same and only the weights move), against
    the served order. The served order_idx must equal the after-weights sum on every row.
    (b) realized: the served artifact before and after the post-epoch rebuild, on the
    rows V2 graded in both."""
    groups = served_rows(current)
    bad = 0
    for g, rows in groups.items():
        side = g.split("|")[0]
        for r in rows:
            wa, wb = w_after[side], w_before[side]
            recon = r["u_c"] + wa["w_skill"] * r["e_skill"] + wa["w_time"] * r["e_time"]
            if abs(recon - r["order"]) > 1e-5:
                bad += 1
            r["before"] = r["u_c"] + wb["w_skill"] * r["e_skill"] + wb["w_time"] * r["e_time"]
            r["after"] = r["order"]
    push = {}
    for side in sorted({g.split("|")[0] for g in groups}):
        rows = [r for g, rr in groups.items() if g.split("|")[0] == side for r in rr]
        rec = {}
        for tag, w in (("before", w_before[side]), ("after", w_after[side])):
            ps = np.array([w["w_skill"] * r["e_skill"] for r in rows])
            pt = np.array([w["w_time"] * r["e_time"] for r in rows])
            rec[tag] = {"mean_abs_skill_push": _rnd(np.abs(ps).mean()) if rows else None,
                        "mean_abs_timing_push": _rnd(np.abs(pt).mean()) if rows else None}
        push[side] = rec
    out = {"counterfactual": {
        "what": ("current served rows at the pre-refit weights (before) against the served "
                 "order (after); same heads, same inputs, only the 10-04 weights move"),
        "push_by_head": push,
        "weights_before": w_before, "weights_after": w_after,
        "rows_not_reconstructed": bad,
        "by_side": {s: order_vs_consensus({g: r for g, r in groups.items()
                                           if g.split("|")[0] == s}, "before", "after")
                    for s in sorted({g.split("|")[0] for g in groups})}}}
    if before_doc is not None and after_doc is not None:
        gb, ga = served_rows(before_doc), served_rows(after_doc)
        joined: dict = {}
        n_b = sum(len(v) for v in gb.values())
        n_a = sum(len(v) for v in ga.values())
        for g in sorted(set(gb) & set(ga)):
            bmap = {r["key"]: r for r in gb[g]}
            for r in ga[g]:
                b = bmap.get(r["key"])
                if b is None or b["cons"] != r["cons"]:
                    continue
                joined.setdefault(g, []).append({"key": r["key"], "cons": r["cons"],
                                                 "before": b["order"], "after": r["order"]})
        out["realized"] = {
            "what": ("the served artifact before and after the post-epoch rebuild, on rows "
                     "V2 graded in both with the same consensus FV; the rebuild also merged "
                     "the other lanes' code, so this is the realized change, not the refit "
                     "alone"),
            "n_rows_before": n_b, "n_rows_after": n_a,
            "n_joined": sum(len(v) for v in joined.values()),
            "by_side": {s: order_vs_consensus({g: r for g, r in joined.items()
                                               if g.split("|")[0] == s}, "before", "after")
                        for s in sorted({g.split("|")[0] for g in joined})}}
    return out


# ---------------------------------------------------------------------------
# the findings, derived from the parts (never typed)
# ---------------------------------------------------------------------------

def ranked_units(drivers: dict, fid: str, side: str) -> list[dict]:
    """The leave-one-out rows of one frame and side, ordered by how much withholding the
    driver gains over V2 (largest gain first)."""
    rows = [r for r in (drivers.get(fid) or {}).get(side, [])
            if r["kind"] == "leave_one_out" and not r.get("identical_to_v2")]
    return sorted(rows, key=lambda r: -(r["vs_v2"]["side"].get("delta") or 0.0))


def findings(doc: dict) -> dict:
    out = {"subtracting_drivers": {}, "base": {}, "largest_cell_gaps": {}}
    for fid in FRAMES:
        out["base"][fid] = {s: (doc["base"][fid][s] or {}).get("delta")
                            for s in ("all",) + F.SIDES}
        for side in F.SIDES:
            out["subtracting_drivers"][f"{fid}|{side}"] = [
                {"driver": r["id"][4:], "loo_gain_vs_v2": r["vs_v2"]["side"].get("delta"),
                 "ci95": r["vs_v2"]["side"].get("ci95"),
                 "admitted_folds": r.get("base_admitted_folds")}
                for r in ranked_units(doc["drivers"], fid, side)]
        cells = []
        for dim, dd in ((doc.get("strata") or {}).get(fid, {}).get("dimensions") or {}).items():
            if dim == "side":
                continue
            for cell, rec in dd.items():
                if rec.get("delta") is not None:
                    cells.append({"dimension": dim, "cell": cell, "n": rec["n"],
                                  "delta": rec["delta"], "ci95": rec.get("ci95"),
                                  "statistic": rec.get("statistic")})
        out["largest_cell_gaps"][fid] = sorted(cells, key=lambda c: c["delta"])[:6]
    return out


# ---------------------------------------------------------------------------
# the real inputs
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def matrix_override(paths: dict | None):
    """efv_v2_model reads the epoch arm's matrices for the duration (part 2 only)."""
    if not paths:
        yield
        return
    orig = H._matrix_path
    H._matrix_path = lambda side: Path(paths[side])
    try:
        yield
    finally:
        H._matrix_path = orig


def vm_training_rows(paths: dict | None = None) -> dict:
    """{side: matrix training rows below the R-VM cohort} on the given matrices (the
    served ones when paths is None)."""
    out = {}
    with matrix_override(paths):
        for side in F.SIDES:
            rows = [r for r in H.matrix_training_rows(side)
                    if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
            H._check_years({int(r["decision_year"]) for r in rows})
            out[side] = rows
    return out


def ewar_table() -> dict:
    """{player_key: {season: WAR}} on the eWAR v2 series, shaped as
    efv_labels.war_seasons_table shapes the default provider's. The career table is
    stored once (war_source.career_war_table returns it as stored for every provider):
    an fwar row carries the eWAR v2 series beside its served `seasons` under
    `seasons_ewar_v2` (the epoch's step C); a row the epoch did not rebase (source
    ewar_v2 or bbref) serves its stored `seasons`, which is what the eWAR provider
    served for it before the epoch."""
    import war_source
    out: dict = {}
    for pk, agg in war_source.career_war_table(provider=EWAR_PROVIDER).items():
        agg = agg or {}
        seasons = ((agg.get("seasons_ewar_v2") if agg.get("source") == "fwar"
                    else agg.get("seasons")) or {})
        try:
            out[pk] = {int(y): float(w) for y, w in seasons.items() if w is not None}
        except (TypeError, ValueError):
            continue
    return out


def label_receipt(rows_a: dict, rows_b: dict) -> dict:
    """Per side: rows on both labels, rows whose target differs, rows whose REACHED
    differs, and the Spearman of the two targets."""
    out = {}
    for side in rows_b:
        a = {(r["player_key"], int(r["decision_year"])): r for r in rows_a.get(side, [])}
        pairs = [(a[k], r) for r in rows_b[side]
                 for k in [(r["player_key"], int(r["decision_year"]))] if k in a]
        ta = np.array([p[0]["target"] for p in pairs], dtype=np.float64)
        tb = np.array([p[1]["target"] for p in pairs], dtype=np.float64)
        out[side] = {"n_a": len(rows_a.get(side, [])), "n_b": len(rows_b[side]),
                     "n_both": len(pairs),
                     "target_differs": int((np.abs(ta - tb) > 1e-9).sum()),
                     "reached_differs": int(sum(1 for x, y in pairs if x["reached"] != y["reached"])),
                     "spearman_targets": _rnd(_spearman(ta, tb))}
    return out


def build_real(epoch_dir: Path | None, *, log=print) -> dict:
    """The screen's inputs (frames, folds, V2 base, guards) plus what parts 2 to 4 read."""
    import efv_labels as L
    import efv_v2_assemble as ASM
    captured: dict = {}
    orig = ASM.build_frames

    def capture():
        captured["frames"] = orig()
        return captured["frames"]
    ASM.build_frames = capture
    try:
        inputs = MCS.build_inputs(log=log)
    finally:
        ASM.build_frames = orig
    frames = captured["frames"]
    for side in F.SIDES:
        bad = sorted(set(frames[side]) & set(F.RESERVED_LV))
        if bad or max(frames[side]) >= min(F.RESERVED_LV):
            raise F.ReservedFrameError(f"lv frames reach a reserved vintage: {sorted(frames[side])}")
    t0 = time.time()
    universe = F.load_universe()
    war_e = ewar_table()
    lv_rows = {"fwar": {}, "ewar_v2": {}}
    for side in F.SIDES:
        lv_rows["fwar"][side] = H.lv_training_rows(side, frames[side])
        relabelled = {V: (rows, L.labels_for_frame(rows, universe=universe, war=war_e))
                      for V, (rows, _labs) in frames[side].items()}
        lv_rows["ewar_v2"][side] = H.lv_training_rows(side, relabelled)
    lv_rows["_receipt"] = label_receipt(lv_rows["ewar_v2"], lv_rows["fwar"])
    log(f"lv rows on both labels ({round(time.time() - t0, 1)} s): "
        + json.dumps(lv_rows["_receipt"]))
    vm_rows = {"current": vm_training_rows(None)}
    epoch = {"dir": None if epoch_dir is None else str(epoch_dir), "arms": {}}
    for arm in EPOCH_ARMS:
        if epoch_dir is None:
            break
        paths = {"hit": Path(epoch_dir) / f"xfv_hitter_matrix__{arm}.json",
                 "pit": Path(epoch_dir) / f"xfv_pitcher_matrix__{arm}.json"}
        if not all(p.exists() for p in paths.values()):
            epoch["arms"][arm] = {"status": "missing"}
            continue
        vm_rows[arm] = vm_training_rows(paths)
        epoch["arms"][arm] = {"sha256": {s: _sha(p) for s, p in paths.items()}}
    for side in F.SIDES:
        epoch.setdefault("current_sha256", {})[side] = _sha(H._matrix_path(side))
    manifests = {}
    if epoch_dir is not None:
        for side in F.SIDES:
            p = Path(epoch_dir) / f"manifest_{side}.json"
            if p.exists():
                m = json.loads(p.read_text(encoding="utf-8"))
                manifests[side] = {a: (m.get("arms") or {}).get(a, {}).get("factor_values")
                                   for a in EPOCH_ARMS}
    epoch["factor_values"] = manifests
    # strata inputs
    import efv_matrix as EM
    _side_of, milb_of = EM._matrix_blocks()
    records = EM._records_by_key(SB._load_universe(H.DATA_DIR))
    cells = {"lv_dev": lv_cells(inputs, frames), "vm_dev": vm_cells(inputs, records, milb_of)}
    # the served board on either side of the refit
    current = json.loads((H.DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    asm_before = _git_json(f"{REFIT_COMMIT}^", ASSEMBLY_REL)
    asm_after = _git_json(REFIT_COMMIT, ASSEMBLY_REL)
    board = {"current": current,
             "w_before": {s: asm_before["weights"][s] for s in F.SIDES},
             "w_after": {s: asm_after["weights"][s] for s in F.SIDES},
             "before_doc": _git_json(SERVED_BEFORE, XFV_REL),
             "after_doc": _git_json(SERVED_AFTER, XFV_REL),
             "assembly_admitted": {"before": asm_before.get("admitted"),
                                   "after": asm_after.get("admitted")}}
    return {"inputs": inputs, "lv_rows": lv_rows, "vm_rows": vm_rows, "epoch": epoch,
            "cells": cells, "board": board}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def run(real: dict, *, B: int = B_DEFAULT, exploratory: bool, log=print) -> dict:
    t0 = time.time()
    inputs = real["inputs"]
    ds16 = MCS._ds16_block() if not exploratory else None
    parity = MCS.base_parity(inputs, ds16)
    if not exploratory and not parity["reproduces"]:
        raise RuntimeError("the V2 base does not reproduce the DS-16 block; nothing scored")
    doc: dict = {
        "schema": 1, "item": ITEM,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": TOOL, "role": "development", "kind": "diagnosis",
        "adjudicates": False, "selects": False, "admits": False, "ledger_row": False,
        "exploratory": bool(exploratory), "note": NOTE,
        "label": MCS._label() if not exploratory else {"provider": "synthetic"},
        "code": {"commit": (_git("rev-parse", "--short=8", "HEAD") or "").strip() or None,
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "assembly_sha256": _sha(H.ASSEMBLY_PATH) if not exploratory else None,
        "weights": inputs["weights"],
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "min_group_rows": S.MIN_GROUP_ROWS,
                      "group": "(side, list vintage) on lv_dev; (side, debut year) on vm_dev",
                      "code": "efv_v2_stat.py"},
        "bootstrap": {"B": int(B), "seed": SEED, "estimator": "E_cond", "unit": "player cluster"},
        "reserved_guard": inputs["guards"],
        "base_parity": parity,
        "base_admission": {fid: base_admission(inputs, fid) for fid in FRAMES},
        "definitions": {
            "driver": "a (head, key) pair; level_rank sits in both hitter heads",
            "leave_one_out": "V2 refit per fold with the driver withheld from its head; "
                             "every other candidate and the registered weights unchanged",
            "leave_one_in": "V2 refit per fold with the driver the ONLY candidate (the "
                            "admission rule still applies); a pitcher timing driver relaxes "
                            "DS-Q2, which would otherwise make it the consensus order",
            "head_rows": "skill head alone, timing head alone (pitcher DS-Q2 relaxed on the "
                         "timing row)",
            "identical_to_v2": "withholding a driver no fold admitted reproduces V2 exactly "
                               "(admission is per key; the penalty is chosen on admitted "
                               "keys); no bootstrap is drawn for such a row",
            "slope": "the DS-06 statistic per training vintage (t of z(x) in y ~ 1 + u_c + "
                     "z(x)) and one pooled partial slope over every vintage that observes "
                     "the driver",
            "strata": "efv_strata cells; never a consensus-FV cell",
        },
    }
    log("base deltas")
    doc["base"] = base_deltas(inputs, B=B, seed=SEED)
    log("part 1: drivers")
    doc["drivers"] = driver_table(inputs, doc["base"], B=B, seed=SEED, log=log)
    log("part 2: slopes")
    doc["slopes"] = slope_table(real["lv_rows"], real["vm_rows"], inputs.get("absent_ok"))
    doc["slopes"]["epoch_matrices"] = real.get("epoch")
    log("part 3: strata")
    doc["strata"] = strata_table(inputs, real["cells"], B=B, seed=SEED, log=log)
    log("weights")
    doc["weights_diag"] = weight_table(inputs, real["board"]["w_before"], B=B, seed=SEED)
    log("part 4: board")
    bd = real["board"]
    doc["board"] = board_move(bd["current"], bd["w_before"], bd["w_after"],
                              before_doc=bd.get("before_doc"), after_doc=bd.get("after_doc"))
    doc["board"]["refit_commit"] = REFIT_COMMIT
    doc["board"]["served_before"] = SERVED_BEFORE
    doc["board"]["served_after"] = SERVED_AFTER
    doc["board"]["assembly_admitted"] = bd.get("assembly_admitted")
    doc["board"]["served_receipt"] = (((bd["current"].get("meta") or {}).get("served_model")
                                       or {}).get("receipt"))
    doc["findings"] = findings(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def write_doc(doc: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_clean(doc), indent=1, ensure_ascii=False) + "\n"
    for ch in (chr(0x2014), chr(0x2013)):
        if ch in text:
            raise RuntimeError("an em-dash or en-dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)


def summary_lines(doc: dict) -> list[str]:
    out = []
    for fid in FRAMES:
        b = doc["base"][fid]
        out.append(f"{fid}: V2 minus consensus all {b['all'].get('delta')} CI {b['all'].get('ci95')}; "
                   f"hit {b['hit'].get('delta')} CI {b['hit'].get('ci95')}; "
                   f"pit {b['pit'].get('delta')} CI {b['pit'].get('ci95')}")
        for side in F.SIDES:
            for r in doc["drivers"][fid][side]:
                if r.get("identical_to_v2"):
                    continue
                out.append(f"  {fid} {side} {r['id']:28s} vs V2 {r['vs_v2']['side'].get('delta')} "
                           f"CI {r['vs_v2']['side'].get('ci95')}  vs cons "
                           f"{r['vs_consensus']['side'].get('delta')} CI "
                           f"{r['vs_consensus']['side'].get('ci95')}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--check", action="store_true",
                    help="build the frames, print counts and the base parity; nothing scored")
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    ap.add_argument("--epoch-arms-dir", default=str(H.DATA_DIR / "_labs" / "fwar_epoch_arms"),
                    help="directory holding the fWAR epoch lab's arm matrices (E0, F1, Estar)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    under = _is_under_data(out)
    if under and a.B != B_DEFAULT:
        print("refused: a reduced bootstrap may not write under data/", flush=True)
        return 2

    def log(msg):
        print(msg, flush=True)
    import efv_labels as L
    if under and L.provider() != MCS.FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {MCS.FROZEN_PROVIDER!r}")
        return 2
    epoch_dir = Path(a.epoch_arms_dir) if a.epoch_arms_dir else None
    real = build_real(epoch_dir, log=log)
    if a.check:
        log(json.dumps({"check": True, "guards": real["inputs"]["guards"],
                        "counts": MCS.counts(real["inputs"]),
                        "base_parity": MCS.base_parity(real["inputs"], MCS._ds16_block()),
                        "epoch": real["epoch"],
                        "vm_rows": {k: {s: len(v[s]) for s in v} for k, v in real["vm_rows"].items()},
                        "cells": {f: len(c) for f, c in real["cells"].items()}},
                       indent=1, default=str))
        return 0
    doc = run(real, B=a.B, exploratory=not under, log=log)
    write_doc(doc, out)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    for line in summary_lines(doc):
        log(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

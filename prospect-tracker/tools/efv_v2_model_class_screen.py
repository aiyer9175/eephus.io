# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_C03: the ONE model-class screen of docs/efv-v2/MODEL_CLASS_SCREEN.md.

Five pre-declared arms (efv_v2_candidates: MC-1 pairwise head, MC-2 reliability anchor,
MC-3 two-band weight, MC-4a sign-constrained ridge, MC-4b monotone I-spline) against the
assembled Driver System V2 base at the DS-08 weights re-derived on the frozen fWAR label
(EFV_V2_GATE.md P5), on the two DEVELOPMENT frames and nothing else:

    lv_dev   F-LV at list vintages 2017 to 2019 (W3 label), the DS-16 row selection
             (tools/efv_v2_dev_read.v2_lv_dev); fold V fit on labelled F-LV rows at
             vintages before V with every V-frame player left out (efv_v2_model
             .v2_lv_scores' rule, repeated here so the arm refits on the same rows).
    vm_dev   the vintage-matched frame at frame version vm2 (career WAR to date), the DS-16
             row selection (v2_vm_dev); fold y fit on matrix rows at decision years before
             y, timing-pinned inputs (v2_vm_scores' rule, repeated here).

The V2 base is refit per fold by this tool on the same rows and must REPRODUCE the DS-16
block of data/efv_v2_dev_eval.json (n, groups and the within statistic of V2 and
consensus) before any arm is scored (base_parity); a mismatch ends the run with nothing
scored. Every arm is then scored on identical rows: arm minus V2 (the admission leg),
arm minus PROSPX consensus (the ledger row), arm minus MLB Pipeline and arm minus
FanGraphs (descriptive), each by the within (side, vintage) Spearman (primary), the pooled
Spearman after the identical output map (secondary) and the contributor AUC (veto),
efv_v2_stat.paired_delta, E_cond, B 2000, seed 20260906.

CONTROLS per arm and frame (MODEL_CLASS_SCREEN.md s5): the zero-information twin (the
arm's non-consensus columns permuted within vintage: the driver columns for MC-1, MC-4a
and MC-4b, the band labels for MC-3, the source reliability weights exchanged across
sources within (side, V) for MC-2; one draw, seed 20260906, refit and scored as the arm);
the per-fold within deltas with their signs; a 500-draw permutation null of the within
delta (the outcome permuted inside each (side, vintage) group); mde95 from the screen's
own draws. Holm m 5 on the vs-V2 within leg, each arm's p the larger of its two frames'
bootstrap shares of draws at or below zero.

ADMISSION (s6, applied by admission_verdict and printed, never by hand): within delta
over V2 at least +0.005 on both frames; the same sign in at least 2 of 3 lv folds and 5
of 7 vm years; lower CI95 vs V2 above -0.005 on both frames; the twin below the arm on
both frames; the AUC veto not fired; Holm survived. MC-4a is marked ADOPTABLE on
non-inferiority alone (lane C E3-Q3 = A), with no margin claim. An admitted arm reaches
the gate only through EFV3_C04; nothing here moves a served number.

OUTSIDE THE FAMILY: MC-1's listwise pair weighting (a sensitivity), the rank-consistent
combiner weight (s6, a sensitivity beside V2 at the DS-08 weights) and MC-5 (the pricing
line, an MAE row through tools/efv_v2_pricing_calibration's own functions on the same
folds, order_idx asserted bit-identical). None takes a Holm slot or an admission leg.

ONE RUN. An artifact already under data/ makes a second run refuse ("spent"); a crash
after scoring began is recorded as spent for the arms that scored (PROGRAM.md s4 kill
rule 2 by analogy). An exploratory run (--out outside data/, or synthetic inputs in the
tests) writes nothing else. NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025
and later debut cohorts (R-VM); the guards run before any fit (screen_guards,
efv_v2_candidates.guard_training_rows per fold) and a violation raises.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only strata are side and vintage.
Nothing here groups, counts or averages rows by consensus-FV level.

Run once:  python -u tools/efv_v2_model_class_screen.py --check   (frames, counts, base
                                                                  parity; no arm scored)
           python -u tools/efv_v2_model_class_screen.py
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import consensus as CS  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_v2_candidates as C  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

OUT_PATH = H.DATA_DIR / "efv_v2_model_class_screen.json"
TOOL = "tools/efv_v2_model_class_screen.py"
ITEM = "EFV3_C03"
DECLARED_DOC = "docs/efv-v2/MODEL_CLASS_SCREEN.md"
NOTE = "model-class screen, spent frame, not a claim"
FROZEN_PROVIDER = "fwar"
ARMS: tuple[str, ...] = C.FAMILY
ARM_LABEL = {"mc1": "MC-1", "mc2": "MC-2", "mc3": "MC-3", "mc4a": "MC-4a", "mc4b": "MC-4b"}
FRAMES: tuple[str, ...] = ("lv_dev", "vm_dev")
FRAME_KIND = {"lv_dev": "lv", "vm_dev": "vm"}
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
N_PERM = 500
HOLM_M = 5
ALPHA = 0.05
MIN_DELTA = 0.005
NONINFERIORITY = -0.005
#: the same sign in at least this many folds of the frame's folds (s6 item 2)
SIGN_REQUIRED = {"lv_dev": (2, 3), "vm_dev": (5, 7)}
FORKING_PATHS_ADDED = 10
RANK_WEIGHT_GRID = tuple(round(0.1 * i, 1) for i in range(11))
CONS = SB.CONSENSUS_KEY
V2_KEY = "efv_v2"
ARM_KEY = "efv_v2_mc"
SOURCES = tuple(SB.SCORED_SOURCES)
#: (grade key, artifact rater name)
RATERS_OUT = ((ARM_KEY, "efv_v2_mc"), (V2_KEY, "efv_v2"), (CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
#: (name, a, b): every delta per arm and frame, a minus b, by every statistic.
COMPARISONS = (("arm_vs_efv_v2", ARM_KEY, V2_KEY),
               ("arm_vs_prospx_consensus", ARM_KEY, CONS),
               ("arm_vs_mlb_pipeline", ARM_KEY, "mlb_pipeline"),
               ("arm_vs_fangraphs", ARM_KEY, "fangraphs"))
ADMISSION_LEG = "arm_vs_efv_v2"
SINGLE_SOURCE = {"k": CS.SINGLE_SOURCE_K, "prior": CS.SINGLE_SOURCE_PRIOR}
ADMISSION_RULE = {
    "1_within_delta_vs_v2": f"at least +{MIN_DELTA} on both frames",
    "2_fold_signs": "the same sign in at least 2 of 3 lv folds and 5 of 7 vm years",
    "3_noninferiority": f"lower CI95 vs V2 above {NONINFERIORITY} on both frames",
    "4_twin": "the twin's within delta over V2 below the arm's on both frames",
    "5_auc_veto": ("the arm-minus-V2 contributor AUC delta not below minus its own mde95 "
                   "on either frame"),
    "6_holm": (f"survives Holm with m {HOLM_M} across the five arms on the vs-V2 within "
               f"leg, one-sided family alpha {ALPHA}; p = the larger of the two frames' "
               "bootstrap shares of draws at or below zero"),
    "mc4a_adoptable": ("MC-4a only: non-inferiority (item 3) on both frames and no AUC "
                       "veto mark it adoptable under lane C E3-Q3 = A, no margin claim, "
                       "behind V2_SIGN_CONSTRAINED = False"),
}


# ---------------------------------------------------------------------------
# guards and small helpers
# ---------------------------------------------------------------------------

def screen_guards(lv_years, vm_years) -> dict:
    """The frame guards, asserted before any fit (tools/efv_v2_dev_read._ds16_guards'
    rule): no list vintage above 2019 or in RESERVED_LV, no vm year at or after the
    first reserved debut cohort, reserved_vm_pins() empty, the combiner rule's years
    below the first scored year. Raises on a violation."""
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    lv = sorted(int(v) for v in lv_years)
    vm = sorted(int(y) for y in vm_years)
    if not lv or not vm:
        raise ValueError("both frames need at least one fold")
    bad = [v for v in lv if v in F.RESERVED_LV or v >= min(F.RESERVED_LV)]
    if bad:
        raise F.ReservedFrameError(f"a list-vintage fold is reserved: {bad}")
    for v in lv:
        F.guard_score_request(v, purpose="model-class screen")
    if max(vm) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise F.ReservedFrameError(f"a vm fold reaches R-VM: {vm}")
    H._check_years(vm)
    if H.RULE_LAST_YEAR >= min(lv) or H.RULE_LAST_YEAR >= min(vm):
        raise ValueError("the combiner rule's years overlap the scored folds")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins, "lv_folds": lv, "vm_folds": vm,
            "rule_last_year": H.RULE_LAST_YEAR,
            "v2_first_scored_year": H.V2_FIRST_SCORED_YEAR}


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _git_text(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                           text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def declared_in() -> dict:
    """The commit that carries the pre-declaration this screen runs under."""
    sha = _git_text("log", "-1", "--format=%H", "--", DECLARED_DOC)
    return {"doc": DECLARED_DOC, "commit": sha,
            "committed_at": _git_text("show", "-s", "--format=%cI", sha) if sha else None}


def _label() -> dict:
    return {"provider": L.provider(), "resolved_through": L.resolved_through(),
            "id": _label_id()}


def _label_id() -> str | None:
    try:
        import storage
        fp = storage.board_basis_fingerprint()
    except Exception:                                         # noqa: BLE001
        return None
    for part in (fp or "").split("|"):
        if part.startswith("label="):
            return part[len("label="):]
    return None


def _is_under_data(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(H.DATA_DIR.resolve())
        return True
    except ValueError:
        return False


def _n_side(rows) -> dict:
    out: dict = {}
    for c in rows:
        out[c["side"]] = out.get(c["side"], 0) + 1
    return out


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


# ---------------------------------------------------------------------------
# the twin controls (one draw each)
# ---------------------------------------------------------------------------

def permute_drivers(rows: list[dict], rng) -> list[dict]:
    """The driver columns (feats, extra, v2) permuted among the rows of each decision
    year; player key, consensus, target, reached, weight and grades stay with the row.
    The vintage marginal of every driver is kept; its link to the row is broken."""
    by: dict = {}
    for i, r in enumerate(rows):
        by.setdefault(int(r["decision_year"]), []).append(i)
    out = [dict(r) for r in rows]
    for y in sorted(by):
        idx = by[y]
        perm = rng.permutation(len(idx))
        for pos, j in zip(idx, perm):
            src = rows[idx[int(j)]]
            out[pos]["feats"] = src["feats"]
            out[pos]["extra"] = src.get("extra")
            out[pos]["v2"] = src["v2"]
    return out


def permute_bands(rows: list[dict], rng) -> list[dict]:
    """MC-3's band labels permuted within decision year, written under
    efv_v2_candidates.MC3_BAND_KEY so band_of_row reads the permuted label; every
    other column stays with its row (the heads are V2's, unchanged)."""
    labels = [C.band_of_row(r) for r in rows]
    by: dict = {}
    for i, r in enumerate(rows):
        by.setdefault(int(r["decision_year"]), []).append(i)
    out = [dict(r) for r in rows]
    for y in sorted(by):
        idx = by[y]
        perm = rng.permutation(len(idx))
        for pos, j in zip(idx, perm):
            out[pos][C.MC3_BAND_KEY] = labels[idx[int(j)]]
    return out


def exchange_reliability(rel: dict, rng) -> dict:
    """MC-2's source reliability weights exchanged across sources within (side, V):
    the table's values permuted among its sources, one draw per (side, V)."""
    out = copy.deepcopy(rel)
    for side, by_v in out["table"].items():
        for V in sorted(by_v):
            srcs = sorted(by_v[V])
            vals = [by_v[V][s] for s in srcs]
            perm = rng.permutation(len(srcs))
            by_v[V] = {s: vals[int(j)] for s, j in zip(srcs, perm)}
    out["twin"] = "weights exchanged across sources within (side, V); one draw"
    return out


# ---------------------------------------------------------------------------
# fitting one arm on one fold
# ---------------------------------------------------------------------------

def _receipt(arm: str, m: dict) -> dict:
    rec = {"consensus_only": m.get("consensus_only"),
           "skill_keys": (m.get("skill") or {}).get("keys"),
           "timing_keys": (m.get("timing") or {}).get("keys"),
           "w_skill": m.get("w_skill"), "w_time": m.get("w_time"),
           "n_train": m.get("n_train")}
    if arm == "mc1":
        rec.update(n_pairs=(m.get("skill") or {}).get("n_pairs"),
                   pair_weighting=m.get("pair_weighting"), note=m.get("note"))
    if arm == "mc2":
        rec.update(n_train_rows_without_source=(m.get("anchor") or {}).get(
            "n_train_rows_without_source"))
    if arm == "mc3":
        rec.update(band_weights=m.get("band_weights"),
                   n_train_by_band=m.get("n_train_by_band"))
    if arm in ("mc4a", "mc4b"):
        rec.update(constrained_zero=m.get("constrained_zero"))
    if arm == "mc4b":
        rec.update(fell_back=m.get("fell_back"), fallback_reason=m.get("fallback_reason"),
                   n_has_block_train=m.get("n_has_block_train"))
    return rec


def fit_fold(arm: str, side: str, kind: str, train: list[dict], test: list[dict],
             ctx: dict, *, variant: str | None = None) -> tuple[dict, dict]:
    """(model, {player_key: order_idx}) for one arm on one fold. `ctx` carries the
    weights, the absence admission, the reliability table per frame and the band
    weights per side (the arm's own, or the twin's)."""
    C.guard_training_rows(train, kind)
    w = ctx["weights"]
    ab = ctx.get("absent_ok")
    if arm == "mc1":
        m = C.fit_mc1_pairwise(train, side, kind, w, pair_weighting=variant or "distance",
                               absent_ok=ab)
        pred = C.predict_mc1(m, test)
    elif arm == "mc2":
        m = C.fit_mc2_anchor(train, side, kind, w, ctx["reliability"], absent_ok=ab)
        pred = C.predict_mc2(m, test)
    elif arm == "mc3":
        m = C.fit_mc3_twoband(train, side, kind, ctx["band_weights"][side]["weights"],
                              absent_ok=ab)
        pred = C.predict_mc3(m, test)
    elif arm == "mc4a":
        m = C.fit_mc4a_signed(train, side, kind, w, absent_ok=ab)
        pred = C.predict_mc4a(m, test)
    elif arm == "mc4b":
        m = C.fit_mc4b_spline(train, side, kind, w, absent_ok=ab)
        pred = C.predict_mc4b(m, test)
    else:
        raise ValueError(f"unknown arm {arm!r}")
    return m, {p["player_key"]: float(p["order_idx"]) for p in pred}


def arm_orders(inputs: dict, fid: str, arm: str, *, variant: str | None = None,
               twin_seed: int | None = None, log=print) -> tuple[dict, dict]:
    """The arm's order index on every scored row of the frame, fold by fold, with the
    fold receipts. `twin_seed` builds the zero-information twin instead."""
    fr = inputs["frames"][fid]
    kind = FRAME_KIND[fid]
    ctx = {"weights": inputs["weights"], "absent_ok": inputs.get("absent_ok"),
           "reliability": fr.get("reliability"), "band_weights": inputs.get("band_weights")}
    twin = twin_seed is not None
    rng = np.random.default_rng(twin_seed) if twin else None
    if twin and arm == "mc2":
        ctx["reliability"] = exchange_reliability(fr["reliability"], rng)
    if twin and arm == "mc3":
        ctx["band_weights"] = inputs["band_weights_twin"]
    orders: dict = {}
    receipts: dict = {}
    for side in F.SIDES:
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            train, test = blk["train"], blk["test"]
            if twin and arm in ("mc1", "mc4a", "mc4b"):
                train, test = permute_drivers(train, rng), permute_drivers(test, rng)
            if twin and arm == "mc3":
                train, test = permute_bands(train, rng), permute_bands(test, rng)
            t0 = time.time()
            m, pred = fit_fold(arm, side, kind, train, test, ctx, variant=variant)
            for c in blk["scored"]:
                if c["key"] not in pred:
                    raise RuntimeError(f"{arm} {fid} {side} {fold}: no score for {c['key']}")
                orders[(side, fold, c["key"])] = pred[c["key"]]
            receipts[f"{side}|{fold}"] = dict(_receipt(arm, m), n_scored=len(blk["scored"]),
                                              elapsed_s=round(time.time() - t0, 1))
            log(f"  {ARM_LABEL[arm]}{' twin' if twin else ''}"
                f"{' ' + variant if variant else ''} {fid} {side} {fold}: "
                f"{len(train)} train, {len(blk['scored'])} scored, "
                f"{round(time.time() - t0, 1)} s")
    return orders, receipts


def rows_with_arm(inputs: dict, fid: str, orders: dict) -> list[dict]:
    """The frame's scored rows with the arm's order index under ARM_KEY."""
    fr = inputs["frames"][fid]
    out = []
    for side in F.SIDES:
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            for c in blk["scored"]:
                row = dict(c)
                row["grades"] = dict(c["grades"], **{ARM_KEY: orders[(side, fold, c["key"])]})
                out.append(row)
    return out


def scored_rows(inputs: dict, fid: str) -> list[dict]:
    fr = inputs["frames"][fid]
    return [c for side in F.SIDES for fold in fr["folds"]
            for c in (fr["by_side"][side].get(fold) or {}).get("scored", [])]


# ---------------------------------------------------------------------------
# the statistics on one frame
# ---------------------------------------------------------------------------

def _cols(sel, key):
    return [c["grades"][key] for c in sel]


def frame_block(rows: list[dict], *, B: int = B_DEFAULT, seed: int = SEED,
                comparisons=COMPARISONS, raters_out=RATERS_OUT) -> dict:
    """Rater stats and every comparison by every statistic, on identical rows
    (tools/efv_v2_dev_read._v2_frame_block with the arm as the subject)."""
    raters = {}
    for key, name in raters_out:
        sel = [c for c in rows if c["grades"].get(key) is not None]
        if not sel:
            continue
        st = S.rater_stats(_cols(sel, key), [c["outcome"]["war"] for c in sel],
                           [bool(c["outcome"]["contributor"]) for c in sel],
                           [c["group"] for c in sel], _cols(sel, CONS))
        raters[name] = {"spearman": st["within"], "auc": st["auc"], "n": st["n"],
                        "within": st["within"], "pooled": st["pooled"],
                        "within_rows": st["within_rows"],
                        "within_groups": st["within_groups"]}
    deltas = {}
    for name, a, b in comparisons:
        sel = [c for c in rows if c["grades"].get(a) is not None
               and c["grades"].get(b) is not None]
        legs = {}
        for stat, slot in (("within", "spearman"), ("pooled", "pooled"), ("auc", "auc")):
            d = S.paired_delta([c["key"] for c in sel], [c["group"] for c in sel],
                               [c["outcome"]["war"] for c in sel],
                               [bool(c["outcome"]["contributor"]) for c in sel],
                               _cols(sel, a), _cols(sel, b), _cols(sel, CONS),
                               statistic=stat, B=B, seed=seed)
            d["reading"] = S.reading(d.get("ci95"))
            legs[slot] = d
        deltas[name] = legs
    return {"raters": raters, "deltas": deltas}


def secondary_view(block: dict) -> dict:
    return {"statistic": S.STAT_LABEL["pooled"],
            "raters": {n: r.get("pooled") for n, r in block["raters"].items()},
            "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                           "ci95": (d.get("pooled") or {}).get("ci95"),
                           "mde95": (d.get("pooled") or {}).get("mde95"),
                           "reading": (d.get("pooled") or {}).get("reading")}
                       for n, d in block["deltas"].items()}}


def _arrays(rows, a_key, b_key):
    sel = [c for c in rows if c["grades"].get(a_key) is not None
           and c["grades"].get(b_key) is not None]
    a = np.asarray(_cols(sel, a_key), dtype=np.float64)
    b = np.asarray(_cols(sel, b_key), dtype=np.float64)
    y = np.asarray([c["outcome"]["war"] for c in sel], dtype=np.float64)
    codes = np.asarray([str(c["group"]) for c in sel])
    return sel, a, b, y, codes


def fold_deltas(rows: list[dict], a_key: str = ARM_KEY, b_key: str = V2_KEY) -> dict:
    """The a-minus-b within delta on each fold (both sides' groups of that vintage,
    size-weighted, groups of at least MIN_GROUP_ROWS rows where both raters have a
    rho), with its sign."""
    sel, a, b, y, codes = _arrays(rows, a_key, b_key)
    years = sorted({int(c["year"]) for c in sel})
    keep = S.kept_groups(codes)
    out = {}
    for yr in years:
        idx = np.asarray([i for i, c in enumerate(sel) if int(c["year"]) == yr])
        ta, tb = S._within_pair(a, b, y, codes, keep, idx)
        d = None if (ta is None or tb is None) else ta - tb
        out[str(yr)] = {"n": int(idx.size), "a": _rnd(ta), "b": _rnd(tb), "delta": _rnd(d),
                        "sign": (None if d is None else (1 if d > 0 else (-1 if d < 0 else 0)))}
    return out


def sign_agreement(folds: dict, fid: str, frame_delta: float | None) -> dict:
    """How many folds share the frame delta's sign, against the registered bar."""
    need, of = SIGN_REQUIRED[fid]
    ref = 0 if frame_delta is None else (1 if frame_delta > 0 else (-1 if frame_delta < 0 else 0))
    same = sum(1 for f in folds.values() if f["sign"] is not None and ref and f["sign"] == ref)
    return {"frame_sign": ref, "same_sign": same, "folds": len(folds), "required": need,
            "of": of, "ok": bool(ref > 0 and len(folds) == of and same >= need)}


def permutation_null(rows: list[dict], observed: float | None, *, n_perm: int = N_PERM,
                     seed: int = SEED, a_key: str = ARM_KEY, b_key: str = V2_KEY) -> dict:
    """n_perm draws of the outcome permuted inside each (side, vintage) group, the
    a-minus-b within delta recomputed per draw on the fixed scores; one-sided
    p = (1 + #(null >= observed)) / (1 + n_perm); the 95th percentile printed."""
    sel, a, b, y, codes = _arrays(rows, a_key, b_key)
    keep = S.kept_groups(codes)
    idx = np.arange(a.size)
    groups = [np.flatnonzero(codes == u) for u in np.unique(codes)]
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(int(n_perm)):
        yp = y.copy()
        for g in groups:
            yp[g] = y[g[rng.permutation(g.size)]]
        ta, tb = S._within_pair(a, b, yp, codes, keep, idx)
        if ta is not None and tb is not None:
            null.append(ta - tb)
    if observed is None or not null:
        return {"n": len(null), "p": None, "seed": int(seed), "status": "not derived"}
    arr = np.asarray(null, dtype=np.float64)
    p = (1.0 + float((arr >= float(observed)).sum())) / (1.0 + arr.size)
    return {"n": int(arr.size), "seed": int(seed), "observed": _rnd(observed),
            "p": round(p, 5), "null_mean": _rnd(arr.mean()), "null_sd": _rnd(arr.std()),
            "null_q95": _rnd(np.quantile(arr, 0.95)), "status": "derived",
            "what": "the outcome permuted inside each (side, vintage) group, scores fixed"}


def holm_adjust(pvals: dict, m: int = HOLM_M, alpha: float = ALPHA) -> dict:
    """Holm step-down over a family of size m (the registered size; an arm with no p
    is absent from the ordering and never survives)."""
    live = sorted(((k, float(p)) for k, p in pvals.items() if p is not None),
                  key=lambda kv: kv[1])
    out: dict = {}
    running = 0.0
    for i, (k, p) in enumerate(live):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = {"p": round(p, 5), "rank": i + 1, "holm_p": round(running, 5),
                  "holm_alpha": round(alpha / (m - i), 5),
                  "survives_holm": bool(running < alpha)}
    for k, p in pvals.items():
        if p is None:
            out[k] = {"p": None, "rank": None, "holm_p": None, "holm_alpha": None,
                      "survives_holm": None}
    return out


# ---------------------------------------------------------------------------
# admission (s6), applied by the tool and printed, never by hand
# ---------------------------------------------------------------------------

def admission_inputs(frame_doc: dict) -> dict:
    """The numbers the rule reads off one arm's frame block."""
    leg = (frame_doc.get("deltas") or {}).get(ADMISSION_LEG) or {}
    w = leg.get("spearman") or {}
    auc = leg.get("auc") or {}
    ci = w.get("ci95")
    return {"delta": w.get("delta"), "ci_low": (ci[0] if isinstance(ci, list) and ci else None),
            "p_gt_0": w.get("p_gt_0"),
            "sign": (frame_doc.get("fold_sign_agreement") or {}).get("ok"),
            "twin_delta": ((frame_doc.get("twin") or {}).get("within") or {}).get("delta"),
            "auc_delta": auc.get("delta"), "auc_mde95": auc.get("mde95")}


def admission_verdict(arm: str, per_frame: dict, holm_row: dict | None) -> dict:
    """The six clauses on both frames; MC-4a's adoptable mark. Every clause is True,
    False or None (not derivable, which never admits)."""
    fids = list(per_frame)

    def both(fn):
        vals = [fn(per_frame[f]) for f in fids]
        if any(v is None for v in vals):
            return None
        return bool(all(vals))
    c1 = both(lambda x: None if x["delta"] is None else x["delta"] >= MIN_DELTA)
    c2 = both(lambda x: x["sign"])
    c3 = both(lambda x: None if x["ci_low"] is None else x["ci_low"] > NONINFERIORITY)
    c4 = both(lambda x: None if (x["twin_delta"] is None or x["delta"] is None)
              else x["twin_delta"] < x["delta"])
    c5 = both(lambda x: None if (x["auc_delta"] is None or x["auc_mde95"] is None)
              else x["auc_delta"] >= -x["auc_mde95"])
    c6 = None if not holm_row else holm_row.get("survives_holm")
    clauses = {"1_within_delta_vs_v2": c1, "2_fold_signs": c2, "3_noninferiority": c3,
               "4_twin": c4, "5_auc_veto": c5, "6_holm": c6}
    admitted = all(v is True for v in clauses.values())
    adoptable = bool(arm == "mc4a" and c3 is True and c5 is True)
    failed = [k for k, v in clauses.items() if v is not True]
    if admitted:
        reason = ("ADMITTED: every clause holds on both frames; a labelled secondary "
                  "candidate for EFV3_C04 (no ship weight), not a claim")
    else:
        reason = "NOT ADMITTED: " + ", ".join(
            f"{k} {'not derivable' if clauses[k] is None else 'failed'}" for k in failed)
        if adoptable:
            reason = ("ADOPTABLE on non-inferiority alone (lane C E3-Q3 = A, no margin "
                      "claim, behind V2_SIGN_CONSTRAINED = False); " + reason)
    return {"admitted": admitted, "adoptable": adoptable, "clauses": clauses,
            "reason": reason}


def probe_verdict(verdict: dict) -> str:
    if verdict["admitted"]:
        return "ADMITTED"
    if verdict["adoptable"]:
        return "ADOPTABLE"
    return "NULL"


# ---------------------------------------------------------------------------
# sensitivities outside the family
# ---------------------------------------------------------------------------

def rank_consistent_weights(side: str, sources: dict, *, last_year: int = H.RULE_LAST_YEAR,
                            absent_ok: bool | None = None,
                            min_rows: int = S.MIN_GROUP_ROWS) -> dict:
    """Lane C E3-Q2 = A, a sensitivity only: on the DS-08 rule rows (the same rule folds
    efv_v2_model.combiner_rule reads, years at most RULE_LAST_YEAR, heads as
    _rule_heads fits them), w per head chosen over RANK_WEIGHT_GRID by maximizing the
    size-weighted within-(side, year) Spearman of u_c + w * e against u_y over the
    counted (source, year) groups, ties to the smaller w. Selected nowhere."""
    if int(last_year) > H.RULE_LAST_YEAR:
        raise ValueError(f"the rule reads no year after {H.RULE_LAST_YEAR}")
    ab = H.absence_admitted(side) if absent_ok is None else bool(absent_ok)
    groups = []
    for name, rows in sources.items():
        rule_rows = [r for r in rows if int(r["decision_year"]) <= int(last_year)]
        H._check_years({int(r["decision_year"]) for r in rule_rows})
        ob = all(bool(r.get("ids_outcome_blind")) for r in rule_rows) and bool(rule_rows)
        for y in H.inner_years(rule_rows):
            te = [r for r in rule_rows if r["decision_year"] == y]
            te_keys = {r["player_key"] for r in te}
            tr = [r for r in rule_rows if r["decision_year"] < y
                  and not (ob and r["player_key"] in te_keys)]
            skill, timing = H._rule_heads(tr, side, ids_outcome_blind=ob, absent_ok=ob and ab)
            es, et = H.e_skill(skill, te), H.e_time(timing, te)
            if not (np.any(es != 0) or np.any(et != 0)):
                continue
            u_c, u_y = H._percentiles(te)
            groups.append({"source": name, "year": int(y), "n": len(te), "u_c": u_c,
                           "u_y": u_y, "e_s": es, "e_t": et})

    def score(w: float, key: str) -> float | None:
        tot, n = 0.0, 0
        for g in groups:
            if g["n"] < min_rows:
                continue
            rho = S._rho(g["u_c"] + w * g[key], g["u_y"])
            if rho is None:
                continue
            tot += rho * g["n"]
            n += g["n"]
        return (tot / n) if n else None

    out = {"side": side, "last_year": int(last_year), "grid": list(RANK_WEIGHT_GRID),
           "rule": ("argmax over the grid of the size-weighted within-(side, year) Spearman "
                    "of u_c + w * e against u_y on the counted rule groups; ties to the "
                    "smaller w; a sensitivity, selected nowhere (lane C E3-Q2 = A)"),
           "groups": [{"source": g["source"], "year": g["year"], "n": g["n"]} for g in groups],
           "weights": {}, "curves": {}}
    for head, key in (("w_skill", "e_s"), ("w_time", "e_t")):
        curve = {str(w): _rnd(score(w, key)) for w in RANK_WEIGHT_GRID}
        best_w, best = None, None
        for w in RANK_WEIGHT_GRID:
            v = score(w, key)
            if v is None:
                continue
            if best is None or v > best:
                best_w, best = w, v
        out["curves"][head] = curve
        out["weights"][head] = best_w
    return out


def rescore_v2(inputs: dict, fid: str, weights: dict) -> dict:
    """V2's order at other weights, from the fold V2 predictions (u_c, e_skill, e_time)
    with no refit: {(side, fold, key): order}. A head whose DS-08 weight is 0 carries
    e = 0 in those predictions, which the receipt discloses."""
    fr = inputs["frames"][fid]
    out = {}
    for side in F.SIDES:
        w = weights[side]
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            pred = {p["player_key"]: p for p in blk["v2_pred"]}
            for c in blk["scored"]:
                p = pred[c["key"]]
                out[(side, fold, c["key"])] = float(
                    p["u_c"] + float(w["w_skill"] or 0.0) * p["e_skill"]
                    + float(w["w_time"] or 0.0) * p["e_time"])
    return out


def within_delta_only(rows: list[dict], a_key: str, b_key: str, *, B: int, seed: int) -> dict:
    sel = [c for c in rows if c["grades"].get(a_key) is not None
           and c["grades"].get(b_key) is not None]
    d = S.paired_delta([c["key"] for c in sel], [c["group"] for c in sel],
                       [c["outcome"]["war"] for c in sel],
                       [bool(c["outcome"]["contributor"]) for c in sel],
                       _cols(sel, a_key), _cols(sel, b_key), _cols(sel, CONS),
                       statistic="within", B=B, seed=seed)
    d["reading"] = S.reading(d.get("ci95"))
    return d


# ---------------------------------------------------------------------------
# the real inputs
# ---------------------------------------------------------------------------

def _grades_for(universe_by_key: dict, key: str, year: int) -> dict:
    p = universe_by_key.get(key)
    if p is None:
        return {}
    g = SB._rater_grades_for_year(p, int(year))
    return {s: float(g[s]) for s in SOURCES if g.get(s) is not None}


def base_parity(inputs: dict, ds16: dict | None) -> dict:
    """This tool's V2 base against the DS-16 block: n, groups and the within statistic of
    V2 and consensus per frame must agree (the base is the one recorded read)."""
    out = {"artifact": "data/efv_v2_dev_eval.json", "block": "ds16",
           "ds16_generated_at": (ds16 or {}).get("generated_at"),
           "ds16_assembly_sha256": (ds16 or {}).get("assembly_sha256"),
           "frames": {}, "reproduces": None}
    ok_all = ds16 is not None
    for fid in FRAMES:
        rows = scored_rows(inputs, fid)
        here = {}
        for key, name in ((V2_KEY, "efv_v2"), (CONS, "prospx_consensus")):
            sel = [c for c in rows if c["grades"].get(key) is not None]
            st = S.rater_stats(_cols(sel, key), [c["outcome"]["war"] for c in sel],
                               [bool(c["outcome"]["contributor"]) for c in sel],
                               [c["group"] for c in sel], _cols(sel, CONS))
            here[name] = {"within": st["within"], "n": st["n"], "auc": st["auc"]}
        groups = sorted({c["group"] for c in rows})
        rec = {"n_here": len(rows), "groups_here": groups, "raters_here": here}
        ok = None
        if ds16 is not None:
            blk = (ds16.get("frames") or {}).get(fid) or {}
            rec.update(n_ds16=blk.get("n"), groups_ds16=blk.get("groups"),
                       raters_ds16={n: {"within": (blk.get("raters") or {}).get(n, {}).get("within"),
                                        "n": (blk.get("raters") or {}).get(n, {}).get("n")}
                                    for n in here})
            ok = (blk.get("n") == len(rows) and blk.get("groups") == groups
                  and all((blk.get("raters") or {}).get(n, {}).get("within") == here[n]["within"]
                          and (blk.get("raters") or {}).get(n, {}).get("n") == here[n]["n"]
                          for n in here))
            ok_all = ok_all and ok
        rec["reproduces"] = ok
        out["frames"][fid] = rec
    out["reproduces"] = bool(ok_all)
    return out


def build_inputs(data_dir: Path | None = None, *, log=print) -> dict:
    """The two frames with their per-fold training and test rows, the DS-16 row
    selection with the V2 base refit per fold, the reliability tables, the rule sources
    and the band weights. No arm is fitted here."""
    import efv_drivers as DRV
    import efv_v2_assemble as ASM
    import efv_v2_dev_read as DR
    t0 = time.time()
    data_dir = Path(data_dir) if data_dir is not None else H.DATA_DIR
    weights = H.load_weights()
    lv_folds = [v for v in F.DEV_VINTAGES if v >= H.V2_FIRST_SCORED_YEAR]
    vm_fold_years = [y for y in V1.SCORED_YEARS
                     if H.V2_FIRST_SCORED_YEAR <= y < F.R_VM_FIRST_DEBUT_YEAR]
    guards = screen_guards(lv_folds, vm_fold_years)
    guards["ds16_guards"] = DR._ds16_guards()
    log(f"guards: {json.dumps(guards)}")
    # --- lv_dev -------------------------------------------------------------
    frames = ASM.build_frames()
    log(f"lv frames built ({round(time.time() - t0, 1)} s)")
    labels_all = [(V, lab) for s in F.SIDES for V in frames[s] for lab in frames[s][V][1]]
    ws = DR.w_star_dev(labels_all)
    lv = {"kind": "lv", "folds": lv_folds, "by_side": {}, "reliability_rows": {},
          "per_vintage": [], "w_star_dev": ws, "reserved_vm_kept_w3_zero": 0}
    rule_sources: dict = {}
    for side in F.SIDES:
        grades_at = {(r["player_key"], int(V)): {k: float(v) for k, v in (r.get("grades") or {}).items()
                                                if v is not None}
                     for V, (rows, _labs) in frames[side].items() for r in rows}
        train_all = [dict(r, grades=grades_at[(r["player_key"], int(r["decision_year"]))])
                     for r in H.lv_training_rows(side, frames[side])]
        mat = H.training_rows(side)
        lv["reliability_rows"][side] = {
            int(V): [{"grades": {s: float(r["grades"][s]) for s in SOURCES
                                 if (r.get("grades") or {}).get(s) is not None},
                      "target": float(lab["w3"])}
                     for r, lab in zip(rows, labs)
                     if lab.get("w3") is not None and (r.get("grades") or {}).get(CONS) is not None]
            for V, (rows, labs) in frames[side].items()}
        rule_sources[side] = {"matrix": [r for r in H.matrix_training_rows(side)
                                         if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR],
                              "lv": train_all}
        lv["by_side"][side] = {}
        for V in lv_folds:
            F.guard_score_request(V, purpose="model-class screen")
            if V in F.RESERVED_LV:
                raise F.ReservedFrameError(f"lv vintage {V} is reserved")
            rows, labs = frames[side][V]
            test = [dict(r, grades=grades_at[(r["player_key"], V)])
                    for r in H.lv_v2_rows(side, V, rows)]
            in_frame = {r["player_key"] for r in rows}
            tr = [r for r in train_all if r["decision_year"] < V
                  and r["player_key"] not in in_frame]
            C.guard_training_rows(tr, "lv")
            model = H.fit_v2(tr, side, frame="lv", weights=weights)
            pred = H.predict_v2(model, test)
            v2 = {p["player_key"]: float(p["order_idx"]) for p in pred}
            sc1 = H.lv_scores(side, V, rows, data=mat)
            rec = {"side": side, "vintage": V, "frame_rows": len(rows), "n_train": len(tr),
                   "n_train_v1": sc1["n_train"], "v1_status": sc1["status"],
                   "consensus_only": model["consensus_only"],
                   "skill_keys": (model["skill"] or {}).get("keys"),
                   "timing_keys": (model["timing"] or {}).get("keys"),
                   "w_skill": model["w_skill"], "w_time": model["w_time"], "n_scored": 0,
                   "reserved_vm_kept_w3_zero": 0}
            scored = []
            for r, lab in zip(rows, labs):
                k = r["player_key"]
                g = r["grades"]
                if (g.get(CONS) is None or lab.get("w3") is None or k not in v2
                        or k not in sc1["v1"]):
                    continue
                if lab.get("status") == "reserved_vm":
                    dy = lab.get("debut_year")
                    if lab["w3"] != 0.0 or (dy is not None and dy <= V + L.W_DEBUT_WINDOW):
                        raise F.ReservedFrameError(f"reserved_vm row in window: {k} {V}")
                    rec["reserved_vm_kept_w3_zero"] += 1
                    lv["reserved_vm_kept_w3_zero"] += 1
                grades = {CONS: float(g[CONS]), V2_KEY: v2[k]}
                for src in SOURCES:
                    if g.get(src) is not None:
                        grades[src] = float(g[src])
                w3 = float(lab["w3"])
                scored.append({"key": k, "side": side, "year": V, "group": f"{side}|{V}",
                               "grades": grades,
                               "outcome": {"war": w3, "contributor": (
                                   ws["w_star"] is not None and w3 >= ws["w_star"])}})
                rec["n_scored"] += 1
            lv["per_vintage"].append(rec)
            lv["by_side"][side][V] = {"train": tr, "test": test, "scored": scored,
                                      "v2_model": model, "v2_pred": pred}
            log(f"  lv {side} {V}: {len(tr)} train, {len(test)} test, {len(scored)} scored")
    # --- vm_dev -------------------------------------------------------------
    frame_rows, vm_meta = DR.v2_vm_dev(data_dir, weights)
    # the folds are the resolved debut years the DS-16 frame scores (2017 to 2023
    # today); a later SCORED_YEAR with no frame row is not a fold of this screen
    vm_fold_years = [y for y in vm_fold_years if y in set(vm_meta["years"])]
    guards = screen_guards(lv_folds, vm_fold_years)
    guards["ds16_guards"] = DR._ds16_guards()
    universe = SB._load_universe(data_dir)
    by_key = {p.get("player_key"): p for p in universe}
    panel = DRV.load_bio_panel()
    vm = {"kind": "vm", "folds": vm_fold_years, "by_side": {}, "reliability_rows": {},
          "per_fold": [], "window": vm_meta["window"], "dropped": vm_meta["dropped"],
          "population_rows": vm_meta["population_rows"]}
    side_of: dict = {}
    for side in F.SIDES:
        data = H.matrix_training_rows(side)
        for r in data:
            side_of.setdefault(r["player_key"], side)
        mine: dict = {}
        pinned = H.pinned_inputs(side, data, mine)
        vm["by_side"][side] = {}
        for yr in vm_fold_years:
            tr = [r for r in data if r["decision_year"] < yr]
            te = [r for r in data if r["decision_year"] == yr]
            if len(te) < H.MIN_TEST_ROWS or len(tr) < H.MIN_TRAIN_ROWS:
                continue
            te2 = []
            for r in te:
                pin = pinned.get(r["player_key"])
                if pin is None:
                    continue
                extra = {"bmi": DRV.bmi_asof(r["player_key"],
                                             mine[r["player_key"]].get("asof_date"), panel)}
                te2.append(dict(r, feats=pin["feats"], fv=pin["fv"], extra=extra,
                                v2=H.v2_row(pin["feats"], extra),
                                grades=_grades_for(by_key, r["player_key"], yr)))
            tr = [dict(r, grades=_grades_for(by_key, r["player_key"], r["decision_year"]))
                  for r in tr]
            C.guard_training_rows(tr, "vm")
            model = H.fit_v2(tr, side, frame="vm", weights=weights)
            pred = H.predict_v2(model, te2)
            v2 = {p["player_key"]: float(p["order_idx"]) for p in pred}
            scored = []
            for c in frame_rows:
                if c["side"] != side or int(c["year"]) != yr:
                    continue
                if c["key"] not in v2:
                    raise RuntimeError(f"vm {side} {yr}: frame row {c['key']} not scored here")
                if v2[c["key"]] != float(c["grades"][DR.V2_KEY]):
                    raise RuntimeError(f"vm {side} {yr}: V2 base differs for {c['key']}")
                grades = {CONS: float(c["grades"][CONS]), V2_KEY: v2[c["key"]]}
                for src in SOURCES:
                    if c["grades"].get(src) is not None:
                        grades[src] = float(c["grades"][src])
                scored.append({"key": c["key"], "side": side, "year": yr,
                               "group": f"{side}|{yr}", "grades": grades,
                               "outcome": {"war": float(c["outcome"]["war"]),
                                           "contributor": bool(c["outcome"]["contributor"])}})
            vm["per_fold"].append({"side": side, "year": yr, "n_train": len(tr),
                                   "n_test": len(te2), "n_scored": len(scored),
                                   "consensus_only": model["consensus_only"],
                                   "skill_keys": (model["skill"] or {}).get("keys"),
                                   "timing_keys": (model["timing"] or {}).get("keys"),
                                   "w_skill": model["w_skill"], "w_time": model["w_time"],
                                   "train_rows_with_a_source": sum(
                                       1 for r in tr if r["grades"])})
            vm["by_side"][side][yr] = {"train": tr, "test": te2, "scored": scored,
                                       "v2_model": model, "v2_pred": pred}
            log(f"  vm {side} {yr}: {len(tr)} train, {len(te2)} test, {len(scored)} scored")
    # the vm reliability rows: debut cohorts by debut year (career WAR to date), the
    # ONE label of the debut frame (MODEL_CLASS_SCREEN.md s2 MC-2 design rule)
    for side in F.SIDES:
        vm["reliability_rows"][side] = {}
    for p in universe:
        k = p.get("player_key")
        side = side_of.get(k)
        out = SB._outcome(p)
        dy = out.get("debut_year")
        if side is None or dy is None or dy < min(F.DEV_VINTAGES) or dy >= F.R_VM_FIRST_DEBUT_YEAR:
            continue
        g = _grades_for(by_key, k, dy)
        if not g:
            continue
        vm["reliability_rows"][side].setdefault(int(dy), []).append(
            {"grades": g, "target": float(out["war"])})
    inputs = {"weights": weights, "absent_ok": None, "guards": guards,
              "rule_sources": rule_sources, "frames": {"lv_dev": lv, "vm_dev": vm},
              "elapsed_build_s": round(time.time() - t0, 1)}
    finish_inputs(inputs, log=log)
    return inputs


def finish_inputs(inputs: dict, *, log=print) -> dict:
    """The reliability tables (MC-2) per frame and the band weights (MC-3, with the
    twin's band weights) from the inputs' rows; shared by the real and the synthetic
    runs. Written to the artifact before any scored read."""
    for fid in FRAMES:
        fr = inputs["frames"][fid]
        years = sorted({int(r["decision_year"]) for side in F.SIDES
                        for blk in fr["by_side"][side].values()
                        for r in blk["train"] + blk["test"]})
        fr["reliability"] = C.build_source_reliability(
            fr["reliability_rows"], single_source=SINGLE_SOURCE, target_vintages=years,
            frame=fr["kind"])
        fr["reliability"]["label"] = ("W3 on list vintages" if fr["kind"] == "lv"
                                      else "career WAR to date on debut cohorts")
    t0 = time.time()
    inputs["band_weights"] = {s: C.band_weights(s, inputs["rule_sources"][s],
                                                absent_ok=inputs.get("absent_ok"))
                              for s in F.SIDES}
    log(f"band weights: {json.dumps({s: b['weights'] for s, b in inputs['band_weights'].items()})}"
        f" ({round(time.time() - t0, 1)} s)")
    rng = np.random.default_rng(SEED)
    inputs["band_weights_twin"] = {
        s: C.band_weights(s, {name: permute_bands(rows, rng)
                              for name, rows in inputs["rule_sources"][s].items()},
                          absent_ok=inputs.get("absent_ok"))
        for s in F.SIDES}
    for s in F.SIDES:
        inputs["band_weights_twin"][s]["twin"] = ("band labels permuted within decision "
                                                  "year on the rule rows; one draw")
    return inputs


def counts(inputs: dict) -> dict:
    out = {}
    for fid in FRAMES:
        fr = inputs["frames"][fid]
        rows = scored_rows(inputs, fid)
        out[fid] = {"folds": fr["folds"], "n": len(rows), "n_by_side": _n_side(rows),
                    "n_players": len({c["key"] for c in rows}),
                    "groups": sorted({c["group"] for c in rows}),
                    "reliability_targets": {s: sorted(fr["reliability"]["table"][s])
                                            for s in F.SIDES},
                    "reliability_reads": fr["reliability"]["reads"]}
    return out


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _ds16_block() -> dict | None:
    try:
        return (json.loads(H.DEV_EVAL_PATH.read_text(encoding="utf-8")) or {}).get("ds16")
    except (OSError, ValueError):
        return None


def mc5_block(*, log=print) -> dict:
    """MC-5 through tools/efv_v2_pricing_calibration's own run (its frames, MAE and
    calibration per position family; order_idx asserted bit-identical per fold there),
    outside the family; its committed artifact is pointed at beside it."""
    import efv_v2_pricing_calibration as PC
    doc = PC.run()
    frames = {}
    for fid, f in doc["frames"].items():
        frames[fid] = {k: f.get(k) for k in ("n", "n_by_side", "n_players", "mae_base",
                                             "mae_position_age", "delta", "ci95", "sd",
                                             "mean_resid_base", "mean_resid_new",
                                             "verdict", "per_side", "per_family")}
        frames[fid]["order_idx_bit_identical"] = all(
            bool(p.get("order_idx_bit_identical")) for p in f.get("per_fold") or [])
    return {"arm": "MC-5", "model_id": C.ARM_IDS["mc5"], "outside_family": True,
            "metric": "mae", "role": "development", "note": doc.get("note"),
            "statistic": doc.get("statistic"), "assembly_sha256": doc.get("assembly_sha256"),
            "frames": frames, "elapsed_s": doc.get("elapsed_s"),
            "committed_artifact": {"path": "data/efv_v2_pricing_calibration_eval.json",
                                   "sha256": _sha(PC.OUT_PATH),
                                   "generated_at": _read_json(PC.OUT_PATH).get("generated_at"),
                                   "assembly_sha256": _read_json(PC.OUT_PATH).get(
                                       "assembly_sha256")}}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _frame_doc(fid: str, inputs: dict, rows: list[dict], blk: dict, receipts: dict,
               twin: dict, folds: dict, perm: dict) -> dict:
    fr = inputs["frames"][fid]
    prim = blk["deltas"][ADMISSION_LEG]["spearman"]
    doc = {"frame_version": "lv1_v2" if fid == "lv_dev" else "vm2",
           "window": [min(fr["folds"]), max(fr["folds"])],
           "n": len(rows), "n_by_side": _n_side(rows),
           "n_players": len({c["key"] for c in rows}),
           "groups": sorted({c["group"] for c in rows}),
           "outcome": ("W3 (WAR over the first three MLB seasons, 0 if no debut within "
                       "three seasons of V)" if fid == "lv_dev" else "career WAR to date"),
           "statistic": S.STAT_LABEL[S.PRIMARY],
           "raters": blk["raters"], "deltas": blk["deltas"], "secondary": secondary_view(blk),
           "mde95": prim.get("mde95"),
           "twin": twin, "per_fold": folds,
           "fold_sign_agreement": sign_agreement(folds, fid, prim.get("delta")),
           "permutation_null": perm, "folds": receipts,
           "verdict": None, "note": NOTE}
    if fid == "lv_dev":
        doc["w_star_dev"] = fr.get("w_star_dev")
        doc["reserved_vm_kept_w3_zero"] = fr.get("reserved_vm_kept_w3_zero")
    return doc


def run(inputs: dict, *, B: int = B_DEFAULT, n_perm: int = N_PERM, exploratory: bool,
        with_mc5: bool = True, with_rank_weight: bool = True, log=print) -> dict:
    """The screen on built inputs: base parity, then every arm on both frames (its
    deltas, twin, per-fold deltas and permutation null), then the Holm family and
    the admission verdicts, then the sensitivities outside the family."""
    t0 = time.time()
    ds16 = _ds16_block() if not exploratory else None
    parity = base_parity(inputs, ds16)
    if not exploratory and not parity["reproduces"]:
        raise RuntimeError("the V2 base does not reproduce the DS-16 block; nothing scored: "
                           + json.dumps(parity["frames"], default=str)[:600])
    doc: dict = {
        "schema": 1, "item": ITEM,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": TOOL, "role": "development", "adjudicates": False, "selects": False,
        "exploratory": bool(exploratory), "note": NOTE,
        "label": _label() if not exploratory else {"provider": "synthetic",
                                                    "resolved_through": None, "id": None},
        "code": {"commit": _commit(), "tool": TOOL,
                 "efv_v2_candidates_sha256": _sha(ROOT / "efv_v2_candidates.py"),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "declared_in": declared_in(),
        "assembly_sha256": _sha(H.ASSEMBLY_PATH) if not exploratory else None,
        "weights": inputs["weights"],
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "secondary": S.STAT_LABEL[S.SECONDARY],
                      "veto": S.STAT_LABEL["auc"], "min_group_rows": S.MIN_GROUP_ROWS,
                      "group": "(side, list vintage) on lv_dev; (side, base year) on vm_dev",
                      "map": "efv_v2_model.output_map on every rater, on the compared rows",
                      "code": "efv_v2_stat.py"},
        "bootstrap": {"B": int(B), "seed": SEED, "estimator": "E_cond", "unit": "player cluster"},
        "controls": {"twin": "one draw per arm and frame, seed 20260906",
                     "permutation_null": {"n": int(n_perm), "seed": SEED},
                     "per_fold": "the arm-minus-V2 within delta per fold, with its sign"},
        "admission_rule": ADMISSION_RULE,
        "reserved_guard": inputs["guards"],
        "base_parity": parity,
        "frames": {fid: {"folds": inputs["frames"][fid]["folds"],
                         "per_fold_base": (inputs["frames"][fid].get("per_vintage")
                                           or inputs["frames"][fid].get("per_fold")),
                         "reliability": {k: v for k, v in inputs["frames"][fid]["reliability"].items()
                                         if k != "stats"}}
                   for fid in FRAMES},
        "band_weights": {s: {k: v for k, v in inputs["band_weights"][s].items() if k != "bands"}
                         for s in F.SIDES},
        "band_weights_twin": {s: {k: v for k, v in inputs["band_weights_twin"][s].items()
                                  if k != "bands"} for s in F.SIDES},
        "arms": {}, "holm": None, "admitted": [], "adoptable": [],
        "sensitivities": {}, "mc5": None, "probes": {}, "n_probes": 0,
        "forking_paths_added": FORKING_PATHS_ADDED, "spent": [], "elapsed_s": None,
    }
    # --- the arms -------------------------------------------------------------
    for arm in ARMS:
        a_doc = {"arm": ARM_LABEL[arm], "model_id": C.ARM_IDS[arm], "frames": {},
                 "holm": None, "admitted": None, "adoptable": None, "reason": None}
        doc["arms"][arm] = a_doc
        for fid in FRAMES:
            log(f"{ARM_LABEL[arm]} on {fid}")
            orders, receipts = arm_orders(inputs, fid, arm, log=log)
            rows = rows_with_arm(inputs, fid, orders)
            blk = frame_block(rows, B=B, seed=SEED)
            prim = blk["deltas"][ADMISSION_LEG]["spearman"]
            t_orders, t_receipts = arm_orders(inputs, fid, arm, twin_seed=SEED, log=log)
            t_rows = rows_with_arm(inputs, fid, t_orders)
            t_within = within_delta_only(t_rows, ARM_KEY, V2_KEY, B=B, seed=SEED)
            t_auc = S.paired_delta([c["key"] for c in t_rows], [c["group"] for c in t_rows],
                                   [c["outcome"]["war"] for c in t_rows],
                                   [bool(c["outcome"]["contributor"]) for c in t_rows],
                                   _cols(t_rows, ARM_KEY), _cols(t_rows, V2_KEY),
                                   _cols(t_rows, CONS), statistic="auc", B=B, seed=SEED)
            twin = {"seed": SEED,
                    "what": {"mc1": "driver columns permuted within vintage",
                             "mc4a": "driver columns permuted within vintage",
                             "mc4b": "driver columns permuted within vintage",
                             "mc3": "band labels permuted within vintage (rule rows and fold rows)",
                             "mc2": "source reliability weights exchanged across sources within (side, V)"}[arm],
                    "within": {k: t_within.get(k) for k in ("delta", "ci95", "mde95", "p_gt_0", "status")},
                    "auc_delta": t_auc.get("delta"),
                    "below_arm": (None if (t_within.get("delta") is None or prim.get("delta") is None)
                                  else bool(t_within["delta"] < prim["delta"])),
                    "folds": t_receipts}
            folds = fold_deltas(rows)
            perm = permutation_null(rows, prim.get("delta"), n_perm=n_perm, seed=SEED)
            a_doc["frames"][fid] = _frame_doc(fid, inputs, rows, blk, receipts, twin, folds, perm)
            doc["spent"].append(f"{arm}:{fid}")
            log(f"  {ARM_LABEL[arm]} {fid}: within vs V2 {prim.get('delta')} CI {prim.get('ci95')}"
                f" mde95 {prim.get('mde95')}; twin {t_within.get('delta')}; perm p {perm.get('p')}"
                f" ({round(time.time() - t0, 1)} s)")
        if arm == "mc1":
            sens = {}
            for fid in FRAMES:
                o, rec = arm_orders(inputs, fid, arm, variant="listwise", log=log)
                d = within_delta_only(rows_with_arm(inputs, fid, o), ARM_KEY, V2_KEY, B=B, seed=SEED)
                sens[fid] = {"within_vs_v2": {k: d.get(k) for k in ("delta", "ci95", "mde95", "p_gt_0", "reading", "status")},
                             "folds": rec}
            doc["sensitivities"]["mc1_listwise"] = {
                "what": "MC-1 with the listwise pair weighting; a sensitivity, selected nowhere",
                "frames": sens}
    # --- the family ---------------------------------------------------------------
    pvals = {}
    for arm in ARMS:
        ps = []
        for fid in FRAMES:
            leg = doc["arms"][arm]["frames"][fid]["deltas"][ADMISSION_LEG]["spearman"]
            ps.append(None if leg.get("p_gt_0") is None else 1.0 - float(leg["p_gt_0"]))
        pvals[arm] = None if any(p is None for p in ps) else max(ps)
    holm = holm_adjust(pvals, m=HOLM_M, alpha=ALPHA)
    doc["holm"] = {"m": HOLM_M, "alpha": ALPHA, "leg": f"{ADMISSION_LEG}.spearman (within)",
                   "p_rule": "the larger of the two frames' bootstrap shares of draws at or below zero",
                   "by_arm": holm}
    for arm in ARMS:
        a_doc = doc["arms"][arm]
        per_frame = {fid: admission_inputs(a_doc["frames"][fid]) for fid in FRAMES}
        v = admission_verdict(arm, per_frame, holm.get(arm))
        a_doc.update(holm=holm.get(arm), admitted=v["admitted"], adoptable=v["adoptable"],
                     clauses=v["clauses"], reason=v["reason"], admission_inputs=per_frame)
        for fid in FRAMES:
            a_doc["frames"][fid]["verdict"] = v["reason"]
            prim = a_doc["frames"][fid]["deltas"][ADMISSION_LEG]["spearman"]
            tag = f"MC-SCREEN:{fid}.{arm}_vs_v2"
            doc["probes"][tag] = {
                "tag": tag, "verdict": probe_verdict(v), "ci95": prim.get("ci95"),
                "delta": prim.get("delta"), "mde95": prim.get("mde95"),
                "twin_delta": ((a_doc["frames"][fid]["twin"] or {}).get("within") or {}).get("delta"),
                "p_perm": (a_doc["frames"][fid]["permutation_null"] or {}).get("p"),
                "holm_p": (holm.get(arm) or {}).get("holm_p"),
                "reason": (f"n {a_doc['frames'][fid]['n']}; within delta vs V2 {prim.get('delta')}, "
                           f"vs consensus {a_doc['frames'][fid]['deltas']['arm_vs_prospx_consensus']['spearman'].get('delta')}; "
                           f"{v['reason']}")}
        if v["admitted"]:
            doc["admitted"].append(arm)
        if v["adoptable"]:
            doc["adoptable"].append(arm)
        log(f"{ARM_LABEL[arm]}: {v['reason']}")
    doc["n_probes"] = len(doc["probes"])
    # --- outside the family ---------------------------------------------------------
    if with_rank_weight:
        try:
            rw = {s: rank_consistent_weights(s, inputs["rule_sources"][s],
                                             absent_ok=inputs.get("absent_ok")) for s in F.SIDES}
            weights2 = {s: {"w_skill": rw[s]["weights"]["w_skill"],
                            "w_time": rw[s]["weights"]["w_time"]} for s in F.SIDES}
            frames_rw = {}
            for fid in FRAMES:
                o = rescore_v2(inputs, fid, weights2)
                d = within_delta_only(rows_with_arm(inputs, fid, o), ARM_KEY, V2_KEY, B=B, seed=SEED)
                frames_rw[fid] = {k: d.get(k) for k in ("delta", "ci95", "mde95", "p_gt_0", "reading", "status")}
            doc["sensitivities"]["rank_consistent_weight"] = {
                "what": ("V2 re-scored at the rank-consistent combiner weights against V2 at the "
                         "DS-08 weights (lane C E3-Q2 = A); a sensitivity, selected nowhere, "
                         "outside the Holm family; no refit, the fold heads' e_skill and e_time "
                         "re-weighted"),
                "ds08_weights": inputs["weights"], "rank_consistent_weights": weights2,
                "derivation": {s: {k: v for k, v in rw[s].items() if k != "curves"} for s in F.SIDES},
                "curves": {s: rw[s]["curves"] for s in F.SIDES},
                "frames": frames_rw}
        except Exception as exc:                                  # noqa: BLE001
            doc["sensitivities"]["rank_consistent_weight"] = {
                "status": "not derived", "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-1500:]}
            log(f"rank-consistent weight sensitivity failed: {exc}")
    if with_mc5 and not exploratory:
        try:
            doc["mc5"] = mc5_block(log=log)
        except Exception as exc:                                  # noqa: BLE001
            doc["mc5"] = {"arm": "MC-5", "status": "not derived",
                          "error": f"{type(exc).__name__}: {exc}",
                          "traceback": traceback.format_exc()[-1500:]}
            log(f"MC-5 block failed: {exc}")
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def write_doc(doc: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if text.find('"band_weights"') > text.find('"arms"'):
        raise RuntimeError("the band weights must be written before the arms")
    for ch in (chr(0x2014), chr(0x2013)):
        if ch in text:
            raise RuntimeError("an em-dash or en-dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)


def summary_lines(doc: dict) -> list[str]:
    out = []
    for arm, a in doc["arms"].items():
        for fid in FRAMES:
            f = a["frames"][fid]
            w = f["deltas"][ADMISSION_LEG]["spearman"]
            c = f["deltas"]["arm_vs_prospx_consensus"]["spearman"]
            out.append(f"{a['arm']:6s} {fid}: n {f['n']}; vs V2 {w.get('delta')} CI {w.get('ci95')} "
                       f"mde95 {w.get('mde95')}; vs consensus {c.get('delta')} CI {c.get('ci95')}; "
                       f"twin {f['twin']['within'].get('delta')}; folds same sign "
                       f"{f['fold_sign_agreement']['same_sign']}/{f['fold_sign_agreement']['of']}; "
                       f"perm p {f['permutation_null'].get('p')}")
        h = a.get("holm") or {}
        out.append(f"{a['arm']:6s} Holm p {h.get('p')} holm_p {h.get('holm_p')} survives "
                   f"{h.get('survives_holm')}; {a['reason']}")
    out.append(f"admitted: {doc['admitted'] or 'none'}; adoptable: {doc['adoptable'] or 'none'}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(OUT_PATH),
                    help="artifact path (default data/efv_v2_model_class_screen.json); "
                         "outside data/ the run is exploratory and writes nothing else")
    ap.add_argument("--check", action="store_true",
                    help="build the frames, print counts and the base parity; no arm scored")
    ap.add_argument("--exploratory", action="store_true",
                    help="form no claim and write nothing else; refused under data/")
    ap.add_argument("--B", type=int, default=B_DEFAULT,
                    help="bootstrap draws (a non-default value is refused under data/)")
    ap.add_argument("--n-perm", type=int, default=N_PERM,
                    help="permutation draws (a non-default value is refused under data/)")
    ap.add_argument("--no-ledger", action="store_true",
                    help="under data/: write the artifact but regenerate no ledger")
    a = ap.parse_args(argv)
    out = Path(a.out)
    under = _is_under_data(out)
    exploratory = bool(a.exploratory) or not under

    def log(msg):
        print(msg, flush=True)
    if under and not a.check and out.exists():
        log(f"refused: {out} exists; the screen is spent (one run on these frames, "
            "MODEL_CLASS_SCREEN.md s8)")
        return 2
    if under and (a.exploratory or a.B != B_DEFAULT or a.n_perm != N_PERM):
        log("refused: an exploratory or reduced run may not write under data/")
        return 2
    if not exploratory and L.provider() != FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {FROZEN_PROVIDER!r}")
        return 2
    inputs = build_inputs(log=log)
    if a.check:
        ds16 = _ds16_block()
        log(json.dumps({"check": True, "guards": inputs["guards"], "counts": counts(inputs),
                        "label": _label(), "weights": inputs["weights"],
                        "band_weights": {s: inputs["band_weights"][s]["weights"] for s in F.SIDES},
                        "band_weights_years_read": {s: inputs["band_weights"][s]["years_read"]
                                                    for s in F.SIDES},
                        "base_parity": base_parity(inputs, ds16)}, indent=1, default=str))
        return 0
    doc = run(inputs, B=a.B, n_perm=a.n_perm, exploratory=exploratory, log=log)
    write_doc(doc, out)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    for line in summary_lines(doc):
        log(line)
    if under and not a.no_ledger:
        import efv_arm_ledger
        import efv_progress
        efv_arm_ledger.main([])
        log(efv_progress.summary_line(efv_progress.update(trigger="efv_change")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

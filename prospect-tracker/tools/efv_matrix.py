# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV scoreboard matrix: FRAME x CELL x COMPARATOR x STATISTIC (EFV3_D2).

Registration: docs/efv-v2/EFV_V2_GATE.md s8.1 to s8.4 (EFV3_D5, 2026-10-02), from
SP/efv3/EFV3_PLAN.md s6 and SP/efv3/LANE_D.md s3. The owner's ask was the widest
resolvable margin over consensus "across AUC/Spearman scores for overall and as many
specific categories as possible"; this artifact is the honest reading of every category
the program may read, each with its own measured floor and one word from a closed
vocabulary. It is an evaluation surface: it selects nothing, re-runs no closed arm,
moves no served number, and no sentence outside the matrix grid reads a key of it.

FRAMES
    vm2            the served vintage-matched, timing-pinned rows exactly as
                   source_backtest.run_source_backtest builds them (_vm2_frame_rows), eFV
                   from the served object (efv_v2_serve.served_oos_scores(timing_pin=True)
                   when V2 serves, else efv_model.oos_grades(timing_pin=True)); the
                   overall cell IS accuracy.head_to_head_verdict and is COPIED, with a
                   parity receipt that recomputes the consensus Spearman interval through
                   source_backtest._paired_delta_ci on the same rows.
    lv_dev         list vintages 2017 to 2019 through tools/efv_v2_dev_read.v2_lv_dev (the
                   DS-16 path: V2 fitted per vintage on earlier list vintages, every frame
                   player excluded); development, spent, every cell reads DEVELOPMENT.
    bust_inclusive the vm2 rows plus the busts at their last list year
                   (source_backtest._bust_frame, the claim instruments' row rule); a
                   secondary panel carrying the AUC tabs only.
    lv_res, vm_pros reserved (R-LV 2020 and 2021; R-VM 2025 and later). NEVER scored here:
                   their cells are copied from data/efv_v2_gate.json once the look runner
                   (EFV3_D6) has written them, and read RESERVED_PENDING until then.

CELLS   efv_strata.DIMENSIONS only (side, position family, level at list, age band, list
        year, archetype, source disagreement) plus the overall cell. No dimension by
        consensus-FV level, eFV grade, any rater's FV, tier, top-N rank, bonus band or
        outcome (docs/PROSPECT_ANCHOR_GATE.md; the ledger's _FV_CELL regex is checked
        against every key). An undeclared "unknown" (position family, level at list,
        source disagreement) is counted, never scored (default D5-a).

STATISTIC PER CELL (LANE_D.md s3.2)
    primary   efv_v2_stat.paired_delta(statistic="within") where at least 2 (side,
              vintage) groups of 20 or more rows survive inside the cell, else
              statistic="pooled" after the identical output map, and the cell carries
              "pooled (within degenerate: k groups)". The pooled statistic is always
              beside it.
    map       efv_v2_model.output_map inside each (side, vintage) group of the WHOLE
              frame, computed once per frame per comparison and never refit per cell
              (paired_delta premapped=True): a cell is a subset, the map is the frame's.
    auc       after the map, at career WAR 1, 2, 3 (CONTRIBUTOR_WAR, the registered veto
              leg) and 4 on vm2 and bust_inclusive; at W3 1.0, w* (w_star_dev), 2 and 4
              and R3 reached on lv_dev; through source_backtest._paired_delta_ci with the
              flag rebuilt per threshold; at least 10 positives and 10 negatives.
    l6        the six-season exposure-matched label (efv_dataset._label_6yr, the
              fully resolved cut and the censored cut) as spearman_l6_* on vm2.
    mae       eFV minus the comparator of the mapped score priced through ONE
              efv_model._fit_ols_fv line per frame (consensus FV to the frame's label on
              the frame's rows); diagnostic, no verdict weight, no reading word.
    interval  paired, player-clustered, B 2000, seed 20260906, E_cond (scores fixed,
              players resampled), mde95 = 1.645 x sd, p_one_sided = P(Z > |delta| / sd).
              The floor is the cell floor (lane D E3-Q4 = A: 40 rows, source_backtest
              .ARCH_MIN_N) with FLOOR_CLUSTERS players; the same resampler, B and seed as
              the claim instruments, which keep their own 60-row gate.

FAMILIES, written into the artifact BEFORE any cell is read (a `families` block precedes
`cells`): P = the overall cell versus consensus (copied from head_to_head_verdict on vm2);
I = the FP3-3 six-cell family (copied from head_to_head_vs_sources on vm2); S = every
stratum cell with n >= 40 versus consensus on its primary statistic, ONE family per frame,
source_backtest._holm_family at alpha 0.05. AUC legs and industry comparators on strata
carry intervals and the uncorrected floor line only, "uncorrected, not a claim"; AUC may
veto and never credit; MAE carries no verdict weight.

READINGS (closed vocabulary, LANE_D.md s3.4), applied in this order from the cell's own
numbers: NOT_SCORED (no rows for the comparator); UNPOWERED (n under the floor, the
interval not derived, or an AUC leg with under 10 positives or negatives); AHEAD or BEHIND
(survives the family, by the sign of delta); UNPOWERED (mde95 above 2 x 0.02); EQUIVALENT
(CI95 inside plus or minus 0.02); FLAGGED_UNCORRECTED (|delta| >= 1.645 sd, did not survive
the family); UNRESOLVED. On a development frame the four interval words read DEVELOPMENT
(the word they would carry is kept beside, never printed as a finding). A reserved cell
reads RESERVED_PENDING. Under lane D E3-Q2 = A a vm2 stratum cell may carry AHEAD or
BEHIND inside the matrix only. Ties are ties: UNRESOLVED and EQUIVALENT are different words.

OUTPUT  data/efv_matrix_eval.json (compare-before-write on content excluding generated_at
and elapsed_s, the scoreboard's idiom) and an append-only .cache/efv_matrix/history.jsonl
(one line per changed state). The label block stamps war_source.DEFAULT_PROVIDER and
RESOLVED_THROUGH: a pre-epoch run is on the eWAR v2 label and a run after the fWAR label
epoch's step Z is a new artifact. This tool appends nothing to data/efv_progress.json
(EFV3_D3 copies the summary into the ledger).

Run:  python tools/efv_matrix.py            (all development frames; 10 to 30 minutes)
      python tools/efv_matrix.py --frames vm2 --B 200 --no-write   (a quick look)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import efv_labels as L          # noqa: E402
import efv_strata as ST         # noqa: E402
import efv_v2_stat as S         # noqa: E402
import efv_vintage_frame as F   # noqa: E402
import source_backtest as SB    # noqa: E402
from efv_model import _fit_ols_fv, _pred_ols  # noqa: E402

OUT_PATH = ROOT / "data" / "efv_matrix_eval.json"
HISTORY_PATH = ROOT / ".cache" / "efv_matrix" / "history.jsonl"
SB_PATH = ROOT / "data" / "source_backtest.json"
GATE_JSON_PATH = ROOT / "data" / "efv_v2_gate.json"
MODEL_ID = "efv_matrix"
REGISTRATION = ("docs/efv-v2/EFV_V2_GATE.md s8.1 to s8.4 (EFV3_D5, 2026-10-02); "
                "SP/efv3/EFV3_PLAN.md s6; SP/efv3/LANE_D.md s3")
REGEN_CMD = "python tools/efv_matrix.py"

CONS = SB.CONSENSUS_KEY
EFV = "efv"
COMPARATORS = (CONS, "mlb_pipeline", "fangraphs", "baseballamerica", "espn")
COMPARATOR_LABELS = {CONS: "PROSPX consensus", "mlb_pipeline": "MLB Pipeline",
                     "fangraphs": "FanGraphs", "baseballamerica": "Baseball America",
                     "espn": "ESPN"}
CLAIM_COMPARATOR = CONS

#: Lane D E3-Q4 = A: the cell floor in rows (source_backtest.ARCH_MIN_N), B 2000, E_cond,
#: seed 20260906. FLOOR_CLUSTERS is the matrix's own player floor beneath it (default
#: MX-b): a 40-row cell drawn from fewer players is not a cluster bootstrap.
FLOOR_ROWS = SB.ARCH_MIN_N
FLOOR_CLUSTERS = 20
AUC_MIN_POS = 10
MIN_GROUP_ROWS = S.MIN_GROUP_ROWS
EQUIVALENCE_MARGIN = 0.02
UNPOWERED_MDE95 = 2 * EQUIVALENCE_MARGIN
ALPHA = SB.H2H_HOLM_ALPHA
B_DEFAULT = SB._CLAIM_BOOT_B
SEED = SB._CLAIM_SEED
Z95 = SB._Z95

READINGS = ("AHEAD", "BEHIND", "EQUIVALENT", "UNRESOLVED", "FLAGGED_UNCORRECTED",
            "UNPOWERED", "NOT_SCORED", "DEVELOPMENT", "RESERVED_PENDING")
INTERVAL_WORDS = ("EQUIVALENT", "UNRESOLVED", "FLAGGED_UNCORRECTED")
PRINTED = {"AHEAD": "ahead", "BEHIND": "behind", "EQUIVALENT": "tie (within 0.02)",
           "UNRESOLVED": "no resolvable difference",
           "FLAGGED_UNCORRECTED": "clears its own floor, not the family",
           "UNPOWERED": "unpowered", "NOT_SCORED": "no rows",
           "DEVELOPMENT": "development, not a claim",
           "RESERVED_PENDING": "pre-registered, not read"}

FRAMES = ("vm2", "lv_dev", "bust_inclusive", "lv_res", "vm_pros")
DEVELOPMENT_FRAMES = frozenset({"lv_dev"})
RESERVED_FRAMES = frozenset({"lv_res", "vm_pros"})
FRAME_ROLE = {"vm2": "headline", "lv_dev": "development, spent",
              "bust_inclusive": "secondary panel, AUC tabs only",
              "lv_res": "reserved (R-LV)", "vm_pros": "reserved (R-VM)"}
FRAME_LABEL = {"vm2": "the vintage-matched, timing-pinned frame",
               "lv_dev": "the list-vintage development frame",
               "bust_inclusive": "the bust-inclusive panel",
               "lv_res": "the reserved list-vintage frame",
               "vm_pros": "the reserved prospective vintage-matched frame"}
VM_AUC_LEGS = (("auc_1", 1.0), ("auc_2", 2.0), ("auc_3", SB.CONTRIBUTOR_WAR), ("auc_4", 4.0))
VETO_LEG = {"vm2": "auc_3", "bust_inclusive": "auc_3", "lv_dev": "auc_wstar"}
STAT_LABELS = {
    "spearman_within": S.STAT_LABEL["within"],
    "spearman_pooled": S.STAT_LABEL["pooled"],
    "spearman_l6_resolved": ("pooled Spearman after the identical output map against the "
                             "six-season label, fully resolved rows"),
    "spearman_l6_censored": ("pooled Spearman after the identical output map against the "
                             "six-season label, every labelled row (censored tail projected)"),
    "auc_1": "contributor AUC after the map at career WAR >= 1",
    "auc_2": "contributor AUC after the map at career WAR >= 2",
    "auc_3": "contributor AUC after the map at career WAR >= 3 (the registered veto leg)",
    "auc_4": "contributor AUC after the map at career WAR >= 4",
    "auc_w1": "AUC after the map at W3 >= 1.0",
    "auc_wstar": "AUC after the map at W3 >= w_star_dev (the registered veto leg)",
    "auc_w2": "AUC after the map at W3 >= 2",
    "auc_w4": "AUC after the map at W3 >= 4",
    "auc_r3": "AUC after the map on R3 (reached the majors within three seasons of V)",
    "mae": ("mean absolute error in WAR of the mapped score priced through one OLS(FV to "
            "label) line per frame; eFV minus the comparator; diagnostic"),
}
UNCORRECTED_NOTE = "uncorrected, not a claim"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _rnd(v, d: int):
    return round(float(v), d) if _isnum(v) else None


def _clean(o):
    """NaN and infinities become None so the artifact is strict JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (np.floating, np.integer)):
        return _clean(o.item())
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _sha_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


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


def label_block() -> dict:
    provider = L.provider()
    rt = L.resolved_through()
    pre = provider == "ewar_v2"
    return {"provider": provider, "resolved_through": rt, "id": _label_id(),
            "epoch": ("pre-epoch run on the eWAR v2 label; a run after the fWAR label "
                      "epoch's step Z entry (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md "
                      "part 9) is a new artifact" if pre else
                      f"run on the {provider} label after the fWAR label epoch")}


# ---------------------------------------------------------------------------
# the reading rules (one place; the test recomputes every reading through them)
# ---------------------------------------------------------------------------

def interval_reading(leg: dict | None) -> str:
    """The word an interval earns on its own (no family): NOT_SCORED, UNPOWERED,
    EQUIVALENT, FLAGGED_UNCORRECTED or UNRESOLVED."""
    if not leg or not leg.get("n"):
        return "NOT_SCORED"
    if leg.get("status") != "derived" or leg.get("unpowered_by_positives"):
        return "UNPOWERED"
    mde = leg.get("mde95")
    ci = leg.get("ci95")
    if not _isnum(mde) or not (isinstance(ci, list) and len(ci) == 2
                               and _isnum(ci[0]) and _isnum(ci[1])):
        return "UNPOWERED"
    if mde > UNPOWERED_MDE95:
        return "UNPOWERED"
    if ci[0] >= -EQUIVALENCE_MARGIN and ci[1] <= EQUIVALENCE_MARGIN:
        return "EQUIVALENT"
    if leg.get("clears_own_floor"):
        return "FLAGGED_UNCORRECTED"
    return "UNRESOLVED"


def family_reading(leg: dict | None, survives_family: bool) -> str:
    """The word a cell in a family earns: AHEAD or BEHIND when it survives, else the
    interval word. NOT_SCORED and the row-count UNPOWERED come first; the mde95
    UNPOWERED comes after a surviving word, as the vocabulary table orders them."""
    if not leg or not leg.get("n"):
        return "NOT_SCORED"
    if leg.get("status") != "derived" or leg.get("unpowered_by_positives"):
        return "UNPOWERED"
    if survives_family and _isnum(leg.get("delta")) and leg["delta"] != 0:
        return "AHEAD" if leg["delta"] > 0 else "BEHIND"
    return interval_reading(leg)


def frame_reading(word: str, development: bool) -> str:
    """On a development frame the four interval words read DEVELOPMENT."""
    if development and word in ("AHEAD", "BEHIND") + INTERVAL_WORDS:
        return "DEVELOPMENT"
    return word


# ---------------------------------------------------------------------------
# intervals (the registered resampler; one normalised leg shape)
# ---------------------------------------------------------------------------

def _base_leg(key: str, n: int, n_clusters: int, B: int, seed: int) -> dict:
    return {"statistic": key, "label": STAT_LABELS.get(key, key), "n": int(n),
            "n_clusters": int(n_clusters), "a": None, "b": None, "delta": None,
            "ci95": None, "sd": None, "mde95": None, "p_one_sided": None, "p_gt_0": None,
            "B": int(B), "B_used": 0, "seed": int(seed), "estimator": "E_cond",
            "resampling_unit": "player cluster", "status": None,
            "clears_own_floor": None, "floor_rows": FLOOR_ROWS,
            "floor_clusters": FLOOR_CLUSTERS}


def _finish(leg: dict) -> dict:
    if leg.get("status") == "derived" and _isnum(leg.get("delta")) and _isnum(leg.get("sd")):
        leg["p_one_sided"] = round(SB._p_one_sided(leg["delta"], leg["sd"]), 5)
        leg["clears_own_floor"] = bool(abs(leg["delta"]) >= leg["mde95"])
        if leg["delta"] == 0 and leg["sd"] == 0:
            # the two raters order every row of the cell identically (the served V2
            # serves the consensus ordering in its earliest decision years): the
            # interval has zero width and the tie is exact, not measured
            leg["identical_ordering"] = True
            leg["identical_note"] = ("eFV and the comparator order every row of this cell "
                                     "identically: a zero-width interval, an exact tie rather "
                                     "than a measured one")
    return leg


def _rank_agreement(rows: list[dict]) -> dict:
    """Per (side, vintage) group: the Spearman between eFV and consensus on the rows
    both graded, and whether the two orderings are identical (rho 1). A receipt, not
    a statistic against any outcome."""
    out: dict = {}
    for g in sorted({r["group"] for r in rows}):
        xs = [(r["grades"][EFV], r["grades"][CONS]) for r in rows
              if r["group"] == g and r["grades"].get(EFV) is not None
              and r["grades"].get(CONS) is not None]
        rho = SB._spearman([a for a, _ in xs], [b for _, b in xs]) if len(xs) > 2 else None
        out[g] = {"n": len(xs), "spearman_efv_vs_consensus": _rnd(rho, 4),
                  "rank_identical": bool(rho is not None and rho >= 1.0 - 1e-12)}
    return out


def _leg_within(key, keys, groups, y, a, b, cons, *, B, seed) -> dict:
    d = S.paired_delta(keys, groups, y, [False] * len(keys), a, b, cons,
                       statistic="within", B=B, seed=seed,
                       floor_rows=FLOOR_ROWS, floor_clusters=FLOOR_CLUSTERS)
    leg = _base_leg(key, d["n"], d["n_clusters"], B, seed)
    leg.update(a=d.get("a"), b=d.get("b"), delta=d.get("delta"),
               groups_kept=d.get("groups_kept"), rows_in_kept_groups=d.get("rows_in_kept_groups"),
               min_group_rows=d.get("min_group_rows"), status=d.get("status"))
    if d.get("status") == "derived":
        leg.update(ci95=d["ci95"], sd=d["sd"], mde95=d["mde95"], p_gt_0=d["p_gt_0"],
                   B_used=d["B_used"])
    return _finish(leg)


def _leg_pooled(key, keys, groups, y, ma, mb, *, B, seed) -> dict:
    d = S.paired_delta(keys, groups, y, [False] * len(keys), ma, mb, ma,
                       statistic="pooled", B=B, seed=seed, premapped=True,
                       floor_rows=FLOOR_ROWS, floor_clusters=FLOOR_CLUSTERS)
    leg = _base_leg(key, d["n"], d["n_clusters"], B, seed)
    leg.update(a=d.get("a"), b=d.get("b"), delta=d.get("delta"), status=d.get("status"),
               map="identical output map computed once on the whole frame")
    if d.get("status") == "derived":
        leg.update(ci95=d["ci95"], sd=d["sd"], mde95=d["mde95"], p_gt_0=d["p_gt_0"],
                   B_used=d["B_used"])
    return _finish(leg)


def _leg_ci(key, keys, ma, mb, target, *, metric, B, seed, label) -> dict:
    """AUC (target: bool flags) or Spearman (target: the label) after the frame map,
    through source_backtest._paired_delta_ci with the matrix floor."""
    rows = [{"key": k, "grades": {"efv": float(x), "comp": float(z)},
             "outcome": ({"contributor": bool(t)} if metric == "auc" else {"war": float(t)})}
            for k, x, z, t in zip(keys, ma, mb, target)]
    n = len(rows)
    n_clusters = len(set(keys))
    leg = _base_leg(key, n, n_clusters, B, seed)
    leg["map"] = "identical output map computed once on the whole frame"
    av = np.asarray(ma, dtype=np.float64)
    bv = np.asarray(mb, dtype=np.float64)
    if metric == "auc":
        pos = np.asarray(target, dtype=bool)
        n_pos, n_neg = int(pos.sum()), int(pos.size - pos.sum())
        leg.update(n_pos=n_pos, n_neg=n_neg, min_positives=AUC_MIN_POS)
        if n_pos < AUC_MIN_POS or n_neg < AUC_MIN_POS:
            leg.update(status="not derived: unpowered by positives", unpowered_by_positives=True)
            return leg
        pa, pb = SB._auc_np(np, av, pos), SB._auc_np(np, bv, pos)
    else:
        tv = np.asarray(target, dtype=np.float64)
        if n:
            yr = SB._ranks_np(np, tv)
            pa = SB._corr_np(np, SB._ranks_np(np, av), yr)
            pb = SB._corr_np(np, SB._ranks_np(np, bv), yr)
        else:
            pa = pb = None
    leg.update(a=_rnd(pa, 5), b=_rnd(pb, 5),
               delta=(None if pa is None or pb is None else round(float(pa - pb), 5)))
    if n < FLOOR_ROWS or n_clusters < FLOOR_CLUSTERS:
        leg["status"] = f"not derived: under the cell floor ({FLOOR_ROWS} rows / {FLOOR_CLUSTERS} players)"
        return leg
    fl = SB._paired_delta_ci(rows, "efv", "comp", metric, label=label, B=B, seed=seed,
                             min_rows=FLOOR_ROWS, min_clusters=FLOOR_CLUSTERS)
    if not fl.get("derived_in_run"):
        leg["status"] = fl.get("status") or "not derived"
        return leg
    leg.update(delta=fl["point_delta"], ci95=fl["ci95"], sd=fl["sd"], mde95=fl["mde95"],
               p_gt_0=fl["p_gt_0"], B_used=fl["B_used"], status="derived")
    return _finish(leg)


def _leg_mae(key, keys, pa, pb, y, *, B, seed) -> dict:
    """eFV minus the comparator in mean absolute error, same resampler, same seed."""
    n = len(keys)
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    n_clusters = len(ids)
    leg = _base_leg(key, n, n_clusters, B, seed)
    leg.update(role="diagnostic, no verdict weight", units="WAR")
    if not n:
        leg["status"] = "not derived: no rows"
        return leg
    ea = np.abs(np.asarray(pa, dtype=np.float64) - np.asarray(y, dtype=np.float64))
    eb = np.abs(np.asarray(pb, dtype=np.float64) - np.asarray(y, dtype=np.float64))
    a, b = float(ea.mean()), float(eb.mean())
    leg.update(a=round(a, 4), b=round(b, 4), delta=round(a - b, 5))
    if n < FLOOR_ROWS or n_clusters < FLOOR_CLUSTERS:
        leg["status"] = f"not derived: under the cell floor ({FLOOR_ROWS} rows / {FLOOR_CLUSTERS} players)"
        return leg
    order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(int(B)):
        idx = SB._cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        diffs.append(float(ea[idx].mean() - eb[idx].mean()))
    if len(diffs) < 50:
        leg["status"] = "not derived: too few usable draws"
        return leg
    d = np.asarray(diffs, dtype=np.float64)
    sd = float(d.std(ddof=1))
    q = np.quantile(d, [0.025, 0.975])
    leg.update(ci95=[round(float(q[0]), 4), round(float(q[1]), 4)], sd=round(sd, 5),
               mde95=round(Z95 * sd, 4), p_gt_0=round(float((d > 0).mean()), 4),
               B_used=len(diffs), status="derived")
    return _finish(leg)


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def guard_rows(frame_id: str, rows: list[dict], *, gate_sha: str | None = None) -> dict:
    """Raise efv_vintage_frame.ReservedFrameError for any reserved row without the
    committed gate sha: a list vintage in RESERVED_LV (through guard_score_request, the
    frame builder's own guard) or, on a vm frame, a debut year at or after
    R_VM_FIRST_DEBUT_YEAR. Also refuses the R-VM pin violations the dev read refuses."""
    kind = ST.frame_kind(frame_id)
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    vintages: set = set()
    for r in rows:
        v = r.get("vintage")
        if kind == "lv":
            if v is None:
                raise F.ReservedFrameError(f"{frame_id}: a row without a list vintage: {r.get('key')}")
            F.guard_score_request(int(v), gate_sha=gate_sha,
                                  purpose=f"scoreboard matrix cells on {frame_id}")
            vintages.add(int(v))
        else:
            dy = r.get("debut_year")
            if dy is None:
                dy = v
            if dy is not None and int(dy) >= F.R_VM_FIRST_DEBUT_YEAR \
                    and not F.gate_sha_committed(gate_sha):
                raise F.ReservedFrameError(
                    f"{frame_id}: row {r.get('key')} debuts in {dy}, an R-VM cohort; a "
                    f"matrix read of it needs the sha of the commit carrying {F.GATE_DOC}")
            if v is not None:
                vintages.add(int(v))
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins, "vintages_read": sorted(vintages),
            "gate_sha": gate_sha}


# ---------------------------------------------------------------------------
# rows: one internal shape for every frame
# ---------------------------------------------------------------------------
# {"key", "group", "side", "vintage", "debut_year", "war", "grades": {"efv", rater...},
#  "cells": {dimension: cell}, "l6": {...} | None, "r3": 0/1/None, receipts...}

def _matrix_blocks() -> tuple[dict, dict]:
    """(side_of, milb_of) from the two eFV matrices, first assignment wins (hit)."""
    import efv_dataset
    side_of: dict = {}
    milb_of: dict = {}
    for side in F.SIDES:
        try:
            raw = json.loads(efv_dataset.matrix_path(side).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in raw:
            k = r.get("player_key")
            if k is None or k in side_of:
                continue
            side_of[k] = side
            milb_of[k] = r.get("milb")
    return side_of, milb_of


def _records_by_key(*universes) -> dict:
    out: dict = {}
    for uni in universes:
        for p in uni or []:
            k = p.get("player_key")
            if not k:
                continue
            if k not in out or (p.get("acquisition") and not out[k].get("acquisition")):
                out[k] = p
    return out


def _extra_grades(rec: dict | None, year: int) -> dict:
    """Baseball America and ESPN in the same preseason window, when they graded the row."""
    if not rec:
        return {}
    inw, _ = SB._all_source_grades_by_year(rec)
    yr = inw.get(year) or {}
    return {s: float(yr[s]) for s in ("baseballamerica", "espn") if yr.get(s) is not None}


def rows_from_vm(frame_id: str, sb_rows: list[dict], side_of: dict, milb_of: dict,
                 records: dict, six_year: dict | None = None) -> tuple[list[dict], dict]:
    """The matrix rows of a vm frame from source_backtest's common rows (`grades["xfv"]`
    is the eFV score), with the strata assigned through efv_strata.assign."""
    rows, receipt = [], {"rows_in": len(sb_rows), "no_matrix_side": 0,
                         "baseballamerica_rows": 0, "espn_rows": 0}
    for c in sb_rows:
        k = c.get("key")
        side = side_of.get(k)
        if side not in ST.CELLS["side"]:
            receipt["no_matrix_side"] += 1
            continue
        rec = records.get(k) or {}
        year = int(c["year"])
        srow = {"year": year, "grades": c.get("grades") or {}, "side": side,
                "milb": milb_of.get(k), "position": rec.get("position"),
                "birth_date": rec.get("birth_date")}
        if "archetype" in c:
            srow["archetype"] = c.get("archetype")
        cells = ST.assign(frame_id, srow, rec)
        grades = {EFV: c["grades"]["xfv"]}
        for r_ in (CONS,) + tuple(SB.SCORED_SOURCES):
            if (c["grades"] or {}).get(r_) is not None:
                grades[r_] = float(c["grades"][r_])
        grades.update(_extra_grades(rec, year))
        receipt["baseballamerica_rows"] += int("baseballamerica" in grades)
        receipt["espn_rows"] += int("espn" in grades)
        out = c.get("outcome") or {}
        rows.append({"key": k, "group": f"{side}|{year}", "side": side, "vintage": year,
                     "debut_year": out.get("debut_year"),
                     "war": float(out.get("war") or 0.0), "debuted": bool(out.get("debuted")),
                     "grades": grades, "cells": cells,
                     "l6": (six_year or {}).get(k), "r3": None,
                     "milb_block": bool(milb_of.get(k))})
    return rows, receipt


def rows_from_lv(frame_id: str, dev_rows: list[dict]) -> tuple[list[dict], dict]:
    """The matrix rows of a list-vintage frame from tools/efv_v2_dev_read.v2_lv_dev
    (keep_frame_rows=True); eFV is V2's order index (grades["efv_v2"])."""
    import efv_v2_dev_read as DR
    rows, receipt = [], {"rows_in": len(dev_rows), "no_frame_row": 0,
                         "baseballamerica_rows": 0, "espn_rows": 0,
                         "reserved_vm_kept_w3_zero": 0}
    for c in dev_rows:
        fr = c.get("frame_row")
        lab = c.get("label") or {}
        if fr is None:
            receipt["no_frame_row"] += 1
            continue
        side = c["side"]
        V = int(c["vintage"])
        srow = {**fr, "side": side, "vintage": V}
        cells = ST.assign(frame_id, srow, None)
        grades = {EFV: c["grades"][DR.V2_KEY]}
        for r_ in (CONS,) + tuple(SB.SCORED_SOURCES):
            if (c["grades"] or {}).get(r_) is not None:
                grades[r_] = float(c["grades"][r_])
        fg = fr.get("grades") or {}
        for s_ in ("baseballamerica", "espn"):
            if fg.get(s_) is not None:
                grades[s_] = float(fg[s_])
        receipt["baseballamerica_rows"] += int("baseballamerica" in grades)
        receipt["espn_rows"] += int("espn" in grades)
        if lab.get("status") == "reserved_vm":
            receipt["reserved_vm_kept_w3_zero"] += 1
        r3 = lab.get("r3")
        rows.append({"key": c["key"], "group": c["group"], "side": side, "vintage": V,
                     "debut_year": None, "war": float(c["outcome"]["war"]),
                     "debuted": bool(lab.get("w3_debut")),
                     "contributor_wstar": bool(c["outcome"].get("contributor")),
                     "grades": grades, "cells": cells, "l6": None,
                     "r3": (None if r3 is None else int(float(r3) >= 1.0)),
                     "id_how": fr.get("id_how"), "label_status": lab.get("status"),
                     "milb_block": bool(fr.get("milb"))})
    return rows, receipt


# ---------------------------------------------------------------------------
# frame inputs (the served path and the development read)
# ---------------------------------------------------------------------------

def vm2_inputs(data_dir: Path = SB.DATA_DIR) -> dict:
    """The vm2 rows exactly as run_source_backtest builds them (common rows, the served
    scores, _attach_raw_efv, _vm2_frame_rows), plus the bust rows and the six-season
    label map. The same dict run_source_backtest(return_rows=True) hands back."""
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    universe = SB._load_universe(data_dir)
    years = SB._resolved_years(universe, date.today().year)
    if any(y >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm window reaches R-VM: {years}")
    raters = list(SB.SCORED_SOURCES) + [CONS]
    common_by_year: dict = {y: [] for y in years}
    for p in universe:
        out = SB._outcome(p)
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if g and all(r in g for r in raters):
                common_by_year[y].append({"key": p.get("player_key"),
                                          "name": p.get("player_name"), "year": y,
                                          "grades": {r: g[r] for r in raters},
                                          "outcome": out, "archetype": SB._archetype(p)})
    try:
        import efv_v2_serve as _v2s
        v2_on = _v2s.enabled()
    except Exception:                                         # noqa: BLE001
        _v2s, v2_on = None, False
    receipts: dict = {}
    if v2_on:
        xfv_oos = _v2s.served_oos_scores()
        xfv_oos_vm2 = _v2s.served_oos_scores(timing_pin=True, receipts=receipts)
        scored = {"model_id": _v2s.SERVED_MODEL_ID, "code": "efv_v2_serve.py"}
    else:
        from efv_model import oos_grades
        xfv_oos = {**oos_grades("hit"), **oos_grades("pit")}
        xfv_oos_vm2 = {}
        for sd in F.SIDES:
            xfv_oos_vm2.update(oos_grades(sd, timing_pin=True, receipts=receipts))
        scored = {"model_id": "efv_v1", "code": "efv_model.py"}
    rows_x, raw_vm1, _n = SB._attach_raw_efv(common_by_year, years, xfv_oos)

    def _is_vm(c):
        dy = (c.get("outcome") or {}).get("debut_year")
        return dy is not None and (c.get("year") or 0) == dy

    vm2_rows, timing = SB._vm2_frame_rows(rows_x, raw_vm1, xfv_oos_vm2, receipts, _is_vm)
    six, six_rec = SB._six_year_label_map(universe)
    busts, excl = SB._load_bust_universe(data_dir, universe)
    bust_rows, bust_rec = SB._bust_frame(busts, years, raters, dict(xfv_oos))
    bust_rec["excluded_by_screen"] = len(excl)
    side_of, _ = _matrix_blocks()
    return {"years": years, "vm2_rows": vm2_rows, "vm2_timing": timing, "side_of": side_of,
            "universe": universe, "xfv_oos": xfv_oos, "xfv_oos_vm2": xfv_oos_vm2,
            "bust_rows": bust_rows, "bust_records": busts, "bust_receipt": bust_rec,
            "six_year": six, "six_year_receipt": six_rec, "efv_scored_object": scored}


def lv_inputs() -> tuple[list[dict], dict]:
    import efv_v2_dev_read as DR
    import efv_v2_model as H
    for v in F.DEV_VINTAGES:
        F.guard_score_request(v, purpose="scoreboard matrix, development read")
    weights = H.load_weights()
    rows, meta = DR.v2_lv_dev(weights, keep_frame_rows=True)
    return rows, meta


# ---------------------------------------------------------------------------
# scoring one frame
# ---------------------------------------------------------------------------

def _cell_index(rows: list[dict]) -> list[tuple[str, str, list[int], bool]]:
    """[(dimension, cell, row indices, declared)] in registered order: the overall cell
    first, then every dimension's declared cells in CELLS order, then any observed
    undeclared value (always "unknown"), which is counted and never scored."""
    out = [("overall", "all", list(range(len(rows))), True)]
    for dim in ST.DIMENSIONS:
        seen: dict = {}
        for i, r in enumerate(rows):
            v = (r.get("cells") or {}).get(dim)
            if v is None:
                continue
            seen.setdefault(v, []).append(i)
        declared = [c for c in ST.CELLS[dim] if c in seen]
        if dim == "list_year":
            declared = sorted(declared)
        for c in declared:
            out.append((dim, c, seen[c], True))
        for c in sorted(v for v in seen if v not in ST.CELLS[dim]):
            out.append((dim, c, seen[c], False))
    return out


def _counts(rows: list[dict], idx: list[int]) -> dict:
    hit = sum(1 for i in idx if rows[i]["side"] == "hit")
    return {"n": len(idx), "n_hit": hit, "n_pit": len(idx) - hit,
            "n_players": len({rows[i]["key"] for i in idx})}


def _kept_groups(rows: list[dict], idx: list[int]) -> list[str]:
    codes = np.asarray([rows[i]["group"] for i in idx])
    return [str(u) for u in S.kept_groups(codes, MIN_GROUP_ROWS)] if idx else []


def _primary_name(k_groups: int) -> str:
    return "within" if k_groups >= 2 else f"pooled (within degenerate: {k_groups} groups)"


def score_frame(frame_id: str, rows: list[dict], *, B: int = B_DEFAULT, seed: int = SEED,
                statistics: tuple[str, ...] = ("spearman", "auc", "mae"),
                auc_legs=None, copied: dict | None = None, parity_rows=None,
                gate_sha: str | None = None, receipts: dict | None = None,
                extra: dict | None = None) -> dict:
    """One frame block: families first, then cells, the Holm families, the summary.

    rows: the internal row shape (rows_from_vm / rows_from_lv). statistics: which tab
    groups to compute ("spearman" = within, pooled and, on rows carrying l6, the
    six-season legs; "auc"; "mae"). auc_legs: [(key, flag function on a row)]; the vm
    default thresholds career WAR. copied: the served accuracy block (vm2), whose
    head_to_head_verdict and head_to_head_vs_sources are copied into families P and I.
    parity_rows: source_backtest's own vm2 rows, for the parity receipt."""
    t0 = time.time()
    development = frame_id in DEVELOPMENT_FRAMES
    guard = guard_rows(frame_id, rows, gate_sha=gate_sha)
    n = len(rows)
    cells_idx = _cell_index(rows)
    do_sp = "spearman" in statistics
    do_auc = "auc" in statistics
    do_mae = "mae" in statistics
    has_l6 = do_sp and any(r.get("l6") for r in rows)
    if auc_legs is None:
        auc_legs = [(k, (lambda thr: (lambda r: r["war"] >= thr))(thr)) for k, thr in VM_AUC_LEGS]
    auc_keys = [k for k, _f in auc_legs] if do_auc else []
    comparators = [c for c in COMPARATORS
                   if any(r["grades"].get(c) is not None for r in rows)]
    for c in COMPARATORS:
        if c not in comparators:
            comparators.append(c)       # printed "no rows"

    # ---- the frame map, once per comparison ---------------------------------
    cmp_idx: dict = {}
    mapped: dict = {}
    for comp in comparators:
        ix = [i for i, r in enumerate(rows)
              if r["grades"].get(EFV) is not None and r["grades"].get(comp) is not None
              and r["grades"].get(CONS) is not None]
        cmp_idx[comp] = ix
        if not ix:
            mapped[comp] = {}
            continue
        groups = [rows[i]["group"] for i in ix]
        cons = [rows[i]["grades"][CONS] for i in ix]
        ma = S.map_scores([rows[i]["grades"][EFV] for i in ix], groups, cons)
        mb = S.map_scores([rows[i]["grades"][comp] for i in ix], groups, cons)
        mapped[comp] = {i: (float(ma[j]), float(mb[j])) for j, i in enumerate(ix)}

    # ---- the pricing line for the MAE diagnostic (one per frame) --------------
    ols = None
    if do_mae:
        train = [{"fv": r["grades"][CONS], "target": r["war"]} for r in rows
                 if r["grades"].get(CONS) is not None]
        ols = _fit_ols_fv(train)

    # ---- families, BEFORE any cell is read -----------------------------------
    primary_by_cell: dict = {}
    fam_s_cells = []
    for dim, cell, idx, declared in cells_idx:
        cnt = _counts(rows, idx)
        ci = [i for i in idx if i in mapped.get(CLAIM_COMPARATOR, {})]
        kg = _kept_groups(rows, ci)
        primary_by_cell[(dim, cell)] = (_primary_name(len(kg)), kg)
        if dim == "overall" or not declared:
            continue
        if cnt["n"] >= n:
            continue                                     # D5-c: the overall cell
        if len(ci) >= FLOOR_ROWS and do_sp:
            fam_s_cells.append({"dimension": dim, "cell": cell, "n": len(ci),
                                "n_hit": cnt["n_hit"], "n_pit": cnt["n_pit"],
                                "primary_statistic": _primary_name(len(kg)),
                                "floor_rows": FLOOR_ROWS, "floor_clusters": FLOOR_CLUSTERS})
    served = copied or {}
    hv = served.get("head_to_head_verdict") or {}
    vs = served.get("head_to_head_vs_sources") or {}
    families: dict = {
        "written_before_cells": True,
        "P": {"what": "the claim: the overall cell, eFV versus PROSPX consensus, the registered primary",
              "comparator": CLAIM_COMPARATOR, "k": 1,
              "source": ("accuracy.head_to_head_verdict (copied, never recomputed)" if hv
                         else "computed here on the frame's primary statistic"
                              + (" (development, not a claim)" if development else "")),
              "copied": ({k: hv.get(k) for k in ("basis", "n", "delta", "ci95", "mde95",
                                                  "mde95_estimator", "resolvable", "verdict",
                                                  "xfv_spearman", "consensus_spearman")}
                         if hv else None)},
        "I": {"what": "the industry: eFV against each scored rater on the overall cell",
              "source": ("accuracy.head_to_head_vs_sources (FP3-3, copied)" if vs else
                         "computed here: MLB Pipeline and FanGraphs on the primary statistic "
                         "and the veto AUC leg" + (" (development, not a claim)" if development else "")),
              "k": (vs.get("holm") or {}).get("k") if vs else 4,
              "alpha": ALPHA,
              "copied": ({"family": (vs.get("holm") or {}).get("family"),
                          "n_verdicts": (vs.get("holm") or {}).get("n_verdicts"),
                          "sources": {r_: {m_: {k_: (leg or {}).get(k_) for k_ in
                                                 ("delta", "ci95", "sd", "mde95", "holm",
                                                  "verdict", "reading", "n")}
                                           for m_, leg in (src or {}).items()
                                           if isinstance(leg, dict)}
                                      for r_, src in (vs.get("sources") or {}).items()}}
                         if vs else None)},
        "S": {"what": ("the strata: every stratum cell at or above the floor, eFV versus "
                       "PROSPX consensus on the cell's declared primary statistic, ONE "
                       "family per frame, Holm step-down one-sided on |delta| / sd"),
              "comparator": CLAIM_COMPARATOR, "k": len(fam_s_cells), "alpha": ALPHA,
              "floor_rows": FLOOR_ROWS, "floor_clusters": FLOOR_CLUSTERS,
              "procedure": "source_backtest._holm_family",
              "expected_false_flags_by_construction": round(ALPHA * len(fam_s_cells), 2),
              "cells": fam_s_cells,
              "note": ("AUC legs and industry comparators on strata are in no family: "
                       "intervals and the uncorrected floor line only, "
                       + UNCORRECTED_NOTE)},
    }
    if not do_sp:
        families["S"].update(k=0, cells=[], expected_false_flags_by_construction=0.0,
                             note="no Family S on this panel (AUC tabs only, no primary statistic)")
        families["P"]["source"] = "no Family P on this panel (AUC tabs only)"
        families["I"]["source"] = "no Family I on this panel (AUC tabs only)"
        families["I"]["k"] = 0

    # ---- cells ------------------------------------------------------------------
    cells: dict = {}
    for dim, cell, idx, declared in cells_idx:
        cnt = _counts(rows, idx)
        prim_name, kg = primary_by_cell[(dim, cell)]
        is_overall = dim == "overall"
        block = {**cnt, "declared": declared,
                 "scored": bool(declared and len(idx) >= FLOOR_ROWS and (is_overall or cnt["n"] < n)),
                 "in_family_s": any(f["dimension"] == dim and f["cell"] == cell for f in fam_s_cells),
                 "primary_statistic": prim_name, "groups_kept": kg,
                 "comparators": {}}
        if dim != "overall" and declared and cnt["n"] >= n:
            block["note"] = "equal to the whole frame: the overall cell, not a stratum (D5-c)"
        if not declared:
            block["note"] = "undeclared cell: counted, never scored (D5-a)"
        for comp in comparators:
            ci = [i for i in idx if i in mapped.get(comp, {})]
            cb: dict = {"label": COMPARATOR_LABELS.get(comp, comp), "n": len(ci),
                        "n_players": len({rows[i]["key"] for i in ci}),
                        "claim": bool(comp == CLAIM_COMPARATOR
                                      and (block["in_family_s"] or is_overall)),
                        "statistics": {}}
            if not ci:
                cb["reading"] = "NOT_SCORED"
                cb["printed"] = PRINTED["NOT_SCORED"]
                block["comparators"][comp] = cb
                continue
            if not block["scored"] or len(ci) < FLOOR_ROWS:
                cb["reading"] = "UNPOWERED"
                cb["printed"] = f"unpowered (n {len(ci)})"
                cb["note"] = "under the cell floor: no interval"
                block["comparators"][comp] = cb
                continue
            keys = [rows[i]["key"] for i in ci]
            groups = [rows[i]["group"] for i in ci]
            y = [rows[i]["war"] for i in ci]
            ma = [mapped[comp][i][0] for i in ci]
            mb = [mapped[comp][i][1] for i in ci]
            st: dict = {}
            if do_sp:
                a_raw = [rows[i]["grades"][EFV] for i in ci]
                b_raw = [rows[i]["grades"][comp] for i in ci]
                cons = [rows[i]["grades"][CONS] for i in ci]
                kg_c = _kept_groups(rows, ci)
                if kg_c:
                    st["spearman_within"] = _leg_within("spearman_within", keys, groups, y,
                                                        a_raw, b_raw, cons, B=B, seed=seed)
                    st["spearman_within"]["degenerate"] = len(kg_c) < 2
                else:
                    st["spearman_within"] = _base_leg("spearman_within", len(ci), len(set(keys)), B, seed)
                    st["spearman_within"].update(
                        status=f"not derived: no (side, vintage) group of {MIN_GROUP_ROWS} rows",
                        degenerate=True, groups_kept=[])
                st["spearman_pooled"] = _leg_pooled("spearman_pooled", keys, groups, y, ma, mb,
                                                    B=B, seed=seed)
                if has_l6:
                    for tag, field, flag in (("spearman_l6_resolved", "resolved", True),
                                             ("spearman_l6_censored", "censored", False)):
                        sub = [j for j, i in enumerate(ci) if rows[i].get("l6")
                               and (not flag or not rows[i]["l6"].get("censored_flag"))]
                        leg = _leg_ci(tag, [keys[j] for j in sub], [ma[j] for j in sub],
                                      [mb[j] for j in sub],
                                      [rows[ci[j]]["l6"][field] for j in sub],
                                      metric="spearman", B=B, seed=seed,
                                      label=f"{frame_id}.{dim}.{cell}.{comp}.{tag}")
                        leg["n_censored"] = sum(1 for j in sub if rows[ci[j]]["l6"].get("censored_flag"))
                        st[tag] = leg
            if do_auc:
                for key, flag in auc_legs:
                    tgt = [bool(flag(rows[i])) for i in ci]
                    leg = _leg_ci(key, keys, ma, mb, tgt, metric="auc", B=B, seed=seed,
                                  label=f"{frame_id}.{dim}.{cell}.{comp}.{key}")
                    leg["veto_leg"] = key == VETO_LEG.get(frame_id)
                    st[key] = leg
            if do_mae and ols:
                pa = [max(0.0, _pred_ols(ols, v)) for v in ma]
                pb = [max(0.0, _pred_ols(ols, v)) for v in mb]
                st["mae"] = _leg_mae("mae", keys, pa, pb, y, B=B, seed=seed)
            for key, leg in st.items():
                if key == "mae":
                    continue
                leg["reading"] = interval_reading(leg)
                leg["note"] = UNCORRECTED_NOTE
            cb["statistics"] = st
            # the cell's primary leg versus this comparator
            if do_sp:
                pk = "spearman_within" if prim_name == "within" else "spearman_pooled"
                cb["primary"] = {"statistic": prim_name, "leg": pk}
            elif do_auc:
                pk = VETO_LEG.get(frame_id, auc_keys[0] if auc_keys else None)
                cb["primary"] = {"statistic": f"{pk} (secondary panel; AUC tabs only)", "leg": pk}
            else:
                pk = None
                cb["primary"] = None
            word = interval_reading(st.get(pk)) if pk else "NOT_SCORED"
            cb["reading"] = frame_reading(word, development)
            cb["reading_if_claim_frame"] = word if development else None
            block["comparators"][comp] = cb
        cells.setdefault(dim, {})[cell] = block

    # ---- Family S: Holm over the stratum cells, consensus, primary -----------------
    holm_s = None
    if do_sp and fam_s_cells:
        fam_in = []
        for f in fam_s_cells:
            cb = cells[f["dimension"]][f["cell"]]["comparators"].get(CLAIM_COMPARATOR) or {}
            leg = (cb.get("statistics") or {}).get((cb.get("primary") or {}).get("leg")) or {}
            ok = leg.get("status") == "derived"
            fam_in.append({"key": f"{f['dimension']}:{f['cell']}",
                           "delta": leg.get("delta") if ok else None,
                           "sd": leg.get("sd") if ok else None})
        holm_s = SB._holm_family(fam_in, ALPHA)
        holm_s["family"] = "S"
        holm_s["rule"] = ("a stratum cell carries AHEAD or BEHIND only when it survives this "
                          "family" + (" (development frame: the word is kept beside, never printed)"
                                      if development else
                                      " (lane D E3-Q2 = A: inside the matrix grid only)"))
        by_key = {c["key"]: c for c in holm_s["cells"]}
        for f in fam_s_cells:
            cb = cells[f["dimension"]][f["cell"]]["comparators"][CLAIM_COMPARATOR]
            h = by_key[f"{f['dimension']}:{f['cell']}"]
            leg = cb["statistics"].get(cb["primary"]["leg"]) or {}
            leg["holm"] = {k: h[k] for k in ("p_one_sided", "holm_step", "holm_alpha",
                                              "holm_z_one_sided", "mde95_holm",
                                              "clears_own_holm_step", "reject_holm")}
            leg["family"] = "S"
            leg["note"] = "Family S member: the word comes from the frame-wide family"
            word = family_reading(leg, bool(h["reject_holm"]))
            leg["reading"] = word
            cb["reading"] = frame_reading(word, development)
            cb["reading_if_claim_frame"] = word if development else None
            cb["family"] = "S"
            cb["k"] = holm_s["k"]
            cb["expected_false_flags_by_construction"] = round(ALPHA * holm_s["k"], 2)
        # the per-dimension secondary reading (each dimension's own m); no word
        by_dim: dict = {}
        for f in fam_s_cells:
            by_dim.setdefault(f["dimension"], []).append(next(
                c for c in fam_in if c["key"] == f"{f['dimension']}:{f['cell']}"))
        holm_s["by_dimension_secondary"] = {
            d: {**SB._holm_family(cs, ALPHA),
                "note": "secondary reading, each dimension its own m; the word comes from the frame-wide family only"}
            for d, cs in by_dim.items()}

    # ---- Family P on the overall cell ---------------------------------------------
    overall = cells["overall"]["all"]
    ocb = overall["comparators"].get(CLAIM_COMPARATOR) or {}
    holm_p = None
    if hv:
        leg_vs = ((vs.get("sources") or {}).get(CONS) or {}).get("spearman") or {}
        # delta from head_to_head_verdict; the consensus Spearman CI95 from the FP3-3
        # block (head_to_head_vs_sources), both copied byte for byte; the verdict's
        # own ci95 is kept beside it.
        copied_leg = {"statistic": "spearman_pooled_raw", "n": hv.get("n"),
                      "delta": hv.get("delta"),
                      "ci95": (leg_vs.get("ci95") if leg_vs.get("ci95") is not None
                               else hv.get("ci95")),
                      "verdict_ci95": hv.get("ci95"),
                      "sd": leg_vs.get("sd"), "mde95": hv.get("mde95"),
                      "mde95_estimator": hv.get("mde95_estimator"),
                      "mde95_e_cond_in_run": leg_vs.get("mde95"),
                      "resolvable": hv.get("resolvable"), "verdict": hv.get("verdict"),
                      "holm": leg_vs.get("holm"), "status": "derived",
                      "clears_own_floor": (None if not _isnum(leg_vs.get("mde95")) or not _isnum(hv.get("delta"))
                                           else bool(abs(hv["delta"]) >= leg_vs["mde95"])),
                      "source": "accuracy.head_to_head_verdict and head_to_head_vs_sources (copied)"}
        survives = bool(hv.get("resolvable")) and bool((leg_vs.get("holm") or {}).get("reject_holm"))
        word = family_reading(copied_leg, survives)
        copied_leg["reading"] = word
        ocb["headline"] = copied_leg
        ocb["reading"] = frame_reading(word, development)
        ocb["family"] = "P"
        holm_p = {"family": "P", "k": 1, "source": "copied", "reading": word,
                  "survives": survives}
    elif do_sp and ocb.get("primary"):
        leg = (ocb.get("statistics") or {}).get(ocb["primary"]["leg"]) or {}
        ok = leg.get("status") == "derived"
        fam = SB._holm_family([{"key": "overall:all", "delta": leg.get("delta") if ok else None,
                                "sd": leg.get("sd") if ok else None}], ALPHA)
        h = fam["cells"][0]
        leg["holm"] = {k: h[k] for k in ("p_one_sided", "holm_step", "holm_alpha",
                                          "holm_z_one_sided", "mde95_holm",
                                          "clears_own_holm_step", "reject_holm")}
        leg["family"] = "P"
        word = family_reading(leg, bool(h["reject_holm"]))
        leg["reading"] = word
        ocb["reading"] = frame_reading(word, development)
        ocb["reading_if_claim_frame"] = word if development else None
        ocb["family"] = "P"
        holm_p = {**fam, "family": "P", "development": development}

    # ---- Family I on the overall cell ---------------------------------------------
    holm_i = None
    if vs:
        holm_i = {"family": "I", "source": "copied from accuracy.head_to_head_vs_sources",
                  **{k: (vs.get("holm") or {}).get(k) for k in ("family", "k", "alpha", "procedure", "rule")},
                  "readings": {}}
        for r_, src in (vs.get("sources") or {}).items():
            for m_, leg in (src or {}).items():
                if not isinstance(leg, dict):
                    continue
                cl = {"n": leg.get("n"), "delta": leg.get("delta"), "ci95": leg.get("ci95"),
                      "sd": leg.get("sd"), "mde95": leg.get("mde95"), "status": "derived",
                      "clears_own_floor": leg.get("clears_e_cond_floor")}
                holm_i["readings"][f"{r_}.{m_}"] = family_reading(
                    cl, bool((leg.get("holm") or {}).get("reject_holm")) and bool(leg.get("verdict")))
    elif do_sp and ocb.get("primary"):
        veto = VETO_LEG.get(frame_id)
        fam_in = []
        for r_ in ("mlb_pipeline", "fangraphs"):
            cb = overall["comparators"].get(r_) or {}
            for lk in ((cb.get("primary") or {}).get("leg"), veto):
                leg = (cb.get("statistics") or {}).get(lk) or {}
                ok = leg.get("status") == "derived"
                fam_in.append({"key": f"{r_}.{lk}", "delta": leg.get("delta") if ok else None,
                               "sd": leg.get("sd") if ok else None})
        fam = SB._holm_family(fam_in, ALPHA)
        holm_i = {**fam, "family": "I", "development": development, "readings": {}}
        for h in fam["cells"]:
            r_, lk = h["key"].split(".", 1)
            cb = overall["comparators"].get(r_) or {}
            leg = (cb.get("statistics") or {}).get(lk)
            if leg is None:
                holm_i["readings"][h["key"]] = "NOT_SCORED"
                continue
            leg["holm"] = {k: h[k] for k in ("p_one_sided", "holm_step", "holm_alpha",
                                              "holm_z_one_sided", "mde95_holm",
                                              "clears_own_holm_step", "reject_holm")}
            leg["family"] = "I"
            word = family_reading(leg, bool(h["reject_holm"]))
            leg["reading"] = word
            holm_i["readings"][h["key"]] = frame_reading(word, development)

    # ---- parity with the served artifact (vm2) --------------------------------------
    parity = None
    if parity_rows is not None and hv:
        use = [c for c in parity_rows if (c.get("grades") or {}).get("xfv") is not None
               and (c.get("grades") or {}).get(CONS) is not None]
        sp_x = SB._spearman([c["grades"]["xfv"] for c in use], [c["outcome"]["war"] for c in use])
        sp_c = SB._spearman([c["grades"][CONS] for c in use], [c["outcome"]["war"] for c in use])
        fl = SB._paired_delta_ci(use, "xfv", CONS, "spearman", label=f"{frame_id}.parity")
        mine_delta = (None if sp_x is None or sp_c is None else round(round(sp_x, 4) - round(sp_c, 4), 5))
        leg_vs = ((vs.get("sources") or {}).get(CONS) or {}).get("spearman") or {}
        parity = {"artifact": "data/source_backtest.json", "n_served": hv.get("n"), "n_read": len(use),
                  "served_delta": hv.get("delta"), "read_delta": mine_delta,
                  "served_ci95": hv.get("ci95"), "read_ci95": fl.get("ci95"),
                  "served_sd": leg_vs.get("sd"), "read_sd": fl.get("sd"),
                  "reproduces": (hv.get("n") == len(use) and hv.get("delta") == mine_delta
                                 and hv.get("ci95") == fl.get("ci95")),
                  "note": ("the overall cell is COPIED from the served verdict; this receipt "
                           "recomputes its interval through source_backtest._paired_delta_ci "
                           "on the rows the matrix scored")}

    # ---- summary -------------------------------------------------------------------
    summary = _summary(frame_id, cells, families["S"]["k"], n, development, do_sp)
    block = {
        "frame_id": frame_id, "role": FRAME_ROLE.get(frame_id), "development": development,
        "n": n, "n_by_side": {s: sum(1 for r in rows if r["side"] == s) for s in F.SIDES},
        "n_players": len({r["key"] for r in rows}),
        "groups": sorted({r["group"] for r in rows}),
        "comparators": comparators, "statistics": list((ocb.get("statistics") or {}).keys()),
        "auc_legs": auc_keys, "veto_leg": VETO_LEG.get(frame_id),
        "reserved_guard": guard,
        **(extra or {}),
        "families": families,
        "cells": cells,
        "holm": {"S": holm_s, "P": holm_p, "I": holm_i},
        "summary": summary,
        "parity": parity,
        "receipts": receipts or {},
        "elapsed_s": round(time.time() - t0, 1),
    }
    return block


def _summary(frame_id, cells, k, n, development, do_sp) -> dict:
    """Counts over the Family S cells (the K the line names), with the declared
    stratum cells outside the family (under the floor, or the AUC-only panel's
    scored cells) counted beside them."""
    counts = {w.lower(): 0 for w in READINGS}
    would = {w.lower(): 0 for w in READINGS}
    outside = {w.lower(): 0 for w in READINGS}
    total = under_floor = 0
    for dim, by in cells.items():
        if dim == "overall":
            continue
        for cell, blk in by.items():
            if not blk.get("declared"):
                continue
            cb = (blk.get("comparators") or {}).get(CLAIM_COMPARATOR) or {}
            w = cb.get("reading")
            if w is None:
                continue
            total += 1
            if not blk.get("scored"):
                under_floor += 1
            if blk.get("in_family_s") or (not do_sp and blk.get("scored")):
                counts[w.lower()] += 1
                wc = cb.get("reading_if_claim_frame") or w
                would[wc.lower()] += 1
            else:
                outside[w.lower()] += 1
    exp = round(ALPHA * k, 2)
    intro = f"On {FRAME_LABEL.get(frame_id, frame_id)} (n {n})"
    scored_panel = sum(counts.values())
    if not do_sp:
        line = (f"{intro}: AUC tabs only, no family; on the veto leg {counts['flagged_uncorrected']} "
                f"cells clear their own floor uncorrected, {counts['equivalent']} equivalent, "
                f"{counts['unresolved']} not resolvable, {counts['unpowered']} unpowered of "
                f"{scored_panel} scored; {under_floor} under the floor.")
    elif development:
        line = (f"{intro}: {counts['development']} cells read as development, not a claim, "
                f"{counts['unpowered']} unpowered of {k} in the family; the family would read "
                f"{would['ahead']} ahead, {would['behind']} behind, {would['equivalent']} equivalent, "
                f"{would['unresolved']} not resolvable, {would['flagged_uncorrected']} clearing their "
                f"own floor; at alpha 0.05 the family would flag {exp} cells by chance; "
                f"{under_floor} cells under the floor.")
    else:
        line = (f"{intro}: {counts['ahead']} cells ahead, {counts['behind']} behind, "
                f"{counts['equivalent']} equivalent, {counts['unresolved']} not resolvable, "
                f"{counts['flagged_uncorrected']} clearing their own floor but not the family, "
                f"{counts['unpowered']} unpowered of {k} in the family; at alpha 0.05 the family "
                f"would flag {exp} cells by chance; {under_floor} cells under the floor.")
    return {"k_family_s": k, "alpha": ALPHA, "expected_false_flags_by_construction": exp,
            "stratum_cells": total, "under_floor": under_floor, "counts": counts,
            "outside_family": outside,
            "would_read_on_a_claim_frame": would if development else None,
            "overall_reading": (((cells.get("overall") or {}).get("all") or {})
                                .get("comparators", {}).get(CLAIM_COMPARATOR, {}).get("reading")),
            "line": line}


# ---------------------------------------------------------------------------
# reserved frames (never scored here)
# ---------------------------------------------------------------------------

def reserved_frame(frame_id: str, gate_doc: dict | None = None) -> dict:
    strata = ((gate_doc or {}).get("strata") or {}).get(frame_id)
    vintages = sorted(F.RESERVED_LV) if frame_id == "lv_res" else None
    pre = {"overall": ["all"]}
    for dim in ST.DIMENSIONS:
        cs = list(ST.CELLS[dim])
        if dim == "list_year":
            cs = [str(v) for v in vintages] if vintages else ["the look's cohort"]
        pre[dim] = cs
    block = {"frame_id": frame_id, "role": FRAME_ROLE.get(frame_id), "development": False,
             "reserved": True,
             "reserved_rule": ("never scored by this tool; the cells are copied from "
                               "data/efv_v2_gate.json once the look runner (EFV3_D6) has "
                               "written them inside the registered look"),
             "list_vintages": vintages,
             "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR if frame_id == "vm_pros" else None,
             "pre_registered_cells": pre,
             "families": {"written_before_cells": True,
                          "P": {"what": "the primary of the look record", "k": 1},
                          "I": {"what": "the secondary industry family of the look record"},
                          "S": {"what": "Family S, secondary, no ship weight (E3-Q4 = A)",
                                "floor_rows": FLOOR_ROWS, "alpha": ALPHA}},
             "cells": strata if strata else {},
             "summary": {"reading": "RESERVED_PENDING" if not strata else "copied from the look record",
                         "line": (f"{FRAME_LABEL.get(frame_id)}: pre-registered, not read"
                                  if not strata else f"{FRAME_LABEL.get(frame_id)}: copied from data/efv_v2_gate.json")}}
    if not strata:
        block["reading"] = "RESERVED_PENDING"
        block["printed"] = PRINTED["RESERVED_PENDING"]
    return block


def cells_for(frame_id: str, rows: list[dict], *, gate_sha: str | None = None, **kw) -> dict:
    """The look runner's entry (EFV3_D6): score the matrix cells of a reserved frame ONCE
    inside the registered look, with the committed gate sha. Same contract as
    score_frame; raises efv_vintage_frame.ReservedFrameError without the sha."""
    return score_frame(frame_id, rows, gate_sha=gate_sha, **kw)


# ---------------------------------------------------------------------------
# the artifact
# ---------------------------------------------------------------------------

def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("generated_at", "elapsed_s")}


def _content_sha(doc: dict) -> str:
    return hashlib.sha256(json.dumps(_strip(doc), sort_keys=True, default=str).encode("utf-8")).hexdigest()


def write_artifact(doc: dict, out_path: Path | None = None,
                   history_path: Path | None = None) -> dict:
    """Compare-before-write on content excluding generated_at and elapsed_s; one
    history line per changed state. Both paths resolve at call time (OUT_PATH and
    HISTORY_PATH), so the test suite can redirect them to its mirror."""
    out_path = OUT_PATH if out_path is None else Path(out_path)
    history_path = HISTORY_PATH if history_path is None else Path(history_path)
    doc = _clean(doc)
    prev = None
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            prev = None
    if prev is not None and _strip(prev) == _strip(doc):
        return {"written": False, "path": str(out_path), "reason": "unchanged (compare-before-write)"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1, allow_nan=False), encoding="utf-8")
    line = {"generated_at": doc.get("generated_at"), "commit": (doc.get("code") or {}).get("commit"),
            "sha256": _content_sha(doc),
            "label": doc.get("label"),
            "frames": {fid: {"n": f.get("n"), "k_family_s": (f.get("summary") or {}).get("k_family_s"),
                             "counts": (f.get("summary") or {}).get("counts"),
                             "reading": (f.get("summary") or {}).get("reading")}
                       for fid, f in (doc.get("frames") or {}).items()}}
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, allow_nan=False) + "\n")
    return {"written": True, "path": str(out_path), "history": str(history_path)}


def _served_backtest(path: Path = SB_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(data_dir: Path | None = None, *, B: int = B_DEFAULT, seed: int = SEED,
        frames: tuple[str, ...] = ("vm2", "lv_dev", "bust_inclusive"),
        write: bool = True, backtest=None, out_path: Path | None = None,
        history_path: Path | None = None, log=print) -> dict:
    """Build the matrix. `backtest` is the (result, frames) pair of
    run_source_backtest(return_rows=True) when the nightly block hands it over; by hand
    the vm2 rows are rebuilt through vm2_inputs."""
    t0 = time.time()
    data_dir = Path(data_dir) if data_dir is not None else SB.DATA_DIR
    label = label_block()
    served = backtest[0] if backtest else _served_backtest(data_dir / "source_backtest.json")
    acc = served.get("accuracy") or {}
    out_frames: dict = {}
    inputs = None
    if "vm2" in frames or "bust_inclusive" in frames:
        log("[efv_matrix] building the vm2 rows")
        inputs = backtest[1] if backtest else vm2_inputs(data_dir)
        side_of, milb_of = _matrix_blocks()
        side_of = {**side_of, **(inputs.get("side_of") or {})}
        records = _records_by_key(inputs.get("universe"), inputs.get("bust_records"))
        vm2_rows, vm2_rec = rows_from_vm("vm2", inputs["vm2_rows"], side_of, milb_of, records,
                                         inputs.get("six_year"))
        vm2_rec.update(timing_pin=inputs.get("vm2_timing"),
                       six_season_label=inputs.get("six_year_receipt"),
                       age_unknown=sum(1 for r in vm2_rows if r["cells"].get("age_band") == ST.UNKNOWN),
                       level_none={"rows": sum(1 for r in vm2_rows if r["cells"].get("level_at_list") == "none"),
                                   "without_milb_block": sum(1 for r in vm2_rows
                                                             if r["cells"].get("level_at_list") == "none"
                                                             and not r.get("milb_block"))},
                       l6_rows={"labelled": sum(1 for r in vm2_rows if r.get("l6")),
                                "fully_resolved": sum(1 for r in vm2_rows if r.get("l6")
                                                      and not r["l6"].get("censored_flag"))},
                       efv_consensus_rank_agreement_by_group=_rank_agreement(vm2_rows))
        if "vm2" in frames:
            log(f"[efv_matrix] scoring vm2 (n {len(vm2_rows)})")
            out_frames["vm2"] = score_frame(
                "vm2", vm2_rows, B=B, seed=seed, copied=acc, parity_rows=inputs["vm2_rows"],
                receipts=vm2_rec,
                extra={"frame_version": "vm2", "window": [min(inputs["years"]), max(inputs["years"])],
                       "outcome": "career WAR to date (busts cannot enter: the frame is keyed on a debut)",
                       "contributor": f"career WAR >= {SB.CONTRIBUTOR_WAR}",
                       "source": {"artifact": "data/source_backtest.json",
                                  "generated_at": served.get("generated_at"),
                                  "basis": SB.VM2_BASIS,
                                  "efv_scored_object": acc.get("efv_scored_object") or inputs.get("efv_scored_object")}})
            log(f"[efv_matrix] vm2 done in {out_frames['vm2']['elapsed_s']} s: {out_frames['vm2']['summary']['line']}")
        if "bust_inclusive" in frames:
            bust_rows, bust_rec = rows_from_vm("bust_inclusive", inputs["bust_rows"], side_of,
                                               milb_of, records, None)
            for r in bust_rows:
                r["debut_year"] = None
            # the strata of a vm row do not depend on the frame id (both are vm kind)
            combined = [dict(r) for r in vm2_rows] + bust_rows
            bust_rec.update(bust_frame=inputs.get("bust_receipt"),
                            n_debuted_half=len(vm2_rows), n_bust_half=len(bust_rows))
            log(f"[efv_matrix] scoring bust_inclusive (n {len(combined)})")
            out_frames["bust_inclusive"] = score_frame(
                "bust_inclusive", combined, B=B, seed=seed, statistics=("auc",),
                receipts=bust_rec,
                extra={"frame_version": "vm2 + busts at their last list year",
                       "outcome": "career WAR to date, busts at 0 (measured, not imputed)",
                       "row_rule": ("the vm2 rows plus source_backtest._bust_frame (the claim "
                                    "instruments' bust_inclusive row rule: each bust at the last "
                                    "year every scored rater still graded him)")})
            log(f"[efv_matrix] bust_inclusive done in {out_frames['bust_inclusive']['elapsed_s']} s")
    if "lv_dev" in frames:
        log("[efv_matrix] building the lv_dev rows (DS-16 path)")
        dev_rows, meta = lv_inputs()
        lv_rows, lv_rec = rows_from_lv("lv_dev", dev_rows)
        ws = meta.get("w_star_dev") or {}
        w_star = ws.get("w_star")
        legs = [("auc_w1", lambda r: r["war"] >= 1.0),
                ("auc_wstar", lambda r: w_star is not None and r["war"] >= w_star),
                ("auc_w2", lambda r: r["war"] >= 2.0),
                ("auc_w4", lambda r: r["war"] >= 4.0),
                ("auc_r3", lambda r: r.get("r3") == 1)]
        lv_rec.update(identity_route={k: sum(1 for r in lv_rows if r.get("id_how") == k)
                                      for k in sorted({r.get("id_how") for r in lv_rows}, key=str)},
                      label_status={k: sum(1 for r in lv_rows if r.get("label_status") == k)
                                    for k in sorted({r.get("label_status") for r in lv_rows}, key=str)},
                      age_unknown=sum(1 for r in lv_rows if r["cells"].get("age_band") == ST.UNKNOWN),
                      level_none={"rows": sum(1 for r in lv_rows if r["cells"].get("level_at_list") == "none"),
                                  "without_milb_block": sum(1 for r in lv_rows
                                                            if r["cells"].get("level_at_list") == "none"
                                                            and not r.get("milb_block"))},
                      r3_rows=sum(1 for r in lv_rows if r.get("r3") is not None),
                      per_vintage=meta.get("per_vintage"),
                      efv_consensus_rank_agreement_by_group=_rank_agreement(lv_rows))
        log(f"[efv_matrix] scoring lv_dev (n {len(lv_rows)})")
        out_frames["lv_dev"] = score_frame(
            "lv_dev", lv_rows, B=B, seed=seed, auc_legs=legs, receipts=lv_rec,
            extra={"frame_version": "lv1_v2", "window": [min(meta["folds"]), max(meta["folds"])],
                   "vintages_scored": meta.get("folds"),
                   "outcome": "W3 (WAR over the first three MLB seasons, 0 if no debut within three seasons of V)",
                   "contributor": "W3 >= w_star_dev", "w_star_dev": ws,
                   "efv_scored_object": {"model_id": "efv_v2 (development, order index)",
                                         "basis": ("V2 fitted per vintage on earlier list vintages, "
                                                   "every frame player excluded (DS-16 path)")}})
        log(f"[efv_matrix] lv_dev done in {out_frames['lv_dev']['elapsed_s']} s: {out_frames['lv_dev']['summary']['line']}")
    gate_doc = _served_backtest(GATE_JSON_PATH)
    for fid in RESERVED_FRAMES:
        out_frames[fid] = reserved_frame(fid, gate_doc)
    doc = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_id": MODEL_ID,
        "registration": REGISTRATION,
        "regen_cmd": REGEN_CMD,
        "role": "evaluation surface: selects nothing, re-runs no closed arm, moves no served number",
        "label": label,
        "code": {"commit": _commit(), "tool": "tools/efv_matrix.py",
                 "efv_matrix_sha256": _sha_file(Path(__file__)),
                 "efv_strata_sha256": _sha_file(ROOT / "efv_strata.py"),
                 "efv_v2_stat_sha256": _sha_file(ROOT / "efv_v2_stat.py")},
        "design": {
            "dimensions": list(ST.DIMENSIONS), "cells": {d: list(c) for d, c in ST.CELLS.items()},
            "dimension_side": dict(ST.DIMENSION_SIDE),
            "disclosed_dimensions": list(ST.DISCLOSED_DIMENSIONS),
            "banned_dimensions": list(ST.BANNED_DIMENSIONS), "amendment_rule": ST.AMENDMENT_RULE,
            "floor_rows": FLOOR_ROWS, "floor_clusters": FLOOR_CLUSTERS,
            "auc_min_positives": AUC_MIN_POS, "min_group_rows": MIN_GROUP_ROWS,
            "equivalence_margin": EQUIVALENCE_MARGIN, "unpowered_mde95": UNPOWERED_MDE95,
            "alpha": ALPHA, "bootstrap": {"B": B, "seed": seed, "estimator": "E_cond",
                                          "unit": "player cluster",
                                          "convention": "MDE95 = 1.645 * sd(delta), one-sided"},
            "vocabulary": list(READINGS), "printed": dict(PRINTED),
            "reading_order": ("NOT_SCORED; UNPOWERED (rows, interval, positives); AHEAD or BEHIND "
                              "(survives the family); UNPOWERED (mde95 above 2 x 0.02); EQUIVALENT; "
                              "FLAGGED_UNCORRECTED; UNRESOLVED; DEVELOPMENT replaces the interval "
                              "words on a development frame; RESERVED_PENDING on a reserved frame"),
            "owner_answers": {"lane D E3-Q2": "A (Holm-corrected words on vm2 inside the matrix only)",
                              "lane D E3-Q4": "A (40 rows, B 2000, E_cond, seed 20260906)"},
            "statistics": dict(STAT_LABELS),
            "comparators": {c: COMPARATOR_LABELS[c] for c in COMPARATORS},
            "claim_comparator": CLAIM_COMPARATOR,
        },
        "frames": out_frames,
        "elapsed_s": round(time.time() - t0, 1),
    }
    doc = _clean(doc)
    if write:
        res = write_artifact(doc, out_path, history_path)
        log(f"[efv_matrix] {res}")
    return doc


# ---------------------------------------------------------------------------
# console
# ---------------------------------------------------------------------------

def _fmt(v, d=4) -> str:
    return f"{v:.{d}f}" if _isnum(v) else "-"


def summary_text(doc: dict) -> str:
    """A console view that survives None and NaN in every cell."""
    lines = [f"=== eFV SCOREBOARD MATRIX ({(doc or {}).get('generated_at')}; label "
             f"{((doc or {}).get('label') or {}).get('provider')} through "
             f"{((doc or {}).get('label') or {}).get('resolved_through')}) ==="]
    for fid, f in ((doc or {}).get("frames") or {}).items():
        f = f or {}
        lines.append(f"\n[{fid}] {f.get('role')}: {(f.get('summary') or {}).get('line')}")
        for dim, by in (f.get("cells") or {}).items():
            for cell, blk in (by or {}).items():
                cb = ((blk or {}).get("comparators") or {}).get(CLAIM_COMPARATOR) or {}
                pk = (cb.get("primary") or {}).get("leg")
                leg = (cb.get("statistics") or {}).get(pk) or {}
                ci = leg.get("ci95") if isinstance(leg.get("ci95"), list) else [None, None]
                lines.append(f"  {dim:<20} {str(cell):<14} n {str((blk or {}).get('n', '-')):>5}  "
                             f"delta {_fmt(leg.get('delta'))} CI [{_fmt(ci[0] if len(ci) > 0 else None)}, "
                             f"{_fmt(ci[1] if len(ci) > 1 else None)}] mde95 {_fmt(leg.get('mde95'))}  "
                             f"{cb.get('reading') or '-'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--frames", default="vm2,lv_dev,bust_inclusive",
                    help="comma list of development frames to score")
    ap.add_argument("--B", type=int, default=B_DEFAULT, help="bootstrap draws (default 2000)")
    ap.add_argument("--no-write", action="store_true", help="compute, print, write nothing")
    ap.add_argument("--quiet", action="store_true", help="no per-cell console table")
    a = ap.parse_args(argv)
    frames = tuple(x.strip() for x in a.frames.split(",") if x.strip())
    bad = [f for f in frames if f in RESERVED_FRAMES]
    if bad:
        raise F.ReservedFrameError(f"reserved frames are never scored by this tool: {bad}")
    doc = run(B=a.B, frames=frames, write=not a.no_write)
    if not a.quiet:
        print(summary_text(doc))
    print(f"elapsed {doc.get('elapsed_s')} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

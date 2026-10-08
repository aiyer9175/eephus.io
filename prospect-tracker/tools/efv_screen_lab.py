# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV screening lab (EFV3 lane B s4; docs/efv-v2/EFV_V2_GATE.md s10 once EFV3_B6
writes it). One question per candidate column: does adding it to the assembled Driver
System V2, under V2's own admission rule inside every fold, move the registered
statistic against the V2 base? A candidate that passes is ADMITTED to the gate's
CANDIDATE LIST (s4.2), never to the served grade. The lab touches no served number,
reads no reserved frame and re-runs no closed arm.

FRAME. lv_dev only: efv_vintage_frame.build_frame(side, V) for the folds V in FOLDS
(2017 to 2019, the development vintages V2 is scored on), labelled by
efv_labels.labels_for_frame (W3; a B9b reserved_vm row is kept at W3 = 0 and counted).
Training per fold: efv_v2_model.lv_training_rows at vintages below V with every V-frame
player excluded, exactly as efv_v2_model.v2_lv_scores trains. vm_dev is never screened.

BASE AND CANDIDATE. The base is V2 as assembled (order_idx, weights from
data/efv_v2_assembly.json) on the frame efv_v2_assemble.build_frames builds. A candidate
is the same assembly with ONE extra column offered to ONE declared head (skill or timing)
through efv_v2_model.fit_v2(extra=...), admitted or refused inside each fold by
efv_v2_model.admission_for_key (DS-06). A refused column leaves the candidate equal to
the base in that fold: the honest null, not an error. Column keys carry
efv_v2_model.V2_SCREEN_PREFIX so a no-value row imputes at the fold's observed training
mean like every sidecar driver (has_block_means).

THE TEXT COLUMN (source "text"; EFV3_B5 wired it, EFV3_B2 built it). The lab hands one
value per (V, player_key) slot, so the fold-fitted text scalar is STACKED OUT OF
VINTAGE: the value at (v, pk) is efv_text_features.fold_columns' prediction for the v
rows from a tokenizer, idf and ridge fit on the text vintages strictly below v with
every v-frame player excluded (GATE s4.5). No row's value reads its own label, and the
lab's fold V test rows read a fit on vintages below V. The dropped vintages (2011, 2012)
and the first text vintage (nothing earlier to fit on) carry no value. A head the DS-03
verdict withholds on a side (efv_text_features.offered_columns) is not built: the arm
is recorded as unavailable, counted in m, never admitted (gate s10.7).

THE COVERAGE ARM (kind "coverage"; EFV3_B3). A frame change has no column. The arm's
candidate is the base assembly refit on frames built with the named
efv_vintage_frame attribute at `candidate`; its base is the same assembly refit on
frames built with the attribute at `base` (the served default floor); the two are paired
row by row on the players both score. The lab's shared frame (the base of every column
arm and of the floors) is build_frames as the tree builds it, whatever floor that is,
and the arm's receipt records the floor every frame was read at per side.

STATISTIC. efv_v2_stat.within primary (size-weighted within-(side, vintage) Spearman,
MIN_GROUP_ROWS 20), pooled after the identical output map secondary, contributor AUC at
w_star_dev veto only. Delta: efv_v2_stat.paired_delta(statistic="within", B, seed),
E_cond, paired, player-clustered; the admission claim is the one-sided 95 percent lower
bound lb95 = delta - mde95 (mde95 = 1.645 x sd of the drawn deltas).

FLOORS FIRST. Before any candidate, N_NOISE standard normal noise columns per head and
side go through the identical refit; the MAX mde95 over them is the head's feature-add
floor on that side, for the within, pooled and AUC legs. The floors are written under
the key `floors` BEFORE `arms`, so a reader never sees an arm without the floor it was
read against. FLOOR MODE (--floor-mode, DISCLOSED): "admitted" sends the noise column
through the identical DS-06 admission as well, as LANE_B.md s4.4 wrote the rule; on
the real frame a standard normal column holds one sign across six or more training
vintages almost never, so every noise delta is identically 0 and the floor is
degenerate (recorded as None, never 0, and every arm then reads
NOT_ADJUDICATED_NO_RHO_FLOOR). "forced" (the default) admits the noise column without
the rule for the floor derivation only (efv_v2_model.fit_v2 extra force), which is the
feature-add floor the rule meant: what a column that IS admitted moves by chance. The
mode in force is named in `floors.mode`; the other mode's receipt is written beside it
under `floors_other` so the choice is visible in every artifact. The permutation null
and the twin always go through the identical admission.

CONTROLS per arm: a zero-information twin (the column permuted within (side, vintage),
same pipeline); an N_PERM-draw permutation null of the within delta (one-sided p); the
per-fold deltas with their signs and the DS-06 per-vintage signs; the contributor AUC
delta against its own floor; a DS-03 balance probe on the column's missingness
indicator (tools/efv_identity_balance.py pattern) when any row lacks a value.

HOLM. One family per wave over every registered (candidate, side) arm, formed after
every arm is measured, never inside the measuring loop (tools/efv_driver_lab.py
apply_holm_verdicts). p is the permutation p of the within delta; m is the registered
family size even when an arm could not be built (an absent arm never shrinks the
correction).

ADMISSION RULE (frozen in the gate's s10 before the registered run), all of:
  (a) within lb95 above 0 and the point at or above the head's floor on that side;
  (b) Holm-adjusted permutation p below 0.05 inside the wave family;
  (c) the twin inside its floor;
  (d) DS-06 admitted the column in every fold and the fold deltas share one sign;
  (e) contributor AUC not adverse beyond its floor;
  (f) any missingness indicator BALANCED under the DS-03 probe;
  (g) the pooled secondary not adverse beyond its floor (reported).
VERDICTS are the eight strings of docs/EFV_GATE_STANDARD.md s3.1 and nothing else in a
registered run: the composite gate (a), (c), (d), (f), (g) plays the role the standard
gives "rho clears"; (e) is the AUC veto; (b) is the Holm step. An absence never reads
as PASS. An EXPLORATORY run (--out outside data/, or --exploratory) forms NO verdict:
every arm reads NOT_ADJUDICATED_EXPLORATORY (reserved to that mode, never written
under data/) and no clause is evaluated, so the registered run has nothing left to
choose.

BANS. List vintages 2020 and 2021 are never built (efv_vintage_frame guard; the lab
asserts reserved_vm_pins() is empty); no 2025 or later debut cohort; nothing is grouped
by consensus-FV level (test_efv_screen_lab.py scans this source); the 39 closed arms are
not re-run; pick_overall runs only under its re-test name; seasons_at_level is not an
arm (owner DS-Q2); no lambda, no correction family, no vm_dev screening.

OUTPUT. --out PATH (default data/xfv_screen_wave1.json): registration_echo, label,
guards, floors, arms[], holm, probes[]. When --out is under data/ the arm ledger is
regenerated (tools/efv_arm_ledger.py) and the lab's own rows join the progress ledger
(efv_progress.update_screening: the screening rows alone, never a served row, which
the nightly's update() owns); when it is outside data/ nothing else is written. --floors-only runs steps 1 and 2
(frame, floors) with no candidate.

Run:  python tools/efv_screen_lab.py --check
      python tools/efv_screen_lab.py --floors-only --out <path>
      python tools/efv_screen_lab.py --out <path>            (exploratory, EFV3_B5)
      python tools/efv_screen_lab.py                         (registered, EFV3_B7)
"""
from __future__ import annotations

import argparse
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

import efv_labels as L  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

DATA_DIR = ROOT / "data"
WAVE = 1
OUT_DEFAULT = DATA_DIR / "xfv_screen_wave1.json"
MODEL_ID = f"efv_v2_screen:wave{WAVE}"
TOOL = "tools/efv_screen_lab.py"
CONS = SB.CONSENSUS_KEY
#: The folds: the development vintages V2 is scored on (after the combiner rule's years,
#: before R-LV).
FOLDS: tuple[int, ...] = tuple(v for v in F.DEV_VINTAGES if v >= H.V2_FIRST_SCORED_YEAR)
HEADS = ("skill", "timing")
SIDES = F.SIDES
#: Rows of both sides pooled: the side a coverage arm (a frame change) is read on.
BOTH = "both"
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
N_PERM = 500
N_NOISE = 3
FLOOR_MODES = ("forced", "admitted")
FLOOR_MODE_DEFAULT = "forced"
#: Balance probe draws (tools/efv_identity_balance.py B_BAL).
B_BAL = 500
ALPHA = 0.05
FROZEN_DATE = "2026-10-02"
#: The commit that froze CANDIDATES (EFV3_B1; docs/efv-v2/EFV_V2_GATE.md s10.9). Later
#: commits changed only where a column reads its values, never a name, side, head,
#: kind or re-test flag (test_wave_one_is_frozen).
FROZEN_COMMIT = "d9fe7db4"
CANDIDATE_KEY = f"{H.V2_SCREEN_PREFIX}cand"
#: The eight verdict strings of docs/EFV_GATE_STANDARD.md s3.1. A registered run emits
#: nothing else.
VERDICTS: frozenset[str] = frozenset({
    "PASS", "VETO_ON_AUC", "NULL", "NULL_AUC_ONLY", "NULL_HOLM",
    "NOT_ADJUDICATED_NO_RHO_FLOOR", "NOT_ADJUDICATED_NO_AUC_FLOOR",
    "NOT_ADJUDICATED_NO_HOLM"})
#: The exploratory run's only verdict (EFV3_B5). Never written under data/.
EXPLORATORY_VERDICT = "NOT_ADJUDICATED_EXPLORATORY"
NOTE = "screening lab; development frame, spent, not a claim"
ADMISSION_RULE = (
    "(a) within lb95 above 0 and point at or above the head's floor on that side; "
    "(b) Holm-adjusted permutation p below 0.05 inside the wave family; "
    "(c) the twin inside its floor; "
    "(d) DS-06 admitted the column in every fold and the fold deltas share one sign; "
    "(e) contributor AUC not adverse beyond its floor; "
    "(f) any missingness indicator BALANCED under the DS-03 probe; "
    "(g) the pooled secondary not adverse beyond its floor (reported)")

#: WAVE 1, frozen 2026-10-02 (LANE_B.md s4.3; EFV3_PLAN.md s4): seven arms, one Holm
#: family. `column` says where the values come from: a frame-row key (with an optional
#: transform), a builder module's function `fn(side, frames) -> {(V, player_key):
#: value | None}` (EFV3_B4 pick), or the text family's stacked fold fit (source "text",
#: EFV3_B2 through text_column_values). A column whose source is absent on the run's
#: tree, or that its builder withholds, is recorded as unavailable and measured by
#: nothing; it still counts in m.
#: `kind` "coverage" is a frame change (EFV3_B3): the candidate is the base refit on
#: frames built with the named efv_vintage_frame attribute at `candidate`, against the
#: same refit on frames built with it at `base`, read on both sides pooled; it has no
#: head and takes the larger of the two heads' pooled floors.
#: seasons_at_level_pit is NOT here (owner DS-Q2; data/efv_v2_assembly.json scrapped.pit;
#: already read on lv_dev in H0's pitcher list). pick_overall is a named re-test of a
#: closed F-VM arm (D-1) on a frame it was never read on, timing head only (D4).
CANDIDATES: tuple[dict, ...] = (
    {"name": "txt_skill_hit", "side": "hit", "head": "skill", "kind": "column",
     "retest": False,
     "column": {"source": "text", "module": "efv_text_features", "head": "skill",
                "construction": "stacked out of vintage (text_column_values)"},
     "what": "fold-fitted tf-idf ridge scalar on the W3 percentile residual (EFV3_B2)"},
    {"name": "txt_skill_pit", "side": "pit", "head": "skill", "kind": "column",
     "retest": False,
     "column": {"source": "text", "module": "efv_text_features", "head": "skill",
                "construction": "stacked out of vintage (text_column_values)"},
     "what": "fold-fitted tf-idf ridge scalar on the W3 percentile residual (EFV3_B2)"},
    {"name": "txt_time_hit", "side": "hit", "head": "timing", "kind": "column",
     "retest": False,
     "column": {"source": "text", "module": "efv_text_features", "head": "time",
                "construction": "stacked out of vintage (text_column_values)"},
     "what": "the same text scalar fitted on the R3 target, timing head (EFV3_B2)"},
    {"name": "txt_time_pit", "side": "pit", "head": "timing", "kind": "column",
     "retest": False,
     "column": {"source": "text", "module": "efv_text_features", "head": "time",
                "construction": "stacked out of vintage (text_column_values)"},
     "what": "the same text scalar fitted on the R3 target, timing head (EFV3_B2)"},
    {"name": "milb_floor_2005", "side": BOTH, "head": None, "kind": "coverage",
     "retest": False,
     "column": {"source": "frame_attr", "attr": "MILB_FLOOR_LV", "candidate": 2005,
                "base": 2014},
     "what": ("the MiLB block floor lifted from 2014 to 2005 on the F-LV frame only "
              "(EFV3_B3): the base assembly refit on frames built at the lifted floor "
              "against the same refit on frames built at the served default floor, "
              "paired row by row; the per-side withhold applies as committed")},
    {"name": "pick_overall_time_hit", "side": "hit", "head": "timing", "kind": "column",
     "retest": True,
     "column": {"source": "module", "module": "efv_pick_features",
                "attr": "screen_column"},
     "what": ("named re-test of the closed F-VM pick arm (D-1) on lv_dev, timing head "
              "only (D4): the draft_history pick joined on the outcome-blind id with "
              "draft year strictly below V, else the sidecar pick known at V, log1p "
              "(EFV3_B4)")},
    {"name": "pick_overall_time_pit", "side": "pit", "head": "timing", "kind": "column",
     "retest": True,
     "column": {"source": "module", "module": "efv_pick_features",
                "attr": "screen_column"},
     "what": ("named re-test of the closed F-VM pick arm (D-1) on lv_dev, timing head "
              "only (D4): the draft_history pick joined on the outcome-blind id with "
              "draft year strictly below V, else the sidecar pick known at V, log1p "
              "(EFV3_B4)")},
)

#: WAVE 2 (EFV3_W2, owner EW2-6 2026-10-08): each family keeps its arms in its own
#: module as ARMS (this file's candidate shape, column source "module") and reads
#: them through that module's development read; wave 1 above is unchanged.
WAVE2_ARM_MODULES: tuple[str, ...] = ("efv_w2_milb",)


def wave2_candidates() -> tuple[dict, ...]:
    """Every registered wave-2 arm, in module order."""
    return tuple(a for m in WAVE2_ARM_MODULES for a in __import__(m).ARMS)



class ColumnUnavailable(RuntimeError):
    """A candidate's column cannot be built on this tree (its builder has not landed)."""


# ---------------------------------------------------------------------------
# guards and receipts
# ---------------------------------------------------------------------------

def guards(folds=FOLDS) -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    folds = tuple(int(v) for v in folds)
    for v in folds:
        F.guard_score_request(v, purpose="screening lab")
    bad = sorted(set(folds) & set(F.RESERVED_LV))
    if bad or max(folds) >= min(F.RESERVED_LV):
        raise F.ReservedFrameError(f"a screening fold is reserved: {folds}")
    if H.RULE_LAST_YEAR >= min(folds):
        raise ValueError("the combiner rule's years overlap the screening folds")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins, "lv_folds": list(folds),
            "rule_last_year": H.RULE_LAST_YEAR,
            "vm_dev_screened": False,
            "closed_arms_rerun": False}


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


def label_id() -> str:
    """'ewar_v2@<build>' off the board fingerprint, or 'fwar@<vintage id>' once the
    epoch has moved the provider."""
    prov = L.provider()
    if prov == "fwar":
        import war_source
        return f"fwar@{(war_source.fwar_index() or {}).get('vintage_id')}"
    try:
        import storage
        fp = storage.board_basis_fingerprint()
    except Exception:                                         # noqa: BLE001
        fp = None
    for part in (fp or "").split("|"):
        if part.startswith("label="):
            return part[len("label="):]
    return f"{prov}@unknown"


def registration_echo(candidates=CANDIDATES, *, B: int = B_DEFAULT, n_perm: int = N_PERM,
                      folds=FOLDS, floor_mode: str = FLOOR_MODE_DEFAULT) -> dict:
    return {
        "wave": WAVE, "frozen": FROZEN_DATE, "frozen_commit": FROZEN_COMMIT,
        "candidates": [{k: c[k] for k in ("name", "side", "head", "kind", "retest")}
                       for c in candidates],
        "family_size": len(candidates),
        "heads": list(HEADS),
        "frame": {"id": "lv_dev", "folds": list(folds), "label": "W3",
                  "training": "efv_v2_model.lv_training_rows, every V-frame player "
                              "excluded (GATE s4.5)",
                  "reserved_vm_policy": "B9b: kept at W3 = 0, counted"},
        "base": "efv_v2_model.v2_lv_scores order_idx, weights of "
                "data/efv_v2_assembly.json",
        "candidate_rule": "one column, one head, efv_v2_model.admission_for_key inside "
                          "each fold (DS-06); refused reads as the base",
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY],
                      "secondary": S.STAT_LABEL[S.SECONDARY],
                      "veto": S.STAT_LABEL["auc"], "min_group_rows": S.MIN_GROUP_ROWS},
        "estimator": {"B": int(B), "seed": SEED, "estimator": "E_cond",
                      "unit": "player cluster", "paired": True,
                      "claim": "one-sided 95 percent lower bound, lb95 = delta - mde95"},
        "floor_rule": (f"{N_NOISE} N(0,1) noise columns per head and side through the "
                       "identical refit; the MAX mde95 is the head's feature-add floor; "
                       "derived in the run before any arm"),
        "floor_mode": floor_mode,
        "floor_mode_meaning": {
            "forced": "the noise column is admitted without the DS-06 rule for the floor "
                      "derivation only (the default; the other mode's receipt is written "
                      "under floors_other)",
            "admitted": "the noise column goes through the identical DS-06 admission "
                        "(LANE_B.md s4.4 as written); degenerate when no noise column is "
                        "admitted in any fold"},
        "controls": ["zero-information twin (permuted within (side, vintage))",
                     f"{int(n_perm)}-draw permutation null of the within delta",
                     "per-fold deltas with signs", "DS-06 per-vintage signs",
                     "contributor AUC delta against its own floor",
                     "DS-03 balance probe on any missingness indicator"],
        "holm": {"family": "every registered (candidate, side) arm of the wave",
                 "m": len(candidates), "alpha": ALPHA,
                 "p": "permutation p of the within delta, one-sided",
                 "formed": "after every arm is measured (apply_holm_verdicts pattern)"},
        "admission_rule": ADMISSION_RULE,
        "verdicts": sorted(VERDICTS),
        "exploratory_verdict": EXPLORATORY_VERDICT,
        "not_arms": ["seasons_at_level_pit (owner DS-Q2; read on lv_dev in H0's pitcher "
                     "list; data/model_registry.json xfv_repeat_level)",
                     "vm_dev (rows at the debut year; every closed arm read there)",
                     "the 39 closed arms (data/xfv_arm_ledger.json)"],
    }


# ---------------------------------------------------------------------------
# the frame: training rows, test rows, scored rows, the base per fold
# ---------------------------------------------------------------------------

def w_star_dev(label_rows) -> dict:
    """The W3 contributor threshold on labels alone (tools/efv_v2_dev_read.w_star_dev)."""
    import efv_v2_dev_read as DR
    return DR.w_star_dev(label_rows)


class Frame:
    """Everything one wave run scores on. Built once; every candidate, noise column
    and twin reads the same rows and the same base."""

    def __init__(self, train: dict[str, list[dict]], tests: dict[tuple[str, int], list[dict]],
                 scored: dict[tuple[str, int], list[dict]], *, weights: dict,
                 folds=FOLDS, absent_ok: dict | None = None, label: dict | None = None,
                 counts: dict | None = None, w_star: dict | None = None):
        self.train = train
        self.tests = tests
        self.scored = scored
        self.weights = weights
        self.folds = tuple(int(v) for v in folds)
        self.absent_ok = absent_ok or {}
        self.label = label or {}
        self.counts = counts or {}
        self.w_star = w_star or {}
        self._fold_train: dict = {}
        self._base: dict = {}

    @classmethod
    def from_frames(cls, frames: dict, *, weights: dict, folds=FOLDS,
                    label: dict | None = None) -> "Frame":
        """{side: {V: (frame rows, labels)}} over the development vintages (the
        efv_v2_assemble.build_frames shape) into a Frame. Reserved vintages raise."""
        folds = tuple(int(v) for v in folds)
        train, tests, scored, counts = {}, {}, {}, {}
        labels_all = []
        for side in SIDES:
            by_v = frames[side]
            for V in by_v:
                F.guard_score_request(int(V), purpose="screening lab frame")
            train[side] = H.lv_training_rows(side, by_v)
            labels_all += [(int(V), lab) for V in by_v for lab in by_v[V][1]]
        ws = w_star_dev(labels_all)
        for side in SIDES:
            counts[side] = {}
            for V in folds:
                rows, labs = frames[side][V]
                test = H.lv_v2_rows(side, V, rows)
                tests[(side, V)] = test
                have = {r["player_key"] for r in test}
                sc, kept = [], 0
                for r, lab in zip(rows, labs):
                    k = r["player_key"]
                    g = r["grades"]
                    if g.get(CONS) is None or lab.get("w3") is None or k not in have:
                        continue
                    if lab.get("status") == "reserved_vm":
                        dy = lab.get("debut_year")
                        if lab["w3"] != 0.0 or (dy is not None
                                                and dy <= V + L.W_DEBUT_WINDOW):
                            raise F.ReservedFrameError(f"reserved_vm row in window: {k} {V}")
                        kept += 1
                    w3 = float(lab["w3"])
                    grades = {src: g[src] for src in SB.SCORED_SOURCES
                              if g.get(src) is not None}
                    sc.append({"key": k, "vintage": V, "side": side,
                               "group": f"{side}|{V}", "cons": float(g[CONS]),
                               "w3": w3, "contributor": bool(ws.get("w_star") is not None
                                                             and w3 >= ws["w_star"]),
                               "grades": grades})
                scored[(side, V)] = sc
                counts[side][str(V)] = {"rows": len(rows), "test_rows": len(test),
                                        "scored": len(sc),
                                        "reserved_vm_kept_w3_zero": kept}
        return cls(train, tests, scored, weights=weights, folds=folds, label=label,
                   counts=counts, w_star=ws)

    @classmethod
    def from_rows(cls, rows_by_side: dict[str, list[dict]], *, weights: dict,
                  folds=FOLDS, w_star: float | None = None,
                  absent_ok: dict | None = None) -> "Frame":
        """A Frame from labelled V2 rows alone (each carrying player_key,
        decision_year, fv, target, reached, v2): the rows at a fold year are its test
        rows, scored on target as W3. Synthetic fixtures and pins; the real run goes
        through from_frames."""
        folds = tuple(int(v) for v in folds)
        train, tests, scored, counts = {}, {}, {}, {}
        for side, rows in rows_by_side.items():
            train[side] = list(rows)
            counts[side] = {}
            for V in folds:
                F.guard_score_request(V, purpose="screening lab frame")
                at = [r for r in rows if int(r["decision_year"]) == V]
                tests[(side, V)] = [{k: v for k, v in r.items()
                                     if k not in ("target", "reached", "weight")}
                                    for r in at]
                scored[(side, V)] = [
                    {"key": r["player_key"], "vintage": V, "side": side,
                     "group": f"{side}|{V}", "cons": float(r["fv"]),
                     "w3": float(r["target"]),
                     "contributor": bool(w_star is not None and r["target"] >= w_star),
                     "grades": {}} for r in at]
                counts[side][str(V)] = {"rows": len(at), "test_rows": len(at),
                                        "scored": len(at), "reserved_vm_kept_w3_zero": 0}
        return cls(train, tests, scored, weights=weights, folds=folds,
                   absent_ok=absent_ok, counts=counts,
                   w_star={"w_star": w_star, "convention": "handed in"})

    # -- rows ---------------------------------------------------------------

    def fold_train(self, side: str, V: int) -> list[dict]:
        key = (side, int(V))
        if key not in self._fold_train:
            in_frame = {r["player_key"] for r in self.tests[key]}
            self._fold_train[key] = [r for r in self.train[side]
                                     if int(r["decision_year"]) < int(V)
                                     and r["player_key"] not in in_frame]
        return self._fold_train[key]

    def rows_of(self, side: str) -> list[dict]:
        """Every row carrying a column slot on the side: the training rows (all
        development vintages) and the test rows of every fold."""
        out = list(self.train[side])
        for V in self.folds:
            out += self.tests[(side, V)]
        return out

    def fit(self, side: str, V: int, extra: dict | None = None) -> dict:
        return H.fit_v2(self.fold_train(side, V), side, frame="lv", weights=self.weights,
                        absent_ok=self.absent_ok.get(side), extra=extra)

    def base(self, side: str, V: int) -> dict:
        """The base model and its order per player on the fold, fitted once."""
        key = (side, int(V))
        if key not in self._base:
            m = self.fit(side, V)
            order = {p["player_key"]: p["order_idx"]
                     for p in H.predict_v2(m, self.tests[key])}
            self._base[key] = {"model": m, "order": order}
        return self._base[key]

    # -- columns ------------------------------------------------------------

    def attach(self, side: str, key: str, values: dict) -> None:
        """values: {(V, player_key): float | None}. A row with no entry reads None."""
        for r in self.rows_of(side):
            r["v2"][key] = values.get((int(r["decision_year"]), r["player_key"]))

    def detach(self, side: str, key: str) -> None:
        for r in self.rows_of(side):
            r["v2"].pop(key, None)

    def slots(self, side: str) -> list[tuple[int, str]]:
        """Every (V, player_key) a column on the side may fill, in a fixed order."""
        return sorted({(int(r["decision_year"]), r["player_key"])
                       for r in self.rows_of(side)})


# ---------------------------------------------------------------------------
# one column through the pipeline
# ---------------------------------------------------------------------------

def _admission(train: list[dict], key: str, head: str) -> dict:
    """The DS-06 check exactly as fit_skill_head / fit_timing_head apply it."""
    if head == "skill":
        return H.admission_for_key(train, key, target="u_y", has_block_only=True)
    return H.admission_for_key(train, key, target="reached", has_block_only=False)


def _offered(frame: Frame, side: str, V: int, head: str) -> tuple[bool, str | None]:
    """A timing column is not offered on a pitcher fold whose base has no usable skill
    head (owner DS-Q2: pitchers take the consensus order there)."""
    base = frame.base(side, V)["model"]
    if head == "timing" and side == "pit" and not H.head_usable(base["skill"]):
        return False, base.get("consensus_only_reason") or "owner DS-Q2"
    return True, None


def run_column(frame: Frame, side: str, head: str, key: str, *, force: bool = False) -> dict:
    """The candidate order per fold for one attached column: refused folds reuse the
    base order (no refit), admitted folds refit the assembly with the column offered to
    `head`. `force` admits the column without the rule (the floor derivation only).
    Returns {"order": {(V, pk): idx}, "folds": {V: receipt}}."""
    order: dict = {}
    folds: dict = {}
    for V in frame.folds:
        base = frame.base(side, V)
        tr = frame.fold_train(side, V)
        offered, why = _offered(frame, side, V, head)
        rec = {"offered": offered, "admitted": False, "reason": why, "forced": bool(force)}
        if offered and force:
            rec.update({"admitted": True,
                        "reason": "forced: admission bypassed (floor derivation)"})
        elif offered:
            chk = _admission(tr, key, head)
            rec.update({"admitted": bool(chk["admitted"]), "reason": chk["reason"],
                        "per_vintage_signs": chk["per_vintage_signs"],
                        "mean_abs_t": chk["mean_abs_t"],
                        "n_valid_vintages": chk["n_valid_vintages"]})
        if rec["admitted"]:
            m = frame.fit(side, V, extra={head: (key,), "force": bool(force)})
            fitted = ((m.get(head) or {}).get("admission") or {}).get(key) or {}
            if not fitted.get("admitted"):
                raise RuntimeError(f"{side} {V} {head} {key}: the fitted head disagrees "
                                   "with the admission check")
            rec["head_keys"] = list((m.get(head) or {}).get("keys") or [])
            rec["head_alpha"] = H._akey((m.get(head) or {}).get("alpha", math.inf))
            for p in H.predict_v2(m, frame.tests[(side, V)]):
                order[(V, p["player_key"])] = p["order_idx"]
        else:
            for pk, idx in base["order"].items():
                order[(V, pk)] = idx
        folds[str(V)] = rec
    return {"order": order, "folds": folds}


def _columns(frame: Frame, sides, cand_order: dict, base_order: dict | None = None):
    """The paired columns on the scored rows of `sides`, in one fixed order."""
    keys, groups, y, pos, a, b, cons, grades = [], [], [], [], [], [], [], []
    for side in sides:
        for V in frame.folds:
            bo = base_order if base_order is not None else frame.base(side, V)["order"]
            for c in frame.scored[(side, V)]:
                ca = cand_order.get((V, c["key"]))
                cb = bo.get(c["key"]) if base_order is None else bo.get((V, c["key"]))
                if ca is None or cb is None:
                    continue
                keys.append(c["key"])
                groups.append(c["group"])
                y.append(c["w3"])
                pos.append(bool(c["contributor"]))
                a.append(float(ca))
                b.append(float(cb))
                cons.append(c["cons"])
                grades.append(c["grades"])
    return keys, groups, y, pos, a, b, cons, grades


def _delta(cols, statistic: str, *, B: int, seed: int) -> dict:
    keys, groups, y, pos, a, b, cons, _g = cols
    d = S.paired_delta(keys, groups, y, pos, a, b, cons, statistic=statistic, B=B,
                       seed=seed)
    if d.get("delta") is not None and d.get("mde95") is not None:
        d["lb95"] = round(float(d["delta"]) - float(d["mde95"]), 5)
    else:
        d["lb95"] = None
    d["reading"] = S.reading(d.get("ci95"))
    return d


def _fold_deltas(cols) -> dict:
    """The within rho of candidate and base inside each (side, vintage) group."""
    keys, groups, y, pos, a, b, cons, _g = cols
    codes = np.asarray([str(g) for g in groups])
    keep = S.kept_groups(codes, S.MIN_GROUP_ROWS)
    out = {}
    for u in sorted(str(k) for k in keep):
        ix = np.where(codes == u)[0]
        wa, n, _ = S.within(np.asarray(a), np.asarray(y), codes, [u], ix)
        wb, _, _ = S.within(np.asarray(b), np.asarray(y), codes, [u], ix)
        d = None if (wa is None or wb is None) else round(wa - wb, 5)
        out[u] = {"n": int(n), "candidate": None if wa is None else round(wa, 5),
                  "base": None if wb is None else round(wb, 5), "delta": d,
                  "sign": (0 if not d else (1 if d > 0 else -1))}
    return out


def _within_point(cols) -> float | None:
    keys, groups, y, pos, a, b, cons, _g = cols
    codes = np.asarray([str(g) for g in groups])
    keep = S.kept_groups(codes, S.MIN_GROUP_ROWS)
    wa, _, _ = S.within(np.asarray(a), np.asarray(y), codes, keep)
    wb, _, _ = S.within(np.asarray(b), np.asarray(y), codes, keep)
    return None if (wa is None or wb is None) else wa - wb


def measure(frame: Frame, side: str, head: str, key: str, values: dict, *,
            B: int, seed: int = SEED, force: bool = False) -> dict:
    """One column (already built) through admission, refit, score and the three
    paired bootstraps against the base. `side` may be BOTH (the column attached to
    both sides, offered to `head` on each). `force` is the floor derivation's only."""
    sides = SIDES if side == BOTH else (side,)
    order: dict = {}
    folds: dict = {}
    for s in sides:
        frame.attach(s, key, values)
        try:
            r = run_column(frame, s, head, key, force=force)
        finally:
            frame.detach(s, key)
        order.update(r["order"])
        folds.update({f"{s}|{V}": rec for V, rec in r["folds"].items()}
                     if side == BOTH else r["folds"])
    cols = _columns(frame, sides, order)
    out = {"n": len(cols[0]), "folds": folds,
           "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
           "n_folds": len(folds),
           "within": _delta(cols, "within", B=B, seed=seed),
           "pooled": _delta(cols, "pooled", B=B, seed=seed),
           "auc": _delta(cols, "auc", B=B, seed=seed),
           "fold_deltas": _fold_deltas(cols)}
    signs = {f["sign"] for f in out["fold_deltas"].values() if f["sign"]}
    out["fold_signs_agree"] = len(signs) <= 1
    out["order"] = order
    return out


# ---------------------------------------------------------------------------
# values: noise, permutation, frame columns, builders
# ---------------------------------------------------------------------------

def _seed_for(name: str, salt: int = 0) -> int:
    h = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
    return int((SEED + h + salt) % (2 ** 31 - 1))


def noise_values(frame: Frame, side: str, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    sides = SIDES if side == BOTH else (side,)
    out = {}
    for s in sides:
        for slot in frame.slots(s):
            out[slot] = float(rng.standard_normal())
    return out


def permuted_values(values: dict, seed: int) -> dict:
    """The column permuted within vintage over the slots it fills (the player set and
    the vintage marginal are kept; the link to the row is broken)."""
    rng = np.random.default_rng(seed)
    by: dict = {}
    for (V, pk), v in values.items():
        by.setdefault(int(V), []).append(((V, pk), v))
    out = {}
    for V in sorted(by):
        items = sorted(by[V], key=lambda kv: kv[0][1])
        vals = [v for _k, v in items]
        perm = rng.permutation(len(vals))
        for (slot, _v), j in zip(items, perm):
            out[slot] = vals[int(j)]
    return out


def _transform(v, how: str | None):
    if v is None:
        return None
    x = float(v)
    if how == "log1p":
        return math.log1p(max(x, 0.0))
    if how in (None, "identity"):
        return x
    raise ValueError(f"unknown transform {how!r}")


def frame_key_values(frames: dict, side: str, key: str, transform: str | None = None,
                     vintages=F.DEV_VINTAGES) -> dict:
    """{(V, player_key): value | None} off the frame rows of the side."""
    out = {}
    for V in vintages:
        rows = (frames.get(side) or {}).get(int(V))
        if rows is None:
            continue
        for r in rows[0]:
            out[(int(V), r["player_key"])] = _transform(r.get(key), transform)
    return out


_REPORTS_CACHE: dict = {}


def _reports_for(vs, *, T) -> dict:
    """efv_text_features.load_reports over the vintages, read once per range (a year
    before the first vintage, so a carried-forward report is seen)."""
    lo, hi = f"{min(vs) - 1}-01-01", f"{max(vs)}-05-01"
    if (lo, hi) not in _REPORTS_CACHE:
        _REPORTS_CACHE[(lo, hi)] = T.load_reports(lo=lo, hi=hi)
    return _REPORTS_CACHE[(lo, hi)]


def text_column_values(head: str, side: str, frames: dict, *, reports: dict | None = None,
                       train: list[dict] | None = None,
                       balance_path: Path | None = None) -> dict:
    """{(V, player_key): value | None} for one text head on one side, stacked out of
    vintage (module docstring): at each vintage v the text fit of
    efv_text_features.fold_columns is trained on the labelled rows of the text vintages
    strictly below v with every v-frame player excluded, and scores the v rows. `train`
    is the labelled row list (efv_v2_model.lv_training_rows: player_key, decision_year,
    fv, target = W3, reached = R3); it is built from `frames` when not handed in. A head
    withheld on the side (efv_text_features.offered_columns, the DS-03 verdict on
    report_absent) raises ColumnUnavailable before any read."""
    import efv_text_features as T
    if head not in T.COLUMN_HEADS:
        raise ValueError(f"head must be one of {T.COLUMN_HEADS}, got {head!r}")
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")
    name = T.column_name(head, side)
    if head not in T.offered_columns(side, balance_path):
        raise ColumnUnavailable(
            f"{name} withheld: report_absent reads {T.balance_verdict(side, balance_path)!r} "
            f"on {side} (efv_text_features.offered_columns, gate s10.7)")
    by_v = frames.get(side) or {}
    vs = sorted(int(V) for V in by_v)
    if not vs:
        raise ColumnUnavailable(f"no frames on side {side}")
    for V in vs:
        F.guard_score_request(V, purpose="text column")
    reports = _reports_for(vs, T=T) if reports is None else reports
    if train is None:
        train = H.lv_training_rows(side, by_v)
    text: dict = {}
    for V in vs:
        for r in T.attach_text(by_v[V][0], reports):
            text[(V, r["player_key"])] = r.get("report_text")
    labelled = {(int(r["decision_year"]), r["player_key"]): r for r in train}
    out: dict = {}
    for V in vs:
        rows_v = by_v[V][0]
        in_frame = {r["player_key"] for r in rows_v}
        for r in rows_v:
            out[(V, r["player_key"])] = None
        if V in T.DROPPED_VINTAGES:
            continue
        tr_keys = sorted((v, pk) for (v, pk) in labelled
                         if T.FIRST_TEXT_VINTAGE <= v < V and pk not in in_frame)
        if not tr_keys:
            continue
        tr = [{"player_key": pk, "vintage": v, "fv": float(labelled[(v, pk)]["fv"]),
               "report_text": text.get((v, pk))} for (v, pk) in tr_keys]
        target = [labelled[k]["target"] for k in tr_keys]
        event = [labelled[k]["reached"] for k in tr_keys]
        test = [{"player_key": r["player_key"], "vintage": V,
                 "fv": (r.get("grades") or {}).get(CONS),
                 "report_text": text.get((V, r["player_key"]))} for r in rows_v]
        res = T.fold_columns(side, V, tr, test, target=target, event=event, offered=(head,))
        for r in rows_v:
            v = (res["columns"].get(r["player_key"]) or {}).get(name)
            out[(V, r["player_key"])] = None if v is None else float(v)
    return out


def column_values(cand: dict, frames: dict) -> dict:
    """The candidate's values on its side(s), by its declared source."""
    spec = cand["column"]
    src = spec.get("source")
    sides = SIDES if cand["side"] == BOTH else (cand["side"],)
    if src == "text":
        try:
            __import__(spec.get("module") or "efv_text_features")
        except ImportError as exc:
            raise ColumnUnavailable(f"builder module {spec.get('module')} absent: {exc}")
        out = {}
        for s in sides:
            out.update(text_column_values(spec["head"], s, frames))
        if all(v is None for v in out.values()):
            raise ColumnUnavailable(f"text head {spec['head']!r} carries no value on "
                                    f"{', '.join(sides)}")
        return out
    if src == "frame_key":
        out = {}
        for s in sides:
            vals = frame_key_values(frames, s, spec["key"], spec.get("transform"))
            if all(v is None for v in vals.values()):
                raise ColumnUnavailable(f"frame key {spec['key']!r} carries no value "
                                        f"on side {s}")
            out.update(vals)
        return out
    if src == "module":
        try:
            mod = __import__(spec["module"])
        except ImportError as exc:
            raise ColumnUnavailable(f"builder module {spec['module']} absent: {exc}")
        fn = getattr(mod, spec["attr"], None)
        if fn is None:
            raise ColumnUnavailable(f"{spec['module']}.{spec['attr']} absent")
        out = {}
        for s in sides:
            vals = fn(spec.get("arg"), s, frames) if spec.get("arg") else fn(s, frames)
            out.update({(int(V), pk): (None if v is None else float(v))
                        for (V, pk), v in dict(vals).items()})
        return out
    raise ColumnUnavailable(f"unknown column source {src!r}")


def _missing_indicator(values: dict, slots) -> dict:
    return {slot: (1.0 if values.get(slot) is None else 0.0) for slot in slots}


# ---------------------------------------------------------------------------
# the DS-03 balance probe (tools/efv_identity_balance.balance pattern)
# ---------------------------------------------------------------------------

def balance_probe(frame: Frame, side: str, indicator: dict, *, seed: int,
                  B: int = B_BAL) -> dict:
    """The indicator's partial coefficient in a linear probability model of W3 > 0 on
    the within-(side, vintage) consensus percentile (a quadratic) and vintage effects,
    with a player-clustered bootstrap CI95. BALANCED when the CI95 covers zero."""
    rows = [r for r in frame.train[side] if r.get("target") is not None]
    if not rows:
        return {"verdict": "CONSTANT", "n": 0}
    x = np.array([indicator.get((int(r["decision_year"]), r["player_key"]), 0.0)
                  for r in rows], dtype=np.float64)
    n1 = int(x.sum())
    out = {"n": len(rows), "n_with": n1, "n_without": len(rows) - n1}
    if n1 == 0 or n1 == len(rows):
        out.update({"verdict": "CONSTANT", "partial": None, "ci95": None})
        return out
    yrs = [int(r["decision_year"]) for r in rows]
    u = H.within_pct([r["fv"] for r in rows], yrs)
    ypos = np.array([float(r["target"] > 0) for r in rows])
    vs = sorted(set(yrs))
    dummies = (np.column_stack([[float(y == v) for y in yrs] for v in vs[1:]])
               if len(vs) > 1 else np.zeros((len(rows), 0)))
    X = np.column_stack([np.ones(len(rows)), u, u ** 2, dummies, x])
    by: dict = {}
    for i, r in enumerate(rows):
        by.setdefault(r["player_key"], []).append(i)
    cl = [np.array(v) for _k, v in sorted(by.items())]

    def coef(ix):
        b, *_ = np.linalg.lstsq(X[ix], ypos[ix], rcond=None)
        return float(b[-1])
    point = coef(np.arange(len(rows)))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(int(B)):
        pick = rng.integers(0, len(cl), len(cl))
        ix = np.concatenate([cl[j] for j in pick])
        if x[ix].min() == x[ix].max():
            continue
        draws.append(coef(ix))
    m1, m0 = x == 1, x == 0
    out.update({"w3_pos_share_with": round(float(ypos[m1].mean()), 4),
                "w3_pos_share_without": round(float(ypos[m0].mean()), 4)})
    if len(draws) < 2:
        out.update({"verdict": "CONSTANT", "partial": round(point, 4), "ci95": None})
        return out
    lo, hi = float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))
    out.update({"partial": round(point, 4), "ci95": [round(lo, 4), round(hi, 4)],
                "B_used": len(draws), "seed": int(seed),
                "verdict": "BALANCED" if lo <= 0 <= hi else "IMBALANCED"})
    return out


# ---------------------------------------------------------------------------
# floors (step 2): derived before any arm
# ---------------------------------------------------------------------------

def _max_or_none(vals):
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def derive_floors(frame: Frame, *, B: int, sides=(*SIDES, BOTH), heads=HEADS,
                  n_noise: int = N_NOISE, mode: str = FLOOR_MODE_DEFAULT) -> dict:
    """{head: {side: {within, pooled, auc, status, noise: [...]}}, "mode": mode}. The
    floor of a leg is the MAX mde95 over the noise columns. In mode "admitted" a noise
    column refused in every fold is the base (mde95 0 by construction) and a side with
    no admitted noise column has no floor (None, never 0); in mode "forced" every noise
    column is refit."""
    if mode not in FLOOR_MODES:
        raise ValueError(f"floor mode must be one of {FLOOR_MODES}, got {mode!r}")
    out: dict = {"mode": mode}
    for head in heads:
        out[head] = {}
        for side in sides:
            receipts = []
            for i in range(int(n_noise)):
                seed = _seed_for(f"noise:{head}:{side}:{i}")
                vals = noise_values(frame, side, seed)
                m = measure(frame, side, head, f"{H.V2_SCREEN_PREFIX}noise{i}", vals,
                            B=B, force=(mode == "forced"))
                receipts.append({"i": i, "seed": seed, "admitted_folds": m["admitted_folds"],
                                 "n_folds": m["n_folds"],
                                 "within": {k: m["within"].get(k) for k in
                                            ("delta", "mde95", "sd", "ci95", "lb95")},
                                 "pooled": {k: m["pooled"].get(k) for k in
                                            ("delta", "mde95")},
                                 "auc": {k: m["auc"].get(k) for k in ("delta", "mde95")},
                                 "folds": {V: {"admitted": f["admitted"], "reason": f["reason"]}
                                           for V, f in m["folds"].items()}})
            any_admitted = any(r["admitted_folds"] for r in receipts)
            # a noise column refused in every fold is the base, so its mde95 is 0 by
            # construction; with no admitted noise column there is no floor at all
            # (None, never 0: a floor of 0 would be cleared by anything)
            blk = {leg: (_max_or_none([r[leg]["mde95"] for r in receipts])
                         if any_admitted else None)
                   for leg in ("within", "pooled", "auc")}
            blk["noise"] = receipts
            blk["n_noise"] = len(receipts)
            blk["mode"] = mode
            blk["rule"] = "MAX mde95 over the noise columns, per leg"
            blk["status"] = ("derived" if any_admitted else
                             "degenerate: no noise column was admitted in any fold, so "
                             "every noise delta is identically 0")
            out[head][side] = blk
    return out


def floor_for(floors: dict, head: str | None, side: str, leg: str) -> float | None:
    """The floor an arm is read against. A coverage arm (no head, side BOTH) takes the
    larger of the two heads' floors on the pooled rows."""
    if head is None:
        return _max_or_none([((floors.get(h) or {}).get(side) or {}).get(leg)
                             for h in HEADS])
    return ((floors.get(head) or {}).get(side) or {}).get(leg)


# ---------------------------------------------------------------------------
# arms (step 3): measure every arm; verdicts only after the family exists
# ---------------------------------------------------------------------------

def _leg(delta: float | None, floor: float | None) -> dict:
    if delta is None:
        return {"delta": None, "floor": floor, "state": "not measured"}
    if floor is None:
        return {"delta": delta, "floor": None, "state": "no floor derived"}
    f = float(floor)
    return {"delta": delta, "floor": round(f, 5),
            "clears": bool(delta >= f), "adverse_beyond_floor": bool(delta <= -f),
            "state": ("clears" if delta >= f else "adverse beyond floor"
                      if delta <= -f else "inside floor")}


def permutation_null(frame: Frame, side: str, head: str, key: str, values: dict,
                     observed: float | None, *, n_perm: int, seed: int) -> dict:
    """n_perm permutations of the column within vintage, each through the identical
    admission and refit, read on the within delta against the base (point only).
    p = (1 + #(null >= observed)) / (1 + n_perm), one-sided."""
    sides = SIDES if side == BOTH else (side,)
    null = []
    admitted = 0
    for i in range(int(n_perm)):
        pv = permuted_values(values, seed + i)
        order: dict = {}
        for s in sides:
            frame.attach(s, key, pv)
            try:
                r = run_column(frame, s, head, key)
            finally:
                frame.detach(s, key)
            order.update(r["order"])
            admitted += sum(1 for f in r["folds"].values() if f["admitted"])
        d = _within_point(_columns(frame, sides, order))
        null.append(0.0 if d is None else float(d))
    if observed is None or not null:
        return {"n": len(null), "p": None, "seed": int(seed), "status": "not derived"}
    arr = np.asarray(null, dtype=np.float64)
    p = (1.0 + float((arr >= float(observed)).sum())) / (1.0 + arr.size)
    return {"n": int(arr.size), "p": round(p, 5), "seed": int(seed),
            "observed": round(float(observed), 5),
            "null_mean": round(float(arr.mean()), 5), "null_sd": round(float(arr.std()), 5),
            "null_q95": round(float(np.quantile(arr, 0.95)), 5),
            "admitted_fold_draws": int(admitted),
            "fold_draws": int(arr.size * len(sides) * len(frame.folds)),
            "status": "derived"}


def _rater_block(frame: Frame, sides, cand_order: dict, base_order: dict | None = None) -> dict:
    """Rater stats (within, pooled, AUC) on the scored rows: the candidate, the base,
    consensus and each scored source on the rows it grades."""
    cols = _columns(frame, sides, cand_order, base_order)
    keys, groups, y, pos, a, b, cons, grades = cols
    out = {}

    def stats(score, ix):
        st = S.rater_stats([score[i] for i in ix], [y[i] for i in ix],
                           [pos[i] for i in ix], [groups[i] for i in ix],
                           [cons[i] for i in ix])
        return {"spearman": st["within"], "auc": st["auc"], "n": st["n"],
                "within": st["within"], "pooled": st["pooled"],
                "within_rows": st["within_rows"], "within_groups": st["within_groups"]}
    every = list(range(len(keys)))
    out["efv_v2_candidate"] = stats(a, every)
    out["efv_v2_base"] = stats(b, every)
    out["prospx_consensus"] = stats(cons, every)
    for src in SB.SCORED_SOURCES:
        ix = [i for i in every if grades[i].get(src) is not None]
        if ix:
            out[src] = stats([grades[i].get(src) for i in every], ix)
    return out


def _vs_consensus(frame: Frame, sides, order: dict, *, B: int,
                  base_order: dict | None = None) -> dict:
    cols = _columns(frame, sides, order, base_order)
    keys, groups, y, pos, a, b, cons, _g = cols
    cc = (keys, groups, y, pos, a, list(cons), cons, _g)
    return {"spearman": _delta(cc, "within", B=B, seed=SEED),
            "pooled": _delta(cc, "pooled", B=B, seed=SEED),
            "auc": _delta(cc, "auc", B=B, seed=SEED)}


def measure_arm(frame: Frame, cand: dict, values: dict, floors: dict, *, B: int,
                n_perm: int, base_vs_cons: dict | None = None) -> dict:
    """Every number one arm carries. No verdict is formed here."""
    side, head, name = cand["side"], cand["head"], cand["name"]
    sides = SIDES if side == BOTH else (side,)
    key = CANDIDATE_KEY
    m = measure(frame, side, head, key, values, B=B)
    tw_seed = _seed_for(f"twin:{name}")
    twin = measure(frame, side, head, key, permuted_values(values, tw_seed), B=B)
    perm = permutation_null(frame, side, head, key, values, m["within"].get("delta"),
                            n_perm=n_perm, seed=_seed_for(f"perm:{name}", 1))
    f_w, f_p, f_a = (floor_for(floors, head, side, leg) for leg in ("within", "pooled", "auc"))
    slots = [s for sd in sides for s in frame.slots(sd)]
    n_missing = sum(1 for s in slots if values.get(s) is None)
    balance = None
    if n_missing:
        ind = _missing_indicator(values, slots)
        balance = {s: balance_probe(frame, s, ind, seed=_seed_for(f"balance:{name}:{s}"))
                   for s in sides}
    arm = {
        "tag": f"SCREEN-W{WAVE}:{side}.{head or 'coverage'}.{name}",
        "name": name, "side": side, "head": head, "kind": cand["kind"],
        "retest": bool(cand.get("retest")), "what": cand.get("what"),
        "model_id": f"{MODEL_ID}:{name}:{side}",
        "measured": True, "unavailable": None,
        "column": {"key": key, "source": cand["column"], "n_slots": len(slots),
                   "n_observed": len(slots) - n_missing, "n_missing": n_missing},
        "n": m["n"], "folds": m["folds"], "admitted_folds": m["admitted_folds"],
        "n_folds": m["n_folds"], "fold_deltas": m["fold_deltas"],
        "fold_signs_agree": m["fold_signs_agree"],
        "within": dict(m["within"], floor=f_w),
        "pooled": dict(m["pooled"], floor=f_p),
        "auc": dict(m["auc"], floor=f_a),
        "legs": {"within": _leg(m["within"].get("delta"), f_w),
                 "pooled": _leg(m["pooled"].get("delta"), f_p),
                 "auc": _leg(m["auc"].get("delta"), f_a)},
        "twin": {"seed": tw_seed, "admitted_folds": twin["admitted_folds"],
                 "within": {k: twin["within"].get(k) for k in
                            ("delta", "mde95", "ci95", "lb95")},
                 "auc_delta": twin["auc"].get("delta"),
                 "inside_floor": (None if (f_w is None or twin["within"].get("delta") is None)
                                  else bool(abs(twin["within"]["delta"]) < f_w))},
        "permutation_null": perm,
        "balance": balance,
        # ledger-compatible spellings (tools/efv_arm_ledger.py)
        "delta": {"rho": m["within"].get("delta"), "pooled": m["pooled"].get("delta"),
                  "auc_contrib": m["auc"].get("delta")},
        "floor_rho": f_w,
        "per_vintage_signs": {V: f.get("per_vintage_signs") for V, f in m["folds"].items()},
        "verdict": None, "clauses": None, "not_adjudicated": [], "holm_joint_row": None,
        "_order": m["order"],
    }
    # the progress-ledger frame block (efv_progress.screen_arm_docs copies it)
    raters = _rater_block(frame, sides, m["order"])
    vs_c = _vs_consensus(frame, sides, m["order"], B=B)
    bvc = base_vs_cons or {}
    deltas = {"candidate_vs_efv_v2_base": {"spearman": arm["within"], "pooled": arm["pooled"],
                                           "auc": arm["auc"]},
              "candidate_vs_prospx_consensus": vs_c}
    if bvc.get(side):
        deltas["efv_v2_base_vs_prospx_consensus"] = bvc[side]
    n_by_side = {}
    for s in sides:
        n_by_side[s] = sum(len(frame.scored[(s, V)]) for V in frame.folds)
    arm["frame"] = {
        "frame_version": "lv1_v2", "window": [min(frame.folds), max(frame.folds)],
        "n": m["n"], "n_by_side": n_by_side,
        "n_players": len({k for (_V, k) in m["order"]}),
        "groups": sorted({f"{s}|{V}" for s in sides for V in frame.folds}),
        "statistic": S.STAT_LABEL[S.PRIMARY], "raters": raters, "deltas": deltas,
        "secondary": {"statistic": S.STAT_LABEL["pooled"],
                      "raters": {n: r.get("pooled") for n, r in raters.items()},
                      "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                                     "ci95": (d.get("pooled") or {}).get("ci95"),
                                     "mde95": (d.get("pooled") or {}).get("mde95"),
                                     "reading": (d.get("pooled") or {}).get("reading")}
                                 for n, d in deltas.items()}},
        "verdict": None, "note": NOTE}
    return arm


def unavailable_arm(cand: dict, why: str) -> dict:
    side, head, name = cand["side"], cand["head"], cand["name"]
    return {"tag": f"SCREEN-W{WAVE}:{side}.{head or 'coverage'}.{name}",
            "name": name, "side": side, "head": head, "kind": cand["kind"],
            "retest": bool(cand.get("retest")), "what": cand.get("what"),
            "model_id": f"{MODEL_ID}:{name}:{side}",
            "measured": False, "unavailable": why, "column": {"source": cand["column"]},
            "verdict": None, "clauses": None,
            "not_adjudicated": [f"column not built on this tree: {why}"],
            "holm_joint_row": None}


# ---------------------------------------------------------------------------
# Holm (step 4) and the verdicts (step 5)
# ---------------------------------------------------------------------------

def holm_adjust(pvals: dict[str, float | None], m: int, alpha: float = ALPHA) -> dict:
    """Holm step-down over a family of size m (the registered size; an arm with no p
    is absent from the ordering and never survives). Returns per key the adjusted p,
    rank and survival."""
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


def screen_verdict(arm: dict, holm_row: dict | None) -> dict:
    """The verdict of one measured arm against the floors it was measured against and
    its row of the Holm family. Emits one of VERDICTS and nothing else."""
    legs = arm["legs"]
    rho, auc, pooled = legs["within"], legs["auc"], legs["pooled"]
    w = arm["within"]
    UNMEASURED = ("no floor derived", "not measured")
    holm = None if holm_row is None else holm_row.get("survives_holm")
    lb = w.get("lb95")
    coverage = arm.get("kind") == "coverage"
    clauses = {
        "a_lb95_above_0_and_point_at_floor": bool(lb is not None and lb > 0
                                                  and rho.get("clears")),
        "b_holm_p_below_alpha": holm,
        # a frame change has no column: (c) and (d) do not apply and read as met
        "c_twin_inside_floor": (True if coverage else arm["twin"].get("inside_floor")),
        "d_admitted_every_fold_one_sign": (
            bool(arm["fold_signs_agree"]) if coverage else
            bool(arm["admitted_folds"] == arm["n_folds"] and arm["n_folds"] > 0
                 and arm["fold_signs_agree"])),
        "e_auc_not_adverse": (None if auc["state"] in UNMEASURED
                              else not auc.get("adverse_beyond_floor")),
        "f_missingness_balanced": (True if not arm.get("balance") else
                                   all((b or {}).get("verdict") in ("BALANCED", "CONSTANT")
                                       for b in arm["balance"].values())),
        "g_pooled_not_adverse": (None if pooled["state"] in UNMEASURED
                                 else not pooled.get("adverse_beyond_floor")),
    }
    missing = []
    if auc["state"] in UNMEASURED:
        missing.append("contributor AUC: " + auc["state"])
    if holm is None:
        missing.append("Holm family survival: not supplied")
    gate = bool(clauses["a_lb95_above_0_and_point_at_floor"]
                and clauses["c_twin_inside_floor"] is True
                and clauses["d_admitted_every_fold_one_sign"]
                and clauses["f_missingness_balanced"]
                and clauses["g_pooled_not_adverse"] is not False)
    if rho["state"] in UNMEASURED:
        verdict = "NOT_ADJUDICATED_NO_RHO_FLOOR"
    elif not gate:
        verdict = "NULL_AUC_ONLY" if auc.get("clears") else "NULL"
    elif auc.get("adverse_beyond_floor"):
        verdict = "VETO_ON_AUC"
    elif holm is False:
        verdict = "NULL_HOLM"
    elif auc["state"] in UNMEASURED:
        verdict = "NOT_ADJUDICATED_NO_AUC_FLOOR"
    elif holm is None:
        verdict = "NOT_ADJUDICATED_NO_HOLM"
    else:
        verdict = "PASS"
    assert verdict in VERDICTS
    return {"verdict": verdict, "clauses": clauses, "not_adjudicated": missing,
            "rule": ("the composite gate (a), (c), (d), (f), (g) plays the role of 'rho "
                     "clears'; contributor AUC may veto and may never credit; Holm "
                     "is applied after every arm is measured")}


def apply_verdicts(arms: list[dict], *, m: int, exploratory: bool) -> dict:
    """SECOND PASS: the family is formed over every arm, then each arm's verdict. The
    only place an arm's `verdict` is written."""
    pvals = {a["tag"]: ((a.get("permutation_null") or {}).get("p") if a["measured"]
                        else None) for a in arms}
    holm = holm_adjust(pvals, m)
    for a in arms:
        row = holm.get(a["tag"])
        if a["measured"]:
            a["within"]["p_perm"] = (a.get("permutation_null") or {}).get("p")
            a["within"]["holm_p"] = (row or {}).get("holm_p")
            a["holm_joint_row"] = a["tag"] if (row or {}).get("p") is not None else None
        if exploratory:
            a["verdict"] = EXPLORATORY_VERDICT
            a["clauses"] = None
            a["not_adjudicated"] = (a.get("not_adjudicated") or []) + [
                "exploratory run: no verdict formed, nothing admitted (EFV3_B5)"]
        elif a["measured"]:
            v = screen_verdict(a, row)
            a.update(v)
        else:
            # never run: no verdict to spell (not an absence state of the standard,
            # which all describe an arm that was measured); never PASS
            a["verdict"] = None
        if "frame" in a:
            a["frame"]["verdict"] = a["verdict"]
            a["frame"]["deltas"]["candidate_vs_efv_v2_base"]["spearman"] = a["within"]
        a["screening"] = {"wave": WAVE, "head": a["head"],
                          "admitted_folds": a.get("admitted_folds"),
                          "twin_inside_floor": (a.get("twin") or {}).get("inside_floor"),
                          "exploratory": bool(exploratory)}
    return {"m": m, "alpha": ALPHA, "p_source": "permutation p of the within delta, one-sided",
            "formed_after_every_arm": True, "rows": holm,
            "verdicts": {a["tag"]: a["verdict"] for a in arms}}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def build_frames_with(overrides: dict | None = None) -> dict:
    """efv_v2_assemble.build_frames with efv_vintage_frame attributes overridden for
    the build (the coverage arm). An attribute the tree lacks raises ColumnUnavailable."""
    import efv_v2_assemble as ASM
    overrides = overrides or {}
    saved = {}
    for k, v in overrides.items():
        if not hasattr(F, k):
            raise ColumnUnavailable(f"efv_vintage_frame.{k} absent on this tree")
        saved[k] = getattr(F, k)
        setattr(F, k, v)
    try:
        return ASM.build_frames()
    finally:
        for k, v in saved.items():
            setattr(F, k, v)


def frame_floor_receipt(frames: dict) -> dict:
    """The MiLB floor the rows of each side were read at (the `milb_floor` key every
    F-LV row carries) and the rows with a block, per vintage. Counts only."""
    out: dict = {}
    for side in SIDES:
        by_v = frames.get(side) or {}
        floors: set = set()
        blocks = {}
        for V in sorted(by_v):
            rows = by_v[V][0]
            floors |= {int(r["milb_floor"]) for r in rows if r.get("milb_floor") is not None}
            blocks[str(int(V))] = {"rows": len(rows),
                                   "with_milb_block": sum(1 for r in rows if r.get("milb"))}
        out[side] = {"milb_floor": sorted(floors), "by_vintage": blocks}
    return out


def coverage_frames(frame: Frame, cand: dict, weights: dict) -> dict:
    """The coverage arm's two Frames: the candidate on frames built with the named
    attribute at `candidate`, the base on frames built with it at `base`. Each carries
    its floor receipt."""
    spec = cand["column"]
    out = {}
    for role in ("candidate", "base"):
        raw = build_frames_with({spec["attr"]: spec[role]})
        fr = Frame.from_frames(raw, weights=weights, folds=frame.folds, label=frame.label)
        fr.absent_ok = dict(frame.absent_ok)
        out[role] = {"frame": fr, "receipt": frame_floor_receipt(raw),
                     "override": {spec["attr"]: spec[role]}}
    return out


def coverage_orders(fr: Frame) -> dict:
    """{(V, player_key): base order_idx} over both sides and every fold of a Frame."""
    order = {}
    for s in SIDES:
        for V in fr.folds:
            for pk, idx in fr.base(s, V)["order"].items():
                order[(V, pk)] = idx
    return order


def coverage_values(frame: Frame, cand: dict, weights: dict, *, B: int | None = None,
                    built: dict | None = None) -> tuple[dict, dict, dict]:
    """A coverage arm is not a column: the candidate is the base assembly refit and
    scored on frames built at `candidate`, paired row by row with the same refit on
    frames built at `base`. Returns (built frames, candidate order, base order)."""
    built = coverage_frames(frame, cand, weights) if built is None else built
    return (built, coverage_orders(built["candidate"]["frame"]),
            coverage_orders(built["base"]["frame"]))


def measure_coverage_arm(frame: Frame, cand: dict, weights: dict, floors: dict, *,
                         B: int, built: dict | None = None) -> dict:
    """The coverage arm's numbers: candidate order from the frames built at
    `candidate`, base order from the frames built at `base`, paired on the players
    both score, read on the shared frame's scored rows (label, consensus, contributor
    flag). No permutation null (no column to permute) and no twin: both are recorded
    as not applicable. `built` hands in the two Frames (tests)."""
    built, order, base_order = coverage_values(frame, cand, weights, B=B, built=built)
    side, name = cand["side"], cand["name"]
    cols = _columns(frame, SIDES, order, base_order)
    within = _delta(cols, "within", B=B, seed=SEED)
    pooled = _delta(cols, "pooled", B=B, seed=SEED)
    auc = _delta(cols, "auc", B=B, seed=SEED)
    f_w, f_p, f_a = (floor_for(floors, None, side, leg) for leg in ("within", "pooled", "auc"))
    fd = _fold_deltas(cols)
    signs = {f["sign"] for f in fd.values() if f["sign"]}
    arm = {
        "tag": f"SCREEN-W{WAVE}:{side}.coverage.{name}",
        "name": name, "side": side, "head": None, "kind": "coverage",
        "retest": False, "what": cand.get("what"),
        "model_id": f"{MODEL_ID}:{name}:{side}",
        "measured": True, "unavailable": None,
        "column": {"source": cand["column"], "n_slots": len(cols[0]),
                   "counts_candidate": built["candidate"]["frame"].counts,
                   "counts_base": built["base"]["frame"].counts,
                   "frames": {role: {"override": built[role]["override"],
                                     "floor_receipt": built[role]["receipt"]}
                              for role in ("candidate", "base")},
                   "shared_frame": {"floor_by_side": {s: F.lv_milb_floor(s) for s in SIDES},
                                    "note": "the lab's shared frame is build_frames as "
                                            "the tree builds it; the arm pairs its own "
                                            "two frames"}},
        "n": len(cols[0]), "folds": {}, "admitted_folds": None, "n_folds": 0,
        "fold_deltas": fd, "fold_signs_agree": len(signs) <= 1,
        "within": dict(within, floor=f_w), "pooled": dict(pooled, floor=f_p),
        "auc": dict(auc, floor=f_a),
        "legs": {"within": _leg(within.get("delta"), f_w),
                 "pooled": _leg(pooled.get("delta"), f_p),
                 "auc": _leg(auc.get("delta"), f_a)},
        "twin": {"inside_floor": None, "not_applicable": "a frame change has no column "
                                                         "to permute"},
        # DISCLOSED substitution: a frame change has no column to permute, so its Holm
        # p is the bootstrap's one-sided p (the share of E_cond draws at or below 0),
        # not a permutation p; the family step reads it like any other p.
        "permutation_null": {"p": (None if within.get("p_gt_0") is None
                                   else round(1.0 - float(within["p_gt_0"]), 5)),
                             "status": "substituted: bootstrap one-sided p (1 - p_gt_0); "
                                       "a frame change has no column to permute",
                             "n": within.get("B_used")},
        "balance": None,
        "delta": {"rho": within.get("delta"), "pooled": pooled.get("delta"),
                  "auc_contrib": auc.get("delta")},
        "floor_rho": f_w, "per_vintage_signs": None,
        "verdict": None, "clauses": None, "not_adjudicated": [], "holm_joint_row": None,
        "_order": order,
    }
    raters = _rater_block(frame, SIDES, order, base_order)
    vs_c = _vs_consensus(frame, SIDES, order, B=B, base_order=base_order)
    arm["frame"] = {
        "frame_version": "lv1_v2", "window": [min(frame.folds), max(frame.folds)],
        "n": len(cols[0]),
        "n_by_side": {s: sum(1 for g in cols[1] if g.startswith(s)) for s in SIDES},
        "n_players": len({k for (_V, k) in order}),
        "groups": sorted({f"{s}|{V}" for s in SIDES for V in frame.folds}),
        "statistic": S.STAT_LABEL[S.PRIMARY], "raters": raters,
        "deltas": {"candidate_vs_efv_v2_base": {"spearman": arm["within"],
                                                "pooled": arm["pooled"], "auc": arm["auc"]},
                   "candidate_vs_prospx_consensus": vs_c},
        "secondary": {"statistic": S.STAT_LABEL["pooled"],
                      "raters": {n: r.get("pooled") for n, r in raters.items()},
                      "deltas": {}},
        "verdict": None, "note": NOTE}
    return arm


def _is_under_data(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(DATA_DIR.resolve())
        return True
    except ValueError:
        return False


def run(frame: Frame, candidates=CANDIDATES, *, frames: dict | None = None, B: int = B_DEFAULT,
        n_perm: int = N_PERM, floors_only: bool = False, exploratory: bool,
        only: set | None = None, label: dict | None = None, extra_meta: dict | None = None,
        floor_mode: str = FLOOR_MODE_DEFAULT, both_floor_modes: bool = True,
        log=print) -> dict:
    """The whole wave on a built Frame: floors, then arms, then the family, then the
    verdicts. `frames` (the raw frames) is needed for frame-key and coverage columns.
    `both_floor_modes` also writes the other mode's floors as a receipt (floors_other),
    never read by a verdict."""
    t0 = time.time()
    if floor_mode not in FLOOR_MODES:
        raise ValueError(f"floor mode must be one of {FLOOR_MODES}, got {floor_mode!r}")
    doc: dict = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": TOOL, "wave": WAVE, "model_id": MODEL_ID,
        "role": "development", "adjudicates": False, "selects": False,
        "exploratory": bool(exploratory),
        "note": NOTE + ("; EXPLORATORY: no verdict formed, nothing admitted"
                        if exploratory else "; admits candidates to the gate's list"),
        "registration_echo": registration_echo(candidates, B=B, n_perm=n_perm,
                                               folds=frame.folds, floor_mode=floor_mode),
        "label": label if label is not None else frame.label,
        "guards": guards(frame.folds),
        "code": {"commit": _commit(), "tool": TOOL,
                 "lab_sha256": _sha(Path(__file__)),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "weights": frame.weights, "assembly_sha256": _sha(H.ASSEMBLY_PATH),
        "frame": {"id": "lv_dev", "folds": list(frame.folds), "counts": frame.counts,
                  "w_star_dev": frame.w_star,
                  "reserved_vm_kept_w3_zero": sum(
                      c.get("reserved_vm_kept_w3_zero", 0)
                      for s in frame.counts.values() for c in s.values()),
                  "absence_admitted": frame.absent_ok},
    }
    if extra_meta:
        doc.update(extra_meta)
    log(f"floors: deriving before any arm (mode {floor_mode})")
    doc["floors"] = derive_floors(frame, B=B, mode=floor_mode)
    for head in HEADS:
        for side, blk in doc["floors"][head].items():
            log(f"  floor {head} {side}: within {blk['within']} pooled {blk['pooled']} "
                f"auc {blk['auc']} ({blk['status'][:9]})")
    if both_floor_modes:
        other = [m for m in FLOOR_MODES if m != floor_mode][0]
        log(f"floors: the other mode's receipt (mode {other}; read by no verdict)")
        doc["floors_other"] = derive_floors(frame, B=B, mode=other)
        for head in HEADS:
            for side, blk in doc["floors_other"][head].items():
                log(f"  floor_other {head} {side}: within {blk['within']} "
                    f"({blk['status'][:9]})")
    doc["floors_derived_before_arms"] = True
    arms: list[dict] = []
    probes: list[dict] = []
    if not floors_only:
        base_vs_cons = {}
        for s in SIDES:
            order = {}
            for V in frame.folds:
                for pk, idx in frame.base(s, V)["order"].items():
                    order[(V, pk)] = idx
            base_vs_cons[s] = _vs_consensus(frame, (s,), order, B=B)
        for cand in candidates:
            if only and cand["name"] not in only:
                continue
            log(f"arm {cand['name']} ({cand['side']}, {cand['head'] or 'coverage'})")
            try:
                if cand["kind"] == "coverage":
                    arm = measure_coverage_arm(frame, cand, frame.weights, doc["floors"],
                                               B=B)
                else:
                    if frames is None and cand["column"].get("source") == "frame_key":
                        raise ColumnUnavailable("no raw frames handed to run()")
                    values = column_values(cand, frames or {})
                    arm = measure_arm(frame, cand, values, doc["floors"], B=B,
                                      n_perm=n_perm, base_vs_cons=base_vs_cons)
            except ColumnUnavailable as exc:
                log(f"  unavailable: {exc}")
                arm = unavailable_arm(cand, str(exc))
            arms.append(arm)
            if arm["measured"]:
                w = arm["within"]
                log(f"  within delta {w.get('delta')} lb95 {w.get('lb95')} mde95 "
                    f"{w.get('mde95')} floor {w.get('floor')}; admitted folds "
                    f"{arm.get('admitted_folds')}; perm p "
                    f"{(arm.get('permutation_null') or {}).get('p')}")
            for s, b in ((arm.get("balance") or {}).items()):
                tag = f"DS-03:screen.{arm['name']}_absent:{s}"
                probes.append({"tag": tag, "verdict": b.get("verdict"),
                               "partial": b.get("partial"), "ci95": b.get("ci95"),
                               "n_with": b.get("n_with"), "n_without": b.get("n_without")})
    for a in arms:
        a.pop("_order", None)
    doc["arms"] = arms
    doc["holm"] = apply_verdicts(arms, m=len(candidates), exploratory=exploratory)
    doc["probes"] = probes
    doc["n_arms"] = len(arms)
    doc["n_measured"] = sum(1 for a in arms if a["measured"])
    doc["n_probes"] = len(probes)
    doc["verdicts"] = {a["tag"]: a["verdict"] for a in arms}
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def write_doc(doc: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if text.find('"floors"') > text.find('"arms"'):
        raise RuntimeError("floors must be written before arms")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)


def verdict_line(tag: str, verdict: str | None) -> str:
    """One console line per arm. An arm that was never measured carries no verdict
    (None); it prints as such instead of failing the echo after the artifact is
    written (the registered run of 2026-10-08 hit that: the artifact was complete,
    the echo raised on the withheld arm)."""
    return f"  {(verdict or 'no verdict (not measured)'):32s} {tag}"


def real_frame(*, folds=FOLDS) -> tuple[Frame, dict]:
    """The lv_dev Frame on the tree's data: frames with sidecars (efv_v2_assemble),
    labels, the registration's weights, the absence admission per side."""
    guards(folds)
    frames = build_frames_with()
    weights = H.load_weights()
    label = {"provider": L.provider(), "resolved_through": L.resolved_through(),
             "id": label_id()}
    frame = Frame.from_frames(frames, weights=weights, folds=folds, label=label)
    frame.absent_ok = {s: H.absence_admitted(s) for s in SIDES}
    return frame, frames


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(OUT_DEFAULT),
                    help="artifact path (default data/xfv_screen_wave1.json); outside "
                         "data/ the run is exploratory and writes nothing else")
    ap.add_argument("--floors-only", action="store_true", help="steps 1 and 2 only")
    ap.add_argument("--exploratory", action="store_true",
                    help="form no verdict (the EFV3_B5 run); refused under data/")
    ap.add_argument("--check", action="store_true",
                    help="build the frame and print counts; no statistic")
    ap.add_argument("--only", default="", help="comma-separated candidate names")
    ap.add_argument("--B", type=int, default=B_DEFAULT,
                    help="bootstrap draws (a non-default value is refused under data/)")
    ap.add_argument("--n-perm", type=int, default=N_PERM,
                    help="permutation draws (a non-default value is refused under data/)")
    ap.add_argument("--no-ledger", action="store_true",
                    help="under data/: write the artifact but regenerate no ledger")
    ap.add_argument("--floor-mode", choices=FLOOR_MODES, default=FLOOR_MODE_DEFAULT,
                    help="how the noise columns reach the refit (module docstring)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    under = _is_under_data(out)
    exploratory = bool(a.exploratory) or not under
    if under and (a.exploratory or a.B != B_DEFAULT or a.n_perm != N_PERM or a.only):
        print("refused: an exploratory, reduced or partial run may not write under data/")
        return 2
    frame, frames = real_frame()
    if a.check:
        print(json.dumps({"guards": guards(), "counts": frame.counts, "label": frame.label,
                          "w_star_dev": frame.w_star, "weights": frame.weights,
                          "absence_admitted": frame.absent_ok}, indent=1))
        return 0
    only = {s.strip() for s in a.only.split(",") if s.strip()} or None
    doc = run(frame, frames=frames, B=a.B, n_perm=a.n_perm, floors_only=a.floors_only,
              exploratory=exploratory, only=only, floor_mode=a.floor_mode)
    write_doc(doc, out)
    print(f"wrote {out} ({doc['n_measured']} of {doc['n_arms']} arms measured, "
          f"{doc['elapsed_s']} s)")
    for tag, v in doc["verdicts"].items():
        print(verdict_line(tag, v))
    if under and not a.no_ledger and not a.floors_only:
        import efv_arm_ledger
        import efv_progress
        efv_arm_ledger.main([])
        print(efv_progress.summary_line(efv_progress.update_screening(trigger="efv_change")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The DS-06 admission diagnostic for the tool family (TL_16_EFV_TOOL_DEV_ADMISSION;
Part 9 PLAN section 9.4.5 'Tools as eFV drivers'; LANE_C.md section 2.7, route (a); owner
asks of 2026-10-01, message 2's last sentence: 'After doing so, if this proves to improve
tool grade accuracy, can we then check if tool grades can be used as eFV drivers / how
they should be weighted?').

WHY THIS MAY RUN AT ALL. The eFV feature frontier is closed (plan Part 2; the 2026-08-14
closure, 39 arms, zero survivors) and game power failed as an eFV driver four times (the
Phase 1 partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds;
data/xfv_arm_ledger.json); nothing here re-runs a spent arm. The columns are NEW (a power
composite chosen on realized ISO by a registered look, a tool-implied ISO residual, the
inputs of an accuracy-weighted hit consensus) and exist on the owner's 2026-10-01 asks.
The served eFV grade does not change.

REGISTRATION PATH. Owner answer TL-Q1 (a) 'Next registration' (DECISIONS_FOR_OWNER.md):
the rule runs on development folds only, adjudicates nothing, and an arm admitted in every
fold is pre-declared for the next registration (docs/efv-v2/NEXT_REGISTRATION_TOOL_
CANDIDATES.md) before that registration's first read.

THE RULE. The DS-06 rule of tools/efv_driver_admission.py, the same function
(efv_v2_model.admission_for_key, target u_y, has-block rows): inside each fold, on the
fold's own training vintages, fit by OLS the W3 percentile within (side, V) on [1,
consensus percentile, z(column)] one training vintage at a time; a vintage gives a t only
when at least 60 of its has-block rows observe the column; the column is admitted when at
least 2 vintages give a t, every t has one sign and the mean |t| is at least 1.0. The
column rides on each row's `v2` view under the screening prefix, so a row without a value
imputes at the fold's observed training mean (no flag, DS-04). The rule reads one column
at a time, so 'tool_hit_w replaces tool_hit in the head for its own arm' changes nothing
the rule reads; it is recorded for a later fit.

ARMS.
  TL:hit.skill.tip_iso_resid  the sidecar's residual (data/_labs/efv_tool_features.json).
  TL:hit.skill.tool_hit_w     the accuracy-weighted hit consensus, built PER FOLD: the
                              weights are BA2's estimator (tools/ba_tool_grade_lab.py
                              derive_weights, imported, not retyped: Spearman floor 0.05,
                              shrink K 150, clamp 0.6 to 1.5, at least 60 rows or flat) on
                              FanGraphs and MLB Pipeline hit grades of players OUTSIDE the
                              fold's frame, board years at most V - 3, the outcome BA2's
                              (MLB AVG after the board year), MLB seasons before 2026 only;
                              the row value is the weight-averaged per-source hit grade.
  TL:hit.skill.pwr_comp       NOT RUN: a candidate only if look P served C2 with a below 1
                              (round 4, leakage 3); look P served C0
                              (data/power_composite_eval.json).

FOLDS. lv: list vintages 2017 to 2021, training rows at list vintages below V with every
player of the V frame left out (gate s4.5); list vintages 2020 and 2021 are read as
development rows because the R-LV record exists (EFV_V3_BACKTEST.md s5.1 at 1c73c420,
decision D-k3) and the committed gate sha opens the guard. vm: decision years 2020 to 2024
on the v1 training matrices (decision years below 2025), training rows below the fold year
as tools/efv_v2_assemble.vm_folds reads them; a matrix row takes the sidecar row of its
latest list vintage V whose read window closed (V-05-01) on or before the row's as-of date.

NEVER READ: the R-VM debut cohorts (2025 and later; reserved_vm_pins asserted, matrix
decision years capped below 2025, the sidecar dropped those rows); any grouping by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md; the only groupings are fold and
training vintage); any order index, delta or served number.

Run:  python tools/efv_tool_admission.py --gate-sha SHA [--dry-run]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_labels as L  # noqa: E402
import efv_tool_features as TF  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

SIDECAR = ROOT / "data" / "_labs" / "efv_tool_features.json"
LOOK_P = ROOT / "data" / "power_composite_eval.json"
OUT = ROOT / "data" / "_labs" / "efv_tool_admission.json"
SCHEMA = "efv_tool_admission/1"
TASK = "TL_16_EFV_TOOL_DEV_ADMISSION"
TOOL = "tools/efv_tool_admission.py"
SIDE = "hit"
HEAD = "skill"
TARGET = "u_y"
ARM_PREFIX = "TL"
LV_FOLDS: tuple[int, ...] = (2017, 2018, 2019, 2020, 2021)
VM_FOLDS: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024)
LV_VINTAGES: tuple[int, ...] = tuple(F.DEV_VINTAGES) + tuple(sorted(F.RESERVED_LV))
#: The two sources BA2's arm A weighs (the only two with dated hit grades in the sidecar).
HIT_W_SOURCES: tuple[str, ...] = ("fangraphs", "mlb_pipeline")
COLUMNS = ("tip_iso_resid", "tool_hit_w")
KEYS = {c: f"{H.V2_SCREEN_PREFIX}tl_{c}" for c in COLUMNS}
WHY_THIS_MAY_RUN = (
    "The eFV feature frontier is closed (plan Part 2; the 2026-08-14 closure, 39 arms, "
    "zero survivors) and game power failed as an eFV driver four times (the Phase 1 "
    "partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds; "
    "data/xfv_arm_ledger.json); nothing here re-runs a spent arm. The columns are NEW (a "
    "power composite chosen on realized ISO by a registered look, a tool-implied ISO "
    "residual, the inputs of an accuracy-weighted hit consensus) and exist on the "
    "owner's 2026-10-01 asks. The served eFV grade does not change.")
REGISTRATION_PATH = (
    "TL-Q1 answer (a) 'Next registration' (DECISIONS_FOR_OWNER.md): the DS-06 rule on "
    "development folds only; nothing is adjudicated; an arm admitted in every lv and vm "
    "fold is pre-declared for the next registration (V3 at the 2027 label epoch, or the "
    "next registration docs/efv-v2/PROGRAM.md names) before its first read.")


# ---------------------------------------------------------------------------
# guards and receipts
# ---------------------------------------------------------------------------

def rlv_record() -> bool:
    import efv_tool_sidecar as T
    return T.rlv_record_exists()


def guards(gate_sha: str | None) -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    if not rlv_record():
        raise F.ReservedFrameError("no R-LV record: list vintages 2020 and 2021 stay closed")
    for V in LV_VINTAGES:
        F.guard_score_request(V, gate_sha=gate_sha, purpose="tool admission")
    if max(VM_FOLDS) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise F.ReservedFrameError(f"a vm fold reaches R-VM: {VM_FOLDS}")
    if H.RULE_LAST_YEAR >= min(LV_FOLDS):
        raise ValueError("the combiner rule's years overlap the admission folds")
    text = (ROOT / F.GATE_DOC).read_text(encoding="utf-8", errors="replace")
    if not F.gate_doc_registered(text):
        raise RuntimeError(f"{F.GATE_DOC} is not REGISTERED")
    return {"reserved_lv": sorted(F.RESERVED_LV), "rlv_record": True,
            "rlv_record_where": ("docs/efv-v2/EFV_V3_BACKTEST.md s5.1 at 1c73c420 "
                                 "(decision D-k3, the TL2-Q1 reading); EFV_V2_GATE.md s9 "
                                 "stays empty by its s11"),
            "gate_sha": gate_sha, "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins, "lv_folds": list(LV_FOLDS),
            "vm_folds": list(VM_FOLDS), "rule_last_year": H.RULE_LAST_YEAR,
            "gate_registered": True, "closed_arms_rerun": False,
            "order_index_fitted": False, "delta_read": False,
            "anchor_gate_grouping": False}


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def label() -> dict:
    prov = L.provider()
    if prov != "fwar":
        raise RuntimeError(f"the label provider is {prov!r}, not the frozen fWAR label")
    import war_source
    vid = (war_source.fwar_index() or {}).get("vintage_id")
    return {"provider": prov, "label_id": f"fwar@{vid}",
            "lv_target": "W3 percentile within (side, list vintage), ties averaged",
            "vm_target": ("the v1 matrix target (target_censored) percentile within "
                          "decision year, matrices as built on the frozen label")}


def pwr_comp_status() -> dict:
    res = (json.loads(LOOK_P.read_text(encoding="utf-8")).get("result")
           if LOOK_P.exists() else None)
    return TF.pwr_comp_status(res)


# ---------------------------------------------------------------------------
# the sidecar columns
# ---------------------------------------------------------------------------

def load_sidecar(path: Path = SIDECAR) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    read = set(int(v) for v in (doc.get("guards") or {}).get("vintages_read") or ())
    missing = sorted(set(LV_VINTAGES) - read)
    if missing:
        raise RuntimeError(f"the sidecar lacks list vintages {missing} (run "
                           "tools/efv_tool_sidecar.py --rebuild --gate-sha SHA)")
    return doc


def sidecar_rows(doc: dict) -> dict[tuple[int, str], dict]:
    """{(V, player_key): {'tip': value or None, 'hit': {source: grade}}}."""
    out: dict = {}
    for V, blk in (doc.get("rows") or {}).get(SIDE, {}).items():
        for pk, rec in blk.items():
            per_source, _cons, tip = rec[0], rec[1], rec[2]
            hit = {s: float(g[0]) for s, g in per_source.items() if g and g[0] is not None}
            out[(int(V), str(pk))] = {"tip": tip, "hit": hit}
    return out


def weighted_hit(hit: dict[str, float], w: dict[str, float]):
    if not hit:
        return None
    num = sum(w.get(s, 1.0) * g for s, g in hit.items())
    den = sum(w.get(s, 1.0) for s in hit)
    return num / den if den else None


# ---------------------------------------------------------------------------
# BA2's estimator, per fold, outside the fold's frame
# ---------------------------------------------------------------------------

class HitWeights:
    """BA2's hit-weight estimator inputs, loaded once; `fold(V, exclude)` returns the
    weights on board years at most V - 3 over players outside `exclude`."""

    def __init__(self):
        import ba_tool_grade_lab as BA
        self.BA = BA
        grades, _census, _years = BA.load_grades()
        cs = BA.load_career_mlb()
        # MLB seasons before 2026 only (round 4, leakage 2; efv_tool_features)
        cs = {pk: [x for x in rows if int(x.get("season") or 0) < TF.FIRST_FORBIDDEN_SEASON]
              for pk, rows in cs.items()}
        self.by_year = BA.build_rows(grades, cs, "hit", HIT_W_SOURCES)
        self.lag = BA.MIN_LAG_YEARS

    def fold(self, V: int, exclude: set[str]) -> dict:
        max_base = int(V) - self.lag
        by_year = {y: [r for r in rs if r["player"] not in exclude]
                   for y, rs in self.by_year.items() if y <= max_base}
        w, n, rho = self.BA.derive_weights(by_year, HIT_W_SOURCES, max_base)
        return {"weights": w, "n_rows": n, "source_rho": rho,
                "board_years": sorted(y for y, rs in by_year.items() if rs),
                "max_board_year": max_base,
                "flat": all(abs(float(v) - 1.0) < 1e-9 for v in w.values()),
                "excluded_players": len(exclude)}


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------

def _observed_by_vintage(tr: list[dict], key: str) -> dict[str, dict]:
    out: dict = {}
    for r in tr:
        b = out.setdefault(str(int(r["decision_year"])), {"rows": 0, "has_block": 0,
                                                          "observed": 0})
        b["rows"] += 1
        if r["v2"]["has_block"]:
            b["has_block"] += 1
            if r["v2"].get(key) is not None:
                b["observed"] += 1
    return out


def fold_check(tr: list[dict], key: str) -> dict:
    chk = H.admission_for_key(tr, key, target=TARGET, has_block_only=True)
    return {"admitted": bool(chk["admitted"]), "reason": chk["reason"],
            "per_vintage_signs": chk["per_vintage_signs"],
            "t_by_vintage": chk["t_by_vintage"],
            "vintages_without_t": chk["vintages_without_t"],
            "n_valid_vintages": chk["n_valid_vintages"],
            "mean_abs_t": chk["mean_abs_t"], "sign": chk["sign"],
            "n_train": len(tr),
            "n_train_has_block": sum(1 for r in tr if r["v2"]["has_block"]),
            "n_train_observed": sum(1 for r in tr if r["v2"]["has_block"]
                                    and r["v2"].get(key) is not None),
            "training_vintages": sorted({int(r["decision_year"]) for r in tr}),
            "by_vintage": _observed_by_vintage(tr, key)}


def set_columns(rows: list[dict], feats_of, weights: dict) -> None:
    """Both columns on every row's v2 view (None where absent), tool_hit_w at `weights`."""
    for r in rows:
        f = feats_of(r) or {}
        r["v2"][KEYS["tip_iso_resid"]] = f.get("tip")
        r["v2"][KEYS["tool_hit_w"]] = weighted_hit(f.get("hit") or {}, weights)


def lv_folds(rows: list[dict], frame_keys: dict[int, set[str]], feats: dict,
             hw: HitWeights | None, *, folds=LV_FOLDS) -> dict:
    """{fold: {column: check, 'hit_weights': ...}} on lv training rows."""
    out: dict = {}
    for V in folds:
        V = int(V)
        F.guard_score_request(V, gate_sha=_GATE[0], purpose="tool admission")
        keys = frame_keys.get(V) or set()
        tr = [r for r in rows if int(r["decision_year"]) < V
              and str(r["player_key"]) not in keys]
        wf = hw.fold(V, keys) if hw is not None else {
            "weights": {s: 1.0 for s in HIT_W_SOURCES}, "flat": True}
        set_columns(tr, lambda r: feats.get((int(r["decision_year"]), str(r["player_key"]))),
                    wf["weights"])
        out[str(V)] = {c: fold_check(tr, KEYS[c]) for c in COLUMNS}
        out[str(V)]["tool_hit_w"]["spearman_vs_tool_hit"] = overlap_with_tool_hit(tr)
        out[str(V)]["hit_weights"] = wf
    return out


def overlap_with_tool_hit(tr: list[dict]) -> dict:
    """Spearman of tool_hit_w with the admitted V2 column tool_hit over the training rows
    that observe tool_hit_w (no outcome read): how far the new column is the spent one."""
    import source_backtest as SB
    pairs = [(r["v2"][KEYS["tool_hit_w"]], r["v2"].get("tool_hit")) for r in tr
             if r["v2"].get(KEYS["tool_hit_w"]) is not None
             and r["v2"].get("tool_hit") is not None]
    rho = SB._spearman([a for a, _b in pairs], [b for _a, b in pairs]) if pairs else None
    return {"n": len(pairs), "rho": None if rho is None else round(float(rho), 4)}


def vm_join(mat_rows: list[dict], asof: dict[str, str], feats: dict) -> dict[str, tuple]:
    """{player_key: (V, sidecar entry)}: the latest list vintage V whose read window
    closed on or before the matrix row's as-of date."""
    by_pk: dict = {}
    for (V, pk), f in feats.items():
        by_pk.setdefault(pk, []).append((V, f))
    out = {}
    for r in mat_rows:
        pk = str(r["player_key"])
        a = str(asof.get(pk) or "")
        best = None
        for V, f in sorted(by_pk.get(pk) or ()):
            if a and f"{V}-05-01" <= a and V < F.R_VM_FIRST_DEBUT_YEAR:
                best = (V, f)
        if best is not None:
            out[pk] = best
    return out


def vm_folds(rows: list[dict], joined: dict, hw: HitWeights | None, *,
             folds=VM_FOLDS) -> dict:
    out: dict = {}
    for yr in folds:
        yr = int(yr)
        tr = [r for r in rows if int(r["decision_year"]) < yr]
        H._check_years({int(r["decision_year"]) for r in tr})
        keys = {str(r["player_key"]) for r in rows if int(r["decision_year"]) == yr}
        wf = hw.fold(yr, keys) if hw is not None else {
            "weights": {s: 1.0 for s in HIT_W_SOURCES}, "flat": True}
        set_columns(tr, lambda r: (joined.get(str(r["player_key"])) or (None, None))[1],
                    wf["weights"])
        out[str(yr)] = {c: fold_check(tr, KEYS[c]) for c in COLUMNS}
        out[str(yr)]["tool_hit_w"]["spearman_vs_tool_hit"] = overlap_with_tool_hit(tr)
        out[str(yr)]["hit_weights"] = wf
    return out


def arm(column: str, lv: dict, vm: dict) -> dict:
    by_fold = {f"lv:{V}": f[column] for V, f in lv.items()}
    by_fold.update({f"vm:{V}": f[column] for V, f in vm.items()})
    adm = [k for k, f in by_fold.items() if f["admitted"]]
    all_folds = len(adm) == len(by_fold)
    signs = {f["sign"] for f in by_fold.values() if f["admitted"]}
    return {
        "tag": f"{ARM_PREFIX}:{SIDE}.{HEAD}.{column}", "side": SIDE, "head": HEAD,
        "driver": column, "column_key": KEYS[column], "target": TARGET,
        "rows": "has_block", "item": "DS-06", "role": "development",
        "frame": ("lv folds 2017 to 2021 (list vintages 2020 and 2021 as spent R-LV "
                  "development rows) and vm folds 2020 to 2024, each on its own "
                  "training vintages"),
        "verdict": "ADMITTED" if all_folds else "REFUSED",
        "verdict_scope": ("the DS-06 rule inside every fold; ADMITTED only when all ten "
                          "folds admit; a development reading that adjudicates nothing"),
        "admitted": all_folds, "admitted_folds": adm, "n_admitted_folds": len(adm),
        "n_folds": len(by_fold), "fold_signs_agree": len(signs) <= 1,
        "reason": ("admitted in every fold" if all_folds else
                   "; ".join(f"{k}: {f['reason']}" for k, f in by_fold.items()
                             if not f["admitted"])),
        "per_vintage_signs": {k: f["per_vintage_signs"] for k, f in by_fold.items()},
        "mean_abs_t": {k: f["mean_abs_t"] for k, f in by_fold.items()},
        "n_valid_vintages": {k: f["n_valid_vintages"] for k, f in by_fold.items()},
        "by_fold": by_fold,
        "hit_weights_by_fold": ({**{f"lv:{V}": f["hit_weights"] for V, f in lv.items()},
                                 **{f"vm:{V}": f["hit_weights"] for V, f in vm.items()}}
                                if column == "tool_hit_w" else None),
        "delta": None, "floor_rho": None,
        "reads": ("the target percentile and the consensus percentile on training rows "
                  "only; no order index, no delta, no served number"),
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

_GATE: list = [None]


def build_lv(gate_sha: str, log=print):
    """{V: (rows, labels)} on the hitter side, list vintages 2011 to 2021."""
    universe = F.load_universe()
    war = L.war_seasons_table()
    frames: dict = {}
    t0 = time.time()
    for V in LV_VINTAGES:
        rows = F.build_frame(SIDE, V, gate_sha=gate_sha, universe=universe)
        labs = L.labels_for_frame(rows, universe=universe, war=war, gate_sha=gate_sha)
        frames[V] = (rows, labs)
        log(f"  lv {SIDE} {V}: {len(rows)} rows ({round(time.time() - t0, 1)} s)")
    return frames


def run(gate_sha: str, *, log=print) -> dict:
    t0 = time.time()
    _GATE[0] = gate_sha
    g = guards(gate_sha)
    lab = label()
    pstat = pwr_comp_status()
    if pstat["candidate"]:
        raise RuntimeError("look P served C2 with a below 1: the pwr_comp arm and its "
                           "cross-fitted a are not built in this tool")
    doc = load_sidecar()
    feats = sidecar_rows(doc)
    frames = build_lv(gate_sha, log=log)
    lv_rows = H.lv_training_rows(SIDE, frames, gate_sha=gate_sha)
    frame_keys = {int(V): {str(r["player_key"]) for r in frames[V][0]} for V in frames}
    in_train = {(int(r["decision_year"]), str(r["player_key"])) for r in lv_rows}
    kept_rvm = sum(1 for V in frames for lab_ in frames[V][1]
                   if lab_.get("status") == "reserved_vm"
                   and (int(V), str(lab_.get("player_key"))) in in_train)
    log(f"lv training rows {len(lv_rows)} ({round(time.time() - t0, 1)} s)")
    hw = HitWeights()
    log(f"BA2 hit rows loaded ({round(time.time() - t0, 1)} s)")
    lv = lv_folds(lv_rows, frame_keys, feats, hw)
    raw = json.loads(H._matrix_path(SIDE).read_text(encoding="utf-8"))
    asof = {str(r["player_key"]): r.get("asof_date") for r in raw}
    mat = [r for r in H.matrix_training_rows(SIDE)
           if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
    joined = vm_join(mat, asof, feats)
    vm = vm_folds(mat, joined, hw)
    arms = {}
    for c in COLUMNS:
        a = arm(c, lv, vm)
        arms[a["tag"]] = a
        log(f"  {a['tag']}: {a['verdict']} ({a['n_admitted_folds']} of {a['n_folds']} "
            f"folds: {a['admitted_folds'] or 'none'})")
    not_run = {f"{ARM_PREFIX}:{SIDE}.{HEAD}.pwr_comp": {
        "verdict": "NOT RUN", "reason": pstat["reason"],
        "rule": "a candidate only if look P served C2 with a below 1 (round 4, leakage 3)"}}
    admitted = sorted(t for t, a in arms.items() if a["admitted"])
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": TOOL, "task": TASK, "code_commit": _commit(),
        "owner_ask": ("2026-10-01, message 2's last sentence: 'After doing so, if this "
                      "proves to improve tool grade accuracy, can we then check if tool "
                      "grades can be used as eFV drivers / how they should be weighted?'"),
        "why_this_may_run": WHY_THIS_MAY_RUN,
        "registration_path": REGISTRATION_PATH,
        "role": "development diagnostic; adjudicates nothing; no served number",
        "adjudicates": "nothing",
        "owner_precondition": {
            "hit": ("look W (docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part 8, "
                    "2026-10-14): hit NULL and the look VOID under W.7; not a PASS, so the "
                    "owner's 'if this proves to improve tool grade accuracy' is NOT met "
                    "for hit"),
            "composite": ("look P (same file, Part 8, 2026-10-14): served C0; no PASS for "
                          "C1 or C2, so the precondition is NOT met for the composite"),
            "tip_iso_resid": ("no accuracy look applies: a production-beyond-grade "
                              "residual, not a tool weight"),
        },
        "folds": {"lv": list(LV_FOLDS), "vm": list(VM_FOLDS)},
        "head": HEAD, "target": TARGET, "guards": g, "label": lab,
        "rule": {"statement": ("a driver enters only if its coefficient's sign held in "
                               "every training vintage that gives a t (at least 60 rows, "
                               "at least 2 such vintages) and its mean |t| is at least "
                               "1.0 (docs/efv-v2/EFV_V2_GATE.md s4.2, DS-06)"),
                 "min_rows": H.ADMIT_MIN_ROWS, "min_vintages": H.ADMIT_MIN_VINTAGES,
                 "min_mean_abs_t": H.ADMIT_MIN_MEAN_ABS_T,
                 "function": "efv_v2_model.admission_for_key(target=u_y, has_block_only=True)",
                 "lv_training": ("efv_v2_model.lv_training_rows at list vintages below V, "
                                 "every V-frame player excluded (gate s4.5)"),
                 "vm_training": ("efv_v2_model.matrix_training_rows at decision years "
                                 "below the fold year (tools/efv_v2_assemble.vm_folds)"),
                 "vm_join": ("the sidecar row of the latest list vintage V with V-05-01 on "
                             "or before the matrix row's asof_date"),
                 "tool_hit_w": ("sum(w_s g_s) / sum(w_s) over the row's per-source hit "
                                "grades, w from BA2's derive_weights per fold"),
                 "tool_hit_replacement": ("tool_hit_w replaces tool_hit for its own arm; "
                                          "the rule reads one column at a time, so the "
                                          "replacement moves nothing it reads")},
        "inputs": {
            "sidecar": SIDECAR.relative_to(ROOT).as_posix(),
            "sidecar_sha256": _sha(SIDECAR),
            "sidecar_generated_at": doc.get("generated_at"),
            "hitter_matrix_sha256": _sha(H._matrix_path(SIDE)),
            "efv_v2_model.py": _sha(ROOT / "efv_v2_model.py"),
            "efv_tool_features.py": _sha(ROOT / "efv_tool_features.py"),
            "ba_tool_grade_lab.py": _sha(ROOT / "tools" / "ba_tool_grade_lab.py"),
            "power_composite_eval.json": _sha(LOOK_P),
        },
        "counts": {
            "lv_training_rows": len(lv_rows),
            "lv_has_block": sum(1 for r in lv_rows if r["v2"]["has_block"]),
            "lv_reserved_vm_kept_w3_zero": kept_rvm,
            "lv_frame_rows": {str(V): len(frames[V][0]) for V in frames},
            "vm_matrix_rows": len(mat),
            "vm_rows_joined_to_sidecar": len(joined),
            "vm_join_vintages": {str(V): sum(1 for v, _f in joined.values() if v == V)
                                 for V in sorted({v for v, _f in joined.values()})},
        },
        "arms": arms, "n_arms": len(arms), "not_run": not_run,
        "admitted_every_fold": admitted,
        "pre_declaration": (
            f"owed for {', '.join(admitted)}: docs/efv-v2/NEXT_REGISTRATION_TOOL_"
            "CANDIDATES.md before the next registration's first read" if admitted else
            "no arm admitted in every fold: docs/efv-v2/NEXT_REGISTRATION_TOOL_"
            "CANDIDATES.md records an empty candidate list"),
        "never": ["debut cohorts 2025+ (R-VM)", "any grouping by consensus-FV level",
                  "any order index or delta", "any served eFV change",
                  "a re-run of a spent arm (pwr_comp under C0 or C1)"],
        "elapsed_s": round(time.time() - t0, 1),
    }


def write(doc: dict, path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, indent=1) + "\n").encode("utf-8"))


def _echo(doc: dict) -> None:
    for tag, a in doc["arms"].items():
        print(f"{a['verdict']:9s} {tag}  ({a['n_admitted_folds']} of {a['n_folds']} folds)")
        for k, f in a["by_fold"].items():
            print(f"    {k}: admitted {f['admitted']!s:5s} signs {f['per_vintage_signs']} "
                  f"mean|t| {f['mean_abs_t']} (train {f['n_train']}, observed "
                  f"{f['n_train_observed']}) {f['reason']}")
    for tag, n in doc["not_run"].items():
        print(f"NOT RUN   {tag}: {n['reason']}")
    print(f"pre-declaration: {doc['pre_declaration']}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--gate-sha" not in argv:
        print("--gate-sha SHA is required (list vintages 2020 and 2021 are read)")
        return 1
    gate_sha = argv[argv.index("--gate-sha") + 1]
    doc = run(gate_sha)
    _echo(doc)
    if "--dry-run" not in argv:
        write(doc)
        print(f"wrote {OUT.relative_to(ROOT).as_posix()} ({doc['elapsed_s']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

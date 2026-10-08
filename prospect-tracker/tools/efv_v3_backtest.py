# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV v3 backtest (EFV3_W3_SELECT_CONFIRM; owner EW2-6, 2026-10-08): SELECT on the
development frames, then CONFIRM the one committed configuration ONCE on the reserved
frames. The rule is fixed in docs/efv-v2/EFV_V3_BACKTEST.md before any combined read;
this tool runs it and records every step.

    --check      build the development inputs (tools/efv_v2_model_class_screen
                 .build_inputs through efv_w2_anchor.build, the anchor tables and the
                 wave-2 columns), assert the V2 base reproduces the DS-16 block, print
                 counts. No statistic of any candidate.
    --select     the forward selection on lv_dev (list vintages 2017 to 2019, W3) and
                 vm_dev (vm2, debut years 2017 to 2023), exactly as the document fixes
                 it: every evaluated step and its deltas are written to
                 data/_labs/efv_v3/efv_v3_select.json, the one selected configuration
                 to data/efv_v3_spec.json (efv_v3.SPEC_PATH), and two development rows
                 (model efv_v3, frames lv_dev and vm_dev) to data/efv_progress.json.
    --confirm --gate-sha SHA
                 the ONE read of the committed configuration on R-LV (list vintages
                 2020 and 2021) and R-VM (the 2025 debut cohort, vm2 rule), against
                 served eFV (V2), PROSPX consensus, MLB Pipeline and FanGraphs: within
                 and pooled Spearman, contributor AUC and the MAE of the priced grade,
                 each with E_cond CI95 (B 2000) and E_refit CI95 (--b-refit draws, the
                 pool resampled by player and every fold refit per draw), overall and
                 per side, plus the position-group cells (efv_strata.position_family:
                 C, IF, OF; pitchers one cell; never an FV cell). Written to
                 data/_labs/efv_v3/efv_v3_confirm.json and, as two reserved-frame rows
                 (frames lv_res and vm_pros, trigger look, model efv_v3), to
                 data/efv_progress.json. The reserved guards open on the gate sha and
                 on nothing else (efv_vintage_frame.guard_score_request, guard_vm_request,
                 efv_v2_model._check_years); a second confirm run refuses while the
                 artifact exists.

Nothing served moves: efv_v3.EFV_V3_ON stays False and no served path reads an
artifact of this tool. GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only
strata are side, vintage and position group. Nothing here groups, counts or averages
rows by consensus-FV level.
"""
from __future__ import annotations

import argparse
import copy
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
import efv_strata as ST  # noqa: E402
import efv_v2_candidates as C  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_v3 as V3  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_anchor as W2A  # noqa: E402
import source_backtest as SB  # noqa: E402

TOOL = "tools/efv_v3_backtest.py"
ITEM = "EFV3_W3_SELECT_CONFIRM"
LAB_DIR = H.DATA_DIR / "_labs" / "efv_v3"
SELECT_PATH = LAB_DIR / "efv_v3_select.json"
CONFIRM_PATH = LAB_DIR / "efv_v3_confirm.json"
FROZEN_PROVIDER = "fwar"
CONS = SB.CONSENSUS_KEY
SOURCES: tuple[str, ...] = tuple(SB.SCORED_SOURCES)
V3_KEY = "efv_v3"
V2_KEY = "efv_v2"
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
#: E_refit: draws of the pool resampled by player with every fold refit per draw.
B_REFIT_DEFAULT = 200
SEED_REFIT = SEED + 1
#: THE RULE (docs/efv-v2/EFV_V3_BACKTEST.md s2): a step is admitted only when the
#: within Spearman on its scope rises by at least MIN_LV_GAIN on lv_dev and does not
#: fall by more than VM_TOLERANCE on vm_dev; at most MAX_STEPS steps; the largest
#: lv_dev gain wins a round, ties to the earlier menu position.
MIN_LV_GAIN = 0.0020
VM_TOLERANCE = -0.0020
MAX_STEPS = 6
FRAMES_DEV: tuple[str, ...] = ("lv_dev", "vm_dev")
FRAMES_RES: tuple[str, ...] = ("lv_res", "vm_pros")
FRAME_KIND = {"lv_dev": "lv", "vm_dev": "vm", "lv_res": "lv", "vm_pros": "vm"}
FRAME_VERSION = {"lv_dev": "lv1_v2", "vm_dev": "vm2", "lv_res": "lv1_v2", "vm_pros": "vm2"}
RATERS_OUT = ((V3_KEY, "efv_v3"), (V2_KEY, "efv_v2"), (CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
COMPARISONS = (("v3_vs_efv_v2", V3_KEY, V2_KEY),
               ("v3_vs_prospx_consensus", V3_KEY, CONS),
               ("v3_vs_mlb_pipeline", V3_KEY, "mlb_pipeline"),
               ("v3_vs_fangraphs", V3_KEY, "fangraphs"),
               ("efv_v2_vs_prospx_consensus", V2_KEY, CONS))
STATS = ("within", "pooled", "auc", "mae")
SCOPES = ("both", "hit", "pit")
#: Position-group cells: the hitter position family (efv_strata) and pitchers as one.
CELLS = (("hit", "C"), ("hit", "IF"), ("hit", "OF"), ("pit", "pit"))
NOTE_SELECT = ("eFV v3 forward selection on the development frames (spent, not a claim); "
               "owner EW2-6")
NOTE_CONFIRM = "eFV v3 backtest, reserved frames, owner waiver 2026-10-08"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

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


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def _label() -> dict:
    import efv_v2_model_class_screen as MCS
    return MCS._label()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assert_no_dash(text: str) -> None:
    for ch in (chr(0x2014), chr(0x2013)):
        if ch in text:
            raise RuntimeError("an em-dash or en-dash reached the artifact")


def write_doc(doc: dict, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n"
    _assert_no_dash(text)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)
    return out


# ---------------------------------------------------------------------------
# the step menu
# ---------------------------------------------------------------------------

def menu(cfg: dict) -> list[dict]:
    """Every step still available from `cfg`, in the fixed order of the document:
    anchors, weight factors, driver removals, wave-2 additions."""
    out = []
    if cfg["anchor"] is None:
        for a in V3.ANCHORS:
            out.append({"kind": "anchor", "arm": a, "sides": list(F.SIDES),
                        "name": f"anchor:{a}"})
    for s in F.SIDES:
        for h in V3.HEADS:
            if float(cfg["scale"][s][h]) == 1.0:
                for k in V3.SCALES:
                    out.append({"kind": "scale", "side": s, "head": h, "factor": k,
                                "sides": [s], "name": f"scale:{s}.{h}x{k:g}"})
    for s in F.SIDES:
        for h in V3.HEADS:
            cands = (H.skill_candidates(s) if h == "skill"
                     else H.timing_candidates(s, ids_outcome_blind=True, absence_admitted=True))
            for d in cands:
                if d not in cfg["remove"][s][h]:
                    out.append({"kind": "remove", "side": s, "head": h, "driver": d,
                                "sides": [s], "name": f"remove:{s}.{h}.{d}"})
    for name, spec in V3.W2_COLUMNS.items():
        if name not in cfg["add"][spec["side"]][spec["head"]]:
            out.append({"kind": "add", "side": spec["side"], "head": spec["head"],
                        "column": name, "sides": [spec["side"]],
                        "name": f"add:{spec['side']}.{spec['head']}.{name}"})
    return out


def apply_step(cfg: dict, step: dict) -> dict:
    new = copy.deepcopy(cfg)
    if step["kind"] == "anchor":
        new["anchor"] = step["arm"]
    elif step["kind"] == "scale":
        new["scale"][step["side"]][step["head"]] = float(step["factor"])
    elif step["kind"] == "remove":
        new["remove"][step["side"]][step["head"]].append(step["driver"])
    elif step["kind"] == "add":
        new["add"][step["side"]][step["head"]].append(step["column"])
    else:
        raise ValueError(step)
    return V3.validate_config(new)


# ---------------------------------------------------------------------------
# inputs: frames, anchor tables and wave-2 columns
# ---------------------------------------------------------------------------

def _row_groups_for_frame(fid: str, groups: dict) -> dict:
    """efv_w2_anchor.build's groups for one frame: {side: {(pk, year): group}}."""
    return groups.get(fid) or {}


def _w2_import(module: str):
    return __import__(module)


def w2_values_dev(inputs: dict, frames_lv: dict, *, log=print) -> dict:
    """{fid: {side: {column name: {(year, pk, kind): value | None}}}} for every
    W2_COLUMNS entry on both development frames, through each module's own builders:
    efv_w2_milb.screen_column / vm_profiles and efv_w2_scout.screen_column /
    values_for. A vm training row reads at its matrix cutoff, a vm test row at its
    pinned preseason read (efv_v2_model.pinned_inputs)."""
    import efv_drivers as DRV  # noqa: F401  (pinned_inputs' panel is loaded by the caller)
    out: dict = {fid: {s: {} for s in F.SIDES} for fid in FRAMES_DEV}
    by_mod: dict = {}
    for name, spec in V3.W2_COLUMNS.items():
        by_mod.setdefault(spec["module"], []).append(name)
    vm = inputs["frames"]["vm_dev"]
    # as-of dates of the vm rows (train: the matrix cutoff; test: the pinned read)
    asof: dict = {}
    raw_by_side: dict = {}
    for side in F.SIDES:
        raw = json.loads(H._matrix_path(side).read_text(encoding="utf-8"))
        raw_by_side[side] = {r["player_key"]: r for r in raw}
        mine: dict = {}
        H.pinned_inputs(side, H.matrix_training_rows(side), mine)
        asof[side] = {"train": {pk: r.get("asof_date") for pk, r in raw_by_side[side].items()},
                      "test": {pk: rec.get("asof_date") for pk, rec in mine.items()}}
    for mod, names in by_mod.items():
        M = _w2_import(mod)
        for name in names:
            spec = V3.W2_COLUMNS[name]
            side = spec["side"]
            t0 = time.time()
            lv = M.screen_column(spec["arg"], side, frames_lv)
            vals_lv = {}
            for (V, pk), v in lv.items():
                for kind in ("train", "test"):
                    vals_lv[(int(V), pk, kind)] = None if v is None else float(v)
            out["lv_dev"][side][name] = vals_lv
            vals_vm: dict = {}
            if mod == "efv_w2_milb":
                prof = M.vm_profiles(side, H.matrix_training_rows(side), raw_by_side[side])
                for fold, blk in vm["by_side"][side].items():
                    for kind in ("train", "test"):
                        for r in blk[kind]:
                            p = prof.get(r["player_key"]) or {}
                            v = p.get(spec["arg"])
                            vals_vm[(int(r["decision_year"]), r["player_key"], kind)] = (
                                None if v is None else float(v))
            else:
                index = M.default_index()
                slots = {}
                for fold, blk in vm["by_side"][side].items():
                    for kind in ("train", "test"):
                        for r in blk[kind]:
                            key = (int(r["decision_year"]), r["player_key"], kind)
                            slots[key] = (key, r["player_key"], asof[side][kind].get(r["player_key"]))
                got = M.values_for(list(slots.values()), spec["arg"], index)
                vals_vm = {k: (None if v is None else float(v)) for k, v in got.items()}
            out["vm_dev"][side][name] = vals_vm
            n_lv = sum(1 for v in vals_lv.values() if v is not None)
            n_vm = sum(1 for v in vals_vm.values() if v is not None)
            log(f"  column {name}: lv {n_lv} of {len(vals_lv)} slots, vm {n_vm} of "
                f"{len(vals_vm)} ({round(time.time() - t0, 1)} s)")
    return out


def attach_columns(rows: list[dict], cfg: dict, side: str, head: str, cols: dict,
                   kind: str) -> list[dict]:
    """Rows (copies) with the configuration's added columns on their v2 view."""
    names = list(cfg["add"][side][head])
    if not names:
        return rows
    out = []
    for r in rows:
        add = {}
        for name in names:
            key = V3.W2_COLUMNS[name]["key"]
            vals = (cols.get(name) or {})
            add[key] = vals.get((int(r["decision_year"]), r["player_key"], kind))
        out.append(dict(r, v2=dict(r["v2"], **add)))
    return out


def w2_values_reserved(names, *, lv: dict, vm: dict, frames_dev: dict, frames_res: dict,
                       raw_by_side: dict, pinned_asof: dict, gate_sha: str,
                       log=print) -> dict:
    """The named wave-2 columns on the reserved frames, {fid: {side: {name: values}}}:
    the scouting-grade builder (efv_w2_scout.values_for) at each row's own as-of date (an
    lv row at its frame row's latest in-window read, a vm training row at its matrix
    cutoff, a vm test row at its pinned preseason read). R-LV rows and vm training rows
    read the development index; the 2025 test rows read efv_w2_scout.look_index, whose
    date range ends at the 2025 window's end and which needs the committed gate sha. The
    MiLB-profile builder's cache ends with the 2022 season, so those columns are not
    buildable here and raise."""
    import efv_w2_scout as SC
    out: dict = {fid: {s: {} for s in F.SIDES} for fid in FRAMES_RES}
    Y = F.R_VM_FIRST_DEBUT_YEAR
    asof_lv: dict = {s: {} for s in F.SIDES}
    for s in F.SIDES:
        for V, (rows, _l) in {**frames_dev[s], **frames_res[s]}.items():
            for r in rows:
                asof_lv[s][(int(V), r["player_key"])] = r.get("asof_date")
    dev_index = SC.default_index()
    look = SC.look_index(gate_sha)
    for name in names:
        spec = V3.W2_COLUMNS[name]
        if spec["module"] != "efv_w2_scout":
            raise NotImplementedError(f"{name}: no reserved-frame builder (the MiLB profile "
                                      f"cache ends with the 2022 season)")
        side = spec["side"]
        slots = {}
        for V, blk in lv["by_side"][side].items():
            for kind in ("train", "test"):
                for r in blk[kind]:
                    key = (int(r["decision_year"]), r["player_key"], kind)
                    slots[key] = (key, r["player_key"],
                                  asof_lv[side].get((int(r["decision_year"]), r["player_key"])))
        got = SC.values_for(list(slots.values()), spec["arg"], dev_index)
        out["lv_res"][side][name] = {k: (None if v is None else float(v)) for k, v in got.items()}
        blk = vm["by_side"][side][Y]
        tr_slots = [((int(r["decision_year"]), r["player_key"], "train"), r["player_key"],
                     (raw_by_side[side].get(r["player_key"]) or {}).get("asof_date"))
                    for r in blk["train"]]
        te_slots = [((int(r["decision_year"]), r["player_key"], "test"), r["player_key"],
                     pinned_asof[side].get(r["player_key"])) for r in blk["test"]]
        got = SC.values_for(tr_slots, spec["arg"], dev_index)
        got.update(SC.values_for(te_slots, spec["arg"], look))
        out["vm_pros"][side][name] = {k: (None if v is None else float(v)) for k, v in got.items()}
        n_lv = sum(1 for v in out["lv_res"][side][name].values() if v is not None)
        n_vm = sum(1 for v in out["vm_pros"][side][name].values() if v is not None)
        n_te = sum(1 for k, v in out["vm_pros"][side][name].items()
                   if k[2] == "test" and v is not None)
        log(f"  column {name}: R-LV {n_lv} of {len(out['lv_res'][side][name])} slots; R-VM "
            f"{n_vm} of {len(out['vm_pros'][side][name])} slots, {n_te} of {len(te_slots)} "
            f"test rows (index range to {look.cap})")
    return out


class Inputs:
    """One frame set (development or reserved) with everything a fit reads: the C03
    fold blocks, the anchor tables and groups, the wave-2 columns, the weights."""

    def __init__(self, frames: dict, *, weights: dict, absent_ok, tables: dict,
                 groups: dict, single: dict, cols: dict, label: dict, guards: dict,
                 gate_sha: str | None = None, meta: dict | None = None):
        self.frames = frames
        self.weights = weights
        self.absent_ok = absent_ok
        self.tables = tables
        self.groups = groups
        self.single = single
        self.cols = cols
        self.label = label
        self.guards = guards
        self.gate_sha = gate_sha
        self.meta = meta or {}
        self._cache: dict = {}

    # -- anchors ------------------------------------------------------------

    def fold_weights(self, fid: str, arm: str, side: str, rows: list[dict]) -> list[dict]:
        t = self.tables[fid]
        if arm == "an2_pos":
            return W2A.row_weights(rows, side, t["an1_rel"],
                                   groups=(self.groups.get(fid) or {}).get(side),
                                   group_table=t["an2_pos"])
        return W2A.row_weights(rows, side, t[arm])

    def anchor(self, fid: str, arm: str, side: str, rows: list[dict]) -> np.ndarray:
        w = self.fold_weights(fid, arm, side, rows)
        u, _missing = W2A.anchor_column(rows, w, SOURCES, self.single)
        return u

    # -- one fold under one configuration --------------------------------------

    @staticmethod
    def _sig(cfg: dict, side: str) -> str:
        return json.dumps({"anchor": cfg["anchor"], "remove": cfg["remove"][side],
                           "add": cfg["add"][side]}, sort_keys=True)

    def fold_fit(self, fid: str, side: str, fold: int, cfg: dict, *,
                 train: list[dict] | None = None, test: list[dict] | None = None,
                 cache: bool = True) -> dict:
        """The configuration's fit on one fold and the three order parts on every
        test row (parts_v3), weight-free so a scale step reads them without a refit.
        `train` / `test` replace the fold's rows (the E_refit draws)."""
        key = (fid, side, int(fold), self._sig(cfg, side))
        if cache and train is None and key in self._cache:
            return self._cache[key]
        blk = self.frames[fid]["by_side"][side][int(fold)]
        kind = FRAME_KIND[fid]
        tr = blk["train"] if train is None else train
        te = blk["test"] if test is None else test
        cols = (self.cols.get(fid) or {}).get(side) or {}
        tr_x = attach_columns(tr, cfg, side, "skill", cols, "train")
        tr_x = attach_columns(tr_x, cfg, side, "timing", cols, "train")
        te_x = attach_columns(te, cfg, side, "skill", cols, "test")
        te_x = attach_columns(te_x, cfg, side, "timing", cols, "test")
        u_tr = u_te = None
        if cfg["anchor"]:
            u_tr = self.anchor(fid, cfg["anchor"], side, tr)
            u_te = self.anchor(fid, cfg["anchor"], side, te)
        m = V3.fit_v3(tr_x, side, frame=kind, weights=self.weights, cfg=cfg, u_train=u_tr,
                      absent_ok=self.absent_ok, gate_sha=self.gate_sha)
        parts = V3.parts_v3(m, te_x, u_rows=u_te)
        by = {r["player_key"]: i for i, r in enumerate(te_x)}
        out = {"model": m, "parts": parts, "index": by,
               "w_skill0": m["w_skill_unscaled"], "w_time0": m["w_time_unscaled"],
               "receipt": {"consensus_only": m["consensus_only"],
                           "skill_keys": (m["skill"] or {}).get("keys"),
                           "timing_keys": (m["timing"] or {}).get("keys"),
                           "w_skill": m["w_skill"], "w_time": m["w_time"],
                           "n_train": m["n_train"]}}
        if cache and train is None:
            self._cache[key] = out
        return out

    def orders(self, fid: str, cfg: dict, *, sides=F.SIDES) -> tuple[dict, dict]:
        """({(side, fold, key): order_idx} over the scored rows of `sides`, receipts)."""
        out: dict = {}
        rec: dict = {}
        for side in sides:
            ks = float(cfg["scale"][side]["skill"])
            kt = float(cfg["scale"][side]["timing"])
            for fold, blk in self.frames[fid]["by_side"][side].items():
                f = self.fold_fit(fid, side, fold, cfg)
                order = V3.order_index(f["parts"], ks * f["w_skill0"], kt * f["w_time0"])
                for c in blk["scored"]:
                    i = f["index"].get(c["key"])
                    if i is None:
                        raise RuntimeError(f"{fid} {side} {fold}: no v3 score for {c['key']}")
                    out[(side, int(fold), c["key"])] = float(order[i])
                rec[f"{side}|{fold}"] = dict(f["receipt"], w_skill=ks * f["w_skill0"],
                                            w_time=kt * f["w_time0"],
                                            n_scored=len(blk["scored"]))
        return out, rec

    def scored(self, fid: str, sides=F.SIDES) -> list[dict]:
        return [c for side in sides for fold, blk in self.frames[fid]["by_side"][side].items()
                for c in blk["scored"]]

    def rows_with(self, fid: str, orders: dict, *, sides=F.SIDES) -> list[dict]:
        """The frame's scored rows with the v3 order under V3_KEY (V2 is already on
        them under V2_KEY) and the priced grades of every rater under `prices`."""
        out = []
        for side in sides:
            for fold, blk in self.frames[fid]["by_side"][side].items():
                sc = blk["scored"]
                if not sc:
                    continue
                war_map = blk["v2_model"]["war_map"]
                groups = [c["group"] for c in sc]
                fv = np.array([c["grades"][CONS] for c in sc], dtype=np.float64)
                o3 = np.array([orders[(side, int(fold), c["key"])] for c in sc])
                o2 = np.array([c["grades"][V2_KEY] for c in sc], dtype=np.float64)
                g3 = H.output_map(o3, groups, fv)
                g2 = H.output_map(o2, groups, fv)
                p3, p2, pc = (H.war_at(war_map, g) for g in (g3, g2, fv))
                for i, c in enumerate(sc):
                    row = dict(c)
                    row["grades"] = dict(c["grades"], **{V3_KEY: float(o3[i])})
                    prices = {V3_KEY: float(p3[i]), V2_KEY: float(p2[i]), CONS: float(pc[i])}
                    for src in SOURCES:
                        if c["grades"].get(src) is not None:
                            prices[src] = float(H.war_at(war_map, [c["grades"][src]])[0])
                    row["prices"] = prices
                    out.append(row)
        return out


# ---------------------------------------------------------------------------
# statistics on scored rows
# ---------------------------------------------------------------------------

def _cols(sel, key):
    return [c["grades"][key] for c in sel]


def _sel(rows, a_key, b_key):
    return [c for c in rows if c["grades"].get(a_key) is not None
            and c["grades"].get(b_key) is not None]


def within_delta_point(rows: list[dict], a_key: str, b_key: str) -> float | None:
    sel = _sel(rows, a_key, b_key)
    if not sel:
        return None
    codes = np.asarray([str(c["group"]) for c in sel])
    keep = S.kept_groups(codes)
    y = np.asarray([c["outcome"]["war"] for c in sel], dtype=np.float64)
    a = np.asarray(_cols(sel, a_key), dtype=np.float64)
    b = np.asarray(_cols(sel, b_key), dtype=np.float64)
    ta, tb = S._within_pair(a, b, y, codes, keep, np.arange(a.size))
    return None if (ta is None or tb is None) else float(ta - tb)


def mae_delta(rows: list[dict], a_key: str, b_key: str, *, B: int = B_DEFAULT,
              seed: int = SEED) -> dict:
    """mean |price_a - outcome| minus mean |price_b - outcome| on the rows both price,
    with a paired player-clustered CI95 (E_cond: prices fixed, players resampled)."""
    sel = [c for c in rows if (c.get("prices") or {}).get(a_key) is not None
           and (c.get("prices") or {}).get(b_key) is not None]
    out = {"statistic": "mae", "label": "MAE of the priced grade against the outcome",
           "n": len(sel), "a": None, "b": None, "delta": None, "ci95": None, "sd": None,
           "mde95": None, "p_gt_0": None, "B": int(B), "B_used": 0, "seed": int(seed),
           "estimator": "E_cond", "ci95_estimator": "E_cond, paired, player-clustered"}
    if not sel:
        out["status"] = "not derived: no priced rows"
        return out
    y = np.asarray([c["outcome"]["war"] for c in sel], dtype=np.float64)
    ea = np.abs(np.asarray([c["prices"][a_key] for c in sel]) - y)
    eb = np.abs(np.asarray([c["prices"][b_key] for c in sel]) - y)
    out.update(a=_rnd(ea.mean(), 4), b=_rnd(eb.mean(), 4), delta=_rnd(ea.mean() - eb.mean(), 5))
    keys = [c["key"] for c in sel]
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    out["n_clusters"] = len(ids)
    if len(sel) < SB._CLAIM_MIN_ROWS or len(ids) < SB._CLAIM_MIN_CLUSTERS:
        out["status"] = "not derived: below the floor gate"
        return out
    order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
    rng = np.random.default_rng(seed)
    d = ea - eb
    diffs = []
    for _ in range(int(B)):
        idx = SB._cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        diffs.append(float(d[idx].mean()))
    arr = np.asarray(diffs)
    sd = float(arr.std(ddof=1))
    q = np.quantile(arr, [0.025, 0.975])
    out.update(ci95=[round(float(q[0]), 4), round(float(q[1]), 4)], sd=round(sd, 5),
               mde95=round(S.Z95 * sd, 4), p_gt_0=round(float((arr > 0).mean()), 4),
               B_used=len(diffs), status="derived")
    return out


def paired(rows: list[dict], a_key: str, b_key: str, stat: str, *, B: int = B_DEFAULT,
           seed: int = SEED) -> dict:
    if stat == "mae":
        d = mae_delta(rows, a_key, b_key, B=B, seed=seed)
    else:
        sel = _sel(rows, a_key, b_key)
        d = S.paired_delta([c["key"] for c in sel], [c["group"] for c in sel],
                           [c["outcome"]["war"] for c in sel],
                           [bool(c["outcome"]["contributor"]) for c in sel],
                           _cols(sel, a_key), _cols(sel, b_key), _cols(sel, CONS),
                           statistic=stat, B=B, seed=seed)
    d["reading"] = S.reading(d.get("ci95"))
    return d


def rater_stats(rows: list[dict]) -> dict:
    out = {}
    for key, name in RATERS_OUT:
        sel = [c for c in rows if c["grades"].get(key) is not None]
        if not sel:
            continue
        st = S.rater_stats(_cols(sel, key), [c["outcome"]["war"] for c in sel],
                           [bool(c["outcome"]["contributor"]) for c in sel],
                           [c["group"] for c in sel], _cols(sel, CONS))
        pr = [c for c in sel if (c.get("prices") or {}).get(key) is not None]
        mae = (float(np.mean([abs(c["prices"][key] - c["outcome"]["war"]) for c in pr]))
               if pr else None)
        out[name] = {"spearman": st["within"], "auc": st["auc"], "n": st["n"],
                     "within": st["within"], "pooled": st["pooled"],
                     "within_rows": st["within_rows"], "within_groups": st["within_groups"],
                     "mae": _rnd(mae, 4)}
    return out


def frame_block(rows: list[dict], *, B: int = B_DEFAULT, seed: int = SEED,
                stats=STATS, comparisons=COMPARISONS, scopes=SCOPES) -> dict:
    """Rater stats and every comparison by every statistic, overall and per side,
    on identical rows (E_cond intervals)."""
    out = {"n": len(rows), "n_by_side": _n_side(rows),
           "n_players": len({c["key"] for c in rows}),
           "groups": sorted({c["group"] for c in rows}), "raters": rater_stats(rows),
           "deltas": {}, "per_side": {}}
    for scope in scopes:
        sel = rows if scope == "both" else [c for c in rows if c["side"] == scope]
        blk = {}
        for name, a, b in comparisons:
            legs = {}
            for stat in stats:
                slot = "spearman" if stat == "within" else stat
                legs[slot] = paired(sel, a, b, stat, B=B, seed=seed)
            blk[name] = legs
        if scope == "both":
            out["deltas"] = blk
        else:
            out["per_side"][scope] = {"n": len(sel), "raters": rater_stats(sel), "deltas": blk}
    return out


def fold_deltas(rows: list[dict], a_key: str, b_key: str) -> dict:
    out = {}
    for g in sorted({c["group"] for c in rows}):
        sel = [c for c in rows if c["group"] == g]
        d = within_delta_point(sel, a_key, b_key)
        out[g] = {"n": len(sel), "delta": _rnd(d),
                  "sign": None if d is None else (1 if d > 0 else (-1 if d < 0 else 0))}
    return out


def _n_side(rows) -> dict:
    out: dict = {}
    for c in rows:
        out[c["side"]] = out.get(c["side"], 0) + 1
    return out


def cell_block(rows: list[dict], *, B: int = B_DEFAULT, seed: int = SEED) -> dict:
    """The position-group cells: within Spearman of v3, V2 and consensus and the v3
    minus V2 and v3 minus consensus within deltas (E_cond) on each cell's rows. Cells
    are efv_strata.position_family on hitters and the pitcher side; never an FV cell."""
    out = {}
    for side, cell in CELLS:
        sel = [c for c in rows if c["side"] == side and (side == "pit" or c.get("cell") == cell)]
        blk = {"n": len(sel), "n_players": len({c["key"] for c in sel})}
        if len(sel) >= S.MIN_GROUP_ROWS:
            st = rater_stats(sel)
            blk["raters"] = {n: {"within": r["within"], "n": r["n"]} for n, r in st.items()}
            blk["v3_vs_efv_v2"] = {k: v for k, v in paired(sel, V3_KEY, V2_KEY, "within",
                                                           B=B, seed=seed).items()
                                   if k in ("delta", "ci95", "mde95", "n", "status", "reading")}
            blk["v3_vs_prospx_consensus"] = {
                k: v for k, v in paired(sel, V3_KEY, CONS, "within", B=B, seed=seed).items()
                if k in ("delta", "ci95", "mde95", "n", "status", "reading")}
        else:
            blk["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        out[f"{side}:{cell}"] = blk
    return out


def all_point_deltas(rows: list[dict]) -> dict:
    """Every comparison by every statistic and scope, point estimates only (one
    E_refit draw)."""
    out = {}
    for scope in SCOPES:
        sel_s = rows if scope == "both" else [c for c in rows if c["side"] == scope]
        for name, a, b in COMPARISONS:
            sel = _sel(sel_s, a, b)
            if not sel:
                continue
            codes = np.asarray([str(c["group"]) for c in sel])
            y = np.asarray([c["outcome"]["war"] for c in sel], dtype=np.float64)
            pos = np.asarray([bool(c["outcome"]["contributor"]) for c in sel])
            av = np.asarray(_cols(sel, a), dtype=np.float64)
            bv = np.asarray(_cols(sel, b), dtype=np.float64)
            cons = np.asarray(_cols(sel, CONS), dtype=np.float64)
            keep = S.kept_groups(codes)
            ta, tb = S._within_pair(av, bv, y, codes, keep, np.arange(av.size))
            ma = S.map_scores(av, list(codes), cons)
            mb = S.map_scores(bv, list(codes), cons)
            yr = SB._ranks_np(np, y)
            pa = SB._corr_np(np, SB._ranks_np(np, ma), yr)
            pb = SB._corr_np(np, SB._ranks_np(np, mb), yr)
            aa, ab = S._auc(ma, pos), S._auc(mb, pos)
            pr = [c for c in sel if (c.get("prices") or {}).get(a) is not None
                  and (c.get("prices") or {}).get(b) is not None]
            mae = None
            if pr:
                yy = np.asarray([c["outcome"]["war"] for c in pr])
                mae = float(np.mean(np.abs(np.asarray([c["prices"][a] for c in pr]) - yy))
                            - np.mean(np.abs(np.asarray([c["prices"][b] for c in pr]) - yy)))
            out[(scope, name)] = {
                "within": None if (ta is None or tb is None) else float(ta - tb),
                "pooled": None if (pa is None or pb is None) else float(pa - pb),
                "auc": None if (aa is None or ab is None) else float(aa - ab),
                "mae": mae}
    return out


# ---------------------------------------------------------------------------
# development inputs
# ---------------------------------------------------------------------------

def build_dev(*, log=print) -> Inputs:
    import efv_v2_assemble as ASM
    import efv_v2_model_class_screen as MCS
    t0 = time.time()
    frames_lv = ASM.build_frames()
    orig = ASM.build_frames
    ASM.build_frames = lambda *a, **k: frames_lv
    try:
        built = W2A.build(log=log)
    finally:
        ASM.build_frames = orig
    inputs = built["inputs"]
    ds16 = MCS._ds16_block()
    parity = MCS.base_parity(inputs, ds16)
    if not parity["reproduces"]:
        raise RuntimeError("the V2 base does not reproduce the DS-16 block; nothing read: "
                           + json.dumps(parity["frames"], default=str)[:600])
    log(f"base parity with DS-16: reproduces ({round(time.time() - t0, 1)} s)")
    cols = w2_values_dev(inputs, frames_lv, log=log)
    # the position-group cell of every scored row (efv_strata), hitters only
    universe = {p.get("player_key"): p for p in SB._load_universe(H.DATA_DIR)}
    for side in F.SIDES:
        for fid in FRAMES_DEV:
            for V, blk in inputs["frames"][fid]["by_side"][side].items():
                fr_rows = ({r["player_key"]: r for r in frames_lv[side][V][0]}
                           if fid == "lv_dev" else {})
                for c in blk["scored"]:
                    if side == "hit":
                        row = fr_rows.get(c["key"]) or {}
                        c["cell"] = ST.position_family(row, universe.get(c["key"]))
    label = _label()
    inp = Inputs(inputs["frames"], weights=inputs["weights"], absent_ok=inputs.get("absent_ok"),
                 tables=built["tables"], groups=built["groups"], single=built["single_source"],
                 cols=cols, label=label, guards=inputs["guards"],
                 meta={"base_parity": parity, "elapsed_build_s": round(time.time() - t0, 1),
                       "group_how": built.get("group_how")})
    inp.meta["v3_base_parity"] = assert_v3_base_parity(inp, FRAMES_DEV)
    log(f"v3 at base_config reproduces V2 bit for bit on every scored row "
        f"({inp.meta['v3_base_parity']['rows']} rows)")
    return inp


def assert_v3_base_parity(inp: Inputs, fids) -> dict:
    """efv_v3.fit_v3 at base_config() must give V2's order on every scored row of
    every frame, bit for bit; otherwise nothing is read."""
    base = V3.base_config()
    n = bad = 0
    for fid in fids:
        orders, _rec = inp.orders(fid, base)
        for c in inp.scored(fid):
            n += 1
            if orders[(c["side"], int(c["year"]), c["key"])] != float(c["grades"][V2_KEY]):
                bad += 1
    if bad:
        raise RuntimeError(f"v3 at base_config differs from V2 on {bad} of {n} scored rows")
    return {"rows": n, "differ": bad, "reproduces": True}


# ---------------------------------------------------------------------------
# the selection (STEP 1)
# ---------------------------------------------------------------------------

def _scope_rows(inp: Inputs, fid: str, sides) -> list[dict]:
    return inp.scored(fid, sides=tuple(sides))


def _orders_to_rows(inp: Inputs, fid: str, orders: dict, sides) -> list[dict]:
    """Scored rows of `sides` with the candidate order under V3_KEY (point reads)."""
    out = []
    for c in _scope_rows(inp, fid, sides):
        o = orders.get((c["side"], int(c["year"]), c["key"]))
        out.append(dict(c, grades=dict(c["grades"], **{V3_KEY: o})))
    return out


def _noop(inp: Inputs, fid: str, cfg: dict, step: dict) -> str | None:
    """A step that cannot move any order on the frame, decided from the current fits
    alone (no fit of the candidate): a removal of a driver no fold admitted, or a
    factor on a head no fold uses."""
    if step["kind"] not in ("remove", "scale"):
        return None
    side, head = step["side"], step["head"]
    used = False
    for fold in inp.frames[fid]["by_side"][side]:
        f = inp.fold_fit(fid, side, fold, cfg)
        if step["kind"] == "remove":
            keys = ((f["model"].get(head) or {}).get("keys") or [])
            if step["driver"] in keys:
                used = True
        else:
            w0 = f["w_skill0"] if head == "skill" else f["w_time0"]
            if w0 > 0:
                used = True
    if used:
        return None
    return ("driver admitted in no fold" if step["kind"] == "remove"
            else "head carries no weight in any fold")


def evaluate_step(inp: Inputs, cfg: dict, step: dict, cur_orders: dict) -> dict:
    """The step's within deltas against the current configuration, on its scope and
    on the whole frame, both development frames. Point estimates only."""
    cand = apply_step(cfg, step)
    out = {"name": step["name"], "kind": step["kind"], "sides": list(step["sides"]),
           "frames": {}}
    for fid in FRAMES_DEV:
        why = _noop(inp, fid, cfg, step)
        if why:
            out["frames"][fid] = {"scope_delta": 0.0, "frame_delta": 0.0, "noop": why}
            continue
        orders, _rec = inp.orders(fid, cand, sides=tuple(step["sides"]))
        full = dict(cur_orders[fid])
        full.update(orders)
        scope_rows = _orders_to_rows(inp, fid, full, step["sides"])
        cur_rows = _orders_to_rows(inp, fid, cur_orders[fid], step["sides"])
        a = within_delta_point(scope_rows, V3_KEY, CONS)
        b = within_delta_point(cur_rows, V3_KEY, CONS)
        all_rows = _orders_to_rows(inp, fid, full, F.SIDES)
        all_cur = _orders_to_rows(inp, fid, cur_orders[fid], F.SIDES)
        fa = within_delta_point(all_rows, V3_KEY, CONS)
        fb = within_delta_point(all_cur, V3_KEY, CONS)
        out["frames"][fid] = {
            "scope_delta": None if (a is None or b is None) else round(a - b, 5),
            "frame_delta": None if (fa is None or fb is None) else round(fa - fb, 5),
            "scope_vs_consensus": _rnd(a), "frame_vs_consensus": _rnd(fa),
            "noop": None}
    return out


def qualifies(ev: dict) -> bool:
    lv = ev["frames"]["lv_dev"]["scope_delta"]
    vm = ev["frames"]["vm_dev"]["scope_delta"]
    return (lv is not None and vm is not None and lv >= MIN_LV_GAIN and vm >= VM_TOLERANCE)


def select(inp: Inputs, *, B: int = B_DEFAULT, log=print, checkpoint: Path | None = None) -> dict:
    t0 = time.time()
    cfg = V3.base_config()
    rounds = []
    taken = []
    cur_orders = {fid: inp.orders(fid, cfg)[0] for fid in FRAMES_DEV}
    for rnd in range(1, MAX_STEPS + 1):
        steps = menu(cfg)
        log(f"round {rnd}: {len(steps)} steps available; current: {V3.describe(cfg)}")
        evals = []
        for step in steps:
            t1 = time.time()
            ev = evaluate_step(inp, cfg, step, cur_orders)
            ev["elapsed_s"] = round(time.time() - t1, 1)
            ev["qualifies"] = qualifies(ev)
            evals.append(ev)
            lvd, vmd = ev["frames"]["lv_dev"], ev["frames"]["vm_dev"]
            log(f"  {step['name']:40s} lv {lvd.get('scope_delta')} vm {vmd.get('scope_delta')}"
                f"{' QUALIFIES' if ev['qualifies'] else ''}"
                f"{' (no-op: ' + lvd['noop'] + ')' if lvd.get('noop') else ''}"
                f" ({ev['elapsed_s']} s)")
        best = None
        for i, ev in enumerate(evals):
            if not ev["qualifies"]:
                continue
            if best is None or ev["frames"]["lv_dev"]["scope_delta"] > evals[best]["frames"]["lv_dev"]["scope_delta"]:
                best = i
        rec = {"round": rnd, "configuration_before": copy.deepcopy(cfg),
               "evaluated": evals, "n_qualifying": sum(1 for e in evals if e["qualifies"]),
               "admitted": None}
        if best is None:
            rec["stop"] = "no step qualifies"
            rounds.append(rec)
            log(f"round {rnd}: no step qualifies; selection ends")
            break
        step = steps[best]
        cfg = apply_step(cfg, step)
        taken.append({"round": rnd, "step": step["name"],
                      "lv_dev_scope_delta": evals[best]["frames"]["lv_dev"]["scope_delta"],
                      "vm_dev_scope_delta": evals[best]["frames"]["vm_dev"]["scope_delta"]})
        rec["admitted"] = taken[-1]
        rounds.append(rec)
        cur_orders = {fid: inp.orders(fid, cfg)[0] for fid in FRAMES_DEV}
        log(f"round {rnd}: ADMITTED {step['name']}; now {V3.describe(cfg)} "
            f"({round(time.time() - t0, 1)} s)")
        if checkpoint is not None:
            write_doc({"partial": True, "rounds": rounds, "config": cfg}, checkpoint)
    if len(taken) >= MAX_STEPS:
        log(f"the cap of {MAX_STEPS} steps is reached")
    # the selected configuration's development read, with intervals
    frames_doc = {}
    for fid in FRAMES_DEV:
        orders, rec = inp.orders(fid, cfg)
        rows = inp.rows_with(fid, orders)
        t1 = time.time()
        blk = frame_block(rows, B=B)
        blk.update({"frame_version": FRAME_VERSION[fid], "receipts": rec,
                    "fold_deltas_vs_v2": fold_deltas(rows, V3_KEY, V2_KEY),
                    "fold_deltas_vs_consensus": fold_deltas(rows, V3_KEY, CONS),
                    "cells": cell_block(rows, B=B), "role": "development",
                    "window": [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])]})
        w = blk["deltas"]["v3_vs_efv_v2"]["spearman"]
        c = blk["deltas"]["v3_vs_prospx_consensus"]["spearman"]
        blk["verdict"] = (f"DEVELOPMENT ONLY (selected on these frames): within vs V2 "
                          f"{_rnd(w.get('delta'), 4)} (CI95 {w.get('ci95')}), vs consensus "
                          f"{_rnd(c.get('delta'), 4)} (CI95 {c.get('ci95')}); adjudicates nothing")
        blk["note"] = NOTE_SELECT + "; the configuration was selected on this frame"
        frames_doc[fid] = blk
        log(f"  {fid}: vs V2 {w.get('delta')} {w.get('ci95')}; vs consensus {c.get('delta')} "
            f"{c.get('ci95')} ({round(time.time() - t1, 1)} s stats)")
    return {"config": cfg, "steps": taken, "rounds": rounds, "frames": frames_doc,
            "elapsed_s": round(time.time() - t0, 1)}


def select_doc(inp: Inputs, res: dict, *, B: int) -> dict:
    return {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
        "role": "development", "adjudicates": False, "selects": True,
        "note": NOTE_SELECT,
        "owner_decision": ("EW2-6 (2026-10-08): select on the development frames only, commit "
                           "the one selected configuration, then confirm it once on the "
                           "reserved frames; this artifact is the selection and reads no "
                           "reserved row"),
        "rule": {"doc": V3.BACKTEST_DOC, "min_lv_gain": MIN_LV_GAIN,
                 "vm_tolerance": VM_TOLERANCE, "max_steps": MAX_STEPS,
                 "statistic": S.STAT_LABEL[S.PRIMARY], "scope": "the rows of the side(s) a step touches",
                 "menu": "anchors, weight factors, driver removals, wave-2 additions, in that order",
                 "anchors": list(V3.ANCHORS), "scales": list(V3.SCALES),
                 "w2_columns": {k: {kk: vv for kk, vv in v.items() if kk != "key"}
                                for k, v in V3.W2_COLUMNS.items()}},
        "label": inp.label,
        "code": {"commit": _commit(), "tool": TOOL, "tool_sha256": _sha(ROOT / TOOL),
                 "efv_v3_sha256": _sha(ROOT / "efv_v3.py"),
                 "efv_v2_candidates_sha256": _sha(ROOT / "efv_v2_candidates.py"),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "assembly_sha256": _sha(H.ASSEMBLY_PATH), "weights": inp.weights,
        "bootstrap": {"B": int(B), "seed": SEED, "estimator": "E_cond", "unit": "player cluster"},
        "reserved_guard": inp.guards, "base_parity": inp.meta.get("base_parity"),
        "selected": {"config": res["config"], "description": V3.describe(res["config"]),
                     "steps": res["steps"]},
        "rounds": res["rounds"], "frames": res["frames"],
        "elapsed_s": res["elapsed_s"] + float(inp.meta.get("elapsed_build_s") or 0.0),
    }


def spec_doc(sel: dict) -> dict:
    return {"schema": 1, "model_id": V3.MODEL_ID, "selected_at": sel["generated_at"],
            "selection_artifact": "data/_labs/efv_v3/efv_v3_select.json",
            "selection_doc": V3.BACKTEST_DOC, "owner_decision": "EW2-6 (2026-10-08)",
            "config": sel["selected"]["config"], "description": sel["selected"]["description"],
            "steps": sel["selected"]["steps"], "weights_base": sel["weights"],
            "assembly_sha256": sel["assembly_sha256"], "label": sel["label"],
            "code": sel["code"], "flag": "efv_v3.EFV_V3_ON (False)"}


# ---------------------------------------------------------------------------
# reserved inputs (STEP 3)
# ---------------------------------------------------------------------------

def _grades_for(by_key: dict, key: str, year: int) -> dict:
    p = by_key.get(key)
    if p is None:
        return {}
    g = SB._rater_grades_for_year(p, int(year))
    return {s: float(g[s]) for s in SOURCES if g.get(s) is not None}


def build_reserved(cfg: dict, *, gate_sha: str, log=print) -> Inputs:
    """R-LV (list vintages 2020 and 2021, W3) and R-VM (the 2025 debut cohort, vm2
    rule) in the C03 fold shape, each fold's V2 base fitted here; the anchor tables
    and wave-2 columns only for what the configuration names."""
    import efv_drivers as DRV
    import efv_v2_assemble as ASM
    import efv_v2_dev_read as DR
    import efv_v2_model_class_screen as MCS
    if not F.gate_sha_committed(gate_sha):
        raise F.ReservedFrameError(f"{gate_sha!r} is not the committed registration")
    t0 = time.time()
    weights = H.load_weights()
    universe = F.load_universe()
    war = L.war_seasons_table()
    res_v = sorted(F.RESERVED_LV)
    for V in res_v:
        F.guard_score_request(V, gate_sha=gate_sha, purpose="eFV v3 confirmation read")
    F.guard_vm_request([F.R_VM_FIRST_DEBUT_YEAR], gate_sha=gate_sha,
                       purpose="eFV v3 confirmation read")
    guards = {"gate_sha": gate_sha, "reserved_lv_read": res_v,
              "r_vm_cohort_read": [F.R_VM_FIRST_DEBUT_YEAR],
              "reserved_vm_pins": F.reserved_vm_pins(), "rule_last_year": H.RULE_LAST_YEAR,
              "anchor_gate_grouping": False}
    frames_dev = ASM.build_frames()
    tx = DRV.load_league_transactions(max(res_v) - 1)
    panel = DRV.load_bio_panel()
    frames_res: dict = {s: {} for s in F.SIDES}
    for side in F.SIDES:
        for V in res_v:
            rows = F.build_frame(side, V, gate_sha=gate_sha, universe=universe)
            DRV.protection_for_frame(rows, index=tx)
            DRV.bmi_for_rows(rows, panel=panel)
            DRV.pl_revision_for_rows(rows)
            labs = L.labels_for_frame(rows, universe=universe, war=war, gate_sha=gate_sha)
            frames_res[side][V] = (rows, labs)
            log(f"  R-LV {side} {V}: {len(rows)} rows ({round(time.time() - t0, 1)} s)")
    labels_dev = [(V, lab) for s in F.SIDES for V in frames_dev[s] for lab in frames_dev[s][V][1]]
    ws = DR.w_star_dev(labels_dev)
    uni_list = SB._load_universe(H.DATA_DIR)
    by_key = {p.get("player_key"): p for p in uni_list}
    # --- R-LV folds -----------------------------------------------------------------
    lv = {"kind": "lv", "folds": res_v, "by_side": {}, "per_vintage": [], "w_star_dev": ws,
          "reserved_vm_kept_w3_zero": 0}
    lv_hist: dict = {s: {} for s in F.SIDES}
    for side in F.SIDES:
        all_frames = {**frames_dev[side], **frames_res[side]}
        grades_at = {(r["player_key"], int(V)): {k: float(v) for k, v in (r.get("grades") or {}).items()
                                                if v is not None}
                     for V, (rows, _l) in all_frames.items() for r in rows}
        train_all = [dict(r, grades=grades_at[(r["player_key"], int(r["decision_year"]))])
                     for r in H.lv_training_rows(side, all_frames, gate_sha=gate_sha)]
        for V, (rows, labs) in frames_dev[side].items():
            for r, lab in zip(rows, labs):
                g = r.get("grades") or {}
                if lab.get("w3") is None or g.get(CONS) is None:
                    continue
                lv_hist[side].setdefault(int(V), []).append(
                    {"grades": {s: float(g[s]) for s in SOURCES if g.get(s) is not None},
                     "target": float(lab["w3"]), "player_key": r["player_key"],
                     "frame_row": r})
        lv["by_side"][side] = {}
        for V in res_v:
            rows, labs = frames_res[side][V]
            test = [dict(r, grades=grades_at[(r["player_key"], V)])
                    for r in H.lv_v2_rows(side, V, rows, gate_sha=gate_sha)]
            in_frame = {r["player_key"] for r in rows}
            tr = [r for r in train_all if r["decision_year"] < V and r["player_key"] not in in_frame]
            C.guard_training_rows(tr, "lv", gate_sha=gate_sha)
            model = H.fit_v2(tr, side, frame="lv", weights=weights)
            pred = H.predict_v2(model, test)
            v2 = {p["player_key"]: float(p["order_idx"]) for p in pred}
            fr_by = {r["player_key"]: r for r in rows}
            rec = {"side": side, "vintage": V, "frame_rows": len(rows), "n_train": len(tr),
                   "train_years": sorted({int(r["decision_year"]) for r in tr}),
                   "consensus_only": model["consensus_only"],
                   "skill_keys": (model["skill"] or {}).get("keys"),
                   "timing_keys": (model["timing"] or {}).get("keys"),
                   "w_skill": model["w_skill"], "w_time": model["w_time"], "n_scored": 0,
                   "reserved_vm_kept_w3_zero": 0, "label_status": {}}
            scored = []
            for r, lab in zip(rows, labs):
                k = r["player_key"]
                g = r["grades"]
                st = lab.get("status")
                rec["label_status"][st] = rec["label_status"].get(st, 0) + 1
                if g.get(CONS) is None or lab.get("w3") is None or k not in v2:
                    continue
                if st == "reserved_vm":
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
                row = {"key": k, "side": side, "year": V, "group": f"{side}|{V}",
                       "grades": grades,
                       "outcome": {"war": w3, "contributor": (ws["w_star"] is not None
                                                             and w3 >= ws["w_star"])}}
                if side == "hit":
                    row["cell"] = ST.position_family(fr_by.get(k) or {}, by_key.get(k))
                scored.append(row)
                rec["n_scored"] += 1
            lv["per_vintage"].append(rec)
            lv["by_side"][side][V] = {"train": tr, "test": test, "scored": scored,
                                      "v2_model": model, "v2_pred": pred,
                                      "frame_rows": {r["player_key"]: r for r in rows}}
            log(f"  R-LV {side} {V}: {len(tr)} train, {len(test)} test, {len(scored)} scored; "
                f"V2 skill {rec['skill_keys']} timing {rec['timing_keys']}")
    # --- R-VM fold ---------------------------------------------------------------------
    Y = F.R_VM_FIRST_DEBUT_YEAR
    vm = {"kind": "vm", "folds": [Y], "by_side": {}, "per_fold": [], "window": [Y, Y]}
    vm_hist: dict = {s: {} for s in F.SIDES}
    side_of: dict = {}
    raw_by_side: dict = {}
    pinned_asof: dict = {}
    for side in F.SIDES:
        data = H.matrix_training_rows(side)
        raw_by_side[side] = {r["player_key"]: r for r in json.loads(
            H._matrix_path(side).read_text(encoding="utf-8"))}
        for r in data:
            side_of.setdefault(r["player_key"], side)
        mine: dict = {}
        pinned = H.pinned_inputs(side, data, mine)
        pinned_asof[side] = {pk: rec.get("asof_date") for pk, rec in mine.items()}
        tr = [dict(r, grades=_grades_for(by_key, r["player_key"], r["decision_year"]))
              for r in data if int(r["decision_year"]) < Y]
        te = [r for r in data if int(r["decision_year"]) == Y]
        te2 = []
        for r in te:
            pin = pinned.get(r["player_key"])
            if pin is None:
                continue
            extra = {"bmi": DRV.bmi_asof(r["player_key"], mine[r["player_key"]].get("asof_date"),
                                         panel)}
            te2.append(dict(r, feats=pin["feats"], fv=pin["fv"], extra=extra,
                            v2=H.v2_row(pin["feats"], extra),
                            grades=_grades_for(by_key, r["player_key"], Y)))
        C.guard_training_rows(tr, "vm", gate_sha=gate_sha)
        model = H.fit_v2(tr, side, frame="vm", weights=weights)
        pred = H.predict_v2(model, te2)
        v2 = {p["player_key"]: float(p["order_idx"]) for p in pred}
        raters = list(SOURCES) + [CONS]
        scored = []
        dropped = {"not_common": 0, "debut_year_differs": 0, "no_outcome": 0}
        for r in te2:
            p = by_key.get(r["player_key"])
            if p is None:
                dropped["no_outcome"] += 1
                continue
            g = SB._rater_grades_for_year(p, Y)
            if not (g and all(x in g for x in raters)):
                dropped["not_common"] += 1
                continue
            out = SB._outcome(p)
            if out.get("debut_year") != Y:
                dropped["debut_year_differs"] += 1
                continue
            grades = {CONS: float(g[CONS]), V2_KEY: v2[r["player_key"]]}
            for src in SOURCES:
                grades[src] = float(g[src])
            row = {"key": r["player_key"], "side": side, "year": Y, "group": f"{side}|{Y}",
                   "grades": grades,
                   "outcome": {"war": float(out["war"]), "contributor": bool(out["contributor"])}}
            if side == "hit":
                row["cell"] = ST.position_family({}, p)
            scored.append(row)
        vm["per_fold"].append({"side": side, "year": Y, "n_train": len(tr), "n_test": len(te2),
                               "n_scored": len(scored), "dropped": dropped,
                               "consensus_only": model["consensus_only"],
                               "skill_keys": (model["skill"] or {}).get("keys"),
                               "timing_keys": (model["timing"] or {}).get("keys"),
                               "w_skill": model["w_skill"], "w_time": model["w_time"]})
        vm["by_side"][side] = {Y: {"train": tr, "test": te2, "scored": scored,
                                   "v2_model": model, "v2_pred": pred}}
        log(f"  R-VM {side} {Y}: {len(tr)} train, {len(te2)} pinned test, {len(scored)} scored "
            f"(dropped {dropped}); V2 skill {(model['skill'] or {}).get('keys')}")
    # the vm reliability history: debut cohorts before the reserved one
    for p in uni_list:
        k = p.get("player_key")
        side = side_of.get(k)
        out = SB._outcome(p)
        dy = out.get("debut_year")
        if side is None or dy is None or dy < min(F.DEV_VINTAGES) or dy >= Y:
            continue
        g = _grades_for(by_key, k, dy)
        if not g:
            continue
        vm_hist[side].setdefault(int(dy), []).append({"grades": g, "target": float(out["war"]),
                                                      "player_key": k, "record": p})
    frames = {"lv_res": lv, "vm_pros": vm}
    # --- anchor tables, for the named anchor only -----------------------------------
    tables: dict = {fid: {} for fid in FRAMES_RES}
    groups: dict = {fid: {} for fid in FRAMES_RES}
    single = W2A._single_source()
    if cfg["anchor"]:
        import efv_v2_pricing_calibration as PC
        hist = {"lv_res": {s: {V: [{"grades": r["grades"], "target": r["target"]} for r in rr]
                               for V, rr in lv_hist[s].items()} for s in F.SIDES},
                "vm_pros": {s: {V: [{"grades": r["grades"], "target": r["target"]} for r in rr]
                                for V, rr in vm_hist[s].items()} for s in F.SIDES}}
        for fid in FRAMES_RES:
            fr = frames[fid]
            kind = FRAME_KIND[fid]
            years = sorted({int(r["decision_year"]) for s in F.SIDES
                            for blk in fr["by_side"][s].values() for r in blk["train"] + blk["test"]})
            rel = C.build_source_reliability(hist[fid], single_source=single,
                                             target_vintages=years, frame=kind, gate_sha=gate_sha)
            rel["label"] = "W3 on list vintages" if kind == "lv" else "career WAR to date on debut cohorts"
            tables[fid]["an1_rel"] = rel
            if cfg["anchor"] == "an1_pl":
                tables[fid]["an1_pl"] = W2A.fixed_reliability(rel)
            if cfg["anchor"] == "an2_pos":
                listings = PC.load_listings()
                roles = PC.MilbRoles()
                hist_g = {s: {} for s in F.SIDES}
                for s in F.SIDES:
                    if kind == "lv":
                        for V, rr in lv_hist[s].items():
                            hist_g[s][V] = [dict(grades=r["grades"], target=r["target"],
                                                 group=W2A.row_groups(s, PC.lv_covariates(
                                                     dict(r["frame_row"], side=s), listings, roles)))
                                            for r in rr]
                        for V, blk in fr["by_side"][s].items():
                            for pk, r in blk["frame_rows"].items():
                                groups[fid].setdefault(s, {})[(pk, int(V))] = W2A.row_groups(
                                    s, PC.lv_covariates(dict(r, side=s), listings, roles))
                            for r in blk["train"]:
                                key = (r["player_key"], int(r["decision_year"]))
                                if key in groups[fid].get(s, {}):
                                    continue
                                frow = next((x for x in frames_dev[s].get(int(r["decision_year"]), ([],))[0]
                                             if x["player_key"] == r["player_key"]), None)
                                if frow is None:
                                    frow = next((x for x in frames_res[s].get(int(r["decision_year"]), ([],))[0]
                                                 if x["player_key"] == r["player_key"]), None)
                                groups[fid].setdefault(s, {})[key] = (
                                    W2A.row_groups(s, PC.lv_covariates(dict(frow, side=s), listings, roles))
                                    if frow else {"fine": W2A.UNKNOWN, "c02": W2A.UNKNOWN, "how": "none"})
                    else:
                        for V, rr in vm_hist[s].items():
                            rows_g = []
                            for r in rr:
                                read = f"{int(V)}-03-01"
                                p = r["record"]
                                cov = PC.covariates(s, player_key=r["player_key"], mlbam=p.get("mlbam_id"),
                                                    birth_date=p.get("birth_date"), read_date=read,
                                                    lo=f"{int(V) - 1}-03-01", hi=PC._next_day(read),
                                                    listings=listings, roles=roles)
                                rows_g.append(dict(grades=r["grades"], target=r["target"],
                                                   group=W2A.row_groups(s, cov)))
                            hist_g[s][V] = rows_g
                        blk = fr["by_side"][s][Y]
                        for r in blk["train"]:
                            rw = raw_by_side[s].get(r["player_key"])
                            cov = (PC.vm_covariates(s, rw, rw.get("asof_date"), listings, roles)
                                   if rw and rw.get("asof_date") else None)
                            groups[fid].setdefault(s, {})[(r["player_key"], int(r["decision_year"]))] = (
                                W2A.row_groups(s, cov))
                        for r in blk["test"]:
                            rw = raw_by_side[s].get(r["player_key"]) or {"player_key": r["player_key"]}
                            asof = pinned_asof[s].get(r["player_key"])
                            groups[fid].setdefault(s, {})[(r["player_key"], int(r["decision_year"]))] = (
                                W2A.row_groups(s, PC.vm_covariates(s, rw, asof, listings, roles)
                                               if asof else None))
                tables[fid]["an2_pos"] = W2A.group_reliability(hist_g, rel, target_vintages=years,
                                                               frame=kind, gate_sha=gate_sha)
            log(f"  {fid}: anchor table {cfg['anchor']} built for years {years}")
    # --- wave-2 columns, for the named columns only ---------------------------------------
    cols: dict = {fid: {s: {} for s in F.SIDES} for fid in FRAMES_RES}
    names = [n for s in F.SIDES for h in V3.HEADS for n in cfg["add"][s][h]]
    if names:
        cols = w2_values_reserved(names, lv=lv, vm=vm, frames_dev=frames_dev,
                                  frames_res=frames_res, raw_by_side=raw_by_side,
                                  pinned_asof=pinned_asof, gate_sha=gate_sha, log=log)
    label = _label()
    return Inputs(frames, weights=weights, absent_ok=None, tables=tables, groups=groups,
                  single=single, cols=cols, label=label, guards=guards, gate_sha=gate_sha,
                  meta={"elapsed_build_s": round(time.time() - t0, 1), "w_star_dev": ws,
                        "lv_per_vintage": lv["per_vintage"], "vm_per_fold": vm["per_fold"],
                        "reserved_vm_kept_w3_zero": lv["reserved_vm_kept_w3_zero"]})


# ---------------------------------------------------------------------------
# E_refit on the reserved frames
# ---------------------------------------------------------------------------

def _refit_draw(inp: Inputs, cfg: dict, fid: str, rng) -> list[dict]:
    """One E_refit draw: per side the pool of players (every training row's player
    and every scored player) resampled with replacement; every fold refit on the drawn
    training rows (the drawn players' rows before the fold year, the fold's drawn test
    players left out) and scored on the drawn test rows, with multiplicity."""
    fr = inp.frames[fid]
    kind = FRAME_KIND[fid]
    rows_out = []
    for side in F.SIDES:
        folds = fr["by_side"][side]
        pool_rows: dict = {}
        for fold, blk in folds.items():
            for r in blk["train"]:
                pool_rows.setdefault(r["player_key"], {})[("train", int(r["decision_year"]))] = r
            for r in blk["test"]:
                pool_rows.setdefault(r["player_key"], {})[("test", int(fold))] = r
        players = sorted(pool_rows)
        draw = rng.choice(len(players), size=len(players), replace=True)
        mult: dict = {}
        for j in draw:
            mult[players[int(j)]] = mult.get(players[int(j)], 0) + 1
        for fold, blk in folds.items():
            V = int(fold)
            test_keys = {r["player_key"] for r in blk["test"]}
            drawn_test = {pk for pk in mult if pk in test_keys}
            train = []
            for pk, m in mult.items():
                if pk in drawn_test:
                    continue
                for (kind_r, y), r in pool_rows[pk].items():
                    if kind_r == "train" and y < V:
                        train += [r] * m
            test = []
            for r in blk["test"]:
                m = mult.get(r["player_key"], 0)
                test += [r] * m
            if len(train) < H.MIN_TRAIN_ROWS or len(test) < H.MIN_TEST_ROWS:
                continue
            m2 = H.fit_v2(train, side, frame=kind, weights=inp.weights)
            p2 = {i: float(p["order_idx"]) for i, p in enumerate(H.predict_v2(m2, test))}
            f3 = inp.fold_fit(fid, side, V, cfg, train=train, test=test, cache=False)
            o3 = V3.order_index(f3["parts"], float(cfg["scale"][side]["skill"]) * f3["w_skill0"],
                                float(cfg["scale"][side]["timing"]) * f3["w_time0"])
            sc = {c["key"]: c for c in blk["scored"]}
            war_map = m2["war_map"]
            idx = [i for i, r in enumerate(test) if r["player_key"] in sc]
            if not idx:
                continue
            groups = [sc[test[i]["player_key"]]["group"] for i in idx]
            fv = np.array([sc[test[i]["player_key"]]["grades"][CONS] for i in idx])
            g3 = H.output_map(np.array([o3[i] for i in idx]), groups, fv)
            g2 = H.output_map(np.array([p2[i] for i in idx]), groups, fv)
            pr3, pr2, prc = (H.war_at(war_map, g) for g in (g3, g2, fv))
            for j, i in enumerate(idx):
                c = sc[test[i]["player_key"]]
                row = dict(c, grades=dict(c["grades"], **{V3_KEY: float(o3[i]), V2_KEY: p2[i]}))
                prices = {V3_KEY: float(pr3[j]), V2_KEY: float(pr2[j]), CONS: float(prc[j])}
                for src in SOURCES:
                    if c["grades"].get(src) is not None:
                        prices[src] = float(H.war_at(war_map, [c["grades"][src]])[0])
                row["prices"] = prices
                rows_out.append(row)
    return rows_out


def e_refit(inp: Inputs, cfg: dict, fid: str, *, B: int, seed: int = SEED_REFIT,
            log=print, point: dict | None = None) -> dict:
    """E_refit intervals for every comparison, statistic and scope on one frame: sd
    over the draws, mde95 = 1.645 sd (one-sided), CI95 the 2.5 and 97.5 percentiles of
    the draws, and the point estimate the frame block measured."""
    t0 = time.time()
    draws: dict = {}
    used = 0
    for b in range(int(B)):
        rng = np.random.default_rng(int(seed) + b)
        rows = _refit_draw(inp, cfg, fid, rng)
        if not rows:
            continue
        used += 1
        for k, d in all_point_deltas(rows).items():
            for stat, v in d.items():
                if v is not None:
                    draws.setdefault(k, {}).setdefault(stat, []).append(float(v))
        if (b + 1) % 10 == 0:
            log(f"  E_refit {fid}: {b + 1} of {B} draws ({round(time.time() - t0, 1)} s)")
    out = {"B": int(B), "B_used": used, "seed": int(seed), "estimator": "E_refit",
           "what": ("the pool resampled by player with replacement; every fold of v3 and "
                    "V2 refit on the drawn training rows (the fold's drawn test players "
                    "left out) and scored on the drawn test rows; consensus, Pipeline "
                    "and FanGraphs fixed"),
           "ci95": "2.5th and 97.5th percentile of the draws; mde95 = 1.645 x sd (one-sided)",
           "elapsed_s": round(time.time() - t0, 1), "legs": {}}
    for (scope, name), by_stat in draws.items():
        for stat, vals in by_stat.items():
            arr = np.asarray(vals, dtype=np.float64)
            if arr.size < 2:
                continue
            sd = float(arr.std(ddof=1))
            q = np.quantile(arr, [0.025, 0.975])
            slot = "spearman" if stat == "within" else stat
            pt = None
            if point is not None:
                blk = point["deltas"] if scope == "both" else point["per_side"][scope]["deltas"]
                pt = ((blk.get(name) or {}).get(slot) or {}).get("delta")
            out["legs"].setdefault(scope, {}).setdefault(name, {})[slot] = {
                "delta": pt, "ci95": [round(float(q[0]), 4), round(float(q[1]), 4)],
                "sd": round(sd, 5), "mde95": round(S.Z95 * sd, 4),
                "boot_mean": round(float(arr.mean()), 5), "B_used": int(arr.size),
                "p_gt_0": round(float((arr > 0).mean()), 4),
                "resolvable": (None if pt is None else bool(abs(pt) >= S.Z95 * sd))}
    return out


# ---------------------------------------------------------------------------
# the confirmation read (STEP 3) and its ledger rows (STEP 4)
# ---------------------------------------------------------------------------

def confirm(inp: Inputs, cfg: dict, *, B: int = B_DEFAULT, b_refit: int = B_REFIT_DEFAULT,
            log=print) -> dict:
    t0 = time.time()
    frames_doc = {}
    for fid in FRAMES_RES:
        orders, rec = inp.orders(fid, cfg)
        rows = inp.rows_with(fid, orders)
        t1 = time.time()
        blk = frame_block(rows, B=B)
        blk.update({"frame_version": FRAME_VERSION[fid], "receipts": rec,
                    "fold_deltas_vs_v2": fold_deltas(rows, V3_KEY, V2_KEY),
                    "fold_deltas_vs_consensus": fold_deltas(rows, V3_KEY, CONS),
                    "cells": cell_block(rows, B=B), "role": "reserved",
                    "window": [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])],
                    "outcome": ("W3 (WAR over the first three MLB seasons, 0 if no debut "
                                "within three seasons of V)" if fid == "lv_res"
                                else "career WAR to date (2025 and 2026 seasons)")})
        log(f"  {fid}: E_cond block ({round(time.time() - t1, 1)} s); E_refit B {b_refit} starts")
        blk["e_refit"] = e_refit(inp, cfg, fid, B=b_refit, log=log, point=blk)
        w = blk["deltas"]["v3_vs_efv_v2"]["spearman"]
        c = blk["deltas"]["v3_vs_prospx_consensus"]["spearman"]
        rc = (((blk["e_refit"]["legs"].get("both") or {}).get("v3_vs_prospx_consensus") or {})
              .get("spearman") or {})
        rv = (((blk["e_refit"]["legs"].get("both") or {}).get("v3_vs_efv_v2") or {})
              .get("spearman") or {})
        blk["verdict"] = verdict_text(c, rc, w, rv)
        blk["note"] = NOTE_CONFIRM
        frames_doc[fid] = blk
        log(f"  {fid}: vs V2 {w.get('delta')} E_cond {w.get('ci95')} E_refit {rv.get('ci95')}; "
            f"vs consensus {c.get('delta')} E_cond {c.get('ci95')} E_refit {rc.get('ci95')}")
    return {"frames": frames_doc, "elapsed_s": round(time.time() - t0, 1)}


def verdict_text(c: dict, rc: dict, w: dict, rv: dict) -> str:
    """The reading under owner EW2-7: the within point against consensus and V2, and
    whether the E_refit CI95 against consensus clears zero."""
    d = c.get("delta")
    lo = (rc.get("ci95") or [None, None])[0]
    if d is None:
        return "not derived"
    if lo is not None and lo > 0:
        head = f"eFV v3 beats consensus within by {d:+.4f} (E_refit CI95 clear of zero)"
    elif d > 0:
        head = f"eFV v3 reads {d:+.4f} within over consensus; not resolved (E_refit CI95 spans zero)"
    else:
        head = f"eFV v3 reads {d:+.4f} within against consensus; ties or trails"
    dv = w.get("delta")
    tail = "" if dv is None else f"; vs served eFV (V2) {dv:+.4f} (E_refit CI95 {rv.get('ci95')})"
    return head + tail


def confirm_doc(inp: Inputs, spec: dict, res: dict, *, B: int, b_refit: int) -> dict:
    return {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
        "role": "reserved", "adjudicates": True, "selects": False, "one_read": True,
        "note": NOTE_CONFIRM,
        "owner_decision": ("EW2-6 (2026-10-08): the 2026-12-01 reserved read and the registration "
                           "sequencing replaced by a same-day backtest; the configuration was "
                           "selected on the development frames and committed before this read, "
                           "and nothing here was tuned on a reserved-frame number"),
        "ship_rule": ("EW2-7: ship eFV v3 if its within Spearman beats served eFV (V2) on both "
                      "reserved frames (point estimates, pooled over sides); copy claims 'beats "
                      "consensus' only if its CI95 lower bound is above 0"),
        "gate": {"doc": F.GATE_DOC, "sha": inp.gate_sha, "guards": inp.guards},
        "spec": {"path": "data/efv_v3_spec.json", "sha256": _sha(V3.SPEC_PATH),
                 "config": spec["config"], "description": spec.get("description"),
                 "steps": spec.get("steps"), "selected_at": spec.get("selected_at"),
                 "selection_commit": (spec.get("code") or {}).get("commit")},
        "label": inp.label,
        "code": {"commit": _commit(), "tool": TOOL, "tool_sha256": _sha(ROOT / TOOL),
                 "efv_v3_sha256": _sha(ROOT / "efv_v3.py"),
                 "efv_v2_candidates_sha256": _sha(ROOT / "efv_v2_candidates.py"),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "assembly_sha256": _sha(H.ASSEMBLY_PATH), "weights": inp.weights,
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "secondary": S.STAT_LABEL[S.SECONDARY],
                      "veto": S.STAT_LABEL["auc"], "mae": "MAE of the priced grade (the fold's "
                      "consensus-FV-to-WAR line at each rater's grade) against the outcome",
                      "min_group_rows": S.MIN_GROUP_ROWS,
                      "group": "(side, list vintage) on R-LV; (side, debut year) on R-VM",
                      "cells": "efv_strata.position_family on hitters (C, IF, OF); pitchers one cell"},
        "bootstrap": {"E_cond": {"B": int(B), "seed": SEED, "unit": "player cluster"},
                      "E_refit": {"B": int(b_refit), "seed": SEED_REFIT, "unit": "player cluster"}},
        "frames_built": {"lv_res": {"per_vintage": inp.meta.get("lv_per_vintage"),
                                    "w_star_dev": inp.meta.get("w_star_dev"),
                                    "reserved_vm_kept_w3_zero": inp.meta.get("reserved_vm_kept_w3_zero")},
                         "vm_pros": {"per_fold": inp.meta.get("vm_per_fold"),
                                     "rule": "vm2: both scored sources and the consensus graded "
                                             "inside the debut year's preseason window, the pinned "
                                             "read as the input, debut year equal to the cohort"}},
        "anchor_tables": {fid: {arm: {k: v for k, v in t.items() if k not in ("stats",)}
                                for arm, t in inp.tables[fid].items()} for fid in FRAMES_RES},
        "frames": res["frames"],
        "elapsed_s": res["elapsed_s"] + float(inp.meta.get("elapsed_build_s") or 0.0),
    }


# -- progress-ledger rows -------------------------------------------------------------

_LEDGER_FRAME = {"lv_dev": "lv_dev", "vm_dev": "vm_dev", "lv_res": "lv_res", "vm_pros": "vm_pros"}
_LEDGER_RATERS = (("efv", "efv_v3"), ("efv_v2_base", "efv_v2"), ("prospx_consensus", "prospx_consensus"),
                  ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
_LEDGER_DELTAS = (("vs_efv_v2_base", "v3_vs_efv_v2"), ("vs_prospx_consensus", "v3_vs_prospx_consensus"),
                  ("vs_mlb_pipeline", "v3_vs_mlb_pipeline"), ("vs_fangraphs", "v3_vs_fangraphs"),
                  ("efv_v2_base_vs_prospx_consensus", "efv_v2_vs_prospx_consensus"))


def ledger_rows(doc: dict, *, artifact: Path, trigger: str, role: str, date: str,
                now_iso: str) -> list[dict]:
    """Rows in data/efv_progress.json's shape, copied from the artifact: role
    development (the selection's frames) or reserved (the confirmation's, trigger
    look). Every number is a copy; the content hash is the ledger's own."""
    import efv_progress as P
    if trigger not in P.TRIGGERS:
        raise ValueError(trigger)
    lab = doc.get("label") or {}
    mv = {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    rows = []
    for fid, f in (doc.get("frames") or {}).items():
        meta = P.FRAMES[_LEDGER_FRAME[fid]]
        if meta["role"] != role:
            raise ValueError(f"{fid} is registered as {meta['role']}, not {role}")
        raters = {}
        for name, key in _LEDGER_RATERS:
            r = (f.get("raters") or {}).get(key) or {}
            if r.get("spearman") is None and r.get("auc") is None:
                continue
            raters[name] = {"spearman": r.get("spearman"), "auc": r.get("auc"), "n": r.get("n")}
        refit = ((f.get("e_refit") or {}).get("legs") or {}).get("both") or {}
        deltas = {}
        for name, comp in _LEDGER_DELTAS:
            legs = {}
            for metric in ("spearman", "auc"):
                leg = ((f.get("deltas") or {}).get(comp) or {}).get(metric)
                if not leg:
                    continue
                rl = ((refit.get(comp) or {}).get(metric) or {})
                entry = {"delta": leg.get("delta"), "ci95": leg.get("ci95"),
                         "mde95": rl.get("mde95") if rl else leg.get("mde95"),
                         "mde95_estimator": "E_refit" if rl else leg.get("estimator"),
                         "ci95_estimator": leg.get("ci95_estimator"),
                         "resolvable": rl.get("resolvable") if rl else None,
                         "reading": leg.get("reading"),
                         "key": f"frames.{fid}.deltas.{comp}.{metric}"}
                if rl:
                    entry["e_refit"] = {"ci95": rl.get("ci95"), "sd": rl.get("sd"),
                                        "B_used": rl.get("B_used"),
                                        "key": f"frames.{fid}.e_refit.legs.both.{comp}.{metric}"}
                legs[metric] = entry
            if legs:
                deltas[name] = legs
        nbs = {s: (f.get("n_by_side") or {})[s] for s in P.STRATA if (f.get("n_by_side") or {}).get(s)} or None
        cons = (deltas.get("vs_prospx_consensus") or {}).get("spearman") or {}
        row = {"run_id": None, "date": date, "trigger": trigger, "model_id": V3.MODEL_ID,
               "model_version": dict(mv), "frame": _LEDGER_FRAME[fid],
               "frame_version": f.get("frame_version"), "role": meta["role"],
               "tilted": bool(meta["tilted"]), "window": f.get("window"), "n": f.get("n"),
               "n_by_side": nbs, "raters": raters, "deltas": deltas,
               "resolvable": cons.get("resolvable"), "verdict": f.get("verdict"), "share": None,
               "sources": [dict(s) for s in src], "note": f.get("note") or "",
               "last_verified_at": now_iso,
               "statistic": S.STAT_LABEL[S.PRIMARY],
               "secondary": {"statistic": S.STAT_LABEL["pooled"],
                             "raters": {name: ((f.get("raters") or {}).get(key) or {}).get("pooled")
                                        for name, key in _LEDGER_RATERS
                                        if ((f.get("raters") or {}).get(key) or {}).get("pooled") is not None},
                             "deltas": {name: {k: (((f.get("deltas") or {}).get(comp) or {}).get("pooled") or {}).get(k)
                                               for k in ("delta", "ci95", "mde95", "reading")}
                                        for name, comp in _LEDGER_DELTAS
                                        if ((f.get("deltas") or {}).get(comp) or {}).get("pooled")}}}
        P._finish(row)
        row["run_id"] = f"{doc.get('generated_at')}|{_LEDGER_FRAME[fid]}|{row['content_hash'][:8]}"
        rows.append(row)
    return rows


def append_ledger(doc: dict, *, artifact: Path, trigger: str, role: str,
                  ledger_path: Path | None = None) -> dict:
    """The rows into data/efv_progress.json and its durable copy (efv_progress.LEDGER_PATH
    unless `ledger_path` names another: a worktree whose .cache is a junction to the
    main tree hands in its own, so the main tree's durable copy is untouched)."""
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    rows = ledger_rows(doc, artifact=artifact, trigger=trigger, role=role,
                       date=now.date().isoformat(), now_iso=now_iso)
    return P.commit_rows(rows, data_dir=P.DATA_DIR, ledger_path=ledger_path,
                         sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def summary_lines(doc: dict) -> list[str]:
    out = []
    for fid, f in doc["frames"].items():
        for name in ("v3_vs_efv_v2", "v3_vs_prospx_consensus", "v3_vs_mlb_pipeline", "v3_vs_fangraphs"):
            w = f["deltas"][name]["spearman"]
            rl = ((((f.get("e_refit") or {}).get("legs") or {}).get("both") or {}).get(name) or {}).get("spearman") or {}
            out.append(f"{fid} {name:26s} within {w.get('delta')} E_cond {w.get('ci95')}"
                       + (f" E_refit {rl.get('ci95')}" if rl else ""))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="build the development inputs, parity, counts")
    ap.add_argument("--select", action="store_true", help="STEP 1: the forward selection")
    ap.add_argument("--confirm", action="store_true", help="STEP 3: the one reserved read")
    ap.add_argument("--gate-sha", default=None, help="the committed registration's 40-hex sha")
    ap.add_argument("--B", type=int, default=B_DEFAULT, help="E_cond draws")
    ap.add_argument("--b-refit", type=int, default=B_REFIT_DEFAULT, help="E_refit draws")
    ap.add_argument("--no-ledger", action="store_true", help="write the artifact, no ledger row")
    ap.add_argument("--ledger-path", default=None,
                    help="the durable ledger copy (default efv_progress.LEDGER_PATH; a "
                         "worktree with a junctioned .cache names its own)")
    a = ap.parse_args(argv)
    ledger_path = Path(a.ledger_path) if a.ledger_path else None

    def log(msg):
        print(msg, flush=True)
    if L.provider() != FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {FROZEN_PROVIDER!r}")
        return 2
    if a.check or a.select:
        inp = build_dev(log=log)
        if a.check:
            import efv_v2_model_class_screen as MCS
            counts = {fid: {"folds": inp.frames[fid]["folds"], "n": len(inp.scored(fid)),
                            "n_by_side": _n_side(inp.scored(fid))} for fid in FRAMES_DEV}
            log(json.dumps({"check": True, "guards": inp.guards, "counts": counts,
                            "label": inp.label, "weights": inp.weights,
                            "base_parity": inp.meta.get("base_parity"),
                            "menu_size": len(menu(V3.base_config())),
                            "w2_columns": {fid: {s: {n: sum(1 for v in vals.values() if v is not None)
                                                     for n, vals in by.items()}
                                                 for s, by in inp.cols[fid].items()}
                                           for fid in FRAMES_DEV}}, indent=1, default=str))
            return 0
        if SELECT_PATH.exists():
            log(f"refused: {SELECT_PATH} exists; the selection ran once")
            return 2
        res = select(inp, B=a.B, log=log, checkpoint=LAB_DIR / "efv_v3_select_partial.json")
        doc = select_doc(inp, res, B=a.B)
        out = write_doc(doc, SELECT_PATH)
        write_doc(spec_doc(doc), V3.SPEC_PATH)
        (LAB_DIR / "efv_v3_select_partial.json").unlink(missing_ok=True)
        log(f"wrote {out} and {V3.SPEC_PATH}: {doc['selected']['description']}")
        if not a.no_ledger:
            r = append_ledger(doc, artifact=out, trigger="efv_change", role="development",
                              ledger_path=ledger_path)
            log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if a.confirm:
        if CONFIRM_PATH.exists():
            log(f"refused: {CONFIRM_PATH} exists; the reserved frames are read once")
            return 2
        if not a.gate_sha:
            log("refused: --gate-sha is required (the committed registration)")
            return 2
        spec = V3.load_spec()
        cfg = V3.spec_config(spec)
        log(f"configuration: {V3.describe(cfg)} (spec selected at {spec.get('selected_at')})")
        inp = build_reserved(cfg, gate_sha=a.gate_sha, log=log)
        res = confirm(inp, cfg, B=a.B, b_refit=a.b_refit, log=log)
        doc = confirm_doc(inp, spec, res, B=a.B, b_refit=a.b_refit)
        out = write_doc(doc, CONFIRM_PATH)
        log(f"wrote {out} ({doc['elapsed_s']} s)")
        for line in summary_lines(doc):
            log(line)
        if not a.no_ledger:
            r = append_ledger(doc, artifact=out, trigger="look", role="reserved",
                              ledger_path=ledger_path)
            log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

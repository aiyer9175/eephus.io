# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV v4 backtest (EFV4_SELECT_SHIP; owner EW2-8 to EW2-12, 2026-10-08): SELECT on
the development frames over the v4 new-source columns, then read the one committed
configuration ONCE on the SPENT reserved frames. The rule is fixed in
docs/efv-v2/EFV_V4_BACKTEST.md before any combined read; this tool runs it and records
every step. It reuses tools/efv_v3_backtest's inputs, fits, statistics and E_refit; only
the menu (add steps over efv_v4.menu_columns) and the column builders are its own.

    --check      build the development inputs and every menu column through its family's
                 own builder, assert the V2 base reproduces the DS-16 block and that v4
                 at base_config reproduces V2 bit for bit, print coverage. No statistic
                 of any candidate.
    --select     the forward selection on lv_dev and vm_dev exactly as the document
                 fixes it: every evaluated step and its deltas are written to
                 data/_labs/efv_v4/efv_v4_select.json, the one selected configuration to
                 data/efv_v4_spec.json (efv_v4.SPEC_PATH), and two development rows
                 (model efv_v4, frames lv_dev and vm_dev) to data/efv_progress.json.
    --spent --gate-sha SHA
                 the ONE read of the committed configuration on R-LV (list vintages 2020
                 and 2021) and R-VM (the 2025 debut cohort, vm2 rule), both SPENT by the
                 v3 confirmation of 2026-10-08, against served eFV (V2), PROSPX consensus,
                 MLB Pipeline and FanGraphs: within and pooled Spearman, contributor AUC
                 and the MAE of the priced grade, each with E_cond CI95 (B 2000) and
                 E_refit CI95 (--b-refit draws), overall and per side, plus the
                 position-group cells. Every block is labelled spent. Written to
                 data/_labs/efv_v4/efv_v4_spent.json; NO ledger row (a spent read is not a
                 look). A second spent run refuses while the artifact exists.

Nothing served moves: efv_v4.EFV_V4_ON stays False and no served path reads an artifact
of this tool. GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only strata are side,
vintage and position group. Nothing here groups, counts or averages rows by consensus-FV
level.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_labels as L  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_v3 as V3  # noqa: E402
import efv_v3_backtest as BT  # noqa: E402
import efv_v4 as V4  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

TOOL = "tools/efv_v4_backtest.py"
ITEM = "EFV4_SELECT_SHIP"
LAB_DIR = H.DATA_DIR / "_labs" / "efv_v4"
SELECT_PATH = LAB_DIR / "efv_v4_select.json"
SPENT_PATH = LAB_DIR / "efv_v4_spent.json"
FROZEN_PROVIDER = BT.FROZEN_PROVIDER
CONS = BT.CONS
SOURCES = BT.SOURCES
#: The candidate's grade slot on a scored row is efv_v3_backtest's (the machinery is
#: shared); every artifact and ledger row names it efv_v4.
CAND_KEY = BT.V3_KEY
V2_KEY = BT.V2_KEY
B_DEFAULT = BT.B_DEFAULT
SEED = BT.SEED
B_REFIT_DEFAULT = BT.B_REFIT_DEFAULT
SEED_REFIT = BT.SEED_REFIT
MIN_LV_GAIN = BT.MIN_LV_GAIN
VM_TOLERANCE = BT.VM_TOLERANCE
MAX_STEPS = BT.MAX_STEPS
FRAMES_DEV = BT.FRAMES_DEV
FRAMES_RES = BT.FRAMES_RES
FRAME_VERSION = BT.FRAME_VERSION
RATERS_OUT = ((CAND_KEY, "efv_v4"), (V2_KEY, "efv_v2"), (CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
COMPARISONS = (("v4_vs_efv_v2", CAND_KEY, V2_KEY),
               ("v4_vs_prospx_consensus", CAND_KEY, CONS),
               ("v4_vs_mlb_pipeline", CAND_KEY, "mlb_pipeline"),
               ("v4_vs_fangraphs", CAND_KEY, "fangraphs"),
               ("efv_v2_vs_prospx_consensus", V2_KEY, CONS))
CELLS = BT.CELLS
SPENT_LABEL = "spent frame, read after the 10-08 confirmation"
NOTE_SELECT = ("eFV v4 forward selection on the development frames (spent, not a claim); "
               "owner EW2-10")
NOTE_SPENT = ("eFV v4 at the committed configuration on the spent reserved frames (read "
              "once by v3 on 2026-10-08 under the owner's waiver); chooses and tunes "
              "nothing; not a look")
_now = BT._now
_sha = BT._sha
_commit = BT._commit
_rnd = BT._rnd
write_doc = BT.write_doc


# ---------------------------------------------------------------------------
# names: the shared machinery labelled v4 for the life of a run
# ---------------------------------------------------------------------------

@contextmanager
def v4_names():
    orig = (BT.COMPARISONS, BT.RATERS_OUT)
    BT.COMPARISONS, BT.RATERS_OUT = COMPARISONS, RATERS_OUT
    try:
        yield
    finally:
        BT.COMPARISONS, BT.RATERS_OUT = orig


@contextmanager
def frames_fixed(frames_lv):
    import efv_v2_assemble as ASM
    orig = ASM.build_frames
    ASM.build_frames = lambda *a, **k: frames_lv
    try:
        yield
    finally:
        ASM.build_frames = orig


# ---------------------------------------------------------------------------
# the step menu: one ADD step per remaining v4 column
# ---------------------------------------------------------------------------

def menu(cfg: dict) -> list[dict]:
    taken = set(V4.added(cfg))
    out = []
    for name, spec in V4.menu_columns().items():
        if name in taken:
            continue
        out.append({"kind": "add", "side": spec["side"], "head": spec["head"],
                    "column": name, "family": spec["family"], "sides": [spec["side"]],
                    "name": f"add:{spec['side']}.{spec['head']}.{name}"})
    return out


def apply_step(cfg: dict, step: dict) -> dict:
    if step["kind"] != "add":
        raise ValueError(step)
    return V4.with_column(cfg, step["column"])


# ---------------------------------------------------------------------------
# column values through each family's own builder
# ---------------------------------------------------------------------------

def _by_family(names) -> dict:
    menu_ = V4.menu_columns()
    out: dict = {}
    for n in names:
        out.setdefault(menu_[n]["family"], []).append(dict(menu_[n], name=n))
    return out


def _slots(inp: BT.Inputs, fid: str, side: str):
    for _fold, blk in inp.frames[fid]["by_side"][side].items():
        for kind in ("train", "test"):
            for r in blk[kind]:
                yield (int(r["decision_year"]), r["player_key"], kind), r


def _vm_meta(side: str) -> tuple[dict, dict]:
    """(raw matrix rows by player_key, pinned preseason read date by player_key)."""
    raw = {r["player_key"]: r for r in json.loads(
        H._matrix_path(side).read_text(encoding="utf-8"))}
    mine: dict = {}
    H.pinned_inputs(side, H.matrix_training_rows(side), mine)
    return raw, {pk: rec.get("asof_date") for pk, rec in mine.items()}


def _lv_rows(frames_lv: dict, inp: BT.Inputs | None = None, fid: str | None = None) -> dict:
    """{(side, V, player_key): frame row} over the development frames and, when `inp`
    and a reserved frame id are given, that frame's own rows."""
    out = {}
    for side in F.SIDES:
        for V, (rows, _labs) in frames_lv[side].items():
            for r in rows:
                out[(side, int(V), r["player_key"])] = r
        if inp is not None and fid is not None:
            for V, blk in inp.frames[fid]["by_side"][side].items():
                for pk, r in (blk.get("frame_rows") or {}).items():
                    out[(side, int(V), pk)] = r
    return out


def _empty(fids) -> dict:
    return {fid: {s: {} for s in F.SIDES} for fid in fids}


def _il(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_w2_il_backfill as M
    out = _empty(fids)
    if gate_sha:
        cols, _cov = M.spent_values(inp, got, gate_sha=gate_sha)
        for fid in fids:
            for a in arms:
                out[fid][a["side"]][a["name"]] = cols[fid][a["side"]][a["name"]]
        return out
    lv_fid, vm_fid = fids
    for side in {a["side"] for a in arms}:
        reads = M.lv_reads(side, frames_lv)
        raw, _pinned = _vm_meta(side)
        vm_r = M.vm_reads(side, H.matrix_training_rows(side), raw)
        for a in [x for x in arms if x["side"] == side]:
            st = a["arg"]
            out[lv_fid][side][a["name"]] = {
                slot: M.transformed(st, (reads.get((slot[0], slot[1])) or {}).get(st))
                for slot, _r in _slots(inp, lv_fid, side)}
            out[vm_fid][side][a["name"]] = {
                slot: M.transformed(st, (vm_r.get(slot[1]) or {}).get(st))
                for slot, _r in _slots(inp, vm_fid, side)}
    return out


def _nri(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_w2_nri as M
    out = _empty(fids)
    index = M.look_index(gate_sha) if gate_sha else M.default_index()
    lv_fid, vm_fid = fids
    lv_rows = _lv_rows(frames_lv, inp, lv_fid)
    cols_lv, _c = M.inputs_columns(inp, lv_fid, "lv", index, lv_rows=lv_rows)
    cols_vm, _c = M.inputs_columns(inp, vm_fid, "vm", index)
    for a in arms:
        out[lv_fid][a["side"]][a["name"]] = cols_lv[a["side"]][a["name"]]
        out[vm_fid][a["side"]][a["name"]] = cols_vm[a["side"]][a["name"]]
    return out


def _pbp(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_w2_pbp as M
    out = _empty(fids)
    if gate_sha:
        cols, _cov, _keep = M.spent_values(inp, got, gate_sha=gate_sha)
        for fid in fids:
            for a in arms:
                out[fid][a["side"]][a["name"]] = cols[fid][a["side"]][a["name"]]
        return out
    lv_fid, vm_fid = fids
    for side in {a["side"] for a in arms}:
        reads = M.lv_values(side, frames_lv)
        keep = {k for k, p in reads.items() if M.has_all(p, side)}
        raw, _pinned = _vm_meta(side)
        vm_r = M.vm_values(side, H.matrix_training_rows(side), raw)
        vm_keep = {k for k, p in vm_r.items() if M.has_all(p, side)}
        for a in [x for x in arms if x["side"] == side]:
            st = a["arg"]
            out[lv_fid][side][a["name"]] = {
                slot: ((reads.get((slot[0], slot[1])) or {}).get(st)
                       if (slot[0], slot[1]) in keep else None)
                for slot, _r in _slots(inp, lv_fid, side)}
            out[vm_fid][side][a["name"]] = {
                slot: ((vm_r.get(slot[1]) or {}).get(st) if slot[1] in vm_keep else None)
                for slot, _r in _slots(inp, vm_fid, side)}
    return out


def _pbp_bb(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_w2_pbp_bb as M
    out = _empty(fids)
    cap = M.SPENT_SEASON_CAP if gate_sha else M.DEV_SEASON_CAP
    lv_fid, vm_fid = fids
    lv_rows = _lv_rows(frames_lv, inp, lv_fid)
    cols_lv, _c, _corr = M.inputs_columns(inp, lv_fid, "lv", season_cap=cap, lv_rows=lv_rows)
    cols_vm, _c, _corr = M.inputs_columns(inp, vm_fid, "vm", season_cap=cap)
    for a in arms:
        out[lv_fid][a["side"]][a["name"]] = cols_lv[a["side"]][a["name"]]
        out[vm_fid][a["side"]][a["name"]] = cols_vm[a["side"]][a["name"]]
    return out


def _popmle(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_w2_popmle as M
    out = _empty(fids)
    lv_fid, vm_fid = fids
    frames_all = {s: dict(frames_lv[s]) for s in F.SIDES}
    if gate_sha:
        for (side, V), rows in (got or {}).get("res", {}).items():
            frames_all[side][int(V)] = (rows, [])
    raw_by_side = {s: _vm_meta(s)[0] for s in F.SIDES}
    pinned = {s: _vm_meta(s)[1] for s in F.SIDES}
    vm_years = sorted({int(r["decision_year"]) for s in F.SIDES
                       for blk in inp.frames[vm_fid]["by_side"][s].values()
                       for r in blk["train"] + blk["test"]})
    excl = M.lv_exclusions(frames_all) | M.vm_exclusions(raw_by_side, vm_years)
    tr = M.Translator(excl, gate_sha=gate_sha)
    for a in arms:
        s = a["side"]
        out[lv_fid][s][a["name"]] = M.lv_values(tr, s, frames_all[s])
        out[vm_fid][s][a["name"]] = M.vm_values(tr, s, inp.frames[vm_fid]["by_side"][s],
                                                raw_by_side[s], pinned[s])
    out["_receipts"] = dict(sorted(tr.receipts.items()))
    return out


def _raters(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_rater_panel as RP
    import efv_w2_raters as M
    out = _empty(fids)
    doc = RP.load_panel(M.PANEL_PATH)
    if gate_sha:
        if not doc.get("reserved_years_built") or not RP.registration_names_reserved():
            raise F.ReservedFrameError("the rater panel has no reserved list years")
    panel = M.Panel.from_doc(doc, allow_reserved=bool(gate_sha))
    lv_fid, vm_fid = fids
    for a in arms:
        s = a["side"]
        by_v = dict(frames_lv[s])
        if gate_sha:
            for (side, V), rows in (got or {}).get("res", {}).items():
                if side == s:
                    by_v[int(V)] = (rows, [])
        v, _inf = M.lv_values(s, by_v, M.lv_slots(inp.frames[lv_fid]["by_side"][s]), panel,
                              gate_sha=gate_sha)
        out[lv_fid][s][a["name"]] = v
        raw, pinned = _vm_meta(s)
        asof = {"train": {pk: r.get("asof_date") for pk, r in raw.items()}, "test": pinned}
        vv, _vinf = M.vm_values(s, inp.frames[vm_fid]["by_side"][s], asof, panel)
        out[vm_fid][s][a["name"]] = vv
    return out


def _report(inp, fids, frames_lv, arms, *, got=None, gate_sha=None) -> dict:
    import efv_w2_report_read as RR
    out = _empty(fids)
    store = RR.Store()
    rarms = [{"name": a["name"], "side": a["side"], "head": a["head"],
              "field_column": a["arg"]} for a in arms]
    lv_fid, vm_fid = fids
    lv_rows = _lv_rows(frames_lv, inp, lv_fid)
    cols_lv, _c = RR.inputs_columns(inp, lv_fid, "lv", store, frames_lv, rarms,
                                    lv_rows=lv_rows)
    cols_vm, _c = RR.inputs_columns(inp, vm_fid, "vm", store, frames_lv, rarms)
    for a in arms:
        out[lv_fid][a["side"]][a["name"]] = cols_lv[a["side"]][a["name"]]
        out[vm_fid][a["side"]][a["name"]] = cols_vm[a["side"]][a["name"]]
    out["_extractor"] = store.model_id
    return out


BUILDERS = {"il": _il, "nri": _nri, "pbp": _pbp, "pbp_bb": _pbp_bb, "popmle": _popmle,
            "raters": _raters, "report": _report}


def v4_values(inp: BT.Inputs, fids, frames_lv: dict, names, *, got=None,
              gate_sha: str | None = None, log=print) -> tuple[dict, dict]:
    """({fid: {side: {name: {(year, pk, kind): value | None}}}}, receipts) for the named
    menu columns on the frames of `inp` (development: fids lv_dev, vm_dev; spent: lv_res,
    vm_pros with `got` and the gate sha), each family through its own builder."""
    cols = _empty(fids)
    receipts: dict = {"coverage": {}, "families": {}}
    for fam, arms in _by_family(names).items():
        t0 = time.time()
        got_f = BUILDERS[fam](inp, fids, frames_lv, arms, got=got, gate_sha=gate_sha)
        for k in list(got_f):
            if str(k).startswith("_"):
                receipts["families"][f"{fam}:{k}"] = got_f.pop(k)
        for fid in fids:
            for s in F.SIDES:
                for name, vals in got_f[fid][s].items():
                    cols[fid][s][name] = vals
                    n_te = sum(1 for k, v in vals.items() if k[2] == "test" and v is not None)
                    n_all = sum(1 for v in vals.values() if v is not None)
                    receipts["coverage"].setdefault(fid, {})[name] = {
                        "slots": len(vals), "with_value": n_all,
                        "test_slots": sum(1 for k in vals if k[2] == "test"),
                        "test_with_value": n_te}
        log(f"  family {fam}: {len(arms)} columns built ({round(time.time() - t0, 1)} s)")
    return cols, receipts


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def build_dev(*, names=None, log=print) -> tuple[BT.Inputs, dict, dict]:
    """efv_v3_backtest.build_dev with the v3 wave-2 column builder replaced by nothing
    (the v3 menu is not built) and the v4 menu columns built after; base parity with
    DS-16 and v4-at-base parity asserted before anything is read."""
    import efv_v2_assemble as ASM
    frames_lv = ASM.build_frames()
    orig = BT.w2_values_dev
    BT.w2_values_dev = lambda inputs, fl, log=print: _empty(FRAMES_DEV)
    try:
        with frames_fixed(frames_lv):
            inp = BT.build_dev(log=log)
    finally:
        BT.w2_values_dev = orig
    names = list(V4.menu_columns()) if names is None else list(names)
    t0 = time.time()
    cols, receipts = v4_values(inp, FRAMES_DEV, frames_lv, names, log=log)
    inp.cols = cols
    inp.meta["elapsed_columns_s"] = round(time.time() - t0, 1)
    inp.meta["column_receipts"] = receipts
    return inp, frames_lv, receipts


def build_spent(cfg: dict, *, gate_sha: str, log=print) -> tuple[BT.Inputs, dict, dict]:
    """The reserved frames through efv_v3_backtest.build_reserved at V2 (the frame rows
    captured), then the configuration's columns through the families' spent builders."""
    import efv_w2_il_backfill as W2I
    inp, got = W2I.build_reserved_capturing(gate_sha, log=log)
    frames_lv = got["dev"]
    parity = BT.assert_v3_base_parity(inp, FRAMES_RES)
    inp.meta["v4_base_parity"] = parity
    log(f"v4 at base_config reproduces V2 on the spent frames ({parity['rows']} rows)")
    t0 = time.time()
    cols, receipts = v4_values(inp, FRAMES_RES, frames_lv, V4.added(cfg), got=got,
                               gate_sha=gate_sha, log=log)
    inp.cols = cols
    inp.meta["elapsed_columns_s"] = round(time.time() - t0, 1)
    inp.meta["column_receipts"] = receipts
    return inp, frames_lv, receipts


# ---------------------------------------------------------------------------
# the selection (STEP 2)
# ---------------------------------------------------------------------------

def _frame_doc(inp: BT.Inputs, fid: str, cfg: dict, *, B: int, role: str, note: str,
               log=print) -> dict:
    orders, rec = inp.orders(fid, cfg)
    rows = inp.rows_with(fid, orders)
    t1 = time.time()
    blk = BT.frame_block(rows, B=B, comparisons=COMPARISONS)
    blk.update({"frame_version": FRAME_VERSION[fid], "receipts": rec,
                "fold_deltas_vs_v2": BT.fold_deltas(rows, CAND_KEY, V2_KEY),
                "fold_deltas_vs_consensus": BT.fold_deltas(rows, CAND_KEY, CONS),
                "cells": cell_block(rows, B=B), "role": role, "note": note,
                "window": [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])]})
    w = blk["deltas"]["v4_vs_efv_v2"]["spearman"]
    c = blk["deltas"]["v4_vs_prospx_consensus"]["spearman"]
    log(f"  {fid}: vs V2 {w.get('delta')} {w.get('ci95')}; vs consensus {c.get('delta')} "
        f"{c.get('ci95')} ({round(time.time() - t1, 1)} s stats)")
    return blk


def cell_block(rows: list[dict], *, B: int = B_DEFAULT, seed: int = SEED) -> dict:
    """The position-group cells (efv_strata.position_family on hitters; pitchers one
    cell; never an FV cell): within Spearman of v4, V2 and consensus and the v4 minus V2
    and v4 minus consensus within deltas (E_cond)."""
    out = {}
    keep = ("delta", "ci95", "mde95", "n", "status", "reading")
    for side, cell in CELLS:
        sel = [c for c in rows if c["side"] == side and (side == "pit" or c.get("cell") == cell)]
        blk = {"n": len(sel), "n_players": len({c["key"] for c in sel})}
        if len(sel) >= S.MIN_GROUP_ROWS:
            st = BT.rater_stats(sel)
            blk["raters"] = {n: {"within": r["within"], "n": r["n"]} for n, r in st.items()}
            blk["v4_vs_efv_v2"] = {k: v for k, v in BT.paired(sel, CAND_KEY, V2_KEY, "within",
                                                              B=B, seed=seed).items() if k in keep}
            blk["v4_vs_prospx_consensus"] = {k: v for k, v in BT.paired(
                sel, CAND_KEY, CONS, "within", B=B, seed=seed).items() if k in keep}
        else:
            blk["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        out[f"{side}:{cell}"] = blk
    return out


def select(inp: BT.Inputs, *, B: int = B_DEFAULT, log=print,
           checkpoint: Path | None = None) -> dict:
    t0 = time.time()
    cfg = V4.base_config()
    rounds = []
    taken = []
    cur_orders = {fid: inp.orders(fid, cfg)[0] for fid in FRAMES_DEV}
    for rnd in range(1, MAX_STEPS + 1):
        steps = menu(cfg)
        log(f"round {rnd}: {len(steps)} steps available; current: {V4.describe(cfg)}")
        evals = []
        for step in steps:
            t1 = time.time()
            ev = BT.evaluate_step(inp, cfg, step, cur_orders)
            ev["family"] = step["family"]
            ev["elapsed_s"] = round(time.time() - t1, 1)
            ev["qualifies"] = BT.qualifies(ev)
            evals.append(ev)
            lvd, vmd = ev["frames"]["lv_dev"], ev["frames"]["vm_dev"]
            log(f"  {step['name']:46s} lv {lvd.get('scope_delta')} vm {vmd.get('scope_delta')}"
                f"{' QUALIFIES' if ev['qualifies'] else ''} ({ev['elapsed_s']} s)")
        best = None
        for i, ev in enumerate(evals):
            if not ev["qualifies"]:
                continue
            if best is None or (ev["frames"]["lv_dev"]["scope_delta"]
                                > evals[best]["frames"]["lv_dev"]["scope_delta"]):
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
        taken.append({"round": rnd, "step": step["name"], "column": step["column"],
                      "lv_dev_scope_delta": evals[best]["frames"]["lv_dev"]["scope_delta"],
                      "vm_dev_scope_delta": evals[best]["frames"]["vm_dev"]["scope_delta"]})
        rec["admitted"] = taken[-1]
        rounds.append(rec)
        cur_orders = {fid: inp.orders(fid, cfg)[0] for fid in FRAMES_DEV}
        log(f"round {rnd}: ADMITTED {step['name']}; now {V4.describe(cfg)} "
            f"({round(time.time() - t0, 1)} s)")
        if checkpoint is not None:
            write_doc({"partial": True, "rounds": rounds, "config": cfg}, checkpoint)
    if len(taken) >= MAX_STEPS:
        log(f"the cap of {MAX_STEPS} steps is reached")
    frames_doc = {}
    for fid in FRAMES_DEV:
        blk = _frame_doc(inp, fid, cfg, B=B, role="development",
                         note=NOTE_SELECT + "; the configuration was selected on this frame",
                         log=log)
        w = blk["deltas"]["v4_vs_efv_v2"]["spearman"]
        c = blk["deltas"]["v4_vs_prospx_consensus"]["spearman"]
        blk["verdict"] = (f"DEVELOPMENT ONLY (selected on these frames): within vs V2 "
                          f"{_rnd(w.get('delta'), 4)} (CI95 {w.get('ci95')}), vs consensus "
                          f"{_rnd(c.get('delta'), 4)} (CI95 {c.get('ci95')}); adjudicates nothing")
        frames_doc[fid] = blk
    return {"config": cfg, "steps": taken, "rounds": rounds, "frames": frames_doc,
            "elapsed_s": round(time.time() - t0, 1)}


def _code() -> dict:
    return {"commit": _commit(), "tool": TOOL, "tool_sha256": _sha(ROOT / TOOL),
            "efv_v4_sha256": _sha(ROOT / "efv_v4.py"),
            "efv_v3_sha256": _sha(ROOT / "efv_v3.py"),
            "efv_v3_backtest_sha256": _sha(ROOT / "tools" / "efv_v3_backtest.py"),
            "efv_v2_candidates_sha256": _sha(ROOT / "efv_v2_candidates.py"),
            "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
            "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")}


def _menu_doc() -> dict:
    return {n: {k: v for k, v in s.items() if k != "key"} for n, s in V4.menu_columns().items()}


def select_doc(inp: BT.Inputs, res: dict, *, B: int) -> dict:
    return {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
        "role": "development", "adjudicates": False, "selects": True,
        "note": NOTE_SELECT,
        "owner_decision": ("EW2-10 (2026-10-08): eFV v4 from the new-source lanes, selected on "
                           "the development frames only; the reserved frames are spent and "
                           "reported as such; this artifact is the selection and reads no "
                           "reserved row"),
        "rule": {"doc": V4.BACKTEST_DOC, "min_lv_gain": MIN_LV_GAIN,
                 "vm_tolerance": VM_TOLERANCE, "max_steps": MAX_STEPS,
                 "statistic": S.STAT_LABEL[S.PRIMARY],
                 "scope": "the rows of the side a step touches",
                 "menu": "one ADD step per v4 menu column at its registered head, family "
                         "order then registered order; no anchor, factor or removal step",
                 "menu_size": len(V4.menu_columns()), "columns": _menu_doc()},
        "label": inp.label, "code": _code(),
        "assembly_sha256": _sha(H.ASSEMBLY_PATH), "weights": inp.weights,
        "bootstrap": {"B": int(B), "seed": SEED, "estimator": "E_cond", "unit": "player cluster"},
        "reserved_guard": inp.guards, "base_parity": inp.meta.get("base_parity"),
        "v4_base_parity": inp.meta.get("v3_base_parity"),
        "column_receipts": inp.meta.get("column_receipts"),
        "selected": {"config": res["config"], "description": V4.describe(res["config"]),
                     "steps": res["steps"], "is_v2": V4.is_base(res["config"])},
        "rounds": res["rounds"], "frames": res["frames"],
        "elapsed_s": round(res["elapsed_s"] + float(inp.meta.get("elapsed_build_s") or 0.0)
                           + float(inp.meta.get("elapsed_columns_s") or 0.0), 1),
    }


def spec_doc(sel: dict) -> dict:
    return {"schema": 1, "model_id": V4.MODEL_ID, "selected_at": sel["generated_at"],
            "selection_artifact": "data/_labs/efv_v4/efv_v4_select.json",
            "selection_doc": V4.BACKTEST_DOC, "owner_decision": "EW2-10 (2026-10-08)",
            "config": sel["selected"]["config"], "description": sel["selected"]["description"],
            "steps": sel["selected"]["steps"], "is_v2": sel["selected"]["is_v2"],
            "columns": {n: sel["rule"]["columns"][n] for n in V4.added(sel["selected"]["config"])},
            "weights_base": sel["weights"], "assembly_sha256": sel["assembly_sha256"],
            "label": sel["label"], "code": sel["code"], "flag": "efv_v4.EFV_V4_ON (False)"}


# ---------------------------------------------------------------------------
# the spent-frame read (STEP 3)
# ---------------------------------------------------------------------------

def verdict_text(c: dict, rc: dict, w: dict, rv: dict) -> str:
    d = c.get("delta")
    lo = (rc.get("ci95") or [None, None])[0]
    if d is None:
        return "not derived"
    if lo is not None and lo > 0:
        head = f"eFV v4 beats consensus within by {d:+.4f} (E_refit CI95 clear of zero)"
    elif d > 0:
        head = f"eFV v4 reads {d:+.4f} within over consensus; not resolved (E_refit CI95 spans zero)"
    else:
        head = f"eFV v4 reads {d:+.4f} within against consensus; ties or trails"
    dv = w.get("delta")
    tail = "" if dv is None else f"; vs served eFV (V2) {dv:+.4f} (E_refit CI95 {rv.get('ci95')})"
    return head + tail + f"; {SPENT_LABEL}"


def spent(inp: BT.Inputs, cfg: dict, *, B: int = B_DEFAULT, b_refit: int = B_REFIT_DEFAULT,
          log=print) -> dict:
    t0 = time.time()
    frames_doc = {}
    for fid in FRAMES_RES:
        blk = _frame_doc(inp, fid, cfg, B=B, role="spent", note=NOTE_SPENT, log=log)
        blk["label"] = SPENT_LABEL
        blk["outcome"] = ("W3 (WAR over the first three MLB seasons, 0 if no debut within "
                          "three seasons of V)" if fid == "lv_res"
                          else "career WAR to date (2025 and 2026 seasons)")
        log(f"  {fid}: E_refit B {b_refit} starts")
        blk["e_refit"] = BT.e_refit(inp, cfg, fid, B=b_refit, log=log, point=blk)
        w = blk["deltas"]["v4_vs_efv_v2"]["spearman"]
        c = blk["deltas"]["v4_vs_prospx_consensus"]["spearman"]
        legs = (blk["e_refit"]["legs"].get("both") or {})
        rc = ((legs.get("v4_vs_prospx_consensus") or {}).get("spearman") or {})
        rv = ((legs.get("v4_vs_efv_v2") or {}).get("spearman") or {})
        blk["verdict"] = verdict_text(c, rc, w, rv)
        frames_doc[fid] = blk
        log(f"  {fid}: vs V2 {w.get('delta')} E_cond {w.get('ci95')} E_refit {rv.get('ci95')}; "
            f"vs consensus {c.get('delta')} E_cond {c.get('ci95')} E_refit {rc.get('ci95')}")
    return {"frames": frames_doc, "elapsed_s": round(time.time() - t0, 1)}


def ship_reading(sel_doc: dict, spent_doc: dict) -> dict:
    """The ship rule of the document (EW2-10): the within point delta of v4 over served
    V2, pooled over sides, on all four frames."""
    out = {"rule": ("EW2-10: ship if v4 beats served eFV (V2) in within Spearman on lv_dev, "
                    "vm_dev, R-LV and R-VM, point estimates, pooled over sides"),
           "frames": {}, "ships": None}
    ok = True
    for fid in FRAMES_DEV:
        d = sel_doc["frames"][fid]["deltas"]["v4_vs_efv_v2"]["spearman"].get("delta")
        out["frames"][fid] = d
        ok = ok and d is not None and d > 0
    for fid in FRAMES_RES:
        d = spent_doc["frames"][fid]["deltas"]["v4_vs_efv_v2"]["spearman"].get("delta")
        out["frames"][fid] = d
        ok = ok and d is not None and d > 0
    out["ships"] = bool(ok)
    cons = {}
    for fid in FRAMES_RES:
        legs = ((spent_doc["frames"][fid].get("e_refit") or {}).get("legs") or {}).get("both") or {}
        rc = (legs.get("v4_vs_prospx_consensus") or {}).get("spearman") or {}
        cons[fid] = {"delta": rc.get("delta"), "e_refit_ci95": rc.get("ci95"),
                     "beats_consensus_resolved": bool(rc.get("ci95") and rc["ci95"][0] > 0)}
    out["vs_consensus_spent"] = cons
    return out


def spent_doc(inp: BT.Inputs, spec: dict, res: dict, *, B: int, b_refit: int,
              sel_doc: dict) -> dict:
    doc = {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
        "role": "spent", "adjudicates": False, "selects": False, "one_read": True,
        "label_note": SPENT_LABEL, "note": NOTE_SPENT, "ledger_rows": False,
        "owner_decision": ("EW2-10 (2026-10-08): the reserved frames were read once by the v3 "
                           "confirmation under the owner's waiver (EW2-6) and are spent; this "
                           "read of the committed v4 configuration chooses nothing and is "
                           "labelled spent; the ship rule reads it as the document fixes"),
        "gate": {"doc": F.GATE_DOC, "sha": inp.gate_sha, "guards": inp.guards},
        "spec": {"path": "data/efv_v4_spec.json", "sha256": _sha(V4.SPEC_PATH),
                 "config": spec["config"], "description": spec.get("description"),
                 "steps": spec.get("steps"), "selected_at": spec.get("selected_at"),
                 "selection_commit": (spec.get("code") or {}).get("commit")},
        "label": inp.label, "code": _code(),
        "assembly_sha256": _sha(H.ASSEMBLY_PATH), "weights": inp.weights,
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "secondary": S.STAT_LABEL[S.SECONDARY],
                      "veto": S.STAT_LABEL["auc"],
                      "mae": "MAE of the priced grade (the fold's consensus-FV-to-WAR line at "
                             "each rater's grade) against the outcome",
                      "min_group_rows": S.MIN_GROUP_ROWS,
                      "group": "(side, list vintage) on R-LV; (side, debut year) on R-VM",
                      "cells": "efv_strata.position_family on hitters (C, IF, OF); pitchers one cell"},
        "bootstrap": {"E_cond": {"B": int(B), "seed": SEED, "unit": "player cluster"},
                      "E_refit": {"B": int(b_refit), "seed": SEED_REFIT, "unit": "player cluster"}},
        "frames_built": {"lv_res": {"per_vintage": inp.meta.get("lv_per_vintage"),
                                    "w_star_dev": inp.meta.get("w_star_dev"),
                                    "reserved_vm_kept_w3_zero": inp.meta.get("reserved_vm_kept_w3_zero")},
                         "vm_pros": {"per_fold": inp.meta.get("vm_per_fold")}},
        "v4_base_parity": inp.meta.get("v4_base_parity"),
        "column_receipts": inp.meta.get("column_receipts"),
        "frames": res["frames"],
        "elapsed_s": round(res["elapsed_s"] + float(inp.meta.get("elapsed_build_s") or 0.0)
                           + float(inp.meta.get("elapsed_columns_s") or 0.0), 1),
    }
    doc["ship_rule"] = ship_reading(sel_doc, doc)
    return doc


# ---------------------------------------------------------------------------
# progress-ledger rows (development only)
# ---------------------------------------------------------------------------

_LEDGER_RATERS = (("efv", "efv_v4"), ("efv_v2_base", "efv_v2"),
                  ("prospx_consensus", "prospx_consensus"),
                  ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
_LEDGER_DELTAS = (("vs_efv_v2_base", "v4_vs_efv_v2"),
                  ("vs_prospx_consensus", "v4_vs_prospx_consensus"),
                  ("vs_mlb_pipeline", "v4_vs_mlb_pipeline"),
                  ("vs_fangraphs", "v4_vs_fangraphs"),
                  ("efv_v2_base_vs_prospx_consensus", "efv_v2_vs_prospx_consensus"))


def ledger_rows(doc: dict, *, artifact: Path, date: str, now_iso: str) -> list[dict]:
    """Development rows in data/efv_progress.json's shape, copied from the selection
    artifact (model efv_v4, frames lv_dev and vm_dev, trigger efv_change). Every number
    is a copy; the content hash is the ledger's own."""
    import efv_progress as P
    lab = doc.get("label") or {}
    mv = {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    rows = []
    for fid, f in (doc.get("frames") or {}).items():
        meta = P.FRAMES[fid]
        if meta["role"] != "development":
            raise ValueError(f"{fid} is registered as {meta['role']}, not development")
        raters = {}
        for name, key in _LEDGER_RATERS:
            r = (f.get("raters") or {}).get(key) or {}
            if r.get("spearman") is None and r.get("auc") is None:
                continue
            raters[name] = {"spearman": r.get("spearman"), "auc": r.get("auc"), "n": r.get("n")}
        deltas = {}
        for name, comp in _LEDGER_DELTAS:
            legs = {}
            for metric in ("spearman", "auc"):
                leg = ((f.get("deltas") or {}).get(comp) or {}).get(metric)
                if not leg:
                    continue
                legs[metric] = {"delta": leg.get("delta"), "ci95": leg.get("ci95"),
                                "mde95": leg.get("mde95"),
                                "mde95_estimator": leg.get("estimator"),
                                "ci95_estimator": leg.get("ci95_estimator"),
                                "resolvable": None, "reading": leg.get("reading"),
                                "key": f"frames.{fid}.deltas.{comp}.{metric}"}
            if legs:
                deltas[name] = legs
        nbs = {s: (f.get("n_by_side") or {})[s] for s in P.STRATA
               if (f.get("n_by_side") or {}).get(s)} or None
        row = {"run_id": None, "date": date, "trigger": "efv_change", "model_id": V4.MODEL_ID,
               "model_version": dict(mv), "frame": fid, "frame_version": f.get("frame_version"),
               "role": meta["role"], "tilted": bool(meta["tilted"]), "window": f.get("window"),
               "n": f.get("n"), "n_by_side": nbs, "raters": raters, "deltas": deltas,
               "resolvable": None, "verdict": f.get("verdict"), "share": None,
               "sources": [dict(s) for s in src], "note": f.get("note") or "",
               "last_verified_at": now_iso, "statistic": S.STAT_LABEL[S.PRIMARY],
               "secondary": {"statistic": S.STAT_LABEL["pooled"],
                             "raters": {name: ((f.get("raters") or {}).get(key) or {}).get("pooled")
                                        for name, key in _LEDGER_RATERS
                                        if ((f.get("raters") or {}).get(key) or {}).get("pooled") is not None},
                             "deltas": {name: {k: (((f.get("deltas") or {}).get(comp) or {}).get("pooled") or {}).get(k)
                                               for k in ("delta", "ci95", "mde95", "reading")}
                                        for name, comp in _LEDGER_DELTAS
                                        if ((f.get("deltas") or {}).get(comp) or {}).get("pooled")}}}
        P._finish(row)
        row["run_id"] = f"{doc.get('generated_at')}|{fid}|{row['content_hash'][:8]}"
        rows.append(row)
    return rows


def append_ledger(doc: dict, *, artifact: Path, ledger_path: Path | None = None) -> dict:
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    rows = ledger_rows(doc, artifact=artifact, date=now.date().isoformat(), now_iso=now_iso)
    return P.commit_rows(rows, data_dir=P.DATA_DIR, ledger_path=ledger_path,
                         sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def summary_lines(doc: dict) -> list[str]:
    out = []
    for fid, f in doc["frames"].items():
        for name in ("v4_vs_efv_v2", "v4_vs_prospx_consensus", "v4_vs_mlb_pipeline",
                     "v4_vs_fangraphs"):
            w = f["deltas"][name]["spearman"]
            rl = ((((f.get("e_refit") or {}).get("legs") or {}).get("both") or {})
                  .get(name) or {}).get("spearman") or {}
            out.append(f"{fid} {name:26s} within {w.get('delta')} E_cond {w.get('ci95')}"
                       + (f" E_refit {rl.get('ci95')}" if rl else ""))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--spent", action="store_true")
    ap.add_argument("--gate-sha", default=None)
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    ap.add_argument("--b-refit", type=int, default=B_REFIT_DEFAULT)
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--ledger", action="store_true",
                    help="re-append the selection artifact's two development rows to "
                         "data/efv_progress.json (a row whose run_id is present is skipped); "
                         "the integration path when the ledger conflicts")
    ap.add_argument("--ledger-path", default=None,
                    help="the durable ledger copy (a worktree with a junctioned .cache "
                         "names its own)")
    a = ap.parse_args(argv)
    ledger_path = Path(a.ledger_path) if a.ledger_path else None

    def log(msg):
        print(msg, flush=True)
    if a.ledger:
        if not SELECT_PATH.exists():
            log("refused: the selection artifact does not exist")
            return 2
        doc = json.loads(SELECT_PATH.read_text(encoding="utf-8"))
        r = append_ledger(doc, artifact=SELECT_PATH, ledger_path=ledger_path)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if L.provider() != FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {FROZEN_PROVIDER!r}")
        return 2
    if a.check or a.select:
        with V4.registered(), v4_names():
            inp, _frames_lv, receipts = build_dev(log=log)
            if a.check:
                counts = {fid: {"folds": inp.frames[fid]["folds"], "n": len(inp.scored(fid)),
                                "n_by_side": BT._n_side(inp.scored(fid))} for fid in FRAMES_DEV}
                log(json.dumps({"check": True, "guards": inp.guards, "counts": counts,
                                "label": inp.label, "weights": inp.weights,
                                "base_parity": inp.meta.get("base_parity"),
                                "v4_base_parity": inp.meta.get("v3_base_parity"),
                                "menu_size": len(menu(V4.base_config())),
                                "coverage": receipts["coverage"],
                                "families": receipts["families"]}, indent=1, default=str))
                return 0
            if SELECT_PATH.exists():
                log(f"refused: {SELECT_PATH} exists; the selection ran once")
                return 2
            res = select(inp, B=a.B, log=log, checkpoint=LAB_DIR / "efv_v4_select_partial.json")
            doc = select_doc(inp, res, B=a.B)
            out = write_doc(doc, SELECT_PATH)
            write_doc(spec_doc(doc), V4.SPEC_PATH)
            (LAB_DIR / "efv_v4_select_partial.json").unlink(missing_ok=True)
            log(f"wrote {out} and {V4.SPEC_PATH}: {doc['selected']['description']}")
            if not a.no_ledger:
                r = append_ledger(doc, artifact=out, ledger_path=ledger_path)
                log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
            return 0
    if a.spent:
        if SPENT_PATH.exists():
            log(f"refused: {SPENT_PATH} exists; the spent frames are read once by this tool")
            return 2
        if not a.gate_sha:
            log("refused: --gate-sha is required (the committed registration)")
            return 2
        if not SELECT_PATH.exists():
            log("refused: the selection comes first")
            return 2
        spec = V4.load_spec()
        cfg = V4.spec_config(spec)
        sel = json.loads(SELECT_PATH.read_text(encoding="utf-8"))
        log(f"configuration: {V4.describe(cfg)} (spec selected at {spec.get('selected_at')})")
        with V4.registered(), v4_names():
            inp, _frames_lv, _receipts = build_spent(cfg, gate_sha=a.gate_sha, log=log)
            res = spent(inp, cfg, B=a.B, b_refit=a.b_refit, log=log)
            doc = spent_doc(inp, spec, res, B=a.B, b_refit=a.b_refit, sel_doc=sel)
        out = write_doc(doc, SPENT_PATH)
        log(f"wrote {out} ({doc['elapsed_s']} s)")
        for line in summary_lines(doc):
            log(line)
        log(f"ship rule: {json.dumps(doc['ship_rule'], default=str)}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

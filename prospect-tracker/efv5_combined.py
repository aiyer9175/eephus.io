# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 COMBINED (EFV5_COMBINE_WEIGHT_SHIP; owner EW3-8 and EW3-9, 2026-10-15,
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`; method docs/efv-v2/EFV_V5_COMBINED.md, committed
before any fit): every candidate driver the atlas work produced, in ONE jointly weighted
model per side, read on the development frames and once on the spent held-out frames.

THE MODEL. Driver System V2's order index and anchor exactly (u_c the consensus percentile
within (side, list year), the registered P5 head weights, the DS-07 output map), with each
head re-fitted as one joint penalized regression: V2's own admitted drivers at V2's own
penalty alpha, re-estimated together with every candidate column of the side at one shared
ridge penalty lambda chosen by nested forward-chained cross-validation inside the fold's
training years (V2's rule, the grid efv_v2_model.V2_ALPHAS), each candidate slope bounded
to the sign the atlas showed where it showed one. At lambda = infinity the head is V2's,
bit for bit. The tracking-era head (efv5_tracking_head) is blended at its registered weight
for the side its artifact ships, on rows whose tracked season it never trained on.

THE CANDIDATES (candidates()): the 28 group drivers of efv5_group_drivers, the four tool
cells of the tool atlas built here as group columns (TOOL_CELLS), the 40 v4 columns of
efv_v4.menu_columns and the five wave-2 scouting columns of efv_v3.W2_COLUMNS
(W2S_COLUMNS). The four wave-2 MiLB-profile columns are excluded: no held-out builder.

DARK. EFV_V5_COMBINED_ON is False until the ship rule of the document passes
(efv_v2_serve.production_models reads the flag before any other eFV flag).

RESERVED FRAMES. The development build raises on list vintages 2020 and 2021 and stops
before the 2025 cohort (efv_vintage_frame); the spent build opens them on the committed
gate sha only, as the v4 and v5 spent reads did. The spent read runs once.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
percentile and as the value multiset the grade is drawn from; the strata are side, vintage,
level, age band, role and position family. Nothing here groups, counts or averages rows by
consensus-FV level; test_efv5_combined.py scans this source.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear, minimize

import efv5_group_drivers as G
import efv_v2_candidates as C
import efv_v2_model as H
import efv_v3 as V3
import efv_v4 as V4
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
FIT_PATH = LAB_DIR / "efv5_combined_fit.json"
SPENT_PATH = LAB_DIR / "efv5_combined_spent.json"
LAB_WEIGHTS_PATH = LAB_DIR / "efv5_combined_weights_dev.json"
#: The served weights file (the production fit's weights and standard errors), written by
#: --weights; read by the tests that pin the served path.
WEIGHTS_PATH = DATA_DIR / "efv5_combined_weights.json"
LEDGER_PATH = ROOT / ".cache" / "efv5_combined" / "progress_ledger.jsonl"
TOOL = "efv5_combined.py"
ITEM = "EFV5_COMBINE_WEIGHT_SHIP"

#: THE SWITCH. True since 2026-10-15 by OWNER OVERRIDE (decision EW3-10, "Make eFV v5, its even
#: with the ship rule so flip it"): the EW3-9 ship rule failed (pooled within Spearman -0.0028 vs
#: served V2 over 6,188 rows; R-VM -0.0288), every interval spans zero; the owner flipped it
#: anyway. False restores served V2.
EFV_V5_COMBINED_ON = True
MODEL_ID = "efv_v5_combined"
DOC = "docs/efv-v2/EFV_V5_COMBINED.md"
RESULTS_DOC = "docs/efv-v2/EFV_V5_COMBINED_RESULTS.md"
HEADS: tuple[str, ...] = V3.HEADS
#: The candidate penalty grid (the document, section 2).
LAMBDAS: tuple[float, ...] = H.V2_ALPHAS
#: EW3-9: a held-out frame may trail served V2 within by at most this much.
MAX_HELD_OUT_TRAIL = 0.005
#: The wave-2 scouting columns that enter (efv_v3.W2_COLUMNS, module efv_w2_scout).
W2S_COLUMNS: tuple[str, ...] = ("w2s_brk_pit", "w2s_cmd_pit", "w2s_pwr_present_hit",
                                "w2s_game_pwr_hit", "w2s_posval_hit")
#: Excluded wave-2 columns and why (the document, section 3.5).
EXCLUDED_W2: dict[str, str] = {n: "no held-out builder (the MiLB profile cache ends with 2022)"
                               for n in ("w2m_k_hit", "w2m_iso_hit", "w2m_air_hit", "w2m_gb_pit")}
#: The tool-grade cells of the tool atlas (data/efv5_atlas_tools.json candidates), built as
#: group columns; the sign is the cell's raw within-season Spearman with early WAR where its
#: CI95 excludes zero.
TOOL_CELLS: dict[str, dict] = {
    "t5_pit_Ap_all_SP_sl_gap": {"side": "pit", "head": "skill", "metric": "tg_sl_gap_pit",
                                "level": "A+", "band": "all", "group": "SP", "sign": -1},
    "t5_pit_Ap_young_all_sl_gap": {"side": "pit", "head": "skill", "metric": "tg_sl_gap_pit",
                                   "level": "A+", "band": "young", "group": "all", "sign": -1},
    "t5_pit_Ap_all_all_sl_gap": {"side": "pit", "head": "skill", "metric": "tg_sl_gap_pit",
                                 "level": "A+", "band": "all", "group": "all", "sign": -1},
    "t5_pit_AAA_all_all_fb_fut": {"side": "pit", "head": "skill", "metric": "tg_fb_fut_pit",
                                  "level": "AAA", "band": "all", "group": "all", "sign": 0},
}
TOOLS_ATLAS_PATH = DATA_DIR / "efv5_atlas_tools.json"
ATLAS_CELLS_PATH = LAB_DIR / "efv5_metric_atlas_cells.json"
#: The scouting-board lookback for a vintage-matched tool read (efv_w2_scout's rule).
TOOL_LOOKBACK_DAYS = 400
SPENT_LABEL = G.SPENT_LABEL
NOTE_FIT = ("eFV v5 COMBINED, joint fit and development read (owner EW3-8); the penalty "
            "was chosen on these frames out of fold; adjudicates nothing")
NOTE_SPENT = ("eFV v5 COMBINED on the spent reserved frames (read once by v3 on 2026-10-08); "
              "chooses and tunes nothing; not a look")
#: The one-sided inner weight of the head's sign bound in the receipts.
AT_BOUND = "at bound"
_SIGNS: dict | None = None
_CANDS: dict | None = None


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ---------------------------------------------------------------------------
# the candidate list (the document, section 3)
# ---------------------------------------------------------------------------

def group_signs(path: Path | None = None) -> dict[str, int]:
    """{group column: sign} from the atlas cells file: +1 when the cell's full-population
    raw AUC CI95 lies above 0.5, -1 below, 0 (free) when it holds 0.5."""
    global _SIGNS
    if _SIGNS is not None and path is None:
        return _SIGNS
    p = ATLAS_CELLS_PATH if path is None else Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    cols = doc["columns"]
    idx = {}
    for r in doc["rows"]:
        d = dict(zip(cols, r))
        idx[(d["metric"], d["side"], d["level"], d["age_band"], d["group"], d["label"],
             d["frame"])] = d
    out = {}
    for n, s in G.menu_columns().items():
        d = idx[(s["metric"], s["side"], s["level"], s["band"], s["group"],
                 s["atlas"]["label"], "clean")]
        lo, hi = d["raw_full_ci95"]
        out[n] = 1 if lo > 0.5 else (-1 if hi < 0.5 else 0)
    if path is None:
        _SIGNS = out
    return out


def candidates(*, refresh: bool = False) -> dict[str, dict]:
    """{name: {side, head, source, key, sign, ...}} in document order: group drivers,
    tool cells, v4 columns, wave-2 scouting columns. Memoized per process."""
    global _CANDS
    if _CANDS is not None and not refresh:
        return _CANDS
    out: dict = {}
    signs = group_signs()
    for n, s in G.menu_columns().items():
        out[n] = {"side": s["side"], "head": s["head"], "source": "group", "key": s["key"],
                  "sign": int(signs[n]), "metric": s["metric"], "level": s["level"],
                  "band": s["band"], "group": s["group"]}
    for n, s in TOOL_CELLS.items():
        out[n] = {"side": s["side"], "head": s["head"], "source": "tool",
                  "key": f"{H.V2_SCREEN_PREFIX}{n}", "sign": int(s["sign"]),
                  "metric": s["metric"], "level": s["level"], "band": s["band"],
                  "group": s["group"]}
    for n, s in V4.menu_columns().items():
        out[n] = {"side": s["side"], "head": s["head"], "source": "v4", "key": s["key"],
                  "sign": 0, "family": s["family"], "arg": s["arg"]}
    for n in W2S_COLUMNS:
        s = V3.W2_COLUMNS[n]
        if s["module"] != "efv_w2_scout":
            raise RuntimeError(f"{n} is not a scouting column")
        out[n] = {"side": s["side"], "head": s["head"], "source": "w2s", "key": s["key"],
                  "sign": 0, "arg": s["arg"]}
    for n in EXCLUDED_W2:
        if n in out:
            raise RuntimeError(f"{n} is excluded by the document")
    _CANDS = out
    return out


def side_candidates(side: str, head: str | None = None) -> list[str]:
    return [n for n, s in candidates().items()
            if s["side"] == side and (head is None or s["head"] == head)]


def tool_cells_are_atlas_candidates(path: Path | None = None) -> dict:
    """Each TOOL_CELLS entry must be a clean candidate of the tool atlas artifact."""
    doc = json.loads((TOOLS_ATLAS_PATH if path is None else Path(path)).read_text(encoding="utf-8"))
    have = {(c["metric"], c["side"], c["level"], c["age_band"], c["group"])
            for c in doc.get("candidates") or [] if c.get("status") == "clean"}
    out = {}
    for n, s in TOOL_CELLS.items():
        out[n] = (s["metric"], s["side"], s["level"], s["band"], s["group"]) in have
    return out


# ---------------------------------------------------------------------------
# the tool-cell columns (section 3.2): grade as of the read, group test, z, centering
# ---------------------------------------------------------------------------

def _tools_mod():
    import efv5_atlas_tools as TA
    return TA


def _scout():
    import efv_w2_scout as SC
    return SC


def _levels_index(ln) -> dict:
    """{(pid, season): [levels]} over a Lines object's qualified lines (memoized on it)."""
    idx = getattr(ln, "_levels_by", None)
    if idx is None:
        idx = {}
        for (pid, season, level) in ln.vals:
            idx.setdefault((pid, season), []).append(level)
        ln._levels_by = idx
    return idx


def tool_member(ln, pid, season: int, spec: dict) -> bool:
    """In the tool cell's group: the player's highest qualified level in S is the cell's
    level, no MLB line at or before S, the age band and (pitchers) the role match."""
    import efv5_atlas as A
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    levels = _levels_index(ln).get((pid, int(season)))
    if not levels:
        return False
    top = max(levels, key=lambda lv: A.LEVEL_RANK[lv])
    if top != spec["level"]:
        return False
    if any(y <= int(season) for y in ln.mlb.get(pid, ())):
        return False
    k = (pid, int(season), top)
    if spec["band"] != "all" and ln.band.get(k) != spec["band"]:
        return False
    if ln.side == "pit" and spec["group"] != "all" and ln.role.get(k) != spec["group"]:
        return False
    return True


def tool_value(index, player_key: str, asof, window_lo, metric: str, side: str):
    """The tool metric off the boards dated inside [window_lo, asof] (a list window) or,
    with window_lo None, inside the TOOL_LOOKBACK_DAYS before asof."""
    TA = _tools_mod()
    if not asof:
        return None
    if window_lo is None:
        per = index.asof(player_key, asof, lookback_days=TOOL_LOOKBACK_DAYS)
    else:
        per = TA.list_entries(index, player_key, asof, window_lo)
    return TA.tool_values(per, side).get(metric)


def _tool_finish(reads: dict, seasons: dict, names: list[str]) -> tuple[dict, dict]:
    """reads {(year, sid): {name: (in group, raw value)}} -> z inside (season, level) over the
    in-group rows that carry the grade (NORM_MIN_LINES or more), then centered within the
    read year (efv5_group_drivers.centered)."""
    pools: dict = {}
    for (y, sid), r in reads.items():
        for n in names:
            ing, v = r[n]
            if ing and v is not None:
                pools.setdefault((n, seasons[(y, sid)]), []).append(float(v))
    norm = {}
    for p, vs in pools.items():
        if len(vs) >= G.NORM_MIN_LINES:
            arr = np.asarray(vs, dtype=np.float64)
            if arr.std() > 0:
                norm[p] = (float(arr.mean()), float(arr.std()))
    zreads = {}
    for (y, sid), r in reads.items():
        row = {}
        for n in names:
            ing, v = r[n]
            nm = norm.get((n, seasons[(y, sid)]))
            row[n] = (ing, None if (v is None or nm is None or not ing) else (float(v) - nm[0]) / nm[1])
        zreads[(y, sid)] = row
    return G.centered(zreads, names)


def tool_lv_columns(side: str, rows_by_v: dict, names, index, *, gate_sha: str | None = None,
                    log=print) -> tuple[dict, dict]:
    """({name: {(V, player_key): value}}, counts) on list-vintage frame rows."""
    for V in rows_by_v:
        F.guard_score_request(int(V), gate_sha=gate_sha, purpose="v5 combined tool column")
    ln = G.lines_for(side, log=log)
    reads, seasons = {}, {}
    for V in sorted(rows_by_v):
        for r in rows_by_v[V]:
            lo = (r.get("window") or [None])[0]
            S = G.read_season(int(V), lo)
            key = (int(V), r["player_key"])
            seasons[key] = S
            row = {}
            for n in names:
                spec = TOOL_CELLS[n]
                ing = tool_member(ln, r.get("mlbam_id"), S, spec)
                v = (tool_value(index, r["player_key"], r.get("asof_date"), lo, spec["metric"], side)
                     if ing else None)
                row[n] = (ing, v)
            reads[key] = row
    return _tool_finish(reads, seasons, list(names))


def tool_vm_columns(side: str, data: list[dict], raw_by_key: dict, names, index, *,
                    asof_by_key: dict | None = None, test_index=None, test_keys=None,
                    gate_sha: str | None = None, log=print) -> tuple[dict, dict]:
    """({name: {(decision year, player_key): value}}, counts) on vintage-matched rows read
    at the matrix cutoff (a training row, its matrix as-of date) or at the pinned preseason
    read (`asof_by_key`; the 2025 test rows through `test_index`, the look index)."""
    late = {int(d["decision_year"]) for d in data
            if int(d["decision_year"]) >= F.R_VM_FIRST_DEBUT_YEAR}
    allow_reserved = False
    if gate_sha:
        F.guard_vm_request(late, gate_sha=gate_sha, purpose="v5 combined tool column")
        allow_reserved = True
    ln = G.lines_for(side, log=log)
    reads, seasons = {}, {}
    test_keys = set(test_keys or ())
    for d in data:
        y = int(d["decision_year"])
        if y >= F.R_VM_FIRST_DEBUT_YEAR and not allow_reserved:
            continue
        pk = d["player_key"]
        if y >= F.R_VM_FIRST_DEBUT_YEAR and pk not in test_keys:
            continue          # a reserved-year row outside the fold's pinned test rows
        raw = raw_by_key.get(pk) or {}
        S = G.read_season(y, raw.get("cutoff"))
        key = (y, pk)
        seasons[key] = S
        asof = (asof_by_key or {}).get(pk) if pk in test_keys else raw.get("asof_date")
        ix = test_index if (pk in test_keys and test_index is not None) else index
        row = {}
        for n in names:
            spec = TOOL_CELLS[n]
            ing = tool_member(ln, raw.get("mlbam_id"), S, spec)
            v = tool_value(ix, pk, asof, None, spec["metric"], side) if ing else None
            row[n] = (ing, v)
        reads[key] = row
    return _tool_finish(reads, seasons, list(names))


# ---------------------------------------------------------------------------
# building every candidate column on the backtest frames
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)
    import efv_v3_backtest as BT
    import efv_v4_backtest as B4
    return BT, B4


def _slots(inp, fid: str, side: str):
    for _fold, blk in inp.frames[fid]["by_side"][side].items():
        for kind in ("train", "test"):
            for r in blk[kind]:
                yield (int(r["decision_year"]), r["player_key"], kind)


def _raw_by_side() -> dict:
    return {s: {r["player_key"]: r for r in json.loads(
        H._matrix_path(s).read_text(encoding="utf-8"))} for s in F.SIDES}


def _pinned_asof(side: str) -> dict:
    mine: dict = {}
    H.pinned_inputs(side, H.matrix_training_rows(side), mine)
    return {pk: rec.get("asof_date") for pk, rec in mine.items()}


@contextmanager
def _w2s_only():
    """efv_v3.W2_COLUMNS reduced to the scouting columns for the life of the block."""
    orig = dict(V3.W2_COLUMNS)
    keep = {n: orig[n] for n in W2S_COLUMNS}
    V3.W2_COLUMNS.clear()
    V3.W2_COLUMNS.update(keep)
    try:
        yield
    finally:
        V3.W2_COLUMNS.clear()
        V3.W2_COLUMNS.update(orig)


def _coverage(cols: dict, fids) -> dict:
    out: dict = {fid: {} for fid in fids}
    for fid in fids:
        for side in F.SIDES:
            for n, mp in (cols[fid].get(side) or {}).items():
                te = [k for k in mp if k[2] == "test"]
                out[fid][n] = {"slots": len(mp),
                               "with_value": sum(1 for v in mp.values() if v is not None),
                               "nonzero": sum(1 for v in mp.values() if v not in (None, 0.0)),
                               "test_slots": len(te),
                               "test_nonzero": sum(1 for k in te if mp[k] not in (None, 0.0))}
    return out


def build_dev(*, log=print):
    """The development inputs with every candidate column: efv5_group_drivers.build_dev (the
    v4 base inputs, DS-16 and v3-at-base parity asserted there, then the 28 group columns),
    then the tool cells, the v4 columns and the scouting columns."""
    BT, B4 = _tools()
    SC = _scout()
    t0 = time.time()
    inp, frames_lv, rec = G.build_dev(log=log)
    cols = inp.cols
    rows_lv = {s: {int(V): rows for V, (rows, _l) in frames_lv[s].items()} for s in F.SIDES}
    raw = _raw_by_side()
    index = SC.default_index()
    lv_fid, vm_fid = BT.FRAMES_DEV
    for side in F.SIDES:
        names = [n for n in TOOL_CELLS if TOOL_CELLS[n]["side"] == side]
        if not names:
            continue
        lv_vals, lv_cnt = tool_lv_columns(side, rows_lv[side], names, index, log=log)
        pinned = _pinned_asof(side)
        te_keys = {r["player_key"] for blk in inp.frames[vm_fid]["by_side"][side].values()
                   for r in blk["test"]}
        vm_vals, vm_cnt = tool_vm_columns(side, H.matrix_training_rows(side), raw[side], names,
                                          index, asof_by_key=pinned, test_keys=te_keys, log=log)
        for n in names:
            cols[lv_fid][side][n] = {s: lv_vals[n].get((s[0], s[1]), 0.0)
                                     for s in _slots(inp, lv_fid, side)}
            cols[vm_fid][side][n] = {s: vm_vals[n].get((s[0], s[1]), 0.0)
                                     for s in _slots(inp, vm_fid, side)}
            rec.setdefault("in_group_by_year", {})[n] = {
                "lv": {str(y): c for y, c in sorted(lv_cnt[n].items())},
                "vm": {str(y): c for y, c in sorted(vm_cnt[n].items())}}
    log(f"  tool cells built ({round(time.time() - t0, 1)} s)")
    t1 = time.time()
    v4_cols, v4_rec = B4.v4_values(inp, BT.FRAMES_DEV, frames_lv, list(V4.menu_columns()), log=log)
    for fid in BT.FRAMES_DEV:
        for side in F.SIDES:
            cols[fid][side].update(v4_cols[fid][side])
    rec["v4_families"] = v4_rec.get("families")
    log(f"  v4 columns built ({round(time.time() - t1, 1)} s)")
    t2 = time.time()
    with _w2s_only():
        w2 = BT.w2_values_dev({"frames": inp.frames}, frames_lv, log=log)
    for fid in BT.FRAMES_DEV:
        for side in F.SIDES:
            cols[fid][side].update(w2[fid][side])
    log(f"  scouting columns built ({round(time.time() - t2, 1)} s)")
    inp.cols = cols
    inp.meta["elapsed_columns_s"] = round(time.time() - t0, 1)
    rec["coverage"] = _coverage(cols, BT.FRAMES_DEV)
    inp.meta["column_receipts"] = rec
    _check_complete(inp, BT.FRAMES_DEV)
    return inp, frames_lv, rec


def build_spent(*, gate_sha: str, log=print):
    """The reserved frames at V2 (frame rows captured), V2 parity asserted, then every
    candidate column through its spent builder."""
    BT, B4 = _tools()
    SC = _scout()
    import efv_w2_il_backfill as W2I
    t0 = time.time()
    inp, got = W2I.build_reserved_capturing(gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    inp.meta["v5_base_parity"] = parity
    log(f"v3 at base_config reproduces V2 on the spent frames ({parity['rows']} rows)")
    rows_lv = {s: {} for s in F.SIDES}
    for s in F.SIDES:
        for V, (rows, _l) in (got["dev"] or {}).get(s, {}).items():
            rows_lv[s][int(V)] = rows
    for (s, V), rows in got["res"].items():
        rows_lv[s][int(V)] = rows
    cols, rec = G.build_columns(inp, BT.FRAMES_RES, rows_lv, list(G.menu_columns()),
                                gate_sha=gate_sha, log=log)
    raw = _raw_by_side()
    index = SC.default_index()
    look = SC.look_index(gate_sha)
    lv_fid, vm_fid = BT.FRAMES_RES
    for side in F.SIDES:
        names = [n for n in TOOL_CELLS if TOOL_CELLS[n]["side"] == side]
        if not names:
            continue
        lv_vals, lv_cnt = tool_lv_columns(side, rows_lv[side], names, index, gate_sha=gate_sha,
                                          log=log)
        pinned = _pinned_asof(side)
        te_keys = {r["player_key"] for blk in inp.frames[vm_fid]["by_side"][side].values()
                   for r in blk["test"]}
        vm_vals, vm_cnt = tool_vm_columns(side, H.matrix_training_rows(side), raw[side], names,
                                          index, asof_by_key=pinned, test_index=look,
                                          test_keys=te_keys, gate_sha=gate_sha, log=log)
        for n in names:
            cols[lv_fid][side][n] = {s: lv_vals[n].get((s[0], s[1]), 0.0)
                                     for s in _slots(inp, lv_fid, side)}
            cols[vm_fid][side][n] = {s: vm_vals[n].get((s[0], s[1]), 0.0)
                                     for s in _slots(inp, vm_fid, side)}
            rec.setdefault("in_group_by_year", {})[n] = {
                "lv": {str(y): c for y, c in sorted(lv_cnt[n].items())},
                "vm": {str(y): c for y, c in sorted(vm_cnt[n].items())}}
    v4_cols, v4_rec = B4.v4_values(inp, BT.FRAMES_RES, got["dev"], list(V4.menu_columns()),
                                   got=got, gate_sha=gate_sha, log=log)
    for fid in BT.FRAMES_RES:
        for side in F.SIDES:
            cols[fid][side].update(v4_cols[fid][side])
    rec["v4_families"] = v4_rec.get("families")
    frames_res = {s: {} for s in F.SIDES}
    for (s, V), rows in got["res"].items():
        frames_res[s][int(V)] = (rows, [])
    pinned_asof = {s: _pinned_asof(s) for s in F.SIDES}
    with _w2s_only():
        w2 = BT.w2_values_reserved(list(W2S_COLUMNS), lv=inp.frames["lv_res"],
                                   vm=inp.frames["vm_pros"], frames_dev=got["dev"],
                                   frames_res=frames_res, raw_by_side=raw,
                                   pinned_asof=pinned_asof, gate_sha=gate_sha, log=log)
    for fid in BT.FRAMES_RES:
        for side in F.SIDES:
            cols[fid][side].update(w2[fid][side])
    inp.cols = cols
    inp.meta["elapsed_columns_s"] = round(time.time() - t0, 1)
    rec["coverage"] = _coverage(cols, BT.FRAMES_RES)
    inp.meta["column_receipts"] = rec
    inp.meta["raw_by_side"] = raw
    _check_complete(inp, BT.FRAMES_RES)
    return inp, got, rec


def _check_complete(inp, fids) -> None:
    for fid in fids:
        for side in F.SIDES:
            missing = [n for n in side_candidates(side) if n not in (inp.cols[fid].get(side) or {})]
            if missing:
                raise RuntimeError(f"{fid} {side}: candidate columns not built: {missing}")


def attach(rows: list[dict], side: str, cols_side: dict, kind: str) -> list[dict]:
    """Rows (copies) with every candidate column of the side on their v2 view under its
    key (None where the builder gave none: the DS-04 imputation)."""
    cands = candidates()
    names = side_candidates(side)
    out = []
    for r in rows:
        slot = (int(r["decision_year"]), r["player_key"], kind)
        add = {}
        for n in names:
            v = (cols_side.get(n) or {}).get(slot)
            add[cands[n]["key"]] = None if v is None else float(v)
        out.append(dict(r, v2=dict(r["v2"], **add)))
    return out


# ---------------------------------------------------------------------------
# the joint fit (the document, section 2)
# ---------------------------------------------------------------------------

def _pens_and_bounds(n_v2: int, alpha, cand_names, lam: float):
    """Penalties and bounds for [1, u_c, z(V2 keys), z(candidates)]."""
    cands = candidates()
    pen = [0.0, 0.0]
    lb, ub = [-np.inf, -np.inf], [np.inf, np.inf]
    fixed = alpha is None or (isinstance(alpha, float) and math.isinf(alpha))
    for _ in range(n_v2):
        pen.append(0.0 if fixed else float(alpha))
        lb.append(0.0 if fixed else -np.inf)
        ub.append(0.0 if fixed else np.inf)
    for n in cand_names:
        s = cands[n]["sign"]
        pen.append(float(lam))
        lb.append(0.0 if s > 0 else -np.inf)
        ub.append(0.0 if s < 0 else np.inf)
    return np.asarray(pen), np.asarray(lb), np.asarray(ub)


def bounded_wls(Z: np.ndarray, y: np.ndarray, w: np.ndarray, pen: np.ndarray,
                lb: np.ndarray, ub: np.ndarray) -> np.ndarray:
    """argmin sum w (y - Z b)^2 + sum pen b^2 subject to lb <= b <= ub (bvls on the
    augmented system)."""
    sw = np.sqrt(w)
    A = Z * sw[:, None]
    b = y * sw
    keep = pen > 0
    if keep.any():
        R = np.zeros((int(keep.sum()), Z.shape[1]))
        R[np.arange(int(keep.sum())), np.flatnonzero(keep)] = np.sqrt(pen[keep])
        A = np.vstack([A, R])
        b = np.concatenate([b, np.zeros(int(keep.sum()))])
    fixed = (lb == 0) & (ub == 0)
    if fixed.any():
        free = ~fixed
        x = np.zeros(Z.shape[1])
        res = lsq_linear(A[:, free], b, bounds=(lb[free], ub[free]), method="bvls")
        x[free] = res.x
        return x
    return lsq_linear(A, b, bounds=(lb, ub), method="bvls").x


def bounded_logistic(Z: np.ndarray, y: np.ndarray, pen: np.ndarray, lb: np.ndarray,
                     ub: np.ndarray) -> np.ndarray:
    """argmin sum(log(1 + e^eta) - y eta) + 0.5 sum pen b^2 subject to the bounds
    (L-BFGS-B on the convex objective), eta = Z b."""
    fixed = (lb == 0) & (ub == 0)
    free = ~fixed
    Zf = Z[:, free]
    pf = pen[free]

    def fg(beta):
        eta = Zf @ beta
        ll = float(np.sum(np.logaddexp(0.0, eta) - y * eta) + 0.5 * np.sum(pf * beta * beta))
        p = H._sigmoid(eta)
        g = Zf.T @ (p - y) + pf * beta
        return ll, g
    res = minimize(fg, np.zeros(Zf.shape[1]), jac=True, method="L-BFGS-B",
                   bounds=list(zip(lb[free], ub[free])),
                   options={"ftol": 1e-13, "gtol": 1e-8, "maxiter": 5000, "maxfun": 20000})
    x = np.zeros(Z.shape[1])
    x[free] = res.x
    return x


def _with_zero_candidates(head: dict | None, cand_keys) -> dict | None:
    """V2's head as fitted (its keys and slopes untouched, so the order is V2's bit for
    bit) carrying the candidate keys whose slope is zero under `zero_candidates`."""
    if head is None:
        return None
    head = dict(head)
    head["zero_candidates"] = list(cand_keys)
    return head


def joint_skill(train: list[dict], v2_keys, alpha, cand_names, lam: float) -> dict | None:
    """The combined skill head: a weighted ridge of u_y on [1, u_c, z(V2 keys) at alpha,
    z(candidates) at lam] over the has-block rows, candidate slopes bounded by sign. At
    lam = infinity it is V2's head (efv_v2_candidates._skill_fit_g) with zero candidate
    slopes appended; None when V2 would have none."""
    cands = candidates()
    v2_keys = list(v2_keys)
    cand_keys = [cands[n]["key"] for n in cand_names]
    keys = v2_keys + cand_keys
    rows = H.skill_training_rows(train)
    if len(rows) < H.MIN_TEST_ROWS or not keys:
        return None
    means = H.has_block_means(train)
    X = H._v2_x(rows, keys, means)
    mu, sd, Xs = H._std_cols(X)
    u_c = C._uc(train)
    _u, u_y = H._percentiles(train)
    pos = {id(r): i for i, r in enumerate(train)}
    ix = [pos[id(r)] for r in rows]
    w = C._weights_of(rows)
    if math.isinf(lam) or not cand_keys:
        if v2_keys:
            base = C._skill_fit_g(train, v2_keys, alpha, C._v2_design(v2_keys))
        else:
            # V2 has no skill head here; the infinity arm is consensus alone with every
            # candidate slope zero (unusable, as V2's absent head is)
            c2 = H._wls(np.column_stack([np.ones(len(rows)), u_c[ix]]), u_y[ix], w, np.zeros(2))
            base = {"keys": [], "means": means, "alpha": alpha, "mu": [], "sd": [],
                    "b0": float(c2[0]), "b_uc": float(c2[1]), "beta": [], "n_train": len(rows),
                    "trained_on": "has_block", "design": {"kind": "v2"}}
        head = _with_zero_candidates(base, cand_keys)
        if head is not None:
            head["lam"] = lam
        return head
    Z = np.column_stack([np.ones(len(rows)), u_c[ix], Xs])
    pen, lb, ub = _pens_and_bounds(len(v2_keys), alpha, cand_names, lam)
    coef = bounded_wls(Z, u_y[ix], w, pen, lb, ub)
    return {"keys": keys, "means": means, "alpha": alpha, "lam": lam, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": float(coef[0]), "b_uc": float(coef[1]),
            "beta": [float(b) for b in coef[2:]], "n_train": len(rows),
            "trained_on": "has_block", "design": {"kind": "v2"}}


def joint_timing(train: list[dict], v2_keys, alpha, cand_names, lam: float) -> dict | None:
    """The combined timing head: a penalized logistic of REACHED on [1, u_c, z(V2 keys) at
    alpha, z(candidates) at lam] over every training row, candidate slopes bounded by sign.
    At lam = infinity it is V2's head with zero candidate slopes appended."""
    cands = candidates()
    v2_keys = list(v2_keys)
    cand_keys = [cands[n]["key"] for n in cand_names]
    keys = v2_keys + cand_keys
    if len(train) < H.MIN_TRAIN_ROWS:
        return None
    y = np.array([r["reached"] for r in train], dtype=np.float64)
    if y.min() == y.max():
        return None
    means = H.has_block_means(train)
    X = H._v2_x(train, keys, means)
    mu, sd, Xs = H._std_cols(X)
    if math.isinf(lam) or not cand_keys:
        base = C._timing_fit_g(train, v2_keys, alpha, C._v2_design(v2_keys))
        head = _with_zero_candidates(base, cand_keys)
        if head is not None:
            head["lam"] = lam
        return head
    u_c = C._uc(train)
    Z = np.column_stack([np.ones(len(train)), u_c, Xs])
    pen, lb, ub = _pens_and_bounds(len(v2_keys), alpha, cand_names, lam)
    pen[:2] = H._OFFSET_EPS
    coef = bounded_logistic(Z, y, pen, lb, ub)
    return {"keys": keys, "means": means, "alpha": alpha, "lam": lam, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": float(coef[0]), "b_uc": float(coef[1]),
            "beta": [float(b) for b in coef[2:]], "n_train": len(train),
            "trained_on": "all", "design": {"kind": "v2"}}


def select_lambda(train: list[dict], kind: str, v2_keys, alpha, cand_names) -> float:
    """lambda by V2's nested forward-chained rule on the joint head (the document, s2)."""
    if kind == "skill":
        def fit(tr, lam):
            return joint_skill(tr, v2_keys, alpha, cand_names, lam)
        loss = C._skill_loss
    else:
        def fit(tr, lam):
            return joint_timing(tr, v2_keys, alpha, cand_names, lam)
        loss = C._timing_loss
    return C._select_alpha_g(train, fit, loss, alphas=LAMBDAS)


def head_se(head: dict | None, train: list[dict]) -> dict | None:
    """Ridge sandwich standard errors of a fitted head's slopes (the document, s2):
    {key: {"se": standardised-slope SE, "at_bound": bool}}; None without a head."""
    if head is None:
        return None
    cands = candidates()
    key_sign = {s["key"]: s["sign"] for s in cands.values()}
    keys = list(head["keys"])
    if head["trained_on"] == "has_block":
        rows = H.skill_training_rows(train)
        u_c = C._uc(train)
        _u, u_y = H._percentiles(train)
        pos = {id(r): i for i, r in enumerate(train)}
        ix = [pos[id(r)] for r in rows]
        y = u_y[ix]
        uc = u_c[ix]
        w = C._weights_of(rows)
    else:
        rows = train
        y = np.array([r["reached"] for r in train], dtype=np.float64)
        uc = C._uc(train)
        w = np.ones(len(train))
    X = H._v2_x(rows, keys, head["means"])
    Xs = (X - np.asarray(head["mu"])) / np.asarray(head["sd"])
    Z = np.column_stack([np.ones(len(rows)), uc, Xs])
    beta = np.concatenate([[head["b0"], head["b_uc"]], np.asarray(head["beta"], dtype=np.float64)])
    alpha = head.get("alpha")
    lam = head.get("lam", math.inf)
    n_v2 = len(keys) - sum(1 for k in keys if k in key_sign)
    pen = np.zeros(Z.shape[1])
    a = 0.0 if (alpha is None or math.isinf(float(alpha))) else float(alpha)
    pen[2:2 + n_v2] = a
    pen[2 + n_v2:] = 0.0 if math.isinf(lam) else float(lam)
    live = np.ones(Z.shape[1], dtype=bool)
    live[2:2 + n_v2] = not (alpha is None or math.isinf(float(alpha)))
    live[2 + n_v2:] = not math.isinf(lam)
    Zl = Z[:, live]
    if head["trained_on"] == "has_block":
        r = y - Z @ beta
        n, p = Zl.shape
        s2 = float(np.sum(w * r * r)) / max(n - p, 1)
        A = Zl.T @ (Zl * w[:, None])
        Hm = A + np.diag(pen[live])
        try:
            Hi = np.linalg.inv(Hm)
        except np.linalg.LinAlgError:
            return None
        cov = s2 * Hi @ A @ Hi
    else:
        pr = H._sigmoid(Z @ beta)
        wd = pr * (1.0 - pr)
        A = Zl.T @ (Zl * wd[:, None])
        Hm = A + np.diag(pen[live])
        try:
            Hi = np.linalg.inv(Hm)
        except np.linalg.LinAlgError:
            return None
        cov = Hi @ A @ Hi
    se_live = np.sqrt(np.maximum(np.diag(cov), 0.0))
    se = np.full(Z.shape[1], np.nan)
    se[live] = se_live
    out = {}
    for j, k in enumerate(keys):
        b = float(head["beta"][j])
        s = key_sign.get(k, 0)
        at_bound = bool(s != 0 and b == 0.0 and live[2 + j])
        out[k] = {"se": None if not np.isfinite(se[2 + j]) else float(se[2 + j]),
                  "at_bound": at_bound, "fixed": not bool(live[2 + j])}
    return out


def fit_combined(train: list[dict], side: str, *, frame: str, weights: dict[str, dict],
                 absent_ok: bool | None = None, gate_sha: str | None = None,
                 lam: dict | None = None, with_se: bool = False) -> dict:
    """The combined model on one fold's training rows (each carrying `v2` with every
    candidate column of the side attached under its key). V2's admitted drivers and alpha
    are the fold's own (efv_v3.fit_v3 at base_config, the same calls); every candidate
    column enters the joint head at lambda chosen by nested CV (or `lam` {head: value})."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    C.guard_training_rows(train, frame, gate_sha=gate_sha)
    ob = frame == "lv"
    ab = ob and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    cfg = V3.base_config()
    sk_c = side_candidates(side, "skill")
    tm_c = side_candidates(side, "timing")
    s_cands = V3.head_candidates(cfg, side, "skill", ids_outcome_blind=ob, absence_admitted=ab)
    v2_keys, checks = ((), {})
    alpha_s = None
    if s_cands:
        v2_keys, checks = C._admitted_keys_a(train, s_cands, target="u_y", has_block_only=True)
        if v2_keys:
            def fit_s(tr, a):
                return C._skill_fit_g(tr, v2_keys, a, C._v2_design(v2_keys))
            alpha_s = C._select_alpha_g(train, fit_s, C._skill_loss)
    skill = None
    lam_s = None
    if v2_keys or sk_c:
        lam_s = (float(lam["skill"]) if lam and lam.get("skill") is not None
                 else select_lambda(train, "skill", v2_keys, alpha_s, sk_c))
        skill = joint_skill(train, v2_keys, alpha_s, sk_c, lam_s)
        if skill is not None:
            skill.update({"side": side, "admission": checks, "candidates": list(s_cands),
                          "v2_keys": list(v2_keys), "candidate_columns": list(sk_c),
                          "anchor": False})
            skill["score_sd"] = C._score_sd(skill, H.skill_training_rows(train))
            if with_se:
                skill["se"] = head_se(skill, train)
    timing = None
    why = None
    lam_t = None
    if side == "pit" and not H.head_usable(skill):
        why = ("owner DS-Q2: no pitcher skill driver passed the admission rule in this "
               "fold, so pitchers take the consensus order")
    else:
        t_cands = V3.head_candidates(cfg, side, "timing", ids_outcome_blind=ob,
                                     absence_admitted=ab)
        tkeys, tchecks = C._admitted_keys_a(train, t_cands, target="reached",
                                            has_block_only=False)

        def fit_t(tr, a):
            return C._timing_fit_g(tr, tkeys, a, C._v2_design(tkeys))
        alpha_t = C._select_alpha_g(train, fit_t, C._timing_loss)
        lam_t = (float(lam["timing"]) if lam and lam.get("timing") is not None
                 else select_lambda(train, "timing", tkeys, alpha_t, tm_c))
        timing = joint_timing(train, tkeys, alpha_t, tm_c, lam_t)
        if timing is not None:
            timing.update({"side": side, "admission": tchecks, "candidates": list(t_cands),
                           "v2_keys": list(tkeys), "candidate_columns": list(tm_c),
                           "ids_outcome_blind": bool(ob), "anchor": False})
            timing["score_sd"] = C._score_sd(timing, train)
            if with_se:
                timing["se"] = head_se(timing, train)
    w = weights[side]
    w_s = float(w["w_skill"]) if H.head_usable(skill) else 0.0
    w_t = float(w["w_time"]) if H.head_usable(timing) else 0.0
    if why is None and w_s <= 0 and w_t <= 0:
        why = "no usable head carries a positive registered weight"
    return {"model_id": MODEL_ID, "base_model_id": H.V2_ASSEMBLED_ID, "side": side,
            "frame": frame, "config": {"lam": {"skill": lam_s, "timing": lam_t}},
            "skill": skill, "timing": timing, "w_skill": w_s, "w_time": w_t,
            "w_skill_unscaled": w_s, "w_time_unscaled": w_t,
            "consensus_only": w_s <= 0 and w_t <= 0, "consensus_only_reason": why,
            "war_map": H.fit_war_map(train), "n_train": len(train),
            "train_years": sorted({int(r["decision_year"]) for r in train})}


def predict_combined(model: dict, rows: list[dict]) -> list[dict]:
    """predict_v2's output on the combined model (the candidate columns read off the
    rows' v2 view by key; a missing one takes the training mean)."""
    return C._predict(model, rows)


# ---------------------------------------------------------------------------
# the tracking-era head blend (the document, section 4)
# ---------------------------------------------------------------------------

def _head():
    import efv5_tracking_head as T
    return T


def head_blend(side: str, rows: list[dict], orders: np.ndarray, season: int, *,
               mlbam_of, fits: dict | None = None, tracking: dict | None = None) -> tuple[np.ndarray, dict]:
    """orders with the tracked rows of a shipping side re-ordered among themselves by the
    registered blend (efv5_tracking_head.blend_orders, weight BLEND_W), the subset's
    multiset of order indices kept. Returns (orders, receipt)."""
    T = _head()
    fits = T.shipped_sides() if fits is None else fits
    fit = fits.get(side)
    rec = {"side": side, "season": int(season), "ships": fit is not None, "tracked": 0,
           "rows": len(rows), "blend_w": T.BLEND_W}
    out = np.asarray(orders, dtype=np.float64).copy()
    if fit is None or not rows:
        return out, rec
    trk = T.live_tracking(side, int(season)) if tracking is None else tracking
    idx, head_rows = [], []
    for i, r in enumerate(rows):
        pid = mlbam_of(r)
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        t = trk.get(pid)
        if t is None:
            continue
        idx.append(i)
        head_rows.append({"level": t[0], "fv": float(r["fv"]), "m": t[1]})
    rec["tracked"] = len(idx)
    if not idx:
        return out, rec
    oh = T.head_order_from_fit(fit, head_rows)
    old = out[idx]
    out[idx] = T.blend_orders(old, oh)
    rec["moved"] = int(np.sum(out[idx] != old))
    return out, rec


def blend_season(fid: str, fold) -> int | None:
    """The tracked season the head reads on a frame's fold: the 2025 debut cohort's pinned
    read reads 2024; nothing else in the backtest (the document, section 4)."""
    if fid == "vm_pros" and int(fold) == F.R_VM_FIRST_DEBUT_YEAR:
        return int(fold) - 1
    return None


# ---------------------------------------------------------------------------
# the backtest: fits, orders, reads
# ---------------------------------------------------------------------------

def _names():
    BT, _B4 = _tools()
    cand, v2 = BT.V3_KEY, BT.V2_KEY
    raters = ((cand, MODEL_ID), (v2, "efv_v2"), (BT.CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
    comps = (("v5c_vs_efv_v2", cand, v2), ("v5c_vs_prospx_consensus", cand, BT.CONS),
             ("v5c_vs_mlb_pipeline", cand, "mlb_pipeline"),
             ("v5c_vs_fangraphs", cand, "fangraphs"),
             ("efv_v2_vs_prospx_consensus", v2, BT.CONS))
    return raters, comps


@contextmanager
def v5c_names():
    BT, _B4 = _tools()
    raters, comps = _names()
    orig = (BT.COMPARISONS, BT.RATERS_OUT)
    BT.COMPARISONS, BT.RATERS_OUT = comps, raters
    try:
        yield
    finally:
        BT.COMPARISONS, BT.RATERS_OUT = orig


class Fits:
    """The combined fit per (frame, side, fold) on the inputs, memoized."""

    def __init__(self, inp, *, with_se: bool = False):
        self.inp = inp
        self.with_se = with_se
        self._cache: dict = {}

    def fold(self, fid: str, side: str, fold, *, train=None, test=None, cache: bool = True) -> dict:
        BT, _B4 = _tools()
        key = (fid, side, int(fold))
        if cache and train is None and key in self._cache:
            return self._cache[key]
        blk = self.inp.frames[fid]["by_side"][side][int(fold)]
        kind = BT.FRAME_KIND[fid]
        cols = (self.inp.cols.get(fid) or {}).get(side) or {}
        tr = attach(blk["train"] if train is None else train, side, cols, "train")
        te = attach(blk["test"] if test is None else test, side, cols, "test")
        m = fit_combined(tr, side, frame=kind, weights=self.inp.weights,
                         absent_ok=self.inp.absent_ok, gate_sha=self.inp.gate_sha,
                         with_se=self.with_se and train is None)
        pred = predict_combined(m, te)
        order = np.array([p["order_idx"] for p in pred], dtype=np.float64)
        season = blend_season(fid, fold)
        head_rec = None
        if season is not None:
            raw = (self.inp.meta.get("raw_by_side") or {}).get(side) or {}
            order, head_rec = head_blend(side, te, order, season,
                                         mlbam_of=lambda r: (raw.get(r["player_key"]) or {}).get("mlbam_id"))
        out = {"model": m, "order": order, "order_no_head": np.array([p["order_idx"] for p in pred]),
               "index": {r["player_key"]: i for i, r in enumerate(te)}, "head": head_rec,
               "receipt": fold_receipt(m, len(blk["scored"]) if train is None else None)}
        if cache and train is None:
            self._cache[key] = out
        return out

    def orders(self, fid: str, *, with_head: bool = True) -> tuple[dict, dict]:
        out: dict = {}
        rec: dict = {}
        for side in F.SIDES:
            for fold, blk in self.inp.frames[fid]["by_side"][side].items():
                f = self.fold(fid, side, fold)
                order = f["order"] if with_head else f["order_no_head"]
                for c in blk["scored"]:
                    i = f["index"].get(c["key"])
                    if i is None:
                        raise RuntimeError(f"{fid} {side} {fold}: no combined score for {c['key']}")
                    out[(side, int(fold), c["key"])] = float(order[i])
                rec[f"{side}|{fold}"] = dict(f["receipt"], head=f["head"])
        return out, rec


def _head_receipt(head: dict | None) -> dict | None:
    if head is None:
        return None
    cands = candidates()
    by_key = {s["key"]: n for n, s in cands.items()}
    se = head.get("se") or {}
    return {"keys": list(head["keys"]), "alpha": _lam_str(head.get("alpha")),
            "lam": _lam_str(head.get("lam")), "b_uc": round(float(head["b_uc"]), 6),
            "n_train": head.get("n_train"),
            "v2_keys": head.get("v2_keys"),
            "zero_candidates": [by_key.get(k, k) for k in head.get("zero_candidates") or []],
            "slopes": {(by_key.get(k) or k): {
                "beta": round(float(b), 6),
                "se": (None if (se.get(k) or {}).get("se") is None else round(float(se[k]["se"]), 6)),
                "at_bound": (se.get(k) or {}).get("at_bound"),
                "sign": cands[by_key[k]]["sign"] if k in by_key else None}
                for k, b in zip(head["keys"], head["beta"])}}


def _lam_str(v):
    if v is None:
        return None
    return "inf" if math.isinf(float(v)) else float(v)


def fold_receipt(m: dict, n_scored) -> dict:
    return {"consensus_only": m["consensus_only"], "reason": m.get("consensus_only_reason"),
            "w_skill": m["w_skill"], "w_time": m["w_time"], "n_train": m["n_train"],
            "lam": {h: _lam_str(v) for h, v in m["config"]["lam"].items()},
            "alpha": {h: _lam_str((m.get(h) or {}).get("alpha")) for h in HEADS},
            "skill_keys": (m["skill"] or {}).get("keys"),
            "timing_keys": (m["timing"] or {}).get("keys"),
            "nonzero": {h: [k for k, b in zip((m.get(h) or {}).get("keys") or [],
                                               (m.get(h) or {}).get("beta") or []) if b != 0.0]
                        for h in HEADS},
            "n_scored": n_scored}


def _keep(d: dict) -> dict:
    return {k: v for k, v in d.items() if k in ("delta", "ci95", "mde95", "n", "status", "reading")}


def cell_block(rows: list[dict], *, B: int, seed: int) -> dict:
    """The position-group cells (efv_strata.position_family on hitters; pitchers one cell;
    never an FV cell): within Spearman of every rater, v5c minus V2 and minus consensus."""
    BT, _B4 = _tools()
    import efv_v2_stat as S
    out = {}
    for side, cell in BT.CELLS:
        sel = [c for c in rows if c["side"] == side and (side == "pit" or c.get("cell") == cell)]
        blk = {"n": len(sel), "n_players": len({c["key"] for c in sel})}
        if len(sel) >= S.MIN_GROUP_ROWS:
            st = BT.rater_stats(sel)
            blk["raters"] = {k: {"within": r["within"], "n": r["n"]} for k, r in st.items()}
            blk["v5c_vs_efv_v2"] = _keep(BT.paired(sel, BT.V3_KEY, BT.V2_KEY, "within", B=B, seed=seed))
            blk["v5c_vs_prospx_consensus"] = _keep(BT.paired(sel, BT.V3_KEY, BT.CONS, "within",
                                                             B=B, seed=seed))
        else:
            blk["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        out[f"{side}:{cell}"] = blk
    return out


def group_cells(inp, fid: str, rows: list[dict], *, B: int, seed: int) -> dict:
    """Per candidate column with a non-zero slope in some fold: v5c minus V2 within on the
    scored rows inside its group (a non-zero column value). Level, band, role groups only."""
    BT, _B4 = _tools()
    out = {}
    cands = candidates()
    for n, s in cands.items():
        if s["source"] not in ("group", "tool"):
            continue
        cols = ((inp.cols.get(fid) or {}).get(s["side"]) or {}).get(n) or {}
        keep = {(k[0], k[1]) for k, v in cols.items() if k[2] == "test" and v not in (None, 0.0)}
        sel = [c for c in rows if (int(c["year"]), c["key"]) in keep]
        blk = {"n": len(sel), "n_players": len({c["key"] for c in sel})}
        if len(sel) >= 20:
            blk["v5c_vs_efv_v2"] = _keep(BT.paired(sel, BT.V3_KEY, BT.V2_KEY, "within", B=B, seed=seed))
            blk["v5c_vs_prospx_consensus"] = _keep(BT.paired(sel, BT.V3_KEY, BT.CONS, "within",
                                                             B=B, seed=seed))
        else:
            blk["status"] = "under 20 rows; not scored"
        out[n] = blk
    return out


def frame_doc(fits: Fits, fid: str, *, B: int, role: str, note: str, log=print) -> dict:
    BT, _B4 = _tools()
    _r, comps = _names()
    inp = fits.inp
    orders, rec = fits.orders(fid)
    rows = inp.rows_with(fid, orders)
    t1 = time.time()
    blk = BT.frame_block(rows, B=B, comparisons=comps)
    blk.update({"frame_version": BT.FRAME_VERSION[fid], "receipts": rec,
                "fold_deltas_vs_v2": BT.fold_deltas(rows, BT.V3_KEY, BT.V2_KEY),
                "fold_deltas_vs_consensus": BT.fold_deltas(rows, BT.V3_KEY, BT.CONS),
                "cells": cell_block(rows, B=B, seed=BT.SEED),
                "group_cells": group_cells(inp, fid, rows, B=B, seed=BT.SEED),
                "role": role, "note": note,
                "window": [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])]})
    if any(r.get("head") and r["head"].get("tracked") for r in rec.values()):
        o2, _r2 = fits.orders(fid, with_head=False)
        rows2 = inp.rows_with(fid, o2)
        blk["without_tracking_head"] = {
            "deltas": {name: {"spearman": _keep(BT.paired(rows2, a, b, "within", B=B, seed=BT.SEED))}
                       for name, a, b in comps[:2]},
            "per_side": {s: {name: _keep(BT.paired([c for c in rows2 if c["side"] == s], a, b,
                                                   "within", B=B, seed=BT.SEED))
                             for name, a, b in comps[:2]} for s in F.SIDES}}
    w = blk["deltas"]["v5c_vs_efv_v2"]["spearman"]
    c = blk["deltas"]["v5c_vs_prospx_consensus"]["spearman"]
    log(f"  {fid}: vs V2 {w.get('delta')} {w.get('ci95')}; vs consensus {c.get('delta')} "
        f"{c.get('ci95')} ({round(time.time() - t1, 1)} s stats)")
    return blk


# ---------------------------------------------------------------------------
# E_refit on the spent frames (tools/efv_v3_backtest.e_refit with the combined fit)
# ---------------------------------------------------------------------------

def _refit_draw(fits: Fits, fid: str, rng) -> list[dict]:
    BT, _B4 = _tools()
    inp = fits.inp
    fr = inp.frames[fid]
    kind = BT.FRAME_KIND[fid]
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
            f5 = fits.fold(fid, side, V, train=train, test=test, cache=False)
            o5 = f5["order"]
            sc = {c["key"]: c for c in blk["scored"]}
            war_map = m2["war_map"]
            idx = [i for i, r in enumerate(test) if r["player_key"] in sc]
            if not idx:
                continue
            groups = [sc[test[i]["player_key"]]["group"] for i in idx]
            fv = np.array([sc[test[i]["player_key"]]["grades"][BT.CONS] for i in idx])
            g5 = H.output_map(np.array([o5[i] for i in idx]), groups, fv)
            g2 = H.output_map(np.array([p2[i] for i in idx]), groups, fv)
            pr5, pr2, prc = (H.war_at(war_map, g) for g in (g5, g2, fv))
            for j, i in enumerate(idx):
                c = sc[test[i]["player_key"]]
                row = dict(c, grades=dict(c["grades"], **{BT.V3_KEY: float(o5[i]), BT.V2_KEY: p2[i]}))
                prices = {BT.V3_KEY: float(pr5[j]), BT.V2_KEY: float(pr2[j]), BT.CONS: float(prc[j])}
                for src in BT.SOURCES:
                    if c["grades"].get(src) is not None:
                        prices[src] = float(H.war_at(war_map, [c["grades"][src]])[0])
                row["prices"] = prices
                rows_out.append(row)
    return rows_out


def e_refit(fits: Fits, fid: str, *, B: int, seed: int | None = None, log=print,
            point: dict | None = None) -> dict:
    BT, _B4 = _tools()
    import efv_v2_stat as S
    seed = BT.SEED_REFIT if seed is None else int(seed)
    t0 = time.time()
    draws: dict = {}
    used = 0
    for b in range(int(B)):
        rng = np.random.default_rng(int(seed) + b)
        rows = _refit_draw(fits, fid, rng)
        if not rows:
            continue
        used += 1
        for k, d in BT.all_point_deltas(rows).items():
            for stat, v in d.items():
                if v is not None:
                    draws.setdefault(k, {}).setdefault(stat, []).append(float(v))
        if (b + 1) % 10 == 0:
            log(f"  E_refit {fid}: {b + 1} of {B} draws ({round(time.time() - t0, 1)} s)")
    out = {"B": int(B), "B_used": used, "seed": int(seed), "estimator": "E_refit",
           "what": ("the pool resampled by player with replacement; every fold of the combined "
                    "model (lambda re-chosen inside the draw's own training years) and of V2 "
                    "refit on the drawn training rows (the fold's drawn test players left out) "
                    "and scored on the drawn test rows; consensus, Pipeline and FanGraphs fixed"),
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
# the weights tables (the document, section 5)
# ---------------------------------------------------------------------------

def weights_table(m: dict) -> dict:
    """Every driver of a fitted model: standardised slope, SE, the weight in
    consensus-percentile equivalents (w_head x beta / b_uc) and whether it is zero."""
    cands = candidates()
    by_key = {s["key"]: n for n, s in cands.items()}
    out = {"side": m["side"], "frame": m["frame"], "n_train": m["n_train"],
           "train_years": m.get("train_years"), "w_skill": m["w_skill"], "w_time": m["w_time"],
           "consensus_only": m["consensus_only"], "heads": {}}
    for h in HEADS:
        head = m.get(h)
        if head is None:
            out["heads"][h] = None
            continue
        w = m["w_skill"] if h == "skill" else m["w_time"]
        se = head.get("se") or {}
        rows = []
        pairs = list(zip(head["keys"], head["beta"])) + [(k, 0.0) for k in head.get("zero_candidates") or []]
        for k, b in pairs:
            n = by_key.get(k)
            src = cands[n]["source"] if n else "v2"
            s = se.get(k) or {}
            eq = (w * float(b) / float(head["b_uc"])) if head["b_uc"] > 0 else None
            rows.append({"driver": n or k, "source": src, "head": h,
                         "sign_constraint": cands[n]["sign"] if n else None,
                         "beta": round(float(b), 6),
                         "se": None if s.get("se") is None else round(float(s["se"]), 6),
                         "weight_pct_equiv": None if eq is None else round(eq, 6),
                         "weight_se_pct_equiv": (None if (s.get("se") is None or head["b_uc"] <= 0)
                                                 else round(w * float(s["se"]) / float(head["b_uc"]), 6)),
                         "zero": float(b) == 0.0, "at_bound": bool(s.get("at_bound")),
                         "fixed": bool(s.get("fixed")) or k in (head.get("zero_candidates") or [])})
        out["heads"][h] = {"alpha": _lam_str(head.get("alpha")), "lam": _lam_str(head.get("lam")),
                           "b_uc": round(float(head["b_uc"]), 6), "b0": round(float(head["b0"]), 6),
                           "n_train": head["n_train"], "usable": H.head_usable(head),
                           "drivers": rows,
                           "zero_drivers": [r["driver"] for r in rows if r["zero"]],
                           "nonzero_drivers": [r["driver"] for r in rows if not r["zero"]]}
    return out


def production_train(side: str, *, log=print) -> list[dict]:
    """The production fit's training rows: every v1 matrix row with a decision year before
    the R-VM cohort, with every candidate column attached at its matrix cutoff (the
    builders of build_dev on a one-fold frame shaped like vm_dev)."""
    data = [r for r in H.matrix_training_rows(side)
            if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
    cols = production_columns(side, data, log=log)
    return attach(data, side, cols, "train")


_PROD_COLS: dict = {}


def production_columns(side: str, data: list[dict], *, log=print, refresh: bool = False) -> dict:
    """{name: {(year, pk, 'train'): value}} for every candidate column of the side on the
    production training rows (memoized per process)."""
    if side in _PROD_COLS and not refresh:
        return _PROD_COLS[side]
    BT, B4 = _tools()
    SC = _scout()
    raw = _raw_by_side()
    out: dict = {}
    t0 = time.time()
    g5_names = [n for n, s in G.menu_columns().items() if s["side"] == side]
    vm_vals, _cnt = G.vm_columns(side, data, raw[side], g5_names, log=log)
    for n in g5_names:
        out[n] = {(int(r["decision_year"]), r["player_key"], "train"):
                  vm_vals[n].get((int(r["decision_year"]), r["player_key"]), 0.0) for r in data}
    t_names = [n for n in TOOL_CELLS if TOOL_CELLS[n]["side"] == side]
    if t_names:
        tv, _c = tool_vm_columns(side, data, raw[side], t_names, SC.default_index(), log=log)
        for n in t_names:
            out[n] = {(int(r["decision_year"]), r["player_key"], "train"):
                      tv[n].get((int(r["decision_year"]), r["player_key"]), 0.0) for r in data}
    # the v4 and scouting families through the backtest builders on a one-fold frame
    fake = _FakeInputs({"lv_prod": {"by_side": {s: {} for s in F.SIDES}},
                        "vm_prod": {"by_side": {s: ({F.R_VM_FIRST_DEBUT_YEAR: {"train": data, "test": []}}
                                                    if s == side else {}) for s in F.SIDES}}})
    v4_names = [n for n, s in V4.menu_columns().items() if s["side"] == side]
    v4_cols, _rec = B4.v4_values(fake, ("lv_prod", "vm_prod"), {s: {} for s in F.SIDES}, v4_names,
                                 log=log)
    out.update(v4_cols["vm_prod"][side])
    w2_names = [n for n in W2S_COLUMNS if V3.W2_COLUMNS[n]["side"] == side]
    index = SC.default_index()
    for n in w2_names:
        spec = V3.W2_COLUMNS[n]
        slots = [((int(r["decision_year"]), r["player_key"], "train"), r["player_key"],
                  (raw[side].get(r["player_key"]) or {}).get("asof_date")) for r in data]
        got = SC.values_for(slots, spec["arg"], index)
        out[n] = {k: (None if v is None else float(v)) for k, v in got.items()}
    log(f"  production columns {side}: {len(out)} built ({round(time.time() - t0, 1)} s)")
    _PROD_COLS[side] = out
    return out


class _FakeInputs:
    """The frame shape the v4 family builders read, with nothing else."""

    def __init__(self, frames: dict):
        self.frames = frames
        self.cols: dict = {}
        self.meta: dict = {}


def production_fit(side: str, *, weights: dict | None = None, log=print) -> dict:
    """The combined model on the production rows (the fit the served path would use)."""
    w = H.load_weights() if weights is None else weights
    train = production_train(side, log=log)
    m = fit_combined(train, side, frame="vm", weights=w, with_se=True)
    m["war_map_6yr"] = H.fit_war_map(train)
    return m


def production_models(*, weights: dict | None = None, log=print) -> dict[str, dict]:
    """{side: the production fit} (efv_v2_serve.production_models reads this while
    EFV_V5_COMBINED_ON is True; dark otherwise)."""
    w = H.load_weights() if weights is None else weights
    return {side: production_fit(side, weights=w, log=log) for side in F.SIDES}


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

def _code() -> dict:
    BT, _B4 = _tools()
    return {"commit": BT._commit(), "tool": TOOL, "tool_sha256": BT._sha(ROOT / TOOL),
            "efv5_group_drivers_sha256": BT._sha(ROOT / "efv5_group_drivers.py"),
            "efv5_atlas_tools_sha256": BT._sha(ROOT / "efv5_atlas_tools.py"),
            "efv_v4_sha256": BT._sha(ROOT / "efv_v4.py"),
            "efv_v3_sha256": BT._sha(ROOT / "efv_v3.py"),
            "efv_v2_model_sha256": BT._sha(ROOT / "efv_v2_model.py"),
            "efv_v2_candidates_sha256": BT._sha(ROOT / "efv_v2_candidates.py"),
            "efv5_tracking_head_sha256": BT._sha(ROOT / "efv5_tracking_head.py"),
            "tracking_head_artifact_sha256": BT._sha(DATA_DIR / "efv5_tracking_head.json"),
            "atlas_artifact_sha256": BT._sha(G.ATLAS_PATH),
            "tools_atlas_artifact_sha256": BT._sha(TOOLS_ATLAS_PATH)}


def _cands_doc() -> dict:
    return {n: {k: v for k, v in s.items() if k != "key"} for n, s in candidates().items()}


def declared() -> dict:
    return {"doc": DOC, "model": ("V2's order index and P5 weights; each head one joint "
                                  "penalized fit of V2's admitted drivers at V2's alpha with "
                                  "every candidate column at one lambda, sign-bounded"),
            "lambda_grid": [_lam_str(v) for v in LAMBDAS],
            "lambda_rule": "nested forward-chained CV inside the fold's training years (V2's rule)",
            "candidates": len(candidates()), "excluded": EXCLUDED_W2,
            "tracking_head": {"weight": _head().BLEND_W, "sides": sorted(_head().shipped_sides()),
                              "applied_on": "vm_pros 2025 test rows (season 2024) and the live board"},
            "ship_rule": ("EW3-9: pooled over lv_dev, vm_dev, R-LV and R-VM by row count, "
                          "within v5c minus V2 above 0; and v5c minus V2 within >= "
                          f"{-MAX_HELD_OUT_TRAIL} on R-LV and on R-VM")}


def fit_doc(inp, frames: dict, weights_tables: dict, *, B: int) -> dict:
    BT, _B4 = _tools()
    import efv_v2_stat as S
    return {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": BT._now(),
            "role": "development", "adjudicates": False, "selects": True, "note": NOTE_FIT,
            "owner_decision": "EW3-8 and EW3-9 (2026-10-15)", "declared": declared(),
            "statistic": S.STAT_LABEL[S.PRIMARY], "label": inp.label, "code": _code(),
            "assembly_sha256": BT._sha(H.ASSEMBLY_PATH), "weights_p5": inp.weights,
            "bootstrap": {"B": int(B), "seed": BT.SEED, "estimator": "E_cond", "unit": "player cluster"},
            "reserved_guard": inp.guards, "base_parity": inp.meta.get("base_parity"),
            "v3_base_parity": inp.meta.get("v3_base_parity"),
            "candidates": _cands_doc(), "column_receipts": inp.meta.get("column_receipts"),
            "frames": frames, "weights": weights_tables}


def spent_doc(inp, res: dict, *, B: int, b_refit: int, fit_doc_: dict, gate_sha: str) -> dict:
    BT, _B4 = _tools()
    import efv_v2_stat as S
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": BT._now(),
           "role": "spent", "adjudicates": False, "selects": False, "one_read": True,
           "label_note": SPENT_LABEL, "note": NOTE_SPENT, "ledger_rows": False,
           "owner_decision": ("EW3-5 and EW3-9: the reserved frames were read once by the v3 "
                              "confirmation and are spent; this read of the committed method "
                              "chooses nothing and is labelled spent"),
           "gate": {"doc": F.GATE_DOC, "sha": gate_sha, "guards": inp.guards},
           "declared": declared(), "label": inp.label, "code": _code(),
           "assembly_sha256": BT._sha(H.ASSEMBLY_PATH), "weights_p5": inp.weights,
           "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "secondary": S.STAT_LABEL[S.SECONDARY],
                         "veto": S.STAT_LABEL["auc"], "min_group_rows": S.MIN_GROUP_ROWS},
           "bootstrap": {"E_cond": {"B": int(B), "seed": BT.SEED, "unit": "player cluster"},
                         "E_refit": {"B": int(b_refit), "seed": BT.SEED_REFIT, "unit": "player cluster"}},
           "frames_built": {"lv_res": {"per_vintage": inp.meta.get("lv_per_vintage")},
                            "vm_pros": {"per_fold": inp.meta.get("vm_per_fold")}},
           "v5_base_parity": inp.meta.get("v5_base_parity"),
           "candidates": _cands_doc(), "column_receipts": inp.meta.get("column_receipts"),
           "frames": res["frames"], "elapsed_s": res["elapsed_s"]}
    doc["ship_rule"] = ship_reading(fit_doc_, doc)
    return doc


def ship_reading(fit_doc_: dict, spent_doc_: dict) -> dict:
    """EW3-9, as the document fixes it (section 7)."""
    BT, _B4 = _tools()
    frames = {}
    tot_n = 0
    tot = 0.0
    ok = True
    for fid, doc in [(f, fit_doc_) for f in BT.FRAMES_DEV] + [(f, spent_doc_) for f in BT.FRAMES_RES]:
        blk = doc["frames"][fid]
        d = blk["deltas"]["v5c_vs_efv_v2"]["spearman"].get("delta")
        n = int(blk["n"])
        frames[fid] = {"n": n, "delta_vs_v2": d}
        if d is None:
            ok = False
            continue
        tot += n * float(d)
        tot_n += n
    pooled = (tot / tot_n) if tot_n else None
    held = {fid: frames[fid]["delta_vs_v2"] for fid in BT.FRAMES_RES}
    rule1 = pooled is not None and pooled > 0
    rule2 = all(v is not None and v >= -MAX_HELD_OUT_TRAIL for v in held.values())
    cons = {}
    for fid in BT.FRAMES_RES:
        legs = ((spent_doc_["frames"][fid].get("e_refit") or {}).get("legs") or {}).get("both") or {}
        rc = (legs.get("v5c_vs_prospx_consensus") or {}).get("spearman") or {}
        cons[fid] = {"delta": rc.get("delta"), "e_refit_ci95": rc.get("ci95"),
                     "beats_consensus_resolved": bool(rc.get("ci95") and rc["ci95"][0] > 0)}
    return {"rule": declared()["ship_rule"], "frames": frames,
            "pooled_delta_vs_v2": None if pooled is None else round(pooled, 5),
            "pooled_rows": tot_n, "rule_pooled_above_zero": bool(rule1),
            "rule_held_out_trail": bool(rule2), "max_held_out_trail": MAX_HELD_OUT_TRAIL,
            "ships": bool(ok and rule1 and rule2), "vs_consensus_spent": cons}


def verdict_text(c: dict, rc: dict, w: dict, rv: dict) -> str:
    d = c.get("delta")
    lo = (rc.get("ci95") or [None, None])[0]
    if d is None:
        return "not derived"
    if lo is not None and lo > 0:
        head = f"eFV v5 COMBINED beats consensus within by {d:+.4f} (E_refit CI95 clear of zero)"
    elif d > 0:
        head = f"eFV v5 COMBINED reads {d:+.4f} within over consensus; not resolved (E_refit CI95 spans zero)"
    else:
        head = f"eFV v5 COMBINED reads {d:+.4f} within against consensus; ties or trails"
    dv = w.get("delta")
    tail = "" if dv is None else f"; vs served eFV (V2) {dv:+.4f} (E_refit CI95 {rv.get('ci95')})"
    return head + tail + f"; {SPENT_LABEL}"


# ---------------------------------------------------------------------------
# progress-ledger rows (development only; the spent read writes none)
# ---------------------------------------------------------------------------

_LEDGER_RATERS = (("efv", MODEL_ID), ("efv_v2_base", "efv_v2"),
                  ("prospx_consensus", "prospx_consensus"),
                  ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
_LEDGER_DELTAS = (("vs_efv_v2_base", "v5c_vs_efv_v2"),
                  ("vs_prospx_consensus", "v5c_vs_prospx_consensus"),
                  ("vs_mlb_pipeline", "v5c_vs_mlb_pipeline"),
                  ("vs_fangraphs", "v5c_vs_fangraphs"),
                  ("efv_v2_base_vs_prospx_consensus", "efv_v2_vs_prospx_consensus"))


def ledger_rows(doc: dict, *, artifact: Path, date: str, now_iso: str) -> list[dict]:
    import efv_progress as P
    import efv_v2_stat as S
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
                                "mde95": leg.get("mde95"), "mde95_estimator": leg.get("estimator"),
                                "ci95_estimator": leg.get("ci95_estimator"), "resolvable": None,
                                "reading": leg.get("reading"),
                                "key": f"frames.{fid}.deltas.{comp}.{metric}"}
            if legs:
                deltas[name] = legs
        nbs = {s: (f.get("n_by_side") or {})[s] for s in P.STRATA
               if (f.get("n_by_side") or {}).get(s)} or None
        row = {"run_id": None, "date": date, "trigger": "efv_change", "model_id": MODEL_ID,
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
    led = LEDGER_PATH if ledger_path is None else Path(ledger_path)
    led.parent.mkdir(parents=True, exist_ok=True)
    return P.commit_rows(rows, data_dir=P.DATA_DIR, ledger_path=led,
                         sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def summary_lines(doc: dict) -> list[str]:
    out = []
    for fid, f in doc["frames"].items():
        for name in ("v5c_vs_efv_v2", "v5c_vs_prospx_consensus", "v5c_vs_mlb_pipeline",
                     "v5c_vs_fangraphs"):
            w = f["deltas"][name]["spearman"]
            rl = ((((f.get("e_refit") or {}).get("legs") or {}).get("both") or {})
                  .get(name) or {}).get("spearman") or {}
            out.append(f"{fid} {name:27s} within {w.get('delta')} E_cond {w.get('ci95')}"
                       + (f" E_refit {rl.get('ci95')}" if rl else ""))
    return out


def run_fit(*, B: int, log=print, ledger: bool = True, ledger_path: Path | None = None) -> dict:
    BT, _B4 = _tools()
    t0 = time.time()
    with G.registered(), v5c_names():
        inp, _frames_lv, _rec = build_dev(log=log)
        fits = Fits(inp, with_se=True)
        frames = {}
        for fid in BT.FRAMES_DEV:
            blk = frame_doc(fits, fid, B=B, role="development",
                            note=NOTE_FIT + "; the penalty was chosen on this frame out of fold",
                            log=log)
            w = blk["deltas"]["v5c_vs_efv_v2"]["spearman"]
            c = blk["deltas"]["v5c_vs_prospx_consensus"]["spearman"]
            blk["verdict"] = (f"DEVELOPMENT ONLY (lambda chosen on these frames out of fold): within "
                              f"vs V2 {BT._rnd(w.get('delta'), 4)} (CI95 {w.get('ci95')}), vs consensus "
                              f"{BT._rnd(c.get('delta'), 4)} (CI95 {c.get('ci95')}); adjudicates nothing")
            frames[fid] = blk
        # the per-fold weights (every fold) and the production fit's weights
        wt = {"folds": {}, "production": {}}
        for fid in BT.FRAMES_DEV:
            for side in F.SIDES:
                for fold in inp.frames[fid]["by_side"][side]:
                    f = fits.fold(fid, side, fold)
                    wt["folds"][f"{fid}|{side}|{fold}"] = weights_table(f["model"])
        for side in F.SIDES:
            log(f"production fit {side}")
            m = production_fit(side, weights=inp.weights, log=log)
            wt["production"][side] = weights_table(m)
        doc = fit_doc(inp, frames, wt, B=B)
        doc["elapsed_s"] = round(time.time() - t0, 1)
    out = BT.write_doc(doc, FIT_PATH)
    BT.write_doc({"schema": 1, "model_id": MODEL_ID, "produced_by": TOOL,
                  "generated_at": doc["generated_at"], "role": "development", "served": False,
                  "note": "the production fit's weights as read at the development fit; the served "
                          "file is data/efv5_combined_weights.json, written by --weights if it ships",
                  "weights": wt["production"], "code": doc["code"]}, LAB_WEIGHTS_PATH)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    if ledger:
        r = append_ledger(doc, artifact=out, ledger_path=ledger_path)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
    return doc


def run_spent(*, gate_sha: str, B: int, b_refit: int, log=print) -> dict:
    BT, _B4 = _tools()
    if SPENT_PATH.exists():
        raise RuntimeError(f"{SPENT_PATH} exists; the spent frames are read once by this tool")
    if not FIT_PATH.exists():
        raise RuntimeError("the development fit comes first")
    fit_doc_ = json.loads(FIT_PATH.read_text(encoding="utf-8"))
    t0 = time.time()
    with G.registered(), v5c_names():
        inp, _got, _rec = build_spent(gate_sha=gate_sha, log=log)
        fits = Fits(inp, with_se=True)
        frames = {}
        for fid in BT.FRAMES_RES:
            blk = frame_doc(fits, fid, B=B, role="spent", note=NOTE_SPENT, log=log)
            blk["label"] = SPENT_LABEL
            blk["outcome"] = ("W3 (WAR over the first three MLB seasons, 0 if no debut within "
                              "three seasons of V)" if fid == "lv_res"
                              else "career WAR to date (2025 and 2026 seasons)")
            wt = {}
            for side in F.SIDES:
                for fold in inp.frames[fid]["by_side"][side]:
                    wt[f"{side}|{fold}"] = weights_table(fits.fold(fid, side, fold)["model"])
            blk["weights"] = wt
            log(f"  {fid}: E_refit B {b_refit} starts")
            blk["e_refit"] = e_refit(fits, fid, B=b_refit, log=log, point=blk)
            w = blk["deltas"]["v5c_vs_efv_v2"]["spearman"]
            c = blk["deltas"]["v5c_vs_prospx_consensus"]["spearman"]
            legs = (blk["e_refit"]["legs"].get("both") or {})
            rc = ((legs.get("v5c_vs_prospx_consensus") or {}).get("spearman") or {})
            rv = ((legs.get("v5c_vs_efv_v2") or {}).get("spearman") or {})
            blk["verdict"] = verdict_text(c, rc, w, rv)
            frames[fid] = blk
            log(f"  {fid}: vs V2 {w.get('delta')} E_cond {w.get('ci95')} E_refit {rv.get('ci95')}; "
                f"vs consensus {c.get('delta')} E_cond {c.get('ci95')} E_refit {rc.get('ci95')}")
        res = {"frames": frames, "elapsed_s": round(time.time() - t0, 1)}
        doc = spent_doc(inp, res, B=B, b_refit=b_refit, fit_doc_=fit_doc_, gate_sha=gate_sha)
    out = BT.write_doc(doc, SPENT_PATH)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    for line in summary_lines(doc):
        log(line)
    log(f"ship rule: {json.dumps(doc['ship_rule'], default=str)}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="build the development inputs and "
                    "every candidate column; print coverage; no statistic")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--spent", action="store_true")
    ap.add_argument("--gate-sha", default=None)
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--b-refit", type=int, default=None)
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--ledger", action="store_true",
                    help="re-append the fit artifact's two development rows (integration path)")
    ap.add_argument("--ledger-path", default=None)
    a = ap.parse_args(argv)
    BT, _B4 = _tools()
    import efv_labels as L
    B = BT.B_DEFAULT if a.B is None else int(a.B)
    b_refit = BT.B_REFIT_DEFAULT if a.b_refit is None else int(a.b_refit)
    ledger_path = Path(a.ledger_path) if a.ledger_path else None

    def log(msg):
        print(msg, flush=True)
    if a.ledger:
        if not FIT_PATH.exists():
            log("refused: the fit artifact does not exist")
            return 2
        doc = json.loads(FIT_PATH.read_text(encoding="utf-8"))
        r = append_ledger(doc, artifact=FIT_PATH, ledger_path=ledger_path)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if L.provider() != BT.FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {BT.FROZEN_PROVIDER!r}")
        return 2
    if a.check:
        with G.registered(), v5c_names():
            inp, _frames_lv, rec = build_dev(log=log)
            counts = {fid: {"folds": inp.frames[fid]["folds"], "n": len(inp.scored(fid)),
                            "n_by_side": BT._n_side(inp.scored(fid))} for fid in BT.FRAMES_DEV}
            log(json.dumps({"check": True, "guards": inp.guards, "counts": counts,
                            "label": inp.label, "weights": inp.weights,
                            "candidates": {s: len(side_candidates(s)) for s in F.SIDES},
                            "coverage": rec["coverage"]}, indent=1, default=str))
        return 0
    if a.fit:
        if FIT_PATH.exists():
            log(f"refused: {FIT_PATH} exists; the fit ran once (delete it to refit)")
            return 2
        run_fit(B=B, log=log, ledger=not a.no_ledger, ledger_path=ledger_path)
        return 0
    if a.spent:
        if not a.gate_sha:
            log("refused: --gate-sha is required (the committed registration)")
            return 2
        run_spent(gate_sha=a.gate_sha, B=B, b_refit=b_refit, log=log)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

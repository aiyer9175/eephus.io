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
from datetime import date, datetime, timedelta, timezone
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
# the live board: every candidate column read as of today (the served path)
# ---------------------------------------------------------------------------
#
# THE DEFECT THIS CLOSES (2026-10-15). The production fit trains on the candidate columns
# production_columns builds, but the live rows efv_v2_serve.score_live scored carried V2's
# keys only: every candidate read None, took its head's training mean (z = 0) and moved
# nothing, so the served board was not the fitted v5 and no candidate chip could print.
#
# THE READ RULE (live_read). The group and centering year is the list year
# (efv_dataset.CURRENT_SEASON, efv_v2_serve.live_year). The read year is the list year + 1
# and the cutoff is today: the MiLB read efv_dataset.build_live_matrix already gives V2's
# own live keys ("LIVE scoring includes the CURRENT season"), so a live row stands to its
# candidate reads as a training row does (both at the row's read year and cutoff). The read
# season S is the last MiLB season ended by the cutoff (efv5_group_drivers.read_season):
# the list year's season once 1 October has passed, the season before until then, never a
# partial season. The literal alternative (read year = the list year, S one season older)
# is the one-line switch LIVE_READ_YEAR_OFFSET = 0. A scouting, NRI or rater read is as of
# min(the live row's consensus as-of date, today), as a training row reads at its matrix
# as-of date. Nothing dated after today is loaded: the scouting and NRI indexes are capped
# at today + 1 day (exclusive), the IL stints are cut at the read and at the transaction
# feed's last day, the population fit uses label windows closed before today's season.
#
# EACH FAMILY THROUGH ITS OWN PRIMITIVE. The production builders read the person and date
# from the training matrix by player_key and skip a 2025 or later decision year, so on a
# live row they return nothing, silently. These call the per-person primitives the
# builders call, with the same constants, z norms and centering:
#   group (28)   Lines.member at S, centered over the in-group rows of the group year
#   tool (4)     tool_member + tool_value + _tool_finish, z inside (cell, S)
#   il (13)      efv_w2_il_backfill.asof on a stint index parsed from the cached feed
#   nri (4)      efv_w2_nri.nri_values on an index through the list year
#   pbp (8)      efv_w2_pbp.profile, kept only with every column (B4._pbp's rule)
#   pbp_bb (2)   efv_w2_pbp_bb.profile from the last readable season down
#   popmle (2)   efv_w2_popmle.Translator at the read year, the live board left out
#   raters (2)   efv_w2_raters.resid_column inside (side, group year, live)
#   report (9)   None on every row: the production construction (production_columns hands
#                the report builder an empty list-vintage frame, so every training value
#                was None and the fitted slopes are exactly 0.0)
#   w2s (5)      efv_w2_scout.values_for on a snapshot index capped at today
# A family whose source does not yet cover the read gives None (the head's training-mean
# imputation, z = 0), never a stale or partial number; the receipt names it and why.

LIVE_KIND = "live"
#: The live read year is the list year plus this (1: efv_dataset.build_live_matrix's MiLB
#: read; 0 would read one season older than V2's own live keys).
LIVE_READ_YEAR_OFFSET = 1
_LIVE_MEMO: dict = {}
_LIVE_RECEIPTS: dict = {}
_LIVE_CACHE: dict = {}

#: Plain-English chip labels for every candidate key (efv_v2_serve.driver_chips reads them
#: after its own V2 labels). A timing-head key says it is about arrival, as V2's do.
CHIP_LABELS_V5: dict[str, str] = {
    # hitters, skill: the group drivers (z inside the level-season, centered in the year)
    "scr_g5_hit_A_all_all_k_pct": "Single-A strikeout rate",
    "scr_g5_hit_A_all_all_bb_minus_k": "Single-A walk rate minus strikeout rate",
    "scr_g5_hit_A_young_all_k_pct": "Single-A strikeout rate (young for level)",
    "scr_g5_hit_A_young_all_bb_minus_k": "Single-A walk rate minus strikeout rate (young for level)",
    "scr_g5_hit_A_all_all_avg": "Single-A batting average",
    "scr_g5_hit_A_all_all_ops": "Single-A OPS",
    "scr_g5_hit_A_all_all_woba": "Single-A wOBA",
    "scr_g5_hit_A_all_all_slg": "Single-A slugging",
    "scr_g5_hit_A_young_all_avg": "Single-A batting average (young for level)",
    "scr_g5_hit_CPX_all_all_avg": "Complex league batting average",
    "scr_g5_hit_CPX_all_all_ops": "Complex league OPS",
    "scr_g5_hit_CPX_all_all_woba": "Complex league wOBA",
    "scr_g5_hit_Ap_all_all_pbp_contact": "High-A contact rate on swings",
    "scr_g5_hit_Ap_all_all_pbp_swstr": "High-A swinging-strike rate",
    "scr_g5_hit_Ap_young_all_pbp_contact": "High-A contact rate on swings (young for level)",
    "scr_g5_hit_Ap_young_all_pbp_swstr": "High-A swinging-strike rate (young for level)",
    "scr_g5_hit_Ap_young_all_pbp_two_strike_contact": "High-A two-strike contact (young for level)",
    # hitters, skill: pitch events, batted balls, translation, lists, scouting grades
    "scr_w2p_swstr_h": "Swinging-strike rate vs level",
    "scr_w2p_contact_h": "Contact rate on swings vs level",
    "scr_w2p_swing_h": "Swing rate vs level",
    "scr_w2p_two_strike_contact_h": "Two-strike contact vs level",
    "scr_w2b_pull_h": "Pull rate on balls in play",
    "scr_w4p_pop_hit": "Minor league line translated to future WAR",
    "scr_w2r_panel_hit": "Outside prospect lists vs consensus",
    "scr_w2s_pwr_present_hit": "Present game power grade",
    "scr_w2s_game_pwr_hit": "Future game power grade",
    "scr_w2s_posval_hit": "Defensive value of listed position",
    # hitters, timing (arrival)
    "scr_g5_hit_A_all_all_age": "Age in Single-A (arrival)",
    "scr_g5_hit_A_young_all_age": "Age vs Single-A peers, young for level (arrival)",
    "scr_w2i_stints_time_hit": "Injured list stints, last four years (arrival)",
    "scr_w2i_days_time_hit": "Days on the injured list, last four years (arrival)",
    "scr_w2i_sixty_time_hit": "60-day injured list stints (arrival)",
    "scr_w2i_open_time_hit": "Injured list stint still open (arrival)",
    "scr_w2i_recur_time_hit": "Two or more injured list stints (arrival)",
    "scr_w2n_nri_pre_hit": "Big league spring training invite (arrival)",
    "scr_w2n_nri_count_pre_hit": "Big league spring training invites, count (arrival)",
    "scr_rpt_conviction_hit": "Scouting report conviction (arrival)",
    "scr_rpt_hedge_count_hit": "Hedging in the scouting report (arrival)",
    "scr_rpt_risk_hit": "Risk stressed in the scouting report (arrival)",
    "scr_rpt_approach_concern_hit": "Approach concerns in the scouting report (arrival)",
    "scr_rpt_writer_minus_stated_hit": "Report tone vs stated grade (arrival)",
    "scr_rpt_arrival_hit": "Scouting report timeline (arrival)",
    # pitchers, skill: the group drivers and the tool cells
    "scr_g5_pit_A_all_all_k_pct": "Single-A strikeout rate",
    "scr_g5_pit_A_all_all_k_minus_bb": "Single-A strikeout rate minus walk rate",
    "scr_g5_pit_A_young_all_k_pct": "Single-A strikeout rate (young for level)",
    "scr_g5_pit_A_young_all_k_minus_bb": "Single-A strikeout rate minus walk rate (young for level)",
    "scr_g5_pit_A_all_SP_k_pct": "Single-A strikeout rate (starters)",
    "scr_g5_pit_A_all_SP_k_minus_bb": "Single-A strikeout rate minus walk rate (starters)",
    "scr_g5_pit_A_all_SP_bf_per_g": "Single-A batters faced per game for age (starters)",
    "scr_t5_pit_Ap_all_SP_sl_gap": "Slider projection gap (High-A starters)",
    "scr_t5_pit_Ap_young_all_sl_gap": "Slider projection gap (young High-A pitchers)",
    "scr_t5_pit_Ap_all_all_sl_gap": "Slider projection gap (High-A pitchers)",
    "scr_t5_pit_AAA_all_all_fb_fut": "Fastball future grade (Triple-A pitchers)",
    # pitchers, skill: injuries, pitch events, batted balls, translation, lists, reports, grades
    "scr_w2i_stints_skill_pit": "Injured list stints, last four years",
    "scr_w2i_days_skill_pit": "Days on the injured list, last four years",
    "scr_w2i_sixty_skill_pit": "60-day injured list stints",
    "scr_w2i_open_skill_pit": "Injured list stint still open",
    "scr_w2i_recur_skill_pit": "Two or more injured list stints",
    "scr_w2p_cstr_p": "Called-strike rate vs level",
    "scr_w2p_csw_p": "Called plus swinging strike rate vs level",
    "scr_w2p_k_resid_p": "Strikeouts beyond whiff rate",
    "scr_w2p_fstrike_p": "First-pitch strike rate vs level",
    "scr_w2b_pu_p": "Popup rate allowed",
    "scr_w4p_pop_pit": "Minor league line translated to future WAR",
    "scr_w2r_panel_pit": "Outside prospect lists vs consensus",
    "scr_rpt_conviction_pit": "Scouting report conviction",
    "scr_rpt_writer_minus_stated_pit": "Report tone vs stated grade",
    "scr_w2s_brk_pit": "Best breaking ball future grade",
    "scr_w2s_cmd_pit": "Command future grade",
    # pitchers, timing (arrival)
    "scr_g5_pit_A_all_all_age": "Age in Single-A (arrival)",
    "scr_g5_pit_A_all_SP_age": "Age vs Single-A peers, starters (arrival)",
    "scr_w2i_stints_time_pit": "Injured list stints, last four years (arrival)",
    "scr_w2i_days_time_pit": "Days on the injured list, last four years (arrival)",
    "scr_w2i_recur_time_pit": "Two or more injured list stints (arrival)",
    "scr_w2n_nri_pre_pit": "Big league spring training invite (arrival)",
    "scr_w2n_nri_count_pre_pit": "Big league spring training invites, count (arrival)",
    "scr_rpt_arrival_pit": "Scouting report timeline (arrival)",
}


def chip_label(key: str) -> str:
    """The chip label of a candidate key (the key itself when none is registered)."""
    return CHIP_LABELS_V5.get(key, key)


def _day(v) -> str | None:
    s = str(v or "")[:10]
    try:
        date.fromisoformat(s)
    except ValueError:
        return None
    return s


def _next_day(d: str) -> str:
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def _season_ended(season: int, today: str) -> bool:
    """A MiLB season S has ended by `today` (the 1 October rule of read_season)."""
    y, m = int(today[:4]), int(today[5:7])
    return int(season) < y or (int(season) == y and m >= 10)


def live_read(today: str | None = None) -> dict:
    """The live board's read: {"today", "group_year", "read_year", "cutoff", "season"}."""
    import efv_dataset as D
    t = _day(today or date.today().isoformat())
    if t is None:
        raise ValueError(f"not a date: {today!r}")
    Y = int(D.CURRENT_SEASON)
    RY = Y + int(LIVE_READ_YEAR_OFFSET)
    S = G.read_season(RY, t)
    if not _season_ended(S, t):
        raise AssertionError(f"read season {S} had not ended by {t}")
    return {"today": t, "group_year": Y, "read_year": RY, "cutoff": t, "season": S}


def _item(slot, pk: str, mlbam, group: int, read_year: int, cutoff: str, asof: str | None,
          fv) -> dict:
    return {"slot": slot, "pk": pk, "mlbam": mlbam, "group": int(group),
            "read_year": int(read_year), "cutoff": cutoff, "asof": asof,
            "season": G.read_season(int(read_year), cutoff),
            "fv": None if fv is None else float(fv)}


def _cached(key, build):
    if key not in _LIVE_CACHE:
        _LIVE_CACHE[key] = build()
    return _LIVE_CACHE[key]


def _asof_lines(side: str, seasons) -> "G.Lines":
    """Lines over just the seasons read (season-local, so equal to the training build's
    values there; never stored in efv5_group_drivers._LINES)."""
    ss = tuple(sorted({int(s) for s in seasons}))
    metrics = [s["metric"] for s in G.menu_columns().values() if s["side"] == side]
    return _cached(("lines", side, ss),
                   lambda: G.Lines(side, metrics, seasons=ss, log=lambda *_a, **_k: None))


def _scout_index(today: str):
    """Board snapshots dated on or before today (the cap is exclusive)."""
    SC = _scout()
    return _cached(("scout", today), lambda: SC.SnapshotIndex.from_db(cap=_next_day(today)))


def _tx_feed(today: str) -> tuple[dict, str]:
    """(league transactions through today's year, the feed's last day on or before today)."""
    import efv_drivers as DRV
    tx = DRV.load_league_transactions(int(today[:4]))
    last = max((d for evs in tx.values() for d, _c, _s in evs if d <= today), default=None)
    return tx, last


def _stint_index(today: str) -> tuple[dict, str | None, dict]:
    """(the IL stint index parsed from the cached transaction feed exactly as
    efv_w2_il_backfill.build_table parses it, the day after the feed's last day, receipt).
    Nothing is written."""
    import efv_w2_il_backfill as IL

    def build():
        _tx, last = _tx_feed(today)
        doc = IL.build_table(out=None, last_year=int(today[:4]))
        idx = IL.index_from_rows(doc["rows"])
        end = _next_day(last) if last else None
        return idx, end, {"n_stints": doc["n_stints"], "feed_last_day": last,
                          "feed_last_month": (doc.get("source") or {}).get("last_month")}
    return _cached(("stints", today), build)


def _nri_index(today: str, season_cap: int):
    """(an NRI index through season_cap with entries known before today + 1 day, the
    seasons whose roster lists are cached)."""
    import efv_w2_nri as NRI

    def build():
        rosters: dict = {}
        have = set()
        for season in range(min(NRI.SEASONS), int(season_cap) + 1):
            files = sorted(NRI.CACHE_DIR.glob(f"nri_{season}_*.json"))
            if files:
                have.add(season)
            for p in files:
                club = int(p.stem.split("_")[2])
                for e in json.loads(p.read_text(encoding="utf-8")).get("roster") or []:
                    pid = (e.get("person") or {}).get("id")
                    if pid:
                        rosters.setdefault(season, {}).setdefault(int(pid), []).append(club)
        tx, _last = _tx_feed(today)
        idx = NRI.NriIndex.build(season_cap=int(season_cap), date_cap=_next_day(today),
                                 rosters=rosters, tx=tx)
        return idx, have
    return _cached(("nri", today, int(season_cap)), build)


def _exclusion_ids(items: list[dict], exclude_ids) -> frozenset:
    """The population fit leaves out every player of the frame it scores (vm_exclusions'
    rule): the live board's ids, both sides, plus every id read here."""
    if exclude_ids is not None:
        return frozenset(int(i) for i in exclude_ids)
    import efv_dataset as D

    def board():
        ids = set()
        for s in F.SIDES:
            p = D.live_matrix_path(s)
            if p.exists():
                ids |= {int(r["mlbam_id"]) for r in json.loads(p.read_text(encoding="utf-8"))
                        if r.get("mlbam_id")}
        return frozenset(ids)
    ids = set(_cached(("board_ids",), board))
    ids |= {int(it["mlbam"]) for it in items if it.get("mlbam")}
    return frozenset(ids)


def _last_season_ended(day: str) -> int:
    """The last season (MiLB or MLB) that had ended by `day` (the 1 October rule)."""
    y, m = int(day[:4]), int(day[5:7])
    return y if m >= 10 else y - 1


def pop_fit_year(read_year: int, cutoff: str) -> int:
    """The population fit year of an as-of read at (read_year, cutoff): the read year,
    lowered until every label window the fit learns from (efv_w2_popmle.train_seasons:
    s + 1 .. s + HORIZON) had closed by the cutoff. A training row reads at its decision
    year with a cutoff inside that year, so its windows closed by 1 January; a history
    snapshot read at min(year, list year) + 1 would otherwise learn from the fWAR season
    still being played on its own date (verifier defect 2026-10-15). The live board
    (read year 2027, cutoff after 1 October 2026) keeps its read year."""
    return min(int(read_year), _last_season_ended(cutoff) + 1)


def _pop_value(tr, side: str, mlbam, read_year: int, cutoff: str) -> tuple:
    """efv_w2_popmle.Translator.value with the population model at pop_fit_year (the MiLB
    read itself stays at (read_year, cutoff)). Raises when a label window the fit learns
    from had not closed by the cutoff."""
    import efv_dataset as D
    import efv_w2_popmle as PM
    from efv_w2_milb import last_readable_season
    fy = pop_fit_year(read_year, cutoff)
    seasons = PM.train_seasons(fy)
    if seasons and max(seasons) + PM.HORIZON > _last_season_ended(cutoff):
        raise F.ReservedFrameError(
            f"population fit {fy}: a label window had not closed by {cutoff}")
    if fy == int(read_year):
        return tr.value(side, LIVE_KIND, mlbam, int(read_year), cutoff, D.MILB_FLOOR_DEFAULT)
    tr.guard(LIVE_KIND, fy)
    if not mlbam:
        return None, None
    mid = int(mlbam)
    top = last_readable_season(int(read_year), cutoff)
    low = max(int(D.MILB_FLOOR_DEFAULT), top - PM.MAX_BACK + 1)
    for s in range(top, low - 1, -1):
        f = PM.player_seasons(s, side).get(mid)
        if f is None or f["exp"] < PM.LINE_MIN[side]:
            continue
        m = tr.model(LIVE_KIND, fy, side)
        if m is None:
            return None, s
        return float(m.predict(np.asarray([PM.vector(f, side)]))[0]), s
    return None, None


def _translator(today: str, ids: frozenset, read_years):
    """efv_w2_popmle.Translator for the live kind: a fit year's population fit uses only
    label windows that closed before today's season (no look-ahead), and its own frame's
    players are left out; each item's fit year is lowered to its own cutoff
    (pop_fit_year). The vm guard (no read year from the R-VM cohort on) guards the
    backtest frames; the live board is not one of them."""
    import efv_w2_popmle as PM

    class _LiveTranslator(PM.Translator):
        def guard(self, kind: str, read_year: int) -> None:
            if kind != LIVE_KIND:
                raise ValueError(kind)
            seasons = PM.train_seasons(int(read_year))
            if seasons and max(seasons) + PM.HORIZON > int(today[:4]) - 1:
                raise F.ReservedFrameError(
                    f"read year {read_year}: a label window had not closed before {today}")
            if int(read_year) > int(today[:4]) + 1:
                raise F.ReservedFrameError(f"read year {read_year} is after {today}")

    key = ("popmle", today, hash(ids))
    tr = _LIVE_CACHE.get(key)
    if tr is None:
        tr = _LiveTranslator({})
        tr.ids = ids
        _LIVE_CACHE[key] = tr
    for ry in read_years:
        tr.excluded.setdefault((LIVE_KIND, int(ry)), ids)
    return tr


def _pooled_asof(items: list[dict], finish) -> dict:
    """{name: {slot: value}} for a family whose value depends on a POOL of rows (a group
    column's centering mean, a tool cell's z norm, a rater percentile), with every item's
    pool made only of the items of its own read season whose cutoff is on or before its
    own: finish(pool) -> {name: {slot: value}} runs once per (read season, cutoff) and each
    item keeps the value of its own cutoff's run.

    The live board (one read season, one cutoff: today) is one pool, exactly the call it
    always was. FV-history snapshots (history_columns) carry many cutoffs: without this a
    snapshot's centering mean, z norm and percentile were taken over snapshots dated after
    it, including the October points that read the newer season (verifier defect
    2026-10-15). Splitting by read season also keeps one season's lines per centering
    group, as one decision year of the training frame reads one season."""
    by_s: dict = {}
    for it in items:
        by_s.setdefault(it["season"], []).append(it)
    out: dict = {}
    for _s, its in sorted(by_s.items()):
        days = sorted({it["cutoff"] for it in its})
        for d in days:
            pool = its if len(days) == 1 else [it for it in its if it["cutoff"] <= d]
            mine = {it["slot"] for it in its if it["cutoff"] == d}
            for n, mp in finish(pool).items():
                dst = out.setdefault(n, {})
                for slot, v in mp.items():
                    if slot in mine:
                        dst[slot] = v
    return out


# -- one function per family: (side, items, names, today) -> ({name: {slot: v}}, note) ----

def _fam_group(side, items, ns, today, **_):
    menu = G.menu_columns()
    seasons = {it["season"] for it in items}
    ln = _asof_lines(side, seasons)
    reads = {(it["group"], it["slot"]): {n: ln.member(it["mlbam"], it["season"], menu[n])
                                         for n in ns} for it in items}
    cnt: dict = {n: {} for n in ns}
    for (y, _sid), r in reads.items():
        for n in ns:
            if r[n][0]:
                cnt[n][y] = cnt[n].get(y, 0) + 1

    def finish(pool):
        keys = [(it["group"], it["slot"]) for it in pool]
        vals, _c = G.centered({k: reads[k] for k in keys}, ns)
        return {n: {k[1]: vals[n].get(k, 0.0) for k in keys} for n in ns}

    vals = _pooled_asof(items, finish)
    out = {n: {it["slot"]: vals[n].get(it["slot"], 0.0) for it in items} for n in ns}
    with_z = {n: sum(1 for r in reads.values() if r[n][0] and r[n][1] is not None) for n in ns}
    in_group = {n: sum(cnt[n].values()) for n in ns}
    dark = [n for n in ns if in_group[n] and not with_z[n]]
    note = {"status": "partial" if dark else "lit", "seasons": sorted(seasons),
            "in_group": in_group, "with_z": with_z}
    if dark:
        note["dark_columns"] = dark
        note["reason"] = ("in-group rows carry no value at the read season: a pitch-call "
                          "metric needs a discipline aggregate for the season "
                          "(.cache/efv4_pbp_discipline); value 0.0 (the in-group mean)")
    return out, note


def _fam_tool(side, items, ns, today, **_):
    seasons = {it["season"] for it in items}
    ln = _asof_lines(side, seasons)
    idx = _scout_index(today)
    reads, sk = {}, {}
    for it in items:
        k = (it["group"], it["slot"])
        sk[k] = it["season"]
        row = {}
        for n in ns:
            spec = TOOL_CELLS[n]
            ing = tool_member(ln, it["mlbam"], it["season"], spec)
            v = tool_value(idx, it["pk"], it["asof"], None, spec["metric"], side) if ing else None
            row[n] = (ing, v)
        reads[k] = row

    def finish(pool):
        keys = [(it["group"], it["slot"]) for it in pool]
        vals, _c = _tool_finish({k: reads[k] for k in keys}, sk, ns)
        return {n: {k[1]: vals[n].get(k, 0.0) for k in keys} for n in ns}

    vals = _pooled_asof(items, finish)
    out = {n: {it["slot"]: vals[n].get(it["slot"], 0.0) for it in items} for n in ns}
    pools: dict = {}
    for k, r in reads.items():
        for n in ns:
            ing, v = r[n]
            if ing:
                p = pools.setdefault(n, {}).setdefault(str(sk[k]), {"in_group": 0, "with_grade": 0})
                p["in_group"] += 1
                p["with_grade"] += int(v is not None)
    thin = sorted({n for n, by in pools.items() for c in by.values()
                   if 0 < c["with_grade"] < G.NORM_MIN_LINES})
    note = {"status": "partial" if thin else "lit", "pools": pools,
            "norm_min_lines": G.NORM_MIN_LINES}
    if thin:
        note["thin_columns"] = thin
        note["reason"] = (f"a (cell, season) pool under {G.NORM_MIN_LINES} graded rows has "
                          "no z norm; its rows read 0.0 (the in-group mean)")
    return out, note


def _fam_il(side, items, ns, today, **_):
    import efv_w2_il_backfill as IL
    cands = candidates()
    idx, end, rc = _stint_index(today)
    out = {n: {} for n in ns}
    for it in items:
        cut = IL.vm_cutoff({"cutoff": it["cutoff"]}, it["read_year"])
        if end is not None:
            cut = min(cut, end)
        p = IL.asof(it["mlbam"], cut, idx)
        for n in ns:
            st = cands[n]["arg"]
            out[n][it["slot"]] = IL.transformed(st, p.get(st))
    return out, dict(rc, status="lit", read_cut_capped_at=end)


def _fam_nri(side, items, ns, today, **_):
    import efv_w2_nri as NRI
    cands = candidates()
    cap = max(it["group"] for it in items) if items else int(today[:4])
    idx, have = _nri_index(today, cap)
    out = {n: {} for n in ns}
    dark_rows = 0
    missing = set()
    for it in items:
        d = it["asof"]
        need = min(int(d[:4]), cap) if d else None
        if need is None or need not in have:
            vals = {s: None for s in NRI.STATS}
            dark_rows += 1
            if need is not None:
                missing.add(need)
        else:
            vals = NRI.nri_values(it["mlbam"], d, idx)
        for n in ns:
            out[n][it["slot"]] = vals.get(cands[n]["arg"])
    note = {"status": "dark" if dark_rows == len(items) else ("partial" if dark_rows else "lit"),
            "roster_seasons_cached": [min(have), max(have)] if have else None,
            "rows_without_roster_season": dark_rows}
    if missing:
        note["reason"] = (f"no non-roster invitee list cached for spring {sorted(missing)} "
                          "(.cache/efv4_nri; efv_w2_nri.fetch(seasons=...)): an undercount "
                          "is never served, so those rows read None")
    return out, note


def _fam_pbp(side, items, ns, today, **_):
    import efv_w2_pbp as P
    cands = candidates()
    out = {n: {} for n in ns}
    kept = 0
    wanted = set()
    for it in items:
        p = P.profile(it["mlbam"], it["read_year"], it["cutoff"], side)
        keep = P.has_all(p, side)
        kept += int(keep)
        wanted |= set(P.read_seasons(it["read_year"], it["cutoff"]))
        for n in ns:
            out[n][it["slot"]] = p.get(cands[n]["arg"]) if keep else None
    note = {"status": "dark" if not kept else "lit", "rows_with_all_columns": kept,
            "agg_seasons_last": max(P.AGG_SEASONS), "seasons_wanted": sorted(wanted)}
    if not kept:
        note["reason"] = (f"no complete pitch-event pool for the seasons read "
                          f"{sorted(wanted)}: efv_w2_pbp.AGG_SEASONS ends "
                          f"{max(P.AGG_SEASONS)} and no aggregate exists past it")
    return out, note


def _fam_pbp_bb(side, items, ns, today, **_):
    import efv_dataset as D
    import efv_w2_pbp_bb as PB
    cands = candidates()
    out = {n: {} for n in ns}
    read: dict = {}
    for it in items:
        top = PB.last_readable_season(it["read_year"], it["cutoff"])
        p = PB.profile(it["mlbam"], it["read_year"], it["cutoff"], side, D.MILB_FLOOR_DEFAULT,
                       season_cap=top)
        key = ",".join(str(s) for s in p.get("_seasons") or []) or "none"
        read[key] = read.get(key, 0) + 1
        for n in ns:
            out[n][it["slot"]] = p.get(cands[n]["arg"])
    pools = sorted({s for (_sp, s) in PB.pools()})
    return out, {"status": "lit", "pool_seasons_last": pools[-1] if pools else None,
                 "seasons_read": dict(sorted(read.items(), key=lambda kv: -kv[1])[:6])}


def _fam_popmle(side, items, ns, today, exclude_ids=None, **_):
    ids = _exclusion_ids(items, exclude_ids)
    fys = sorted({pop_fit_year(it["read_year"], it["cutoff"]) for it in items})
    tr = _translator(today, ids, fys)
    vals = {}
    for it in items:
        v, _s = _pop_value(tr, side, it["mlbam"], it["read_year"], it["cutoff"])
        vals[it["slot"]] = v
    out = {n: dict(vals) for n in ns}
    rec = {k: v for k, v in tr.receipts.items() if k.endswith(f"|{side}")}
    return out, {"status": "lit", "fits": rec, "excluded_ids": len(ids), "fit_years": fys,
                 "owner_note": ("the live fit learns from population seasons whose six-season "
                                "fWAR windows closed before today's season (through 2025 "
                                "fWAR), labels the backtest's vm guard kept away from "
                                "development reads; nothing after today is read")}


class _MemoPanel:
    """A rater panel whose value(pk, asof) is computed once per pair (the pooled reads
    call it once per pool)."""

    def __init__(self, panel):
        self.panel = panel
        self.lists = panel.lists
        self._memo: dict = {}

    def value(self, pk, asof):
        k = (pk, asof)
        if k not in self._memo:
            self._memo[k] = self.panel.value(pk, asof)
        return self._memo[k]


def _fam_raters(side, items, ns, today, **_):
    import efv_rater_panel as RP
    import efv_w2_raters as RW
    panel = _cached(("raters",), lambda: RW.Panel.from_doc(RP.load_panel(RW.PANEL_PATH)))
    memo = _MemoPanel(panel)

    def finish(pool):
        g, _info = RW.resid_column([(it["slot"], it["pk"], it["asof"], it["fv"],
                                     (side, it["group"], LIVE_KIND)) for it in pool], memo)
        return {"_": g}

    got = _pooled_asof(items, finish).get("_", {})
    got = {it["slot"]: got.get(it["slot"]) for it in items}
    n_val = sum(1 for v in got.values() if v is not None)
    years = sorted({y for (_r, y) in panel.lists})
    note = {"status": "lit" if n_val else "dark", "with_value": n_val,
            "list_years": [years[0], years[-1]] if years else None}
    if not n_val:
        note["reason"] = ("the rater panel carries no list of the read's own year "
                          f"(list years {note['list_years']}); every row reads None, as every "
                          "training row read after the panel's last year did")
    return {n: dict(got) for n in ns}, note


def _fam_report(side, items, ns, today, **_):
    # The production construction: production_columns hands the report builder an empty
    # list-vintage frame (frames_lv), so store.lv returns nothing and every training value
    # is None; the fitted slopes are 0.0. Reading real report values here would be a
    # different construction from the fit and would still multiply a zero slope.
    return ({n: {it["slot"]: None for it in items} for n in ns},
            {"status": "dark", "reason": ("None by construction: every production training "
                                          "value was None (empty list-vintage frame in "
                                          "production_columns) and the fitted slopes are 0.0")})


def _fam_w2s(side, items, ns, today, **_):
    SC = _scout()
    idx = _scout_index(today)
    slots = [(it["slot"], it["pk"], it["asof"]) for it in items]
    out = {}
    for n in ns:
        got = SC.values_for(slots, V3.W2_COLUMNS[n]["arg"], idx)
        out[n] = {k: (None if v is None else float(v)) for k, v in got.items()}
    return out, {"status": "lit", "snapshot_cap": _next_day(today)}


_FAMILIES = {"group": _fam_group, "tool": _fam_tool, "il": _fam_il, "nri": _fam_nri,
             "pbp": _fam_pbp, "pbp_bb": _fam_pbp_bb, "popmle": _fam_popmle,
             "raters": _fam_raters, "report": _fam_report, "w2s": _fam_w2s}


def _family_of(name: str) -> str:
    c = candidates()[name]
    return c["family"] if c["source"] == "v4" else c["source"]


def asof_columns(side: str, items: list[dict], *, today: str, names=None, exclude_ids=None,
                 log=print) -> tuple[dict, dict]:
    """({name: {slot: value | None}}, receipt) for every candidate column of the side on
    as-of read items (see _item). Raises when any read reaches past `today`."""
    t = _day(today)
    names = side_candidates(side) if names is None else list(names)
    for it in items:
        if it["cutoff"] > t or (it["asof"] is not None and it["asof"] > t):
            raise F.ReservedFrameError(f"{it['pk']}: a read after {t}")
        if not _season_ended(it["season"], t):
            raise F.ReservedFrameError(f"{it['pk']}: season {it['season']} had not ended by {t}")
    by_fam: dict = {}
    for n in names:
        by_fam.setdefault(_family_of(n), []).append(n)
    cols, fams = {}, {}
    for fam, ns in by_fam.items():
        t0 = time.time()
        got, note = _FAMILIES[fam](side, items, ns, t, exclude_ids=exclude_ids)
        cols.update(got)
        fams[fam] = dict(note, columns=len(ns), seconds=round(time.time() - t0, 1))
        log(f"  live {side} {fam}: {len(ns)} columns, {note.get('status')} "
            f"({fams[fam]['seconds']} s)")
    missing = [n for n in names if n not in cols]
    if missing:
        raise RuntimeError(f"{side}: candidate columns not built live: {missing}")
    cov = {n: {"rows": len(cols[n]),
               "with_value": sum(1 for v in cols[n].values() if v is not None),
               "nonzero": sum(1 for v in cols[n].values() if v not in (None, 0.0))}
           for n in names}
    return cols, {"today": t, "rows": len(items), "families": fams, "coverage": cov}


def live_columns(side: str, rows: list[dict], *, today: str | None = None,
                 raw_by_key: dict | None = None, exclude_ids=None, receipt: dict | None = None,
                 clip: bool = True, log=print) -> dict:
    """{name: {(list year, player_key, 'live'): value | None}} for every candidate column of
    the side on live board rows (efv_v2_serve.live_rows), read as of today with the
    construction, units and standardization basis of production_columns (the read rule
    above). raw_by_key maps player_key to its live matrix row (its consensus as-of date).
    Pass every gradeable row of the side in one call: a group column is centered over the
    call's in-group rows, as a training column is over its decision year's. With `clip`
    (the served default) every value is then held to the production training support
    (support_clip); clip=False gives the raw construction. Memoized per (side, today,
    rows, clip); `receipt`, when a dict, receives the coverage receipt."""
    rd = live_read(today)
    t = rd["today"]
    key = (side, t, tuple(sorted(r["player_key"] for r in rows)), bool(clip))
    hit = _LIVE_MEMO.get(key)
    if hit is None:
        items = []
        for r in rows:
            if int(r["decision_year"]) != rd["group_year"]:
                raise ValueError(f"{r['player_key']}: decision year {r['decision_year']} is "
                                 f"not the live list year {rd['group_year']}")
            raw = (raw_by_key or {}).get(r["player_key"]) or {}
            a = _day(raw.get("asof_date")) or t
            items.append(_item((rd["group_year"], r["player_key"], LIVE_KIND), r["player_key"],
                               r.get("mlbam_id") or raw.get("mlbam_id"), rd["group_year"],
                               rd["read_year"], t, min(a, t), r.get("fv")))
        cols, rec = asof_columns(side, items, today=t, exclude_ids=exclude_ids, log=log)
        if clip:
            cols = support_clip(side, cols, rec, log=log)
        rec["read"] = rd
        hit = (cols, rec)
        _LIVE_MEMO[key] = hit
        _LIVE_RECEIPTS[side] = rec
    if receipt is not None:
        receipt.update(hit[1])
    return hit[0]


def live_receipt(side: str) -> dict | None:
    """The coverage receipt of the side's last live_columns build (None before one)."""
    return _LIVE_RECEIPTS.get(side)


def history_columns(side: str, points: list[tuple], *, today: str | None = None,
                    exclude_ids=None, clip: bool = True, log=print) -> tuple[dict, dict]:
    """({name: {(player_key, snapshot date): value | None}}, receipt) for FV-history
    snapshots [(player_key, mlbam_id, snapshot date, consensus fv)], each read as of its own
    date: read year min(snapshot year, list year) + 1 and cutoff the snapshot date (the
    efv_score history MiLB read), the population fit at pop_fit_year, and every pooled
    value (centering mean, tool z norm, rater percentile) taken over the snapshots of the
    same read season dated on or before it (_pooled_asof). Snapshots dated after today are
    skipped. With `clip` the values are held to the training support (support_clip)."""
    rd = live_read(today)
    Y = rd["group_year"]
    items = []
    for pk, mid, d, fv in points:
        d = _day(d)
        if d is None or d > rd["today"]:
            continue
        yr = int(d[:4])
        items.append(_item((pk, d), pk, mid, yr, min(yr, Y) + int(LIVE_READ_YEAR_OFFSET), d, d, fv))
    cols, rec = asof_columns(side, items, today=rd["today"], exclude_ids=exclude_ids, log=log)
    if clip:
        cols = support_clip(side, cols, rec, log=log)
    return cols, rec


# ---------------------------------------------------------------------------
# the training support: a served candidate value never leaves what the fit saw
# ---------------------------------------------------------------------------
#
# THE DEFECT THIS CLOSES (verifier, 2026-10-15). The live construction equals the training
# construction, but the populations it runs on differ, and a linear head extrapolates:
#   - a tool cell's z exists only for a (cell, season) pool of NORM_MIN_LINES graded rows.
#     Training pools split by read season almost never reached it (High-A slider gap:
#     one 2019 pool of 33, 98% of training values 0.0), while the live 2026 pool has 127,
#     so the live column is nonzero on 13% of rows and reached 36 training SDs (one
#     pitcher moved 93 percentile points);
#   - the injured list counts drift by era (the post-2021 minor league IL): 60-day stints
#     were 0 or 1 on every training hitter and reach 5 live.
# The served guard, per candidate key, against the production training rows' own values:
#   1. CLIP every value into the training [min, max]: a served value is never one the fit
#      did not see, so its head z never passes the training max |z|.
#   2. WITHHOLD (None: the head's training mean, z = 0) a column whose nonzero training
#      values come from fewer than SUPPORT_MIN_YEARS decision years: its slope rests on one
#      or two pools, and a board that lights it is a regime the backtest never scored.
#      Only the High-A slider gap cells fall under it on 2026-10-15 (33 nonzero training
#      rows, all of the 2019 pool, and 0 and 0); a column lit across many years with a
#      small share (60-day IL stints, 67 hitter rows) is clipped and its drift reported.
#   3. REPORT drift: a key whose served nonzero share passes DRIFT_RATIO times its training
#      share (and by DRIFT_MIN_GAP) is named in the receipt and its family's status says
#      "drift" (the IL family on both sides on 2026-10-15).
# Nothing here touches a training number: the support is read off production_train.

#: A column whose nonzero production training values come from fewer decision years than
#: this is withheld when served.
SUPPORT_MIN_YEARS = 3
#: Drift report thresholds (served nonzero share against the training share).
DRIFT_RATIO = 2.0
DRIFT_MIN_GAP = 0.05
_SUPPORT: dict = {}


def training_support(side: str, *, log=print) -> dict:
    """{candidate key: {"n", "nonzero", "nonzero_share", "nonzero_years", "min", "max"}}
    over the production training rows' non-None values of the side (memoized per
    process); nonzero_years counts the decision years with a nonzero value; min and max
    are None for a key with no training value."""
    if side in _SUPPORT:
        return _SUPPORT[side]
    train = production_train(side, log=log)
    cands = candidates()
    out = {}
    for n in side_candidates(side):
        k = cands[n]["key"]
        have = [r for r in train if r["v2"].get(k) is not None]
        vals = np.asarray([r["v2"][k] for r in have], dtype=np.float64)
        nz = int(np.count_nonzero(vals))
        yrs = {int(r["decision_year"]) for r in have if float(r["v2"][k]) != 0.0}
        out[k] = {"n": int(vals.size), "nonzero": nz,
                  "nonzero_share": round(nz / vals.size, 4) if vals.size else 0.0,
                  "nonzero_years": len(yrs),
                  "min": float(vals.min()) if vals.size else None,
                  "max": float(vals.max()) if vals.size else None}
    _SUPPORT[side] = out
    return out


def support_clip(side: str, cols: dict, receipt: dict | None = None, *, log=print) -> dict:
    """cols ({name: {slot: value | None}}) held to the production training support (the
    block above): clipped into the training [min, max], withheld (None) where the training
    column's nonzero values span fewer than SUPPORT_MIN_YEARS decision years, drift named. `receipt`, when a
    dict, takes {"support": {key: ...}} and each drifting family's status."""
    sup = training_support(side, log=log)
    cands = candidates()
    out, rep = {}, {}
    drift_fams: dict = {}
    for n, mp in cols.items():
        k = cands[n]["key"]
        s = sup.get(k) or {"n": 0, "nonzero": 0, "nonzero_share": 0.0, "nonzero_years": 0,
                           "min": None, "max": None}
        vals = [v for v in mp.values() if v is not None]
        nz = sum(1 for v in vals if v != 0.0)
        share = round(nz / len(vals), 4) if vals else 0.0
        r = {"train_nonzero_rows": s["nonzero"], "train_nonzero_share": s["nonzero_share"],
             "train_nonzero_years": s["nonzero_years"], "served_nonzero_share": share,
             "clipped_low": 0, "clipped_high": 0, "withheld": False}
        if vals and s["nonzero_years"] < SUPPORT_MIN_YEARS and (nz or s["min"] is None):
            out[n] = {slot: None for slot in mp}
            r["withheld"] = True
            r["reason"] = (f"{s['nonzero']} nonzero training rows from {s['nonzero_years']} "
                           f"decision years (under {SUPPORT_MIN_YEARS}): the slope never "
                           "saw this column lit on a board")
        else:
            lo, hi = s["min"], s["max"]
            got = {}
            for slot, v in mp.items():
                if v is not None and lo is not None:
                    if v < lo:
                        v = lo
                        r["clipped_low"] += 1
                    elif v > hi:
                        v = hi
                        r["clipped_high"] += 1
                got[slot] = v
            out[n] = got
            if (vals and share > DRIFT_RATIO * s["nonzero_share"]
                    and share - s["nonzero_share"] > DRIFT_MIN_GAP):
                r["drift"] = True
                drift_fams.setdefault(_family_of(n), []).append(k)
        rep[k] = r
    if receipt is not None:
        receipt["support"] = rep
        fams = receipt.get("families") or {}
        for fam, ks in drift_fams.items():
            note = fams.get(fam)
            if note is None:
                continue
            note["drift"] = sorted(ks)
            if note.get("status") == "lit":
                note["status"] = "drift"
                note["reason"] = ("served nonzero share above "
                                  f"{DRIFT_RATIO:g}x the training share for {sorted(ks)}; "
                                  "values clipped to the training range")
        receipt["withheld"] = sorted(k for k, r in rep.items() if r["withheld"])
        receipt["clipped"] = sum(r["clipped_low"] + r["clipped_high"] for r in rep.values())
    return out


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

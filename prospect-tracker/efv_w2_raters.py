# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4: the historical rater panel as one lab column (EFV4_RATER_PANEL; owner EW2-10,
2026-10-08; registration docs/efv-v2/EFV4_RATER_PANEL.md).

WHAT THIS IS. On list vintages 2011 to 2016 the served consensus carries one real source
per row (MLB Pipeline; FanGraphs joins in 2017). Raters outside it published dated
preseason lists every year: Baseball Prospectus (Top 101, 2011 to 2020 public; 2021 is
paywalled) and FanGraphs (top 100 2011 to 2014, top 200 in 2015). efv_rater_panel.py
parses those lists and resolves each entry to a player_key without reading any outcome;
this module turns the panel into ONE column offered to the V2 skill head of each side,
and reads it on the development frames and, under EW2-10, on the spent reserved frames.

THE COLUMN (registered). For a row read at as-of date d (player p, side s, group g):
    each rater r with a list of year d.year published on or before d contributes
        implied_fv(rank)  if r listed p (consensus.implied_fv_from_rank, the repo's map)
        floor_r           if r did not (LIST FLOOR, below)
    panel_fv   = the mean over the contributing raters (None when no rater has such a
                 list: a row with no panel is imputed at the training mean by the fit,
                 as every sidecar column is; no absence flag enters any head)
    rater_panel_resid = within-g percentile of panel_fv minus within-g percentile of
                 the consensus FV (u_c), over the group's rows that carry both.
g is (side, list vintage V) on the list-vintage frames, every frame row of the vintage
with a consensus, and (side, decision year, train or test) on the vintage-matched frames.

DEFAULTS (named; the owner may choose otherwise):
    LIST FLOOR      an unlisted player takes the map's band one step below the band of
                    the list's last rank (a 100 or 101 list: 45; the 2015 FanGraphs 142
                    list: 40), so an unlisted player never ties a listed one.
    PANEL MEAN      every contributing rater counts once (unlisted at its floor), the
                    reliability arithmetic of the registration.
    AS OF           a rater's list counts only for reads in its own year and on or after
                    its publication day; lists are kept only when published inside
                    [V-01-01, V-05-01) (efv_rater_panel.in_window). An lv frame row reads
                    on the last day of its own window (lv_read_day: V-04-30, or the day
                    before a debut inside the window); a vm row reads at its own as-of
                    date (the matrix cutoff for a training row, the pinned preseason
                    read for a test row).
    ARMS            the column on hitters, on pitchers, and on both sides together, each
                    under V2's own DS-06 admission inside every fold (efv_v3.fit_v3 at the
                    base configuration plus the column, which is fit_v2 plus the column).

THE READS. Development (EW2-10 choice frames): lv_dev (list vintages 2017 to 2019 scored,
training on 2011 onward, W3 on the frozen fWAR label) and vm_dev (vm2, debut years 2017
to 2023), through tools/efv_v3_backtest.build_dev, whose V2 base reproduces the DS-16
block bit for bit before anything is read. Spent (EW2-10: R-LV list vintages 2020 and
2021 and R-VM 2025 were read once on 2026-10-08 and are spent): the same arms through
tools/efv_v3_backtest.build_reserved on the committed gate sha, labelled "spent frame,
read after the 10-08 confirmation", choosing and tuning nothing and written to the
artifact only (no progress-ledger row: a reserved-frame ledger row is charted).
Statistics: within (side, vintage) Spearman, pooled Spearman and contributor AUC deltas
against the V2 base and against PROSPX consensus, paired and player-clustered E_cond
CI95 (efv_v2_stat.paired_delta, B 2000); a zero-information twin (the column permuted
within year); and on lv_dev the DS-03 balance probe of panel_absent on the rows the
Pipeline lists.

NOTHING SERVED MOVES. This module is a lab: consensus.py, SCORED_SOURCES, the displayed
PROSPX consensus FV and every served eFV grade are untouched; the column joins
efv_v3.W2_COLUMNS only inside this module's own process (register_runtime) and is
removed again when the read ends. GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md):
strata are side, vintage and frame only; nothing is grouped, counted or averaged by
consensus-FV level (test-pinned source scan).

Run:  python efv_w2_raters.py --panel                 (parse and resolve the lists)
      python efv_w2_raters.py --dev                   (development read; artifact and
                                                       this module's own ledger rows)
      python efv_w2_raters.py --spent --gate-sha SHA  (spent-frame read; artifact only)
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import consensus as CN  # noqa: E402
import efv_rater_panel as RP  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

MODULE = "efv_w2_raters"
TOOL = "efv_w2_raters.py"
ITEM = "EFV4_RATER_PANEL"
OUT_PATH = ROOT / "data" / "_labs" / "efv_w2" / "efv_w2_raters.json"
PANEL_PATH = RP.OUT_PATH
PRIVATE_LEDGER = ROOT / ".cache" / "efv4_raters" / "progress_ledger.jsonl"
MODEL_PREFIX = "efv_w2_raters:wave4"
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
DEV_FRAMES = ("lv_dev", "vm_dev")
SPENT_FRAMES = ("lv_res", "vm_pros")
FRAME_KIND = {"lv_dev": "lv", "vm_dev": "vm", "lv_res": "lv", "vm_pros": "vm"}
SPENT_LABEL = "spent frame, read after the 10-08 confirmation"
NOTE = "eFV v4 rater-panel arm; development frame, spent, selects nothing, not a claim"
VERDICT = ("development only: eFV v4 rater-panel arm (EW2-10); chooses on the development "
           "frames only and adjudicates nothing")
#: The map's steps, high to low (consensus.implied_fv_from_rank).
MAP_STEPS: tuple[float, ...] = (70.0, 60.0, 55.0, 50.0, 45.0, 40.0)
COLUMN_NAMES = {"hit": "w2r_panel_hit", "pit": "w2r_panel_pit"}
ARMS: tuple[dict, ...] = (
    {"name": "w2r_panel_hit", "sides": ("hit",), "head": "skill", "kind": "column",
     "what": "rater_panel_resid offered to the hitter skill head"},
    {"name": "w2r_panel_pit", "sides": ("pit",), "head": "skill", "kind": "column",
     "what": "rater_panel_resid offered to the pitcher skill head"},
    {"name": "w2r_panel_both", "sides": ("hit", "pit"), "head": "skill", "kind": "column_set",
     "what": "rater_panel_resid offered to the skill head of both sides (pooled read)"},
)


def column_key(side: str) -> str:
    return f"{H.V2_SCREEN_PREFIX}{COLUMN_NAMES[side]}"


# ---------------------------------------------------------------------------
# the panel's value for one read
# ---------------------------------------------------------------------------

def list_floor(last_rank: int) -> float:
    """The band one step below the band of the list's last rank."""
    v = float(CN.implied_fv_from_rank(int(last_rank)))
    lower = [b for b in MAP_STEPS if b < v]
    return lower[0] if lower else MAP_STEPS[-1]


class Panel:
    """Per rater, per list year: publication day, {player_key: rank}, floor."""

    def __init__(self, lists: dict):
        self.lists = lists          # {(rater, year): {"published", "ranks", "floor"}}

    @classmethod
    def from_doc(cls, doc: dict, *, allow_reserved: bool = False) -> "Panel":
        out = {}
        for lid, blk in (doc.get("lists") or {}).items():
            y = int(blk["year"])
            if y in F.RESERVED_LV and not allow_reserved:
                continue
            ranks: dict = {}
            for e in blk["entries"]:
                pk = e.get("player_key")
                if pk and (pk not in ranks or e["rank"] < ranks[pk]):
                    ranks[pk] = int(e["rank"])
            out[(blk["rater"], y)] = {"published": blk["published"], "ranks": ranks,
                                      "floor": list_floor(int(blk["last_rank"])),
                                      "list": lid}
        return cls(out)

    def raters(self) -> list[str]:
        return sorted({r for r, _y in self.lists})

    def value(self, player_key: str, asof: str | None) -> tuple[float | None, int, int]:
        """(panel_fv or None, raters contributing, raters listing the player)."""
        if not asof:
            return None, 0, 0
        d = str(asof)[:10]
        y = int(d[:4])
        vals, listed = [], 0
        for (rater, ly), blk in self.lists.items():
            if ly != y or blk["published"] > d:
                continue
            rk = blk["ranks"].get(player_key)
            if rk is not None:
                listed += 1
                vals.append(float(CN.implied_fv_from_rank(rk)))
            else:
                vals.append(float(blk["floor"]))
        if not vals:
            return None, 0, 0
        return float(sum(vals) / len(vals)), len(vals), listed


def resid_column(items, panel: Panel) -> tuple[dict, dict]:
    """items: [(slot, player_key, asof, consensus_fv, group)]. Returns ({slot: resid or
    None}, {slot: {"panel_fv", "n_raters", "n_listed"}}). The percentiles are taken
    within each group over the rows that carry both a panel value and a consensus."""
    vals: dict = {}
    info: dict = {}
    by_g: dict = {}
    for slot, pk, asof, cons, g in items:
        pv, n, nl = panel.value(pk, asof)
        info[slot] = {"panel_fv": pv, "n_raters": n, "n_listed": nl}
        vals[slot] = None
        if pv is None or cons is None:
            continue
        by_g.setdefault(g, []).append((slot, pv, float(cons)))
    for g, rows in by_g.items():
        pp = H.within_pct([r[1] for r in rows], [0] * len(rows))
        pc = H.within_pct([r[2] for r in rows], [0] * len(rows))
        for (slot, _pv, _c), a, b in zip(rows, pp, pc):
            vals[slot] = float(a - b)
    return vals, info


# ---------------------------------------------------------------------------
# column values on the v3 backtest Inputs frames
# ---------------------------------------------------------------------------

def lv_read_day(row: dict, V: int) -> str | None:
    """The last day a list may carry for an lv frame row: the day before the row's own
    window end (efv_vintage_frame.window_bounds: V-05-01, or the debut day when that is
    earlier), so a list counts when it was published inside the row's preseason window.
    The frame row's asof_date (its latest consensus point, often the January Pipeline
    board) is NOT the bound: the lists of the window are the frame's information set."""
    win = row.get("window") or []
    hi = win[1] if len(win) > 1 and win[1] else f"{int(V)}{RP.WINDOW_END_MMDD}"
    try:
        d = date.fromisoformat(str(hi)[:10]) - timedelta(days=1)
    except ValueError:
        return None
    if d.year != int(V):
        return None
    return d.isoformat()


def lv_values(side: str, by_v: dict, slots_by_v: dict, panel: Panel, *,
              gate_sha: str | None = None) -> tuple[dict, dict]:
    """{(V, pk, kind): resid} for the slots of an lv frame. by_v: {V: (frame rows,
    labels)} (frame rows carry window and grades); slots_by_v: {V: {(V, pk, kind)}}.
    A row reads the lists published inside its own window (lv_read_day).
    The percentile group is (side, V) over every frame row of V with a consensus."""
    import source_backtest as SB
    vals, info = {}, {}
    for V, (rows, _labs) in sorted(by_v.items()):
        F.guard_score_request(int(V), gate_sha=gate_sha, purpose="rater panel column")
        items = []
        for r in rows:
            c = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
            items.append(((int(V), r["player_key"]), r["player_key"], lv_read_day(r, V),
                          None if c is None else float(c), (side, int(V))))
        v, inf = resid_column(items, panel)
        for slot in slots_by_v.get(int(V), ()):
            vals[slot] = v.get((int(V), slot[1]))
            info[slot] = inf.get((int(V), slot[1]))
    return vals, info


def vm_values(side: str, blocks: dict, asof: dict, panel: Panel) -> tuple[dict, dict]:
    """{(decision year, pk, kind): resid} over the train and test rows of every fold
    block; the group is (side, decision year, kind) over the distinct rows."""
    seen: dict = {}
    for _fold, blk in blocks.items():
        for kind in ("train", "test"):
            for r in blk[kind]:
                slot = (int(r["decision_year"]), r["player_key"], kind)
                if slot not in seen:
                    seen[slot] = (slot, r["player_key"], asof[kind].get(r["player_key"]),
                                  None if r.get("fv") is None else float(r["fv"]),
                                  (side, int(r["decision_year"]), kind))
    return resid_column(list(seen.values()), panel)


def lv_slots(blocks: dict) -> dict:
    out: dict = {}
    for _fold, blk in blocks.items():
        for kind in ("train", "test"):
            for r in blk[kind]:
                y = int(r["decision_year"])
                out.setdefault(y, set()).add((y, r["player_key"], kind))
    return out


def vm_asof(side: str) -> dict:
    """{"train": {pk: matrix as-of}, "test": {pk: pinned preseason read}} (the
    efv_v3_backtest.w2_values_dev reading)."""
    raw = json.loads(H._matrix_path(side).read_text(encoding="utf-8"))
    mine: dict = {}
    H.pinned_inputs(side, H.matrix_training_rows(side), mine)
    return {"train": {r["player_key"]: r.get("asof_date") for r in raw},
            "test": {pk: rec.get("asof_date") for pk, rec in mine.items()}}


def coverage(info: dict, vals: dict) -> dict:
    """By (year, kind): slots, rows with a panel value, rows listed by at least one
    rater, rows carrying the column."""
    out: dict = {}
    for slot, inf in info.items():
        key = f"{slot[0]}|{slot[2]}" if len(slot) > 2 else str(slot[0])
        c = out.setdefault(key, {"slots": 0, "with_panel": 0, "listed": 0, "column": 0})
        c["slots"] += 1
        inf = inf or {}
        c["with_panel"] += int(inf.get("panel_fv") is not None)
        c["listed"] += int((inf.get("n_listed") or 0) > 0)
        c["column"] += int(vals.get(slot) is not None)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# runtime registration in efv_v3.W2_COLUMNS (this process only)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def register_runtime():
    """The two columns join efv_v3.W2_COLUMNS for the duration of a read, so the v3
    machinery (validate_config, attach_columns, fit_v3) carries them; removed after."""
    import efv_v3 as V3
    added = []
    for side, name in COLUMN_NAMES.items():
        if name not in V3.W2_COLUMNS:
            V3.W2_COLUMNS[name] = {"side": side, "head": "skill", "module": MODULE,
                                   "arg": "rater_panel_resid", "key": column_key(side)}
            added.append(name)
    try:
        yield
    finally:
        for name in added:
            V3.W2_COLUMNS.pop(name, None)


def arm_config(arm: dict) -> dict:
    import efv_v3 as V3
    cfg = V3.base_config()
    for s in arm["sides"]:
        cfg["add"][s]["skill"].append(COLUMN_NAMES[s])
    return V3.validate_config(cfg)


# ---------------------------------------------------------------------------
# statistics (the DS-16 frame block of efv_w2_scout)
# ---------------------------------------------------------------------------

def frame_cols(inp, fid: str, orders: dict, sides) -> tuple:
    import efv_v3_backtest as BT
    keys, groups, y, pos, a, b, cons, grades = [], [], [], [], [], [], [], []
    for c in inp.scored(fid, sides=sides):
        keys.append(c["key"])
        groups.append(c["group"])
        y.append(float(c["outcome"]["war"]))
        pos.append(bool(c["outcome"]["contributor"]))
        a.append(float(orders[(c["side"], int(c["year"]), c["key"])]))
        b.append(float(c["grades"][BT.V2_KEY]))
        cons.append(float(c["grades"][BT.CONS]))
        grades.append({k: v for k, v in c["grades"].items() if k in BT.SOURCES})
    return keys, groups, y, pos, a, b, cons, grades


def fold_receipts(rec: dict, arm: dict) -> dict:
    out = {}
    for fk, r in rec.items():
        side = fk.split("|")[0]
        key = column_key(side)
        sk = list(r.get("skill_keys") or [])
        out[fk] = {"any_admitted": key in sk, "admitted": {key: key in sk}, "skill_keys": sk,
                   "w_skill": r.get("w_skill"), "consensus_only": r.get("consensus_only"),
                   "n_train": r.get("n_train"), "n_scored": r.get("n_scored")}
    return out


def permuted(values: dict, seed: int) -> dict:
    """The column permuted within its slot year and kind (the zero-information twin)."""
    rng = np.random.default_rng(seed)
    by: dict = {}
    for slot, v in values.items():
        by.setdefault((int(slot[0]), slot[2] if len(slot) > 2 else ""), []).append((slot, v))
    out = {}
    for g in sorted(by):
        items = sorted(by[g], key=lambda kv: tuple(str(x) for x in kv[0]))
        vals = [v for _s, v in items]
        perm = rng.permutation(len(vals))
        for (slot, _v), j in zip(items, perm):
            out[slot] = vals[int(j)]
    return out


def _seed_for(name: str) -> int:
    h = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
    return int((SEED + h) % (2 ** 31 - 1))


def read_arm(inp, fid: str, arm: dict, *, B: int, twin_cols: dict | None = None) -> dict:
    """One arm on one frame: the frame block, the fold receipts, the twin's point."""
    import efv_w2_scout as SC
    cfg = arm_config(arm)
    sides = tuple(arm["sides"])
    orders, rec = inp.orders(fid, cfg, sides=sides)
    cols = frame_cols(inp, fid, orders, sides)
    folds = fold_receipts(rec, arm)
    years = sorted({int(k.split("|")[1]) for k in rec})
    blk = SC.frame_block(cols, B=B, frame_id="lv_dev" if FRAME_KIND[fid] == "lv" else "vm_dev",
                         window=[min(years), max(years)], folds=folds,
                         n_by_side={s: sum(1 for g in cols[1] if g.startswith(s + "|"))
                                    for s in sides})
    blk["frame_version"] = "lv1_v2" if FRAME_KIND[fid] == "lv" else "vm2"
    blk["fold_deltas_note"] = "candidate minus V2 base within each (side, vintage) group"
    if twin_cols is not None:
        saved = inp.cols
        inp.cols = twin_cols
        inp._cache.clear()
        try:
            t_orders, t_rec = inp.orders(fid, cfg, sides=sides)
            t_cols = frame_cols(inp, fid, t_orders, sides)
            blk["twin"] = {"within": SC._within_point(t_cols),
                           "admitted_folds": sum(1 for f in fold_receipts(t_rec, arm).values()
                                                 if f["any_admitted"]),
                           "what": "the column permuted within year and kind"}
        finally:
            inp.cols = saved
            inp._cache.clear()
    return blk


def twin_of(cols: dict, fid: str) -> dict:
    out = {f: {s: dict(v) for s, v in by.items()} for f, by in cols.items()}
    for s, by in (cols.get(fid) or {}).items():
        for name, vals in by.items():
            out[fid][s][name] = permuted(vals, _seed_for(f"twin:{fid}:{name}"))
    return out


# ---------------------------------------------------------------------------
# the DS-03 balance probe of panel_absent
# ---------------------------------------------------------------------------

class _ProbeFrame:
    def __init__(self, train: dict):
        self.train = train


def balance(inp, info_lv: dict) -> dict:
    """panel_absent (no panel rater listed the player) on the lv_dev training rows of
    the last fold that the Pipeline lists, through efv_screen_lab.balance_probe."""
    import efv_screen_lab as LAB
    out = {}
    for side in F.SIDES:
        blocks = inp.frames["lv_dev"]["by_side"][side]
        last = blocks[max(blocks)]
        rows = [r for r in last["train"] if r.get("target") is not None
                and ((r.get("grades") or {}).get("mlb_pipeline") is not None
                     or "grades" not in r)]
        ind = {}
        for r in rows:
            slot = (int(r["decision_year"]), r["player_key"], "train")
            inf = (info_lv.get(side) or {}).get(slot) or {}
            if inf.get("panel_fv") is None:
                continue
            ind[(int(r["decision_year"]), r["player_key"])] = (
                1.0 if (inf.get("n_listed") or 0) == 0 else 0.0)
        rows = [r for r in rows if (int(r["decision_year"]), r["player_key"]) in ind]
        res = LAB.balance_probe(_ProbeFrame({side: rows}), side, ind,
                                seed=_seed_for(f"balance:{side}"))
        res["rows"] = "lv_dev training rows of the last fold listed by MLB Pipeline"
        res["indicator"] = "panel_absent (no panel rater listed the player)"
        res["grades_on_rows"] = any("grades" in r for r in last["train"][:5])
        out[side] = res
    return out


# ---------------------------------------------------------------------------
# builders patched into the v3 backtest for this process
# ---------------------------------------------------------------------------

def dev_columns(inputs: dict, frames_lv: dict, panel: Panel, *, log=print) -> tuple[dict, dict]:
    cols = {fid: {s: {} for s in F.SIDES} for fid in DEV_FRAMES}
    infos = {fid: {} for fid in DEV_FRAMES}
    for side in F.SIDES:
        name = COLUMN_NAMES[side]
        blocks = inputs["frames"]["lv_dev"]["by_side"][side]
        v, inf = lv_values(side, frames_lv[side], lv_slots(blocks), panel)
        cols["lv_dev"][side][name] = v
        infos["lv_dev"][side] = inf
        vblocks = inputs["frames"]["vm_dev"]["by_side"][side]
        vv, vinf = vm_values(side, vblocks, vm_asof(side), panel)
        cols["vm_dev"][side][name] = vv
        infos["vm_dev"][side] = vinf
        log(f"  column {name}: lv {sum(x is not None for x in v.values())} of {len(v)}, "
            f"vm {sum(x is not None for x in vv.values())} of {len(vv)}")
    return cols, infos


def build_dev_inputs(panel: Panel, *, log=print):
    """efv_v3_backtest.build_dev with its wave-2 column builder replaced by this
    module's (the base parity checks run unchanged)."""
    import efv_v2_assemble as ASM
    import efv_v3_backtest as BT
    frames_lv = ASM.build_frames()
    store: dict = {}

    def w2(inputs, frames, *, log=print):
        cols, infos = dev_columns(inputs, frames, panel, log=log)
        store["infos"] = infos
        return cols
    orig_bf, orig_w2 = ASM.build_frames, BT.w2_values_dev
    ASM.build_frames = lambda *a, **k: frames_lv
    BT.w2_values_dev = w2
    try:
        inp = BT.build_dev(log=log)
    finally:
        ASM.build_frames, BT.w2_values_dev = orig_bf, orig_w2
    return inp, store["infos"]


def build_spent_inputs(panel: Panel, gate_sha: str, *, log=print):
    """efv_v3_backtest.build_reserved at the both-sides configuration with its wave-2
    column builder replaced by this module's. Needs the committed gate sha and the
    registration naming the reserved list years."""
    import efv_v3_backtest as BT
    if not RP.registration_names_reserved():
        raise F.ReservedFrameError("the registration at HEAD does not name the reserved "
                                   "list years; no reserved row is built")
    if not F.gate_sha_committed(gate_sha):
        raise F.ReservedFrameError(f"{gate_sha!r} is not the committed gate")
    store: dict = {}

    def w2(_names, *, lv, vm, frames_dev, frames_res, raw_by_side, pinned_asof, gate_sha,
           log=print):
        cols = {fid: {s: {} for s in F.SIDES} for fid in SPENT_FRAMES}
        infos = {fid: {} for fid in SPENT_FRAMES}
        for side in F.SIDES:
            name = COLUMN_NAMES[side]
            by_v = {**frames_dev[side], **frames_res[side]}
            v, inf = lv_values(side, by_v, lv_slots(lv["by_side"][side]), panel,
                               gate_sha=gate_sha)
            cols["lv_res"][side][name] = v
            infos["lv_res"][side] = inf
            asof = {"train": {pk: r.get("asof_date") for pk, r in raw_by_side[side].items()},
                    "test": pinned_asof[side]}
            vv, vinf = vm_values(side, vm["by_side"][side], asof, panel)
            cols["vm_pros"][side][name] = vv
            infos["vm_pros"][side] = vinf
            log(f"  column {name}: R-LV {sum(x is not None for x in v.values())} of {len(v)}, "
                f"R-VM {sum(x is not None for x in vv.values())} of {len(vv)}")
        store["infos"] = infos
        return cols
    orig = BT.w2_values_reserved
    BT.w2_values_reserved = w2
    try:
        with register_runtime():
            inp = BT.build_reserved(arm_config(ARMS[-1]), gate_sha=gate_sha, log=log)
    finally:
        BT.w2_values_reserved = orig
    return inp, store["infos"]


# ---------------------------------------------------------------------------
# the runs
# ---------------------------------------------------------------------------

def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _summary(blk: dict) -> dict:
    d2 = blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
    dc = blk["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
    bc = blk["deltas"]["efv_v2_base_vs_prospx_consensus"]["spearman"]
    return {"n": blk["n"], "vs_v2": d2.get("delta"), "vs_v2_ci95": d2.get("ci95"),
            "vs_consensus": dc.get("delta"), "vs_consensus_ci95": dc.get("ci95"),
            "v2_vs_consensus": bc.get("delta"),
            "admitted_folds": f"{blk['admitted_folds']} of {blk['n_folds']}",
            "twin_vs_v2": (blk.get("twin") or {}).get("within")}


def run_reads(inp, infos: dict, fids, *, B: int, log=print) -> dict:
    out = {"arms": [], "coverage": {}}
    for fid in fids:
        out["coverage"][fid] = {s: coverage(infos[fid][s], inp.cols[fid][s][COLUMN_NAMES[s]])
                                for s in F.SIDES}
    with register_runtime():
        for arm in ARMS:
            a = {"name": arm["name"], "sides": list(arm["sides"]), "head": arm["head"],
                 "kind": arm["kind"], "what": arm["what"],
                 "model_id": (f"{MODEL_PREFIX}:{arm['name']}:"
                              f"{arm['sides'][0] if len(arm['sides']) == 1 else 'both'}"),
                 "columns": {s: column_key(s) for s in arm["sides"]}, "frames": {}}
            t0 = time.time()
            for fid in fids:
                blk = read_arm(inp, fid, arm, B=B, twin_cols=twin_of(inp.cols, fid))
                a["frames"][fid] = blk
                s = _summary(blk)
                log(f"  {arm['name']} {fid}: vs V2 {s['vs_v2']} {s['vs_v2_ci95']}; vs consensus "
                    f"{s['vs_consensus']} {s['vs_consensus_ci95']}; admitted {s['admitted_folds']}; "
                    f"twin {s['twin_vs_v2']}")
            a["elapsed_s"] = round(time.time() - t0, 1)
            out["arms"].append(a)
    out["summary"] = [{"arm": a["name"], **{fid: _summary(a["frames"][fid]) for fid in fids}}
                      for a in out["arms"]]
    return out


def base_doc(panel_doc: dict) -> dict:
    import efv_labels as L
    return {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "role": "development",
        "adjudicates": False, "selects": False, "exploratory": False,
        "owner_decision": "EW2-10 (2026-10-08)", "note": NOTE,
        "registration": RP.REGISTRATION_DOC,
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through()},
        "code": {"commit": _commit(), "tool": TOOL, "sha256": _sha(Path(__file__)),
                 "panel_tool_sha256": _sha(ROOT / "efv_rater_panel.py"),
                 "efv_v3_sha256": _sha(ROOT / "efv_v3.py"),
                 "efv_v3_backtest_sha256": _sha(ROOT / "tools" / "efv_v3_backtest.py")},
        "panel": {"path": "data/_labs/efv_w2/rater_panel.json", "sha256": _sha(PANEL_PATH),
                  "lists": {lid: {k: b[k] for k in ("rater", "year", "published", "n_entries",
                                                      "n_resolved", "last_rank")}
                            for lid, b in (panel_doc.get("lists") or {}).items()},
                  "skipped_lists": panel_doc.get("skipped_lists"),
                  "skipped_sources": panel_doc.get("skipped_sources")},
        "defaults": {"list_floor": "the map band one step below the band of the list's "
                                   "last rank", "floors": {lid: list_floor(b["last_rank"])
                                                           for lid, b in (panel_doc.get("lists")
                                                                          or {}).items()},
                     "panel_mean": "every contributing rater once, unlisted at its floor",
                     "as_of": "a list counts for reads in its own year on or after its "
                              "publication day",
                     "fv_map": "consensus.implied_fv_from_rank"},
        "estimator": {"B": None, "seed": SEED, "estimator": "E_cond", "paired": True,
                      "unit": "player cluster",
                      "statistic": {"primary": S.STAT_LABEL[S.PRIMARY],
                                    "secondary": S.STAT_LABEL[S.SECONDARY],
                                    "veto": S.STAT_LABEL["auc"]}},
        "not_read": ["no grouping by consensus-FV level",
                     "no midseason list", "no list published outside [V-01-01, V-05-01)"],
    }


def run_dev(*, B: int = B_DEFAULT, log=print) -> dict:
    panel_doc = RP.load_panel(PANEL_PATH)
    panel = Panel.from_doc(panel_doc, allow_reserved=False)
    t0 = time.time()
    inp, infos = build_dev_inputs(panel, log=log)
    doc = base_doc(panel_doc)
    doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["estimator"]["B"] = int(B)
    doc["label"]["id"] = (inp.label or {}).get("id")
    doc["guards"] = inp.guards
    doc["base_parity"] = {"ds16": (inp.meta.get("base_parity") or {}).get("reproduces"),
                          "v3_base": inp.meta.get("v3_base_parity")}
    res = run_reads(inp, infos, DEV_FRAMES, B=B, log=log)
    doc["dev"] = {"frames": list(DEV_FRAMES), "coverage": res["coverage"],
                  "balance": {"lv_dev": balance(inp, infos["lv_dev"])},
                  "arms": res["arms"], "summary": res["summary"]}
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def run_spent(doc: dict, gate_sha: str, *, B: int = B_DEFAULT, log=print) -> dict:
    panel_doc = RP.load_panel(PANEL_PATH)
    if not panel_doc.get("reserved_years_built"):
        raise F.ReservedFrameError("the panel was built without the reserved list years")
    panel = Panel.from_doc(panel_doc, allow_reserved=True)
    t0 = time.time()
    inp, infos = build_spent_inputs(panel, gate_sha, log=log)
    res = run_reads(inp, infos, SPENT_FRAMES, B=B, log=log)
    doc = dict(doc)
    doc["spent"] = {"label": SPENT_LABEL, "frames": list(SPENT_FRAMES),
                    "role": "spent", "chooses": False, "tunes": False,
                    "gate_sha": gate_sha, "guards": inp.guards,
                    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "B": int(B), "coverage": res["coverage"], "arms": res["arms"],
                    "summary": res["summary"], "elapsed_s": round(time.time() - t0, 1),
                    "note": ("R-LV (list vintages 2020 and 2021) and R-VM (2025 debut "
                             "cohort) were read once on 2026-10-08 under the owner's waiver "
                             "(EW2-6) and are spent (EW2-10); this read chooses and tunes "
                             "nothing and writes no progress-ledger row")}
    return doc


def write_doc(doc: dict, out: Path = OUT_PATH) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n"
    for bad in (chr(0x2014), chr(0x2013)):
        if bad in text:
            raise ValueError("an em or en dash in the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)
    return out


# ---------------------------------------------------------------------------
# the progress ledger: this module's own development rows
# ---------------------------------------------------------------------------

def arm_docs(doc: dict) -> list[dict]:
    """One development document per arm (the efv_w2_scout shape), with a screening block
    so the Source Comparison page lists it in the collapsed screening block and never
    charts it."""
    out = []
    dev = doc.get("dev") or {}
    for a in dev.get("arms") or []:
        scr = {"wave": 4, "lane": "rater_panel", "item": ITEM, "head": a["head"],
               "side": "both" if len(a["sides"]) > 1 else a["sides"][0], "kind": a["kind"],
               "components": ["rater_panel_resid"], "exploratory": False,
               "development_only": True, "artifact": "data/_labs/efv_w2/efv_w2_raters.json",
               "admitted_folds": {fid: a["frames"][fid]["admitted_folds"] for fid in DEV_FRAMES},
               "twin_within": {fid: (a["frames"][fid].get("twin") or {}).get("within")
                               for fid in DEV_FRAMES}}
        out.append({"role": "development", "model_id": a["model_id"],
                    "generated_at": doc.get("generated_at"), "label": doc.get("label") or {},
                    "code": doc.get("code") or {}, "screening": scr,
                    "frames": {fid: a["frames"][fid] for fid in DEV_FRAMES}})
    return out


def update_progress(doc: dict, *, artifact: Path = OUT_PATH, data_dir: Path | None = None,
                    out_path: Path | None = None, ledger_path: Path | None = None) -> dict:
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    data_dir = Path(data_dir) if data_dir is not None else H.DATA_DIR
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    cands = []
    for d in arm_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now.date().isoformat(),
                                  trigger="efv_change", now_iso=now_iso, frames=DEV_FRAMES,
                                  raters=P.SCREEN_RATERS, deltas=P.SCREEN_DELTAS,
                                  statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no rows"}
    res = P.commit_rows(cands, data_dir=data_dir, out_path=out_path,
                        ledger_path=ledger_path if ledger_path is not None else PRIVATE_LEDGER,
                        sb=P._load_json(data_dir / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--panel", action="store_true", help="parse and resolve the lists")
    ap.add_argument("--dev", action="store_true", help="the development read")
    ap.add_argument("--spent", action="store_true", help="the spent-frame read")
    ap.add_argument("--gate-sha", default=None)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    ap.add_argument("--no-ledger", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if a.panel:
        d = RP.build_panel()
        RP.write_panel(d, PANEL_PATH)
        for lid, blk in d["lists"].items():
            print(lid, blk["published"], blk["n_entries"], blk["n_resolved"])
        for s in d["skipped_lists"]:
            print("skipped", json.dumps(s))
    if a.dev:
        doc = run_dev(B=a.B)
        write_doc(doc, out)
        print(f"wrote {out} ({doc['elapsed_s']} s)")
        for r in doc["dev"]["summary"]:
            print(json.dumps(r))
        if not a.no_ledger and a.B == B_DEFAULT:
            res = update_progress(doc, artifact=out)
            print(f"progress: {len(res.get('appended') or [])} row(s) appended, "
                  f"{res.get('n_rows')} total")
    if not (a.panel or a.dev or a.spent):
        # no action named (efv_screen_lab --wave2-dev): the development read
        return main(["--dev"] + (["--no-ledger"] if a.no_ledger else []))
    if a.spent:
        if not a.gate_sha:
            print("refused: --spent needs --gate-sha")
            return 2
        doc = json.loads(out.read_text(encoding="utf-8"))
        doc = run_spent(doc, a.gate_sha, B=a.B)
        write_doc(doc, out)
        print(f"wrote {out} (spent block, {doc['spent']['elapsed_s']} s)")
        for r in doc["spent"]["summary"]:
            print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())

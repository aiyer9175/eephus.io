# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 COMBINED, the registered re-fit (EFV_FIX_B_REFIT; owner decision EW3-21,
2026-10-15; method docs/efv-v2/EFV_V5_REFIT.md, committed alone before this module).

THE ARMS (the document, section 2), each a change to how eFV v5 COMBINED is fitted:
  A1  the population norms repair (efv_w2_popmle.POP_REPAIR_ON) in every fit and read
  A2  the columns dark on the live board dropped from both heads (DARK)
  A3  the arrival (timing) head fitted on the outcome-blind list-vintage frame
  A4  twin training rows read on 15 October of the read season (the live timing)
  A5  the population column as a within-group rank (the registered variant RT)
and the head weights w_skill, w_time re-derived per side by DS-08's OLS ratio over the
forward-chained out-of-fold head terms of both development frames, cross-fitted for the
read (section 4).

THE READ. Development frames only (lv_dev, vm_dev); the comparator V5 (eFV v5 COMBINED as
served) is recomputed in the same run on the same rows; the ship rule of section 6 decides
whether the flip is PREPARED. It is never served here: EFV_V5_REFIT_ON stays False, and
the owner flips it (with efv_w2_popmle.POP_REPAIR_ON, which moves with it).

THE SERVED PATH (dark). With EFV_V5_REFIT_ON True, efv_v2_serve.production_models serves
production_models() below: the production fit stored in data/efv5_refit_weights.json by
the run (heads, weights, pricing line), read as fitted.

RESERVED FRAMES. The development build raises on list vintages 2020 and 2021 and stops
before the 2025 cohort (efv_vintage_frame); the list-vintage timing pool stops at 2019.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
percentile and as the value multiset the grade is drawn from; the strata are side, year,
fold, level, age band, role and position family. Nothing here groups, counts or averages
rows by consensus-FV level; test_efv5_refit.py scans this source.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

import efv5_combined as V5C
import efv_v2_candidates as C
import efv_v2_model as H
import efv_v3 as V3
import efv_vintage_frame as F

#: THE SWITCH. False: nothing here serves. True: efv_v2_serve.production_models serves the
#: re-fit's stored production fit; efv_w2_popmle.POP_REPAIR_ON must equal it (test-pinned).
#: Only the owner flips it, and only after a PREPARED read (data/efv5_refit_weights.json).
EFV_V5_REFIT_ON = False
#: Which passing candidate the flag serves: None serves the one the ship rule PREPARED
#: (section 6); the owner may name another candidate that passed (data/efv5_refit_weights.json
#: stores the production fit of every candidate).
SERVE_CANDIDATE: str | None = None

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
FIT_PATH = LAB_DIR / "efv5_refit_fit.json"
WEIGHTS_PATH = DATA_DIR / "efv5_refit_weights.json"
DOC = "docs/efv-v2/EFV_V5_REFIT.md"
TOOL = "efv5_refit.py"
ITEM = "EFV_FIX_B_REFIT"
#: The served model id when the flag is on (the re-fit is eFV v5 COMBINED re-fitted).
SERVED_MODEL_ID = V5C.MODEL_ID
#: The progress-ledger model id of the re-fit's development rows.
LEDGER_MODEL_ID = "efv_v5_refit"

#: A2: the columns the 2026-10-15 live read lists as dark or withheld (the document, s2).
DARK: tuple[str, ...] = (
    "w2r_panel_hit", "w2r_panel_pit",
    "rpt_conviction_hit", "rpt_hedge_count_hit", "rpt_risk_hit", "rpt_approach_concern_hit",
    "rpt_writer_minus_stated_hit", "rpt_arrival_hit",
    "rpt_conviction_pit", "rpt_writer_minus_stated_pit", "rpt_arrival_pit",
    "t5_pit_Ap_all_SP_sl_gap", "t5_pit_Ap_young_all_sl_gap", "t5_pit_Ap_all_all_sl_gap",
)
#: A4: the twin's read day inside its read season (the live board's calendar day).
TWIN_MMDD = "-10-15"
#: A3: the last list vintage of the timing pool (2020 and 2021 are reserved).
LV_POOL_LAST = 2019
LV_POOL_FIRST = 2011
#: A5: the population columns the variant transforms.
POP_COLUMNS = {"hit": "w4p_pop_hit", "pit": "w4p_pop_pit"}
#: Section 4: the weight bootstrap.
WEIGHT_B = 2000
WEIGHT_SEED = 20261016
#: Section 6: a candidate may trail V5 by at most this much on either frame.
MAX_TRAIL = 0.005
#: Section 4: the descriptive objective grid.
GRID_SKILL: tuple[float, ...] = tuple(round(0.1 * i, 1) for i in range(11))
#: The configurations read (the document, section 3).
CONFIGS: dict[str, dict] = {
    "V5": {"norms": False, "dark": False, "lv_timing": False, "twins": False,
           "transform": False, "weights": "p5", "role": "comparator (eFV v5 COMBINED as served)"},
    "W": {"norms": False, "dark": False, "lv_timing": False, "twins": False,
          "transform": False, "weights": "rederived", "role": "decomposition: V5's heads, re-derived weights"},
    "R": {"norms": True, "dark": True, "lv_timing": True, "twins": True,
          "transform": False, "weights": "rederived", "role": "primary candidate"},
    "R0": {"norms": True, "dark": True, "lv_timing": True, "twins": False,
           "transform": False, "weights": "rederived", "role": "decomposition: R without twins"},
    "RT": {"norms": True, "dark": True, "lv_timing": True, "twins": True,
           "transform": True, "weights": "rederived", "role": "registered variant (popmle rank)"},
}
CANDIDATES: tuple[str, ...] = ("R", "RT")
#: Score keys of each configuration on the scored rows.
KEY = {c: f"efv_v5_{c.lower()}" for c in CONFIGS}

_LOG = print


def _tools():
    return V5C._tools()


def _f(v):
    return V5C._f(v)


# ---------------------------------------------------------------------------
# the population norms flag (A1): one place flips it, every cache follows
# ---------------------------------------------------------------------------

def clear_flag_caches() -> None:
    """Every memo whose value depends on efv_w2_popmle.POP_REPAIR_ON."""
    import efv_w2_popmle as PM
    for fn in (PM.season_lines, PM.norms, PM.player_seasons):
        fn.cache_clear()
    for d in (V5C._PROD_COLS, V5C._LIVE_CACHE, V5C._LIVE_MEMO, V5C._LIVE_RECEIPTS,
              V5C._SUPPORT):
        d.clear()
    try:
        import efv_v2_serve as S
        S._MODELS = None
    except ImportError:
        pass


@contextmanager
def pop_repair(on: bool):
    """efv_w2_popmle.POP_REPAIR_ON set to `on` for the block, caches cleared both ways."""
    import efv_w2_popmle as PM
    prev = PM.POP_REPAIR_ON
    PM.POP_REPAIR_ON = bool(on)
    clear_flag_caches()
    try:
        yield
    finally:
        PM.POP_REPAIR_ON = prev
        clear_flag_caches()


# ---------------------------------------------------------------------------
# the candidate columns of a configuration (A2)
# ---------------------------------------------------------------------------

def refit_candidates(side: str, head: str | None = None, *, dark: bool = True) -> list[str]:
    """V5's candidate columns of the side (and head), minus DARK when `dark`."""
    names = V5C.side_candidates(side, head)
    return [n for n in names if not (dark and n in DARK)]


def pop_key(side: str) -> str:
    return V5C.candidates()[POP_COLUMNS[side]]["key"]


# ---------------------------------------------------------------------------
# A5: the population column as a within-group rank
# ---------------------------------------------------------------------------

def rank_values(vals: list) -> list:
    """Mid-rank percentile minus 0.5 of the non-None values (ties take their mean rank);
    None stays None. Monotone and bounded in (-0.5, 0.5]."""
    idx = [i for i, v in enumerate(vals) if v is not None]
    out: list = [None] * len(vals)
    if not idx:
        return out
    x = np.asarray([float(vals[i]) for i in idx], dtype=np.float64)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(x.size)
    ranks[order] = np.arange(1, x.size + 1, dtype=np.float64)
    for u in np.unique(x):
        m = x == u
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    pct = ranks / x.size - 0.5
    for j, i in enumerate(idx):
        out[i] = float(pct[j])
    return out


def rank_transform(rows: list[dict], side: str, *, group_of=None) -> list[dict]:
    """Copies of rows with the population column replaced by its within-group rank
    (group_of(row), default the decision year, among the rows given)."""
    k = pop_key(side)
    group_of = group_of or (lambda r: int(r["decision_year"]))
    by: dict = {}
    for i, r in enumerate(rows):
        by.setdefault(group_of(r), []).append(i)
    new = [None] * len(rows)
    for idx in by.values():
        got = rank_values([rows[i]["v2"].get(k) for i in idx])
        for i, v in zip(idx, got):
            new[i] = v
    return [dict(r, v2=dict(r["v2"], **{k: new[i]})) for i, r in enumerate(rows)]


_LIVE_POP: dict = {}


def transform_live(rows: list[dict], side: str) -> list[dict]:
    """The live board's rows with the population column ranked within the board side
    (the served path of RT; one group: the live list year). The board's raw values are
    kept for transform_history."""
    k = pop_key(side)
    _LIVE_POP[side] = np.sort(np.asarray([float(r["v2"][k]) for r in rows
                                          if r["v2"].get(k) is not None], dtype=np.float64))
    return rank_transform(rows, side, group_of=lambda r: "live")


def transform_history(side: str, cands: dict) -> dict:
    """A history snapshot's candidate values ({key: value}) with the population value placed
    in the live board's raw distribution (its mid-rank percentile among the board's values,
    minus 0.5), the scale the served RT heads read; None when the board has not been read
    in this process (the head's training mean, never a raw value on the wrong scale)."""
    k = pop_key(side)
    if k not in cands:
        return cands
    v = cands.get(k)
    ref = _LIVE_POP.get(side)
    if v is None or ref is None or ref.size == 0:
        return dict(cands, **{k: None})
    lo = int(np.searchsorted(ref, float(v), side="left"))
    hi = int(np.searchsorted(ref, float(v), side="right"))
    return dict(cands, **{k: (lo + (hi - lo + 1) / 2.0) / ref.size - 0.5})


#: What the board discloses about its head weights and its read once the re-fit serves.
REFIT_WEIGHTS_NOTE = ("w_skill and w_time are the re-fit's own (EFV_FIX_B_REFIT, "
                      "docs/efv-v2/EFV_V5_REFIT.md): DS-08's OLS ratio on forward-chained "
                      "out-of-fold head terms of both development frames, clipped to [0, 1]")


def refit_disclosures(disc: dict) -> dict:
    """efv_v2_serve.served_disclosures under the re-fit: the head weights' source and the
    season read's training coverage (A4) restated; the dark list is the fit's own (A2)."""
    out = dict(disc)
    hw = dict(out.get("head_weights") or {})
    hw.update(source=WEIGHTS_PATH.relative_to(ROOT).as_posix(), pending=None,
              note=REFIT_WEIGHTS_NOTE)
    out["head_weights"] = hw
    sr = dict(out.get("season_read") or {})
    sr["note"] = ("the re-fit adds training rows read on the live board's calendar day "
                  "(15 October of the read season, consensus as it stood that day); no "
                  "training row carries a consensus re-ranked after the season ended, the "
                  "regime of the October lists on the live board")
    out["season_read"] = sr
    out["dropped_from_fit"] = sorted(V5C.candidates()[n]["key"] for n in DARK)
    return out


# ---------------------------------------------------------------------------
# A4: twin rows read at the live timing
# ---------------------------------------------------------------------------

def twin_day(read_season: int) -> str:
    return f"{int(read_season)}{TWIN_MMDD}"


def build_twins(side: str, rows: list[dict], *, raw_by_key: dict | None = None,
                recs: dict | None = None, panel: dict | None = None) -> tuple[list[dict], dict]:
    """(twin rows, receipt) for the v1 matrix rows given (efv_v2_model.matrix_training_rows
    shape). The twin of a row reads on T = R-10-15 (R its MiLB read season) with the
    record's latest consensus point on or before T; no twin when T is on or after the row's
    cutoff, when no such point exists, or when it is the row's own as-of point (the
    document, A4). The prior block is read at the point (efv_v2_model.pinned_inputs'
    construction), the MiLB block stays the row's own, BMI is read as of T."""
    import efv_dataset as D
    import efv_drivers as DRV
    import efv_model as V1
    from efv_w2_milb import last_readable_season
    raw_by_key = raw_by_key if raw_by_key is not None else V5C._raw_by_side()[side]
    recs = recs if recs is not None else D.asof_records()
    panel = panel if panel is not None else DRV.load_bio_panel()
    out = []
    why: dict = {}
    lags = []
    for d in rows:
        pk = d["player_key"]
        raw = raw_by_key.get(pk)
        if raw is None:
            why["no_matrix_row"] = why.get("no_matrix_row", 0) + 1
            continue
        dy = int(d["decision_year"])
        cut = raw.get("cutoff")
        R = last_readable_season(dy, cut)
        T = twin_day(R)
        if cut and T >= str(cut)[:10]:
            why["read_day_not_before_cutoff"] = why.get("read_day_not_before_cutoff", 0) + 1
            continue
        pts = [p for p in ((recs.get(pk) or {}).get("points") or [])
               if p.get("snapshot_date") and str(p["snapshot_date"])[:10] <= T
               and _f(p.get("consensus_fv_raw")) is not None]
        if not pts:
            why["no_point_by_read_day"] = why.get("no_point_by_read_day", 0) + 1
            continue
        pt = sorted(pts, key=lambda p: p["snapshot_date"])[-1]
        pdate = str(pt["snapshot_date"])[:10]
        if pdate == str(raw.get("asof_date") or "")[:10]:
            why["same_point_as_row"] = why.get("same_point_as_row", 0) + 1
            continue
        row = dict(raw)
        row.update(D._prior_features(recs.get(pk), pt, side))
        row.pop("fv_effective", None)
        feats = V1._vec(row, side)
        extra = {"bmi": DRV.bmi_asof(pk, T, panel)}
        tw = dict(d, feats=feats, fv=float(row["consensus_fv_raw"]), extra=extra,
                  v2=H.v2_row(feats, extra), twin=True, twin_read_day=T,
                  twin_point=pdate, twin_read_season=int(R),
                  mlbam_id=raw.get("mlbam_id"))
        out.append(tw)
        lags.append((date.fromisoformat(pdate) - date(int(R), 10, 1)).days)
    lag = np.asarray(lags, dtype=np.float64)
    q = (lambda p: round(float(np.percentile(lag, p)), 1)) if lag.size else (lambda p: None)
    rec = {"rows_in": len(rows), "twins": len(out), "skipped": why,
           "by_year": {str(y): sum(1 for t in out if int(t["decision_year"]) == y)
                       for y in sorted({int(t["decision_year"]) for t in out})},
           "consensus_lag_days": {"p10": q(10), "p25": q(25), "p50": q(50), "p75": q(75),
                                  "p90": q(90),
                                  "share_0_to_30": (round(float(((lag >= 0) & (lag <= 30)).mean()), 4)
                                                    if lag.size else None),
                                  "share_negative": (round(float((lag < 0).mean()), 4)
                                                     if lag.size else None)}}
    return out, rec


def twin_slot(t: dict) -> tuple:
    return (int(t["decision_year"]), t["player_key"], "twin")


def twin_columns(side: str, twins: list[dict], *, today: str, names=None,
                 log=print) -> tuple[dict, dict]:
    """({name: {slot: value}}, receipt): every candidate column of the twins, read as of
    each twin (read year R + 1, cutoff T, as-of the point's date) by the live board's
    as-of builders (efv5_combined.asof_columns), unclipped."""
    items = [V5C._item(twin_slot(t), t["player_key"], t.get("mlbam_id"),
                       int(t["decision_year"]), int(t["twin_read_season"]) + 1,
                       t["twin_read_day"], t["twin_point"], t["fv"]) for t in twins]
    names = V5C.side_candidates(side) if names is None else list(names)
    cols, rec = V5C.asof_columns(side, items, today=today, names=names, log=log)
    return cols, rec


def attach_slots(rows: list[dict], side: str, cols_side: dict, slot_of) -> list[dict]:
    """V5C.attach with an arbitrary slot function."""
    cands = V5C.candidates()
    out = []
    for r in rows:
        s = slot_of(r)
        add = {}
        for n in V5C.side_candidates(side):
            v = (cols_side.get(n) or {}).get(s)
            add[cands[n]["key"]] = None if v is None else float(v)
        out.append(dict(r, v2=dict(r["v2"], **add)))
    return out


# ---------------------------------------------------------------------------
# A3: the list-vintage pool (every labelled list-vintage row of 2011 to 2019)
# ---------------------------------------------------------------------------

def lv_pool(frames_lv: dict, *, log=print) -> tuple[dict, dict]:
    """({side: pool rows with every candidate column attached}, receipt). The rows are
    efv_v2_model.lv_training_rows over the development list vintages; the columns are
    built by the development read's list-vintage builders on one frame holding every
    pool row (a fold-free build: each value depends on its (V, player) only)."""
    BT, B4 = _tools()
    SC = V5C._scout()
    import efv5_group_drivers as G
    rows = {}
    for s in F.SIDES:
        fl = {int(V): v for V, v in frames_lv[s].items()
              if LV_POOL_FIRST <= int(V) <= LV_POOL_LAST}
        rows[s] = H.lv_training_rows(s, fl)
        if any(int(r["decision_year"]) in F.RESERVED_LV for r in rows[s]):
            raise F.ReservedFrameError("a reserved list vintage reached the timing pool")
    fake = V5C._FakeInputs({"lv_pool": {"by_side": {s: {LV_POOL_LAST: {"train": rows[s], "test": []}}
                                                    for s in F.SIDES}},
                            "vm_none": {"by_side": {s: {} for s in F.SIDES}}})
    fids = ("lv_pool", "vm_none")
    rows_lv = {s: {int(V): r for V, (r, _l) in frames_lv[s].items()
                   if LV_POOL_FIRST <= int(V) <= LV_POOL_LAST} for s in F.SIDES}
    t0 = time.time()
    gcols, _grec = G.build_columns(fake, fids, rows_lv, list(G.menu_columns()), log=log)
    cols = {s: dict(gcols["lv_pool"][s]) for s in F.SIDES}
    index = SC.default_index()
    for s in F.SIDES:
        names = [n for n in V5C.TOOL_CELLS if V5C.TOOL_CELLS[n]["side"] == s]
        if not names:
            continue
        vals, _cnt = V5C.tool_lv_columns(s, rows_lv[s], names, index, log=log)
        for n in names:
            cols[s][n] = {(int(r["decision_year"]), r["player_key"], "train"):
                          vals[n].get((int(r["decision_year"]), r["player_key"]), 0.0)
                          for r in rows[s]}
    v4c, v4rec = B4.v4_values(fake, fids, frames_lv, list(V5C.V4.menu_columns()), log=log)
    for s in F.SIDES:
        cols[s].update(v4c["lv_pool"][s])
    fl_pool = {s: {int(V): v for V, v in frames_lv[s].items()
                   if LV_POOL_FIRST <= int(V) <= LV_POOL_LAST} for s in F.SIDES}
    with V5C._w2s_only():
        w2 = BT.w2_values_dev({"frames": {"vm_dev": {"by_side": {s: {} for s in F.SIDES}}}},
                              fl_pool, log=log)
    for s in F.SIDES:
        cols[s].update(w2["lv_dev"][s])
    out = {}
    rec = {"seconds": round(time.time() - t0, 1), "rows": {}, "missing": {}}
    for s in F.SIDES:
        missing = [n for n in V5C.side_candidates(s) if n not in cols[s]]
        rec["missing"][s] = missing
        out[s] = V5C.attach(rows[s], s, cols[s], "train")
        rec["rows"][s] = {"n": len(out[s]),
                          "vintages": sorted({int(r["decision_year"]) for r in out[s]})}
    if any(rec["missing"].values()):
        raise RuntimeError(f"timing pool columns not built: {rec['missing']}")
    return out, rec


def lv_timing_rows(pool_side: list[dict], *, last: int, leave_out: set) -> list[dict]:
    """The pool rows of vintages LV_POOL_FIRST to `last`, players in `leave_out` out."""
    return [r for r in pool_side if int(r["decision_year"]) <= int(last)
            and r["player_key"] not in leave_out]


# ---------------------------------------------------------------------------
# the fit: skill head on its rows, timing head on its rows (fit_combined's calls)
# ---------------------------------------------------------------------------

def fit_heads(skill_rows: list[dict], skill_frame: str, timing_rows: list[dict],
              timing_frame: str, side: str, *, cands_skill, cands_timing,
              timing_outcome_blind: bool, absent_ok=None, lam: dict | None = None,
              with_se: bool = False) -> dict:
    """efv5_combined.fit_combined with the two heads on their own rows: the skill head on
    `skill_rows` (frame `skill_frame`), the timing head on `timing_rows` with the menu
    of `timing_outcome_blind` (False: the vm-frame menu, no protection or absence keys)."""
    C.guard_training_rows(skill_rows, skill_frame)
    C.guard_training_rows(timing_rows, timing_frame)
    cfg = V3.base_config()
    ob_s = skill_frame == "lv"
    ab_s = ob_s and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    s_cands = V3.head_candidates(cfg, side, "skill", ids_outcome_blind=ob_s,
                                 absence_admitted=ab_s)
    v2_keys, checks = ((), {})
    alpha_s = None
    if s_cands:
        v2_keys, checks = C._admitted_keys_a(skill_rows, s_cands, target="u_y",
                                             has_block_only=True)
        if v2_keys:
            def fit_s(tr, a):
                return C._skill_fit_g(tr, v2_keys, a, C._v2_design(v2_keys))
            alpha_s = C._select_alpha_g(skill_rows, fit_s, C._skill_loss)
    skill = None
    lam_s = None
    sk_c = list(cands_skill)
    if v2_keys or sk_c:
        lam_s = (float(lam["skill"]) if lam and lam.get("skill") is not None
                 else V5C.select_lambda(skill_rows, "skill", v2_keys, alpha_s, sk_c))
        skill = V5C.joint_skill(skill_rows, v2_keys, alpha_s, sk_c, lam_s)
        if skill is not None:
            skill.update({"side": side, "candidates": list(s_cands), "v2_keys": list(v2_keys),
                          "candidate_columns": sk_c, "anchor": False,
                          "trained_frame": skill_frame,
                          "admission": {k: {"admitted": v.get("admitted"), "sign": v.get("sign"),
                                            "mean_abs_t": v.get("mean_abs_t")}
                                        for k, v in checks.items()}})
            skill["score_sd"] = C._score_sd(skill, H.skill_training_rows(skill_rows))
            if with_se:
                skill["se"] = V5C.head_se(skill, skill_rows)
    timing = None
    why = None
    lam_t = None
    tm_c = list(cands_timing)
    if side == "pit" and not H.head_usable(skill):
        why = ("owner DS-Q2: no pitcher skill driver passed the admission rule in this "
               "fold, so pitchers take the consensus order")
    else:
        ab_t = bool(timing_outcome_blind) and (H.absence_admitted(side) if absent_ok is None
                                               else bool(absent_ok))
        t_cands = V3.head_candidates(cfg, side, "timing",
                                     ids_outcome_blind=bool(timing_outcome_blind),
                                     absence_admitted=ab_t)
        tkeys, tchecks = C._admitted_keys_a(timing_rows, t_cands, target="reached",
                                            has_block_only=False)

        def fit_t(tr, a):
            return C._timing_fit_g(tr, tkeys, a, C._v2_design(tkeys))
        alpha_t = C._select_alpha_g(timing_rows, fit_t, C._timing_loss)
        lam_t = (float(lam["timing"]) if lam and lam.get("timing") is not None
                 else V5C.select_lambda(timing_rows, "timing", tkeys, alpha_t, tm_c))
        timing = V5C.joint_timing(timing_rows, tkeys, alpha_t, tm_c, lam_t)
        if timing is not None:
            timing.update({"side": side, "candidates": list(t_cands), "v2_keys": list(tkeys),
                           "candidate_columns": tm_c, "anchor": False,
                           "ids_outcome_blind": bool(timing_outcome_blind),
                           "trained_frame": timing_frame,
                           "admission": {k: {"admitted": v.get("admitted"), "sign": v.get("sign"),
                                             "mean_abs_t": v.get("mean_abs_t")}
                                         for k, v in tchecks.items()}})
            timing["score_sd"] = C._score_sd(timing, timing_rows)
            if with_se:
                timing["se"] = V5C.head_se(timing, timing_rows)
    return {"model_id": V5C.MODEL_ID, "base_model_id": H.V2_ASSEMBLED_ID, "side": side,
            "frame": skill_frame, "timing_frame": timing_frame,
            "config": {"lam": {"skill": lam_s, "timing": lam_t}},
            "skill": skill, "timing": timing,
            "consensus_only_reason": why,
            "n_train": len(skill_rows), "n_train_timing": len(timing_rows),
            "train_years": sorted({int(r["decision_year"]) for r in skill_rows}),
            "timing_train_years": sorted({int(r["decision_year"]) for r in timing_rows})}


def pack(fold_id: str, fid: str, side: str, fold: int, te: list[dict], scored: list[dict],
         e_s: np.ndarray, e_t: np.ndarray, **extra) -> dict:
    """One fold's out-of-fold terms. Orders read u_c within the fold's test rows (as
    efv_v2_model.predict_v2 does); the weight regression reads the fold's SCORED rows (the
    rows carrying the frame's label): u_c and u_y within them, the test rows' e terms."""
    BT, _B4 = _tools()
    uc_test = H.within_pct([r["fv"] for r in te], [0] * len(te)) if te else np.zeros(0)
    pos = {r["player_key"]: i for i, r in enumerate(te)}
    sc = [c for c in scored if c["key"] in pos]
    ix = np.asarray([pos[c["key"]] for c in sc], dtype=int)
    fv = [float(te[pos[c["key"]]]["fv"]) for c in sc]
    war = [float(c["outcome"]["war"]) for c in sc]
    ols = {"keys": [c["key"] for c in sc],
           "u_c": H.within_pct(fv, [0] * len(sc)) if sc else np.zeros(0),
           "u_y": H.within_pct(war, [0] * len(sc)) if sc else np.zeros(0),
           "e_s": np.asarray(e_s)[ix] if sc else np.zeros(0),
           "e_t": np.asarray(e_t)[ix] if sc else np.zeros(0)}
    return dict({"fold_id": fold_id, "fid": fid, "side": side, "fold": int(fold),
                 "keys": [r["player_key"] for r in te], "u_c": uc_test,
                 "e_s": np.asarray(e_s), "e_t": np.asarray(e_t), "ols": ols}, **extra)


def e_terms(m: dict, rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """(e_skill, e_time) of a fitted model on rows, weight-free (0 for an unusable head)."""
    return H.e_skill(m.get("skill"), rows), H.e_time(m.get("timing"), rows)


# ---------------------------------------------------------------------------
# section 4: the weights
# ---------------------------------------------------------------------------

def _share(r):
    return H._share(r)


def ols_ratios(u_c, u_y, e_s, e_t) -> dict:
    """DS-08's pooled OLS u_y ~ 1 + u_c + e_skill + e_time and the clipped weights."""
    u_c, u_y, e_s, e_t = (np.asarray(a, dtype=np.float64) for a in (u_c, u_y, e_s, e_t))
    n = u_y.size
    cols = {"u_c": u_c, "e_skill": e_s, "e_time": e_t}
    live = [k for k, v in cols.items() if k == "u_c" or np.any(v != 0)]
    X = np.column_stack([np.ones(n)] + [cols[k] for k in live])
    XtX = X.T @ X
    b = np.linalg.solve(XtX, X.T @ u_y)
    coef = {"intercept": float(b[0]), **{k: float(b[i + 1]) for i, k in enumerate(live)}}
    c_uc = coef["u_c"]
    r_s = coef["e_skill"] / c_uc if (c_uc > 0 and "e_skill" in coef) else None
    r_t = coef["e_time"] / c_uc if (c_uc > 0 and "e_time" in coef) else None
    return {"n": int(n), "coef": coef, "live_columns": live,
            "w_skill_ratio": r_s, "w_time_ratio": r_t,
            "w_skill": _share(r_s), "w_time": _share(r_t)}


def _pool(packs: list[dict]) -> tuple:
    cat = (lambda k: np.concatenate([p["ols"][k] for p in packs]) if packs else np.zeros(0))
    return cat("u_c"), cat("u_y"), cat("e_s"), cat("e_t")


def weights_from(packs: list[dict]) -> dict:
    return ols_ratios(*_pool(packs))


def cross_fitted(packs: list[dict]) -> dict:
    """{fold id: the weights of the pool with that fold left out}."""
    out = {}
    for p in packs:
        rest = [q for q in packs if q["fold_id"] != p["fold_id"]]
        w = weights_from(rest)
        out[p["fold_id"]] = {"w_skill": w["w_skill"], "w_time": w["w_time"],
                             "w_skill_ratio": w["w_skill_ratio"],
                             "w_time_ratio": w["w_time_ratio"]}
    return out


def boot_weights(packs: list[dict], *, B: int = WEIGHT_B, seed: int = WEIGHT_SEED) -> dict:
    """Player-clustered bootstrap of the pooled OLS ratios: CI95 of each ratio and of
    each clipped weight."""
    u_c, u_y, e_s, e_t = _pool(packs)
    keys = [k for p in packs for k in p["ols"]["keys"]]
    ids: dict = {}
    for k in keys:
        ids.setdefault(k, len(ids))
    cl = np.asarray([ids[k] for k in keys])
    members = [np.flatnonzero(cl == i) for i in range(len(ids))]
    rng = np.random.default_rng(int(seed))
    got = {"w_skill_ratio": [], "w_time_ratio": [], "w_skill": [], "w_time": []}
    for _ in range(int(B)):
        draw = rng.integers(0, len(members), size=len(members))
        ix = np.concatenate([members[j] for j in draw])
        try:
            w = ols_ratios(u_c[ix], u_y[ix], e_s[ix], e_t[ix])
        except np.linalg.LinAlgError:
            continue
        for k in got:
            if w.get(k) is not None:
                got[k].append(float(w[k]))
    out = {"B": int(B), "seed": int(seed), "unit": "player cluster"}
    for k, v in got.items():
        a = np.asarray(v)
        out[k] = ({"ci95": [round(float(np.quantile(a, 0.025)), 4),
                            round(float(np.quantile(a, 0.975)), 4)],
                   "sd": round(float(a.std(ddof=1)), 4), "B_used": int(a.size)}
                  if a.size > 1 else None)
    return out


# ---------------------------------------------------------------------------
# the scored rows and statistics (the development read's machinery)
# ---------------------------------------------------------------------------

@contextmanager
def raters_named(raters):
    BT, _B4 = _tools()
    orig = BT.RATERS_OUT
    BT.RATERS_OUT = tuple(raters)
    try:
        yield
    finally:
        BT.RATERS_OUT = orig


def _keep(d: dict) -> dict:
    return {k: v for k, v in d.items()
            if k in ("delta", "ci95", "mde95", "n", "status", "reading", "a", "b")}


def frame_rows(inp, fid: str, orders: dict[str, dict]) -> list[dict]:
    """The frame's scored rows with each configuration's order under KEY[config];
    orders[config][fid] is keyed (side, fold, player_key) INSIDE its frame (a player can sit
    in a list-vintage fold and a debut-year fold of the same year)."""
    out = []
    for c in inp.scored(fid):
        k = (c["side"], int(c["year"]), c["key"])
        g = dict(c["grades"])
        for name, by_fid in orders.items():
            od = by_fid.get(fid) or {}
            if k in od:
                g[KEY[name]] = float(od[k])
        out.append(dict(c, grades=g))
    return out


def within_of(rows: list[dict], key: str) -> dict:
    """{"within", "n"} of one score on rows (efv_v2_stat's within, groups of 20+)."""
    import efv_v2_stat as S
    BT, _B4 = _tools()
    sel = [c for c in rows if c["grades"].get(key) is not None]
    if not sel:
        return {"within": None, "n": 0}
    st = S.rater_stats([c["grades"][key] for c in sel], [c["outcome"]["war"] for c in sel],
                       [bool(c["outcome"]["contributor"]) for c in sel],
                       [c["group"] for c in sel], [c["grades"][BT.CONS] for c in sel])
    return {"within": st["within"], "n": st["n"], "pooled": st.get("pooled"),
            "auc": st.get("auc")}


def comparisons() -> tuple:
    BT, _B4 = _tools()
    out = []
    for c in CANDIDATES:
        out += [(f"{c}_vs_V5", KEY[c], KEY["V5"]), (f"{c}_vs_prospx_consensus", KEY[c], BT.CONS),
                (f"{c}_vs_mlb_pipeline", KEY[c], "mlb_pipeline"),
                (f"{c}_vs_fangraphs", KEY[c], "fangraphs")]
    out += [("V5_vs_prospx_consensus", KEY["V5"], BT.CONS), ("RT_vs_R", KEY["RT"], KEY["R"]),
            ("W_vs_V5", KEY["W"], KEY["V5"]), ("R0_vs_V5", KEY["R0"], KEY["V5"]),
            ("R_vs_R0", KEY["R"], KEY["R0"])]
    return tuple(out)


def raters_out() -> tuple:
    BT, _B4 = _tools()
    return tuple((KEY[c], f"efv_v5_{c.lower()}") for c in CONFIGS) + (
        (BT.V2_KEY, "efv_v2"), (BT.CONS, "prospx_consensus"),
        ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))


def frame_read(rows: list[dict], *, B: int, log=print) -> dict:
    """Every comparison on the frame (within, pooled, AUC; E_cond, paired), overall and
    per side, plus the position-group cells and the fold deltas of each candidate."""
    BT, _B4 = _tools()
    import efv_v2_stat as S
    t0 = time.time()
    with raters_named(raters_out()):
        blk = BT.frame_block(rows, B=B, stats=("within", "pooled", "auc"),
                             comparisons=comparisons())
    cells = {}
    for side, cell in BT.CELLS:
        sel = [c for c in rows if c["side"] == side and (side == "pit" or c.get("cell") == cell)]
        cb = {"n": len(sel)}
        if len(sel) >= S.MIN_GROUP_ROWS:
            for c in CANDIDATES:
                cb[f"{c}_vs_V5"] = _keep(BT.paired(sel, KEY[c], KEY["V5"], "within", B=B,
                                                   seed=BT.SEED))
                cb[f"{c}_vs_prospx_consensus"] = _keep(BT.paired(sel, KEY[c], BT.CONS, "within",
                                                                 B=B, seed=BT.SEED))
        else:
            cb["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        cells[f"{side}:{cell}"] = cb
    blk["cells"] = cells
    blk["fold_deltas"] = {f"{c}_vs_V5": BT.fold_deltas(rows, KEY[c], KEY["V5"]) for c in CANDIDATES}
    log(f"  stats {round(time.time() - t0, 1)} s")
    return blk


def ship_reading(frames: dict) -> dict:
    """Section 6, per candidate."""
    out = {}
    for c in CANDIDATES:
        per = {}
        tot = n_tot = 0.0
        ok = True
        for fid in ("lv_dev", "vm_dev"):
            f = frames[fid]
            d = f["deltas"][f"{c}_vs_V5"]["spearman"].get("delta")
            n = int(f["n"])
            per[fid] = {"n": n, "delta_vs_V5": d,
                        "delta_vs_consensus": f["deltas"][f"{c}_vs_prospx_consensus"]["spearman"].get("delta"),
                        "ci95_vs_consensus": f["deltas"][f"{c}_vs_prospx_consensus"]["spearman"].get("ci95")}
            if d is None:
                ok = False
                continue
            tot += n * float(d)
            n_tot += n
        pooled = tot / n_tot if n_tot else None
        rule1 = pooled is not None and pooled > 0
        rule2 = all(v["delta_vs_V5"] is not None and v["delta_vs_V5"] >= -MAX_TRAIL
                    for v in per.values())
        out[c] = {"frames": per, "pooled_delta_vs_V5": None if pooled is None else round(pooled, 5),
                  "pooled_rows": int(n_tot), "rule_pooled_above_zero": bool(rule1),
                  "rule_no_frame_trails": bool(rule2), "passes": bool(ok and rule1 and rule2)}
    passing = [c for c in CANDIDATES if out[c]["passes"]]
    prepared = (max(passing, key=lambda c: out[c]["pooled_delta_vs_V5"]) if passing else None)
    return {"rule": ("pooled over lv_dev and vm_dev by row count, within Spearman minus V5 above 0, "
                     f"and minus V5 >= -{MAX_TRAIL} on each frame"),
            "candidates": out, "passing": passing, "prepared": prepared}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()


class Run:
    """One development read: phase 0 (legacy norms: V5 and W), phase 1 (repaired norms:
    R, R0, RT), production fits and the board effect."""

    def __init__(self, *, B: int, log=print, cache_dir: Path | None = None,
                 today: str | None = None):
        self.B = int(B)
        self.log = log
        self.cache = Path(cache_dir) if cache_dir else None
        self.today = today or _today()
        self.t0 = time.time()
        self.doc: dict = {"twins": {}, "pool": {}, "phase0": {}, "phase1": {}}

    # -- caching (an interrupted run resumes from its last built phase) ---------------
    def _load(self, name):
        if self.cache is None:
            return None
        p = self.cache / f"{name}.pkl"
        if p.exists():
            self.log(f"  cache hit {p.name}")
            with p.open("rb") as fh:
                return pickle.load(fh)
        return None

    def _save(self, name, obj):
        if self.cache is None:
            return
        self.cache.mkdir(parents=True, exist_ok=True)
        with (self.cache / f"{name}.pkl").open("wb") as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)

    # -- phase 0: legacy norms ----------------------------------------------------------
    def phase0(self) -> dict:
        got = self._load("phase0")
        if got is not None:
            return got
        BT, _B4 = _tools()
        import efv5_group_drivers as G
        log = self.log
        with pop_repair(False), G.registered(), V5C.v5c_names():
            inp, _frames_lv, _rec = V5C.build_dev(log=log)
            fits = V5C.Fits(inp)
            orders, packs, models = {}, [], {}
            for fid in BT.FRAMES_DEV:
                o, _r = fits.orders(fid, with_head=False)
                orders[fid] = dict(o)
                for side in F.SIDES:
                    for fold, blk in inp.frames[fid]["by_side"][side].items():
                        f = fits.fold(fid, side, fold)
                        cols = (inp.cols.get(fid) or {}).get(side) or {}
                        te = V5C.attach(blk["test"], side, cols, "test")
                        es, et = e_terms(f["model"], te)
                        packs.append(pack(f"{fid}|{side}|{fold}", fid, side, int(fold), te,
                                          blk["scored"], es, et))
                        models[(fid, side, int(fold))] = f["model"]
            scored = {fid: inp.scored(fid) for fid in BT.FRAMES_DEV}
            # the twins of the vm_dev scored test rows, legacy columns, scored by V5's folds
            twin_test = {}
            twin_rec = {}
            for side in F.SIDES:
                keys = {(int(c["year"]), c["key"]) for c in scored["vm_dev"] if c["side"] == side}
                rows = [r for r in H.matrix_training_rows(side)
                        if (int(r["decision_year"]), r["player_key"]) in keys]
                tw, rec = build_twins(side, rows)
                cols, crec = twin_columns(side, tw, today=self.today, log=log)
                twa = attach_slots(tw, side, cols, twin_slot)
                twin_rec[side] = {"twins": rec, "columns": {"families": crec.get("families"),
                                                            "coverage": crec.get("coverage")}}
                o = {}
                for fold in inp.frames["vm_dev"]["by_side"][side]:
                    te = [t for t in twa if int(t["decision_year"]) == int(fold)]
                    if not te:
                        continue
                    m = models[("vm_dev", side, int(fold))]
                    for t, p in zip(te, V5C.predict_combined(m, te)):
                        o[(side, int(fold), t["player_key"])] = float(p["order_idx"])
                twin_test[side] = {"rows": [{"player_key": t["player_key"],
                                             "decision_year": int(t["decision_year"]),
                                             "fv": t["fv"], "twin_point": t["twin_point"]}
                                            for t in tw], "orders": o}
            out = {"orders": orders, "packs": packs, "scored": scored,
                   "twin_test": twin_test, "twin_rec": twin_rec,
                   "label": inp.label, "weights_p5": inp.weights,
                   "receipts": {fid: {f"{s}|{fold}": V5C.fold_receipt(models[(fid, s, fold)], None)
                                      for (f_, s, fold) in models if f_ == fid}
                                for fid in BT.FRAMES_DEV}}
        self._save("phase0", out)
        return out

    # -- phase 1: repaired norms --------------------------------------------------------
    def build1(self) -> dict:
        got = self._load("build1")
        if got is not None:
            return got
        import efv5_group_drivers as G
        log = self.log
        with G.registered(), V5C.v5c_names():
            inp, frames_lv, _rec = V5C.build_dev(log=log)
            pool, prec = lv_pool(frames_lv, log=log)
            prod, twins, trec = {}, {}, {}
            for side in F.SIDES:
                prod[side] = V5C.production_train(side, log=log)
                base = [r for r in H.matrix_training_rows(side)
                        if int(r["decision_year"]) < F.train_end_year()]
                tw, rec = build_twins(side, base)
                cols, crec = twin_columns(side, tw, today=self.today, log=log)
                twins[side] = attach_slots(tw, side, cols, twin_slot)
                trec[side] = {"twins": rec, "columns": {"families": crec.get("families"),
                                                        "coverage": crec.get("coverage")}}
            live_rec = {}
            for side in F.SIDES:
                live_rec[side] = live_dark(side, today=self.today)
        out = {"inp": inp, "pool": pool, "pool_rec": prec, "prod": prod, "twins": twins,
               "twin_rec": trec, "live_dark": live_rec}
        self._save("build1", out)
        return out

    def _fit(self, cfg: dict, side: str, skill_rows, skill_frame, timing_rows, timing_frame,
             *, with_se=False) -> dict:
        if cfg["transform"]:
            skill_rows = rank_transform(skill_rows, side)
        sk = refit_candidates(side, "skill", dark=cfg["dark"])
        tm = refit_candidates(side, "timing", dark=cfg["dark"])
        return fit_heads(skill_rows, skill_frame, timing_rows, timing_frame, side,
                         cands_skill=sk, cands_timing=tm,
                         timing_outcome_blind=False, with_se=with_se)

    def fold_packs(self, name: str, b1: dict, *, design: str = "FC") -> tuple[list, dict]:
        """Every development fold of the configuration: (packs on the test rows, receipts)."""
        BT, _B4 = _tools()
        cfg = CONFIGS[name]
        inp, pool, prod, twins = b1["inp"], b1["pool"], b1["prod"], b1["twins"]
        packs, rec = [], {}
        for fid in BT.FRAMES_DEV:
            kind = BT.FRAME_KIND[fid]
            for side in F.SIDES:
                cols = (inp.cols.get(fid) or {}).get(side) or {}
                for fold, blk in inp.frames[fid]["by_side"][side].items():
                    t1 = time.time()
                    te = V5C.attach(blk["test"], side, cols, "test")
                    test_keys = {r["player_key"] for r in te}
                    Y = int(fold)
                    if design == "FC":
                        tr = V5C.attach(blk["train"], side, cols, "train")
                        if fid == "vm_dev" and cfg["twins"]:
                            tr = tr + [t for t in twins[side] if int(t["decision_year"]) < Y]
                        if fid == "lv_dev":
                            tim = V5C.attach(blk["train"], side, cols, "train")
                        else:
                            tim = lv_timing_rows(pool[side], last=min(LV_POOL_LAST, Y - 1),
                                                 leave_out=test_keys)
                    else:   # LOYO (section 4 sensitivity)
                        if fid == "lv_dev":
                            tr = [r for r in pool[side] if int(r["decision_year"]) != Y
                                  and r["player_key"] not in test_keys]
                            tim = tr
                        else:
                            last = vm_dev_last()
                            tr = [r for r in prod[side] if int(r["decision_year"]) != Y
                                  and int(r["decision_year"]) <= last]
                            if cfg["twins"]:
                                tr = tr + [t for t in twins[side] if int(t["decision_year"]) != Y
                                           and int(t["decision_year"]) <= last]
                            tim = lv_timing_rows(pool[side], last=LV_POOL_LAST,
                                                 leave_out=test_keys)
                    m = self._fit(cfg, side, tr, kind, tim, "lv")
                    te_x = rank_transform(te, side) if cfg["transform"] else te
                    es, et = e_terms(m, te_x)
                    fid_ = f"{fid}|{side}|{fold}"
                    packs.append(pack(fid_, fid, side, Y, te, blk["scored"], es, et, model=m))
                    rec[fid_] = {"n_train_skill": m["n_train"], "n_train_timing": m["n_train_timing"],
                                 "timing_years": [min(m["timing_train_years"] or [0]),
                                                  max(m["timing_train_years"] or [0])],
                                 "twins_in_skill": sum(1 for r in tr if r.get("twin")),
                                 "lam": {h: V5C._lam_str(v) for h, v in m["config"]["lam"].items()},
                                 "skill_keys": (m["skill"] or {}).get("keys"),
                                 "skill_nonzero": [k for k, b in zip((m["skill"] or {}).get("keys") or [],
                                                                     (m["skill"] or {}).get("beta") or [])
                                                   if b != 0.0],
                                 "timing_nonzero": [k for k, b in zip((m["timing"] or {}).get("keys") or [],
                                                                      (m["timing"] or {}).get("beta") or [])
                                                    if b != 0.0],
                                 "consensus_only_reason": m.get("consensus_only_reason"),
                                 "seconds": round(time.time() - t1, 1)}
                    self.log(f"  {name} {design} {fid_}: {len(tr)} skill rows, {len(tim)} timing rows "
                             f"({rec[fid_]['seconds']} s)")
        return packs, rec

    def production(self, name: str, b1: dict, weights: dict) -> dict:
        cfg = CONFIGS[name]
        out = {}
        for side in F.SIDES:
            tr = list(b1["prod"][side])
            if cfg["twins"]:
                tr = tr + list(b1["twins"][side])
            tim = lv_timing_rows(b1["pool"][side], last=LV_POOL_LAST, leave_out=set())
            m = self._fit(cfg, side, tr, "vm", tim, "lv", with_se=True)
            w = weights[side]
            m["w_skill"] = float(w["w_skill"]) if H.head_usable(m["skill"]) else 0.0
            m["w_time"] = float(w["w_time"]) if H.head_usable(m["timing"]) else 0.0
            m["w_skill_unscaled"], m["w_time_unscaled"] = m["w_skill"], m["w_time"]
            m["consensus_only"] = m["w_skill"] <= 0 and m["w_time"] <= 0
            if m["consensus_only"] and m.get("consensus_only_reason") is None:
                m["consensus_only_reason"] = "no usable head carries a positive re-derived weight"
            base = list(b1["prod"][side])
            m["war_map"] = H.fit_war_map(base)
            m["war_map_6yr"] = H.fit_war_map(base)
            m["refit"] = {"item": ITEM, "candidate": name, "transform": bool(cfg["transform"]),
                          "twins": sum(1 for r in tr if r.get("twin"))}
            m["refit_transform"] = bool(cfg["transform"])
            out[side] = m
            self.log(f"  production {name} {side}: {len(tr)} skill rows, {len(tim)} timing rows")
        return out


def vm_dev_last() -> int:
    """The last decision year of the vm_dev frame (2023): leave-one-year-out on vm_dev
    trains on decision years 2011 to this year but the test year (the document, s4)."""
    return int(F.train_end_year()) - 2


def live_dark(side: str, *, today: str) -> dict:
    """The live read's dark and withheld columns (the receipt A2 is checked against)."""
    import efv_dataset as D
    import efv_v2_serve as S
    live = json.loads(D.live_matrix_path(side).read_text(encoding="utf-8"))
    rec: dict = {}
    V5C.live_columns(side, S.live_rows(side, live, today=today), today=today,
                     raw_by_key={r["player_key"]: r for r in live if r.get("player_key")},
                     receipt=rec, log=lambda *_a, **_k: None)
    cands = V5C.candidates()
    by_key = {c["key"]: n for n, c in cands.items()}
    dark = set()
    for fam, note in (rec.get("families") or {}).items():
        names = [n for n in V5C.side_candidates(side) if V5C._family_of(n) == fam]
        if note.get("status") == "dark":
            dark |= set(names)
        else:
            dark |= set(note.get("dark_columns") or [])
    for k, s in (rec.get("support") or {}).items():
        if s.get("withheld"):
            dark.add(by_key.get(k, k))
    return {"dark": sorted(dark),
            "registered": sorted(n for n in DARK if V5C.candidates()[n]["side"] == side),
            "families": {f: n.get("status") for f, n in (rec.get("families") or {}).items()}}


# ---------------------------------------------------------------------------
# the board effect (section 8)
# ---------------------------------------------------------------------------

def score_board(side: str, model: dict, *, today: str) -> dict:
    """{player_key: {"grade", "order_idx", "fv", "rank", "chips"}} for the live board of
    the side under `model` (efv_v2_serve's rows, the live candidate columns, the variant's
    rank where the model carries it)."""
    import efv_dataset as D
    import efv_v2_serve as S
    live = json.loads(D.live_matrix_path(side).read_text(encoding="utf-8"))
    rows = S.live_rows(side, live, today=today)
    rows = S._with_live_candidates(side, rows, live, model, today)   # RT ranks here
    preds = H.predict_v2(model, rows)
    parts = S._chip_parts(model, rows)
    order = sorted(range(len(preds)), key=lambda i: (-preds[i]["order_idx"], preds[i]["player_key"]))
    rank = {i: k + 1 for k, i in enumerate(order)}
    return {r["player_key"]: {"grade": float(p["efv_grade"]), "order_idx": float(p["order_idx"]),
                              "fv": float(r["fv"]), "rank": rank[i],
                              "chips": S.driver_chips(parts[i])[:6]}
            for i, (r, p) in enumerate(zip(rows, preds))}


def board_effect(new: dict[str, dict], *, xfv_path: Path | None = None) -> dict:
    """Section 8: served (data/xfv.json) against the candidate's board."""
    doc = json.loads((xfv_path or DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    bp = doc["by_player"]
    out = {}
    for side, got in new.items():
        served = {}
        for pk, r in bp.items():
            e = (r or {}).get("efv_v2") or {}
            if (e.get("group") or [None])[0] == side and r.get("grade_basis") == "efv_v2":
                served[pk] = {"grade": float(r["xfv_grade"]), "rank": int(e["order_rank"]),
                              "fv": float(r["consensus_fv"]),
                              "chips": [{"driver": f.get("driver"), "dir": f.get("dir"),
                                         "mag": f.get("mag")} for f in (r.get("factors") or [])
                                        if f.get("driver")][:6]}
        both = sorted(set(served) & set(got))
        d_old = np.asarray([abs(served[k]["grade"] - served[k]["fv"]) for k in both])
        d_new = np.asarray([abs(got[k]["grade"] - got[k]["fv"]) for k in both])
        mv = sorted(both, key=lambda k: (-abs(got[k]["grade"] - served[k]["grade"]), k))
        moved = np.asarray([abs(got[k]["grade"] - served[k]["grade"]) for k in both])
        top = []
        for k in mv[:50]:
            top.append({"player_key": k, "consensus": round(served[k]["fv"], 1),
                        "served": round(served[k]["grade"], 1), "refit": round(got[k]["grade"], 1),
                        "served_rank": served[k]["rank"], "refit_rank": got[k]["rank"]})
        old_top = {k for k in both if served[k]["rank"] <= 50}
        new_top = {k for k in both if got[k]["rank"] <= 50}
        out[side] = {"n": len(both),
                     "mean_abs_efv_minus_consensus": {"served": round(float(d_old.mean()), 3),
                                                      "refit": round(float(d_new.mean()), 3)},
                     "moved_1_or_more": int(np.sum(moved >= 1.0 - 1e-9)),
                     "moved_3_or_more": int(np.sum(moved >= 3.0 - 1e-9)),
                     "max_move": round(float(moved.max()), 1) if moved.size else None,
                     "top50_kept": len(old_top & new_top),
                     "top_movers": top}
        if side == "hit" and "nelson_rada" in served and "nelson_rada" in got:
            out[side]["nelson_rada"] = {"served": served["nelson_rada"],
                                        "refit": {k: v for k, v in got["nelson_rada"].items()}}
    return out


# ---------------------------------------------------------------------------
# serialization of a production fit (the weights file the served path reads)
# ---------------------------------------------------------------------------

_HEAD_FIELDS = ("keys", "means", "alpha", "lam", "mu", "sd", "b0", "b_uc", "beta", "n_train",
                "trained_on", "design", "score_sd", "trained_frame", "v2_keys",
                "candidate_columns", "zero_candidates")


def _enc(v):
    if isinstance(v, float) and math.isinf(v):
        return "inf"
    return v


def _dec(v):
    return math.inf if v == "inf" else v


def head_out(head: dict | None) -> dict | None:
    if head is None:
        return None
    return {k: _enc(head[k]) for k in _HEAD_FIELDS if k in head}


def head_in(d: dict | None) -> dict | None:
    if d is None:
        return None
    out = dict(d)
    for k in ("alpha", "lam"):
        if k in out:
            out[k] = _dec(out[k])
    return out


def model_out(m: dict) -> dict:
    return {"model_id": m["model_id"], "side": m["side"], "frame": m["frame"],
            "timing_frame": m.get("timing_frame"), "w_skill": m["w_skill"], "w_time": m["w_time"],
            "consensus_only": m["consensus_only"],
            "consensus_only_reason": m.get("consensus_only_reason"),
            "skill": head_out(m.get("skill")), "timing": head_out(m.get("timing")),
            "war_map": m.get("war_map"), "war_map_6yr": m.get("war_map_6yr"),
            "n_train": m["n_train"], "n_train_timing": m.get("n_train_timing"),
            "train_years": m.get("train_years"), "timing_train_years": m.get("timing_train_years"),
            "config": {"lam": {h: _enc(v) for h, v in (m.get("config") or {}).get("lam", {}).items()}},
            "refit": m.get("refit"), "refit_transform": bool(m.get("refit_transform"))}


def model_in(d: dict) -> dict:
    m = dict(d)
    m["skill"] = head_in(d.get("skill"))
    m["timing"] = head_in(d.get("timing"))
    m["w_skill_unscaled"], m["w_time_unscaled"] = m["w_skill"], m["w_time"]
    m["config"] = {"lam": {h: _dec(v) for h, v in ((d.get("config") or {}).get("lam") or {}).items()}}
    return m


def production_models(path: Path | None = None) -> dict[str, dict]:
    """The served re-fit (efv_v2_serve.production_models reads this while EFV_V5_REFIT_ON
    is True): the production fit stored by the run, as read. Refuses unless the stored
    read PREPARED a candidate and the population norms flag moves with this one."""
    import efv_w2_popmle as PM
    if bool(PM.POP_REPAIR_ON) != bool(EFV_V5_REFIT_ON):
        raise RuntimeError("efv_w2_popmle.POP_REPAIR_ON must equal efv5_refit.EFV_V5_REFIT_ON "
                           "(docs/efv-v2/EFV_FIX_A.md s2: the norms repair never flips alone)")
    doc = json.loads((path or WEIGHTS_PATH).read_text(encoding="utf-8"))
    cand = served_candidate(doc)
    return {s: model_in(m) for s, m in doc["models_by_candidate"][cand].items()}


def served_candidate(doc: dict) -> str:
    """The candidate the flag serves: SERVE_CANDIDATE, else the prepared one; refuses an
    unprepared read and a candidate that did not pass the ship rule."""
    if not doc.get("prepared"):
        raise RuntimeError(f"{WEIGHTS_PATH.name}: no candidate passed the ship rule of {DOC}; "
                           "nothing is prepared to serve")
    cand = SERVE_CANDIDATE or doc["candidate"]
    if cand not in (doc.get("passing") or []):
        raise RuntimeError(f"candidate {cand!r} did not pass the ship rule of {DOC}")
    return cand


# ---------------------------------------------------------------------------
# the served claim, re-derived (section 7)
# ---------------------------------------------------------------------------

def claim_from(frames: dict, cand_key: str, *, date_: str, model_id: str = SERVED_MODEL_ID,
               source: str) -> dict:
    """The claim word and text from a development read's frames: vm_dev decides the word
    ('trails' when its CI95 against consensus lies below 0, else 'ties'; a development
    frame never reads 'leads'), lv_dev stated beside it."""
    vm = frames["vm_dev"][cand_key]
    lv = frames["lv_dev"][cand_key]
    d, ci = vm.get("delta"), vm.get("ci95")
    word = "trails" if (isinstance(ci, list) and len(ci) == 2 and ci[1] is not None
                        and ci[1] < 0) else "ties"

    def part(x, label):
        c = x.get("ci95") or [None, None]
        return (f"{x.get('delta'):+.4f} (CI95 {c[0]:+.3f} to {c[1]:+.3f}) on {label} "
                f"(n {x.get('n')})")
    text = (f"{'Ties' if word == 'ties' else 'Trails'} PROSPX consensus on the development "
            f"frames: within Spearman difference {part(vm, 'the vintage-matched frame')} and "
            f"{part(lv, 'list vintages 2017 to 2019')}; development reads ({date_}).")
    return {"word": word, "model_id": model_id, "frame": "vm_dev", "delta": d, "ci95": ci,
            "n": vm.get("n"), "lv_dev": {"delta": lv.get("delta"), "ci95": lv.get("ci95"),
                                         "n": lv.get("n")},
            "resolvable": bool(isinstance(ci, list) and ci[1] is not None and ci[1] < 0),
            "date": date_, "reserved_read": False, "text": text, "source": source}


def served_claim() -> dict:
    """The claim the board prints while EFV_V5_REFIT_ON is True, derived from the re-fit's
    weights file (its own development read, copied there from the fit artifact)."""
    doc = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    return dict(doc["claims_by_candidate"][served_candidate(doc)])


def weights_doc(doc: dict, prod_models: dict) -> dict:
    """data/efv5_refit_weights.json from the fit artifact's document and the production
    fits of the candidates ({candidate: {side: model}})."""
    ship = doc["ship"]
    prepared = ship["prepared"]
    cand = prepared or "R"
    w_of = (lambda c: {s: {k: doc["weights"][c][s][k] for k in
                           ("w_skill", "w_time", "w_skill_ratio", "w_time_ratio", "n")}
                       for s in F.SIDES})
    ci_of = (lambda c: {s: {k: ((doc["weights_bootstrap"][c][s] or {}).get(k) or {}).get("ci95")
                            for k in ("w_skill", "w_time", "w_skill_ratio", "w_time_ratio")}
                        for s in F.SIDES})
    return {"schema": 2, "model_id": SERVED_MODEL_ID, "item": ITEM, "produced_by": TOOL,
            "generated_at": doc["generated_at"], "doc": DOC,
            "fit_artifact": FIT_PATH.relative_to(ROOT).as_posix(),
            "prepared": bool(prepared), "candidate": cand, "passing": list(ship["passing"]),
            "served": False, "flag": "efv5_refit.EFV_V5_REFIT_ON",
            "note": ("the production fit of every re-fit candidate as read; the flag serves the "
                     "prepared candidate (or efv5_refit.SERVE_CANDIDATE among the passing) only "
                     "when the owner flips EFV_V5_REFIT_ON (with efv_w2_popmle.POP_REPAIR_ON)"
                     + ("" if prepared else "; NOT PREPARED: no candidate passed the ship rule")),
            "weights": w_of(cand), "weights_ci95": ci_of(cand),
            "weights_by_candidate": {c: w_of(c) for c in prod_models},
            "weights_ci95_by_candidate": {c: ci_of(c) for c in prod_models},
            "models_by_candidate": {c: {s: model_out(m) for s, m in ms.items()}
                                    for c, ms in prod_models.items()},
            "claim": doc["claim_prepared"],
            "claims_by_candidate": {c: doc["claims"][c] for c in prod_models},
            "code": doc["code"]}


def store_weights(*, cache_dir: Path, log=print) -> dict:
    """Rewrite data/efv5_refit_weights.json from the fit artifact and the run's cached
    builds (the production fits are deterministic; nothing is read or scored)."""
    BT, _B4 = _tools()
    doc = json.loads(FIT_PATH.read_text(encoding="utf-8"))
    R = Run(B=0, log=log, cache_dir=cache_dir)
    b1 = R._load("build1")
    if b1 is None:
        raise RuntimeError("the cached builds of the read are needed")
    with pop_repair(True):
        prod = {c: R.production(c, b1, {s: doc["weights"][c][s] for s in F.SIDES})
                for c in CANDIDATES}
    w = weights_doc(doc, prod)
    BT.write_doc(w, WEIGHTS_PATH)
    log(f"wrote {WEIGHTS_PATH}")
    return w


# ---------------------------------------------------------------------------
# documents and the ledger
# ---------------------------------------------------------------------------

def _code() -> dict:
    BT, _B4 = _tools()
    return {"commit": BT._commit(), "tool": TOOL, "tool_sha256": BT._sha(ROOT / TOOL),
            "efv5_combined_sha256": BT._sha(ROOT / "efv5_combined.py"),
            "efv_w2_popmle_sha256": BT._sha(ROOT / "efv_w2_popmle.py"),
            "efv_v2_model_sha256": BT._sha(ROOT / "efv_v2_model.py"),
            "doc": DOC, "doc_sha256": BT._sha(ROOT / DOC)}


def _pack_weights(packs: list[dict]) -> dict:
    out = {}
    for side in F.SIDES:
        mine = [p for p in packs if p["side"] == side]
        w = weights_from(mine)
        w["by_frame"] = {fid: {k: weights_from([p for p in mine if p["fid"] == fid]).get(k)
                               for k in ("w_skill_ratio", "w_time_ratio", "n")}
                         for fid in ("lv_dev", "vm_dev")}
        out[side] = w
    return out


def orders_from(packs: list[dict], weights_cf: dict, scored_keys: dict) -> dict:
    """{fid: {(side, fold, key): order}} on the scored rows of each frame with each
    fold's cross-fitted weights (keyed inside the frame: see frame_rows)."""
    out: dict = {}
    for p in packs:
        w = weights_cf[p["side"]][p["fold_id"]]
        o = p["u_c"] + w["w_skill"] * p["e_s"] + w["w_time"] * p["e_t"]
        mine = out.setdefault(p["fid"], {})
        for k, v in zip(p["keys"], o):
            if (p["side"], p["fold"], k) in scored_keys[p["fid"]]:
                mine[(p["side"], p["fold"], k)] = float(v)
    return out


def grid_read(packs: list[dict], scored: dict, w_time_est: dict) -> dict:
    """Section 4 objective, descriptive: pooled within Spearman of one configuration's
    heads at fixed weights (w_skill on GRID_SKILL; w_time 0 and its estimate)."""
    out = {}
    for side in F.SIDES:
        mine = [p for p in packs if p["side"] == side]
        res = []
        for wt in sorted({0.0, round(float(w_time_est[side]), 4)}):
            for ws in GRID_SKILL:
                tot = n_tot = 0.0
                per = {}
                for fid in ("lv_dev", "vm_dev"):
                    od = {}
                    for p in mine:
                        if p["fid"] != fid:
                            continue
                        o = p["u_c"] + ws * p["e_s"] + wt * p["e_t"]
                        for k, v in zip(p["keys"], o):
                            od[(side, p["fold"], k)] = float(v)
                    rows = [dict(c, grades=dict(c["grades"], _g=od[(c["side"], int(c["year"]), c["key"])]))
                            for c in scored[fid] if c["side"] == side
                            and (c["side"], int(c["year"]), c["key"]) in od]
                    w = within_of(rows, "_g")
                    per[fid] = w["within"]
                    if w["within"] is not None:
                        tot += w["n"] * w["within"]
                        n_tot += w["n"]
                res.append({"w_skill": ws, "w_time": wt, "lv_dev": per["lv_dev"],
                            "vm_dev": per["vm_dev"],
                            "pooled": None if not n_tot else round(tot / n_tot, 5)})
        out[side] = res
    return out


def twin_read(p0: dict, packs: dict, weights_cf: dict, b1: dict, scored_vm: list[dict], *,
              B: int) -> dict:
    """Section 5, the live-timing read on vm_dev: each scored test row read as its twin."""
    BT, _B4 = _tools()
    twins = b1["twins"]
    out = {"note": ("vm_dev scored test rows read as their live-timing twins (A4); "
                    "secondary, decides nothing")}
    rows = []
    for side in F.SIDES:
        tw = {(int(t["decision_year"]), t["player_key"]): t for t in twins[side]}
        v5 = p0["twin_test"][side]["orders"]
        by_fold: dict = {}
        for c in scored_vm:
            if c["side"] != side:
                continue
            t = tw.get((int(c["year"]), c["key"]))
            if t is None or (side, int(c["year"]), c["key"]) not in v5:
                continue
            by_fold.setdefault(int(c["year"]), []).append((c, t))
        for Y, items in sorted(by_fold.items()):
            te = [t for _c, t in items]
            g = {}
            for name in CANDIDATES:
                pk = [p for p in packs[name] if p["fid"] == "vm_dev" and p["side"] == side
                      and p["fold"] == Y]
                if not pk:
                    continue
                m = pk[0]["model"]
                te_x = rank_transform(te, side) if CONFIGS[name]["transform"] else te
                es, et = e_terms(m, te_x)
                uc, _uy = H._percentiles([dict(t, target=0.0) for t in te])
                w = weights_cf[name][side][f"vm_dev|{side}|{Y}"]
                g[name] = uc + w["w_skill"] * es + w["w_time"] * et
            for i, (c, t) in enumerate(items):
                gr = {BT.CONS: float(t["fv"]), KEY["V5"]: v5[(side, Y, c["key"])]}
                for name in g:
                    gr[KEY[name]] = float(g[name][i])
                rows.append(dict(c, grades=gr))
    out["n"] = len(rows)
    out["n_by_side"] = {s: sum(1 for r in rows if r["side"] == s) for s in F.SIDES}
    blk = {}
    for scope in ("both", "hit", "pit"):
        sel = rows if scope == "both" else [r for r in rows if r["side"] == scope]
        b = {"n": len(sel)}
        for name in CANDIDATES:
            b[f"{name}_vs_V5"] = _keep(BT.paired(sel, KEY[name], KEY["V5"], "within", B=B, seed=BT.SEED))
            b[f"{name}_vs_twin_consensus"] = _keep(BT.paired(sel, KEY[name], BT.CONS, "within", B=B,
                                                             seed=BT.SEED))
        b["V5_vs_twin_consensus"] = _keep(BT.paired(sel, KEY["V5"], BT.CONS, "within", B=B,
                                                    seed=BT.SEED))
        for k in [KEY[c] for c in ("V5",) + CANDIDATES] + [BT.CONS]:
            b.setdefault("raters", {})[k] = within_of(sel, k)
        blk[scope] = b
    out["read"] = blk
    return out


def ledger_rows(doc: dict, cand: str, *, artifact: Path, date_: str, now_iso: str) -> list[dict]:
    """Two development rows (model efv_v5_refit, the candidate read), as the v5 fit wrote."""
    import efv_progress as P
    import efv_v2_stat as S
    BT, _B4 = _tools()
    lab = doc.get("label") or {}
    mv = {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    raters_map = (("efv", f"efv_v5_{cand.lower()}"), ("efv_v5_base", "efv_v5_v5"),
                  ("prospx_consensus", "prospx_consensus"), ("mlb_pipeline", "mlb_pipeline"),
                  ("fangraphs", "fangraphs"))
    deltas_map = (("vs_efv_v5_base", f"{cand}_vs_V5"),
                  ("vs_prospx_consensus", f"{cand}_vs_prospx_consensus"),
                  ("vs_mlb_pipeline", f"{cand}_vs_mlb_pipeline"),
                  ("vs_fangraphs", f"{cand}_vs_fangraphs"),
                  ("efv_v5_base_vs_prospx_consensus", "V5_vs_prospx_consensus"))
    rows = []
    for fid in ("lv_dev", "vm_dev"):
        f = doc["frames"][fid]
        meta = P.FRAMES[fid]
        if meta["role"] != "development":
            raise ValueError(f"{fid} is registered as {meta['role']}, not development")
        raters = {}
        for name, key in raters_map:
            r = (f.get("raters") or {}).get(key) or {}
            if r.get("spearman") is None and r.get("auc") is None:
                continue
            raters[name] = {"spearman": r.get("spearman"), "auc": r.get("auc"), "n": r.get("n")}
        deltas = {}
        for name, comp in deltas_map:
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
        w = f["deltas"][f"{cand}_vs_V5"]["spearman"]
        c = f["deltas"][f"{cand}_vs_prospx_consensus"]["spearman"]
        row = {"run_id": None, "date": date_, "trigger": "efv_change", "model_id": LEDGER_MODEL_ID,
               "model_version": dict(mv), "frame": fid, "frame_version": f.get("frame_version"),
               "role": meta["role"], "tilted": bool(meta["tilted"]),
               "window": f.get("window"), "n": f.get("n"), "n_by_side": nbs, "raters": raters,
               "deltas": deltas, "resolvable": None,
               "verdict": (f"DEVELOPMENT ONLY (the re-fit {cand}, weights cross-fitted on these "
                           f"frames): within vs eFV v5 COMBINED as served {BT._rnd(w.get('delta'), 4)} "
                           f"(CI95 {w.get('ci95')}), vs consensus {BT._rnd(c.get('delta'), 4)} "
                           f"(CI95 {c.get('ci95')}); adjudicates nothing"),
               "share": None, "sources": [dict(s) for s in src],
               "note": (f"eFV v5 COMBINED re-fit ({ITEM}, candidate {cand}; {DOC}); development "
                        "read, adjudicates nothing"),
               "last_verified_at": now_iso, "statistic": S.STAT_LABEL[S.PRIMARY]}
        P._finish(row)
        row["run_id"] = f"{doc.get('generated_at')}|{fid}|{row['content_hash'][:8]}"
        rows.append(row)
    return rows


def append_ledger(doc: dict, cand: str, *, artifact: Path, ledger_path: Path) -> dict:
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    rows = ledger_rows(doc, cand, artifact=artifact, date_=now.date().isoformat(), now_iso=now_iso)
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    return P.commit_rows(rows, data_dir=P.DATA_DIR, ledger_path=Path(ledger_path),
                         sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)


def _jsonable_packs_receipt(rec: dict) -> dict:
    return rec


def run(*, B: int, log=print, cache_dir: Path | None = None, today: str | None = None) -> dict:
    """The registered read, once (section 3 to 8)."""
    import efv_labels as L
    BT, _B4 = _tools()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    R = Run(B=B, log=log, cache_dir=cache_dir, today=today)
    t0 = time.time()
    log("phase 0: legacy norms (V5, W)")
    p0 = R.phase0()
    with pop_repair(True):
        log("phase 1: repaired norms (R, R0, RT)")
        b1 = R.build1()
        inp = b1["inp"]
        for fid in BT.FRAMES_DEV:
            k0 = sorted((c["side"], int(c["year"]), c["key"]) for c in p0["scored"][fid])
            k1 = sorted((c["side"], int(c["year"]), c["key"]) for c in inp.scored(fid))
            if k0 != k1:
                raise RuntimeError(f"{fid}: the scored rows differ between the two builds")
        packs = {"W": p0["packs"]}
        recs = {}
        for name in ("R", "R0", "RT"):
            got = R._load(f"packs_{name}")
            if got is None:
                got = R.fold_packs(name, b1, design="FC")
                R._save(f"packs_{name}", got)
            packs[name], recs[name] = got
        got = R._load("packs_R_LOYO")
        if got is None:
            got = R.fold_packs("R", b1, design="LOYO")
            R._save("packs_R_LOYO", got)
        loyo_packs, loyo_rec = got
        # section 4: the weights
        weights, weights_cf, boots = {}, {}, {}
        for name, pk in packs.items():
            weights[name] = _pack_weights(pk)
            weights_cf[name] = {s: cross_fitted([p for p in pk if p["side"] == s]) for s in F.SIDES}
            boots[name] = {s: boot_weights([p for p in pk if p["side"] == s]) for s in F.SIDES}
        loyo_w = _pack_weights(loyo_packs)
        scored_keys = {fid: {(c["side"], int(c["year"]), c["key"]) for c in inp.scored(fid)}
                       for fid in BT.FRAMES_DEV}
        orders = {"V5": p0["orders"]}
        for name in ("W", "R", "R0", "RT"):
            orders[name] = orders_from(packs[name], weights_cf[name], scored_keys)
        # section 3: V5 must reproduce the committed development read before anything is read
        v5fit = json.loads((LAB_DIR / "efv5_combined_fit.json").read_text(encoding="utf-8"))
        parity = {}
        for fid in BT.FRAMES_DEV:
            rows = frame_rows(inp, fid, orders)
            got = within_of(rows, KEY["V5"])["within"]
            want = v5fit["frames"][fid]["raters"]["efv_v5_combined"]["within"]
            parity[fid] = {"recomputed": got, "committed": want}
            if got is None or abs(float(got) - float(want)) > 5e-5:
                raise RuntimeError(f"V5 does not reproduce the committed development read on "
                                   f"{fid}: {got} against {want}; nothing is read")
        log(f"V5 reproduces the committed development read: {parity}")
        frames = {}
        for fid in BT.FRAMES_DEV:
            rows = frame_rows(inp, fid, orders)
            log(f"{fid}: {len(rows)} scored rows")
            frames[fid] = frame_read(rows, B=B, log=log)
            frames[fid]["window"] = [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])]
            frames[fid]["frame_version"] = BT.FRAME_VERSION[fid]
        ship = ship_reading(frames)
        grid = {name: grid_read(packs[name], {fid: inp.scored(fid) for fid in BT.FRAMES_DEV},
                                {s: weights[name][s]["w_time"] for s in F.SIDES})
                for name in ("R", "RT", "W")}
        twin = twin_read(p0, packs, weights_cf, b1, inp.scored("vm_dev"), B=B)
        # production fits and the board effect
        prod_models, boards = {}, {}
        for name in CANDIDATES:
            prod_models[name] = R.production(name, b1, {s: weights[name][s] for s in F.SIDES})
            got = {s: score_board(s, prod_models[name][s], today=R.today) for s in F.SIDES}
            boards[name] = board_effect(got)
        tables = {name: {s: V5C.weights_table(prod_models[name][s]) for s in F.SIDES}
                  for name in CANDIDATES}
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": BT._now(),
           "role": "development", "adjudicates": False, "doc": DOC,
           "owner_decision": "EW3-21 (2026-10-15)", "label": p0["label"],
           "weights_p5": p0["weights_p5"], "code": _code(),
           "configs": CONFIGS, "dark": list(DARK), "v5_parity": parity,
           "live_dark_receipt": b1["live_dark"],
           "twins": b1["twin_rec"], "twins_test_legacy": p0["twin_rec"],
           "timing_pool": b1["pool_rec"],
           "weights": {name: {s: {k: v for k, v in weights[name][s].items()} for s in F.SIDES}
                       for name in weights},
           "weights_bootstrap": boots,
           "weights_cross_fitted": weights_cf,
           "weights_loyo_R": loyo_w,
           "fold_receipts": {name: recs[name] for name in recs},
           "fold_receipts_loyo_R": loyo_rec, "fold_receipts_V5": p0["receipts"],
           "frames": frames, "ship": ship, "objective_grid": grid, "live_timing_read": twin,
           "production": {name: {"driver_tables": tables[name],
                                 "lam": {s: {h: V5C._lam_str(v) for h, v in
                                             prod_models[name][s]["config"]["lam"].items()}
                                         for s in F.SIDES}} for name in CANDIDATES},
           "board": boards, "elapsed_s": round(time.time() - t0, 1)}
    prepared = ship["prepared"]
    claims = {}
    for name in CANDIDATES:
        cf = {fid: dict(frames[fid]["deltas"][f"{name}_vs_prospx_consensus"]["spearman"],
                        n=frames[fid]["n"]) for fid in BT.FRAMES_DEV}
        claims[name] = claim_from({fid: {"x": cf[fid]} for fid in cf}, "x", date_=R.today,
                                  source=f"{FIT_PATH.relative_to(ROOT).as_posix()} ({name})")
    cf5 = {fid: dict(v5fit["frames"][fid]["deltas"]["v5c_vs_prospx_consensus"]["spearman"],
                     n=v5fit["frames"][fid]["n"]) for fid in BT.FRAMES_DEV}
    claims["V5_committed"] = claim_from({fid: {"x": cf5[fid]} for fid in cf5}, "x",
                                        date_=v5fit["generated_at"][:10],
                                        source="data/_labs/efv5/efv5_combined_fit.json")
    doc["claims"] = claims
    doc["claim_prepared"] = claims[prepared] if prepared else claims["V5_committed"]
    BT.write_doc(doc, FIT_PATH)
    BT.write_doc(weights_doc(json.loads(json.dumps(doc, default=str)), prod_models), WEIGHTS_PATH)
    log(f"wrote {FIT_PATH} and {WEIGHTS_PATH} ({round(time.time() - t0, 1)} s)")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--cache", default=None, help="a scratch directory for resumable builds")
    ap.add_argument("--ledger", action="store_true",
                    help="append the read's two development rows to data/efv_progress.json")
    ap.add_argument("--ledger-path", default=None)
    ap.add_argument("--store-weights", action="store_true",
                    help="rewrite data/efv5_refit_weights.json from the read and its cache")
    a = ap.parse_args(argv)
    BT, _B4 = _tools()

    def log(msg):
        print(msg, flush=True)
    if a.ledger:
        if not FIT_PATH.exists():
            log("refused: the fit artifact does not exist")
            return 2
        doc = json.loads(FIT_PATH.read_text(encoding="utf-8"))
        cand = doc["ship"]["prepared"] or "R"
        led = Path(a.ledger_path) if a.ledger_path else (ROOT / ".cache" / "efv5_refit"
                                                         / "progress_ledger.jsonl")
        r = append_ledger(doc, cand, artifact=FIT_PATH, ledger_path=led)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if a.store_weights:
        if not (FIT_PATH.exists() and a.cache):
            log("refused: the fit artifact and --cache are needed")
            return 2
        store_weights(cache_dir=Path(a.cache), log=log)
        return 0
    if a.run:
        if FIT_PATH.exists():
            log(f"refused: {FIT_PATH} exists; the registered read runs once")
            return 2
        B = BT.B_DEFAULT if a.B is None else int(a.B)
        run(B=B, log=log, cache_dir=Path(a.cache) if a.cache else None)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

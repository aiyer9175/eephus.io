# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV tool inputs on eTools (EFV_ETOOLS_REWEIGHT; owner decision EW3-26, 2026-10-15;
method docs/efv-v2/EFV_ETOOLS_REWEIGHT.md, committed alone before this module).

THE ETOOL ON AN eFV ROW (the document, section 2). For tool T, a fit Phi (lines a_j, b_j;
slopes c_j) is etools.etool_fit on the eTools frame of T restricted to a training mask; on a
row with an observed consensus grade g and sub-drivers Z_j:

    eT = clip(g + sum_j c_j (Z_j - a_j - b_j g - delta_j), 20, 80)

delta_j the re-centring of amendment 2 (F1.5) over the cohort (the rows sharing the fit and
the board year). The masks are forward chained by board year inside every development fold
and out of fold for training rows (section 2.3). Live rows read data/etools.json (2.2).

THE RE-WEIGHT (section 4). The served re-fit RT (efv5_refit, variant RT) with its four tool
slots holding eTools: hitters the V2 key tool_hit (eHIT) and the game power column (ePOW);
pitchers the command column (eCMD) and a fastball column on every graded pitcher (eFB) in
place of the Triple-A fastball cell. Candidates E and ED (E minus the raw rates an eTool
sub-driver already carries); nulls EC (consensus values in E's slots) and EP (the eTool
shift permuted inside its cohort); sensitivity ES (eSPD in the speed slot). Weights by
efv5_refit's section 4, unchanged.

THE SWITCH. EFV_ETOOLS_REWEIGHT_ON is False: nothing here serves. True (with
efv5_refit.EFV_V5_REFIT_ON) makes efv_v2_serve.production_models serve the prepared
candidate's production fit from data/efv_etools_reweight_weights.json. Only the owner flips
it, and only after a PREPARED read.

RESERVED FRAMES. The development build raises on list vintages 2020 and 2021 and stops before
the 2025 cohort (efv_vintage_frame); the eTools frame is etools.DEV_YEARS only, and no label of
a board year outside it is read.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group percentile
and as the value multiset the grade is drawn from; the strata are side, year, fold, board
year, position group, role and age band. Nothing here groups, counts or averages rows by
consensus-FV level; test_efv_etools_reweight.py scans this source.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

import efv5_combined as V5C
import efv5_refit as RF
import efv_v2_model as H
import efv_v3 as V3
import efv_vintage_frame as F

#: THE SWITCH. False: nothing here serves. Only the owner flips it, after a PREPARED read.
EFV_ETOOLS_REWEIGHT_ON = False
#: Which passing candidate the flag serves: None serves the prepared one.
SERVE_CANDIDATE: str | None = None

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
FIT_PATH = LAB_DIR / "efv_etools_reweight_fit.json"
WEIGHTS_PATH = DATA_DIR / "efv_etools_reweight_weights.json"
SERVED_ETOOLS_PATH = DATA_DIR / "etools.json"
ETOOLS_EVAL_PATH = DATA_DIR / "_labs" / "etools" / "etools_eval.json"
DOC = "docs/efv-v2/EFV_ETOOLS_REWEIGHT.md"
TOOL = "efv_etools_reweight.py"
ITEM = "EFV_ETOOLS_REWEIGHT"
LEDGER_MODEL_ID = "efv_etools_reweight"
SERVED_MODEL_ID = V5C.MODEL_ID

#: The eTools frame's candidate build (the look's: etools.run, last season 2023).
FRAME_LAST_SEASON = 2023
#: The live board's board year (the 2026 season read).
LIVE_BOARD_YEAR = 2027
#: Section 7: a candidate may trail RT by at most this much on either frame.
MAX_TRAIL = 0.005
#: Section 1: RT must reproduce the committed development read within this.
PARITY_TOL = 1e-4
#: Section 4.2: the permutation null's seed.
PERM_SEED = 20261017
#: The admitted sub-drivers of each eTool (section 0: data/etools.json for the six served
#: eTools; the look's admitted lists for the two sensitivity tools). test-pinned.
SUBDRIVERS: dict[str, tuple[str, ...]] = {
    "hit": ("k_rw", "ppa_par", "babip_rw"),
    "game_pwr": ("iso_rw", "bb_fb"),
    "pitch_sel": ("pbp_swing",),
    "bat_ctrl": ("pbp_contact",),
    "fb": ("k_rw", "pbf_raw", "pbp_swstr"),
    "cmd": ("bb_rw", "pbp_fstrike", "pbf_par"),
    "raw_pwr": ("iso_rw",),
    "speed": ("sb_rel",),
}
TOOL_SIDE = {"hit": "hit", "game_pwr": "hit", "pitch_sel": "hit", "bat_ctrl": "hit",
             "raw_pwr": "hit", "speed": "hit", "fb": "pit", "cmd": "pit"}
TOOL_KEY = {"hit": "eHIT", "game_pwr": "ePOW", "pitch_sel": "eSEL", "bat_ctrl": "eBAT",
            "fb": "eFB", "cmd": "eCMD", "raw_pwr": "eRAW", "speed": "eSPD"}
#: The raw consensus grade of a tool on a row (efv_dataset._prior_features' keys).
RAW_KEY = {"hit": "tool_hit", "speed": "tool_speed", "raw_pwr": "tool_raw_pwr", "fb": "tool_fb",
           "game_pwr": "tool_game_pwr", "cmd": "tool_cmd"}
#: Section 4.1: the slots. kind v2key: the V2 key's own value is replaced where g is observed;
#: kind column: a new candidate column holds the eTool and the consensus column leaves the list.
SLOTS: dict[str, tuple[dict, ...]] = {
    "hit": ({"tool": "hit", "kind": "v2key", "key": "tool_hit", "g": "raw"},
            {"tool": "game_pwr", "kind": "column", "name": "e5_pow_hit",
             "replaces": "w2s_game_pwr_hit", "g": "scr_w2s_game_pwr_hit"}),
    "pit": ({"tool": "cmd", "kind": "column", "name": "e5_cmd_pit",
             "replaces": "w2s_cmd_pit", "g": "scr_w2s_cmd_pit"},
            {"tool": "fb", "kind": "column", "name": "e5_fb_pit",
             "replaces": "t5_pit_AAA_all_all_fb_fut", "g": "raw"}),
}
SPEED_SLOT = {"tool": "speed", "kind": "v2key", "key": "tool_speed", "g": "raw"}
#: The new candidate columns (sign +1: a higher grade is the better outcome).
NEW_COLUMNS: dict[str, dict] = {
    "e5_pow_hit": {"side": "hit", "head": "skill", "source": "etool", "key": "scr_e5_pow_hit",
                   "sign": 1, "tool": "game_pwr"},
    "e5_cmd_pit": {"side": "pit", "head": "skill", "source": "etool", "key": "scr_e5_cmd_pit",
                   "sign": 1, "tool": "cmd"},
    "e5_fb_pit": {"side": "pit", "head": "skill", "source": "etool", "key": "scr_e5_fb_pit",
                  "sign": 1, "tool": "fb"},
}
CHIP_LABELS = {"scr_e5_pow_hit": "Game power (eTool)", "scr_e5_cmd_pit": "Command (eTool)",
               "scr_e5_fb_pit": "Fastball (eTool)", "tool_hit": "Hit tool (eTool)",
               "tool_speed": "Speed (eTool)"}
#: Section 4.2, ED: the columns that carry the same rate as an admitted eTool sub-driver.
DEDUPE: dict[str, dict] = {
    "hit": {"v2": ("contact",), "columns": ("g5_hit_A_all_all_k_pct", "g5_hit_A_young_all_k_pct")},
    "pit": {"v2": (), "columns": ("g5_pit_A_all_all_k_pct", "g5_pit_A_young_all_k_pct",
                                  "g5_pit_A_all_SP_k_pct", "w2p_fstrike_p")},
}
#: Section 4.2: the configurations.
CONFIGS: dict[str, dict] = {
    "RT": {"mode": None, "dedupe": False, "speed": False, "role": "comparator (the served re-fit RT)"},
    "E": {"mode": "etool", "dedupe": False, "speed": False, "role": "primary candidate"},
    "ED": {"mode": "etool", "dedupe": True, "speed": False,
           "role": "registered variant (the double-count removal)"},
    "EC": {"mode": "consensus", "dedupe": False, "speed": False,
           "role": "null comparator (consensus values in E's slots)"},
    "EP": {"mode": "perm", "dedupe": False, "speed": False,
           "role": "null comparator (the eTool shift permuted inside its cohort)"},
    "ES": {"mode": "etool", "dedupe": False, "speed": True, "role": "sensitivity (eSPD in the speed slot)"},
}
CANDIDATES: tuple[str, ...] = ("E", "ED")
NULLS: tuple[str, ...] = ("EC", "EP")
KEY = {c: f"efv_er_{c.lower()}" for c in CONFIGS}
#: Part 1's tools (section 3) on the eFV rows; eSEL and eBAT are matched in the eTools frame.
PART1_TOOLS = {"hit": ("hit", "game_pwr", "raw_pwr", "speed"), "pit": ("fb", "cmd")}
PART1_FRAME_TOOLS = ("pitch_sel", "bat_ctrl")
PART1_SENSITIVITY = ("raw_pwr", "speed")

_LOG = print


def _tools():
    return V5C._tools()


def _f(v):
    return V5C._f(v)


# ---------------------------------------------------------------------------
# the eTool on a cohort of rows (section 2.1) and on a live row (2.2)
# ---------------------------------------------------------------------------

def residuals(g, Z, lines) -> np.ndarray:
    """Z_j - (a_j + b_j g) where the row carries Z_j and g; 0 elsewhere (and for a line the
    fit could not estimate)."""
    g = np.asarray(g, dtype=np.float64)
    Z = np.asarray(Z, dtype=np.float64).reshape(g.size, len(lines))
    U = np.zeros(Z.shape)
    for j, (a, b, ok) in enumerate(lines):
        if not ok:
            continue
        f = np.isfinite(Z[:, j]) & np.isfinite(g)
        U[f, j] = Z[f, j] - (a + b * g[f])
    return U


def etool_cohort(g, Z, fit: dict, *, centre: bool = True) -> np.ndarray:
    """The eTool of every row of one cohort (NaN where g is not observed): g plus each carried
    sub-driver's residual minus delta_j (the cohort's mean residual of j minus the fit's
    training mean, amendment 2 F1.5), times c_j, clipped to 20 to 80."""
    g = np.asarray(g, dtype=np.float64)
    lines = fit["lines"]
    Z = np.asarray(Z, dtype=np.float64).reshape(g.size, len(lines))
    pres = np.isfinite(Z) & np.isfinite(g)[:, None]
    U = residuals(g, Z, lines)
    if centre:
        cnt = pres.sum(axis=0)
        mu_co = np.where(cnt > 0, np.where(pres, U, 0.0).sum(axis=0) / np.maximum(cnt, 1), 0.0)
        delta = mu_co - np.asarray(fit.get("mu_tr") or np.zeros(len(lines)), dtype=np.float64)
    else:
        delta = np.zeros(len(lines))
    contrib = np.where(pres, U - delta[None, :], 0.0) * np.asarray(fit["c"], dtype=np.float64)[None, :]
    out = np.clip(g + contrib.sum(axis=1), 20.0, 80.0)
    out[~np.isfinite(g)] = np.nan
    return out


def live_etool(g, rec: dict | None, cb: dict) -> float | None:
    """The served eTool at the slot's own g (section 2.2): rec is the player's tool record in
    data/etools.json ({"consensus", "drivers": [[j, points], ...]}); cb {j: c_j b_j} of the
    final fit. g itself when the player carries no served eTool."""
    if g is None:
        return None
    g = float(g)
    if not rec or rec.get("etool") is None or rec.get("consensus") is None:
        return g
    drivers = rec.get("drivers") or []
    pts = 0.0
    slope = 0.0
    for d in drivers:
        j, p = (d[0], d[1]) if isinstance(d, (list, tuple)) else (d.get("key"), d.get("points"))
        if p is None:
            continue
        pts += float(p)
        slope += float(cb.get(j, 0.0))
    return float(min(80.0, max(20.0, g + pts - (g - float(rec["consensus"])) * slope)))


def final_fit_cb(eval_doc: dict | None = None) -> dict[str, dict[str, float]]:
    """{tool: {j: c_j b_j}} of the look's final fit (the served eTools' fit)."""
    doc = eval_doc or json.loads(ETOOLS_EVAL_PATH.read_text(encoding="utf-8"))
    out = {}
    for tool, v in (doc.get("etools") or {}).items():
        ff = v.get("final_fit") or {}
        adm = list(v.get("admitted") or [])
        if not ff or not adm:
            continue
        out[tool] = {j: float(c) * float(line[1]) for j, c, line in zip(adm, ff["c"], ff["lines"])}
    return out


# ---------------------------------------------------------------------------
# the eTools frame and its fits (section 2.3)
# ---------------------------------------------------------------------------

class Bank:
    """The eTools frames (one per tool) and their fits by (tool, board years, players out)."""

    def __init__(self, frames: dict):
        self.frames = {t: frames[t] for t in SUBDRIVERS if t in frames}
        self.Z = {t: np.column_stack([fr.cands[j] for j in SUBDRIVERS[t]])
                  for t, fr in self.frames.items()}
        self._fits: dict = {}
        self.receipts: list[dict] = []

    def fit(self, tool: str, years, excl, *, tag: str = "") -> dict | None:
        import etools as E
        years = tuple(sorted(int(y) for y in years))
        ex = np.asarray(sorted(int(p) for p in excl if p is not None), dtype=np.int64)
        key = (tool, years, hash(ex.tobytes()), ex.size)
        if key in self._fits:
            return self._fits[key]
        fr = self.frames[tool]
        Z = self.Z[tool]
        m = np.isin(fr.year, np.asarray(years, dtype=np.int64)) & ~np.isin(fr.pid, ex)
        fit = E.etool_fit(fr.gc, Z, fr.y, m) if m.any() else None
        if fit is not None:
            U = E.etool_residuals(fr.gc, Z, fit["lines"])
            fit["mu_tr"] = [float(v) for v in E._present_mean(U, Z, m)]
            fit["n_rows"] = int(m.sum())
            fit["years"] = list(years)
            fit["players_out"] = int(ex.size)
        self._fits[key] = fit
        self.receipts.append({"tool": tool, "tag": tag, "years": [min(years), max(years)] if years else None,
                              "n_years": len(years), "players_out": int(ex.size),
                              "rows": None if fit is None else fit["n_rows"],
                              "c": None if fit is None else [round(float(c), 4) for c in fit["c"]]})
        return fit


def build_bank(*, log=print) -> tuple[Bank, dict]:
    """The look's eTools frames (etools.run's construction), and a receipt."""
    import etools as E
    E.guard_years(E.DEV_YEARS)
    t0 = time.time()
    board = E.load_board(E.DEV_YEARS)
    rows, counts = E.build_universe(board, E.DEV_YEARS, log=log)
    E.attach_candidates(rows, last_season=FRAME_LAST_SEASON, log=log)
    E.attach_labels(rows, log=log)
    for r in rows:
        if r["year"] in E.RESERVED_BOARD_YEARS:
            raise E.GuardError("reserved board year in the eTools frame")
    frames = E.tool_frames(rows)
    look = json.loads(ETOOLS_EVAL_PATH.read_text(encoding="utf-8"))
    repro = {}
    for tool in SUBDRIVERS:
        adm = list((look["etools"].get(tool) or {}).get("admitted") or [])
        if tuple(adm) != SUBDRIVERS[tool]:
            raise RuntimeError(f"{tool}: admitted {adm} is not the registered {SUBDRIVERS[tool]}")
        fr = frames[tool]
        pred, _sig = E.etool_oof(fr, adm)
        for lb in E.LABELS:
            want = ((look["etools"][tool].get("labels") or {}).get(lb) or {}).get("d")
            if want is None:
                continue
            got = E.paired_d(pred, fr.gc, fr.y[lb], fr.year, fr.pid, Bn=0).get("d")
            repro[f"{tool}:{lb}"] = {"look": want, "now": got}
            if got is None or abs(float(got) - float(want)) > 5e-5:
                raise RuntimeError(f"{tool} {lb}: the eTool d {got} does not reproduce the look's {want}")
    rec = {"universe": counts, "universe_matches_look": counts == look.get("universe"),
           "reproduction": repro, "seconds": round(time.time() - t0, 1),
           "rows_by_tool": {t: int(frames[t].n) for t in SUBDRIVERS}}
    if not rec["universe_matches_look"]:
        raise RuntimeError(f"the eTools universe {counts} differs from the look's {look.get('universe')}")
    log(f"  eTools frame rebuilt and every look d reproduced ({rec['seconds']} s)")
    return Bank(frames), rec


# ---------------------------------------------------------------------------
# a row's eTool context: pid, board year, observed grades (section 2.1)
# ---------------------------------------------------------------------------

class RowMeta:
    """{ctx, side, decision year, player_key: {"pid", "b", "raw": {tool: g}}} and the
    sub-driver values by (side, pid, board year)."""

    def __init__(self, frames_lv: dict, *, log=print):
        import efv_dataset as D
        self.D = D
        self.recs = D.asof_records()
        self.raw = V5C._raw_by_side()
        self.lv = {}
        for s in F.SIDES:
            for V, entry in frames_lv[s].items():
                rows = entry[0] if isinstance(entry, (tuple, list)) else entry
                for r in rows:
                    self.lv[(s, int(V), r["player_key"])] = r
        self.meta: dict = {}
        self.Z: dict = {}
        self.group: dict = {}
        self.consistency = {"checked": 0, "mismatch": 0, "examples": []}
        self.log = log

    def _point(self, pk: str, day: str):
        pts = [p for p in ((self.recs.get(pk) or {}).get("points") or [])
               if str(p.get("snapshot_date") or "")[:10] == str(day)[:10]]
        return sorted(pts, key=lambda p: p["snapshot_date"])[-1] if pts else None

    def raw_of(self, row: dict, side: str, ctx: str) -> tuple[dict, int | None, int | None, str | None]:
        """(raw tool grades, pid, board year, position) of one row in its context."""
        from efv_w2_milb import last_readable_season
        pk = row["player_key"]
        dy = int(row["decision_year"])
        if ctx == "lv":
            fr = self.lv.get((side, dy, pk)) or {}
            prior = fr.get("prior") or {}
            pid = _f(fr.get("mlbam_id"))
            return ({t: _f(prior.get(k)) for t, k in RAW_KEY.items()},
                    None if pid is None else int(pid), dy, fr.get("position"))
        raw = self.raw[side].get(pk) or {}
        pid = _f(raw.get("mlbam_id") if raw.get("mlbam_id") is not None else row.get("mlbam_id"))
        b = last_readable_season(dy, raw.get("cutoff")) + 1 if raw else None
        if ctx == "vm_test":
            pre = self.D.preseason_consensus_asof(self.recs.get(pk), dy, side) or {}
            src = pre
        elif ctx == "twin":
            pt = self._point(pk, row.get("twin_point"))
            src = self.D._prior_features(self.recs.get(pk), pt, side) if pt else {}
            b = int(row["twin_read_season"]) + 1
        else:
            src = raw
        return ({t: _f(src.get(k)) for t, k in RAW_KEY.items()},
                None if pid is None else int(pid), b, raw.get("position"))

    def of(self, row: dict, side: str, ctx: str) -> dict:
        k = (ctx, side, int(row["decision_year"]), row["player_key"])
        got = self.meta.get(k)
        if got is not None:
            return got
        tools, pid, b, pos = self.raw_of(row, side, ctx)
        feats = row.get("feats") or {}
        for t, fk in (("hit", "tool_hit"), ("speed", "tool_speed"), ("fb", "tool_fb")):
            if TOOL_SIDE[t] != side or fk not in feats:
                continue
            self.consistency["checked"] += 1
            g = tools.get(t)
            want = float(feats[fk])
            if g is not None and abs(float(g) - want) > 1e-9:
                self.consistency["mismatch"] += 1
                if len(self.consistency["examples"]) < 10:
                    self.consistency["examples"].append([ctx, side, int(row["decision_year"]),
                                                         row["player_key"], t, g, want])
        got = {"pid": pid, "b": b, "raw": tools, "position": pos}
        self.meta[k] = got
        return got

    def build_z(self, *, log=print) -> dict:
        """Every needed (side, pid, board year)'s sub-driver values through
        etools.attach_candidates (the eTools frame's own function)."""
        import etools as E
        need = {}
        for (ctx, side, _dy, _pk), m in self.meta.items():
            if m["pid"] is not None and m["b"] is not None:
                need.setdefault((side, m["pid"], int(m["b"])), m.get("position"))
        todo = [k for k in need if k not in self.Z]
        if not todo:
            return {"rows": 0}
        bs = [k[2] for k in todo]
        last = max(FRAME_LAST_SEASON, max(bs) - 1)
        rows = [{"year": b, "pid": pid, "side": side, "position": need[(side, pid, b)],
                 "fg_extras": {}} for side, pid, b in todo]
        t0 = time.time()
        E.attach_candidates(rows, last_season=last, log=log)
        for r in rows:
            self.Z[(r["side"], r["pid"], r["year"])] = dict(r["cands"])
            self.group[(r["side"], r["pid"], r["year"])] = r.get("group")
        rec = {"rows": len(rows), "last_season": last, "seconds": round(time.time() - t0, 1),
               "board_years": sorted(set(bs))}
        log(f"  sub-drivers for {len(rows)} eFV (player, board year) pairs ({rec['seconds']} s)")
        return rec

    def zrow(self, side: str, pid, b, tool: str) -> list:
        c = self.Z.get((side, pid, b)) if (pid is not None and b is not None) else None
        return [np.nan if (c is None or c.get(j) is None) else float(c[j]) for j in SUBDRIVERS[tool]]


def z_agreement(rm: RowMeta, bank: Bank) -> dict:
    """Receipt: an eFV row and an eTools frame row of the same (player, board year) carry the
    same sub-driver values (the same function read both)."""
    out = {}
    for tool, fr in bank.frames.items():
        side = TOOL_SIDE[tool]
        idx = {(int(y), int(p)): i for i, (y, p) in enumerate(zip(fr.year.tolist(), fr.pid.tolist()))}
        n = bad = 0
        for (s, pid, b), c in rm.Z.items():
            if s != side:
                continue
            i = idx.get((int(b), int(pid)))
            if i is None:
                continue
            for j in SUBDRIVERS[tool]:
                a, v = fr.cands[j][i], c.get(j)
                a = None if not np.isfinite(a) else float(a)
                n += 1
                if (a is None) != (v is None) or (a is not None and abs(a - float(v)) > 1e-9):
                    bad += 1
        out[tool] = {"compared": n, "differ": bad}
    return out


# ---------------------------------------------------------------------------
# writing a configuration's slot values onto rows (section 4.1)
# ---------------------------------------------------------------------------

def slots_of(side: str, cfg: dict) -> tuple[dict, ...]:
    out = tuple(SLOTS[side])
    if cfg.get("speed") and side == "hit":
        out = out + (SPEED_SLOT,)
    return out


def slot_g(row: dict, slot: dict, meta: dict):
    """The slot's observed consensus value on the row (None when unobserved)."""
    if slot["g"] == "raw":
        return meta["raw"].get(slot["tool"])
    v = (row.get("v2") or {}).get(slot["g"])
    return None if v is None else float(v)


def write_slots(rows: list[dict], side: str, cfg: dict, metas: list[dict], values: dict) -> list[dict]:
    """Copies of rows with each slot's value: values {tool: array (NaN = unobserved)}."""
    out = []
    for i, r in enumerate(rows):
        add = {}
        for slot in slots_of(side, cfg):
            v = values[slot["tool"]][i]
            if slot["kind"] == "v2key":
                if np.isfinite(v):
                    add[slot["key"]] = float(v)
            else:
                add[NEW_COLUMNS[slot["name"]]["key"]] = float(v) if np.isfinite(v) else None
        out.append(dict(r, v2=dict(r["v2"], **add)))
    return out


def cohort_values(rows: list[dict], metas: list[dict], side: str, tools, fits: dict, mode: str,
                  rm: RowMeta, rng=None, slot_for=None) -> tuple[dict, dict]:
    """({tool: values}, {tool: (g, eT)}) for one cohort (rows sharing the fits and the board
    year). mode etool: the eTool; consensus: g; perm: g plus a permuted eTool shift."""
    vals, pair = {}, {}
    for tool in tools:
        slot = (slot_for or {}).get(tool) or {"tool": tool, "g": "raw"}
        g = np.asarray([np.nan if (x := slot_g(r, slot, m)) is None else float(x)
                        for r, m in zip(rows, metas)], dtype=np.float64)
        fit = fits.get(tool)
        if fit is None:
            e = g.copy()
        else:
            Z = np.asarray([rm.zrow(side, m["pid"], m["b"], tool) for m in metas],
                           dtype=np.float64).reshape(len(rows), len(SUBDRIVERS[tool]))
            e = etool_cohort(g, Z, fit)
        pair[tool] = (g, e)
        if mode == "consensus":
            vals[tool] = g
        elif mode == "perm":
            obs = np.flatnonzero(np.isfinite(g))
            sh = (e - g)[obs]
            perm = sh[rng.permutation(sh.size)] if sh.size else sh
            v = g.copy()
            v[obs] = np.clip(g[obs] + perm, 20.0, 80.0)
            vals[tool] = v
        else:
            vals[tool] = e
    return vals, pair


def slot_map(side: str, cfg: dict) -> dict:
    return {s["tool"]: s for s in slots_of(side, cfg)}


def etool_inputs(rows: list[dict], side: str, metas: list[dict], rm: "RowMeta", bank: "Bank", *,
                 years, test_pids: set, training: bool, config: str = "E") -> list[dict]:
    """The re-weighted tool arm (section 8, handed to EFV_X3_POOLED_MODEL as its tool inputs):
    copies of `rows` with the configuration's slots (section 4.1) holding eTools built by the
    registered fold design (section 2.3): `training` rows each out of fold by board year,
    else one fit on `years` with `test_pids` left out. `metas` are RowMeta.of(row, side, ctx)."""
    cfg = CONFIGS[config]
    if cfg["mode"] is None:
        return list(rows)
    vals, _p = Run(B=0, log=lambda *_a, **_k: None).fold_values(
        bank, rm, side, cfg, rows, metas, years_allowed=list(years), test_pids=set(test_pids),
        rng=np.random.default_rng(PERM_SEED), tag="etool_inputs", by_b_exclusive=bool(training))
    return write_slots(rows, side, cfg, metas, vals)


# ---------------------------------------------------------------------------
# the fit of a configuration (RT's machinery with the slots swapped)
# ---------------------------------------------------------------------------

@contextmanager
def injected():
    """The new eTool columns as efv5_combined candidates for the life of the block (fits and
    driver tables only; never around a column build or the live columns)."""
    cands = V5C.candidates()
    added = []
    try:
        for n, s in NEW_COLUMNS.items():
            if n not in cands:
                cands[n] = dict(s)
                added.append(n)
        yield cands
    finally:
        for n in added:
            cands.pop(n, None)


@contextmanager
def v2_removed(side: str, keys):
    """efv_v3.base_config with the V2 skill keys `keys` of `side` removed (ED's contact term)."""
    keys = list(keys)
    if not keys:
        yield
        return
    orig = V3.base_config

    def patched():
        cfg = orig()
        cfg["remove"][side]["skill"] = list(keys)
        return cfg
    V3.base_config = patched
    try:
        yield
    finally:
        V3.base_config = orig


def skill_candidates(side: str, cfg: dict) -> list[str]:
    """The skill head's candidate columns under a configuration."""
    base = RF.refit_candidates(side, "skill", dark=True)
    if cfg["mode"] is None:
        return base
    rep = {s["replaces"]: s["name"] for s in SLOTS[side] if s["kind"] == "column"}
    out = [rep.get(n, n) for n in base]
    for s in SLOTS[side]:
        if s["kind"] == "column" and s["name"] not in out:
            out.append(s["name"])
    if cfg["dedupe"]:
        out = [n for n in out if n not in DEDUPE[side]["columns"]]
    return out


def fit_config(cfg_name: str, side: str, skill_rows, skill_frame, timing_rows, timing_frame, *,
               with_se: bool = False) -> dict:
    cfg = CONFIGS[cfg_name]
    rows = RF.rank_transform(skill_rows, side)
    sk = skill_candidates(side, cfg)
    tm = RF.refit_candidates(side, "timing", dark=True)
    rm_keys = DEDUPE[side]["v2"] if cfg["dedupe"] else ()
    with injected(), v2_removed(side, rm_keys):
        m = RF.fit_heads(rows, skill_frame, timing_rows, timing_frame, side, cands_skill=sk,
                         cands_timing=tm, timing_outcome_blind=False, with_se=with_se)
    m["etools_reweight"] = {"config": cfg_name, "removed_v2": list(rm_keys)}
    return m


# ---------------------------------------------------------------------------
# the development read
# ---------------------------------------------------------------------------

class Run:
    """One development read: the RT build (efv5_refit's phase 1), the eTools bank, the row
    contexts, every configuration's folds, Part 1, the production fits and the board."""

    def __init__(self, *, B: int, log=print, cache_dir: Path | None = None, today: str | None = None):
        self.B = int(B)
        self.log = log
        self.cache = Path(cache_dir) if cache_dir else None
        self.today = today or date.today().isoformat()

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

    def build(self) -> dict:
        """efv5_refit.Run.build1's inputs (repaired norms), keeping the list-vintage frames."""
        got = self._load("build")
        if got is not None:
            return got
        import efv_dataset as D
        import efv_drivers as DRV
        import efv5_group_drivers as G
        log = self.log
        with G.registered(), V5C.v5c_names():
            inp, frames_lv, _rec = V5C.build_dev(log=log)
            pool, prec = RF.lv_pool(frames_lv, log=log)
            prod, twins, trec = {}, {}, {}
            recs = D.asof_records()
            panel = DRV.load_bio_panel()
            for side in F.SIDES:
                prod[side] = V5C.production_train(side, log=log)
                base = [r for r in H.matrix_training_rows(side)
                        if int(r["decision_year"]) < F.train_end_year()]
                tw, rec = RF.build_twins(side, base, recs=recs, panel=panel)
                cols, crec = RF.twin_columns(side, tw, today=self.today, log=log)
                twins[side] = RF.attach_slots(tw, side, cols, RF.twin_slot)
                trec[side] = {"twins": rec}
        out = {"inp": inp, "frames_lv": frames_lv, "pool": pool, "pool_rec": prec, "prod": prod,
               "twins": twins, "twin_rec": trec}
        self._save("build", out)
        return out

    def contexts(self, b1: dict) -> tuple[RowMeta, dict]:
        """Every row's eTool context and the sub-driver values (section 2.1)."""
        got = self._load("contexts")
        if got is not None:
            return got
        BT, _B4 = _tools()
        rm = RowMeta(b1["frames_lv"], log=self.log)
        inp = b1["inp"]
        for fid in BT.FRAMES_DEV:
            for side in F.SIDES:
                for _fold, blk in inp.frames[fid]["by_side"][side].items():
                    for r in blk["train"]:
                        rm.of(r, side, "lv" if fid == "lv_dev" else "vm_train")
                    for r in blk["test"]:
                        rm.of(r, side, "lv" if fid == "lv_dev" else "vm_test")
        for side in F.SIDES:
            for r in b1["prod"][side]:
                rm.of(r, side, "prod")
            for t in b1["twins"][side]:
                rm.of(t, side, "twin")
        if rm.consistency["mismatch"]:
            raise RuntimeError(f"observed tool grades disagree with the rows' features: {rm.consistency}")
        zrec = rm.build_z(log=self.log)
        rm.recs = rm.raw = rm.lv = rm.D = rm.log = None      # not pickled
        out = (rm, {"consistency": rm.consistency, "z": zrec, "metas": len(rm.meta)})
        self._save("contexts", out)
        return out

    # -- eTool values on a fold ---------------------------------------------------------
    @staticmethod
    def _pids(metas) -> set:
        return {m["pid"] for m in metas if m["pid"] is not None}

    def fold_values(self, bank: Bank, rm: RowMeta, side: str, cfg: dict, rows, metas, *,
                    years_allowed, test_pids: set, rng, tag: str, by_b_exclusive: bool,
                    tools=None) -> tuple[dict, dict]:
        """Slot values (and the (g, eT) pairs) over `rows`, one cohort per board year. With
        by_b_exclusive the cohort's fit leaves out its own board year and its players (a
        training row); else one fit on years_allowed (the fold's test rows)."""
        tools = list(tools or [s["tool"] for s in slots_of(side, cfg)])
        smap = slot_map(side, cfg)
        n = len(rows)
        vals = {t: np.full(n, np.nan) for t in tools}
        pairs = {t: (np.full(n, np.nan), np.full(n, np.nan)) for t in tools}
        by_b: dict = {}
        for i, m in enumerate(metas):
            by_b.setdefault(m["b"], []).append(i)
        for b in sorted(by_b, key=lambda x: (x is None, x)):
            ix = by_b[b]
            sub_rows = [rows[i] for i in ix]
            sub_meta = [metas[i] for i in ix]
            if by_b_exclusive:
                yrs = [y for y in years_allowed if y != b]
                excl = set(test_pids) | self._pids(sub_meta)
            else:
                yrs = list(years_allowed)
                excl = set(test_pids)
            fits = {}
            if b is not None and cfg.get("mode") != "consensus":
                for t in tools:
                    fits[t] = bank.fit(t, yrs, excl, tag=f"{tag}|b{b}")
            v, p = cohort_values(sub_rows, sub_meta, side, tools, fits,
                                 cfg.get("mode") or "etool", rm, rng=rng, slot_for=smap)
            for t in tools:
                vals[t][ix] = v[t]
                pairs[t][0][ix] = p[t][0]
                pairs[t][1][ix] = p[t][1]
        return vals, pairs

    def fold_packs(self, name: str, b1: dict, bank: Bank, rm: RowMeta) -> tuple[list, dict, dict]:
        """Every development fold of a configuration: (packs, receipts, Part 1 pairs)."""
        import etools as E
        BT, _B4 = _tools()
        cfg = CONFIGS[name]
        inp, pool, twins = b1["inp"], b1["pool"], b1["twins"]
        rng = np.random.default_rng(PERM_SEED)
        packs, rec, part1 = [], {}, {}
        for fid in BT.FRAMES_DEV:
            kind = BT.FRAME_KIND[fid]
            ctx_tr = "lv" if fid == "lv_dev" else "vm_train"
            ctx_te = "lv" if fid == "lv_dev" else "vm_test"
            for side in F.SIDES:
                cols = (inp.cols.get(fid) or {}).get(side) or {}
                for fold, blk in inp.frames[fid]["by_side"][side].items():
                    t1 = time.time()
                    Y = int(fold)
                    te = V5C.attach(blk["test"], side, cols, "test")
                    tr = V5C.attach(blk["train"], side, cols, "train")
                    m_tr = [rm.of(r, side, ctx_tr) for r in tr]
                    if fid == "vm_dev":
                        tw = [t for t in twins[side] if int(t["decision_year"]) < Y]
                        tr = tr + tw
                        m_tr = m_tr + [rm.of(t, side, "twin") for t in tw]
                        tim = RF.lv_timing_rows(pool[side], last=min(RF.LV_POOL_LAST, Y - 1),
                                                leave_out={r["player_key"] for r in te})
                    else:
                        tim = V5C.attach(blk["train"], side, cols, "train")
                    m_te = [rm.of(r, side, ctx_te) for r in te]
                    years = [y for y in E.DEV_YEARS if y < Y]
                    test_pids = self._pids(m_te)
                    if cfg["mode"] is not None:
                        v_tr, _p = self.fold_values(bank, rm, side, cfg, tr, m_tr, years_allowed=years,
                                                    test_pids=test_pids, rng=rng,
                                                    tag=f"{fid}|{side}|{Y}|train", by_b_exclusive=True)
                        v_te, p_te = self.fold_values(bank, rm, side, cfg, te, m_te, years_allowed=years,
                                                      test_pids=test_pids, rng=rng,
                                                      tag=f"{fid}|{side}|{Y}|test", by_b_exclusive=False)
                        tr = write_slots(tr, side, cfg, m_tr, v_tr)
                        te_w = write_slots(te, side, cfg, m_te, v_te)
                    else:
                        te_w = te
                    m = fit_config(name, side, tr, kind, tim, "lv")
                    te_x = RF.rank_transform(te_w, side)
                    es, et = RF.e_terms(m, te_x)
                    fid_ = f"{fid}|{side}|{Y}"
                    packs.append(RF.pack(fid_, fid, side, Y, te, blk["scored"], es, et, model=m))
                    sk = m.get("skill") or {}
                    rec[fid_] = {"n_train_skill": m["n_train"], "n_train_timing": m["n_train_timing"],
                                 "twins_in_skill": sum(1 for r in tr if r.get("twin")),
                                 "lam": {h: V5C._lam_str(v) for h, v in m["config"]["lam"].items()},
                                 "skill_nonzero": {k: round(float(b), 5) for k, b in
                                                   zip(sk.get("keys") or [], sk.get("beta") or []) if b != 0.0},
                                 "seconds": round(time.time() - t1, 1)}
                    self.log(f"  {name} {fid_}: {len(tr)} skill rows ({rec[fid_]['seconds']} s)")
        return packs, rec, part1

    def production(self, name: str, b1: dict, bank: Bank, rm: RowMeta, weights: dict) -> dict:
        """The production fit of a configuration: training rows of every decision year before
        the R-VM cohort plus the twins, each eTool out of fold on every development board year
        but its own (section 2.3); the timing head on the list-vintage pool."""
        import etools as E
        cfg = CONFIGS[name]
        rng = np.random.default_rng(PERM_SEED)
        out = {}
        for side in F.SIDES:
            tr = list(b1["prod"][side])
            m_tr = [rm.of(r, side, "prod") for r in tr]
            tr = tr + list(b1["twins"][side])
            m_tr = m_tr + [rm.of(t, side, "twin") for t in b1["twins"][side]]
            if cfg["mode"] is not None:
                v_tr, _p = self.fold_values(bank, rm, side, cfg, tr, m_tr, years_allowed=list(E.DEV_YEARS),
                                            test_pids=set(), rng=rng, tag=f"production|{side}",
                                            by_b_exclusive=True)
                tr = write_slots(tr, side, cfg, m_tr, v_tr)
            tim = RF.lv_timing_rows(b1["pool"][side], last=RF.LV_POOL_LAST, leave_out=set())
            m = fit_config(name, side, tr, "vm", tim, "lv", with_se=True)
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
            m["refit"] = {"item": ITEM, "candidate": name, "transform": True,
                          "twins": sum(1 for r in tr if r.get("twin"))}
            m["refit_transform"] = True
            out[side] = m
            self.log(f"  production {name} {side}: {len(tr)} skill rows")
        return out

    # -- Part 1 -----------------------------------------------------------------------
    def part1_pairs(self, b1: dict, bank: Bank, rm: RowMeta) -> dict:
        """{(fid, side, fold, player_key): {tool: (g, eT)}} on every test row: each Part 1
        tool's eTool from the fold's test fit (section 3)."""
        import etools as E
        BT, _B4 = _tools()
        inp = b1["inp"]
        out = {}
        cfg = {"mode": "etool", "dedupe": False, "speed": False}
        for fid in BT.FRAMES_DEV:
            ctx_te = "lv" if fid == "lv_dev" else "vm_test"
            for side in F.SIDES:
                cols = (inp.cols.get(fid) or {}).get(side) or {}
                tools = PART1_TOOLS[side]
                for fold, blk in inp.frames[fid]["by_side"][side].items():
                    Y = int(fold)
                    te = V5C.attach(blk["test"], side, cols, "test")
                    m_te = [rm.of(r, side, ctx_te) for r in te]
                    years = [y for y in E.DEV_YEARS if y < Y]
                    _v, p = self.fold_values(bank, rm, side, cfg, te, m_te, years_allowed=years,
                                             test_pids=self._pids(m_te), rng=None,
                                             tag=f"part1|{fid}|{side}|{Y}", by_b_exclusive=False,
                                             tools=tools)
                    for i, r in enumerate(te):
                        out[(fid, side, Y, r["player_key"])] = {
                            "tools": {t: (float(p[t][0][i]), float(p[t][1][i])) for t in tools},
                            "age_rel_level": (r["v2"] or {}).get("age_rel_level"),
                            "group": rm.group.get((side, m_te[i]["pid"], m_te[i]["b"])),
                            "pid": m_te[i]["pid"], "b": m_te[i]["b"]}
        return out


# ---------------------------------------------------------------------------
# Part 1: the correlation recheck (section 3)
# ---------------------------------------------------------------------------

def _age_bands(vals: list) -> list:
    x = np.asarray([np.nan if v is None else float(v) for v in vals], dtype=np.float64)
    ok = np.isfinite(x)
    if ok.sum() < 30:
        return [None] * len(vals)
    lo, hi = np.percentile(x[ok], [100 / 3, 200 / 3])
    return [None if not np.isfinite(v) else ("young" if v <= lo else ("old" if v > hi else "average"))
            for v in x]


def incremental_scores(rows: list[dict], key: str) -> np.ndarray:
    """s_X = u_c + b z(X) with b the OLS slope of u_y on [1, u_c, z(X)] fitted on the other
    folds' rows (leave one fold out; z standardized on those rows)."""
    BT, _B4 = _tools()
    grp = [c["group"] for c in rows]
    u_c = H.within_pct([c["grades"][BT.CONS] for c in rows], grp)
    u_y = H.within_pct([c["outcome"]["war"] for c in rows], grp)
    x = np.asarray([c["grades"][key] for c in rows], dtype=np.float64)
    fold = np.asarray([int(c["year"]) for c in rows])
    out = np.full(len(rows), np.nan)
    for Y in np.unique(fold):
        te = fold == Y
        tr = ~te
        if tr.sum() < 30:
            continue
        mu, sd = float(x[tr].mean()), float(x[tr].std())
        if sd <= 0:
            out[te] = u_c[te]
            continue
        X = np.column_stack([np.ones(int(tr.sum())), u_c[tr], (x[tr] - mu) / sd])
        b, *_ = np.linalg.lstsq(X, u_y[tr], rcond=None)
        out[te] = u_c[te] + b[2] * (x[te] - mu) / sd
    return out


def part1_block(rows: list[dict], *, B: int) -> dict:
    """A (the eTool against the consensus grade it replaces) and B (each one's incremental gain
    over consensus FV) on rows carrying both."""
    BT, _B4 = _tools()
    import efv_v2_stat as S
    out = {"n": len(rows), "n_players": len({c["key"] for c in rows})}
    if len(rows) < S.MIN_GROUP_ROWS:
        out["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        return out
    for k in ("s_et", "s_cg"):
        s = incremental_scores(rows, k[2:])
        for c, v in zip(rows, s):
            c["grades"][k] = None if not np.isfinite(v) else float(v)
    keep = ("delta", "ci95", "mde95", "n", "status", "reading", "a", "b")
    out["etool_vs_consensus_grade"] = {k: v for k, v in BT.paired(rows, "et", "cg", "within", B=B,
                                                                     seed=BT.SEED).items() if k in keep}
    out["etool_incremental_over_consensus_fv"] = {k: v for k, v in BT.paired(
        rows, "s_et", BT.CONS, "within", B=B, seed=BT.SEED).items() if k in keep}
    out["consensus_grade_incremental_over_consensus_fv"] = {k: v for k, v in BT.paired(
        rows, "s_cg", BT.CONS, "within", B=B, seed=BT.SEED).items() if k in keep}
    out["etool_minus_consensus_grade_incremental"] = {k: v for k, v in BT.paired(
        rows, "s_et", "s_cg", "within", B=B, seed=BT.SEED).items() if k in keep}
    return out


def part1(inp, pairs: dict, *, B: int, log=print) -> dict:
    """Section 3 on the scored test rows of each frame, per tool, overall and by position
    group and age band."""
    BT, _B4 = _tools()
    out = {}
    for fid in BT.FRAMES_DEV:
        scored = inp.scored(fid)
        bands = {}
        for side in F.SIDES:
            mine = [c for c in scored if c["side"] == side]
            ages = [(pairs.get((fid, side, int(c["year"]), c["key"])) or {}).get("age_rel_level")
                    for c in mine]
            for c, bnd in zip(mine, _age_bands(ages)):
                bands[(side, int(c["year"]), c["key"])] = bnd
        blk = {}
        for side in F.SIDES:
            for tool in PART1_TOOLS[side]:
                rows = []
                for c in scored:
                    if c["side"] != side:
                        continue
                    p = pairs.get((fid, side, int(c["year"]), c["key"]))
                    if not p:
                        continue
                    g, e = p["tools"][tool]
                    if not (np.isfinite(g) and np.isfinite(e)):
                        continue
                    pos = c.get("cell") if side == "hit" else (p.get("group") or None)
                    rows.append(dict(c, grades=dict(c["grades"], et=float(e), cg=float(g)),
                                     _pos=pos, _band=bands.get((side, int(c["year"]), c["key"]))))
                t0 = time.time()
                tb = {"tool": tool, "key": TOOL_KEY[tool], "side": side,
                      "sensitivity": tool in PART1_SENSITIVITY,
                      "overall": part1_block(rows, B=B), "by_position_group": {}, "by_age_band": {}}
                for pos in sorted({r["_pos"] for r in rows if r["_pos"]}):
                    tb["by_position_group"][pos] = part1_block([r for r in rows if r["_pos"] == pos], B=B)
                for bnd in ("young", "average", "old"):
                    tb["by_age_band"][bnd] = part1_block([r for r in rows if r["_band"] == bnd], B=B)
                blk[tool] = tb
                log(f"  part 1 {fid} {tool}: {len(rows)} rows ({round(time.time() - t0, 1)} s)")
        out[fid] = blk
    return out


def part1_frame_tools(inp, bank: Bank, rm: RowMeta) -> dict:
    """eSEL and eBAT (section 3): the vm_dev scored rows whose (player, board year) sits in the
    tool's eTools frame, counted per (side, year) group; read nowhere unless a group reaches 20."""
    import efv_v2_stat as S
    out = {}
    vm = inp.scored("vm_dev")
    for tool in PART1_FRAME_TOOLS:
        fr = bank.frames[tool]
        have = set(zip(fr.year.tolist(), fr.pid.tolist()))
        by: dict = {}
        for c in vm:
            if c["side"] != "hit":
                continue
            m = rm.meta.get(("vm_test", "hit", int(c["year"]), c["key"]))
            if not m or m["pid"] is None or m["b"] is None:
                continue
            if (int(m["b"]), int(m["pid"])) in have:
                by[c["group"]] = by.get(c["group"], 0) + 1
        out[tool] = {"key": TOOL_KEY[tool], "frame_board_years": sorted({int(y) for y in fr.year}),
                     "matched_by_group": by, "computable": any(v >= S.MIN_GROUP_ROWS for v in by.values()),
                     "note": ("consensus grades for this tool first appear on the 2021 boards; lv_dev "
                              "(list years 2017 to 2019) carries none")}
    return out


def part1_frame_read(inp, bank: Bank, rm: RowMeta, *, B: int) -> dict:
    """Section 3 for eSEL and eBAT: on the vm_dev scored hitter rows whose (player, board
    year) sits in the tool's eTools frame, the eTool from the fold's forward-chained fit
    (board years before the decision year, the fold's test players out) at the frame row's
    consensus grade, beside that grade; a fold with no earlier board year has no eTool."""
    import etools as E
    out = {}
    vm = [c for c in inp.scored("vm_dev") if c["side"] == "hit"]
    for tool in PART1_FRAME_TOOLS:
        fr = bank.frames[tool]
        idx = {(int(y), int(p)): i for i, (y, p) in enumerate(zip(fr.year.tolist(), fr.pid.tolist()))}
        by_fold: dict = {}
        for c in vm:
            m = rm.meta.get(("vm_test", "hit", int(c["year"]), c["key"]))
            if not m or m["pid"] is None or m["b"] is None:
                continue
            i = idx.get((int(m["b"]), int(m["pid"])))
            if i is not None:
                by_fold.setdefault(int(c["year"]), []).append((c, i, m))
        rows, folds = [], {}
        for Y, items in sorted(by_fold.items()):
            test_pids = {rm.meta.get(("vm_test", "hit", int(c["year"]), c["key"]), {}).get("pid")
                         for c in inp.scored("vm_dev") if c["side"] == "hit" and int(c["year"]) == Y}
            years = [y for y in E.DEV_YEARS if y < Y]
            fit = bank.fit(tool, years, test_pids, tag=f"part1|{tool}|{Y}") if years else None
            folds[str(Y)] = {"rows": len(items), "fit_years": years,
                             "fit_rows": None if fit is None else fit["n_rows"]}
            if fit is None:
                continue
            ix = np.asarray([i for _c, i, _m in items])
            Zs = bank.Z[tool][ix]
            g = fr.gc[ix]
            e = etool_cohort(g, Zs, fit)
            for (c, _i, _m), gv, ev in zip(items, g, e):
                rows.append(dict(c, grades=dict(c["grades"], et=float(ev), cg=float(gv))))
        out[tool] = {"key": TOOL_KEY[tool], "folds": folds, "rows_read": len(rows),
                     "overall": part1_block(rows, B=B) if rows else {"n": 0, "status": "no fold has an eTool"}}
    return out


# ---------------------------------------------------------------------------
# the read's statistics, the ship rule and the attribution check (sections 6 and 7)
# ---------------------------------------------------------------------------

def comparisons() -> tuple:
    BT, _B4 = _tools()
    out = []
    for c in CANDIDATES:
        out += [(f"{c}_vs_RT", KEY[c], KEY["RT"]), (f"{c}_vs_prospx_consensus", KEY[c], BT.CONS),
                (f"{c}_vs_mlb_pipeline", KEY[c], "mlb_pipeline"), (f"{c}_vs_fangraphs", KEY[c], "fangraphs"),
                (f"{c}_vs_EC", KEY[c], KEY["EC"]), (f"{c}_vs_EP", KEY[c], KEY["EP"])]
    out += [("RT_vs_prospx_consensus", KEY["RT"], BT.CONS), ("EC_vs_RT", KEY["EC"], KEY["RT"]),
            ("EP_vs_RT", KEY["EP"], KEY["RT"]), ("ES_vs_RT", KEY["ES"], KEY["RT"]),
            ("ES_vs_E", KEY["ES"], KEY["E"]), ("ED_vs_E", KEY["ED"], KEY["E"])]
    return tuple(out)


def raters_out() -> tuple:
    BT, _B4 = _tools()
    return tuple((KEY[c], f"efv_er_{c.lower()}") for c in CONFIGS) + (
        (BT.CONS, "prospx_consensus"), ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))


def frame_rows(inp, fid: str, orders: dict[str, dict]) -> list[dict]:
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


def frame_read(rows: list[dict], *, B: int, log=print) -> dict:
    BT, _B4 = _tools()
    import efv_v2_stat as S
    t0 = time.time()
    with RF.raters_named(raters_out()):
        blk = BT.frame_block(rows, B=B, stats=("within", "pooled", "auc"), comparisons=comparisons())
    cells = {}
    for side, cell in BT.CELLS:
        sel = [c for c in rows if c["side"] == side and (side == "pit" or c.get("cell") == cell)]
        cb = {"n": len(sel)}
        if len(sel) >= S.MIN_GROUP_ROWS:
            for c in CANDIDATES:
                cb[f"{c}_vs_RT"] = RF._keep(BT.paired(sel, KEY[c], KEY["RT"], "within", B=B, seed=BT.SEED))
                cb[f"{c}_vs_prospx_consensus"] = RF._keep(BT.paired(sel, KEY[c], BT.CONS, "within", B=B,
                                                                    seed=BT.SEED))
        else:
            cb["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        cells[f"{side}:{cell}"] = cb
    blk["cells"] = cells
    blk["fold_deltas"] = {f"{c}_vs_RT": BT.fold_deltas(rows, KEY[c], KEY["RT"]) for c in CANDIDATES}
    log(f"  stats {round(time.time() - t0, 1)} s")
    return blk


def lower_bound(leg: dict) -> float | None:
    """One-sided 95 percent lower bound from a paired leg (delta - 1.645 sd)."""
    d, sd = leg.get("delta"), leg.get("sd")
    if d is None or sd is None:
        return None
    return round(float(d) - 1.6449 * float(sd), 5)


def pooled(frames: dict, comp: str) -> float | None:
    tot = n_tot = 0.0
    for fid in ("lv_dev", "vm_dev"):
        d = frames[fid]["deltas"][comp]["spearman"].get("delta")
        if d is None:
            return None
        n = int(frames[fid]["n"])
        tot += n * float(d)
        n_tot += n
    return round(tot / n_tot, 5) if n_tot else None


def ship_reading(frames: dict) -> dict:
    """Section 7, per candidate, plus the attribution check."""
    out = {}
    for c in CANDIDATES:
        per = {}
        ok = True
        for fid in ("lv_dev", "vm_dev"):
            f = frames[fid]
            d = f["deltas"][f"{c}_vs_RT"]["spearman"].get("delta")
            cons = f["deltas"][f"{c}_vs_prospx_consensus"]["spearman"]
            per[fid] = {"n": int(f["n"]), "delta_vs_RT": d, "ci95_vs_RT": f["deltas"][f"{c}_vs_RT"]["spearman"].get("ci95"),
                        "delta_vs_consensus": cons.get("delta"), "ci95_vs_consensus": cons.get("ci95"),
                        "lb95_vs_consensus": lower_bound(cons)}
            if d is None:
                ok = False
        pl = pooled(frames, f"{c}_vs_RT")
        rule1 = pl is not None and pl > 0
        rule2 = all(v["delta_vs_RT"] is not None and v["delta_vs_RT"] >= -MAX_TRAIL for v in per.values())
        vs_ec, vs_ep = pooled(frames, f"{c}_vs_EC"), pooled(frames, f"{c}_vs_EP")
        out[c] = {"frames": per, "pooled_delta_vs_RT": pl,
                  "pooled_rows": sum(v["n"] for v in per.values()),
                  "pooled_delta_vs_consensus": pooled(frames, f"{c}_vs_prospx_consensus"),
                  "rule_pooled_above_zero": bool(rule1), "rule_no_frame_trails": bool(rule2),
                  "passes": bool(ok and rule1 and rule2),
                  "attribution": {"pooled_vs_EC": vs_ec, "pooled_vs_EP": vs_ep,
                                  "etool_gain": bool(vs_ec is not None and vs_ec > 0
                                                     and vs_ep is not None and vs_ep > 0)}}
    passing = [c for c in CANDIDATES if out[c]["passes"]]
    prepared = max(passing, key=lambda c: out[c]["pooled_delta_vs_RT"]) if passing else None
    return {"rule": ("pooled over lv_dev and vm_dev by row count, within Spearman minus RT above 0, "
                     f"and minus RT >= -{MAX_TRAIL} on each frame"),
            "attribution_rule": ("the prepared candidate beats EC and EP on the same pooled estimand; "
                                 "otherwise the pass is a restructuring effect and the owner question's "
                                 "default is not to flip"),
            "candidates": out, "passing": passing, "prepared": prepared,
            "etool_gain": bool(prepared and out[prepared]["attribution"]["etool_gain"])}


# ---------------------------------------------------------------------------
# the live board (sections 2.2 and 8)
# ---------------------------------------------------------------------------

def _served_etools() -> dict:
    return json.loads(SERVED_ETOOLS_PATH.read_text(encoding="utf-8")).get("players") or {}


def live_slots(rows: list[dict], side: str, cfg_name: str, live: list[dict], *,
               served: dict | None = None, cb: dict | None = None) -> list[dict]:
    """The live rows with the configuration's slots holding the served eTools at each slot's
    own g (section 2.2)."""
    cfg = CONFIGS[cfg_name]
    if cfg["mode"] is None:
        return rows
    served = _served_etools() if served is None else served
    cb = final_fit_cb() if cb is None else cb
    raw = {r["player_key"]: r for r in live if r.get("player_key")}
    out = []
    for r in rows:
        meta = {"raw": {t: _f((raw.get(r["player_key"]) or {}).get(k)) for t, k in RAW_KEY.items()}}
        add = {}
        for slot in slots_of(side, cfg):
            g = slot_g(r, slot, meta)
            rec = (((served.get(r["player_key"]) or {}).get("tools") or {}).get(slot["tool"]))
            v = g if cfg["mode"] == "consensus" else live_etool(g, rec, cb.get(slot["tool"], {}))
            if slot["kind"] == "v2key":
                if v is not None:
                    add[slot["key"]] = float(v)
            else:
                add[NEW_COLUMNS[slot["name"]]["key"]] = None if v is None else float(v)
        out.append(dict(r, v2=dict(r["v2"], **add)))
    return out


def score_board(side: str, model: dict, cfg_name: str, *, today: str) -> dict:
    import efv_dataset as D
    import efv_v2_serve as S
    live = json.loads(D.live_matrix_path(side).read_text(encoding="utf-8"))
    rows = S.live_rows(side, live, today=today)
    rows = S._with_live_candidates(side, rows, live, model, today)
    rows = live_slots(rows, side, cfg_name, live)
    preds = H.predict_v2(model, rows)
    parts = S._chip_parts(model, rows)
    order = sorted(range(len(preds)), key=lambda i: (-preds[i]["order_idx"], preds[i]["player_key"]))
    rank = {i: k + 1 for k, i in enumerate(order)}
    return {r["player_key"]: {"grade": float(p["efv_grade"]), "order_idx": float(p["order_idx"]),
                              "fv": float(r["fv"]), "rank": rank[i],
                              "chips": S.driver_chips(parts[i])[:6]}
            for i, (r, p) in enumerate(zip(rows, preds))}


# ---------------------------------------------------------------------------
# the served path (dark) and the weights file
# ---------------------------------------------------------------------------

def model_out(m: dict) -> dict:
    out = RF.model_out(m)
    out["etools_reweight"] = m.get("etools_reweight")
    return out


def model_in(d: dict) -> dict:
    m = RF.model_in(d)
    m["etools_reweight"] = d.get("etools_reweight")
    return m


def served_candidate(doc: dict) -> str:
    if not doc.get("prepared"):
        raise RuntimeError(f"{WEIGHTS_PATH.name}: no candidate passed the ship rule of {DOC}; "
                           "nothing is prepared to serve")
    cand = SERVE_CANDIDATE or doc["candidate"]
    if cand not in (doc.get("passing") or []):
        raise RuntimeError(f"candidate {cand!r} did not pass the ship rule of {DOC}")
    return cand


def production_models(path: Path | None = None) -> dict[str, dict]:
    """The served re-weight (efv_v2_serve.production_models reads this while
    EFV_ETOOLS_REWEIGHT_ON and efv5_refit.EFV_V5_REFIT_ON are True)."""
    if not RF.EFV_V5_REFIT_ON:
        raise RuntimeError("the eTools re-weight builds on the served re-fit; "
                           "efv5_refit.EFV_V5_REFIT_ON must be True")
    doc = json.loads((path or WEIGHTS_PATH).read_text(encoding="utf-8"))
    cand = served_candidate(doc)
    return {s: model_in(m) for s, m in doc["models_by_candidate"][cand].items()}


def serves(model: dict) -> str | None:
    """The configuration a served model carries the eTool slots of (None: not this model)."""
    er = (model or {}).get("etools_reweight") or {}
    return er.get("config") if er.get("config") in CONFIGS else None


def chip_label(key: str) -> str | None:
    return CHIP_LABELS.get(key)


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _code() -> dict:
    BT, _B4 = _tools()
    return {"commit": BT._commit(), "tool": TOOL, "tool_sha256": BT._sha(ROOT / TOOL),
            "efv5_refit_sha256": BT._sha(ROOT / "efv5_refit.py"),
            "efv5_combined_sha256": BT._sha(ROOT / "efv5_combined.py"),
            "etools_sha256": BT._sha(ROOT / "etools.py"),
            "etools_json_sha256": BT._sha(SERVED_ETOOLS_PATH),
            "doc": DOC, "doc_sha256": BT._sha(ROOT / DOC)}


def tool_weights(tables: dict, side: str) -> list[dict]:
    """Each slot's driver row of a production driver table (the tool's weight)."""
    want = set()
    for s in SLOTS[side] + ((SPEED_SLOT,) if side == "hit" else ()):
        if s["kind"] == "v2key":
            want.add(s["key"])
        else:
            want.add(s["name"])
            want.add(s["replaces"])
    head = (tables.get("heads") or {}).get("skill") or {}
    return [r for r in head.get("drivers") or [] if r["driver"] in want]


def prep(*, log=print, cache_dir: Path, today: str | None = None) -> dict:
    """The read's inputs and fits, cached, with no statistic computed: the build, the eTools
    frame (its look reproduction), the row contexts, every configuration's fold fits and the
    Part 1 eTool values. --run then reads from the cache."""
    BT, _B4 = _tools()
    R = Run(B=0, log=log, cache_dir=cache_dir, today=today)
    t0 = time.time()
    with RF.pop_repair(True):
        b1 = R.build()
        got = R._load("bank")
        if got is None:
            got = build_bank(log=log)
            R._save("bank", got)
        bank, _bank_rec = got
        rm, ctx_rec = R.contexts(b1)
        agree = z_agreement(rm, bank)
        log(f"  contexts: {ctx_rec['metas']} rows, consistency {ctx_rec['consistency']['checked']} checked, "
            f"sub-driver agreement {agree}")
        for name in CONFIGS:
            if R._load(f"packs_{name}") is None:
                R._save(f"packs_{name}", R.fold_packs(name, b1, bank, rm))
        if R._load("part1_pairs") is None:
            R._save("part1_pairs", R.part1_pairs(b1, bank, rm))
    log(f"prep done ({round(time.time() - t0, 1)} s)")
    return {"seconds": round(time.time() - t0, 1)}


def run(*, B: int, log=print, cache_dir: Path | None = None, today: str | None = None) -> dict:
    """The registered read, once (sections 3 to 8)."""
    import efv_labels as L
    BT, _B4 = _tools()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    R = Run(B=B, log=log, cache_dir=cache_dir, today=today)
    t0 = time.time()
    with RF.pop_repair(True):
        log("build: the re-fit's inputs (repaired norms)")
        b1 = R.build()
        inp = b1["inp"]
        got = R._load("bank")
        if got is None:
            got = build_bank(log=log)
            R._save("bank", got)
        bank, bank_rec = got
        rm, ctx_rec = R.contexts(b1)
        ctx_rec = dict(ctx_rec, z_agreement=z_agreement(rm, bank))
        if any(v["differ"] for v in ctx_rec["z_agreement"].values()):
            raise RuntimeError(f"eFV rows and the eTools frame disagree on sub-drivers: {ctx_rec['z_agreement']}")
        packs, recs = {}, {}
        for name in CONFIGS:
            got = R._load(f"packs_{name}")
            if got is None:
                got = R.fold_packs(name, b1, bank, rm)
                R._save(f"packs_{name}", got)
            packs[name], recs[name], _p1 = got
        weights, weights_cf, boots = {}, {}, {}
        for name, pk in packs.items():
            weights[name] = RF._pack_weights(pk)
            weights_cf[name] = {s: RF.cross_fitted([p for p in pk if p["side"] == s]) for s in F.SIDES}
            boots[name] = {s: RF.boot_weights([p for p in pk if p["side"] == s]) for s in F.SIDES}
        scored_keys = {fid: {(c["side"], int(c["year"]), c["key"]) for c in inp.scored(fid)}
                       for fid in BT.FRAMES_DEV}
        orders = {name: RF.orders_from(packs[name], weights_cf[name], scored_keys) for name in CONFIGS}
        # section 1: RT must reproduce the committed development read before anything is read
        rfit = json.loads(RF.FIT_PATH.read_text(encoding="utf-8"))
        parity = {}
        for fid in BT.FRAMES_DEV:
            rows = frame_rows(inp, fid, orders)
            got_w = RF.within_of(rows, KEY["RT"])["within"]
            want = rfit["frames"][fid]["raters"]["efv_v5_rt"]["within"]
            parity[fid] = {"recomputed": got_w, "committed": want}
            if got_w is None or abs(float(got_w) - float(want)) > PARITY_TOL:
                raise RuntimeError(f"RT does not reproduce the committed development read on {fid}: "
                                   f"{got_w} against {want}; nothing is read")
        log(f"RT reproduces the committed development read: {parity}")
        p1_pairs = R._load("part1_pairs")
        if p1_pairs is None:
            p1_pairs = R.part1_pairs(b1, bank, rm)
            R._save("part1_pairs", p1_pairs)
        log("part 1: the correlation recheck")
        p1 = part1(inp, p1_pairs, B=B, log=log)
        p1_frame = part1_frame_tools(inp, bank, rm)
        frames = {}
        for fid in BT.FRAMES_DEV:
            rows = frame_rows(inp, fid, orders)
            log(f"{fid}: {len(rows)} scored rows")
            frames[fid] = frame_read(rows, B=B, log=log)
            frames[fid]["window"] = [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])]
            frames[fid]["frame_version"] = BT.FRAME_VERSION[fid]
        ship = ship_reading(frames)
        log(f"ship reading: {json.dumps({c: ship['candidates'][c]['passes'] for c in CANDIDATES})}, "
            f"prepared {ship['prepared']}")
        # production fits (RT for the old weights, each candidate), the board effect
        prod_models, boards, tables = {}, {}, {}
        for name in ("RT",) + CANDIDATES:
            prod_models[name] = R.production(name, b1, bank, rm, {s: weights[name][s] for s in F.SIDES})
            with injected():
                tables[name] = {s: V5C.weights_table(prod_models[name][s]) for s in F.SIDES}
        for name in CANDIDATES:
            got_b = {s: score_board(s, prod_models[name][s], name, today=R.today) for s in F.SIDES}
            boards[name] = RF.board_effect(got_b)
        rt_board = {s: score_board(s, prod_models["RT"][s], "RT", today=R.today) for s in F.SIDES}
        boards["RT_recomputed"] = {s: {k: v for k, v in blk.items() if k != "top_movers"}
                                   for s, blk in RF.board_effect(rt_board).items()}
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": BT._now(),
           "role": "development", "adjudicates": False, "doc": DOC,
           "owner_decision": "EW3-26 (2026-10-15)", "label": inp.label, "code": _code(),
           "configs": CONFIGS, "slots": SLOTS, "speed_slot": SPEED_SLOT, "new_columns": NEW_COLUMNS,
           "dedupe": DEDUPE, "subdrivers": SUBDRIVERS, "rt_parity": parity,
           "etools_frame": bank_rec, "row_contexts": ctx_rec,
           "etool_fits": {"n": len(bank.receipts), "receipts": bank.receipts},
           "twins": b1["twin_rec"], "timing_pool": b1["pool_rec"],
           "part1": p1, "part1_frame_tools": p1_frame,
           "weights": {name: {s: dict(weights[name][s]) for s in F.SIDES} for name in weights},
           "weights_bootstrap": boots, "weights_cross_fitted": weights_cf,
           "fold_receipts": recs, "frames": frames, "ship": ship,
           "production": {name: {"driver_tables": tables[name],
                                 "tool_weights": {s: tool_weights(tables[name][s], s) for s in F.SIDES},
                                 "lam": {s: {h: V5C._lam_str(v) for h, v in
                                             prod_models[name][s]["config"]["lam"].items()}
                                         for s in F.SIDES}} for name in prod_models},
           "board": boards, "elapsed_s": round(time.time() - t0, 1)}
    claims = {}
    for name in CANDIDATES:
        cf = {fid: dict(frames[fid]["deltas"][f"{name}_vs_prospx_consensus"]["spearman"], n=frames[fid]["n"])
              for fid in BT.FRAMES_DEV}
        claims[name] = RF.claim_from({fid: {"x": cf[fid]} for fid in cf}, "x", date_=R.today,
                                     source=f"{FIT_PATH.relative_to(ROOT).as_posix()} ({name})")
    doc["claims"] = claims
    doc["claim_prepared"] = claims.get(ship["prepared"]) if ship["prepared"] else None
    BT.write_doc(doc, FIT_PATH)
    cand_models = {c: prod_models[c] for c in CANDIDATES}
    BT.write_doc(weights_doc(json.loads(json.dumps(doc, default=str)), cand_models), WEIGHTS_PATH)
    log(f"wrote {FIT_PATH} and {WEIGHTS_PATH} ({round(time.time() - t0, 1)} s)")
    return doc


def weights_doc(doc: dict, prod_models: dict) -> dict:
    ship = doc["ship"]
    prepared = ship["prepared"]
    cand = prepared or "E"

    def w_of(c):
        return {s: {k: doc["weights"][c][s][k] for k in
                    ("w_skill", "w_time", "w_skill_ratio", "w_time_ratio", "n")} for s in F.SIDES}
    return {"schema": 1, "model_id": SERVED_MODEL_ID, "item": ITEM, "produced_by": TOOL,
            "generated_at": doc["generated_at"], "doc": DOC,
            "fit_artifact": FIT_PATH.relative_to(ROOT).as_posix(),
            "prepared": bool(prepared), "candidate": cand, "passing": list(ship["passing"]),
            "etool_gain": bool(ship.get("etool_gain")),
            "served": False, "flag": "efv_etools_reweight.EFV_ETOOLS_REWEIGHT_ON",
            "note": ("the production fit of each eTools re-weight candidate as read; the flag serves "
                     "the prepared candidate only when the owner flips EFV_ETOOLS_REWEIGHT_ON (with "
                     "efv5_refit.EFV_V5_REFIT_ON on)"
                     + ("" if prepared else "; NOT PREPARED: no candidate passed the ship rule")),
            "weights": w_of(cand), "weights_by_candidate": {c: w_of(c) for c in prod_models},
            "models_by_candidate": {c: {s: model_out(m) for s, m in ms.items()}
                                    for c, ms in prod_models.items()},
            "claim": doc.get("claim_prepared"),
            "claims_by_candidate": {c: doc["claims"][c] for c in prod_models},
            "code": doc["code"]}


# ---------------------------------------------------------------------------
# the ledger (two development rows)
# ---------------------------------------------------------------------------

def ledger_rows(doc: dict, cand: str, *, artifact: Path, date_: str, now_iso: str) -> list[dict]:
    import efv_progress as P
    import efv_v2_stat as S
    BT, _B4 = _tools()
    lab = doc.get("label") or {}
    mv = {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    raters_map = (("efv", f"efv_er_{cand.lower()}"), ("efv_v5_refit", "efv_er_rt"),
                  ("prospx_consensus", "prospx_consensus"), ("mlb_pipeline", "mlb_pipeline"),
                  ("fangraphs", "fangraphs"))
    deltas_map = (("vs_efv_v5_refit", f"{cand}_vs_RT"),
                  ("vs_prospx_consensus", f"{cand}_vs_prospx_consensus"),
                  ("vs_mlb_pipeline", f"{cand}_vs_mlb_pipeline"),
                  ("vs_fangraphs", f"{cand}_vs_fangraphs"),
                  ("efv_v5_refit_vs_prospx_consensus", "RT_vs_prospx_consensus"))
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
                                "reading": leg.get("reading"), "key": f"frames.{fid}.deltas.{comp}.{metric}"}
            if legs:
                deltas[name] = legs
        nbs = {s: (f.get("n_by_side") or {})[s] for s in P.STRATA if (f.get("n_by_side") or {}).get(s)} or None
        w = f["deltas"][f"{cand}_vs_RT"]["spearman"]
        c = f["deltas"][f"{cand}_vs_prospx_consensus"]["spearman"]
        row = {"run_id": None, "date": date_, "trigger": "efv_change", "model_id": LEDGER_MODEL_ID,
               "model_version": dict(mv), "frame": fid, "frame_version": f.get("frame_version"),
               "role": meta["role"], "tilted": bool(meta["tilted"]), "window": f.get("window"),
               "n": f.get("n"), "n_by_side": nbs, "raters": raters, "deltas": deltas, "resolvable": None,
               "verdict": (f"DEVELOPMENT ONLY (the eTools re-weight {cand}, weights cross-fitted on these "
                           f"frames): within vs the served re-fit RT {BT._rnd(w.get('delta'), 4)} "
                           f"(CI95 {w.get('ci95')}), vs consensus {BT._rnd(c.get('delta'), 4)} "
                           f"(CI95 {c.get('ci95')}); adjudicates nothing"),
               "share": None, "sources": [dict(s) for s in src],
               "note": f"eFV tool inputs on eTools ({ITEM}, candidate {cand}; {DOC}); development read, adjudicates nothing",
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--part1-frame", action="store_true",
                    help="section 3's eSEL and eBAT rows, once, into the fit artifact")
    ap.add_argument("--prep", action="store_true",
                    help="build and fit everything into --cache without computing a statistic")
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--cache", default=None, help="a scratch directory for resumable builds")
    ap.add_argument("--ledger", action="store_true",
                    help="append the read's two development rows to data/efv_progress.json")
    ap.add_argument("--ledger-path", default=None)
    a = ap.parse_args(argv)
    BT, _B4 = _tools()

    def log(msg):
        print(msg, flush=True)
    if a.ledger:
        if not FIT_PATH.exists():
            log("refused: the fit artifact does not exist")
            return 2
        doc = json.loads(FIT_PATH.read_text(encoding="utf-8"))
        cand = doc["ship"]["prepared"] or "E"
        led = Path(a.ledger_path) if a.ledger_path else (ROOT / ".cache" / "efv_etools_reweight"
                                                         / "progress_ledger.jsonl")
        r = append_ledger(doc, cand, artifact=FIT_PATH, ledger_path=led)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if a.part1_frame:
        if not (FIT_PATH.exists() and a.cache):
            log("refused: the fit artifact and --cache are needed")
            return 2
        doc = json.loads(FIT_PATH.read_text(encoding="utf-8"))
        R = Run(B=0, log=log, cache_dir=Path(a.cache))
        with RF.pop_repair(True):
            b1 = R.build()
            bank, _rec = R._load("bank")
            rm, _ctx = R.contexts(b1)
            got = part1_frame_read(b1["inp"], bank, rm, B=BT.B_DEFAULT if a.B is None else int(a.B))
        doc["part1_frame_tools_read"] = dict(got, note=(
            "computed after the main read (2026-10-16): the first write counted the matched rows "
            "of section 3 but did not read them, a harness omission; this is the registered read "
            "of those rows, run once"))
        BT.write_doc(doc, FIT_PATH)
        log(json.dumps({t: {k: v for k, v in r.items() if k != "overall"} for t, r in got.items()}))
        return 0
    if a.prep:
        if not a.cache:
            log("refused: --prep needs --cache")
            return 2
        prep(log=log, cache_dir=Path(a.cache))
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

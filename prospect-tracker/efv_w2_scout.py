# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV wave 2, lane 1a: scouting-grade driver families beyond the hit tool
(EFV3_W2_1a_SCOUT_GRADES; owner decision EW2-6, 2026-10-08).

WHAT THIS IS. Column builders and ONE development read for scouting grades that the
V2 assembly does not offer today: pitch and command grades for pitchers (offered to the
pitcher skill head beside k_rel), raw and game power for hitters, and defence (field,
arm, position value) for hitters. Each arm is one column (or one declared set of
columns) offered to the SKILL head of the assembled Driver System V2 and admitted or
refused inside every fold by V2's own DS-06 rule (efv_v2_model.fit_v2(extra=...)). A
refused column leaves the fold equal to the V2 base.

SOURCE AND DATING. The grades come from the dated board snapshots in prospects.db
(table snapshots, sources fangraphs and mlb_pipeline; tools_json carries the FUTURE
grade per tool and, for FanGraphs, the PRESENT grade under _extras.present; the
Pipeline boards of 2011 to 2013 print present/future grades on the 2 to 8 scale inside
the report text, parsed by report_grades, a structured grade winning where both exist). A
row's value reads, per source, the LATEST snapshot dated on or before the row's own
as-of date and no more than LOOKBACK_DAYS before it; nothing dated after the as-of
date is ever read (test-pinned on fixtures), and no snapshot dated on or after
SNAPSHOT_CAP is loaded at all. The as-of date is the date of the read the row's
consensus came from:
    lv_dev   the frame row's asof_date (the latest point inside the V preseason window,
             efv_vintage_frame), for every training and test row;
    vm_dev   the timing-pinned preseason read for a test row (efv_v2_model.
             pinned_inputs receipts) and the matrix row's own asof_date for a training
             row (efv_v2_model.matrix_training_rows reads the same date for BMI).
Where both sources carry a grade the column is their mean; where one does, it is that
one; where neither does, None (the fit imputes the observed training mean, as for
every sidecar driver; no missingness flag ever enters a head).

DATED VINTAGES ON DISK (snapshots, preseason boards): MLB Pipeline future grades for
hit, game power, run, field, arm and fb, sl, cb, ch, control on every list vintage
2011 to 2019 (thin in 2011 and 2012; 2011 to 2013 from the report text, which also
carries present grades; no raw power anywhere, no present grade after 2013); FanGraphs future
AND present grades for hit, game power, raw power, run, field, arm and fb, sl, cb, ch,
command from list vintage 2017 (boards 2017-02-15, 2018-02-15, 2019-02-13, plus
midseason 2018-08-01 and 2019-07-31). The coverage receipt in the artifact counts
every column per vintage and side.

DEFAULTS (named, owner may choose otherwise): LOOKBACK_DAYS 400 (one prior board may
carry forward, as the frame's own grades do); the two sources averaged with equal
weight; the best breaking ball is the larger of slider and curveball per source; arm is
FanGraphs `throw` (else its _extras arm) and Pipeline `throw`; position value is the
FanGraphs positional adjustment in runs per 162 games of the first listed non-pitcher
position at the as-of read (FanGraphs position first, Pipeline second), with generic
OF and IF at the mean of their positions and UTIL at 0.

THE READ (development mode). Frames: lv_dev (list vintages 2017 to 2019, W3, the
screening lab's Frame on the frozen label) and vm_dev (frame version vm2, debut years
2017 to 2023, career WAR to date, the DS-16 rows). No reserved frame: list vintages
2020 and 2021 are never built (efv_vintage_frame guard), no 2025 or later debut cohort
is scored (reserved_vm_pins, the fold years and an as-of cap), and nothing is grouped
by consensus-FV level (test-pinned source scan). Per arm and frame: the within
(side, vintage) Spearman delta against the V2 base and against PROSPX consensus, the
pooled and contributor-AUC legs beside them, each with its paired, player-clustered
E_cond CI95 (efv_v2_stat.paired_delta, B 2000, seed 20260906); the admitted folds;
the per-fold deltas; one zero-information twin (the column permuted within vintage);
and on lv_dev the DS-03 balance probe of the column's missingness. It selects nothing
and adjudicates nothing: EW2-6 lets the owner SELECT one configuration on these
development numbers and then confirm it ONCE on the reserved frames, which this
module never reads.

Run:  python efv_w2_scout.py --check     (frames, base parity and coverage; no statistic)
      python efv_w2_scout.py             (the development read; writes
                                           data/_labs/efv_w2/efv_w2_scout.json and this
                                           module's own progress-ledger rows)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

DB_PATH = ROOT / "prospects.db"
OUT_PATH = ROOT / "data" / "_labs" / "efv_w2" / "efv_w2_scout.json"
TOOL = "efv_w2_scout.py"
ITEM = "EFV3_W2_1a_SCOUT_GRADES"
MODEL_PREFIX = "efv_w2_scout:wave2"
SOURCES: tuple[str, ...] = ("fangraphs", "mlb_pipeline")
LOOKBACK_DAYS = 400
#: No snapshot dated on or after this day is loaded: the first reserved debut cohort's
#: year (R-VM). Every as-of date this module reads is earlier still.
SNAPSHOT_CAP = f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01"
KEY_PREFIX = f"{H.V2_SCREEN_PREFIX}w2s_"
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
FRAMES = ("lv_dev", "vm_dev")
CONS = SB.CONSENSUS_KEY
NOTE = "wave 2 scouting-grade arm; development frame, spent, selects nothing, not a claim"
VERDICT = ("development only: wave 2 scouting-grade arm (EW2-6); selects nothing by "
           "itself and adjudicates nothing")

#: FanGraphs positional adjustment, runs per 162 games (the fWAR constants).
POSITION_RUNS: dict[str, float] = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5,
                                   "LF": -7.5, "RF": -7.5, "1B": -12.5, "DH": -17.5}
POSITION_RUNS["OF"] = round((POSITION_RUNS["CF"] + POSITION_RUNS["LF"]
                             + POSITION_RUNS["RF"]) / 3.0, 4)
POSITION_RUNS["IF"] = round((POSITION_RUNS["2B"] + POSITION_RUNS["3B"]
                             + POSITION_RUNS["SS"]) / 3.0, 4)
POSITION_RUNS["INF"] = POSITION_RUNS["IF"]
POSITION_RUNS["UTIL"] = 0.0
POSITION_RUNS["UT"] = 0.0
_PITCHER_POS = frozenset({"P", "RHP", "LHP", "SP", "RP"})

#: The columns. side, the tool keys read, which grade (future or FanGraphs present),
#: and how sources combine.
COMPONENTS: dict[str, dict] = {
    "fb": {"side": "pit", "keys": ("fb",), "grade": "future",
           "what": "fastball future grade"},
    "brk": {"side": "pit", "keys": ("sl", "cb"), "grade": "future", "per_source": "max",
            "what": "best breaking ball future grade (larger of slider and curveball)"},
    "ch": {"side": "pit", "keys": ("ch",), "grade": "future",
           "what": "changeup future grade"},
    "cmd": {"side": "pit", "keys": ("cmd",), "grade": "future",
            "what": "control (Pipeline) or command (FanGraphs) future grade"},
    "cmd_present": {"side": "pit", "keys": ("cmd",), "grade": "present",
                    "what": "present command or control grade (FanGraphs from 2017, "
                            "Pipeline report text 2011 to 2013)"},
    "raw_pwr": {"side": "hit", "keys": ("raw_pwr",), "grade": "future",
                "what": "raw power future grade (FanGraphs; Pipeline carries none)"},
    "game_pwr": {"side": "hit", "keys": ("game_pwr",), "grade": "future",
                 "what": "game power future grade"},
    "pwr_present": {"side": "hit", "keys": ("game_pwr",), "grade": "present",
                    "what": "present game power grade (FanGraphs from 2017, Pipeline "
                            "report text 2011 to 2013)"},
    "field": {"side": "hit", "keys": ("field",), "grade": "future",
              "what": "fielding future grade"},
    "arm": {"side": "hit", "keys": ("throw",), "grade": "future",
            "what": "arm (throwing) future grade"},
    "posval": {"side": "hit", "keys": (), "grade": "position",
               "what": "positional adjustment (runs per 162) of the listed position at "
                       "the as-of read"},
}

#: The arms: one column, or one declared set, offered to the skill head. Single-column
#: arms are in the screening lab's candidate shape (tools/efv_screen_lab.py
#: w2_candidates); the set arms are read by this module only.
ARMS: tuple[dict, ...] = tuple(
    [{"name": f"w2s_{c}_{COMPONENTS[c]['side']}", "side": COMPONENTS[c]["side"],
      "head": "skill", "kind": "column", "retest": False,
      "column": {"source": "module", "module": "efv_w2_scout", "attr": "screen_column",
                 "arg": c},
      "components": (c,), "what": COMPONENTS[c]["what"]}
     for c in ("fb", "brk", "ch", "cmd", "cmd_present", "raw_pwr", "game_pwr",
               "pwr_present", "field", "arm", "posval")]
    + [{"name": "w2s_arsenal_set_pit", "side": "pit", "head": "skill",
        "kind": "column_set", "retest": False,
        "column": {"source": "module", "module": "efv_w2_scout", "attr": "screen_column",
                   "set": ["fb", "brk", "ch", "cmd"]},
        "components": ("fb", "brk", "ch", "cmd"),
        "what": "the four pitch and command grades offered together beside k_rel, each "
                "admitted or refused on its own"},
       {"name": "w2s_defence_set_hit", "side": "hit", "head": "skill",
        "kind": "column_set", "retest": False,
        "column": {"source": "module", "module": "efv_w2_scout", "attr": "screen_column",
                   "set": ["field", "arm", "posval"]},
        "components": ("field", "arm", "posval"),
        "what": "field, arm and position value offered together, each admitted or "
                "refused on its own"}])


def column_key(component: str) -> str:
    return f"{KEY_PREFIX}{component}"


# ---------------------------------------------------------------------------
# the dated snapshot index
# ---------------------------------------------------------------------------

def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


#: Report-text grade labels (Pipeline 2011 to 2013) to tool keys.
REPORT_LABELS: dict[str, str] = {
    "hit": "hit", "power": "game_pwr", "run": "speed", "arm": "throw", "field": "field",
    "fastball": "fb", "fb": "fb", "curveball": "cb", "curve": "cb", "curvel": "cb",
    "slider": "sl", "changeup": "ch", "change": "ch", "control": "cmd", "cutter": "ct",
    "splitter": "sp", "split": "sp"}
_REPORT_HEAD = re.compile(r"Scouting Grades\*?\s*\(present/future\):\s*(.*)", re.S)
_REPORT_SEG = re.compile(r"([A-Za-z]+(?: [A-Za-z]+)?)\s*:\s*(\d{1,2})\s*/\s*(\d{1,2})")


def report_grades(text) -> tuple[dict, dict]:
    """(future, present) tool grades on the 20 to 80 scale from a report's
    "Scouting Grades (present/future)" line; a 2 to 8 grade is read times ten."""
    if not text or "present/future" not in str(text):
        return {}, {}
    m = _REPORT_HEAD.search(str(text))
    if not m:
        return {}, {}
    fut, pre = {}, {}
    for lab, p, f in _REPORT_SEG.findall(m.group(1)[:240]):
        k = REPORT_LABELS.get(lab.strip().lower())
        if k is None:
            continue
        pv, fv = int(p), int(f)
        pv, fv = (pv * 10 if pv <= 8 else pv), (fv * 10 if fv <= 8 else fv)
        if 20 <= fv <= 80 and k not in fut:
            fut[k] = float(fv)
        if 20 <= pv <= 80 and k not in pre:
            pre[k] = float(pv)
    return fut, pre


class SnapshotIndex:
    """{player_key: [(snapshot_date, source, tools, present, extras, position)]} over
    the board snapshots of SOURCES dated before SNAPSHOT_CAP, sorted by date."""

    def __init__(self, entries: dict[str, list[tuple]]):
        self.by_key = {k: sorted(v, key=lambda e: (e[0], e[1])) for k, v in entries.items()}

    @classmethod
    def from_db(cls, path: Path | str = DB_PATH) -> "SnapshotIndex":
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            q = ("select source, snapshot_date, player_key, position, tools_json "
                 "from snapshots where source in (%s) and snapshot_date < ?"
                 % ",".join("?" * len(SOURCES)))
            rows = con.execute(q, (*SOURCES, SNAPSHOT_CAP)).fetchall()
        finally:
            con.close()
        return cls.from_rows(rows)

    @classmethod
    def from_rows(cls, rows) -> "SnapshotIndex":
        """rows: (source, snapshot_date, player_key, position, tools_json)."""
        out: dict[str, list[tuple]] = {}
        for src, sd, pk, pos, tj in rows:
            if not pk or not sd or src not in SOURCES or str(sd)[:10] >= SNAPSHOT_CAP:
                continue
            try:
                t = json.loads(tj) if tj else {}
            except ValueError:
                t = {}
            t = t if isinstance(t, dict) else {}
            ex = t.get("_extras") if isinstance(t.get("_extras"), dict) else {}
            tools = {k: _f(v) for k, v in t.items() if k != "_extras"}
            present = {k: _f(v) for k, v in (ex.get("present") or {}).items()}
            # Pipeline 2011 to 2013 boards print the grades inside the report text
            # ("Scouting Grades (present/future): Fastball: 5/6 | ..."); a structured
            # grade wins where both exist
            fut_t, pre_t = report_grades(ex.get("report"))
            for k, v in fut_t.items():
                if tools.get(k) is None:
                    tools[k] = v
            for k, v in pre_t.items():
                if present.get(k) is None:
                    present[k] = v
            extras = {"arm": _f(ex.get("arm"))}
            out.setdefault(pk, []).append((str(sd)[:10], src, tools, present, extras,
                                           pos))
        return cls(out)

    def asof(self, player_key: str, asof_date: str | None,
             lookback_days: int = LOOKBACK_DAYS) -> dict[str, tuple]:
        """{source: entry} the latest snapshot per source dated on or before asof_date
        and no earlier than lookback_days before it. {} when the date is missing."""
        if not asof_date:
            return {}
        hi = str(asof_date)[:10]
        if hi >= SNAPSHOT_CAP:
            raise F.ReservedFrameError(f"as-of {hi} reaches the R-VM cap {SNAPSHOT_CAP}")
        lo = (date.fromisoformat(hi) - timedelta(days=int(lookback_days))).isoformat()
        out: dict[str, tuple] = {}
        for e in self.by_key.get(player_key) or ():
            if lo <= e[0] <= hi:
                out[e[1]] = e            # sorted by date: the latest wins
        return out


def _position_runs(pos: str | None) -> float | None:
    if not pos:
        return None
    for tok in str(pos).replace("-", "/").split("/"):
        t = tok.strip().upper()
        if t in _PITCHER_POS or not t:
            continue
        if t in POSITION_RUNS:
            return float(POSITION_RUNS[t])
    return None


def component_value(comp: str, per_source: dict[str, tuple]) -> float | None:
    """One component's value off the as-of entries of each source (see the module
    docstring for the combination rule)."""
    spec = COMPONENTS[comp]
    if spec["grade"] == "position":
        for src in SOURCES:                       # FanGraphs first, then Pipeline
            e = per_source.get(src)
            if e is not None:
                v = _position_runs(e[5])
                if v is not None:
                    return v
        return None
    vals = []
    for src in SOURCES:
        e = per_source.get(src)
        if e is None:
            continue
        _sd, _s, tools, present, extras, _pos = e
        if spec["grade"] == "present":
            got = [present.get(k) for k in spec["keys"]]
        else:
            got = [tools.get(k) for k in spec["keys"]]
            if comp == "arm" and got[0] is None:
                got = [extras.get("arm")]
        got = [g for g in got if g is not None]
        if not got:
            continue
        vals.append(max(got) if spec.get("per_source") == "max" else got[0])
    return float(sum(vals) / len(vals)) if vals else None


def values_for(slots, comp: str, index: SnapshotIndex) -> dict:
    """{slot: value | None} for slots [(slot, player_key, asof_date)]."""
    return {slot: component_value(comp, index.asof(pk, asof)) for slot, pk, asof in slots}


_INDEX: SnapshotIndex | None = None


def default_index() -> SnapshotIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = SnapshotIndex.from_db()
    return _INDEX


def lv_slots(side: str, frames: dict) -> list[tuple]:
    """[((V, player_key), player_key, asof_date)] over the side's F-LV frame rows
    (the efv_v2_assemble.build_frames shape). Reserved vintages raise."""
    out = []
    for V, entry in sorted((frames.get(side) or {}).items()):
        V = int(V)
        F.guard_score_request(V, purpose="scouting-grade column")
        rows = entry[0] if isinstance(entry, (tuple, list)) else entry
        for r in rows:
            out.append(((V, r["player_key"]), r["player_key"], r.get("asof_date")))
    return out


def screen_column(arg: str, side: str, frames: dict, *,
                  index: SnapshotIndex | None = None) -> dict:
    """The screening lab's column (source "module", attr screen_column, arg the
    component): {(V, player_key): value | None} over the side's F-LV frames."""
    if arg not in COMPONENTS:
        raise ValueError(f"unknown scouting component {arg!r}")
    if COMPONENTS[arg]["side"] != side:
        raise ValueError(f"{arg} is a {COMPONENTS[arg]['side']} column, not {side}")
    return values_for(lv_slots(side, frames), arg, index or default_index())


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------

def coverage(values: dict, slot_year) -> dict:
    """{year: {"slots": n, "observed": n, "share": x}} by the slot's year."""
    out: dict = {}
    for slot, v in values.items():
        y = str(slot_year(slot))
        c = out.setdefault(y, {"slots": 0, "observed": 0})
        c["slots"] += 1
        c["observed"] += int(v is not None)
    for c in out.values():
        c["share"] = round(c["observed"] / c["slots"], 4) if c["slots"] else None
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def guards(lv_folds, vm_years) -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    for v in lv_folds:
        F.guard_score_request(int(v), purpose="wave 2 scouting read")
    if set(int(v) for v in lv_folds) & set(F.RESERVED_LV):
        raise F.ReservedFrameError(f"a reserved list vintage is a fold: {lv_folds}")
    bad = [y for y in vm_years if int(y) >= F.R_VM_FIRST_DEBUT_YEAR]
    if bad:
        raise F.ReservedFrameError(f"vm years reach R-VM: {bad}")
    if H.RULE_LAST_YEAR >= min(lv_folds):
        raise ValueError("the combiner rule's years overlap the folds")
    return {"reserved_lv": sorted(F.RESERVED_LV), "lv_folds": list(lv_folds),
            "vm_years": list(vm_years), "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins, "snapshot_cap": SNAPSHOT_CAP,
            "rule_last_year": H.RULE_LAST_YEAR}


# ---------------------------------------------------------------------------
# vm_dev: the DS-16 vintage-matched rows, refit per fold
# ---------------------------------------------------------------------------

class VmFrame:
    """vm_dev at frame version vm2: per (side, debut year) the matrix training rows,
    the timing-pinned test rows and the DS-16 scored rows (outcome career WAR to date),
    each training and test row carrying its as-of date."""

    def __init__(self, folds: dict, years: list[int], weights: dict, meta: dict):
        self.folds = folds          # {(side, yr): {"train", "test", "scored", "base"}}
        self.years = years
        self.weights = weights
        self.meta = meta
        self.train = {s: [] for s in F.SIDES}     # the DS-03 probe's rows
        for (s, yr), blk in folds.items():
            if yr == max(y for (ss, y) in folds if ss == s):
                self.train[s] = [r for r in blk["train"] if r.get("target") is not None]

    @classmethod
    def build(cls, weights: dict, *, log=print) -> "VmFrame":
        import efv_drivers as DRV
        import efv_v2_dev_read as DR
        frame_rows, meta = DR.v2_vm_dev(H.DATA_DIR, weights)
        years = [y for y in meta["fold_years"] if y in set(meta["years"])]
        panel = DRV.load_bio_panel()
        folds: dict = {}
        for side in F.SIDES:
            raw = json.loads(H._matrix_path(side).read_text(encoding="utf-8"))
            asof_raw = {r["player_key"]: r.get("asof_date") for r in raw}
            data = [r for r in H.matrix_training_rows(side)
                    if int(r["decision_year"]) <= max(years)]
            mine: dict = {}
            pinned = H.pinned_inputs(side, data, mine)
            for yr in years:
                tr = [dict(r, asof_date=asof_raw.get(r["player_key"]))
                      for r in data if r["decision_year"] < yr]
                te = [r for r in data if r["decision_year"] == yr]
                if len(te) < H.MIN_TEST_ROWS or len(tr) < H.MIN_TRAIN_ROWS:
                    continue
                te2 = []
                for r in te:
                    pin = pinned.get(r["player_key"])
                    if pin is None:
                        continue
                    asof = mine[r["player_key"]].get("asof_date")
                    extra = {"bmi": DRV.bmi_asof(r["player_key"], asof, panel)}
                    te2.append(dict(r, feats=pin["feats"], fv=pin["fv"], extra=extra,
                                    v2=H.v2_row(pin["feats"], extra), asof_date=asof))
                model = H.fit_v2(tr, side, frame="vm", weights=weights)
                base = {p["player_key"]: float(p["order_idx"])
                        for p in H.predict_v2(model, te2)}
                scored = []
                for c in frame_rows:
                    if c["side"] != side or int(c["year"]) != yr:
                        continue
                    if c["key"] not in base:
                        raise RuntimeError(f"vm {side} {yr}: {c['key']} not scored")
                    if base[c["key"]] != float(c["grades"][DR.V2_KEY]):
                        raise RuntimeError(f"vm {side} {yr}: V2 base differs for {c['key']}")
                    g = {CONS: float(c["grades"][CONS])}
                    for src in SB.SCORED_SOURCES:
                        if c["grades"].get(src) is not None:
                            g[src] = float(c["grades"][src])
                    scored.append({"key": c["key"], "group": f"{side}|{yr}",
                                   "cons": float(c["grades"][CONS]),
                                   "w3": float(c["outcome"]["war"]),
                                   "contributor": bool(c["outcome"]["contributor"]),
                                   "grades": g})
                folds[(side, yr)] = {"train": tr, "test": te2, "scored": scored,
                                     "base": base, "base_model": model}
                log(f"  vm {side} {yr}: {len(tr)} train, {len(te2)} test, "
                    f"{len(scored)} scored")
        return cls(folds, years, weights, meta)

    def slots(self, side: str) -> list[tuple]:
        """[((decision_year, player_key), player_key, asof_date)] over every training
        and test row of the side (a training row may serve several folds)."""
        seen: dict = {}
        for (s, _yr), blk in self.folds.items():
            if s != side:
                continue
            for kind in ("train", "test"):
                for r in blk[kind]:
                    seen.setdefault((int(r["decision_year"]), r["player_key"], kind),
                                    r.get("asof_date"))
        out = []
        for (y, pk, kind), asof in sorted(seen.items()):
            if asof and str(asof)[:10] >= SNAPSHOT_CAP:
                raise F.ReservedFrameError(f"vm row {pk} as-of {asof} reaches the cap")
            out.append(((y, pk, kind), pk, asof))
        return out


def _with_cols(rows: list[dict], cols: dict[str, dict], kind: str) -> list[dict]:
    """Rows with the columns attached to their v2 view (copies)."""
    out = []
    for r in rows:
        add = {k: vals.get((int(r["decision_year"]), r["player_key"], kind))
               for k, vals in cols.items()}
        out.append(dict(r, v2=dict(r["v2"], **add)))
    return out


def vm_orders(vm: VmFrame, side: str, cols: dict[str, dict], *,
              force: bool = False) -> tuple[dict, dict]:
    """The candidate order on every scored vm row of the side, and fold receipts.
    `force` admits the columns without the DS-06 rule (the forced sensitivity)."""
    order, folds = {}, {}
    keys = tuple(cols)
    for (s, yr), blk in sorted(vm.folds.items()):
        if s != side:
            continue
        tr = _with_cols(blk["train"], cols, "train")
        te = _with_cols(blk["test"], cols, "test")
        m = H.fit_v2(tr, side, frame="vm", weights=vm.weights,
                     extra={"skill": keys, "force": bool(force)})
        pred = {p["player_key"]: float(p["order_idx"]) for p in H.predict_v2(m, te)}
        for c in blk["scored"]:
            order[(yr, c["key"])] = pred[c["key"]]
        folds[f"{side}|{yr}"] = _fold_receipt(tr, m, keys, force=force)
    return order, folds


def _fold_receipt(train: list[dict], m: dict, keys, *, force: bool = False) -> dict:
    head = m.get("skill") or {}
    if force:
        return {"forced": True, "any_admitted": True,
                "skill_keys": list(head.get("keys") or []),
                "beta": [round(float(b), 5) for b in head.get("beta") or []],
                "w_skill": m.get("w_skill"), "consensus_only": m.get("consensus_only")}
    adm = {}
    for k in keys:
        chk = H.admission_for_key(train, k, target="u_y", has_block_only=True)
        adm[k] = {"admitted": bool(chk["admitted"]), "reason": chk["reason"],
                  "mean_abs_t": chk["mean_abs_t"],
                  "per_vintage_signs": chk["per_vintage_signs"]}
    return {"admitted": {k: v["admitted"] for k, v in adm.items()},
            "any_admitted": any(v["admitted"] for v in adm.values()),
            "skill_keys": list(head.get("keys") or []), "checks": adm,
            "w_skill": m.get("w_skill"), "consensus_only": m.get("consensus_only")}


def _vm_cols(vm: VmFrame, side: str, order: dict):
    keys, groups, y, pos, a, b, cons, grades = [], [], [], [], [], [], [], []
    for (s, yr), blk in sorted(vm.folds.items()):
        if s != side:
            continue
        for c in blk["scored"]:
            keys.append(c["key"])
            groups.append(c["group"])
            y.append(c["w3"])
            pos.append(c["contributor"])
            a.append(order[(yr, c["key"])])
            b.append(blk["base"][c["key"]])
            cons.append(c["cons"])
            grades.append(c["grades"])
    return keys, groups, y, pos, a, b, cons, grades


# ---------------------------------------------------------------------------
# lv_dev: the screening lab's Frame
# ---------------------------------------------------------------------------

def lv_orders(frame, side: str, cols: dict[str, dict], *,
              force: bool = False) -> tuple[dict, dict]:
    """The candidate order on every test row of the side's lv folds (all columns
    offered to the skill head together), and fold receipts. `force` admits the
    columns without the DS-06 rule (the forced sensitivity)."""
    for k, vals in cols.items():
        frame.attach(side, k, vals)
    try:
        order, folds = {}, {}
        for V in frame.folds:
            m = frame.fit(side, V, extra={"skill": tuple(cols), "force": bool(force)})
            for p in H.predict_v2(m, frame.tests[(side, V)]):
                order[(V, p["player_key"])] = p["order_idx"]
            folds[f"{side}|{V}"] = _fold_receipt(frame.fold_train(side, V), m,
                                                 tuple(cols), force=force)
    finally:
        for k in cols:
            frame.detach(side, k)
    return order, folds


# ---------------------------------------------------------------------------
# statistics (shared by both frames)
# ---------------------------------------------------------------------------

def _delta(cols, statistic: str, *, B: int) -> dict:
    keys, groups, y, pos, a, b, cons, _g = cols
    d = S.paired_delta(keys, groups, y, pos, a, b, cons, statistic=statistic, B=B,
                       seed=SEED)
    d["reading"] = S.reading(d.get("ci95"))
    return d


def _legs(cols, *, B: int) -> dict:
    return {"spearman": _delta(cols, "within", B=B), "pooled": _delta(cols, "pooled", B=B),
            "auc": _delta(cols, "auc", B=B)}


def _vs_cons(cols) -> tuple:
    keys, groups, y, pos, a, b, cons, g = cols
    return keys, groups, y, pos, a, list(cons), cons, g


def _base_vs_cons(cols) -> tuple:
    keys, groups, y, pos, a, b, cons, g = cols
    return keys, groups, y, pos, b, list(cons), cons, g


def _raters(cols) -> dict:
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


def _fold_deltas(cols) -> dict:
    keys, groups, y, pos, a, b, cons, _g = cols
    codes = np.asarray([str(g) for g in groups])
    keep = S.kept_groups(codes, S.MIN_GROUP_ROWS)
    out = {}
    for u in sorted(str(k) for k in keep):
        ix = np.where(codes == u)[0]
        wa, n, _ = S.within(np.asarray(a), np.asarray(y), codes, [u], ix)
        wb, _, _ = S.within(np.asarray(b), np.asarray(y), codes, [u], ix)
        d = None if (wa is None or wb is None) else round(wa - wb, 5)
        out[u] = {"n": int(n), "delta": d, "sign": (0 if not d else (1 if d > 0 else -1))}
    return out


def _within_point(cols) -> float | None:
    keys, groups, y, pos, a, b, cons, _g = cols
    codes = np.asarray([str(g) for g in groups])
    keep = S.kept_groups(codes, S.MIN_GROUP_ROWS)
    wa, _, _ = S.within(np.asarray(a), np.asarray(y), codes, keep)
    wb, _, _ = S.within(np.asarray(b), np.asarray(y), codes, keep)
    return None if (wa is None or wb is None) else round(wa - wb, 5)


def permuted(values: dict, seed: int) -> dict:
    """The column permuted within its slot year over the slots it covers (the twin)."""
    rng = np.random.default_rng(seed)
    by: dict = {}
    for slot, v in values.items():
        by.setdefault(int(slot[0]), []).append((slot, v))
    out = {}
    for y in sorted(by):
        items = sorted(by[y], key=lambda kv: tuple(str(x) for x in kv[0]))
        vals = [v for _s, v in items]
        perm = rng.permutation(len(vals))
        for (slot, _v), j in zip(items, perm):
            out[slot] = vals[int(j)]
    return out


def _seed_for(name: str) -> int:
    h = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
    return int((SEED + h) % (2 ** 31 - 1))


def frame_block(cols, *, B: int, frame_id: str, window, folds: dict, n_by_side: dict) -> dict:
    """One arm on one frame, in the DS-16 shape efv_progress.build_dev_rows copies."""
    vs_v2 = _legs(cols, B=B)
    vs_c = _legs(_vs_cons(cols), B=B)
    base_c = _legs(_base_vs_cons(cols), B=B)
    raters = _raters(cols)
    deltas = {"candidate_vs_efv_v2_base": vs_v2, "candidate_vs_prospx_consensus": vs_c,
              "efv_v2_base_vs_prospx_consensus": base_c}
    return {
        "frame_version": "lv1_v2" if frame_id == "lv_dev" else "vm2",
        "window": list(window), "n": len(cols[0]), "n_by_side": n_by_side,
        "n_players": len(set(cols[0])), "groups": sorted(set(cols[1])),
        "statistic": S.STAT_LABEL[S.PRIMARY], "raters": raters, "deltas": deltas,
        "secondary": {"statistic": S.STAT_LABEL["pooled"],
                      "raters": {n: r.get("pooled") for n, r in raters.items()},
                      "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                                     "ci95": (d.get("pooled") or {}).get("ci95"),
                                     "mde95": (d.get("pooled") or {}).get("mde95"),
                                     "reading": (d.get("pooled") or {}).get("reading")}
                                 for n, d in deltas.items()}},
        "admitted_folds": sum(1 for f in folds.values() if f["any_admitted"]),
        "n_folds": len(folds), "folds": folds, "fold_deltas": _fold_deltas(cols),
        "verdict": VERDICT, "note": NOTE}


# ---------------------------------------------------------------------------
# the run
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


def build_values(lv_frame, frames: dict, vm: VmFrame | None, index: SnapshotIndex) -> dict:
    """{component: {"lv": values, "vm": values}} for every component, built once."""
    out = {}
    for comp, spec in COMPONENTS.items():
        side = spec["side"]
        out[comp] = {"lv": values_for(lv_slots(side, frames), comp, index)}
        if vm is not None:
            out[comp]["vm"] = values_for(vm.slots(side), comp, index)
    return out


def coverage_receipt(values: dict, lv_frame=None) -> dict:
    """Per component: the lv coverage by list vintage over every frame row of the side
    and the vm coverage by decision year over the test (scored-fold) rows and the
    training rows."""
    rec = {}
    for comp, v in values.items():
        side = COMPONENTS[comp]["side"]
        blk = {"side": side, "what": COMPONENTS[comp]["what"],
               "lv_by_vintage": coverage(v["lv"], lambda s: s[0])}
        if "vm" in v:
            blk["vm_test_by_debut_year"] = coverage(
                {s: x for s, x in v["vm"].items() if s[2] == "test"}, lambda s: s[0])
            blk["vm_train_by_decision_year"] = coverage(
                {s: x for s, x in v["vm"].items() if s[2] == "train"}, lambda s: s[0])
        rec[comp] = blk
    return rec


def run_arm(arm: dict, lv_frame, vm: VmFrame, values: dict, *, B: int, log=print) -> dict:
    side = arm["side"]
    comps = arm["components"]
    out = {"name": arm["name"], "side": side, "head": arm["head"], "kind": arm["kind"],
           "components": list(comps), "what": arm["what"],
           "model_id": f"{MODEL_PREFIX}:{arm['name']}:{side}",
           "columns": {c: column_key(c) for c in comps}, "frames": {}, "twin": {},
           "balance": None}
    t0 = time.time()
    # lv_dev
    cols = {column_key(c): values[c]["lv"] for c in comps}
    order, folds = lv_orders(lv_frame, side, cols)
    import efv_screen_lab as LAB
    lv_cols = LAB._columns(lv_frame, (side,), order)
    out["frames"]["lv_dev"] = frame_block(
        lv_cols, B=B, frame_id="lv_dev", window=[min(lv_frame.folds), max(lv_frame.folds)],
        folds=folds, n_by_side={side: len(lv_cols[0])})
    tw = {k: permuted(v, _seed_for(f"twin:lv:{arm['name']}:{k}")) for k, v in cols.items()}
    tw_order, tw_folds = lv_orders(lv_frame, side, tw)
    tw_cols = LAB._columns(lv_frame, (side,), tw_order)
    out["twin"]["lv_dev"] = {"within": _within_point(tw_cols),
                             "admitted_folds": sum(1 for f in tw_folds.values()
                                                   if f["any_admitted"])}
    slots = lv_frame.slots(side)
    bal = {}
    for k, v in cols.items():
        if any(v.get(s) is None for s in slots):
            ind = LAB._missing_indicator(v, slots)
            bal[k] = LAB.balance_probe(lv_frame, side, ind,
                                       seed=_seed_for(f"balance:{arm['name']}:{k}"))
    out["balance"] = {"lv_dev": bal}
    out["forced"] = {"lv_dev": forced_block(
        LAB._columns(lv_frame, (side,), lv_orders(lv_frame, side, cols, force=True)[0]),
        B=B)}
    # vm_dev
    vcols = {column_key(c): values[c]["vm"] for c in comps}
    vorder, vfolds = vm_orders(vm, side, vcols)
    vm_cols = _vm_cols(vm, side, vorder)
    out["frames"]["vm_dev"] = frame_block(
        vm_cols, B=B, frame_id="vm_dev", window=[min(vm.years), max(vm.years)],
        folds=vfolds, n_by_side={side: len(vm_cols[0])})
    vtw = {k: permuted(v, _seed_for(f"twin:vm:{arm['name']}:{k}")) for k, v in vcols.items()}
    vtw_order, vtw_folds = vm_orders(vm, side, vtw)
    out["twin"]["vm_dev"] = {"within": _within_point(_vm_cols(vm, side, vtw_order)),
                             "admitted_folds": sum(1 for f in vtw_folds.values()
                                                   if f["any_admitted"])}
    out["forced"]["vm_dev"] = forced_block(
        _vm_cols(vm, side, vm_orders(vm, side, vcols, force=True)[0]), B=B)
    out["elapsed_s"] = round(time.time() - t0, 1)
    for fid in FRAMES:
        f = out["frames"][fid]
        d2 = f["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
        dc = f["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  {fid}: vs V2 {d2.get('delta')} {d2.get('ci95')}; vs consensus "
            f"{dc.get('delta')} {dc.get('ci95')}; admitted folds {f['admitted_folds']} of "
            f"{f['n_folds']}; twin {out['twin'][fid]['within']}; forced vs V2 "
            f"{out['forced'][fid]['vs_v2']['delta']} "
            f"{out['forced'][fid]['vs_v2']['ci95']}")
    return out


def forced_block(cols, *, B: int) -> dict:
    """The forced sensitivity: the columns admitted WITHOUT the DS-06 rule in every
    fold (efv_v2_model.fit_v2 extra force), read against the V2 base and consensus.
    It says what the column would move if V2 took it; V2's own rule decides whether
    it does (the frame block above). Selected nowhere by this module."""
    return {"rule": "admission bypassed in every fold (fit_v2 extra force)",
            "vs_v2": _delta(cols, "within", B=B),
            "vs_v2_pooled": _delta(cols, "pooled", B=B),
            "vs_consensus": _delta(_vs_cons(cols), "within", B=B),
            "fold_deltas": _fold_deltas(cols)}


def summary_table(arms: list[dict]) -> list[dict]:
    rows = []
    for a in arms:
        r = {"arm": a["name"], "side": a["side"]}
        for fid in FRAMES:
            f = a["frames"][fid]
            d2 = f["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            dc = f["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
            r[fid] = {"vs_v2": d2.get("delta"), "vs_v2_ci95": d2.get("ci95"),
                      "vs_consensus": dc.get("delta"), "vs_consensus_ci95": dc.get("ci95"),
                      "admitted_folds": f"{f['admitted_folds']} of {f['n_folds']}",
                      "twin_vs_v2": a["twin"][fid]["within"],
                      "forced_vs_v2": a["forced"][fid]["vs_v2"].get("delta"),
                      "forced_vs_v2_ci95": a["forced"][fid]["vs_v2"].get("ci95"),
                      "forced_vs_consensus": a["forced"][fid]["vs_consensus"].get("delta"),
                      "forced_vs_consensus_ci95":
                          a["forced"][fid]["vs_consensus"].get("ci95")}
        rows.append(r)
    return rows


def run(*, B: int = B_DEFAULT, only: set | None = None, check: bool = False,
        log=print) -> dict:
    import efv_labels as L
    import efv_screen_lab as LAB
    t0 = time.time()
    lv_frame, frames = LAB.real_frame()
    log(f"lv frame built ({round(time.time() - t0, 1)} s): {json.dumps(lv_frame.counts)}")
    vm = VmFrame.build(lv_frame.weights, log=log)
    g = guards(lv_frame.folds, vm.years)
    log(f"vm frame built ({round(time.time() - t0, 1)} s); guards {json.dumps(g)}")
    index = default_index()
    values = build_values(lv_frame, frames, vm, index)
    doc = {
        "schema": 1, "item": ITEM, "produced_by": TOOL,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": "development", "adjudicates": False, "selects": False,
        "exploratory": False, "owner_decision": "EW2-6 (2026-10-08)",
        "note": NOTE,
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                  "id": LAB.label_id()},
        "guards": g,
        "code": {"commit": _commit(), "tool": TOOL, "sha256": _sha(Path(__file__)),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "weights": lv_frame.weights, "assembly_sha256": _sha(H.ASSEMBLY_PATH),
        "defaults": {"lookback_days": LOOKBACK_DAYS, "sources": list(SOURCES),
                     "source_combination": "equal-weight mean of the sources carrying "
                                           "the grade",
                     "best_breaking_ball": "larger of slider and curveball per source",
                     "arm": "throw, else FanGraphs _extras arm",
                     "position_runs": POSITION_RUNS,
                     "position_source_order": list(SOURCES)},
        "estimator": {"B": int(B), "seed": SEED, "estimator": "E_cond", "paired": True,
                      "unit": "player cluster",
                      "statistic": {"primary": S.STAT_LABEL[S.PRIMARY],
                                    "secondary": S.STAT_LABEL[S.SECONDARY],
                                    "veto": S.STAT_LABEL["auc"]}},
        "frames": {"lv_dev": {"folds": list(lv_frame.folds), "counts": lv_frame.counts,
                              "w_star_dev": lv_frame.w_star, "label": "W3"},
                   "vm_dev": {"years": vm.years, "frame_version": "vm2",
                              "label": "career WAR to date",
                              "dropped": vm.meta.get("dropped"),
                              "per_fold": {f"{s}|{y}": {"n_train": len(b["train"]),
                                                        "n_test": len(b["test"]),
                                                        "n_scored": len(b["scored"])}
                                           for (s, y), b in sorted(vm.folds.items())}}},
        "coverage": coverage_receipt(values),
        "not_read": ["list vintages 2020 and 2021 (R-LV)",
                     "debut cohorts 2025 and later (R-VM)",
                     "no grouping by consensus-FV level"],
        "prior_closed_arms": ("the v1 driver re-tests on the fWAR label (data/"
                              "xfv_arm_ledger.json: H-MECH tool_field and tool_throw, "
                              "H-NOMECH tool_game_pwr, P-MECH tool_sl, tool_ch, tool_cmd, "
                              "ABL drop-tool_fb, all NULL) read the consensus tool means on "
                              "the v1 frame; this read offers the dated per-source grades "
                              "to the V2 skill head and is disclosed as a re-look the "
                              "owner ordered (EW2-6)"),
    }
    if check:
        doc["check"] = True
        return doc
    arms = []
    for arm in ARMS:
        if only and arm["name"] not in only:
            continue
        log(f"arm {arm['name']} ({arm['side']}, {', '.join(arm['components'])})")
        arms.append(run_arm(arm, lv_frame, vm, values, B=B, log=log))
    doc["arms"] = arms
    doc["summary"] = summary_table(arms)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def write_doc(doc: dict, out: Path = OUT_PATH) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n"
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)


# ---------------------------------------------------------------------------
# the progress ledger: this module's own development rows
# ---------------------------------------------------------------------------

def arm_docs(doc: dict) -> list[dict]:
    """One development document per arm in the shape efv_progress.build_dev_rows
    reads, with a `screening` block so the Source Comparison page lists the row in its
    collapsed screening block and never charts it (no verdict is PASS)."""
    out = []
    for a in doc.get("arms") or []:
        scr = {"wave": 2, "lane": "1a", "item": ITEM, "head": a["head"], "side": a["side"],
               "kind": a["kind"], "components": a["components"], "exploratory": False,
               "development_only": True, "artifact": "data/_labs/efv_w2/efv_w2_scout.json",
               "admitted_folds": {fid: a["frames"][fid]["admitted_folds"] for fid in FRAMES},
               "twin_within": {fid: a["twin"][fid]["within"] for fid in FRAMES}}
        out.append({"role": "development", "model_id": a["model_id"],
                    "generated_at": doc.get("generated_at"), "label": doc.get("label") or {},
                    "code": doc.get("code") or {}, "screening": scr,
                    "frames": {fid: a["frames"][fid] for fid in FRAMES}})
    return out


def update_progress(doc: dict, *, artifact: Path = OUT_PATH, data_dir: Path | None = None,
                    out_path: Path | None = None, ledger_path: Path | None = None) -> dict:
    """This module's rows alone, appended to data/efv_progress.json (efv_progress
    .commit_rows). `ledger_path` names the durable ledger to merge and append; the run
    passes a private one so no other lane's rows enter this tree's file."""
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    data_dir = Path(data_dir) if data_dir is not None else H.DATA_DIR
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    cands = []
    for d in arm_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now.date().isoformat(),
                                  trigger="efv_change", now_iso=now_iso, frames=FRAMES,
                                  raters=P.SCREEN_RATERS, deltas=P.SCREEN_DELTAS,
                                  statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no rows"}
    res = P.commit_rows(cands, data_dir=data_dir, out_path=out_path,
                        ledger_path=ledger_path,
                        sb=P._load_json(data_dir / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="frames, base parity and coverage only; no statistic")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    ap.add_argument("--only", default="", help="comma-separated arm names")
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--ledger-path", default=None,
                    help="the durable progress ledger to merge (default efv_progress's)")
    a = ap.parse_args(argv)
    only = {s.strip() for s in a.only.split(",") if s.strip()} or None
    doc = run(B=a.B, only=only, check=a.check)
    if a.check:
        print(json.dumps({"guards": doc["guards"], "label": doc["label"],
                          "frames": doc["frames"], "coverage": doc["coverage"]}, indent=1))
        return 0
    out = Path(a.out)
    write_doc(doc, out)
    print(f"wrote {out} ({len(doc['arms'])} arms, {doc['elapsed_s']} s)")
    for r in doc["summary"]:
        print(json.dumps(r))
    if not a.no_ledger and a.B == B_DEFAULT and not only:
        res = update_progress(doc, artifact=out,
                              ledger_path=Path(a.ledger_path) if a.ledger_path else None)
        print(f"progress: {len(res.get('appended') or [])} row(s) appended, "
              f"{res.get('n_rows')} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())

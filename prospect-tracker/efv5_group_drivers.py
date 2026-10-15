# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 group drivers (EFV5_GROUP_DRIVERS; owner 2026-10-14, decisions EW3-1 to EW3-5,
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): the eFV v5 metric atlas's candidates on the
metric families that carry a long label, built as Driver System V2 columns that apply
only inside their own group, selected on the development frames by the rule of
docs/efv-v2/EFV_V5_BACKTEST.md and read once on the spent reserved frames.

DARK. EFV_V5_ON is False: nothing served reads this module's fit while it is off
(efv_v2_serve.production_models checks the flag and fits V2 as before). The flag flips
only through the ship rule of the backtest document (EW2-10: the selection beats served
V2 on lv_dev, vm_dev, R-LV and R-VM, point estimates pooled over sides).

THE MENU (menu_columns), derived from data/efv5_metric_atlas.json and nothing else:
    1. every atlas candidate cell on a CLEAN frame (status "clean": its label window
       closes before the 2025 debut cohort), of a family with a long label (box, season
       lines 2005+; pbp, pitch calls 2007+), whose incremental lift over consensus is
       above 0 with the CI95 lower bound above 0 and q at or below CANDIDATE_Q;
       spent-overlap cells select nothing (atlas rule);
    2. one column per (side, level, age band, role or position group, statistic): the
       level-and-age relative version of a rate ("_rel") and its raw version are one
       statistic, and so are age and age for level (identical inside a level-season);
       the cell with the smallest q represents it (then the larger lift, then the raw
       name), whichever label it was read on;
    3. the head: age is arrival evidence, so an age column goes to the TIMING head
       (Driver System V2 principle 4: timing is not talent); every performance
       statistic goes to the SKILL head;
    4. menu order: q ascending, then lift descending, then name.
The group of a column is the atlas cell's group, fixed by the atlas before any read.

THE COLUMN (metric times a group indicator). A row read at year Y as of a cutoff reads
season S, the last MiLB season that had ended by the read (efv_w2_milb's as-of rule,
identical), stepped back over 2020 (no MiLB season was played). The row is IN the
column's group when the player has a qualified line (100 PA or 100 batters faced) at
the column's level in season S, no MLB line in any season at or before S, an age band
that matches (terciles of age inside the level-season's qualified lines, the atlas's
bands) and, for a pitcher role group, a role that matches (games started over games
below one half is RP, the EFV3_C05 rule). An in-group row's value is the statistic
z-scored inside its level-season (mean and sd over the qualified lines; pitch-call
statistics over the lines the pitch-call aggregate keeps), centered at the mean of the
in-group rows of the same (side, read year) on the frame being built (a predictor-only
transform: no outcome and no grade is read), so the column carries the statistic
within the group and not the group's own level. Every other row, and an in-group row
whose statistic is missing, takes 0: the interaction's zero. The person id is the
row's OUTCOME-BLIND id (`mlbam_id` on a list-vintage frame row; the matrix id on a
vintage-matched row, read at its decision year as of its matrix cutoff, as the MiLB
profile family reads it).

THE CONFIGURATION SPACE. As eFV v4: V2 (efv_v2_model.fit_v2 at the P5 weights the
owner kept, EW2-9) with columns ADDED to a head under the unchanged DS-06 admission
rule inside every fold; nothing is re-weighted, removed or re-anchored. fit_v5 is
efv_v3.fit_v3 at an add-only configuration with the v5 columns registered in
efv_v3.W2_COLUMNS for the life of the call (registered()); at base_config() it is
fit_v2 bit for bit (test_efv5_group_drivers.py).

THE BACKTEST (this module's CLI; tools/efv_screen_lab.py registers it as wave 5):
    --check      build the development inputs and every menu column, assert V2 parity,
                 print coverage; no statistic of any candidate.
    --select     the forward selection on lv_dev and vm_dev exactly as the document
                 fixes it; writes data/_labs/efv5/efv5_group_select.json, the selected
                 configuration to data/_labs/efv5/efv5_group_spec.json and two
                 development rows (model efv_v5) to data/efv_progress.json.
    --spent --gate-sha SHA
                 the ONE read of the committed configuration on R-LV and R-VM, both
                 SPENT since the 10-08 confirmation, labelled spent, no ledger row;
                 writes data/_labs/efv5/efv5_group_spent.json.
    --ledger     re-append the selection's development rows (the integration path).

RESERVED FRAMES. The development build reads no reserved row (efv_vintage_frame's guard
raises on list vintages 2020 and 2021; the vm window stops before the 2025 cohort). The
spent read opens them only with the committed gate sha, as the v4 spent read did.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters V2 as a within-group
percentile and as the value multiset the grade is drawn from; the column's groups are
level, age band and role, never a consensus-FV level. Nothing here groups, counts or
averages rows by consensus-FV level; test_efv5_group_drivers.py scans this source.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import efv_v2_model as H
import efv_v3 as V3
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
ATLAS_PATH = DATA_DIR / "efv5_metric_atlas.json"
SELECT_PATH = LAB_DIR / "efv5_group_select.json"
SPENT_PATH = LAB_DIR / "efv5_group_spent.json"
SPEC_PATH = LAB_DIR / "efv5_group_spec.json"
#: This task's own durable copy of the progress ledger rows it appends.
LEDGER_PATH = ROOT / ".cache" / "efv5_group_drivers" / "progress_ledger.jsonl"
TOOL = "efv5_group_drivers.py"
ITEM = "EFV5_GROUP_DRIVERS"
WAVE = 5

#: THE SWITCH. False: nothing served reads a v5 fit. Flips through the ship rule only.
EFV_V5_ON = False
MODEL_ID = "efv_v5"
BACKTEST_DOC = "docs/efv-v2/EFV_V5_BACKTEST.md"
RESULTS_DOC = "docs/efv-v2/EFV_V5_RESULTS.md"
HEADS: tuple[str, ...] = V3.HEADS
#: The atlas families that carry a long label (season lines 2005+, pitch calls 2007+).
LONG_FAMILIES: tuple[str, ...] = ("box", "pbp")
CANDIDATE_Q = 0.10
#: Statistics read as arrival evidence (the timing head); everything else is skill.
TIMING_BASES = frozenset({"age"})
#: Seasons in which no MiLB season was played; a read steps back over them.
NO_SEASON = frozenset({2020})
#: A level-season z norm needs this many lines (the atlas's NORM_MIN_LINES).
NORM_MIN_LINES = 30
#: The pitcher role rule (EFV3_C05): games started over games below this is RP.
RP_GS_SHARE = 0.5
SPENT_LABEL = "spent frame, read after the 10-08 confirmation"
NOTE_SELECT = ("eFV v5 group drivers, forward selection on the development frames "
               "(spent, not a claim); owner EW3-1 to EW3-3, rule EW2-10")
NOTE_SPENT = ("eFV v5 group drivers at the committed configuration on the spent reserved "
              "frames (read once by v3 on 2026-10-08); chooses and tunes nothing; not a look")

_METRIC_RE = re.compile(r"^(?P<base>.+?)(?:_rel_level|_rel)?_(?P<side>hit|pit)$")
_MENU: dict | None = None


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ---------------------------------------------------------------------------
# the menu, derived from the atlas
# ---------------------------------------------------------------------------

def metric_base(metric: str) -> str:
    """The statistic a metric name measures: "k_pct_rel_pit" and "k_pct_pit" are
    "k_pct"; "age_rel_level_hit" and "age_hit" are "age"."""
    m = _METRIC_RE.match(str(metric))
    if not m:
        raise ValueError(f"not an atlas metric name: {metric!r}")
    return m.group("base")


def _token(s: str) -> str:
    return str(s).replace("+", "p").replace("-", "m").replace("/", "")


def column_name(side: str, level: str, band: str, group: str, base: str) -> str:
    return f"g5_{side}_{_token(level)}_{band}_{_token(group)}_{base}"


def load_atlas(path: Path | None = None) -> dict:
    p = ATLAS_PATH if path is None else Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def eligible_cells(atlas: dict) -> list[dict]:
    """The atlas candidates this task may build (module docstring, step 1)."""
    out = []
    for c in atlas.get("candidates") or []:
        if c.get("status") != "clean" or c.get("frame") != "clean":
            continue
        if c.get("family") not in LONG_FAMILIES:
            continue
        q, incr, ci = _f(c.get("q")), _f(c.get("incr")), c.get("ci95") or [None, None]
        lo = _f(ci[0])
        if q is None or incr is None or lo is None:
            continue
        if q <= CANDIDATE_Q and incr > 0 and lo > 0:
            out.append(c)
    return out


def menu_from_atlas(atlas: dict) -> dict[str, dict]:
    """{name: spec} in menu order (module docstring, steps 2 to 4)."""
    best: dict = {}
    for c in eligible_cells(atlas):
        base = metric_base(c["metric"])
        if c["side"] == "hit" and c["group"] != "all":
            raise NotImplementedError("a hitter position-group column needs the as-of "
                                      "listing position, which this builder does not read")
        k = (c["side"], c["level"], c["age_band"], c["group"], base)
        rank = (float(c["q"]), -float(c["incr"]), "_rel" in c["metric"], c["metric"])
        if k not in best or rank < best[k][0]:
            best[k] = (rank, c)
    rows = []
    for (side, level, band, group, base), (rank, c) in best.items():
        name = column_name(side, level, band, group, base)
        rows.append((rank[0], rank[1], name, {
            "side": side, "head": "timing" if base in TIMING_BASES else "skill",
            "metric": c["metric"], "base": base, "family": c["family"], "level": level,
            "band": band, "group": group, "module": "efv5_group_drivers", "arg": name,
            "key": f"{H.V2_SCREEN_PREFIX}{name}",
            "atlas": {"label": c["label"], "incr": c["incr"], "ci95": c["ci95"],
                      "q": c["q"], "n": c.get("n"), "players": c.get("players")}}))
    rows.sort(key=lambda t: (t[0], t[1], t[2]))
    return {name: spec for _q, _i, name, spec in rows}


def menu_columns(*, refresh: bool = False) -> dict[str, dict]:
    """The menu from the committed atlas artifact, memoized per process."""
    global _MENU
    if _MENU is None or refresh:
        menu = menu_from_atlas(load_atlas())
        for n in menu:
            if n in V3.W2_COLUMNS and V3.W2_COLUMNS[n].get("module") != "efv5_group_drivers":
                raise RuntimeError(f"{n} is already a column")
        _MENU = menu
    return _MENU


@contextmanager
def registered(names=None):
    """The v5 menu columns (or `names`) as efv_v3.W2_COLUMNS entries for the life of the
    block; removed afterwards, so the v3 menu is never widened. Re-entrant."""
    menu = menu_columns()
    want = list(menu) if names is None else list(names)
    added_ = []
    try:
        for n in want:
            if n in V3.W2_COLUMNS:
                continue
            spec = menu.get(n)
            if spec is None:
                raise KeyError(f"{n} is not a v5 menu column")
            V3.W2_COLUMNS[n] = {k: spec[k] for k in ("side", "head", "module", "arg", "key")}
            added_.append(n)
        yield V3.W2_COLUMNS
    finally:
        for n in added_:
            V3.W2_COLUMNS.pop(n, None)


# ---------------------------------------------------------------------------
# configurations (efv_v4's add-only space over the v5 menu)
# ---------------------------------------------------------------------------

def base_config() -> dict:
    return V3.base_config()


def added(cfg: dict) -> list[str]:
    return [a for s in F.SIDES for h in HEADS for a in cfg["add"][s][h]]


def validate_config(cfg: dict) -> dict:
    if cfg.get("anchor") is not None:
        raise ValueError("a v5 configuration takes no anchor")
    menu = menu_columns()
    for s in F.SIDES:
        for h in HEADS:
            if float(cfg["scale"][s][h]) != 1.0:
                raise ValueError(f"a v5 configuration keeps the P5 weight of {s} {h}")
            if cfg["remove"][s][h]:
                raise ValueError(f"a v5 configuration removes no driver ({s} {h})")
            for a in cfg["add"][s][h]:
                spec = menu.get(a)
                if spec is None or spec["side"] != s or spec["head"] != h:
                    raise ValueError(f"{a} is not a v5 {s} {h} column")
    with registered(added(cfg)):
        V3.validate_config(cfg)
    return cfg


def is_base(cfg: dict) -> bool:
    return V3.is_base(cfg)


def describe(cfg: dict) -> str:
    parts = [f"{s} {h} plus {a}" for s in F.SIDES for h in HEADS for a in cfg["add"][s][h]]
    return "; ".join(parts) if parts else "V2 as assembled (no step)"


def with_column(cfg: dict, name: str) -> dict:
    spec = menu_columns()[name]
    new = copy.deepcopy(cfg)
    new["add"][spec["side"]][spec["head"]].append(name)
    return validate_config(new)


def fit_v5(train: list[dict], side: str, *, frame: str, weights: dict[str, dict],
           cfg: dict, absent_ok: bool | None = None, gate_sha: str | None = None) -> dict:
    """v5 on one fold's training rows (every added column already on the v2 view under
    its key). At base_config() this is fit_v2's model, bit for bit."""
    validate_config(cfg)
    with registered(added(cfg)):
        m = V3.fit_v3(train, side, frame=frame, weights=weights, cfg=cfg,
                      absent_ok=absent_ok, gate_sha=gate_sha)
    m["model_id"] = MODEL_ID
    return m


def predict_v5(model: dict, rows: list[dict]) -> list[dict]:
    return V3.predict_v3(model, rows)


def load_spec(path: Path | None = None) -> dict:
    p = SPEC_PATH if path is None else Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def spec_config(spec: dict | None = None) -> dict:
    doc = load_spec() if spec is None else spec
    return validate_config(copy.deepcopy(doc["config"]))


def production_models(*, weights: dict | None = None) -> dict[str, dict]:
    """The dark production fit: read only while EFV_V5_ON is True. The live path has no
    v5 column builder: a configuration with an added column raises rather than serving
    a half-built fit (the ship step wires it); the base configuration is V2 itself."""
    cfg = spec_config()
    if added(cfg):
        raise NotImplementedError("the live path has no v5 column builder yet (the ship "
                                  "step of EFV5_GROUP_DRIVERS wires it)")
    w = H.load_weights() if weights is None else weights
    out = {}
    for side in F.SIDES:
        train = [r for r in H.matrix_training_rows(side)
                 if int(r["decision_year"]) < F.train_end_year()]
        m = fit_v5(train, side, frame="vm", weights=w, cfg=cfg)
        m["war_map_6yr"] = H.fit_war_map(train)
        m["train_years"] = sorted({int(r["decision_year"]) for r in train})
        out[side] = m
    return out


# ---------------------------------------------------------------------------
# the column: the season lines, the group test, the z value
# ---------------------------------------------------------------------------

def read_season(read_year: int, cutoff: str | None) -> int:
    """The last MiLB season that had ended by the read (efv_w2_milb's rule), stepped
    back over a season that was not played."""
    import efv_w2_milb as WM
    s = WM.last_readable_season(int(read_year), cutoff)
    while s in NO_SEASON:
        s -= 1
    return s


class Lines:
    """One side's qualified MiLB lines with every atlas statistic the menu names, their
    level-season z norms, age bands and pitcher roles, and the MLB seasons of each
    person. Built from the atlas's own readers (efv5_atlas), so a statistic means what
    it meant in the atlas cell.

    `seasons` (default: the atlas's SEASONS, the training build) names the seasons whose
    lines are read. Every norm, age line, age band and role is fitted inside one (season,
    level), so a season's values do not depend on which other seasons are loaded; the live
    board (efv5_combined.live_columns) reads its one season this way, including a season
    newer than the atlas's last."""

    def __init__(self, side: str, metrics, *, seasons=None, log=print):
        import efv5_atlas as A
        t0 = time.time()
        self.side = side
        self.metrics = sorted(set(metrics))
        lines = A.box_lines(side) if seasons is None else A.box_lines(side, tuple(seasons))
        rate_fn = A.hit_rates if side == "hit" else A.pit_rates
        stat_keys = list(A._HIT_BOX if side == "hit" else A._PIT_BOX)
        exp_key = "pa" if side == "hit" else "bf"
        values, ages, qual = {}, {}, {}
        for k, c in lines.items():
            qual[k] = (c.get(exp_key) or 0.0) >= A.QUAL[side]
            ages[k] = c.get("age")
            values[k] = rate_fn(c)
        keys = list(lines)
        rel = A._relative(values, ages, qual, keys, stat_keys)
        self.band = A._age_bands(keys, ages, qual)
        mean_age: dict = {}
        for k in keys:
            if qual[k] and ages.get(k) is not None:
                mean_age.setdefault((k[1], k[2]), []).append(ages[k])
        mean_age = {p: float(np.mean(v)) for p, v in mean_age.items()}
        pbp = A.pbp_metrics(side) if any(m.startswith("pbp_") for m in self.metrics) else {}
        self.vals: dict = {}
        self.role: dict = {}
        for k in keys:
            if not qual[k]:
                continue
            m = {f"{s}_{side}": v for s, v in values[k].items()}
            m.update({f"{s}_{side}": v for s, v in rel[k].items()})
            a = ages.get(k)
            m[f"age_{side}"] = a
            m[f"age_rel_level_{side}"] = ((a - mean_age[(k[1], k[2])])
                                          if a is not None and (k[1], k[2]) in mean_age else None)
            m.update(pbp.get(k) or {})
            self.vals[k] = {x: m.get(x) for x in self.metrics}
            if side == "pit":
                c = lines[k]
                g = c.get("g") or 0.0
                self.role[k] = (("RP" if (c.get("gs") or 0.0) / g < RP_GS_SHARE else "SP")
                                if g > 0 else None)
        # z norms per (season, level, metric) over the qualified lines that carry it
        pools: dict = {}
        for k, m in self.vals.items():
            for x, v in m.items():
                if v is not None:
                    pools.setdefault((k[1], k[2], x), []).append(float(v))
        self.norm = {}
        for p, vs in pools.items():
            if len(vs) < NORM_MIN_LINES:
                continue
            arr = np.asarray(vs, dtype=np.float64)
            sd = float(arr.std())
            if sd > 0:
                self.norm[p] = (float(arr.mean()), sd)
        self.mlb = A.mlb_seasons()
        log(f"  lines {side}: {len(lines)} level-season lines, {len(self.vals)} qualified, "
            f"pbp {len(pbp)}, {len(self.norm)} norms ({round(time.time() - t0, 1)} s)")

    def member(self, pid, season: int, spec: dict) -> tuple[bool, float | None]:
        """(in the column's group, z value or None) for one person at season S."""
        if not pid:
            return False, None
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False, None
        k = (pid, int(season), spec["level"])
        m = self.vals.get(k)
        if m is None:
            return False, None
        if any(y <= int(season) for y in self.mlb.get(pid, ())):
            return False, None
        if spec["band"] != "all" and self.band.get(k) != spec["band"]:
            return False, None
        if self.side == "pit" and spec["group"] != "all" and self.role.get(k) != spec["group"]:
            return False, None
        v = m.get(spec["metric"])
        nm = self.norm.get((int(season), spec["level"], spec["metric"]))
        if v is None or nm is None:
            return True, None
        return True, (float(v) - nm[0]) / nm[1]


_LINES: dict = {}


def lines_for(side: str, *, log=print) -> Lines:
    metrics = [s["metric"] for s in menu_columns().values() if s["side"] == side]
    if side not in _LINES:
        _LINES[side] = Lines(side, metrics, log=log)
    return _LINES[side]


def centered(reads: dict, names) -> tuple[dict, dict]:
    """reads {(year, slot id): {name: (in group, z)}} -> ({name: {(year, slot id):
    value}}, {name: {year: in-group count}}): in-group z centered at the mean of the
    in-group values of the same year, every other slot 0."""
    out: dict = {n: {} for n in names}
    cnt: dict = {n: {} for n in names}
    for n in names:
        acc: dict = {}
        for (y, sid), r in reads.items():
            ing, z = r[n]
            if ing:
                cnt[n][y] = cnt[n].get(y, 0) + 1
            if ing and z is not None:
                acc.setdefault(y, []).append(z)
        mean = {y: float(np.mean(v)) for y, v in acc.items()}
        for (y, sid), r in reads.items():
            ing, z = r[n]
            out[n][(y, sid)] = (z - mean[y]) if (ing and z is not None) else 0.0
    return out, cnt


def lv_columns(side: str, rows_by_v: dict, names, *, gate_sha: str | None = None,
               log=print) -> tuple[dict, dict]:
    """({name: {(V, player_key): value}}, in-group counts) on list-vintage frame rows,
    each read on its outcome-blind id at its own window start."""
    for V in rows_by_v:
        F.guard_score_request(int(V), gate_sha=gate_sha, purpose="v5 group column")
    menu = menu_columns()
    ln = lines_for(side, log=log)
    reads = {}
    for V in sorted(rows_by_v):
        for r in rows_by_v[V]:
            S = read_season(int(V), (r.get("window") or [None])[0])
            reads[(int(V), r["player_key"])] = {
                n: ln.member(r.get("mlbam_id"), S, menu[n]) for n in names}
    return centered(reads, names)


def vm_columns(side: str, data: list[dict], raw_by_key: dict, names, *,
               gate_sha: str | None = None, log=print) -> tuple[dict, dict]:
    """({name: {(decision year, player_key): value}}, in-group counts) on the
    vintage-matched matrix rows, read on the matrix id at the decision year as of the
    matrix cutoff. A 2025 or later decision year is skipped unless the committed gate
    sha opens the cohort (the spent read; efv_vintage_frame.guard_vm_request). With
    EFV_TRAIN_THROUGH_2026 on the bound is efv_vintage_frame.train_end_year()."""
    end = F.train_end_year()
    late = {int(d["decision_year"]) for d in data
            if int(d["decision_year"]) >= end}
    allow_reserved = False
    if gate_sha:
        F.guard_vm_request(late, gate_sha=gate_sha, purpose="v5 group column")
        allow_reserved = True
    menu = menu_columns()
    ln = lines_for(side, log=log)
    reads = {}
    for d in data:
        y = int(d["decision_year"])
        if y >= end and not allow_reserved:
            continue
        raw = raw_by_key.get(d["player_key"]) or {}
        S = read_season(y, raw.get("cutoff"))
        reads[(y, d["player_key"])] = {n: ln.member(raw.get("mlbam_id"), S, menu[n])
                                       for n in names}
    return centered(reads, names)


# ---------------------------------------------------------------------------
# the backtest: inputs (tools/efv_v3_backtest's machinery, efv_v4_backtest's shape)
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)
    import efv_v3_backtest as BT
    import efv_v4_backtest as B4
    return BT, B4


def _raw_by_side() -> dict:
    return {s: {r["player_key"]: r for r in json.loads(
        H._matrix_path(s).read_text(encoding="utf-8"))} for s in F.SIDES}


def _slots(inp, fid: str, side: str):
    for _fold, blk in inp.frames[fid]["by_side"][side].items():
        for kind in ("train", "test"):
            for r in blk[kind]:
                yield (int(r["decision_year"]), r["player_key"], kind)


def build_columns(inp, fids, rows_lv: dict, names, *, gate_sha: str | None = None,
                  log=print) -> tuple[dict, dict]:
    """({fid: {side: {name: {(year, pk, kind): value}}}}, receipts) for the named
    columns on the frames of `inp` (development: lv_dev, vm_dev; spent: lv_res,
    vm_pros). rows_lv is {side: {V: frame rows}} over every list vintage a fold reads."""
    lv_fid, vm_fid = fids
    names = list(names)
    menu = menu_columns()
    cols = {fid: {s: {} for s in F.SIDES} for fid in fids}
    rec: dict = {"coverage": {fid: {} for fid in fids}, "in_group_by_year": {}}
    raw = _raw_by_side()
    for side in F.SIDES:
        mine = [n for n in names if menu[n]["side"] == side]
        if not mine:
            continue
        t0 = time.time()
        lv_vals, lv_cnt = lv_columns(side, rows_lv[side], mine, gate_sha=gate_sha, log=log)
        vm_vals, vm_cnt = vm_columns(side, H.matrix_training_rows(side), raw[side], mine,
                                     gate_sha=gate_sha, log=log)
        for n in mine:
            lv_map = {}
            for slot in _slots(inp, lv_fid, side):
                lv_map[slot] = lv_vals[n].get((slot[0], slot[1]), 0.0)
            vm_map = {}
            for slot in _slots(inp, vm_fid, side):
                vm_map[slot] = vm_vals[n].get((slot[0], slot[1]), 0.0)
            cols[lv_fid][side][n] = lv_map
            cols[vm_fid][side][n] = vm_map
            for fid, mp in ((lv_fid, lv_map), (vm_fid, vm_map)):
                te = [k for k in mp if k[2] == "test"]
                rec["coverage"][fid][n] = {
                    "slots": len(mp), "nonzero": sum(1 for v in mp.values() if v != 0.0),
                    "test_slots": len(te),
                    "test_nonzero": sum(1 for k in te if mp[k] != 0.0)}
            rec["in_group_by_year"][n] = {
                "lv": {str(y): c for y, c in sorted(lv_cnt[n].items())},
                "vm": {str(y): c for y, c in sorted(vm_cnt[n].items())}}
        log(f"  columns {side}: {len(mine)} built ({round(time.time() - t0, 1)} s)")
    return cols, rec


def build_dev(*, names=None, log=print):
    """efv_v4_backtest.build_dev with no v4 column (V2 parity with DS-16 and v3 at
    base_config asserted there), then the v5 menu columns."""
    BT, B4 = _tools()
    inp, frames_lv, _rec = B4.build_dev(names=[], log=log)
    names = list(menu_columns()) if names is None else list(names)
    t0 = time.time()
    rows_lv = {s: {int(V): rows for V, (rows, _l) in frames_lv[s].items()} for s in F.SIDES}
    cols, rec = build_columns(inp, BT.FRAMES_DEV, rows_lv, names, log=log)
    inp.cols = cols
    inp.meta["elapsed_columns_s"] = round(time.time() - t0, 1)
    inp.meta["column_receipts"] = rec
    return inp, frames_lv, rec


def build_spent(cfg: dict, *, gate_sha: str, log=print):
    """The reserved frames through efv_v3_backtest.build_reserved at V2 (frame rows
    captured), V2 parity asserted, then the configuration's columns."""
    BT, _B4 = _tools()
    import efv_w2_il_backfill as W2I
    inp, got = W2I.build_reserved_capturing(gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    inp.meta["v5_base_parity"] = parity
    log(f"v5 at base_config reproduces V2 on the spent frames ({parity['rows']} rows)")
    rows_lv = {s: {} for s in F.SIDES}
    for s in F.SIDES:
        for V, (rows, _l) in (got["dev"] or {}).get(s, {}).items():
            rows_lv[s][int(V)] = rows
    for (s, V), rows in got["res"].items():
        rows_lv[s][int(V)] = rows
    t0 = time.time()
    cols, rec = build_columns(inp, BT.FRAMES_RES, rows_lv, added(cfg), gate_sha=gate_sha,
                              log=log)
    inp.cols = cols
    inp.meta["elapsed_columns_s"] = round(time.time() - t0, 1)
    inp.meta["column_receipts"] = rec
    return inp, rec


# ---------------------------------------------------------------------------
# names: the shared machinery labelled v5 for the life of a run
# ---------------------------------------------------------------------------

def _names():
    BT, _B4 = _tools()
    cand, v2 = BT.V3_KEY, BT.V2_KEY
    raters = ((cand, "efv_v5"), (v2, "efv_v2"), (BT.CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
    comps = (("v5_vs_efv_v2", cand, v2), ("v5_vs_prospx_consensus", cand, BT.CONS),
             ("v5_vs_mlb_pipeline", cand, "mlb_pipeline"),
             ("v5_vs_fangraphs", cand, "fangraphs"),
             ("efv_v2_vs_prospx_consensus", v2, BT.CONS))
    return raters, comps


@contextmanager
def v5_names():
    BT, _B4 = _tools()
    raters, comps = _names()
    orig = (BT.COMPARISONS, BT.RATERS_OUT)
    BT.COMPARISONS, BT.RATERS_OUT = comps, raters
    try:
        yield
    finally:
        BT.COMPARISONS, BT.RATERS_OUT = orig


# ---------------------------------------------------------------------------
# the selection
# ---------------------------------------------------------------------------

def menu_steps(cfg: dict) -> list[dict]:
    taken = set(added(cfg))
    return [{"kind": "add", "side": s["side"], "head": s["head"], "column": n,
             "family": s["family"], "sides": [s["side"]],
             "name": f"add:{s['side']}.{s['head']}.{n}"}
            for n, s in menu_columns().items() if n not in taken]


def apply_step(cfg: dict, step: dict) -> dict:
    if step["kind"] != "add":
        raise ValueError(step)
    return with_column(cfg, step["column"])


def _group_rows(inp, fid: str, rows: list[dict], name: str) -> list[dict]:
    """The scored rows of `fid` whose test slot is in the column's group (a nonzero
    value; an in-group row at exactly its year's mean reads as outside)."""
    cols = ((inp.cols.get(fid) or {}).get(menu_columns()[name]["side"]) or {}).get(name) or {}
    keep = {(k[0], k[1]) for k, v in cols.items() if k[2] == "test" and v != 0.0}
    return [c for c in rows if (int(c["year"]), c["key"]) in keep]


def group_cells(inp, fid: str, rows: list[dict], cfg: dict, *, B: int, seed: int) -> dict:
    """Per added column: the scored rows inside its group, v5 minus V2 and v5 minus
    consensus within (E_cond) on them. Groups are level, age band and role; never an FV
    cell."""
    BT, _B4 = _tools()
    keep = ("delta", "ci95", "mde95", "n", "status", "reading")
    out = {}
    for n in added(cfg):
        sel = _group_rows(inp, fid, rows, n)
        blk = {"n": len(sel), "n_players": len({c["key"] for c in sel})}
        if len(sel) >= 20:
            blk["v5_vs_efv_v2"] = {k: v for k, v in BT.paired(
                sel, BT.V3_KEY, BT.V2_KEY, "within", B=B, seed=seed).items() if k in keep}
            blk["v5_vs_prospx_consensus"] = {k: v for k, v in BT.paired(
                sel, BT.V3_KEY, BT.CONS, "within", B=B, seed=seed).items() if k in keep}
        else:
            blk["status"] = "under 20 rows; not scored"
        out[n] = blk
    return out


def cell_block(rows: list[dict], *, B: int, seed: int) -> dict:
    """The position-group cells (efv_strata.position_family on hitters; pitchers one
    cell; never an FV cell)."""
    BT, _B4 = _tools()
    import efv_v2_stat as S
    keep = ("delta", "ci95", "mde95", "n", "status", "reading")
    out = {}
    for side, cell in BT.CELLS:
        sel = [c for c in rows if c["side"] == side and (side == "pit" or c.get("cell") == cell)]
        blk = {"n": len(sel), "n_players": len({c["key"] for c in sel})}
        if len(sel) >= S.MIN_GROUP_ROWS:
            st = BT.rater_stats(sel)
            blk["raters"] = {k: {"within": r["within"], "n": r["n"]} for k, r in st.items()}
            blk["v5_vs_efv_v2"] = {k: v for k, v in BT.paired(
                sel, BT.V3_KEY, BT.V2_KEY, "within", B=B, seed=seed).items() if k in keep}
            blk["v5_vs_prospx_consensus"] = {k: v for k, v in BT.paired(
                sel, BT.V3_KEY, BT.CONS, "within", B=B, seed=seed).items() if k in keep}
        else:
            blk["status"] = f"under {S.MIN_GROUP_ROWS} rows; not scored"
        out[f"{side}:{cell}"] = blk
    return out


def frame_doc(inp, fid: str, cfg: dict, *, B: int, role: str, note: str, log=print) -> dict:
    BT, _B4 = _tools()
    _r, comps = _names()
    orders, rec = inp.orders(fid, cfg)
    rows = inp.rows_with(fid, orders)
    t1 = time.time()
    blk = BT.frame_block(rows, B=B, comparisons=comps)
    blk.update({"frame_version": BT.FRAME_VERSION[fid], "receipts": rec,
                "fold_deltas_vs_v2": BT.fold_deltas(rows, BT.V3_KEY, BT.V2_KEY),
                "fold_deltas_vs_consensus": BT.fold_deltas(rows, BT.V3_KEY, BT.CONS),
                "cells": cell_block(rows, B=B, seed=BT.SEED),
                "group_cells": group_cells(inp, fid, rows, cfg, B=B, seed=BT.SEED),
                "role": role, "note": note,
                "window": [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])]})
    w = blk["deltas"]["v5_vs_efv_v2"]["spearman"]
    c = blk["deltas"]["v5_vs_prospx_consensus"]["spearman"]
    log(f"  {fid}: vs V2 {w.get('delta')} {w.get('ci95')}; vs consensus {c.get('delta')} "
        f"{c.get('ci95')} ({round(time.time() - t1, 1)} s stats)")
    return blk


def select(inp, *, B: int, log=print, checkpoint: Path | None = None) -> dict:
    BT, _B4 = _tools()
    t0 = time.time()
    cfg = base_config()
    rounds, taken = [], []
    cur = {fid: inp.orders(fid, cfg)[0] for fid in BT.FRAMES_DEV}
    for rnd in range(1, BT.MAX_STEPS + 1):
        steps = menu_steps(cfg)
        log(f"round {rnd}: {len(steps)} steps available; current: {describe(cfg)}")
        evals = []
        for step in steps:
            t1 = time.time()
            ev = BT.evaluate_step(inp, cfg, step, cur)
            ev["family"] = step["family"]
            ev["elapsed_s"] = round(time.time() - t1, 1)
            ev["qualifies"] = BT.qualifies(ev)
            evals.append(ev)
            lvd, vmd = ev["frames"]["lv_dev"], ev["frames"]["vm_dev"]
            log(f"  {step['name']:52s} lv {lvd.get('scope_delta')} vm {vmd.get('scope_delta')}"
                f"{' QUALIFIES' if ev['qualifies'] else ''} ({ev['elapsed_s']} s)")
        best = None
        for i, ev in enumerate(evals):
            if ev["qualifies"] and (best is None or ev["frames"]["lv_dev"]["scope_delta"]
                                    > evals[best]["frames"]["lv_dev"]["scope_delta"]):
                best = i
        rec = {"round": rnd, "configuration_before": copy.deepcopy(cfg), "evaluated": evals,
               "n_qualifying": sum(1 for e in evals if e["qualifies"]), "admitted": None}
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
        cur = {fid: inp.orders(fid, cfg)[0] for fid in BT.FRAMES_DEV}
        log(f"round {rnd}: ADMITTED {step['name']}; now {describe(cfg)} "
            f"({round(time.time() - t0, 1)} s)")
        if checkpoint is not None:
            BT.write_doc({"partial": True, "rounds": rounds, "config": cfg}, checkpoint)
    if len(taken) >= BT.MAX_STEPS:
        log(f"the cap of {BT.MAX_STEPS} steps is reached")
    frames = {}
    for fid in BT.FRAMES_DEV:
        blk = frame_doc(inp, fid, cfg, B=B, role="development",
                        note=NOTE_SELECT + "; the configuration was selected on this frame",
                        log=log)
        w = blk["deltas"]["v5_vs_efv_v2"]["spearman"]
        c = blk["deltas"]["v5_vs_prospx_consensus"]["spearman"]
        blk["verdict"] = (f"DEVELOPMENT ONLY (selected on these frames): within vs V2 "
                          f"{BT._rnd(w.get('delta'), 4)} (CI95 {w.get('ci95')}), vs consensus "
                          f"{BT._rnd(c.get('delta'), 4)} (CI95 {c.get('ci95')}); adjudicates nothing")
        frames[fid] = blk
    return {"config": cfg, "steps": taken, "rounds": rounds, "frames": frames,
            "elapsed_s": round(time.time() - t0, 1)}


def _code() -> dict:
    BT, _B4 = _tools()
    return {"commit": BT._commit(), "tool": TOOL, "tool_sha256": BT._sha(ROOT / TOOL),
            "efv5_atlas_sha256": BT._sha(ROOT / "efv5_atlas.py"),
            "atlas_artifact_sha256": BT._sha(ATLAS_PATH),
            "efv_v3_sha256": BT._sha(ROOT / "efv_v3.py"),
            "efv_v3_backtest_sha256": BT._sha(ROOT / "tools" / "efv_v3_backtest.py"),
            "efv_v2_model_sha256": BT._sha(ROOT / "efv_v2_model.py"),
            "efv_v2_stat_sha256": BT._sha(ROOT / "efv_v2_stat.py")}


def _menu_doc() -> dict:
    return {n: {k: v for k, v in s.items() if k != "key"} for n, s in menu_columns().items()}


def select_doc(inp, res: dict, *, B: int) -> dict:
    BT, _B4 = _tools()
    import efv_v2_stat as S
    return {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": BT._now(),
        "role": "development", "adjudicates": False, "selects": True, "note": NOTE_SELECT,
        "owner_decision": ("EW3-1 to EW3-3 (2026-10-14): the atlas's long-label candidates "
                           "built as group drivers, selected on the development frames only; "
                           "the reserved frames are spent and reported as such (EW2-10)"),
        "rule": {"doc": BACKTEST_DOC, "min_lv_gain": BT.MIN_LV_GAIN,
                 "vm_tolerance": BT.VM_TOLERANCE, "max_steps": BT.MAX_STEPS,
                 "statistic": S.STAT_LABEL[S.PRIMARY],
                 "scope": "the rows of the side a step touches",
                 "menu": "one ADD step per v5 menu column at its declared head, in menu order",
                 "menu_size": len(menu_columns()), "columns": _menu_doc()},
        "label": inp.label, "code": _code(), "assembly_sha256": BT._sha(H.ASSEMBLY_PATH),
        "weights": inp.weights,
        "bootstrap": {"B": int(B), "seed": BT.SEED, "estimator": "E_cond", "unit": "player cluster"},
        "reserved_guard": inp.guards, "base_parity": inp.meta.get("base_parity"),
        "v5_base_parity": inp.meta.get("v3_base_parity"),
        "column_receipts": inp.meta.get("column_receipts"),
        "selected": {"config": res["config"], "description": describe(res["config"]),
                     "steps": res["steps"], "is_v2": is_base(res["config"])},
        "rounds": res["rounds"], "frames": res["frames"],
        "elapsed_s": round(res["elapsed_s"] + float(inp.meta.get("elapsed_build_s") or 0.0)
                           + float(inp.meta.get("elapsed_columns_s") or 0.0), 1)}


def spec_doc(sel: dict) -> dict:
    return {"schema": 1, "model_id": MODEL_ID, "selected_at": sel["generated_at"],
            "selection_artifact": "data/_labs/efv5/efv5_group_select.json",
            "selection_doc": BACKTEST_DOC, "owner_decision": "EW3-1 to EW3-3 (2026-10-14)",
            "config": sel["selected"]["config"], "description": sel["selected"]["description"],
            "steps": sel["selected"]["steps"], "is_v2": sel["selected"]["is_v2"],
            "columns": {n: sel["rule"]["columns"][n] for n in added(sel["selected"]["config"])},
            "weights_base": sel["weights"], "assembly_sha256": sel["assembly_sha256"],
            "label": sel["label"], "code": sel["code"],
            "flag": "efv5_group_drivers.EFV_V5_ON (False)"}


# ---------------------------------------------------------------------------
# the spent-frame read
# ---------------------------------------------------------------------------

def verdict_text(c: dict, rc: dict, w: dict, rv: dict) -> str:
    d = c.get("delta")
    lo = (rc.get("ci95") or [None, None])[0]
    if d is None:
        return "not derived"
    if lo is not None and lo > 0:
        head = f"eFV v5 beats consensus within by {d:+.4f} (E_refit CI95 clear of zero)"
    elif d > 0:
        head = f"eFV v5 reads {d:+.4f} within over consensus; not resolved (E_refit CI95 spans zero)"
    else:
        head = f"eFV v5 reads {d:+.4f} within against consensus; ties or trails"
    dv = w.get("delta")
    tail = "" if dv is None else f"; vs served eFV (V2) {dv:+.4f} (E_refit CI95 {rv.get('ci95')})"
    return head + tail + f"; {SPENT_LABEL}"


def spent(inp, cfg: dict, *, B: int, b_refit: int, log=print) -> dict:
    BT, _B4 = _tools()
    t0 = time.time()
    frames = {}
    for fid in BT.FRAMES_RES:
        blk = frame_doc(inp, fid, cfg, B=B, role="spent", note=NOTE_SPENT, log=log)
        blk["label"] = SPENT_LABEL
        blk["outcome"] = ("W3 (WAR over the first three MLB seasons, 0 if no debut within "
                          "three seasons of V)" if fid == "lv_res"
                          else "career WAR to date (2025 and 2026 seasons)")
        log(f"  {fid}: E_refit B {b_refit} starts")
        blk["e_refit"] = BT.e_refit(inp, cfg, fid, B=b_refit, log=log, point=blk)
        w = blk["deltas"]["v5_vs_efv_v2"]["spearman"]
        c = blk["deltas"]["v5_vs_prospx_consensus"]["spearman"]
        legs = (blk["e_refit"]["legs"].get("both") or {})
        rc = ((legs.get("v5_vs_prospx_consensus") or {}).get("spearman") or {})
        rv = ((legs.get("v5_vs_efv_v2") or {}).get("spearman") or {})
        blk["verdict"] = verdict_text(c, rc, w, rv)
        frames[fid] = blk
        log(f"  {fid}: vs V2 {w.get('delta')} E_cond {w.get('ci95')} E_refit {rv.get('ci95')}; "
            f"vs consensus {c.get('delta')} E_cond {c.get('ci95')} E_refit {rc.get('ci95')}")
    return {"frames": frames, "elapsed_s": round(time.time() - t0, 1)}


def ship_reading(sel_doc: dict, spent_doc_: dict) -> dict:
    """EW2-10: ship only if v5 beats served V2 in within Spearman on lv_dev, vm_dev, R-LV
    and R-VM, point estimates, pooled over sides."""
    BT, _B4 = _tools()
    out = {"rule": ("EW2-10: ship if v5 beats served eFV (V2) in within Spearman on lv_dev, "
                    "vm_dev, R-LV and R-VM, point estimates, pooled over sides"),
           "frames": {}, "ships": None}
    ok = True
    for fid, doc in [(f, sel_doc) for f in BT.FRAMES_DEV] + [(f, spent_doc_) for f in BT.FRAMES_RES]:
        d = doc["frames"][fid]["deltas"]["v5_vs_efv_v2"]["spearman"].get("delta")
        out["frames"][fid] = d
        ok = ok and d is not None and d > 0
    out["ships"] = bool(ok)
    cons = {}
    for fid in BT.FRAMES_RES:
        legs = ((spent_doc_["frames"][fid].get("e_refit") or {}).get("legs") or {}).get("both") or {}
        rc = (legs.get("v5_vs_prospx_consensus") or {}).get("spearman") or {}
        cons[fid] = {"delta": rc.get("delta"), "e_refit_ci95": rc.get("ci95"),
                     "beats_consensus_resolved": bool(rc.get("ci95") and rc["ci95"][0] > 0)}
    out["vs_consensus_spent"] = cons
    return out


def spent_doc(inp, spec: dict, res: dict, *, B: int, b_refit: int, sel_doc: dict) -> dict:
    BT, _B4 = _tools()
    import efv_v2_stat as S
    doc = {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": BT._now(),
        "role": "spent", "adjudicates": False, "selects": False, "one_read": True,
        "label_note": SPENT_LABEL, "note": NOTE_SPENT, "ledger_rows": False,
        "owner_decision": ("EW3-5 (2026-10-14) and EW2-10: the reserved frames were read once "
                           "by the v3 confirmation and are spent; this read of the committed v5 "
                           "configuration chooses nothing and is labelled spent"),
        "gate": {"doc": F.GATE_DOC, "sha": inp.gate_sha, "guards": inp.guards},
        "spec": {"path": "data/_labs/efv5/efv5_group_spec.json", "sha256": BT._sha(SPEC_PATH),
                 "config": spec["config"], "description": spec.get("description"),
                 "steps": spec.get("steps"), "selected_at": spec.get("selected_at"),
                 "selection_commit": (spec.get("code") or {}).get("commit")},
        "label": inp.label, "code": _code(), "assembly_sha256": BT._sha(H.ASSEMBLY_PATH),
        "weights": inp.weights,
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "secondary": S.STAT_LABEL[S.SECONDARY],
                      "veto": S.STAT_LABEL["auc"], "min_group_rows": S.MIN_GROUP_ROWS,
                      "group": "(side, list vintage) on R-LV; (side, debut year) on R-VM",
                      "cells": "efv_strata.position_family on hitters (C, IF, OF); pitchers one "
                               "cell; each added column's own group"},
        "bootstrap": {"E_cond": {"B": int(B), "seed": BT.SEED, "unit": "player cluster"},
                      "E_refit": {"B": int(b_refit), "seed": BT.SEED_REFIT, "unit": "player cluster"}},
        "frames_built": {"lv_res": {"per_vintage": inp.meta.get("lv_per_vintage"),
                                    "reserved_vm_kept_w3_zero": inp.meta.get("reserved_vm_kept_w3_zero")},
                         "vm_pros": {"per_fold": inp.meta.get("vm_per_fold")}},
        "v5_base_parity": inp.meta.get("v5_base_parity"),
        "column_receipts": inp.meta.get("column_receipts"),
        "frames": res["frames"],
        "elapsed_s": round(res["elapsed_s"] + float(inp.meta.get("elapsed_build_s") or 0.0)
                           + float(inp.meta.get("elapsed_columns_s") or 0.0), 1)}
    doc["ship_rule"] = ship_reading(sel_doc, doc)
    return doc


# ---------------------------------------------------------------------------
# progress-ledger rows (development only)
# ---------------------------------------------------------------------------

_LEDGER_RATERS = (("efv", "efv_v5"), ("efv_v2_base", "efv_v2"),
                  ("prospx_consensus", "prospx_consensus"),
                  ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
_LEDGER_DELTAS = (("vs_efv_v2_base", "v5_vs_efv_v2"),
                  ("vs_prospx_consensus", "v5_vs_prospx_consensus"),
                  ("vs_mlb_pipeline", "v5_vs_mlb_pipeline"),
                  ("vs_fangraphs", "v5_vs_fangraphs"),
                  ("efv_v2_base_vs_prospx_consensus", "efv_v2_vs_prospx_consensus"))


def ledger_rows(doc: dict, *, artifact: Path, date: str, now_iso: str) -> list[dict]:
    """Development rows in data/efv_progress.json's shape, copied from the selection
    artifact (model efv_v5, frames lv_dev and vm_dev, trigger efv_change)."""
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
        for name in ("v5_vs_efv_v2", "v5_vs_prospx_consensus", "v5_vs_mlb_pipeline",
                     "v5_vs_fangraphs"):
            w = f["deltas"][name]["spearman"]
            rl = ((((f.get("e_refit") or {}).get("legs") or {}).get("both") or {})
                  .get(name) or {}).get("spearman") or {}
            out.append(f"{fid} {name:26s} within {w.get('delta')} E_cond {w.get('ci95')}"
                       + (f" E_refit {rl.get('ci95')}" if rl else ""))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--menu", action="store_true", help="print the menu (no frame is built)")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--spent", action="store_true")
    ap.add_argument("--gate-sha", default=None)
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--b-refit", type=int, default=None)
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--ledger", action="store_true",
                    help="re-append the selection artifact's two development rows to "
                         "data/efv_progress.json (a row whose run_id is present is skipped)")
    ap.add_argument("--ledger-path", default=None)
    a = ap.parse_args(argv)
    BT, _B4 = _tools()
    import efv_labels as L
    B = BT.B_DEFAULT if a.B is None else int(a.B)
    b_refit = BT.B_REFIT_DEFAULT if a.b_refit is None else int(a.b_refit)
    ledger_path = Path(a.ledger_path) if a.ledger_path else None

    def log(msg):
        print(msg, flush=True)
    if a.menu:
        for n, s in menu_columns().items():
            log(f"{n:40s} {s['head']:6s} {s['metric']:24s} {s['atlas']['label']} "
                f"lift {s['atlas']['incr']} q {s['atlas']['q']}")
        return 0
    if a.ledger:
        if not SELECT_PATH.exists():
            log("refused: the selection artifact does not exist")
            return 2
        doc = json.loads(SELECT_PATH.read_text(encoding="utf-8"))
        r = append_ledger(doc, artifact=SELECT_PATH, ledger_path=ledger_path)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if L.provider() != BT.FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {BT.FROZEN_PROVIDER!r}")
        return 2
    if a.select or a.check or not a.spent:
        with registered(), v5_names():
            inp, _frames_lv, rec = build_dev(log=log)
            if not a.select:
                counts = {fid: {"folds": inp.frames[fid]["folds"], "n": len(inp.scored(fid)),
                                "n_by_side": BT._n_side(inp.scored(fid))} for fid in BT.FRAMES_DEV}
                log(json.dumps({"check": True, "guards": inp.guards, "counts": counts,
                                "label": inp.label, "weights": inp.weights,
                                "base_parity": inp.meta.get("base_parity"),
                                "v5_base_parity": inp.meta.get("v3_base_parity"),
                                "menu_size": len(menu_steps(base_config())),
                                "coverage": rec["coverage"],
                                "in_group_by_year": rec["in_group_by_year"]},
                               indent=1, default=str))
                return 0
            if SELECT_PATH.exists():
                log(f"refused: {SELECT_PATH} exists; the selection ran once")
                return 2
            part = LAB_DIR / "efv5_group_select_partial.json"
            res = select(inp, B=B, log=log, checkpoint=part)
            doc = select_doc(inp, res, B=B)
            out = BT.write_doc(doc, SELECT_PATH)
            BT.write_doc(spec_doc(doc), SPEC_PATH)
            part.unlink(missing_ok=True)
            log(f"wrote {out} and {SPEC_PATH}: {doc['selected']['description']}")
            if not a.no_ledger:
                r = append_ledger(doc, artifact=out, ledger_path=ledger_path)
                log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
            return 0
    if SPENT_PATH.exists():
        log(f"refused: {SPENT_PATH} exists; the spent frames are read once by this tool")
        return 2
    if not a.gate_sha:
        log("refused: --gate-sha is required (the committed registration)")
        return 2
    if not SELECT_PATH.exists():
        log("refused: the selection comes first")
        return 2
    spec = load_spec()
    cfg = spec_config(spec)
    sel = json.loads(SELECT_PATH.read_text(encoding="utf-8"))
    log(f"configuration: {describe(cfg)} (spec selected at {spec.get('selected_at')})")
    with registered(), v5_names():
        inp, _rec = build_spent(cfg, gate_sha=a.gate_sha, log=log)
        res = spent(inp, cfg, B=B, b_refit=b_refit, log=log)
        doc = spent_doc(inp, spec, res, B=B, b_refit=b_refit, sel_doc=sel)
    out = BT.write_doc(doc, SPENT_PATH)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    for line in summary_lines(doc):
        log(line)
    log(f"ship rule: {json.dumps(doc['ship_rule'], default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

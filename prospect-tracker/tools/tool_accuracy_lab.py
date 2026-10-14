# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""Tool accuracy lab: look P (the power composite), look W (tool source weights
and TAG) and look T (re-derived tool tables), to
docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md (the gate; Parts P, W and T).
Built by TL_4_TOOL_LAB_BUILD; the looks are run once each by TL_5, TL_12 and
TL_21. This build runs no look.

Modes:
    --look P [--gate-sha SHA]                       Part P, once (TL_5)
    --look W [--gate-sha SHA --rlv-record SHA]      Part W, once (TL_12)
    --look T [--registration SHA --mde SHA]         Part T, once (TL_21)
    --look T --mde-only                             Part T.10, FIT rows only (TL_4)
    --look P|W|T --dry-run                          the whole reporting path on
                                                    fixtures carrying None values;
                                                    reads no real row
    --k-m                                           Part 4: split-half reliability on
                                                    MLB player-seasons (no prospect
                                                    join, no grade read)
    --freeze-grade-rows                             Part T.3's frozen grade rows

Everything the gate imports by name is imported here by name, never retyped:
BA2's estimator and gate constants (tools/ba_tool_grade_lab.py, source_backtest),
the vintage window, the reserved frames (efv_vintage_frame) and the outcome-blind
identity (efv_identity). The TIP tables come from tool_implied.

Guards asserted before any score (gate Part 5): the gate sha names a commit
carrying the gate with its REGISTERED status line; no debut year at or after
R_VM_FIRST_DEBUT_YEAR; no board year in RESERVED_LV unless --rlv-record names the
R-LV record; a spent look is refused; no grouping key names a future-value grade
(the source scan in test_tool_accuracy_lab.py). Lab outputs go under data/_labs/,
the eval artifacts (registry eval artifacts that ship) under data/ only at a look.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import source_backtest as SB                                    # noqa: E402
from efv_vintage_frame import (RESERVED_LV, R_VM_FIRST_DEBUT_YEAR,  # noqa: E402
                               gate_doc_registered)
import efv_identity                                             # noqa: E402
import tool_implied as TI                                       # noqa: E402

# BA2's estimator, gate constants, controls and seeds, by name (gate W.1).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ba_tool_grade_lab as BA2                                 # noqa: E402

MIN_LAG_YEARS = BA2.MIN_LAG_YEARS
WEIGHT_SHRINK_K = BA2.WEIGHT_SHRINK_K
WEIGHT_CLAMP = BA2.WEIGHT_CLAMP
SPEARMAN_FLOOR = BA2.SPEARMAN_FLOOR
WIN_START = SB._WINDOW_START_MMDD
WIN_END = SB._WINDOW_END_MMDD
_spearman = SB._spearman
_auc = SB._auc
_cluster_layout = SB._cluster_layout
_cluster_draw = SB._cluster_draw
W_SEED = BA2.SEED
W_SEED_ALT = BA2.SEED_ALT
W_BOOT = BA2.BOOT
W_PERM = BA2.PERM

DATA = ROOT / "data"
CACHE = ROOT / ".cache"
LABS = DATA / "_labs" / "tool_accuracy"
T_LABS = DATA / "_labs" / "tool_tables_rederived"
GATE_DOC = "docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md"
RLV_GATE_DOC = "docs/efv-v2/EFV_V2_GATE.md"
RLV_BACKTEST_DOC = "docs/efv-v2/EFV_V3_BACKTEST.md"
ARTIFACT = {"P": DATA / "power_composite_eval.json",
            "W": DATA / "tool_accuracy_eval.json",
            "T": DATA / "tool_tables_rederived_eval.json"}
FROZEN_ROWS = T_LABS / "grade_rows_frozen.json"
MDE_FOLDS = T_LABS / "mde95_folds.json"
K_M_RECEIPT = LABS / "k_m.json"

SURVIVORSHIP = ("Accuracy AMONG DEBUTS: only players who reached the majors have a realized "
                "MLB quantity, so this is not accuracy over all graded prospects (gate Part 0.6).")

# --- frames and floors (gate Parts P.2, W.8, W.3, T.3) ----------------------
P_YEARS = (2017, 2018, 2019, 2022, 2023, 2024)
W_YEARS = tuple(range(2017, 2025))
MAX_DEBUT_YEAR = R_VM_FIRST_DEBUT_YEAR - 1            # 2024
LAST_OUTCOME_SEASON = 2026
PA_FLOOR = 300
INN_FLOOR = 700.0
BF_FLOOR = 100
THIN_CELL = 20
POOL_MIN = 100
P_SEED = 20261021
P_BOOT = 2000
P_PERM = 1000
P_A_GRID = tuple(round(0.1 * i, 1) for i in range(11))
T_SEED = 20261028
T_BOOT = 2000
T_FIT_SEASONS = tuple(y for y in range(2015, 2026) if y != 2020)
T_VELO_SEASONS = tuple(y for y in range(2017, 2026) if y != 2020)
T_HOLDOUT_SEASON = 2026
T_MIN_ROWS = 60
T_MIN_FOLDS = 5
MDE_Z = 1.645
HOLM_ALPHA = 0.05
OAA_POS = ("3", "4", "5", "6", "7", "8", "9")
OAA_POS_NAMES = {"3": "1B", "4": "2B", "5": "3B", "6": "SS", "7": "LF", "8": "CF", "9": "RF"}
PITCHER_POS = ("P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP")
ARMS = {"A_fg_vs_pipeline": ("fangraphs", "mlb_pipeline"),
        "B_fg_pipeline_ba": ("fangraphs", "mlb_pipeline", "baseballamerica")}

#: Look W primaries (W.2) and secondaries (W.4), with the outcome key, its
#: orientation (sign 1 = higher is better) and its exposure unit.
W_PRIMARY = {
    "hit": {"stat": "k_pct", "sign": -1, "unit": "pa"},
    "speed": {"stat": "sprint", "sign": 1, "unit": "competitive_runs"},
    "field": {"stat": "oaa_per1000", "sign": 1, "unit": "innings"},
    "throw": {"stat": "arm_z", "sign": 1, "unit": "throws"},
}
W_SECONDARY = {
    "game_pwr": {"stat": "iso", "sign": 1, "unit": "ab", "ba2": "NO SHIP"},
    "fb": {"stat": "k_pct_pit", "sign": 1, "unit": "bf", "ba2": "resolved LOSS"},
    "cmd": {"stat": "bb_pct_pit", "sign": -1, "unit": "bf", "ba2": "NO SHIP"},
    "hit_avg": {"tool": "hit", "stat": "avg", "sign": 1, "unit": "ab", "ba2": "TL-Q2 beside"},
    "speed_sb": {"tool": "speed", "stat": "sb_per600", "sign": 1, "unit": "pa", "ba2": "secondary"},
}
#: Single-source tools, TAG table only (W.5).
W_SINGLE = {
    "raw_pwr": {"stat": "ev_avg", "sign": 1, "unit": "attempts"},
    "pitch_sel": {"stat": "chase_pct", "sign": -1, "unit": "oz_pitches"},
    "bat_ctrl": {"stat": "z_contact_pct", "sign": 1, "unit": "iz_swings"},
}

#: Part 4, the k_m stabilization constants (gate Part 4, written by this task's
#: amendment from --k-m; test_tool_accuracy_lab.py pins them to the gate's table).
#: Unit per stat beside each value; None means NOT COMPUTABLE (no 2015-2019
#: per-game or per-event data on disk), so the regressed TAG is not computed.
K_M = {
    "k_pct": {"value": 46.7354, "unit": "pa"},
    "avg": {"value": 468.3212, "unit": "ab"},
    "babip": {"value": 401.5923, "unit": "ab"},
    "iso": {"value": 177.5259, "unit": "ab"},
    "hr_pa": {"value": 197.0406, "unit": "pa"},
    "sb_per600": {"value": 75.7105, "unit": "pa"},
    "ev_avg": {"value": 43.6082, "unit": "attempts"},
    "chase_pct": {"value": 68.3172, "unit": "oz_pitches"},
    "z_contact_pct": {"value": 59.3017, "unit": "iz_swings"},
    "k_pct_pit": {"value": 76.5133, "unit": "bf"},
    "bb_pct_pit": {"value": 225.8052, "unit": "bf"},
    "fb_velo": {"value": 0.2552, "unit": "fastballs"},
    "sprint": {"value": None, "unit": "competitive_runs"},
    "oaa_per1000": {"value": None, "unit": "innings"},
    "arm_z": {"value": None, "unit": "throws"},
    "brl_pa": {"value": None, "unit": "pa"},
}

# --- Part T incumbents (T.1), transcribed; floors disclosed ---------------
T_INCUMBENT = {
    "game_pwr__hr_per600": {"rows": [(30, 4.0), (35, 6.5), (40, 10.0), (45, 13.5), (50, 16.5),
                                     (55, 20.5), (60, 25.0), (65, 28.5), (70, 32.5),
                                     (75, 37.5), (80, 40.0)],
                            "source": "FANGRAPHS_FV_FRAMEWORK.md 2.1 S3 (2014) Homers, per 600 PA; "
                                      "open 80 band read at its stated bound 40 (D1)"},
    "game_pwr__iso": {"rows": [(20, 0.000), (30, 0.038), (40, 0.089), (50, 0.140), (60, 0.191),
                               (70, 0.242), (80, 0.294)],
                      "source": "2.2 Power tool, Smith W2 (2013) ISO; the 20 row -.013 floored "
                                "at .000 (rule 4)"},
    "hit__avg": {"rows": [(30, .220), (35, .230), (40, .240), (45, .250), (50, .260), (55, .270),
                          (60, .280), (65, .290), (70, .300), (75, .310), (80, .320)],
                 "source": "2.1 S3 (2014) Batting Avg"},
    "hit__k_pct": {"rows": None, "source": "grade-blind league line: 100 x sum SO / sum PA over "
                                           "every hitter row of the season with at least 300 PA (D2)"},
    "speed__sb_per600": {"rows": [(20, 0.0), (30, 0.0), (40, 4.5), (50, 9.0), (60, 19.0),
                                  (70, 29.0), (80, 38.0)],
                         "source": "2.2 Speed tool, W2 SB per season read per 600 PA; the 20 and "
                                   "30 rows floored at 0 (rule 4), the blank 40 row interpolated "
                                   "(rule 5)"},
    "cmd__bb_pct_sp": {"rows": [(20, 13.9), (30, 11.8), (40, 9.8), (50, 7.8), (60, 5.7), (70, 3.7),
                                (80, 1.7)],
                       "source": "2.2 Control, W2 SP BB%, used as published (no sign flip)"},
    "fb__velo_sp": {"rows": [(30, 86.0), (35, 87.0), (40, 88.0), (45, 89.0), (50, 90.5), (55, 92.0),
                             (60, 93.0), (65, 94.0), (70, 95.0), (75, 96.0), (80, 97.0)],
                    "source": "2.1 S3 (2014) Fastball Velo, read for starters"},
}
T_BESIDE = {
    "hit__avg": {"rows": [(20, .199), (30, .221), (40, .244), (50, .267), (60, .290), (70, .313),
                          (80, .336)], "source": "W2 BA column (2.2 Hit tool)"},
    "fb__velo_sp": {"rows": [(20, 84.0), (30, 86.0), (40, 88.0), (50, 91.0), (60, 93.0), (70, 95.0),
                             (80, 97.0)], "source": "W2 SP Velo column"},
}
T_SECONDARY_INCUMBENT = {
    "cmd__bb_pct_rp": {"rows": [(20, 16.3), (30, 13.9), (40, 11.6), (50, 9.2), (60, 6.8), (70, 4.4),
                                (80, 2.0)], "source": "W2 RP BB% column"},
    "fb__velo_rp": {"rows": [(20, 84.0), (30, 86.0), (40, 89.0), (50, 92.0), (60, 95.0), (70, 97.0),
                             (80, 100.0)], "source": "W2 RP Velo column"},
}
#: Primary cells (T.4): tool, stat key, side, the MAE weight and the TIP orientation.
T_PRIMARY = [
    {"cell": "game_pwr__hr_per600", "tool": "game_pwr", "stat": "hr_per600", "side": "hit", "w": "pa", "sign": 1},
    {"cell": "game_pwr__iso", "tool": "game_pwr", "stat": "iso", "side": "hit", "w": "pa", "sign": 1},
    {"cell": "hit__avg", "tool": "hit", "stat": "avg", "side": "hit", "w": "pa", "sign": 1},
    {"cell": "hit__k_pct", "tool": "hit", "stat": "k_pct", "side": "hit", "w": "pa", "sign": -1},
    {"cell": "speed__sb_per600", "tool": "speed", "stat": "sb_per600", "side": "hit", "w": "pa", "sign": 1},
    {"cell": "cmd__bb_pct_sp", "tool": "cmd", "stat": "bb_pct", "side": "sp", "w": "bf", "sign": -1},
    {"cell": "fb__velo_sp", "tool": "fb", "stat": "velo", "side": "sp", "w": "bf", "sign": 1},
]
T_SECONDARY = [
    {"cell": "raw_pwr__ev_avg", "tool": "raw_pwr", "stat": "ev_avg", "side": "hit", "w": "attempts", "sign": 1},
    {"cell": "speed__sprint", "tool": "speed", "stat": "sprint", "side": "hit", "w": "competitive_runs", "sign": 1},
    {"cell": "field__oaa_per1000", "tool": "field", "stat": "oaa_per1000", "side": "hit", "w": "innings", "sign": 1},
    {"cell": "cmd__bb_pct_rp", "tool": "cmd", "stat": "bb_pct", "side": "rp", "w": "bf", "sign": -1},
    {"cell": "fb__velo_rp", "tool": "fb", "stat": "velo", "side": "rp", "w": "bf", "sign": 1},
]
T_TOOLS = ("game_pwr", "hit", "speed", "cmd", "fb", "raw_pwr", "field")


class GuardError(RuntimeError):
    """A gate Part 5 or Part 6 guard failed before any score."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _f(v):
    try:
        if v is None or v == "" or v == "NA":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _r4(v):
    return None if v is None else round(float(v), 4)


def _r6(v):
    return None if v is None else round(float(v), 6)


def round_half(v):
    return None if v is None else round(float(v) * 2) / 2.0


def sha256_of(path: Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rel(p) -> str:
    """A path printed relative to the module root when it sits under it."""
    p = Path(p)
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def holm(pvals: dict, alpha: float = HOLM_ALPHA) -> dict:
    """Holm step-down over the computable members: {key: {p, step, rejected}}."""
    items = [(k, p) for k, p in pvals.items() if p is not None]
    m = len(items)
    out = {k: {"p": p, "step": None, "rejected": False, "m": m} for k, p in pvals.items()}
    stop = False
    for i, (k, p) in enumerate(sorted(items, key=lambda kv: kv[1])):
        thr = alpha / (m - i)
        out[k]["step"] = i + 1
        out[k]["threshold"] = _r6(thr)
        if stop or p > thr:
            stop = True
            out[k]["rejected"] = False
        else:
            out[k]["rejected"] = True
    return out


def interp_table(rows, g) -> float | None:
    """T.1 reading rule: linear between published grades, flat beyond them."""
    g = _f(g)
    if g is None or not rows:
        return None
    g = min(80.0, max(20.0, g))
    rows = sorted(rows)
    if g <= rows[0][0]:
        return float(rows[0][1])
    if g >= rows[-1][0]:
        return float(rows[-1][1])
    for i in range(1, len(rows)):
        if g <= rows[i][0]:
            (g0, v0), (g1, v1) = rows[i - 1], rows[i]
            t = (g - g0) / (g1 - g0)
            return float(v0 + t * (v1 - v0))
    return float(rows[-1][1])


# ---------------------------------------------------------------------------
# numpy estimators (the pure-Python forms of source_backtest define the numbers;
# the array forms reproduce them and run the resampling loops)
# ---------------------------------------------------------------------------
def _np():
    import numpy as np
    return np


def np_rank(a):
    return BA2._np_rank(a)


def np_spearman(x, y):
    return BA2._np_spearman(x, y)


def np_auc(scores, labels):
    return BA2._np_auc(scores, labels)


def within_year_rho(score, y, years, min_rows: int = THIN_CELL):
    """The n-weighted mean of per-board-year Spearman; years under `min_rows`
    leave the mean (gate P.4, Part 3.5). (value, rows_used, per_year)."""
    np = _np()
    tot = wsum = 0.0
    per = {}
    for Y in sorted(set(years.tolist())):
        m = years == Y
        n = int(m.sum())
        if n < min_rows:
            per[int(Y)] = {"n": n, "rho": None, "skipped": "under 20 rows"}
            continue
        r = np_spearman(score[m], y[m])
        if r is None:
            per[int(Y)] = {"n": n, "rho": None, "skipped": "degenerate"}
            continue
        per[int(Y)] = {"n": n, "rho": _r4(r)}
        tot += n * r
        wsum += n
    return (tot / wsum if wsum else None), int(wsum), per


def within_year_auc(score, labels, years, min_rows: int = THIN_CELL):
    np = _np()
    tot = wsum = 0.0
    for Y in sorted(set(years.tolist())):
        m = years == Y
        n = int(m.sum())
        if n < min_rows:
            continue
        a = np_auc(score[m], labels[m])
        if a is None:
            continue
        tot += n * a
        wsum += n
    return (tot / wsum if wsum else None)


def top_tercile_labels(y, years):
    """Top ISO tercile within board year (gate P.6 clause 3)."""
    np = _np()
    lab = np.zeros(len(y), dtype=bool)
    for Y in set(years.tolist()):
        m = years == Y
        if m.sum() < 3:
            continue
        cut = np.quantile(y[m], 2.0 / 3.0)
        lab[m] = y[m] >= cut
    return lab


# ---------------------------------------------------------------------------
# guards (gate Part 5, Part 6)
# ---------------------------------------------------------------------------
def gate_sha_ok(sha: str | None, doc: str = GATE_DOC, status_part: str | None = None) -> bool:
    """True only when `sha` is a committed ancestor of HEAD whose tree carries the
    gate with its status line reading REGISTERED (and, for Part T, the Part T
    status line)."""
    if not isinstance(sha, str) or not re.match(r"^[0-9a-f]{7,40}$", sha):
        return False
    if _git("cat-file", "-e", f"{sha}^{{commit}}") is None:
        return False
    text = _git("show", f"{sha}:./{doc}")
    if text is None:
        return False
    if not gate_doc_registered(text):
        return False
    if status_part and f"{status_part} status: REGISTERED" not in text:
        return False
    return _git("merge-base", "--is-ancestor", sha, "HEAD") is not None


def rlv_record_exists(sha: str | None) -> bool:
    """The R-LV record (gate Part 0.3): an entry under EFV_V2_GATE.md '## 9. Results'
    at `sha`, or EFV_V3_BACKTEST.md '### 5.1 R-LV' at `sha` (the reading of 0.3,
    owner question TL2-Q1)."""
    if not isinstance(sha, str) or not re.match(r"^[0-9a-f]{7,40}$", sha):
        return False
    gate = _git("show", f"{sha}:./{RLV_GATE_DOC}") or ""
    m = re.search(r"^## 9\. Results\s*$(.*?)(?=^## |\Z)", gate, re.S | re.M)
    if m:
        body = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()
                and not ln.strip().startswith("(Empty") and ln.strip() != "---"]
        if body:
            return True
    back = _git("show", f"{sha}:./{RLV_BACKTEST_DOC}") or ""
    return bool(re.search(r"^### 5\.1 R-LV", back, re.M))


def guard_board_years(years, rlv_record: str | None) -> None:
    bad = sorted({int(y) for y in years if int(y) in RESERVED_LV})
    if bad and not rlv_record_exists(rlv_record):
        raise GuardError(
            f"board years {bad} are reserved (R-LV, efv_vintage_frame.RESERVED_LV) and "
            "--rlv-record does not name a commit carrying the R-LV record")


def guard_debut_years(years) -> None:
    bad = sorted({int(y) for y in years if y is not None and int(y) >= R_VM_FIRST_DEBUT_YEAR})
    if bad:
        raise GuardError(
            f"debut years {bad} are reserved (R-VM, from {R_VM_FIRST_DEBUT_YEAR}); never read")


def guard_fit_seasons(seasons, allowed) -> None:
    bad = sorted({int(s) for s in seasons if int(s) not in set(allowed)})
    if bad:
        raise GuardError(f"seasons {bad} may not enter a FIT row (allowed {sorted(allowed)})")


def look_spent(look: str) -> str | None:
    """A reason when the look has run: a look record in its artifact, or an entry in
    the gate's results part (Part 8 for P and W, T.12 for T)."""
    art = ARTIFACT[look]
    if art.exists():
        try:
            doc = json.loads(art.read_text(encoding="utf-8"))
        except ValueError:
            doc = {"unparseable": True}
        if doc.get("look") == look or doc.get("spent") or doc.get("unparseable"):
            return f"{_rel(art)} carries a look record"
    text = (ROOT / GATE_DOC).read_text(encoding="utf-8", errors="replace")
    if look in ("P", "W"):
        m = re.search(r"^## Part 8\. Results\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
        body = m.group(1) if m else ""
        if re.search(rf"^#+ .*\bLook {look}\b", body, re.M):
            return f"the gate's Part 8 carries a Look {look} entry"
    else:
        m = re.search(r"^### T\.12 Results\s*$(.*?)(?=^## |^### |\Z)", text, re.S | re.M)
        body = m.group(1) if m else ""
        if body.strip() and "EMPTY AT REGISTRATION" not in body:
            return "the gate's T.12 carries a look record"
    return None


def guard_no_grade_grouping(keys) -> None:
    """No stratum, key or label names a future-value grade cell (Part 6)."""
    bad = [k for k in keys if re.search(r"(^|_)fv($|_)", str(k))]
    if bad:
        raise GuardError(f"grouping keys {bad} name a future-value grade cell")


# ---------------------------------------------------------------------------
# loaders (real path; never called by --dry-run)
# ---------------------------------------------------------------------------
def load_debuts() -> list[dict]:
    return json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))


def is_pitcher_position(pos) -> bool:
    return (pos or "") in PITCHER_POS


def load_board_grades(tools=None) -> dict:
    """(Y, source) -> player_key -> {tool: grade}: each source's EARLIEST snapshot
    dated in [Y-01-01, Y-05-01), grades parsed into [20, 80], `_extras` stripped
    (gate Part 3.2)."""
    import storage
    grades: dict = defaultdict(lambda: defaultdict(dict))
    picked: dict = {}
    with storage.connect() as con:
        rows = list(con.execute(
            "SELECT source, snapshot_date, player_key, tools_json FROM snapshots "
            "WHERE tools_json IS NOT NULL AND tools_json != '' ORDER BY snapshot_date"))
    for r in rows:
        d = r["snapshot_date"]
        try:
            td = json.loads(r["tools_json"])
        except ValueError:
            continue
        if not isinstance(td, dict):
            continue
        year = int(d[:4])
        if not (f"{year}{WIN_START}" <= d < f"{year}{WIN_END}"):
            continue
        for tool, g in td.items():
            if tool == "_extras" or (tools and tool not in tools):
                continue
            g = _f(g)
            if g is None or not (20.0 <= g <= 80.0):
                continue
            key = (r["source"], year, tool, r["player_key"])
            if key in picked and picked[key] <= d:
                continue
            picked[key] = d
            grades[(year, r["source"])][r["player_key"]][tool] = g
    return grades


def consensus_tool_grade(per_source: dict, tool: str) -> float | None:
    """consensus.py's per-tool rule: the unweighted mean across the outlets
    publishing the key, rounded to 0.5."""
    vals = [g[tool] for g in per_source.values() if tool in g]
    if not vals:
        return None
    return round_half(sum(vals) / len(vals))


def load_statsapi(group: str, years) -> dict:
    """{pid: {season: counts}} from .cache/fa_statsapi_<group>_Y.json for `years`
    only (the caller controls which seasons may be read)."""
    out: dict = defaultdict(dict)
    for y in years:
        p = CACHE / f"fa_statsapi_{group}_{y}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for blk in d.get("stats") or []:
            for sp in blk.get("splits") or []:
                pid = (sp.get("player") or {}).get("id")
                st = sp.get("stat") or {}
                if pid is None:
                    continue
                if group == "hitting":
                    pa = _f(st.get("plateAppearances"))
                    if not pa:
                        continue
                    row = {"pa": pa, "ab": _f(st.get("atBats")) or 0.0,
                           "h": _f(st.get("hits")) or 0.0, "hr": _f(st.get("homeRuns")) or 0.0,
                           "tb": _f(st.get("totalBases")) or 0.0, "so": _f(st.get("strikeOuts")) or 0.0,
                           "bb": _f(st.get("baseOnBalls")) or 0.0, "sb": _f(st.get("stolenBases")) or 0.0,
                           "sf": _f(st.get("sacFlies")) or 0.0}
                else:
                    bf = _f(st.get("battersFaced"))
                    if not bf:
                        continue
                    row = {"bf": bf, "so": _f(st.get("strikeOuts")) or 0.0,
                           "bb": _f(st.get("baseOnBalls")) or 0.0,
                           "g": _f(st.get("gamesPlayed")) or 0.0, "gs": _f(st.get("gamesStarted")) or 0.0}
                out[int(pid)][int(y)] = row
    return out


def _csv_rows(path: Path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_statcast_batter(years) -> dict:
    out: dict = defaultdict(dict)
    for y in years:
        for r in _csv_rows(CACHE / "savant_mlb" / f"statcast_batter_{y}.csv"):
            pid = _f(r.get("player_id"))
            if pid is None:
                continue
            out[int(pid)][int(y)] = {"attempts": _f(r.get("attempts")) or 0.0,
                                     "ev": _f(r.get("avg_hit_speed")),
                                     "barrels": _f(r.get("barrels")) or 0.0,
                                     "brl_pa": _f(r.get("brl_pa"))}
    return out


def load_sprint(years) -> dict:
    out: dict = defaultdict(dict)
    for y in years:
        for r in _csv_rows(CACHE / "savant_sprint" / f"sprint_{y}.csv"):
            pid = _f(r.get("player_id"))
            ss = _f(r.get("sprint_speed"))
            if pid is None or ss is None:
                continue
            out[int(pid)][int(y)] = {"sprint": ss, "runs": _f(r.get("competitive_runs")) or 0.0}
    return out


def load_arm(years) -> dict:
    """{season: {pid: {group, arm, throws, pos}}} plus the (season, group) z tables."""
    out: dict = {}
    for y in years:
        rows = {}
        for r in _csv_rows(CACHE / "savant_arm" / f"arm_{y}.csv"):
            pid = _f(r.get("player_id"))
            if pid is None:
                continue
            pos = (r.get("primary_position") or "").strip()
            if pos in ("2", "3"):
                continue                                # catchers and first basemen out (W.3)
            t_inf, t_of = _f(r.get("total_throws_inf")) or 0.0, _f(r.get("total_throws_of")) or 0.0
            if t_inf >= t_of and t_inf > 0:
                grp, arm, thr = "inf", _f(r.get("arm_inf")), t_inf
            elif t_of > 0:
                grp, arm, thr = "of", _f(r.get("arm_of")), t_of
            else:
                continue
            if arm is None:
                continue
            rows[int(pid)] = {"group": grp, "arm": arm, "throws": thr, "pos": pos}
        if rows:
            out[int(y)] = rows
    z = {}
    for y, rows in out.items():
        for grp in ("inf", "of"):
            vals = [r["arm"] for r in rows.values() if r["group"] == grp]
            if len(vals) >= 2:
                mu = sum(vals) / len(vals)
                sd = (sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
                z[(y, grp)] = (mu, sd if sd > 0 else None)
    for y, rows in out.items():
        for r in rows.values():
            mu, sd = z.get((y, r["group"]), (None, None))
            r["z"] = None if (mu is None or sd is None) else (r["arm"] - mu) / sd
    return out


def load_oaa(years) -> dict:
    """{pid: {season: oaa summed over positions 3 to 9}} from oaa_Y_posN.csv, never pos2."""
    out: dict = defaultdict(dict)
    for y in years:
        for pos in OAA_POS:
            for r in _csv_rows(CACHE / "savant_oaa" / f"oaa_{y}_pos{pos}.csv"):
                pid = _f(r.get("player_id"))
                o = _f(r.get("outs_above_average"))
                if pid is None or o is None:
                    continue
                out[int(pid)][int(y)] = out[int(pid)].get(int(y), 0.0) + o
    return out


def load_fielding_innings() -> dict:
    d = json.loads((DATA / "fielding_innings.json").read_text(encoding="utf-8"))
    out: dict = defaultdict(dict)
    for season, byp in (d.get("seasons") or {}).items():
        for pid, byq in byp.items():
            inn = sum((_f((v or {}).get("inn")) or 0.0) for k, v in byq.items()
                      if k in OAA_POS_NAMES.values())
            out[int(pid)][int(season)] = inn
    return out


def load_velo(years) -> dict:
    out: dict = {}
    for y in years:
        p = CACHE / f"velo_arsenal_{y}.json"
        if p.exists():
            out[int(y)] = {int(k): float(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    return out


def load_leaderboard_discipline() -> dict:
    """pitch_sel and bat_ctrl outcomes: chase% and zone-contact% per player from
    data/hitter_leaderboards.json (one leaderboard season, descriptive only)."""
    p = DATA / "hitter_leaderboards.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for r in d.get("hitters") or []:
        pid = r.get("mlbam")
        if pid is None:
            continue
        out[int(pid)] = {"chase_pct": _f(r.get("chase_pct")), "z_contact_pct": _f(r.get("z_contact_pct")),
                         "pa": _f(r.get("pa")) or 0.0, "season": d.get("season")}
    return out


# ---------------------------------------------------------------------------
# outcome window (gate Part 3.3, W.3)
# ---------------------------------------------------------------------------
def window_seasons(seasons_present, board_year: int, last: int = LAST_OUTCOME_SEASON) -> list[int]:
    """The first three MLB seasons strictly after Y and no later than `last` in
    which the player appears at the stat's source."""
    return sorted(s for s in seasons_present if board_year < s <= last)[:3]


def pooled_hitting(lines: dict, seasons) -> dict | None:
    tot = defaultdict(float)
    for s in seasons:
        for k, v in (lines.get(s) or {}).items():
            tot[k] += v
    if not tot.get("pa"):
        return None
    pa, ab = tot["pa"], tot["ab"]
    return {"pa": pa, "ab": ab,
            "k_pct": 100.0 * tot["so"] / pa,
            "iso": ((tot["tb"] - tot["h"]) / ab) if ab else None,
            "avg": (tot["h"] / ab) if ab else None,
            "hr_pa": tot["hr"] / pa, "hr_per600": 600.0 * tot["hr"] / pa,
            "sb_per600": 600.0 * tot["sb"] / pa}


def pooled_pitching(lines: dict, seasons) -> dict | None:
    tot = defaultdict(float)
    for s in seasons:
        for k, v in (lines.get(s) or {}).items():
            tot[k] += v
    if not tot.get("bf"):
        return None
    return {"bf": tot["bf"], "k_pct_pit": 100.0 * tot["so"] / tot["bf"],
            "bb_pct_pit": 100.0 * tot["bb"] / tot["bf"]}


def outcome_hitter(pid: int, Y: int, hit: dict, sc: dict | None = None) -> dict | None:
    lines = hit.get(pid) or {}
    seasons = window_seasons(lines.keys(), Y)
    pooled = pooled_hitting(lines, seasons)
    if pooled is None or pooled["pa"] < PA_FLOOR:
        return None
    pooled["seasons"] = seasons
    if sc is not None:
        rows = [sc.get(pid, {}).get(s) for s in seasons]
        rows = [r for r in rows if r and r.get("attempts")]
        att = sum(r["attempts"] for r in rows)
        pooled["attempts"] = att
        pooled["ev_avg"] = (sum(r["ev"] * r["attempts"] for r in rows if r["ev"] is not None) / att) if att else None
        pooled["brl_pa"] = (sum(r["barrels"] for r in rows) / pooled["pa"]) if rows else None
    return pooled


def outcome_sprint(pid: int, Y: int, sprint: dict) -> dict | None:
    lines = sprint.get(pid) or {}
    seasons = window_seasons(lines.keys(), Y)
    rows = [lines[s] for s in seasons]
    w = sum(r["runs"] for r in rows)
    if not rows or not w:
        return None
    return {"sprint": sum(r["sprint"] * r["runs"] for r in rows) / w, "competitive_runs": w,
            "seasons": seasons}


def outcome_oaa(pid: int, Y: int, oaa: dict, finn: dict) -> dict | None:
    o, inn = oaa.get(pid) or {}, finn.get(pid) or {}
    present = [s for s in inn if inn[s] > 0 and s in o]
    seasons = window_seasons(present, Y)
    tot_inn = sum(inn[s] for s in seasons)
    if not seasons or tot_inn < INN_FLOOR:
        return None
    return {"oaa_per1000": 1000.0 * sum(o[s] for s in seasons) / tot_inn, "innings": tot_inn,
            "seasons": seasons}


def outcome_arm(pid: int, Y: int, arm: dict) -> dict | None:
    present = [s for s, rows in arm.items() if pid in rows and rows[pid].get("z") is not None]
    seasons = window_seasons(present, Y)
    rows = [arm[s][pid] for s in seasons]
    if not rows:
        return None
    by_grp = defaultdict(float)
    for r in rows:
        by_grp[r["group"]] += r["throws"]
    grp = max(by_grp, key=by_grp.get)
    rows = [r for r in rows if r["group"] == grp]
    w = sum(r["throws"] for r in rows)
    if not w:
        return None
    return {"arm_z": sum(r["z"] * r["throws"] for r in rows) / w, "throws": w, "group": grp,
            "seasons": seasons}


def outcome_pitcher(pid: int, Y: int, pit: dict) -> dict | None:
    lines = pit.get(pid) or {}
    seasons = window_seasons(lines.keys(), Y)
    pooled = pooled_pitching(lines, seasons)
    if pooled is None or pooled["bf"] < BF_FLOOR:
        return None
    pooled["seasons"] = seasons
    return pooled


# ---------------------------------------------------------------------------
# the universe (gate Part 3): one row per (board year, player) with identity
# ---------------------------------------------------------------------------
class Universe:
    """Debuted players with pre-debut board-year grades, outcome-blind identity
    (efv_identity, mlbam ids only), debut year at most MAX_DEBUT_YEAR."""

    def __init__(self, years, rlv_record: str | None = None, *, grades=None, debuts=None,
                 index=None):
        self.years = tuple(int(y) for y in years)
        guard_board_years(self.years, rlv_record)
        self.grades = grades if grades is not None else load_board_grades()
        self.debuts = debuts if debuts is not None else load_debuts()
        self.index = index if index is not None else efv_identity.build_index(max(self.years) - 1)
        self.counts = defaultdict(int)
        self.rows: dict = {}                   # (Y, pid) -> row
        self.by_key = {r.get("player_key"): r for r in self.debuts}
        self._build()

    def _build(self):
        sources_at = defaultdict(dict)         # Y -> player_key -> {source: {tool: g}}
        for (Y, src), players in self.grades.items():
            if Y not in self.years:
                continue
            for pk, g in players.items():
                sources_at[Y].setdefault(pk, {})[src] = g
        for Y in self.years:
            for pk, per_source in sources_at.get(Y, {}).items():
                rec = self.by_key.get(pk)
                if rec is None:
                    self.counts["no_debut_record"] += 1
                    continue
                dd = rec.get("debut_date") or ""
                if rec.get("debut_date_is_placeholder") or len(dd) < 4:
                    self.counts["placeholder_debut"] += 1
                    continue
                dy = int(dd[:4])
                if dd < f"{Y}-01-01":
                    self.counts["debuted_before_board_year"] += 1
                    continue
                if dy > MAX_DEBUT_YEAR:
                    self.counts["debut_after_frame"] += 1
                    continue
                side = "pit" if is_pitcher_position(rec.get("position")) else "hit"
                res = efv_identity.resolve_record(rec, Y, self.index, side)
                mid = rec.get("mlbam_id")
                if res.person_id is None:
                    self.counts[f"identity_{res.how}"] += 1
                    continue
                if mid is None or int(res.person_id) != int(mid):
                    self.counts["identity_disagrees_with_record"] += 1
                    continue
                self.rows[(Y, int(mid))] = {"year": Y, "pid": int(mid), "player_key": pk,
                                            "side": side, "debut_year": dy,
                                            "per_source": per_source,
                                            "consensus": {t: consensus_tool_grade(per_source, t)
                                                          for t in {k for g in per_source.values() for k in g}}}
        guard_debut_years([r["debut_year"] for r in self.rows.values()])
        self.counts["rows"] = len(self.rows)


# ---------------------------------------------------------------------------
# LOOK P: the power composite (gate Part P)
# ---------------------------------------------------------------------------
def p_frame_rows(universe: Universe, hit: dict, sc: dict) -> list[dict]:
    rows = []
    for (Y, pid), r in universe.rows.items():
        if r["side"] != "hit" or Y not in P_YEARS:
            continue
        g, raw = r["consensus"].get("game_pwr"), r["consensus"].get("raw_pwr")
        if g is None or raw is None:
            continue
        out = outcome_hitter(pid, Y, hit, sc)
        if out is None:
            continue
        rows.append({"pid": pid, "year": Y, "game": g, "raw": raw, "iso": out["iso"], "pa": out["pa"],
                     "hr_pa": out["hr_pa"], "brl_pa": out.get("brl_pa"), "ev_avg": out.get("ev_avg")})
    return rows


def p_fit_a(game, raw, y, mask):
    """The grid a maximizing the pooled Spearman of round-half(a game + (1 - a) raw)
    with the outcome over `mask`; ties resolve to the a nearer 0.5."""
    np = _np()
    best, best_r = None, None
    if mask.sum() < 4:
        return 0.5
    g, r, yy = game[mask], raw[mask], y[mask]
    for a in P_A_GRID:
        s = np.round((a * g + (1 - a) * r) * 2) / 2.0
        rho = np_spearman(s, yy)
        if rho is None:
            continue
        if best_r is None or rho > best_r + 1e-12 or (abs(rho - best_r) <= 1e-12
                                                     and abs(a - 0.5) < abs(best - 0.5)):
            best, best_r = a, rho
    return 0.5 if best is None else best


def p_pipeline(game, raw, y, years, pids, *, outcome_key="iso"):
    """Candidates C0, C1, C2 (C2 cross-fit by leave-one-board-year-out,
    player-disjoint), the within-year Spearman and AUC of each, and d against C0."""
    np = _np()
    c0 = np.round(((game + raw) / 2.0) * 2) / 2.0
    c1 = game.copy()
    c2 = np.empty_like(game)
    a_by_year = {}
    for Y in sorted(set(years.tolist())):
        m = years == Y
        p_in = set(pids[m].tolist())
        fit = (~m) & np.array([p not in p_in for p in pids.tolist()])
        a = p_fit_a(game, raw, y, fit)
        a_by_year[int(Y)] = a
        c2[m] = np.round((a * game[m] + (1 - a) * raw[m]) * 2) / 2.0
    served_a = p_fit_a(game, raw, y, np.ones(len(y), dtype=bool))
    labels = top_tercile_labels(y, years)
    out = {"a_by_year": a_by_year, "served_a": served_a, "candidates": {}}
    rho0, n_used, per0 = within_year_rho(c0, y, years)
    auc0 = within_year_auc(c0, labels, years)
    out["candidates"]["C0"] = {"rho": rho0, "auc": auc0, "per_year": per0}
    out["rows_used"] = n_used
    for name, s in (("C1", c1), ("C2", c2)):
        rho, _n, per = within_year_rho(s, y, years)
        auc = within_year_auc(s, labels, years)
        out["candidates"][name] = {
            "rho": rho, "auc": auc, "per_year": per,
            "d": None if (rho is None or rho0 is None) else rho - rho0,
            "d_auc": None if (auc is None or auc0 is None) else auc - auc0}
    out["scores"] = {"C0": c0, "C1": c1, "C2": c2}
    out["labels"] = labels
    out["outcome_key"] = outcome_key
    return out


def p_bootstrap(pipe, y, years, pids, draws: int, seed: int) -> dict:
    """Paired, player-clustered bootstrap of d for C1 and C2 (candidate scores
    fixed; B draws; one-sided 95% lower bound)."""
    np = _np()
    order, starts, lens = _cluster_layout(np, pids)
    rng = np.random.default_rng(seed)
    labels = pipe["labels"]
    sc = pipe["scores"]
    dr = {"C1": [], "C2": []}
    da = {"C1": [], "C2": []}
    for _ in range(draws):
        idx = _cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        yy, yr = y[idx], years[idx]
        r0, _n, _p = within_year_rho(sc["C0"][idx], yy, yr)
        a0 = within_year_auc(sc["C0"][idx], labels[idx], yr)
        for name in ("C1", "C2"):
            r, _n, _p = within_year_rho(sc[name][idx], yy, yr)
            a = within_year_auc(sc[name][idx], labels[idx], yr)
            if r is not None and r0 is not None:
                dr[name].append(r - r0)
            if a is not None and a0 is not None:
                da[name].append(a - a0)
    out = {"draws": draws, "seed": seed}
    for name in ("C1", "C2"):
        v = sorted(dr[name])
        w = sorted(da[name])
        out[name] = {"n_draws": len(v),
                     "d_lo95": _r6(v[int(0.05 * len(v))]) if v else None,
                     "d_sd": _r6(float(np.std(v, ddof=1))) if len(v) > 2 else None,
                     "d_auc_lo95": _r6(w[int(0.05 * len(w))]) if w else None}
    return out


def p_floor(game, raw, y, years, pids, draws: int, seed: int, obs: dict) -> dict:
    """P.5: swap game and raw with probability 0.5 per row, rerun the whole
    pipeline (C2's cross-fit included); F = p95 of |d|, the AUC floor, and the
    add-one corrected permutation p of each candidate."""
    np = _np()
    rng = np.random.default_rng(seed)
    dd = {"C1": [], "C2": []}
    aa = {"C1": [], "C2": []}
    for _ in range(draws):
        swap = rng.random(len(game)) < 0.5
        g = np.where(swap, raw, game)
        r = np.where(swap, game, raw)
        pipe = p_pipeline(g, r, y, years, pids)
        for name in ("C1", "C2"):
            c = pipe["candidates"][name]
            if c["d"] is not None:
                dd[name].append(c["d"])
            if c["d_auc"] is not None:
                aa[name].append(c["d_auc"])
    out = {"draws": draws, "seed": seed}
    for name in ("C1", "C2"):
        absd = sorted(abs(v) for v in dd[name])
        absa = sorted(abs(v) for v in aa[name])
        od = obs.get(name, {}).get("d")
        out[name] = {
            "n_draws": len(absd),
            "F": _r6(absd[int(0.95 * (len(absd) - 1))]) if absd else None,
            "F_auc": _r6(absa[int(0.95 * (len(absa) - 1))]) if absa else None,
            "p_perm": (_r6((1 + sum(1 for v in dd[name] if v >= od)) / (len(dd[name]) + 1))
                       if (od is not None and dd[name]) else None)}
    return out


def p_verdict(cands: dict, boot: dict, floor: dict) -> dict:
    """P.6 per candidate, P.7 serve rule."""
    pv = {n: floor[n]["p_perm"] for n in ("C1", "C2")}
    hz = holm(pv)
    out = {}
    for name in ("C1", "C2"):
        c, b, f = cands[name], boot[name], floor[name]
        d, lo, F = c["d"], b["d_lo95"], f["F"]
        c1 = bool(lo is not None and lo > 0)
        c2 = bool(d is not None and F is not None and d >= 2 * F)
        veto = bool(c["d_auc"] is not None and f["F_auc"] is not None and c["d_auc"] < -f["F_auc"])
        c4 = bool(hz[name]["rejected"])
        out[name] = {"d": _r6(d), "lo95": lo, "F": F,
                     "ratio_to_floor": _r4(None if (d is None or not F) else d / F),
                     "d_auc": _r6(c["d_auc"]), "F_auc": f["F_auc"], "auc_veto": veto,
                     "p_perm": f["p_perm"], "holm_step": hz[name]["step"],
                     "holm_threshold": hz[name].get("threshold"), "holm_rejected": c4,
                     "clauses": {"1_lo95_above_0": c1, "2_d_at_least_2F": c2,
                                 "3_not_vetoed": not veto, "4_holm": c4},
                     "pass": bool(c1 and c2 and (not veto) and c4)}
    serve = "C2" if out["C2"]["pass"] else "C1" if out["C1"]["pass"] else "C0"
    out["serve"] = serve
    return out


def run_look_p(rows: list[dict], *, boot: int = P_BOOT, perm: int = P_PERM, seed: int = P_SEED,
               secondary: bool = True) -> dict:
    """The whole Part P pipeline on frame rows (pure; the caller loaded them)."""
    np = _np()
    rows = [r for r in rows if r.get("game") is not None and r.get("raw") is not None
            and r.get("iso") is not None]
    if not rows:
        return {"n": 0, "note": "no rows"}
    game = np.array([r["game"] for r in rows], float)
    raw = np.array([r["raw"] for r in rows], float)
    y = np.array([r["iso"] for r in rows], float)
    years = np.array([r["year"] for r in rows], int)
    pids = np.array([r["pid"] for r in rows], int)
    pipe = p_pipeline(game, raw, y, years, pids)
    bt = p_bootstrap(pipe, y, years, pids, boot, seed)
    fl = p_floor(game, raw, y, years, pids, perm, seed, pipe["candidates"])
    verdict = p_verdict(pipe["candidates"], bt, fl)
    out = {"n": len(rows), "rows_by_year": {str(k): int(v) for k, v in
                                           zip(*np.unique(years, return_counts=True))},
           "rows_used_in_rho": pipe["rows_used"],
           "a_by_year": pipe["a_by_year"], "served_a": pipe["served_a"],
           "served_as": "C1" if pipe["served_a"] == 1.0 else "C2",
           "candidates": {k: {kk: (_r6(vv) if isinstance(vv, float) else vv)
                              for kk, vv in v.items() if kk != "per_year"}
                          for k, v in pipe["candidates"].items()},
           "per_year": {k: v["per_year"] for k, v in pipe["candidates"].items()},
           "bootstrap": bt, "floor": fl, "verdict": verdict,
           "survivorship": SURVIVORSHIP}
    if secondary:
        out["secondary"] = {}
        for key in ("hr_pa", "brl_pa", "ev_avg"):
            sub = [r for r in rows if r.get(key) is not None]
            if len(sub) < 8:
                out["secondary"][key] = {"n": len(sub), "note": "too few rows", "verdict": "secondary: no verdict"}
                continue
            g2 = np.array([r["game"] for r in sub], float)
            r2 = np.array([r["raw"] for r in sub], float)
            y2 = np.array([r[key] for r in sub], float)
            yr2 = np.array([r["year"] for r in sub], int)
            pd2 = np.array([r["pid"] for r in sub], int)
            pp = p_pipeline(g2, r2, y2, yr2, pd2, outcome_key=key)
            b2 = p_bootstrap(pp, y2, yr2, pd2, boot, seed)
            f2 = p_floor(g2, r2, y2, yr2, pd2, perm, seed, pp["candidates"])
            out["secondary"][key] = {
                "n": len(sub), "verdict": "secondary: no verdict",
                "candidates": {k: {"rho": _r6(v["rho"]), "d": _r6(v.get("d"))}
                               for k, v in pp["candidates"].items()},
                "bootstrap": {k: b2[k] for k in ("C1", "C2")},
                "floor": {k: f2[k] for k in ("C1", "C2")}}
    return out


# ---------------------------------------------------------------------------
# LOOK W: source weights and TAG (gate Part W)
# ---------------------------------------------------------------------------
def w_outcome(stat: str, pid: int, Y: int, data: dict):
    """(value, exposure) of the W.2/W.4/W.5 outcome for a player at board year Y."""
    if stat in ("k_pct", "iso", "avg", "sb_per600", "hr_pa"):
        o = outcome_hitter(pid, Y, data["hit"], data.get("sc"))
        if o is None or o.get(stat) is None:
            return None
        return o[stat], (o["ab"] if stat in ("iso", "avg") else o["pa"])
    if stat == "ev_avg":
        o = outcome_hitter(pid, Y, data["hit"], data.get("sc"))
        if o is None or o.get("ev_avg") is None:
            return None
        return o["ev_avg"], o.get("attempts") or 0.0
    if stat == "sprint":
        o = outcome_sprint(pid, Y, data["sprint"])
        return None if o is None else (o["sprint"], o["competitive_runs"])
    if stat == "oaa_per1000":
        o = outcome_oaa(pid, Y, data["oaa"], data["finn"])
        return None if o is None else (o["oaa_per1000"], o["innings"])
    if stat == "arm_z":
        o = outcome_arm(pid, Y, data["arm"])
        return None if o is None else (o["arm_z"], o["throws"])
    if stat in ("k_pct_pit", "bb_pct_pit"):
        o = outcome_pitcher(pid, Y, data["pit"])
        return None if o is None else (o[stat], o["bf"])
    if stat in ("chase_pct", "z_contact_pct"):
        o = (data.get("disc") or {}).get(pid)
        if not o or o.get(stat) is None:
            return None
        return o[stat], o.get("pa") or 0.0
    raise KeyError(stat)


def w_rows(universe: Universe, tool: str, stat: str, sign: int, sources, data: dict) -> dict:
    """BA2's by_year rows on the COMMON set of `sources` for `tool`, outcome
    oriented so that higher is better."""
    by_year: dict = {}
    side = "pit" if tool in ("fb", "cmd") else "hit"
    for (Y, pid), r in universe.rows.items():
        if r["side"] != side:
            continue
        gd = {s: r["per_source"][s][tool] for s in sources
              if s in r["per_source"] and tool in r["per_source"][s]}
        if len(gd) < len(sources):
            continue
        o = w_outcome(stat, pid, Y, data)
        if o is None:
            continue
        by_year.setdefault(Y, []).append({"player": pid, "grades": gd, "y": sign * o[0],
                                          "exposure": o[1]})
    return by_year


def cluster_boot_bounds(pool, seed: int, draws: int) -> dict:
    """Both one-sided 95% bounds on d_rho and d_auc under BA2's player-clustered
    paired bootstrap (the lower bound is BA2's cluster_boot; the upper bound is the
    LOSS clause of W.6)."""
    np = _np()
    if not pool["y"]:
        return {"draws": 0}
    E, W, Y, L = BA2._np_pool(pool)
    order, starts, lens = _cluster_layout(np, np.asarray(pool["player"]))
    rng = np.random.default_rng(seed)
    dr, da = [], []
    for _ in range(draws):
        idx = _cluster_draw(np, rng, order, starts, lens)
        a, b = BA2._np_delta(E, W, Y, L, idx)
        if a is not None:
            dr.append(a)
        if b is not None:
            da.append(b)
    dr.sort(); da.sort()
    return {"draws": draws, "seed": seed,
            "d_rho_lo95": _r6(dr[int(0.05 * len(dr))]) if dr else None,
            "d_rho_hi95": _r6(dr[min(len(dr) - 1, int(0.95 * len(dr)))]) if dr else None,
            "d_auc_lo95": _r6(da[int(0.05 * len(da))]) if da else None,
            "d_auc_hi95": _r6(da[min(len(da) - 1, int(0.95 * len(da)))]) if da else None,
            "d_rho_sd": _r6(float(np.std(dr, ddof=0))) if len(dr) > 2 else None}


def w_cell(by_year: dict, sources, *, boot: int = W_BOOT, perm: int = W_PERM,
           seed: int = W_SEED, seed_alt: int = W_SEED_ALT, controls: bool = True) -> dict:
    """One (arm, tool) cell with BA2's estimator and gate, imported by name: the
    A/B (ab_pass, score), the permuted-source floor (C6.1), the bootstrap at BA2's
    seeds (C6.5), the shuffled outcome (C6.3), the forced-equal identity in its
    honest form (C6.4), the player-disjoint arm (C6.7), single-source context and
    the numpy equivalence checks; G1 to G5 as BA2 reads them (marginal is FAIL)."""
    cov = {str(y): len(r) for y, r in sorted(by_year.items())}
    cell = {"common_set_by_year": cov, "pooled_n": sum(cov.values()),
            "thin_years": [y for y, n in cov.items() if n < THIN_CELL]}
    if cell["pooled_n"] < POOL_MIN:
        cell["gate"] = {"verdict": "NOT COMPUTABLE", "reason": f"pool under {POOL_MIN} players"}
        return cell
    pool = BA2.ab_pass(by_year, sources, MIN_LAG_YEARS)
    s = BA2.score(pool)
    cell["primary"] = s
    cell["per_year"] = pool["per_year"]
    cell["evaluable_years"] = [p["year"] for p in pool["per_year"] if "skipped" not in p]
    if not s["n"]:
        cell["gate"] = {"verdict": "NULL", "reason": "no board year has both a non-flat weight "
                                                     f"vintage and resolvable outcomes at lag {MIN_LAG_YEARS}"}
        return cell
    nullc = BA2.permuted_source_null_np(by_year, sources, MIN_LAG_YEARS, seed, draws=perm,
                                        obs=(s["d_rho"], s["d_auc"]))
    bt = cluster_boot_bounds(pool, seed, boot)
    cell["C61_permuted_source_null"] = nullc
    cell["bootstrap"] = bt
    cell["C0_numpy_equivalence_check"] = BA2._np_equivalence_check(pool)
    cell["C0_array_ab_equivalence"] = BA2.np_ab_equivalence(by_year, sources, MIN_LAG_YEARS)
    if controls:
        cell["C65_seed_stability"] = {
            "boot_seed_alt": cluster_boot_bounds(pool, seed_alt, boot),
            "perm_seed_alt": BA2.permuted_source_null_np(by_year, sources, MIN_LAG_YEARS, seed_alt,
                                                         draws=max(20, perm // 5),
                                                         obs=(s["d_rho"], s["d_auc"]))}
        cell["C63_shuffled_outcome_null"] = BA2.shuffled_outcome_null_np(by_year, sources,
                                                                         MIN_LAG_YEARS, seed)
        ones = {src: 1.0 for src in sources}
        fe = BA2.score(BA2.ab_pass(by_year, sources, MIN_LAG_YEARS, weight_override=ones,
                                   allow_flat=True))
        cell["C64_forced_equal_identity"] = {"n": fe["n"], "d_rho": fe["d_rho"], "d_auc": fe["d_auc"],
                                             "passes": bool(fe["n"] > 0 and fe["d_rho"] == 0.0
                                                            and fe["d_auc"] == 0.0)}
        cell["C67_player_disjoint_weights"] = BA2.disjoint_player_pass(by_year, sources,
                                                                        MIN_LAG_YEARS, seed=seed)
        cell["context_single_source"] = BA2.single_source_context(by_year, sources, MIN_LAG_YEARS)
    f_rho, f_auc = nullc["abs_d_rho_p95"], nullc["abs_d_auc_p95"]
    dr, da = s["d_rho"], s["d_auc"]
    g1 = bool(dr is not None and f_rho is not None and dr >= f_rho)
    g2 = bool(da is not None and f_auc is not None and da >= f_auc)
    g3 = bool(bt.get("d_rho_lo95") is not None and bt["d_rho_lo95"] > 0)
    g4 = bool(bt.get("d_auc_lo95") is not None and bt["d_auc_lo95"] > 0)
    g5 = bool(dr is not None and f_rho is not None and dr >= 2 * f_rho)
    loss = bool(dr is not None and f_rho is not None and dr < -f_rho
                and bt.get("d_rho_hi95") is not None and bt["d_rho_hi95"] < 0)
    seed_moves = None
    if controls:
        alt = cell["C65_seed_stability"]["boot_seed_alt"]
        g3_alt = bool(alt.get("d_rho_lo95") is not None and alt["d_rho_lo95"] > 0)
        seed_moves = bool(g3 != g3_alt)
    cell["gate"] = {"F_rho": f_rho, "F_auc": f_auc,
                    "margin_over_F_rho": _r4(None if (dr is None or not f_rho) else dr / f_rho),
                    "G1_rho_resolvable": g1, "G2_auc_resolvable": g2, "G3_rho_lo95_pos": g3,
                    "G4_auc_lo95_pos": g4, "G5_not_knife_edge": g5,
                    "G1_to_G5": bool(g1 and g2 and g3 and g4 and g5),
                    "p_rho": nullc.get("p_rho"), "loss_clause": loss,
                    "verdict_moves_between_seeds": seed_moves,
                    "shuffled_outcome_collapsed": (None if not controls
                                                   else shuffled_collapsed(cell["C63_shuffled_outcome_null"]))}
    return cell


def shuffled_collapsed(c63: dict) -> bool:
    """W.7: the shuffled-outcome control collapses when the weighted blend's Spearman
    on the permuted outcome sits inside the chance band 2.5 / sqrt(n) of zero (or no
    year survives the flat-weight skip). A result that does not collapse voids the look."""
    n = c63.get("n") or 0
    if n == 0:
        return True
    rho = (c63.get("weighted") or {}).get("spearman")
    if rho is None:
        return True
    return bool(abs(rho) <= 2.5 / (n ** 0.5))


def w_tag_tables(universe: Universe, tool: str, stat: str, sign: int, data: dict,
                 k_m: dict | None = None) -> dict:
    """W.5: per source and board year, the TAG triple (Part 2.1) and the three source
    metrics (Part 2.2). TIP_f3 for board year Y is fit on every OTHER board year's rows
    with Y's players removed, on the consensus grade, then read at the source's grade."""
    k_m = K_M if k_m is None else k_m
    side = "pit" if tool in ("fb", "cmd") else "hit"
    frame = []
    for (Y, pid), r in universe.rows.items():
        if r["side"] != side or r["consensus"].get(tool) is None:
            continue
        o = w_outcome(stat, pid, Y, data)
        if o is None:
            continue
        frame.append({"id": (Y, pid), "pid": pid, "year": Y, "grade": r["consensus"][tool],
                      "value": o[0], "exposure": o[1], "per_source": r["per_source"]})
    years = sorted({r["year"] for r in frame})
    km = (k_m.get(stat) or {}).get("value")
    out = {"tool": tool, "stat": stat, "n_frame": len(frame), "k_m": km,
           "k_m_unit": (k_m.get(stat) or {}).get("unit"),
           "regressed": km is not None, "by_source": {}}
    tables = {}
    for Y in years:
        in_y = {r["pid"] for r in frame if r["year"] == Y}
        fit = [r for r in frame if r["year"] != Y and r["pid"] not in in_y]
        tables[Y] = TI.tip_f3(fit, tool, stat, sign=sign)
    sources = sorted({s for r in frame for s in r["per_source"] if tool in r["per_source"][s]})
    for src in sources:
        per_year = {}
        all_gap, all_reg, all_pct, all_abs = [], [], [], []
        rho_num = rho_den = 0.0
        for Y in years:
            tbl = tables[Y]
            rows = [r for r in frame if r["year"] == Y and tool in r["per_source"].get(src, {})]
            gaps, regs, pcts = [], [], []
            gs, ys = [], []
            for r in rows:
                tbl.assert_not_fit_on(r["id"])
                g = r["per_source"][src][tool]
                tip = tbl.read(g)
                if tip is None:
                    continue
                gap = sign * (r["value"] - tip)
                pct = tbl.bin_percentile(g, r["value"])
                if pct is not None and sign < 0:
                    pct = 1.0 - pct
                reg = None if km is None else gap * (r["exposure"] / (r["exposure"] + km))
                gaps.append(gap); pcts.append(pct); regs.append(reg)
                gs.append(g); ys.append(r["value"] * sign)
            n = len(gaps)
            cellv = {"n": n}
            if n and n < THIN_CELL:
                cellv["thin"] = True
                cellv["range_gap"] = [_r4(min(gaps)), _r4(max(gaps))]
            elif n:
                cellv["mean_gap"] = _r4(sum(gaps) / n)
                cellv["mean_regressed_gap"] = (_r4(sum(x for x in regs if x is not None) / n)
                                               if km is not None else None)
                pv = [p for p in pcts if p is not None]
                cellv["mean_pit_minus_half"] = _r4(sum(pv) / len(pv) - 0.5) if pv else None
                cellv["mean_abs_regressed_gap"] = (_r4(sum(abs(x) for x in regs if x is not None) / n)
                                                   if km is not None else None)
                rho = _spearman(gs, ys)
                cellv["ordering_rho"] = _r4(rho)
                if rho is not None:
                    rho_num += n * rho
                    rho_den += n
                all_gap += gaps; all_reg += [x for x in regs if x is not None]
                all_pct += pv; all_abs += [abs(x) for x in regs if x is not None]
            per_year[str(Y)] = cellv
        n_all = len(all_gap)
        out["by_source"][src] = {
            "per_year": per_year, "n": n_all,
            "computable": n_all >= POOL_MIN,
            "ordering": _r4(rho_num / rho_den) if rho_den else None,
            "bias_regressed": _r4(sum(all_reg) / len(all_reg)) if all_reg else None,
            "bias_pit": _r4(sum(all_pct) / len(all_pct) - 0.5) if all_pct else None,
            "error_abs_regressed": _r4(sum(all_abs) / len(all_abs)) if all_abs else None,
            "note": None if n_all >= POOL_MIN else f"NOT COMPUTABLE: pool under {POOL_MIN} players"}
    out["tables"] = {str(Y): {"n_rows": t.n_rows, "knots": [_r4(k) for k in t.knots],
                              "values": [_r4(v) for v in t.values],
                              "thin_bins": [b["bin"] for b in t.bins if b["thin"]]}
                     for Y, t in tables.items()}
    return out


def run_look_w(universe: Universe, data: dict, *, boot: int = W_BOOT, perm: int = W_PERM,
               controls: bool = True, k_m: dict | None = None) -> dict:
    """The whole Part W pipeline: primaries with verdicts (Holm m = the computable
    primaries), secondaries marked as such, TAG tables, controls."""
    out = {"primaries": {}, "secondaries": {}, "tag": {}, "survivorship": SURVIVORSHIP,
           "constants": {"MIN_LAG_YEARS": MIN_LAG_YEARS, "WEIGHT_SHRINK_K": WEIGHT_SHRINK_K,
                         "WEIGHT_CLAMP": list(WEIGHT_CLAMP), "SPEARMAN_FLOOR": SPEARMAN_FLOOR,
                         "BOOT": boot, "PERM": perm, "SEED": W_SEED, "SEED_ALT": W_SEED_ALT}}
    pv = {}
    for tool, spec in W_PRIMARY.items():
        cells = {}
        for arm, sources in ARMS.items():
            by_year = w_rows(universe, tool, spec["stat"], spec["sign"], sources, data)
            cells[arm] = w_cell(by_year, sources, boot=boot, perm=perm, controls=controls)
        out["primaries"][tool] = {"stat": spec["stat"], "arms": cells}
        a = cells["A_fg_vs_pipeline"].get("gate") or {}
        pv[tool] = a.get("p_rho")
    hz = holm(pv)
    voided = False
    for tool, blk in out["primaries"].items():
        a = blk["arms"]["A_fg_vs_pipeline"].get("gate") or {}
        if a.get("verdict") == "NOT COMPUTABLE":
            blk["verdict"] = "NOT COMPUTABLE"
            continue
        blk["holm"] = hz[tool]
        if a.get("verdict_moves_between_seeds"):
            blk["verdict"] = "FAIL"
            blk["reason"] = "verdict moves between seeds (C6.5)"
        elif a.get("shuffled_outcome_collapsed") is False:
            blk["verdict"] = "VOID"
            voided = True
        elif a.get("G1_to_G5") and hz[tool]["rejected"]:
            blk["verdict"] = "PASS"
        elif a.get("loss_clause"):
            blk["verdict"] = "LOSS"
        else:
            blk["verdict"] = "NULL"
        blk["arm_B"] = "NULL by construction: Baseball America's earliest tool vintage is 2023"
    out["look_void"] = voided
    for key, spec in W_SECONDARY.items():
        tool = spec.get("tool", key)
        cells = {}
        for arm, sources in ARMS.items():
            by_year = w_rows(universe, tool, spec["stat"], spec["sign"], sources, data)
            cells[arm] = w_cell(by_year, sources, boot=boot, perm=perm, controls=False)
        out["secondaries"][key] = {"tool": tool, "stat": spec["stat"], "arms": cells,
                                   "ba2": spec["ba2"], "verdict": "secondary: no verdict"}
    for tool, spec in list(W_PRIMARY.items()) + [(k, v) for k, v in W_SECONDARY.items()] \
            + list(W_SINGLE.items()):
        t = spec.get("tool", tool)
        out["tag"][tool] = w_tag_tables(universe, t, spec["stat"], spec["sign"], data, k_m)
    return out


# ---------------------------------------------------------------------------
# LOOK T: re-derived tables against the published estimates (gate Part T)
# ---------------------------------------------------------------------------
def freeze_grade_rows(debuts=None, index=None) -> dict:
    """T.3's frozen grade rows: the last pre-debut tools_consensus point per
    debuts.json record, identity-resolved outcome-blind, R-LV grade-point years and
    R-VM debuts excluded and counted; the named tools only, no other field."""
    debuts = debuts if debuts is not None else load_debuts()
    counts = defaultdict(int)
    rows = []
    pending = []
    for rec in debuts:
        mid = rec.get("mlbam_id")
        dd = rec.get("debut_date") or ""
        if rec.get("debut_date_is_placeholder") or len(dd) < 10:
            counts["placeholder_debut"] += 1
            continue
        if mid is None:
            counts["no_id"] += 1
            continue
        chosen = None
        for pt in rec.get("points") or []:
            d = pt.get("snapshot_date") or ""
            if d and d < dd and pt.get("tools_consensus"):
                chosen = pt
        if chosen is None:
            counts["no_pre_debut_grade_point"] += 1
            continue
        V = int(chosen["snapshot_date"][:4])
        if V in RESERVED_LV:
            counts["rlv_grade_point_year"] += 1
            continue
        if int(dd[:4]) >= R_VM_FIRST_DEBUT_YEAR:
            counts["rvm_debut"] += 1
            continue
        tools = {k: _f(v) for k, v in (chosen.get("tools_consensus") or {}).items()
                 if k in T_TOOLS and _f(v) is not None}
        if not tools:
            counts["no_named_tool"] += 1
            continue
        pending.append((rec, V, int(mid), dd, chosen["snapshot_date"], tools))
    if pending:
        max_v = max(p[1] for p in pending)
        index = index if index is not None else efv_identity.build_index(max_v - 1)
    for rec, V, mid, dd, sd, tools in pending:
        side = "pit" if is_pitcher_position(rec.get("position")) else "hit"
        res = efv_identity.resolve_record(rec, V, index, side)
        if res.person_id is None:
            counts[f"identity_{res.how}"] += 1
            continue
        if int(res.person_id) != mid:
            counts["identity_disagrees_with_record"] += 1
            continue
        rows.append({"mlbam": mid, "side": side, "debut_date": dd, "snapshot_date": sd,
                     "tools_consensus": tools})
    guard_debut_years([int(r["debut_date"][:4]) for r in rows])
    rows.sort(key=lambda r: (r["mlbam"], r["snapshot_date"]))
    return {"generated_at": _now(), "gate": GATE_DOC, "part": "T.3",
            "rule": "last pre-debut tools_consensus point; identity efv_identity.resolve_record "
                    "at the point's calendar year; R-LV grade-point years and R-VM debuts excluded",
            "tools": list(T_TOOLS), "n_rows": len(rows), "dropped": dict(counts), "rows": rows}


def t_season_lines(hit: dict, pit: dict, velo: dict, seasons) -> dict:
    """{(pid, season): line} of qualifying T.3 season lines per side."""
    out = {"hit": {}, "sp": {}, "rp": {}}
    for pid, by in hit.items():
        for s, r in by.items():
            if s in seasons and r["pa"] >= PA_FLOOR:
                out["hit"][(pid, s)] = r
    for pid, by in pit.items():
        for s, r in by.items():
            if s not in seasons or r["bf"] < BF_FLOOR or not r["g"]:
                continue
            role = "sp" if (r["gs"] / r["g"]) >= 0.5 else "rp"
            line = dict(r)
            line["velo"] = (velo.get(s) or {}).get(pid)
            out[role][(pid, s)] = line
    return out


def t_pool(lines: list[dict], stat: str) -> tuple[float | None, float]:
    """FIT pooling by exposure (T.3): the value and its weight."""
    if not lines:
        return None, 0.0
    if stat in ("hr_per600", "iso", "avg", "k_pct", "sb_per600"):
        pa = sum(r["pa"] for r in lines)
        ab = sum(r["ab"] for r in lines)
        if not pa:
            return None, 0.0
        if stat == "hr_per600":
            return 600.0 * sum(r["hr"] for r in lines) / pa, pa
        if stat == "k_pct":
            return 100.0 * sum(r["so"] for r in lines) / pa, pa
        if stat == "sb_per600":
            return 600.0 * sum(r["sb"] for r in lines) / pa, pa
        if not ab:
            return None, 0.0
        if stat == "iso":
            return (sum(r["tb"] for r in lines) - sum(r["h"] for r in lines)) / ab, pa
        return sum(r["h"] for r in lines) / ab, pa
    if stat == "bb_pct":
        bf = sum(r["bf"] for r in lines)
        return (100.0 * sum(r["bb"] for r in lines) / bf, bf) if bf else (None, 0.0)
    if stat == "velo":
        rows = [r for r in lines if r.get("velo") is not None]
        bf = sum(r["bf"] for r in rows)
        return (sum(r["velo"] * r["bf"] for r in rows) / bf, bf) if bf else (None, 0.0)
    if stat == "ev_avg":
        att = sum(r["attempts"] for r in lines if r.get("ev") is not None)
        return (sum(r["ev"] * r["attempts"] for r in lines if r.get("ev") is not None) / att, att) if att else (None, 0.0)
    if stat == "sprint":
        w = sum(r["runs"] for r in lines)
        return (sum(r["sprint"] * r["runs"] for r in lines) / w, w) if w else (None, 0.0)
    if stat == "oaa_per1000":
        inn = sum(r["inn"] for r in lines)
        return (1000.0 * sum(r["oaa"] for r in lines) / inn, inn) if inn else (None, 0.0)
    raise KeyError(stat)


def t_cell_rows(cell: dict, grade_rows: list[dict], season_lines: dict, seasons) -> dict:
    """{pid: {grade, lines: [season lines in `seasons`]}} for a cell."""
    side = cell["side"]
    out = {}
    for gr in grade_rows:
        g = gr["tools_consensus"].get(cell["tool"])
        if g is None:
            continue
        if (side == "hit") != (gr["side"] == "hit"):
            continue
        pid = gr["mlbam"]
        lines = [(s, season_lines[side][(pid, s)]) for s in seasons if (pid, s) in season_lines[side]]
        if lines:
            out[pid] = {"grade": g, "lines": lines}
    return out


def t_incumbent_value(cell_key: str, g, league_line: float | None):
    inc = T_INCUMBENT.get(cell_key) or T_SECONDARY_INCUMBENT.get(cell_key)
    if inc is None or inc["rows"] is None:
        return league_line
    return interp_table(inc["rows"], g)


def mae_w(pred, y, w):
    np = _np()
    pred, y, w = np.asarray(pred, float), np.asarray(y, float), np.asarray(w, float)
    if not w.sum():
        return None
    return float((w * np.abs(pred - y)).sum() / w.sum())


def t_fit_candidate(cell: dict, rows: dict, exclude_season=None, exclude_pids=()):
    fit_rows = []
    for pid, r in rows.items():
        if pid in exclude_pids:
            continue
        lines = [ln for s, ln in r["lines"] if s != exclude_season]
        v, _w = t_pool(lines, cell["stat"])
        if v is None:
            continue
        fit_rows.append({"id": pid, "grade": r["grade"], "value": v})
    return TI.fit_tables(fit_rows, cell["tool"], cell["stat"], "fit", sign=cell["sign"])


def t_league_line(season_lines: dict, season: int, stat: str = "k_pct") -> float | None:
    """The grade-blind league line (T.1, D2): 100 x sum SO / sum PA over every
    hitter row of the season with at least PA_FLOOR PA."""
    rows = [ln for (pid, s), ln in season_lines["hit"].items() if s == season]
    pa = sum(r["pa"] for r in rows)
    return (100.0 * sum(r["so"] for r in rows) / pa) if pa else None


def t_mde_cell(cell: dict, rows: dict, season_lines: dict, seasons) -> dict:
    """T.10: leave one FIT season out; score the players with a qualifying season-s
    line on that line; d_s = MAE_w(candidate refit without s) - MAE_w(incumbent)."""
    folds = []
    for s in seasons:
        tbl = t_fit_candidate(cell, rows, exclude_season=s)
        if not tbl.computable:
            folds.append({"season": s, "n": 0, "skipped": "no non-thin bin"})
            continue
        league = t_league_line(season_lines, s) if cell["cell"] == "hit__k_pct" else None
        pred_c, pred_i, ys, ws = [], [], [], []
        for pid, r in rows.items():
            ln = [line for ss, line in r["lines"] if ss == s]
            if not ln:
                continue
            v, w = t_pool(ln, cell["stat"])
            inc = t_incumbent_value(cell["cell"], r["grade"], league)
            if v is None or inc is None:
                continue
            pred_c.append(tbl.read(r["grade"])); pred_i.append(inc); ys.append(v); ws.append(w)
        n = len(ys)
        if n < T_MIN_ROWS:
            folds.append({"season": s, "n": n, "skipped": f"under {T_MIN_ROWS} rows"})
            continue
        mc, mi = mae_w(pred_c, ys, ws), mae_w(pred_i, ys, ws)
        folds.append({"season": s, "n": n, "mae_candidate": _r6(mc), "mae_incumbent": _r6(mi),
                      "d": _r6(mc - mi)})
    used = [f for f in folds if "d" in f]
    out = {"cell": cell["cell"], "folds": folds, "folds_used": len(used),
           "fold_rows": {str(f["season"]): f["n"] for f in used}}
    if len(used) < T_MIN_FOLDS:
        out["mde95"] = None
        out["note"] = f"NOT COMPUTABLE: fewer than {T_MIN_FOLDS} folds"
        return out
    import statistics
    sd = statistics.stdev(f["d"] for f in used)
    out["sd_d"] = _r6(sd)
    out["mde95"] = _r6(MDE_Z * sd)
    return out


def t_score_cell(cell: dict, rows_fit: dict, rows_hold: dict, season_lines: dict, *,
                 mde95, boot: int = T_BOOT, seed: int = T_SEED, beside=None) -> dict:
    """T.5 on the HOLDOUT rows: both MAEs, delta, UB95, p and the candidate bins."""
    np = _np()
    tbl = t_fit_candidate(cell, rows_fit)
    out = {"cell": cell["cell"], "n_fit": tbl.n_rows, "mde95": mde95,
           "candidate_bins": tbl.to_dict()["bins"], "knots": list(tbl.knots),
           "values": list(tbl.values)}
    if not tbl.computable:
        out["verdict"] = "NOT COMPUTABLE"
        out["reason"] = "no non-thin FIT bin"
        return out
    league = (t_league_line(season_lines, T_HOLDOUT_SEASON) if cell["cell"] == "hit__k_pct" else None)
    pc, pi, pb, ys, ws = [], [], [], [], []
    for pid, r in rows_hold.items():
        v, w = t_pool([ln for _s, ln in r["lines"]], cell["stat"])
        inc = t_incumbent_value(cell["cell"], r["grade"], league)
        if v is None or inc is None:
            continue
        pc.append(tbl.read(r["grade"])); pi.append(inc); ys.append(v); ws.append(w)
        pb.append(interp_table(beside["rows"], r["grade"]) if beside else None)
    n = len(ys)
    out["n"] = n
    if n < T_MIN_ROWS:
        out["verdict"] = "NOT COMPUTABLE"
        out["reason"] = f"fewer than {T_MIN_ROWS} HOLDOUT rows"
        return out
    pc, pi, ys, ws = (np.asarray(pc, float), np.asarray(pi, float), np.asarray(ys, float),
                      np.asarray(ws, float))
    mc, mi = mae_w(pc, ys, ws), mae_w(pi, ys, ws)
    delta = mc - mi
    rng = np.random.default_rng(seed)
    ds = []
    for _ in range(boot):
        idx = rng.integers(0, n, n)
        ds.append(mae_w(pc[idx], ys[idx], ws[idx]) - mae_w(pi[idx], ys[idx], ws[idx]))
    ds.sort()
    ub95 = ds[min(len(ds) - 1, int(0.95 * len(ds)))]
    p = (1 + sum(1 for d in ds if d >= 0)) / (len(ds) + 1)
    out.update({"mae_candidate": _r6(mc), "mae_incumbent": _r6(mi), "delta": _r6(delta),
                "ub95": _r6(ub95), "p": _r6(p), "boot": boot, "seed": seed,
                "margin_required": _r6(max(mde95 or 0.0, 0.05 * mi)) if mde95 is not None else None})
    if beside:
        pb = np.asarray(pb, float)
        out["beside"] = {"source": beside["source"], "mae": _r6(mae_w(pb, ys, ws)),
                         "verdict": "secondary: no verdict"}
    if mde95 is None:
        out["verdict"] = "NOT COMPUTABLE"
        out["reason"] = "no T.10 MDE95"
    return out


def t_verdicts(cells: dict) -> dict:
    pv = {k: c.get("p") for k, c in cells.items() if c.get("verdict") != "NOT COMPUTABLE"}
    hz = holm(pv)
    for k, c in cells.items():
        if c.get("verdict") == "NOT COMPUTABLE":
            continue
        c["holm"] = hz[k]
        c1 = bool(c["ub95"] is not None and c["ub95"] < 0)
        c2 = bool(c["delta"] is not None and -c["delta"] >= c["margin_required"])
        c3 = bool(hz[k]["rejected"])
        c["clauses"] = {"1_ub95_below_0": c1, "2_margin": c2, "3_holm": c3}
        c["verdict"] = "PASS" if (c1 and c2 and c3) else "FAIL"
    return cells


def run_look_t(grade_rows: list[dict], season_lines_fit: dict, season_lines_hold: dict, *,
               mde95: dict, boot: int = T_BOOT, seed: int = T_SEED, secondary_lines=None) -> dict:
    """The whole Part T pipeline (pure; the caller loaded FIT and HOLDOUT lines)."""
    cells = {}
    for cell in T_PRIMARY:
        seasons = T_VELO_SEASONS if cell["stat"] == "velo" else T_FIT_SEASONS
        rows_fit = t_cell_rows(cell, grade_rows, season_lines_fit, seasons)
        rows_hold = t_cell_rows(cell, grade_rows, season_lines_hold, (T_HOLDOUT_SEASON,))
        res = t_score_cell(cell, rows_fit, rows_hold, season_lines_hold,
                           mde95=(mde95.get(cell["cell"]) or {}).get("mde95"), boot=boot, seed=seed,
                           beside=T_BESIDE.get(cell["cell"]))
        # T.11 (b): the candidate refit on FIT players who hold no HOLDOUT row.
        hold_p = set(rows_hold)
        tbl_s = t_fit_candidate(cell, rows_fit, exclude_pids=hold_p)
        if tbl_s.computable and res.get("n", 0) >= T_MIN_ROWS:
            league = (t_league_line(season_lines_hold, T_HOLDOUT_SEASON)
                      if cell["cell"] == "hit__k_pct" else None)
            pc, pi, ys, ws = [], [], [], []
            for pid, r in rows_hold.items():
                v, w = t_pool([ln for _s, ln in r["lines"]], cell["stat"])
                inc = t_incumbent_value(cell["cell"], r["grade"], league)
                if v is None or inc is None:
                    continue
                pc.append(tbl_s.read(r["grade"])); pi.append(inc); ys.append(v); ws.append(w)
            mc, mi = mae_w(pc, ys, ws), mae_w(pi, ys, ws)
            res["sensitivity"] = {"delta": _r6(None if (mc is None or mi is None) else mc - mi),
                                  "n_fit_disjoint": tbl_s.n_rows, "verdict": "sensitivity: no verdict"}
        cells[cell["cell"]] = res
    t_verdicts(cells)
    out = {"primary": cells, "survivorship": SURVIVORSHIP, "secondary": {}}
    for cell in T_SECONDARY:
        lines_fit = (secondary_lines or {}).get("fit") or season_lines_fit
        lines_hold = (secondary_lines or {}).get("hold") or season_lines_hold
        seasons = T_VELO_SEASONS if cell["stat"] == "velo" else T_FIT_SEASONS
        try:
            rows_fit = t_cell_rows(cell, grade_rows, lines_fit, seasons)
            rows_hold = t_cell_rows(cell, grade_rows, lines_hold, (T_HOLDOUT_SEASON,))
            res = t_score_cell(cell, rows_fit, rows_hold, lines_hold, mde95=None, boot=boot, seed=seed)
        except KeyError as e:
            res = {"cell": cell["cell"], "verdict": "NOT COMPUTABLE", "reason": f"no lines: {e}"}
        res["verdict"] = "secondary: no verdict" if res.get("n", 0) >= T_MIN_ROWS else res.get("verdict", "NOT COMPUTABLE")
        out["secondary"][cell["cell"]] = res
    return out


# ---------------------------------------------------------------------------
# Part 4: k_m by split-half reliability (no prospect join, no grade read)
# ---------------------------------------------------------------------------
K_M_WINDOW = (2015, 2016, 2017, 2018, 2019)
_PA_EVENTS = {"field_out", "strikeout", "single", "walk", "double", "home_run", "force_out",
              "grounded_into_double_play", "hit_by_pitch", "field_error", "sac_fly", "intent_walk",
              "triple", "sac_bunt", "double_play", "fielders_choice", "fielders_choice_out",
              "strikeout_double_play", "catcher_interf", "sac_fly_double_play", "triple_play",
              "sac_bunt_double_play", "other_out"}
_NON_AB = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf",
           "sac_fly_double_play", "sac_bunt_double_play"}
_HITS = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
_SO = {"strikeout", "strikeout_double_play"}
_BB = {"walk", "intent_walk"}
_SWING = {"S", "F", "X", "D", "E", "T", "W", "L", "M", "Q", "R", "O"}
_CONTACT = {"F", "X", "D", "E", "T", "L", "O"}
_FASTBALLS = {"FF", "SI", "FC"}


def _split_half(values_by_unit: dict, floor: float):
    """values_by_unit: {(pid, season): (odd_num, odd_den, even_num, even_den)}.
    Returns the split-half Pearson r over units with den >= floor, mean half
    exposure and the count."""
    np = _np()
    xs, ys, ex = [], [], []
    for (on, od, en, ed) in values_by_unit.values():
        if od + ed < floor or not od or not ed:
            continue
        xs.append(on / od); ys.append(en / ed); ex.append((od + ed) / 2.0)
    n = len(xs)
    if n < 30:
        return None, None, n
    r = float(np.corrcoef(np.asarray(xs), np.asarray(ys))[0, 1])
    return r, float(np.mean(ex)), n


def k_from_r(r: float | None, n_h: float | None):
    """Spearman-Brown: R = 2r / (1 + r) at exposure n = 2 n_h; k_m = n (1 - R) / R."""
    if r is None or n_h is None or r <= 0:
        return None
    R = 2 * r / (1 + r)
    return 2 * n_h * (1 - R) / R


def measure_k_m(seasons=K_M_WINDOW, *, hitter_floor: float = PA_FLOOR, pitcher_floor: float = BF_FLOOR) -> dict:
    """Part 4: split-half reliability of every TAG stat on MLB player-seasons in
    the 2015-2019 window from the per-event caches on disk (.cache/pbp_corpus
    plays and pitches, .cache/pbp_runners pa and runners), odd and even events
    (odd and even games for stolen bases, a runner event). A stat with no
    per-event data on disk for the window is NOT COMPUTABLE. No prospect row, no
    grade and no debut is read."""
    import pyarrow.parquet as pq
    np = _np()
    found = []
    acc = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))
    sb_games = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))
    seq = defaultdict(int)
    for s in seasons:
        plays_p = CACHE / "pbp_corpus" / "plays" / str(s) / f"plays-{s}.parquet"
        pa_p = CACHE / "pbp_runners" / "plays" / str(s) / f"pa-{s}.parquet"
        if not plays_p.exists():
            continue
        found.append(s)
        plays = pq.read_table(plays_p, columns=["game_pk", "at_bat_index", "batter_id", "pitcher_id",
                                                "event_type"]).to_pylist()
        launch = {}
        if pa_p.exists():
            for r in pq.read_table(pa_p, columns=["game_pk", "at_bat_index", "launch_speed"]).to_pylist():
                if r["launch_speed"] is not None:
                    launch[(r["game_pk"], r["at_bat_index"])] = float(r["launch_speed"])
        plays.sort(key=lambda r: (r["game_pk"], r["at_bat_index"]))
        for r in plays:
            et = r["event_type"]
            if et not in _PA_EVENTS:
                continue
            b, p = r["batter_id"], r["pitcher_id"]
            kb, kp = (b, s), (p, s)
            hb = seq[("b", kb)] % 2; seq[("b", kb)] += 1
            hp = seq[("p", kp)] % 2; seq[("p", kp)] += 1
            ob = 0 if hb == 0 else 2
            op = 0 if hp == 0 else 2
            ab = et not in _NON_AB
            so = et in _SO
            hit = _HITS.get(et, 0)
            hr = 1 if et == "home_run" else 0
            # hitters
            a = acc["k_pct"][kb]; a[ob] += so; a[ob + 1] += 1
            a = acc["hr_pa"][kb]; a[ob] += hr; a[ob + 1] += 1
            if ab:
                a = acc["avg"][kb]; a[ob] += 1 if hit else 0; a[ob + 1] += 1
                a = acc["iso"][kb]; a[ob] += max(0, hit - 1) if hit else 0; a[ob + 1] += 1
                if not so and not hr:
                    a = acc["babip"][kb]; a[ob] += 1 if hit else 0; a[ob + 1] += 1
            elif et in ("sac_fly", "sac_fly_double_play"):
                a = acc["babip"][kb]; a[ob + 1] += 1
            ls = launch.get((r["game_pk"], r["at_bat_index"]))
            if ls is not None:
                a = acc["ev_avg"][kb]; a[ob] += ls; a[ob + 1] += 1
            # pitchers
            a = acc["k_pct_pit"][kp]; a[op] += so; a[op + 1] += 1
            a = acc["bb_pct_pit"][kp]; a[op] += 1 if et in _BB else 0; a[op + 1] += 1
        # stolen bases by the runner, split by odd and even games
        run_p = CACHE / "pbp_runners" / "runners" / str(s) / f"runners-{s}.parquet"
        if run_p.exists():
            games_of = defaultdict(set)
            for r in plays:
                if r["event_type"] in _PA_EVENTS:
                    games_of[r["batter_id"]].add(r["game_pk"])
            pa_in_game = defaultdict(int)
            for r in plays:
                if r["event_type"] in _PA_EVENTS:
                    pa_in_game[(r["batter_id"], r["game_pk"])] += 1
            sb_in_game = defaultdict(int)
            for r in pq.read_table(run_p, columns=["game_pk", "runner_id", "movement_reason"]).to_pylist():
                if (r["movement_reason"] or "").startswith("r_stolen_base"):
                    sb_in_game[(r["runner_id"], r["game_pk"])] += 1
            for b, games in games_of.items():
                for i, gpk in enumerate(sorted(games)):
                    h = 0 if i % 2 == 0 else 2
                    a = sb_games["sb_per600"][(b, s)]
                    a[h] += sb_in_game.get((b, gpk), 0); a[h + 1] += pa_in_game[(b, gpk)]
        # pitch-level: chase, zone contact (batters) and fastball velocity (pitchers)
        pitch_p = CACHE / "pbp_corpus" / "pitches" / str(s) / f"pitches-{s}.parquet"
        if pitch_p.exists():
            who = {(r["game_pk"], r["at_bat_index"]): (r["batter_id"], r["pitcher_id"]) for r in plays}
            pitches = pq.read_table(pitch_p, columns=["game_pk", "at_bat_index", "pitch_number",
                                                      "call_code", "zone", "pitch_type", "start_speed",
                                                      "is_pitch"]).to_pylist()
            pitches.sort(key=lambda r: (r["game_pk"], r["at_bat_index"], r["pitch_number"] or 0))
            for r in pitches:
                if not r.get("is_pitch", True):
                    continue
                ids = who.get((r["game_pk"], r["at_bat_index"]))
                if ids is None:
                    continue
                b, p = ids
                code, zone = r["call_code"], r["zone"]
                if code is None:
                    continue
                swing = code in _SWING
                if zone is not None and 11 <= zone <= 14:
                    kb = (b, s)
                    h = seq[("oz", kb)] % 2; seq[("oz", kb)] += 1
                    a = acc["chase_pct"][kb]; a[2 * h] += 100.0 if swing else 0.0; a[2 * h + 1] += 1
                if zone is not None and 1 <= zone <= 9 and swing:
                    kb = (b, s)
                    h = seq[("iz", kb)] % 2; seq[("iz", kb)] += 1
                    a = acc["z_contact_pct"][kb]; a[2 * h] += 100.0 if code in _CONTACT else 0.0; a[2 * h + 1] += 1
                if r["pitch_type"] in _FASTBALLS and r["start_speed"] is not None:
                    kp = (p, s)
                    h = seq[("fb", kp)] % 2; seq[("fb", kp)] += 1
                    a = acc["fb_velo"][kp]; a[2 * h] += float(r["start_speed"]); a[2 * h + 1] += 1
    acc["sb_per600"] = sb_games["sb_per600"]
    floors = {"k_pct": hitter_floor, "hr_pa": hitter_floor, "avg": 0.8 * hitter_floor,
              "iso": 0.8 * hitter_floor, "babip": 0.6 * hitter_floor, "sb_per600": hitter_floor,
              "ev_avg": 100.0, "chase_pct": 400.0, "z_contact_pct": 150.0,
              "k_pct_pit": pitcher_floor, "bb_pct_pit": pitcher_floor, "fb_velo": 200.0}
    units = {"k_pct": "pa", "hr_pa": "pa", "avg": "ab", "iso": "ab", "babip": "ab (less SO and HR, plus SF)",
             "sb_per600": "pa (odd and even games)", "ev_avg": "attempts (batted balls)",
             "chase_pct": "oz_pitches", "z_contact_pct": "iz_swings", "k_pct_pit": "bf",
             "bb_pct_pit": "bf", "fb_velo": "fastballs (FF, SI, FC)"}
    out = {"generated_at": _now(), "gate": GATE_DOC, "part": "4",
           "window": list(seasons), "seasons_on_disk": found,
           "method": "split-half (odd and even events; odd and even games for stolen bases) on MLB "
                     "player-seasons; r at mean half exposure n_h; R = 2r / (1 + r); k_m = 2 n_h (1 - R) / R",
           "floors": floors, "stats": {}, "not_computable": {}}
    for stat, floor in floors.items():
        r, n_h, n = _split_half(acc.get(stat, {}), floor)
        k = k_from_r(r, n_h)
        out["stats"][stat] = {"unit": units[stat], "n_player_seasons": n, "split_half_r": _r4(r),
                              "mean_half_exposure": _r4(n_h), "R_full": _r4(None if r is None or r <= 0 else 2 * r / (1 + r)),
                              "k_m": _r4(k), "floor": floor}
    out["not_computable"] = {
        "sprint": "no per-run sprint data for 2015-2019 on disk (.cache/savant_sprint/ is a season leaderboard)",
        "oaa_per1000": "no per-play OAA for 2015-2019 on disk (.cache/savant_oaa/ is a season leaderboard)",
        "arm_z": "arm strength is cached from 2020 (.cache/savant_arm/)",
        "brl_pa": "no per-event barrel flag for 2015-2019 on disk",
    }
    for stat, reason in out["not_computable"].items():
        out["stats"].setdefault(stat, {"unit": K_M.get(stat, {}).get("unit"), "k_m": None, "note": reason})
    return out


def render_k_m_table(km: dict) -> str:
    lines = ["| stat | exposure unit | player-seasons | split-half r | R (full) | k_m |",
             "|---|---|---|---|---|---|"]
    for stat, v in km["stats"].items():
        if v.get("k_m") is None:
            lines.append(f"| {stat} | {v.get('unit')} | n/a | n/a | n/a | NOT COMPUTABLE: {v.get('note', 'no data')} |")
        else:
            lines.append(f"| {stat} | {v['unit']} | {v['n_player_seasons']} | {v['split_half_r']} | "
                         f"{v['R_full']} | {v['k_m']} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# fixtures and the dry run (reads no real row)
# ---------------------------------------------------------------------------
def fixtures(seed: int = 7, n_players: int = 240) -> dict:
    """Synthetic frames carrying None values for every look's reporting path."""
    import random
    rng = random.Random(seed)
    years = (2017, 2018, 2019, 2022, 2023, 2024)
    p_rows, w_by_year, grade_rows = [], defaultdict(list), []
    hit_fit, hit_hold, sp_fit, sp_hold = {}, {}, {}, {}
    for i in range(n_players):
        pid = 100000 + i
        true = rng.gauss(50, 10)
        g = round_half(min(80, max(20, true + rng.gauss(0, 5))))
        raw = round_half(min(80, max(20, true + rng.gauss(0, 7))))
        iso = max(0.0, 0.05 + 0.003 * (true - 50) + rng.gauss(0, 0.04))
        Y = years[i % len(years)]
        if i % 17 == 0:
            iso = None
        if i % 23 == 0:
            raw = None
        p_rows.append({"pid": pid, "year": Y, "game": g, "raw": raw, "iso": iso, "pa": 400 + i,
                       "hr_pa": None if i % 13 == 0 else max(0.0, 0.02 + 0.001 * (true - 50) + rng.gauss(0, 0.01)),
                       "brl_pa": None if i % 5 == 0 else max(0.0, 0.05 + rng.gauss(0, 0.02)),
                       "ev_avg": None if i % 7 == 0 else 88 + 0.1 * (true - 50) + rng.gauss(0, 2)})
        fg = min(80, max(20, true + rng.gauss(0, 6)))
        pl = min(80, max(20, true + rng.gauss(0, 6)))
        y = -(22 - 0.2 * (true - 50) + rng.gauss(0, 4))
        if i % 19 != 0:
            w_by_year[Y].append({"player": pid, "grades": {"fangraphs": fg, "mlb_pipeline": pl}, "y": y,
                                 "exposure": 400.0})
        side = "hit" if i % 3 else "pit"
        grade_rows.append({"mlbam": pid, "side": side, "debut_date": f"{2016 + i % 8}-06-01",
                           "snapshot_date": f"{2015 + i % 8}-02-01",
                           "tools_consensus": ({"game_pwr": g, "hit": round_half(fg), "speed": round_half(pl)}
                                               if side == "hit" else {"cmd": round_half(fg), "fb": round_half(pl)})})
        for s in T_FIT_SEASONS:
            if (i + s) % 3 == 0:
                continue
            pa = 320 + (i * 7 + s) % 200
            if side == "hit":
                hit_fit[(pid, s)] = {"pa": pa, "ab": pa * 0.9, "h": pa * 0.23, "hr": pa * (0.02 + 0.0005 * (true - 50)),
                                     "tb": pa * 0.38, "so": pa * (0.22 - 0.002 * (true - 50)), "bb": pa * 0.08,
                                     "sb": pa * 0.01, "sf": 2}
            else:
                sp_fit[(pid, s)] = {"bf": pa, "so": pa * 0.22, "bb": pa * (0.08 - 0.001 * (true - 50)),
                                    "g": 30, "gs": 28, "velo": None if i % 11 == 0 else 92 + 0.08 * (true - 50)}
        pa = 350 + i % 150
        if side == "hit":
            hit_hold[(pid, T_HOLDOUT_SEASON)] = {"pa": pa, "ab": pa * 0.9, "h": pa * 0.24, "hr": pa * 0.025,
                                                 "tb": pa * 0.39, "so": pa * 0.21, "bb": pa * 0.08, "sb": pa * 0.012, "sf": 2}
        else:
            sp_hold[(pid, T_HOLDOUT_SEASON)] = {"bf": pa, "so": pa * 0.23, "bb": pa * 0.07, "g": 30, "gs": 29,
                                                "velo": None if i % 9 == 0 else 93.0}
    return {"p_rows": p_rows, "w_by_year": dict(w_by_year), "grade_rows": grade_rows,
            "t_fit": {"hit": hit_fit, "sp": sp_fit, "rp": {}},
            "t_hold": {"hit": hit_hold, "sp": sp_hold, "rp": {}}}


class _FixtureUniverse:
    """A Universe stand-in for the dry run (no identity index, no database)."""

    def __init__(self, fx):
        self.rows = {}
        for Y, rows in fx["w_by_year"].items():
            for r in rows:
                self.rows[(Y, r["player"])] = {"year": Y, "pid": r["player"], "side": "hit",
                                               "debut_year": Y + 1,
                                               "per_source": {s: {"hit": g, "speed": g, "field": g, "throw": g,
                                                                  "game_pwr": g, "raw_pwr": g}
                                                              for s, g in r["grades"].items()},
                                               "consensus": {t: consensus_tool_grade(
                                                   {s: {t: g} for s, g in r["grades"].items()}, t)
                                                   for t in ("hit", "speed", "field", "throw", "game_pwr", "raw_pwr")}}
        self.counts = {"rows": len(self.rows), "fixture": True}


def _fixture_data(fx) -> dict:
    """Outcome caches for the dry run, keyed like the real loaders, with None holes."""
    hit, sprint, oaa, finn, arm = {}, {}, {}, {}, {}
    for Y, rows in fx["w_by_year"].items():
        for i, r in enumerate(rows):
            pid = r["player"]
            lines = {}
            for k, s in enumerate((Y + 1, Y + 2, Y + 3)):
                if s > LAST_OUTCOME_SEASON or (i + k) % 7 == 0:
                    continue
                pa = 150.0 + 10 * (i % 20)
                lines[s] = {"pa": pa, "ab": pa * 0.9, "h": pa * 0.23, "hr": pa * 0.02, "tb": pa * 0.37,
                            "so": pa * (0.25 + (-r["y"] - 22) / 400.0), "bb": pa * 0.08, "sb": pa * 0.01, "sf": 2}
            hit[pid] = lines
            sprint[pid] = {s: {"sprint": 27 + (r["grades"]["fangraphs"] - 50) * 0.05, "runs": 40.0}
                           for s in lines if i % 5}
            oaa[pid] = {s: (r["grades"]["mlb_pipeline"] - 50) * 0.1 for s in lines}
            finn[pid] = {s: 300.0 + 20 * (i % 30) for s in lines}
            for s in lines:
                if s >= 2020:
                    arm.setdefault(s, {})[pid] = {"group": "inf", "arm": 85 + (r["grades"]["fangraphs"] - 50) * 0.1,
                                                  "throws": 100.0, "pos": "6", "z": (r["grades"]["fangraphs"] - 50) / 10.0}
    return {"hit": hit, "sc": {}, "sprint": sprint, "oaa": oaa, "finn": finn, "arm": arm, "pit": {},
            "disc": {}}


def dry_run(look: str, out_dir: Path, *, seed: int = 7, boot: int = 40, perm: int = 30) -> dict:
    """The whole reporting path of `look` on fixtures carrying None values. Reads no
    real row; writes only under `out_dir` (never a served file)."""
    fx = fixtures(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {"generated_at": _now(), "dry_run": True, "look": look, "reads_real_rows": False,
           "fixture_seed": seed, "boot": boot, "perm": perm}
    if look == "P":
        res = run_look_p(fx["p_rows"], boot=boot, perm=perm, seed=P_SEED)
    elif look == "W":
        uni = _FixtureUniverse(fx)
        res = run_look_w(uni, _fixture_data(fx), boot=boot, perm=perm, controls=True)
    else:
        mde = {}
        for cell in T_PRIMARY:
            seasons = T_VELO_SEASONS if cell["stat"] == "velo" else T_FIT_SEASONS
            rows = t_cell_rows(cell, fx["grade_rows"], fx["t_fit"], seasons)
            mde[cell["cell"]] = t_mde_cell(cell, rows, fx["t_fit"], seasons)
        res = run_look_t(fx["grade_rows"], fx["t_fit"], fx["t_hold"], mde95=mde, boot=boot, seed=T_SEED)
        res["mde"] = mde
    rec["result"] = res
    rec["record_text"] = render_record(look, res, rec)
    path = out_dir / f"dry_run_{look}.json"
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    rec["path"] = str(path)
    return rec


# ---------------------------------------------------------------------------
# the record (gate P.11, W.13, T.12)
# ---------------------------------------------------------------------------
def render_record(look: str, res: dict, meta: dict) -> str:
    lines = [f"### Look {look} ({'dry run on fixtures' if meta.get('dry_run') else meta.get('date', '')})",
             ""]
    if look == "P":
        v = res.get("verdict") or {}
        lines.append(f"rows {res.get('n')} by board year {res.get('rows_by_year')}; "
                     f"a by year {res.get('a_by_year')}; served a {res.get('served_a')} ({res.get('served_as')})")
        for name in ("C1", "C2"):
            c = v.get(name) or {}
            lines.append(f"- {name}: d {c.get('d')}, lo95 {c.get('lo95')}, F {c.get('F')}, ratio {c.get('ratio_to_floor')}, "
                         f"d_auc {c.get('d_auc')} (floor {c.get('F_auc')}, veto {c.get('auc_veto')}), "
                         f"p {c.get('p_perm')}, Holm step {c.get('holm_step')}, pass {c.get('pass')}")
        lines.append(f"- serve: {v.get('serve')}")
        for k, s in (res.get("secondary") or {}).items():
            lines.append(f"- secondary {k}: n {s.get('n')} {s.get('candidates')} ({s.get('verdict')})")
    elif look == "W":
        for tool, blk in (res.get("primaries") or {}).items():
            a = (blk.get("arms") or {}).get("A_fg_vs_pipeline") or {}
            g = a.get("gate") or {}
            pr = a.get("primary") or {}
            lines.append(f"- {tool} ({blk.get('stat')}): n {pr.get('n')}, equal rho {(pr.get('equal') or {}).get('spearman')}, "
                         f"weighted rho {(pr.get('weighted') or {}).get('spearman')}, d {pr.get('d_rho')}, "
                         f"F {g.get('F_rho')}, lo95 {(a.get('bootstrap') or {}).get('d_rho_lo95')}, p {g.get('p_rho')}, "
                         f"Holm {(blk.get('holm') or {}).get('step')}, verdict {blk.get('verdict')}; arm B {blk.get('arm_B')}")
        for key, blk in (res.get("secondaries") or {}).items():
            a = (blk.get("arms") or {}).get("A_fg_vs_pipeline") or {}
            lines.append(f"- {key} ({blk.get('stat')}): n {(a.get('primary') or {}).get('n')}, d {(a.get('primary') or {}).get('d_rho')}; "
                         f"{blk.get('verdict')}; BA2 {blk.get('ba2')}")
        for tool, t in (res.get("tag") or {}).items():
            lines.append(f"- TAG {tool}/{t.get('stat')}: frame {t.get('n_frame')}, k_m {t.get('k_m')}; "
                         + "; ".join(f"{s}: ordering {b.get('ordering')}, bias {b.get('bias_regressed')}, "
                                     f"error {b.get('error_abs_regressed')}" for s, b in (t.get('by_source') or {}).items()))
    else:
        for k, c in (res.get("primary") or {}).items():
            lines.append(f"- {k}: n {c.get('n')}, MAE candidate {c.get('mae_candidate')}, incumbent {c.get('mae_incumbent')}, "
                         f"delta {c.get('delta')}, UB95 {c.get('ub95')}, p {c.get('p')}, MDE95 {c.get('mde95')}, "
                         f"Holm {(c.get('holm') or {}).get('step')}, verdict {c.get('verdict')}")
        for k, c in (res.get("secondary") or {}).items():
            lines.append(f"- {k}: n {c.get('n')}, delta {c.get('delta')}; {c.get('verdict')}")
    lines.append("")
    lines.append(SURVIVORSHIP)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# real runs
# ---------------------------------------------------------------------------
def _inputs_sha(paths) -> dict:
    return {_rel(p): sha256_of(p)
            for p in paths}


def _assert_no_look_today_conflict(look: str) -> None:
    spent = look_spent(look)
    if spent:
        raise GuardError(f"look {look} is spent: {spent}")


def real_look_p(args) -> dict:
    _assert_no_look_today_conflict("P")
    if not gate_sha_ok(args.gate_sha):
        raise GuardError("--gate-sha must name a committed ancestor carrying the gate with its REGISTERED status line")
    uni = Universe(P_YEARS, None)
    hit_years = range(min(P_YEARS) + 1, LAST_OUTCOME_SEASON + 1)
    hit = load_statsapi("hitting", hit_years)
    sc = load_statcast_batter(range(2016, LAST_OUTCOME_SEASON + 1))
    inputs = [CACHE / f"fa_statsapi_hitting_{y}.json" for y in hit_years] + \
             [CACHE / "savant_mlb" / f"statcast_batter_{y}.csv" for y in range(2016, LAST_OUTCOME_SEASON + 1)]
    sha_start = _inputs_sha(inputs)
    rows = p_frame_rows(uni, hit, sc)
    guard_debut_years([r["debut_year"] for r in uni.rows.values()])
    res = run_look_p(rows, boot=args.boot or P_BOOT, perm=args.perm or P_PERM)
    rec = {"generated_at": _now(), "look": "P", "spent": True, "gate": GATE_DOC, "gate_sha": args.gate_sha,
           "universe_counts": dict(uni.counts), "inputs_sha256_start": sha_start,
           "inputs_sha256_end": _inputs_sha(inputs), "result": res}
    rec["record_text"] = render_record("P", res, {"date": date.today().isoformat()})
    return rec


def real_look_w(args) -> dict:
    _assert_no_look_today_conflict("W")
    if not gate_sha_ok(args.gate_sha):
        raise GuardError("--gate-sha must name a committed ancestor carrying the gate with its REGISTERED status line")
    uni = Universe(W_YEARS, args.rlv_record)
    yrs = range(min(W_YEARS) + 1, LAST_OUTCOME_SEASON + 1)
    data = {"hit": load_statsapi("hitting", yrs), "pit": load_statsapi("pitching", yrs),
            "sc": load_statcast_batter(range(2016, LAST_OUTCOME_SEASON + 1)),
            "sprint": load_sprint(yrs), "oaa": load_oaa(range(2016, LAST_OUTCOME_SEASON + 1)),
            "finn": load_fielding_innings(), "arm": load_arm(range(2020, LAST_OUTCOME_SEASON + 1)),
            "disc": load_leaderboard_discipline()}
    inputs = [CACHE / f"fa_statsapi_hitting_{y}.json" for y in yrs] + \
             [CACHE / f"fa_statsapi_pitching_{y}.json" for y in yrs] + \
             [CACHE / "savant_sprint" / f"sprint_{y}.csv" for y in yrs] + \
             [CACHE / "savant_arm" / f"arm_{y}.csv" for y in range(2020, LAST_OUTCOME_SEASON + 1)] + \
             [DATA / "fielding_innings.json", DATA / "hitter_leaderboards.json"]
    sha_start = _inputs_sha(inputs)
    res = run_look_w(uni, data, boot=args.boot or W_BOOT, perm=args.perm or W_PERM)
    rec = {"generated_at": _now(), "look": "W", "spent": True, "gate": GATE_DOC, "gate_sha": args.gate_sha,
           "rlv_record": args.rlv_record, "universe_counts": dict(uni.counts),
           "inputs_sha256_start": sha_start, "inputs_sha256_end": _inputs_sha(inputs), "result": res}
    rec["record_text"] = render_record("W", res, {"date": date.today().isoformat()})
    return rec


def _t_fit_inputs():
    paths = [CACHE / f"fa_statsapi_hitting_{y}.json" for y in T_FIT_SEASONS] + \
            [CACHE / f"fa_statsapi_pitching_{y}.json" for y in T_FIT_SEASONS] + \
            [CACHE / f"velo_arsenal_{y}.json" for y in T_VELO_SEASONS]
    return paths


def load_frozen_rows() -> list[dict]:
    if not FROZEN_ROWS.exists():
        raise GuardError(f"{_rel(FROZEN_ROWS)} is missing: run --freeze-grade-rows first")
    doc = json.loads(FROZEN_ROWS.read_text(encoding="utf-8"))
    rows = doc["rows"]
    for r in rows:
        guard_no_grade_grouping(r.keys())
    bad = [r for r in rows if int(r["snapshot_date"][:4]) in RESERVED_LV]
    if bad:
        raise GuardError("frozen grade rows carry an R-LV grade point")
    guard_debut_years([int(r["debut_date"][:4]) for r in rows])
    return rows


def real_mde_only(args) -> dict:
    """T.10 on FIT rows only: no HOLDOUT row and no 2026 line is loaded."""
    grade_rows = load_frozen_rows()
    hit = load_statsapi("hitting", T_FIT_SEASONS)
    pit = load_statsapi("pitching", T_FIT_SEASONS)
    velo = load_velo(T_VELO_SEASONS)
    for d in (hit, pit):
        guard_fit_seasons([s for by in d.values() for s in by], T_FIT_SEASONS)
    guard_fit_seasons(velo.keys(), T_VELO_SEASONS)
    lines = t_season_lines(hit, pit, velo, T_FIT_SEASONS)
    assert all(s != T_HOLDOUT_SEASON for side in lines.values() for (_p, s) in side), "a 2026 line was loaded"
    cells = {}
    for cell in T_PRIMARY:
        seasons = T_VELO_SEASONS if cell["stat"] == "velo" else T_FIT_SEASONS
        rows = t_cell_rows(cell, grade_rows, lines, seasons)
        cells[cell["cell"]] = t_mde_cell(cell, rows, lines, seasons)
        cells[cell["cell"]]["n_players"] = len(rows)
    velo26 = CACHE / "velo_arsenal_2026.json"
    rec = {"generated_at": _now(), "gate": GATE_DOC, "part": "T.10", "mode": "mde-only",
           "fit_seasons": list(T_FIT_SEASONS), "velo_fit_seasons": list(T_VELO_SEASONS),
           "holdout_loaded": False, "frozen_rows_sha256": sha256_of(FROZEN_ROWS),
           "frozen_rows_n": len(grade_rows), "inputs_sha256": _inputs_sha(_t_fit_inputs()),
           "velo_arsenal_2026": {"present": velo26.exists(), "sha256": sha256_of(velo26),
                                 "mtime": (datetime.fromtimestamp(velo26.stat().st_mtime, timezone.utc).isoformat()
                                           if velo26.exists() else None)},
           "cells": cells}
    return rec


def real_look_t(args) -> dict:
    _assert_no_look_today_conflict("T")
    if not gate_sha_ok(args.registration, status_part="Part T"):
        raise GuardError("--registration must name a committed ancestor carrying Part T with its REGISTERED status line")
    if not isinstance(args.mde, str) or _git("cat-file", "-e", f"{args.mde}^{{commit}}") is None:
        raise GuardError("--mde must name the committed T.10 amendment")
    mde_text = _git("show", f"{args.mde}:./{GATE_DOC}") or ""
    if "T.10" not in mde_text or "PENDING: written by TL_4_TOOL_LAB_BUILD (`--look T --mde-only`)" in mde_text:
        raise GuardError("the --mde commit does not carry the T.10 amendment")
    if not MDE_FOLDS.exists():
        raise GuardError("data/_labs/tool_tables_rederived/mde95_folds.json is missing")
    mde = json.loads(MDE_FOLDS.read_text(encoding="utf-8"))["cells"]
    grade_rows = load_frozen_rows()
    hit = load_statsapi("hitting", T_FIT_SEASONS)
    pit = load_statsapi("pitching", T_FIT_SEASONS)
    velo = load_velo(T_VELO_SEASONS)
    lines_fit = t_season_lines(hit, pit, velo, T_FIT_SEASONS)
    for d in (hit, pit):
        guard_fit_seasons([s for by in d.values() for s in by], T_FIT_SEASONS)
    hit26 = load_statsapi("hitting", (T_HOLDOUT_SEASON,))
    pit26 = load_statsapi("pitching", (T_HOLDOUT_SEASON,))
    velo26 = load_velo((T_HOLDOUT_SEASON,))
    lines_hold = t_season_lines(hit26, pit26, velo26, (T_HOLDOUT_SEASON,))
    inputs = _t_fit_inputs() + [CACHE / f"fa_statsapi_hitting_{T_HOLDOUT_SEASON}.json",
                                CACHE / f"fa_statsapi_pitching_{T_HOLDOUT_SEASON}.json",
                                CACHE / f"velo_arsenal_{T_HOLDOUT_SEASON}.json", FROZEN_ROWS]
    sha_start = _inputs_sha(inputs)
    res = run_look_t(grade_rows, lines_fit, lines_hold, mde95=mde, boot=args.boot or T_BOOT)
    rec = {"generated_at": _now(), "look": "T", "spent": True, "gate": GATE_DOC,
           "registration_sha": args.registration, "mde_sha": args.mde,
           "inputs_sha256_start": sha_start, "inputs_sha256_end": _inputs_sha(inputs), "result": res}
    rec["record_text"] = render_record("T", res, {"date": date.today().isoformat()})
    return rec


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--look", choices=("P", "W", "T"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mde-only", action="store_true")
    ap.add_argument("--k-m", action="store_true")
    ap.add_argument("--freeze-grade-rows", action="store_true")
    ap.add_argument("--gate-sha")
    ap.add_argument("--rlv-record")
    ap.add_argument("--registration")
    ap.add_argument("--mde")
    ap.add_argument("--out-dir")
    ap.add_argument("--boot", type=int)
    ap.add_argument("--perm", type=int)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir) if args.out_dir else LABS
    if args.k_m:
        km = measure_k_m()
        K_M_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        K_M_RECEIPT.write_text(json.dumps(km, indent=1), encoding="utf-8")
        print(render_k_m_table(km))
        print("seasons on disk:", km["seasons_on_disk"])
        print("wrote", _rel(K_M_RECEIPT))
        return 0
    if args.freeze_grade_rows:
        doc = freeze_grade_rows()
        FROZEN_ROWS.parent.mkdir(parents=True, exist_ok=True)
        FROZEN_ROWS.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print("frozen grade rows:", doc["n_rows"], "dropped:", doc["dropped"])
        print("wrote", _rel(FROZEN_ROWS), "sha256", sha256_of(FROZEN_ROWS))
        return 0
    if not args.look:
        ap.error("--look P|W|T, --k-m or --freeze-grade-rows is required")
    if args.dry_run:
        rec = dry_run(args.look, out_dir / "dryrun", boot=args.boot or 40, perm=args.perm or 30)
        print(rec["record_text"])
        print("dry run complete; wrote", rec["path"])
        return 0
    if args.look == "T" and args.mde_only:
        rec = real_mde_only(args)
        MDE_FOLDS.parent.mkdir(parents=True, exist_ok=True)
        MDE_FOLDS.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        for k, c in rec["cells"].items():
            print(f"{k}: MDE95 {c.get('mde95')} folds {c.get('folds_used')} rows {c.get('fold_rows')} {c.get('note', '')}")
        print("wrote", _rel(MDE_FOLDS), "sha256", sha256_of(MDE_FOLDS))
        return 0
    # a real look: guards first, then the whole run; an exception after scoring began
    # records the look as spent and writes OWNER_QUESTION.md (gate Part 5 clause 5)
    art = ARTIFACT[args.look]
    runner = {"P": real_look_p, "W": real_look_w, "T": real_look_t}[args.look]
    try:
        rec = runner(args)
    except GuardError:
        raise
    except Exception:
        tb = traceback.format_exc()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "OWNER_QUESTION.md").write_text(
            f"# Look {args.look} stopped after scoring began\n\n```\n{tb}\n```\n", encoding="utf-8")
        art.write_text(json.dumps({"generated_at": _now(), "look": args.look, "spent": True,
                                   "stopped": True, "traceback": tb}, indent=1), encoding="utf-8")
        raise
    art.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(rec["record_text"])
    print("wrote", _rel(art), "sha256", sha256_of(art))
    return 0


if __name__ == "__main__":
    sys.exit(main())

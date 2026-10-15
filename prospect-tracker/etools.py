# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools: stat sub-drivers for tool grades, the eTool, accuracy weighting, and the
P/PA, P/IP, P/BF and PAR read (owner asks of 2026-10-15, decision EW3-15), built to
docs/tools-2026-10/ETOOLS_GATE.md, which was committed alone before this module
computed anything.

WHAT IT ASKS. For each tool grade (hit, game power, raw power, speed, field, throw,
pitch selection, bat control, fastball, command, slider, curveball, changeup): which
MiLB statistics, dated before the board, add to the CONSENSUS TOOL GRADE at predicting
the tool's own outcome stat (the FanGraphs framework: hit to K%, power to ISO, and so
on)? Every test is the gate's Part 4 statistic: the within-board-year Spearman of an
out-of-fold [1, consensus tool grade, candidate] model minus that of the consensus tool
grade alone, folds = board years with the test year's players removed from training,
player-clustered bootstrap B 2000, BH q within each (tool, label), and a permuted floor.

TWO LABELS, ALWAYS SIDE BY SIDE. L_MLB, the framework outcome among debuts (the first
three MLB seasons after the board year, first MLB season 2024 or earlier); L_UM, the
X1-translated upper-minors outcome over seasons Y to Y + 2 capped at 2024, which exists
for players who never reached the majors (the survivorship check).

THE eTool. eTool = consensus tool grade + sum_j c_j u_j, u_j the residual of admitted
sub-driver j given the consensus grade, c fit on the grade scale (each label through its
own TIP table) by player-disjoint leave one board year out. It passes only when it
beats the consensus tool grade on BOTH labels (one-sided 95% lower bound above 0).

DARK. ETOOLS_ON is False: the preview builder writes .cache/etools/preview.json only.
Nothing served imports this module; no served number moves.

BANS. Development board years only (2011 to 2019, 2022 to 2024); no R-LV list read, no
R-VM outcome read; no grouping, key, filter or weight by consensus FV or any source's
FV (docs/PROSPECT_ANCHOR_GATE.md); never backtest.run_backtest, run_monthly or
build_site; no network request.

Run:  python etools.py --check                     (rows and coverage; no statistic)
      python etools.py --dry-run                   (the reporting path on fixtures)
      python etools.py --run --gate-sha SHA        (the one look)
      python etools.py --preview                   (the dark preview from the spent look)
      python etools.py --review-reads --amend-sha SHA   (amendment 1, run once)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

# ---------------------------------------------------------------------------
# flag, paths, constants (the gate's numbers, by section)
# ---------------------------------------------------------------------------
ETOOLS_ON = False

DATA = ROOT / "data"
CACHE = ROOT / ".cache"
LAB_DIR = DATA / "_labs" / "etools"
ATLAS_PATH = LAB_DIR / "etools_atlas.json"
EVAL_PATH = LAB_DIR / "etools_eval.json"
PREVIEW_PATH = CACHE / "etools" / "preview.json"
SERVED_PATH = DATA / "etools.json"
GATE_DOC = "docs/tools-2026-10/ETOOLS_GATE.md"
TOOL = "etools.py"
ITEM = "ETOOLS"

DEV_YEARS: tuple[int, ...] = tuple(range(2011, 2020)) + (2022, 2023, 2024)   # 1.1
RESERVED_BOARD_YEARS = (2020, 2021)
SOURCES = ("fangraphs", "mlb_pipeline", "baseballamerica")                  # 1.2
WEIGHT_SOURCES = ("fangraphs", "mlb_pipeline")                              # 6.1
MAX_DEBUT_YEAR = 2024                                                       # 2.1
LAST_MLB_SEASON = 2026
LAST_UM_SEASON = 2024                                                       # 2.2
UM_LEVELS = ("AA", "AAA")
TRACK_LEVELS = ("AAA", "A")
SEED = 20261023                                                             # 4.2
PERM_SEED = 20261024                                                        # 4.3
B = 2000
B_CHUNK = 500
PERM = 200
Q_ADMIT = 0.10                                                              # 4.4
R_CAP = 0.6
MAX_SUB = 3
POOL_MIN = 100                                                              # 2.3
THIN = 20
MIN_YEARS = 3
CELL_MIN = 100                                                              # 4.5
TIP_BIN_MIN = 15                                                            # 5.1
BAND_Z = 1.2816
MARCEL = {1: 5.0, 2: 4.0, 3: 3.0}                                           # 3.3
NORM_MIN_LINES = 30
R_MIN = 0.05
FIELD_K = 50.0
PITCHER_TOKENS = {"P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP", "RHSP", "LHSP", "RHRP", "LHRP"}
LEVEL_CELL = {"DSL": "low", "CPX": "low", "A-": "low", "A": "low", "A+": "A+", "AA": "AA", "AAA": "AAA"}
LEVEL_ORDER = {"DSL": 0, "CPX": 1, "A-": 2, "A": 3, "A+": 4, "AA": 5, "AAA": 6}
POS_GROUP = {"C": "C", "SS": "SS", "CF": "CF", "2B": "IF", "3B": "IF", "IF": "IF",
             "INF": "IF", "UTIL": "IF", "UT": "IF", "MI": "IF", "CI": "IF",
             "LF": "COF", "RF": "COF", "OF": "COF", "1B": "1B/DH", "DH": "1B/DH"}
SURVIVORSHIP = ("L_MLB is accuracy AMONG DEBUTS: only players who reached the majors have "
                "a realized MLB quantity. L_UM (translated upper-minors outcomes, seasons Y to "
                "Y + 2 capped at 2024) does not require a debut, but it does require reaching "
                "Double-A or Triple-A for 300 PA (150 BF), itself a promotion outcome: among "
                "hitter rows with no debut by 2024 only about 37% carry it, and non-debuts who "
                "stalled below Double-A are on neither label. L_UM is accuracy AMONG PROMOTED "
                "players (amendment 1, A1).")
REVIEW_DOC = "docs/tools-2026-10/ETOOLS_AMENDMENT_1.md"
REVIEW_PATH = LAB_DIR / "etools_review_reads.json"
#: tools whose eTool was evaluated at the look and that carry an L_UM (amendment A1.2)
REVIEW_TOOLS = ("hit", "game_pwr", "raw_pwr", "speed", "pitch_sel", "bat_ctrl", "fb", "cmd")

LABELS = ("mlb", "um")

#: The per-tool specification (gate 2.1, 2.2, 3.5): side, label stats, display key.
TOOLS: dict[str, dict] = {
    "hit": {"side": "hit", "key": "eHIT", "mlb": "k_pct (negated)", "um": "translated K% (negated)",
            "cands": ["k_rw", "babip_rw", "woba_rw", "age_rel_level", "pbp_contact", "pbp_swstr",
                      "pbp_two_strike_contact", "trk_zone_contact", "trk_whiff", "ppa_raw", "ppa_par"]},
    "game_pwr": {"side": "hit", "key": "ePOW", "mlb": "ISO", "um": "translated ISO",
                 "cands": ["iso_rw", "woba_rw", "age_rel_level", "bb_fb", "bb_pull", "bb_hard",
                           "trk_barrel", "trk_ev_p90"]},
    "raw_pwr": {"side": "hit", "key": "eRAW", "mlb": "average exit velocity", "um": "tracked EV mean",
                "cands": ["iso_rw", "bb_hard", "trk_ev_p90", "trk_ev_max", "trk_hard_hit", "fg_avg_ev",
                          "fg_max_ev"]},
    "speed": {"side": "hit", "key": "eSPD", "mlb": "sprint speed", "um": "SB per PA over level-season mean",
              "cands": ["sb_rel", "tri_rel", "age_rel_level"]},
    "field": {"side": "hit", "key": "eFLD", "mlb": "OAA per 1,000 innings", "um": None,
              "cands": ["prem_share", "age_rel_level"]},
    "throw": {"side": "hit", "key": "eARM", "mlb": "arm z (IF/OF)", "um": None,
              "cands": ["arm_share"]},
    "pitch_sel": {"side": "hit", "key": "eSEL", "mlb": "chase % 2026 (negated)", "um": "tracked chase (negated)",
                  "cands": ["bb_rw", "k_rw", "pbp_swing", "pbp_fstrike_taken", "trk_chase", "ppa_raw",
                            "ppa_par"]},
    "bat_ctrl": {"side": "hit", "key": "eBAT", "mlb": "zone contact % 2026", "um": "tracked zone contact",
                 "cands": ["k_rw", "pbp_contact", "pbp_two_strike_contact", "trk_zone_contact", "ppa_raw",
                           "ppa_par"]},
    "fb": {"side": "pit", "key": "eFB", "mlb": "pitcher K%", "um": "translated pitcher K%",
           "cands": ["k_rw", "kbb_rw", "age_rel_level", "pbp_swstr", "pbp_csw", "fg_sits", "fg_tops",
                     "fg_rpm_fb", "trk_fb_velo_mean", "trk_fb_velo_p95", "trk_fb_ivb", "trk_whiff_fb",
                     "pbf_raw", "pbf_par", "pip_raw", "pip_par"]},
    "cmd": {"side": "pit", "key": "eCMD", "mlb": "pitcher BB% (negated)", "um": "translated pitcher BB% (negated)",
            "cands": ["bb_rw", "pbp_ball_rate", "pbp_fstrike", "pbp_cstr", "trk_zone", "pbf_raw", "pbf_par",
                      "pip_raw", "pip_par"]},
    "sl": {"side": "pit", "key": "eSL", "mlb": "whiff % on SL/ST", "um": "tracked breaking whiff",
           "cands": ["k_rw", "pbp_swstr", "fg_rpm_break", "trk_whiff_br", "trk_chase", "pbf_raw", "pbf_par",
                     "pip_raw", "pip_par"]},
    "cb": {"side": "pit", "key": "eCB", "mlb": "whiff % on CU/KC/SV", "um": "tracked breaking whiff",
           "cands": ["k_rw", "pbp_swstr", "fg_rpm_break", "trk_whiff_br", "trk_chase", "pbf_raw", "pbf_par",
                     "pip_raw", "pip_par"]},
    "ch": {"side": "pit", "key": "eCH", "mlb": "whiff % on CH/FS", "um": "tracked offspeed whiff",
           "cands": ["k_rw", "pbp_swstr", "trk_whiff_os", "trk_chase", "pbf_raw", "pbf_par", "pip_raw",
                     "pip_par"]},
}
ARSENAL_TYPES = {"sl": ("SL", "ST"), "cb": ("CU", "KC", "SV", "CS"), "ch": ("CH", "FS", "FO", "SC")}
X1_HIT = ("k_rw", "bb_rw", "iso_rw", "babip_rw", "woba_rw", "age_rel_level")
X1_PIT = ("k_rw", "bb_rw", "hr9_rw", "gb_rw", "kbb_rw", "age_rel_level")
FG_EXTRAS = {"fg_sits": "sits", "fg_tops": "tops", "fg_rpm_fb": "rpm_fb", "fg_rpm_break": "rpm_break",
             "fg_avg_ev": "avg_ev", "fg_max_ev": "max_ev"}
#: Part P metrics on the first atlas's rows.
PR_METRICS = {"hit": ("ppa_raw_hit", "ppa_par_hit"),
              "pit": ("pbf_raw_pit", "pbf_par_pit", "pip_raw_pit", "pip_par_pit")}
PR_LABELS = (("reach3", "clean"), ("reach5", "clean"), ("w3", "all"), ("l6", "all"))


class GuardError(RuntimeError):
    """A gate section 8 guard failed."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _f(v):
    try:
        if v is None or v == "" or v == "NA":
            return None
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _r(v, nd=4):
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def sha256_of(path: Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def db_path() -> Path:
    """prospects.db: this checkout's, else the main checkout's (a lane worktree carries
    no copy of the gitignored database). Opened read-only, always."""
    p = ROOT / "prospects.db"
    if p.exists():
        return p
    common = _git("rev-parse", "--git-common-dir")
    if common:
        c = Path(common.strip())
        if not c.is_absolute():
            c = (ROOT / c).resolve()
        cand = c.parent / ROOT.name / "prospects.db"
        if cand.exists():
            return cand
    return p


def parse_mph(v) -> float | None:
    """'94-97' -> 95.5; '98' -> 98.0; numbers pass through."""
    x = _f(v)
    if x is not None:
        return x
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(v or ""))]
    nums = [n for n in nums if 50 <= n <= 4000]
    if not nums:
        return None
    return sum(nums[:2]) / len(nums[:2])


def round_half(v):
    return None if v is None else round(float(v) * 2) / 2.0


def display_grade(v) -> int | None:
    """Grades round UP (the owner's rule) to the next 5."""
    if v is None:
        return None
    return int(min(80, max(20, 5 * math.ceil(float(v) / 5.0 - 1e-9))))


def position_token(pos) -> str:
    return str(pos or "").upper().replace("-", "/").split("/")[0].strip()


def is_pitcher(pos) -> bool:
    return position_token(pos) in PITCHER_TOKENS


# ---------------------------------------------------------------------------
# guards (gate section 8)
# ---------------------------------------------------------------------------
def guard_years(years) -> None:
    bad = sorted({int(y) for y in years if int(y) not in DEV_YEARS})
    if bad:
        raise GuardError(f"board years {bad} are outside the development list {DEV_YEARS}")


def guard_no_fv(keys) -> None:
    bad = [k for k in keys if re.search(r"(^|_)fv($|_)", str(k).lower())]
    if bad:
        raise GuardError(f"grouping keys {bad} name a future-value grade cell")


def gate_sha_ok(sha: str | None, doc: str = GATE_DOC) -> bool:
    if not isinstance(sha, str) or not re.match(r"^[0-9a-f]{7,40}$", sha):
        return False
    if _git("cat-file", "-e", f"{sha}^{{commit}}") is None:
        return False
    text = _git("show", f"{sha}:./{doc}")
    if text is None:
        return False
    status = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("Registration status:")]
    if status != ["Registration status: REGISTERED"]:
        return False
    return _git("merge-base", "--is-ancestor", sha, "HEAD") is not None


def look_spent() -> str | None:
    if EVAL_PATH.exists():
        try:
            d = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        except ValueError:
            return f"{EVAL_PATH} is unparseable"
        if d.get("spent"):
            return f"{EVAL_PATH} carries a spent marker ({d.get('spent_at')})"
    return None


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def _ranks(x: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    return rankdata(x)


def within_rho(pred, y, year, W=None, min_rows: int = THIN):
    """n-weighted mean of within-board-year Spearman over years with min_rows or more
    rows; with W (B x n draw counts) the ranks stay fixed and each year's weighted
    Pearson of the ranks is combined by its drawn size (efv5_atlas.within_rho)."""
    pred, y, year = np.asarray(pred, float), np.asarray(y, float), np.asarray(year)
    yrs, cnt = np.unique(year, return_counts=True)
    keep = yrs[cnt >= min_rows]
    if W is None:
        tot = n = 0.0
        for s in keep:
            m = year == s
            rp, ry = _ranks(pred[m]), _ranks(y[m])
            if rp.std() <= 0 or ry.std() <= 0:
                continue
            tot += float(np.corrcoef(rp, ry)[0, 1]) * m.sum()
            n += m.sum()
        return tot / n if n else None
    Bn = W.shape[0]
    tot, n = np.zeros(Bn), np.zeros(Bn)
    for s in keep:
        m = year == s
        rp, ry = _ranks(pred[m]), _ranks(y[m])
        Wg = W[:, m]
        sw = Wg.sum(axis=1)
        ok = sw > 0
        d = np.where(ok, sw, 1.0)
        mx, my = (Wg @ rp) / d, (Wg @ ry) / d
        sxx = (Wg @ (rp * rp)) / d - mx * mx
        syy = (Wg @ (ry * ry)) / d - my * my
        sxy = (Wg @ (rp * ry)) / d - mx * my
        den = np.sqrt(np.clip(sxx, 0, None) * np.clip(syy, 0, None))
        good = ok & (den > 1e-12)
        r = np.where(good, sxy / np.where(den > 0, den, 1.0), 0.0)
        tot += np.where(good, r * sw, 0.0)
        n += np.where(good, sw, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = tot / n
    out[n <= 0] = np.nan
    return out


def cluster_weights(pid, Bn: int, seed: int) -> np.ndarray:
    players, inv = np.unique(np.asarray(pid), return_inverse=True)
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(players.size, np.full(players.size, 1.0 / players.size), size=Bn)
    return counts[:, inv].astype(np.float64)


def paired_draws(a, b, y, year, pid, *, Bn: int = B, seed: int = SEED) -> np.ndarray:
    """Bootstrap draws of rho_w(a) - rho_w(b), players resampled, in chunks."""
    out = []
    k = 0
    left = int(Bn)
    while left > 0:
        nb = min(B_CHUNK, left)
        W = cluster_weights(pid, nb, seed + k)
        out.append(within_rho(a, y, year, W) - within_rho(b, y, year, W))
        left -= nb
        k += 1
    return np.concatenate(out) if out else np.array([])


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def summarize_draws(d: float | None, draws: np.ndarray) -> dict:
    dd = draws[np.isfinite(draws)] if draws is not None else np.array([])
    if d is None or dd.size < 50:
        return {"d": _r(d), "lb95": None, "ci95": None, "sd": None, "p": None, "draws": int(dd.size)}
    sd = float(dd.std(ddof=1))
    p = (1.0 - _phi(d / sd)) if sd > 0 else (0.0 if d > 0 else 1.0)
    lo, hi = np.percentile(dd, [2.5, 97.5])
    return {"d": _r(d), "lb95": _r(float(np.percentile(dd, 5.0))),
            "ci95": [_r(float(lo)), _r(float(hi))], "sd": _r(sd, 5), "p": _r(p, 6),
            "draws": int(dd.size)}


def bh_q(ps: list) -> list:
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = [None] * len(ps)
    if not idx:
        return out
    m = len(idx)
    order = sorted(idx, key=lambda i: ps[i])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, ps[i] * m / rank)
        q[rank - 1] = prev
    for rank, i in enumerate(order):
        out[i] = round(float(min(1.0, q[rank])), 6)
    return out


def computable(year, pid) -> bool:
    year = np.asarray(year)
    if np.unique(np.asarray(pid)).size < POOL_MIN:
        return False
    _yrs, cnt = np.unique(year, return_counts=True)
    return int((cnt >= THIN).sum()) >= MIN_YEARS


def fold_train_mask(year, pid, Y) -> np.ndarray:
    """Training rows for test board year Y: other years, Y's players removed."""
    te = year == Y
    return (~te) & (~np.isin(pid, np.unique(pid[te])))


def loyo_oof(cols: list, y, year, pid) -> np.ndarray:
    """Out-of-fold OLS on [1, cols], folds = board years, player-disjoint."""
    n = len(y)
    X = np.column_stack([np.ones(n)] + [np.asarray(c, float) for c in cols])
    out = np.full(n, np.nan)
    for Y in np.unique(year):
        te = year == Y
        tr = fold_train_mask(year, pid, Y)
        if tr.sum() < X.shape[1] + 10:
            continue
        b, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        out[te] = X[te] @ b
    return out


# --- the TIP table on the grade scale (gate 5.1, gate TIP 1.2) ----------------
def pava_increasing(vals, w):
    vals = [float(v) for v in vals]
    w = [float(x) for x in w]
    blocks = [[v, wt, 1] for v, wt in zip(vals, w)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            v0, w0, c0 = blocks[i]
            v1, w1, c1 = blocks[i + 1]
            blocks[i] = [(v0 * w0 + v1 * w1) / (w0 + w1), w0 + w1, c0 + c1]
            del blocks[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    out = []
    for v, _w, c in blocks:
        out.extend([v] * c)
    return out


def fit_tip(g, y) -> dict | None:
    """{"grade": [...], "stat": [...]} increasing in the oriented stat, or None."""
    g, y = np.asarray(g, float), np.asarray(y, float)
    bins = np.round(g / 5.0) * 5.0
    pts = []
    for b in np.unique(bins):
        m = bins == b
        if m.sum() < TIP_BIN_MIN:
            continue
        pts.append((float(g[m].mean()), float(np.median(y[m])), int(m.sum())))
    if len(pts) < 2:
        return None
    pts.sort()
    fitted = pava_increasing([p[1] for p in pts], [p[2] for p in pts])
    return {"grade": [p[0] for p in pts], "stat": fitted}


def tip_inverse(tip: dict, y) -> np.ndarray:
    """Grade at the realized stat: linear between the table's points, flat beyond;
    a flat run of the table maps to the mean grade of the run."""
    st = np.asarray(tip["stat"], float)
    gr = np.asarray(tip["grade"], float)
    us, inv = np.unique(st, return_inverse=True)
    ug = np.array([gr[inv == i].mean() for i in range(us.size)])
    y = np.asarray(y, float)
    if us.size == 1:
        return np.full(y.shape, ug[0])
    return np.interp(y, us, ug)


# ---------------------------------------------------------------------------
# the frame object (one tool): arrays over its (board year, player) rows
# ---------------------------------------------------------------------------
class ToolFrame:
    def __init__(self, tool: str, rows: list[dict]):
        self.tool = tool
        self.keys = [(r["year"], r["pid"]) for r in rows]
        self.n = len(rows)
        self.year = np.array([r["year"] for r in rows], dtype=np.int64)
        self.pid = np.array([r["pid"] for r in rows], dtype=np.int64)
        self.gc = np.array([r["gc"] for r in rows], dtype=np.float64)
        self.group = np.array([r.get("group") or "" for r in rows])
        self.level = np.array([r.get("level_cell") or "" for r in rows])
        self.band = np.array([r.get("band") or "" for r in rows])
        self.src = {s: np.array([np.nan if r["src"].get(s) is None else r["src"][s] for r in rows])
                    for s in SOURCES}
        names = TOOLS[tool]["cands"]
        self.cands = {c: np.array([np.nan if r["cands"].get(c) is None else r["cands"][c] for r in rows])
                      for c in names}
        self.y = {lb: np.array([np.nan if r["y"].get(lb) is None else r["y"][lb] for r in rows])
                  for lb in LABELS}
        #: debut by MAX_DEBUT_YEAR (first MLB season 2024 or earlier): amendment A1 only
        self.debut = np.array([r.get("mlb_first") is not None and int(r["mlb_first"]) <= MAX_DEBUT_YEAR
                               for r in rows], dtype=bool)


# ---------------------------------------------------------------------------
# the sub-driver test (gate 4.1 to 4.3)
# ---------------------------------------------------------------------------
def incr_test(gc, cand, y, year, pid, *, Bn: int = B, seed: int = SEED, perm: int = 0,
              perm_seed: int = PERM_SEED) -> dict | None:
    m = np.isfinite(gc) & np.isfinite(cand) & np.isfinite(y)
    if not computable(year[m], pid[m]):
        return {"computable": False, "n": int(m.sum()), "players": int(np.unique(pid[m]).size)}
    gc, cand, y, year, pid = gc[m], cand[m], y[m], year[m], pid[m]
    aug = loyo_oof([gc, cand], y, year, pid)
    k = np.isfinite(aug)
    gc, cand, y, year, pid, aug = gc[k], cand[k], y[k], year[k], pid[k], aug[k]
    if not computable(year, pid):
        return {"computable": False, "n": int(k.sum()), "players": int(np.unique(pid).size)}
    r_aug, r_gc = within_rho(aug, y, year), within_rho(gc, y, year)
    if r_aug is None or r_gc is None:
        return {"computable": False, "n": int(y.size), "players": int(np.unique(pid).size)}
    d = r_aug - r_gc
    draws = paired_draws(aug, gc, y, year, pid, Bn=Bn, seed=seed)
    out = {"computable": True, "n": int(y.size), "players": int(np.unique(pid).size),
           "years": sorted({int(v) for v in year}),
           "rho_consensus": _r(r_gc), "rho_candidate_alone": _r(within_rho(cand, y, year)),
           "rho_augmented": _r(r_aug), "corr_with_consensus": _r(within_rho(cand, gc, year))}
    out.update(summarize_draws(d, draws))
    if perm:
        rng = np.random.default_rng(perm_seed)
        ds = []
        for _ in range(int(perm)):
            c2 = cand.copy()
            for Y in np.unique(year):
                mm = np.flatnonzero(year == Y)
                c2[mm] = c2[rng.permutation(mm)]
            a2 = loyo_oof([gc, c2], y, year, pid)
            ok = np.isfinite(a2)
            r2 = within_rho(a2[ok], y[ok], year[ok])
            r0 = within_rho(gc[ok], y[ok], year[ok])
            if r2 is not None and r0 is not None:
                ds.append(r2 - r0)
        out["perm_floor95"] = _r(float(np.percentile(ds, 95))) if ds else None
        out["perm_draws"] = len(ds)
    return out


def run_atlas(frames: dict, *, Bn: int = B, perm: int = PERM, cells: bool = True, log=print) -> list[dict]:
    """Every (tool, candidate, label) test on the pooled cell (with the permuted floor),
    plus the descriptive cells; BH q within (tool, label) on the pooled rows."""
    rows = []
    for tool, fr in frames.items():
        for lb in LABELS:
            if TOOLS[tool].get(lb) is None:
                continue
            fam = []
            for c in TOOLS[tool]["cands"]:
                t0 = time.time()
                res = incr_test(fr.gc, fr.cands[c], fr.y[lb], fr.year, fr.pid, Bn=Bn, perm=perm)
                row = {"tool": tool, "candidate": c, "label": lb, "cell": "pooled", "cell_value": "all"}
                row.update(res or {"computable": False})
                rows.append(row)
                fam.append(row)
                log(f"    {tool:9s} {lb:3s} {c:24s} n {row.get('n')} d {row.get('d')} lb {row.get('lb95')} "
                    f"floor {row.get('perm_floor95')} ({time.time() - t0:.1f} s)")
                if cells and row.get("computable"):
                    for cell, arr in (("group", fr.group), ("level", fr.level), ("age_band", fr.band)):
                        guard_no_fv([cell])
                        for v in sorted(set(arr.tolist()) - {""}):
                            mk = arr == v
                            if np.unique(fr.pid[mk & np.isfinite(fr.cands[c]) & np.isfinite(fr.y[lb])]).size < CELL_MIN:
                                continue
                            r2 = incr_test(fr.gc[mk], fr.cands[c][mk], fr.y[lb][mk], fr.year[mk], fr.pid[mk],
                                           Bn=Bn, perm=0)
                            if r2 and r2.get("computable"):
                                rr = {"tool": tool, "candidate": c, "label": lb, "cell": cell, "cell_value": v}
                                rr.update(r2)
                                rows.append(rr)
            qs = bh_q([r.get("p") if r.get("computable") else None for r in fam])
            for r, q in zip(fam, qs):
                r["q"] = q
    return rows


def admit(frames: dict, atlas_rows: list[dict]) -> dict:
    """Gate 4.4, per tool: {tool: {"admitted": [...], "considered": [...]}}."""
    pooled = {(r["tool"], r["candidate"], r["label"]): r for r in atlas_rows if r["cell"] == "pooled"}
    out = {}
    for tool, fr in frames.items():
        quals = []
        for c in TOOLS[tool]["cands"]:
            best = None
            for lb in LABELS:
                r = pooled.get((tool, c, lb))
                if not r or not r.get("computable") or r.get("q") is None:
                    continue
                ok1 = (r["q"] <= Q_ADMIT and (r.get("lb95") or -1) > 0
                       and r.get("perm_floor95") is not None and r["d"] > r["perm_floor95"])
                if not ok1:
                    continue
                other = [o for o in LABELS if o != lb]
                ok2 = True
                for o in other:
                    ro = pooled.get((tool, c, o))
                    if ro and ro.get("computable") and not (ro.get("d") is not None and ro["d"] > 0):
                        ok2 = False
                if ok2 and (best is None or (r["q"], -r["d"]) < (best[1]["q"], -best[1]["d"])):
                    best = (lb, r)
            if best is not None:
                quals.append((best[1]["q"], -best[1]["d"], c, best[0]))
        quals.sort()
        chosen, considered = [], []
        for q, negd, c, lb in quals:
            rec = {"candidate": c, "label": lb, "q": q, "d": -negd}
            if len(chosen) >= MAX_SUB:
                rec["dropped"] = "cap of 3"
                considered.append(rec)
                continue
            worst = 0.0
            for ch in chosen:
                a, b2 = fr.cands[c], fr.cands[ch["candidate"]]
                mm = np.isfinite(a) & np.isfinite(b2)
                if mm.sum() >= 30:
                    from scipy.stats import spearmanr
                    rr = spearmanr(a[mm], b2[mm]).correlation
                    worst = max(worst, abs(float(rr)) if rr == rr else 0.0)
            if worst > R_CAP:
                rec["dropped"] = f"|r| {worst:.3f} with a chosen sub-driver"
                considered.append(rec)
                continue
            chosen.append(rec)
            considered.append(rec)
        out[tool] = {"admitted": chosen, "qualifying": considered}
    return out


# ---------------------------------------------------------------------------
# the eTool (gate 5)
# ---------------------------------------------------------------------------
def etool_fit(gc, Z, ys: dict, train) -> dict | None:
    """One fit on the `train` rows: the TIP table per label, the zhat lines, c and sigma."""
    tips, yg = {}, {}
    for lb, y in ys.items():
        m = train & np.isfinite(y)
        if m.sum() < 60:
            continue
        tip = fit_tip(gc[m], y[m])
        if tip is None:
            continue
        tips[lb] = tip
        v = np.full(y.size, np.nan)
        f = np.isfinite(y)
        v[f] = tip_inverse(tip, y[f])
        yg[lb] = v
    if not yg:
        return None
    J = Z.shape[1]
    lines = []
    for j in range(J):
        m = train & np.isfinite(Z[:, j])
        if m.sum() < 30:
            lines.append((0.0, 0.0, False))
            continue
        X = np.column_stack([np.ones(m.sum()), gc[m]])
        b, *_ = np.linalg.lstsq(X, Z[m, j], rcond=None)
        lines.append((float(b[0]), float(b[1]), True))
    U = etool_residuals(gc, Z, lines)
    Xs, ts = [], []
    for lb, v in yg.items():
        m = train & np.isfinite(v)
        Xs.append(U[m])
        ts.append(v[m] - gc[m])
    X = np.vstack(Xs)
    t = np.concatenate(ts)
    if X.shape[0] < J + 10:
        return None
    c, *_ = np.linalg.lstsq(X, t, rcond=None)
    resid = t - X @ c
    return {"tips": tips, "lines": lines, "c": [float(v) for v in c],
            "sigma": float(resid.std(ddof=1)) if resid.size > 2 else None,
            "n_fit": int(X.shape[0])}


def etool_residuals(gc, Z, lines) -> np.ndarray:
    U = np.zeros(Z.shape)
    for j, (a, b, ok) in enumerate(lines):
        if not ok:
            continue
        f = np.isfinite(Z[:, j])
        U[f, j] = Z[f, j] - (a + b * gc[f])
    return U


def etool_apply(gc, Z, fit: dict) -> np.ndarray:
    U = etool_residuals(gc, Z, fit["lines"])
    return np.clip(gc + U @ np.asarray(fit["c"]), 20.0, 80.0)


def etool_oof(fr: ToolFrame, admitted: list[str]) -> tuple[np.ndarray, dict]:
    Z = np.column_stack([fr.cands[c] for c in admitted])
    pred = np.full(fr.n, np.nan)
    sig = {}
    for Y in np.unique(fr.year):
        tr = fold_train_mask(fr.year, fr.pid, Y)
        fit = etool_fit(fr.gc, Z, fr.y, tr)
        if fit is None:
            continue
        te = fr.year == Y
        pred[te] = etool_apply(fr.gc[te], Z[te], fit)
        sig[int(Y)] = _r(fit["sigma"])
    return pred, sig


def etool_eval(fr: ToolFrame, admitted: list[str], *, Bn: int = B) -> dict:
    out = {"tool": fr.tool, "key": TOOLS[fr.tool]["key"], "admitted": admitted, "labels": {}}
    if not admitted:
        out["verdict"] = "NO SUB-DRIVER"
        out["basis"] = "consensus"
        return out
    pred, sig = etool_oof(fr, admitted)
    out["fold_sigma"] = sig
    passes = []
    for lb in LABELS:
        if TOOLS[fr.tool].get(lb) is None:
            out["labels"][lb] = {"computable": False, "why": "no label for this tool (gate 2.2)"}
            passes.append(False)
            continue
        y = fr.y[lb]
        m = np.isfinite(y) & np.isfinite(pred) & np.isfinite(fr.gc)
        if not computable(fr.year[m], fr.pid[m]):
            out["labels"][lb] = {"computable": False, "n": int(m.sum())}
            passes.append(False)
            continue
        r_e, r_c = within_rho(pred[m], y[m], fr.year[m]), within_rho(fr.gc[m], y[m], fr.year[m])
        d = None if (r_e is None or r_c is None) else r_e - r_c
        draws = paired_draws(pred[m], fr.gc[m], y[m], fr.year[m], fr.pid[m], Bn=Bn)
        rec = {"computable": True, "n": int(m.sum()), "players": int(np.unique(fr.pid[m]).size),
               "rows_with_a_subdriver": int((m & np.any(np.isfinite(np.column_stack(
                   [fr.cands[c] for c in admitted])), axis=1)).sum()),
               "rho_consensus": _r(r_c), "rho_etool": _r(r_e)}
        rec.update(summarize_draws(d, draws))
        out["labels"][lb] = rec
        passes.append(bool(rec.get("lb95") is not None and rec["lb95"] > 0))
    out["verdict"] = "PASS" if all(passes) else "NOT PASS"
    if TOOLS[fr.tool].get("um") is None:
        out["verdict"] = "NOT PASS (no upper-minors label, gate 5.2)"
    out["basis"] = "etool" if out["verdict"] == "PASS" else "consensus"
    final = etool_fit(fr.gc, np.column_stack([fr.cands[c] for c in admitted]), fr.y,
                      np.ones(fr.n, dtype=bool))
    if final is not None:
        out["final_fit"] = {"lines": [[_r(a, 6), _r(b, 6), ok] for a, b, ok in final["lines"]],
                            "c": [_r(v, 6) for v in final["c"]], "sigma": _r(final["sigma"]),
                            "n_fit": final["n_fit"],
                            "tips": {lb: {"grade": [_r(v) for v in t["grade"]],
                                          "stat": [_r(v, 6) for v in t["stat"]]}
                                     for lb, t in final["tips"].items()}}
    return out


# ---------------------------------------------------------------------------
# accuracy weighting (gate 6)
# ---------------------------------------------------------------------------
def _derive(rows: list[dict], sources) -> dict:
    import ba_tool_grade_lab as BA2
    w, _n, _rho = BA2.derive_weights({0: rows}, list(sources), 0)
    return w


def group_weights(gr_rows: dict[str, list[dict]], sources) -> dict:
    allrows = [r for rs in gr_rows.values() for r in rs]
    pooled = _derive(allrows, sources)
    out = {"_pooled": pooled}
    for g, rs in gr_rows.items():
        if len({r["pid"] for r in rs}) < POOL_MIN:
            out[g] = dict(pooled, _pooled_fallback=True)
        else:
            out[g] = _derive(rs, sources)
    return out


def weighted_grade(vals: dict, w: dict) -> float | None:
    num = den = 0.0
    for s, v in vals.items():
        if v is None or not np.isfinite(v):
            continue
        ws = float(w.get(s, 1.0))
        num += ws * v
        den += ws
    return num / den if den else None


def weighting_arm(fr: ToolFrame, admitted: list[str], *, Bn: int = B) -> dict:
    lb_p = "mlb" if computable(fr.year[np.isfinite(fr.y["mlb"])], fr.pid[np.isfinite(fr.y["mlb"])]) else "um"
    yp = fr.y[lb_p]
    aw1 = np.full(fr.n, np.nan)
    aw2 = np.full(fr.n, np.nan)
    Z = np.column_stack([fr.cands[c] for c in admitted]) if admitted else None
    weights_by_fold = {}
    for Y in np.unique(fr.year):
        tr = fold_train_mask(fr.year, fr.pid, Y) & np.isfinite(yp)
        te = fr.year == Y
        gr_rows = defaultdict(list)
        for i in np.flatnonzero(tr):
            if all(np.isfinite(fr.src[s][i]) for s in WEIGHT_SOURCES):
                gr_rows[fr.group[i]].append({"pid": int(fr.pid[i]), "y": float(yp[i]),
                                             "grades": {s: float(fr.src[s][i]) for s in WEIGHT_SOURCES}})
        w1 = group_weights(gr_rows, WEIGHT_SOURCES)
        stat = np.full(fr.n, np.nan)
        w2 = None
        if Z is not None:
            tip = fit_tip(fr.gc[tr], yp[tr])
            anyc = np.any(np.isfinite(Z), axis=1)
            if tip is not None and (tr & anyc).sum() >= 60:
                mu = np.array([np.nanmean(Z[tr, j]) if np.isfinite(Z[tr, j]).any() else 0.0
                               for j in range(Z.shape[1])])
                Zf = np.where(np.isfinite(Z), Z, mu)
                X = np.column_stack([np.ones(fr.n), Zf])
                m = tr & anyc
                b, *_ = np.linalg.lstsq(X[m], tip_inverse(tip, yp[m]), rcond=None)
                stat[anyc] = np.clip(X[anyc] @ b, 20.0, 80.0)
                gr2 = defaultdict(list)
                for i in np.flatnonzero(tr & anyc):
                    if all(np.isfinite(fr.src[s][i]) for s in WEIGHT_SOURCES):
                        g = {s: float(fr.src[s][i]) for s in WEIGHT_SOURCES}
                        g["stat"] = float(stat[i])
                        gr2[fr.group[i]].append({"pid": int(fr.pid[i]), "y": float(yp[i]), "grades": g})
                w2 = group_weights(gr2, WEIGHT_SOURCES + ("stat",))
        weights_by_fold[int(Y)] = {"aw1": {g: {k: _r(v) for k, v in w.items() if not k.startswith("_")}
                                           for g, w in w1.items()},
                                   "aw2": None if w2 is None else
                                   {g: {k: _r(v) for k, v in w.items() if not k.startswith("_")}
                                    for g, w in w2.items()}}
        for i in np.flatnonzero(te):
            vals = {s: (float(fr.src[s][i]) if np.isfinite(fr.src[s][i]) else None) for s in SOURCES}
            wg = w1.get(fr.group[i], w1["_pooled"])
            aw1[i] = weighted_grade(vals, wg)
            if w2 is not None and np.isfinite(stat[i]):
                vals2 = dict(vals, stat=float(stat[i]))
                aw2[i] = weighted_grade(vals2, w2.get(fr.group[i], w2["_pooled"]))
            else:
                aw2[i] = aw1[i]
    out = {"tool": fr.tool, "weight_label": lb_p, "arms": {}, "weights_by_fold": weights_by_fold}
    for arm, pred in (("AW1_outlets_by_group", aw1), ("AW2_outlets_plus_stat", aw2)):
        out["arms"][arm] = {}
        oks = []
        for lb in LABELS:
            if TOOLS[fr.tool].get(lb) is None:
                continue
            y = fr.y[lb]
            m = np.isfinite(y) & np.isfinite(pred) & np.isfinite(fr.gc)
            if not computable(fr.year[m], fr.pid[m]):
                out["arms"][arm][lb] = {"computable": False}
                oks.append(False)
                continue
            r_a, r_c = within_rho(pred[m], y[m], fr.year[m]), within_rho(fr.gc[m], y[m], fr.year[m])
            d = None if (r_a is None or r_c is None) else r_a - r_c
            draws = paired_draws(pred[m], fr.gc[m], y[m], fr.year[m], fr.pid[m], Bn=Bn)
            rec = {"computable": True, "n": int(m.sum()), "rho_consensus": _r(r_c), "rho_arm": _r(r_a)}
            rec.update(summarize_draws(d, draws))
            out["arms"][arm][lb] = rec
            oks.append(bool(rec.get("lb95") is not None and rec["lb95"] > 0))
        out["arms"][arm]["verdict"] = "BEATS CONSENSUS" if (oks and all(oks) and len(oks) == 2) else "NULL"
    if not admitted:
        out["arms"]["AW2_outlets_plus_stat"]["note"] = "no admitted sub-driver: AW2 equals AW1"
    return out


# ---------------------------------------------------------------------------
# amendment 1 (docs/tools-2026-10/ETOOLS_AMENDMENT_1.md): the review reads
# ---------------------------------------------------------------------------
def paired_d(a, b, y, year, pid, *, Bn: int = B, seed: int = SEED) -> dict:
    """rho_w(a) - rho_w(b) over the rows where a, b and y are all finite, with the gate
    4.2 interval; NOT COMPUTABLE under the gate 2.3 rule."""
    a, b, y = np.asarray(a, float), np.asarray(b, float), np.asarray(y, float)
    m = np.isfinite(a) & np.isfinite(b) & np.isfinite(y)
    if not computable(year[m], pid[m]):
        return {"computable": False, "n": int(m.sum()), "players": int(np.unique(pid[m]).size)}
    r_a, r_b = within_rho(a[m], y[m], year[m]), within_rho(b[m], y[m], year[m])
    if r_a is None or r_b is None:
        return {"computable": False, "n": int(m.sum()), "players": int(np.unique(pid[m]).size)}
    rec = {"computable": True, "n": int(m.sum()), "players": int(np.unique(pid[m]).size),
           "rho_a": _r(r_a), "rho_b": _r(r_b)}
    if Bn:
        rec.update(summarize_draws(r_a - r_b, paired_draws(a[m], b[m], y[m], year[m], pid[m], Bn=Bn,
                                                           seed=seed)))
    else:
        rec["d"] = _r(r_a - r_b)
    return rec


def promotion_counts(fr: ToolFrame) -> dict:
    """A1.1: the frame rows split by L_UM present or absent and debut by 2024 or not."""
    um, deb = np.isfinite(fr.y["um"]), fr.debut
    nd = int((~deb).sum())
    return {"rows": fr.n, "um_and_debut": int((um & deb).sum()), "um_no_debut": int((um & ~deb).sum()),
            "no_um_no_debut": int((~um & ~deb).sum()), "no_um_debut": int((~um & deb).sum()),
            "share_of_non_debuts_with_um": _r((um & ~deb).sum() / nd) if nd else None,
            "share_of_um_that_debuted": _r((um & deb).sum() / um.sum()) if um.sum() else None}


def nondebut_read(fr: ToolFrame, admitted: list[str], *, Bn: int = B, pred=None) -> dict:
    """A1.2: d_E on L_UM pooled (the look's figure, reproduced), over the rows with no
    debut by 2024, and over the rows with one. A1.3 labels a non-debut lower bound at or
    below 0 (or a pool that is not computable) PROMOTION-DEPENDENT."""
    if pred is None:
        pred, _sig = etool_oof(fr, admitted)
    y = fr.y["um"]
    out = {"tool": fr.tool, "admitted": list(admitted)}
    for name, mask in (("pooled", np.ones(fr.n, dtype=bool)), ("non_debut", ~fr.debut), ("debut", fr.debut)):
        yy = np.where(mask, y, np.nan)
        out[name] = paired_d(pred, fr.gc, yy, fr.year, fr.pid, Bn=Bn)
    nd = out["non_debut"]
    out["promotion_dependent"] = not (nd.get("computable") and nd.get("lb95") is not None and nd["lb95"] > 0)
    return out


def margin_read(fr: ToolFrame, admitted: list[str], *, Bn: int = B) -> dict:
    """A2.1: for each admitted sub-driver j, the eTool on S against the eTool on S without
    j (what j adds given the others), and the reduced eTool against consensus, on both
    labels. A2.2 labels j NO ADDED EFFECT when its lower bound is not above 0 on both."""
    full, _ = etool_oof(fr, admitted)
    out = {"tool": fr.tool, "admitted": list(admitted), "subdrivers": {}}
    for j in admitted:
        rest = [c for c in admitted if c != j]
        red, _ = etool_oof(fr, rest)
        rec = {"without": rest, "labels": {}}
        adds = []
        for lb in LABELS:
            if TOOLS[fr.tool].get(lb) is None:
                continue
            y = fr.y[lb]
            g = paired_d(full, red, y, fr.year, fr.pid, Bn=Bn)
            rc = paired_d(red, fr.gc, y, fr.year, fr.pid, Bn=Bn)
            rec["labels"][lb] = {"given_others": g, "reduced_vs_consensus": rc}
            adds.append(bool(g.get("computable") and g.get("lb95") is not None and g["lb95"] > 0))
        rec["no_added_effect"] = not any(adds)
        out["subdrivers"][j] = rec
    return out


def review_spent() -> str | None:
    if REVIEW_PATH.exists():
        try:
            d = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
        except ValueError:
            return f"{REVIEW_PATH} is unparseable"
        if d.get("spent"):
            return f"{REVIEW_PATH} carries a spent marker ({d.get('spent_at')})"
    return None


# ---------------------------------------------------------------------------
# data: board grades (gate 1.2, 0.4)
# ---------------------------------------------------------------------------
def _parse_grade(v):
    g = _f(v)
    return g if (g is not None and 20.0 <= g <= 80.0) else None


def load_board(years=DEV_YEARS, *, live_from: str | None = None) -> dict:
    """{(Y, source, player_key): {"tools", "extras", "position", "date"}}: per tool the
    EARLIEST snapshot dated in [Y-01-01, Y-05-01). With live_from, Y = 0 holds each
    source's LATEST snapshot dated on or after live_from (the dark preview)."""
    import efv_w2_scout as SC
    import source_backtest as SB
    ws, we = SB._WINDOW_START_MMDD, SB._WINDOW_END_MMDD
    years = set(int(y) for y in years)
    con = sqlite3.connect(f"file:{db_path().as_posix()}?mode=ro", uri=True)
    try:
        q = ("SELECT source, snapshot_date, player_key, position, tools_json FROM snapshots "
             "WHERE source IN (?, ?, ?) AND tools_json IS NOT NULL AND tools_json != '' "
             "ORDER BY snapshot_date " + ("DESC" if live_from else "ASC"))
        cur = con.execute(q, SOURCES)
        out: dict = {}
        for src, sd, pk, pos, tj in cur:
            sd = str(sd or "")[:10]
            if not pk or len(sd) < 10:
                continue
            if live_from:
                if sd < live_from:
                    continue
                Y = 0
            else:
                Y = int(sd[:4])
                if Y not in years or not (f"{Y}{ws}" <= sd < f"{Y}{we}"):
                    continue
            try:
                t = json.loads(tj)
            except ValueError:
                continue
            if not isinstance(t, dict):
                continue
            ex = t.get("_extras") if isinstance(t.get("_extras"), dict) else {}
            tools = {k: _parse_grade(v) for k, v in t.items() if k != "_extras"}
            tools = {k: v for k, v in tools.items() if v is not None}
            if src == "mlb_pipeline":
                fut, _pre = SC.report_grades(ex.get("report"))
                for k, v in fut.items():
                    if k not in tools and v is not None:
                        tools[k] = float(v)
            if src == "fangraphs" and "throw" not in tools:
                arm = _parse_grade(ex.get("arm"))
                if arm is not None:
                    tools["throw"] = arm
            slot = out.setdefault((Y, src, pk), {"tools": {}, "extras": {}, "position": pos, "date": sd})
            for k, v in tools.items():
                slot["tools"].setdefault(k, v)            # earliest (or latest live) wins
            if src == "fangraphs":
                for name, key in FG_EXTRAS.items():
                    v = parse_mph(ex.get(key)) if key in ("sits", "tops") else _f(ex.get(key))
                    if v is not None:
                        slot["extras"].setdefault(name, v)
            if not slot.get("position") and pos:
                slot["position"] = pos
    finally:
        con.close()
    return out


# ---------------------------------------------------------------------------
# data: MiLB and MLB lines
# ---------------------------------------------------------------------------
_MEMO: dict = {}


def mlb_first_seasons() -> dict[int, int]:
    if "mlb_first" in _MEMO:
        return _MEMO["mlb_first"]
    import milb_history as mh
    out: dict[int, int] = {}
    for s in range(2005, LAST_MLB_SEASON + 1):
        for g in ("hitting", "pitching"):
            for r in mh.season_splits(1, s, g, fetch=False):
                pid = r.get("mlbam")
                if pid:
                    out[int(pid)] = min(out.get(int(pid), 9999), s)
    _MEMO["mlb_first"] = out
    return out


def milb_lines(side: str) -> dict:
    """{(pid, season, level): counts} summed over stints, sports 11 to 16, 2005 to 2026."""
    key = ("milb", side)
    if key in _MEMO:
        return _MEMO[key]
    import milb_history as mh
    group = "hitting" if side == "hit" else "pitching"
    keys = ("pa", "ab", "h", "triples", "hr", "so", "bb", "sb") if side == "hit" else ("bf", "so", "bb", "g", "gs")
    out: dict = {}
    for s in range(2005, LAST_MLB_SEASON + 1):
        if s == 2020:
            continue
        for sport in (11, 12, 13, 14, 15, 16):
            for r in mh.season_splits(sport, s, group, fetch=False):
                pid, lv = r.get("mlbam"), r.get("level")
                if not pid or lv not in LEVEL_ORDER:
                    continue
                slot = out.setdefault((int(pid), s, lv), {})
                for k in keys:
                    v = _f(r.get(k))
                    if v is not None:
                        slot[k] = slot.get(k, 0.0) + v
    _MEMO[key] = out
    return out


def player_profile(side: str) -> dict:
    """{pid: {season: {"level": highest level with 100 or more PA/BF, "g", "gs"}}}."""
    key = ("profile", side)
    if key in _MEMO:
        return _MEMO[key]
    exp = "pa" if side == "hit" else "bf"
    out: dict = defaultdict(dict)
    for (pid, s, lv), c in milb_lines(side).items():
        slot = out[pid].setdefault(s, {"level": None, "g": 0.0, "gs": 0.0})
        if (c.get(exp) or 0) >= 100 and (slot["level"] is None or LEVEL_ORDER[lv] > LEVEL_ORDER[slot["level"]]):
            slot["level"] = lv
        slot["g"] += c.get("g", 0.0)
        slot["gs"] += c.get("gs", 0.0)
    _MEMO[key] = dict(out)
    return _MEMO[key]


# ---------------------------------------------------------------------------
# the level-season z family (gate 3.3)
# ---------------------------------------------------------------------------
class ZMetric:
    """Per-line metric -> as-of reliability-shrunk Marcel z. lines: {(pid, season,
    level): (value, exposure, norm_key_extra)}."""

    def __init__(self, name: str, lines: dict, floor: float, *, by_level: bool = True):
        self.name = name
        self.floor = float(floor)
        pools = defaultdict(list)
        for (pid, s, lv), (v, e, extra) in lines.items():
            if v is None or e is None or e < self.floor:
                continue
            pk = (s, lv, extra) if by_level else (s,)
            pools[pk].append(((pid, s, lv), v, e))
        stats = {}
        for pk, items in pools.items():
            if len(items) < NORM_MIN_LINES:
                continue
            v = np.array([x[1] for x in items])
            e = np.array([x[2] for x in items])
            mu = float((v * e).sum() / e.sum())
            sd = float(math.sqrt(max(((e * (v - mu) ** 2).sum() / e.sum()), 0.0)))
            if sd > 0:
                stats[pk] = (mu, sd)
        season_z: dict = defaultdict(dict)       # pid -> season -> [sum e z, sum e]
        for pk, items in pools.items():
            st = stats.get(pk)
            if st is None:
                continue
            for (pid, s, lv), v, e in items:
                z = (v - st[0]) / st[1]
                a = season_z[pid].setdefault(s, [0.0, 0.0])
                a[0] += e * z
                a[1] += e
        self.season_z = {pid: {s: (a[0] / a[1], a[1]) for s, a in d.items()} for pid, d in season_z.items()}
        # consecutive played seasons (2019 -> 2021 across the cancelled 2020)
        pairs = defaultdict(list)                # second season -> [(z1, z2, nbar)]
        for pid, d in self.season_z.items():
            for s, (z, e) in d.items():
                s2 = 2021 if s == 2019 else s + 1
                if s2 in d:
                    z2, e2 = d[s2]
                    pairs[s2].append((z, z2, 0.5 * (e + e2)))
        self.pairs = dict(pairs)
        self._k: dict = {}

    def k_at(self, last_season: int) -> float | None:
        if last_season in self._k:
            return self._k[last_season]
        ps = [p for s2, lst in self.pairs.items() if s2 <= last_season for p in lst]
        k = None
        if len(ps) >= 30:
            a = np.array(ps)
            r = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
            if r > R_MIN:
                k = float(a[:, 2].mean() * (1.0 - r) / r)
        self._k[last_season] = k
        return k

    def asof(self, pid: int, Y: int) -> float | None:
        d = self.season_z.get(int(pid))
        if not d:
            return None
        k = self.k_at(Y - 1)
        if k is None:
            return None
        num = den = E = 0.0
        for back, w in MARCEL.items():
            s = Y - back
            if s >= Y:
                raise GuardError(f"{self.name}: season {s} is not before board year {Y}")
            if s not in d:
                continue
            z, e = d[s]
            num += w * e * z
            den += w * e
            E += (w / MARCEL[1]) * e
        if den <= 0:
            return None
        return (num / den) * (E / (E + k))


def build_zmetrics(side: str, *, last_season: int = 2025, log=print) -> dict[str, ZMetric]:
    import efv5_atlas as A
    out: dict[str, ZMetric] = {}
    lines = milb_lines(side)
    if side == "hit":
        for name, num in (("sb_rel", "sb"), ("tri_rel", "triples")):
            ln = {k: ((c.get(num, 0.0) / c["pa"]) if c.get("pa") else None, c.get("pa"), None)
                  for k, c in lines.items()}
            out[name] = ZMetric(name, ln, 100.0)
    # pitch-call aggregates with exposure
    pcols = {"hit": ("contact", "swstr", "swing", "two_strike_contact", "fstrike_taken"),
             "pit": ("swstr", "cstr", "csw", "fstrike", "ball_rate")}[side]
    acc = {m: {} for m in pcols}
    for p in sorted(A.PBP_AGG_DIR.glob("*.v1.json.gz")):
        d = A._read_gz_json(p)
        sport, season = int(d["sport"]), int(d["season"])
        lv = A.SPORT_LEVEL.get(sport)
        if lv is None or season > last_season:
            continue
        cols = d[f"{side}_cols"]
        for k, v in d[side].items():
            c = dict(zip(cols, v))
            e = c["pa"] if side == "hit" else c["bf"]
            if c["pitches"] <= 0:
                continue
            if side == "hit":
                sw, two = c["swings"], c["two_swings"]
                vals = {"swstr": c["whiffs"] / c["pitches"],
                        "contact": (sw - c["whiffs"]) / sw if sw else None,
                        "swing": sw / c["pitches"],
                        "two_strike_contact": (two - c["two_whiffs"]) / two if two else None,
                        "fstrike_taken": c["fp_called"] / c["fp_den"] if c["fp_den"] else None}
            else:
                vals = {"swstr": c["whiffs"] / c["pitches"], "cstr": c["called"] / c["pitches"],
                        "csw": (c["called"] + c["whiffs"]) / c["pitches"],
                        "fstrike": c["fp_strike"] / c["fp_den"] if c["fp_den"] else None,
                        "ball_rate": c["balls"] / c["pitches"]}
            for m in pcols:
                acc[m][(int(k), season, lv)] = (vals[m], float(e), None)
    for m in pcols:
        out[f"pbp_{m}"] = ZMetric(f"pbp_{m}", acc[m], 100.0)
    if side == "hit":
        bacc = {"fb": {}, "pull": {}, "hard": {}}
        for p in sorted(A.BB_AGG_DIR.glob("*.v1.json.gz")):
            d = A._read_gz_json(p)
            sport, season = int(d["sport"]), int(d["season"])
            lv = A.SPORT_LEVEL.get(sport)
            if lv is None or season > last_season:
                continue
            for k, v in d["bat"].items():
                c = dict(zip(A._BAT_COLS, v))
                bip = float(c.get("bip") or 0)
                if bip <= 0:
                    continue
                bacc["fb"][(int(k), season, lv)] = (c["fb"] / bip, bip, None)
                bacc["hard"][(int(k), season, lv)] = (c["hard"] / bip, bip, None)
                if c.get("spray"):
                    bacc["pull"][(int(k), season, lv)] = (c["pull"] / c["spray"], float(c["spray"]), None)
        for m, ln in bacc.items():
            out[f"bb_{m}"] = ZMetric(f"bb_{m}", ln, 50.0)
    # tracked components
    tpath = A.TRACK_DIR / ("hitter_season_level.csv.gz" if side == "hit" else "pitcher_season_level.csv.gz")
    tnames = (("ev_p90", "ev_max", "barrel", "hard_hit", "chase", "zone_contact", "whiff") if side == "hit"
              else ("fb_velo_mean", "fb_velo_p95", "fb_ivb", "extension", "whiff_fb", "whiff_br", "whiff_os",
                    "chase", "zone"))
    tacc = {m: {} for m in tnames}
    if tpath.exists():
        with gzip.open(tpath, "rt", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                s = int(r["season"])
                if s > last_season or r["level"] not in TRACK_LEVELS:
                    continue
                e = _f(r.get("pa") if side == "hit" else r.get("pitches")) or 0.0
                for m in tnames:
                    tacc[m][(int(r["mlbam"]), s, r["level"])] = (_f(r.get(m)), e, None)
    tfloor = 50.0 if side == "hit" else 100.0
    for m in tnames:
        out[f"trk_{m}"] = ZMetric(f"trk_{m}", tacc[m], tfloor)
    # pitch rates (Part P.1)
    pr = pitch_rate_lines(side, last_season=last_season)
    for name, ln in pr.items():
        out[name] = ZMetric(name, ln, 100.0, by_level=not name.endswith("_raw"))
    log(f"  z family {side}: " + ", ".join(f"{k} {len(v.season_z)}" for k, v in out.items()))
    return out


def pitch_rate_lines(side: str, *, last_season: int = 2025) -> dict[str, dict]:
    """Part P.1 per (pid, season, level): raw rates and the rate over its anchor, usable
    level-seasons only (pitch_rates' tracking guard).

    A pitcher's exposure (batters faced) is read off the SAME line his rate was computed
    on (pitch_rates.player_lines): the majority-role line on the role-split basis, the
    season line on the season-line fallback. Before the 2026-10-15 review fix the role
    line's BF was used on the fallback basis too, where the rate is the season line's
    (381 of 47,983 pitcher lines, 79 of them crossing the 100 BF floor)."""
    import pitch_rates as PR
    out = {"ppa_raw": {}, "ppa_par": {}} if side == "hit" else {
        "pbf_raw": {}, "pbf_par": {}, "pip_raw": {}, "pip_par": {}}
    for s in range(PR.MILB_FIRST, last_season + 1):
        if s == 2020:
            continue
        for lv in PR.MILB_LEVELS:
            try:
                lr = PR.league_rates(lv, s)
                pl = PR.player_lines(s, lv)
            except Exception:                                   # noqa: BLE001
                continue
            for pid, line in pl.items():
                if side == "hit":
                    h = line.get("hit")
                    if not h or h.get("pos") == "P" or h.get("p_pa") is None:
                        continue
                    anc = lr["hit"].get("p_pa")
                    out["ppa_raw"][(int(pid), s, lv)] = (h["p_pa"], float(h.get("pa") or 0), None)
                    if anc:
                        out["ppa_par"][(int(pid), s, lv)] = (h["p_pa"] / anc, float(h.get("pa") or 0), None)
                else:
                    p = line.get("pit")
                    if not p:
                        continue
                    role = p.get("role")
                    if p.get("basis") == PR.BASIS_ROLE:
                        rl = p.get("sp" if role == "SP" else "rp") or {}
                    else:
                        rl = p.get("season_line") or {}
                    bf = float(rl.get("bf") or 0)
                    blk = lr["sp" if role == "SP" else "rp"]
                    for rate, key in (("pbf", "p_bf"), ("pip", "p_ip")):
                        v = p.get(key)
                        if v is None:
                            continue
                        out[f"{rate}_raw"][(int(pid), s, lv)] = (v, bf, None)
                        anc = blk.get(key)
                        if anc:
                            out[f"{rate}_par"][(int(pid), s, lv)] = (v / anc, bf, role)
    return out


def field_shares(last_season: int) -> dict:
    """{pid: {season: {pos: games}}} from .cache/statsapi_field_season (sports 11 to 16)."""
    if "field" in _MEMO:
        return _MEMO["field"]
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for p in sorted((CACHE / "statsapi_field_season").glob("fld_v2_*_*.json")):
        m = re.match(r"fld_v2_(\d+)_(\d{4})\.json", p.name)
        if not m or int(m.group(1)) == 1:
            continue
        s = int(m.group(2))
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for r in rows or []:
            pid, pos, g = r.get("mlbam"), str(r.get("pos") or "").upper(), _f(r.get("g"))
            if pid and g and pos and pos != "P":
                out[int(pid)][s][pos] += g
    _MEMO["field"] = out
    return out


def share_asof(pid: int, Y: int, positions: tuple, fs: dict, mean: float | None) -> float | None:
    d = fs.get(int(pid))
    if not d:
        return None
    tot = num = 0.0
    for s, byp in d.items():
        if s >= Y:
            continue
        for pos, g in byp.items():
            if pos in ("DH", "PH", "PR"):
                continue
            tot += g
            if pos in positions:
                num += g
    if tot <= 0:
        return None
    share = num / tot
    rel = tot / (tot + FIELD_K)
    base = mean if mean is not None else share
    return base + (share - base) * rel


# ---------------------------------------------------------------------------
# labels (gate 2)
# ---------------------------------------------------------------------------
def load_mlb_label_data() -> dict:
    import tool_accuracy_lab as TAL
    seasons = range(2011, LAST_MLB_SEASON + 1)
    data = {"hit": TAL.load_statsapi("hitting", seasons), "pit": TAL.load_statsapi("pitching", seasons),
            "sc": TAL.load_statcast_batter(range(2015, LAST_MLB_SEASON + 1)),
            "sprint": TAL.load_sprint(range(2015, LAST_MLB_SEASON + 1)),
            "arm": TAL.load_arm(range(2020, LAST_MLB_SEASON + 1)),
            "oaa": TAL.load_oaa(range(2016, LAST_MLB_SEASON + 1)),
            "finn": TAL.load_fielding_innings(), "custom": {}, "arsenal": defaultdict(dict)}
    for r in TAL._csv_rows(CACHE / "savant_custom" / "custom_batter_2026.csv"):
        pid = _f(r.get("player_id"))
        if pid is None:
            continue
        data["custom"][int(pid)] = {"pa": _f(r.get("pa")) or 0.0, "chase": _f(r.get("oz_swing_percent")),
                                    "zcon": _f(r.get("iz_contact_percent"))}
    for s in (2024, 2025, 2026):
        for r in TAL._csv_rows(CACHE / "savant_mlb" / f"arsenal_pitcher_{s}.csv"):
            pid, n, wh = _f(r.get("player_id")), _f(r.get("pitches")), _f(r.get("whiff_percent"))
            if pid is None or not n or wh is None:
                continue
            for tool, types in ARSENAL_TYPES.items():
                if r.get("pitch_type") in types:
                    a = data["arsenal"][int(pid)].setdefault((tool, s), [0.0, 0.0])
                    a[0] += wh * n
                    a[1] += n
    return data


def mlb_label(tool: str, pid: int, Y: int, data: dict) -> float | None:
    import tool_accuracy_lab as TAL
    if tool in ("hit", "game_pwr"):
        o = TAL.outcome_hitter(pid, Y, data["hit"])
        if o is None:
            return None
        return -o["k_pct"] if tool == "hit" else o.get("iso")
    if tool == "raw_pwr":
        o = TAL.outcome_hitter(pid, Y, data["hit"], data["sc"])
        if o is None or (o.get("attempts") or 0) < 100:
            return None
        return o.get("ev_avg")
    if tool == "speed":
        o = TAL.outcome_sprint(pid, Y, data["sprint"])
        return None if o is None else o["sprint"]
    if tool == "field":
        o = TAL.outcome_oaa(pid, Y, data["oaa"], data["finn"])
        return None if o is None else o["oaa_per1000"]
    if tool == "throw":
        o = TAL.outcome_arm(pid, Y, data["arm"])
        return None if o is None else o["arm_z"]
    if tool in ("pitch_sel", "bat_ctrl"):
        c = data["custom"].get(pid)
        if not c or c["pa"] < 100:
            return None
        v = c["chase"] if tool == "pitch_sel" else c["zcon"]
        if v is None:
            return None
        return -v if tool == "pitch_sel" else v
    if tool in ("fb", "cmd"):
        o = TAL.outcome_pitcher(pid, Y, data["pit"])
        if o is None:
            return None
        return o["k_pct_pit"] if tool == "fb" else -o["bb_pct_pit"]
    if tool in ARSENAL_TYPES:
        lines = data["pit"].get(pid) or {}
        win = [s for s in TAL.window_seasons(lines.keys(), Y) if s >= 2024]
        a = data["arsenal"].get(pid) or {}
        num = sum(a[(tool, s)][0] for s in win if (tool, s) in a)
        den = sum(a[(tool, s)][1] for s in win if (tool, s) in a)
        return (num / den) if den >= 50 else None
    raise KeyError(tool)


def um_tables() -> dict:
    """Everything the upper-minors labels read: X1 translated AA/AAA lines, the raw SB
    lines and the tracked tables (seasons capped at LAST_UM_SEASON)."""
    import efv5_atlas as A
    import efv_x1_translate as X1
    out = {"x1": {"hit": defaultdict(list), "pit": defaultdict(list)}, "sb": defaultdict(list),
           "trk": {"hit": defaultdict(list), "pit": defaultdict(list)}}
    for side, stats in (("hit", ("k", "iso")), ("pit", ("k", "bb"))):
        for s in X1.SEASONS:
            if s > LAST_UM_SEASON:
                continue
            tabs = {st: X1.league_table(s, side, st) for st in stats}
            parks = {st: X1.park_factors(s, side, st) for st in stats}
            env = {st: X1.env_scale(s, 2018, side, st) for st in stats}
            for ln in X1.season_lines(s, side):
                if ln["level"] not in UM_LEVELS:
                    continue
                rec = {"season": s, "exp": ln["exp"]}
                for st in stats:
                    c = ln["c"].get(st)
                    lam = (tabs[st].get(ln["lg"]) or {}).get("lambda")
                    if c is None or not lam:
                        continue
                    pi = parks[st].get(ln["team"], 1.0) if ln["nt"] == 1 and ln["team"] else 1.0
                    rec[st] = (c[0] * env[st], c[1] * pi * lam, c[1])
                out["x1"][side][ln["mlbam"]].append(rec)
    lines = milb_lines("hit")
    ls = defaultdict(lambda: [0.0, 0.0])
    for (pid, s, lv), c in lines.items():
        if lv in UM_LEVELS and c.get("pa"):
            ls[(s, lv)][0] += c.get("sb", 0.0)
            ls[(s, lv)][1] += c["pa"]
    for (pid, s, lv), c in lines.items():
        if lv in UM_LEVELS and c.get("pa") and s <= LAST_UM_SEASON:
            a = ls[(s, lv)]
            mean = a[0] / a[1] if a[1] else None
            if mean:
                out["sb"][pid].append((s, c.get("sb", 0.0), c["pa"] * mean, c["pa"]))
    for side in ("hit", "pit"):
        tpath = A.TRACK_DIR / ("hitter_season_level.csv.gz" if side == "hit" else "pitcher_season_level.csv.gz")
        if not tpath.exists():
            continue
        with gzip.open(tpath, "rt", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                s = int(r["season"])
                if s > LAST_UM_SEASON or r["level"] not in TRACK_LEVELS:
                    continue
                out["trk"][side][int(r["mlbam"])].append(r)
    return out


def um_label(tool: str, pid: int, Y: int, side: str, T: dict) -> float | None:
    seasons = set(range(Y, min(Y + 2, LAST_UM_SEASON) + 1))
    if not seasons:
        return None
    if tool in ("hit", "game_pwr", "fb", "cmd"):
        st = {"hit": "k", "game_pwr": "iso", "fb": "k", "cmd": "bb"}[tool]
        recs = [r for r in T["x1"][side].get(pid, []) if r["season"] in seasons]
        exp = sum(r["exp"] for r in recs)
        if exp < (300 if side == "hit" else 150):
            return None
        num = sum(r[st][0] for r in recs if st in r)
        den = sum(r[st][1] for r in recs if st in r)
        if den <= 0:
            return None
        v = num / den
        return -v if tool in ("hit", "cmd") else v
    if tool == "speed":
        recs = [r for r in T["sb"].get(pid, []) if r[0] in seasons]
        pa = sum(r[3] for r in recs)
        exp_sb = sum(r[2] for r in recs)
        if pa < 300 or exp_sb <= 0:
            return None
        return sum(r[1] for r in recs) / exp_sb
    trk = {"raw_pwr": ("hit", "ev_mean", 1), "pitch_sel": ("hit", "chase", -1),
           "bat_ctrl": ("hit", "zone_contact", 1), "sl": ("pit", "whiff_br", 1),
           "cb": ("pit", "whiff_br", 1), "ch": ("pit", "whiff_os", 1)}.get(tool)
    if trk is None:
        return None
    sd, col, sign = trk
    recs = [r for r in T["trk"][sd].get(pid, []) if int(r["season"]) in seasons]
    num = den = 0.0
    for r in recs:
        v = _f(r.get(col))
        if v is None:
            continue
        if sd == "hit":
            w = _f(r.get("pa")) or 0.0
        else:
            share = _f(r.get("share_br" if col == "whiff_br" else "share_os")) or 0.0
            w = (_f(r.get("pitches")) or 0.0) * share
        num += v * w
        den += w
    floor = 50.0 if sd == "hit" else 100.0
    if den < floor:
        return None
    return sign * num / den


# ---------------------------------------------------------------------------
# the rows (gate 1.3, 1.4) and their candidates (gate 3)
# ---------------------------------------------------------------------------
def build_universe(board: dict, years, *, log=print, live: bool = False) -> tuple[list[dict], dict]:
    import efv_identity
    import efv_vintage_frame as F
    recs = F.load_universe()
    idx = efv_identity.build_index((max(years) - 1) if not live else LAST_MLB_SEASON)
    first = mlb_first_seasons()
    counts = defaultdict(int)
    grouped = defaultdict(dict)
    for (Y, src, pk), slot in board.items():
        grouped[(Y, pk)][src] = slot
    rows, seen = [], set()
    for (Y, pk), per in sorted(grouped.items()):
        rec = recs.get(pk)
        if rec is None:
            counts["no_record"] += 1
            continue
        pos = None
        for s in SOURCES:
            if per.get(s) and per[s].get("position"):
                pos = per[s]["position"]
                break
        pos = pos or rec.get("position")
        side = "pit" if is_pitcher(pos) else "hit"
        vint = (LAST_MLB_SEASON + 1) if live else Y
        res = efv_identity.resolve_record(rec, vint, idx, side)
        if res.person_id is None:
            counts[f"identity_{res.how}"] += 1
            continue
        mid = rec.get("mlbam_id")
        if mid is not None and _f(mid) is not None and int(_f(mid)) != int(res.person_id):
            counts["identity_disagrees_with_record"] += 1
            continue
        pid = int(res.person_id)
        fm = first.get(pid)
        if not live and fm is not None and fm < Y:
            counts["mlb_line_before_board_year"] += 1
            continue
        if (Y, pid) in seen:
            counts["duplicate_player"] += 1
            continue
        seen.add((Y, pid))
        tools = {s: per[s]["tools"] for s in SOURCES if per.get(s)}
        extras = (per.get("fangraphs") or {}).get("extras") or {}
        rows.append({"year": Y, "pid": pid, "player_key": pk, "name": rec.get("player_name"),
                     "side": side, "position": pos, "per_source": tools, "fg_extras": extras,
                     "mlb_first": fm})
    counts["rows"] = len(rows)
    log(f"  universe: {dict(counts)}")
    return rows, dict(counts)


def attach_candidates(rows: list[dict], *, last_season: int, log=print) -> dict:
    """Candidate values for every row (gate 3), the position group, the level cell and
    the age band. Returns coverage counts."""
    import efv_x1_translate as X1
    zm = {"hit": build_zmetrics("hit", last_season=last_season, log=log),
          "pit": build_zmetrics("pit", last_season=last_season, log=log)}
    prof = {"hit": player_profile("hit"), "pit": player_profile("pit")}
    fs = field_shares(last_season)
    # population mean shares for the field shrink, per board year (hitters' rows)
    mean_share = {}
    for Y in sorted({r["year"] for r in rows}):
        for name, posset in (("prem_share", ("SS", "CF")), ("arm_share", ("SS", "3B", "RF", "C"))):
            vals = [share_asof(r["pid"], Y if Y else last_season + 1, posset, fs, None)
                    for r in rows if r["year"] == Y and r["side"] == "hit"]
            vals = [v for v in vals if v is not None]
            mean_share[(Y, name)] = float(np.mean(vals)) if vals else None
    cov = defaultdict(int)
    t0 = time.time()
    for i, r in enumerate(rows):
        Y = r["year"] if r["year"] else last_season + 1
        side, pid = r["side"], r["pid"]
        c: dict = {}
        f = X1.features(pid, Y, None, side)
        if f.get("_T") is not None and f["_T"] >= Y:
            raise GuardError(f"X1 read season {f['_T']} for board year {Y}")
        if any(s >= Y for s in f.get("_seasons") or []):
            raise GuardError(f"X1 read a season at or after {Y}")
        for k in (X1_HIT if side == "hit" else X1_PIT):
            c[k] = f.get(k)
        for name, z in zm[side].items():
            c[name] = z.asof(pid, Y)
        if side == "hit":
            c["prem_share"] = share_asof(pid, Y, ("SS", "CF"), fs, mean_share.get((r["year"], "prem_share")))
            c["arm_share"] = share_asof(pid, Y, ("SS", "3B", "RF", "C"), fs, mean_share.get((r["year"], "arm_share")))
        for name in FG_EXTRAS:
            c[name] = (r.get("fg_extras") or {}).get(name)
        r["cands"] = c
        for k, v in c.items():
            if v is not None:
                cov[(side, k)] += 1
        # cells
        p = prof[side].get(pid, {})
        last = p.get(Y - 1) or {}
        r["level_cell"] = LEVEL_CELL.get(last.get("level")) if last.get("level") else None
        if side == "hit":
            r["group"] = POS_GROUP.get(position_token(r.get("position")))
        else:
            seas = sorted(s for s in p if s < Y and p[s].get("g"))
            r["group"] = (("SP" if p[seas[-1]]["gs"] / p[seas[-1]]["g"] >= 0.5 else "RP") if seas else None)
        if (i + 1) % 2000 == 0:
            log(f"    candidates {i + 1}/{len(rows)} ({time.time() - t0:.0f} s)")
    # age bands: terciles of age_rel_level within side
    for side in ("hit", "pit"):
        ages = [r["cands"].get("age_rel_level") for r in rows if r["side"] == side]
        ages = np.array([a for a in ages if a is not None])
        if ages.size >= 30:
            lo, hi = np.percentile(ages, [100 / 3, 200 / 3])
            for r in rows:
                a = r["cands"].get("age_rel_level")
                if r["side"] == side:
                    r["band"] = None if a is None else ("young" if a <= lo else ("old" if a > hi else "average"))
    return {f"{s}:{k}": v for (s, k), v in sorted(cov.items())}


def attach_labels(rows: list[dict], *, log=print) -> dict:
    data = load_mlb_label_data()
    T = um_tables()
    cnt = defaultdict(int)
    for r in rows:
        r["labels"] = {}
        for tool, spec in TOOLS.items():
            if spec["side"] != r["side"]:
                continue
            ym = None
            if r.get("mlb_first") is not None and r["mlb_first"] <= MAX_DEBUT_YEAR:
                ym = mlb_label(tool, r["pid"], r["year"], data)
            yu = um_label(tool, r["pid"], r["year"], r["side"], T) if spec.get("um") else None
            r["labels"][tool] = {"mlb": ym, "um": yu}
            cnt[(tool, "mlb")] += ym is not None
            cnt[(tool, "um")] += yu is not None
    log("  labels: " + ", ".join(f"{t}/{lb} {n}" for (t, lb), n in sorted(cnt.items())))
    return {f"{t}:{lb}": n for (t, lb), n in sorted(cnt.items())}


def tool_frames(rows: list[dict]) -> dict[str, ToolFrame]:
    frames = {}
    for tool, spec in TOOLS.items():
        out = []
        for r in rows:
            if r["side"] != spec["side"]:
                continue
            src = {s: (r["per_source"].get(s) or {}).get(tool) for s in SOURCES}
            vals = [v for v in src.values() if v is not None]
            if not vals:
                continue
            out.append({"year": r["year"], "pid": r["pid"], "gc": round_half(sum(vals) / len(vals)),
                        "src": src, "cands": {c: r["cands"].get(c) for c in spec["cands"]},
                        "y": dict(r.get("labels", {}).get(tool) or {}), "group": r.get("group"),
                        "mlb_first": r.get("mlb_first"),
                        "level_cell": r.get("level_cell"), "band": r.get("band")})
        frames[tool] = ToolFrame(tool, out)
    return frames


# ---------------------------------------------------------------------------
# Part P (EW3-15): pitch rates as direct eFV drivers on the first atlas's rows
# ---------------------------------------------------------------------------
def pr_line_metrics(side: str, zm: dict | None = None) -> dict:
    """{(pid, season, level): {metric: value}}: raw rates and par forms, the par forms
    shrunk toward 1 by n / (n + k), k the 3.3 stabilization point at that season."""
    lines = pitch_rate_lines(side, last_season=2025)
    out: dict = defaultdict(dict)
    for name, ln in lines.items():
        zmet = ZMetric(name, ln, 100.0, by_level=not name.endswith("_raw")) if name.endswith("_par") else None
        for key, (v, e, _x) in ln.items():
            if v is None or e < 100:
                continue
            if zmet is not None:
                k = zmet.k_at(key[1])
                if k is None:
                    continue
                v = 1.0 + (v - 1.0) * e / (e + k)
            out[key][f"{name}_{side}"] = v
    return out


def pr_atlas(*, Bn: int = B, seed: int = SEED, log=print) -> dict:
    import efv5_atlas as A
    A.DB_PATH = db_path()
    t0 = time.time()
    tables = A.build_tables(log=log)
    log(f"  atlas tables in {time.time() - t0:.0f} s")
    rows_out, redundancy = [], {}
    for side in ("hit", "pit"):
        T = tables[side]
        met = pr_line_metrics(side)
        names = list(PR_METRICS[side])
        keys = list(zip(T.pid.tolist(), T.season.tolist(), T.level.tolist()))
        for m in names:
            T.x[m] = np.array([met.get((int(p), int(s), lv), {}).get(m, np.nan) for p, s, lv in keys])
            A.METRICS[m] = ("pitch_rate", side, m)
        T.metrics = names
        for m in names:
            red = {}
            for other in (f"bb_pct_rel_{side}", f"k_pct_rel_{side}"):
                if other in T.x:
                    mm = np.isfinite(T.x[m]) & np.isfinite(T.x[other])
                    if mm.sum() >= 30:
                        from scipy.stats import spearmanr
                        red[other] = {"rho": _r(spearmanr(T.x[m][mm], T.x[other][mm]).correlation),
                                      "n": int(mm.sum())}
            red["coverage_rows"] = int(np.isfinite(T.x[m]).sum())
            redundancy[m] = red
        folds_all = A.player_folds(T.pid, A.FOLDS, seed)
        for lv, band, g, mask in A.cell_masks(T):
            guard_no_fv([lv, band, g])
            for label, frame in PR_LABELS:
                fr_mask = dict(A.label_frames(label, T.season)).get(frame)
                if fr_mask is None:
                    continue
                mf = mask & fr_mask
                for m in names:
                    rec = pr_score_listed(T, mf, m, label, Bn=Bn, seed=seed, folds_all=folds_all)
                    if rec is None:
                        continue
                    rec.update({"side": side, "level": lv, "age_band": band, "group": g, "metric": m,
                                "label": label, "frame": frame})
                    rows_out.append(rec)
        log(f"  pitch-rate atlas {side}: {len(rows_out)} tests ({time.time() - t0:.0f} s)")
    fam = defaultdict(list)
    for i, r in enumerate(rows_out):
        fam[r["label"]].append(i)
    for idx in fam.values():
        qs = bh_q([rows_out[i].get("p") for i in idx])
        for i, q in zip(idx, qs):
            rows_out[i]["q"] = q
    flagged = [r for r in rows_out if r.get("incr") is not None and r["incr"] > 0
               and r.get("ci95") and r["ci95"][0] > 0 and r.get("q") is not None and r["q"] <= Q_ADMIT]
    return {"rows": rows_out, "flagged": flagged, "redundancy": redundancy,
            "seconds": round(time.time() - t0, 1), "fwar_vintage": (tables.get("_meta") or {}).get("fwar_vintage_id")}


def pr_score_listed(T, mask, metric, label, *, Bn, seed, folds_all) -> dict | None:
    """efv5_atlas.score_cell's listed-row incremental score (consensus FV plus the
    metric, out of fold), with its player-clustered bootstrap drawn in chunks."""
    import efv5_atlas as A
    kind = A.LABELS[label]["kind"]
    y_all, x_all = T.y[label], T.x[metric]
    m = mask & np.isfinite(y_all) & np.isfinite(x_all) & np.isfinite(T.fv)
    if not m.any():
        return None
    pid, y, x, season, fv = T.pid[m], y_all[m], x_all[m], T.season[m], T.fv[m]
    if not A.enough(pid, y, kind):
        return None
    folds = folds_all[m]
    p_c = A.oof_predictions([fv], y, season, folds, kind)
    p_cm = A.oof_predictions([fv, x], y, season, folds, kind)
    if kind == "binary":
        s_c, s_cm = A.auc(p_c, y), A.auc(p_cm, y)
    else:
        s_c, s_cm = A.within_rho(p_c, y, season), A.within_rho(p_cm, y, season)
    if s_c is None or s_cm is None:
        return None
    delta = float(s_cm - s_c)
    draws, k, left = [], 0, int(Bn)
    while left > 0:
        nb = min(B_CHUNK, left)
        W = A.cluster_weights(pid, nb, seed + 1 + k)
        if kind == "binary":
            draws.append(A.auc_weighted(p_cm, y, W) - A.auc_weighted(p_c, y, W))
        else:
            draws.append(A.within_rho(p_cm, y, season, W) - A.within_rho(p_c, y, season, W))
        left -= nb
        k += 1
    iv = A.interval(np.concatenate(draws))
    raw, _ = A.raw_score(x, y, season, kind, None)
    return {"n": int(y.size), "players": int(np.unique(pid).size),
            "pos": int((y > 0).sum()) if kind == "binary" else int((y != 0).sum()),
            "seasons": [int(season.min()), int(season.max())], "raw": _r(raw),
            "model_c": _r(s_c), "model_cm": _r(s_cm), "incr": _r(delta), "ci95": iv["ci95"],
            "sd": iv["sd"], "p": A.p_normal(delta, iv["sd"])}


def grade_revisions(rows: list[dict]) -> dict:
    """Part P.5: the change in the consensus grade from Y to Y + 1 (both development
    years) against the pitch rate as of Y. Grades only; no outcome is read."""
    from scipy.stats import spearmanr
    by = {(r["year"], r["pid"]): r for r in rows}
    out = {}
    spec = {"hit": ("hit", ("ppa_raw", "ppa_par")), "pitch_sel": ("hit", ("ppa_raw", "ppa_par")),
            "bat_ctrl": ("hit", ("ppa_raw", "ppa_par")), "cmd": ("pit", ("pbf_raw", "pbf_par", "pip_raw", "pip_par"))}
    for tool, (side, rates) in spec.items():
        for rate in rates:
            xs, ys = [], []
            for (Y, pid), r in by.items():
                if r["side"] != side or (Y + 1) not in DEV_YEARS:
                    continue
                r2 = by.get((Y + 1, pid))
                if r2 is None:
                    continue
                g1 = [v.get(tool) for v in r["per_source"].values() if v.get(tool) is not None]
                g2 = [v.get(tool) for v in r2["per_source"].values() if v.get(tool) is not None]
                x = r["cands"].get(rate)
                if not g1 or not g2 or x is None:
                    continue
                xs.append(x)
                ys.append(np.mean(g2) - np.mean(g1))
            rho = spearmanr(xs, ys).correlation if len(xs) >= 30 else None
            out[f"{tool}:{rate}"] = {"n": len(xs), "rho": _r(rho)}
    return out


# ---------------------------------------------------------------------------
# the dark preview (gate 7)
# ---------------------------------------------------------------------------
def build_preview(eval_doc: dict, *, log=print) -> Path:
    board = load_board(live_from="2026-01-01")
    rows, _counts = build_universe(board, (LAST_MLB_SEASON + 1,), log=log, live=True)
    attach_candidates(rows, last_season=LAST_MLB_SEASON, log=log)
    verdicts = eval_doc.get("etools") or {}
    out_players = {}
    for r in rows:
        tools_out = {}
        for tool, spec in TOOLS.items():
            if spec["side"] != r["side"]:
                continue
            vals = [v.get(tool) for v in r["per_source"].values() if v.get(tool) is not None]
            if not vals:
                continue
            gc = round_half(sum(vals) / len(vals))
            v = verdicts.get(tool) or {}
            rec = {"consensus": gc, "consensus_display": display_grade(gc), "basis": "consensus",
                   "verdict": v.get("verdict")}
            ff = v.get("final_fit")
            if v.get("verdict") == "PASS" and ff:
                Z = np.array([[np.nan if r["cands"].get(c) is None else r["cands"][c] for c in v["admitted"]]])
                fit = {"lines": [(a, b, ok) for a, b, ok in ff["lines"]], "c": ff["c"]}
                e = float(etool_apply(np.array([gc]), Z, fit)[0])
                sig = ff.get("sigma") or 0.0
                rec.update({"etool": _r(e, 2), "etool_display": display_grade(e),
                            "band80": [_r(max(20.0, e - BAND_Z * sig), 2), _r(min(80.0, e + BAND_Z * sig), 2)],
                            "basis": "etool"})
            tools_out[spec["key"]] = rec
        if tools_out:
            out_players[r["player_key"]] = {"name": r.get("name"), "mlbam": r["pid"], "side": r["side"],
                                            "tools": tools_out}
    doc = {"generated_at": _now(), "item": ITEM, "flag_etools_on": ETOOLS_ON,
           "note": "dark preview: nothing served reads this file unless the owner flips ETOOLS_ON",
           "verdicts": {t: (verdicts.get(t) or {}).get("verdict") for t in TOOLS},
           "players": out_players}
    path = SERVED_PATH if ETOOLS_ON else PREVIEW_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    log(f"  preview: {len(out_players)} players -> {path}")
    return path


# ---------------------------------------------------------------------------
# fixtures (the dry run and the tests)
# ---------------------------------------------------------------------------
def fixture_frames(seed: int = 7, n_players: int = 260) -> dict[str, ToolFrame]:
    rng = np.random.default_rng(seed)
    frames = {}
    for tool, spec in TOOLS.items():
        rows = []
        for p in range(n_players):
            true = rng.normal(50, 8)
            yrs = rng.choice(DEV_YEARS, size=rng.integers(1, 3), replace=False)
            for Y in yrs:
                fg = true + rng.normal(0, 6)
                pl = true + rng.normal(0, 6)
                src = {"fangraphs": round_half(fg), "mlb_pipeline": round_half(pl), "baseballamerica": None}
                gc = round_half((fg + pl) / 2)
                cands = {}
                for j, c in enumerate(spec["cands"]):
                    cands[c] = (true - 50) / 8 + rng.normal(0, 1.0) if (j == 0 and rng.random() < 0.8) else (
                        rng.normal() if rng.random() < 0.6 else None)
                y = {"mlb": (true + rng.normal(0, 6)) if rng.random() < 0.6 else None,
                     "um": (true + rng.normal(0, 6)) if (spec.get("um") and rng.random() < 0.8) else None}
                rows.append({"year": int(Y), "pid": 1000 + p, "gc": gc, "src": src, "cands": cands, "y": y,
                             "group": ["C", "SS", "CF", "IF", "COF"][p % 5] if spec["side"] == "hit" else ["SP", "RP"][p % 2],
                             "level_cell": ["low", "A+", "AA", "AAA"][p % 4], "band": ["young", "average", "old"][p % 3]})
        frames[tool] = ToolFrame(tool, rows)
    return frames


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
def evaluate(frames: dict, *, Bn: int = B, perm: int = PERM, cells: bool = True, log=print) -> dict:
    log("  atlas of sub-drivers")
    atlas = run_atlas(frames, Bn=Bn, perm=perm, cells=cells, log=log)
    adm = admit(frames, atlas)
    et, aw = {}, {}
    for tool, fr in frames.items():
        names = [a["candidate"] for a in adm[tool]["admitted"]]
        et[tool] = etool_eval(fr, names, Bn=Bn)
        et[tool]["qualifying"] = adm[tool]["qualifying"]
        aw[tool] = weighting_arm(fr, names, Bn=Bn)
        log(f"  {tool:9s} admitted {names} -> {et[tool]['verdict']}")
    return {"atlas": atlas, "etools": et, "weighting": aw}


def input_shas() -> dict:
    paths = [db_path(), DATA / "debuts.json", DATA / "inactive.json", DATA / "timeseries.json",
             DATA / "fielding_innings.json", CACHE / "savant_custom" / "custom_batter_2026.csv",
             DATA / "fwar_vintage.json"]
    return {str(p.name): sha256_of(p) for p in paths}


def check(log=print) -> dict:
    guard_years(DEV_YEARS)
    board = load_board(DEV_YEARS)
    rows, counts = build_universe(board, DEV_YEARS, log=log)
    cov = attach_candidates(rows, last_season=max(DEV_YEARS) - 1, log=log)
    lab = attach_labels(rows, log=log)
    frames = tool_frames(rows)
    per_tool = {}
    for tool, fr in frames.items():
        per_tool[tool] = {"rows_with_consensus": fr.n,
                          "players": int(np.unique(fr.pid).size),
                          "by_year": {int(y): int((fr.year == y).sum()) for y in np.unique(fr.year)},
                          "labels": {lb: int(np.isfinite(fr.y[lb]).sum()) for lb in LABELS},
                          "candidates": {c: int(np.isfinite(fr.cands[c]).sum()) for c in TOOLS[tool]["cands"]},
                          "candidates_with_mlb_label": {c: int((np.isfinite(fr.cands[c]) & np.isfinite(fr.y["mlb"])).sum())
                                                        for c in TOOLS[tool]["cands"]},
                          "candidates_with_um_label": {c: int((np.isfinite(fr.cands[c]) & np.isfinite(fr.y["um"])).sum())
                                                       for c in TOOLS[tool]["cands"]}}
    return {"universe": counts, "coverage": cov, "labels": lab, "per_tool": per_tool}


def run(gate_sha: str, *, log=print) -> dict:
    why = look_spent()
    if why:
        raise GuardError(f"the look is spent: {why}")
    if not gate_sha_ok(gate_sha):
        raise GuardError(f"{gate_sha} does not name a commit carrying {GATE_DOC} as REGISTERED")
    guard_years(DEV_YEARS)
    shas_start = input_shas()
    t0 = time.time()
    board = load_board(DEV_YEARS)
    rows, counts = build_universe(board, DEV_YEARS, log=log)
    cov = attach_candidates(rows, last_season=max(DEV_YEARS) - 1, log=log)
    lab = attach_labels(rows, log=log)
    for r in rows:
        if r["year"] in RESERVED_BOARD_YEARS:
            raise GuardError("reserved board year in the frame")
        for tool, v in (r.get("labels") or {}).items():
            if v.get("mlb") is not None and (r.get("mlb_first") is None or r["mlb_first"] > MAX_DEBUT_YEAR):
                raise GuardError("an L_MLB row whose first MLB season is after 2024")
    frames = tool_frames(rows)
    log(f"  inputs built in {time.time() - t0:.0f} s; the look begins")
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    started = _now()
    try:
        res = evaluate(frames, log=log)
        log("  Part P: pitch rates as direct eFV drivers")
        pr = pr_atlas(log=log)
        rev = grade_revisions(rows)
    except Exception as exc:                                     # noqa: BLE001
        doc = {"item": ITEM, "spent": True, "spent_at": _now(), "gate_sha": gate_sha,
               "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(),
               "started": started}
        EVAL_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
        raise
    pr_rows = pr.pop("rows")
    atlas_doc = {"item": ITEM, "tool": TOOL, "generated_at": _now(), "gate_sha": gate_sha,
                 "survivorship": SURVIVORSHIP, "rows": res["atlas"], "pitch_rate_rows": pr_rows}
    ATLAS_PATH.write_text(json.dumps(atlas_doc, indent=None, separators=(",", ":")), encoding="utf-8",
                          newline="\n")
    eval_doc = {"item": ITEM, "tool": TOOL, "spent": True, "spent_at": _now(), "started": started,
                "gate_doc": GATE_DOC, "gate_sha": gate_sha, "head": (_git("rev-parse", "HEAD") or "").strip(),
                "survivorship": SURVIVORSHIP,
                "constants": {"dev_years": DEV_YEARS, "B": B, "seed": SEED, "perm": PERM, "perm_seed": PERM_SEED,
                              "q_admit": Q_ADMIT, "r_cap": R_CAP, "max_sub": MAX_SUB, "pool_min": POOL_MIN,
                              "last_um_season": LAST_UM_SEASON, "max_debut_year": MAX_DEBUT_YEAR},
                "universe": counts, "coverage": cov, "label_counts": lab,
                "tests": {"atlas_rows": len(res["atlas"]),
                          "pooled_tests": sum(1 for r in res["atlas"] if r["cell"] == "pooled"),
                          "pitch_rate_tests": len(pr_rows)},
                "etools": res["etools"], "weighting": res["weighting"],
                "pitch_rate": {"atlas": pr, "grade_revisions": rev,
                               "subdriver_rows": [r for r in res["atlas"] if r["cell"] == "pooled"
                                                  and r["candidate"].split("_")[0] in ("ppa", "pbf", "pip")]},
                "inputs_sha256_start": shas_start, "inputs_sha256_end": input_shas(),
                "seconds": round(time.time() - t0, 1), "flag_etools_on": ETOOLS_ON}
    EVAL_PATH.write_text(json.dumps(eval_doc, indent=1), encoding="utf-8", newline="\n")
    log(f"  wrote {ATLAS_PATH} and {EVAL_PATH} ({time.time() - t0:.0f} s)")
    return eval_doc


def review_reads(amend_sha: str, *, log=print) -> dict:
    """Amendment 1, run once: A1 (promotion counts and the non-debut read), A2 (margins)
    and A3 (the Part P.3 re-run with the R4 exposure fix). The look's artifacts are read,
    never rewritten."""
    why = review_spent()
    if why:
        raise GuardError(f"the review reads are spent: {why}")
    if not gate_sha_ok(amend_sha, REVIEW_DOC):
        raise GuardError(f"{amend_sha} does not name a commit carrying {REVIEW_DOC} as REGISTERED")
    look = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    if not look.get("spent") or "etools" not in look:
        raise GuardError("no spent look to review")
    guard_years(DEV_YEARS)
    shas_start = input_shas()
    t0 = time.time()
    board = load_board(DEV_YEARS)
    rows, counts = build_universe(board, DEV_YEARS, log=log)
    attach_candidates(rows, last_season=max(DEV_YEARS) - 1, log=log)
    attach_labels(rows, log=log)
    if counts != look.get("universe"):
        raise GuardError(f"universe {counts} differs from the look's {look.get('universe')}")
    frames = tool_frames(rows)
    started = _now()
    a1, a2, repro = {}, {}, {}
    for tool in REVIEW_TOOLS:
        fr = frames[tool]
        adm = list(look["etools"][tool]["admitted"])
        pred, _ = etool_oof(fr, adm)
        for lb in LABELS:                                   # reproduce the look first
            want = (look["etools"][tool]["labels"].get(lb) or {}).get("d")
            got = paired_d(pred, fr.gc, fr.y[lb], fr.year, fr.pid, Bn=0).get("d")
            repro[f"{tool}:{lb}"] = {"look": want, "now": got}
            if want is not None and (got is None or abs(got - want) > 5e-5):
                raise GuardError(f"{tool} {lb}: d_E {got} does not reproduce the look's {want}")
        a1[tool] = {"counts": promotion_counts(fr), **nondebut_read(fr, adm, pred=pred)}
        log(f"  A1 {tool:9s} non-debut d {a1[tool]['non_debut'].get('d')} lb {a1[tool]['non_debut'].get('lb95')}")
        if len(adm) >= 2:
            a2[tool] = margin_read(fr, adm)
            log(f"  A2 {tool:9s} " + ", ".join(f"{j} {'NO ADDED EFFECT' if v['no_added_effect'] else 'adds'}"
                                              for j, v in a2[tool]["subdrivers"].items()))
    log("  A3: Part P.3 re-run (R4 exposure fix)")
    pr = pr_atlas(log=log)
    pr_rows = pr.pop("rows")
    qs = [r["q"] for r in pr_rows if r.get("q") is not None]
    orig = (look.get("pitch_rate") or {}).get("atlas") or {}
    doc = {"item": ITEM, "tool": TOOL, "spent": True, "spent_at": _now(), "started": started,
           "amendment_doc": REVIEW_DOC, "amendment_sha": amend_sha, "look_gate_sha": look.get("gate_sha"),
           "head": (_git("rev-parse", "HEAD") or "").strip(), "survivorship": SURVIVORSHIP,
           "universe": counts, "reproduction": repro,
           "A1_promotion": a1,
           "A1_promotion_dependent": [t for t in REVIEW_TOOLS
                                      if look["etools"][t]["verdict"] == "PASS" and a1[t]["promotion_dependent"]],
           "A2_margins": a2,
           "A2_no_added_effect": {t: [j for j, v in d["subdrivers"].items() if v["no_added_effect"]]
                                  for t, d in a2.items()},
           "A3_part_p3_rerun": {"disclosure": "a registered read (gate Part P.3) re-run once because of a "
                                              "code defect (R4, pitch-rate exposure on the fallback basis)",
                                "tests": len(pr_rows), "flagged": pr["flagged"],
                                "min_q": _r(min(qs), 6) if qs else None,
                                "original_tests": None, "original_flagged": len(orig.get("flagged") or []),
                                "redundancy": pr["redundancy"], "seconds": pr["seconds"],
                                "fwar_vintage": pr.get("fwar_vintage"), "rows": pr_rows},
           "inputs_sha256_start": shas_start, "inputs_sha256_end": input_shas(),
           "seconds": round(time.time() - t0, 1), "flag_etools_on": ETOOLS_ON}
    doc["A3_part_p3_rerun"]["original_tests"] = (look.get("tests") or {}).get("pitch_rate_tests")
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    log(f"  wrote {REVIEW_PATH} ({time.time() - t0:.0f} s)")
    return doc


def dry_run(log=print) -> dict:
    frames = fixture_frames()
    res = evaluate(frames, Bn=100, perm=5, cells=False, log=lambda *_a: None)
    return {"tools": {t: v["verdict"] for t, v in res["etools"].items()},
            "atlas_rows": len(res["atlas"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--gate-sha")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--review-reads", action="store_true")
    ap.add_argument("--amend-sha")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.review_reads:
        review_reads(a.amend_sha)
        return 0
    if a.dry_run:
        print(json.dumps(dry_run(), indent=1))
        return 0
    if a.check:
        doc = check()
        txt = json.dumps(doc, indent=1, default=str)
        if a.out:
            Path(a.out).write_text(txt, encoding="utf-8")
        print(txt[:20000])
        return 0
    if a.run:
        run(a.gate_sha)
        return 0
    if a.preview:
        if not EVAL_PATH.exists():
            print("no spent look to build from")
            return 1
        build_preview(json.loads(EVAL_PATH.read_text(encoding="utf-8")))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

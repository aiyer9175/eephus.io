# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The look runner of docs/efv-v2/SURROGATE_2026_GATE.md (precondition Q7; task
SG_7_PREREQS). BUILT ONLY: no look has run from this file. SG_8 runs it once, after the
gate's REGISTERED commit.

What it refuses (each before any outcome is read):
- without the gate file's REGISTERED commit sha: the sha is found at RUN time (the
  latest commit touching SURROGATE_GATE_DOC whose tree marks it REGISTERED and that is
  an ancestor of HEAD, efv_surrogate_guard.gate_sha_committed_for); none, no look;
- a spent look: data/efv_surrogate_gate.json already carries the read's key, or the
  marker .cache/efv_surrogate/look_started.json records a look that began scoring and
  wrote no result (the crash protocol's owner question is then pending);
- in a session that runs another gate's look (another .cache/<gate>/look_started.json,
  efv_surrogate_guard.blocked_day). No calendar day is refused: the owner waived every
  registered look day and date on 2026-10-14 (decision EW3-5), and the eFV reserved
  read no longer exists (EW2-6 took it on 2026-10-08);
- while the nightly, a pipeline or a test session runs (the process listing; a failed
  listing counts as busy);
- a driver constant within a scored split (T2): checked on the drivers alone BEFORE any
  outcome is read; the runner STOPs there and no look is spent (the handling goes to a
  dated amendment written from the variance check alone).

How it runs (the one-look crash protocol): stdout and stderr are teed into the task
directory FIRST; the inputs are pinned at the start and again at the end (sha256 of the
pinned files, git blobs of the builder, the guard and efv_vintage_frame.py; a moved pin
voids the run); the marker is written when scoring begins; on any exception after that,
OWNER_QUESTION.md is written and the runner STOPs without rerunning (the marker keeps
the look spent). Every cell's bootstrap SD is printed BEFORE any point delta, and every
printed cell tolerates None and NaN.

The read it carries is S3, the transfer read (s6.1, clauses T1 to T4 and the T6
descriptives; T5 is asserted before scoring), purpose `transfer`, V 2011-2019 and V 2022
only. S4 (lv_2026) is void under the recorded OQ2 = A and is not implemented here.
Nothing here groups anything by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_surrogate_guard as G  # noqa: E402

DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / G.OWN_CACHE_DIR
ARTIFACT = "efv_surrogate_gate.json"
READ_KEY = "transfer"
PURPOSE = "transfer"

#: s4: paired bootstrap B 2000, seed 20260930; permutation seed 20260931.
BOOT_B = 2000
BOOT_SEED = 20260930
PERM_SEED = 20260931
#: s5 T1: the one-sided 95 percent lower bound of rho(S_idx, L6 pct), both sides.
T1_FLOOR = 0.50
#: s5 T2 (c): the slope-ratio band.
T2_RATIO_BAND = (0.5, 2.0)
#: s5 T3: the Fisher-z CI95 of the difference lies inside this band.
T3_BAND = 0.10
#: s5 T4: HARM iff the upper bound is below 0 or the point is below this.
T4_HARM_POINT = -0.005
Z95_ONE = 1.6448536269514722
Z95_TWO = 1.959963984540054

SIDES = ("hit", "pit")
FIT_VINTAGES = tuple(range(2011, 2017))
G_S_VINTAGES = tuple(range(2011, 2020))
T3_VINTAGE = 2022
T4_EVAL_VINTAGES = (2017, 2018, 2019)
#: T2: the timing-head candidates (efv_v2_model.V2_TIMING_KEYS, V2_ABSENCE_KEY and the
#: protection keys) and their split schedule; MiLB drivers are scored on V 2015-2019.
T2_MILB_DRIVERS = ("age_rel_level", "level_rank", "milb_absent")
T2_OTHER_DRIVERS = ("on_40man", "nov_add")
T2_SPLITS = {"milb": ((2015, 2016), (2017, 2018, 2019)),
             "other": ((2011, 2012, 2013), (2014, 2015, 2016), (2017, 2018, 2019))}
MIN_GROUP_ROWS = 20

#: The files a look pins (relative to DATA_DIR) and the modules whose git blobs it pins.
PINNED_FILES = ("efv_surrogate_pins_2026.json", "efv_surrogate_frame_2026.json",
                G.LOOK_1_RECORD_NAME, G.GATE_RECORD_NAME, G.ETA_EVAL_NAME)
PINNED_BLOBS = ("efv_vintage_frame.py", "efv_surrogate.py", "efv_surrogate_guard.py",
                "efv_labels.py", "efv_v2_model.py")
BUSY_TOKENS = ("run_monthly", "nightly", "pytest")


class LookRefused(RuntimeError):
    """The look does not start; nothing was read and no look is spent."""


class RegistrationStop(RuntimeError):
    """A registration error found before any outcome was read (T2's variance check);
    no look is spent."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# printing: every cell tolerates None and NaN
# ---------------------------------------------------------------------------

def fnum(v, nd: int = 4) -> str:
    """A number for a printed cell; "NA" for None, NaN, inf or a non-number."""
    if v is None or isinstance(v, bool):
        return "NA" if v is None else str(v)
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "NA"
    if not math.isfinite(x):
        return "NA"
    return f"{x:+.{nd}f}"


def clean_json(obj):
    """JSON-safe copy: NaN and inf become None; numpy scalars become Python numbers."""
    if isinstance(obj, dict):
        return {str(k): clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if math.isfinite(x) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def sd_lines(cells: dict) -> list[str]:
    """The bootstrap SD of every cell, printed BEFORE any point (Q7)."""
    out = ["BOOTSTRAP SDs (every cell, before any point delta):"]
    for name in sorted(cells):
        c = cells[name] or {}
        out.append(f"  {name}: sd_player {fnum(c.get('sd_player'))} "
                   f"sd_club {fnum(c.get('sd_club'))} n {c.get('n', 'NA')}")
    return out


def point_lines(cells: dict) -> list[str]:
    out = ["POINTS (one-sided 95 percent bounds beside each):"]
    for name in sorted(cells):
        c = cells[name] or {}
        out.append(f"  {name}: point {fnum(c.get('point'))} "
                   f"lo95 {fnum(c.get('lo95'))} hi95 {fnum(c.get('hi95'))} "
                   f"lo95_club {fnum(c.get('lo95_club'))} mde95 {fnum(c.get('mde95'))}")
    return out


def report_lines(block: dict) -> list[str]:
    """The whole printed report of a scored block: SDs first, then points, then each
    clause's verdict."""
    cells = block.get("cells") or {}
    lines = sd_lines(cells) + point_lines(cells)
    for clause in ("T1", "T2", "T3", "T4"):
        v = (block.get("verdicts") or {}).get(clause)
        lines.append(f"{clause}: {v if v is not None else 'NA'}")
    return lines


# ---------------------------------------------------------------------------
# statistics (pure numpy)
# ---------------------------------------------------------------------------

def _ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), dtype=float)
    r[order] = np.arange(len(x), dtype=float)
    xs = x[order]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(x, y) -> float | None:
    """Spearman rho on the finite pairs; None under three pairs or a constant side."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 3:
        return None
    rx, ry = _ranks(x), _ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def within_spearman(x, y, groups, min_rows: int = MIN_GROUP_ROWS) -> float | None:
    """Size-weighted within-group Spearman (groups of at least min_rows)."""
    x, y, g = np.asarray(x, float), np.asarray(y, float), np.asarray(groups)
    num = den = 0.0
    for k in np.unique(g):
        m = g == k
        if m.sum() < min_rows:
            continue
        r = spearman(x[m], y[m])
        if r is None:
            continue
        num += r * m.sum()
        den += m.sum()
    return num / den if den else None


def partial_spearman(x, y, z) -> float | None:
    """rho(x, y given z): Pearson of the rank residuals after regressing each rank on
    the rank of z."""
    x, y, z = (np.asarray(a, float) for a in (x, y, z))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if ok.sum() < 4:
        return None
    rx, ry, rz = _ranks(x[ok]), _ranks(y[ok]), _ranks(z[ok])
    Z = np.column_stack([np.ones(rz.size), rz])

    def resid(v):
        b, *_ = np.linalg.lstsq(Z, v, rcond=None)
        return v - Z @ b
    ex, ey = resid(rx), resid(ry)
    if ex.std() == 0 or ey.std() == 0:
        return None
    return float(np.corrcoef(ex, ey)[0, 1])


def slope_given(y, u, d) -> float | None:
    """The unstandardized OLS slope of y on driver d given u (y ~ 1 + u + d)."""
    y, u, d = (np.asarray(a, float) for a in (y, u, d))
    ok = np.isfinite(y) & np.isfinite(u) & np.isfinite(d)
    if ok.sum() < 4 or np.std(d[ok]) == 0:
        return None
    X = np.column_stack([np.ones(ok.sum()), u[ok], d[ok]])
    b, *_ = np.linalg.lstsq(X, y[ok], rcond=None)
    return float(b[2])


def cluster_bootstrap(stat, n: int, clusters, *, B: int = BOOT_B,
                      seed: int = BOOT_SEED) -> np.ndarray:
    """B draws of stat(idx) resampling whole clusters with replacement; draws where
    stat returns None are dropped."""
    clusters = np.asarray(clusters)
    keys = np.unique(clusters)
    members = {k: np.flatnonzero(clusters == k) for k in keys}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(int(B)):
        pick = rng.integers(0, len(keys), len(keys))
        idx = np.concatenate([members[keys[i]] for i in pick]) if len(keys) else np.array([], int)
        v = stat(idx)
        if v is not None and math.isfinite(v):
            out.append(float(v))
    return np.asarray(out)


def cell(stat, n: int, players, clubs=None, *, B: int = BOOT_B,
         seed: int = BOOT_SEED) -> dict:
    """One cell: point, player-clustered SD and one-sided bounds, the club-clustered
    SD and lower bound (the binding sensitivity) and mde95 = 1.645 x SD."""
    full = np.arange(n)
    point = stat(full)
    dp = cluster_bootstrap(stat, n, players, B=B, seed=seed)
    sd_p = float(dp.std(ddof=1)) if dp.size > 1 else None
    out = {"n": int(n), "point": point, "sd_player": sd_p,
           "lo95": float(np.quantile(dp, 0.05)) if dp.size else None,
           "hi95": float(np.quantile(dp, 0.95)) if dp.size else None,
           "mde95": Z95_ONE * sd_p if sd_p is not None else None,
           "draws": int(dp.size)}
    if clubs is not None:
        dc = cluster_bootstrap(stat, n, clubs, B=B, seed=seed)
        out["sd_club"] = float(dc.std(ddof=1)) if dc.size > 1 else None
        out["lo95_club"] = float(np.quantile(dc, 0.05)) if dc.size else None
    return out


def fisher_z_diff_ci(r1, n1, r2, n2) -> tuple[float | None, float | None, float | None]:
    """(difference, lo, hi) of the Fisher-z difference z(r1) - z(r2), CI95, back on the
    z scale; None on any missing input."""
    if None in (r1, r2) or min(n1, n2) <= 3:
        return None, None, None
    r1 = max(-0.999999, min(0.999999, float(r1)))
    r2 = max(-0.999999, min(0.999999, float(r2)))
    d = math.atanh(r1) - math.atanh(r2)
    se = math.sqrt(1.0 / (n1 - 3) + 1.0 / (n2 - 3))
    return d, d - Z95_TWO * se, d + Z95_TWO * se


# ---------------------------------------------------------------------------
# clause verdicts (pure; the rules of s5, frozen at registration)
# ---------------------------------------------------------------------------

def t1_verdict(lo_by_side: dict) -> str:
    """PASS iff the one-sided lower bound is at least T1_FLOOR on BOTH sides."""
    los = [lo_by_side.get(s) for s in SIDES]
    if any(v is None or not math.isfinite(float(v)) for v in los):
        return "UNDECIDED (a side has no bound)"
    return "PASS" if all(float(v) >= T1_FLOOR for v in los) else "FAIL"


def t2_driver_verdict(partial_lo, sign_g, sign_r, ratio) -> bool:
    """(a) partial lower bound above 0, (b) equal slope signs, (c) ratio in band."""
    if partial_lo is None or sign_g is None or sign_r is None or ratio is None:
        return False
    lo, hi = T2_RATIO_BAND
    return partial_lo > 0 and sign_g == sign_r and lo <= ratio <= hi


def t3_verdict(lo, hi) -> str:
    if lo is None or hi is None:
        return "STOP (no interval)"
    return "PASS" if (-T3_BAND < lo and hi < T3_BAND) else "STOP"


def t4_verdict(point, hi95, twin_lo95) -> dict:
    harm = (hi95 is not None and hi95 < 0) or (point is not None and point < T4_HARM_POINT)
    return {"harm": bool(harm),
            "reading": "HARM" if harm else "not shown harmful, unpowered",
            "beats_twin": bool(twin_lo95 is not None and twin_lo95 > 0)}


# ---------------------------------------------------------------------------
# T2's variance check: drivers only, before any outcome
# ---------------------------------------------------------------------------

def driver_variance_check(rows_by_side: dict) -> list[str]:
    """Every (side, driver, split) where the driver is constant (or absent) on the
    rows of that split. Reads the drivers off row["v2"] only; no outcome."""
    bad = []
    for side, rows in rows_by_side.items():
        for drv in T2_MILB_DRIVERS + T2_OTHER_DRIVERS:
            sched = T2_SPLITS["milb" if drv in T2_MILB_DRIVERS else "other"]
            for split in sched:
                vals = [((r.get("v2") or {}).get(drv)) for r in rows
                        if int(r["decision_year"]) in split]
                vals = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
                if len(set(vals)) < 2:
                    bad.append(f"{side}:{drv}:{split[0]}-{split[-1]}")
    return bad


# ---------------------------------------------------------------------------
# scoring a block from assembled rows (pure: the tests run it on fixtures)
# ---------------------------------------------------------------------------

def _arr(rows, key):
    return np.asarray([np.nan if r.get(key) is None else float(r[key]) for r in rows])


def score_transfer(data: dict, *, B: int = BOOT_B) -> dict:
    """The S3 block from assembled inputs:
    data["t1"][side]: rows with s_idx_oos, l6_pct, resolved (bool), player, club, vintage;
    data["t2"][side]: rows with g_s, r3, u_c, vintage and the drivers;
    data["t3"]: {"old": rows with g_s, r3; "v2022": rows with g_s, r3} (one row per player);
    data["t4"][side]: {V: {"aug": rows, "inc": rows, "twin": rows}} each with score, r3,
    player, club.
    Returns {"cells", "t2", "t3", "verdicts"}."""
    cells: dict = {}
    t1_lo: dict = {}
    for side in SIDES:
        rows = (data.get("t1") or {}).get(side) or []
        if not rows:
            t1_lo[side] = None
            continue
        x, y = _arr(rows, "s_idx_oos"), _arr(rows, "l6_pct")
        pl = [r.get("player") for r in rows]
        cl = [r.get("club") for r in rows]
        c = cell(lambda i, x=x, y=y: spearman(x[i], y[i]), len(rows), pl, cl, B=B)
        cells[f"T1|{side}|L6"] = c
        t1_lo[side] = c.get("lo95")
        res = [i for i, r in enumerate(rows) if r.get("resolved")]
        cells[f"T1|{side}|L6_resolved_only"] = {
            "n": len(res), "point": spearman(x[res], y[res]) if res else None}
    t2_out: dict = {}
    t2_fail = []
    for side in SIDES:
        rows = (data.get("t2") or {}).get(side) or []
        if not rows:
            continue
        g_all, r_all, u_all = _arr(rows, "g_s"), _arr(rows, "r3"), _arr(rows, "u_c")
        V_all = np.asarray([int(r["vintage"]) for r in rows])
        pl = [r.get("player") for r in rows]
        c = cell(lambda i: partial_spearman(g_all[i], r_all[i], u_all[i]),
                 len(rows), pl, B=B)
        cells[f"T2a|{side}|partial"] = c
        rho_ug, rho_gy, rho_uy = (spearman(u_all, g_all), spearman(g_all, r_all),
                                  spearman(u_all, r_all))
        bypass = (1.0 - rho_ug * rho_gy / rho_uy
                  if None not in (rho_ug, rho_gy, rho_uy) and rho_uy else None)
        drivers = {}
        for drv in T2_MILB_DRIVERS + T2_OTHER_DRIVERS:
            d_all = _arr(rows, drv)
            sched = T2_SPLITS["milb" if drv in T2_MILB_DRIVERS else "other"]
            pooled_years = sorted({y for s in sched for y in s})
            res = {}
            for name, years in [("pooled", pooled_years)] + [
                    (f"{s[0]}-{s[-1]}", s) for s in sched]:
                m = np.isin(V_all, years)
                sg = slope_given(g_all[m], u_all[m], d_all[m])
                sr = slope_given(r_all[m], u_all[m], d_all[m])
                ratio = (sg / sr) if (sg is not None and sr not in (None, 0.0)) else None
                ok = t2_driver_verdict(c.get("lo95"), None if sg is None else sg > 0,
                                       None if sr is None else sr > 0, ratio)
                res[name] = {"slope_g": sg, "slope_r3": sr, "ratio": ratio, "holds": ok}
                if not ok:
                    t2_fail.append(f"{side}:{drv}:{name}")
            drivers[drv] = res
        t2_out[side] = {"bypass_share": bypass, "drivers": drivers}
    t3 = data.get("t3") or {}
    old, new = t3.get("old") or [], t3.get("v2022") or []
    r_old = spearman(_arr(old, "g_s"), _arr(old, "r3")) if old else None
    r_new = spearman(_arr(new, "g_s"), _arr(new, "r3")) if new else None
    d, lo, hi = fisher_z_diff_ci(r_old, len(old), r_new, len(new))
    t3_out = {"rho_old": r_old, "n_old": len(old), "rho_2022": r_new, "n_2022": len(new),
              "z_diff": d, "lo95": lo, "hi95": hi}
    t4_out: dict = {}
    for side in SIDES:
        for V, arms in sorted(((data.get("t4") or {}).get(side) or {}).items()):
            aug, inc, twin = arms.get("aug") or [], arms.get("inc") or [], arms.get("twin") or []
            if not aug or len(aug) != len(inc):
                continue
            a, b, y = _arr(aug, "score"), _arr(inc, "score"), _arr(aug, "r3")
            pl, cl = [r.get("player") for r in aug], [r.get("club") for r in aug]

            def delta(i, a=a, b=b, y=y):
                ra, rb = spearman(a[i], y[i]), spearman(b[i], y[i])
                return None if ra is None or rb is None else ra - rb
            c = cell(delta, len(aug), pl, cl, B=B)
            cells[f"T4|{side}|{V}|aug_minus_inc"] = c
            tw = None
            if twin and len(twin) == len(aug):
                t = _arr(twin, "score")

                def dtwin(i, a=a, t=t, y=y):
                    ra, rt = spearman(a[i], y[i]), spearman(t[i], y[i])
                    return None if ra is None or rt is None else ra - rt
                tw = cell(dtwin, len(aug), pl, cl, B=B)
                cells[f"T4|{side}|{V}|real_minus_twin"] = tw
            t4_out[f"{side}|{V}"] = t4_verdict(c.get("point"), c.get("hi95"),
                                                (tw or {}).get("lo95"))
    verdicts = {"T1": t1_verdict(t1_lo),
                "T2": ("PASS" if t2_out and not t2_fail else
                       f"FAIL ({len(t2_fail)} driver cells)" if t2_out else "NA"),
                "T3": t3_verdict(lo, hi),
                "T4": ("HARM" if any(v["harm"] for v in t4_out.values()) else
                       "not shown harmful, unpowered") if t4_out else "NA"}
    return {"cells": cells, "t2": t2_out, "t2_failures": t2_fail, "t3": t3_out,
            "t4": t4_out, "verdicts": verdicts}


# ---------------------------------------------------------------------------
# preconditions and pins
# ---------------------------------------------------------------------------

def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def registered_sha() -> str | None:
    """The newest commit touching the gate file whose tree marks it REGISTERED and that
    is an ancestor of HEAD; None while no such commit exists."""
    log = _git("log", "--format=%H", "--", G.SURROGATE_GATE_DOC) or ""
    for sha in log.split():
        if G.gate_sha_committed_for(sha, G.SURROGATE_GATE_DOC):
            return sha
    return None


def stored_read(data_dir: Path = DATA_DIR) -> dict | None:
    p = Path(data_dir) / ARTIFACT
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    blk = doc.get(READ_KEY) if isinstance(doc, dict) else None
    return blk if isinstance(blk, dict) and blk else None


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def input_pins(data_dir: Path = DATA_DIR) -> dict:
    """sha256 of every pinned data file and the HEAD git blob of every pinned module
    (never a working-tree sha256 of code, which drifts with CRLF)."""
    files = {n: _sha256(Path(data_dir) / n) for n in PINNED_FILES}
    blobs = {n: _git("rev-parse", f"HEAD:./{n}") for n in PINNED_BLOBS}
    return {"files": files, "blobs": blobs}


def busy_processes() -> list[str]:
    """The nightly, a pipeline or a test session running beside this process."""
    from tools import dvm_difficulty_lab as dvm  # noqa: PLC0415  the shared lister
    return dvm.busy_processes()


def preflight(*, data_dir: Path = DATA_DIR, today: str | None = None,
              check_busy: bool = True) -> dict:
    """Every refusal that comes before any read. Returns the run's context or raises
    LookRefused."""
    if stored_read(data_dir) is not None:
        raise LookRefused(f"data/{ARTIFACT} already carries the {READ_KEY} read; "
                          "no second look runs (s5 kill rule 2)")
    marker = CACHE_DIR / G.LOOK_MARKER
    if marker.exists():
        raise LookRefused(f"{marker} records a look that began scoring and wrote no "
                          "result; the owner question it left is pending. No rerun.")
    sha = registered_sha()
    if sha is None:
        raise LookRefused(f"{G.SURROGATE_GATE_DOC} has no REGISTERED commit that is an "
                          "ancestor of HEAD; the runner refuses without it (Q7)")
    try:
        G.blocked_day(today)
    except G.BlockedDayError as exc:
        raise LookRefused(str(exc)) from exc
    if check_busy:
        busy = busy_processes()
        if busy:
            raise LookRefused("the nightly, a pipeline or a test session is running: "
                              + "; ".join(busy))
    G.require_eta_look()
    records = G.look_records()
    if G.LOOK_1 not in records:
        raise LookRefused("R-VM look 1 has no record (Q8); V 2022 cannot be read")
    return {"gate_sha": sha, "look_records": sorted(records),
            "today": today or date.today().isoformat()}


# ---------------------------------------------------------------------------
# assembly from the real stores (SG_8 runs this; the tests never do)
# ---------------------------------------------------------------------------

def _within_pct(vals: list[float | None], groups: list) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    by: dict = {}
    for i, (v, g) in enumerate(zip(vals, groups)):
        if v is not None:
            by.setdefault(g, []).append(i)
    for idx in by.values():
        x = np.asarray([vals[i] for i in idx], float)
        r = _ranks(x)
        for k, i in enumerate(idx):
            out[i] = float((r[k] + 0.5) / len(idx))
    return out


def assemble_drivers(ctx: dict) -> dict:
    """STEP 1, no outcome: the frames and their V2 rows (drivers and consensus) for
    every vintage the read takes."""
    import efv_vintage_frame as F  # noqa: PLC0415
    import efv_v2_model as M  # noqa: PLC0415
    uni = F.load_universe()
    sha = ctx["gate_sha"]
    frames: dict = {}
    v2rows: dict = {}
    for side in SIDES:
        frames[side], v2rows[side] = {}, []
        for V in G_S_VINTAGES + (T3_VINTAGE,):
            G.guard_surrogate_read(V, gate_sha=sha, look_records=ctx["look_records"],
                                   purpose=PURPOSE)
            rows = F.build_frame(side, V, gate_sha=sha, universe=uni)
            frames[side][V] = rows
            v2rows[side].extend(M.lv_v2_rows(side, V, rows, gate_sha=sha))
    return {"universe": uni, "frames": frames, "v2rows": v2rows}


def assemble_outcomes(ctx: dict, drv: dict) -> dict:
    """STEP 2, after the marker: the builder's outcomes, the labels, S_idx, g_S and the
    T4 emulation, joined into score_transfer's input."""
    import efv_labels as L  # noqa: PLC0415
    import efv_surrogate as S  # noqa: PLC0415
    import efv_v2_model as M  # noqa: PLC0415
    sha, recs = ctx["gate_sha"], ctx["look_records"]
    uni, frames = drv["universe"], drv["frames"]
    war = L.war_seasons_table()
    data: dict = {"t1": {}, "t2": {}, "t3": {"old": [], "v2022": []}, "t4": {}}
    seen_old: set = set()
    seen_new: set = set()
    for side in SIDES:
        built, labs = {}, {}
        for V, rows in frames[side].items():
            built[V] = S.build_outcomes(side, V, rows, gate_sha=sha, look_records=recs,
                                        purpose=PURPOSE, universe=uni)
            labs[V] = {lb["player_key"]: lb for lb in
                       L.labels_for_frame(rows, universe=uni, war=war, gate_sha=sha)}
        fit_rows = [r for V in FIT_VINTAGES for r in built[V]]
        maps = S.fit_maps(fit_rows, side, gate_sha=sha, look_records=recs)
        comp = {V: S.apply_maps(built[V], maps, gate_sha=sha, look_records=recs,
                                purpose=PURPOSE) for V in built}
        cons = {(r["player_key"], r["decision_year"]): r["fv"] for r in drv["v2rows"][side]}
        v2 = {(r["player_key"], r["decision_year"]): r for r in drv["v2rows"][side]}
        # T1: S_idx out of sample against the L6 percentile within (side, V)
        t1_rows = []
        for V in FIT_VINTAGES:
            keys = [r["player_key"] for r in comp[V]]
            l6 = [labs[V][k].get("l6") if labs[V][k].get("status") == "ok" else None
                  for k in keys]
            pct = _within_pct(l6, [V] * len(keys))
            for r, p, k in zip(comp[V], pct, keys):
                lab = labs[V][k]
                r["target"], r["weight"] = p, lab.get("l6_weight") or 1.0
                r["_resolved"] = lab.get("l6_censored") is False
        fit_in = [r for V in FIT_VINTAGES for r in comp[V]]
        model = S.fit_s_idx(fit_in, side, gate_sha=sha, look_records=recs)
        by_key = {(r["player_key"], int(r["vintage"])): r for r in fit_in}
        for (pk, V), pred in zip(model["keys"], model["oos"]):
            r = by_key[(pk, V)]
            t1_rows.append({"s_idx_oos": pred, "l6_pct": r["target"],
                            "resolved": r["_resolved"], "player": pk,
                            "club": r.get("org") or S.ORG_UNKNOWN, "vintage": V})
        data["t1"][side] = t1_rows
        # T2: g_S forward-chained against R3, with u_c and the drivers
        gs_in = []
        for V in G_S_VINTAGES:
            for r in comp[V]:
                r3 = labs[V][r["player_key"]].get("r3")
                gs_in.append(dict(r, reached=r3))
        gs = S.fit_g_s(gs_in, side, gate_sha=sha, look_records=recs, train_through=2019)
        gs_by = {(pk, V): p for (pk, V), p in zip(gs["keys"], gs["forward"])}
        t2_rows = []
        for r in gs_in:
            k = (r["player_key"], int(r["vintage"]))
            if r.get("reached") is None or k not in cons or gs_by.get(k) is None:
                continue
            row = {"g_s": gs_by[k], "r3": r["reached"], "u_c": cons[k],
                   "vintage": k[1], "player": k[0]}
            for d in T2_MILB_DRIVERS + T2_OTHER_DRIVERS:
                row[d] = (v2[k].get("v2") or {}).get(d)
            t2_rows.append(row)
        data["t2"][side] = t2_rows
        # T3: g_S on V 2011-2019 (forward) against V 2022 (the full fit), one row per player
        for row in t2_rows:
            if row["player"] not in seen_old:
                seen_old.add(row["player"])
                data["t3"]["old"].append({"g_s": row["g_s"], "r3": row["r3"]})
        fit = gs.get("fit")
        if fit is not None:
            new = [r for r in comp[T3_VINTAGE]
                   if labs[T3_VINTAGE][r["player_key"]].get("r3") is not None
                   and r.get("id_resolved")]
            if new:
                p = S._logit_predict(fit, S._design(new, S.FEATURES[side]))
                for r, pv in zip(new, p):
                    if r["player_key"] not in seen_new:
                        seen_new.add(r["player_key"])
                        data["t3"]["v2022"].append(
                            {"g_s": float(pv), "r3": labs[T3_VINTAGE][r["player_key"]]["r3"]})
        # T4: the S-only regime emulated against the incumbent timing head
        data["t4"][side] = _t4_arms(side, ctx, frames[side], labs, comp, cons, war, M, S)
    return data


def _t4_arms(side, ctx, frames, labs, comp, cons, war, M, S) -> dict:
    """For each V in 2017-2019: R3 masked on V-3..V-1 and imputed by g_S fitted through
    V-4; the timing head trained on resolved plus imputed rows (aug), on resolved rows
    (inc) and on a within-vintage permuted S (twin); each scored on V's rows."""
    import efv_vintage_frame as F  # noqa: PLC0415,F401
    sha, recs = ctx["gate_sha"], ctx["look_records"]
    out = {}
    rng = np.random.default_rng(PERM_SEED)
    for V in T4_EVAL_VINTAGES:
        train_v = [v for v in G_S_VINTAGES if v < V]
        fr = {v: (frames[v], [labs[v][r["player_key"]] for r in frames[v]]) for v in train_v}
        base = M.lv_training_rows(side, fr, gate_sha=sha)
        imp_in = [dict(r, reached=labs[v][r["player_key"]].get("r3"))
                  for v in train_v if v <= V - 4 for r in comp[v]]
        g = S.fit_g_s(imp_in, side, gate_sha=sha, look_records=recs,
                      train_through=V - 4).get("fit")
        if g is None:
            continue

        def imputed(permute: bool):
            rows = []
            for v in range(V - 3, V):
                cr = [r for r in comp[v] if r.get("id_resolved")]
                if not cr:
                    continue
                X = S._design(cr, S.FEATURES[side])
                if permute:
                    X = X[rng.permutation(len(cr))]
                p = S._logit_predict(g, X)
                imp = {r["player_key"]: float(pv) for r, pv in zip(cr, p)}
                for r in M.lv_v2_rows(side, v, frames[v], gate_sha=sha):
                    if r["player_key"] in imp:
                        rows.append(dict(r, reached=imp[r["player_key"]], weight=1.0,
                                         target=0.0))
            return rows
        masked = [r for r in base if r["decision_year"] < V - 3]
        inc_head = M.fit_timing_head([r for r in base if r["decision_year"] < V - 3]
                                     + [r for r in base if V - 3 <= r["decision_year"] < V
                                        and r.get("reached") is not None], side)
        aug_head = M.fit_timing_head(masked + imputed(False), side)
        twin_head = M.fit_timing_head(masked + imputed(True), side)
        ev = [r for r in M.lv_v2_rows(side, V, frames[V], gate_sha=sha)
              if labs[V][r["player_key"]].get("r3") is not None]
        y = [labs[V][r["player_key"]]["r3"] for r in ev]
        club = {r["player_key"]: r.get("org") or S.ORG_UNKNOWN for r in comp[V]}

        def arm(head):
            sc = M.z_time(head, ev)
            return [{"score": float(s), "r3": yy, "player": r["player_key"],
                     "club": club.get(r["player_key"], S.ORG_UNKNOWN)}
                    for s, yy, r in zip(sc, y, ev)]
        out[V] = {"aug": arm(aug_head), "inc": arm(inc_head), "twin": arm(twin_head)}
    return out


# ---------------------------------------------------------------------------
# the one look
# ---------------------------------------------------------------------------

class _Tee:
    def __init__(self, stream, path: Path):
        self.stream = stream
        self.f = open(path, "a", encoding="utf-8")

    def write(self, s):
        self.stream.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.stream.flush()
        self.f.flush()


def _owner_question(task_dir: Path, title: str, body: str) -> None:
    (Path(task_dir) / "OWNER_QUESTION.md").write_text(f"# {title}\n\n{body}\n",
                                                      encoding="utf-8")


def run_look(task_dir: Path, *, today: str | None = None, data_dir: Path = DATA_DIR,
             B: int = BOOT_B, check_busy: bool = True,
             _assemble_drivers=assemble_drivers,
             _assemble_outcomes=assemble_outcomes) -> int:
    """THE ONE S3 LOOK. Tees first; refuses by preflight(); checks T2's driver variance
    before any outcome (a STOP spends nothing); pins at start and end; marks the look
    spent when scoring begins; on an exception after that, writes OWNER_QUESTION.md and
    STOPs without rerunning."""
    task_dir = Path(task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    out, err = sys.stdout, sys.stderr
    sys.stdout = _Tee(out, task_dir / "look_stdout.txt")
    sys.stderr = _Tee(err, task_dir / "look_stderr.txt")
    try:
        return _look(task_dir, today=today, data_dir=data_dir, B=B, check_busy=check_busy,
                     assemble_d=_assemble_drivers, assemble_o=_assemble_outcomes)
    finally:
        for t in (sys.stdout, sys.stderr):
            if isinstance(t, _Tee):
                t.f.close()
        sys.stdout, sys.stderr = out, err


def _look(task_dir, *, today, data_dir, B, check_busy, assemble_d, assemble_o) -> int:
    try:
        ctx = preflight(data_dir=data_dir, today=today, check_busy=check_busy)
    except LookRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(f"gate {G.SURROGATE_GATE_DOC} REGISTERED at {ctx['gate_sha']}; "
          f"records {ctx['look_records']}; run day {ctx['today']} (no calendar day "
          "blocks, EW3-5)")
    pins_start = input_pins(data_dir)
    drv = assemble_d(ctx)
    bad = driver_variance_check(drv["v2rows"])
    if bad:
        _owner_question(task_dir, "Surrogate S3 look stopped before scoring: constant drivers",
                        "T2's variance check found drivers constant within a scored split: "
                        + ", ".join(bad) + ". No outcome was read and no look is spent; the "
                        "handling goes to a dated amendment written from this check alone.")
        print("STOPPED (registration error, no look spent): " + ", ".join(bad))
        return 3
    marker = CACHE_DIR / G.LOOK_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"started": _now(), "read": READ_KEY,
                                  "gate_sha": ctx["gate_sha"]}), encoding="utf-8")
    try:
        data = assemble_o(ctx, drv)
        block = score_transfer(data, B=B)
        pins_end = input_pins(data_dir)
        if pins_end != pins_start:
            raise RuntimeError("an input moved during the look (s5 kill rule 5)")
        early = "OWNER-WAIVED EARLY READ (EW3-5)"
        block["receipt"] = {"generated_at": _now(), "today": ctx["today"],
                            "gate_sha": ctx["gate_sha"], "look_records": ctx["look_records"],
                            "purpose": PURPOSE, "B": B, "seed": BOOT_SEED,
                            "input_pins": {"start": pins_start, "end": pins_end},
                            "note": early}
        for line in report_lines(block):
            print(line)
        p = Path(data_dir) / ARTIFACT
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        doc = {"generated_at": block["receipt"]["generated_at"], **doc,
               READ_KEY: clean_json(block)}
        p.write_text(json.dumps(clean_json(doc), indent=1, allow_nan=False),
                     encoding="utf-8")
        return 0
    except Exception as exc:
        _owner_question(task_dir, "Surrogate S3 look crashed after scoring began",
                        f"{type(exc).__name__}: {exc}\n\nThe look is not rerun (Q7, the "
                        f"one-look crash protocol). The marker {marker} keeps it spent until "
                        "the owner decides.")
        raise


# ---------------------------------------------------------------------------
# fixtures and the dry run (never writes data/)
# ---------------------------------------------------------------------------

def fixture_data(n: int = 240, seed: int = 7, *, nulls: bool = True) -> dict:
    """Synthetic score_transfer input with None and NaN in every printed column."""
    rng = np.random.default_rng(seed)

    def t1(side):
        rows = []
        for i in range(n):
            s = float(rng.normal())
            rows.append({"s_idx_oos": s, "l6_pct": float(s + rng.normal(scale=0.6)),
                         "resolved": bool(i % 3), "player": f"{side}{i}",
                         "club": f"c{i % 30}", "vintage": 2011 + i % 6})
        if nulls:
            rows[0]["s_idx_oos"], rows[1]["l6_pct"] = None, float("nan")
        return rows

    def t2(side):
        rows = []
        for i in range(n):
            u = float(rng.normal())
            d = {k: float(rng.normal()) for k in T2_MILB_DRIVERS + T2_OTHER_DRIVERS}
            lin = 0.8 * u + 0.4 * d["level_rank"]
            r3 = float(rng.random() < 1 / (1 + math.exp(-lin)))
            rows.append(dict(d, g_s=1 / (1 + math.exp(-lin)), r3=r3, u_c=u,
                             vintage=2011 + i % 9, player=f"{side}{i}"))
        if nulls:
            rows[2]["g_s"], rows[3]["u_c"] = None, float("nan")
        return rows

    def t4(side):
        out = {}
        for V in T4_EVAL_VINTAGES:
            y = [float(rng.random() < 0.3) for _ in range(n)]
            base = [float(v + rng.normal()) for v in y]
            mk = lambda sc: [{"score": s, "r3": yy, "player": f"{side}{i}",  # noqa: E731
                              "club": f"c{i % 30}"} for i, (s, yy) in enumerate(zip(sc, y))]
            out[V] = {"aug": mk(base), "inc": mk([b + float(rng.normal(scale=0.2)) for b in base]),
                      "twin": mk(list(rng.normal(size=n)))}
        return out
    old = [{"g_s": float(x), "r3": float(x + rng.normal() > 0)} for x in rng.normal(size=n)]
    new = [{"g_s": float(x), "r3": float(x + rng.normal() > 0)} for x in rng.normal(size=n // 2)]
    if nulls:
        old[0]["g_s"] = None
    return {"t1": {s: t1(s) for s in SIDES}, "t2": {s: t2(s) for s in SIDES},
            "t3": {"old": old, "v2022": new}, "t4": {s: t4(s) for s in SIDES}}


def run_dry(out_dir: Path, *, B: int = 50) -> dict:
    """The reporting path end to end on fixtures with nulls, written to out_dir only."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    block = score_transfer(fixture_data(), B=B)
    block["receipt"] = {"generated_at": _now(), "fixture": True}
    (out_dir / "dry_run.json").write_text(
        json.dumps(clean_json(block), indent=1, allow_nan=False), encoding="utf-8")
    (out_dir / "dry_run.txt").write_text("\n".join(report_lines(block)) + "\n",
                                         encoding="utf-8")
    return block


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--look", metavar="TASK_DIR", help="run THE ONE S3 look")
    g.add_argument("--dry-run", metavar="OUT_DIR", help="fixtures only; never data/")
    g.add_argument("--preflight", action="store_true", help="the refusals only")
    a = ap.parse_args(argv)
    if a.dry_run:
        run_dry(Path(a.dry_run))
        return 0
    if a.preflight:
        try:
            print(json.dumps(preflight(), indent=1))
            return 0
        except LookRefused as exc:
            print(f"REFUSED: {exc}")
            return 2
    return run_look(Path(a.look))


if __name__ == "__main__":
    raise SystemExit(main())

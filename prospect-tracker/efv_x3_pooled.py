# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV X3: one pooled model in place of the cell drivers (EFV_X3_POOLED_MODEL; owner
decisions EW3-12, EW3-13, EW3-21, EW3-26, EW3-35, EW3-41, EW3-42; method
docs/efv-v2/EFV_X3_POOLED_MODEL.md, committed alone (56d6879d) before this module).

THE MODEL (registration sections 4 and 5). Consensus is the anchor; every stage models the
outcome given consensus:

    E[L6 | x] = P(reach | x) * sum over k = 0..5 of max(0, E[PT_k | x, reach]) * E[rate_k | x, play]

Stage R is R3 on list-vintage instances; stages T and Q read the season panel of every
reached training instance (observed seasons only: censoring-aware). Two classes are fitted in
every fold: (a) a hierarchical ridge (global, side and group slopes, the deviations penalized
four times harder) and (b) LightGBM started from the anchor-only fit with monotone
constraints. Nested selection inside each forward-chained development fold picks the
configuration. The expert components of EW3-42 (censoring, a control-function survivorship
term, consensus as a noisy measurement, covariate-shift weights toward the live board, the
pitcher role path, conformal intervals) each carry a null comparator and a planted check.

THE READ (sections 7 to 9). The pooled within (frame, side, year) Spearman of X3 minus PROSPX
consensus over lv_dev and vm_dev (EFV_BEAT_POOLED_POWER's estimand), B 4000, seed 20261020,
player- and club-clustered, beside the served eFV, v5 COMBINED and V2; the null reruns and
the planted feature of clauses (C) and (D).

THE SWITCH. EFV_X3_ON is False. Nothing here serves: a dark build exists only after a PASS of
section 9, and only the owner flips it.

RESERVED FRAMES. No list vintage 2020 or 2021, no debut cohort 2025 or later is built, scored or
used to select (guards() raises first). backtest.run_backtest is never called.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only groups are frame, side, year, fold,
hitter position group, pitcher usage role and outcome classes cut on WAR. Consensus enters as a
within-group percentile, a raw grade in the shift classifier and a rater. Nothing here groups,
counts or averages rows by consensus-FV level; test_efv_x3_pooled.py scans this source.

Run:  python efv_x3_pooled.py --prep --cache <dir>   (instances and fold eTools, no statistic)
      python efv_x3_pooled.py --run --cache <dir>    (the registered read, once)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import efv_vintage_frame as F  # noqa: E402

#: THE SWITCH. False: nothing here serves. Only the owner flips it, after a PASS.
EFV_X3_ON = False

ITEM = "EFV_X3_POOLED_MODEL"
TOOL = "efv_x3_pooled.py"
DOC = "docs/efv-v2/EFV_X3_POOLED_MODEL.md"
RESULTS_DOC = "docs/efv-v2/EFV_X3_POOLED_MODEL_RESULTS.md"
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "_labs" / "efv_x3" / "efv_x3_pooled.json"
LEDGER_MODEL_ID = "efv_x3_pooled"
#: The registration commit (the document alone, before this module).
REGISTRATION_COMMIT = "56d6879d"

SIDES = ("hit", "pit")
FRAMES = ("lv_dev", "vm_dev")
LV_FIRST, LV_LAST = 2011, 2019
RESOLVED = 2026
LIVE_BOARD_YEAR = 2027
LIVE_READ_SEASON = 2026
#: section 7.3 and 9
B = 4000
SEED = 20261020
NULL_SEEDS = tuple(range(20261021, 20261041))
PLANT_SEED = 20261041
PLANT_RHO = 0.20
MAX_TRAIL = 0.005
#: section 3.1
COVER_MIN = 0.20
#: section 5
LAM_GRID = (1.0, 3.0, 10.0, 30.0, 100.0)
KAPPA = 4.0
TREES = (50, 100, 200)
GBM_PARAMS = {"num_leaves": 7, "learning_rate": 0.05, "min_data_in_leaf": 40,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
              "lambda_l2": 1.0, "num_threads": 2, "seed": SEED, "deterministic": True,
              "force_col_wise": True, "verbose": -1}
MIN_GROUP = 20
#: section 4.2
PT_SCALE = {"hit": 600.0, "pit": 700.0}
SEASONS_K = 6
#: harness default (named): the 2020 season is not a panel row (the EFV_X1 sport-1 cache
#: skips the 60-game season); the role label reads 2020 from milb_history's sport-1 splits.
PANEL_SKIP_SEASONS = frozenset({2020})
#: section 6
CROSSFIT_K = 5
SHIFT_RIDGE = 1.0
ROLE_RIDGE = 1.0
W_CLIP = 10.0
ESS_MIN = 0.30
CONF_NOMINAL = 0.80
CONF_BAND = (0.75, 0.85)
PIT_BAND = (0.05, 0.15)

# ---------------------------------------------------------------------------
# the features (section 3, fixed by the registration)
# ---------------------------------------------------------------------------

FEATURES: dict[str, tuple[str, ...]] = {
    "hit": ("e_hit", "e_pow", "e_sel", "e_bat", "c_speed", "c_field", "c_raw_pwr",
            "x1_obp_rw", "x1_woba_rw", "x1_woba_yoy", "x1_age_rel_level", "level_rank",
            "age", "pick_overall", "is_ifa", "is_college", "x2_options", "x2_trades",
            "x2_r5_selected", "ppa_raw", "ppa_par", "lam", "fv_stddev", "pos_prem"),
    "pit": ("e_fb", "e_cmd", "c_best_sec", "arsenal_depth", "x1_hr9_rw", "x1_gb_rw",
            "x1_age_rel_level", "level_rank", "age", "pick_overall", "is_college",
            "x2_options", "x2_trades", "x2_r5_selected", "pbf_raw", "pbf_par", "pip_raw",
            "pip_par", "gs_share", "ip_per_g", "workload", "p_rel", "p_rel_x_uc", "lam",
            "fv_stddev"),
}
#: section 3.4 and 13.7: eRAW and eSPD in place of items 7 and 5 (hitters), sensitivity only
SENSITIVITY_SWAP = {"c_raw_pwr": "e_raw", "c_speed": "e_spd"}
#: section 5 (a): a feature on both lists carries a global slope and side deviations
SHARED = tuple(f for f in FEATURES["hit"] if f in FEATURES["pit"])
#: the eTool of each eTool feature (efv_etools_reweight's tool names)
ETOOL_OF = {"e_hit": "hit", "e_pow": "game_pwr", "e_sel": "pitch_sel", "e_bat": "bat_ctrl",
            "e_fb": "fb", "e_cmd": "cmd", "e_raw": "raw_pwr", "e_spd": "speed"}
ETOOL_SIDE = {"hit": "hit", "game_pwr": "hit", "pitch_sel": "hit", "bat_ctrl": "hit",
              "raw_pwr": "hit", "speed": "hit", "fb": "pit", "cmd": "pit"}
#: section 3.2 item 1, 3.3 item 1 (amendment 1 A2): eHIT and eFB on their reduced sets; the
#: other eTools keep the look's admitted sets.
ETOOL_SUBDRIVERS: dict[str, tuple[str, ...]] = {
    "hit": ("k_rw", "babip_rw"),
    "game_pwr": ("iso_rw", "bb_fb"),
    "pitch_sel": ("pbp_swing",),
    "bat_ctrl": ("pbp_contact",),
    "fb": ("k_rw", "pbf_raw"),
    "cmd": ("bb_rw", "pbp_fstrike", "pbf_par"),
    "raw_pwr": ("iso_rw",),
    "speed": ("sb_rel",),
}
#: features rebuilt inside each fold
FOLD_FEATURES = frozenset({"e_hit", "e_pow", "e_sel", "e_bat", "e_fb", "e_cmd", "e_raw",
                           "e_spd", "lam", "p_rel", "p_rel_x_uc"})
#: 0/1 features are not z-scored
BINARY = frozenset({"is_ifa", "is_college", "x2_r5_selected", "pos_prem"})
#: section 5 (b): monotone directions where known (u_c +1; eTools and consensus tool grades
#: +1; age and age relative to level -1; 0 elsewhere)
MONO_UP = frozenset({"e_hit", "e_pow", "e_sel", "e_bat", "e_fb", "e_cmd", "e_raw", "e_spd",
                     "c_speed", "c_field", "c_raw_pwr", "c_best_sec"})
MONO_DOWN = frozenset({"age", "x1_age_rel_level"})
PITCH_RATES = {"hit": ("ppa_raw", "ppa_par"), "pit": ("pbf_raw", "pbf_par", "pip_raw", "pip_par")}
#: plain-English labels (card driver chips after a PASS; reports)
LABELS = {
    "e_hit": "Hit tool (eTool)", "e_pow": "Game power (eTool)", "e_sel": "Pitch selection (eTool)",
    "e_bat": "Bat control (eTool)", "e_fb": "Fastball (eTool)", "e_cmd": "Command (eTool)",
    "e_raw": "Raw power (eTool)", "e_spd": "Speed (eTool)",
    "c_speed": "Run grade", "c_field": "Field grade", "c_raw_pwr": "Raw power grade",
    "c_best_sec": "Best secondary pitch grade", "arsenal_depth": "Pitches graded 55 or better",
    "x1_obp_rw": "On-base rate, translated", "x1_woba_rw": "wOBA, translated",
    "x1_woba_yoy": "wOBA change from last season", "x1_age_rel_level": "Age for level",
    "x1_hr9_rw": "Home runs per nine, translated", "x1_gb_rw": "Ground-ball rate, translated",
    "level_rank": "Level reached", "age": "Age", "pick_overall": "Draft pick",
    "is_ifa": "International signing", "is_college": "College draftee",
    "x2_options": "Options used", "x2_trades": "Times traded",
    "x2_r5_selected": "Taken in the Rule 5 draft", "ppa_raw": "Pitches per PA",
    "ppa_par": "Pitches per PA for level", "pbf_raw": "Pitches per batter",
    "pbf_par": "Pitches per batter for level and role", "pip_raw": "Pitches per inning",
    "pip_par": "Pitches per inning for level and role", "gs_share": "Share of games started",
    "ip_per_g": "Innings per appearance", "workload": "Innings this season",
    "p_rel": "Chance he ends in relief", "p_rel_x_uc": "Relief chance times consensus",
    "lam": "Agreement among graders", "fv_stddev": "Grader disagreement",
    "pos_prem": "Premium position", "planted": "Planted check feature"}
#: section 6.5 and 5 (a): the pitcher usage roles and the hitter position groups
ROLES = ("STARTER", "SHORT-START", "RELIEF", "OTHER")
HIT_GROUPS = ("C", "SS", "CF", "IF", "COF", "1B/DH")
GROUPS = tuple(f"hit:{g}" for g in HIT_GROUPS) + tuple(f"pit:{r}" for r in ROLES)
KINDS = ("LV", "MTX", "PIN", "LIVE")

_LOG = print


class GuardError(RuntimeError):
    pass


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _sha(path: Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def features_of(side: str, sensitivity: bool = False) -> tuple[str, ...]:
    out = FEATURES[side]
    if sensitivity and side == "hit":
        out = tuple(SENSITIVITY_SWAP.get(f, f) for f in out)
    return out


def pos_group(position) -> str | None:
    """The listing position's first token, as efv_upside_volatility groups hitters."""
    import efv_upside_volatility as UV
    tok = str(position or "").replace("-", "/").replace(",", "/").split("/")[0].strip().upper()
    return UV.POS_GROUP.get(tok)


def role_of(u: dict | None) -> str:
    r = (u or {}).get("role")
    return r if r in ("STARTER", "SHORT-START", "RELIEF") else "OTHER"


# ---------------------------------------------------------------------------
# guards (section 11)
# ---------------------------------------------------------------------------

def guard_instance(kind: str, year: int, *, dev: bool = True) -> None:
    """Raise on a reserved row (R-LV, R-VM) or a row the development folds may not read."""
    y = int(year)
    if kind == "LV":
        if y in F.RESERVED_LV or y > LV_LAST or y < LV_FIRST:
            raise F.ReservedFrameError(f"list-vintage instance at {y}")
    elif kind in ("PIN", "MTX"):
        if dev and y >= F.R_VM_FIRST_DEBUT_YEAR:
            raise F.ReservedFrameError(f"{kind} instance at {y}, a reserved cohort")
    elif kind != "LIVE":
        raise ValueError(kind)


def guards(T: "Table") -> dict:
    n = {k: 0 for k in KINDS}
    for k, y in zip(T.kind.tolist(), T.year.tolist()):
        guard_instance(k, y)
        n[k] += 1
    return {"checked": n, "reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": int(F.R_VM_FIRST_DEBUT_YEAR)}


# ---------------------------------------------------------------------------
# small numerics
# ---------------------------------------------------------------------------

def pct_within(values, groups) -> np.ndarray:
    """Average-rank percentile within each group (efv_v2_model.within_pct)."""
    import efv_v2_model as H
    return np.asarray(H.within_pct(values, list(groups)), dtype=np.float64)


def ranks(a: np.ndarray) -> np.ndarray:
    import source_backtest as SB
    return SB._ranks_np(np, np.asarray(a, dtype=np.float64))


def spearman(a, b) -> float | None:
    import source_backtest as SB
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3:
        return None
    return SB._corr_np(np, ranks(a), ranks(b))


def within_spearman(score, y, groups, *, min_rows: int = MIN_GROUP) -> float | None:
    """Size-weighted within-group Spearman over groups of at least min_rows rows."""
    score = np.asarray(score, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    groups = np.asarray(groups)
    tot = n = 0.0
    for g in np.unique(groups):
        m = groups == g
        if m.sum() < min_rows:
            continue
        r = spearman(score[m], y[m])
        if r is None:
            continue
        tot += r * m.sum()
        n += m.sum()
    return tot / n if n else None


def norm_ppf(p):
    from scipy.stats import norm
    return norm.ppf(p)


def imr(p) -> np.ndarray:
    """The inverse Mills ratio phi(Phi^-1(p)) / p (section 6.2)."""
    from scipy.stats import norm
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-4, 1 - 1e-4)
    return norm.pdf(norm.ppf(p)) / p


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def wls(X: np.ndarray, y: np.ndarray, w: np.ndarray, pen: np.ndarray) -> np.ndarray:
    """argmin sum w (y - X b)^2 + sum pen b^2 (weights scaled to mean 1)."""
    w = np.asarray(w, dtype=np.float64)
    w = w / w.mean() if w.size and w.mean() > 0 else w
    Xw = X * w[:, None]
    A = X.T @ Xw
    A[np.diag_indices_from(A)] += pen + 1e-8
    return np.linalg.solve(A, Xw.T @ y)


def logistic(X: np.ndarray, y: np.ndarray, w: np.ndarray, pen: np.ndarray, *,
             b0: np.ndarray | None = None, iters: int = 30, tol: float = 1e-7) -> np.ndarray:
    """Penalized weighted logistic regression by Newton steps (weights scaled to mean 1)."""
    w = np.asarray(w, dtype=np.float64)
    w = w / w.mean() if w.size and w.mean() > 0 else w
    b = np.zeros(X.shape[1]) if b0 is None else np.array(b0, dtype=np.float64)
    P = np.diag(pen + 1e-8)

    def loss(bb):
        eta = np.clip(X @ bb, -30, 30)
        return float(np.sum(w * (np.logaddexp(0.0, eta) - y * eta)) + 0.5 * bb @ P @ bb)
    cur = loss(b)
    for _ in range(int(iters)):
        p = sigmoid(X @ b)
        g = X.T @ (w * (p - y)) + P @ b
        H = X.T @ (X * (w * p * (1 - p))[:, None]) + P
        step = np.linalg.solve(H, g)
        t = 1.0
        while True:
            nb = b - t * step
            nl = loss(nb)
            if nl <= cur + 1e-12 or t < 1e-4:
                break
            t *= 0.5
        b, done = nb, abs(cur - nl) < tol * (1.0 + abs(cur))
        cur = nl
        if done or float(np.max(np.abs(t * step))) < tol:
            break
    return b


def auc(score, y) -> float | None:
    score = np.asarray(score, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64) > 0.5
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return None
    r = ranks(score)
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


# ---------------------------------------------------------------------------
# the instance table (section 2.1)
# ---------------------------------------------------------------------------

class Table:
    """Every instance of both sides as arrays. feats: {name: float array, NaN = missing}
    (a side's array is NaN on the other side's rows). Labels never enter a feature."""

    def __init__(self, recs: list[dict]):
        self.n = len(recs)
        self.recs = recs
        g = lambda k, dt=None: np.asarray([r.get(k) for r in recs], dtype=dt)  # noqa: E731
        self.side = np.asarray([0 if r["side"] == "hit" else 1 for r in recs], dtype=np.int64)
        self.kind = g("kind", object)
        self.year = np.asarray([int(r["year"]) for r in recs], dtype=np.int64)
        self.pk = g("pk", object)
        self.fv = np.asarray([float(r["fv"]) for r in recs], dtype=np.float64)
        self.grp = g("group", object)
        self.n_src = np.asarray([max(1.0, _f(r.get("n_sources")) or 1.0) for r in recs])
        self.sd_src = np.asarray([_f(r.get("fv_stddev")) or 0.0 for r in recs])
        gkey = [f"{r['side']}|{r['kind']}|{int(r['year'])}" for r in recs]
        self.zgroup = np.asarray(gkey, dtype=object)
        self.u_c = pct_within(self.fv, gkey)
        names = sorted({f for s in SIDES for f in FEATURES[s]} | set(SENSITIVITY_SWAP.values()))
        self.base = {}
        for f in names:
            if f in FOLD_FEATURES:
                continue
            self.base[f] = np.asarray([np.nan if (v := _f((r.get("feats") or {}).get(f))) is None
                                       else v for r in recs], dtype=np.float64)
        lab = [r.get("labels") or {} for r in recs]
        lf = lambda k: np.asarray([np.nan if _f(x.get(k)) is None else _f(x.get(k))  # noqa: E731
                                   for x in lab], dtype=np.float64)
        self.r3 = lf("r3")
        self.w3 = lf("w3")
        self.l6 = lf("l6")
        self.l6w = lf("l6_weight")
        self.l6_fit = lf("l6_fit")
        self.l6_obs = np.asarray([bool(x.get("l6_observed")) for x in lab])
        self.y_pin = lf("y_pin")
        self.mtx_target = lf("mtx_target")
        self.mtx_weight = lf("mtx_weight")
        self.debut = np.asarray([int(x["d"]) if x.get("d") is not None else -1 for x in lab])
        self.cond = np.asarray([bool(x.get("cond")) for x in lab])
        self.role_y = lf("ends_reliever")
        self.panel = [x.get("panel") or [] for x in lab]
        self.panel_open = [x.get("panel_open") or [] for x in lab]
        self.meta = [r.get("etool_meta") for r in recs]
        self.index = {(r["kind"], r["side"], int(r["year"]), r["pk"]): i for i, r in enumerate(recs)}

    def side_name(self, i: int) -> str:
        return SIDES[int(self.side[i])]

    def plant_label(self) -> np.ndarray:
        """The label the planted feature of clause (D) correlates with: W3 (LV), the L6 target
        (MTX), career WAR to date (PIN); NaN elsewhere."""
        out = np.full(self.n, np.nan)
        out[self.kind == "LV"] = self.w3[self.kind == "LV"]
        out[self.kind == "MTX"] = self.mtx_target[self.kind == "MTX"]
        out[self.kind == "PIN"] = self.y_pin[self.kind == "PIN"]
        return out


def z_within(values: np.ndarray, groups: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """z-scores within each group on the rows that carry a value (NaN stays NaN)."""
    v = np.asarray(values, dtype=np.float64)
    out = np.full(v.size, np.nan)
    ok = np.isfinite(v) if mask is None else (np.isfinite(v) & mask)
    for g in np.unique(groups[ok]):
        m = ok & (groups == g)
        x = v[m]
        sd = x.std()
        out[m] = (x - x.mean()) / sd if sd > 0 else 0.0
    return out


# ---------------------------------------------------------------------------
# building the instances (sections 2 and 3; cached, no statistic)
# ---------------------------------------------------------------------------

def _mlb_lines(season: int, group: str) -> dict[int, dict]:
    """{mlbam: sport-1 season line} from the EFV_X1 cache (2020 from milb_history)."""
    import efv_x1_fetch as X
    import milb_history as mh
    rows = (mh.season_splits(1, int(season), group, fetch=False) if int(season) == 2020
            else X.load("players", group, 1, int(season)))
    out: dict = {}
    for r in rows or []:
        m = r.get("mlbam")
        if not m:
            continue
        a = out.setdefault(int(m), {"pa": 0.0, "bf": 0.0, "g": 0.0, "gs": 0.0})
        for k in a:
            a[k] += _f(r.get(k)) or 0.0
    return out


class MlbBook:
    def __init__(self):
        self.cache: dict = {}

    def line(self, season: int, side: str, mlbam) -> dict | None:
        key = (int(season), side)
        if key not in self.cache:
            self.cache[key] = _mlb_lines(int(season), "hitting" if side == "hit" else "pitching")
        try:
            return self.cache[key].get(int(mlbam))
        except (TypeError, ValueError):
            return None


def panel_rows(side: str, d: int, mlbam, war: dict | None, book: MlbBook) -> tuple[list, list]:
    """(observed panel rows [(k, PT_k, WAR_k)], unobserved k) for a debut in d (section 4.2)."""
    obs, open_ = [], []
    for k in range(SEASONS_K):
        s = int(d) + k
        if s in PANEL_SKIP_SEASONS:
            continue
        if s > RESOLVED:
            open_.append(k)
            continue
        ln = book.line(s, side, mlbam) if mlbam else None
        exp = (ln or {}).get("pa" if side == "hit" else "bf") or 0.0
        obs.append((k, float(exp) / PT_SCALE[side], float((war or {}).get(s, 0.0))))
    return obs, open_


def ends_reliever(d: int, mlbam, book: MlbBook) -> float | None:
    """1 when MLB games started are under half of MLB games over seasons d to d + 2 (at least 5
    MLB games), 0 when not, None under 5 games (section 6.5)."""
    g = gs = 0.0
    for s in range(int(d), int(d) + 3):
        if s > RESOLVED:
            break
        ln = book.line(s, "pit", mlbam) if mlbam else None
        if ln:
            g += ln["g"]
            gs += ln["gs"]
    if g < 5:
        return None
    return 1.0 if gs < 0.5 * g else 0.0


def _raw_tools(src: dict | None, side: str) -> dict:
    s = src or {}
    if side == "hit":
        return {k: _f(s.get(f"tool_{k}")) for k in ("hit", "game_pwr", "raw_pwr", "speed", "field")}
    return {k: _f(s.get(f"tool_{k}")) for k in ("fb", "cmd", "sl", "cb", "ch")}


def tool_features(side: str, raw: dict) -> dict:
    if side == "hit":
        return {"c_speed": raw.get("speed"), "c_field": raw.get("field"),
                "c_raw_pwr": raw.get("raw_pwr")}
    sec = [raw.get(k) for k in ("sl", "cb", "ch") if raw.get(k) is not None]
    obs = [raw.get(k) for k in ("fb", "sl", "cb", "ch") if raw.get(k) is not None]
    return {"c_best_sec": max(sec) if sec else None,
            "arsenal_depth": float(sum(1 for v in obs if v >= 55.0)) if obs else None}


def basic_features(feats: dict) -> dict:
    """Level, age, route and grader fields of the row's own feature view; a value the view
    imputes (its missing flag set) is missing here."""
    g = feats.get
    has_milb = not g("milb_unavailable") and not g("milb_missing")
    return {"level_rank": _f(g("level_rank")) if has_milb else None,
            "age": None if g("age_missing") else _f(g("age")),
            "pick_overall": None if g("pick_missing") else _f(g("pick_overall")),
            "is_ifa": _f(g("is_ifa")), "is_college": _f(g("is_college")),
            "pos_prem": _f(g("pos_prem")), "fv_stddev": _f(g("fv_stddev")) or 0.0}


class Builder:
    """Assembles the instance table from the cached builds (the re-fit's inputs as the
    tilted-labels read rebuilt them, the eTools re-weight's list-vintage frames, row contexts
    and eTools frame)."""

    def __init__(self, cache_dir: Path, *, today: str, log=print):
        self.cache = Path(cache_dir)
        self.today = today
        self.log = log
        self.receipts: dict = {"lookahead": {k: {"checks": 0, "latest_input": None} for k in KINDS}}

    def _pk(self, name: str):
        import efv_etools_reweight as ER
        import __main__
        # the re-weight's caches were written by its __main__ run
        for cls in ("Bank", "RowMeta"):
            if not hasattr(__main__, cls):
                setattr(__main__, cls, getattr(ER, cls))
        with (self.cache / name).open("rb") as fh:
            return pickle.load(fh)

    def _la(self, kind: str, read: str, latest: str | None) -> None:
        """Record a no-look-ahead check: every input dated at or before the read."""
        if latest is None:
            return
        if str(latest)[:10] > str(read)[:10]:
            raise AssertionError(f"look-ahead: {kind} input {latest} after its read {read}")
        r = self.receipts["lookahead"][kind]
        r["checks"] += 1
        if r["latest_input"] is None or str(latest)[:10] > r["latest_input"]:
            r["latest_input"] = str(latest)[:10]

    def build(self) -> dict:
        import efv_dataset as D
        import efv_labels as L
        import efv_reliever_adj as RA
        import efv_v2_serve as SV
        import efv_x1_translate as X1
        import efv_x2_revealed as X2
        import efv5_combined as V5C
        from efv_w2_milb import last_readable_season
        log = self.log
        t0 = time.time()
        b1 = self._pk("tilted_build1.pkl")
        inp = b1["inp"]
        er = self._pk("er/build.pkl")
        frames_lv = er["frames_lv"]
        rm, ctx_rec = self._pk("er/contexts.pkl")
        if ctx_rec["consistency"]["mismatch"]:
            raise RuntimeError("row contexts disagree with the rows' features")
        U = F.load_universe()
        war = L.war_seasons_table()
        raw_m = V5C._raw_by_side()
        pinned = {s: V5C._pinned_asof(s) for s in SIDES}
        recs_asof = D.asof_records()
        book = MlbBook()
        log(f"  inputs loaded ({round(time.time() - t0, 1)} s)")
        books_dev = X2.Books.load(last_year=F.R_VM_FIRST_DEBUT_YEAR - 1,
                                  date_cap=f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01", log=log)
        tomorrow = (date.fromisoformat(self.today).toordinal() + 1)
        books_live = X2.Books.load(last_year=LIVE_READ_SEASON,
                                   date_cap=date.fromordinal(tomorrow).isoformat(), log=log)
        out: list[dict] = []
        cnt: dict = {}

        def x1(side, mlbam, read_year, cutoff, kind):
            f = X1.features(mlbam, int(read_year), cutoff, side)
            if f.get("_seasons"):
                self._la(kind, X1.asof_date(int(read_year), cutoff),
                         f"{max(f['_seasons'])}{X1.SEASON_END_MMDD}")
            names = ("obp_rw", "woba_rw", "woba_yoy", "age_rel_level") if side == "hit" else (
                "hr9_rw", "gb_rw", "age_rel_level")
            return {f"x1_{k}": f.get(k) for k in names}

        def x2(side, pid, asof, birth, kind, books):
            vals, dates = X2.column_values(pid, asof, birth, side, books)
            ds = [d for d in dates.values() if d]
            if ds:
                # column_values asserts strictly before the read itself
                self._la(kind, str(asof)[:10], max(ds))
            return {k: vals.get(k) for k in ("x2_options", "x2_trades", "x2_r5_selected")}

        def usage(side, mlbam, read_year, cutoff, kind, asof):
            if side != "pit":
                return {}, None
            rs = last_readable_season(int(read_year), cutoff)
            if rs > int(read_year) - 1:
                raise AssertionError("usage reads a season after its read")
            self._la(kind, asof, f"{rs}-10-01")
            u = RA.usage(mlbam, rs)
            su = RA.season_usage(rs).get(int(mlbam)) if mlbam else None
            work = None if not mlbam else math.log1p((su[2] / 3.0) if su else 0.0)
            if u.get("role") in (RA.NO_LINE,) or not u.get("g"):
                return {"gs_share": None, "ip_per_g": None, "workload": work}, u
            return {"gs_share": u["gs_share"], "ip_per_g": u["ip_per_g"], "workload": work}, u

        def pitch_rates(side, meta, kind, read):
            if not meta or meta.get("pid") is None or meta.get("b") is None:
                return {k: None for k in PITCH_RATES[side]}
            self._la(kind, read, f"{int(meta['b']) - 1}-10-01")
            z = rm.Z.get((side, meta["pid"], meta["b"])) or {}
            return {k: _f(z.get(k)) for k in PITCH_RATES[side]}

        extra_meta = self._lv_extra_metas(b1, frames_lv, rm)
        for side in SIDES:
            # LV: every list-vintage row of the re-fit's lv_dev frame (vintages 2011 to 2019)
            lv_by = {}
            for V, (rows, labs) in frames_lv[side].items():
                if int(V) in F.RESERVED_LV:
                    raise F.ReservedFrameError(f"list vintage {V}")
                for r, lab in zip(rows, labs):
                    lv_by[(int(V), r["player_key"])] = (r, lab)
            # the re-fit's list-vintage pool (efv5_refit.lv_pool: every labelled list-vintage
            # row of 2011 to 2019, the lv_dev test rows among them)
            lv_rows = {(int(r["decision_year"]), r["player_key"]): r for r in b1["pool"][side]}
            for fold, blk in inp.frames["lv_dev"]["by_side"][side].items():
                for r in blk["test"]:
                    if (int(r["decision_year"]), r["player_key"]) not in lv_rows:
                        raise RuntimeError(f"lv_dev test row outside the pool: {r['player_key']}")
            for (V, pk), r in sorted(lv_rows.items()):
                guard_instance("LV", V)
                fr, lab = lv_by[(V, pk)]
                meta = rm.meta.get(("lv", side, V, pk)) or extra_meta.get((side, V, pk))
                cutoff = (fr.get("window") or [None])[0]
                asof = str(fr.get("asof_date") or f"{V}-01-01")[:10]
                feats = basic_features(r["feats"])
                raw = _raw_tools(fr.get("prior"), side)
                feats.update(tool_features(side, raw))
                feats.update(x1(side, fr.get("mlbam_id"), V, cutoff, "LV"))
                feats.update(x2(side, fr.get("mlbam_id"), asof, fr.get("birth_date"), "LV", books_dev))
                uf, u = usage(side, fr.get("mlbam_id"), V, cutoff, "LV", asof)
                feats.update(uf)
                feats.update(pitch_rates(side, meta, "LV", asof))
                rec_id = (U.get(pk) or {}).get("mlbam_id")
                labels = {"r3": lab.get("r3"), "w3": lab.get("w3"), "l6": lab.get("l6"),
                          "l6_weight": lab.get("l6_weight"),
                          # the L6 arm's fit label: the label's own censoring rule (the
                          # observed-rate tail projection, weight observed seasons / 6)
                          "l6_fit": (lab.get("l6_censored_target") if lab.get("l6_censored")
                                     else lab.get("l6")),
                          "l6_observed": lab.get("l6") is not None and lab.get("l6_censored") is False}
                if lab.get("r3") == 1.0 and lab.get("debut_year") is not None:
                    d = int(lab["debut_year"])
                    obs, open_ = panel_rows(side, d, rec_id, war.get(pk), book)
                    labels.update({"cond": True, "d": d, "panel": obs, "panel_open": open_})
                    if side == "pit":
                        labels["ends_reliever"] = ends_reliever(d, rec_id, book)
                out.append({"kind": "LV", "side": side, "year": V, "pk": pk, "fv": float(r["fv"]),
                            "n_sources": r["feats"].get("n_sources"),
                            "fv_stddev": r["feats"].get("fv_stddev"),
                            "group": (f"hit:{pos_group(fr.get('position'))}"
                                      if side == "hit" and pos_group(fr.get("position"))
                                      else (f"pit:{role_of(u)}" if side == "pit" else None)),
                            "feats": feats, "labels": labels,
                            "etool_meta": None if meta is None else dict(meta),
                            "read": asof})
            # MTX: the v1 matrix training rows the vm_dev folds train on (decision years to 2022)
            vm = inp.frames["vm_dev"]["by_side"][side]
            last = max(int(k) for k in vm)
            for r in vm[last]["train"]:
                dy, pk = int(r["decision_year"]), r["player_key"]
                guard_instance("MTX", dy)
                rw = raw_m[side].get(pk) or {}
                meta = rm.meta.get(("vm_train", side, dy, pk))
                cutoff = rw.get("cutoff")
                asof = str(rw.get("asof_date") or cutoff or f"{dy}-01-01")[:10]
                # the matrix row's decision point: its MiLB cutoff (the matrix features read
                # through it) or its consensus as-of, whichever is later; the club columns read
                # at the as-of (EFV_X2's rule), strictly earlier
                read = max(asof, str(cutoff or asof)[:10])
                feats = basic_features(r["feats"])
                feats.update(tool_features(side, _raw_tools(rw, side)))
                feats.update(x1(side, rw.get("mlbam_id"), dy, cutoff, "MTX"))
                feats.update(x2(side, rw.get("mlbam_id"), asof, rw.get("birth_date"), "MTX", books_dev))
                uf, u = usage(side, rw.get("mlbam_id"), dy, cutoff, "MTX", read)
                feats.update(uf)
                feats.update(pitch_rates(side, meta, "MTX", read))
                rec_id = (U.get(pk) or {}).get("mlbam_id")
                labels = {"mtx_target": r.get("target"), "mtx_weight": r.get("weight")}
                if r.get("kind") == "debuted":
                    obs, open_ = panel_rows(side, dy, rec_id, war.get(pk), book)
                    labels.update({"cond": True, "d": dy, "panel": obs, "panel_open": open_})
                    if side == "pit":
                        labels["ends_reliever"] = ends_reliever(dy, rec_id, book)
                out.append({"kind": "MTX", "side": side, "year": dy, "pk": pk, "fv": float(r["fv"]),
                            "n_sources": r["feats"].get("n_sources"),
                            "fv_stddev": r["feats"].get("fv_stddev"),
                            "group": (f"hit:{pos_group(rw.get('position'))}"
                                      if side == "hit" and pos_group(rw.get("position"))
                                      else (f"pit:{role_of(u)}" if side == "pit" else None)),
                            "feats": feats, "labels": labels,
                            "etool_meta": None if meta is None else dict(meta),
                            "read": read, "mtx_kind": r.get("kind")})
            # PIN: the vm_dev test rows at their pinned preseason read
            scored_vm = {(c["side"], int(c["year"]), c["key"]): c for c in inp.scored("vm_dev")}
            for fold, blk in vm.items():
                for r in blk["test"]:
                    dy, pk = int(r["decision_year"]), r["player_key"]
                    guard_instance("PIN", dy)
                    rw = raw_m[side].get(pk) or {}
                    meta = rm.meta.get(("vm_test", side, dy, pk))
                    cut = pinned[side].get(pk)
                    asof = str(cut or f"{dy}-01-01")[:10]
                    pre = D.preseason_consensus_asof(recs_asof.get(pk), dy, side) or {}
                    feats = basic_features(r["feats"])
                    feats.update(tool_features(side, _raw_tools(pre, side)))
                    feats.update(x1(side, rw.get("mlbam_id"), dy, cut, "PIN"))
                    feats.update(x2(side, rw.get("mlbam_id"), asof, rw.get("birth_date"), "PIN", books_dev))
                    uf, u = usage(side, rw.get("mlbam_id"), dy, cut, "PIN", asof)
                    feats.update(uf)
                    feats.update(pitch_rates(side, meta, "PIN", asof))
                    sc = scored_vm.get((side, dy, pk))
                    t6 = rw.get("target_resolved")
                    labels = {"y_pin": None if sc is None else float(sc["outcome"]["war"]),
                              "l6": t6, "l6_observed": t6 is not None and rw.get("censored") is False}
                    out.append({"kind": "PIN", "side": side, "year": dy, "pk": pk,
                                "fv": float(r["fv"]), "n_sources": r["feats"].get("n_sources"),
                                "fv_stddev": r["feats"].get("fv_stddev"),
                                "group": (f"hit:{pos_group(rw.get('position'))}"
                                          if side == "hit" and pos_group(rw.get("position"))
                                          else (f"pit:{role_of(u)}" if side == "pit" else None)),
                                "feats": feats, "labels": labels,
                                "etool_meta": None if meta is None else dict(meta),
                                "read": asof, "scored": sc is not None})
            # LIVE: the live board read today (the covariate-shift classifier's target)
            live = json.loads(D.live_matrix_path(side).read_text(encoding="utf-8"))
            live_by = {r["player_key"]: r for r in live}
            rows = SV.live_rows(side, live, today=self.today)
            served_et = json.loads((DATA_DIR / "etools.json").read_text(encoding="utf-8")).get("players") or {}
            for r in rows:
                pk = r["player_key"]
                lr = live_by.get(pk) or {}
                raw = _raw_tools(lr, side)
                feats = basic_features(r["feats"])
                feats.update(tool_features(side, raw))
                feats.update(x1(side, lr.get("mlbam_id"), LIVE_BOARD_YEAR, None, "LIVE"))
                feats.update(x2(side, lr.get("mlbam_id"), self.today, lr.get("birth_date"), "LIVE",
                                books_live))
                uf, u = usage(side, lr.get("mlbam_id"), LIVE_BOARD_YEAR, None, "LIVE", self.today)
                feats.update(uf)
                et_raw = {"hit": raw.get("hit") if side == "hit" else None,
                          "game_pwr": raw.get("game_pwr") if side == "hit" else None,
                          "raw_pwr": raw.get("raw_pwr") if side == "hit" else None,
                          "speed": raw.get("speed") if side == "hit" else None,
                          "fb": raw.get("fb") if side == "pit" else None,
                          "cmd": raw.get("cmd") if side == "pit" else None}
                tl = ((served_et.get(pk) or {}).get("tools") or {})
                for t in ("pitch_sel", "bat_ctrl"):
                    et_raw[t] = _f((tl.get(t) or {}).get("consensus")) if side == "hit" else None
                pid = lr.get("mlbam_id")
                meta = {"pid": None if pid is None else int(pid), "b": LIVE_BOARD_YEAR, "raw": et_raw,
                        "position": lr.get("position")}
                out.append({"kind": "LIVE", "side": side, "year": LIVE_BOARD_YEAR, "pk": pk,
                            "fv": float(r["fv"]), "n_sources": r["feats"].get("n_sources"),
                            "fv_stddev": r["feats"].get("fv_stddev"),
                            "group": (f"hit:{pos_group(lr.get('position'))}"
                                      if side == "hit" and pos_group(lr.get("position"))
                                      else (f"pit:{role_of(u)}" if side == "pit" else None)),
                            "feats": feats, "labels": {}, "etool_meta": meta, "read": self.today})
            cnt[side] = {k: sum(1 for o in out if o["side"] == side and o["kind"] == k) for k in KINDS}
            log(f"  {side}: {cnt[side]} ({round(time.time() - t0, 1)} s)")
        # extra raw tools of pitch_sel and bat_ctrl on development rows: the eTools frame's
        # consensus grade at the row's (board year, player), when the frame holds one
        self._frame_grades(out)
        self._live_z(out, rm)
        self.receipts.update({"instances": cnt, "row_contexts": {"metas": len(rm.meta),
                                                                  "consistency": ctx_rec["consistency"]},
                              "seconds": round(time.time() - t0, 1)})
        return {"instances": out, "rm_z": dict(rm.Z), "receipts": self.receipts}

    def _lv_extra_metas(self, b1: dict, frames_lv: dict, rm) -> dict:
        """eTool contexts of the pool rows the re-weight's row contexts do not hold (a player
        left out of an lv_dev training set as a later fold's test player): the frame row's
        outcome-blind id, board year V, its raw grades, and its sub-driver values through
        etools.attach_candidates (RowMeta.build_z's call)."""
        import efv_etools_reweight as ER
        import etools as E
        out, need = {}, {}
        for side in SIDES:
            lv_by = {(int(V), r["player_key"]): r for V, (rows, _l) in frames_lv[side].items()
                     for r in rows}
            for r in b1["pool"][side]:
                V, pk = int(r["decision_year"]), r["player_key"]
                if ("lv", side, V, pk) in rm.meta:
                    continue
                fr = lv_by.get((V, pk)) or {}
                prior = fr.get("prior") or {}
                pid = _f(fr.get("mlbam_id"))
                m = {"pid": None if pid is None else int(pid), "b": V,
                     "raw": {t: _f(prior.get(k)) for t, k in ER.RAW_KEY.items()},
                     "position": fr.get("position")}
                out[(side, V, pk)] = m
                if m["pid"] is not None and (side, m["pid"], V) not in rm.Z:
                    need[(side, m["pid"], V)] = fr.get("position")
        if need:
            rows = [{"year": b, "pid": pid, "side": side, "position": pos, "fg_extras": {}}
                    for (side, pid, b), pos in need.items()]
            last = max(ER.FRAME_LAST_SEASON, max(r["year"] for r in rows) - 1)
            E.attach_candidates(rows, last_season=last, log=self.log)
            for r in rows:
                rm.Z[(r["side"], r["pid"], r["year"])] = dict(r["cands"])
        self.receipts["lv_extra_contexts"] = {"rows": len(out), "sub_driver_reads": len(need)}
        self.log(f"  {len(out)} pool rows without a re-weight context; {len(need)} sub-driver reads")
        return out

    def _frame_grades(self, out: list[dict]) -> None:
        bank, _rec = self._pk("er/bank.pkl")
        idx = {}
        for t in ("pitch_sel", "bat_ctrl"):
            fr = bank.frames[t]
            idx[t] = {(int(y), int(p)): float(g) for y, p, g in zip(fr.year.tolist(), fr.pid.tolist(),
                                                                    fr.gc.tolist()) if np.isfinite(g)}
        n = 0
        for o in out:
            m = o.get("etool_meta")
            if o["kind"] == "LIVE" or o["side"] != "hit" or not m:
                continue
            raw = dict(m.get("raw") or {})
            for t in ("pitch_sel", "bat_ctrl"):
                g = (idx[t].get((int(m["b"]), int(m["pid"])))
                     if m.get("pid") is not None and m.get("b") is not None else None)
                raw[t] = g
                n += int(g is not None)
            m["raw"] = raw
        self.receipts["frame_grades_pitch_sel_bat_ctrl"] = n

    def _live_z(self, out: list[dict], rm) -> None:
        """The live rows' sub-driver values at board year 2027 (etools.attach_candidates, the
        eTools frame's own function), and their pitch rates."""
        import etools as E
        rows = [{"year": LIVE_BOARD_YEAR, "pid": o["etool_meta"]["pid"], "side": o["side"],
                 "position": o["etool_meta"].get("position"), "fg_extras": {}}
                for o in out if o["kind"] == "LIVE" and o["etool_meta"]["pid"] is not None]
        t0 = time.time()
        E.attach_candidates(rows, last_season=LIVE_READ_SEASON, log=self.log)
        for r in rows:
            rm.Z[(r["side"], r["pid"], LIVE_BOARD_YEAR)] = dict(r["cands"])
        for o in out:
            if o["kind"] != "LIVE":
                continue
            m = o["etool_meta"]
            z = rm.Z.get((o["side"], m["pid"], LIVE_BOARD_YEAR)) or {}
            for k in PITCH_RATES[o["side"]]:
                o["feats"][k] = _f(z.get(k))
            if z:
                self._la("LIVE", self.today, f"{LIVE_READ_SEASON}-10-01")
        self.log(f"  live sub-drivers for {len(rows)} rows ({round(time.time() - t0, 1)} s)")


# ---------------------------------------------------------------------------
# the fold eTools (section 3.4: the re-weight's version E, eHIT and eFB reduced)
# ---------------------------------------------------------------------------

@contextmanager
def reduced_subdrivers():
    """efv_etools_reweight.SUBDRIVERS with X3's sets for the life of the block."""
    import efv_etools_reweight as ER
    orig = dict(ER.SUBDRIVERS)
    ER.SUBDRIVERS.clear()
    ER.SUBDRIVERS.update(ETOOL_SUBDRIVERS)
    try:
        yield ER
    finally:
        ER.SUBDRIVERS.clear()
        ER.SUBDRIVERS.update(orig)


class ZBook:
    """The sub-driver lookup efv_etools_reweight.cohort_values reads (RowMeta.zrow)."""

    def __init__(self, Z: dict):
        self.Z = Z

    def zrow(self, side, pid, b, tool):
        import efv_etools_reweight as ER
        c = self.Z.get((side, pid, b)) if (pid is not None and b is not None) else None
        return [np.nan if (c is None or c.get(j) is None) else float(c[j]) for j in ER.SUBDRIVERS[tool]]


def etool_values(bank, zb: ZBook, side: str, metas: list[dict], tools, *, years, test_pids: set,
                 exclusive: bool) -> dict:
    """{tool: values} over rows with metas, one cohort per board year (the re-weight's
    Run.fold_values with every slot at the raw consensus grade): exclusive (a training row)
    leaves out the cohort's own board year and players; else one fit on `years`."""
    import efv_etools_reweight as ER
    n = len(metas)
    vals = {t: np.full(n, np.nan) for t in tools}
    by_b: dict = {}
    for i, m in enumerate(metas):
        if m is None:
            continue
        by_b.setdefault(m.get("b"), []).append(i)
    for b in sorted(by_b, key=lambda x: (x is None, x)):
        ix = by_b[b]
        sub = [metas[i] for i in ix]
        if exclusive:
            yrs = [y for y in years if y != b]
            excl = set(test_pids) | {m["pid"] for m in sub if m.get("pid") is not None}
        else:
            yrs = list(years)
            excl = set(test_pids)
        fits = {}
        if b is not None and yrs:
            for t in tools:
                fits[t] = bank.fit(t, yrs, excl, tag=f"x3|b{b}")
        v, _p = ER.cohort_values([{} for _ in ix], sub, side, tools, fits, "etool", zb)
        for t in tools:
            vals[t][ix] = v[t]
    return vals


# ---------------------------------------------------------------------------
# the folds (section 2.3)
# ---------------------------------------------------------------------------

def fold_list(T: Table, inp) -> list[dict]:
    """The comparator's outer folds: lv_dev V in 2017 to 2019, vm_dev Y in 2017 to 2023, both
    sides jointly; test rows are the fold's rows of both sides."""
    out = []
    for fid in FRAMES:
        years = sorted({int(y) for s in SIDES for y in inp.frames[fid]["by_side"][s]})
        for Y in years:
            if fid == "vm_dev" and Y >= F.R_VM_FIRST_DEBUT_YEAR:
                raise F.ReservedFrameError(f"vm_dev fold {Y}")
            kind = "LV" if fid == "lv_dev" else "PIN"
            test = np.flatnonzero((T.kind == kind) & (T.year == Y))
            out.append({"fid": fid, "Y": int(Y), "test": test, "id": f"{fid}|{Y}"})
    return out


def training_sets(T: Table, Y: int, exclude_pk: set, *, before: int | None = None) -> dict:
    """{stage: index array} of a fold: R the LV instances of vintages to min(2019, Y - 1); C (the
    conditional stages and L6) those plus the MTX instances of decision years before Y; every
    player of `exclude_pk` out. `before` restricts both to instances read before it (the
    inner training set)."""
    last = min(LV_LAST, Y - 1)
    keep = ~np.isin(T.pk, list(exclude_pk)) if exclude_pk else np.ones(T.n, dtype=bool)
    lv = (T.kind == "LV") & (T.year <= last) & keep
    mtx = (T.kind == "MTX") & (T.year < Y) & keep
    if before is not None:
        lv &= T.year < before
        mtx &= T.year < before
    return {"R": np.flatnonzero(lv & np.isfinite(T.r3)),
            "LV": np.flatnonzero(lv),
            "C": np.flatnonzero((lv & (T.r3 == 1.0) & T.cond) | (mtx & T.cond)),
            "MTX": np.flatnonzero(mtx),
            "ALL": np.flatnonzero(lv | mtx)}


def player_weights(T: Table, idx: np.ndarray) -> np.ndarray:
    """1 / (the player's instance count inside the set) (section 2.3)."""
    pks = T.pk[idx]
    u, inv, c = np.unique(pks, return_inverse=True, return_counts=True)
    return 1.0 / c[inv]


# ---------------------------------------------------------------------------
# the per-fold features and components (sections 3, 6.3, 6.4, 6.5)
# ---------------------------------------------------------------------------

def eiv_lambda(T: Table, train: np.ndarray) -> tuple[np.ndarray, dict]:
    """Consensus reliability lambda_i (section 6.3) from the fold's training instances of each
    side (features only, no label)."""
    lam = np.full(T.n, np.nan)
    rec = {}
    for s in (0, 1):
        tr = train[T.side[train] == s]
        n, sd = T.n_src[tr], T.sd_src[tr]
        m2 = n >= 2
        sig_e2 = float(np.mean(sd[m2] ** 2)) if m2.any() else 1.0
        sig_e2 = max(sig_e2, 1e-6)
        tau2 = float(np.var(T.fv[tr]) - np.mean(sig_e2 / n))
        tau2 = max(tau2, 0.25 * sig_e2)
        rows = T.side == s
        nn, ss = T.n_src[rows], T.sd_src[rows]
        sig_i2 = ((nn - 1.0) * ss ** 2 + 2.0 * sig_e2) / (nn + 1.0)
        lam[rows] = tau2 / (tau2 + sig_i2 / nn)
        rec[SIDES[s]] = {"sigma_e2": _rnd(sig_e2, 4), "tau2": _rnd(tau2, 4),
                         "lam_mean_train": _rnd(float(np.mean(lam[tr])), 4) if tr.size else None}
    return lam, rec


def _std_design(cols: list[np.ndarray], rows: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Columns standardized on the reference rows (missing 0) plus missing indicators."""
    out = []
    for c in cols:
        v = c[rows]
        r = c[ref]
        ok = np.isfinite(r)
        mu = float(r[ok].mean()) if ok.any() else 0.0
        sd = float(r[ok].std()) if ok.sum() > 1 else 1.0
        sd = sd if sd > 0 else 1.0
        z = np.where(np.isfinite(v), (v - mu) / sd, 0.0)
        out.append(z)
        if (~np.isfinite(r)).any():
            out.append((~np.isfinite(v)).astype(float))
    return np.column_stack([np.ones(rows.size)] + out) if out else np.ones((rows.size, 1))


def role_model(T: Table, feats: dict, train_c: np.ndarray, *, perm_seed: int | None = None
               ) -> tuple[np.ndarray, dict]:
    """P(ends a reliever) for every pitcher instance (section 6.5): a ridge logistic on GS / G,
    IP / G, workload, arsenal depth, eCMD, eFB, the best secondary grade and u_c, fitted on the
    fold's reached training pitchers with a role outcome."""
    pit = np.flatnonzero(T.side == 1)
    cols = [feats["gs_share"], feats["ip_per_g"], feats["workload"], feats["arsenal_depth"],
            feats["e_cmd"], feats["e_fb"], feats["c_best_sec"], T.u_c]
    tr = train_c[(T.side[train_c] == 1) & np.isfinite(T.role_y[train_c])]
    out = np.full(T.n, np.nan)
    rec = {"n_train": int(tr.size)}
    if tr.size < 30 or len(np.unique(T.role_y[tr])) < 2:
        rec["status"] = "too few reached pitchers with a role outcome; constant"
        out[pit] = float(np.nanmean(T.role_y[tr])) if tr.size else 0.5
        return out, rec
    Xtr = _std_design(cols, tr, tr)
    pen = np.full(Xtr.shape[1], ROLE_RIDGE)
    pen[0] = 0.0
    b = logistic(Xtr, T.role_y[tr], np.ones(tr.size), pen)
    Xall = _std_design(cols, pit, tr)
    out[pit] = sigmoid(Xall @ b)
    rec.update({"auc_in_sample": _rnd(auc(sigmoid(Xtr @ b), T.role_y[tr]), 4),
                "share_reliever": _rnd(float(T.role_y[tr].mean()), 4)})
    if perm_seed is not None:
        # the null (section 6.5): the prediction permuted within year
        rng = np.random.default_rng(int(perm_seed))
        for y in np.unique(T.year[pit]):
            ix = pit[T.year[pit] == y]
            out[ix] = out[ix][rng.permutation(ix.size)]
        rec["null"] = "permuted within year"
    return out, rec


def shift_weights(T: Table, Zf: dict, miss_cols: dict, train_all: np.ndarray, *, uniform: bool
                  ) -> tuple[np.ndarray, dict]:
    """Covariate-shift weights toward the live board (section 6.4), per side: a ridge logistic
    separating the fold's training instances (0) from the side's live instances (1) on the
    standardized features with missing indicators and the raw consensus grade."""
    w = np.ones(T.n)
    rec = {}
    for s in (0, 1):
        side = SIDES[s]
        tr = train_all[T.side[train_all] == s]
        lv = np.flatnonzero((T.kind == "LIVE") & (T.side == s))
        if uniform or tr.size == 0 or lv.size == 0:
            rec[side] = {"uniform": True}
            continue
        names = [f for f in miss_cols[side]]
        cols = [Zf[f] for f in names] + [T.fv]
        rows = np.concatenate([tr, lv])
        X = _std_design(cols, rows, rows)
        y = np.concatenate([np.zeros(tr.size), np.ones(lv.size)])
        pen = np.full(X.shape[1], SHIFT_RIDGE)
        pen[0] = 0.0
        b = logistic(X, y, np.ones(rows.size), pen)
        p = sigmoid(X @ b)
        ptr = np.clip(p[:tr.size], 1e-6, 1 - 1e-6)
        ww = ptr / (1 - ptr) * (tr.size / lv.size)
        clipped = int((ww > W_CLIP).sum())
        ww = np.minimum(ww, W_CLIP)
        ww = ww / ww.mean()
        ess = float(ww.sum() ** 2 / (ww ** 2).sum()) / tr.size
        tempered = False
        if ess < ESS_MIN:
            ww = np.sqrt(ww)
            ww = ww / ww.mean()
            ess = float(ww.sum() ** 2 / (ww ** 2).sum()) / tr.size
            tempered = True
        w[tr] = ww
        gaps = []
        for f, c in zip(names + ["consensus_grade"], cols):
            a, bb = c[tr], c[lv]
            a, bb = a[np.isfinite(a)], bb[np.isfinite(bb)]
            if a.size > 1 and bb.size > 1 and a.std() > 0:
                gaps.append((f, float((bb.mean() - a.mean()) / a.std())))
        gaps.sort(key=lambda t: -abs(t[1]))
        rec[side] = {"auc": _rnd(auc(p, y), 4), "ess_over_n": _rnd(ess, 4), "clipped": clipped,
                     "tempered": tempered, "n_train": int(tr.size), "n_live": int(lv.size),
                     "top_gaps": [[f, _rnd(g, 3)] for f, g in gaps[:3]]}
    return w, rec


# ---------------------------------------------------------------------------
# the designs (section 5)
# ---------------------------------------------------------------------------

class FoldX:
    """The fold's feature arrays (z-scored, NaN missing), the features kept per side, and the
    design builders of both classes."""

    def __init__(self, T: Table, Zf: dict, kept: dict, lam: np.ndarray, lam_bar: dict, *,
                 plant: np.ndarray | None = None):
        self.T = T
        self.Zf = Zf
        self.kept = kept
        self.lam = lam
        self.lam_bar = lam_bar
        self.plant = plant
        names = []
        for s in SIDES:
            for f in kept[s]:
                if f not in names:
                    names.append(f)
        if plant is not None:
            names.append("planted")
        self.names = names
        # the features that are ever missing on a side (a missing indicator column each)
        self.has_missing = {SIDES[s]: {f for f in kept[SIDES[s]]
                                       if (~np.isfinite(Zf[f][T.side == s])).any()} for s in (0, 1)}

    def _val(self, f: str, rows: np.ndarray) -> np.ndarray:
        if f == "planted":
            return self.plant[rows]
        return self.Zf[f][rows]

    def _on_side(self, f: str, s: int) -> bool:
        return f == "planted" or f in self.kept[SIDES[s]]

    def design_a(self, rows: np.ndarray, *, k: np.ndarray | None = None, extra: dict | None = None,
                 anchor_only: bool = False) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """(X, penalty multipliers (0 anchor, 1 slope, KAPPA deviation), names)."""
        T = self.T
        side = T.side[rows]
        cols, mult, names = [], [], []

        def add(c, m, nm):
            cols.append(c)
            mult.append(m)
            names.append(nm)
        for s in (0, 1):
            on = (side == s).astype(float)
            if k is None:
                add(on, 0.0, f"{SIDES[s]}:intercept")
            else:
                for j in range(SEASONS_K):
                    add(on * (k == j), 0.0, f"{SIDES[s]}:k{j}")
            add(on * T.u_c[rows], 0.0, f"{SIDES[s]}:u_c")
            add(on * T.u_c[rows] * (self.lam[rows] - self.lam_bar[SIDES[s]]), 0.0,
                f"{SIDES[s]}:u_c_x_lam")
        if not anchor_only:
            grp = T.grp[rows]
            for f in self.names:
                v = self._val(f, rows)
                x = np.where(np.isfinite(v), v, 0.0)
                miss = (~np.isfinite(v)).astype(float)
                sides_on = [s for s in (0, 1) if self._on_side(f, s)]
                shared = len(sides_on) == 2
                if shared:
                    on_any = np.isin(side, sides_on).astype(float)
                    add(x * on_any, 1.0, f"{f}")
                # the column set is fixed by the fold (never by the rows passed), so a fit and
                # a prediction read the same columns
                for s in sides_on:
                    on = (side == s).astype(float)
                    add(x * on, KAPPA if shared else 1.0, f"{f}|{SIDES[s]}")
                    if f in self.has_missing.get(SIDES[s], ()):
                        add(miss * on, 1.0, f"{f}|{SIDES[s]}|missing")
                    for g in GROUPS:
                        if g.startswith(SIDES[s] + ":"):
                            add(x * (grp == g).astype(float), KAPPA, f"{f}|{g}")
            for nm, v in (extra or {}).items():
                for s in (0, 1):
                    on = (side == s).astype(float)
                    add(v * on, 1.0, f"{nm}|{SIDES[s]}")
        return np.column_stack(cols), np.asarray(mult), names

    def design_b(self, rows: np.ndarray, *, k: np.ndarray | None = None,
                 extra: dict | None = None) -> tuple[np.ndarray, list[str], list[int], list[int]]:
        """(X with NaN for missing, names, monotone directions, categorical column indexes)."""
        T = self.T
        side = T.side[rows]
        cols, names, mono = [T.u_c[rows], self.lam[rows]], ["u_c", "lam_anchor"], [1, 0]
        for f in self.names:
            v = self._val(f, rows).copy()
            for s in (0, 1):
                if not self._on_side(f, s):
                    v[side == s] = np.nan
            cols.append(v)
            names.append(f)
            mono.append(1 if f in MONO_UP else (-1 if f in MONO_DOWN else 0))
        gcode = np.asarray([GROUPS.index(g) if g in GROUPS else -1 for g in T.grp[rows]], dtype=float)
        gcode[gcode < 0] = np.nan
        cols += [side.astype(float), gcode]
        names += ["side", "group"]
        mono += [0, 0]
        cat = [len(names) - 2, len(names) - 1]
        if k is not None:
            cols.append(k.astype(float))
            names.append("k")
            mono.append(0)
        for nm, v in (extra or {}).items():
            cols.append(np.asarray(v, dtype=float))
            names.append(nm)
            mono.append(0)
        return np.column_stack(cols), names, mono, cat


# ---------------------------------------------------------------------------
# the two classes, one stage at a time
# ---------------------------------------------------------------------------

class StageFit:
    """One fitted stage of one configuration: predict(rows, k, extra) on any rows."""

    def __init__(self, cls: str, kind: str, fx: FoldX, *, beta=None, names=None, booster=None,
                 anchor=None, trees: int | None = None):
        self.cls, self.kind, self.fx = cls, kind, fx
        self.beta, self.names, self.booster, self.anchor, self.trees = beta, names, booster, anchor, trees

    def raw(self, rows, *, k=None, extra=None) -> np.ndarray:
        if self.cls == "ridge":
            X, _m, names = self.fx.design_a(rows, k=k, extra=extra)
            if names != self.names:
                raise RuntimeError("design columns differ between fit and predict")
            return X @ self.beta
        base = self.anchor.raw(rows, k=k, extra=None)
        Xb, _n, _m, _c = self.fx.design_b(rows, k=k, extra=extra)
        return base + self.booster.predict(Xb, num_iteration=self.trees, raw_score=True)

    def predict(self, rows, *, k=None, extra=None) -> np.ndarray:
        r = self.raw(rows, k=k, extra=extra)
        return sigmoid(r) if self.kind == "binary" else r

    def coef(self) -> dict:
        if self.cls != "ridge":
            return {}
        return {n: float(b) for n, b in zip(self.names, self.beta)}


class AnchorFit(StageFit):
    pass


def fit_anchor(fx: FoldX, rows, y, w, kind: str, *, k=None) -> StageFit:
    X, mult, names = fx.design_a(rows, k=k, anchor_only=True)
    pen = mult * 0.0
    b = logistic(X, y, w, pen) if kind == "binary" else wls(X, y, w, pen)

    class _A(StageFit):
        def raw(self, rr, *, k=None, extra=None):
            Xa, _m, _n = fx.design_a(rr, k=k, anchor_only=True)
            return Xa @ b
    return _A("anchor", kind, fx, beta=b, names=names)


def fit_ridge(fx: FoldX, rows, y, w, kind: str, lam: float, *, k=None, extra=None,
              warm: np.ndarray | None = None) -> StageFit:
    X, mult, names = fx.design_a(rows, k=k, extra=extra)
    pen = mult * float(lam)
    b = logistic(X, y, w, pen, b0=warm) if kind == "binary" else wls(X, y, w, pen)
    return StageFit("ridge", kind, fx, beta=b, names=names)


def fit_gbm(fx: FoldX, rows, y, w, kind: str, *, k=None, extra=None, trees: int = max(TREES)
            ) -> StageFit:
    import lightgbm as lgb
    anc = fit_anchor(fx, rows, y, w, kind, k=k)
    init = anc.raw(rows, k=k)
    Xb, names, mono, cat = fx.design_b(rows, k=k, extra=extra)
    params = dict(GBM_PARAMS, objective="binary" if kind == "binary" else "regression",
                  monotone_constraints=mono)
    ww = np.asarray(w, dtype=np.float64)
    ww = ww / ww.mean()
    ds = lgb.Dataset(Xb, label=np.asarray(y, dtype=np.float64), weight=ww, init_score=init,
                     feature_name=[n.replace("|", "_").replace(":", "_") for n in names],
                     categorical_feature=cat, free_raw_data=False, params={"verbose": -1})
    bst = lgb.train(params, ds, num_boost_round=int(trees))
    return StageFit("gbm", kind, fx, booster=bst, anchor=anc, trees=int(trees), names=names)


# ---------------------------------------------------------------------------
# the staged model on one training set (section 4)
# ---------------------------------------------------------------------------

class Ctx:
    """Everything one fold's fits share: the table, the fold design, weights, the variant."""

    def __init__(self, T: Table, fx: FoldX, w_shift: np.ndarray, variant: dict):
        self.T, self.fx, self.w_shift, self.variant = T, fx, w_shift, variant


def panel_design(T: Table, idx: np.ndarray, *, zero_fill: bool) -> tuple:
    """(row instance index, k, PT, WAR) over the panel rows of instances idx."""
    ii, kk, pt, wr = [], [], [], []
    for i in idx:
        for k, p, w in T.panel[i]:
            ii.append(i)
            kk.append(k)
            pt.append(p)
            wr.append(w)
        if zero_fill:
            for k in T.panel_open[i]:
                ii.append(i)
                kk.append(k)
                pt.append(0.0)
                wr.append(0.0)
    return (np.asarray(ii, dtype=np.int64), np.asarray(kk, dtype=np.int64),
            np.asarray(pt, dtype=np.float64), np.asarray(wr, dtype=np.float64))


def _crossfit_folds(pks: np.ndarray, k: int = CROSSFIT_K, seed: int = SEED) -> np.ndarray:
    return np.asarray([int(hashlib.sha256(f"{seed}:{p}".encode()).hexdigest()[:8], 16) % k
                       for p in pks], dtype=np.int64)


class Staged:
    """The three stages of one configuration (cls ridge with lam, or gbm with trees)."""

    def __init__(self, cls: str, par: float):
        self.cls, self.par = cls, par
        self.R = self.T_ = self.Q = None
        self.rec: dict = {}

    def _fit(self, ctx, rows, y, w, kind, *, k=None, extra=None):
        if self.cls == "ridge":
            return fit_ridge(ctx.fx, rows, y, w, kind, self.par, k=k, extra=extra)
        return fit_gbm(ctx.fx, rows, y, w, kind, k=k, extra=extra, trees=int(self.par))

    def fit(self, ctx: Ctx, tr: dict) -> "Staged":
        T = ctx.T
        v = ctx.variant
        R = tr["R"]
        wR = player_weights(T, R) * ctx.w_shift[R]
        self.R = self._fit(ctx, R, T.r3[R], wR, "binary")
        # the reach probability of every conditional row: LV rows cross-fitted (5 player folds
        # of the stage R set), MTX rows by the full stage R fit (section 6.2)
        C = tr["C"]
        p = self.R.predict(C)
        lvC = T.kind[C] == "LV"
        if lvC.any():
            cf = _crossfit_folds(T.pk[R])
            cfC = _crossfit_folds(T.pk[C])
            for j in range(CROSSFIT_K):
                m = cf != j
                if m.sum() < 50:
                    continue
                Rj = R[m]
                fj = self._fit(ctx, Rj, T.r3[Rj], wR[m], "binary")
                sel = lvC & (cfC == j)
                if sel.any():
                    p[sel] = fj.predict(C[sel])
        mills = imr(p)
        if v.get("imr") == "perm":
            rng = np.random.default_rng(int(v.get("imr_seed", SEED)))
            for key in np.unique(T.side[C] * 10000 + T.year[C]):
                ix = np.flatnonzero(T.side[C] * 10000 + T.year[C] == key)
                mills[ix] = mills[ix][rng.permutation(ix.size)]
        inst_m = dict(zip(C.tolist(), mills.tolist()))
        wC = dict(zip(C.tolist(), (player_weights(T, C) * ctx.w_shift[C]).tolist()))
        ii, kk, pt, wr = panel_design(T, C, zero_fill=v.get("censor") == "zero")
        if ii.size == 0:
            raise RuntimeError("no panel rows")
        wi = np.asarray([wC[i] for i in ii])
        mi = np.asarray([inst_m[i] for i in ii])
        self.T_ = self._fit(ctx, ii, pt, wi, "reg", k=kk, extra={"imr": mi})
        q = pt > 0
        self.Q = self._fit(ctx, ii[q], wr[q] / pt[q], wi[q] * pt[q], "reg", k=kk[q],
                           extra={"imr": mi[q]})
        if self.cls == "ridge":
            cT, cQ = self.T_.coef(), self.Q.coef()
            self.rec["imr_coef"] = {"T": {s: _rnd(cT.get(f"imr|{s}"), 4) for s in SIDES},
                                    "Q": {s: _rnd(cQ.get(f"imr|{s}"), 4) for s in SIDES}}
        self.rec["panel_rows"] = int(ii.size)
        self.rec["n_R"] = int(R.size)
        self.rec["n_C"] = int(C.size)
        return self

    def score(self, rows: np.ndarray) -> dict:
        """{p, cond (E[L6 | reach]), e (the X3 score)} on rows."""
        p = self.R.predict(rows)
        mills = imr(p)
        cond = np.zeros(rows.size)
        for k in range(SEASONS_K):
            kk = np.full(rows.size, k, dtype=np.int64)
            t = self.T_.predict(rows, k=kk, extra={"imr": mills})
            q = self.Q.predict(rows, k=kk, extra={"imr": mills})
            cond += np.maximum(0.0, t) * q
        return {"p": p, "cond": cond, "e": p * cond}


class Direct:
    """A direct arm (section 4.4): W3 on LV instances or L6 on LV and MTX instances."""

    def __init__(self, label: str, cls: str, par: float):
        self.label, self.cls, self.par = label, cls, par
        self.fit_ = None

    def fit(self, ctx: Ctx, tr: dict) -> "Direct":
        T = ctx.T
        if self.label == "W3":
            rows = tr["LV"][np.isfinite(T.w3[tr["LV"]])]
            y = T.w3[rows]
            lw = np.ones(rows.size)
        else:
            lv = tr["LV"][np.isfinite(T.l6_fit[tr["LV"]])]
            mt = tr["MTX"][np.isfinite(T.mtx_target[tr["MTX"]])]
            rows = np.concatenate([lv, mt])
            y = np.concatenate([T.l6_fit[lv], T.mtx_target[mt]])
            lw = np.concatenate([np.nan_to_num(T.l6w[lv], nan=1.0), np.nan_to_num(T.mtx_weight[mt], nan=1.0)])
        w = player_weights(T, rows) * ctx.w_shift[rows] * lw
        if self.cls == "ridge":
            self.fit_ = fit_ridge(ctx.fx, rows, y, w, "reg", self.par)
        else:
            self.fit_ = fit_gbm(ctx.fx, rows, y, w, "reg", trees=int(self.par))
        return self

    def score(self, rows) -> dict:
        return {"e": self.fit_.predict(rows)}


CONFIGS = tuple(("ridge", lam) for lam in LAM_GRID) + tuple(("gbm", float(t)) for t in TREES)


def config_name(c) -> str:
    return f"ridge_lam{c[1]:g}" if c[0] == "ridge" else f"gbm_{int(c[1])}"


def pick(scores: dict) -> tuple:
    """The best configuration: highest inner score; ties to the larger lambda, then to fewer
    trees, then to ridge (section 5)."""
    best = None
    for c in CONFIGS:
        s = scores.get(c)
        if s is None:
            continue
        key = (round(s, 12), 1 if c[0] == "ridge" else 0, c[1] if c[0] == "ridge" else -c[1])
        if best is None or key > best[0]:
            best = (key, c)
    return best[1] if best else ("ridge", max(LAM_GRID))


def pick_class(scores: dict, cls: str) -> tuple:
    return pick({c: s for c, s in scores.items() if c[0] == cls})


# ---------------------------------------------------------------------------
# one pipeline run (every outer fold)
# ---------------------------------------------------------------------------

def fold_eval_groups(T: Table, rows: np.ndarray) -> np.ndarray:
    return np.asarray([f"{SIDES[s]}|{y}" for s, y in zip(T.side[rows], T.year[rows])])


def inner_score(T: Table, rows: np.ndarray, e: np.ndarray) -> float | None:
    ok = np.isfinite(T.w3[rows])
    return within_spearman(e[ok], T.w3[rows][ok], fold_eval_groups(T, rows[ok]))


def build_fold_features(T: Table, fold_et: dict, fold: dict, tr: dict, variant: dict, *,
                        perm: dict | None, plant: np.ndarray | None, sensitivity: bool,
                        log=None) -> tuple[FoldX, np.ndarray, dict]:
    """The fold's feature arrays (sections 3, 6.3, 6.4, 6.5): eTools from the fold build,
    lambda, the role path, z-scores, the coverage rule and the shift weights."""
    raw = {f: v.copy() for f, v in T.base.items()}
    for f, t in ETOOL_OF.items():
        raw[f] = fold_et.get(t, np.full(T.n, np.nan)).copy()
    train_all = tr["ALL"]
    lam, lam_rec = eiv_lambda(T, train_all)
    rec = {"lambda": lam_rec}
    if variant.get("lam") == "perm":
        rng = np.random.default_rng(int(variant.get("lam_seed", SEED)))
        for g in np.unique(T.zgroup):
            ix = np.flatnonzero(T.zgroup == g)
            lam[ix] = lam[ix][rng.permutation(ix.size)]
    raw["lam"] = lam
    # the role path needs z-free inputs: z-scored copies for its design
    z = {}
    for f, v in raw.items():
        z[f] = v if f in BINARY else z_within(v, T.zgroup)
    p_rel, role_rec = role_model(T, z, tr["C"],
                                 perm_seed=(variant.get("role_seed", SEED) if variant.get("role") == "perm"
                                            else None))
    rec["role"] = role_rec
    raw["p_rel"] = p_rel
    raw["p_rel_x_uc"] = np.where(np.isfinite(p_rel), p_rel * T.u_c, np.nan)
    for f in ("p_rel", "p_rel_x_uc"):
        z[f] = z_within(raw[f], T.zgroup)
    if perm is not None:
        # clause (C): every feature permuted within (side, instance kind, year), jointly, and
        # the pitcher usage role and hitter position group with them
        for f in z:
            z[f] = z[f][perm["idx"]]
        lam = lam[perm["idx"]]
    # the coverage rule (section 3.1), per side on the fold's training instances
    kept = {}
    cover = {}
    for s in (0, 1):
        side = SIDES[s]
        trs = train_all[T.side[train_all] == s]
        kept[side] = []
        cover[side] = {}
        for f in features_of(side, sensitivity):
            share = float(np.isfinite(z[f][trs]).mean()) if trs.size else 0.0
            cover[side][f] = _rnd(share, 3)
            if share >= COVER_MIN:
                kept[side].append(f)
    rec["kept"] = {s: list(v) for s, v in kept.items()}
    rec["coverage"] = cover
    lam_bar = {SIDES[s]: float(np.mean(lam[train_all[T.side[train_all] == s]])) for s in (0, 1)}
    fx = FoldX(T, z, kept, lam, lam_bar, plant=plant)
    w_shift, srec = shift_weights(T, z, kept, train_all, uniform=variant.get("shift") == "uniform")
    rec["shift"] = srec
    return fx, w_shift, rec


def run_pipeline(T: Table, folds: list[dict], fold_ets: dict, *, variant: dict | None = None,
                 lite: bool = False, sensitivity: bool = False, perm_seed: int | None = None,
                 plant: bool = False, log=print) -> dict:
    """Every outer fold once: nested selection, the refit, the test scores. lite: X3 alone
    (no per-class refits, direct arms or conformal sets)."""
    variant = dict(variant or {})
    t0 = time.time()
    perm = None
    if perm_seed is not None:
        rng = np.random.default_rng(int(perm_seed))
        idx = np.arange(T.n)
        for g in np.unique(T.zgroup):
            ix = np.flatnonzero(T.zgroup == g)
            idx[ix] = ix[rng.permutation(ix.size)]
        perm = {"idx": idx, "seed": int(perm_seed)}
    plant_v = plant_feature(T) if plant else None
    scores: dict = {}
    receipts: dict = {}
    for fold in folds:
        t1 = time.time()
        Y = fold["Y"]
        test = fold["test"]
        excl = set(T.pk[test].tolist())
        tr = training_sets(T, Y, excl)
        fx, w_shift, frec = build_fold_features(T, fold_ets[fold["id"]], fold, tr, variant,
                                                perm=perm, plant=plant_v, sensitivity=sensitivity)
        if perm is not None:
            T_grp = T.grp
            T.grp = T.grp[perm["idx"]]
        try:
            ctx = Ctx(T, fx, w_shift, variant)
            last = min(LV_LAST, Y - 1)
            val_years = (last - 1, last)
            val = tr["LV"][np.isin(T.year[tr["LV"]], val_years) & np.isfinite(T.w3[tr["LV"]])]
            tr_in = training_sets(T, Y, excl | set(T.pk[val].tolist()), before=val_years[0])
            inner: dict = {}
            inner_fit: dict = {}
            for c in CONFIGS:
                m = Staged(*c).fit(ctx, tr_in)
                sc = m.score(val)
                inner[c] = inner_score(T, val, sc["e"])
                inner_fit[c] = (m, sc)
            best = pick(inner)
            sel = {"X3": best}
            if not lite:
                sel["X3_ridge"] = pick_class(inner, "ridge")
                sel["X3_gbm"] = pick_class(inner, "gbm")
            fitted = {}
            for name, c in sel.items():
                if c in fitted:
                    continue
                fitted[c] = Staged(*c).fit(ctx, tr)
            out = {}
            for name, c in sel.items():
                out[name] = fitted[c].score(test)
            frec.update({"selected": config_name(best),
                         "inner": {config_name(c): _rnd(s, 5) for c, s in inner.items()},
                         "val_years": list(val_years), "n_val": int(val.size),
                         "n_train": {k: int(v.size) for k, v in tr.items()},
                         "stage_receipt": fitted[best].rec})
            if not lite:
                # the direct arms, each class selected by the same inner read
                for lab in ("W3", "L6"):
                    for cls in ("ridge", "gbm"):
                        grid = [p for (c_, p) in CONFIGS if c_ == cls]
                        isc = {}
                        for par in grid:
                            d = Direct(lab, cls, par).fit(ctx, tr_in)
                            isc[(cls, par)] = inner_score(T, val, d.score(val)["e"])
                        bc = pick_class(isc, cls)
                        out[f"{lab}_{cls}"] = Direct(lab, cls, bc[1]).fit(ctx, tr).score(test)
                        frec.setdefault("direct_selected", {})[f"{lab}_{cls}"] = config_name(bc)
                # conformal calibration (section 6.6): the inner validation instances scored
                # by the inner fit of the selected configuration
                m_in, sc_in = inner_fit[best]
                frec["conformal_cal"] = calibration(T, val, sc_in)
                frec["coef"] = {name: coef_report(fitted[c]) for name, c in sel.items()
                                if c[0] == "ridge"}
                frec["gbm_gain"] = {name: gain_report(fitted[c]) for name, c in sel.items()
                                    if c[0] == "gbm"}
                # the anchor-only (consensus) fit's intervals: section 6.6's null
                anc = Staged("ridge", 1e9).fit(ctx, tr_in)
                frec["conformal_cal_anchor"] = calibration(T, val, anc.score(val))
                out["anchor_only"] = Staged("ridge", 1e9).fit(ctx, tr).score(test)
        finally:
            if perm is not None:
                T.grp = T_grp
        for name, sc in out.items():
            for j, i in enumerate(test.tolist()):
                scores.setdefault(name, {})[i] = {k: float(v[j]) for k, v in sc.items()}
        receipts[fold["id"]] = frec
        log(f"    fold {fold['id']}: selected {frec['selected']} ({round(time.time() - t1, 1)} s)")
    return {"scores": scores, "receipts": receipts, "seconds": round(time.time() - t0, 1),
            "variant": variant, "perm_seed": perm_seed, "plant": bool(plant),
            "sensitivity": bool(sensitivity), "lite": bool(lite)}


def coef_report(st: Staged) -> dict:
    """Every pitch-rate, eTool and IMR coefficient of a ridge configuration's stages."""
    out = {}
    for name, fit in (("R", st.R), ("T", st.T_), ("Q", st.Q)):
        c = fit.coef()
        out[name] = {k: _rnd(v, 5) for k, v in c.items()
                     if any(k == f or k.startswith(f + "|") for f in
                            ("ppa_raw", "ppa_par", "pbf_raw", "pbf_par", "pip_raw", "pip_par",
                             "e_hit", "e_pow", "e_sel", "e_bat", "e_fb", "e_cmd", "e_raw", "e_spd",
                             "imr", "planted", "p_rel", "p_rel_x_uc", "lam"))
                     and not k.endswith("|missing")
                     and k.count("|") <= 1}
    return out


def gain_report(st: Staged) -> dict:
    out = {}
    for name, fit in (("R", st.R), ("T", st.T_), ("Q", st.Q)):
        g = fit.booster.feature_importance(importance_type="gain", iteration=fit.trees)
        tot = float(g.sum()) or 1.0
        out[name] = {n: _rnd(v / tot, 4) for n, v in zip(fit.names, g) if v > 0}
    return out


def calibration(T: Table, rows: np.ndarray, sc: dict) -> dict:
    """The split-conformal calibration set of a fold (section 6.6)."""
    grp = fold_eval_groups(T, rows)
    ok = np.isfinite(T.w3[rows])
    u_y = np.full(rows.size, np.nan)
    u_y[ok] = pct_within(T.w3[rows][ok], grp[ok])
    u_hat = pct_within(sc["e"], grp)
    order_res = np.abs(u_y - u_hat)[ok]
    l6ok = T.l6_obs[rows] & np.isfinite(T.l6[rows])
    war_res = np.abs(T.l6[rows][l6ok] - sc["e"][l6ok])
    reached = l6ok & (T.r3[rows] == 1.0)
    cond_res = T.l6[rows][reached] - sc["cond"][reached]
    return {"order": order_res.tolist(), "war": war_res.tolist(), "cond_resid": cond_res.tolist(),
            "l6_min": float(np.min(T.l6[rows][l6ok])) if l6ok.any() else 0.0}


def conformal_q(res, nominal: float = CONF_NOMINAL) -> float | None:
    """The ceil(nominal (m + 1)) / m empirical quantile of m calibration scores."""
    r = np.sort(np.asarray(res, dtype=np.float64))
    m = r.size
    if m == 0:
        return None
    j = int(math.ceil(nominal * (m + 1)))
    return float(r[min(j, m) - 1])


def plant_feature(T: Table, *, rho: float = PLANT_RHO, seed: int = PLANT_SEED) -> np.ndarray:
    """Clause (D): rho times the normal score of the instance's own label percentile within
    (side, kind, year), plus sqrt(1 - rho^2) standard normal noise; noise alone without a label."""
    rng = np.random.default_rng(int(seed))
    lab = T.plant_label()
    eps = rng.standard_normal(T.n)
    out = eps.copy()
    ok = np.isfinite(lab)
    for g in np.unique(T.zgroup[ok]):
        ix = np.flatnonzero(ok & (T.zgroup == g))
        q = pct_within(lab[ix], [0] * ix.size)
        q = np.clip(q - 0.5 / ix.size, 1e-6, 1 - 1e-6)
        zq = norm_ppf(q)
        sd = zq.std()
        zq = (zq - zq.mean()) / sd if sd > 0 else zq * 0.0
        out[ix] = rho * zq + math.sqrt(1 - rho * rho) * eps[ix]
    return out


# ---------------------------------------------------------------------------
# the fold eTools, built once (cached)
# ---------------------------------------------------------------------------

def build_fold_etools(T: Table, folds: list[dict], bank0, Z: dict, *, log=print) -> dict:
    """{fold id: {tool: values over every instance (NaN off the fold)}}: training instances
    out of fold by board year, test instances by the forward fit, live instances by one fit on
    every eTools board year (the production construction)."""
    import etools as E
    with reduced_subdrivers() as ER:
        bank = ER.Bank(bank0.frames)
        zb = ZBook(Z)
        tools_by_side = {"hit": ("hit", "game_pwr", "pitch_sel", "bat_ctrl", "raw_pwr", "speed"),
                         "pit": ("fb", "cmd")}
        live = {}
        for s in (0, 1):
            side = SIDES[s]
            ix = np.flatnonzero((T.kind == "LIVE") & (T.side == s))
            v = etool_values(bank, zb, side, [T.meta[i] for i in ix], tools_by_side[side],
                             years=list(E.DEV_YEARS), test_pids=set(), exclusive=False)
            live[side] = (ix, v)
        out = {}
        for fold in folds:
            t0 = time.time()
            Y = fold["Y"]
            test = fold["test"]
            tr = training_sets(T, Y, set(T.pk[test].tolist()))
            years = [y for y in E.DEV_YEARS if y < Y]
            vals = {t: np.full(T.n, np.nan) for s in SIDES for t in tools_by_side[s]}
            for s in (0, 1):
                side = SIDES[s]
                trs = tr["ALL"][T.side[tr["ALL"]] == s]
                tes = test[T.side[test] == s]
                test_pids = {T.meta[i]["pid"] for i in tes if T.meta[i] and T.meta[i].get("pid") is not None}
                v_tr = etool_values(bank, zb, side, [T.meta[i] for i in trs], tools_by_side[side],
                                    years=years, test_pids=test_pids, exclusive=True)
                v_te = etool_values(bank, zb, side, [T.meta[i] for i in tes], tools_by_side[side],
                                    years=years, test_pids=test_pids, exclusive=False)
                lix, lv = live[side]
                for t in tools_by_side[side]:
                    vals[t][trs] = v_tr[t]
                    vals[t][tes] = v_te[t]
                    vals[t][lix] = lv[t]
            out[fold["id"]] = vals
            log(f"  fold eTools {fold['id']} ({round(time.time() - t0, 1)} s)")
        receipts = bank.receipts
    return {"values": out, "fits": len(receipts)}


# ---------------------------------------------------------------------------
# the read (sections 7 to 9)
# ---------------------------------------------------------------------------

def x3_key(name: str) -> str:
    return {"X3": "x3", "X3_ridge": "x3_ridge", "X3_gbm": "x3_gbm"}.get(name, name.lower())


SERVED = "efv_served_rt"
V5C_KEY = "efv_v5_combined_dev"
V2_KEY = "efv_v2"
CONS = "prospx_consensus"


def pool_rows(T: Table, comp: dict, inp, runs: dict[str, dict]) -> list[dict]:
    """The pooled rows of both frames (EFV_BEAT_POOLED_POWER's rows) with every rater's score:
    the comparator scores from the tilted-labels build, V2 from the frame rows, and each run's
    scores by key."""
    out = []
    v2 = {}
    for fid in FRAMES:
        for c in inp.scored(fid):
            v2[(fid, c["side"], int(c["year"]), c["key"])] = float(c["grades"]["efv_v2"])
    for fid in FRAMES:
        kind = "LV" if fid == "lv_dev" else "PIN"
        for r in comp["frames"][fid]:
            i = T.index.get((kind, r["side"], int(r["year"]), r["key"]))
            if i is None:
                raise RuntimeError(f"no instance for {fid} {r['side']} {r['year']} {r['key']}")
            sc = {SERVED: r["scores"]["efv_served_rt"], V5C_KEY: r["scores"]["efv_v5_combined_dev"],
                  CONS: r["scores"]["prospx_consensus"], V2_KEY: v2[(fid, r["side"], int(r["year"]), r["key"])]}
            for key, run in runs.items():
                for name, by in run["scores"].items():
                    # the run's X3 under the run's key; the main run's other raters as x3:<name>
                    if name == "X3":
                        k = key
                    elif key == "x3":
                        k = f"x3:{name}"
                    else:
                        continue
                    got = by.get(i)
                    if got is not None:
                        sc[k] = got["e"]
            y = (T.w3[i] if fid == "lv_dev" else T.y_pin[i])
            out.append({"key": r["key"], "frame": fid, "kind": fid[:2], "side": r["side"],
                        "year": int(r["year"]), "pgroup": f"{fid}:{r['side']}|{int(r['year'])}",
                        "club": r["club"], "y": float(y), "scores": sc, "i": i,
                        "y_label": r["labels"]})
    return out


def read_legs(rows: list[dict], comparisons, *, B_: int = B, seed: int = SEED, clusterings=("player", "club"),
              log=print) -> dict:
    import efv_beat_pooled_power as PP
    return PP.read_pool(rows, comparisons, B_=B_, seed=seed, clusterings=clusterings, log=log)


def point_delta(rows: list[dict], a: str, b: str) -> float | None:
    import efv_beat_pooled_power as PP
    pool = PP.Pool(rows, (a, b))
    wa, wb = pool.pair(pool.group_rhos(np.arange(pool.n)), a, b, "both")
    return None if wa is None else wa - wb


def dist_block(rows: list[dict], T: Table, raters: dict, x3_dist: dict | None, *, B_: int, seed: int) -> dict:
    """Section 7.4: per rater, its within-group percentile mapped by the leave-one-year-out
    threshold logistic (efv_upside_volatility's grid and lambda) to a predictive distribution:
    CRPS on six-season WAR and the bust/middle/star log loss (rows with a fully observed L6);
    the REACH log loss from a leave-one-year-out logistic of R3 (lv_dev rows)."""
    import efv_upside_volatility as UV
    l6rows = [r for r in rows if T.l6_obs[r["i"]] and np.isfinite(T.l6[r["i"]])]
    y = np.asarray([T.l6[r["i"]] for r in l6rows])
    frames = np.asarray([r["frame"] for r in l6rows])
    years = np.asarray([r["year"] for r in l6rows])
    groups = np.asarray([r["pgroup"] for r in l6rows])
    keys = [r["key"] for r in l6rows]
    per = {}
    for name, key in raters.items():
        u = pct_within([r["scores"][key] for r in l6rows], groups)
        X = np.column_stack([np.ones(len(l6rows)), u])
        Fm = np.zeros((len(l6rows), len(UV.GRID)))
        for fid in np.unique(frames):
            for yr in np.unique(years[frames == fid]):
                te = (frames == fid) & (years == yr)
                trm = (frames == fid) & (years != yr)
                Fm[te] = UV.predict_cdf(X[trm], y[trm], X[te])
        per[name] = {"crps": UV.crps_rows(Fm, y), "ll": UV.logloss_rows(Fm, y)}
    out = {"n_l6": len(l6rows), "raters": {n: {"crps": _rnd(v["crps"].mean(), 5),
                                               "logloss": _rnd(v["ll"].mean(), 5)} for n, v in per.items()}}
    if x3_dist is not None:
        Fx = np.asarray([x3_dist[r["i"]] for r in l6rows])
        cx = UV.crps_rows(Fx, y)
        out["x3_predictive"] = {"crps": _rnd(cx.mean(), 5), "logloss": _rnd(UV.logloss_rows(Fx, y).mean(), 5)}
    legs = {}
    for a, b in (("x3", "consensus"), ("x3", "served")):
        if a in per and b in per:
            for m in ("crps", "ll"):
                d = per[a][m] - per[b][m]
                legs[f"{a}_minus_{b}|{m}"] = UV.cluster_boot(d, keys, B=B_, seed=seed)
    # REACH log loss on lv_dev rows
    lvr = [r for r in rows if r["frame"] == "lv_dev" and np.isfinite(T.r3[r["i"]])]
    yr3 = np.asarray([T.r3[r["i"]] for r in lvr])
    yrs = np.asarray([r["year"] for r in lvr])
    g3 = np.asarray([r["pgroup"] for r in lvr])
    k3 = [r["key"] for r in lvr]
    ll3 = {}
    for name, key in raters.items():
        u = pct_within([r["scores"][key] for r in lvr], g3)
        X = np.column_stack([np.ones(len(lvr)), u])
        p = np.zeros(len(lvr))
        for yr in np.unique(yrs):
            te = yrs == yr
            pen = np.array([0.0, 1e-6])
            b = logistic(X[~te], yr3[~te], np.ones(int((~te).sum())), pen)
            p[te] = sigmoid(X[te] @ b)
        p = np.clip(p, 1e-6, 1 - 1e-6)
        ll3[name] = -(yr3 * np.log(p) + (1 - yr3) * np.log(1 - p))
    out["reach_logloss"] = {n: _rnd(v.mean(), 5) for n, v in ll3.items()}
    for a, b in (("x3", "consensus"), ("x3", "served")):
        if a in ll3 and b in ll3:
            legs[f"{a}_minus_{b}|reach_ll"] = UV.cluster_boot(ll3[a] - ll3[b], k3, B=B_, seed=seed)
    out["legs"] = legs
    return out


def predictive_cdf(p: float, cond: float, resid: np.ndarray, grid) -> np.ndarray:
    """X3's predictive distribution of L6 on the grid (section 6.6): a mass of 1 - p at 0 and,
    given reach, cond plus the calibration residuals."""
    g = np.asarray(grid, dtype=np.float64)
    at0 = (g >= 0).astype(float)
    if resid.size:
        given = (cond + resid[None, :] <= g[:, None]).mean(axis=1)
    else:
        given = (cond <= g).astype(float)
    return (1 - p) * at0 + p * given


def pit_value(p: float, cond: float, resid: np.ndarray, y: float, rng) -> float:
    """The randomized PIT of y under the predictive distribution (the mass at 0 randomized)."""
    def cdf(x, strict=False):
        a0 = (0.0 < x) if strict else (0.0 <= x)
        v = cond + resid if resid.size else np.asarray([cond])
        gv = (v < x).mean() if strict else (v <= x).mean()
        return (1 - p) * float(a0) + p * float(gv)
    lo, hi = cdf(y, strict=True), cdf(y)
    return lo + rng.random() * (hi - lo)


def conformal_read(T: Table, main: dict, rows_by_fold: dict) -> dict:
    """Section 6.6's coverage checks pooled over the folds: the order interval, the six-season
    WAR interval, PIT deciles of the predictive distribution, and the anchor-only null."""
    rng = np.random.default_rng(SEED)
    out = {}
    for tag, cal_key, sc_name in (("x3", "conformal_cal", "X3"), ("anchor_only", "conformal_cal_anchor",
                                                                 "anchor_only")):
        inside_o = inside_w = n_o = n_w = 0
        width_o, width_w = [], []
        pits = []
        for fid_, rec in main["receipts"].items():
            cal = rec.get(cal_key)
            if not cal:
                continue
            qo = conformal_q(cal["order"])
            qw = conformal_q(cal["war"])
            resid = np.asarray(cal["cond_resid"], dtype=np.float64)
            rows = rows_by_fold[fid_]
            sc = main["scores"][sc_name]
            grp = fold_eval_groups(T, rows)
            fid = fid_.split("|")[0]
            lab = T.w3[rows] if fid == "lv_dev" else T.y_pin[rows]
            ok = np.isfinite(lab)
            e = np.asarray([sc[i]["e"] for i in rows])
            if qo is not None and ok.sum() > 2:
                u_y = pct_within(lab[ok], grp[ok])
                u_hat = pct_within(e, grp)[ok]
                inside_o += int((np.abs(u_y - u_hat) <= qo).sum())
                n_o += int(ok.sum())
                width_o.append(2 * qo)
            l6ok = T.l6_obs[rows] & np.isfinite(T.l6[rows])
            if qw is not None and l6ok.any():
                lo = np.maximum(e[l6ok] - qw, cal["l6_min"])
                hi = e[l6ok] + qw
                yv = T.l6[rows][l6ok]
                inside_w += int(((yv >= lo) & (yv <= hi)).sum())
                n_w += int(l6ok.sum())
                width_w.append(2 * qw)
            if tag == "x3":
                for j in np.flatnonzero(l6ok):
                    i = rows[j]
                    pits.append(pit_value(sc[i]["p"], sc[i]["cond"], resid, T.l6[i], rng))
        blk = {"order": {"n": n_o, "coverage": _rnd(inside_o / n_o, 4) if n_o else None,
                         "mean_width": _rnd(float(np.mean(width_o)), 4) if width_o else None},
               "war": {"n": n_w, "coverage": _rnd(inside_w / n_w, 4) if n_w else None,
                       "mean_width": _rnd(float(np.mean(width_w)), 3) if width_w else None}}
        for k in ("order", "war"):
            c = blk[k]["coverage"]
            blk[k]["covers"] = bool(c is not None and CONF_BAND[0] <= c <= CONF_BAND[1])
        if tag == "x3" and pits:
            h = np.histogram(np.asarray(pits), bins=10, range=(0, 1))[0] / len(pits)
            blk["pit"] = {"n": len(pits), "deciles": [_rnd(v, 4) for v in h],
                          "calibrated": bool(all(PIT_BAND[0] <= v <= PIT_BAND[1] for v in h))}
        out[tag] = blk
    out["nominal"] = CONF_NOMINAL
    out["band"] = list(CONF_BAND)
    return out


def x3_dist_table(T: Table, main: dict, rows_by_fold: dict) -> dict:
    import efv_upside_volatility as UV
    out = {}
    for fid_, rec in main["receipts"].items():
        cal = rec.get("conformal_cal") or {}
        resid = np.asarray(cal.get("cond_resid") or [], dtype=np.float64)
        for i in rows_by_fold[fid_]:
            sc = main["scores"]["X3"][i]
            out[i] = predictive_cdf(sc["p"], sc["cond"], resid, UV.GRID)
    return out


def role_rows(rows: list[dict], T: Table) -> dict:
    """{role: rows} of the pitcher rows by usage role at the read (section 6.7)."""
    out = {}
    for r in rows:
        if r["side"] != "pit":
            continue
        g = str(T.grp[r["i"]] or "")
        role = g.split(":", 1)[1] if ":" in g else None
        if role in ("STARTER", "SHORT-START", "RELIEF"):
            out.setdefault(role, []).append(r)
    return out


def verdict(leg_d: dict, d_served: float | None, null_p95: float | None, planted: dict) -> dict:
    """Section 9."""
    p = leg_d.get("player") or {}
    c = leg_d.get("club") or {}
    lp, lc = p.get("lb95"), c.get("lb95")
    A = bool(lp is not None and lc is not None and lp > 0 and lc > 0)
    Bc = bool(d_served is not None and d_served >= -MAX_TRAIL)
    D_ = leg_d.get("delta")
    Cc = bool(D_ is not None and null_p95 is not None and D_ > null_p95)
    Dc = bool(planted.get("recovered"))
    passed = A and Bc and Cc and Dc
    if passed:
        word = "beats"
    elif p.get("ub95") is not None and p["ub95"] < 0:
        word = "trails"
    else:
        word = "ties"
    return {"pass": passed, "verdict": "PASS" if passed else "FAIL", "word": word,
            "unresolved": not Dc, "A_lower_bound_above_0": A, "B_not_trailing_served": Bc,
            "C_above_null_p95": Cc, "D_planted_recovered": Dc, "D": D_,
            "lb95_player": lp, "lb95_club": lc, "ub95_player": p.get("ub95"),
            "ci95_player": p.get("ci95"), "ci95_club": c.get("ci95"),
            "mde95_player": p.get("mde95"), "mde95_club": c.get("mde95"),
            "x3_minus_served": _rnd(d_served), "null_p95": null_p95}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

class Run:
    def __init__(self, cache_dir: Path, *, today: str | None = None, log=print, workers: int = 1):
        self.cache = Path(cache_dir)
        self.today = today or date.today().isoformat()
        self.log = log
        self.workers = int(workers)

    def _load(self, name):
        p = self.cache / f"{name}.pkl"
        if p.exists():
            with p.open("rb") as fh:
                return pickle.load(fh)
        return None

    def _save(self, name, obj):
        self.cache.mkdir(parents=True, exist_ok=True)
        tmp = self.cache / f"{name}.pkl.tmp"
        with tmp.open("wb") as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(self.cache / f"{name}.pkl")

    def comparator(self) -> dict:
        got = self._load("x3_comparator")
        if got is not None:
            return got
        import efv_beat_tilted_labels as TL
        comp = TL.build(self.cache, log=self.log)
        self._save("x3_comparator", comp)
        return comp

    def instances(self) -> dict:
        got = self._load("x3_instances")
        if got is not None:
            return got
        b = Builder(self.cache, today=self.today, log=self.log).build()
        self._save("x3_instances", b)
        return b

    def prep(self) -> tuple:
        import efv_etools_reweight as ER
        import __main__
        for cls in ("Bank", "RowMeta"):
            if not hasattr(__main__, cls):
                setattr(__main__, cls, getattr(ER, cls))
        comp = self.comparator()
        built = self.instances()
        T = Table(built["instances"])
        g = guards(T)
        with (self.cache / "tilted_build1.pkl").open("rb") as fh:
            inp = pickle.load(fh)["inp"]
        folds = fold_list(T, inp)
        ets = self._load("x3_fold_etools")
        if ets is None:
            with (self.cache / "er" / "bank.pkl").open("rb") as fh:
                bank0, _r = pickle.load(fh)
            ets = build_fold_etools(T, folds, bank0, built["rm_z"], log=self.log)
            self._save("x3_fold_etools", ets)
        return comp, built, T, inp, folds, ets, g

    def pipeline(self, name: str, T, folds, ets, **kw) -> dict:
        got = self._load(f"x3_run_{name}")
        if got is not None:
            return got
        self.log(f"  run {name}")
        out = run_pipeline(T, folds, ets["values"], log=self.log, **kw)
        self._save(f"x3_run_{name}", out)
        return out


RUN_SPECS: dict[str, dict] = {
    "main": {},
    "null_censor": {"variant": {"censor": "zero"}, "lite": True},
    "null_imr": {"variant": {"imr": "perm"}, "lite": True},
    "null_lambda": {"variant": {"lam": "perm"}, "lite": True},
    "null_shift": {"variant": {"shift": "uniform"}, "lite": True},
    "null_role": {"variant": {"role": "perm"}, "lite": True},
    "planted": {"plant": True, "lite": True},
    "sensitivity": {"sensitivity": True, "lite": True},
    **{f"perm_{s}": {"perm_seed": s, "lite": True} for s in NULL_SEEDS},
}
COMPONENT_NULLS = {"6.1 censoring": "null_censor", "6.2 survivorship": "null_imr",
                   "6.3 consensus reliability": "null_lambda", "6.4 covariate shift": "null_shift",
                   "6.5 role path": "null_role"}


def run_named(cache_dir: Path, names: list[str], *, log=print) -> None:
    """Compute and cache the named pipeline runs (no statistic)."""
    R = Run(cache_dir, log=log)
    _c, _b, T, _inp, folds, ets, _g = R.prep()
    for n in names:
        R.pipeline(n, T, folds, ets, **RUN_SPECS[n])


def read(cache_dir: Path, *, B_: int = B, log=print) -> dict:
    """The registered read, once (sections 7 to 10)."""
    import efv_beat_pooled_power as PP
    import efv_labels as L
    t0 = time.time()
    R = Run(cache_dir, log=log)
    comp, built, T, inp, folds, ets, g = R.prep()
    runs = {n: R.pipeline(n, T, folds, ets, **spec) for n, spec in RUN_SPECS.items()}
    main = runs["main"]
    rows_by_fold = {f["id"]: f["test"] for f in folds}
    keys = {"main": "x3"}
    keys.update({n: n for n in runs if n != "main"})
    rows_all = pool_rows(T, comp, inp, {keys[n]: runs[n] for n in runs})
    rows = PP.dedupe(rows_all, PP.DEDUP_PRIMARY)
    log(f"pool: {len(rows)} rows after keep_lv ({len(rows_all)} before)")
    ok_keys = set.intersection(*[set(r["scores"]) for r in rows])
    # the comparisons (section 8): X3 first (the estimand)
    comps = [("x3_vs_consensus", "x3", CONS), ("x3_vs_served", "x3", SERVED),
             ("x3_vs_v5c", "x3", V5C_KEY), ("x3_vs_v2", "x3", V2_KEY),
             ("served_vs_consensus", SERVED, CONS)]
    for nm in ("X3_ridge", "X3_gbm", "W3_ridge", "W3_gbm", "L6_ridge", "L6_gbm"):
        k = f"x3:{nm}"
        if k in ok_keys:
            comps += [(f"{nm.lower()}_vs_consensus", k, CONS), (f"{nm.lower()}_vs_served", k, SERVED)]
    pooled = read_legs(rows, comps, B_=B_, seed=SEED, log=log)
    per_frame = {}
    for fid in FRAMES:
        fr = [r for r in rows if r["frame"] == fid]
        per_frame[fid] = read_legs(fr, comps[:5], B_=B_, seed=SEED, log=log)
    # the component nulls (section 6), point and player-clustered interval against X3
    comp_nulls = {}
    for label, n in COMPONENT_NULLS.items():
        k = n
        res = read_legs(rows, (("x3_minus_null", "x3", k),), B_=B_, seed=SEED, clusterings=("player",),
                        log=lambda *_a: None)
        leg = res["legs"]["x3_minus_null|both"]
        comp_nulls[label] = {"run": n, "delta": leg["delta"], "ci95": (leg.get("player") or {}).get("ci95"),
                             "lb95": (leg.get("player") or {}).get("lb95")}
    # clause (C): the 20 null reruns
    D_obs = point_delta(rows, "x3", CONS)
    null_d = [point_delta(rows, f"perm_{s}", CONS) for s in NULL_SEEDS]
    null_d = [d for d in null_d if d is not None]
    p95 = float(np.quantile(null_d, 0.95)) if null_d else None
    clause_c = {"draws": [_rnd(d) for d in null_d], "p95": _rnd(p95), "observed": _rnd(D_obs),
                "above": bool(D_obs is not None and p95 is not None and D_obs > p95)}
    # clause (D): the planted rerun
    pl = read_legs(rows, (("planted_vs_consensus", "planted", CONS),), B_=B_, seed=SEED,
                   clusterings=("player",), log=lambda *_a: None)["legs"]["planted_vs_consensus|both"]
    clause_d = {"delta": pl["delta"], "lb95_player": (pl.get("player") or {}).get("lb95"),
                "ci95": (pl.get("player") or {}).get("ci95"),
                "recovered": bool((pl.get("player") or {}).get("lb95") is not None
                                  and pl["player"]["lb95"] > 0)}
    # sensitivity (13.7)
    sens = read_legs(rows, (("sensitivity_vs_consensus", "sensitivity", CONS),
                            ("sensitivity_vs_x3", "sensitivity", "x3")), B_=B_, seed=SEED,
                     clusterings=("player",), log=lambda *_a: None)
    est = pooled["legs"]["x3_vs_consensus|both"]
    d_served = pooled["legs"]["x3_vs_served|both"]["delta"]
    v = verdict(est, d_served, p95, clause_d)
    # pitcher-by-role (6.7)
    by_role = {}
    for role, rr in role_rows(rows, T).items():
        cnt = {}
        for r in rr:
            cnt[r["pgroup"]] = cnt.get(r["pgroup"], 0) + 1
        rr2 = [dict(r, pgroup=f"{r['pgroup']}|{role}") for r in rr if cnt[r["pgroup"]] >= MIN_GROUP]
        if not rr2:
            by_role[role] = {"n": len(rr), "status": f"no (frame, side, year) group of {MIN_GROUP} rows"}
            continue
        res = read_legs(rr2, (("x3_vs_consensus", "x3", CONS), ("x3_vs_served", "x3", SERVED)),
                        B_=B_, seed=SEED, clusterings=("player",), log=lambda *_a: None)
        by_role[role] = {"n": len(rr2), "n_before_group_floor": len(rr),
                         "x3_vs_consensus": _leg(res["legs"]["x3_vs_consensus|both"]),
                         "x3_vs_served": _leg(res["legs"]["x3_vs_served|both"])}
    # distributional scores (7.4)
    dist = dist_block(rows, T, {"x3": "x3", "consensus": CONS, "served": SERVED},
                      x3_dist_table(T, main, rows_by_fold), B_=B_, seed=SEED)
    conf = conformal_read(T, main, rows_by_fold)
    synth = planted_checks()
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "registration": DOC,
           "registration_commit": REGISTRATION_COMMIT, "generated_at": _now(),
           "role": "development", "adjudicates": False,
           "owner_decisions": ["EW3-12", "EW3-13", "EW3-21", "EW3-26", "EW3-35", "EW3-41", "EW3-42"],
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": (comp.get("label_id") or {}).get("id")},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool_sha256": _sha(ROOT / TOOL)},
           "guards": g, "comparator_parity": comp["receipts"].get("parity"),
           "instances": built["receipts"],
           "fold_etools_fits": ets.get("fits"),
           "statistic": {"estimand": "W(X3) - W(PROSPX consensus), within (frame, side, year) "
                                     "Spearman, size-weighted, keep_lv, groups of 20 or more",
                         "B": int(B_), "seed": SEED, "estimator": "E_cond, paired"},
           "pool": {"n": pooled["n"], "n_players": pooled["n_players"], "n_by_frame": pooled["n_by_frame"],
                    "n_by_side": pooled["n_by_side"], "groups": pooled["groups_kept"]},
           "legs": {k: _leg(v_) for k, v_ in pooled["legs"].items()},
           "per_frame": {fid: {k: _leg(v_) for k, v_ in blk["legs"].items()} for fid, blk in per_frame.items()},
           "verdict": v, "clause_c_null": clause_c, "clause_d_planted": clause_d,
           "component_nulls": comp_nulls,
           "sensitivity_etools_raw_speed": {k: _leg(v_) for k, v_ in sens["legs"].items()},
           "pitcher_by_role": by_role, "distributional": dist, "conformal": conf,
           "planted_synthetic": synth,
           "folds": {fid: _fold_out(rec) for fid, rec in main["receipts"].items()},
           "runs": {n: {"seconds": r["seconds"], "variant": r["variant"], "perm_seed": r["perm_seed"],
                        "plant": r["plant"], "sensitivity": r["sensitivity"],
                        "selected": {fid: rec.get("selected") for fid, rec in r["receipts"].items()}}
                    for n, r in runs.items()},
           "reweight_tool_weights": reweight_weights(),
           "x3_weights": weights_report(main),
           "elapsed_s": round(time.time() - t0, 1)}
    return doc


def weights_report(main: dict) -> dict:
    """Section 13.6: every pitch-rate, eTool and inverse Mills ratio slope of the best ridge
    configuration (X3-ridge) per stage, across the outer folds (the side slope, mean and range),
    and the boosted configuration's gain shares."""
    keys = {f"{f}|{s}" for s in SIDES for f in list(PITCH_RATES[s]) + [
        f for f in FEATURES[s] if f.startswith("e_")] + ["imr", "p_rel", "p_rel_x_uc"]}
    keys |= {f"{f}|hit" for f in ("e_raw", "e_spd")}
    ridge: dict = {}
    gain: dict = {}
    for fid, rec in main["receipts"].items():
        for stage, c in ((rec.get("coef") or {}).get("X3_ridge") or {}).items():
            for k, v in c.items():
                if k in keys and v is not None:
                    ridge.setdefault(stage, {}).setdefault(k, []).append(float(v))
        for stage, g in ((rec.get("gbm_gain") or {}).get("X3_gbm") or {}).items():
            for k, v in g.items():
                if any(k == f for s in SIDES for f in PITCH_RATES[s]) or k.startswith("e_") or k == "imr":
                    gain.setdefault(stage, {}).setdefault(k, []).append(float(v))
    out = {"ridge_side_slopes": {st: {k: {"mean": _rnd(np.mean(v), 5), "min": _rnd(min(v), 5),
                                          "max": _rnd(max(v), 5), "folds": len(v)}
                                      for k, v in sorted(d.items())} for st, d in ridge.items()},
           "gbm_gain_share": {st: {k: {"mean": _rnd(np.mean(v), 4), "folds": len(v)}
                                   for k, v in sorted(d.items())} for st, d in gain.items()},
           "note": ("ridge slopes are per standard deviation of the z-scored feature on the stage's "
                    "scale (R: log odds of reaching; T: seasons of 600 PA or 700 BF; Q: WAR per "
                    "such season); a slope of 0 means the penalty removed it")}
    return out


def _leg(leg: dict) -> dict:
    out = {k: leg.get(k) for k in ("a", "b", "scope", "n", "w_a", "w_b", "delta")}
    for cl in ("player", "club"):
        if leg.get(cl):
            out[cl] = {k: leg[cl].get(k) for k in ("mde95", "lb95", "ub95", "ci95", "p_gt_0", "n_clusters", "B_used")}
    return out


def _fold_out(rec: dict) -> dict:
    out = {k: v for k, v in rec.items() if k not in ("conformal_cal", "conformal_cal_anchor")}
    for k in ("conformal_cal", "conformal_cal_anchor"):
        c = rec.get(k)
        if c:
            out[k] = {"n_order": len(c["order"]), "n_war": len(c["war"]), "q_order": _rnd(conformal_q(c["order"]), 4),
                      "q_war": _rnd(conformal_q(c["war"]), 3)}
    return out


def reweight_weights() -> dict:
    """EFV_ETOOLS_REWEIGHT's production tool weights (printed beside X3's, section 3.4)."""
    p = DATA_DIR / "_labs" / "efv5" / "efv_etools_reweight_fit.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for cand, blk in (d.get("production") or {}).items():
        out[cand] = {s: [{"driver": r.get("driver"), "beta": r.get("beta"),
                          "weight_pct_equiv": r.get("weight_pct_equiv")}
                         for r in rows] for s, rows in (blk.get("tool_weights") or {}).items()}
    return out


# ---------------------------------------------------------------------------
# the planted synthetic checks (section 6, each component; seeded)
# ---------------------------------------------------------------------------

def synth_censoring(seed: int = SEED) -> dict:
    """6.1: 4,000 synthetic players over 12 debut years; the censoring-aware estimate of the
    six-season PT sum within 5 percent of the truth and the zero-fill estimate not."""
    rng = np.random.default_rng(seed)
    n = 4000
    d = rng.integers(RESOLVED - 11, RESOLVED + 1, n)
    x = rng.standard_normal(n)
    mean_k = np.array([0.3, 0.6, 0.7, 0.7, 0.65, 0.6])
    truth = float((mean_k.sum() + 0.0) * 1.0)
    rows_k, rows_x, rows_y, rows_k0, rows_x0, rows_y0 = [], [], [], [], [], []
    for i in range(n):
        for k in range(SEASONS_K):
            y = max(0.0, mean_k[k] * (1 + 0.2 * x[i]) + 0.1 * rng.standard_normal())
            if d[i] + k <= RESOLVED:
                rows_k.append(k); rows_x.append(x[i]); rows_y.append(y)  # noqa: E702
                rows_k0.append(k); rows_x0.append(x[i]); rows_y0.append(y)  # noqa: E702
            else:
                rows_k0.append(k); rows_x0.append(x[i]); rows_y0.append(0.0)  # noqa: E702

    def est(kk, xx, yy):
        kk, xx, yy = np.asarray(kk), np.asarray(xx), np.asarray(yy)
        X = np.column_stack([(kk == j).astype(float) for j in range(SEASONS_K)] + [xx])
        b = wls(X, yy, np.ones(yy.size), np.zeros(X.shape[1]))
        return float(b[:SEASONS_K].sum())
    a, z = est(rows_k, rows_x, rows_y), est(rows_k0, rows_x0, rows_y0)
    truth = float(mean_k.sum())
    ok = abs(a - truth) / truth <= 0.05 and abs(z - truth) / truth > 0.05
    return {"truth": _rnd(truth, 4), "censoring_aware": _rnd(a, 4), "zero_fill": _rnd(z, 4), "pass": bool(ok)}


def synth_heckman(seed: int = SEED, reps: int = 100) -> dict:
    """6.2: selection with correlated errors (rho 0.5); the two-step slope closer to the truth
    than the uncorrected slope in at least 90 of 100 replications."""
    from scipy.stats import norm
    rng = np.random.default_rng(seed)
    wins = 0
    for _ in range(reps):
        # no exclusion restriction: the selection index is nonlinear in the outcome feature
        # itself, as X3's stage R is (section 6.2)
        n = 4000
        x = rng.standard_normal(n)
        e1 = rng.standard_normal(n)
        e2 = 0.5 * e1 + math.sqrt(0.75) * rng.standard_normal(n)
        sel = (0.2 + 0.9 * x + 0.6 * x ** 2 - 0.6 + e1) > 0
        y = 1.0 + 0.5 * x + e2
        Xs = np.column_stack([np.ones(n), x, x ** 2])
        b = logistic(Xs, sel.astype(float), np.ones(n), np.zeros(3))
        p = sigmoid(Xs @ b)
        lam_ = norm.pdf(norm.ppf(np.clip(p, 1e-4, 1 - 1e-4))) / np.clip(p, 1e-4, 1)
        Xo = np.column_stack([np.ones(sel.sum()), x[sel]])
        b0 = np.linalg.lstsq(Xo, y[sel], rcond=None)[0][1]
        Xc = np.column_stack([np.ones(sel.sum()), x[sel], lam_[sel]])
        b1 = np.linalg.lstsq(Xc, y[sel], rcond=None)[0][1]
        wins += int(abs(b1 - 0.5) < abs(b0 - 0.5))
    return {"reps": reps, "two_step_closer": wins, "pass": bool(wins >= 90)}


def synth_eiv(seed: int = SEED) -> dict:
    """6.3: consensus = truth + noise with variance falling in n; the slope on u_c x lambda is
    positive with its 95 percent interval above 0."""
    rng = np.random.default_rng(seed)
    n = 6000
    truth = rng.standard_normal(n)
    k = rng.integers(1, 6, n).astype(float)
    graders = truth[:, None] + 1.5 * rng.standard_normal((n, 5))
    use = np.arange(5)[None, :] < k[:, None]
    cons = np.where(use, graders, 0.0).sum(axis=1) / k
    dev = np.where(use, graders - cons[:, None], 0.0)
    s_obs = np.where(k >= 2, np.sqrt((dev ** 2).sum(axis=1) / np.maximum(k - 1, 1)), 0.0)
    y = truth + 0.5 * rng.standard_normal(n)
    sig_e2 = float(np.mean(s_obs[k >= 2] ** 2))
    tau2 = max(float(np.var(cons) - np.mean(sig_e2 / k)), 0.25 * sig_e2)
    sig_i2 = ((k - 1) * s_obs ** 2 + 2 * sig_e2) / (k + 1)
    lam = tau2 / (tau2 + sig_i2 / k)
    u = pct_within(cons, [0] * n)
    uy = pct_within(y, [0] * n)
    X = np.column_stack([np.ones(n), u, u * (lam - lam.mean())])
    b = np.linalg.lstsq(X, uy, rcond=None)[0]
    r = uy - X @ b
    cov = np.linalg.inv(X.T @ X) * float(r @ r) / (n - 3)
    se = float(math.sqrt(cov[2, 2]))
    lo = float(b[2] - 1.96 * se)
    return {"slope": _rnd(b[2], 4), "ci95_lo": _rnd(lo, 4), "pass": bool(b[2] > 0 and lo > 0)}


def synth_shift(seed: int = SEED) -> dict:
    """6.4: training and target samples with a known density ratio; the estimated log weights
    correlate with the true ones at 0.8 or more."""
    rng = np.random.default_rng(seed)
    ntr, nlv = 4000, 1500
    xtr = rng.standard_normal((ntr, 3))
    xlv = rng.standard_normal((nlv, 3)) + np.array([0.5, -0.3, 0.0])
    X = np.vstack([xtr, xlv])
    y = np.concatenate([np.zeros(ntr), np.ones(nlv)])
    Xd = np.column_stack([np.ones(X.shape[0]), X])
    pen = np.array([0.0, SHIFT_RIDGE, SHIFT_RIDGE, SHIFT_RIDGE])
    b = logistic(Xd, y, np.ones(y.size), pen)
    p = sigmoid(Xd[:ntr] @ b)
    est = np.log(p / (1 - p))
    true = xtr @ np.array([0.5, -0.3, 0.0])
    r = float(np.corrcoef(est, true)[0, 1])
    return {"corr": _rnd(r, 4), "pass": bool(r >= 0.8)}


def synth_role(seed: int = SEED) -> dict:
    """6.5: synthetic pitchers whose reliever outcome follows GS / G; held-out AUC 0.8 or more."""
    rng = np.random.default_rng(seed)
    n = 3000
    gs = rng.random(n)
    ipg = 1 + 4 * gs + 0.5 * rng.standard_normal(n)
    other = rng.standard_normal((n, 6))
    y = (rng.random(n) < sigmoid(4.0 - 8.0 * gs)).astype(float)
    X = np.column_stack([np.ones(n), gs, ipg, other])
    tr = np.arange(n) < 2000
    pen = np.full(X.shape[1], ROLE_RIDGE)
    pen[0] = 0
    b = logistic(X[tr], y[tr], np.ones(int(tr.sum())), pen)
    a = auc(sigmoid(X[~tr] @ b), y[~tr])
    return {"auc": _rnd(a, 4), "pass": bool(a is not None and a >= 0.8)}


def synth_conformal(seed: int = SEED) -> dict:
    """6.6: exchangeable synthetic data, n 2,000; coverage inside 0.77 to 0.83."""
    rng = np.random.default_rng(seed)
    n = 2000
    x = rng.standard_normal(n * 2)
    y = x + rng.standard_normal(n * 2)
    cal = np.abs(y[:n] - x[:n])
    q = conformal_q(cal)
    cov = float((np.abs(y[n:] - x[n:]) <= q).mean())
    return {"coverage": _rnd(cov, 4), "pass": bool(0.77 <= cov <= 0.83)}


def planted_checks() -> dict:
    return {"6.1 censoring": synth_censoring(), "6.2 survivorship": synth_heckman(),
            "6.3 consensus reliability": synth_eiv(), "6.4 covariate shift": synth_shift(),
            "6.5 role path": synth_role(), "6.6 conformal": synth_conformal()}


# ---------------------------------------------------------------------------
# the ledger (two development rows) and the artifact
# ---------------------------------------------------------------------------

def write(doc: dict) -> Path:
    import efv_v3_backtest as BT
    return BT.write_doc(doc, OUT_PATH)


def ledger_rows(doc: dict, *, artifact: Path, date_: str, now_iso: str) -> list[dict]:
    """Two development rows (model efv_x3_pooled, role development, adjudicating nothing)."""
    import efv_progress as P
    import efv_v2_stat as S
    lab = doc.get("label") or {}
    mv = {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    rows = []
    for fid in FRAMES:
        meta = P.FRAMES[fid]
        if meta["role"] != "development":
            raise ValueError(f"{fid} is registered as {meta['role']}, not development")
        legs = doc["per_frame"][fid]
        est = legs["x3_vs_consensus|both"]
        srv = legs["x3_vs_served|both"]
        raters = {"efv_x3_pooled": {"spearman": est.get("w_a"), "auc": None, "n": est.get("n")},
                  "prospx_consensus": {"spearman": est.get("w_b"), "auc": None, "n": est.get("n")},
                  "efv": {"spearman": srv.get("w_b"), "auc": None, "n": srv.get("n")}}
        deltas = {}
        for name, leg in (("vs_prospx_consensus", est), ("vs_efv_served", srv)):
            pl = leg.get("player") or {}
            deltas[name] = {"spearman": {"delta": leg.get("delta"), "ci95": pl.get("ci95"),
                                         "mde95": pl.get("mde95"), "mde95_estimator": "E_cond",
                                         "ci95_estimator": "E_cond", "resolvable": None,
                                         "reading": None,
                                         "key": f"per_frame.{fid}.{leg.get('a')}_vs_{leg.get('b')}"}}
        nbs = None
        row = {"run_id": None, "date": date_, "trigger": "efv_change", "model_id": LEDGER_MODEL_ID,
               "model_version": dict(mv), "frame": fid, "frame_version": None,
               "role": meta["role"], "tilted": bool(meta["tilted"]), "window": None,
               "n": est.get("n"), "n_by_side": nbs, "raters": raters, "deltas": deltas,
               "resolvable": None,
               "verdict": (f"DEVELOPMENT ONLY (the pooled model X3): within vs PROSPX consensus "
                           f"{_rnd(est.get('delta'), 4)} (CI95 {(est.get('player') or {}).get('ci95')}), "
                           f"vs the served eFV {_rnd(srv.get('delta'), 4)}; adjudicates nothing"),
               "share": None, "sources": [dict(s) for s in src],
               "note": f"eFV X3 pooled model ({ITEM}; {DOC}); development read, adjudicates nothing",
               "last_verified_at": now_iso, "statistic": S.STAT_LABEL[S.PRIMARY]}
        P._finish(row)
        row["run_id"] = f"{doc.get('generated_at')}|{fid}|{row['content_hash'][:8]}"
        rows.append(row)
    return rows


def append_ledger(doc: dict, *, artifact: Path, ledger_path: Path) -> dict:
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    rows = ledger_rows(doc, artifact=artifact, date_=now.date().isoformat(), now_iso=now_iso)
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    return P.commit_rows(rows, data_dir=P.DATA_DIR, ledger_path=Path(ledger_path),
                         sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)


def summary_lines(doc: dict) -> list[str]:
    v = doc["verdict"]
    out = [f"VERDICT: {v['verdict']} ({v['word']}{', UNRESOLVED' if v['unresolved'] else ''})",
           f"D = X3 minus consensus {v['D']} (lb95 player {v['lb95_player']}, club {v['lb95_club']}; "
           f"mde95 {v['mde95_player']})",
           f"X3 minus served {v['x3_minus_served']}; null p95 {v['null_p95']}; planted {doc['clause_d_planted']}"]
    for k, leg in doc["legs"].items():
        if k.endswith("|both"):
            out.append(f"  {k}: delta {leg['delta']} ci95 {(leg.get('player') or {}).get('ci95')}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prep", action="store_true", help="instances and fold eTools; no statistic")
    ap.add_argument("--runs", default=None, help="comma-separated pipeline runs to compute and cache")
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="the scratch directory of the cached builds")
    ap.add_argument("--B", type=int, default=B)
    ap.add_argument("--ledger", action="store_true", help="append the two development rows")
    ap.add_argument("--ledger-path", default=None)
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    import efv_labels as L
    if a.ledger:
        if not OUT_PATH.exists():
            log("refused: the artifact does not exist")
            return 2
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        led = Path(a.ledger_path) if a.ledger_path else ROOT / ".cache" / "efv_x3" / "progress_ledger.jsonl"
        r = append_ledger(doc, artifact=OUT_PATH, ledger_path=led)
        log(f"progress ledger: appended {len(r['appended'])} rows, {r['n_rows']} rows")
        return 0
    if not a.cache:
        log("refused: pass --cache <scratch dir>")
        return 2
    if L.provider() != "fwar":
        log(f"refused: label provider is {L.provider()!r}, not the frozen 'fwar'")
        return 2
    if a.prep:
        Run(Path(a.cache), log=log).prep()
        return 0
    if a.runs:
        run_named(Path(a.cache), [n for n in a.runs.split(",") if n], log=log)
        return 0
    if a.run:
        if _git("cat-file", "-e", REGISTRATION_COMMIT) is None:
            log("refused: the registration commit is not in this repository")
            return 2
        if OUT_PATH.exists():
            log(f"refused: {OUT_PATH} exists; the read runs once")
            return 2
        doc = read(Path(a.cache), B_=int(a.B), log=log)
        write(doc)
        for line in summary_lines(doc):
            log(line)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

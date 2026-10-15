# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV tracking-era head (EFV5_TRACKING_HEAD; owner 2026-10-14, decision EW3-1;
registration docs/efv-v2/EFV_TRACKING_HEAD_GATE.md, committed before this file existed).

WHAT IT IS. A separate, clearly labelled head for prospects whose as-of record carries
MiLB pitch tracking (Savant minors, 2021 and later: the Florida State League and, from
2022, Triple-A). It combines PROSPX consensus FV with the tracking candidates the owner's
task named and is scored on a SHORT label the tracking-era cohorts can already resolve:

    reach3   reached MLB within 3 seasons after the tracked season S
    rate3    fWAR per MLB season over the MLB seasons inside S+1 .. S+3 (0 without one)

Two heads per side on X = [1, AAA, z(consensus FV), z(metrics)]: a ridge logistic reach
head and a ridge rate head fitted on the reached rows (the hurdle form of eFV v2). The one
output per row is order_head = P(reach3) * E[rate3 | reached], unclipped. The only choice
the run makes is one penalty per head from LAMBDAS, by player-grouped cross-validation on
the TRAINING cohorts (2021, 2022); the held-out cohort (2023) is scored once, after the
selection is written to the artifact, against consensus FV and the served eFV v2 fold
object on the same rows (section 6 of the registration). The ship rule (section 8) is
applied by `ship_verdict` and nothing else; EFV_TRACKING_HEAD_ON stays False in this file.

DARK. No served module imports this file; nothing it writes is read by a served exporter.
GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus FV enters only as a continuous
covariate and as a comparator score; nothing here groups, counts or averages anything by
consensus-FV level. RESERVED FRAMES: no R-LV list vintage (2020, 2021) is built (the
consensus vintages are V 2022 to 2024); rows whose label window reaches a 2025 or later
debut cohort (R-VM, spent) are flagged `spent` on every number they touch.

Run:  python efv5_tracking_head.py --run [--b 2000]   (the one registered read; writes
                                                       data/efv5_tracking_head.json)
      python efv5_tracking_head.py --md               (the results document from the artifact)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import efv5_atlas as A
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "efv5_tracking_head.json"
GATE_DOC = ROOT / "docs" / "efv-v2" / "EFV_TRACKING_HEAD_GATE.md"
RESULTS_DOC = ROOT / "docs" / "efv-v2" / "EFV_TRACKING_HEAD_RESULTS.md"
TOOL = "efv5_tracking_head.py"
ITEM = "EFV5_TRACKING_HEAD"
SCHEMA = 1
NOTE = ("eFV tracking-era head, development read (EW3-1): short-horizon label, nothing "
        "served moves, no number by consensus-FV level, consensus FV a covariate and a "
        "comparator only")
SPENT_NOTE = ("spent: the label window reaches a 2025 or later debut cohort (R-VM, spent "
              "since the 10-08 confirmation); an owner-authorised short-horizon read (EW3-1)")

#: The served switch. Flipped only by the ship path the registration names (section 8),
#: never by this task's own commits.
EFV_TRACKING_HEAD_ON = False

#: Declared in the registration before any read.
N_SEASONS = 3
HORIZON = 2026
TRAIN_COHORTS: tuple[int, ...] = (2021, 2022)
HOLDOUT_COHORT = 2023
COHORTS: tuple[int, ...] = TRAIN_COHORTS + (HOLDOUT_COHORT,)
CONSENSUS_VINTAGES: tuple[int, ...] = tuple(s + 1 for s in COHORTS)      # 2022, 2023, 2024
LEVEL_ORDER = ("A", "AAA")                     # the tracked levels; the higher wins a tie
CORE = {"pit": ("astuff_plus", "fb_velo_p95", "fb_ivb", "xwoba_against", "ev_against"),
        "hit": ("ev_p90", "hard_hit", "barrel", "chase", "zone_contact")}
IMPUTED = {"pit": ("arm_angle",), "hit": ()}
NAMES = {"astuff_plus": "aStuff+", "fb_velo_p95": "top-end fastball velocity (95th pct)",
         "fb_ivb": "fastball ride (induced vertical break)", "xwoba_against": "xwOBA against",
         "ev_against": "exit velocity against", "arm_angle": "arm angle",
         "ev_p90": "exit velocity, 90th pct", "hard_hit": "hard-hit rate", "barrel": "barrel rate",
         "chase": "chase rate", "zone_contact": "zone contact rate"}
LAMBDAS: tuple[float, ...] = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, math.inf)
FOLDS = 5
SEED = 20261015
B_DEFAULT = 2000
MIN_ROWS, MIN_POS, MIN_NEG = 50, 10, 10          # a readable side
GROUP_MIN_ROWS, GROUP_MIN_POS = 20, 5            # a reported group
WEIGHT_SHARE = 0.15                              # "carries weight" (section 5)
BLEND_W = 0.5                                    # D-1, if a side ships
NEWTON_ITERS = 25
RP_GS_SHARE = A.RP_GS_SHARE
SURFACE_NOTE = ("tracking-era head, short-horizon label (reached MLB within 3 seasons; "
                "fWAR per MLB season over those seasons)")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def metrics_of(side: str) -> tuple[str, ...]:
    return tuple(CORE[side]) + tuple(IMPUTED[side])


# ---------------------------------------------------------------------------
# labels (section 2)
# ---------------------------------------------------------------------------

def labels3(pid: int, season: int, mlb: dict, war: dict) -> dict | None:
    """reach3 and rate3 of one (player, S) row; None when the player had a MLB line at or
    before S. Only seasons S+1 .. S+N_SEASONS are read."""
    seasons = mlb.get(pid) or set()
    if any(s <= season for s in seasons):
        return None
    inside = sorted(s for s in seasons if season < s <= season + N_SEASONS)
    reach = 1.0 if inside else 0.0
    rate = (float(sum(war.get((pid, s), 0.0) for s in inside)) / len(inside)) if inside else 0.0
    return {"reach3": reach, "rate3": rate}


def spent(season: int) -> bool:
    """The row's label window reaches a reserved (spent) R-VM debut cohort."""
    return int(season) + N_SEASONS >= F.R_VM_FIRST_DEBUT_YEAR


# ---------------------------------------------------------------------------
# the frame (section 3)
# ---------------------------------------------------------------------------

def pick_rows(trk: dict, side: str, cohorts=COHORTS) -> dict:
    """{(pid, S): (level, metric values)}: one tracked line per player and cohort season,
    the higher level winning; only rows with every CORE metric present."""
    out: dict = {}
    rank = {lv: i for i, lv in enumerate(LEVEL_ORDER)}
    for (pid, season, level), vals in trk.items():
        if season not in cohorts or level not in rank:
            continue
        m = {k: vals.get(f"trk_{k}_{side}") for k in metrics_of(side)}
        if any(m[k] is None for k in CORE[side]):
            continue
        key = (int(pid), int(season))
        cur = out.get(key)
        if cur is None or rank[level] > rank[cur[0]]:
            out[key] = (level, m)
    return out


def pitcher_roles(seasons=COHORTS) -> dict:
    """{(pid, S, level): "SP" | "RP"} by the EFV3_C05 rule on the row's own season line."""
    out = {}
    for (pid, season, level), c in A.box_lines("pit", seasons=tuple(seasons)).items():
        g = c.get("g") or 0.0
        if g > 0:
            out[(pid, season, level)] = "RP" if (c.get("gs") or 0.0) / g < RP_GS_SHARE else "SP"
    return out


def build_rows(side: str, *, mlb: dict, war: dict, cons: dict, roles: dict | None = None,
               trk: dict | None = None) -> list[dict]:
    trk = A.tracking_metrics(side) if trk is None else trk
    picked = pick_rows(trk, side)
    rows = []
    for (pid, season), (level, m) in sorted(picked.items()):
        cr = cons.get((pid, season))
        if cr is None:
            continue
        y = labels3(pid, season, mlb, war)
        if y is None:
            continue
        group = (roles or {}).get((pid, season, level)) if side == "pit" else cr.get("group")
        rows.append({"pid": pid, "season": season, "level": level,
                     "player_key": cr["player_key"], "fv": float(cr["fv"]),
                     "group": group, "m": m, "reach3": y["reach3"], "rate3": y["rate3"],
                     "spent": spent(season),
                     "role": "train" if season in TRAIN_COHORTS else "holdout"})
    return rows


def frame_counts(rows: list[dict]) -> list[dict]:
    out: dict = {}
    for r in rows:
        k = (r["season"], r["level"])
        c = out.setdefault(k, {"season": r["season"], "level": r["level"], "role": r["role"],
                               "rows": 0, "reach3_pos": 0, "spent": r["spent"]})
        c["rows"] += 1
        c["reach3_pos"] += int(r["reach3"] > 0)
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------------------
# served V2 on the same rows (section 6)
# ---------------------------------------------------------------------------

def v2_order_scores(sides=F.SIDES, vintages=CONSENSUS_VINTAGES, *, log=print) -> tuple[dict, dict]:
    """{side: {(player_key, S): order_idx}} from the V2 fold object fitted on the labelled
    development vintages with every V-frame player left out (efv_v2_model.v2_lv_scores),
    scoring the full F-LV frame of each V with the V2 sidecars attached as
    tools/efv_v2_assemble.build_frames attaches them. Reserved vintages never asked."""
    sys.path.insert(0, str(ROOT / "tools"))
    import efv_drivers as DRV
    import efv_v2_assemble as ASM
    import efv_v2_model as H
    for V in vintages:
        assert int(V) not in F.RESERVED_LV
    t0 = time.time()
    frames = ASM.build_frames()
    weights = H.load_weights()
    universe = F.load_universe()
    tx = DRV.load_league_transactions(max(vintages) - 1)
    panel = DRV.load_bio_panel()
    log(f"  V2 development frames built ({time.time() - t0:.0f} s)")
    out, receipt = {}, {"weights": weights, "per_vintage": []}
    for side in sides:
        train = H.lv_training_rows(side, frames[side])
        out[side] = {}
        for V in vintages:
            rows = F.build_frame(side, int(V), universe=universe)
            DRV.protection_for_frame(rows, index=tx)
            DRV.bmi_for_rows(rows, panel=panel)
            DRV.pl_revision_for_rows(rows)
            sc = H.v2_lv_scores(side, int(V), rows, train, weights=weights)
            for p in sc["rows"]:
                out[side][(p["player_key"], int(V) - 1)] = float(p["order_idx"])
            m = sc["model"]
            receipt["per_vintage"].append({
                "side": side, "vintage": int(V), "frame_rows": len(rows),
                "n_train": sc["n_train"], "n_scored": sc["n_scored"],
                "train_years": m.get("train_years"), "consensus_only": m.get("consensus_only"),
                "skill_keys": (m.get("skill") or {}).get("keys"),
                "timing_keys": (m.get("timing") or {}).get("keys"),
                "w_skill": m.get("w_skill"), "w_time": m.get("w_time")})
            log(f"  V2 {side} V {V}: {len(rows)} frame rows, {sc['n_scored']} scored, "
                f"{sc['n_train']} training rows ({time.time() - t0:.0f} s)")
    receipt["seconds"] = round(time.time() - t0, 1)
    return out, receipt


# ---------------------------------------------------------------------------
# the model (section 5)
# ---------------------------------------------------------------------------

def moments(rows: list[dict], side: str) -> dict:
    """Training means and sds of the consensus column and every metric (an imputed metric's
    moments come from the rows that carry it)."""
    out = {"fv": _mu_sd([r["fv"] for r in rows])}
    for k in metrics_of(side):
        out[k] = _mu_sd([r["m"][k] for r in rows if r["m"].get(k) is not None])
    return out


def _mu_sd(vals) -> tuple[float, float]:
    v = np.asarray(vals, dtype=np.float64)
    if v.size == 0:
        return 0.0, 1.0
    sd = float(v.std())
    return float(v.mean()), (sd if sd > 1e-12 else 1.0)


def design(rows: list[dict], side: str, mom: dict) -> np.ndarray:
    """[1, AAA, z(fv), z(metrics)] with the given (training) moments; an absent imputed
    metric takes z = 0."""
    cols = [np.ones(len(rows)), np.array([1.0 if r["level"] == "AAA" else 0.0 for r in rows])]
    mu, sd = mom["fv"]
    cols.append((np.array([r["fv"] for r in rows]) - mu) / sd)
    for k in metrics_of(side):
        mu, sd = mom[k]
        cols.append(np.array([0.0 if r["m"].get(k) is None else (r["m"][k] - mu) / sd
                              for r in rows]))
    return np.column_stack(cols)


N_FIXED = 3     # intercept, level, consensus: never penalised


def _penalty(p: int, lam: float) -> np.ndarray:
    pen = np.zeros(p)
    pen[N_FIXED:] = 0.0 if math.isinf(lam) else lam
    return pen


def fit_logistic(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    """Ridge-penalised logistic regression (metric columns only) by Newton steps from a
    zero start; lam = inf drops the metric columns (their weights stay 0)."""
    n, p = X.shape
    use = np.ones(p, dtype=bool)
    if math.isinf(lam):
        use[N_FIXED:] = False
    Xu = X[:, use]
    pen = _penalty(p, lam)[use]
    w = np.zeros(Xu.shape[1])
    for _ in range(NEWTON_ITERS):
        pr = 1.0 / (1.0 + np.exp(-(Xu @ w)))
        g = Xu.T @ (pr - y) + pen * w
        s = pr * (1.0 - pr)
        Hs = (Xu * s[:, None]).T @ Xu + np.diag(pen) + 1e-9 * np.eye(Xu.shape[1])
        try:
            step = np.linalg.solve(Hs, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(Hs, g, rcond=None)[0]
        w = w - step
        if float(np.abs(step).max()) < 1e-9:
            break
    out = np.zeros(p)
    out[use] = w
    return out


def fit_ridge(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    n, p = X.shape
    use = np.ones(p, dtype=bool)
    if math.isinf(lam):
        use[N_FIXED:] = False
    Xu = X[:, use]
    pen = _penalty(p, lam)[use]
    Am = Xu.T @ Xu + np.diag(pen) + 1e-9 * np.eye(Xu.shape[1])
    try:
        w = np.linalg.solve(Am, Xu.T @ y)
    except np.linalg.LinAlgError:
        w = np.linalg.lstsq(Am, Xu.T @ y, rcond=None)[0]
    out = np.zeros(p)
    out[use] = w
    return out


def p_reach(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(X @ w)))


def order_head(w_r: np.ndarray, w_w: np.ndarray, X: np.ndarray) -> np.ndarray:
    """P(reach3) * E[rate3 | reached], unclipped."""
    return p_reach(w_r, X) * (X @ w_w)


def _oof(rows: list[dict], side: str, folds: np.ndarray, lam_r: float, lam_w: float):
    """Out-of-fold P(reach3), E[rate3] and order_head on `rows` (moments refit inside each
    fold on its training part)."""
    n = len(rows)
    P, E = np.full(n, np.nan), np.full(n, np.nan)
    y_r = np.array([r["reach3"] for r in rows])
    y_w = np.array([r["rate3"] for r in rows])
    for f in np.unique(folds):
        te, tr = folds == f, folds != f
        tr_rows = [r for r, t in zip(rows, tr) if t]
        mom = moments(tr_rows, side)
        Xtr, Xte = design(tr_rows, side, mom), design([r for r, t in zip(rows, te) if t], side, mom)
        w_r = fit_logistic(Xtr, y_r[tr], lam_r)
        reached = y_r[tr] > 0
        w_w = fit_ridge(Xtr[reached], y_w[tr][reached], lam_w)
        P[te] = p_reach(w_r, Xte)
        E[te] = Xte @ w_w
    return P, E, P * E


def select_penalties(rows: list[dict], side: str, *, folds: np.ndarray | None = None,
                     log=print) -> dict:
    """lambda_R by out-of-fold AUC of P(reach3); lambda_W by the out-of-fold within-cohort
    Spearman of E[rate3] on the reached rows. Ties go to the larger penalty."""
    pid = np.array([r["pid"] for r in rows])
    folds = A.player_folds(pid, FOLDS, SEED) if folds is None else folds
    y_r = np.array([r["reach3"] for r in rows])
    y_w = np.array([r["rate3"] for r in rows])
    season = np.array([r["season"] for r in rows])
    curve_r, curve_w = [], []
    for lam in LAMBDAS:
        P, E, _ = _oof(rows, side, folds, lam, lam)
        reached = y_r > 0
        curve_r.append({"lambda": _lam(lam), "auc": _r4(A.auc(P, y_r))})
        curve_w.append({"lambda": _lam(lam),
                        "rho": _r4(A.within_rho(E[reached], y_w[reached], season[reached]))})
    lam_r = _argmax_last([c["auc"] for c in curve_r])
    lam_w = _argmax_last([c["rho"] for c in curve_w])
    log(f"  {side}: lambda_R {_lam(lam_r)} (AUC curve {[c['auc'] for c in curve_r]}), "
        f"lambda_W {_lam(lam_w)} (rho curve {[c['rho'] for c in curve_w]})")
    return {"lambda_R": _lam(lam_r), "lambda_W": _lam(lam_w), "curve_R": curve_r,
            "curve_W": curve_w, "folds": FOLDS, "seed": SEED, "rule": "ties to the larger penalty",
            "_lam_r": lam_r, "_lam_w": lam_w}


def _argmax_last(vals: list) -> float:
    best, best_i = None, len(LAMBDAS) - 1
    for i, v in enumerate(vals):
        if v is None:
            continue
        if best is None or v >= best:      # >= : a tie moves to the larger penalty
            best, best_i = v, i
    return LAMBDAS[best_i]


def _lam(x: float):
    return "inf" if math.isinf(x) else x


def _r4(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 4)


def fit_final(rows: list[dict], side: str, lam_r: float, lam_w: float) -> dict:
    mom = moments(rows, side)
    X = design(rows, side, mom)
    y_r = np.array([r["reach3"] for r in rows])
    y_w = np.array([r["rate3"] for r in rows])
    w_r = fit_logistic(X, y_r, lam_r)
    reached = y_r > 0
    w_w = fit_ridge(X[reached], y_w[reached], lam_w)
    return {"moments": {k: [round(v[0], 6), round(v[1], 6)] for k, v in mom.items()},
            "columns": ["intercept", "aaa", "consensus_fv"] + list(metrics_of(side)),
            "w_reach": [round(float(v), 6) for v in w_r], "w_rate": [round(float(v), 6) for v in w_w],
            "n_train": len(rows), "n_reached_train": int(reached.sum()),
            "_w_r": w_r, "_w_w": w_w, "_mom": mom}


def weight_report(rows: list[dict], side: str, fit: dict, lam_r: float, lam_w: float,
                  folds: np.ndarray | None = None) -> list[dict]:
    """Per metric: standardised coefficient in each head, its share of the head's metric
    weight, and sign stability across the training folds (section 5)."""
    mets = list(metrics_of(side))
    pid = np.array([r["pid"] for r in rows])
    folds = A.player_folds(pid, FOLDS, SEED) if folds is None else folds
    signs = {"reach": {k: [] for k in mets}, "rate": {k: [] for k in mets}}
    y_r = np.array([r["reach3"] for r in rows])
    y_w = np.array([r["rate3"] for r in rows])
    for f in np.unique(folds):
        tr = folds != f
        tr_rows = [r for r, t in zip(rows, tr) if t]
        mom = moments(tr_rows, side)
        X = design(tr_rows, side, mom)
        w_r = fit_logistic(X, y_r[tr], lam_r)
        reached = y_r[tr] > 0
        w_w = fit_ridge(X[reached], y_w[tr][reached], lam_w)
        for j, k in enumerate(mets):
            signs["reach"][k].append(float(np.sign(w_r[N_FIXED + j])))
            signs["rate"][k].append(float(np.sign(w_w[N_FIXED + j])))
    out = []
    for head, w in (("reach", fit["_w_r"]), ("rate", fit["_w_w"])):
        wm = np.abs(w[N_FIXED:])
        tot = float(wm.sum())
        for j, k in enumerate(mets):
            coef = float(w[N_FIXED + j])
            share = (wm[j] / tot) if tot > 0 else 0.0
            stable = coef != 0.0 and all(s == np.sign(coef) for s in signs[head][k])
            out.append({"head": head, "metric": k, "name": NAMES.get(k, k),
                        "coef_std": round(coef, 5), "share": round(float(share), 4),
                        "sign_stable": bool(stable),
                        "carries_weight": bool(stable and share >= WEIGHT_SHARE)})
    return out


# ---------------------------------------------------------------------------
# statistics (section 7)
# ---------------------------------------------------------------------------

def readable(rows: list[dict]) -> tuple[bool, str | None]:
    n = len(rows)
    pos = sum(1 for r in rows if r["reach3"] > 0)
    if n < MIN_ROWS:
        return False, f"{n} rows, fewer than {MIN_ROWS}"
    if pos < MIN_POS:
        return False, f"{pos} reach3 positives, fewer than {MIN_POS}"
    if n - pos < MIN_NEG:
        return False, f"{n - pos} reach3 negatives, fewer than {MIN_NEG}"
    return True, None


def compare(rows: list[dict], scores: dict[str, np.ndarray], *, B: int, seed: int,
            bootstrap: bool = True) -> dict:
    """AUC on reach3 and within-cohort Spearman on rate3 for every named score, and the
    paired deltas head minus each comparator with a row-resampled CI95 (E_cond)."""
    y_r = np.array([r["reach3"] for r in rows])
    y_w = np.array([r["rate3"] for r in rows])
    season = np.array([r["season"] for r in rows])
    pid = np.array([r["pid"] for r in rows])
    out = {"n": len(rows), "reach3_pos": int(y_r.sum()),
           "seasons": sorted({int(s) for s in season}),
           "spent": bool(any(r["spent"] for r in rows)), "scores": {}, "deltas": {}}
    W = A.cluster_weights(pid, B, seed) if bootstrap else None
    draws = {}
    for name, s in scores.items():
        auc = A.auc(s, y_r)
        rho = A.within_rho(s, y_w, season)
        out["scores"][name] = {"auc_reach3": _r4(auc), "rho_rate3": _r4(rho)}
        if W is not None:
            draws[name] = (A.auc_weighted(s, y_r, W), A.within_rho(s, y_w, season, W))
    if W is not None and "head" in scores:
        for name in scores:
            if name == "head":
                continue
            d_auc = draws["head"][0] - draws[name][0]
            d_rho = draws["head"][1] - draws[name][1]
            pa, pr = out["scores"]["head"], out["scores"][name]
            out["deltas"][f"head_minus_{name}"] = {
                "auc_reach3": _delta(pa["auc_reach3"], pr["auc_reach3"], d_auc),
                "rho_rate3": _delta(pa["rho_rate3"], pr["rho_rate3"], d_rho)}
    return out


def _delta(a, b, draws: np.ndarray) -> dict:
    iv = A.interval(draws)
    return {"point": None if a is None or b is None else round(a - b, 4),
            "ci95": iv["ci95"], "sd": iv["sd"], "draws": iv["draws"]}


def group_reports(rows: list[dict], scores: dict[str, np.ndarray]) -> list[dict]:
    """Held-out statistics by level, role or position group; reporting only."""
    out = []
    keys = [("level", r["level"]) for r in rows]
    groups = [("group", r["group"]) for r in rows]
    for kind, lab in sorted(set(keys) | set(groups), key=lambda t: (t[0], str(t[1]))):
        if lab is None:
            continue
        m = np.array([(k == (kind, lab)) or (g == (kind, lab)) for k, g in zip(keys, groups)])
        sub = [r for r, t in zip(rows, m) if t]
        pos = sum(1 for r in sub if r["reach3"] > 0)
        if len(sub) < GROUP_MIN_ROWS or pos < GROUP_MIN_POS or len(sub) - pos < GROUP_MIN_POS:
            continue
        rep = compare(sub, {k: v[m] for k, v in scores.items()}, B=0, seed=0, bootstrap=False)
        out.append({"kind": kind, "group": lab, "label": A.GROUP_LABEL.get(lab, lab),
                    "n": rep["n"], "reach3_pos": rep["reach3_pos"], "scores": rep["scores"]})
    return out


# ---------------------------------------------------------------------------
# the ship rule (section 8)
# ---------------------------------------------------------------------------

def ship_verdict(held: dict | None, selection: dict, *, readable_ok: bool, why_unreadable=None) -> dict:
    """Four strict inequalities on the held-out point estimates; unreadable or a head with
    both penalties at infinity does not ship."""
    if not readable_ok:
        return {"ships": False, "reason": f"unreadable: {why_unreadable}"}
    if selection["lambda_R"] == "inf" and selection["lambda_W"] == "inf":
        return {"ships": False, "reason": "both penalties at infinity: the head is consensus plus level"}
    sc = held["scores"]
    checks = {}
    for comp in ("consensus", "v2"):
        for stat in ("auc_reach3", "rho_rate3"):
            a, b = sc["head"].get(stat), sc.get(comp, {}).get(stat)
            checks[f"{stat}_vs_{comp}"] = (a is not None and b is not None and a > b)
    ships = all(checks.values())
    return {"ships": ships, "checks": checks,
            "reason": ("beats consensus and served V2 on both statistics as point estimates"
                       if ships else "fails at least one of the four strict inequalities"),
            "blend_if_ships": {"w_head": BLEND_W, "w_v2": 1.0 - BLEND_W,
                               "rule": "within-(side, list year) percentiles, through efv_v2_model.output_map",
                               "surface_note": SURFACE_NOTE}}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def declared() -> dict:
    return {"n_seasons": N_SEASONS, "horizon": HORIZON, "train_cohorts": list(TRAIN_COHORTS),
            "holdout_cohort": HOLDOUT_COHORT, "consensus_vintages": list(CONSENSUS_VINTAGES),
            "reserved_lv_never_built": sorted(F.RESERVED_LV), "levels": list(LEVEL_ORDER),
            "core_metrics": {s: list(v) for s, v in CORE.items()},
            "imputed_metrics": {s: list(v) for s, v in IMPUTED.items()},
            "qualification": "the fetch's: pitchers 100+ pitches, hitters 50+ PA at the level and season",
            "lambdas": [_lam(x) for x in LAMBDAS], "folds": FOLDS, "seed": SEED,
            "min_rows": MIN_ROWS, "min_pos": MIN_POS, "min_neg": MIN_NEG,
            "group_min_rows": GROUP_MIN_ROWS, "group_min_pos": GROUP_MIN_POS,
            "weight_share": WEIGHT_SHARE, "blend_w": BLEND_W, "rp_gs_share": RP_GS_SHARE,
            "ship_rule": "per side: order_head > consensus AND > served V2 on AUC(reach3) AND Spearman(rate3), held-out point estimates",
            "statistic": "AUC ties at one half; Spearman within cohort (one cohort held out); row-resampled bootstrap, scores fixed (E_cond)"}


def run(*, B: int = B_DEFAULT, seed: int = SEED, log=print, out_path: Path = OUT_PATH,
        sides=F.SIDES) -> dict:
    t0 = time.time()
    doc = {"schema": SCHEMA, "generated_at": _now(), "tool": TOOL, "item": ITEM, "note": NOTE,
           "role": "development", "served": False, "flag": {"EFV_TRACKING_HEAD_ON": EFV_TRACKING_HEAD_ON},
           "spent_note": SPENT_NOTE,
           "registration": {"doc": "docs/efv-v2/EFV_TRACKING_HEAD_GATE.md", "sha256": _sha(GATE_DOC),
                            "git_head_at_run": _git_head(),
                            "early_read": "owner-waived early read (EW3-5): the read runs on the registration's own day"},
           "declared": declared(), "bootstrap_b": B, "surface_note": SURFACE_NOTE}
    mlb = A.mlb_seasons()
    war, vintage_id = A.fwar_totals()
    listings = A.load_listings()
    universe = F.load_universe()
    roles = pitcher_roles()
    doc["inputs"] = {"fwar_vintage_id": vintage_id, "mlb_players": len(mlb),
                     "tracking_tables": {s: _sha(A.TRACK_DIR / f"{'pitcher' if s == 'pit' else 'hitter'}_season_level.csv.gz")
                                         for s in sides}}
    frames = {}
    for side in sides:
        cons = A.consensus_reads(side, listings, vintages=CONSENSUS_VINTAGES, universe=universe, log=log)
        rows = build_rows(side, mlb=mlb, war=war, cons=cons, roles=roles)
        frames[side] = rows
        log(f"  {side}: {len(rows)} rows ({sum(1 for r in rows if r['role'] == 'train')} train, "
            f"{sum(1 for r in rows if r['role'] == 'holdout')} held out)")
    doc["frame"] = {s: frame_counts(frames[s]) for s in sides}
    # 1. selection on the training cohorts only; written before any held-out row is scored
    sel, fits = {}, {}
    for side in sides:
        tr = [r for r in frames[side] if r["role"] == "train"]
        sel[side] = select_penalties(tr, side, log=log)
        fits[side] = fit_final(tr, side, sel[side]["_lam_r"], sel[side]["_lam_w"])
    doc["selection"] = {s: {k: v for k, v in sel[s].items() if not k.startswith("_")} for s in sides}
    doc["fit"] = {s: {k: v for k, v in fits[s].items() if not k.startswith("_")} for s in sides}
    doc["weights"] = {s: weight_report([r for r in frames[s] if r["role"] == "train"], s, fits[s],
                                       sel[s]["_lam_r"], sel[s]["_lam_w"]) for s in sides}
    doc["status"] = "selection written; held-out cohort not yet scored"
    _write(doc, out_path)
    log(f"  selection written to {out_path} ({time.time() - t0:.0f} s)")
    # 2. the comparators on the same rows
    v2, receipt = v2_order_scores(sides, log=log)
    doc["v2"] = receipt
    # 3. development (out of fold on the training rows) and the ONE held-out read
    doc["development"], doc["holdout"], doc["groups"], doc["verdict"] = {}, {}, {}, {}
    for side in sides:
        rows = frames[side]
        tr = [r for r in rows if r["role"] == "train"]
        ho = [r for r in rows if r["role"] == "holdout"]
        joined = {"train": 0, "holdout": 0, "train_missing_v2": 0, "holdout_missing_v2": 0}
        for name, rs in (("train", tr), ("holdout", ho)):
            for r in rs:
                v = v2[side].get((r["player_key"], r["season"]))
                r["v2"] = v
                joined[name] += 1
                joined[f"{name}_missing_v2"] += int(v is None)
        doc["v2"].setdefault("join", {})[side] = joined
        tr_j = [r for r in tr if r["v2"] is not None]
        folds = A.player_folds(np.array([r["pid"] for r in tr_j]), FOLDS, seed)
        _, _, oof = _oof(tr_j, side, folds, sel[side]["_lam_r"], sel[side]["_lam_w"])
        dev_scores = {"head": oof, "consensus": np.array([r["fv"] for r in tr_j]),
                      "v2": np.array([r["v2"] for r in tr_j])}
        doc["development"][side] = compare(tr_j, dev_scores, B=B, seed=seed)
        doc["development"][side]["note"] = "out of fold on the training cohorts at the selected penalties; the selection frame; adjudicates nothing"
        ho_j = [r for r in ho if r["v2"] is not None]
        ok, why = readable(ho_j)
        if ho_j:
            X = design(ho_j, side, fits[side]["_mom"])
            ho_scores = {"head": order_head(fits[side]["_w_r"], fits[side]["_w_w"], X),
                         "consensus": np.array([r["fv"] for r in ho_j]),
                         "v2": np.array([r["v2"] for r in ho_j])}
            held = compare(ho_j, ho_scores, B=B, seed=seed + 1)
            held["components"] = {"p_reach_auc": _r4(A.auc(p_reach(fits[side]["_w_r"], X), np.array([r["reach3"] for r in ho_j]))),
                                  "e_rate_rho": _r4(A.within_rho(X @ fits[side]["_w_w"], np.array([r["rate3"] for r in ho_j]), np.array([r["season"] for r in ho_j])))}
            held["readable"] = ok
            held["unreadable_reason"] = why
            held["note"] = "the one registered held-out read (cohort 2023), labelled spent for its R-VM overlap"
            doc["holdout"][side] = held
            doc["groups"][side] = group_reports(ho_j, ho_scores)
        else:
            held = None
            doc["holdout"][side] = {"n": 0, "readable": False, "unreadable_reason": why}
            doc["groups"][side] = []
        doc["verdict"][side] = ship_verdict(held, doc["selection"][side], readable_ok=ok, why_unreadable=why)
        log(f"  {side}: held out {len(ho_j)} rows; verdict {doc['verdict'][side]['ships']} "
            f"({doc['verdict'][side]['reason']})")
    doc["ships_any_side"] = any(doc["verdict"][s]["ships"] for s in sides)
    doc["status"] = "complete"
    doc["seconds"] = round(time.time() - t0, 1)
    _write(doc, out_path)
    log(f"wrote {out_path} in {doc['seconds']} s")
    return doc


def _write(doc: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# the served path (section 8), DARK while EFV_TRACKING_HEAD_ON is False
# ---------------------------------------------------------------------------
# efv_v2_serve.score_live calls apply_to_live after V2's prediction. Off, it returns 0
# and touches nothing, so the served artifact stays byte for byte V2's. On, for every
# side whose artifact verdict ships, the tracked prospects of the live group (a tracked
# line in the latest finished MiLB season with every core metric present, at the
# fetch's qualification) are re-ordered among themselves by the registered blend of
# within-group percentiles, the tracked subset keeping its own multiset of V2 order
# indices (consensus sets the level, the head only reorders), and the group's grades are
# re-drawn through V2's output map. Untracked prospects keep V2's order as served.

CHIP_DRIVER = "tracking_head"
CHIP_LABEL = "Tracking-era head, short-horizon label"


def shipped_sides(artifact: dict | None = None) -> dict[str, dict]:
    """{side: fit} for every side whose completed artifact verdict ships; {} without an
    artifact. Read by the served path only when the switch is on."""
    if artifact is None:
        try:
            artifact = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    if artifact.get("status") != "complete":
        return {}
    out = {}
    for side, v in (artifact.get("verdict") or {}).items():
        if v.get("ships"):
            out[side] = artifact["fit"][side]
    return out


def tracked_season() -> int:
    """The latest finished MiLB season (efv_dataset.RESOLVED_THROUGH)."""
    import efv_dataset as D
    return int(D.RESOLVED_THROUGH)


def live_tracking(side: str, season: int, trk: dict | None = None) -> dict:
    """{mlbam: (level, metric values)} for the season, the higher level winning."""
    trk = A.tracking_metrics(side) if trk is None else trk
    return {pid: v for (pid, s), v in pick_rows(trk, side, cohorts=(int(season),)).items()}


def head_order_from_fit(fit: dict, rows: list[dict]) -> np.ndarray:
    """order_head for rows [{"level", "fv", "m"}] from an artifact fit (lists)."""
    side = "pit" if "astuff_plus" in fit["columns"] else "hit"
    mom = {k: (float(v[0]), float(v[1])) for k, v in fit["moments"].items()}
    X = design(rows, side, mom)
    return order_head(np.asarray(fit["w_reach"], dtype=np.float64),
                      np.asarray(fit["w_rate"], dtype=np.float64), X)


def _pct(x: np.ndarray) -> np.ndarray:
    return (A._ranks(np.asarray(x, dtype=np.float64)) - 0.5) / x.size


def blend_orders(order_idx, order_head_values, w: float = BLEND_W) -> np.ndarray:
    """The tracked subset re-ordered by u = w * u(head) + (1 - w) * u(V2), the row at
    rank k of u taking the k-th smallest of the subset's OWN V2 order indices, so the
    subset's index multiset, and therefore every untracked row's place, is kept exactly.
    A tie on u (two rank sums are often equal) is broken by V2's own order, then by the
    head's, so no value is averaged away."""
    o = np.asarray(order_idx, dtype=np.float64)
    if o.size == 0:
        return o
    h = np.asarray(order_head_values, dtype=np.float64)
    u = w * _pct(h) + (1.0 - w) * _pct(o)
    order = np.lexsort((h, o, u))              # u first, then V2's order, then the head
    out = np.empty(o.size)
    out[order] = np.sort(o)
    return out


def apply_to_live(side: str, rows: list[dict], preds: list[dict], model: dict, *,
                  fits: dict | None = None, tracking: dict | None = None) -> int:
    """Blend the shipped head into V2's live predictions in place (section 8). Returns
    the number of rows re-ordered; 0 and no change while the switch is off, for a side
    that does not ship, or with no tracked row."""
    if not EFV_TRACKING_HEAD_ON:
        return 0
    fits = shipped_sides() if fits is None else fits
    fit = fits.get(side)
    if fit is None or not rows:
        return 0
    season = tracked_season()
    tracking = live_tracking(side, season) if tracking is None else tracking
    idx, head_rows = [], []
    for i, r in enumerate(rows):
        pid = r.get("mlbam_id")
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        t = tracking.get(pid)
        if t is None:
            continue
        idx.append(i)
        head_rows.append({"level": t[0], "fv": float(r["fv"]), "m": t[1]})
    if not idx:
        return 0
    import efv_v2_model as H
    oh = head_order_from_fit(fit, head_rows)
    old = np.array([preds[i]["order_idx"] for i in idx], dtype=np.float64)
    new = blend_orders(old, oh)
    for j, i in enumerate(idx):
        preds[i]["order_idx"] = float(new[j])
        preds[i]["tracking_head"] = {
            "order_head": round(float(oh[j]), 6), "order_idx_v2": round(float(old[j]), 9),
            "shift_pct": round(float(new[j] - old[j]) * 100.0, 4),
            "season": int(season), "level": head_rows[j]["level"],
            "blend_w": BLEND_W, "label": "short-horizon label (reach3, rate3)",
            "note": SURFACE_NOTE}
    groups = [int(r["decision_year"]) for r in rows]
    fv = np.array([r["fv"] for r in rows], dtype=np.float64)
    order = np.array([p["order_idx"] for p in preds], dtype=np.float64)
    grade = H.output_map(order, groups, fv)
    war = H.war_at(model.get("war_map"), grade)
    for i, p in enumerate(preds):
        p["efv_grade"] = float(grade[i])
        p["efv_war"] = float(war[i])
    return len(idx)


def head_chip(p: dict, floor: float) -> list[dict]:
    """The one chip a blended row carries, in the board's own units; none below floor."""
    th = p.get("tracking_head")
    if not th or abs(th["shift_pct"]) < floor:
        return []
    return [{"label": CHIP_LABEL, "driver": CHIP_DRIVER,
             "dir": "up" if th["shift_pct"] > 0 else "down",
             "mag": round(abs(th["shift_pct"]), 2), "unit": "percentile points"}]


def serve_receipt() -> dict:
    """What the served export records when the switch is on."""
    ships = {s: True for s in shipped_sides()}
    return {"on": EFV_TRACKING_HEAD_ON, "ships": ships, "blend_w": BLEND_W,
            "artifact": "data/efv5_tracking_head.json",
            "registration": "docs/efv-v2/EFV_TRACKING_HEAD_GATE.md", "note": SURFACE_NOTE}


# ---------------------------------------------------------------------------
# the results document
# ---------------------------------------------------------------------------

def _f(v, nd=4):
    if v is None:
        return "n/a"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_f(x, nd) for x in v) + "]"
    if isinstance(v, float):
        return f"{v:+.{nd}f}" if nd == 4 else f"{v:.{nd}f}"
    return str(v)


def _dl(d: dict) -> str:
    """A paired delta cell: point and CI95, or blank on the head's own row."""
    if not d or d.get("point") is None:
        return ""
    return f"{_f(d['point'])} {_f(d.get('ci95'))}"


def results_md(doc: dict) -> str:
    L = []
    L.append("# eFV tracking-era head: results in plain language")
    L.append("")
    L.append(f"Generated {doc['generated_at']} by `{doc['tool']}` from `data/efv5_tracking_head.json` "
             f"({doc['seconds']} s, bootstrap B {doc['bootstrap_b']}). Registration: "
             f"`{doc['registration']['doc']}` (sha256 {doc['registration']['sha256'][:12]}), read the same day as an "
             f"owner-waived early read (EW3-5). {doc['note']}. {doc['spent_note']}.")
    L.append("")
    L.append("## 1. What was asked")
    L.append("")
    L.append("For prospects with minor-league pitch tracking (2021 and later; the Florida State League and, from "
             "2022, Triple-A), does a head that adds the tracking metrics to PROSPX consensus FV order a held-out "
             "cohort better than consensus alone AND better than the served eFV v2, on a short label the tracking "
             f"era can already resolve: reached MLB within {doc['declared']['n_seasons']} seasons (reach3) and fWAR per "
             "MLB season over those seasons (rate3)? The head enters eFV only on a lead over both (EW3-1).")
    L.append("")
    L.append("## 2. The verdict")
    L.append("")
    for side in ("hit", "pit"):
        v = doc["verdict"].get(side) or {}
        L.append(f"- {'hitters' if side == 'hit' else 'pitchers'}: **{'SHIPS' if v.get('ships') else 'DOES NOT SHIP'}** ({v.get('reason')}).")
    L.append("")
    L.append("## 3. The held-out cohort (2023), read once")
    L.append("")
    L.append("| side | rows (reached) | score | AUC reach3 | Spearman rate3 | head minus it: AUC (CI95) | head minus it: rho (CI95) |")
    L.append("|---|---|---|---|---|---|---|")
    for side in ("hit", "pit"):
        h = doc["holdout"].get(side) or {}
        if not h.get("scores"):
            L.append(f"| {side} | {h.get('n', 0)} | unreadable | | | {h.get('unreadable_reason')} | |")
            continue
        for name in ("head", "consensus", "v2"):
            s = h["scores"][name]
            d = h["deltas"].get(f"head_minus_{name}") or {}
            da, dr = d.get("auc_reach3") or {}, d.get("rho_rate3") or {}
            L.append(f"| {side} | {h['n']} ({h['reach3_pos']}) | {name} | {_f(s['auc_reach3'])} | {_f(s['rho_rate3'])} | "
                     f"{_dl(da)} | {_dl(dr)} |")
    L.append("")
    L.append("Every held-out number is labelled spent: the 2023 cohort's window reaches the 2025 and 2026 debut cohorts.")
    L.append("")
    L.append("## 4. The training cohorts (2021, 2022), out of fold: the selection frame")
    L.append("")
    L.append("| side | rows (reached) | score | AUC reach3 | Spearman rate3 | head minus it: AUC (CI95) | head minus it: rho (CI95) |")
    L.append("|---|---|---|---|---|---|---|")
    for side in ("hit", "pit"):
        h = doc["development"].get(side) or {}
        if not h.get("scores"):
            continue
        for name in ("head", "consensus", "v2"):
            s = h["scores"][name]
            d = h["deltas"].get(f"head_minus_{name}") or {}
            da, dr = d.get("auc_reach3") or {}, d.get("rho_rate3") or {}
            L.append(f"| {side} | {h['n']} ({h['reach3_pos']}) | {name} | {_f(s['auc_reach3'])} | {_f(s['rho_rate3'])} | "
                     f"{_dl(da)} | {_dl(dr)} |")
    L.append("")
    L.append("## 5. Which tracking metrics carry the weight")
    L.append("")
    L.append("Standardised coefficients of the fitted heads at the selected penalties (a metric 'carries weight' "
             f"when its sign holds in every training fold and it holds at least {int(100 * doc['declared']['weight_share'])} percent "
             "of its head's metric weight). This describes the fit; it admits nothing by itself.")
    L.append("")
    for side in ("hit", "pit"):
        sel = doc["selection"][side]
        L.append(f"### {'Hitters' if side == 'hit' else 'Pitchers'} (lambda reach {sel['lambda_R']}, lambda rate {sel['lambda_W']})")
        L.append("")
        L.append("| head | metric | coefficient (z) | share of metric weight | sign stable | carries weight |")
        L.append("|---|---|---|---|---|---|")
        for w in doc["weights"][side]:
            L.append(f"| {w['head']} | {w['name']} | {_f(w['coef_std'])} | {_f(w['share'], 2)} | "
                     f"{'yes' if w['sign_stable'] else 'no'} | {'yes' if w['carries_weight'] else 'no'} |")
        L.append("")
    L.append("## 6. By group on the held-out cohort (reporting only)")
    L.append("")
    L.append("| side | group | n (reached) | head AUC / rho | consensus AUC / rho | V2 AUC / rho |")
    L.append("|---|---|---|---|---|---|")
    for side in ("hit", "pit"):
        for g in doc["groups"].get(side) or []:
            s = g["scores"]
            L.append(f"| {side} | {g['label']} | {g['n']} ({g['reach3_pos']}) | "
                     f"{_f(s['head']['auc_reach3'])} / {_f(s['head']['rho_rate3'])} | "
                     f"{_f(s['consensus']['auc_reach3'])} / {_f(s['consensus']['rho_rate3'])} | "
                     f"{_f(s['v2']['auc_reach3'])} / {_f(s['v2']['rho_rate3'])} |")
    L.append("")
    L.append("## 7. The frame")
    L.append("")
    L.append("| side | cohort | level | role | rows | reached within 3 | spent |")
    L.append("|---|---|---|---|---|---|---|")
    for side in ("hit", "pit"):
        for c in doc["frame"][side]:
            L.append(f"| {side} | {c['season']} | {c['level']} | {c['role']} | {c['rows']} | {c['reach3_pos']} | {'yes' if c['spent'] else 'no'} |")
    L.append("")
    j = doc["v2"].get("join") or {}
    L.append(f"Served V2 joined on {_f(j)} (rows missing a V2 score are left out of every comparison). "
             f"fWAR vintage {doc['inputs']['fwar_vintage_id']}.")
    L.append("")
    L.append("## 8. What happens next")
    L.append("")
    if doc.get("ships_any_side"):
        L.append("A side that ships enters eFV for its tracked prospects at the registered blend "
                 f"(w_head {doc['declared']['blend_w']}), with the note '{doc['surface_note']}' on every surface "
                 "that shows the grade; the flip and the rebuild are listed under the task's INTEGRATION NOTES.")
    else:
        L.append("Nothing served moves: the head stays dark (EFV_TRACKING_HEAD_ON = False). The next read is the "
                 "registration's upgrade path: cohort 2024 joins as the held-out cohort after the 2027 season, and "
                 "the six-season label replaces the short one as the 2021 cohort's debuts mature.")
    L.append("")
    return "\r\n".join(L) + "\r\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--b", type=int, default=B_DEFAULT)
    ap.add_argument("--md", action="store_true", help="write the results document from the artifact")
    a = ap.parse_args(argv)
    if a.run:
        run(B=a.b)
    if a.md:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        RESULTS_DOC.write_bytes(results_md(doc).encode("utf-8"))
        print(f"wrote {RESULTS_DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

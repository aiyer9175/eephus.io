# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV PROXY -- a faster-resolving LEADING INDICATOR, NOT eFV and NOT a WAR backtest.

eFV predicts first-6-MLB-season WAR (resolves in ~6 years). This proxy predicts a prospect's
FIRST-MLB-season Statcast quality -- hitters: expected wOBA (est_woba); pitchers: expected
wOBA-AGAINST -- from the SAME pre-debut profile, forward-validated on the 2024-2026 debut
cohorts. It resolves in ~1 season, so it is an earlier signal of "is the contact/stuff
major-league quality" and the empirical companion to the live Statcast tilt.

Leakage-safe by construction: features are the as-of-debut profile (consensus FV + tools +
translated MiLB rates, all dated before the debut), and the TARGET is the player's own
first-MLB-season Savant line (after debut) -- so this never feeds eFV or its training matrix.
Survivorship caveat: the cohort is DEBUTS ONLY, so it answers "among players good enough to
debut, whose MLB contact/stuff is strong," a different (and easier) question than eFV's
bust-inclusive WAR target. Provisional; publish-the-r.

Writes data/xfv_proxy_eval.json (forward-chained r/rho + coefficients + per-active projections).
Run: python xfv_proxy.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from xfv_dataset import (_asof_point, _prior_features, _milb_features, _side_match,
                         _f, live_matrix_path)
from xfv_model import _vec, _feature_spec

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
COHORT_YEARS = (2024, 2025, 2026)
MIN_PA = 50          # Savant expected-stats min sample to count as a resolved target
_TARGET = {"hit": "first-MLB xwOBA (est_woba)", "pit": "first-MLB xwOBA-against (est_woba)"}


def _spearman(a, b):
    if len(a) < 3:
        return None
    ar = np.argsort(np.argsort(a)); br = np.argsort(np.argsort(b))
    return float(np.corrcoef(ar, br)[0, 1])


def _pull_targets(year: int, side: str) -> dict:
    """{mlbam(str): first-MLB est_woba} for `year`, gated at MIN_PA. Hitters use the batter
    leaderboard, pitchers the pitcher leaderboard (est_woba there is wOBA-against)."""
    from mlb_player_export import _savant
    rows = _savant("expected", year, "pitcher" if side == "pit" else "batter")
    out = {}
    for r in rows:
        pid = r.get("player_id")
        woba = _f(r.get("est_woba"))
        pa = _f(r.get("pa"))
        if pid and woba is not None and (pa is None or pa >= MIN_PA):
            out[str(pid)] = woba
    return out


def _build_pairs(side: str) -> list[dict]:
    """(pre-debut features -> first-MLB est_woba) pairs for the debut cohorts."""
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    if isinstance(debuts, dict):
        debuts = debuts.get("players") or []
    targets = {y: _pull_targets(y, side) for y in COHORT_YEARS}
    keys, _m = _feature_spec(side)
    pairs = []
    for rec in debuts:
        if not _side_match(rec, side):
            continue
        dd = rec.get("debut_date") or ""
        y = int(dd[:4]) if dd[:4].isdigit() else None
        mlbam = rec.get("mlbam_id")
        if y not in COHORT_YEARS or not mlbam:
            continue
        tgt = targets.get(y, {}).get(str(mlbam))
        if tgt is None:                                  # no qualifying MLB target -> drop (unobserved)
            continue
        pt = _asof_point(rec, dd)                        # last snapshot strictly before debut
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            continue
        row = {"consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
               "position": rec.get("position"), "birth_date": rec.get("birth_date")}
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(mlbam, y, rec.get("birth_date"), side)
        pairs.append({"key": rec.get("player_key"), "year": y,
                      "x": [float(_vec(row, side)[k]) for k in keys], "y": float(tgt)})
    return pairs


def _eval_forward(pairs: list[dict], keys: list[str]) -> dict:
    """Forward-chained: train on cohorts < test year, predict the test year; pool OOS preds."""
    yhat, ytrue = [], []
    for test_y in (2025, 2026):
        tr = [p for p in pairs if p["year"] < test_y]
        te = [p for p in pairs if p["year"] == test_y]
        if len(tr) < 25 or len(te) < 10:
            continue
        Xtr = np.array([p["x"] for p in tr]); ytr = np.array([p["y"] for p in tr])
        sc = StandardScaler().fit(Xtr)
        rg = Ridge(alpha=3.0).fit(sc.transform(Xtr), ytr)
        pred = rg.predict(sc.transform(np.array([p["x"] for p in te])))
        yhat.extend(pred.tolist()); ytrue.extend(p["y"] for p in te)
    if len(ytrue) < 10:
        return {"n": len(ytrue), "r": None, "spearman": None}
    r = float(np.corrcoef(yhat, ytrue)[0, 1])
    return {"n": len(ytrue), "r": round(r, 4), "spearman": round(_spearman(yhat, ytrue) or 0.0, 4)}


def _project_active(pairs: list[dict], keys: list[str], side: str) -> dict:
    """Fit on ALL cohort pairs, project current active prospects' first-MLB est_woba."""
    if len(pairs) < 30:
        return {}
    Xtr = np.array([p["x"] for p in pairs]); ytr = np.array([p["y"] for p in pairs])
    sc = StandardScaler().fit(Xtr)
    rg = Ridge(alpha=3.0).fit(sc.transform(Xtr), ytr)
    try:
        live = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for r in live:
        if r.get("consensus_fv_raw") is None:
            continue
        try:
            x = np.array([[float(_vec(r, side)[k]) for k in keys]])
        except Exception:
            continue
        out[r["player_key"]] = round(float(rg.predict(sc.transform(x))[0]), 3)
    return out


def run(persist: bool = True) -> dict:
    report = {"model": "eFV proxy (pre-debut -> first-MLB Statcast quality)",
              "kind": "leading_indicator_not_xfv", "cohort_years": list(COHORT_YEARS),
              "min_pa": MIN_PA, "sides": {}}
    projections = {}
    for side in ("hit", "pit"):
        keys, _m = _feature_spec(side)
        pairs = _build_pairs(side)
        ev = _eval_forward(pairs, keys)
        ev["target"] = _TARGET[side]
        ev["pairs"] = len(pairs)
        ev["per_cohort"] = {y: sum(1 for p in pairs if p["year"] == y) for y in COHORT_YEARS}
        report["sides"][side] = ev
        for k, v in _project_active(pairs, keys, side).items():
            projections[k] = {"proj_xwoba": v, "side": side}
        log.info("proxy %s: %d pairs | OOS r=%s rho=%s (n=%s)",
                 side, len(pairs), ev.get("r"), ev.get("spearman"), ev.get("n"))
    report["projections"] = projections
    report["note"] = ("Forward-chained on debut cohorts; survivorship-limited (debuts only) and "
                      "small-n -- provisional leading indicator, NOT the eFV WAR backtest.")
    if persist:
        (DATA_DIR / "xfv_proxy_eval.json").write_text(json.dumps(report, separators=(",", ":")),
                                                      encoding="utf-8")
        log.info("wrote %s", DATA_DIR / "xfv_proxy_eval.json")
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    for side, ev in rep["sides"].items():
        print(f"{side}: {ev['pairs']} pairs | OOS r={ev.get('r')} rho={ev.get('spearman')} "
              f"n={ev.get('n')} | target={ev['target']}")
    print("active projections:", len(rep["projections"]))

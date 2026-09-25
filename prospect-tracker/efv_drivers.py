# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v2 drivers D1 and D3 (docs/efv-v2/PROGRAM.md s3.2, items EV-07 and EV-08).

D1, THE CONSENSUS-REVISION FRONT-RUNNER (EV-07). consensus_revision_hat(side, V) predicts
how far the PROSPX consensus will move between the V and V+1 preseason reads,

    target  dc = c(V+1) - c(V)      c(V) = the consensus on the player's F-LV row at V
                                    (efv_vintage_frame.build_frame, the board as it stood
                                    at the latest in-window point)

from what was public at the V read: c(V), age, and the as-of MiLB production the frame
row already carries (efv_dataset._milb_features with cutoff V-01-01, so the last season
read is V - 1). It lives in GRADE SPACE ONLY. The module reads no WAR column and imports
no label module (test_efv_drivers.py enforces both); the only outcome it ever sees is the
next consensus read.

    forward-chained   the fit for V uses training vintages t < V whose target c(t+1) is
                      itself a read taken no later than V (t + 1 <= V). Nothing dated
                      after the V window enters the prediction for V.
    rows              a (player, t) pair trains when the player has a consensus and a
                      complete MiLB vector at t and is still in the frame at t + 1 (listed
                      by a real grader, not yet debuted). A player who debuted or dropped
                      off every list before the t + 1 read has no revision to learn from.
    estimator         ridge on standardized columns, intercept unpenalized, alpha
                      RIDGE_ALPHA; the design probe's specification (scratchpad E2
                      probe_consensus_lag.py), not a tuned constant.
    base / full       base = [c(V), age]; full = base + the side's MiLB production
                      columns. The front-runner is the full model; base is its control.

D3, ORG-PRIVATE SIGNALS (EV-08). forty_man_asof and contract_selections_asof read the
per-player MLB transaction history (storage table player_transactions) strictly before a
cutoff date: a transaction announced on the cutoff day or later is not known at the read.
The frame helper org_signals_for_frame uses each row's window start (V-01-01), the same
cutoff as its MiLB and IL inputs, so a November 40-man add in V - 1 counts at V.

    on the 40-man     the latest status-bearing transaction before the cutoff decides:
                      a contract selection (SE), a Rule 5 selection (R5) or a waiver
                      claim (CLW) adds; an option (OPT) or a recall (CU) implies it; an
                      outright (OUT), release (REL), designation (DES), elected free
                      agency (DFA), retirement (RET), Rule 5 return (RTN) or a minor-league
                      phase Rule 5 pick (R5M) removes. Signings (SFA, SGN) are left out:
                      the payload does not say whether the deal was a 40-man contract.
    unobserved        None, not False, when the player has no transaction on record
                      before the cutoff: the stored history starts at each player's fetch
                      window (stats.TRANSACTIONS_LOOKBACK_SEASONS, widened by
                      tools/backfill_player_transactions.py), so an empty past is not
                      evidence of no 40-man add.

RESERVED FRAMES. Every entry point calls efv_vintage_frame.guard_score_request for each
list vintage it reads, INCLUDING the V + 1 target vintage, so a development evaluation
stops at V = 2018 (its target is the 2019 read) and nothing here opens 2020 or 2021
without the committed gate sha. dev_oos_r2 refuses any vintage outside DEV_VINTAGES.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md). Nothing here groups, counts or averages
rows by consensus-FV level; the consensus enters only as a continuous regressor.
"""
from __future__ import annotations

import math

import numpy as np

import efv_vintage_frame as F
import source_backtest as SB

#: The design probe's MiLB production columns per side (E2 probe_consensus_lag.py).
HIT_FEATURES: tuple[str, ...] = ("obp_rel", "k_rel", "iso_rel", "ops_rel", "bb_rel",
                                 "age_rel_level", "level_rank", "peak_ops_rel",
                                 "prod_trend", "n_milb_seasons")
PIT_FEATURES: tuple[str, ...] = ("k_rel", "bb_rel", "era_rel", "age_rel_level",
                                 "level_rank", "peak_k_rel", "prod_trend",
                                 "n_milb_seasons")
BASE_COLUMNS: tuple[str, ...] = ("c_v", "age")
RIDGE_ALPHA = 1.0
#: A fit needs this many training pairs; an evaluation vintage needs MIN_TEST_ROWS.
MIN_TRAIN_ROWS = 100
MIN_TEST_ROWS = 20

_ADD = frozenset({"SE", "R5", "CLW"})
_IMPLIED = frozenset({"OPT", "CU"})
_REMOVE = frozenset({"OUT", "REL", "DES", "DFA", "RET", "RTN", "R5M"})
_NOVEMBER = "11"


def feature_columns(side: str) -> tuple[str, ...]:
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    return HIT_FEATURES if side == "hit" else PIT_FEATURES


# ---------------------------------------------------------------------------
# D1: frames, vectors, targets
# ---------------------------------------------------------------------------

_FRAMES: dict[tuple, tuple[object, dict[str, dict]]] = {}


def _frame(side: str, V: int, gate_sha: str | None, universe: dict | None
           ) -> dict[str, dict]:
    """{player_key: F-LV row} for (side, V). The guard runs on every call, memo or not."""
    F.guard_score_request(V, gate_sha=gate_sha, purpose="revision")
    u = universe if universe is not None else F.load_universe()
    key = (side, int(V), id(u))
    hit = _FRAMES.get(key)
    if hit is not None and hit[0] is u:
        return hit[1]
    rows = F.build_frame(side, V, gate_sha=gate_sha, universe=u, sidecars=False)
    out = {r["player_key"]: r for r in rows if r.get("player_key")}
    _FRAMES[key] = (u, out)
    return out


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def row_vector(row: dict, side: str) -> list[float] | None:
    """[c(V), age, *production] for one frame row, or None when any input is missing."""
    c = (row.get("grades") or {}).get(SB.CONSENSUS_KEY)
    m = row.get("milb") or {}
    if not _finite(c) or not m or m.get("rates_missing"):
        return None
    x = [c, m.get("age")] + [m.get(k) for k in feature_columns(side)]
    if not all(_finite(v) for v in x):
        return None
    return [float(v) for v in x]


def revision_targets(side: str, V: int, *, gate_sha: str | None = None,
                     universe: dict | None = None) -> dict[str, float]:
    """{player_key: c(V+1) - c(V)} for players with a consensus in both frames. Reads the
    V + 1 frame, so both vintages pass the reserved guard."""
    now = _frame(side, V, gate_sha, universe)
    nxt = _frame(side, int(V) + 1, gate_sha, universe)
    out = {}
    for pk, r in now.items():
        r1 = nxt.get(pk)
        if r1 is None:
            continue
        c0 = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
        c1 = (r1.get("grades") or {}).get(SB.CONSENSUS_KEY)
        if _finite(c0) and _finite(c1):
            out[pk] = float(c1) - float(c0)
    return out


def _ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    """Ridge on standardized columns with an unpenalized intercept (train statistics)."""
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    pen = alpha * np.eye(Z.shape[1])
    pen[0, 0] = 0.0
    b = np.linalg.solve(Z.T @ Z + pen, Z.T @ y)
    return {"mu": mu, "sd": sd, "b": b}


def _predict(fit: dict, X: np.ndarray) -> np.ndarray:
    Z = np.column_stack([np.ones(len(X)), (X - fit["mu"]) / fit["sd"]])
    return Z @ fit["b"]


def consensus_revision_hat(side: str, V: int, *, gate_sha: str | None = None,
                           universe: dict | None = None,
                           first_train_vintage: int = min(F.DEV_VINTAGES)) -> dict:
    """Forward-chained prediction of c(V+1) - c(V) for every F-LV row at (side, V).

    Trains on (player, t) pairs with first_train_vintage <= t < V, target c(t+1) - c(t),
    all t + 1 <= V. Returns the fitted coefficients (standardized scale), the training
    vintages and sizes, and per-player predictions: `hat` (full model) and `hat_base`
    (c and age only). Rows without a complete vector get no prediction. With fewer than
    MIN_TRAIN_ROWS pairs, status is "insufficient_training" and no row is predicted."""
    V = int(V)
    feature_columns(side)
    F.guard_score_request(V, gate_sha=gate_sha, purpose="revision")
    Xs, ys, used = [], [], []
    for t in range(int(first_train_vintage), V):
        tgt = revision_targets(side, t, gate_sha=gate_sha, universe=universe)
        rows = _frame(side, t, gate_sha, universe)
        n0 = len(ys)
        for pk in sorted(tgt):
            x = row_vector(rows[pk], side)
            if x is None:
                continue
            Xs.append(x)
            ys.append(tgt[pk])
        if len(ys) > n0:
            used.append(t)
    now = _frame(side, V, gate_sha, universe)
    cols = list(BASE_COLUMNS) + list(feature_columns(side))
    out = {"side": side, "vintage": V, "train_vintages": used, "n_train": len(ys),
           "alpha": RIDGE_ALPHA, "columns": cols, "n_rows": len(now),
           "hat": {}, "hat_base": {}, "coef": None, "coef_base": None}
    if len(ys) < MIN_TRAIN_ROWS:
        out["status"] = "insufficient_training"
        return out
    X = np.asarray(Xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    nb = len(BASE_COLUMNS)
    full = _ridge(X, y, RIDGE_ALPHA)
    base = _ridge(X[:, :nb], y, RIDGE_ALPHA)
    keys, Xn = [], []
    for pk in sorted(now):
        x = row_vector(now[pk], side)
        if x is not None:
            keys.append(pk)
            Xn.append(x)
    if Xn:
        Xn_arr = np.asarray(Xn, dtype=float)
        pf = _predict(full, Xn_arr)
        pb = _predict(base, Xn_arr[:, :nb])
        out["hat"] = {k: float(v) for k, v in zip(keys, pf)}
        out["hat_base"] = {k: float(v) for k, v in zip(keys, pb)}
    out["coef"] = dict(zip(["intercept"] + cols, (float(v) for v in full["b"])))
    out["coef_base"] = dict(zip(["intercept"] + list(BASE_COLUMNS),
                                (float(v) for v in base["b"])))
    out["status"] = "ok"
    return out


def dev_oos_r2(side: str, vintages=F.DEV_VINTAGES, *, universe: dict | None = None
               ) -> dict:
    """Forward-chained out-of-sample R2 of the front-runner on DEVELOPMENT vintages only.

    Each test vintage t needs t and t + 1 inside DEV_VINTAGES (so the last test vintage
    is 2018, whose target is the 2019 read), at least MIN_TRAIN_ROWS training pairs and
    MIN_TEST_ROWS scored rows. R2 is pooled over the test vintages against the pooled
    mean, as in the design probe. A development row: it adjudicates nothing."""
    dev = set(F.DEV_VINTAGES)
    bad = sorted(int(v) for v in vintages if int(v) not in dev)
    if bad:
        raise F.ReservedFrameError(f"dev_oos_r2 reads development vintages only, got {bad}")
    pf, pb, yy, per = [], [], [], {}
    for t in sorted(int(v) for v in vintages):
        if t + 1 not in dev:
            continue
        fit = consensus_revision_hat(side, t, universe=universe)
        if fit["status"] != "ok":
            per[t] = {"status": fit["status"], "n_train": fit["n_train"]}
            continue
        tgt = revision_targets(side, t, universe=universe)
        keys = sorted(k for k in fit["hat"] if k in tgt)
        if len(keys) < MIN_TEST_ROWS:
            per[t] = {"status": "too_few_test_rows", "n_train": fit["n_train"],
                      "n_test": len(keys)}
            continue
        pf += [fit["hat"][k] for k in keys]
        pb += [fit["hat_base"][k] for k in keys]
        yy += [tgt[k] for k in keys]
        per[t] = {"status": "ok", "n_train": fit["n_train"], "n_test": len(keys),
                  "train_vintages": fit["train_vintages"]}
    out = {"side": side, "role": "development", "frame": "lv_dev",
           "target": "c(V+1) - c(V), grade space", "per_vintage": per,
           "n_oos": len(yy), "columns": list(BASE_COLUMNS) + list(feature_columns(side))}
    if len(yy) < MIN_TEST_ROWS:
        out["status"] = "insufficient"
        return out
    from scipy.stats import spearmanr
    y = np.asarray(yy, dtype=float)
    sst = float(((y - y.mean()) ** 2).sum())

    def r2(p):
        return 1.0 - float(((y - np.asarray(p)) ** 2).sum()) / sst

    out.update(status="ok", sd_dc=round(float(y.std()), 3),
               oos_r2_base=round(r2(pb), 4), oos_r2_full=round(r2(pf), 4),
               rho_dc_base=round(float(spearmanr(pb, y).statistic), 4),
               rho_dc_full=round(float(spearmanr(pf, y).statistic), 4))
    return out


# ---------------------------------------------------------------------------
# D3: org-private signals from the transaction history
# ---------------------------------------------------------------------------

_TX_MEMO: dict[str, list[dict]] | None = None


def load_transactions() -> dict[str, list[dict]]:
    """{player_key: [transaction]} from the player_transactions table (memoized)."""
    global _TX_MEMO
    if _TX_MEMO is None:
        import storage
        _TX_MEMO = storage.load_player_transactions()
    return _TX_MEMO


def _tx_date(tx: dict) -> str:
    return str(tx.get("date") or tx.get("effective_date") or "")[:10]


def _history(player_key: str, cutoff: str, transactions: dict | None) -> list[dict]:
    """The player's transactions announced strictly before `cutoff`, oldest first."""
    txs = (transactions if transactions is not None else load_transactions()
           ).get(player_key) or []
    cut = str(cutoff)[:10]
    known = [t for t in txs if _tx_date(t) and _tx_date(t) < cut]
    known.sort(key=lambda t: (_tx_date(t), t.get("id") or 0))
    return known


def contract_selections_asof(player_key: str, cutoff: str, *,
                             transactions: dict | None = None) -> list[dict]:
    """Every contract selection (type SE) announced before `cutoff`, oldest first."""
    return [{"date": _tx_date(t), "from_team_id": t.get("from_team_id"),
             "to_team_id": t.get("to_team_id"), "november": _tx_date(t)[5:7] == _NOVEMBER,
             "description": t.get("description") or ""}
            for t in _history(player_key, cutoff, transactions)
            if t.get("type_code") == "SE"]


def forty_man_asof(player_key: str, cutoff: str, *,
                   transactions: dict | None = None) -> dict:
    """40-man status and protection history as of `cutoff` (see module docstring)."""
    hist = _history(player_key, cutoff, transactions)
    out = {"cutoff": str(cutoff)[:10], "observed": bool(hist),
           "history_from": _tx_date(hist[0]) if hist else None,
           "on_40man": None, "status_event": None, "status_date": None,
           "november_adds": [], "rule5_selected": False, "rule5_minors_selected": False}
    if not hist:
        return out
    on = False
    for t in hist:
        code = t.get("type_code")
        if code in _ADD or code in _IMPLIED:
            on = True
        elif code in _REMOVE:
            on = False
        else:
            continue
        out["status_event"], out["status_date"] = code, _tx_date(t)
        if code == "SE" and _tx_date(t)[5:7] == _NOVEMBER:
            out["november_adds"].append(_tx_date(t))
        elif code == "R5":
            out["rule5_selected"] = True
        elif code == "R5M":
            out["rule5_minors_selected"] = True
    out["on_40man"] = on
    return out


def org_signals_for_frame(rows: list[dict], *, transactions: dict | None = None
                          ) -> list[dict]:
    """Attach D3 columns to F-LV rows, each as of its own window start (V-01-01)."""
    txs = transactions if transactions is not None else load_transactions()
    for r in rows:
        cut = r["window"][0]
        fm = forty_man_asof(r["player_key"], cut, transactions=txs)
        sel = contract_selections_asof(r["player_key"], cut, transactions=txs)
        r["tx_cutoff"] = cut
        r["tx_observed"] = fm["observed"]
        r["forty_man_at_v"] = fm["on_40man"]
        r["november_added_before_v"] = (bool(fm["november_adds"]) if fm["observed"]
                                        else None)
        r["contract_selections_before_v"] = len(sel) if fm["observed"] else None
        r["rule5_selected_before_v"] = fm["rule5_selected"] if fm["observed"] else None
    return rows


if __name__ == "__main__":
    import json
    import sys
    u = F.load_universe()
    res = {s: dev_oos_r2(s, universe=u) for s in F.SIDES}
    json.dump(res, sys.stdout, indent=1, default=str)
    sys.stdout.write("\n")

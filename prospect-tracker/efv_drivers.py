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

DS-09 (Driver System V2). The per-player store above is keyed on record ids, which are a
debut proxy (bug B4), so the V2 timing head reads protection_for_frame instead: the
league-wide monthly feed joined on the frame row's OUTCOME-BLIND id. The same section
holds the BMI re-test input (bmi_asof, dated FanGraphs board archives) and the PV-12
Pipeline-revision slot (pl_revision_for_rows).

RESERVED FRAMES. Every entry point calls efv_vintage_frame.guard_score_request for each
list vintage it reads, INCLUDING the V + 1 target vintage, so a development evaluation
stops at V = 2018 (its target is the 2019 read) and nothing here opens 2020 or 2021
without the committed gate sha. dev_oos_r2 refuses any vintage outside DEV_VINTAGES.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md). Nothing here groups, counts or averages
rows by consensus-FV level; the consensus enters only as a continuous regressor.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

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


# ---------------------------------------------------------------------------
# DS-09: protection status from the LEAGUE-WIDE transaction feed (outcome-blind)
# ---------------------------------------------------------------------------
# The per-player store above is fetched by each record's stored mlbam id, and records
# gained ids mostly on reaching the majors (bug B4), so its coverage is itself a debut
# proxy. The V2 timing head reads protection from the monthly league-wide feed instead
# (.cache/mlb_transactions/tx_YYYY_MM.json.gz: 2008 to 2014 from
# tools/backfill_mlb_transactions.py, 2015 onward from tools/pt_risk_lab.py fetch),
# joined on the OUTCOME-BLIND id the frame row carries (efv_identity via
# efv_vintage_frame). A row without a resolved id gets None, never False.
#
#     on_40man   the latest status-bearing transaction ANNOUNCED before V-01-01
#                decides, with the same codes as forty_man_asof, plus a signing whose
#                description says "major league contract" (it puts the player on the
#                40-man; the league feed spells this out where the per-player payload
#                does not).
#     nov_add    a contract selection (SE) announced in November of V - 1, the
#                Rule 5 protection window.
#
# COVERAGE. The feed is sparse before 2009 (2008 holds 389 transactions against about
# 25,000 to 35,000 a year from 2009), so a list vintage V reads LEAGUE_TX_FULL_FROM
# through V - 1; protection_coverage reports the years of history by V.

TX_DIR = Path(__file__).resolve().parent / ".cache" / "mlb_transactions"
#: First month of the league feed on disk, and the first year it is complete.
LEAGUE_TX_FIRST = (2008, 1)
LEAGUE_TX_FULL_FROM = 2009
_MLB_CONTRACT = "major league contract"
_SIGNINGS = frozenset({"SGN", "SFA"})

_LEAGUE_TX_MEMO: dict[tuple, dict[int, list[tuple[str, str, str]]]] = {}


def league_tx_path(year: int, month: int, tx_dir: Path = TX_DIR) -> Path:
    return Path(tx_dir) / f"tx_{int(year)}_{int(month):02d}.json.gz"


def league_tx_months(last_year: int, tx_dir: Path = TX_DIR) -> dict[str, bool]:
    """{"YYYY-MM": on disk} from LEAGUE_TX_FIRST through December of last_year."""
    out = {}
    y, m = LEAGUE_TX_FIRST
    while y <= int(last_year):
        out[f"{y}-{m:02d}"] = league_tx_path(y, m, tx_dir).exists()
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def load_league_transactions(last_year: int, *, tx_dir: Path = TX_DIR
                             ) -> dict[int, list[tuple[str, str, str]]]:
    """{person id: [(announced date, type code, lower-case description)]}, oldest first,
    from every cached month through December of last_year (memoized)."""
    key = (str(tx_dir), int(last_year))
    hit = _LEAGUE_TX_MEMO.get(key)
    if hit is not None:
        return hit
    out: dict[int, list[tuple[str, str, str]]] = {}
    for ym, present in league_tx_months(last_year, tx_dir).items():
        if not present:
            continue
        y, m = (int(p) for p in ym.split("-"))
        with gzip.open(league_tx_path(y, m, tx_dir), "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        for t in doc.get("transactions") or []:
            pid = (t.get("person") or {}).get("id")
            day = str(t.get("date") or t.get("effectiveDate") or "")[:10]
            if not pid or not day:
                continue
            out.setdefault(int(pid), []).append(
                (day, str(t.get("typeCode") or ""), str(t.get("description") or "").lower()))
    for evs in out.values():
        evs.sort()
    _LEAGUE_TX_MEMO[key] = out
    return out


def protection_asof(person_id, vintage: int,
                    index: dict[int, list[tuple[str, str, str]]]) -> dict:
    """Protection status of one outcome-blind id at the V read (cutoff V-01-01).
    None on every field when the id is unresolved or the feed does not reach V - 1."""
    V = int(vintage)
    cut = f"{V}-01-01"
    out = {"cutoff": cut, "observed": False, "on_40man": None, "nov_add": None,
           "status_event": None}
    try:
        pid = int(person_id) if person_id is not None else None
    except (TypeError, ValueError):
        pid = None
    if pid is None or V - 1 < LEAGUE_TX_FULL_FROM:
        return out
    on = False
    nov = False
    nov_month = f"{V - 1}-{_NOVEMBER}"
    for day, code, desc in index.get(pid, ()):
        if day >= cut:
            break
        if code in _ADD or code in _IMPLIED or (code in _SIGNINGS
                                                 and _MLB_CONTRACT in desc):
            on = True
        elif code in _REMOVE:
            on = False
        else:
            continue
        out["status_event"] = code
        if code == "SE" and day[:7] == nov_month:
            nov = True
    out.update(observed=True, on_40man=1.0 if on else 0.0, nov_add=1.0 if nov else 0.0)
    return out


def protection_for_frame(rows: list[dict], *, index=None, tx_dir: Path = TX_DIR
                         ) -> list[dict]:
    """Attach on_40man_at_v and nov_add_v_minus_1 to F-LV rows, each read on the row's
    outcome-blind `mlbam_id` as of its own window start. Never reads record_mlbam_id."""
    if not rows:
        return rows
    last = max(int(r["vintage"]) for r in rows) - 1
    idx = index if index is not None else load_league_transactions(last, tx_dir=tx_dir)
    for r in rows:
        p = protection_asof(r.get("mlbam_id"), r["vintage"], idx)
        r["protection_cutoff"] = p["cutoff"]
        r["protection_observed"] = p["observed"]
        r["on_40man_at_v"] = p["on_40man"]
        r["nov_add_v_minus_1"] = p["nov_add"]
    return rows


def protection_coverage(rows: list[dict]) -> dict:
    """Per list vintage: rows, rows with a protection read, how many of those were on
    the 40-man and had a November add, and the years of complete feed before the read.
    Counts by vintage only; nothing here is split by grade."""
    out: dict = {}
    for r in rows:
        v = int(r["vintage"])
        c = out.setdefault(v, {"rows": 0, "observed": 0, "on_40man": 0, "nov_add": 0,
                               "feed_years_before_read": max(0, v - LEAGUE_TX_FULL_FROM)})
        c["rows"] += 1
        if r.get("protection_observed"):
            c["observed"] += 1
            c["on_40man"] += int(bool(r.get("on_40man_at_v")))
            c["nov_add"] += int(bool(r.get("nov_add_v_minus_1")))
    return {str(v): c for v, c in sorted(out.items())}


# ---------------------------------------------------------------------------
# BMI as of the read, from the dated FanGraphs board archives (one pre-declared
# pitcher skill-head re-test, owner question 2026-09-25)
# ---------------------------------------------------------------------------
# data/_frozen/arch_bio_panel.json holds, per player key, every dated FanGraphs board listing
# (report, updated and draft boards from 2017) with height (inches) and weight (lb).
# It is a FROZEN INPUT with no producer in the repo: its builder, the archetype lab
# script tools/_arch_bio_panel.py, was deleted in 8fecb2f5 (last copy at 8fecb2f5^).
# Moved byte-identical from tools/_arch_bio_panel.json on 2026-10-03; data/_frozen/
# ships in neither deploy consumer.
# bmi_asof reads the LATEST listing dated on or before the read and never a later one.
# Height, weight, BMI and frame were tested twice before (the D-2 driver arms and the
# archetype bio lab, tools/_arch_bio_result.json, all null); this is one re-test in the
# V2 pitcher skill head, counted in the forking-path total.

BIO_PANEL = Path(__file__).resolve().parent / "data" / "_frozen" / "arch_bio_panel.json"
_BMI_FACTOR = 703.0          # lb per square inch to kg per square metre
_BIO_MEMO: dict[str, dict[str, list[dict]]] = {}


def load_bio_panel(path: Path = BIO_PANEL) -> dict[str, list[dict]]:
    key = str(path)
    if key not in _BIO_MEMO:
        _BIO_MEMO[key] = json.loads(Path(path).read_text(encoding="utf-8"))
    return _BIO_MEMO[key]


def bmi_asof(player_key: str, asof_date: str | None, panel: dict[str, list[dict]]
             ) -> float | None:
    """BMI from the latest dated listing on or before asof_date, or None."""
    if not asof_date:
        return None
    cut = str(asof_date)[:10]
    best = None
    for e in panel.get(player_key) or ():
        d = str(e.get("vintage") or "")[:10]
        h, w = e.get("h"), e.get("w")
        if not d or d > cut or not _finite(h) or not _finite(w) or h <= 0 or w <= 0:
            continue
        if best is None or d > best[0]:
            best = (d, float(h), float(w))
    if best is None:
        return None
    return round(_BMI_FACTOR * best[2] / (best[1] ** 2), 4)


def bmi_for_rows(rows: list[dict], *, date_field: str = "asof_date",
                 panel: dict[str, list[dict]] | None = None) -> list[dict]:
    """Attach bmi_at_read (and the date it was read as of) to each row."""
    pan = panel if panel is not None else load_bio_panel()
    for r in rows:
        r["bmi_asof_date"] = r.get(date_field)
        r["bmi_at_read"] = bmi_asof(r.get("player_key"), r.get(date_field), pan)
    return rows


# ---------------------------------------------------------------------------
# PV-12: the Pipeline-revision candidate (provisional program, PROVISIONAL_V2.md s3)
# ---------------------------------------------------------------------------
# The pre-grade provisional prediction anticipated MLB Pipeline's own later revision given
# its first FV (dR2 0.031, CI95 0.006 to 0.082, survivor-only, in sample). It is a
# pre-declared V2 skill candidate for Pipeline-anchored rows only. Its input, the
# forward-chained PG2 Pipeline prediction per anchor, is not in this repository, and its
# first anchor is 2021-10-15 (PG2 anchors 2021 to 2025), so the first list vintage whose
# read can follow a prediction is PL_REV_FIRST_LIST_VINTAGE: no development vintage
# (2011 to 2019) and no R-LV vintage (2020, 2021) can carry it. The slot stays so the
# admission rule sees it and the forking-path count carries it.

PL_REV_FIRST_ANCHOR = "2021-10-15"
PL_REV_FIRST_LIST_VINTAGE = 2022


def pipeline_anchored(row: dict) -> bool:
    """True when the row's read carries an MLB Pipeline grade."""
    g = row.get("grades") or {}
    return g.get("mlb_pipeline") is not None


def pl_revision_for_rows(rows: list[dict], preds: dict | None = None) -> list[dict]:
    """Attach pl_rev_at_read: the latest pre-grade Pipeline prediction dated before the
    row's read, for Pipeline-anchored rows only. `preds` maps an outcome-blind id to
    [(anchor date, prediction)] oldest first; with none supplied every row gets None."""
    src = preds or {}
    for r in rows:
        val = None
        if pipeline_anchored(r) and r.get("mlbam_id") is not None:
            cut = str(r.get("asof_date") or "")[:10]
            known = [p for d, p in src.get(r["mlbam_id"], ()) if str(d)[:10] < cut]
            val = float(known[-1]) if known else None
        r["pl_rev_at_read"] = val
    return rows


if __name__ == "__main__":
    import sys
    u = F.load_universe()
    res = {s: dev_oos_r2(s, universe=u) for s in F.SIDES}
    json.dump(res, sys.stdout, indent=1, default=str)
    sys.stdout.write("\n")

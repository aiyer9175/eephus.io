# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Lane D-3 -- fit a recency decay on consensus vote weight and gate it.

READ-ONLY on consensus.py, efv_dataset.py and source_backtest.py. This lab rebuilds
source_backtest's common pool from the snapshot table, recomputes the consensus under
alternative age-decay weightings, and scores the CONSENSUS's own accuracy against
realized WAR. It never reads an eFV matrix for its statistic.

Pre-registration, verdict rule and results:
    docs/efv-2026-08-07b/CONSENSUS_RECENCY_GATE.md
Artifact:
    data/consensus_recency_eval.json

Arms (gate doc section 4a):
    nodecay        w(age) = 1                          BASELINE (production today)
    exp_global     w(age) = 2 ** (-age / H)            HEADLINE, gated
    exp_persource  separate H for fangraphs / mlb_pipeline / other        secondary
    cliff          w = 1 if age <= T else c                                secondary
    degenerate     only the newest publication date votes                 CONTROL

Controls (gate doc section 4c):
    C1 permuted-date null (500 draws, full refit each draw)
    C2 nodecay + degenerate bracket
    C3 player-cluster bootstrap (500 draws)
    C4 MDE95 = 1.96 * sd(d_rho under C1)

Run: python tools/consensus_recency_lab.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import consensus as C                      # noqa: E402
import efv_dataset as EFV                  # noqa: E402
import source_backtest as SB               # noqa: E402
import storage                             # noqa: E402
from grade_normalization import build_remapper   # noqa: E402

DATA = _ROOT / "data"
OUT = DATA / "consensus_recency_eval.json"

SEED = 20260807
N_PERM = 500
N_BOOT = 500

# Gate doc 4a. Half-life grid in days.
H_GRID = (30, 60, 90, 120, 180, 240, 365, 547, 730, 1095, 1460, 2190)
CLIFF_T = (180, 365, 730)
CLIFF_C = (0.0, 0.25, 0.5, 0.75)

# Gate doc 4b. Base years and folds.
BASE_YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023)
FOLD_YEARS = (2019, 2020, 2021, 2022, 2023)

# Gate doc 5, clause 5. SELF-ADDED threshold, disclosed in the headline if binding.
H_SPAN_MAX = 10.0
# source_backtest's own incumbent floor for a consensus A/B, quoted for calibration.
INCUMBENT_MDE95 = 0.0068

FASTPATH_TOL = 1e-9


def _d(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


# ---------------------------------------------------------------------------
# 1. Pool construction -- mirrors source_backtest.run_source_backtest's common set
# ---------------------------------------------------------------------------

def load_outcomes() -> dict:
    """career_war outcome per player_key, from the same universe source_backtest reads."""
    uni = SB._load_universe(DATA)
    out = {}
    for p in uni:
        o = SB._outcome(p)
        out[p.get("player_key")] = {"war": o["war"], "debuted": o["debuted"],
                                    "contributor": o["contributor"]}
    return out


def build_pool(outcomes: dict):
    """[(player_key, base_year, event_date, day_snaps_flat, asof_fv_instances)]."""
    snaps = [C._canonicalize_player_snapshot(s) for s in storage.load_all_snapshots()]
    by_player: dict[str, list] = defaultdict(list)
    for s in snaps:
        by_player[s.player_key].append(s)
    org_ranked, _ = C._org_ranked_snapshot_keys(snaps)

    rows = []
    for pk in sorted(by_player):                      # sorted: never iterate a set/hash order
        if pk not in outcomes:
            continue
        ps = C._prune_collision_cluster(by_player[pk])
        by_date: dict[str, list] = defaultdict(list)
        for s in ps:
            by_date[s.snapshot_date].append(s)
        dates = sorted(by_date)
        last_in_window = {}
        for d in dates:
            if SB._WINDOW_START_MMDD <= d[4:] < SB._WINDOW_END_MMDD:
                y = int(d[:4])
                if y in BASE_YEARS:
                    last_in_window[y] = d
        if not last_in_window:
            continue
        latest: dict[str, list] = {}
        asof_fv: set = set()
        state = {}
        # per-year: which sources published an fv anywhere inside the window
        win_src: dict = defaultdict(set)
        for d in dates:
            for s in by_date[d]:
                if s.fv is not None and s.source not in C.CONSTANT_ANCHOR_SOURCES:
                    asof_fv.add((s.source, s.snapshot_date))
                prev = latest.get(s.source)
                if not prev:
                    latest[s.source] = [s]
                elif s.snapshot_date > prev[0].snapshot_date:
                    latest[s.source] = [s]
                elif s.snapshot_date == prev[0].snapshot_date:
                    dup = any(e.interval_label == s.interval_label and e.fv == s.fv
                              and e.rank == s.rank for e in prev)
                    if not dup:
                        prev.append(s)
            y = int(d[:4])
            if SB._WINDOW_START_MMDD <= d[4:] < SB._WINDOW_END_MMDD and y in BASE_YEARS:
                flat = [x for lst in latest.values() for x in lst]
                for s in C._dedupe_source_aliases(list(flat)):
                    if s.fv is not None:
                        win_src[y].add(s.source)
                if last_in_window.get(y) == d:
                    state[y] = (d, list(flat), len(asof_fv))
        for y in sorted(state):
            if all(r in win_src[y] for r in SB.SCORED_SOURCES):
                d, flat, nfv = state[y]
                rows.append((pk, y, d, flat, nfv))
    return rows, org_ranked


# ---------------------------------------------------------------------------
# 2. Vote-vector extraction + the fast weighted-mean path
# ---------------------------------------------------------------------------

def extract_votes(rows, grade_norm):
    """Per pool row: the ordered vote vector compute_consensus_point would build.

    Faithful to consensus.compute_consensus_point:848-972 for the configuration this
    repo actually ships (DROPOFF_SHRINK_ENABLED False, so no (fv+30)/2 leg).
    """
    out = []
    for pk, y, ev, flat, nfv in rows:
        day = list(flat)
        alias_src = C._alias_grade_sources(day)
        dd = C._dedupe_source_aliases(day)
        seen: set = set()
        votes = []          # (source, fv_for_consensus, age_days, is_constant)
        has_rank = False
        evd = _d(ev)
        for s in dd:
            if s.rank is not None:
                has_rank = True
            if s.source in seen:
                continue          # extras never re-vote
            seen.add(s.source)
            if s.fv is None:
                continue
            base = s.fv
            if grade_norm is not None:
                try:
                    yr = int(str(s.snapshot_date)[:4])
                    gsrc = alias_src.get((s.player_key, s.source), s.source)
                    nm = grade_norm(base, gsrc, s.position, yr)
                    if nm is not None:
                        base = nm
                except (TypeError, ValueError):
                    base = s.fv
            age = (evd - _d(s.snapshot_date)).days
            votes.append((s.source, float(base), max(0, age),
                          s.source in C.CONSTANT_ANCHOR_SOURCES))
        out.append({"pk": pk, "year": y, "date": ev, "nfv": nfv,
                    "votes": votes, "has_rank": has_rank})
    return out


def fast_consensus(vote_row, wfun) -> float | None:
    """Weighted-mean consensus for one pool row under weight function wfun(source, age)."""
    ex_v, ex_w, sy_v, sy_w = [], [], [], []
    for src, fv, age, is_const in vote_row["votes"]:
        w = C._SOURCE_WEIGHTS.get(src, 1.0) * wfun(src, age)
        if is_const:
            sy_v.append(fv); sy_w.append(w)
        else:
            ex_v.append(fv); ex_w.append(w)
    if not ex_v and sy_v:
        ex_v, ex_w = sy_v, sy_w
    if not ex_v:
        return None
    wsum = sum(ex_w) or float(len(ex_v))
    pre = sum(w * v for w, v in zip(ex_w, ex_v)) / wsum
    if vote_row["nfv"] <= 1 and C.SINGLE_SOURCE_K > 0:
        sw = 1.0 / (1.0 + C.SINGLE_SOURCE_K)
        pre = sw * pre + (1.0 - sw) * C.SINGLE_SOURCE_PRIOR
    # ConsensusPoint stores consensus_fv_raw=round(value, 2) (consensus.py:1121).
    # The fast path matches that rounding, so it reproduces what production serves.
    return round(pre, 2)


def real_consensus(row, org_ranked, grade_norm, wfun) -> float | None:
    """Same quantity via the REAL consensus.compute_consensus_point."""
    pk, y, ev, flat, nfv = row
    dd = C._dedupe_source_aliases(list(flat))
    evd = _d(ev)
    sw = {}
    for s in dd:
        age = max(0, (evd - _d(s.snapshot_date)).days)
        sw[s.source] = C._SOURCE_WEIGHTS.get(s.source, 1.0) * wfun(s.source, age)
    pt = C.compute_consensus_point(
        list(flat), event_date=ev, event_label="lab",
        single_source_k=C.SINGLE_SOURCE_K, total_fv_instances=nfv,
        dropped_off_pairs=set(), source_weights=sw,
        grade_norm=grade_norm, org_ranked_rows=org_ranked)
    return pt.consensus_fv_raw if pt is not None else None


# ---------------------------------------------------------------------------
# 3. Weight functions
# ---------------------------------------------------------------------------

def w_nodecay(src, age):
    return 1.0


def w_exp(H):
    def f(src, age, H=float(H)):
        return 2.0 ** (-age / H)
    return f


def w_exp_persource(h_fg, h_pipe, h_other):
    def f(src, age, a=float(h_fg), b=float(h_pipe), c=float(h_other)):
        H = a if src == "fangraphs" else (b if src == "mlb_pipeline" else c)
        return 2.0 ** (-age / H)
    return f


def w_cliff(T, c):
    def f(src, age, T=float(T), c=float(c)):
        return 1.0 if age <= T else c
    return f


def degenerate_ages(vote_row):
    """Weight 1 only on the freshest vote(s) at this row (age == min age)."""
    if not vote_row["votes"]:
        return {}
    mn = min(v[2] for v in vote_row["votes"])
    return {v[0]: (1.0 if v[2] == mn else 0.0) for v in vote_row["votes"]}


# ---------------------------------------------------------------------------
# 4. Scoring
# ---------------------------------------------------------------------------

def score(preds, idx, wars, contrib):
    x = [preds[i] for i in idx]
    y = [wars[i] for i in idx]
    c = [contrib[i] for i in idx]
    return SB._spearman(x, y), SB._auc(x, c)


def rho_only(preds, idx, wars):
    return SB._spearman([preds[i] for i in idx], [wars[i] for i in idx])


def forward_chain(pred_by_param, params, idx_by_year, wars):
    """Select a param per fold on earlier years, return (oos_idx, oos_pred, chosen)."""
    chosen = {}
    oos_idx, oos_pred = [], {}
    for fy in FOLD_YEARS:
        tr = [i for y in BASE_YEARS if y < fy for i in idx_by_year.get(y, [])]
        best, best_r = None, None
        for p in params:                     # params is an ordered tuple, never a set
            r = rho_only(pred_by_param[p], tr, wars)
            if r is None:
                continue
            if best_r is None or r > best_r:
                best, best_r = p, r
        chosen[fy] = best
        for i in idx_by_year.get(fy, []):
            oos_idx.append(i)
            oos_pred[i] = pred_by_param[best][i]
    return oos_idx, oos_pred, chosen


def main():
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    print("loading outcomes ...")
    outcomes = load_outcomes()
    print("building pool ...")
    rows, org_ranked = build_pool(outcomes)
    # as-of cutoff threaded 2026-08-14 with the C-4 flip. consensus.grade_norm_cutoff
    # is the single point of truth, so this lab cannot describe a basis the board
    # does not serve.
    grade_norm = build_remapper(aliases=C.SOURCE_ALIASES,
                                as_of_year=C.grade_norm_cutoff())
    n = len(rows)
    players = sorted({r[0] for r in rows})
    print(f"pool rows={n} players={len(players)}  ({time.time()-t0:.1f}s)")

    votes = extract_votes(rows, grade_norm)
    wars = [outcomes[r[0]]["war"] for r in rows]
    contrib = [outcomes[r[0]]["contributor"] for r in rows]
    years = [r[1] for r in rows]
    idx_by_year = defaultdict(list)
    for i, y in enumerate(years):
        idx_by_year[y].append(i)

    # ---- served-consensus fidelity (gate doc 2b) --------------------------
    served = {}
    for p in SB._load_universe(DATA):
        for pt in (p.get("points") or []):
            served[(p.get("player_key"), pt.get("snapshot_date"))] = pt.get("consensus_fv_raw")
    base_real = [real_consensus(r, org_ranked, grade_norm, w_nodecay) for r in rows]
    fid = []
    for r, v in zip(rows, base_real):
        sv = served.get((r[0], r[2]))
        if sv is not None and v is not None:
            fid.append(abs(v - float(sv)))
    fidelity = {
        "n": len(fid),
        "pct_within_0.005": round(sum(1 for x in fid if x <= 0.005) / len(fid), 4),
        "mean_abs": round(sum(fid) / len(fid), 4),
        "max_abs": round(max(fid), 4),
        "note": ("served timeseries.json predates this session's Baseball America ingest; "
                 "the residual is BA rows entering the average"),
    }
    print("fidelity vs served:", fidelity)

    # ---- fast-path verification (gate doc 4d) ----------------------------
    print("verifying fast path ...")
    checks = []
    wfuns = [("nodecay", w_nodecay)] + [(f"exp_{h}", w_exp(h)) for h in H_GRID] \
        + [(f"cliff_{T}_{c}", w_cliff(T, c)) for T in CLIFF_T for c in CLIFF_C]
    worst = 0.0
    for name, wf in wfuns:
        for r, vr in zip(rows, votes):
            a = real_consensus(r, org_ranked, grade_norm, wf)
            b = fast_consensus(vr, wf)
            if a is None or b is None:
                if a is not b:
                    worst = float("inf")
                continue
            worst = max(worst, abs(a - b))
        checks.append(name)
    # degenerate is row-specific, so it is verified with a per-row closure
    for r, vr in zip(rows, votes):
        wmap = degenerate_ages(vr)
        wf = (lambda src, age, m=wmap: m.get(src, 1.0))
        a = real_consensus(r, org_ranked, grade_norm, wf)
        b = fast_consensus(vr, wf)
        if a is not None and b is not None:
            worst = max(worst, abs(a - b))
    fastpath_check = {"arms_checked": len(checks) + 1, "max_abs_delta": worst,
                      "tolerance": FASTPATH_TOL, "passed": worst <= FASTPATH_TOL}
    print("fastpath:", fastpath_check)
    if not fastpath_check["passed"]:
        OUT.write_text(json.dumps({"status": "BLOCKED", "fastpath_check": fastpath_check},
                                  indent=1), encoding="utf-8")
        print("BLOCKED: fast path does not reproduce compute_consensus_point")
        return

    # ---- predictions per parameter ---------------------------------------
    pred_nodecay = [fast_consensus(v, w_nodecay) for v in votes]
    pred_exp = {h: [fast_consensus(v, w_exp(h)) for v in votes] for h in H_GRID}
    pred_cliff = {(T, c): [fast_consensus(v, w_cliff(T, c)) for v in votes]
                  for T in CLIFF_T for c in CLIFF_C}
    pred_degen = []
    for v in votes:
        wmap = degenerate_ages(v)
        pred_degen.append(fast_consensus(v, lambda src, age, m=wmap: m.get(src, 1.0)))

    # ---- forward-chained headline ----------------------------------------
    oos_idx, oos_exp, chosen_exp = forward_chain(pred_exp, H_GRID, idx_by_year, wars)
    oos_players = len({rows[i][0] for i in oos_idx})
    rho_b, auc_b = score(pred_nodecay, oos_idx, wars, contrib)
    exp_vec = [oos_exp.get(i) for i in range(n)]
    rho_e, auc_e = score(exp_vec, oos_idx, wars, contrib)
    rho_d, auc_d = score(pred_degen, oos_idx, wars, contrib)

    # secondary families
    oos_cliff, chosen_cliff = None, None
    cparams = tuple((T, c) for T in CLIFF_T for c in CLIFF_C)
    ci, cp, chosen_cliff = forward_chain(pred_cliff, cparams, idx_by_year, wars)
    cliff_vec = [cp.get(i) for i in range(n)]
    rho_c, auc_c = score(cliff_vec, ci, wars, contrib)

    # per-source: coordinate ascent per fold, initialized at that fold's exp_global pick
    chosen_ps, ps_pred = {}, {}
    for fy in FOLD_YEARS:
        tr = [i for y in BASE_YEARS if y < fy for i in idx_by_year.get(y, [])]
        cur = [chosen_exp[fy]] * 3
        for coord in (0, 1, 2):
            best, best_r = cur[coord], None
            for h in H_GRID:
                trial = list(cur); trial[coord] = h
                p = [fast_consensus(v, w_exp_persource(*trial)) for v in votes]
                r = rho_only(p, tr, wars)
                if r is not None and (best_r is None or r > best_r):
                    best, best_r = h, r
            cur[coord] = best
        chosen_ps[fy] = tuple(cur)
        p = [fast_consensus(v, w_exp_persource(*cur)) for v in votes]
        for i in idx_by_year.get(fy, []):
            ps_pred[i] = p[i]
    ps_vec = [ps_pred.get(i) for i in range(n)]
    rho_p, auc_p = score(ps_vec, oos_idx, wars, contrib)

    d_rho = rho_e - rho_b
    d_auc = auc_e - auc_b
    print(f"rho base {rho_b:.5f} exp {rho_e:.5f} d {d_rho:+.5f} | "
          f"auc base {auc_b:.5f} exp {auc_e:.5f} d {auc_e-auc_b:+.5f}")
    print("chosen H per fold:", chosen_exp)

    # ---- POST-HOC EXPLORATORY slice (appended after the headline was seen) --
    # The obvious objection to the null: 88 percent of pool rows carry no stale vote
    # at all, so a real effect could be diluted to nothing by averaging. The slice is
    # defined on the REAL ages (rows whose oldest contributing vote exceeds 365 days),
    # is FIXED across permutation draws, and is explicitly NOT a gate clause.
    rowmax_age = [max((a for (_s, _f, a, _c) in v["votes"]), default=0) for v in votes]
    slice_idx = [i for i in oos_idx if rowmax_age[i] > 365]

    # ---- C1 permuted-date null -------------------------------------------
    print(f"permuted-date null, {N_PERM} draws ...")
    src_slots = defaultdict(list)            # source -> [(row_i, vote_j)]
    for i, v in enumerate(votes):
        for j, (src, fv, age, isc) in enumerate(v["votes"]):
            src_slots[src].append((i, j))
    src_names = sorted(src_slots)            # sorted list, never a set (standing rule F)
    orig = [list(v["votes"]) for v in votes]
    perm_drho, perm_dauc, perm_slice = [], [], []
    tperm = time.time()
    for b in range(N_PERM):
        for src in src_names:
            slots = src_slots[src]
            ages = [orig[i][j][2] for i, j in slots]
            order = rng.permutation(len(slots))
            for (i, j), k in zip(slots, order):
                s, fv, _a, isc = orig[i][j]
                votes[i]["votes"][j] = (s, fv, ages[k], isc)
        pe = {h: [fast_consensus(v, w_exp(h)) for v in votes] for h in H_GRID}
        pn = [fast_consensus(v, w_nodecay) for v in votes]     # unchanged, but recomputed
        oi, op, _ch = forward_chain(pe, H_GRID, idx_by_year, wars)
        ev = [op.get(i) for i in range(n)]
        r1, a1 = score(ev, oi, wars, contrib)
        r0, a0 = score(pn, oi, wars, contrib)
        perm_drho.append(r1 - r0)
        perm_dauc.append(a1 - a0)
        sr1, sr0 = rho_only(ev, slice_idx, wars), rho_only(pn, slice_idx, wars)
        if sr1 is not None and sr0 is not None:
            perm_slice.append(sr1 - sr0)
        if b == 9:
            print(f"  ... {(time.time()-tperm)/10:.2f}s/draw")
    for i, v in enumerate(votes):            # restore
        v["votes"] = orig[i]
    pr = np.array(perm_drho); pa = np.array(perm_dauc)
    perm = {
        "draws": N_PERM,
        "d_rho": {"mean": float(pr.mean()), "sd": float(pr.std(ddof=1)),
                  "p2.5": float(np.percentile(pr, 2.5)), "p50": float(np.percentile(pr, 50)),
                  "p97.5": float(np.percentile(pr, 97.5)), "p99": float(np.percentile(pr, 99)),
                  "max": float(pr.max())},
        "d_auc": {"mean": float(pa.mean()), "sd": float(pa.std(ddof=1)),
                  "p97.5": float(np.percentile(pa, 97.5)), "p99": float(np.percentile(pa, 99))},
        "one_sided_p_rho": float((pr >= d_rho).sum() + 1) / (N_PERM + 1),
        "one_sided_p_auc": float((pa >= d_auc).sum() + 1) / (N_PERM + 1),
    }
    mde95 = 1.96 * perm["d_rho"]["sd"]
    sl_r1, sl_a1 = score(exp_vec, slice_idx, wars, contrib)
    sl_r0, sl_a0 = score(pred_nodecay, slice_idx, wars, contrib)
    ps_ = np.array(perm_slice)
    exploratory_slice = {
        "definition": "OOS rows whose oldest contributing vote is older than 365 days",
        "status": "POST-HOC, appended after the headline was seen; NOT a gate clause",
        "rows": len(slice_idx),
        "share_of_oos": round(len(slice_idx) / len(oos_idx), 4),
        "rho_nodecay": sl_r0, "rho_exp_global": sl_r1,
        "d_rho": (sl_r1 - sl_r0) if (sl_r1 is not None and sl_r0 is not None) else None,
        "d_auc": (sl_a1 - sl_a0) if (sl_a1 is not None and sl_a0 is not None) else None,
        "perm_null_d_rho": {"draws": len(ps_), "mean": float(ps_.mean()),
                            "sd": float(ps_.std(ddof=1)),
                            "p99": float(np.percentile(ps_, 99))},
        "perm_one_sided_p": float((ps_ >= (sl_r1 - sl_r0)).sum() + 1) / (len(ps_) + 1),
        "mde95": 1.96 * float(ps_.std(ddof=1)),
    }
    print("exploratory stale slice:", {k: exploratory_slice[k]
                                       for k in ("rows", "d_rho", "perm_one_sided_p", "mde95")})
    print("perm null d_rho: mean %.5f sd %.5f p99 %.5f | MDE95 %.5f"
          % (perm["d_rho"]["mean"], perm["d_rho"]["sd"], perm["d_rho"]["p99"], mde95))

    # ---- C3 player-cluster bootstrap -------------------------------------
    print(f"player-cluster bootstrap, {N_BOOT} draws ...")
    idx_by_player = defaultdict(list)
    for i in oos_idx:
        idx_by_player[rows[i][0]].append(i)
    pl = sorted(idx_by_player)
    boot = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(pl), size=len(pl))
        bi = [i for k in pick for i in idx_by_player[pl[k]]]
        r1 = rho_only(exp_vec, bi, wars)
        r0 = rho_only(pred_nodecay, bi, wars)
        if r1 is not None and r0 is not None:
            boot.append(r1 - r0)
    ba = np.array(boot)
    bootstats = {"draws": len(boot), "p2.5": float(np.percentile(ba, 2.5)),
                 "p50": float(np.percentile(ba, 50)),
                 "p97.5": float(np.percentile(ba, 97.5))}
    print("cluster bootstrap d_rho:", bootstats)

    # ---- gate clauses ------------------------------------------------------
    hs = [chosen_exp[fy] for fy in FOLD_YEARS if chosen_exp[fy] is not None]
    h_span = (max(hs) / min(hs)) if hs else None
    clauses = {
        "1_above_perm_p99": bool(d_rho > 0 and d_rho > perm["d_rho"]["p99"]),
        "2_above_mde95": bool(d_rho > mde95),
        "3_cluster_boot_p2.5_above_0": bool(bootstats["p2.5"] > 0),
        "4_d_auc_positive": bool(d_auc > 0),
        "5_halflife_span_le_10x": bool(h_span is not None and h_span <= H_SPAN_MAX),
    }
    verdict = "PASS" if all(clauses.values()) else "NULL"

    # ---- E-STALE overlap ---------------------------------------------------
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))
    live_n = stale_n = decay_n = both_n = 0
    lam = math.log(2) / 365.0
    for p in (ts.get("players") or []):
        pts = p.get("points") or []
        if not pts:
            continue
        pt = pts[-1]
        if pt.get("consensus_fv_raw") is None:
            continue
        evd = _d(pt["snapshot_date"])
        ctr = set(pt.get("sources_contributing") or [])
        ages = []
        for src, ps in (pt.get("per_source") or {}).items():
            if src not in ctr or (ps or {}).get("fv_published") is None:
                continue
            ages.append((evd - _d(ps["snapshot_date"])).days)
        if not ages:
            continue
        live_n += 1
        anchor = EFV._anchor_asof_date(pt) or pt["snapshot_date"]
        disc = EFV._stale_anchor_discount(anchor, pt["consensus_fv_raw"], today=evd)
        w = [math.exp(-lam * max(0, a)) for a in ages]
        material = (max(w) - min(w)) > 0.05 or min(w) < 0.7
        if disc > 0:
            stale_n += 1
        if material:
            decay_n += 1
        if disc > 0 and material:
            both_n += 1
    estale = {"basis": "data/timeseries.json latest point per active player",
              "live_rows": live_n, "estale_discount_gt_0": stale_n,
              "materially_decayed_hl365": decay_n, "both": both_n,
              "training_rows_affected_by_estale": 0,
              "note": ("_stale_anchor_discount has ONE call site, efv_dataset.py:1331, "
                       "in the live-rows builder; it never fires on a training row, so the "
                       "overlap on this lane's 2017-2023 pool is structurally zero")}

    # ---- vote-age leverage census (gate doc 2c) ---------------------------
    allages = sorted(a for v in votes for (_s, _f, a, _c) in v["votes"])
    m = len(allages)
    rowmax = [max((a for (_s, _f, a, _c) in v["votes"]), default=0) for v in votes]
    leverage = {
        "votes": m, "median_age_days": allages[m // 2],
        "p90": allages[int(0.9 * m)], "p99": allages[int(0.99 * m)], "max": allages[-1],
        "share_votes_over_365d": round(sum(1 for a in allages if a > 365) / m, 4),
        "rows_with_a_vote_over_180d": sum(1 for a in rowmax if a > 180),
        "rows_with_a_vote_over_365d": sum(1 for a in rowmax if a > 365),
    }

    # ---- leverage: how far does each decay move the consensus? (gate doc 2d) --
    def _move(pred):
        dl = [abs(a - b) for a, b in zip(pred, pred_nodecay)
              if a is not None and b is not None]
        return {"n": len(dl),
                "pct_moved_ge_0.005": round(sum(1 for x in dl if x >= 0.005) / len(dl), 4),
                "pct_moved_ge_0.5fv": round(sum(1 for x in dl if x >= 0.5) / len(dl), 4),
                "mean_abs": round(sum(dl) / len(dl), 4), "max_abs": round(max(dl), 3)}
    leverage_move = {f"exp_H{h}": _move(pred_exp[h]) for h in (180, 365, 730, 1460)}
    leverage_move["degenerate"] = _move(pred_degen)

    ceiling_vs_floor = {
        "note": ("the whole mechanism's CEILING is the best in-sample H with full hindsight "
                 "and no fitting penalty; the FLOOR is what this design can resolve"),
        "in_sample_ceiling_d_rho": (max(rho_only(pred_exp[h], list(range(n)), wars)
                                        for h in H_GRID)
                                    - rho_only(pred_nodecay, list(range(n)), wars)),
        "mde95_floor_d_rho": mde95,
        "ceiling_over_floor": None,
    }
    ceiling_vs_floor["ceiling_over_floor"] = round(
        ceiling_vs_floor["in_sample_ceiling_d_rho"] / mde95, 3) if mde95 else None

    payload = {
        "lane": "D-3 consensus recency decay",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gate_doc": "docs/efv-2026-08-07b/CONSENSUS_RECENCY_GATE.md",
        "seed": SEED,
        "verdict": verdict,
        "pool": {"rows": n, "players": len(players),
                 "rows_by_year": {str(y): len(idx_by_year[y]) for y in BASE_YEARS},
                 "oos_rows": len(oos_idx), "oos_players": oos_players,
                 "served_common_n_reference": 4259},
        "fidelity_vs_served": fidelity,
        "fastpath_check": fastpath_check,
        "leverage": leverage,
        "leverage_move": leverage_move,
        "ceiling_vs_floor": ceiling_vs_floor,
        "exploratory_stale_slice": exploratory_slice,
        "results": {
            "nodecay": {"rho": rho_b, "auc": auc_b},
            "exp_global": {"rho": rho_e, "auc": auc_e, "d_rho": d_rho, "d_auc": d_auc,
                           "chosen_halflife_by_fold": {str(k): v for k, v in chosen_exp.items()},
                           "halflife_span": h_span},
            "degenerate": {"rho": rho_d, "auc": auc_d,
                           "d_rho": rho_d - rho_b, "d_auc": auc_d - auc_b},
            "cliff": {"rho": rho_c, "auc": auc_c, "d_rho": rho_c - rho_b,
                      "d_auc": auc_c - auc_b,
                      "chosen_by_fold": {str(k): list(v) if v else None
                                         for k, v in chosen_cliff.items()}},
            "exp_persource": {"rho": rho_p, "auc": auc_p, "d_rho": rho_p - rho_b,
                              "d_auc": auc_p - auc_b,
                              "chosen_by_fold": {str(k): list(v) for k, v in chosen_ps.items()}},
        },
        "in_sample_reference": {
            "note": "full-pool in-sample best H, reported only to show the ceiling",
            "best_H": max(H_GRID, key=lambda h: rho_only(pred_exp[h], list(range(n)), wars)),
            "rho_nodecay": rho_only(pred_nodecay, list(range(n)), wars),
            "rho_best": max(rho_only(pred_exp[h], list(range(n)), wars) for h in H_GRID),
        },
        "controls": {"permuted_date_null": perm, "cluster_bootstrap_d_rho": bootstats,
                     "mde95_d_rho": mde95, "incumbent_mde95_reference": INCUMBENT_MDE95},
        "gate_clauses": clauses,
        "multiplicity": {"families_measured": 3, "families_gated": 1,
                         "gated": "exp_global",
                         "note": "cliff and exp_persource are reported, not promotable"},
        "estale_overlap": estale,
        "self_added_thresholds": [
            {"threshold": "clause 5: forward-chained half-life span <= 10x",
             "source": "lane, not the brief",
             "binding": bool(not clauses["5_halflife_span_le_10x"]
                             and all(v for k, v in clauses.items() if k != "5_halflife_span_le_10x"))}
        ],
        "runtime_s": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("VERDICT:", verdict)
    print("clauses:", clauses)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

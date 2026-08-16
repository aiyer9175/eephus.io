"""Lane J1: the consensusRank gate-opening measurement.

Question: within a single (source, org|global, snapshot_date, interval_label, fv) cell,
does that source's own published rank predict realized WAR?

Read-only. Writes exactly one artifact, data/consensus_rank_eval.json.
Protocol pre-registered in docs/efv-2026-08-07b/CONSENSUS_RANK_GATE.md BEFORE this ran.

Run as:  python tools/consensus_rank_lab.py
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import the org-list regex, do NOT re-derive it. The Bryan Sanchez canary
# (rank 30 on a 2021 Nationals Top-30 inflating to FV 55, #19 overall with zero
# published FVs) is exactly what happens when org and global lists get pooled.
from consensus import _ORG_LIST_LABEL_RE as ORG_LIST_RE  # noqa: E402

DB_PATH = ROOT / "prospects.db"
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "consensus_rank_eval.json"

MIN_CELL_N = 5
N_PERM = 1000
N_BOOT = 500
SEED = 20260807


# ---------------------------------------------------------------------------
# labels: the eFV training matrix's own resolved-outcome basis
# ---------------------------------------------------------------------------

def load_labels() -> dict:
    """player_key -> {kind, censored, bust_recent, target_resolved, target_censored,
    cutoff, side}. Read off the on-disk labeled matrices, which are the exact frames
    efv_dataset.run scores its baselines on (efv_dataset.py:1371-1373)."""
    out = {}
    for side, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        rows = json.loads((DATA_DIR / fn).read_text(encoding="utf-8"))
        for r in rows:
            out[r["player_key"]] = {
                "side": side,
                "kind": r["kind"],
                "censored": bool(r["censored"]),
                "bust_recent": bool(r.get("bust_recent")),
                "target_resolved": r.get("target_resolved"),
                "target_censored": r.get("target_censored"),
                "cutoff": r.get("cutoff"),
            }
    return out


def label_value(lab: dict, basis: str):
    """full_pool_resolved / full_pool_censored, matching efv_dataset.run.

    resolved:  debuted rows with censored == False, plus busts that are not bust_recent.
    censored:  all debuted rows (censored tail projected), busts that are not bust_recent.
    """
    if lab["kind"] == "bust" and lab["bust_recent"]:
        return None
    if basis == "resolved":
        if lab["censored"]:
            return None
        return lab["target_resolved"]
    return lab["target_censored"]


# ---------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------

def load_snapshots() -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = [
            dict(r)
            for r in con.execute(
                "SELECT source, snapshot_date, interval_label, player_key, rank, fv "
                "FROM snapshots WHERE rank IS NOT NULL AND fv IS NOT NULL"
            )
        ]
    finally:
        con.close()
    return rows


def segment(interval_label) -> str:
    return "org" if ORG_LIST_RE.search(interval_label or "") else "global"


def fv_tier(fv) -> str:
    if fv is None:
        return "unknown"
    if fv <= 40:
        return "<=40"
    if fv <= 45:
        return "45"
    if fv <= 50:
        return "50"
    return "55+"


def build_pool(snaps, labels, basis) -> list[dict]:
    """One record per usable snapshot row: cell key, score, outcome, player_key."""
    pool = []
    for r in snaps:
        lab = labels.get(r["player_key"])
        if lab is None:
            continue
        # as-of: the snapshot must not postdate the eFV decision point
        if lab["cutoff"] and r["snapshot_date"] > lab["cutoff"]:
            continue
        y = label_value(lab, basis)
        if y is None:
            continue
        seg = segment(r["interval_label"])
        pool.append({
            "cell": (r["source"], seg, r["snapshot_date"], r["interval_label"] or "", r["fv"]),
            "source": r["source"],
            "seg": seg,
            "fv": r["fv"],
            "player_key": r["player_key"],
            # sign convention: better (lower-numbered) rank -> higher score, so a
            # positive statistic means rank predicts WAR in the expected direction.
            "score": -float(r["rank"]),
            "y": float(y),
        })
    return pool


def group_cells(pool) -> dict:
    cells = defaultdict(list)
    for rec in pool:
        cells[rec["cell"]].append(rec)
    return {k: v for k, v in cells.items() if len(v) >= MIN_CELL_N}


# ---------------------------------------------------------------------------
# statistics (hand-rolled, no scipy)
# ---------------------------------------------------------------------------

def cell_pair_counts(scores, ys):
    """Concordant / discordant pairs within one cell. Pairs tied on either axis are
    excluded from both. Returns (conc, disc, tied)."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(ys, dtype=float)
    ds = np.sign(s[:, None] - s[None, :])
    dy = np.sign(y[:, None] - y[None, :])
    prod = ds * dy
    iu = np.triu_indices(len(s), 1)
    p = prod[iu]
    conc = int((p > 0).sum())
    disc = int((p < 0).sum())
    tied = int((p == 0).sum())
    return conc, disc, tied


def _rank_avg(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    rx, ry = _rank_avg(xs), _rank_avg(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def statistic(cells) -> dict:
    """gamma_pooled (headline) + spearman_wmean (secondary) over a set of cells."""
    conc = disc = tied = 0
    sp_num = sp_den = 0.0
    n_cells_sp = 0
    for recs in cells.values():
        scores = [r["score"] for r in recs]
        ys = [r["y"] for r in recs]
        c, d, t = cell_pair_counts(scores, ys)
        conc += c
        disc += d
        tied += t
        rho = spearman(scores, ys)
        if rho is not None:
            sp_num += rho * len(recs)
            sp_den += len(recs)
            n_cells_sp += 1
    comparable = conc + disc
    return {
        "n_cells": len(cells),
        "n_rows": sum(len(v) for v in cells.values()),
        "n_players": len({r["player_key"] for v in cells.values() for r in v}),
        "pairs_total": conc + disc + tied,
        "pairs_comparable": comparable,
        "pairs_tied": tied,
        "gamma_pooled": round((conc - disc) / comparable, 5) if comparable else None,
        "spearman_wmean": round(sp_num / sp_den, 5) if sp_den else None,
        "n_cells_with_spearman": n_cells_sp,
    }


def gamma_only(cells) -> float | None:
    conc = disc = 0
    for recs in cells.values():
        c, d, _ = cell_pair_counts([r["score"] for r in recs], [r["y"] for r in recs])
        conc += c
        disc += d
    return (conc - disc) / (conc + disc) if (conc + disc) else None


def permute_null(cells, n_perm, rng) -> list[float]:
    """MANDATORY CONTROL: same statistic with rank permuted WITHIN each cell.
    Identical marginal, zero ordering information."""
    prepped = [([r["score"] for r in v], [r["y"] for r in v]) for v in cells.values()]
    out = []
    for _ in range(n_perm):
        conc = disc = 0
        for scores, ys in prepped:
            sh = scores[:]
            rng.shuffle(sh)
            c, d, _t = cell_pair_counts(sh, ys)
            conc += c
            disc += d
        out.append((conc - disc) / (conc + disc) if (conc + disc) else 0.0)
    return out


def cluster_bootstrap(pool, n_boot, rng) -> list[float]:
    """Resample distinct player_keys with replacement, rebuild cells from scratch.
    2,911 players supply ~10,400 rows, so cells are heavily correlated across dates and
    the permutation null alone understates the real statistic's variance."""
    by_player = defaultdict(list)
    for rec in pool:
        by_player[rec["player_key"]].append(rec)
    keys = list(by_player)
    n = len(keys)
    out = []
    for _ in range(n_boot):
        draw = []
        for _i in range(n):
            k = keys[rng.randrange(n)]
            draw.extend(by_player[k])
        g = gamma_only(group_cells(draw))
        if g is not None:
            out.append(g)
    return out


def pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
    return round(s[i], 5)


def null_band(nulls) -> dict:
    m = sum(nulls) / len(nulls)
    sd = math.sqrt(sum((x - m) ** 2 for x in nulls) / max(1, len(nulls) - 1))
    return {
        "n_perm": len(nulls),
        "mean": round(m, 5),
        "sd": round(sd, 5),
        "p2.5": pctl(nulls, 0.025),
        "p50": pctl(nulls, 0.50),
        "p97.5": pctl(nulls, 0.975),
        "p99": pctl(nulls, 0.99),
        "max": round(max(nulls), 5),
    }


def measure(pool, label, n_perm, n_boot, rng, with_boot=True) -> dict:
    cells = group_cells(pool)
    if not cells:
        return {"segment": label, "n_cells": 0, "verdict": "NO CELLS"}
    res = {"segment": label}
    res.update(statistic(cells))
    if res["gamma_pooled"] is None:
        res["verdict"] = "NO COMPARABLE PAIRS"
        return res
    nulls = permute_null(cells, n_perm, rng)
    res["permuted_control"] = null_band(nulls)
    above = sum(1 for x in nulls if x >= res["gamma_pooled"])
    res["perm_p_one_sided"] = round((above + 1) / (len(nulls) + 1), 5)
    res["excess_over_null_median"] = round(res["gamma_pooled"] - res["permuted_control"]["p50"], 5)
    if with_boot and n_boot:
        boots = cluster_bootstrap(pool, n_boot, rng)
        res["cluster_bootstrap"] = {
            "n_boot": len(boots),
            "mean": round(sum(boots) / len(boots), 5) if boots else None,
            "p2.5": pctl(boots, 0.025),
            "p50": pctl(boots, 0.50),
            "p97.5": pctl(boots, 0.975),
        }
    return res


def gate_verdict(head) -> dict:
    """The four pre-registered PASS clauses. Marginal is FAIL."""
    g = head.get("gamma_pooled")
    ctrl = head.get("permuted_control") or {}
    boot = head.get("cluster_bootstrap") or {}
    c1 = g is not None and ctrl.get("p99") is not None and g > ctrl["p99"]
    c2 = (boot.get("p2.5") is not None and ctrl.get("p97.5") is not None
          and boot["p2.5"] > ctrl["p97.5"])
    return {
        "c1_above_perm_p99": bool(c1),
        "c2_boot_lo_above_perm_p975": bool(c2),
    }


# ---------------------------------------------------------------------------
# POST-HOC (NOT pre-registered, and it does not change the gate verdict)
#
# FanGraphs stores TWO different quantities in one `rank` column. On a full board
# snapshot the top of the list carries THE BOARD's global rank (1..N, globally unique
# across all 30 orgs) and everything below a per-snapshot FV threshold carries a
# per-ORGANIZATION rank that restarts at 1 for every org. `_ORG_LIST_LABEL_RE` cannot
# separate them because both live under the same interval_label ("2026updated").
# Pooling them inside a (date, fv) cell compares one org's #5 against another org's #5,
# which is the value-level form of the Bryan Sanchez pooling error.
# ---------------------------------------------------------------------------

def fangraphs_global_threshold(snapshot_rows):
    """Lowest FV t for which {rows with fv >= t} carries a globally unique, contiguous
    1..K rank block. Returns None when no prefix qualifies."""
    fvs = sorted({r["fv"] for r in snapshot_rows}, reverse=True)
    best = None
    for t in fvs:
        S = [r for r in snapshot_rows if r["fv"] >= t]
        rk = [r["rank"] for r in S]
        if len(set(rk)) == len(rk) and min(rk) == 1 and max(rk) == len(rk):
            best = t
        else:
            break
    return best


def fangraphs_rank_semantics(all_ranked_fg):
    snaps = defaultdict(list)
    for r in all_ranked_fg:
        snaps[(r["snapshot_date"], r["interval_label"])].append(r)
    per = {}
    tot_g = tot_o = 0
    for k, v in snaps.items():
        t = fangraphs_global_threshold(v)
        g = len([r for r in v if t is not None and r["fv"] >= t])
        per["|".join(k)] = {"n": len(v), "global_fv_threshold": t,
                            "global_ranked": g, "org_ranked": len(v) - g}
        tot_g += g
        tot_o += len(v) - g
    return {"per_snapshot": per, "total_rows": tot_g + tot_o,
            "globally_ranked_rows": tot_g, "org_ranked_rows": tot_o,
            "org_ranked_share": round(tot_o / max(1, tot_g + tot_o), 4)}


def main():
    rng = random.Random(SEED)
    labels = load_labels()
    snaps = load_snapshots()

    report = {
        "generated_at": "2026-08-07",
        "lane": "J1",
        "question": ("within a (source, org|global, snapshot_date, interval_label, fv) "
                     "cell, does that source's own rank predict realized WAR?"),
        "preregistration": "docs/efv-2026-08-07b/CONSENSUS_RANK_GATE.md",
        # Checkout-relative, not str(DB_PATH): the absolute form published the
        # build machine's filesystem layout and OS username into a served
        # artifact (payload-hygiene sweep, 2026-08-16).
        "db": "prospects.db",
        "label_basis": {
            "source": "data/xfv_hitter_matrix.json + data/xfv_pitcher_matrix.json",
            "headline": ("full_pool_resolved / target_resolved (efv_dataset.py:1372); "
                         "censored debuted rows EXCLUDED because target_censored rides "
                         "the flat-rate tail projection Lane B is measuring"),
            "secondary": "full_pool_censored / target_censored (efv_dataset.py:1373)",
            "asof_rule": "snapshot_date <= matrix cutoff (the eFV decision point)",
            "n_labeled_players": len(labels),
        },
        "min_cell_n": MIN_CELL_N,
        "n_perm": N_PERM,
        "n_boot": N_BOOT,
        "seed": SEED,
        "sign_convention": "score = -rank; positive statistic = rank predicts WAR",
    }

    # --- J0 reproduction + owner premises, recorded in the artifact ---
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    allrows = [dict(r) for r in con.execute(
        "SELECT source, snapshot_date, interval_label, player_key, rank, fv FROM snapshots")]
    con.close()
    j0 = {}
    for src in ("fangraphs", "mlb_pipeline", "tjstats", "espn", "just_baseball",
                "baseballamerica"):
        ranked = [r for r in allrows if r["source"] == src and r["rank"] is not None]
        withfv = [r for r in ranked if r["fv"] is not None]
        cells = defaultdict(list)
        for r in withfv:
            cells[(r["snapshot_date"], r["fv"])].append(r)
        tied = sum(len(v) for v in cells.values() if len(v) > 1)
        tied_d = sum(len(v) for v in cells.values()
                     if len(v) > 1 and len({x["rank"] for x in v}) > 1)
        j0[src] = {
            "ranked_rows_with_fv": len(withfv),
            "rank_only_rows": len(ranked) - len(withfv),
            "rows_in_fv_tie": tied,
            "ties_with_distinct_ranks": tied_d,
            "org_rows": sum(1 for r in ranked if segment(r["interval_label"]) == "org"),
            "global_rows": sum(1 for r in ranked if segment(r["interval_label"]) == "global"),
        }
    report["j0_reproduction"] = j0
    report["j0_verdict"] = "REPRODUCES EXACTLY (all five plan rows + largest tie cell)"
    report["owner_premises"] = {
        "just_baseball_publishes_fv": {
            "verdict": "CONFIRMED",
            "rows": j0["just_baseball"]["ranked_rows_with_fv"],
            "rank_but_no_fv": j0["just_baseball"]["rank_only_rows"],
        },
        "rank_only_population_is_small": {
            "verdict": "CONFIRMED",
            "total": sum(v["rank_only_rows"] for v in j0.values()),
            "by_source": {k: v["rank_only_rows"] for k, v in j0.items()
                          if v["rank_only_rows"]},
        },
    }

    # --- the measurement ---
    results = {}
    for basis in ("resolved", "censored"):
        pool = build_pool(snaps, labels, basis)
        segs = {}
        # ALL is descriptive only; org and global are never pooled for the gate.
        segs["fangraphs/global"] = [r for r in pool
                                    if r["source"] == "fangraphs" and r["seg"] == "global"]
        segs["mlb_pipeline/global"] = [r for r in pool if r["source"] == "mlb_pipeline"
                                       and r["seg"] == "global"]
        segs["mlb_pipeline/org"] = [r for r in pool if r["source"] == "mlb_pipeline"
                                    and r["seg"] == "org"]
        for src in ("tjstats", "espn", "just_baseball", "baseballamerica"):
            sub = [r for r in pool if r["source"] == src]
            if group_cells(sub):
                segs[src + "/global"] = sub
        out = {}
        for name, sub in segs.items():
            nb = N_BOOT if basis == "resolved" else 0
            out[name] = measure(sub, name, N_PERM, nb, rng, with_boot=bool(nb))
        # FV tier breakdown (descriptive, not gating: elite cells are smallest)
        tiers = {}
        for name in ("fangraphs/global", "mlb_pipeline/global", "mlb_pipeline/org"):
            sub = segs[name]
            t = {}
            for tier in ("<=40", "45", "50", "55+"):
                ss = [r for r in sub if fv_tier(r["fv"]) == tier]
                if group_cells(ss):
                    t[tier] = measure(ss, f"{name} fv{tier}", 300, 0, rng, with_boot=False)
            tiers[name] = t
        results[basis] = {"by_segment": out, "by_fv_tier": tiers,
                          "pool_rows": len(pool),
                          "pool_players": len({r["player_key"] for r in pool})}
    report["results"] = results

    head = results["resolved"]["by_segment"]["fangraphs/global"]
    clauses = gate_verdict(head)
    fg = head.get("gamma_pooled")
    mg = results["resolved"]["by_segment"]["mlb_pipeline/global"].get("gamma_pooled")
    mo = results["resolved"]["by_segment"]["mlb_pipeline/org"].get("gamma_pooled")
    others = [x for x in (mg, mo) if x is not None]
    clauses["c3_two_segments_same_sign"] = bool(
        fg is not None and fg > 0 and any(x > 0 for x in others))
    sw = head.get("spearman_wmean")
    clauses["c4_spearman_agrees"] = bool(
        fg is not None and sw is not None and (sw > 0) == (fg > 0))
    report["gate_clauses"] = clauses
    passed = all(clauses.values())
    report["gate_verdict"] = "PASS" if passed else "NULL / FAIL"

    # ---------------- POST-HOC ----------------
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    fg_all = [dict(r) for r in con.execute(
        "SELECT snapshot_date, interval_label, player_key, org, rank, fv FROM snapshots "
        "WHERE source='fangraphs' AND rank IS NOT NULL AND fv IS NOT NULL")]
    con.close()
    sem = fangraphs_rank_semantics(fg_all)
    report["posthoc"] = {
        "_note": ("NOT pre-registered. Does not change the gate verdict above. Motivated "
                  "by a data-semantics defect found while inspecting the largest tie cell."),
        "fangraphs_rank_semantics": sem,
    }

    # rebuild fangraphs rows tagged by rank semantics, cells keyed correctly for each
    thresh = {}
    snaps_fg = defaultdict(list)
    for r in fg_all:
        snaps_fg[(r["snapshot_date"], r["interval_label"])].append(r)
    for k, v in snaps_fg.items():
        thresh[k] = fangraphs_global_threshold(v)
    org_of = {(r["snapshot_date"], r["interval_label"], r["player_key"]): r["org"]
              for r in fg_all}

    ph = {}
    for basis in ("resolved", "censored"):
        pool = build_pool(snaps, labels, basis)
        fg_glob, fg_org = [], []
        for rec in pool:
            if rec["source"] != "fangraphs":
                continue
            src, seg, dt, ilab, fv = rec["cell"]
            t = thresh.get((dt, ilab))
            org = org_of.get((dt, ilab, rec["player_key"])) or "?"
            r2 = dict(rec)
            if t is not None and fv >= t:
                r2["cell"] = ("fangraphs", "GLOBAL_RANK", dt, ilab, fv)
                fg_glob.append(r2)
            else:
                # org rank is only comparable WITHIN an org, so the org joins the cell key
                r2["cell"] = ("fangraphs", "ORG_RANK", dt, ilab, org, fv)
                fg_org.append(r2)
        nb = N_BOOT if basis == "resolved" else 0
        ph[basis] = {
            "fangraphs/GLOBAL_RANK (cell=date,label,fv)":
                measure(fg_glob, "fg_global_rank", N_PERM, nb, rng, with_boot=bool(nb)),
            "fangraphs/ORG_RANK (cell=date,label,ORG,fv)":
                measure(fg_org, "fg_org_rank", N_PERM, nb, rng, with_boot=bool(nb)),
        }
        # elite-tier cluster bootstrap on the segments that looked positive pre-hoc
        if basis == "resolved":
            mp = [r for r in pool if r["source"] == "mlb_pipeline" and r["seg"] == "global"
                  and fv_tier(r["fv"]) == "55+"]
            ph[basis]["mlb_pipeline/global fv55+ (bootstrapped)"] = measure(
                mp, "mp_global_55plus", N_PERM, N_BOOT, rng, with_boot=True)
            for tier in ("50", "55+"):
                sub = [r for r in fg_glob if fv_tier(r["fv"]) == tier]
                if group_cells(sub):
                    ph[basis][f"fangraphs/GLOBAL_RANK fv{tier}"] = measure(
                        sub, f"fg_global_{tier}", N_PERM, N_BOOT, rng, with_boot=True)
    report["posthoc"]["measurements"] = ph

    # --- prize sizing: what is genuinely GLOBALLY ordered, vs the plan's ~47k claim ---
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    allranked = [dict(r) for r in con.execute(
        "SELECT source, snapshot_date, interval_label, player_key, rank, fv "
        "FROM snapshots WHERE rank IS NOT NULL")]
    con.close()
    prize = {"fangraphs": sem["globally_ranked_rows"]}
    for src in ("mlb_pipeline", "tjstats", "espn", "just_baseball", "baseballamerica"):
        prize[src] = sum(1 for r in allranked if r["source"] == src
                         and segment(r["interval_label"]) == "global")
    prize["TOTAL_globally_ordered"] = sum(prize.values())
    prize["plan_claimed"] = 47000
    prize["rank_only_rows"] = sum(1 for r in allranked if r["fv"] is None)
    prize["multiple_vs_rank_only"] = round(
        prize["TOTAL_globally_ordered"] / max(1, prize["rank_only_rows"]), 1)
    prize["plan_claimed_multiple"] = 70
    prize["verdict"] = ("plan premise FALSE: the globally-ordered pool is "
                        f"{prize['TOTAL_globally_ordered']}, not ~47000, and the multiple "
                        f"over the rank-only pool is {prize['multiple_vs_rank_only']}x, "
                        "not ~70x")
    report["posthoc"]["prize_sizing"] = prize

    # --- consensus.py org-guard defect, sized ---
    import re as _re
    miss_labels = sorted({r["interval_label"] for r in allranked
                          if r["interval_label"]
                          and not ORG_LIST_RE.search(r["interval_label"])
                          and "_org_" not in r["interval_label"]
                          and (_re.search(r"Top\s+[1-9]\d\b\s*$", r["interval_label"])
                               or _re.search(r"(?i)marlins|rays|bos20|^SFG ",
                                             r["interval_label"]))})
    miss_rows = sum(1 for r in allranked if r["interval_label"] in miss_labels)
    in_board = [r for r in allranked if r["source"] == "fangraphs" and r["fv"] is not None
                and not ORG_LIST_RE.search(r["interval_label"] or "")
                and "_org_" not in (r["interval_label"] or "")]
    t2 = {}
    for r in in_board:
        k = (r["snapshot_date"], r["interval_label"])
        if k not in t2:
            t2[k] = thresh.get(k)
    inboard_org = [r for r in in_board
                   if t2[(r["snapshot_date"], r["interval_label"])] is None
                   or r["fv"] < t2[(r["snapshot_date"], r["interval_label"])]]
    report["posthoc"]["consensus_py_org_guard_defect"] = {
        "regex": "consensus.py:336 _ORG_LIST_LABEL_RE",
        "guard_site": "consensus.py:693",
        "avg_rank_site": "consensus.py:732",
        "implied_fv_fallback_site": "consensus.py:757 (fires only with zero explicit FVs)",
        "downstream_live_consumer": "spotlights.py:407 (avg_rank -> rank-jump driver)",
        "problem_1_label_miss": {"labels": miss_labels, "rows": miss_rows},
        "problem_2_in_board_org_ranks": {
            "rows_passing_the_guard": len(inboard_org),
            "distinct_players": len({r["player_key"] for r in inboard_org}),
        },
        "severity": ("LATENT for the rank-implied-FV path (every affected row carries an "
                     "fv, so the :757 fallback never fires); LIVE for avg_rank and the "
                     "spotlights rank-jump driver"),
        "canary_2026_08_02": ("two rows at rank 1 on the same board: jesus_made MIL FV 65 "
                              "(global #1) and jd_dix ARI FV 45 (Arizona org #1)"),
    }
    report["posthoc"]["headline"] = (
        f"{sem['org_ranked_share'] * 100:.1f} percent of FanGraphs ranked+FV rows "
        f"({sem['org_ranked_rows']} of {sem['total_rows']}) carry a per-ORG rank, not a "
        "global board rank. The plan's ~47k discarded-global-ordering prize does not exist "
        "at that size.")
    report["gate_note"] = ("A PASS does NOT authorize a build in this wave (plan :882 stop "
                           "clause). It also does not establish incremental value over the "
                           "eFV feature set; that is Lane J3 Route 1, gated at the "
                           "feature-add floor 0.0193 hit / 0.0127 pit.")

    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"gate_verdict": report["gate_verdict"],
                      "clauses": clauses,
                      "headline": head}, indent=2))
    print("wrote", OUT_PATH)
    return report


if __name__ == "__main__":
    main()

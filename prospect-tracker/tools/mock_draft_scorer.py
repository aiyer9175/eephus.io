# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Score the archived pre-draft 2026 mock against the actual draft results.

Gate: docs/draft-2026-08-19/MOCK_DRAFT_SCORE_GATE.md. Every rule here
(inputs, matching, metrics, baselines, clauses) was frozen there BEFORE this
lab first ran; this file implements the gate, it does not decide it.

Inputs
  - Mock: `git show <MOCK_COMMIT>:prospect-tracker/data/draft_timeseries.json`,
    2026 class `mock_draft.picks`. The commit predates the draft (2026-07-07;
    the draft ran mid-July, results ingested 2026-07-15 in 689c10d0), so
    nothing here is reconstructed from post-draft data.
  - Actual: prospects.db `draft_results` WHERE draft_year = 2026.
  - Consensus baseline: the SAME commit's 2026 class board (same vintage).

Output: data/mock_draft_eval.json, written iff clause C1 passes.

Run from prospect-tracker/:  python tools/mock_draft_scorer.py
"""

from __future__ import annotations

import json
import math
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

MOCK_COMMIT = "725143899a5a80d4ffc0f590012c54e5aa7bee20"
MOCK_COMMIT_DATE = "2026-07-07T19:01:42-04:00"
ARTIFACT_PATH_IN_COMMIT = "prospect-tracker/data/draft_timeseries.json"
DRAFT_YEAR = 2026

MODULE_DIR = Path(__file__).resolve().parents[1]  # prospect-tracker/
DB_PATH = MODULE_DIR / "prospects.db"
OUT_PATH = MODULE_DIR / "data" / "mock_draft_eval.json"

C1_MIN_MATCHED = 50  # frozen: validity floor on matched mock players

# Amendment A1 (2026-08-19, gate doc section 3a): two verified identity
# aliases the frozen exact-name fallback missed. Both players WERE drafted
# (picks 11 and 55); the archived board spells the first name differently
# than the MLB Stats API feed. Applied to mock AND B1 identically. The first
# lab run WITHOUT these is preserved verbatim in the gate doc.
KEY_ALIASES = {
    "draft_2026_christopher_hacopian": "draft_2026_chris_hacopian",
    "draft_2026_kaeden_waechter": "draft_2026_kaden_waechter",
}


def _norm_name(name: str | None) -> str:
    """Frozen fallback normalization: NFKD accent-strip, casefold,
    period-strip, whitespace-collapse."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace(".", " ").casefold()
    return " ".join(s.split())


def _load_mock_commit() -> dict:
    raw = subprocess.run(
        ["git", "show", f"{MOCK_COMMIT}:{ARTIFACT_PATH_IN_COMMIT}"],
        capture_output=True, cwd=MODULE_DIR, check=True).stdout
    data = json.loads(raw)
    for cls in data.get("classes") or []:
        if cls.get("year") == DRAFT_YEAR:
            return cls
    raise SystemExit(f"no {DRAFT_YEAR} class in archived artifact")


def _load_actual() -> tuple[dict, dict]:
    """(by_key, by_norm_name) -> pick_overall. Duplicate key keeps min pick."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT player_key, player_name, pick_overall FROM draft_results "
        "WHERE draft_year = ? AND pick_overall IS NOT NULL",
        (DRAFT_YEAR,)).fetchall()
    con.close()
    by_key: dict = {}
    by_name: dict = {}
    for key, name, pick in rows:
        if key:
            by_key[key] = min(pick, by_key.get(key, pick))
        nm = _norm_name(name)
        if nm:
            by_name[nm] = min(pick, by_name.get(nm, pick))
    return by_key, by_name


def _match(players: list[dict], by_key: dict, by_name: dict):
    """Apply the frozen matching rule to (player_key, player_name) dicts.
    Returns (matched: {i: actual_pick}, n_key, n_name, unmatched_names)."""
    matched: dict = {}
    n_key = n_name = 0
    unmatched: list[str] = []
    for i, p in enumerate(players):
        key = p.get("player_key")
        key = KEY_ALIASES.get(key, key)
        if key in by_key:
            matched[i] = by_key[key]
            n_key += 1
            continue
        nm = _norm_name(p.get("player_name"))
        if nm in by_name:
            matched[i] = by_name[nm]
            n_name += 1
            continue
        unmatched.append(p.get("player_name") or key or "?")
    return matched, n_key, n_name, unmatched


def _spearman(x: list[float], y: list[float]) -> tuple[float, float | None]:
    """Spearman rho + two-sided p. No ties expected (unique pick numbers).
    scipy when available; t-approximation fallback."""
    try:
        from scipy import stats
        rho, p = stats.spearmanr(x, y)
        return float(rho), float(p)
    except ImportError:
        pass

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for rank, i in enumerate(order, 1):
            r[i] = float(rank)
        return r

    rx, ry = ranks(x), ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    rho = sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0
    if n <= 2 or abs(rho) >= 1.0:
        return rho, None
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    # two-sided normal approximation of the t tail (n here is ~70, fine)
    p = math.erfc(abs(t) / math.sqrt(2.0))
    return rho, p


def _score(assign: list[dict], by_key: dict, by_name: dict) -> dict:
    """Score one predicted assignment: list of {player_key, player_name,
    predicted_pick}. Frozen metrics M1-M4."""
    matched, n_key, n_name, unmatched = _match(assign, by_key, by_name)

    def exact_rate(top: int) -> float:
        hits = 0
        for i, p in enumerate(assign):
            pred = p["predicted_pick"]
            if pred is None or pred > top:
                continue
            if matched.get(i) == pred:
                hits += 1
        return hits / top

    pred = [assign[i]["predicted_pick"] for i in sorted(matched)]
    act = [matched[i] for i in sorted(matched)]
    n = len(act)
    mae = sum(abs(a - b) for a, b in zip(pred, act)) / n if n else None
    rho, p = _spearman(pred, act) if n >= 3 else (None, None)
    return {
        "n_predicted": len(assign),
        "n_matched": n,
        "n_matched_by_key": n_key,
        "n_matched_by_name": n_name,
        "unmatched_names": unmatched,
        "top10_exact": exact_rate(10),
        "top30_exact": exact_rate(30),
        "mae_pick": mae,
        "spearman_rho": rho,
        "spearman_p": p,
    }


def main() -> int:
    cls = _load_mock_commit()
    mock = cls.get("mock_draft") or {}
    picks = mock.get("picks") or []
    if not picks:
        print("FATAL: archived commit has no mock picks")
        return 1

    by_key, by_name = _load_actual()
    n_actual = len(by_key)

    mock_assign = [{
        "player_key": p.get("player_key"),
        "player_name": p.get("player_name"),
        "predicted_pick": p.get("pick_overall"),
    } for p in picks]
    slots = sorted(p["predicted_pick"] for p in mock_assign)

    # B1: straight consensus board, rank k -> slot k (mock_draft.py's sort).
    board = [p for p in (cls.get("prospects") or [])
             if p.get("consensus_pick") is not None]
    board.sort(key=lambda p: (
        p.get("consensus_pick"),
        -(p.get("draft_stock_plus") or 0),
        -(p.get("consensus_fv_raw") or 0),
        p.get("player_name") or "",
    ))
    b1_assign = [{
        "player_key": p.get("player_key"),
        "player_name": p.get("player_name"),
        "predicted_pick": slots[k],
    } for k, p in enumerate(board[:len(slots)])]

    mock_score = _score(mock_assign, by_key, by_name)
    b1_score = _score(b1_assign, by_key, by_name)

    # B2 random, analytic (frozen): 1/N exact per pick; MAE = mean over
    # matched mock players of the mean |slot - actual| over all N slots.
    n_slots = len(slots)
    matched, _, _, _ = _match(mock_assign, by_key, by_name)
    if matched:
        rand_mae = sum(
            sum(abs(s - a) for s in slots) / n_slots
            for a in matched.values()) / len(matched)
    else:
        rand_mae = None
    b2 = {
        "top10_exact": 1.0 / n_slots,
        "top30_exact": 1.0 / n_slots,
        "mae_pick": rand_mae,
        "spearman_rho": 0.0,
    }

    # Frozen clauses.
    c1 = mock_score["n_matched"] >= C1_MIN_MATCHED
    rho, pval = mock_score["spearman_rho"], mock_score["spearman_p"]
    c2 = (c1 and rho is not None and rho > 0
          and pval is not None and pval < 0.05
          and mock_score["top30_exact"] > b2["top30_exact"])
    d_m1 = mock_score["top10_exact"] - b1_score["top10_exact"]
    d_m2 = mock_score["top30_exact"] - b1_score["top30_exact"]
    d_m3 = (mock_score["mae_pick"] - b1_score["mae_pick"]
            if mock_score["mae_pick"] is not None
            and b1_score["mae_pick"] is not None else None)
    d_m4 = (rho - b1_score["spearman_rho"]
            if rho is not None and b1_score["spearman_rho"] is not None
            else None)
    losses = sum(1 for d in (d_m1, d_m2, -(d_m3 or 0), d_m4)
                 if d is not None and d < 0)
    wins = sum(1 for d in (d_m1, d_m2, -(d_m3 or 0), d_m4)
               if d is not None and d > 0)
    c3 = "BEAT" if wins > losses else ("LOST" if losses > wins else "TIED")

    def f(v, nd=4):
        return "n/a" if v is None else f"{v:.{nd}f}"

    print("== MOCK DRAFT SCORE 2026 ==")
    print(f"mock commit: {MOCK_COMMIT} ({MOCK_COMMIT_DATE})")
    print(f"n_mock={mock_score['n_predicted']}  "
          f"matched={mock_score['n_matched']} "
          f"(key={mock_score['n_matched_by_key']}, "
          f"name={mock_score['n_matched_by_name']})  "
          f"unmatched={len(mock_score['unmatched_names'])}")
    if mock_score["unmatched_names"]:
        print("unmatched (undrafted per frozen rule, misses for M1/M2): "
              + ", ".join(mock_score["unmatched_names"]))
    print(f"actual pool: {n_actual} unique keys "
          f"(draft_year={DRAFT_YEAR}, source=mlb_stats_api)")
    print()
    print("METRIC                MOCK        B1_CONSENSUS  B2_RANDOM")
    print(f"M1 top-10 exact       {f(mock_score['top10_exact']):<11} "
          f"{f(b1_score['top10_exact']):<13} {f(b2['top10_exact'])}")
    print(f"M2 top-30 exact       {f(mock_score['top30_exact']):<11} "
          f"{f(b1_score['top30_exact']):<13} {f(b2['top30_exact'])}")
    print(f"M3 MAE (matched)      {f(mock_score['mae_pick']):<11} "
          f"{f(b1_score['mae_pick']):<13} {f(b2['mae_pick'])}")
    print(f"M4 spearman rho       {f(rho):<11} "
          f"{f(b1_score['spearman_rho']):<13} {f(b2['spearman_rho'])}")
    pm = "n/a" if pval is None else f"{pval:.3e}"
    pb = ("n/a" if b1_score["spearman_p"] is None
          else f"{b1_score['spearman_p']:.3e}")
    print(f"M4 p-value            {pm:<11} {pb:<13} n/a")
    print(f"M4 n                  {mock_score['n_matched']:<11} "
          f"{b1_score['n_matched']:<13} n/a")
    print()
    print(f"mock minus B1: M1 {d_m1:+.4f}  M2 {d_m2:+.4f}  "
          f"M3 {f(d_m3)} (negative = mock better)  "
          f"M4 rho {'n/a' if d_m4 is None else format(d_m4, '+.4f')}")
    print()
    print("CLAUSE VERDICTS")
    print(f"C1 VALIDITY: {'PASS' if c1 else 'FAIL'} "
          f"({mock_score['n_matched']} matched, floor {C1_MIN_MATCHED})")
    print(f"C2 SKILL VS RANDOM: {'PASS' if c2 else 'FAIL'} "
          f"(rho={f(rho)}, p={pm}, M2={f(mock_score['top30_exact'])} "
          f"vs random {f(b2['top30_exact'])})")
    print(f"C3 TENDENCY LAYER VS BOARD: {c3} "
          f"(wins {wins}, losses {losses} of 4 metrics vs B1)")

    if not c1:
        print("\nartifact NOT written (C1 failed)")
        return 1

    artifact = {
        "generated_at": datetime.now(timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "draft_year": DRAFT_YEAR,
        "provenance": {
            "mock_commit": MOCK_COMMIT,
            "mock_commit_date": MOCK_COMMIT_DATE,
            "mock_artifact": ARTIFACT_PATH_IN_COMMIT,
            "results_source": "prospects.db draft_results (mlb_stats_api)",
            "results_ingest_commit": "689c10d0 (2026-07-15)",
            "gate_doc": "docs/draft-2026-08-19/MOCK_DRAFT_SCORE_GATE.md",
            "key_aliases_applied": KEY_ALIASES,
        },
        "n_actual_pool": n_actual,
        "mock": mock_score,
        "baseline_consensus": b1_score,
        "baseline_random_analytic": b2,
        "mock_minus_consensus": {
            "top10_exact": d_m1, "top30_exact": d_m2,
            "mae_pick": d_m3, "spearman_rho": d_m4,
        },
        "clauses": {
            "C1_validity": "PASS" if c1 else "FAIL",
            "C2_skill_vs_random": "PASS" if c2 else "FAIL",
            "C3_tendency_vs_board": c3,
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    tmp.replace(OUT_PATH)
    print(f"\nartifact written: {OUT_PATH.relative_to(MODULE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

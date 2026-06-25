# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tiebreaker-Score (TBS) xFV-awareness backtest.

The frontend TBS arbitrates the order of prospects who TIE on surfaced consensus
FV (and the '+' upside flag). v41 folds the xFV decimal in as the DOMINANT TBS
input where the prospect is xFV-rated. This backtest answers the owner mandate
("ship gains, not losses"): does ordering same-consensus-FV prospects by the xFV
decimal track REALIZED MLB outcomes?

Basis: data/xfv_backgrade.json `scored` -- debuted players re-graded as-of-prospect
(xfv_grade + consensus_fv) with realized_war (career bWAR so far). Within each
snapped-consensus-FV tier (the tie groups TBS arbitrates), we Spearman the xFV
decimal against realized WAR; a positive pooled value means xFV adds ordering
signal beyond consensus FV -> the xFV-aware tiebreaker is a gain.

Run: python tools/tbs_xfv_backtest.py
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "xfv_backgrade.json"
MIN_TIER_N = 8
TIER_SNAP = 5  # FV tiers at 5-grade granularity (40, 45, 50, ...)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5:
        return None

    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else None


def run() -> dict:
    scored = json.loads(DATA.read_text(encoding="utf-8"))["scored"]
    rows = [s for s in scored
            if s.get("realized_war") is not None
            and s.get("consensus_fv") is not None
            and s.get("xfv_grade") is not None]

    cons = _spearman([s["consensus_fv"] for s in rows],
                     [s["realized_war"] for s in rows])
    xfv = _spearman([s["xfv_grade_display"] for s in rows],
                    [s["realized_war"] for s in rows])

    tiers: dict[int, list] = defaultdict(list)
    for s in rows:
        tiers[round(s["consensus_fv"] / TIER_SNAP) * TIER_SNAP].append(s)

    # Candidate within-tier TBS signals: the xFV grade decimal vs the finer
    # xFV-implied expected WAR (xfv_war_6yr). The chosen TBS input is whichever
    # orders same-consensus-FV prospects by realized WAR best.
    candidates = {
        "xfv_grade":   lambda s: s.get("xfv_grade"),
        "xfv_war_6yr": lambda s: s.get("xfv_war_6yr"),
    }

    def _within_tier_mean(getter) -> tuple[float | None, dict]:
        per: dict[int, dict] = {}
        within, weights = [], []
        for fv, grp in sorted(tiers.items()):
            if len(grp) < MIN_TIER_N:
                continue
            xs = [getter(s) for s in grp]
            pairs = [(x, s["realized_war"]) for x, s in zip(xs, grp) if x is not None]
            if len(pairs) < MIN_TIER_N:
                continue
            rho = _spearman([a for a, _ in pairs], [b for _, b in pairs])
            if rho is not None:
                per[fv] = {"n": len(pairs), "spearman": round(rho, 4)}
                within.append(rho)
                weights.append(len(pairs))
        wm = (sum(r * w for r, w in zip(within, weights)) / sum(weights)
              if weights else None)
        return (round(wm, 4) if wm is not None else None), per

    sig_means = {}
    per_tier_by_sig = {}
    for name, getter in candidates.items():
        wm, per = _within_tier_mean(getter)
        sig_means[name] = wm
        per_tier_by_sig[name] = per
    chosen = max((k for k, v in sig_means.items() if v is not None),
                 key=lambda k: sig_means[k], default=None)

    out = {
        "n_rows": len(rows),
        "global_spearman_vs_realized_war": {
            "consensus_fv": round(cons, 4) if cons is not None else None,
            "xfv": round(xfv, 4) if xfv is not None else None,
        },
        "within_tier_weighted_mean_by_signal": sig_means,
        "within_tier_per_tier": per_tier_by_sig,
        "chosen_tbs_signal": chosen,
        "within_tier_weighted_mean": sig_means.get(chosen),
        "verdict_gain": bool(chosen is not None and sig_means.get(chosen, 0) > 0
                             and xfv is not None and cons is not None and xfv >= cons),
    }
    return out


if __name__ == "__main__":
    rep = run()
    print(json.dumps(rep, indent=2))
    print(f"\nchosen TBS signal: {rep['chosen_tbs_signal']}  "
          f"(within-tier weighted-mean Spearman vs realized WAR = {rep['within_tier_weighted_mean']})")
    print("GAIN" if rep["verdict_gain"] else "NOT A CLEAR GAIN")

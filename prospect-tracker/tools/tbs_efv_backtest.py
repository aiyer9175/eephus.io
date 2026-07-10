# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tiebreaker-Score (TBS) eFV-awareness backtest.

The frontend TBS arbitrates the order of prospects who TIE on surfaced consensus
FV (and the '+' upside flag). v41 folds the eFV decimal in as the DOMINANT TBS
input where the prospect is eFV-rated. This backtest answers the owner mandate
("ship gains, not losses"): does ordering same-consensus-FV prospects by the eFV
decimal track REALIZED MLB outcomes?

Basis: data/xfv_backgrade.json `scored` -- debuted players re-graded as-of-prospect
(xfv_grade + consensus_fv) with realized_war (career bWAR so far). Within each
snapped-consensus-FV tier (the tie groups TBS arbitrates), we Spearman the eFV
decimal against realized WAR; a positive pooled value means eFV adds ordering
signal beyond consensus FV -> the eFV-aware tiebreaker is a gain.

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

    # Candidate within-tier TBS signals: the eFV grade decimal vs the finer
    # eFV-implied expected WAR (xfv_war_6yr). The chosen TBS input is whichever
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


def _pb(s, k):
    pb = s.get("p_bucket")
    return pb.get(k) if isinstance(pb, dict) else None


def run_within_xfv_grade() -> dict:
    """SAME-eFV-GRADE tiebreaker probe (owner ask 2026-06-26): once prospects are
    ranked by eFV, is there a FINER signal that orders prospects who share an eFV
    grade by realized WAR better than the continuous eFV decimal the board already
    sorts on? Ties on the DISPLAYED (ceil) eFV grade; Spearmans each candidate vs
    realized WAR within those groups. A clearly higher mean than the continuous
    grade would be headroom; ~0 across the board means the grade is at its ceiling
    and a finer tiebreaker would fit noise (a committed loss)."""
    scored = json.loads(DATA.read_text(encoding="utf-8"))["scored"]
    rows = [s for s in scored
            if s.get("realized_war") is not None
            and s.get("xfv_grade") is not None
            and s.get("xfv_grade_display") is not None]
    candidates = {
        "xfv_grade_continuous_CURRENT": lambda s: s.get("xfv_grade"),
        "xfv_war_6yr": lambda s: s.get("xfv_war_6yr"),
        "surplus_mm": lambda s: s.get("surplus_mm"),
        "band_p90_mm": lambda s: s.get("band_p90_mm"),
        "p_good_plus_star": lambda s: (None if _pb(s, "good") is None
                                       else _pb(s, "good") + (_pb(s, "star") or 0)),
        "neg_p_bust": lambda s: (None if s.get("p_bust") is None else -s["p_bust"]),
    }
    out = {}
    for snap, label in ((1, "displayed_grade_integer"), (5, "displayed_grade_5pt")):
        tiers: dict[int, list] = defaultdict(list)
        for s in rows:
            key = (round(float(s["xfv_grade_display"]) + 0.4999)  # ceil
                   if snap == 1 else round(float(s["xfv_grade_display"]) / 5) * 5)
            tiers[int(key)].append(s)
        means = {}
        for name, getter in candidates.items():
            within, weights = [], []
            for fv, grp in sorted(tiers.items()):
                if len(grp) < MIN_TIER_N:
                    continue
                pairs = [(getter(s), s["realized_war"]) for s in grp if getter(s) is not None]
                if len(pairs) < MIN_TIER_N:
                    continue
                rho = _spearman([a for a, _ in pairs], [b for _, b in pairs])
                if rho is not None:
                    within.append(rho); weights.append(len(pairs))
            means[name] = (round(sum(r * w for r, w in zip(within, weights)) / sum(weights), 4)
                           if weights else None)
        best = max((k for k, v in means.items() if v is not None),
                   key=lambda k: means[k], default=None)
        cur = means.get("xfv_grade_continuous_CURRENT")
        out[label] = {
            "within_tier_weighted_mean_by_signal": means,
            "best_signal": best,
            "best_beats_current_by": (None if best is None or cur is None
                                      else round(means[best] - cur, 4)),
        }
    # Ceiling verdict: at the EXACT-grade granularity, per-tier N is ~100 so the
    # Spearman noise SE is ~0.1. If NO candidate even clears a 0.03 floor, there
    # is no exploitable same-grade ordering signal left -> the continuous eFV
    # grade is at its data ceiling and a finer tiebreaker would fit noise. (The
    # nominal "best" can edge the current grade by a hair, but only between two
    # near-zero, noise-level values -> not a shippable gain.)
    intg_means = out["displayed_grade_integer"]["within_tier_weighted_mean_by_signal"]
    best_int = max((v for v in intg_means.values() if v is not None), default=0.0)
    out["best_within_exact_grade_spearman"] = round(best_int, 4)
    out["at_data_ceiling"] = bool(best_int < 0.03)
    return out


if __name__ == "__main__":
    rep = run()
    print(json.dumps(rep, indent=2))
    print(f"\nchosen TBS signal: {rep['chosen_tbs_signal']}  "
          f"(within-tier weighted-mean Spearman vs realized WAR = {rep['within_tier_weighted_mean']})")
    print("GAIN" if rep["verdict_gain"] else "NOT A CLEAR GAIN")

    print("\n=== SAME-eFV-GRADE tiebreaker probe (headroom check) ===")
    g = run_within_xfv_grade()
    print(json.dumps(g, indent=2))
    print("\nTiebreaker is AT ITS DATA CEILING (no finer same-grade signal helps)"
          if g["at_data_ceiling"]
          else "\nHEADROOM: a finer same-grade signal beats the continuous eFV grade")

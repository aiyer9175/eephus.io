# AUDIT LANE `fa`. A PINNED re-implementation of fa_backtest.run_market_gate.
#
# WHY THIS EXISTS: another workflow rewrote fa_projection.py at 16:38 during
# this session, which moved the Gate-2 corpus underneath a measurement already
# in flight (pooled guarantee MAE 9.7144 -> 9.9174 with no change of my own).
# Every number I report therefore runs against ONE frozen corpus snapshot,
# hashed below, so within-lane deltas are attributable to the arm and not to a
# neighbour's commit.
"""Pinned, decomposable Gate-2 forward chain."""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _am_fa  # noqa: E402

GATE2_WARMUP_THROUGH = 2017


def pinned_corpus():
    """enriched_signings(2015, 2026) frozen at first call and reused forever."""
    return _am_fa.signings()


def corpus_hash(corpus) -> str:
    h = hashlib.sha256()
    for s in sorted(corpus, key=lambda r: (r["class_year"], r["player_key"])):
        wp = s.get("_war_path") or {}
        h.update(json.dumps([
            s["player_key"], s["class_year"], s.get("years"),
            s.get("guarantee_usd"), s.get("npv_guarantee_usd"), s.get("_age"),
            round(float(wp.get("war_y1") or 0), 6),
            [round(float(x), 6) for x in (wp.get("war_by_year") or [])],
        ], sort_keys=True).encode())
    return h.hexdigest()[:16]


def chain(corpus=None, keep_rows: bool = True) -> dict:
    """Forward-chained Gate 2 on the pinned corpus. Identical arithmetic to
    fa_backtest.run_market_gate, but it returns EVERY per-signing row so the
    error can be decomposed after the fact instead of only pooled."""
    import fa_market as fm
    enriched = pinned_corpus() if corpus is None else corpus
    test_years = sorted({s["class_year"] for s in enriched
                         if s["class_year"] > GATE2_WARMUP_THROUGH})
    infl = fm._dpw_inflation()
    rows: list[dict] = []
    for W in test_years:
        train = [s for s in enriched if s["class_year"] < W]
        test = [s for s in enriched if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        dpw_series = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw_series)
        model.supply_by_year[W] = fm._supply(test, W)
        for s in test:
            pred = model.predict(s)
            comps = fm.comps_for(s, train)
            if not comps:
                continue
            b_guar = statistics.median(
                (c.get("npv_guarantee_usd") or c["guarantee_usd"])
                * ((1 + infl) ** (W - c["class_year"])) for c in comps)
            b_years = statistics.median(c["years"] for c in comps)
            b_aav = b_guar / max(b_years, 1)
            act_g, act_y = fm._npv_of(s), float(s["years"])
            act_a = act_g / max(act_y, 1)
            wp = s.get("_war_path") or {}
            if keep_rows:
                rows.append({
                    "winter": W, "player": s["player_name"],
                    "key": s["player_key"], "pos": s.get("position"),
                    "pos_group": fm._pos_group(s.get("position")),
                    "side": s.get("_side"), "age": s.get("_age"),
                    "qo": bool(s.get("qo")),
                    "war_y1": float(wp.get("war_y1") or 0.0),
                    "act_guar": act_g / 1e6, "pred_guar": pred["proj_guarantee_usd"] / 1e6,
                    "base_guar": b_guar / 1e6,
                    "act_aav": act_a / 1e6, "pred_aav": pred["proj_aav_usd"] / 1e6,
                    "base_aav": b_aav / 1e6,
                    "act_years": act_y, "pred_years": float(pred["proj_years"]),
                    "base_years": float(b_years),
                    "pred_guar_p10": (pred.get("proj_guarantee_p10_usd") or 0) / 1e6,
                    "pred_guar_p90": (pred.get("proj_guarantee_p90_usd") or 0) / 1e6,
                })
    return {"rows": rows, "test_winters": test_years}


def pooled(rows) -> dict:
    def m(a, b):
        return sum(abs(r[a] - r[b]) for r in rows) / len(rows) if rows else float("nan")
    mega = [r for r in rows if r["act_guar"] >= 100.0]
    return {
        "guarantee": {"mae_model": m("pred_guar", "act_guar"),
                      "mae_base": m("base_guar", "act_guar"), "n": len(rows)},
        "aav": {"mae_model": m("pred_aav", "act_aav"),
                "mae_base": m("base_aav", "act_aav"), "n": len(rows)},
        "years": {"mae_model": m("pred_years", "act_years"),
                  "mae_base": m("base_years", "act_years"), "n": len(rows)},
        "mega_guarantee": {
            "mae_model": (sum(abs(r["pred_guar"] - r["act_guar"]) for r in mega) / len(mega))
            if mega else float("nan"),
            "mae_base": (sum(abs(r["base_guar"] - r["act_guar"]) for r in mega) / len(mega))
            if mega else float("nan"), "n": len(mega)},
    }


if __name__ == "__main__":
    c = pinned_corpus()
    print("pinned corpus n=%d hash=%s" % (len(c), corpus_hash(c)))
    r = chain(c)
    p = pooled(r["rows"])
    for k, v in p.items():
        print("  %-16s model %.4f  base %.4f  n=%d" % (k, v["mae_model"], v["mae_base"], v["n"]))

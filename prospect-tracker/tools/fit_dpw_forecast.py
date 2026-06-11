# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""$/WAR next-winter forecast evaluation (model-audit Phase 2, WS-2b).

Forward-chained one-winter-ahead forecasts of the signings-implied $/WAR
series (NPV basis): for each test winter Y, every method sees only
winters < Y. Candidates vs the v1 flat-5% carry:

  flat5      last prior winter x 1.05^gap (the incumbent assumption)
  trend      log-linear trend on prior winters
  trend_cbt  trend + log CBT-threshold covariate (dated CBA records —
             known ex-ante, including carry-forward years)

Writes data/dpw_forecast_eval.json. The winning method is set by hand in
fa_config.yaml market_model.dpw_forecast.method (a config decision
committed WITH its eval — the standing-rule pattern). n is tiny (single
digits of winters); the eval exists so the choice is measured, not vibes.

Run: python tools/fit_dpw_forecast.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fa_market as fm                                       # noqa: E402

log = logging.getLogger(__name__)
TEST_WINTERS = list(range(2018, 2027))


def _forecast(series: dict[int, float], year: int, method: str) -> float | None:
    prior = {y: v for y, v in series.items() if y < year}
    if len(prior) < 2:
        return None
    if method == "flat5" or len(prior) < 4:
        y = max(prior)
        return prior[y] * (1.05 ** (year - y))
    return fm._fit_log_trend(prior, with_cbt=(method == "trend_cbt"))(year)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    enriched = fm.enriched_signings(2015, 2026)
    series = fm.dollars_per_war_by_winter(enriched)
    rows = []
    err = {m: [] for m in ("flat5", "trend", "trend_cbt")}
    for Y in TEST_WINTERS:
        if Y not in series:
            continue
        actual = series[Y]
        row = {"winter": Y, "actual_usd": int(actual)}
        for m in err:
            pred = _forecast(series, Y, m)
            if pred is None:
                continue
            ape = abs(pred - actual) / actual
            row[m] = {"pred_usd": int(pred), "ape": round(ape, 4)}
            err[m].append(ape)
        rows.append(row)
    summary = {m: {"mape": round(sum(v) / len(v), 4), "n": len(v)}
               for m, v in err.items() if v}
    winner = min(summary, key=lambda m: summary[m]["mape"])
    out = {
        "generated_at": date.today().isoformat(),
        "basis": "npv_deferral_adjusted signings-implied series",
        "test_winters": [r["winter"] for r in rows],
        "per_winter": rows,
        "summary": summary,
        "winner": winner,
        "notes": [
            "forward-chained one-winter-ahead; each method sees only prior winters",
            "tiny n by nature — the eval justifies a config choice, not a model claim",
            "active method lives in fa_config market_model.dpw_forecast.method",
        ],
    }
    (ROOT / "data" / "dpw_forecast_eval.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("winner:", winner)
    print("wrote data/dpw_forecast_eval.json")


if __name__ == "__main__":
    main()

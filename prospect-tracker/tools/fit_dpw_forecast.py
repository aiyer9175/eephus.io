# Regeneration runner for data/dpw_forecast_eval.json.
# RESTORED 2026-08-19: verbatim logic of this file at 8fecb2f5^ (deleted in
# the A8 dead-file sweep while its artifact stayed live and registered; the
# 2026-08-19 freshness wave had to reconstruct it from git, so it lives in
# tools/ again). ROOT is derived from this file's location.
#
# VAL_5 build refactor (2026-10-02, docs/dpw-2026-09-25/DPW_PATH_GATE.md G-0):
#   * the methods are unchanged: flat5, trend and trend_cbt, scored one winter
#     ahead exactly as before (_forecast is byte-identical);
#   * horizon 1 is MECHANICAL: a test winter is forecast only if the winter
#     before it is present in the series the tool is given, and every other
#     target is skipped (_forecast has no horizon parameter and fits every
#     winter before Y, so on a series missing Y - 1 it would be trend at
#     horizon 2, which the registration counts as an early look);
#   * the writer takes a series and an output path (--series, --out), so the
#     carry-forward test runs on a synthetic series and a tmp path;
#   * the dpw_path_gate block, and any other "*_gate" block a lab writes into
#     the artifact, is carried forward on a re-run (the fa_backtest.py
#     carry-forward pattern), so a freshness regeneration never deletes it.
# Running this tool with its registered method list at its mechanical horizon 1,
# on any series, is not an early look (G-0). Adding a horizon above 1, or any
# method outside flat5, trend, trend_cbt, carry_destale, carry_zero and
# carry_const, and running it on a real series IS one.
from __future__ import annotations

import argparse
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
METHODS = ("flat5", "trend", "trend_cbt")
DEFAULT_OUT = ROOT / "data" / "dpw_forecast_eval.json"


def _forecast(series: dict[int, float], year: int, method: str) -> float | None:
    prior = {y: v for y, v in series.items() if y < year}
    if len(prior) < 2:
        return None
    if method == "flat5" or len(prior) < 4:
        y = max(prior)
        return prior[y] * (1.05 ** (year - y))
    return fm._fit_log_trend(prior, with_cbt=(method == "trend_cbt"))(year)


def horizon_one_targets(series: dict[int, float], test_winters=TEST_WINTERS) -> list[int]:
    """The targets the tool may forecast: in the series AND with the winter
    before them present (mechanical horizon 1)."""
    return [y for y in test_winters if y in series and (y - 1) in series]


def build_eval(series: dict[int, float], test_winters=TEST_WINTERS,
               generated_at: str | None = None) -> dict:
    """The eval payload for one series. Pure: no I/O."""
    rows = []
    err = {m: [] for m in METHODS}
    for Y in horizon_one_targets(series, test_winters):
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
    winner = min(summary, key=lambda m: summary[m]["mape"]) if summary else None
    return {
        "generated_at": generated_at or date.today().isoformat(),
        "basis": "npv_deferral_adjusted signings-implied series",
        "test_winters": [r["winter"] for r in rows],
        "per_winter": rows,
        "summary": summary,
        "winner": winner,
        "notes": [
            "forward-chained one-winter-ahead; each method sees only prior winters",
            "tiny n by nature - the eval justifies a config choice, not a model claim",
            "active method lives in fa_config market_model.dpw_forecast.method",
        ],
    }


def write_eval(out: dict, path: Path) -> dict:
    """Write the payload, carrying forward every block a lab wrote into the
    artifact (the dpw_path_gate block above all), so a re-run never deletes it."""
    try:
        prev = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        prev = {}
    for k, v in prev.items():
        if k not in out and k.endswith("_gate"):
            out[k] = v
    Path(path).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _load_series(path: str) -> dict[int, float]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = doc.get("usd_per_war_by_winter", doc) if isinstance(doc, dict) else {}
    return {int(k): float(v) for k, v in raw.items()}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="forward-chained one-winter-ahead $/WAR eval")
    ap.add_argument("--series", default=None,
                    help="a JSON series ({winter: usd} or a file with usd_per_war_by_winter); "
                         "default: the in-run signings-implied series")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.series:
        series = _load_series(args.series)
    else:
        enriched = fm.enriched_signings(2015, 2026)
        series = fm.dollars_per_war_by_winter(enriched)
    out = write_eval(build_eval(series), Path(args.out))
    print(json.dumps(out["summary"], indent=1))
    print("winner:", out["winner"])
    print("wrote", args.out)


if __name__ == "__main__":
    main()

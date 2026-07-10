# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 7 (Tier 2) -- emit the upgrade-option report + eval artifact.

  reports/upgrade_option.md      -- per-role grade table (intrinsic / option /
                                    OPT% / sample sizes), tier medians, a universe
                                    option rollup, and the config-prior cross-check.
  data/upgrade_option_eval.json  -- machine-readable, with the acceptance gate.

Run:  python -m tools.build_upgrade_option     (from repo root)
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path

import upgrade_option as uo

_ROOT = Path(__file__).resolve().parent.parent
_REPORTS = _ROOT / "reports"
_DATA = _ROOT / "data"


def _today() -> str:
    return _dt.date.today().isoformat()


def _universe_grade_counts() -> dict:
    """{(is_pitcher, grade): n} of active graded prospects on the latest snapshot,
    snapped to the option-layer grade grid."""
    db = _ROOT / "prospects.db"
    out: dict = {}
    if not db.exists():
        return out
    con = sqlite3.connect(str(db))
    try:
        d = con.execute("SELECT MAX(snapshot_date) FROM metric_snapshots").fetchone()[0]
        rows = con.execute(
            "SELECT consensus_fv, is_pitcher FROM metric_snapshots "
            "WHERE snapshot_date=? AND status='active' AND consensus_fv IS NOT NULL", (d,)
        ).fetchall()
    finally:
        con.close()
    for fv, is_pit in rows:
        key = (bool(is_pit), uo._snap_tier(float(fv)))
        out[key] = out.get(key, 0) + 1
    return out


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def build_eval() -> dict:
    roles = {}
    for is_pit in (False, True):
        roles["pitcher" if is_pit else "hitter"] = uo.option_valuation(is_pit)
    h = roles["hitter"]["grades"]
    gate_pass = (h[45]["opt_pct"] > 0.50) and (h[60]["opt_pct"] < h[45]["opt_pct"])
    return {
        "generated_at": _today(),
        "experiment": "upgrade-option-layer",
        "model": "upgrade_option (grade-transition absorbing Markov; OPT% = option/total)",
        "seed": None,
        "method": {
            "states": "grades " + str(uo.GRADES) + " + graduated + out; annual step",
            "estimation": "prospects.db snapshots (fangraphs + mlb_pipeline pooled to "
                          "one grade per player per year), Laplace-smoothed; graduated "
                          "= debuts.json debut year, out = inactive.json; last year of a "
                          "still-active player is censored (no fabricated transitions).",
            "payoff": "clemens_2026 TABLE value of the grade a player graduates FROM.",
            "total": "expected payoff under the full chain; intrinsic = frozen-grade "
                     "chain (stay/graduate/out at the current grade); option = total - "
                     "intrinsic; OPT% = option/total.",
            "caveat": "High grades are thin (60 FV ~221 hitter obs, 70 ~30) and their "
                      "graduation timing is partly censored, so their OPT% runs low or "
                      "negative: grade mobility at the top is net-downgrade risk, which "
                      "the frozen-at-grade intrinsic ignores. Low grades, where the data "
                      "is thick, show the expected large positive option value.",
        },
        "roles": roles,
        "config_prior_cross_check": {
            "hitter_45_opt_pct_data": h[45]["opt_pct"],
            "hitter_45_opt_pct_config_prior": uo.option_valuation(False, mode="config_prior")["grades"][45]["opt_pct"],
            "note": "config_prior uses the labelled literature anchor (45 FV ~20% upgrade), "
                    "NOT estimated from our data; shown only as a sanity cross-check.",
        },
        "gate": {
            "criterion": "hitter 45 FV OPT% > 0.50 AND hitter 60 FV OPT% < hitter 45 FV OPT%",
            "hitter_45_opt_pct": h[45]["opt_pct"],
            "hitter_60_opt_pct": h[60]["opt_pct"],
            "pass": bool(gate_pass),
            "verdict": "provisional",
        },
    }


def main() -> None:
    _REPORTS.mkdir(exist_ok=True)
    doc = build_eval()
    (_DATA / "upgrade_option_eval.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8")

    counts = _universe_grade_counts()
    lines = [
        "# Upgrade-option layer (Phase 7, Tier 2)", "",
        f"_Generated {_today()} from computed numbers only. UI deferred; report + "
        "registry only._", "",
        "A prospect's grade is a call option on development. We model the grade as a "
        "role-split absorbing Markov chain (grades 35-70, plus graduated and out) with "
        "an annual step, estimated from our own dated grade history (fangraphs + "
        "mlb_pipeline snapshots, Laplace-smoothed). Payoff = the clemens_2026 table "
        "value of the grade a player graduates from.", "",
        "- total = expected payoff under the full chain (grade can move)",
        "- intrinsic = payoff under frozen-grade transitions (stay / graduate / out at "
        "the current grade)",
        "- option = total - intrinsic; OPT% = option / total", "",
        "Low grades are long-dated out-of-the-money calls on development: most of their "
        "value is option. High grades are thin in our data and their graduation timing "
        "is partly censored, so their OPT% runs low or negative (grade mobility at the "
        "top is net-downgrade risk the frozen view ignores). Nobody publishes OPT%.", "",
    ]
    for is_pit in (False, True):
        role = "pitcher" if is_pit else "hitter"
        g = uo.option_valuation(is_pit)["grades"]
        rows = []
        for grade, r in g.items():
            n_univ = counts.get((is_pit, grade), 0)
            agg_opt = round(r["option_musd"] * n_univ / 1000.0, 2)   # $B aggregate option
            rows.append([grade, f"{r['total_musd']:.1f}", f"{r['intrinsic_musd']:.1f}",
                         f"{r['option_musd']:.1f}", f"{r['opt_pct'] * 100:.0f}%",
                         r["n_obs"], f"{r['p_upgrade_annual'] * 100:.0f}%",
                         f"{r['p_graduate_annual'] * 100:.0f}%", n_univ, agg_opt])
        lines += [f"## {role.title()}", "",
                  _md_table(["FV", "total $M", "intrinsic $M", "option $M", "OPT%",
                             "obs (n)", "annual upgrade", "annual graduate",
                             "board n", "agg option $B"], rows), ""]
    h = uo.option_valuation(False)["grades"]
    lines += [
        "## Acceptance", "",
        f"- 45 FV hitter OPT% = {h[45]['opt_pct'] * 100:.0f}% (target > 50%): "
        f"{'PASS' if h[45]['opt_pct'] > 0.5 else 'FAIL'}",
        f"- 60 FV hitter OPT% = {h[60]['opt_pct'] * 100:.0f}% (well below the 45 FV): "
        f"{'PASS' if h[60]['opt_pct'] < h[45]['opt_pct'] else 'FAIL'}", "",
        "## Config-prior cross-check", "",
        "The config-prior mode uses a labelled literature anchor (45 FV position player "
        "~20% upgrade odds), NOT estimated from our data. It is a sanity cross-check "
        f"only: 45 FV hitter OPT% is "
        f"{uo.option_valuation(False, mode='config_prior')['grades'][45]['opt_pct'] * 100:.0f}% "
        "under the config prior vs "
        f"{h[45]['opt_pct'] * 100:.0f}% from our data.", "",
    ]
    (_REPORTS / "upgrade_option.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote data/upgrade_option_eval.json (gate pass={doc['gate']['pass']}) "
          f"and reports/upgrade_option.md")


if __name__ == "__main__":
    main()

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV Pass 5 -- tool eFVs, grounded in the realized MLB stat each tool predicts.

For each gradeable tool we (1) take the player's realized MLB outcome stat (from
career_stats MLB rows), (2) measure how well the consensus tool grade ranks it
(baseline), and (3) measure whether the relevant pre-debut MiLB production adds
signal BEYOND the grade (rank-partial, the Phase-1 method). The tool eFV blends
grade (prior) + production where production earns it, re-expressed on the 20-80
tool scale by a rank-preserving map onto the consensus grade distribution.

Honest scope: tools with a clean realized target are modeled (power->ISO,
hit->AVG/contact, speed->SB; pitcher stuff->K%, command->BB%). Field / arm /
individual pitch SHAPES have no clean realized metric in our data -> the tool eFV
passes the consensus grade through unchanged, disclosed as such.

Artifacts: data/xfv_tools.json (+ report). Run: python efv_tools.py
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import storage
from prospect_path import _spearman
from efv_dataset import matrix_path
from efv_model import SCORED_YEARS, _decision_year

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv_tools.json"

# tool -> (grade key, milb production key, realized MLB stat, higher_is_better)
_TOOLS = {
    "hit":      {"grade": "tool_hit",      "milb": "k_rel",  "stat": "avg",    "hi": True,  "side": "hit"},
    "game_pwr": {"grade": "tool_game_pwr", "milb": "iso_rel", "stat": "iso",   "hi": True,  "side": "hit"},
    "speed":    {"grade": "tool_speed",    "milb": None,      "stat": "sb",     "hi": True,  "side": "hit"},
    "fb":       {"grade": "tool_fb",       "milb": "k_rel",  "stat": "k_pct",  "hi": True,  "side": "pit"},
    "cmd":      {"grade": "tool_cmd",      "milb": "bb_rel", "stat": "bb_pct", "hi": False, "side": "pit"},
}
# disclosed pass-through (no clean realized target in our data)
_PASSTHROUGH = ["raw_pwr", "field", "throw (arm)", "sl/cb/ch pitch shapes"]


def _realized_mlb() -> dict[str, dict]:
    """Per player: PA/BF-weighted mean of each MLB-level stat."""
    out: dict[str, dict] = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
            try:
                rows = [x for x in json.loads(r["payload_json"]) if x.get("level") == "MLB"]
            except ValueError:
                continue
            if not rows:
                continue
            agg, wsum = {}, {}
            for x in rows:
                w = float(x.get("ab") or x.get("bf") or x.get("ip") or 1) or 1.0
                for k in ("avg", "iso", "sb", "k_pct", "bb_pct"):
                    v = x.get(k)
                    if v is None:
                        continue
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        continue
                    # sb is a counting stat -> per-season mean, others rate -> weighted
                    if k == "sb":
                        agg[k] = agg.get(k, 0.0) + v
                        wsum[k] = wsum.get(k, 0) + 1
                    else:
                        agg[k] = agg.get(k, 0.0) + v * w
                        wsum[k] = wsum.get(k, 0.0) + w
            out[r["player_key"]] = {k: agg[k] / wsum[k] for k in agg if wsum.get(k)}
    return out


def _partial_after_grade(grade, feat, realized):
    """Rank-partial: corr(feat, realized) after removing grade from both (the
    Phase-1 'adds beyond the prior' test)."""
    import numpy as np
    if len(grade) < 12:
        return None
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        for pos, i in enumerate(order):
            rk[i] = pos
        return np.array(rk, float)
    g, f, y = rank(grade), rank(feat), rank(realized)
    def resid(a, b):
        b = b - b.mean(); a = a - a.mean()
        beta = (a * b).sum() / ((b * b).sum() or 1)
        return a - beta * b
    fr, yr = resid(f, g), resid(y, g)
    n = len(fr)
    cov = (fr * yr).sum(); vf = (fr * fr).sum(); vy = (yr * yr).sum()
    return round(float(cov / ((vf * vy) ** 0.5)) if vf and vy else 0.0, 4)


def _oos_validate(tool, spec, rows, realized) -> dict | None:
    """Forward-chained OOS check: fit the blend on cohorts < test year, score the
    test year, pool. Returns OOS blend-rho vs grade-only-rho so the platform's
    own OOS bar (not the in-sample partial) decides whether the production blend
    earns a non-zero weight. The blend weight stays the full-window fit; this
    only GATES whether it is applied."""
    sign = 1.0 if spec["hi"] else -1.0
    recs = []
    for r in rows:
        if r["kind"] != "debuted":
            continue
        g = r.get(spec["grade"])
        st = (realized.get(r["player_key"]) or {}).get(spec["stat"])
        if g is None or st is None:
            continue
        milb = (r.get("milb") or {}).get(spec["milb"]) if spec["milb"] else None
        recs.append((_decision_year(r), float(g), milb, sign * float(st)))
    oos_score, oos_grade, oos_y = [], [], []
    for ty in SCORED_YEARS:
        tr = [r for r in rows if r["kind"] == "debuted" and _decision_year(r) < ty]
        params = _fit_blend(tool, spec, tr, realized)
        if not params:
            continue
        for dy, g, milb, sy in recs:
            if dy != ty:
                continue
            gz = (g - params["gmu"]) / params["gsd"]
            fz = (((milb if milb is not None else 0.0) - params["fmu"]) / params["fsd"]
                  if spec["milb"] else 0.0)
            oos_score.append(gz + params["sign"] * params["w"] * fz)
            oos_grade.append(g)
            oos_y.append(sy)
    if len(oos_y) < 15:
        return None
    br = _spearman(oos_score, oos_y)
    gr = _spearman(oos_grade, oos_y)
    return {"n": len(oos_y), "blend_rho": br, "grade_rho": gr,
            "validated": bool(br is not None and gr is not None and br > gr)}


def run(persist: bool = True) -> dict:
    realized = _realized_mlb()
    matrices = {s: json.loads(matrix_path(s).read_text(encoding="utf-8")) for s in ("hit", "pit")}
    tool_out, report = {}, {}

    for tool, spec in _TOOLS.items():
        rows = matrices[spec["side"]]
        recs = []
        for r in rows:
            if r["kind"] != "debuted":
                continue
            g = r.get(spec["grade"])
            st = (realized.get(r["player_key"]) or {}).get(spec["stat"])
            if g is None or st is None:
                continue
            milb = (r.get("milb") or {}).get(spec["milb"]) if spec["milb"] else None
            recs.append((r["player_key"], float(g), milb, float(st)))
        if len(recs) < 20:
            report[tool] = {"n": len(recs), "note": "too few resolved players"}
            continue
        sign = 1.0 if spec["hi"] else -1.0
        grades = [x[1] for x in recs]
        stats = [sign * x[3] for x in recs]            # orient so higher=better
        base_rho = _spearman(grades, stats)
        partial = None
        if spec["milb"]:
            sub = [(x[1], x[2], sign * x[3]) for x in recs if x[2] is not None]
            if len(sub) >= 20:
                partial = _partial_after_grade([s[0] for s in sub],
                                               [s[1] for s in sub], [s[2] for s in sub])
        # tool eFV score = z(grade) + w*z(milb), w from the partial (cap 0.5).
        # The partial is IN-SAMPLE, so GATE the applied weight on a forward-chained
        # OOS check (the platform's own bar): keep the blend only where it beats
        # grade-only out-of-sample; otherwise zero it (grade-only).
        w_insample = max(0.0, min(0.5, (partial or 0.0) * 2.0)) if partial else 0.0
        oos = _oos_validate(tool, spec, rows, realized)
        w = w_insample if (oos and oos["validated"]) else 0.0
        gz = _z([x[1] for x in recs])
        fz = _z([(x[2] if x[2] is not None else 0.0) for x in recs]) if spec["milb"] else [0.0] * len(recs)
        score = [gz[i] + (sign * w) * fz[i] for i in range(len(recs))]
        blend_rho = _spearman(score, stats)
        # re-grade: rank-map score onto the consensus grade distribution
        target = sorted(grades)
        order = sorted(range(len(recs)), key=lambda i: score[i])
        m = len(recs)
        for pos, i in enumerate(order):
            p = pos / (m - 1) if m > 1 else 0.0
            tool_out.setdefault(recs[i][0], {})[tool] = round(target[min(m - 1, int(round(p * (m - 1))))], 1)
        report[tool] = {
            "n": len(recs), "realized_stat": spec["stat"],
            "grade_only_spearman": base_rho,
            "production_partial_after_grade": partial,
            "blend_weight_insample": round(w_insample, 3),
            "blend_weight_applied": round(w, 3),
            "tool_xfv_spearman": blend_rho,
            "oos_validation": oos,
            "adds_over_grade_oos": bool(oos and oos["validated"]),
        }

    out = {
        "generated_at": date.today().isoformat(),
        "modeled_tools": report,
        "passthrough_tools": _PASSTHROUGH,
        "passthrough_reason": "no clean realized MLB metric in our data; consensus grade used as-is",
        "method": ("tool eFV = consensus grade (prior) + pre-debut MiLB production where it "
                   "adds signal beyond the grade (rank-partial), mapped onto the 20-80 grade "
                   "scale. Validated vs grade-only on realized MLB stats."),
        "n_players_with_tool_xfv": len(tool_out),
    }
    if persist:
        OUT_PATH.write_text(json.dumps({"meta": out, "by_player": tool_out}, indent=0), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


def _z(v):
    mu = statistics.mean(v)
    sd = statistics.pstdev(v) or 1.0
    return [(x - mu) / sd for x in v]


def _mean_sd(v):
    return statistics.mean(v), (statistics.pstdev(v) or 1.0)


def _fit_blend(tool, spec, train_rows, realized):
    """Re-derive a tool's blend params on the resolved debuted set (the same fit run()
    does): production blend weight + the grade/production z-stats used to normalize."""
    recs = []
    for r in train_rows:
        if r["kind"] != "debuted":
            continue
        g = r.get(spec["grade"])
        st = (realized.get(r["player_key"]) or {}).get(spec["stat"])
        if g is None or st is None:
            continue
        milb = (r.get("milb") or {}).get(spec["milb"]) if spec["milb"] else None
        recs.append((float(g), milb, float(st)))
    if len(recs) < 20:
        return None
    sign = 1.0 if spec["hi"] else -1.0
    partial = None
    if spec["milb"]:
        sub = [(x[0], x[1], sign * x[2]) for x in recs if x[1] is not None]
        if len(sub) >= 20:
            partial = _partial_after_grade([s[0] for s in sub], [s[1] for s in sub],
                                           [s[2] for s in sub])
    w = max(0.0, min(0.5, (partial or 0.0) * 2.0)) if partial else 0.0
    gmu, gsd = _mean_sd([x[0] for x in recs])
    fmu, fsd = (_mean_sd([(x[1] if x[1] is not None else 0.0) for x in recs])
                if spec["milb"] else (0.0, 1.0))
    return {"sign": sign, "w": w, "gmu": gmu, "gsd": gsd, "fmu": fmu, "fsd": fsd}


def run_live(persist: bool = True) -> dict:
    """Tool eFVs for the CURRENT active prospect board. Apply the production blend weight
    learned from resolved players (run()) to each live player's tool grade + pre-decision
    MiLB production, then rank-map onto the LIVE pool's consensus grade distribution so the
    units match the tool grades shown on the site. Modeled tools only (pass-through tools
    have no realized target -> the site shows the consensus grade unchanged)."""
    from efv_dataset import live_matrix_path
    realized = _realized_mlb()
    train = {s: json.loads(matrix_path(s).read_text(encoding="utf-8")) for s in ("hit", "pit")}
    live = {s: json.loads(live_matrix_path(s).read_text(encoding="utf-8")) for s in ("hit", "pit")}
    tool_out, report = {}, {}
    for tool, spec in _TOOLS.items():
        side = spec["side"]
        blend = _fit_blend(tool, spec, train[side], realized)
        # live players gate on pro track record (milb present) -- same rule as the
        # headline live grade -- so a tool eFV only exists where production grounds it.
        lrows = [r for r in live[side]
                 if r.get(spec["grade"]) is not None and r.get("milb")]
        if blend is None or not lrows:
            report[tool] = {"n_live": len(lrows), "note": "no blend or no live rows"}
            continue
        # Gate the applied production weight on the forward-chained OOS check, so
        # the LIVE displayed tool grade only blends in MiLB production where it
        # beats grade-only out-of-sample (not just in-sample).
        oos = _oos_validate(tool, spec, train[side], realized)
        sign = blend["sign"]
        w = blend["w"] if (oos and oos["validated"]) else 0.0
        live_grades = [float(r[spec["grade"]]) for r in lrows]

        def _lscore(r):
            gz = (float(r[spec["grade"]]) - blend["gmu"]) / blend["gsd"]
            if spec["milb"]:
                f = (r.get("milb") or {}).get(spec["milb"])
                fz = ((float(f) if f is not None else 0.0) - blend["fmu"]) / blend["fsd"]
            else:
                fz = 0.0
            return gz + (sign * w) * fz

        scores = [_lscore(r) for r in lrows]
        target = sorted(live_grades)
        order = sorted(range(len(lrows)), key=lambda i: scores[i])
        m = len(lrows)
        for pos, i in enumerate(order):
            p = pos / (m - 1) if m > 1 else 0.0
            tool_out.setdefault(lrows[i]["player_key"], {})[tool] = round(
                target[min(m - 1, int(round(p * (m - 1))))], 1)
        report[tool] = {"n_live": len(lrows), "blend_weight_applied": round(w, 3),
                        "adds_over_grade_oos": bool(oos and oos["validated"])}

    out = {"generated_at": date.today().isoformat(), "scope": "LIVE active board",
           "modeled_tools": report, "passthrough_tools": _PASSTHROUGH,
           "n_players_with_tool_xfv": len(tool_out)}
    if persist:
        (DATA_DIR / "xfv_tools_live.json").write_text(
            json.dumps({"meta": out, "by_player": tool_out}, indent=0), encoding="utf-8")
        log.info("wrote %s (%d players)", DATA_DIR / "xfv_tools_live.json", len(tool_out))
    return out


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--live" in sys.argv:
        rep = run_live()
        print("LIVE tool eFV:", rep["n_players_with_tool_xfv"], "players")
        for t, d in rep["modeled_tools"].items():
            print(f"  {t:9s} n_live={d.get('n_live')} blend_w={d.get('blend_weight_production')}")
        sys.exit(0)
    rep = run()
    print("tool eFV validation (realized MLB stat):")
    for t, d in rep["modeled_tools"].items():
        if d.get("n", 0) >= 20:
            print(f"  {t:9s} n={d['n']:4d} stat={d['realized_stat']:7s} "
                  f"grade-only rho={d['grade_only_spearman']} | partial={d['production_partial_after_grade']} "
                  f"| tool-eFV rho={d['tool_xfv_spearman']} | adds={d['adds_over_grade']}")
    print("passthrough (no realized target):", ", ".join(rep["passthrough_tools"]))
    print("players with >=1 tool eFV:", rep["n_players_with_tool_xfv"])

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 8 (Tier 2) -- emit the cross-source grade-normalization report + eval.

  reports/grade_normalization.md        -- per-source drift tables (overlap with
                                           FanGraphs), the before/after consensus
                                           diff, and the material-drift flags.
  data/grade_normalization_eval.json    -- machine-readable, with the gate.

Run:  python -m tools.build_grade_normalization      (from repo root)
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path

import numpy as np

import grade_normalization as gn

_ROOT = Path(__file__).resolve().parent.parent
_REPORTS = _ROOT / "reports"
_DATA = _ROOT / "data"
_CYCLE = 2026   # the latest cycle where several sources overlap


def _today() -> str:
    return _dt.date.today().isoformat()


def _sources() -> list[str]:
    db = _ROOT / "prospects.db"
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT DISTINCT source FROM snapshots WHERE fv IS NOT NULL "
            "AND substr(snapshot_date,1,4)=?", (str(_CYCLE),)).fetchall()
    finally:
        con.close()
    return sorted(r[0] for r in rows if r[0])


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def build_eval() -> dict:
    drift = []
    for role in ("hitter", "pitcher"):
        for src in _sources():
            r = gn.drift_row(src, role, _CYCLE)
            if r:
                drift.append(r)
    nc = gn.normalized_consensus(_CYCLE)
    diffs = np.array([p["diff"] for p in nc.values()]) if nc else np.array([0.0])
    # reproducibility check (deterministic recomputation)
    reproducible = gn.normalized_consensus(_CYCLE) == nc
    # identity check (reference maps to itself)
    identity = all(abs(gn.quantile_map(v, gn.REFERENCE, "hitter", _CYCLE) - v) < 1e-6
                   for v in (35, 45, 55, 65))
    material = [d for d in drift if d.get("material")]
    return {
        "generated_at": _today(),
        "experiment": "cross-source-grade-normalization",
        "model": "grade_normalization (paired quantile map of each source onto FanGraphs FV)",
        "cycle": _CYCLE,
        "method": {
            "mapping": "quantile-map each source's grade distribution onto FanGraphs "
                       "on the OVERLAP (players graded by both), per role per cycle, so "
                       "coverage is controlled for and only a true scale bias remains.",
            "reference": gn.REFERENCE,
            "consensus": "normalized consensus = mean of the FanGraphs-scale normalized "
                         "per-source grades (>= 2 sources); does NOT change the live "
                         "consensus (analytical layer, default unchanged).",
            "no_equivalence": "no assumed scale equivalences; mappings are data-derived; "
                              "thin cells pool the source's overlap across years (flagged).",
        },
        "drift": drift,
        "consensus_diff": {
            "n_players": len(nc),
            "mean": round(float(diffs.mean()), 3),
            "median": round(float(np.median(diffs)), 3),
            "p10": round(float(np.percentile(diffs, 10)), 3),
            "p90": round(float(np.percentile(diffs, 90)), 3),
            "max_abs": round(float(np.abs(diffs).max()), 3),
        },
        "gate": {
            "reproducible": bool(reproducible),
            "reference_identity": bool(identity),
            "material_drift_sources": sorted({d["source"] for d in material}),
            "pass": bool(reproducible and identity),
            "verdict": "provisional",
        },
    }


def main() -> None:
    _REPORTS.mkdir(exist_ok=True)
    doc = build_eval()
    (_DATA / "grade_normalization_eval.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8")

    nc = gn.normalized_consensus(_CYCLE)
    movers = sorted(nc.items(), key=lambda kv: -abs(kv[1]["diff"]))[:20]
    lines = [
        "# Cross-source grade normalization (Phase 8, Tier 2)", "",
        f"_Generated {_today()} for cycle {_CYCLE}. Analytical layer: the live "
        "consensus is unchanged; this is reproducible and diff-able._", "",
        "Each source's grade distribution is quantile-mapped onto FanGraphs FV on the "
        "OVERLAP (players graded by both source and FanGraphs), per role per cycle. "
        "Mapping on the shared players separates a genuine scale bias from a coverage "
        "difference, so a top-only outlet is not called hot just for skipping the low "
        "tiers. No scale equivalences are assumed; the mappings are data-derived.", "",
        "## Source drift vs FanGraphs (overlap, cycle " + str(_CYCLE) + ")", "",
        "median shift = FanGraphs median minus the source median on the shared players "
        "(negative = the source grades higher than FanGraphs).", "",
    ]
    for role in ("hitter", "pitcher"):
        rows = []
        for src in _sources():
            r = gn.drift_row(src, role, _CYCLE)
            if r:
                rows.append([r["source"], r["n"], r["median_raw"], r["median_fg_overlap"],
                             r["median_shift"], "yes" if r["pooled"] else "",
                             "MATERIAL" if r["material"] else ""])
        lines += [f"### {role.title()}", "",
                  _md_table(["source", "overlap n", "source median", "FG median",
                             "shift", "pooled", "flag"], rows), ""]
    d = doc["consensus_diff"]
    lines += [
        "## Consensus: before vs after normalization", "",
        f"Over {d['n_players']} players graded by 2+ sources in {_CYCLE}, the normalized "
        f"consensus moves by mean {d['mean']}, median {d['median']} FV (p10 {d['p10']}, "
        f"p90 {d['p90']}, max abs {d['max_abs']}). Most players are unchanged; the moves "
        "concentrate on players graded by a materially hot or cold source.", "",
        "### Top 20 consensus movers", "",
        _md_table(["player", "role", "raw consensus", "normalized", "diff", "sources"],
                  [[pk, p["role"], p["raw_consensus"], p["norm_consensus"], p["diff"],
                    len(p["sources"])] for pk, p in movers]), "",
        "## Reproducibility + identity", "",
        f"- Recomputation is deterministic: {doc['gate']['reproducible']}.",
        f"- FanGraphs maps to itself (identity): {doc['gate']['reference_identity']}.",
        f"- Material-drift sources flagged: {', '.join(doc['gate']['material_drift_sources']) or 'none'}.", "",
    ]
    (_REPORTS / "grade_normalization.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote data/grade_normalization_eval.json (gate pass={doc['gate']['pass']}) "
          f"and reports/grade_normalization.md")


if __name__ == "__main__":
    main()

# Regeneration runner for data/grade_normalization_eval.json.
# RESTORED 2026-08-19 (deleted in the A8 dead-file sweep 2026-08-05 while its
# artifact stayed live and registered) with ONE deliberate change: every
# analysis view is threaded with as_of_year = consensus.grade_norm_cutoff()
# so the eval describes the LIVE configuration (GRADE_NORM_AS_OF is True;
# the 2026-07-04 eval predates the flip and measured the uncapped basis).
# Emits the eval JSON only (the reports/ markdown is out of scope here).
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import consensus as _cons              # noqa: E402
import grade_normalization as gn       # noqa: E402

_DATA = _ROOT / "data"
_CYCLE = 2026   # the latest cycle where several sources overlap


def _sources() -> list[str]:
    con = sqlite3.connect(str(_ROOT / "prospects.db"))
    try:
        rows = con.execute(
            "SELECT DISTINCT source FROM snapshots WHERE fv IS NOT NULL "
            "AND substr(snapshot_date,1,4)=?", (str(_CYCLE),)).fetchall()
    finally:
        con.close()
    return sorted(r[0] for r in rows if r[0])


def build_eval() -> dict:
    as_of = _cons.grade_norm_cutoff()
    drift = []
    for role in ("hitter", "pitcher"):
        for src in _sources():
            r = gn.drift_row(src, role, _CYCLE, as_of_year=as_of)
            if r:
                drift.append(r)
    nc = gn.normalized_consensus(_CYCLE, as_of_year=as_of)
    diffs = np.array([p["diff"] for p in nc.values()]) if nc else np.array([0.0])
    reproducible = gn.normalized_consensus(_CYCLE, as_of_year=as_of) == nc
    identity = all(abs(gn.quantile_map(v, gn.REFERENCE, "hitter", _CYCLE,
                                       as_of_year=as_of) - v) < 1e-6
                   for v in (35, 45, 55, 65))
    material = [d for d in drift if d.get("material")]
    return {
        "generated_at": _dt.date.today().isoformat(),
        "experiment": "cross-source-grade-normalization",
        "model": "grade_normalization (paired quantile map of each source onto FanGraphs FV)",
        "cycle": _CYCLE,
        "as_of_year": as_of,
        "method": {
            "mapping": "quantile-map each source's grade distribution onto FanGraphs "
                       "on the OVERLAP (players graded by both), per role per cycle, so "
                       "coverage is controlled for and only a true scale bias remains.",
            "reference": gn.REFERENCE,
            "as_of": "every view is capped at consensus.grade_norm_cutoff() "
                     "(GRADE_NORM_AS_OF is True), the same basis the served "
                     "board applies; the 2026-07-04 edition of this eval "
                     "predated the flip and measured the uncapped mapping.",
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
    doc = build_eval()
    (_DATA / "grade_normalization_eval.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("as_of_year:", doc["as_of_year"])
    print("consensus_diff:", json.dumps(doc["consensus_diff"]))
    print("gate:", json.dumps(doc["gate"]))
    print("wrote data/grade_normalization_eval.json")


if __name__ == "__main__":
    main()

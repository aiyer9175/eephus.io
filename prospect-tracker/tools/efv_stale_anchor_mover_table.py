"""Lane B3 mover table: what flipping efv_dataset.STALE_ANCHOR_DATE_BASIS from
'point' to 'source' actually moves, measured on the committed board.

WHY THIS EXISTS. STALE_ANCHOR_DATE_BASIS is basis-adjacent: fv_effective is the
model's dominant feature and it feeds the blend's consensus leg, so a change of
which date the staleness ramp reads re-grades and re-ranks live rows. The flip
was blocked on producing this table first (master plan 2026-08-07, Lane B3), and
the tests that pin the shipped default exist so the flip cannot land silently.

WHAT IT MEASURES. For every ACTIVE row on the committed timeseries board it
recomputes efv_dataset._stale_anchor_discount under both bases, using
efv_dataset's OWN functions (imported, never re-implemented, so the table cannot
drift from the code it is about to authorize):

  point   discount from the consensus POINT date, which build_timeseries
          forward-fills to the newest date ANY source touched the player,
          including mlbam_ingest.refresh_performance_anchors' daily FV-35 stamp
  source  discount from efv_dataset._anchor_asof_date(pt), the 3-tier
          precedence real-FV > folded-back constant > rank-only

FV-POINT DELTAS, NOT GRADE DELTAS. The discount is subtracted from
consensus_fv_raw to make fv_effective. It reaches the served grade through the
ridge's fv feature AND through the blend's consensus leg, so the served grade
move is a MODEL response, not this number. Running the model here would need a
refit inside a forbidden exporter, so the table reports the input move plus the
population that takes one, and says so rather than implying a grade delta it did
not measure. The +12mo / +24mo projections re-run the same ramp on a FROZEN
board with the clock advanced, which is the shape the spec quoted.

Read-only. Writes exactly one artifact, docs/efv-2026-08-07/STALE_ANCHOR_MOVER_TABLE.json,
and prints a summary. Run: python tools/efv_stale_anchor_mover_table.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efv_dataset as ed   # noqa: E402  (path bootstrap must precede the import)

TS_PATH = ROOT / "data" / "timeseries.json"
OUT_DIR = ROOT / "docs" / "efv-2026-08-07"
OUT_PATH = OUT_DIR / "STALE_ANCHOR_MOVER_TABLE.json"

# Clock offsets the table reports. 0 is today; the other two answer "what does a
# board that stops being re-listed look like", which is the question the ramp was
# built for and the only way to see a suppressed ramp's future cost.
HORIZONS_MO = (0, 12, 24)


def _latest_point(rec: dict) -> dict | None:
    pts = [p for p in (rec.get("points") or []) if p.get("snapshot_date")]
    if not pts:
        return None
    pts.sort(key=lambda p: p["snapshot_date"])
    return pts[-1]


def _months_ago(asof_iso, today):
    try:
        d = date.fromisoformat(str(asof_iso)[:10])
    except (TypeError, ValueError):
        return None
    return (today - d).days / 30.44


def build() -> dict:
    ts = json.loads(TS_PATH.read_text(encoding="utf-8"))
    players = ts.get("players") or []
    today = date.today()
    constants = ed._constant_anchor_sources()

    rows = []
    for rec in players:
        if rec.get("status") == "debuted" or rec.get("debut_date"):
            continue
        pt = _latest_point(rec)
        if pt is None:
            continue
        fv_raw = pt.get("consensus_fv_raw")
        if fv_raw is None:
            continue
        point_date = pt.get("snapshot_date")
        source_date = ed._anchor_asof_date(pt) or point_date
        # Which tier supplied the source date, so the table can show that the
        # constant-only cohort is retained rather than dropped (the inversion
        # _anchor_asof_date's docstring warns about).
        per = pt.get("per_source") or {}
        tier = "none"
        for src, entry in per.items():
            if not isinstance(entry, dict):
                continue
            for e in [entry, *(entry.get("extras") or [])]:
                if not isinstance(e, dict) or not e.get("snapshot_date"):
                    continue
                if e.get("fv_published") is not None:
                    t = "fv_const" if src in constants else "fv_real"
                elif e.get("rank") is not None:
                    t = "rank_only"
                else:
                    continue
                if str(e["snapshot_date"])[:10] == source_date:
                    order = {"fv_real": 0, "fv_const": 1, "rank_only": 2}
                    if tier == "none" or order[t] < order[tier]:
                        tier = t
        rows.append({
            "player_key": rec.get("player_key"),
            "player_name": rec.get("player_name"),
            "org": rec.get("org"),
            "consensus_fv_raw": float(fv_raw),
            "point_date": point_date,
            "source_date": source_date,
            "source_tier": tier,
            "dates_differ": bool(source_date != point_date),
        })

    horizons = {}
    for mo in HORIZONS_MO:
        clock = today + timedelta(days=int(round(mo * 30.44)))
        n_point = n_source = 0
        movers = []
        for r in rows:
            d_point = ed._stale_anchor_discount(r["point_date"], r["consensus_fv_raw"], today=clock)
            d_source = ed._stale_anchor_discount(r["source_date"], r["consensus_fv_raw"], today=clock)
            if d_point > 0:
                n_point += 1
            if d_source > 0:
                n_source += 1
            if abs(d_source - d_point) > 1e-9:
                movers.append({
                    **{k: r[k] for k in ("player_key", "player_name", "org",
                                         "consensus_fv_raw", "point_date",
                                         "source_date", "source_tier")},
                    "discount_point": round(d_point, 2),
                    "discount_source": round(d_source, 2),
                    "delta_fv": round(d_source - d_point, 2),
                    "months_point": round(_months_ago(r["point_date"], clock) or 0.0, 1),
                    "months_source": round(_months_ago(r["source_date"], clock) or 0.0, 1),
                })
        movers.sort(key=lambda m: -m["delta_fv"])
        by_band = Counter(int(round(m["consensus_fv_raw"] / 5.0) * 5) for m in movers)
        by_tier = Counter(m["source_tier"] for m in movers)
        deltas = sorted(m["delta_fv"] for m in movers)
        horizons[f"+{mo}mo"] = {
            "clock": clock.isoformat(),
            "decayed_under_point": n_point,
            "decayed_under_source": n_source,
            "net_newly_decayed": n_source - n_point,
            "movers": len(movers),
            "mover_fv_band": dict(sorted(by_band.items())),
            "mover_source_tier": dict(by_tier),
            "delta_fv_max": deltas[-1] if deltas else 0.0,
            "delta_fv_median": deltas[len(deltas) // 2] if deltas else 0.0,
            "delta_fv_min": deltas[0] if deltas else 0.0,
            "top_movers": movers[:40],
        }

    # THE GUARD THE GATE ASKS FOR. The flip must only touch rows whose REAL anchor
    # is older than the ramp start; anything else means the tiering leaked.
    leaks = []
    for m in horizons["+0mo"]["top_movers"]:
        if m["months_source"] <= ed.STALE_ANCHOR_RAMP_START_MO:
            leaks.append(m["player_key"])

    out = {
        "line": "LANE-B3: STALE_ANCHOR_DATE_BASIS point -> source mover table",
        "generated_at": date.today().isoformat(),
        "lab": "tools/efv_stale_anchor_mover_table.py",
        "plan": "docs/master-plan-2026-08-07-omnibus3.md Lane B3",
        "board_source": {"path": "data/timeseries.json",
                         "generated_at": ts.get("generated_at"),
                         "active_rows_considered": len(rows)},
        "ramp_constants": {
            "STALE_ANCHOR_RAMP_START_MO": ed.STALE_ANCHOR_RAMP_START_MO,
            "STALE_ANCHOR_RAMP_FULL_MO": ed.STALE_ANCHOR_RAMP_FULL_MO,
            "STALE_ANCHOR_TERMINAL": ed.STALE_ANCHOR_TERMINAL,
            "pinned_by": "data/xfv_stale_anchor_eval.json (test_efv_stale_anchor.py)",
        },
        "basis_before": "point",
        "basis_after": "source",
        "date_disagreement": {
            "rows_where_source_date_differs": sum(1 for r in rows if r["dates_differ"]),
            "source_tier_census": dict(Counter(r["source_tier"] for r in rows)),
        },
        "horizons": horizons,
        "gate_ramp_start_leak": {
            "rule": "a mover's source-basis age must exceed STALE_ANCHOR_RAMP_START_MO",
            "violations": leaks,
        },
        "reads_as": ("FV-point moves on the model's fv_effective input, not served grade "
                     "deltas. The grade response runs through the ridge fv feature and the "
                     "blend consensus leg and is only observable after a box regen."),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main() -> None:
    out = build()
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print(f"board {out['board_source']['generated_at']}, "
          f"{out['board_source']['active_rows_considered']} active rows")
    print(f"source date differs on {out['date_disagreement']['rows_where_source_date_differs']} rows; "
          f"tiers {out['date_disagreement']['source_tier_census']}")
    for k, h in out["horizons"].items():
        print(f"  {k:6s} decayed point={h['decayed_under_point']:5d} "
              f"source={h['decayed_under_source']:5d} "
              f"net={h['net_newly_decayed']:+5d} movers={h['movers']:5d} "
              f"delta_fv max={h['delta_fv_max']} median={h['delta_fv_median']}")
    print(f"ramp-start leaks: {len(out['gate_ramp_start_leak']['violations'])}")


if __name__ == "__main__":
    main()

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The prediction-only blast radius of the unified $/WAR path (VAL_5,
DESIGN_v2 section 10; docs/dpw-2026-09-25/DPW_PATH_GATE.md section 13).

One lever at a time, each stage against the previous one:

  OFF    the legacy branches (value_framework.dpw_path_forced(False))
  U1a    the base season B (OD-3)
  U1b    the nominal rate R on fixed-dollar legs, the escalator path, the
         companion salary legs and the cliff rate (OD-2, OD-4)
  U1c    the Trade Machine convention (OD-5)
  U2     the served level basis (OD-1)

Every stage prices the same PROBES (prospects, veterans, free agents, Trade
Machine contract rows) through the production functions with the unified path
forced on in-process over a named series file (dpw_path_forced(True,
stages=..., series_path=...)), never the environment and never the live file
unless the flip task names it. It reports totals by surface, the movers of each
stage, and the bands that send a breach to the owner (they are not pass
criteria). No realized value and no FV cell: probes are rows, totals are by
surface only.

Built and fixture-tested in the build commit (test_dpw_blast_radius.py, on
SYNTHETIC probes); run on real data only in the flip commit (F-D). The veteran
price mirrors proj_export's per-season loop without the tender cliff, which the
flip measures on the regenerated artifacts themselves.

Usage (the flip only):
  python tools/dpw_blast_radius.py --series data/fa_dpw_series.json \\
      --from-data data --out <scratch>/blast.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                    # noqa: E402

STAGES = ("U1a", "U1b", "U1c", "U2")
LEVERS = {"U1a": "base season B (OD-3)",
          "U1b": "nominal rate R, escalator path, companion legs, cliff rate (OD-2, OD-4)",
          "U1c": "Trade Machine convention (OD-5)",
          "U2": "served level basis (OD-1)"}
# The bands that trigger an owner decision (DESIGN_v2 section 10). Not pass criteria.
BAND_VETERAN_SUM = 0.075
BAND_PROSPECT_SUM = 0.25
BAND_ROW_PCT = 0.50
BAND_ROW_PCT_BASE_USD = 5_000_000.0       # a row counts for the percent band only above this base
BAND_ROW_USD = 15_000_000.0
SURFACES = ("prospects", "veterans", "fa", "trade_machine")


def stage_sequence() -> list[tuple[str, tuple[str, ...] | None]]:
    """[("OFF", None), ("U1a", ("U1a",)), ("U1b", ("U1a", "U1b")), ...]: each
    stage adds ONE lever to the previous one."""
    seq: list[tuple[str, tuple[str, ...] | None]] = [("OFF", None)]
    on: list[str] = []
    for s in STAGES:
        on.append(s)
        seq.append((s, tuple(on)))
    return seq


# ---------------------------------------------------------------------------
# Pricing one probe per surface, through the production functions
# ---------------------------------------------------------------------------

def price_prospect(p: dict) -> float:
    """USD: the engine's raw expected surplus (pre-calibration; the calibration
    route is OD-8's and is measured on the regenerated artifacts)."""
    v = vf.expected_surplus_usd(p["fv"], bool(p["is_pitcher"]), p.get("position"),
                                age=p.get("age"), eta_years=p.get("eta_years"),
                                eta_origin=p.get("eta_origin"))
    return float(v or 0.0)


def price_veteran(v: dict) -> float:
    """USD: proj_export's per-season surNpv loop (no tender cliff): value of
    season FIRST_SEASON + t at its level minus the salary (times the companion
    index in unified mode), discounted at the rate the loop uses, times d(B) in
    unified mode."""
    import proj_export as pe
    seasons = v["salary"]
    war = v["war"]
    dpw = float(v.get("dpw_usd") or 17_143_641.0)
    if vf.dpw_path_active():
        r = vf.nominal_rate()
        d_usd, _ = pe._unified_path_surplus(seasons, war, dpw)
        npv = sum(d / (1.0 + r) ** c["t"] for c, d in zip(seasons, d_usd) if d is not None)
        return npv * vf.season_discount(pe.FIRST_SEASON)
    r = float(vf._config()["discount_rate"])
    npv = 0.0
    for c in seasons:
        if c["usd"] is None:
            continue
        w = war[c["t"]] if c["t"] < len(war) else 0.0
        npv += (pe._season_value_usd(w or 0.0, c["t"], dpw) - float(c["usd"])) / (1.0 + r) ** c["t"]
    return npv


def price_fa(f: dict) -> float:
    """USD: rational value at the class year (the /fa/ basis)."""
    import fa_market as fm
    return float(fm.rational_value_usd(f["war_path"], int(f["class_year"]),
                                       float(f.get("dpw_usd") or 17_143_641.0),
                                       infl=f.get("infl")))


def price_trade_machine(t: dict) -> float:
    """USD: the Trade Machine's backup contract surplus (bayes)."""
    import bayes_trade_value as bt
    return float(bt._contract_surplus_mm(t["player"], float(t["true_talent_war"]),
                                         float(t["remaining_years"]))) * 1e6


PRICERS = {"prospects": price_prospect, "veterans": price_veteran, "fa": price_fa,
           "trade_machine": price_trade_machine}


def price_all(probes: dict) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for surface in SURFACES:
        rows = probes.get(surface) or []
        out[surface] = {str(r["id"]): PRICERS[surface](r) for r in rows}
    return out


# ---------------------------------------------------------------------------
# The run: one lever at a time, against the previous stage
# ---------------------------------------------------------------------------

def _movers(prev: dict[str, float], cur: dict[str, float], names: dict[str, str]) -> list[dict]:
    out = []
    for k in sorted(cur):
        a, b = prev.get(k, 0.0), cur.get(k, 0.0)
        d = b - a
        pct = (d / abs(a)) if abs(a) > BAND_ROW_PCT_BASE_USD else None
        if abs(d) >= BAND_ROW_USD or (pct is not None and abs(pct) >= BAND_ROW_PCT):
            out.append({"id": k, "name": names.get(k), "before_usd": a, "after_usd": b,
                        "delta_usd": d, "delta_pct": pct})
    return out


def run(probes: dict, series_path: str | Path) -> dict:
    """Price every probe at every stage and report each stage against the
    previous one. Read-only; writes nothing."""
    names = {str(r["id"]): r.get("name") for s in SURFACES for r in (probes.get(s) or [])}
    priced: list[tuple[str, dict]] = []
    for label, stages in stage_sequence():
        if stages is None:
            with vf.dpw_path_forced(False):
                priced.append((label, price_all(probes)))
        else:
            with vf.dpw_path_forced(True, stages=stages, series_path=series_path):
                if not vf.dpw_path_active():
                    raise SystemExit(f"{series_path} carries no dpw_path block; nothing to measure")
                priced.append((label, price_all(probes)))
    report = {"levers": LEVERS, "series_path": str(series_path),
              "bands": {"veteran_surnpv_sum_pct": BAND_VETERAN_SUM,
                        "prospect_surplus_sum_pct": BAND_PROSPECT_SUM,
                        "row_pct": BAND_ROW_PCT, "row_pct_base_usd": BAND_ROW_PCT_BASE_USD,
                        "row_usd": BAND_ROW_USD},
              "stages": []}
    for i, (label, cur) in enumerate(priced):
        totals = {s: sum(cur[s].values()) for s in SURFACES}
        entry = {"stage": label, "totals_usd": totals}
        if i:
            prev_label, prev = priced[i - 1]
            ptot = {s: sum(prev[s].values()) for s in SURFACES}
            entry["against"] = prev_label
            entry["delta_usd"] = {s: totals[s] - ptot[s] for s in SURFACES}
            entry["delta_pct"] = {s: ((totals[s] - ptot[s]) / abs(ptot[s])) if ptot[s] else None
                                  for s in SURFACES}
            entry["rows_moved"] = {s: sum(1 for k in cur[s] if cur[s][k] != prev[s].get(k))
                                   for s in SURFACES}
            entry["movers"] = {s: _movers(prev[s], cur[s], names) for s in SURFACES}
            breaches = []
            vp = entry["delta_pct"]["veterans"]
            if vp is not None and abs(vp) > BAND_VETERAN_SUM:
                breaches.append(f"veteran surNpv sum {vp:+.1%} (band +/- {BAND_VETERAN_SUM:.1%})")
            pp = entry["delta_pct"]["prospects"]
            if pp is not None and abs(pp) > BAND_PROSPECT_SUM:
                breaches.append(f"prospect surplus sum {pp:+.1%} (band +/- {BAND_PROSPECT_SUM:.0%})")
            for s in SURFACES:
                for m in entry["movers"][s]:
                    breaches.append(f"{s} row {m['name'] or m['id']} {m['delta_usd'] / 1e6:+.1f}M")
            entry["breaches"] = breaches
        report["stages"].append(entry)
    return report


# ---------------------------------------------------------------------------
# Probes from the served payloads (the flip only)
# ---------------------------------------------------------------------------

def probes_from_data(data_dir: str | Path) -> dict:
    """Prospects and veterans from data/mlb_projections.json, free agents from
    data/fa_class.json. Read-only. The Trade Machine surface is measured on the
    regenerated trade_values.json in the flip; no probe is built for it here."""
    import proj_export as pe
    dd = Path(data_dir)
    mp = json.loads((dd / "mlb_projections.json").read_text(encoding="utf-8"))
    first = int(mp.get("first_season") or pe.FIRST_SEASON)
    dpw = float(mp.get("dpw_usd") or 0.0) or None
    probes: dict = {"prospects": [], "veterans": [], "fa": [], "trade_machine": []}
    for p in mp.get("prospects") or []:
        if p.get("fv") is None:
            continue
        eta = p.get("eta")
        probes["prospects"].append({
            "id": p.get("key"), "name": p.get("name"), "fv": float(p["fv"]),
            "is_pitcher": str(p.get("pos") or "").upper() in ("SP", "RP", "P", "RHP", "LHP"),
            "position": p.get("pos"), "age": p.get("age"),
            "eta_years": (float(eta) - (first - 1)) if eta is not None else None,
            "eta_origin": first - 1})
    for v in mp.get("vets") or []:
        sp = v.get("salPath") or []
        if not sp or not v.get("war"):
            continue
        sal = [{"t": int(r[0]) - first, "season": int(r[0]), "usd": r[1], "tok": r[4], "src": r[5]}
               for r in sp if int(r[0]) >= first]
        war = list(v["war"]) + list(v.get("warTail") or [])
        probes["veterans"].append({"id": v.get("key"), "name": v.get("name"), "war": war,
                                   "salary": sal, "dpw_usd": dpw})
    fa_path = dd / "fa_class.json"
    if fa_path.exists():
        fc = json.loads(fa_path.read_text(encoding="utf-8"))
        for m in fc.get("members") or []:
            if not m.get("warPath"):
                continue
            yrs = int(round(float(m.get("projYears") or len(m["warPath"]))))
            probes["fa"].append({"id": m.get("key"), "name": m.get("name"),
                                 "war_path": list(m["warPath"])[:max(1, yrs)],
                                 "class_year": int(fc["class_year"]), "dpw_usd": fc.get("dpw_usd"),
                                 "infl": fc.get("dpw_infl")})
    return probes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", required=True, help="the series file carrying the dpw_path block")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--probes", help="a JSON file of probes by surface")
    src.add_argument("--from-data", help="build probes from the served payloads in this directory")
    ap.add_argument("--out", required=True, help="where to write the report (outside the webroot)")
    args = ap.parse_args(argv)
    probes = (json.loads(Path(args.probes).read_text(encoding="utf-8")) if args.probes
              else probes_from_data(args.from_data))
    report = run(probes, args.series)
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    for st in report["stages"]:
        line = f"{st['stage']:>4}: " + ", ".join(f"{s} {st['totals_usd'][s] / 1e6:,.1f}M" for s in SURFACES)
        print(line)
        for b in st.get("breaches") or []:
            print("      breach:", b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

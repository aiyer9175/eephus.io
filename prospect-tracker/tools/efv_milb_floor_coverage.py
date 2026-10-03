# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MiLB floor coverage receipt for the list-vintage frame (EFV3_B3; EFV3_PLAN.md s4
wave 1 arm milb_floor_2005, LANE_B.md F-B4 and the M1 rule).

efv_vintage_frame.MILB_FLOOR_LV lifts the earliest MiLB season an F-LV row reads from
efv_dataset.MILB_FLOOR_DEFAULT (2014) to 2005, the first season on disk for every sport
id, on the sides the DS-03 balance re-run leaves BALANCED (MILB_FLOOR_LV_WITHHELD names
the rest). This tool builds every development (side, vintage) frame at the default
floor, at the lifted floor (the candidate, both sides) and as the program reads it
(lv_milb_floor per side), and writes data/efv_milb_floor_coverage.json:

  by_vintage[side][V]   rows; with_milb_block at the default floor and at the lifted
                        floor; the n_milb_seasons distribution and the entry_observed
                        share at each floor; the latest block season (must be at most
                        V - 1); blocks whose final season is before the default floor.
  as_built              the floor each side reads at and its block count by vintage.
  norms                 for every (season, level) a lifted block was translated with,
                        whether the contemporaneous level-season norm existed in the
                        cache or the prior-season / static fallback was used
                        (efv_dataset._resolved_norms): the era enters only there.
  ds03_rerun            the DS-03 balance probe (tools/efv_identity_balance.py, its own
                        build_rows and balance, same seed) at the default floor and at
                        the lifted floor on the same inputs, every indicator, both sides,
                        and the pre-registered reading: a side whose milb_absent or
                        level_prev_missing was BALANCED at the default floor and is not
                        at the lifted floor is WITHHELD. The committed DS-03 receipt
                        (data/efv_identity_balance.json) is not rewritten here.

The ds03_rerun block reads the W3 label (the retiring eWAR v2 label, as the task spec
says) to measure an indicator's balance; it scores no rater, no eFV and no candidate,
and nothing is grouped by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md). The
reserved vintages (R-LV 2020, 2021) are never built; the guard is called first and must
raise. The v1 matrices and the live board read the default floor and are not touched
(test_efv_milb_floor.py pins the default byte-identical).

Run:  python tools/efv_milb_floor_coverage.py            (writes the artifact)
      python tools/efv_milb_floor_coverage.py --dry-run  (prints, writes nothing)
      python tools/efv_milb_floor_coverage.py --no-balance  (coverage only, no label)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_dataset as D  # noqa: E402
import efv_identity_balance as TB  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import milb_history as mh  # noqa: E402

OUT = ROOT / "data" / "efv_milb_floor_coverage.json"
#: The indicators the pre-registered withhold rule reads (task spec, VALIDITY).
WITHHOLD_INDICATORS = ("milb_absent", "level_prev_missing")


def _guards() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    for V in sorted(F.RESERVED_LV):
        try:
            F.guard_score_request(V, purpose="milb floor coverage")
        except F.ReservedFrameError:
            continue
        raise F.ReservedFrameError(f"the reserved guard did not raise for {V}")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "vintages_read": list(F.DEV_VINTAGES), "reserved_vm_pins": pins}


def _dist(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[int, int] = {}
    for r in rows:
        b = r.get("milb")
        if b:
            k = int(b.get(key) or 0)
            out[k] = out.get(k, 0) + 1
    return {str(k): out[k] for k in sorted(out)}


def _share(rows: list[dict], key: str) -> float | None:
    blk = [r["milb"] for r in rows if r.get("milb")]
    if not blk:
        return None
    return round(sum(1 for b in blk if float(b.get(key) or 0.0) == 1.0) / len(blk), 4)


def vintage_block(base: list[dict], lift: list[dict], V: int) -> dict:
    """The receipt for one (side, V): counts at both floors, nothing else."""
    wb = sum(1 for r in base if r.get("milb"))
    wl = sum(1 for r in lift if r.get("milb"))
    seasons = [int(r["milb"]["milb_season"]) for r in lift if r.get("milb")]
    return {
        "rows": len(lift),
        "with_milb_block": {"default_floor": wb, "lifted_floor": wl, "gained": wl - wb},
        "n_milb_seasons": {"default_floor": _dist(base, "n_milb_seasons"),
                           "lifted_floor": _dist(lift, "n_milb_seasons")},
        "entry_observed_share": {"default_floor": _share(base, "entry_observed"),
                                 "lifted_floor": _share(lift, "entry_observed")},
        "latest_block_season": max(seasons) if seasons else None,
        "block_season_before_v": all(s <= V - 1 for s in seasons),
        "final_season_before_default_floor": sum(1 for s in seasons
                                                 if s < D.MILB_FLOOR_DEFAULT),
        "milb_floor_keys": sorted({int(r.get("milb_floor") or 0) for r in lift}),
    }


def norms_receipt(frames_lifted: dict[str, dict[int, list[dict]]]) -> dict:
    """Which (season, level) norms the lifted blocks were translated with, and whether
    the contemporaneous norm existed in the cache (cache-only read, no fetch)."""
    seen: set[tuple[int, str, str]] = set()
    for side, by_v in frames_lifted.items():
        group = "pitching" if side == "pit" else "hitting"
        for rows in by_v.values():
            for r in rows:
                b = r.get("milb")
                if b and int(b["milb_season"]) < D.MILB_FLOOR_DEFAULT:
                    seen.add((int(b["milb_season"]), str(b["milb_level"]), group))
    out: dict = {}
    for season, level, group in sorted(seen):
        n = mh.league_norms(season, level, group, fetch=False)
        src = "contemporaneous" if n and n.get("k_pct") else (
            "prior_season" if (mh.league_norms(season - 1, level, group, fetch=False)
                               or {}).get("k_pct") else "static_prior")
        out.setdefault(group, {})[f"{season}:{level}"] = {
            "source": src, "n": (n or {}).get("n")}
    counts = {g: {s: sum(1 for v in d.values() if v["source"] == s)
                  for s in ("contemporaneous", "prior_season", "static_prior")}
              for g, d in out.items()}
    return {"rule": "efv_dataset._resolved_norms(season, level): contemporaneous "
                    "level-season median, else the prior season's, else the static "
                    "per-group prior; no era indicator is emitted",
            "counts": counts, "by_season_level": out}


def withhold_reading(at_default: dict, at_lifted: dict) -> dict:
    """The pre-registered rule: a side is WITHHELD when an indicator in
    WITHHOLD_INDICATORS was BALANCED at the default floor and is not at the lifted
    floor. Returns {side: {"withheld", "because"}} plus the set the code must carry."""
    out: dict = {}
    for side in F.SIDES:
        because = []
        for name in WITHHOLD_INDICATORS:
            d, lft = at_default[side][name], at_lifted[side][name]
            if d["verdict"] == "BALANCED" and lft["verdict"] != "BALANCED":
                because.append({"indicator": name, "default_floor": d["verdict"],
                                "lifted_floor": lft["verdict"],
                                "partial_lifted": lft.get("partial"),
                                "ci95_lifted": lft.get("ci95")})
        out[side] = {"withheld": bool(because), "because": because}
    out["withheld_sides"] = sorted(s for s in F.SIDES if out[s]["withheld"])
    out["code_withheld_sides"] = sorted(F.MILB_FLOOR_LV_WITHHELD)
    out["code_agrees"] = out["withheld_sides"] == out["code_withheld_sides"]
    return out


def ds03_rerun() -> dict:
    """The balance probe at both floors on the same inputs, same seed each run."""
    runs = {}
    for label, floor in (("default_floor", D.MILB_FLOOR_DEFAULT),
                         ("lifted_floor", F.MILB_FLOOR_LV)):
        rng = np.random.default_rng(TB.SEED)
        rows, receipt = TB.build_rows(milb_floor=floor)
        runs[label] = {"floor": floor, "rows": receipt, "balance": TB.balance(rows, rng)}
    reading = withhold_reading(runs["default_floor"]["balance"],
                               runs["lifted_floor"]["balance"])
    return {
        "tool": "tools/efv_identity_balance.py build_rows(milb_floor) + balance",
        "label": {"provider": TB.L.provider(), "resolved_through": TB.L.resolved_through()},
        "seed": TB.SEED, "B": TB.B_BAL,
        "indicators": dict(TB.INDICATORS),
        "withhold_indicators": list(WITHHOLD_INDICATORS),
        "rule": ("a side is withheld when milb_absent or level_prev_missing is BALANCED "
                 "at the default floor and not at the lifted floor"),
        "runs": runs,
        "reading": reading,
        "committed_receipt_untouched": "data/efv_identity_balance.json",
    }


def run(balance: bool = True) -> dict:
    guards = _guards()
    universe = F.load_universe()
    by_v: dict = {}
    lifted: dict = {}
    as_built: dict = {}
    for side in F.SIDES:
        for V in F.DEV_VINTAGES:
            F.guard_score_request(V, purpose="milb floor coverage")
            base = F.build_frame(side, V, universe=universe, sidecars=False,
                                 milb_floor=D.MILB_FLOOR_DEFAULT)
            lift = F.build_frame(side, V, universe=universe, sidecars=False,
                                 milb_floor=F.MILB_FLOOR_LV)
            built = F.build_frame(side, V, universe=universe, sidecars=False)
            by_v.setdefault(side, {})[str(V)] = vintage_block(base, lift, V)
            lifted.setdefault(side, {})[V] = lift
            as_built.setdefault(side, {"floor": F.lv_milb_floor(side),
                                       "with_milb_block_by_vintage": {}})
            as_built[side]["with_milb_block_by_vintage"][str(V)] = sum(
                1 for r in built if r.get("milb"))
            as_built[side]["row_floor_keys"] = sorted(
                set(as_built[side].get("row_floor_keys") or [])
                | {int(r.get("milb_floor") or 0) for r in built})
    totals = {}
    for side in F.SIDES:
        blocks = by_v[side].values()
        totals[side] = {
            "rows": sum(b["rows"] for b in blocks),
            "with_milb_block_default": sum(b["with_milb_block"]["default_floor"]
                                           for b in blocks),
            "with_milb_block_lifted": sum(b["with_milb_block"]["lifted_floor"]
                                          for b in blocks),
            "with_milb_block_as_built": sum(
                as_built[side]["with_milb_block_by_vintage"].values()),
            "every_block_season_before_v": all(b["block_season_before_v"]
                                               for b in blocks),
        }
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_milb_floor_coverage.py",
        "role": "development",
        "adjudicates": ("nothing; a coverage receipt and the DS-03 balance re-run the "
                        "lift is pre-registered against"),
        "what": ("F-LV MiLB block coverage at efv_dataset.MILB_FLOOR_DEFAULT and at "
                 "efv_vintage_frame.MILB_FLOOR_LV, by (side, vintage), and the floor "
                 "each side reads at"),
        "floors": {"default": D.MILB_FLOOR_DEFAULT, "lifted_lv": F.MILB_FLOOR_LV,
                   "withheld_sides": sorted(F.MILB_FLOOR_LV_WITHHELD),
                   "floor_by_side": {s: F.lv_milb_floor(s) for s in F.SIDES},
                   "fetch_floor_season": mh.FETCH_FLOOR_SEASON,
                   "entry_observed_rule": ("entry season after the floor season and "
                                           "the one following it (the shipped guard, "
                                           "slid with the floor)")},
        "guards": guards,
        "code": {"commit": commit},
        "by_vintage": by_v,
        "as_built": as_built,
        "totals": totals,
        "norms": norms_receipt(lifted),
        "ds03_rerun": ds03_rerun() if balance else None,
        "not_in_efv_progress": ("no score is read here; the lifted frame is scored "
                                "only by the screening lab (EFV3_B7) as the arm "
                                "milb_floor_2005 against the default-floor base"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-balance", action="store_true")
    args = ap.parse_args(argv)
    doc = run(balance=not args.no_balance)
    for side in F.SIDES:
        for V, b in doc["by_vintage"][side].items():
            w = b["with_milb_block"]
            e = b["entry_observed_share"]
            print(f"{side} {V}: rows {b['rows']} block {w['default_floor']} -> "
                  f"{w['lifted_floor']} latest {b['latest_block_season']} "
                  f"entry_observed {e['default_floor']} -> {e['lifted_floor']}")
    print("as built:", json.dumps({s: doc["as_built"][s]["floor"] for s in F.SIDES}))
    print("norms:", json.dumps(doc["norms"]["counts"]))
    if doc["ds03_rerun"]:
        for side in F.SIDES:
            for name in WITHHOLD_INDICATORS:
                for lab in ("default_floor", "lifted_floor"):
                    v = doc["ds03_rerun"]["runs"][lab]["balance"][side][name]
                    print(f"DS-03 {side} {name} {lab}: n_with {v['n_with']} partial "
                          f"{v.get('partial')} ci95 {v.get('ci95')} {v['verdict']}")
        print("withheld:", json.dumps(doc["ds03_rerun"]["reading"]["withheld_sides"]),
              "code agrees:", doc["ds03_rerun"]["reading"]["code_agrees"])
    if not args.dry_run:
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

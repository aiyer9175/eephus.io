#!/usr/bin/env python
"""Produce data/hof_ledger_eval.json: the induction-ledger repair, receipted.

WHAT WAS WRONG. StatsAPI names Hall of Fame inductees by MLBAM id and
Baseball-Reference names ballot rows by bbref id. Where the ingest could not
bridge the two, the inductee did not enter the ledger at all, and the label
layer then reported him as not in the Hall. Measured 2026-09-06: 130 of 354
inductees unresolved, 63 of them inside the eligible universe, of whom 33
carried a resolved ZERO and 30 read as censored. The shipped label said Charlie
Gehringer, Ed Delahanty, Eddie Plank, Buck Ewing and Jesse Burkett are not Hall
of Famers.

Both war_daily parquets carry both ids, so the bridge was on disk the whole
time.

THIS IS A CORRECTNESS REPAIR WITH NO FORWARD CLAIM. It does not make any model
more accurate and is not expected to; if anything it should make a downstream
bake-off score LOWER, because the players it recovers are heavily the 1930s and
1940s veterans-committee wave, who carry less WAR than the existing positives.
It is worth doing because the label was wrong, not because it wins anything.

Deterministic and offline. Run:  python tools/hof_ledger_check.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hof_data as hd                              # noqa: E402

OUT = ROOT / "data" / "hof_ledger_eval.json"
AS_OF = 2026


def _census(df, col) -> dict:
    return {"positive": int((df[col] == 1).sum()),
            "negative": int((df[col] == 0).sum()),
            "censored": int(df[col].isna().sum())}


def _route_census(df, col) -> dict:
    out: dict = {}
    for v in df[col]:
        k = "none" if v is None or (isinstance(v, float) and v != v) else str(v)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def build() -> dict:
    hd.clear_cache()
    xwalk = hd.crosswalk_bbref_mlbam()
    after_b = hd.ballots()
    before_b = hd.ballots(crosswalk={})

    after = hd.label_frame(offline=True, as_of_year=AS_OF, ballots_=after_b)
    before = hd.label_frame(offline=True, as_of_year=AS_OF, ballots_=before_b)
    a_idx = after.set_index("player_ID")
    b_idx = before.set_index("player_ID")

    before_pos = set(b_idx.index[b_idx["label_any"] == 1])
    after_pos = set(a_idx.index[a_idx["label_any"] == 1])
    added = sorted(after_pos - before_pos)
    lost = sorted(before_pos - after_pos)

    false_zero = sorted(p for p in added if b_idx.loc[p, "label_any"] == 0)
    false_cens = sorted(p for p in added if b_idx.loc[p, "label_any"] != 0)

    res = after_b["resolution"]

    # the ones the repair could not reach, and what they are
    out_of_universe = []
    uni = set(a_idx.index)
    for pid, r in after_b["inducted"].items():
        if pid not in uni:
            out_of_universe.append({
                "player_id": pid, "name": r.get("player_name"),
                "election_year": r.get("election_year"),
                "reason": "not in the eligible universe (fewer than ten seasons "
                          "with a WAR row, or last season inside the five-year wait)",
            })

    rf = hd.resolution_frame(offline=True, as_of_year=AS_OF, ballots_=after_b)

    # the two resolution_year corrections, counted
    pre79 = 0
    anachronistic = 0
    non_final_flag = 0
    non_final_examples = []
    for pid, rows in after_b["by_pid"].items():
        bb = [r for r in rows
              if (r.get("route") or "").upper() == "BBWAA" and r.get("election_year")]
        if not bb:
            continue
        drop = [int(r["election_year"]) for r in bb if r.get("dropped_off")]
        last = max(int(r["election_year"]) for r in bb)
        pre = [y for y in drop if y < hd.BBWAA_DROP_RULE_FIRST_YEAR]
        if pre:
            pre79 += 1
            if min(drop) < last:
                anachronistic += 1
        if drop and not any(r.get("elected") for r in bb) and max(drop) < last:
            non_final_flag += 1
            if len(non_final_examples) < 12:
                nm = next((r.get("player_name") for r in bb if r.get("player_name")), pid)
                non_final_examples.append({"player_id": pid, "name": nm,
                                           "drop_years": sorted(drop),
                                           "last_appearance": last})

    panel = hd._bbwaa_panel_years(after_b)
    gap_years = [y for y in range(min(panel), max(panel) + 1) if y not in panel]
    gap_cases = 0
    for pid in rf["player_ID"]:
        if hd.resolution_route(pid, ballots_=after_b) != "left_ballot":
            continue
        bb = [r for r in (after_b["by_pid"].get(pid) or [])
              if (r.get("route") or "").upper() == "BBWAA" and r.get("election_year")]
        if bb and (max(int(r["election_year"]) for r in bb) + 1) in gap_years:
            gap_cases += 1

    # label_any is non-monotone in Y: inducted long after the window closed
    non_monotone = []
    for pid, r in after_b["inducted"].items():
        if pid not in uni:
            continue
        close = hd.bbwaa_window_close_year(pid, ballots_=after_b)
        ey = r.get("election_year")
        if close and ey and int(ey) > int(close) + hd.COMMITTEE_HORIZON_YEARS:
            non_monotone.append({"player_id": pid, "name": r.get("player_name"),
                                 "window_close": int(close), "inducted": int(ey)})
    non_monotone.sort(key=lambda x: x["inducted"] - x["window_close"], reverse=True)

    horizon = {}
    base = hd.COMMITTEE_HORIZON_YEARS
    for h in (15, 20, 25, 30, 40):
        hd.COMMITTEE_HORIZON_YEARS = h
        hd.clear_cache()
        bb = hd.ballots()
        f = hd.label_frame(offline=True, as_of_year=AS_OF, ballots_=bb)
        horizon[str(h)] = _census(f, "label_any")
    hd.COMMITTEE_HORIZON_YEARS = base
    hd.clear_cache()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "tools/hof_ledger_check.py",
        "deterministic": True,
        "as_of_year": AS_OF,
        "what": ("the induction-ledger repair: StatsAPI inductees the ingest could "
                 "not bridge to a bbref id were dropped from the ledger, and the "
                 "label layer reported them as not in the Hall"),
        "crosswalk": {
            "pairs": len(xwalk),
            "distinct_bbref": len(set(xwalk.values())),
            "distinct_mlbam": len(set(xwalk.keys())),
            "is_one_to_one": (len(set(xwalk.values())) == len(xwalk)
                              and len(set(xwalk.keys())) == len(xwalk)),
            "source": "war_source last-good parquets, read by path, never over the network",
        },
        "ledger": {
            "n_statsapi": len((after_b.get("doc") or {}).get("statsapi_inductees") or []),
            "n_resolved_before": len(before_b["inducted"]),
            "n_resolved_after": len(after_b["inducted"]),
            "resolution": {k: v for k, v in res.items()
                           if k not in ("plaque_role_unverified", "unresolved_names")},
            "unresolved_names": res["unresolved_names"],
            "n_in_eligible_universe": sum(1 for p in after_b["inducted"] if p in uni),
            "out_of_universe": sorted(out_of_universe, key=lambda x: x["name"] or ""),
        },
        "plaque_role_unverified": {
            "n": len(res["plaque_role_unverified"]),
            "n_in_eligible_universe": sum(
                1 for r in res["plaque_role_unverified"] if r["player_id"] in uni),
            "players_in_eligible_universe": [
                r for r in res["plaque_role_unverified"] if r["player_id"] in uni],
            "blocking_lane": "H-DATA-PLAQUE",
            "what_must_not_happen": (
                "no Hall-sized line, no snub list and no deserved-versus-inducted "
                "verdict may be published off label_any while the plaque role is "
                "unverified. A line sized on a Hall that counts managers and "
                "executives is not a player line."),
        },
        "labels_before": {"label_any": _census(before, "label_any"),
                          "label_bbwaa": _census(before, "label_bbwaa")},
        "labels_after": {"label_any": _census(after, "label_any"),
                         "label_bbwaa": _census(after, "label_bbwaa")},
        "repair_effect": {
            "n_added_positive": len(added),
            "n_lost_positive": len(lost),
            "false_zeros_corrected": len(false_zero),
            "false_censors_corrected": len(false_cens),
            "added_names": sorted(str(a_idx.loc[p, "name"]) for p in added),
            "false_zero_names": sorted(str(a_idx.loc[p, "name"]) for p in false_zero),
        },
        "label_bbwaa_invariance": {
            "is_byte_identical": bool(before["label_bbwaa"].equals(after["label_bbwaa"])),
            "why": ("label_bbwaa reads only b['by_pid']; b['inducted'] is read at "
                    "exactly one site, inside label_any. The repair cannot move a "
                    "writers' verdict and any movement here is a bug in the repair."),
        },
        "resolution_year": {
            "frame_shape": list(rf.shape),
            "route_census_bbwaa": _route_census(rf, "res_route_bbwaa"),
            "route_census_any": _route_census(rf, "res_route_any"),
            "players_with_a_pre_1979_drop_flag": pre79,
            "players_whose_drop_flag_precedes_their_last_appearance": anachronistic,
            "players_with_a_drop_flag_on_a_year_they_survived": non_final_flag,
            "drop_flag_on_a_survived_year_examples": non_final_examples,
            "why_the_flag_must_be_on_the_final_appearance": (
                "the 1979 restriction alone does not catch these. Harvey Haddix "
                "is flagged in 1979 and appears through 1985; Edd Roush is "
                "flagged in five separate years from 1936 and appears through "
                "1960. A flag on a year the player went on to survive did not "
                "end anything, and resolving on it would date the writers' "
                "verdict years before the writers had finished. Found by a test, "
                "not by reasoning it out in advance."),
            "bbwaa_panel_gap_years": gap_years,
            "left_ballot_cases_where_last_plus_one_is_a_gap_year": gap_cases,
            "why_the_gap_years_matter": (
                "the writers voted only every other year from 1956 to 1966 while "
                "the committees kept meeting, so the BBWAA panel has ten empty "
                "years and not the five the ingest records. Resolving a departed "
                "candidate at last plus one would name a year in which no verdict "
                "could have been observed, for the counted number of players above."),
            "label_any_non_monotone_players": non_monotone[:40],
            "n_label_any_non_monotone": len(non_monotone),
            "why_non_monotone": (
                "label_any checks the induction ledger before the window close, so "
                "a player enshrined by a committee more than COMMITTEE_HORIZON_YEARS "
                "after his window closed reads a resolved zero for decades and then "
                "flips to one. The as-of identity with label_frame therefore holds "
                "at 2026 and is not claimed generally."),
        },
        "horizon_sensitivity": horizon,
        "what_this_does_not_show": (
            "any accuracy gain. This is a correctness repair. Its most likely "
            "downstream effect on a benchmark bake-off is NEGATIVE, because the "
            "recovered positives are heavily the 1930s and 1940s veterans wave and "
            "carry lower JAWS than the existing positive class. It also makes the "
            "plaque-role problem larger rather than smaller, because the players it "
            "recovers include managers who also played."),
    }


def main() -> int:
    d = build()
    OUT.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  ledger {d['ledger']['n_resolved_before']} -> "
          f"{d['ledger']['n_resolved_after']} of {d['ledger']['n_statsapi']}")
    print(f"  label_any {d['labels_before']['label_any']} -> "
          f"{d['labels_after']['label_any']}")
    print(f"  false zeros corrected {d['repair_effect']['false_zeros_corrected']}, "
          f"false censors {d['repair_effect']['false_censors_corrected']}")
    print(f"  label_bbwaa byte-identical: "
          f"{d['label_bbwaa_invariance']['is_byte_identical']}")
    print(f"  plaque role unverified inside E: "
          f"{d['plaque_role_unverified']['n_in_eligible_universe']}")
    if not d["crosswalk"]["pairs"]:
        print("  WARNING: the crosswalk read NOTHING, so the ledger is unrepaired")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

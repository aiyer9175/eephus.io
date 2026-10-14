# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV tool-feature sidecar and its no-outcome coverage probes
(TL_9_EFV_TOOL_SIDECAR; Part 9 PLAN section 9.4.5; LANE_C.md sections 1.3 and 2.7).

WHY THIS MAY RUN AT ALL. The eFV feature frontier is closed (plan Part 2; the 2026-08-14
closure, 39 arms, zero survivors) and game power failed as an eFV driver four times (the
Phase 1 partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds;
data/xfv_arm_ledger.json). Nothing here re-runs a spent arm. The columns are NEW (a power
composite chosen on realized ISO by a registered look, a tool-implied ISO residual, the
inputs of an accuracy-weighted hit consensus) and exist on the owner's 2026-10-01 asks.
The served eFV grade does not change in this task. Route: owner answer TL-Q1 (a), build
the sidecar now, run the DS-06 admission diagnostic on development folds later (TL_16),
pre-declare for the next registration.

WHAT IT WRITES. data/_labs/efv_tool_features.json (data/_labs ships in neither deploy
consumer), keyed (side, list vintage V, player_key) on the efv_vintage_frame rows of the
development vintages 2011 to 2019 (lv_dev). It is never a column in a pinned matrix: the
matrices are not read or written, so their sha256 pins do not move. Column definitions
are in efv_tool_features.py. A frame row with no entry has no input at all; a consumer
imputes at the has-block TRAIN mean (efv_tool_features.impute_at_train_mean) and emits no
absence flag.

THE STEPS, each a probe with role development in data/xfv_arm_ledger.json through
tools/efv_arm_ledger.py (counts only; reads_outcome False):

    TL9:coverage.frame:<side>             frame rows, outcome-blind ids, R-VM rows dropped
    TL9:coverage.per_source_grades:hit    rows with each tool's grade, by source
    TL9:coverage.pwr_comp:hit             rows with both as-of inputs; candidacy from look P
    TL9:coverage.tip_iso_resid:hit        rows with the residual; TIP table rows per V
    TL9:coverage.tool_hit_w_inputs:hit    rows with one, and two or more, source hit grades

NEVER READ: list vintages 2020 and 2021 (R-LV) while docs/efv-v2/EFV_V2_GATE.md
'## 9. Results' holds no R-LV entry; every row whose effective debut year is 2025 or later
(R-VM; dropped before any count, the number dropped reported); any season at or after V,
or 2026 or later (asserted, and the seasons used recorded per V); a WAR, W3, label or
outcome module; .cache/milb_platoon; the stored career rows. Identity is the frame's
outcome-blind efv_identity id. Nothing is grouped by consensus-FV level.

Run:  python tools/efv_tool_sidecar.py [--dry-run]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_tool_features as TF  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import level_norms  # noqa: E402
import milb_history as mh  # noqa: E402
import tool_implied as TI  # noqa: E402

OUT = ROOT / "data" / "_labs" / "efv_tool_features.json"
LOOK_P = ROOT / "data" / "power_composite_eval.json"
SCHEMA = "efv_tool_features/1"
TASK = "TL_9_EFV_TOOL_SIDECAR"
#: Compact row fields (rows block, hitter side).
ROW_FIELDS = ("per_source", "consensus", "tip_iso_resid", "iso_shrunk", "tip",
              "milb_level", "milb_season", "milb_pa")
WHY = ("The eFV feature frontier is closed (plan Part 2; the 2026-08-14 closure, 39 arms, "
       "zero survivors) and game power failed as an eFV driver four times (the Phase 1 "
       "partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds; "
       "data/xfv_arm_ledger.json); nothing here re-runs a spent arm. The columns are NEW "
       "(a power composite chosen on realized ISO by a registered look, a tool-implied ISO "
       "residual, the inputs of an accuracy-weighted hit consensus) and exist on the "
       "owner's 2026-10-01 asks. The served eFV grade does not change.")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def rlv_record_exists(gate_text: str | None = None) -> bool:
    """True when docs/efv-v2/EFV_V2_GATE.md '## 9. Results' holds an entry naming R-LV
    (anything in the section but its placeholder line)."""
    if gate_text is None:
        p = ROOT / F.GATE_DOC
        gate_text = p.read_text(encoding="utf-8") if p.exists() else ""
    m = re.search(r"^## 9\. Results\s*$(.*?)^## ", gate_text, re.S | re.M)
    if not m:
        return False
    body = [ln for ln in m.group(1).splitlines()
            if ln.strip() and ln.strip() != "---" and not ln.strip().startswith("(Empty.")]
    return any("R-LV" in ln for ln in body)


def _guards(vintages) -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    rlv = rlv_record_exists()
    for V in vintages:
        TF.assert_vintage_allowed(V, rlv_record=rlv)
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "rlv_record_in_gate_s9": rlv,
            "vintages_read": [int(v) for v in vintages], "reserved_vm_pins": pins,
            "first_forbidden_season": TF.FIRST_FORBIDDEN_SEASON}


def load_tool_snapshots() -> dict:
    """{player_key: [(source, snapshot_date, tools dict)]} for every snapshot carrying a
    hit, game_pwr or raw_pwr grade in a January to April window of a development year."""
    import storage
    lo, hi = min(F.DEV_VINTAGES), max(F.DEV_VINTAGES)
    out: dict = {}
    with storage.connect() as con:
        for r in con.execute(
                "SELECT source, snapshot_date, player_key, tools_json FROM snapshots "
                "WHERE tools_json IS NOT NULL AND tools_json != '' "
                "AND snapshot_date >= ? AND snapshot_date < ? ORDER BY snapshot_date",
                (f"{lo}-01-01", f"{hi}-05-01")):
            d = str(r["snapshot_date"])[:10]
            if d[5:] >= "05-01":
                continue
            try:
                td = json.loads(r["tools_json"])
            except ValueError:
                continue
            if not isinstance(td, dict) or not any(t in td for t in TF.TOOLS):
                continue
            out.setdefault(r["player_key"], []).append((r["source"], d, td))
    return out


_MLB: dict = {}


def mlb_line(pid: int, season: int):
    if season not in _MLB:
        _MLB[season] = {int(r["mlbam"]): r for r in mh.season_splits(1, season, "hitting",
                                                                      fetch=False)
                        if r.get("mlbam")}
    return _MLB[season].get(int(pid))


def league_lines(season: int) -> list[dict]:
    rows = []
    for sport in mh.ALL_SPORTS:
        rows.extend(mh.season_splits(sport, season, "hitting", fetch=False))
    return rows


def milb_line(pid, season: int, level: str):
    if not pid or season is None or not level:
        return None
    rows = [r for r in (mh.player_index(int(season), "hitting", fetch=False).get(int(pid))
                        or []) if r.get("level") != "MLB"]
    return mh.level_row(rows, level, "hitting") if rows else None


def build(frames: dict | None = None, snaps: dict | None = None, *, mlb=None,
          league=None, milb=None, look_p: dict | None = None,
          vintages=F.DEV_VINTAGES) -> dict:
    """The sidecar document. `frames` ({side: {V: rows}}), `snaps`, `mlb(pid, season)`,
    `league(season)`, `milb(pid, season, level)` and `look_p` (the look P result block)
    are for tests; None reads the real inputs."""
    vintages = tuple(int(v) for v in vintages)
    guards = _guards(vintages)
    snaps = load_tool_snapshots() if snaps is None else snaps
    mlb = mlb or mlb_line
    league = league or league_lines
    milb = milb or milb_line
    if look_p is None:
        look_p = (json.loads(LOOK_P.read_text(encoding="utf-8")).get("result")
                  if LOOK_P.exists() else None)
    pwr_status = TF.pwr_comp_status(look_p)
    non_rater, constant = F._real_sources()
    excl = frozenset(non_rater | constant)

    universe = None
    kept: dict = {s: {} for s in F.SIDES}
    dropped = {s: 0 for s in F.SIDES}
    feats: dict = {s: {} for s in F.SIDES}
    for V in vintages:
        F.guard_score_request(V, purpose="tool sidecar")
        for side in F.SIDES:
            if frames is not None:
                rows = list((frames.get(side) or {}).get(V) or [])
            else:
                if universe is None:
                    universe = F.load_universe()
                rows = F.build_frame(side, V, universe=universe, sidecars=False,
                                     milb=(side == "hit"))
            keep = [r for r in rows if not TF.is_rvm(r)]
            dropped[side] += len(rows) - len(keep)
            for r in keep:
                ps = TF.earliest_grades(snaps.get(r["player_key"]) or (), r["window"][0],
                                        r["window"][1], excl)
                r["consensus"] = TF.consensus(ps)
                feats[side].setdefault(V, {})[r["player_key"]] = {
                    "per_source": ps, "consensus": r["consensus"], "tip": None}
            kept[side][V] = keep

    tables: dict = {}
    for V in vintages:
        fit = TF.tip_fit_rows(kept["hit"], V, mlb)
        table = TI.fit_tables(fit, "game_pwr", "iso", "mlb_pooled_through_v_minus_1")
        cs, bd, career_seasons = TF.career_rows(league, V)
        as_of = date(V - 1, 12, 31)
        norms = level_norms.compute_level_norms(cs, bd, today=as_of)
        tip_cache: dict = {}
        n_tip = 0
        for r in kept["hit"][V]:
            f = feats["hit"][V][r["player_key"]]
            g = f["consensus"].get("game_pwr")
            m = r.get("milb") or {}
            lv, s = m.get("milb_level"), m.get("milb_season")
            if g is None or not lv or s is None:
                continue
            table.assert_not_fit_on(r["player_key"])
            k = (lv, g)
            if k not in tip_cache:
                tip_cache[k] = TI.tip_level(table, g, lv, V, stat="iso", side="hit",
                                            career_stats=cs, birth_dates=bd)
            tl = tip_cache[k]
            norm_iso = ((norms.get(lv) or {}).get("perf") or {}).get("avg_iso")
            res = TF.tip_iso_resid(r, g, milb(r.get("mlbam_id"), s, lv), tl.get("value"),
                                   norm_iso)
            res["tip_label"] = tl.get("label")
            f["tip"] = res
            n_tip += res["value"] is not None
        aaa = next((v.get("inputs", {}).get("aaa_offset") for (lv, _g), v in tip_cache.items()
                    if lv == "AAA" and v.get("inputs", {}).get("aaa_offset")), None)
        tables[str(V)] = {
            "fit_rows": table.n_rows, "computable": table.computable,
            "bins_kept": len(table.knots), "bins_thin": sum(1 for b in table.bins if b["thin"]),
            "fit_max_season": table.max_season, "fit_max_debut_year": table.max_debut_year,
            "fit_board_years": sorted({r["board_year"] for r in fit}),
            "career_seasons": career_seasons,
            "level_norms_as_of": as_of.isoformat(),
            "level_norms_seasons_window": level_norms.DEFAULT_SEASONS_WINDOW,
            "aaa_offset_players": (aaa or {}).get("n_players"),
            "aaa_offset_through_season": (aaa or {}).get("through_season"),
            "rows_with_residual": n_tip,
        }

    coverage: dict = {}
    for side in F.SIDES:
        for V in vintages:
            blk = TF.coverage_block(kept[side][V], feats[side].get(V) or {})
            coverage[f"{side}:{V}"] = blk

    rows_out: dict = {}
    for side in F.SIDES:
        for V in vintages:
            blk = {}
            for pk, f in sorted((feats[side].get(V) or {}).items()):
                t = f.get("tip") or {}
                has_any = bool(f["per_source"]) or t.get("value") is not None
                if not has_any:
                    continue
                blk[pk] = [
                    {s: [g.get(x) for x in TF.TOOLS] for s, g in sorted(f["per_source"].items())},
                    [f["consensus"].get(x) for x in TF.TOOLS],
                    None if t.get("value") is None else round(t["value"], 6),
                    None if t.get("iso_shrunk") is None else round(t["iso_shrunk"], 6),
                    None if t.get("tip") is None else round(t["tip"], 6),
                    t.get("level"), t.get("season"), t.get("pa"),
                ]
            rows_out.setdefault(side, {})[str(V)] = blk

    def tot(side, fn):
        return sum(fn(coverage[f"{side}:{V}"]) for V in vintages)

    probes: dict = {}
    base = {"verdict": "COUNTED", "role": "development", "reads_outcome": False}
    for side in F.SIDES:
        tag = f"TL9:coverage.frame:{side}"
        probes[tag] = {"tag": tag, **base,
                       "rows": tot(side, lambda b: b["rows"]),
                       "id_resolved": tot(side, lambda b: b["id_resolved"]),
                       "rvm_rows_dropped": dropped[side],
                       "reason": ""}
        pr = probes[tag]
        pr["reason"] = (f"frame rows {pr['rows']}, outcome-blind id {pr['id_resolved']}, "
                        f"R-VM rows dropped {pr['rvm_rows_dropped']}, V "
                        f"{min(vintages)} to {max(vintages)}; counts only")
    tag = "TL9:coverage.per_source_grades:hit"
    probes[tag] = {"tag": tag, **base,
                   "consensus": {t: tot("hit", lambda b, t=t: b["consensus"][t])
                                 for t in TF.TOOLS},
                   "reason": ""}
    probes[tag]["reason"] = ("rows with a consensus from each source's earliest in-window "
                             "snapshot: " + ", ".join(f"{t} {n}" for t, n in
                                                      probes[tag]["consensus"].items())
                             + "; counts only")
    tag = "TL9:coverage.pwr_comp:hit"
    probes[tag] = {"tag": tag, **base, "candidate": pwr_status["candidate"],
                   "rows": tot("hit", lambda b: b["pwr_comp_inputs"]),
                   "reason": ""}
    probes[tag]["reason"] = (f"rows with both as-of game and raw consensus inputs "
                             f"{probes[tag]['rows']}; {pwr_status['reason']}")
    tag = "TL9:coverage.tip_iso_resid:hit"
    probes[tag] = {"tag": tag, **base,
                   "rows": tot("hit", lambda b: b["tip_iso_resid"]),
                   "tip_fit_rows": {V: tables[V]["fit_rows"] for V in tables},
                   "reason": ""}
    probes[tag]["reason"] = (f"rows with a residual {probes[tag]['rows']} (TIP table "
                             "computable at V " + ", ".join(
                                 V for V in tables if tables[V]["computable"]) +
                             "); PA-shrunk pre-V MiLB ISO minus tip_level at the block "
                             "level, every input season at most V - 1; counts only")
    tag = "TL9:coverage.tool_hit_w_inputs:hit"
    probes[tag] = {"tag": tag, **base,
                   "one_source": tot("hit", lambda b: b["tool_hit_w_inputs"]["one_source"]),
                   "two_or_more": tot("hit", lambda b: b["tool_hit_w_inputs"]["two_or_more"]),
                   "reason": ""}
    probes[tag]["reason"] = (f"rows with one source hit grade {probes[tag]['one_source']}, "
                             f"with two or more {probes[tag]['two_or_more']}; per-source hit "
                             "grades only, the weight is computed per fold outside the V "
                             "frame and never stored")

    inputs = {name: _sha(ROOT / name) for name in
              ("efv_tool_features.py", "tool_implied.py", "level_norms.py",
               "efv_vintage_frame.py", "efv_identity.py")}
    inputs["power_composite_eval.json"] = _sha(LOOK_P) if LOOK_P.exists() else None
    inputs["league_lines"] = ".cache/milb_stats hitting, sport ids 1 and 11 to 16 (read only, never fetched)"
    inputs["grades"] = "prospects.db snapshots.tools_json (read only)"

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_tool_sidecar.py",
        "task": TASK,
        "why": WHY,
        "owner_asks": {
            "message_1": ("Right now, we are only using raw power grade for our power tool "
                          "composite grade and across the site. We have the data for \"Game "
                          "Power\" tool on FanGraphs as well. Can we incorporate game power "
                          "in some way and test to see if it corresponds as an eFV driver? "
                          "Can we blend game power into our power composite grades to make "
                          "them more accurate (and then test our power tool as an eFV "
                          "driver)?"),
            "message_2": ("Similar to the way we do WAG, can we check each debuted "
                          "player's statistical production against their tool-implied "
                          "statistical production (using the FanGraphs framework, ex. "
                          "power tool -> ISO, hit tool -> batting average, etc.) to see "
                          "where different sources miss or hit more based on tools, and "
                          "then accuracy-weight our tool grades accordingly? After doing "
                          "so, if this proves to improve tool grade accuracy, can we then "
                          "check if tool grades can be used as eFV drivers / how they "
                          "should be weighted?"),
        },
        "registration_path": ("TL-Q1 answer (a), recorded in DECISIONS_FOR_OWNER.md: build "
                              "the sidecar now; TL_16 runs the DS-06 admission diagnostic on "
                              "development folds and pre-declares for the next registration"),
        "role": "development sidecar; adjudicates nothing; no served number",
        "frame": "lv_dev",
        "guards": guards,
        "pwr_comp": pwr_status,
        "definition": {
            "tools": list(TF.TOOLS),
            "per_source": ("each source's earliest snapshot inside the row's frame window "
                           "[V-01-01, min(V-05-01, debut day)); non-rater and constant-anchor "
                           "sources excluded as the frame excludes them"),
            "consensus": "unweighted mean across the outlets publishing the tool, rounded to 0.5",
            "pwr_comp": ("the as-of game_pwr and raw_pwr consensus inputs only; no a is "
                         "stored or read (TL_16 cross-fits a per fold on board years up to "
                         "V - 3, players outside the fold, only if a candidate)"),
            "tip_iso_resid": ("iso_shrunk - tip; iso_shrunk = norm + w x (ISO - norm) on the "
                              "frame block's level and season line, w = PA / (PA + "
                              f"{TF.K_SHRINK_PA:g}), norm = the as-of level_norms avg_iso; "
                              "tip = tool_implied.tip_level(table, game_pwr consensus, level, "
                              "V, stat='iso', side='hit') with the table fit on MLB ISO pooled "
                              f"from the debut year to V - 1 (at least {TF.TIP_PA_FLOOR} PA) "
                              "of frame players with a game_pwr consensus at a list vintage "
                              "up to V - 1 who debuted before V, and league lines of seasons "
                              f"V - {TF.CAREER_WINDOW} to V - 1"),
            "tool_hit_w": ("per-source hit grades only; the weight is BA2's estimator, "
                           "computed per fold on players outside the fold's V frame, never "
                           "stored as a value"),
            "id": "the frame row's outcome-blind mlbam_id (efv_identity, DS-03)",
            "missing": ("None, no entry when the row has no input at all; impute at the "
                        "has-block TRAIN mean; no absence flag in any head (DS-04, bug B3)"),
            "norm_min_pa": TF.NORM_MIN_PA,
            "birth_date": "the feed's printed season age placed at July 1 (level_norms age band only)",
        },
        "defaults_taken": [
            "TL-Q1 answered (a) in DECISIONS_FOR_OWNER.md; no default needed for it",
            "look days waived by owner EW3-5 (2026-10-14): the look P record dated today does "
            "not stop this build",
            f"TIP fit frame: MLB ISO pooled from debut year to V - 1 with at least "
            f"{TF.TIP_PA_FLOOR} PA (no age 26+ frame is supportable before 2019)",
            f"league lines for the AAA offset: seasons V - {TF.CAREER_WINDOW} to V - 1",
            f"level norm cameo floor: {TF.NORM_MIN_PA} PA standing in for 10 games",
            "shrink toward the as-of level_norms avg_iso with the house k of 50 PA",
            "pitcher side: frame and grade coverage only (no hitter tool grades apply)",
        ],
        "inputs": inputs,
        "tip_tables": tables,
        "rvm_rows_dropped": dropped,
        "coverage": coverage,
        "row_fields": list(ROW_FIELDS),
        "row_tool_order": list(TF.TOOLS),
        "rows": rows_out,
        "probes": probes,
        "n_probes": len(probes),
    }


def write(doc: dict, path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, indent=1) + "\n").encode("utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if OUT.exists() and "--dry-run" not in argv and "--rebuild" not in argv:
        print(f"{OUT.relative_to(ROOT).as_posix()} exists; pass --rebuild to rewrite it")
        return 1
    doc = build()
    for k, blk in doc["coverage"].items():
        print(f"  {k:9s} rows {blk['rows']:5d}  id {blk['id_resolved']:5d}  "
              f"cons {blk['consensus']}  pwr_comp {blk['pwr_comp_inputs']:4d}  "
              f"tip {blk['tip_iso_resid']:4d}  hit_w {blk['tool_hit_w_inputs']}")
    for V, t in doc["tip_tables"].items():
        print(f"  table {V}: fit rows {t['fit_rows']}  bins {t['bins_kept']}  "
              f"max season {t['fit_max_season']}  career {t['career_seasons']}")
    print(f"R-VM rows dropped: {doc['rvm_rows_dropped']}")
    print(f"pwr_comp: {doc['pwr_comp']['reason']}")
    if "--dry-run" not in argv:
        write(doc)
        print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

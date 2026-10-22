# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Assemble eWAR v3 and eWAR realized (docs/ebr-2026-09-30/EBR_GATE.md parts 9.2,
9.7 and amendment 11.10; task EWAR_V3_ASSEMBLE, which folded EBR_3_EWAR_V3).

    python tools/build_ewar_v3.py            # build and print the census, write nothing
    python tools/build_ewar_v3.py --write    # write data/ewar_v3.json (EWAR_V3_LIVE on)
                                             # or .cache/ewar_v3/preview/ewar_v3.json (off)
    python tools/build_ewar_v3.py --xhem-preview   # the build WITH the xHEM+ part, whatever
                                             # ewar_v3.XHEM_HALF_LIVE says, written to
                                             # .cache/ewar_v3/preview/ewar_v3_xhem.json only

WHAT IT READS (caches and committed artifacts only; nothing is fetched):
  - the frozen fWAR vintage, data/fwar_vintage.json: the base of both series, the
    hitting rows' plate appearances and the pitching rows' outs (the re-centring
    exposures);
  - the eABS frame, through eabs_export.frame (the ABS challenge ledger
    data/_labs/abs_ledger/mlb_2026.json, data/count_value.json and the 2026
    pbp corpus plays): each zone challenge's value v and failure cost c;
  - data/fielding_innings.json: innings at C (the catcher exposure of the move);
  - the swar preview build the looks read, .cache/swar/preview/swar.json: R2's
    re-pinned Delta_r per pitcher-season (EBR_GATE.md 11.3.3), on the same vintage
    id (a different id stops the build);
  - data/rpw_fit.json: the runs-per-win candidate RPW_GATE.md carries forward;
  - with the xHEM+ part on (ewar_v3.XHEM_HALF_LIVE, or --xhem-preview), the same swar
    preview's candidate part 4 xHEM+ arm: the re-centred d_batx per hitter-season and
    the season's runs per win (EBR_GATE.md 11.11.1).

WHAT IT WRITES: one file (above). The admitted parts are part 12.1 to 12.3's
(none) plus the ABS part by owner override (11.10.2); R2 enters eWAR realized only.
With the flag on, the xHEM+ part (11.11, owner decision EW3-51, taken while the
registered admission rule was not met) enters the headline series' hitting side,
2016 on, at LAMBDA 0.5: x = 0.5 * d_batx / RPW*_s, RPW*_s the skill look's own
conversion (league_constants.league_totals(s)["rpw"]). Off, the file is the one
this builder wrote before 11.11.

THE RPW TEAM GUARD (RPW_GATE.md part 4, EBR_GATE.md 11.10.4). Computed once here
as an identity: on the guard's predictor seasons (2021 to 2024) the headline
series carries no departure, so the candidate's series equals the frame's on
every row and dT is 0 under both bootstraps. The build checks that, and only
then carries the candidate's RPW; no WAR sum is related to a club outcome. The
xHEM+ part does not touch the identity: it converts at RPW*_s whichever RPW_s the
series carries, so the two series still differ only in the ABS part.

STOPS (EwarV3Refusal, nothing written): a vintage season not frozen, the preview
on another vintage id, a catcher with challenge wins and no innings at C, any
zero-sum identity off by more than 1e-9, or data/ewar.json's sha256 moving.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ewar_v3 as V3                     # noqa: E402
import fwar_vintage                      # noqa: E402
import league_constants as LCM           # noqa: E402
import war_source                        # noqa: E402

PREVIEW_SWAR = ROOT / ".cache" / "swar" / "preview" / "swar.json"
RPW_FIT = ROOT / "data" / "rpw_fit.json"
FIELDING = ROOT / "data" / "fielding_innings.json"
EWAR_V2 = ROOT / "data" / "ewar.json"
GUARD_SEASONS = (2021, 2022, 2023, 2024)


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _rows(block: dict) -> dict[int, dict]:
    fields = list(block.get("fields") or [])
    return {int(mid): dict(zip(fields, vals)) for mid, vals in (block.get("rows") or {}).items()}


class Inputs:
    """Every input, one method each, so a test can supply fixtures."""

    def vintage(self) -> dict:
        if not fwar_vintage.available():
            raise V3.EwarV3Refusal("the frozen fWAR vintage (data/fwar_vintage.json) is absent")
        return fwar_vintage.load()

    def challenges(self, season: int) -> list[dict]:
        """The eABS frame's rows for `season` (2026 only today)."""
        if season != 2026:
            return []
        import eabs_export
        fr = eabs_export.frame()
        return [{"role": r.get("role"), "challenge_side": r.get("challenge_side"),
                 "challenger_id": r.get("challenger_id"), "pitcher_id": r.get("pitcher_id"),
                 "o": r["o"], "v": r["v"], "c": r["c_fail"]} for r in fr["rows"]]

    def catcher_innings(self, season: int) -> dict[int, float]:
        blob = json.loads(FIELDING.read_text(encoding="utf-8"))
        rows = (blob.get("seasons") or {}).get(str(int(season))) or {}
        return {int(mid): float(((byp or {}).get("C") or {}).get("inn") or 0.0) for mid, byp in rows.items()}

    def r2(self) -> tuple[dict[int, dict[int, float]], dict]:
        """({season: {mlbam: Delta_r}}, receipt) from the swar preview."""
        if not PREVIEW_SWAR.exists():
            raise V3.EwarV3Refusal(f"the swar preview is absent ({PREVIEW_SWAR}); build it: python tools/build_swar.py")
        doc = json.loads(PREVIEW_SWAR.read_text(encoding="utf-8"))
        out: dict[int, dict[int, float]] = {}
        zs: dict[str, float] = {}
        for s, blk in (doc.get("seasons") or {}).items():
            sd = {}
            zs[str(s)] = (((blk.get("checks") or {}).get("pitch_basis") or {}).get("zero_sum") or {}).get("realized")
            for r in blk.get("pitchers") or []:
                d = ((r.get("parts") or {}).get("realized") or {}).get("delta")
                if d is not None and not r.get("nopp"):
                    sd[int(r["mlbam"])] = float(d)
            out[int(s)] = sd
        rec = {"path": ".cache/swar/preview/swar.json", "sha256": _sha(PREVIEW_SWAR),
               "generated_at": doc.get("generated_at"), "fwar_vintage_id": doc.get("fwar_vintage_id"),
               "seasons": sorted(out), "zero_sum": zs}
        return out, rec

    def rpw_fit(self) -> dict:
        return json.loads(RPW_FIT.read_text(encoding="utf-8"))

    def xhem(self) -> tuple[dict[int, dict], dict]:
        """({season: {"rpw": RPW*_s, "rows": {mlbam: {"d": runs, "pa", "arm", "pb"}}}},
        receipt) from the swar preview: candidate part 4's xHEM+ arm (EBR_GATE.md 9.4
        S1x), re-centred, as the skill look read it (11.11.1)."""
        if not PREVIEW_SWAR.exists():
            raise V3.EwarV3Refusal(f"the swar preview is absent ({PREVIEW_SWAR}); build it: python tools/build_swar.py")
        doc = json.loads(PREVIEW_SWAR.read_text(encoding="utf-8"))
        out: dict[int, dict] = {}
        for s, blk in (doc.get("seasons") or {}).items():
            rows = {}
            for r in blk.get("hitters") or []:
                bx = (r.get("parts") or {}).get("batx") or {}
                if bx.get("d") is None:
                    continue
                rows[int(r["mlbam"])] = {"d": float(bx["d"]), "pa": float(r.get("pa") or 0.0),
                                         "arm": bx.get("arm"), "pb": bool(r.get("pitcher_batter"))}
            out[int(s)] = {"rpw": float(blk["rpw"]), "rows": rows}
        rec = {"path": ".cache/swar/preview/swar.json", "sha256": _sha(PREVIEW_SWAR),
               "generated_at": doc.get("generated_at"), "fwar_vintage_id": doc.get("fwar_vintage_id"),
               "seasons": sorted(out)}
        return out, rec


def _incumbent_rpw(season: int) -> float:
    return float(LCM.league_totals(int(season))["rpw"])


def xhem_terms(season: int, src: dict, bat_rows: set, lam: float) -> tuple[dict[int, dict], dict]:
    """The xHEM+ part for one season (EBR_GATE.md 11.11.1), in wins on the hitting
    side: x = lam * d_batx / RPW*_s, the stored d re-centred once more per PA over
    the rule's rows (pitcher-batters outside it) so the part sums to zero exactly.
    A preview hitter with no hitting row in the vintage stops the build."""
    rows = src["rows"]
    gap = sorted(m for m in rows if m not in bat_rows)
    if gap:
        raise V3.EwarV3Refusal(f"{season}: {len(gap)} xHEM+ hitters have no hitting row in the vintage")
    rpw_s = float(src["rpw"])
    if not rpw_s > 0:
        raise V3.EwarV3Refusal(f"{season}: the preview's runs per win is {rpw_s!r}")
    inside = {m: r for m, r in rows.items() if not r["pb"]}
    d = V3.recentre({m: r["d"] for m, r in inside.items()}, {m: r["pa"] for m, r in inside.items()})
    out = {}
    for m, r in inside.items():
        w = lam * d[m] / rpw_s
        if w != 0.0:
            out[m] = {"runs": d[m], "wins": w, "arm": r["arm"]}
    tot = sum(v["wins"] for v in out.values())
    if abs(tot) > V3.TOL:
        raise V3.EwarV3Refusal(f"{season}: the xHEM+ part sums to {tot} wins, not zero")
    rec = {"lambda": lam, "rpw_star": rpw_s, "rows": len(out),
           "xhem_arm_rows": sum(1 for v in out.values() if v["arm"] == "xhem"),
           "hem_arm_rows": sum(1 for v in out.values() if v["arm"] != "xhem"),
           "pitcher_batters": len(rows) - len(inside),
           "stored_sum_runs": sum(r["d"] for r in inside.values()),
           "sum_wins": tot}
    return out, rec


def build(inp: Inputs | None = None, log=print, xhem: bool | None = None) -> dict:
    """The payload. `xhem` None follows ewar_v3.XHEM_HALF_LIVE; True or False forces
    the xHEM+ part on or off (the --xhem-preview census and the tests)."""
    inp = inp or Inputs()
    xhem_on = V3.XHEM_HALF_LIVE if xhem is None else bool(xhem)
    ewar_sha_before = _sha(EWAR_V2)
    vin = inp.vintage()
    vid = str(vin.get("vintage_id") or "")
    seasons = fwar_vintage.fwar_seasons(vin)
    if not seasons:
        raise V3.EwarV3Refusal("the vintage has no frozen season")

    # --- the exposures and the fWAR sides, per season
    hit_pa, pit_ip, fside = {}, {}, {}
    for s in seasons:
        sb = (vin.get("seasons") or {}).get(str(s)) or {}
        h, p = _rows(sb.get("hitting") or {}), _rows(sb.get("pitching") or {})
        hit_pa[s] = {mid: float(r.get("plateAppearances") or 0.0) for mid, r in h.items()}
        pit_ip[s] = {mid: float(r.get("outs") or 0.0) / 3.0 for mid, r in p.items()}
        fside[s] = {"bat": {mid: float(r["war"]) for mid, r in h.items() if r.get("war") is not None},
                    "pit": {mid: float(r["war"]) for mid, r in p.items() if r.get("war") is not None}}

    # --- the ABS part (runs), by season
    abs_by: dict[int, dict] = {}
    for s in seasons:
        if s < V3.ABS_FIRST_SEASON:
            continue
        ch = inp.challenges(s)
        if not ch:
            continue
        abs_by[s] = V3.abs_terms(ch, hit_pa[s], pit_ip[s], inp.catcher_innings(s))

    # --- R2 (wins), by season
    r2_by, r2_rec = inp.r2()
    if str(r2_rec.get("fwar_vintage_id") or "") != vid:
        raise V3.EwarV3Refusal(f"the swar preview is on vintage {r2_rec.get('fwar_vintage_id')}, "
                               f"not {vid}; rebuild it: python tools/build_swar.py")

    # --- the xHEM+ part (wins, hitting side, headline only), by season (11.11)
    xh_by: dict[int, tuple] = {}
    xh_rec: dict = {}
    if xhem_on:
        xsrc, xh_rec = inp.xhem()
        if str(xh_rec.get("fwar_vintage_id") or "") != vid:
            raise V3.EwarV3Refusal(f"the swar preview is on vintage {xh_rec.get('fwar_vintage_id')}, "
                                   f"not {vid}; rebuild it: python tools/build_swar.py")
        for s in seasons:
            if s < V3.XHEM_FIRST_SEASON:
                continue
            if s not in xsrc:
                raise V3.EwarV3Refusal(f"{s}: the swar preview carries no xHEM+ arm for this season")
            xh_by[s] = xhem_terms(s, xsrc[s], set(fside[s]["bat"]), V3.XHEM_LAMBDA)

    # --- runs per win: the candidate RPW_GATE carries forward, behind the guard
    fit = inp.rpw_fit()
    verdict = fit.get("verdict") or {}
    guard_rows = sum(1 for s in GUARD_SEASONS if s in abs_by)
    cand = verdict.get("candidate")
    cand_rpw = {int(k): float(v) for k, v in (verdict.get("rpw_by_season") or {}).items()}
    if str(verdict.get("status") or "").startswith("PRIMARY PASS") and cand and guard_rows == 0:
        rpw_form = cand
        how = ("identity: the headline series carries no departure on predictor seasons 2021 to 2024 "
               "(the ABS part begins in 2026), so the candidate's series equals the frame's on every "
               "row; dT is 0 under both bootstraps with sd 0; no WAR sum was related to a club outcome")
        if xh_by:
            how = ("identity: the ABS part, the only departure converted at RPW_s, carries no row on "
                   "predictor seasons 2021 to 2024 (it begins in 2026); the xHEM+ part converts at the "
                   "skill look's own runs per win whichever RPW_s is chosen (EBR_GATE.md 11.11.1), so "
                   "the candidate's series equals the frame's on every row; dT is 0 under both "
                   "bootstraps with sd 0; no WAR sum was related to a club outcome")
        guard = {"status": "NON-INFERIOR", "how": how,
                 "seasons": list(GUARD_SEASONS), "departure_rows": 0}
    else:
        rpw_form = "incumbent"
        guard = {"status": "NOT COMPUTED" if not cand else "NOT AN IDENTITY",
                 "how": "the incumbent stands", "seasons": list(GUARD_SEASONS),
                 "departure_rows": guard_rows}

    # (c) is one constant, 1 / beta, for every season (RPW_GATE.md part 4); the
    # verdict lists 2016 to 2026, and a season outside that list takes the same value
    cand_const = ((fit.get("full_fit") or {}).get("c") or {}).get("rpw") if cand == "c" else None

    def rpw(s: int) -> float:
        if rpw_form != "incumbent":
            if s in cand_rpw:
                return cand_rpw[s]
            if cand_const:
                return float(cand_const)
        return _incumbent_rpw(s)

    # --- assemble
    players: dict[str, dict] = {}
    checks: dict[str, dict] = {}
    for s in seasons:
        ab = abs_by.get(s)
        r2s = r2_by.get(s, {}) if s >= V3.R2_FIRST_SEASON else {}
        r_s = rpw(s)
        xs, xs_rec = xh_by.get(s, ({}, None))
        sums = {"dh_bat": 0.0, "dh_pit": 0.0, "dr_bat": 0.0, "dr_pit": 0.0, "r2": 0.0,
                "abs_bat_runs": 0.0, "abs_pit_runs": 0.0, "rows": 0, "xhem": 0.0}
        mids = set(fside[s]["bat"]) | set(fside[s]["pit"])
        r2_gap = sorted(m for m in r2s if m not in fside[s]["pit"])
        if r2_gap:
            raise V3.EwarV3Refusal(f"{s}: {len(r2_gap)} R2 pitchers have no pitching row in the vintage")
        # the preview stores Delta_r to 6 decimals, so its season sum carries
        # rounding of at most 5e-7 a row; the preview's own unrounded check is
        # carried beside (checks[season].r2_preview_zero_sum)
        r2_tol = max(1e-6, 5e-7 * len(r2s))
        for mid in mids:
            blk = {"f": {}, "dh": {}, "dr": {}}
            parts = {}
            a_ws: dict = {}
            for side in V3.SIDES:
                if mid not in fside[s][side]:
                    continue
                blk["f"][side] = round(fside[s][side][mid], 6)
                a = (ab or {}).get(side, {}).get(mid) if ab else None
                a_runs = float(a["runs"]) if a else 0.0
                a_w = a_runs / r_s
                r2 = float(r2s.get(mid, 0.0)) if side == "pit" else 0.0
                if a and (abs(a_runs) > 0.0):
                    parts.setdefault("abs", {})[side] = {k: round(float(v), 6) for k, v in a.items()}
                    parts["abs"][side]["wins"] = round(a_w, 6)
                if side == "pit" and r2 != 0.0:
                    parts["r2"] = round(r2, 6)
                x = xs.get(mid) if side == "bat" else None
                x_w = float(x["wins"]) if x else 0.0
                if x:
                    parts["xhem"] = {"runs": round(float(x["runs"]), 6), "wins": round(x_w, 6),
                                     "arm": x["arm"]}
                a_ws[side] = a_w
                sums["xhem"] += x_w
                dh, dr = a_w + x_w, a_w + r2
                sums["dh_" + side] += dh
                sums["dr_" + side] += dr
                sums["r2"] += r2
                sums["abs_%s_runs" % side] += a_runs
                if dh != 0.0:
                    blk["dh"][side] = round(dh, 6)
                if dr != 0.0:
                    blk["dr"][side] = round(dr, 6)
            if "xhem" in parts:
                # the headline without the xHEM+ part (the eFV label's basis, 11.11.3):
                # every side's departure is then the ABS part alone, stored as dh was
                blk["dx"] = {side: round(w, 6) for side, w in a_ws.items() if w != 0.0}
            if blk["dh"] or blk["dr"]:
                if parts:
                    blk["parts"] = parts
                players.setdefault(str(mid), {})[str(s)] = blk
                sums["rows"] += 1
        for k in ("dh_bat", "dh_pit", "dr_bat", "abs_bat_runs", "abs_pit_runs"):
            if abs(sums[k]) > 1e-6:
                raise V3.EwarV3Refusal(f"{s}: {k} sums to {sums[k]}, not zero")
        if abs(sums["dr_pit"]) > r2_tol + 1e-6:
            raise V3.EwarV3Refusal(f"{s}: dr_pit sums to {sums['dr_pit']}, beyond the rounding bound {r2_tol}")
        checks[str(s)] = {"rpw": r_s, "rows_listed": sums["rows"],
                          "sum_departure_wins": {k: sums[k] for k in ("dh_bat", "dh_pit", "dr_bat", "dr_pit")},
                          "sum_r2_wins": sums["r2"],
                          "sum_abs_runs": {"bat": sums["abs_bat_runs"], "pit": sums["abs_pit_runs"]},
                          "fwar_total": {side: sum(fside[s][side].values()) for side in V3.SIDES},
                          "r2_rows": len(r2s), "r2_rounding_bound": r2_tol,
                          "r2_preview_zero_sum": (r2_rec.get("zero_sum") or {}).get(str(s))}
        if ab:
            checks[str(s)]["abs_receipt"] = ab["receipt"]
        if xs_rec is not None:
            checks[str(s)]["xhem_receipt"] = dict(xs_rec, sum_listed_wins=sums["xhem"])

    if _sha(EWAR_V2) != ewar_sha_before:
        raise V3.EwarV3Refusal("data/ewar.json moved during the build")

    meta = {
        "what_this_is": ("eWAR v3: the frozen published fWAR vintage plus named departures, each zero-sum per "
                         "season and side. The headline eWAR carries the ABS part (owner override EW3-32, 2026 "
                         "on); eWAR realized adds the realized pitching basis R2 (2016 on). A player-season "
                         "not listed here carries fWAR unchanged on both series."),
        "admitted_by_look": [],
        "looks": {"outcome": "EBR_GATE.md part 12.1 (2026-10-19): candidate parts 1 and 2 not admitted",
                  "skill": "EBR_GATE.md part 12.2 (2026-10-19): candidate parts 3 to 6, PE-P and PE-H not admitted",
                  "holdout": "EBR_GATE.md part 12.3 (2026-10-21): changes no admission"},
        "parts": {
            "eabs": {"label": V3.PART_LABELS["eabs"], "series": ["headline", "realized"],
                     "how": "owner override EW3-32 (EBR_GATE.md 11.10.2; EABS_GATE.md 9.2), not a look",
                     "first_season": V3.ABS_FIRST_SEASON, "unit": "runs, converted at RPW_s"},
            "r2": {"label": V3.PART_LABELS["r2"], "series": ["realized"],
                   "how": "EBR_GATE.md 11.3.3 and 11.10.3: eWAR realized prices pitchers on R2",
                   "first_season": V3.R2_FIRST_SEASON, "unit": "wins (the replica chain's own conversion)",
                   "source": r2_rec},
        },
        "fg_components": ("batting, baserunning, fielding and framing, the positional adjustment and pitching "
                          "are FanGraphs' published components (no look-decided part is admitted)"
                          + ("; the headline series' batting also carries half of the xHEM+ part from "
                             f"{V3.XHEM_FIRST_SEASON} (owner decision EW3-51, provisional)" if xh_by else "")),
        "fielding_source": "Its fielding is FanGraphs' published fielding and framing (Fld and Frm), the frame of this board.",
        "baserunning_source": "Its baserunning is FanGraphs' published BsR, the column beside eBR here.",
        "rpw": {"form": rpw_form, "candidate": cand, "guard": guard,
                "by_season": {str(s): rpw(s) for s in seasons},
                "incumbent": "league_constants.league_totals(s)['rpw'], FanGraphs' closed form",
                "source": "data/rpw_fit.json (docs/ewar/RPW_GATE.md)"},
        "not_listed": "fWAR on both series",
        "labels": {"headline": "eWAR", "realized": "eWAR realized"},
    }
    if xh_by:
        meta["what_this_is"] = meta["what_this_is"].replace(
            "The headline eWAR carries the ABS part (owner override EW3-32, 2026 on);",
            "The headline eWAR carries the ABS part (owner override EW3-32, 2026 on) and, provisionally, "
            f"half of the xHEM+ batting part ({V3.XHEM_FIRST_SEASON} on, owner decision EW3-51);")
        meta["parts"]["xhem"] = {
            "label": V3.PART_LABELS["xhem"], "series": ["headline"],
            "how": ("owner decision EW3-51 (EBR_GATE.md 11.11), taken while the registered admission rule "
                    "was not met: the skill look read the xHEM+ arm WIN (components) but its team guard "
                    "NOT NON-INFERIOR (underpowered), and the holdout read UNRESOLVED; not a look"),
            "lambda": V3.XHEM_LAMBDA, "first_season": V3.XHEM_FIRST_SEASON,
            "unit": ("runs (candidate part 4's re-centred d_batx), converted at the skill look's own runs per "
                     "win, league_constants.league_totals(s)['rpw'], then halved"),
            "rows_rule": ("EBR_GATE.md 9.4 S1x as scored: the xHEM+ arm at 200 PA or more with a Savant xwOBA, "
                          "the HEM+ arm's value on every other hitter-season, pitcher-batters 0"),
            "provisional": True, "copy": V3.xhem_copy(),
            "keep_or_remove": ("EWAR_XHEM_2027_READ, not before 2027-11-10 (EBR_GATE.md 11.11.5): KEEP if the "
                               "gap's one-sided 95 percent lower bound is above 0 and the team guard is "
                               "NON-INFERIOR; otherwise the flag goes False"),
            "label_basis": ("the eFV label reads the headline without this part (dx); its frozen vintage "
                            "does not move (11.11.3)"),
            "source": xh_rec,
        }
    payload = {
        "schema": 1,
        "model": "ewar_v3",
        "version": V3.VERSION,
        "generated_at": _now(),
        "registration": V3.GATE_DOC + " parts 9.2, 9.7, 11.10",
        "fwar_vintage_id": vid,
        "fwar_vintage_sha256": _sha(fwar_vintage.VINTAGE_PATH),
        "seasons": [min(seasons), max(seasons)],
        "ewar_json_sha256": ewar_sha_before,
        "field_key": {"f": "published fWAR per side (bat: hitting group, pit: pitching group)",
                      "dh": "headline eWAR minus fWAR per side, wins",
                      "dr": "eWAR realized minus fWAR per side, wins",
                      "parts.abs": "the ABS part per side: runs terms (move, cost on bat; charge, cost on pit), "
                                   "raw and re-centred, runs and wins",
                      "parts.r2": "R2's Delta_r, wins (realized only)",
                      **({"parts.xhem": ("the xHEM+ part on the hitting side, headline only: its re-centred "
                                         "runs, its wins at LAMBDA 0.5 and the arm the row took"),
                          "dx": ("headline eWAR minus fWAR per side without the xHEM+ part, on a block that "
                                 "carries it (the eFV label's basis); a side not listed departs by 0")}
                         if xh_by else {})},
        "meta": meta,
        "checks": checks,
        "players": players,
    }
    return payload


def write(payload: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path


def census(payload: dict, log=print) -> None:
    m = payload["meta"]
    log(f"eWAR v3 {payload['version']} on fWAR vintage {payload['fwar_vintage_id']}; "
        f"seasons {payload['seasons'][0]} to {payload['seasons'][1]}")
    log(f"  rpw form {m['rpw']['form']} (candidate {m['rpw']['candidate']}); guard {m['rpw']['guard']['status']}")
    for s, c in sorted(payload["checks"].items()):
        if not c["rows_listed"]:
            continue
        line = (f"  {s}: rows listed {c['rows_listed']}, rpw {c['rpw']:.4f}, "
                f"sum dh {c['sum_departure_wins']['dh_bat']:+.2e}/{c['sum_departure_wins']['dh_pit']:+.2e}, "
                f"sum dr {c['sum_departure_wins']['dr_bat']:+.2e}/{c['sum_departure_wins']['dr_pit']:+.2e}")
        if c.get("xhem_receipt"):
            x = c["xhem_receipt"]
            line += (f"; xhem rows {x['rows']} ({x['xhem_arm_rows']} on the xHEM+ arm), "
                     f"rpw* {x['rpw_star']:.4f}, sum {x['sum_wins']:+.2e}")
        if c.get("abs_receipt"):
            r = c["abs_receipt"]
            line += (f"; abs challenges {r['challenges']}, catcher-won runs {r['catcher_won_runs']:.1f}, "
                     f"failure cost {r['failure_cost_runs']:.1f}, gaps move {r['gap_move']} charge {r['gap_charge']}")
        log(line)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--xhem-preview", action="store_true",
                    help="build with the xHEM+ part and write it under .cache/ewar_v3/preview/ only")
    a = ap.parse_args(argv)
    if a.xhem_preview and a.write:
        print("REFUSED: --xhem-preview writes the preview only; run --write on its own")
        return 2
    try:
        payload = build(xhem=True if a.xhem_preview else None)
    except V3.EwarV3Refusal as e:
        print(f"REFUSED: {e}")
        return 2
    census(payload)
    if a.xhem_preview:
        write(payload, V3.PREVIEW_XHEM)
        print(f"written {V3.PREVIEW_XHEM}")
        return 0
    if a.write:
        path = V3.OUT if war_source.EWAR_V3_LIVE else V3.PREVIEW
        write(payload, path)
        print(f"written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_rpw_fit - runs per win fitted from team outcomes (rpw_fit_v1).

docs/ewar/RPW_GATE.md (task EWAR_RPW_FIT, owner decision EW3-24). Reads, never fetches
and never writes a cache:
  .cache/statsapi_standings_<Y>.json          wins, losses, runs scored and allowed
  .cache/team_stats/<Y>_pit.json              StatsAPI team id to club code
  .cache/fangraphs/park_factors_<Y>.json      FanGraphs Guts Basic (5yr)
  .cache/war_daily/bat.parquet, pit.parquet   Baseball-Reference (candidate e, part 5)
  league_constants.league_totals(Y)           the incumbent rpw and lg_ra9
Writes data/rpw_fit.json (or --out). Every refusal of gate part 6 is checked before
anything is written; a miss raises rpw_fit.RpwRefusal and writes nothing.

Run:  python tools/build_rpw_fit.py [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import rpw_fit as rf  # noqa: E402

CACHE = ROOT / ".cache"
OUT = ROOT / "data" / "rpw_fit.json"
DIGITS = 4


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _r(x, d: int = DIGITS):
    if x is None:
        return None
    return round(float(x), d)


# ------------------------------------------------------------------ inputs
def standings(season: int, cache: Path = CACHE) -> tuple[list[dict], dict]:
    sp = cache / f"statsapi_standings_{season}.json"
    tp = cache / "team_stats" / f"{season}_pit.json"
    blob = json.loads(sp.read_text(encoding="utf-8"))
    club_of = {r["team_id"]: r["club"] for r in json.loads(tp.read_text(encoding="utf-8"))["rows"]}
    clubs = []
    for rec in blob.get("records") or []:
        for t in rec.get("teamRecords") or []:
            tid = t["team"]["id"]
            if tid not in club_of:
                raise rf.RpwRefusal(f"{season}: team id {tid} has no club code")
            clubs.append({"season": season, "club": club_of[tid], "team_id": tid,
                          "w": int(t["wins"]), "l": int(t["losses"]),
                          "rs": int(t["runsScored"]), "ra": int(t["runsAllowed"])})
    rf.check_season(season, clubs)
    return clubs, {"standings": _sha(sp), "team_stats_pit": _sha(tp)}


def park_factors(season: int, cache: Path = CACHE) -> tuple[dict, int, str]:
    """{team_id: Basic (5yr) / 100} from the latest COMPLETE file at or before `season`."""
    for s in range(season, season - 6, -1):
        p = cache / "fangraphs" / f"park_factors_{s}.json"
        if not p.exists():
            continue
        blob = json.loads(p.read_text(encoding="utf-8"))
        if not blob.get("complete"):
            continue
        pf = {int(r["team_id"]): float(r["Basic (5yr)"]) / 100.0 for r in blob["rows"]}
        if len(pf) != rf.CLUBS_PER_SEASON:
            raise rf.RpwRefusal(f"park factors {s}: {len(pf)} clubs")
        return pf, s, _sha(p)
    raise rf.RpwRefusal(f"{season}: no complete park-factor file in the six seasons before it")


def bref_frames(cache: Path = CACHE):
    import pandas as pd  # noqa: PLC0415
    bp = cache / "war_daily" / "bat.parquet"
    pp = cache / "war_daily" / "pit.parquet"
    meta = {}
    for name, p in (("bat", bp), ("pit", pp)):
        meta[name] = {"sha256": _sha(p),
                      "mtime": _dt.datetime.fromtimestamp(os.path.getmtime(p), _dt.timezone.utc)
                      .replace(microsecond=0).isoformat()}
    return pd.read_parquet(bp), pd.read_parquet(pp), meta


def bref_rpw(bat, pit) -> tuple[dict, dict]:
    import ewar  # noqa: PLC0415
    return ewar.runs_per_win(bat, pit)


def _fold(club: str) -> str:
    return "OAK" if club == "ATH" else club


def stints(pit, seasons) -> list[dict]:
    import pandas as pd  # noqa: PLC0415
    d = pit[["year_ID", "team_ID", "player_ID", "G", "IPouts", "RA"]].copy()
    d["year_ID"] = pd.to_numeric(d["year_ID"], errors="coerce")
    d = d[d["year_ID"].isin(list(seasons))]
    out = []
    for r in d.itertuples(index=False):
        club = "ATH" if str(r.team_ID) == "OAK" else str(r.team_ID)
        out.append({"season": int(r.year_ID), "club": club, "pid": str(r.player_ID),
                    "g": float(pd.to_numeric(r.G, errors="coerce") or 0.0),
                    "outs": float(pd.to_numeric(r.IPouts, errors="coerce") or 0.0),
                    "ra": float(pd.to_numeric(r.RA, errors="coerce") or 0.0)})
    return out


# ------------------------------------------------------------------ the build
def build(cache: Path = CACHE, log=print) -> dict:
    import league_constants  # noqa: PLC0415

    bat, pit, wd_meta = bref_frames(cache)
    log(f"war_daily bat sha256 {wd_meta['bat']['sha256']} mtime {wd_meta['bat']['mtime']}")
    log(f"war_daily pit sha256 {wd_meta['pit']['sha256']} mtime {wd_meta['pit']['mtime']}")
    by_team, by_season = bref_rpw(bat, pit)

    rows_all: dict[int, list[dict]] = {}
    digests: dict = {"war_daily": wd_meta, "seasons": {}}
    lg_ra9: dict = {}
    L_s: dict = {}
    pf_used: dict = {}
    fg_rpw: dict = {}
    bref_fallbacks = []
    for s in rf.ALL_SEASONS:
        clubs, dg = standings(s, cache)
        lt = league_constants.league_totals(s)
        if not lt:
            raise rf.RpwRefusal(f"{s}: league_constants.league_totals returned nothing")
        pf, pf_season, pf_sha = park_factors(s, cache)
        fg_rpw[s] = float(lt["rpw"])
        lg_ra9[s] = float(lt["lg_ra9"])
        L_s[s] = rf.league_rpg(clubs)
        pf_used[s] = pf_season
        digests["seasons"][str(s)] = {**dg, "park_factors_season": pf_season, "park_factors": pf_sha}
        for c in clubs:
            v = by_team.get((s, _fold(c["club"])))
            if v is None:
                v = by_season.get(s, 9.7)
                bref_fallbacks.append(f"{s} {c['club']}")
            c.update({"pf": pf[c["team_id"]], "rpw_fg": fg_rpw[s], "rpw_bref": float(v),
                      "L": L_s[s]})
        rows_all[s] = clubs
        log(f"{s}: 30 clubs, L {L_s[s]:.4f}, closed-form rpw {fg_rpw[s]:.4f}, "
            f"park file {pf_season}")

    prim_rows = [c for s in rf.PRIMARY_SEASONS for c in rows_all[s]]
    f = rf.frame(prim_rows)
    n = len(f["g"])
    if n != 300:
        raise rf.RpwRefusal(f"primary frame has {n} team-seasons, expected 300")

    # Part 5's ledger is a refusal (part 6, 2), so it runs before any statistic.
    st = stints(pit, rf.PRIMARY_SEASONS)
    arms = rf.pitcher_arms(f, st, lg_ra9)
    log(f"part 5 ledger: stint runs allowed reconcile on all {n} club-seasons; "
        f"arm L vs (a) max {arms['arm_l_max_abs_vs_a']:.3g} wins")

    cands = ("a", "b", "c", "d", "e", "r0", "r1")
    held = rf.loso(f, cands)
    err = {c: held[c]["pred"] - f["w"] for c in cands}
    idx = rf.boot_index(n)

    per_cand = {}
    for c in cands:
        e = err[c]
        per_season = {}
        for s in rf.PRIMARY_SEASONS:
            m = f["season"] == s
            per_season[str(s)] = {"mae": _r(rf.mae(e[m])), "rmse": _r(rf.rmse(e[m]))}
        per_cand[c] = {"name": rf.NAMES[c], "mae": _r(rf.mae(e)), "rmse": _r(rf.rmse(e)),
                       "mean_error": _r(float(np.mean(e))), "void": held[c]["void"],
                       "per_season": per_season}
        if c in ("b", "c", "d"):
            per_cand[c]["held_out_fits"] = {
                str(s): ({"z": p["z"]} if c == "b" else
                         {"beta": _r(p["beta"], 6), "rpw": _r(p["rpw"])} if c == "c" else
                         {"coef": [_r(x, 6) for x in p["coef"]]})
                for s, p in held[c]["fits"].items()}
        log(f"({c}) {rf.NAMES[c]}: held-out MAE {rf.mae(e):.4f} RMSE {rf.rmse(e):.4f} wins"
            + (" VOID" if held[c]["void"] else ""))

    contrasts = {}
    for c in rf.CHALLENGERS:
        k = rf.contrast(err["a"], err[c], idx)
        contrasts[c] = {kk: _r(v) for kk, v in k.items()}
        contrasts[c]["primary_pass"] = (not held[c]["void"]) and k["lo95"] > 0.0
        log(f"dMAE (a) - ({c}): {k['d_mae']:+.4f} sd {k['sd']:.4f} lo95 {k['lo95']:+.4f} "
            f"hi95 {k['hi95']:+.4f} p {k['p_le_0']:.4f} -> "
            + ("PRIMARY PASS" if contrasts[c]["primary_pass"] else "no pass"))
    raw_contrasts = {c: rf.contrast(err["a"], err[c], idx) for c in rf.CHALLENGERS}
    hl = rf.holm({c: raw_contrasts[c]["p_le_0"] for c in rf.CHALLENGERS})
    ver = rf.verdict(raw_contrasts, {c: held[c]["void"] for c in rf.CHALLENGERS})
    log(f"verdict: {ver['status']} (candidate {ver['candidate']})")

    # Full fits on all ten primary seasons, and what each candidate supplies per season.
    full = {c: rf.fit(c, f) for c in ("b", "c", "d")}
    supplies = {}
    for c in ("a", "b", "c", "d", "e"):
        supplies[c] = {str(s): _r(rf.league_rpw(c, full.get(c, {}), L_s[s],
                                                bref_season=by_season.get(s),
                                                fg_season=fg_rpw[s]))
                       for s in rf.ALL_SEASONS}
    full_out = {"b": {"z": full["b"]["z"]},
                "c": {"beta": _r(full["c"]["beta"], 6), "rpw": _r(full["c"]["rpw"])},
                "d": {"coef": [_r(x, 6) for x in full["d"]["coef"]],
                      "terms": ["RD", "RD (L - 9)", "RD (T - L)", "RD (PF - 1)"]}}
    marg = rf.pythag_marginal_rpw(f["rs"], f["ra"], f["g"], full["b"]["z"])
    d_team = rf.team_rpw("d", full["d"], f)
    team_env = {
        "b_marginal_rpw": {"min": _r(marg.min()), "median": _r(np.median(marg)), "max": _r(marg.max())},
        "d_team_rpw": {"min": _r(d_team.min()), "median": _r(np.median(d_team)), "max": _r(d_team.max())},
        "e_team_rpw": {"min": _r(f["rpw_bref"].min()), "median": _r(np.median(f["rpw_bref"])),
                       "max": _r(f["rpw_bref"].max())},
    }

    # Per-season slopes (reported, deciding nothing), every season 2016 to 2026.
    slopes = {}
    for s in rf.ALL_SEASONS:
        fs = rf.frame(rows_all[s])
        b = rf.fit_slope(fs["rd"], fs["g"], fs["w"])
        slopes[str(s)] = {"beta": _r(b, 6), "rpw": _r(1.0 / b)}

    # 2020 sensitivity: every candidate fitted on the ten primary seasons.
    f20 = rf.frame(rows_all[rf.SENSITIVITY_SEASON])
    sens = {}
    for c in cands:
        pr = rf.predict(c, full.get(c, {}), f20)
        e = pr - f20["w"]
        g_mean = float(np.mean(f20["g"]))
        sens[c] = {"mae": _r(rf.mae(e)), "rmse": _r(rf.rmse(e)),
                   "mae_per_162": _r(rf.mae(e) * 162.0 / g_mean)}

    # Part 5.
    e_l = arms["L"] - f["w"]
    e_d = arms["D"] - f["w"]
    pc = rf.contrast(e_l, e_d, idx)
    pleg = {"arm_L": {"mae": _r(rf.mae(e_l)), "rmse": _r(rf.rmse(e_l))},
            "arm_D": {"mae": _r(rf.mae(e_d)), "rmse": _r(rf.rmse(e_d))},
            "contrast_L_minus_D": {k: _r(v) for k, v in pc.items()},
            "arm_L_max_abs_vs_a": arms["arm_l_max_abs_vs_a"],
            "stints": len(st),
            "finding": rf.pitcher_verdict(pc)}
    log(f"part 5: MAE arm L {rf.mae(e_l):.4f}, arm D {rf.mae(e_d):.4f}; dMAE {pc['d_mae']:+.4f} "
        f"lo95 {pc['lo95']:+.4f} hi95 {pc['hi95']:+.4f}: the dynamic form {rf.pitcher_verdict(pc)}")

    verdict_out = {"status": ver["status"], "candidate": ver["candidate"],
                   "passing": ver["passing"],
                   "team_guard": ("not run: no candidate passed" if not ver["passing"] else
                                  "PENDING: EBR_GATE.md 11.2.4, computed by EWAR_V3_ASSEMBLE or the skill look"),
                   "rpw_by_season": supplies[ver["candidate"]]}

    return {
        "rpw_fit_version": rf.RPW_FIT_VERSION,
        "generated_at": _now(),
        "gate_doc": rf.GATE_DOC,
        "estimand": "leave-one-season-out MAE in wins predicting club wins from run differential (RMSE reported)",
        "frame": {"primary_seasons": list(rf.PRIMARY_SEASONS), "team_seasons": n,
                  "sensitivity_season": rf.SENSITIVITY_SEASON,
                  "park_factor_season_used": {str(k): v for k, v in pf_used.items()}},
        "bootstrap": {"b": rf.BOOT_B, "seed": rf.BOOT_SEED,
                      "resampling": "team-season rows of the held-out errors, one index matrix"},
        "league": {str(s): {"closed_form_rpw": _r(fg_rpw[s]), "lg_ra9": _r(lg_ra9[s]),
                            "league_runs_per_game": _r(L_s[s]),
                            "bref_season_rpw": _r(by_season.get(s))} for s in rf.ALL_SEASONS},
        "candidates": per_cand,
        "contrasts_vs_a": contrasts,
        "holm_reported": {c: {"p": _r(v["p"]), "threshold": _r(v["threshold"], 6),
                              "rejects": v["rejects"]} for c, v in hl.items()},
        "full_fit": full_out,
        "rpw_by_season": supplies,
        "team_environment_reported": team_env,
        "per_season_slope_reported": slopes,
        "sensitivity_2020": sens,
        "pitcher_leg": pleg,
        "bref_fallbacks": bref_fallbacks,
        "verdict": verdict_out,
        "inputs": digests,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    doc = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=False, ensure_ascii=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

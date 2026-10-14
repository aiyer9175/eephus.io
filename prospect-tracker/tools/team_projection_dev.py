# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The DEV half of the team projection candidates (task
TM_3_TEAM_CANDIDATES_DARK): the constants of T1, T2 and T3 are chosen on the
retro seasons 2022 to 2025 and frozen, once, in model/team_projection/.

docs/TEAM_PROJECTIONS_GATE.md sections 1, 2.1 and 8; LANE_A 2.6; plan Part 9
section 9.5.

WHAT RUNS. For each DEV season (proj_backtest.TARGETS, never the GATE season
2026) the point-in-time team frame proj_backtest.team_frame(target, aging="v2")
on the retro engine at HEAD: per club the champion mean WAR, projected PA or
IP, the served_recentered win roll-up, the talent prior p_prior, the club's
actual exposure and its actual wins. The club's actual runs scored and allowed
come from the one standings parser (proj_backtest.club_actuals, DEV seasons
only). The season's actual regular-season schedule is read once from StatsAPI
(a fixture, not an outcome) and cached write-once under
.cache/team_projection/schedules/.

WHAT IS CHOSEN, each from the rule the gate fixed before any number existed:
  T1  s_res, the RMSE over the 120 DEV club-seasons of the served_recentered
      residual (projected minus actual wins); s_sched, the mean over the same
      club-seasons of the sd of the schedule-only simulated win total (each
      club at its p_prior over that season's schedule, n_sims MC_SIMS, seed
      MC_SEED); sigma_T = sqrt(max(0, s_res^2 - s_sched^2)).
  T2  the club PA and IP budget: the 2022-2025 league means of club PA and
      club IP per 162 games (actual exposure x 162 / games played).
  T3  no constant of its own: the park factor column, the Pythagenpat
      exponent and the PJ-C params it reads are named in the file.

WHAT IS PUBLISHED. DEV CRPS, MAE and 80% coverage for each candidate against
its comparator (T1 against the schedule-only incumbent, the candidate's DEV
coverage in-sample because sigma_T is fitted here; T2 the budgeted roll-up
against served_recentered; T3 RS and RA against carry-forward and league
average), each with the gate's paired club bootstrap, per season and pooled.
model/team_projection/params.json carries the constants and
model/team_projection/dev_receipt.json the tables. Nothing is written under
data/; the GATE look (TM_4) is a separate task and reads nothing here but the
params file's hash.

Usage:
    python tools/team_projection_dev.py --write          # freeze (once)
    python tools/team_projection_dev.py --out DIR        # preview to DIR only
    python tools/team_projection_dev.py --quick --out DIR
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import math
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("team_projection_dev")

DEV_SEED = 20261014        # the DEV bootstrap seed (the GATE look keeps its own, 20261208)
DEV_B = 2000               # the gate's B (section 3)
QUICK_SIMS = 2000


def _head_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                                       text=True).strip()
    except Exception:                                          # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# The season schedule (a fixture, cached write-once)
# --------------------------------------------------------------------------

_PLAYED = {"Final", "Completed Early", "Game Over"}


def season_pairs(season: int, cache_dir: Path | None = None) -> tuple[list[tuple[str, str]], dict]:
    """[(home_org, away_org), ...] of every regular-season game of ``season``
    that was played, by game id (a resumed game counts once), from StatsAPI's
    /schedule through proj_current's cached reader, kept write-once under
    .cache/team_projection/schedules/schedule_<season>.json."""
    import team_projection as TP
    p = TP.schedule_path(season, cache_dir)
    if p.exists():
        blob = json.loads(p.read_text(encoding="utf-8"))
        return [tuple(x) for x in blob["pairs"]], {"file": p.name, "n_games": blob["n_games"],
                                                   "source": "cache", "fetched_at": blob.get("fetched_at")}
    import proj_current as pc
    from trades import canonical_org_from_id
    data = pc._fetch_schedule_raw(f"{season}-03-01", f"{season}-11-05")
    if not data:
        raise RuntimeError(f"schedule {season}: StatsAPI /schedule returned nothing")
    seen: set = set()
    pairs: list[tuple[str, str]] = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            if g.get("gameType") != "R":
                continue
            st = (g.get("status") or {}).get("detailedState") or ""
            if st not in _PLAYED:
                continue
            pk = g.get("gamePk")
            if pk in seen:
                continue
            seen.add(pk)
            tm = g.get("teams") or {}
            ht = (tm.get("home") or {}).get("team") or {}
            at = (tm.get("away") or {}).get("team") or {}
            ho = canonical_org_from_id(ht.get("id"), ht.get("name") or "")
            ao = canonical_org_from_id(at.get("id"), at.get("name") or "")
            if ho and ao and len(ho) <= 3 and len(ao) <= 3:
                pairs.append((ho, ao))
    fetched_at = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"season": season, "n_games": len(pairs), "fetched_at": fetched_at,
                             "source": "statsapi /schedule gameType R, played games by gamePk",
                             "pairs": pairs}), encoding="utf-8")
    return pairs, {"file": p.name, "n_games": len(pairs), "source": "statsapi", "fetched_at": fetched_at}


def _mc_teams(clubs: dict) -> dict:
    """The simulator's team table for a preseason DEV read: every club at 0-0
    on its p_prior, league and division from proj_current's alignment."""
    import proj_current as pc
    lg_div = {}
    for dv, members in pc._DIVISIONS.items():
        for o in members:
            lg_div[o] = (103 if dv.startswith("AL") else 104, dv)
    out = {}
    for o, c in clubs.items():
        lg, dv = lg_div.get(o, (None, None))
        out[o] = {"wins": 0, "losses": 0, "p": float(c["p_prior"]), "league": lg, "div": dv}
    return out


# --------------------------------------------------------------------------
# T3 on a DEV season
# --------------------------------------------------------------------------

def _age_curves(corpus: dict, last: int):
    try:
        import aging_v3
        import aging_v3_sidecar
        import proj_components as PC
        sidecar = aging_v3_sidecar.load(corpus, build_if_missing=False)
        return (PC.component_age_curves(aging_v3.fitted(corpus, last, None, sidecar=sidecar)),
                f"aging_v3 component_curve('hit', 'bsr' | 'fld') fitted at {last} (U5)")
    except Exception as e:                                     # noqa: BLE001
        log.warning("aging_v3 component curves unavailable at %d: %s", last, e)
        return None, f"none (aging_v3 fit unavailable at {last}: {type(e).__name__}); flat age walks"


def runs_frame(target: int, corpus: dict, frame: dict, scales: dict) -> dict:
    """T3 for one DEV season: per club RS, RA, run differential and Pythag
    wins from the component heads at base ``target`` (constants and park
    factors held at target - 1), batting plus baserunning at T2's PA scale,
    FIP runs above average at T2's IP scale, the club's fielding runs."""
    import fa_projection as fp
    import proj_components as PC
    import team_projection as TP
    last = target - 1
    blob = PC.resolve_vintage(None)
    consts = PC.season_constants(last, corpus, blob)
    pc_params = PC.load_params() if PC.PARAMS_PATH.exists() else None
    curves, _wm = fp.fitted_models(corpus, last)
    age_curves, age_note = _age_curves(corpus, last)
    src = PC._Sources(blob)
    pf, pf_meta = TP.park_factors(last)
    lg_runs = TP.league_runs_per_team(consts)
    league = corpus["league"]
    by_player: dict[str, dict[int, dict[int, dict]]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam") and target - 3 <= int(r["season"]) <= target - 1:
                by_player[side][r["mlbam"]][r["season"]] = r
    clubs: dict[str, dict] = {}
    n_blocks = 0
    for org, c in frame["clubs"].items():
        sc = (scales or {}).get(org) or {}
        tot = {"bat_bsr": 0.0, "fld": 0.0, "fip_raa": 0.0, "pa": 0.0, "ip": 0.0,
               "n_hit": 0, "n_pit": 0, "not_projected": {}}
        for p in c["players"]:
            side = p["side"]
            seasons = by_player[side].get(p["mlbam"]) or {}
            hist = [seasons[s] for s in (target - 1, target - 2, target - 3) if s in seasons]
            if not hist:
                continue
            blk = None
            try:
                eng = PC.engine_projection(hist, side, target, p.get("age"), curves, league, 1)
                if eng is not None:
                    feat = (PC._hit_lags if side == "hit" else PC._pit_lags)(src, p["mlbam"], target)
                    blk = (PC.hitter_heads(eng, feat, pc_params, consts, age_curves, 1) if side == "hit"
                           else PC.pitcher_heads(eng, feat, pc_params, consts, 1))
            except Exception:                                  # noqa: BLE001
                log.debug("heads failed %s %s %d", p["mlbam"], side, target, exc_info=True)
                blk = None
            cr = TP.component_runs(blk, side, float(sc.get(side, 1.0) or 1.0), 1)
            n_blocks += 1 if blk else 0
            tot["bat_bsr"] += cr["bat_bsr"]
            tot["fld"] += cr["fld"]
            tot["fip_raa"] += cr["fip_raa"]
            tot["pa" if side == "hit" else "ip"] += cr["pt"]
            tot["n_hit" if side == "hit" else "n_pit"] += 1
            for k in cr["not_projected"]:
                tot["not_projected"][k] = tot["not_projected"].get(k, 0) + 1
        line = TP.club_runs(lg_runs, tot["bat_bsr"], tot["fip_raa"], tot["fld"], pf.get(org, 1.0))
        line.update({"batBsrRuns": round(tot["bat_bsr"], 1), "fldRuns": round(tot["fld"], 1),
                     "fipRaaRuns": round(tot["fip_raa"], 1), "paAllocated": round(tot["pa"], 1),
                     "ipAllocated": round(tot["ip"], 1), "nHit": tot["n_hit"], "nPit": tot["n_pit"],
                     "notProjected": tot["not_projected"]})
        clubs[org] = line
    return {"season": target, "clubs": clubs, "league": TP.runs_identity(clubs, lg_runs),
            "meta": {"league_runs_per_team": round(lg_runs, 1), "constants_season": last,
                     "park_factor": pf_meta, "age_curves": age_note,
                     "pj_params": ("model/proj_components/params.json" if pc_params else "none"),
                     "pj_params_sha256": (PC.params_hash(pc_params) if pc_params else None),
                     "n_player_blocks": n_blocks, "frame": "FanGraphs frame"}}


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def _pooled(deltas_by_season: dict, B: int, seed: int) -> dict:
    import proj_backtest as PB
    pooled = {f"{s}:{o}": d for s, dd in deltas_by_season.items() for o, d in dd.items()}
    return PB._club_bootstrap(pooled, B, seed)


def run(n_sims: int, B: int, out_dir: Path | None, write: bool) -> int:
    import fa_projection as fp
    import proj_backtest as PB
    import proj_current as pc
    import team_projection as TP
    from rate_stabilization import REPLACEMENT_WINS

    if write and TP.PARAMS_PATH.exists():
        print(f"REFUSED: {TP.PARAMS_PATH} exists; the DEV freeze happens once", file=sys.stderr)
        return 2
    # proj_current.simulate_playoffs breaks ties by draws taken while
    # iterating a set of division names, so its stream follows the process's
    # string hash seed: the freeze runs under PYTHONHASHSEED=0 so the record
    # reproduces to the digit (measured 2026-10-14: sigma_T 7.6765 against
    # 7.6766 across two unpinned processes, the same schedules and seed).
    hash_seed = os.environ.get("PYTHONHASHSEED")
    if write and hash_seed != "0":
        print("REFUSED: the freeze runs under PYTHONHASHSEED=0 (see the note in run())", file=sys.stderr)
        return 2
    seasons = list(PB.TARGETS)
    if PB.GATE_SEASON in seasons:
        raise RuntimeError("the GATE season is never a DEV season")
    head = _head_sha()
    t0 = time.time()
    corpus = fp.build_corpus()
    log.info("corpus %.1fs", time.time() - t0)

    frames: dict[int, dict] = {}
    actuals: dict[int, dict] = {}
    schedules: dict[int, list] = {}
    sched_meta: dict[int, dict] = {}
    for s in seasons:
        t1 = time.time()
        frames[s] = PB.team_frame(s, corpus, aging="v2")
        actuals[s] = PB.club_actuals(s)
        schedules[s], sched_meta[s] = season_pairs(s)
        log.info("frame %d: %d clubs, %d games, %.1fs", s, frames[s]["league"]["n_clubs"],
                 len(schedules[s]), time.time() - t1)

    # ---- T1 constants: s_res, s_sched -------------------------------------
    resid_rows = []
    sched_sd: dict[int, dict[str, float]] = {}
    inc_samples: dict[int, dict[str, list]] = {}
    for s in seasons:
        fr = frames[s]
        for o, c in fr["clubs"].items():
            a = (actuals[s].get(o) or {}).get("wins")
            if a is None:
                continue
            resid_rows.append({"season": s, "org": o, "served_recentered": c["wins_served_recentered"],
                               "actual": a, "resid": round(c["wins_served_recentered"] - a, 3)})
        odds = pc.simulate_playoffs(_mc_teams(fr["clubs"]), schedules[s], n_sims=n_sims,
                                    seed=pc.MC_SEED, bracket=False, samples=True)
        sched_sd[s] = {o: statistics.pstdev(v["winSamples"]) for o, v in odds.items()}
        inc_samples[s] = {o: v["winSamples"] for o, v in odds.items()}
    s_res = math.sqrt(sum(r["resid"] ** 2 for r in resid_rows) / len(resid_rows))
    all_sd = [v for d in sched_sd.values() for v in d.values()]
    s_sched = sum(all_sd) / len(all_sd)
    sigma_t = TP.sigma_t(s_res, s_sched)
    per_season_mae = {s: round(statistics.mean(abs(r["resid"]) for r in resid_rows if r["season"] == s), 3)
                      for s in seasons}
    log.info("s_res %.4f s_sched %.4f sigma_T %.4f", s_res, s_sched, sigma_t)

    # ---- T1 DEV: CRPS and coverage, both arms ------------------------------
    t1_tbl: dict = {"per_season": {}, "deltas": {}}
    for s in seasons:
        fr = frames[s]
        act = {o: (actuals[s].get(o) or {}).get("wins") for o in fr["clubs"]}
        cand = pc.simulate_playoffs(_mc_teams(fr["clubs"]), schedules[s], n_sims=n_sims,
                                    seed=pc.MC_SEED, bracket=False, samples=True,
                                    talent_sd_wins=sigma_t, games_played=0)
        inc_sc = PB.score_win_distribution(inc_samples[s], act)
        cand_sc = PB.score_win_distribution({o: v["winSamples"] for o, v in cand.items()}, act)
        deltas = {o: cand_sc["crps_by_club"][o] - inc_sc["crps_by_club"][o]
                  for o in cand_sc["crps_by_club"] if o in inc_sc["crps_by_club"]}
        t1_tbl["deltas"][s] = deltas
        t1_tbl["per_season"][s] = {
            "incumbent": {"crps_mean": inc_sc["crps_mean"], "coverage80": inc_sc["coverage80"],
                          "sched_sd_mean": round(statistics.mean(sched_sd[s].values()), 4)},
            "candidate": {"crps_mean": cand_sc["crps_mean"], "coverage80": cand_sc["coverage80"],
                          "win_sd_mean": round(statistics.mean(
                              statistics.pstdev(v["winSamples"]) for v in cand.values()), 4),
                          "in_sample": True},
            "bootstrap": PB._club_bootstrap(deltas, B, DEV_SEED),
            "missing": sorted(set(inc_sc["missing"]) | set(cand_sc["missing"])),
        }
    t1_tbl["pooled"] = _pooled(t1_tbl["deltas"], B, DEV_SEED)
    n_cs = sum(v["incumbent"]["coverage80"]["n"] for v in t1_tbl["per_season"].values())
    k_inc = sum(v["incumbent"]["coverage80"]["k"] for v in t1_tbl["per_season"].values())
    k_cand = sum(v["candidate"]["coverage80"]["k"] for v in t1_tbl["per_season"].values())
    t1_tbl["pooled_coverage80"] = {
        "incumbent": {"k": k_inc, "n": n_cs, "rate": round(k_inc / n_cs, 4), "wilson95": PB._wilson(k_inc, n_cs)},
        "candidate": {"k": k_cand, "n": n_cs, "rate": round(k_cand / n_cs, 4),
                      "wilson95": PB._wilson(k_cand, n_cs), "in_sample": True}}
    t1_tbl["pooled_crps_mean"] = {
        "incumbent": round(statistics.mean(v["incumbent"]["crps_mean"] for v in t1_tbl["per_season"].values()), 4),
        "candidate": round(statistics.mean(v["candidate"]["crps_mean"] for v in t1_tbl["per_season"].values()), 4)}
    del t1_tbl["deltas"]

    # ---- T2 constants and DEV ---------------------------------------------
    expo_rows = []
    for s in seasons:
        for o, c in frames[s]["clubs"].items():
            e = c.get("exposure")
            gp = (actuals[s].get(o) or {}).get("gp") or 162
            if e and e.get("pa") and e.get("ip"):
                expo_rows.append({"season": s, "org": o, "pa162": e["pa"] * 162.0 / gp,
                                  "ip162": e["ip"] * 162.0 / gp, "gp": gp})
    budget_pa = sum(r["pa162"] for r in expo_rows) / len(expo_rows)
    budget_ip = sum(r["ip162"] for r in expo_rows) / len(expo_rows)
    budget = {"pa": round(budget_pa, 1), "ip": round(budget_ip, 1)}
    t2_tbl: dict = {"per_season": {}, "deltas": {}, "budget_by_season": {}}
    scales_by_season: dict[int, dict] = {}
    for s in seasons:
        fr = frames[s]
        rows = [r for r in expo_rows if r["season"] == s]
        t2_tbl["budget_by_season"][s] = {"pa162": round(statistics.mean(r["pa162"] for r in rows), 1),
                                         "ip162": round(statistics.mean(r["ip162"] for r in rows), 1),
                                         "n_clubs": len(rows)}
        war_b, acct, scales = {}, {}, {}
        for o, c in fr["clubs"].items():
            hit = [{"pt": p.get("pa_proj"), "war": p["pred"]} for p in c["players"] if p["side"] == "hit"]
            pit = [{"pt": p.get("ip_proj"), "war": p["pred"]} for p in c["players"] if p["side"] == "pit"]
            b = TP.budgeted_club_war(hit, pit, budget["pa"], budget["ip"])
            war_b[o] = b["war"]
            scales[o] = {"hit": b["hit"]["scale"], "pit": b["pit"]["scale"]}
            acct[o] = {"paSum": b["hit"]["pt_sum"], "paScale": round(b["hit"]["scale"], 4),
                       "paShort": b["hit"]["shortfall"], "ipSum": b["pit"]["pt_sum"],
                       "ipScale": round(b["pit"]["scale"], 4), "ipShort": b["pit"]["shortfall"],
                       "warBudget": b["war"], "warUnscaled": b["war_unscaled"]}
        scales_by_season[s] = scales
        wins_b, shift = TP.recenter({o: REPLACEMENT_WINS + w for o, w in war_b.items()}, PB.LEAGUE_WINS)
        act = {o: (actuals[s].get(o) or {}).get("wins") for o in fr["clubs"]}
        srv = {o: c["wins_served_recentered"] for o, c in fr["clubs"].items()}
        sc_b = PB.score_team_wins(wins_b, act)
        sc_s = PB.score_team_wins(srv, act)
        deltas = {o: sc_b["abs_err_by_club"][o] - sc_s["abs_err_by_club"][o]
                  for o in sc_b["abs_err_by_club"] if o in sc_s["abs_err_by_club"]}
        t2_tbl["deltas"][s] = deltas
        t2_tbl["per_season"][s] = {
            "budgeted": {"mae": sc_b["mae"], "bias": sc_b["bias_pred_minus_act"], "r": sc_b["r"],
                         "recenter_shift": round(shift, 3), "sum_wins": round(sum(wins_b.values()), 1)},
            "served_recentered": {"mae": sc_s["mae"], "bias": sc_s["bias_pred_minus_act"], "r": sc_s["r"]},
            "bootstrap": PB._club_bootstrap(deltas, B, DEV_SEED),
            "clubs_over_budget": {"pa": sum(1 for a in acct.values() if a["paScale"] < 1.0),
                                  "ip": sum(1 for a in acct.values() if a["ipScale"] < 1.0)},
            "accounting": acct,
        }
    t2_tbl["pooled"] = _pooled(t2_tbl["deltas"], B, DEV_SEED)
    t2_tbl["pooled_mae"] = {
        "budgeted": round(statistics.mean(v["budgeted"]["mae"] for v in t2_tbl["per_season"].values()), 3),
        "served_recentered": round(statistics.mean(v["served_recentered"]["mae"]
                                                   for v in t2_tbl["per_season"].values()), 3)}
    del t2_tbl["deltas"]

    # ---- T3 DEV --------------------------------------------------------------
    t3_tbl: dict = {"per_season": {}, "deltas": {"rs": {}, "ra": {}}}
    t3_err = None
    try:
        for s in seasons:
            rf = runs_frame(s, corpus, frames[s], scales_by_season[s])
            prior = {o: {"rs": v.get("rs"), "ra": v.get("ra")} for o, v in PB.club_actuals(s - 1).items()}
            pred_rs = {o: v["rs"] for o, v in rf["clubs"].items()}
            pred_ra = {o: v["ra"] for o, v in rf["clubs"].items()}
            srv = {o: c["wins_served_recentered"] for o, c in frames[s]["clubs"].items()}
            sc = PB.score_team_runs(pred_rs, pred_ra, actuals[s], prior=prior, pred_wins=srv,
                                    B=B, seed=DEV_SEED)
            for side in ("rs", "ra"):
                t3_tbl["deltas"][side][s] = {
                    "vs_carry_forward": sc[side]["vs_carry_forward"]["delta_by_club"],
                    "vs_league_avg": sc[side]["vs_league_avg"]["delta_by_club"]}
            t3_tbl["per_season"][s] = {
                "rs": {"mae": sc["rs"]["mae"], "n": sc["rs"]["n"],
                       "vs_carry_forward": {"comparator_mae": sc["rs"]["vs_carry_forward"]["comparator_mae"],
                                            "bootstrap": sc["rs"]["vs_carry_forward"]["bootstrap"]},
                       "vs_league_avg": {"comparator_mae": sc["rs"]["vs_league_avg"]["comparator_mae"],
                                         "bootstrap": sc["rs"]["vs_league_avg"]["bootstrap"]}},
                "ra": {"mae": sc["ra"]["mae"], "n": sc["ra"]["n"],
                       "vs_carry_forward": {"comparator_mae": sc["ra"]["vs_carry_forward"]["comparator_mae"],
                                            "bootstrap": sc["ra"]["vs_carry_forward"]["bootstrap"]},
                       "vs_league_avg": {"comparator_mae": sc["ra"]["vs_league_avg"]["comparator_mae"],
                                         "bootstrap": sc["ra"]["vs_league_avg"]["bootstrap"]}},
                "pythag_wins_mae": sc["pythag_wins"]["mae"],
                "served_wins_mae": (sc["served_wins"] or {}).get("mae"),
                "league_identity": rf["league"], "meta": rf["meta"],
                "clubs": {o: {k: v[k] for k in ("rs", "ra", "runDiff", "pythW", "pf", "batBsrRuns",
                                                 "fldRuns", "fipRaaRuns", "paAllocated", "ipAllocated",
                                                 "nHit", "nPit", "notProjected")}
                          for o, v in rf["clubs"].items()},
            }
        t3_tbl["pooled"] = {side: {comp: _pooled({s: d[comp] for s, d in t3_tbl["deltas"][side].items()}, B, DEV_SEED)
                                   for comp in ("vs_carry_forward", "vs_league_avg")}
                            for side in ("rs", "ra")}
        t3_tbl["pooled_mae"] = {side: round(statistics.mean(v[side]["mae"] for v in t3_tbl["per_season"].values()), 3)
                                for side in ("rs", "ra")}
        t3_tbl["pooled_pythag_wins_mae"] = round(statistics.mean(
            v["pythag_wins_mae"] for v in t3_tbl["per_season"].values()), 3)
    except Exception as e:                                     # noqa: BLE001
        log.exception("T3 DEV failed")
        t3_err = f"{type(e).__name__}: {e}"
        t3_tbl["error"] = t3_err
    t3_tbl.pop("deltas", None)

    # ---- freeze ---------------------------------------------------------------
    import proj_components as PC
    pj_sha = PC.params_hash(PC.load_params()) if PC.PARAMS_PATH.exists() else None
    today = _dt.date.today().isoformat()
    retro_eval = {}
    try:
        retro_eval = json.loads((ROOT / "data" / "team_outlook_eval.json").read_text(encoding="utf-8"))
        retro_eval = {"retro_backtest_generated_at": (retro_eval.get("retro_backtest") or {}).get("generated_at"),
                      "served_recentered_mae_published": {
                          str(r["season"]): (r.get("served_recentered") or {}).get("mae")
                          for r in (retro_eval.get("retro_backtest") or {}).get("team_level_per_season") or []}}
    except (OSError, ValueError):
        retro_eval = {}
    params = {
        "task": "TM_3_TEAM_CANDIDATES_DARK",
        "gate": "docs/TEAM_PROJECTIONS_GATE.md",
        "frozen_on": today,
        "head": head,
        "dev_seasons": seasons,
        "aging": "v2",
        "retro_run": {"engine": f"proj_backtest.team_frame on the retro engine at HEAD {head} "
                                "(curves and WAR map refit per target on data through target - 1)",
                      **retro_eval},
        "sigma_T": round(sigma_t, 4),
        "s_res": round(s_res, 4),
        "s_sched": round(s_sched, 4),
        "k_pseudo_games": TP.K_PSEUDO_GAMES,
        "talent_clip": list(TP.TALENT_CLIP),
        "budget": budget,
        "sim": {"n_sims": n_sims, "seed": pc.MC_SEED, "home_edge": pc.MC_HOME_EDGE, "bracket": False},
        "runs": {"park_factor_column": TP.PF_COLUMN, "pythagenpat_exp": TP.PYTHAGENPAT_EXP,
                 "bf_per_ip": TP.BF_PER_IP, "pj_params_sha256": pj_sha},
        "bootstrap": {"B": B, "seed": DEV_SEED},
        "python_hash_seed": hash_seed,
    }
    receipt = {
        "task": "TM_3_TEAM_CANDIDATES_DARK",
        "frozen_on": today, "head": head, "python_hash_seed": hash_seed,
        "params_sha256": TP.params_hash(params),
        "dev_seasons": seasons,
        "n_club_seasons": len(resid_rows),
        "schedules": {str(s): sched_meta[s] for s in seasons},
        "served_recentered_mae_by_season": {str(s): per_season_mae[s] for s in seasons},
        "t1": {"s_res": round(s_res, 4), "s_sched": round(s_sched, 4), "sigma_T": round(sigma_t, 4),
               "sched_sd_by_season": {str(s): round(statistics.mean(sched_sd[s].values()), 4) for s in seasons},
               "table": t1_tbl},
        "t2": {"budget": budget, "n_club_seasons": len(expo_rows), "table": t2_tbl},
        "t3": {"table": t3_tbl, "error": t3_err},
        "residuals": resid_rows,
        "elapsed_s": round(time.time() - t0, 1),
    }
    receipt["params_sha256"] = TP.params_hash(params)
    targets = []
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        targets.append((out_dir / "params.json", out_dir / "dev_receipt.json"))
    if write:
        TP.PARAMS_DIR.mkdir(parents=True, exist_ok=True)
        targets.append((TP.PARAMS_PATH, TP.DEV_RECEIPT_PATH))
    for pp, rp in targets:
        pp.write_text(json.dumps(params, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        rp.write_text(json.dumps(receipt, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
        print(f"wrote {pp} and {rp}")
    print(json.dumps({"sigma_T": params["sigma_T"], "s_res": params["s_res"], "s_sched": params["s_sched"],
                      "budget": budget, "params_sha256": receipt["params_sha256"],
                      "t1_pooled": t1_tbl["pooled"], "t1_crps": t1_tbl["pooled_crps_mean"],
                      "t1_cov": t1_tbl["pooled_coverage80"], "t2_pooled": t2_tbl["pooled"],
                      "t2_mae": t2_tbl["pooled_mae"],
                      "t3": {k: t3_tbl.get(k) for k in ("pooled_mae", "pooled_pythag_wins_mae", "error")}},
                     indent=1, default=str))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="freeze model/team_projection/ (once)")
    ap.add_argument("--out", type=Path, default=None, help="preview directory")
    ap.add_argument("--quick", action="store_true", help=f"{QUICK_SIMS} simulations per arm")
    ap.add_argument("--sims", type=int, default=None)
    ap.add_argument("--B", type=int, default=DEV_B)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    import proj_current as pc
    n_sims = a.sims or (QUICK_SIMS if a.quick else pc.MC_SIMS)
    if not a.write and a.out is None:
        ap.error("pass --write or --out DIR")
    return run(n_sims, a.B, a.out, a.write)


if __name__ == "__main__":
    sys.exit(main())

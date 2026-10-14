# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The team gate's GATE look (task TM_4_TEAM_LOOK_2026): TM-A, TM-B and TM-C
scored once on the 2026 club season against the frozen DEV params
(docs/TEAM_PROJECTIONS_GATE.md sections 2.2, 3 and 4; LANE_A section 3.3).

    python tools/team_projection_look.py --dry-run --out <dir>
        the whole reporting path on fixtures with nulls (a club with no rows,
        a club with no samples, a missing RS, a missing prior RA); reads no
        2026 club quantity and writes nothing under data/
    PYTHONHASHSEED=0 python tools/team_projection_look.py --out <dir> --write
        the one look: proj_backtest.team_frame(2026, look=True), the 2026
        schedule (a fixture, cached write-once), the actual 2026 standings
        through the one parser, the three scorers with the frozen params,
        the block written once as team_projection_gate.gate_2026 in
        data/team_outlook_eval.json (read-modify-write, first write wins)
        and the section 8 entry rendered to <dir>/gate_entry.md

The run refuses when model/team_projection/params.json does not hash to the
DEV freeze entry of section 8, when the artifact already carries gate_2026,
or when PYTHONHASHSEED is not 0 (proj_current.simulate_playoffs takes its
tie-break draws while iterating a set of division names; the DEV record was
taken under 0, TM_3 finding 5). The 2026 projection is the retro design with
every input dated 2025 or earlier; no row carries a 2026 actual WAR, so no
player-level 2026 residual exists here (section 7). Verdicts come from the
registered rules only: PASS is ub95 < 0, FAIL is ub95 >= 0, NULL is no club
scored.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import re
import statistics
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

log = logging.getLogger("team_projection_look")

TASK = "TM_4_TEAM_LOOK_2026"
GATE_DOC = ROOT / "docs" / "TEAM_PROJECTIONS_GATE.md"
GATE_KEY = "gate_2026"
SEED_LOOK = 20261208            # section 3.1 to 3.3
DRY_SIMS = 200
FLAGS = {"TM-A": "TEAM_TALENT_RANGE_LIVE", "TM-B": "TEAM_PT_BUDGET_LIVE", "TM-C": "TEAM_RUNS_LIVE"}
_FREEZE_RE = re.compile(r"DEV frozen \d{4}-\d{2}-\d{2} at [0-9a-f]{7,40}, params sha256 ([0-9a-f]{64})")


class LookRefused(RuntimeError):
    """A precondition of section 4 failed before anything was read."""


# --------------------------------------------------------------------------
# preconditions
# --------------------------------------------------------------------------

def recorded_params_sha(doc_path: Path | None = None) -> str:
    """The params sha256 of the one DEV freeze entry in section 8."""
    text = (doc_path or GATE_DOC).read_text(encoding="utf-8")
    found = _FREEZE_RE.findall(text)
    if len(found) != 1:
        raise LookRefused(f"{len(found)} DEV freeze entries in the gate document; exactly one expected")
    return found[0]


def check_preconditions(*, dry_run: bool, eval_path: Path | None = None) -> dict:
    """The frozen params hash to the gate record and the look is unspent.
    Returns the params. The hash seed is checked by main() for the real run."""
    import proj_backtest as PB
    import team_projection as TP
    params = TP.load_params()
    if params is None:
        raise LookRefused(f"{TP.PARAMS_PATH} is absent: the DEV freeze (TM_3) has not happened")
    recorded = recorded_params_sha()
    try:
        TP.check_params(params, recorded)
    except TP.TeamParamsError as e:
        raise LookRefused(f"DEV params changed after freezing: {e}") from e
    if not dry_run and PB._gate_already_read(eval_path, GATE_KEY):
        raise LookRefused(f"team_projection_gate.{GATE_KEY} is already recorded; the look runs once")
    return params


# --------------------------------------------------------------------------
# the scorers, on any frame (the dry run hands fixtures; the look the engine)
# --------------------------------------------------------------------------

def _verdict(boot: dict | None) -> str:
    p = (boot or {}).get("pass")
    return "NULL" if p is None else ("PASS" if p else "FAIL")


def _wins(actual: dict) -> dict:
    return {o: (v or {}).get("wins") for o, v in (actual or {}).items()}


def _sd_mean(odds: dict) -> float | None:
    sds = [statistics.pstdev(v["winSamples"]) for v in odds.values() if len(v.get("winSamples") or []) > 1]
    return round(statistics.mean(sds), 4) if sds else None


def score_look(frame: dict, actual: dict, prior: dict, pairs: list, params: dict, *,
               runs_fn, n_sims: int, B: int, seed: int = SEED_LOOK,
               dev_receipt: dict | None = None) -> dict:
    """TM-A, TM-B and TM-C on one frame. ``frame`` is proj_backtest.team_frame's
    output; ``actual`` {org: {'wins', 'rs', 'ra', 'gp'}} from club_actuals;
    ``prior`` {org: {'rs', 'ra'}} the prior season's actuals; ``pairs`` the
    season's (home, away) games; ``runs_fn(frame, scales)`` the T3 runs frame
    (team_projection_dev.runs_frame on the look, a fixture on the dry run).
    Every missing club or value is named under a ``missing`` key and scored
    nowhere; a null statistic is a finding."""
    import proj_backtest as PB
    import proj_current as pc
    import team_projection as TP
    import team_projection_dev as DEV
    from rate_stabilization import REPLACEMENT_WINS

    clubs = frame["clubs"]
    act_w = _wins(actual)
    sim = params["sim"]
    sigma_t = float(params["sigma_T"])

    # ---- TM-A: the win-total distribution, both arms on shared draws -------
    teams_mc = DEV._mc_teams(clubs)
    common = dict(n_sims=n_sims, home_edge=float(sim["home_edge"]), seed=int(sim["seed"]),
                  bracket=bool(sim["bracket"]), samples=True)
    inc = pc.simulate_playoffs(teams_mc, pairs, **common)
    cand = pc.simulate_playoffs(teams_mc, pairs, talent_sd_wins=sigma_t, games_played=0, **common)
    inc_sc = PB.score_win_distribution({o: v["winSamples"] for o, v in inc.items()}, act_w)
    cand_sc = PB.score_win_distribution({o: v["winSamples"] for o, v in cand.items()}, act_w)
    deltas_a = {o: cand_sc["crps_by_club"][o] - inc_sc["crps_by_club"][o]
                for o in cand_sc["crps_by_club"] if o in inc_sc["crps_by_club"]}
    boot_a = PB._club_bootstrap(deltas_a, B, seed)
    dev_cov = None
    if dev_receipt:
        try:
            t = dev_receipt["t1"]["table"]
            dev_cov = {"incumbent": t["pooled_coverage80"]["incumbent"],
                       "candidate_in_sample": t["pooled_coverage80"]["candidate"],
                       "crps_mean": t["pooled_crps_mean"], "n_club_seasons": dev_receipt.get("n_club_seasons")}
        except (KeyError, TypeError):
            dev_cov = None
    tm_a = {
        "statistic": "mean CRPS of the win-total distribution against actual wins, candidate (T1, sigma_T) "
                     "minus incumbent (schedule only), paired over clubs",
        "sigma_T": sigma_t, "n_sims": int(n_sims), "sim_seed": int(sim["seed"]),
        "home_edge": float(sim["home_edge"]), "bracket": bool(sim["bracket"]), "games_played": 0,
        "incumbent": {"crps_mean": inc_sc["crps_mean"], "coverage80": inc_sc["coverage80"],
                      "win_sd_mean": _sd_mean(inc), "n_clubs": inc_sc["n_clubs"]},
        "candidate": {"crps_mean": cand_sc["crps_mean"], "coverage80": cand_sc["coverage80"],
                      "win_sd_mean": _sd_mean(cand), "n_clubs": cand_sc["n_clubs"]},
        "delta_by_club": {o: round(d, 4) for o, d in deltas_a.items()},
        "bootstrap": boot_a,
        "missing": sorted(set(inc_sc["missing"]) | set(cand_sc["missing"])),
        "dev_coverage80": dev_cov,
        "verdict": _verdict(boot_a),
    }

    # ---- TM-B: the budgeted roll-up against served_recentered --------------
    budget = params["budget"]
    war_b, scales, acct = {}, {}, {}
    for o, c in clubs.items():
        hit = [{"pt": p.get("pa_proj"), "war": p["pred"]} for p in c["players"] if p["side"] == "hit"]
        pit = [{"pt": p.get("ip_proj"), "war": p["pred"]} for p in c["players"] if p["side"] == "pit"]
        b = TP.budgeted_club_war(hit, pit, budget["pa"], budget["ip"])
        war_b[o] = b["war"]
        scales[o] = {"hit": b["hit"]["scale"], "pit": b["pit"]["scale"]}
        acct[o] = {"paSum": b["hit"]["pt_sum"], "paScale": round(b["hit"]["scale"], 4),
                   "paShort": b["hit"]["shortfall"], "ipSum": b["pit"]["pt_sum"],
                   "ipScale": round(b["pit"]["scale"], 4), "ipShort": b["pit"]["shortfall"],
                   "warBudget": b["war"], "warUnscaled": b["war_unscaled"]}
    wins_b, shift = TP.recenter({o: REPLACEMENT_WINS + w for o, w in war_b.items()}, PB.LEAGUE_WINS)
    srv = {o: c["wins_served_recentered"] for o, c in clubs.items()}
    sc_b = PB.score_team_wins(wins_b, act_w)
    sc_s = PB.score_team_wins(srv, act_w)
    deltas_b = {o: sc_b["abs_err_by_club"][o] - sc_s["abs_err_by_club"][o]
                for o in sc_b["abs_err_by_club"] if o in sc_s["abs_err_by_club"]}
    boot_b = PB._club_bootstrap(deltas_b, B, seed)
    tm_b = {
        "statistic": "team wins MAE, the T2 budgeted roll-up (after the 2,430 pin) minus "
                     "served_recentered, paired over clubs",
        "budget": dict(budget),
        "budgeted": {"mae": sc_b["mae"], "bias": sc_b["bias_pred_minus_act"], "r": sc_b["r"], "n": sc_b["n"],
                     "recenter_shift": round(shift, 3), "sum_wins": round(sum(wins_b.values()), 1)},
        "served_recentered": {"mae": sc_s["mae"], "bias": sc_s["bias_pred_minus_act"], "r": sc_s["r"],
                              "n": sc_s["n"]},
        "delta_by_club": {o: round(d, 4) for o, d in deltas_b.items()},
        "bootstrap": boot_b,
        "clubs_over_budget": {"pa": sum(1 for a in acct.values() if a["paScale"] < 1.0),
                              "ip": sum(1 for a in acct.values() if a["ipScale"] < 1.0)},
        "missing": sorted(set(sc_b["missing"]) | set(sc_s["missing"])),
        "verdict": _verdict(boot_b),
    }

    # ---- TM-C: runs scored and allowed ---------------------------------------
    rf = runs_fn(frame, scales)
    pred_rs = {o: (v or {}).get("rs") for o, v in rf["clubs"].items()}
    pred_ra = {o: (v or {}).get("ra") for o, v in rf["clubs"].items()}
    sc_c = PB.score_team_runs(pred_rs, pred_ra, actual, prior=prior, pred_wins=srv, B=B, seed=seed)

    def _side_verdict(side):
        p = sc_c["pass"].get(side)
        return "NULL" if p is None else ("PASS" if p else "FAIL")

    def _side_block(side):
        s = sc_c[side]
        out = {"mae": s["mae"], "n": s["n"], "missing": s["missing"]}
        for comp in ("vs_carry_forward", "vs_league_avg"):
            c = s.get(comp)
            out[comp] = (None if not c else
                         {"comparator_mae": c["comparator_mae"], "n": c["n"], "bootstrap": c["bootstrap"]})
        out["league_avg_comparator"] = s.get("league_avg_comparator")
        out["verdict"] = _side_verdict(side)
        return out

    tm_c = {
        "statistic": "RS MAE and RA MAE against actual runs; comparators prior-season carry-forward "
                     "and league average; pass per side is ub95 < 0 against both",
        "rs": _side_block("rs"), "ra": _side_block("ra"),
        "pythag_wins": {"n": sc_c["pythag_wins"]["n"], "mae": sc_c["pythag_wins"]["mae"],
                        "missing": sc_c["pythag_wins"]["missing"]},
        "served_wins_same_clubs": sc_c["served_wins"],
        "comparators": sc_c["comparators"],
        "league_identity": rf.get("league"), "meta": rf.get("meta"),
        "verdict": {"rs": _side_verdict("rs"), "ra": _side_verdict("ra")},
    }

    # ---- the per-club table (aggregates only; no player row leaves here) ----
    table = {}
    for o in sorted(set(clubs) | set(actual or {})):
        a = (actual or {}).get(o) or {}
        c = clubs.get(o) or {}
        ia, ca = inc_sc["clubs"].get(o) or {}, cand_sc["clubs"].get(o) or {}
        rl = (rf["clubs"].get(o) or {}) if rf.get("clubs") else {}
        table[o] = {
            "in_frame": o in clubs, "n_players": c.get("n_players"),
            "actual_wins": a.get("wins"), "actual_gp": a.get("gp"), "actual_rs": a.get("rs"), "actual_ra": a.get("ra"),
            "served_recentered": c.get("wins_served_recentered"), "budgeted": (round(wins_b[o], 3) if o in wins_b else None),
            "p_prior": c.get("p_prior"),
            "crps_incumbent": ia.get("crps"), "crps_candidate": ca.get("crps"),
            "p10_p90_incumbent": ([ia.get("p10"), ia.get("p90")] if ia else None),
            "p10_p90_candidate": ([ca.get("p10"), ca.get("p90")] if ca else None),
            "pred_rs": pred_rs.get(o), "pred_ra": pred_ra.get(o), "pythag_wins": sc_c["pythag_wins"]["by_club"].get(o),
            "park_factor": rl.get("pf"), "pa_scale": (scales.get(o) or {}).get("hit"), "ip_scale": (scales.get(o) or {}).get("pit"),
        }

    verdicts = {"TM-A": tm_a["verdict"], "TM-B": tm_b["verdict"], "TM-C": dict(tm_c["verdict"])}
    eligible = {FLAGS["TM-A"]: verdicts["TM-A"] == "PASS",
                FLAGS["TM-B"]: verdicts["TM-B"] == "PASS",
                FLAGS["TM-C"]: verdicts["TM-C"]["rs"] == "PASS" and verdicts["TM-C"]["ra"] == "PASS"}
    return {"tm_a": tm_a, "tm_b": tm_b, "tm_c": tm_c, "verdicts": verdicts,
            "flags_eligible": eligible, "clubs": table, "accounting_t2": acct,
            "bootstrap": {"B": int(B), "seed": int(seed)}}


# --------------------------------------------------------------------------
# the record (section 8 entry), rendered from the block only
# --------------------------------------------------------------------------

def _f(v, nd=3):
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _cov(c: dict | None) -> str:
    if not c or c.get("rate") is None:
        return "n/a"
    w = c.get("wilson95") or {}
    return f"{_f(c['rate'])} ({c['k']} of {c['n']}; Wilson {_f(w.get('lo'))} to {_f(w.get('hi'))})"


def _boot(b: dict | None) -> str:
    if not b or b.get("n", 0) == 0:
        return "null (no club scored)"
    return f"mean {_f(b['mean'])} / ub95 {_f(b['ub95'])} (n {b['n']}, dropped {len(b.get('dropped') or [])})"


def render_entry(block: dict) -> str:
    """The verbatim section 8 entry for the look, from the block alone."""
    a, b, c = block["tm_a"], block["tm_b"], block["tm_c"]
    v = block["verdicts"]
    inp = block.get("inputs") or {}
    date = block["look_date"]
    lines = [
        f"### {date}: the GATE look (TM_4_TEAM_LOOK_2026), verdicts TM-A {v['TM-A']}, TM-B {v['TM-B']}, "
        f"TM-C RS {v['TM-C']['rs']} RA {v['TM-C']['ra']}",
        "",
        f"Run once on {date} at {block.get('head')} (branch {block.get('branch')}), "
        f"`PYTHONHASHSEED={block.get('python_hash_seed')} python tools/team_projection_look.py --out <dir> --write`, "
        f"stdout and stderr teed to the task's output directory before anything else ran, the reporting path "
        f"dry-run first on fixtures with nulls. {block.get('early_read_note') or ''}".rstrip(),
        "",
        f"**Preconditions.** The DEV params hashed to the freeze entry above ({block.get('params_sha256')}); "
        f"gate_2026 was absent from the artifact; the 2026 frame was complete "
        f"({inp.get('n_clubs_actual')} clubs with wins, RS and RA through franchise_export._standings, "
        f"games played {inp.get('gp_set')}).",
        "",
        f"**The frame (section 2.2).** proj_backtest.team_frame(2026, look=True, aging=\"v2\"): "
        f"{inp.get('n_rows')} point-in-time rows (inputs 2023 to 2025; curves and the WAR map refit on data "
        f"through 2025), {inp.get('n_assigned')} assigned to {inp.get('n_clubs')} clubs by the primary-stint rule "
        f"on the 2026 stints (exposure only), {inp.get('unassigned_n')} unassigned ({inp.get('unassigned_war')} WAR); "
        f"no row carries a 2026 actual WAR. Roster WAR sum {inp.get('roster_war_sum')}; served_recentered "
        f"recenters to 2,430. Schedule: {inp.get('schedule_n_games')} played regular-season games "
        f"({inp.get('schedule_source')}), n_sims {a['n_sims']}, seed {a['sim_seed']}, home edge {a['home_edge']}, "
        f"bracket off, both arms on the same stream. Actual 2026 wins, RS and RA read once from "
        f"`.cache/statsapi_standings_2026.json`; the prior season for TM-C is 2025 (carry-forward per club; "
        f"league mean RS {_f(c['comparators']['league_avg'].get('rs'), 1)}, RA "
        f"{_f(c['comparators']['league_avg'].get('ra'), 1)} per club).",
        "",
        f"**Bootstrap.** Paired over clubs, B {block['bootstrap']['B']}, seed {block['bootstrap']['seed']}, "
        "candidate minus comparator, ub95 the 95th percentile of the resampled mean delta; pass is ub95 < 0.",
        "",
        "| gate | statistic | 2026 |",
        "|---|---|---|",
        f"| TM-A incumbent (schedule only) | mean CRPS | {_f(a['incumbent']['crps_mean'])} (win sd {_f(a['incumbent']['win_sd_mean'])}) |",
        f"| TM-A candidate (sigma_T {_f(a['sigma_T'], 4)}) | mean CRPS | {_f(a['candidate']['crps_mean'])} (win sd {_f(a['candidate']['win_sd_mean'])}) |",
        f"| TM-A | CRPS delta {_boot(a['bootstrap'])} | **{v['TM-A']}** |",
        f"| TM-A incumbent | 80% coverage | {_cov(a['incumbent']['coverage80'])} |",
        f"| TM-A candidate | 80% coverage | {_cov(a['candidate']['coverage80'])} |",
    ]
    dc = a.get("dev_coverage80")
    if dc:
        lines.append(f"| TM-A DEV coverage beside (section 3.1) | incumbent / candidate (in-sample) | "
                     f"{_cov(dc.get('incumbent'))} / {_cov(dc.get('candidate_in_sample'))} |")
    lines += [
        f"| TM-B served_recentered | wins MAE | {_f(b['served_recentered']['mae'])} (bias {_f(b['served_recentered']['bias'])}, r {_f(b['served_recentered']['r'])}) |",
        f"| TM-B budgeted (PA {_f(b['budget']['pa'], 1)}, IP {_f(b['budget']['ip'], 1)}; after the 2,430 pin) | wins MAE | "
        f"{_f(b['budgeted']['mae'])} (bias {_f(b['budgeted']['bias'])}, r {_f(b['budgeted']['r'])}) |",
        f"| TM-B | abs-error delta {_boot(b['bootstrap'])} | **{v['TM-B']}** |",
        f"| TM-B | clubs over the PA / IP budget | {b['clubs_over_budget']['pa']} / {b['clubs_over_budget']['ip']} |",
    ]
    for side, label in (("rs", "RS"), ("ra", "RA")):
        s = c[side]
        lines.append(f"| TM-C | {label} MAE (runs) | {_f(s['mae'], 1)} (n {s['n']}) |")
        for comp, name in (("vs_carry_forward", "carry-forward"), ("vs_league_avg", "league average")):
            cc = s.get(comp)
            if cc:
                lines.append(f"| TM-C | {label} vs {name}: comparator MAE / delta / ub95 | "
                             f"{_f(cc['comparator_mae'], 1)} / {_f(cc['bootstrap'].get('mean'), 2)} / "
                             f"{_f(cc['bootstrap'].get('ub95'), 2)} |")
            else:
                lines.append(f"| TM-C | {label} vs {name} | null (no prior) |")
        lines.append(f"| TM-C | {label} verdict (ub95 < 0 against both) | **{v['TM-C'][side]}** |")
    sw = c.get("served_wins_same_clubs") or {}
    lines.append(f"| TM-C | Pythag wins MAE (served wins MAE beside, same clubs; no verdict) | "
                 f"{_f(c['pythag_wins']['mae'], 2)} ({_f(sw.get('mae'), 2)}; n {c['pythag_wins']['n']}) |")
    li = c.get("league_identity") or {}
    if li and li.get("rs_minus_ra") is not None:
        lines.append(f"| TM-C | league identity, sum RS minus sum RA (runs; 1% tolerance, reported only) | "
                     f"{_f(li.get('rs_minus_ra'), 1)} (RS minus 30 x league {_f(li.get('rs_minus_league'), 1)}, "
                     f"RA minus 30 x league {_f(li.get('ra_minus_league'), 1)}; "
                     f"{'within' if li.get('within_tol') else 'outside'} tolerance) |")
    missing = sorted(set(a.get("missing") or []) | set(b.get("missing") or [])
                     | set(c["rs"].get("missing") or []) | set(c["ra"].get("missing") or []))
    lines += [
        "",
        f"**Clubs scored nowhere (named, never imputed):** {', '.join(missing) if missing else 'none'}.",
        "",
        "**Verdicts by the registered rules only (section 3; a null is a finding).** "
        f"TM-A {v['TM-A']}; TM-B {v['TM-B']}; TM-C RS {v['TM-C']['rs']}, RA {v['TM-C']['ra']}. "
        + "; ".join(f"{flag} {'eligible' if ok else 'not eligible'}" for flag, ok in block["flags_eligible"].items())
        + ". A pass makes its flag eligible and flips nothing (section 5.1); the class 3 flips also need "
        "owner answer TM-Q1 (answered: serve each that passes) and land as TM_8's own commits; a null or a "
        "fail keeps the incumbent. Nothing served moves at this look.",
        "",
        "**Bans kept (section 7).** No player-level 2026 residual, cohort or MAE (the frame rows carry no "
        "actual WAR, asserted by team_frame); no team statistic by consensus-FV cell; both arms aging v2; "
        "the labels and run parts are the frozen fWAR vintage (FanGraphs frame); no cohort intercept and no "
        "team-level recalibration (the T3 league identity is reported, not corrected); no second look.",
        "",
        f"The block is `team_projection_gate.gate_2026` in `data/team_outlook_eval.json` (per-club table, "
        f"both arms' CRPS, the T2 accounting, the bootstraps); the registry rows team_win_distribution and "
        f"team_run_projection point at it and stay provisional whatever the outcome (section 5.2); "
        f"team_win_projections carries TM-B's dated note. Elapsed {block.get('elapsed_s')} s.",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# fixtures with nulls (the dry run; every code is a fixture, not a reading)
# --------------------------------------------------------------------------

def fixture_inputs() -> dict:
    """A DEV-shaped fixture frame (2025) with a club carrying no rows (TBR),
    a club with actuals but no frame rows and so no samples (BAL), a missing
    RS (BOS), a missing prior RA (TBR), a club missing from the prior (BAL),
    a fixture schedule and a fixture runs frame with a null RS."""
    import proj_backtest as PB
    rows = [
        {"mlbam": 1, "target": 2025, "side": "hit", "role": "H", "band": "26-29", "age": 27, "pred": 4.0, "pa_proj": 600.0},
        {"mlbam": 2, "target": 2025, "side": "pit", "role": "SP", "band": "30-33", "age": 31, "pred": 2.0, "ip_proj": 180.0},
        {"mlbam": 3, "target": 2025, "side": "hit", "role": "C", "band": "0-25", "age": 24, "pred": 1.0, "pa_proj": 300.0},
        {"mlbam": 4, "target": 2025, "side": "pit", "role": "RP", "band": "34-99", "age": 35, "pred": 0.5, "ip_proj": 60.0},
        {"mlbam": 5, "target": 2025, "side": "hit", "role": "H", "band": "26-29", "age": 28, "pred": 2.5, "pa_proj": 5500.0},
        {"mlbam": 6, "target": 2025, "side": "pit", "role": "SP", "band": "26-29", "age": 29, "pred": 3.0, "ip_proj": 1500.0},
    ]
    teams = {(1, 2025): "NYY", (2, 2025): "NYY", (3, 2025): "BOS", (4, 2025): "BOS", (5, 2025): "BOS", (6, 2025): "BOS"}
    exposure = {"NYY": {"pa": 6100.0, "ip": 1440.0}, "BOS": {"pa": 6200.0, "ip": 1450.0}}
    actual_wins = {"NYY": 94, "BOS": 81, "TBR": 70}
    frame = PB.team_frame(2025, rows=rows, teams=teams, exposure=exposure, actual_wins=actual_wins)
    actual = {"NYY": {"wins": 94, "losses": 68, "rs": 800, "ra": 700, "gp": 162},
              "BOS": {"wins": 81, "losses": 81, "rs": None, "ra": 720, "gp": 162},
              "TBR": {"wins": 70, "losses": 91, "rs": 650, "ra": 660, "gp": 161},
              "BAL": {"wins": 85, "losses": 77, "rs": 700, "ra": 690, "gp": 162}}
    prior = {"NYY": {"rs": 790, "ra": 690}, "BOS": {"rs": 750, "ra": 730}, "TBR": {"rs": 640, "ra": None}}
    pairs = ([("NYY", "BOS")] * 12 + [("BOS", "TBR")] * 12 + [("TBR", "NYY")] * 12 + [("NYY", "BAL")] * 3)

    def runs_fn(fr, scales):
        return {"season": 2025,
                "clubs": {"NYY": {"rs": 810.0, "ra": 705.0, "runDiff": 105.0, "pythW": 92.0, "pf": 1.0},
                          "BOS": {"rs": None, "ra": 710.0, "runDiff": None, "pythW": None, "pf": 1.02},
                          "TBR": {"rs": 655.0, "ra": 670.0, "runDiff": -15.0, "pythW": 79.5, "pf": 0.98}},
                "league": {"sum_rs_minus_sum_ra": None, "note": "fixture"},
                "meta": {"frame": "fixture", "park_factor": None}}

    return {"frame": frame, "actual": actual, "prior": prior, "pairs": pairs, "runs_fn": runs_fn}


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def _git(args: list[str]) -> str | None:
    import subprocess
    try:
        return subprocess.check_output(["git", *args], cwd=str(ROOT), text=True).strip()
    except Exception:                                          # noqa: BLE001
        return None


def run(out_dir: Path, *, dry_run: bool, write: bool, n_sims: int | None, B: int | None) -> int:
    import proj_backtest as PB
    import team_projection as TP
    import team_projection_dev as DEV

    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    params = check_preconditions(dry_run=dry_run)
    sha = TP.params_hash(params)
    B = int(B or params["bootstrap"]["B"])
    today = _dt.date.today().isoformat()
    head, branch = _git(["rev-parse", "--short", "HEAD"]), _git(["rev-parse", "--abbrev-ref", "HEAD"])
    hash_seed = os.environ.get("PYTHONHASHSEED")
    dev_receipt = None
    if TP.DEV_RECEIPT_PATH.exists():
        dev_receipt = json.loads(TP.DEV_RECEIPT_PATH.read_text(encoding="utf-8"))
    print(f"{TASK}: {'DRY RUN on fixtures with nulls' if dry_run else 'THE LOOK'} {today} at {head} "
          f"({branch}); params sha256 {sha}; PYTHONHASHSEED {hash_seed}; B {B}; seed {SEED_LOOK}", flush=True)

    if dry_run:
        fx = fixture_inputs()
        frame, actual, prior, pairs, runs_fn = (fx["frame"], fx["actual"], fx["prior"], fx["pairs"], fx["runs_fn"])
        n_sims = int(n_sims or DRY_SIMS)
        sched_meta = {"n_games": len(pairs), "source": "fixture"}
        season, early_note = 2025, "A dry run on fixtures; no 2026 club quantity was read."
    else:
        import fa_projection as fp
        n_sims = int(n_sims or params["sim"]["n_sims"])
        season = PB.GATE_SEASON
        print("corpus and frame", flush=True)
        corpus = fp.build_corpus()
        frame = PB.team_frame(season, corpus, look=True, aging=params["aging"])
        for c in frame["clubs"].values():
            for p in c["players"]:
                assert p.get("act") is None and p.get("war_act") is None
        print(f"frame {season}: {frame['league']['n_clubs']} clubs, {frame['league']['n_rows']} rows, "
              f"{frame['league']['n_assigned']} assigned, {time.time() - t0:.1f}s", flush=True)
        pairs, sched_meta = DEV.season_pairs(season)
        print(f"schedule {season}: {sched_meta['n_games']} games ({sched_meta['source']})", flush=True)
        actual = PB.club_actuals(season, look=True)
        complete = [o for o, v in actual.items() if v.get("wins") is not None and v.get("rs") is not None
                    and v.get("ra") is not None]
        if len(complete) < 30:
            raise LookRefused(f"the {season} frame is incomplete: {len(complete)} clubs with wins, RS and RA")
        prior = {o: {"rs": v.get("rs"), "ra": v.get("ra")} for o, v in PB.club_actuals(season - 1).items()}
        print(f"actuals {season}: {len(actual)} clubs ({len(complete)} complete); prior {season - 1}: "
              f"{len(prior)} clubs", flush=True)

        def runs_fn(fr, scales):
            return DEV.runs_frame(season, corpus, fr, scales)

        early_note = ("An OWNER-WAIVED EARLY READ (EW3-5, owner 2026-10-14): registered for 2026-12-08 and "
                      "for the first day after the DEV freeze landed on which no other look is recorded; "
                      "both waived, the frame itself complete (the 2026 regular season is final).")

    print("SCORING BEGINS (an exception from here on is a STOP, no rerun)", flush=True)
    block = score_look(frame, actual, prior, pairs, params, runs_fn=runs_fn, n_sims=n_sims, B=B,
                       seed=SEED_LOOK, dev_receipt=dev_receipt)
    gps = sorted({v.get("gp") for v in actual.values() if v.get("gp") is not None})
    block.update({
        "task": TASK, "look_date": today, "frame": frame.get("frame"), "season": season,
        "dry_run": bool(dry_run), "head": head, "branch": branch, "python_hash_seed": hash_seed,
        "params_sha256": sha, "params_path": str(TP.PARAMS_PATH.relative_to(ROOT)).replace("\\", "/"),
        "params": {k: params[k] for k in ("sigma_T", "s_res", "s_sched", "k_pseudo_games", "talent_clip",
                                           "budget", "sim", "aging", "frozen_on", "head")},
        "early_read_note": early_note,
        "inputs": {"n_clubs": frame["league"]["n_clubs"], "n_rows": frame["league"]["n_rows"],
                   "n_assigned": frame["league"]["n_assigned"],
                   "unassigned_n": frame["unassigned"]["n"], "unassigned_war": frame["unassigned"]["war_proj_sum"],
                   "roster_war_sum": frame["league"]["roster_war_sum"],
                   "exposure_mean": frame["league"]["exposure_mean"],
                   "design": frame.get("design"), "aging": frame.get("aging"),
                   "schedule_n_games": sched_meta.get("n_games"), "schedule_source": sched_meta.get("source"),
                   "schedule_file": sched_meta.get("file"),
                   "n_clubs_actual": len(actual), "gp_set": gps, "prior_season": season - 1,
                   "standings_file": (None if dry_run else f".cache/statsapi_standings_{season}.json")},
        "elapsed_s": round(time.time() - t0, 1),
    })
    entry = render_entry(block)
    (out_dir / ("dry_run_block.json" if dry_run else "gate_2026_block.json")).write_text(
        json.dumps(block, indent=1, default=str) + "\n", encoding="utf-8")
    (out_dir / ("dry_run_entry.md" if dry_run else "gate_entry.md")).write_text(entry, encoding="utf-8")
    print(entry, flush=True)
    print(json.dumps({"verdicts": block["verdicts"], "flags_eligible": block["flags_eligible"],
                      "tm_a": {"inc": block["tm_a"]["incumbent"]["crps_mean"], "cand": block["tm_a"]["candidate"]["crps_mean"],
                               "boot": {k: block["tm_a"]["bootstrap"].get(k) for k in ("mean", "ub95", "n", "pass")}},
                      "tm_b": {"served": block["tm_b"]["served_recentered"]["mae"], "budgeted": block["tm_b"]["budgeted"]["mae"],
                               "boot": {k: block["tm_b"]["bootstrap"].get(k) for k in ("mean", "ub95", "n", "pass")}},
                      "tm_c": {"rs_mae": block["tm_c"]["rs"]["mae"], "ra_mae": block["tm_c"]["ra"]["mae"],
                               "pass": block["verdicts"]["TM-C"], "pythag": block["tm_c"]["pythag_wins"]["mae"]},
                      "elapsed_s": block["elapsed_s"]}, indent=1, default=str), flush=True)
    if write and not dry_run:
        PB.write_team_gate_block(block, key=GATE_KEY)
        print(f"wrote team_projection_gate.{GATE_KEY} to {PB.EVAL_PATH}", flush=True)
    elif write:
        print("dry run: nothing written under data/", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="the task's output directory")
    ap.add_argument("--dry-run", action="store_true", help="fixtures with nulls; reads no 2026 club quantity")
    ap.add_argument("--write", action="store_true", help="write team_projection_gate.gate_2026 (once)")
    ap.add_argument("--sims", type=int, default=None)
    ap.add_argument("--B", type=int, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.dry_run and os.environ.get("PYTHONHASHSEED") != "0":
        print("REFUSED: the look runs under PYTHONHASHSEED=0 (the DEV record's process seed, TM_3 finding 5)",
              file=sys.stderr)
        return 2
    try:
        return run(args.out, dry_run=args.dry_run, write=args.write, n_sims=args.sims, B=args.B)
    except LookRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except Exception:                                          # noqa: BLE001
        traceback.print_exc()
        print("STOP: an exception after the run began; no rerun (section 4.3)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

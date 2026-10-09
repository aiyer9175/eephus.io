# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Retro point-in-time backtest: the league-wide veteran engine + the
Team Outlook win roll-up, scored against real past seasons (owner ask
2026-06-12, after the level-bias finding: rosters carried 560 of the
league's 1000 bWAR and the best team read 83 wins).

  DESIGN    For each target season Y in TARGETS: aging curves + WAR map
            refit on data through Y-1 (fp.fitted_models - the Gate-1
            no-lookahead pattern), every player with >=1 input season in
            Y-3..Y-1 projected for Y, actual bWAR = 0 when absent (he
            delivered nothing). Teams: each projected player assigned to
            his PRIMARY actual season-Y team (max exposure stint from
            the B-Ref war_daily stint rows) - this isolates engine error
            from roster-construction error and is disclosed. Players
            with no season-Y team drop from team sums (their WAR never
            materialized for anyone); the recentering absorbs the level.
  SCORES    player level: bias / MAE / r, pooled + by side x age band;
            team level per season: wins MAE + Pearson r for (a) raw
            47.7+roster WAR, (b) league-sum recentered (the SHIPPED
            display calibration), (c) cohort-intercept calibrated +
            recentered (the pre-registered challenger), vs the
            (d) prior-season-wins carry-forward baseline.
  GATE      cohort intercepts (side x age band, additive) fit on
            TARGETS[:-1] residuals only, applied to the held-out final
            target. Ship if held-out team MAE beats the uniform
            recentering; publish either way.
  ARTIFACT  data/team_outlook_eval.json gains a "retro_backtest" block
            (proj_export preserves it across re-exports).

Run: python proj_backtest.py
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import fa_projection as fp
from rate_stabilization import REPLACEMENT_WINS   # shared with proj_export

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
EVAL_PATH = DATA_DIR / "team_outlook_eval.json"

TARGETS = (2022, 2023, 2024, 2025)      # last one = the held-out gate season
LEAGUE_WINS = 2430.0
AGE_BANDS = ((0, 25), (26, 29), (30, 33), (34, 99))
BREF_ORG_FIX = {"OAK": "ATH", "WSH": "WSN", "ANA": "LAA", "TBD": "TBR",
                "FLA": "MIA", "KCA": "KCR"}


def _age_band(age) -> str:
    a = int(age) if age else 28          # unknown age: prime-band prior
    for lo, hi in AGE_BANDS:
        if lo <= a <= hi:
            return f"{lo}-{hi}"
    return "34-99"


def _primary_teams() -> dict[tuple[int, int], str]:
    """(mlbam, season) -> primary org code, from the B-Ref war_daily
    stint rows (max exposure stint wins; PA for bats, IPouts for arms),
    read through the war_source facade (provider 'bwar')."""
    import war_source
    best: dict[tuple[int, int], tuple[float, str]] = {}
    for side, expo_col in (("bat", "PA"), ("pit", "IPouts")):
        df = war_source.stint_frame(side)
        cols = {c.lower(): c for c in df.columns}
        team_c = cols.get("team_id")
        expo_c = cols.get(expo_col.lower()) or cols.get("g")
        sub = df[df["mlb_ID"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid = int(getattr(row, "mlb_ID"))
                yr = int(getattr(row, "year_ID"))
            except (TypeError, ValueError):
                continue
            team = str(getattr(row, team_c) or "")
            team = BREF_ORG_FIX.get(team, team)
            if len(team) != 3 or team == "TOT":
                continue
            expo = float(getattr(row, expo_c) or 0)
            key = (mid, yr)
            if key not in best or expo > best[key][0]:
                best[key] = (expo, team)
    return {k: v[1] for k, v in best.items()}


def _mae(pairs):
    return (sum(abs(p - a) for p, a in pairs) / len(pairs)) if pairs else None


def _r(pairs):
    if len(pairs) < 3:
        return None
    xs = [p for p, _ in pairs]
    ys = [a for _, a in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _project_targets() -> list[dict]:
    """One row per (player, target): projected vs actual WAR + cohort tags."""
    corpus = fp.build_corpus()
    league = corpus["league"]
    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    rows: list[dict] = []
    for target in TARGETS:
        curves, war_map = fp.fitted_models(corpus, target - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[s] for s in (target - 1, target - 2, target - 3)
                        if s in seasons]
                if not hist:
                    continue
                # Anchor the age offset to the row that supplied the age.
                age_row = next((h for h in hist if h.get("age")), None)
                age = (age_row["age"] + (target - age_row["season"])) if age_row else None
                proj = fp.project_player(hist, side, target, curves, league, age)
                if proj is None:
                    continue
                war_pred = fp.war_from_projection(proj, side, war_map, league, target)
                act_row = seasons.get(target)
                war_act = (act_row.get("war") if act_row and act_row.get("war") is not None
                           else 0.0)
                rows.append({"mlbam": mlbam, "target": target, "side": side,
                             "band": _age_band(age), "pred": float(war_pred or 0.0),
                             "act": float(war_act)})
    return rows


def _served_intercepts() -> dict[str, float]:
    """The cohort-intercept vector proj_export ACTUALLY SERVES right now.

    Mirrors proj_export._cohort_intercepts exactly: read the committed artifact,
    and return {} unless its own ship_decision says the challenger won. Kept as a
    local read rather than an import so the backtest cannot pull the exporter's
    module-level machinery into a measurement run.

    Why this exists: the gate below scores a FRESH refit against plain
    recentering, and never scored the vector actually in production. Those are
    different questions, and on 2026-08-04 they had different answers - the
    fresh refit LOST (7.27 vs 7.21) while the committed 2026-06-12 vector was
    MAE-neutral (7.18 vs 7.21). Without this arm the artifact could not say
    whether what ships was helping, hurting, or doing nothing.
    """
    try:
        d = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        rb = d.get("retro_backtest") or {}
        if not ((rb.get("ship_decision") or {}).get("challenger_wins")):
            return {}
        return rb.get("cohort_intercepts_fit_2022_24") or {}
    except (OSError, ValueError):
        return {}


def _holdout_gap_ci(served: dict, prior: dict, act_wins: dict) -> dict:
    """LIBRARY_14: the paired interval on the served win vector's holdout MAE
    improvement over prior-season wins carried forward (prior minus served, so
    positive means the served vector is better). Team-clustered, one row per
    club; the recentered wins are held as computed, nothing is refit."""
    import numpy as np
    import gap_intervals as gi
    orgs = sorted(act_wins)
    act = np.array([float(act_wins[o]) for o in orgs])
    e_s = np.abs(np.array([served[o] for o in orgs], float) - act)
    e_p = np.abs(np.array([prior[o] for o in orgs], float) - act)

    def gaps(idx):
        return {"mae": float(e_p[idx].mean() - e_s[idx].mean())}

    return gi.paired_cluster_interval(orgs, gaps, seed=gi.SEED, cluster="team (org)")


def _team_tables(rows, teams, standings):
    """Per-season team scoring for every calibration variant."""
    out = []
    fit_targets = TARGETS[:-1]
    holdout = TARGETS[-1]
    # cohort intercepts: mean(actual - pred) per side x band on fit targets
    coh_n: dict[tuple, int] = defaultdict(int)
    coh_sum: dict[tuple, float] = defaultdict(float)
    for r in rows:
        if r["target"] in fit_targets:
            coh_sum[(r["side"], r["band"])] += r["act"] - r["pred"]
            coh_n[(r["side"], r["band"])] += 1
    intercepts = {k: coh_sum[k] / coh_n[k] for k in coh_n if coh_n[k] >= 100}

    # The vector proj_export ACTUALLY SERVES, read exactly the way it reads it
    # (committed artifact, gated on its own ship_decision). The gate below scores
    # a FRESH refit against plain recentering and has never scored this, so
    # "is what ships helping" was a question the artifact could not answer.
    served = _served_intercepts()

    for target in TARGETS:
        act_wins = standings.get(target) or {}
        prior_wins = standings.get(target - 1) or {}
        if len(act_wins) < 28:
            continue
        sums_raw: dict[str, float] = defaultdict(float)
        sums_coh: dict[str, float] = defaultdict(float)
        sums_srv: dict[str, float] = defaultdict(float)
        assigned = 0
        act_assigned = 0.0
        pred_assigned = 0.0
        for r in (x for x in rows if x["target"] == target):
            org = teams.get((r["mlbam"], target))
            if not org or org not in act_wins:
                continue
            assigned += 1
            act_assigned += r["act"]
            pred_assigned += r["pred"]
            sums_raw[org] += r["pred"]
            sums_coh[org] += r["pred"] + intercepts.get((r["side"], r["band"]), 0.0)
            sums_srv[org] += r["pred"] + served.get(f"{r['side']}:{r['band']}", 0.0)

        def wins_of(sums, recenter):
            w = {o: REPLACEMENT_WINS + sums.get(o, 0.0) for o in act_wins}
            if recenter:
                shift = (LEAGUE_WINS - sum(w.values())) / len(w)
                w = {o: v + shift for o, v in w.items()}
            return w

        variants = {
            "raw": wins_of(sums_raw, False),
            "recentered": wins_of(sums_raw, True),
            "cohort_recentered": wins_of(sums_coh, True),
            "served_recentered": wins_of(sums_srv, True),
            "baseline_prior_wins": {o: float(prior_wins.get(o, 81.0)) for o in act_wins},
        }
        row = {"season": target, "n_assigned_players": assigned,
               "roster_war_sum": round(sum(sums_raw.values()), 1),
               # The LEVEL check, which no recentered MAE can see: recentering
               # forces the league to a constant, so a systematic per-player
               # shortfall cancels out of every recentered number while
               # accumulating in this sum. The 2026-08-04 measurement found the
               # engine under-projecting real 2025 rosters by 88.1 WAR while
               # every recentered metric looked fine, so the series is emitted
               # rather than left to a scratch script.
               "assigned_actual_war": round(act_assigned, 1),
               "assigned_pred_war": round(pred_assigned, 1),
               "assigned_level_deficit": round(pred_assigned - act_assigned, 1),
               "is_holdout": target == holdout}
        for name, w in variants.items():
            pairs = [(w[o], float(act_wins[o])) for o in act_wins]
            row[name] = {"mae": round(_mae(pairs), 2), "r": round(_r(pairs) or 0, 3)}
        if target == holdout:
            row["_gap_ci"] = _holdout_gap_ci(variants["served_recentered"],
                                             variants["baseline_prior_wins"], act_wins)
        out.append(row)
    return out, {f"{s}:{b}": round(v, 3) for (s, b), v in sorted(intercepts.items())}


def run(persist: bool = True) -> dict:
    import fa_fit_backtest as ffb
    rows = _project_targets()
    log.info("projected %d player-target rows", len(rows))
    teams = _primary_teams()
    standings = {}
    for y in range(min(TARGETS) - 1, max(TARGETS) + 1):
        standings[y] = ffb.standings_wins(y)

    # ---- player-level metrics ------------------------------------------
    def _stats(sel):
        pairs = [(r["pred"], r["act"]) for r in sel]
        bias = (sum(a - p for p, a in pairs) / len(pairs)) if pairs else None
        return {"n": len(pairs), "bias_act_minus_pred": round(bias, 3) if bias is not None else None,
                "mae": round(_mae(pairs), 3) if pairs else None,
                "r": round(_r(pairs) or 0, 3)}

    player_block = {"pooled": _stats(rows)}
    # POOLED DILUTES BY 1.75x, and the registry quoted the diluted figure for
    # two months. Roughly 4,019 of the 8,866 scored rows are players who never
    # took a roster spot in the target season, so their actual WAR is 0 BY
    # CONSTRUCTION and their error is near-zero by construction with it. They
    # drag the pooled bias toward zero while contributing nothing to any team
    # sum. The assigned-roster rows are the population every team-level number
    # is actually built from, so they get their own block and the registry
    # quotes THAT one.
    assigned_rows = [r for r in rows if teams.get((r["mlbam"], r["target"]))]
    player_block["assigned_only"] = _stats(assigned_rows)
    player_block["unassigned_only"] = _stats(
        [r for r in rows if not teams.get((r["mlbam"], r["target"]))])
    player_block["_reading"] = (
        "pooled mixes rostered players with players who never took a roster spot "
        "(actual WAR 0 by construction); assigned_only is the population the team "
        "roll-up is built from and is the one to quote")
    for side in ("hit", "pit"):
        for lo, hi in AGE_BANDS:
            band = f"{lo}-{hi}"
            sel = [r for r in rows if r["side"] == side and r["band"] == band]
            player_block[f"{side}:{band}"] = _stats(sel)

    team_rows, intercepts = _team_tables(rows, teams, standings)
    holdout = next((t for t in team_rows if t["is_holdout"]), None)
    holdout_gap = holdout.pop("_gap_ci", None) if holdout else None
    ship_cohort = bool(holdout
                       and holdout["cohort_recentered"]["mae"] < holdout["recentered"]["mae"])

    result = {
        "generated_at": date.today().isoformat(),
        "design": {
            "targets": list(TARGETS), "holdout": TARGETS[-1],
            "no_lookahead": "curves + WAR map refit per target on data through Y-1 (Gate-1 pattern)",
            "team_assignment": "primary actual season-Y team by exposure stint (B-Ref war_daily); isolates engine error from roster churn - disclosed",
            "population": "every player with >=1 input season in Y-3..Y-1; absent target season scores actual WAR 0; new entrants (rookies/IFA, ~61 WAR/season) are outside the veteran engine and absorbed by the recentering level",
        },
        "player_level": player_block,
        "cohort_intercepts_fit_2022_24": intercepts,
        "team_level_per_season": team_rows,
        "ship_decision": {
            "challenger": "cohort intercepts (side x age band) + recentering",
            "incumbent": "uniform league-sum recentering (shipped 2026-06-12)",
            "holdout_season": TARGETS[-1],
            "challenger_wins": ship_cohort,
            "holdout_mae": {k: holdout[k]["mae"] for k in
                            ("raw", "recentered", "cohort_recentered",
                             "served_recentered", "baseline_prior_wins")} if holdout else None,
            "served_vector_note": (
                "served_recentered scores the vector proj_export actually serves "
                "today, which the challenger-vs-incumbent comparison does not. A "
                "served arm that matches 'recentered' means the vector is doing "
                "nothing; worse means it is actively costing wins."),
            "holdout_gap_ci_vs_prior_wins": holdout_gap,
        },
    }
    if persist:
        try:
            cur = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}
        cur["retro_backtest"] = result
        EVAL_PATH.write_text(json.dumps(cur, indent=1), encoding="utf-8")
        log.info("wrote retro_backtest block -> %s", EVAL_PATH)
    return result


# ============================================================================
# Team projection scorer (TM_2_TEAM_SCORER; docs/TEAM_PROJECTIONS_GATE.md)
# ============================================================================
# The scoring path the team gates TM-A, TM-B and TM-C read (LANE_A section
# 3.3). Everything below is NEW and changes nothing above it: TARGETS, run(),
# _team_tables and the __main__ block are pinned by source hash in
# test_team_projection_scorer.py. Frames: DEV is the retro seasons in TARGETS
# (read); GATE is the 2026 club season, read once by TM_4 and never before;
# nothing here computes a player-level 2026 residual, cohort or MAE.

GATE_SEASON = 2026                  # the GATE frame: one look, never a DEV season
TEAM_AGING = "v2"                   # both TM arms pass aging="v2" explicitly (U5)
TM_BOOTSTRAP_B = 2000               # section 3: clubs resampled with replacement
TM_SEED_GATE_2026 = 20261208        # section 3.1 to 3.3
TM_SEED_FORWARD_2027 = 20271116     # section 3.4
COVERAGE_LO, COVERAGE_HI = 0.10, 0.90   # the 80% range, inclusive
TALENT_PCT_CLAMP = (0.20, 0.80)     # proj_export._talent_prior_pct's rails
PYTHAGENPAT_EXP = 0.287             # proj_export._PYTHAGENPAT_EXP
GATE_BLOCK_KEY = "team_projection_gate"   # the eval artifact's look block
TEAM_FRAME_TARGETS = TARGETS + (GATE_SEASON,)


def _gate_already_read(path: Path | None = None, key: str = "gate_2026") -> bool:
    """True once the eval artifact carries the GATE look's result, which makes
    every further look=True call an early second look and refused. ``path``
    defaults to EVAL_PATH as it stands at call time."""
    try:
        d = json.loads((path or EVAL_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool((d.get(GATE_BLOCK_KEY) or {}).get(key))


def _project_season(target: int, corpus: dict, *, aging: str = TEAM_AGING) -> list[dict]:
    """One row per point-in-time player for ``target``: the champion mean WAR
    and projected PA (hitters) or IP (pitchers) from the retro design of
    _project_targets (curves and WAR map refit on data through target - 1,
    every player with an input season in target-3..target-1). The actual WAR
    is attached for a DEV target only; the GATE season never carries one."""
    if aging != TEAM_AGING:
        raise ValueError(f"aging={aging!r}: the team frame runs on aging {TEAM_AGING!r} only (U3, U5)")
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, target - 1)
    is_gate = target == GATE_SEASON
    rows: list[dict] = []
    for side in ("hit", "pit"):
        by_player: dict[int, dict[int, dict]] = defaultdict(dict)
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[r["mlbam"]][r["season"]] = r
        for mlbam, seasons in by_player.items():
            hist = [seasons[s] for s in (target - 1, target - 2, target - 3) if s in seasons]
            if not hist:
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            age = (age_row["age"] + (target - age_row["season"])) if age_row else None
            proj = fp.project_player(hist, side, target, curves, league, age)
            if proj is None:
                continue
            war_pred = fp.war_from_projection(proj, side, war_map, league, target)
            row = {"mlbam": mlbam, "target": target, "side": side,
                   "role": proj.get("role"), "band": _age_band(age), "age": age,
                   "pred": float(war_pred or 0.0)}
            if side == "hit":
                row["pa_proj"] = float(proj.get("pt_proj") or 0.0)
            else:
                row["ip_proj"] = float(proj.get("ip_proj") or 0.0)
            if not is_gate:
                act_row = seasons.get(target)
                row["act"] = float(act_row.get("war") if act_row and act_row.get("war") is not None
                                   else 0.0)
            rows.append(row)
    return rows


def _club_exposure(season: int) -> dict[str, dict]:
    """{org: {'pa', 'ip'}} actual club exposure for ``season`` from the B-Ref
    war_daily stint rows (PA for bats, IPouts / 3 for arms), the same frame and
    org fix _primary_teams reads. Exposure only: no WAR column is read."""
    import war_source
    out: dict[str, dict] = defaultdict(lambda: {"pa": 0.0, "ip": 0.0})
    for side, expo_col, key, scale in (("bat", "PA", "pa", 1.0), ("pit", "IPouts", "ip", 1.0 / 3.0)):
        df = war_source.stint_frame(side)
        cols = {c.lower(): c for c in df.columns}
        team_c = cols.get("team_id")
        expo_c = cols.get(expo_col.lower())
        if not team_c or not expo_c:
            continue
        sub = df[df["year_ID"] == season]
        for row in sub.itertuples(index=False):
            team = BREF_ORG_FIX.get(str(getattr(row, team_c) or ""), str(getattr(row, team_c) or ""))
            if len(team) != 3 or team == "TOT":
                continue
            try:
                out[team][key] += float(getattr(row, expo_c) or 0) * scale
            except (TypeError, ValueError):
                continue
    return {o: {"pa": round(v["pa"], 1), "ip": round(v["ip"], 1)} for o, v in out.items()}


def _actuals_from_standings(table: dict, season: int) -> dict[str, dict]:
    """{org: {'wins', 'losses', 'rs', 'ra', 'gp'}} for ``season`` from the
    {code: {season: row}} table franchise_export._standings returns. A club
    whose row has no win count is left out (a null is a finding, not a 0)."""
    out: dict[str, dict] = {}
    for org, seasons in (table or {}).items():
        row = (seasons or {}).get(season) or (seasons or {}).get(str(season))
        if not row or row.get("w") is None:
            continue
        out[org] = {"wins": int(row["w"]),
                    "losses": int(row["l"]) if row.get("l") is not None else None,
                    "rs": int(row["rs"]) if row.get("rs") is not None else None,
                    "ra": int(row["ra"]) if row.get("ra") is not None else None,
                    "gp": int(row["gp"]) if row.get("gp") is not None else None}
    return out


def club_actuals(season: int, *, look: bool = False, table: dict | None = None) -> dict[str, dict]:
    """Actual club wins, runs scored and runs allowed for ``season`` through
    the one standings parser (franchise_export._standings, master plan 8.E),
    which reads .cache/statsapi_standings_<season>.json. The GATE season and
    anything after it are read only at the look (look=True)."""
    if season >= GATE_SEASON and not look:
        raise RuntimeError(f"club_actuals({season}): the {GATE_SEASON} club season is the GATE frame; "
                           "its actual wins, RS and RA are read only at the registered look (look=True)")
    if look and _gate_already_read():
        raise RuntimeError("the GATE look is already recorded in the eval artifact; no second look")
    if table is None:
        import franchise_export
        table = franchise_export._standings()[0]
    return _actuals_from_standings(table, season)


def _talent_pct(win_total: float) -> float:
    """proj_export._talent_prior_pct's clamp, kept local so the backtest does
    not import the exporter's module-level machinery (pinned by test)."""
    lo, hi = TALENT_PCT_CLAMP
    return min(hi, max(lo, float(win_total) / 162.0))


def team_frame(target: int, corpus: dict | None = None, *, look: bool = False,
               aging: str = TEAM_AGING, rows: list[dict] | None = None,
               teams: dict | None = None, exposure: dict | None = None,
               actual_wins: dict | None = None, clubs=None) -> dict:
    """Per club, the point-in-time projection the team gates score.

    ``target`` is a DEV season (TARGETS) or GATE_SEASON. Each club carries its
    players (champion mean WAR, projected PA or IP, side, role, age band),
    their actual-roster assignment by the existing primary-stint rule
    (_primary_teams), the roster WAR sum, the raw, recentered and
    served_recentered win roll-ups of _team_tables, the talent prior p_prior
    the simulator consumes (T1), the club's actual exposure (the T2 budget
    hook) and, on a DEV season, its actual wins. The GATE season needs
    look=True, refuses a second look once the artifact carries gate_2026, and
    never carries a player-level actual (section 2.2 and 7 of the gate).

    ``rows``, ``teams``, ``exposure`` and ``actual_wins`` are injected by the
    look's dry run and the tests; left None they come from the engine
    (_project_season on ``corpus``, built when None), the stint frame and
    fa_fit_backtest.standings_wins (DEV only). ``aging`` is pinned to
    TEAM_AGING: this module adds no age adjustment of its own (U3)."""
    if aging != TEAM_AGING:
        raise ValueError(f"aging={aging!r}: both TM arms pass aging={TEAM_AGING!r} explicitly (U5)")
    if target not in TEAM_FRAME_TARGETS:
        raise ValueError(f"team_frame({target}): the frames are DEV {TARGETS} and GATE {GATE_SEASON}")
    is_gate = target == GATE_SEASON
    if is_gate and not look:
        raise RuntimeError(f"team_frame({GATE_SEASON}) is the GATE look (docs/TEAM_PROJECTIONS_GATE.md "
                           "section 2.2); pass look=True from the registered look only")
    if look and _gate_already_read():
        raise RuntimeError("the GATE look is already recorded in the eval artifact; no second look")
    if rows is None:
        if corpus is None:
            corpus = fp.build_corpus()
        rows = _project_season(target, corpus, aging=aging)
    rows = [r for r in rows if int(r.get("target", target)) == target]
    if is_gate:
        for r in rows:
            if r.get("act") is not None or r.get("war_act") is not None:
                raise RuntimeError(f"a {GATE_SEASON} row carries an actual WAR: no player-level "
                                   f"{GATE_SEASON} residual is computed before the path-shape "
                                   "gate's CONFIRM look (section 7)")
    if teams is None:
        teams = _primary_teams()
    if actual_wins is None and not is_gate:
        import fa_fit_backtest as ffb
        actual_wins = ffb.standings_wins(target)
    if exposure is None:
        exposure = _club_exposure(target)
    served = _served_intercepts()
    if clubs is None:
        clubs = sorted(actual_wins) if actual_wins else sorted(
            {o for (m, y), o in teams.items() if y == target})
    clubs = sorted(set(clubs))
    club_set = set(clubs)
    players: dict[str, list[dict]] = {o: [] for o in clubs}
    unassigned_n, unassigned_war = 0, 0.0
    for r in rows:
        org = teams.get((r["mlbam"], target))
        if not org or org not in club_set:
            unassigned_n += 1
            unassigned_war += float(r.get("pred") or 0.0)
            continue
        players[org].append(r)
    sums_raw = {o: sum(float(p.get("pred") or 0.0) for p in players[o]) for o in clubs}
    sums_srv = {o: sum(float(p.get("pred") or 0.0) + served.get(f"{p.get('side')}:{p.get('band')}", 0.0)
                       for p in players[o]) for o in clubs}

    def wins_of(sums, recenter):
        w = {o: REPLACEMENT_WINS + sums.get(o, 0.0) for o in clubs}
        if recenter and w:
            shift = (LEAGUE_WINS - sum(w.values())) / len(w)
            w = {o: v + shift for o, v in w.items()}
        return w

    raw = wins_of(sums_raw, False)
    rec = wins_of(sums_raw, True)
    srv = wins_of(sums_srv, True)
    shift = ((LEAGUE_WINS - sum(raw.values())) / len(raw)) if raw else None
    out_clubs: dict[str, dict] = {}
    for o in clubs:
        hit = [p for p in players[o] if p.get("side") == "hit"]
        pit = [p for p in players[o] if p.get("side") == "pit"]
        a = actual_wins.get(o) if actual_wins else None
        out_clubs[o] = {
            "players": players[o],
            "n_players": len(players[o]), "n_hit": len(hit), "n_pit": len(pit),
            "roster_war": round(sums_raw[o], 3),
            "pa_proj_sum": round(sum(float(p.get("pa_proj") or 0.0) for p in hit), 1),
            "ip_proj_sum": round(sum(float(p.get("ip_proj") or 0.0) for p in pit), 1),
            "wins_raw": round(raw[o], 3),
            "wins_recentered": round(rec[o], 3),
            "wins_served_recentered": round(srv[o], 3),
            "p_prior": round(_talent_pct(srv[o]), 4),
            "exposure": (exposure or {}).get(o),
            "actual": ({"wins": int(a["wins"] if isinstance(a, dict) else a)}
                       if a is not None else None),
        }
    expo_rows = [v for v in ((exposure or {}).get(o) for o in clubs) if v]
    league = {
        "n_clubs": len(clubs), "n_rows": len(rows),
        "n_assigned": sum(len(players[o]) for o in clubs),
        "roster_war_sum": round(sum(sums_raw.values()), 1),
        "replacement_wins": REPLACEMENT_WINS, "league_wins": LEAGUE_WINS,
        "recenter_shift_per_club": round(shift, 3) if shift is not None else None,
        "served_vector_applied": bool(served),
        "exposure_mean": ({"pa": round(sum(v["pa"] for v in expo_rows) / len(expo_rows), 1),
                           "ip": round(sum(v["ip"] for v in expo_rows) / len(expo_rows), 1),
                           "n_clubs": len(expo_rows)} if expo_rows else None),
    }
    return {
        "target": target, "frame": "GATE" if is_gate else "DEV", "look": bool(look),
        "aging": aging,
        "design": {"engine": "fa_projection champion means; curves and WAR map refit on data "
                             f"through {target - 1} (proj_backtest retro design)",
                   "team_assignment": "primary actual season team by exposure stint (_primary_teams)",
                   "actual_player_war": "DEV seasons only; never the GATE season"},
        "league": league,
        "clubs": out_clubs,
        "unassigned": {"n": unassigned_n, "war_proj_sum": round(unassigned_war, 1)},
    }


def _nearest_rank(sorted_vals: list, q: float):
    """proj_current._percentile's nearest-rank read, kept local and pinned by
    test so the coverage band here is the simulator's own P10 and P90."""
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def _crps_from_samples(sorted_vals: list[float], y: float) -> float:
    """CRPS of an empirical distribution against ``y``, exactly from the
    sorted samples: mean|X_i - y| - (1 / (2 n^2)) sum_i sum_j |X_i - X_j|,
    the double sum taken as 2 sum_{i<j} (X_j - X_i) = 2 sum_i X_i (2i - n + 1)."""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("no samples")
    term1 = sum(abs(x - y) for x in sorted_vals) / n
    pair = sum(x * (2 * i - n + 1) for i, x in enumerate(sorted_vals))
    return term1 - pair / (n * n)


def _wilson(k: int, n: int, z: float = 1.96) -> dict | None:
    """Wilson score interval on a proportion k of n."""
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"lo": round(centre - half, 4), "hi": round(centre + half, 4)}


def _club_bootstrap(deltas, B: int = TM_BOOTSTRAP_B, seed: int = TM_SEED_GATE_2026) -> dict:
    """Section 3's bootstrap on paired per-club deltas (candidate minus
    comparator): clubs resampled with replacement B times under
    numpy.random.default_rng(seed); ub95 is the 95th percentile of the
    resampled mean deltas and the pass rule is ub95 < 0. A None or non-finite
    delta is dropped and named; no club at all is a null (pass None)."""
    import numpy as np
    items = list(deltas.items()) if isinstance(deltas, dict) else list(enumerate(deltas))
    vals, dropped = [], []
    for k, v in items:
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = float("nan")
        if v is None or not math.isfinite(f):
            dropped.append(k)
        else:
            vals.append(f)
    base = {"B": int(B), "seed": int(seed), "dropped": dropped,
            "method": "paired percentile bootstrap over clubs with replacement; ub95 is the 95th "
                      "percentile of the resampled mean deltas (candidate minus comparator); pass is ub95 < 0"}
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "lo05": None, "ub95": None, "pass": None, **base}
    arr = np.asarray(vals, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(int(B), n))
    means = arr[idx].mean(axis=1)
    ub95 = float(np.percentile(means, 95))
    return {"n": n, "mean": round(float(arr.mean()), 4),
            "lo05": round(float(np.percentile(means, 5)), 4), "ub95": round(ub95, 4),
            "pass": bool(ub95 < 0), **base}


def _win_count(v):
    if isinstance(v, dict):
        v = v.get("wins")
    return None if v is None else float(v)


def score_win_distribution(samples_by_club: dict, actual_wins: dict, *,
                           lo: float = COVERAGE_LO, hi: float = COVERAGE_HI) -> dict:
    """TM-A's per-arm read: the CRPS of each club's simulated win-total
    samples against its actual wins, the mean over clubs, and the 80% range
    coverage (actual inside [P10, P90], inclusive, nearest rank) with a
    Wilson 95% interval. A club with no samples or no actual is listed under
    ``missing`` and scored nowhere. The TM-A statistic itself is the paired
    delta of ``crps_by_club`` between the candidate and the incumbent read,
    handed to _club_bootstrap."""
    by_club: dict[str, dict] = {}
    missing: list[str] = []
    for org in sorted(set(samples_by_club or {}) | set(actual_wins or {})):
        s = (samples_by_club or {}).get(org)
        y = _win_count((actual_wins or {}).get(org))
        if not s or y is None:
            missing.append(org)
            continue
        srt = sorted(float(x) for x in s)
        p_lo, p_hi = _nearest_rank(srt, lo), _nearest_rank(srt, hi)
        by_club[org] = {"crps": round(_crps_from_samples(srt, y), 4),
                        "p10": p_lo, "p90": p_hi, "inside80": bool(p_lo <= y <= p_hi),
                        "n_samples": len(srt), "actual": y}
    n = len(by_club)
    k = sum(1 for v in by_club.values() if v["inside80"])
    return {"n_clubs": n,
            "crps_mean": round(sum(v["crps"] for v in by_club.values()) / n, 4) if n else None,
            "crps_by_club": {o: v["crps"] for o, v in by_club.items()},
            "coverage80": {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
                           "wilson95": _wilson(k, n)},
            "clubs": by_club, "missing": missing}


def score_team_wins(pred: dict, actual: dict) -> dict:
    """TM-B's per-arm read: team wins MAE, bias and r of ``pred`` against
    ``actual`` ({org: wins} or {org: {'wins': ...}}) on the clubs both carry;
    the per-club absolute errors are what the paired delta is built from."""
    pairs: dict[str, tuple[float, float]] = {}
    for org in sorted(set(pred or {}) | set(actual or {})):
        p = (pred or {}).get(org)
        a = _win_count((actual or {}).get(org))
        if p is None or a is None:
            continue
        pairs[org] = (float(p), a)
    missing = sorted((set(pred or {}) | set(actual or {})) - set(pairs))
    vals = list(pairs.values())
    bias = (sum(p - a for p, a in vals) / len(vals)) if vals else None
    r_val = _r(vals)
    return {"n": len(pairs),
            "mae": round(_mae(vals), 3) if vals else None,
            "bias_pred_minus_act": round(bias, 3) if bias is not None else None,
            "r": round(r_val, 3) if r_val is not None else None,
            "abs_err_by_club": {o: round(abs(p - a), 3) for o, (p, a) in pairs.items()},
            "missing": missing}


def _pythag_wins(rs: float | None, ra: float | None, g: float = 162.0) -> float | None:
    """Pythagenpat wins: g x RS^e / (RS^e + RA^e), e = ((RS + RA) / g)^0.287,
    proj_export._pythag_pct's form with games known (pinned by test)."""
    if rs is None or ra is None or rs < 0 or ra < 0 or (rs + ra) <= 0 or not g or g <= 0:
        return None
    rpg = (rs + ra) / g
    e = rpg ** PYTHAGENPAT_EXP
    num = rs ** e
    den = num + ra ** e
    return (g * num / den) if den > 0 else None


def _side_scores(pred: dict, actual: dict, side: str, prior: dict | None,
                 B: int, seed: int) -> dict:
    """One side (rs or ra) of score_team_runs: the candidate's MAE, and the
    paired delta of its absolute error against each comparator."""
    cand: dict[str, tuple[float, float]] = {}
    for org in sorted(set(pred or {}) | set(actual or {})):
        p = (pred or {}).get(org)
        a = ((actual or {}).get(org) or {}).get(side)
        if p is None or a is None:
            continue
        cand[org] = (float(p), float(a))
    out: dict = {"n": len(cand),
                 "mae": round(_mae(list(cand.values())), 3) if cand else None,
                 "abs_err_by_club": {o: round(abs(p - a), 3) for o, (p, a) in cand.items()},
                 "missing": sorted((set(pred or {}) | set(actual or {})) - set(cand))}
    if not prior:
        out["vs_carry_forward"] = None
        out["vs_league_avg"] = None
        return out
    prior_side = {o: float(v[side]) for o, v in prior.items()
                  if isinstance(v, dict) and v.get(side) is not None}
    lg = (sum(prior_side.values()) / len(prior_side)) if prior_side else None
    for name, comp in (("vs_carry_forward", prior_side),
                       ("vs_league_avg", {o: lg for o in cand} if lg is not None else {})):
        rows = {o: (abs(p - a), abs(comp[o] - a)) for o, (p, a) in cand.items() if o in comp}
        deltas = {o: c - b for o, (c, b) in rows.items()}
        out[name] = {"n": len(rows),
                     "comparator_mae": round(sum(b for _, b in rows.values()) / len(rows), 3) if rows else None,
                     "delta_by_club": {o: round(d, 3) for o, d in deltas.items()},
                     "bootstrap": _club_bootstrap(deltas, B, seed)}
    out["league_avg_comparator"] = round(lg, 2) if lg is not None else None
    return out


def score_team_runs(pred_rs: dict, pred_ra: dict, actual: dict, *, prior: dict | None = None,
                    pred_wins: dict | None = None, games: float = 162.0,
                    B: int = TM_BOOTSTRAP_B, seed: int = TM_SEED_GATE_2026) -> dict:
    """TM-C: RS MAE and RA MAE of the candidate against ``actual``
    ({org: {'rs', 'ra', 'wins'}}), each side paired against both comparators
    when ``prior`` ({org: {'rs', 'ra'}}, the prior season's actuals) is given:
    carry-forward (the club's own prior row) and league average (the prior
    season's mean per club, every club). Pass per side is ub95 < 0 against
    both; the verdict is the caller's, from the two ``pass`` flags. Reported
    beside, no verdict: Pythagenpat wins MAE and, with ``pred_wins``, the
    served wins MAE on the same clubs. A club missing RS or RA is listed under
    the side's ``missing``; a missing ``prior`` makes both comparators None."""
    rs = _side_scores(pred_rs, actual, "rs", prior, B, seed)
    ra = _side_scores(pred_ra, actual, "ra", prior, B, seed)
    pyth: dict[str, float] = {}
    for org in sorted(set(pred_rs or {}) & set(pred_ra or {})):
        w = _pythag_wins((pred_rs or {}).get(org), (pred_ra or {}).get(org), games)
        if w is not None:
            pyth[org] = w
    act_w = {o: (v or {}).get("wins") for o, v in (actual or {}).items()}
    pyth_score = score_team_wins(pyth, act_w)
    served_score = None
    if pred_wins:
        same = {o: pred_wins.get(o) for o in pyth_score["abs_err_by_club"] if pred_wins.get(o) is not None}
        served_score = score_team_wins(same, act_w)

    def _passes(side):
        cf, la = side.get("vs_carry_forward"), side.get("vs_league_avg")
        if not cf or not la:
            return None
        p1, p2 = cf["bootstrap"]["pass"], la["bootstrap"]["pass"]
        return None if p1 is None or p2 is None else bool(p1 and p2)

    return {"rs": rs, "ra": ra,
            "pass": {"rs": _passes(rs), "ra": _passes(ra)},
            "pythag_wins": {"n": pyth_score["n"], "mae": pyth_score["mae"],
                            "by_club": {o: round(w, 2) for o, w in pyth.items()},
                            "missing": pyth_score["missing"]},
            "served_wins": ({"n": served_score["n"], "mae": served_score["mae"]}
                            if served_score else None),
            "comparators": {"prior_clubs": len(prior) if prior else 0,
                            "league_avg": {"rs": rs.get("league_avg_comparator"),
                                           "ra": ra.get("league_avg_comparator")}},
            "B": int(B), "seed": int(seed)}


def write_team_gate_block(block: dict, key: str = "gate_2026", path: Path | None = None) -> dict:
    """Section 4.3's writer: read-modify-write ``block`` as
    team_projection_gate.<key> in the eval artifact, keeping every other key
    (proj_export._write_team_outlook_eval preserves the block across
    re-exports the way it preserves retro_backtest). First write wins: an
    existing entry under ``key`` is never overwritten."""
    path = path or EVAL_PATH
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    gate = cur.get(GATE_BLOCK_KEY) or {}
    if gate.get(key):
        raise RuntimeError(f"{GATE_BLOCK_KEY}.{key} already recorded; first write wins")
    gate[key] = block
    cur[GATE_BLOCK_KEY] = gate
    path.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    return cur


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = run()
    print(json.dumps({"player_pooled": out["player_level"]["pooled"],
                      "ship": out["ship_decision"]}, indent=1))
    for t in out["team_level_per_season"]:
        print(t["season"], {k: t[k] for k in ("raw", "recentered",
                                              "cohort_recentered", "baseline_prior_wins")})

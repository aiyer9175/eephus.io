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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = run()
    print(json.dumps({"player_pooled": out["player_level"]["pooled"],
                      "ship": out["ship_decision"]}, indent=1))
    for t in out["team_level_per_season"]:
        print(t["season"], {k: t[k] for k in ("raw", "recentered",
                                              "cohort_recentered", "baseline_prior_wins")})

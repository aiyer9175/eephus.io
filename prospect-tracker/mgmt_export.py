#!/usr/bin/env python
"""Build data/management_board.json, the payload behind /management/.

WHAT THIS PAGE MAY SAY, AND THE GATE DECIDED IT RATHER THAN TASTE.
`docs/IN_GAME_MANAGEMENT_GATE.md` was frozen before the battery ran, the battery
came back a bounded null, and its verdict is the page's scope:

    DESCRIPTIVE ONLY. The season-controlled split-half correlation of 0.0691
    sits INSIDE its permutation null band, so per-agent decision value in the
    running game is not a repeatable property of the agent. The board may render
    and be sorted by attempt VOLUME, which is a style axis; the plus metric is
    WITHHELD.

So there is no MWAR on this page and no team is ranked by decision quality. What
there is instead is better than a leaderboard nobody could trust:

  THE LEAGUE STEALS SECOND AT ALMOST EXACTLY ITS OWN BREAK-EVEN. 75.00 percent
  success against a swing-weighted break-even of 75.03 percent, which nets out to
  MINUS 0.19 WINS across 11,977 attempts over eight seasons. Steals of third pay
  (+4.31 wins on 1,932 attempts) and steals of home do not (-2.33 on 62). The
  whole running game across 19,130 games is worth +1.79 wins to the league that
  plays it.

  AND NO CLUB IS REPEATABLY BETTER AT DECIDING. The split-half sits inside its
  own permutation band; season explains 79.6 percent of the variance in a team
  season's summed decision value and the team itself explains 2.2 percent.

  THE NULL IS BOUNDED, which is what makes it worth publishing. The battery would
  have detected a true per-agent effect of 0.0005 wins per attempt at 80 percent
  power, so this is a ceiling and not a shrug.

The reference tables ship too, because they need no gate at all: the 24-cell run
expectancy matrix, the measured half-inning-start table, and the break-even any
reader can check a manager against.

Deterministic. Reads the artifacts; recomputes the team style board from the
corpus only when it is present.  python mgmt_export.py [--no-teams]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "management_board.json"
RUNNING = ROOT / "data" / "management_running.json"
GATE_EVAL = ROOT / "data" / "management_gate_eval.json"
WE = ROOT / "data" / "win_expectancy.json"
GATE_DOC = ROOT / "docs" / "IN_GAME_MANAGEMENT_GATE.md"

BASE_LABEL = {0: "empty", 1: "1B", 2: "2B", 3: "1B 2B", 4: "3B",
              5: "1B 3B", 6: "2B 3B", 7: "loaded"}


def _r(v, nd=4):
    try:
        return None if v is None or v != v else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _run_expectancy(we: dict) -> list:
    """The 24-cell matrix, as rows a page can draw.

    Keys are "base|outs" where base is the three-bit occupancy code. The label
    map is spelled out here rather than left to the reader, because "5" meaning
    first and third is the kind of thing that looks like a typo on a page.
    """
    out = []
    for k, v in sorted((we.get("run_expectancy") or {}).items(),
                       key=lambda kv: (int(kv[0].split("|")[1]),
                                       int(kv[0].split("|")[0]))):
        base, outs = k.split("|")
        # THE CELL IS A DICT, NOT A SCALAR. It carries {"re": ..., "n": ...}, and
        # reading it as a number silently produced a matrix of nulls that looked
        # like a rendering problem rather than a parsing one. The sample size
        # ships too: a run-expectancy cell is only as good as the plays behind
        # it, and bases-loaded-two-out is an order of magnitude thinner than
        # bases-empty-none-out.
        cell = v if isinstance(v, dict) else {"re": v, "n": None}
        out.append({"base_code": int(base), "bases": BASE_LABEL[int(base)],
                    "outs": int(outs), "runs": _r(cell.get("re"), 3),
                    "n": cell.get("n")})
    return out


def _half_inning_start(we: dict) -> dict:
    """The measured table, reduced to the tied game, which is the readable slice.

    THE WHOLE TABLE IS A FEW HUNDRED CELLS and it is not a page. What a reader
    wants is "what is my chance of winning as I come to bat in the seventh,
    tied", and that is one column of it. The rest stays in
    data/win_expectancy.json. The count ships as `n_cells_total`, derived, so
    nothing here has to be kept in step with the model by hand.

    THE CELL IS A DICT, NOT A SCALAR (audit F07-01). It carries
    {"p": ..., "n": ..., "thin": ...}, and `_r` on the dict raised TypeError
    inside its own try, returned None, and drew all 18 rows of the "Coming to
    bat in a tied game" table with an empty Win probability column under a
    paragraph saying the numbers were measured. This is the identical defect
    `_run_expectancy` documents having fixed eight lines above; the fix was
    applied to one of the two functions. The sample size ships too, for the same
    reason it ships on the run-expectancy matrix.
    """
    tab = we.get("half_inning_start") or {}
    rows = []
    for inn in range(1, 10):
        for half in ("top", "bottom"):
            v = tab.get(f"{inn}|{half}|0")
            if v is None:
                continue
            cell = v if isinstance(v, dict) else {"p": v, "n": None, "thin": None}
            rows.append({"inning": inn, "half": half, "score_diff": 0,
                         "batting_team_win_prob": _r(cell.get("p")),
                         "n": cell.get("n"), "thin": cell.get("thin")})
    return {"tied_game": rows,
            "note": we.get("half_inning_start_note"),
            "n_cells_total": len(tab)}


def _team_board(corpus: Path | None):
    """Attempts, success rate and target mix per club-season. STYLE ONLY.

    THE GATE ALLOWS VOLUME AND REFUSES THE PLUS METRIC, so summed decision value
    per club is deliberately NOT in this board. It is not a coyness: the
    split-half battery says a club's decision value does not repeat, so a column
    of it sorted descending would be a ranking of noise, and a reader has no way
    to tell that by looking at it.

    What does ship is what a club CHOSE to do: how often it ran, at which base,
    and how hard the spots it picked were. Those are style axes and they repeat
    trivially, because running a lot is a policy.
    """
    try:
        import numpy as np
        import pandas as pd
        import management as M
        import mgmt_teams
    except Exception as exc:                       # noqa: BLE001
        return {"status": f"not built: {exc}"}
    corpus = corpus or (ROOT / ".cache" / "pbp_corpus")
    if not corpus.exists():
        return {"status": f"not built: no corpus at {corpus}"}
    tmap = mgmt_teams.build_map(corpus=corpus)
    df = M.attempts(corpus=corpus)
    df = df[df["dv"].notna()].copy()
    gp = df["game_pk"].astype(int)
    df["home"] = gp.map(lambda k: (tmap.get(k) or {}).get("home"))
    df["away"] = gp.map(lambda k: (tmap.get(k) or {}).get("away"))
    df["team"] = np.where(df["half"].astype(str).str.startswith("bot"),
                          df["home"], df["away"])
    df = df[df["team"].notna()].copy()
    rows = []
    for (team, season), g in df.groupby(["team", "season"]):
        n = len(g)
        tgt = g["target"].value_counts()
        rows.append({
            "team": str(team), "season": int(season),
            "attempts": int(n),
            "success_rate": _r(float(g["success"].mean())),
            "share_2B": _r(float(tgt.get("2B", 0) / n)),
            "share_3B": _r(float(tgt.get("3B", 0) / n)),
            "mean_breakeven_faced": _r(float(g["breakeven_p"].mean())),
        })
    rows.sort(key=lambda r: (-r["season"], -r["attempts"]))
    return {
        "status": "built",
        "n_rows": len(rows),
        "rows": rows,
        "columns_are_style_not_skill": (
            "attempts, success rate and target mix are what a club CHOSE to do. "
            "They repeat trivially, because running a lot is a policy. Summed "
            "decision value is deliberately absent: the gate battery found it "
            "does not repeat between halves of a season, so a column of it "
            "sorted descending would be a ranking of noise that a reader has no "
            "way to recognise as one."),
    }


BUNT = ROOT / "data" / "management_bunt.json"


def _raw_number_sentence(raw_r, ctl_r, clears, v_season, v_team) -> str:
    """Why the raw split-half number is not the finding, from the numbers the
    gate block publishes beside it."""
    def f(x, nd=4):
        return "n/a" if x is None else f"{float(x):.{nd}f}"

    def pct(x):
        return "n/a" if x is None else f"{100.0 * float(x):.1f}"

    return (f"The raw split-half correlation is {f(raw_r)}, which looks like a "
            "repeatable skill and is not one: both halves of an agent-season sit "
            "in the same season, so a league-wide year effect reads as agreement. "
            f"Season explains {pct(v_season)} percent of the variance in a "
            f"club-season's summed decision value; the club explains "
            f"{pct(v_team)} percent. Controlled for season it is {f(ctl_r)}"
            + (", inside its permutation band." if clears is False else "."))


def _bunt_sentence(d: dict) -> str:
    """DERIVED, not typed. A first version asserted the squeeze was "the only
    positive cell" and there are three of them; they simply all share a runner on
    third with one out, which is the more interesting statement and is true."""
    pos = [c for c in (d.get("cells") or []) if (c.get("dv_per_bunt") or 0) > 0]
    tail = "Every cell on the board is negative."
    if pos:
        on_third = all("3B" in (c.get("bases") or "") and c.get("outs") == 1
                       for c in pos)
        best = max(pos, key=lambda c: c["dv_per_bunt"])
        tail = (f"Every one of the {len(pos)} positive cells is a squeeze, a runner "
                f"on third with one out, the best of them "
                f"{best['bases']} at {best['dv_per_bunt']:+.4f} wins a bunt."
                if on_third else
                f"{len(pos)} of {len(d.get('cells') or [])} cells come out positive, "
                f"the best {best['bases']} with {best['outs']} out.")
    return (f"The league's sacrifice bunting has cost "
            f"{abs(d.get('total_decision_value_wins') or 0):.0f} wins across "
            f"{d.get('n_bunts_priced'):,} bunts in "
            f"{len(d.get('seasons') or [])} seasons, about "
            f"{abs(d.get('dv_per_bunt_mean') or 0):.4f} wins each. " + tail)


def _bunt_section() -> dict:
    """The sacrifice-bunt family, read off its artifact.

    LIVE, and it is a LEAGUE result rather than a leaderboard, on the same
    discipline the running game ships under: no per-club column, because nothing
    has shown a club's decision value repeats in THIS family either and the
    running-game battery found it does not in that one.
    """
    try:
        d = json.loads(BUNT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"live": False, "blocked_on": "data/management_bunt.json",
                "why": "the bunt family has not been built on this machine"}
    if d.get("status") != "built":
        return {"live": False, "blocked_on": "corpus",
                "why": str(d.get("status"))}
    ctl = d.get("independent_control") or {}
    return {
        "live": True,
        "plus_metric": False,
        "eval_artifact": "data/management_bunt.json",
        "n_bunts_priced": d.get("n_bunts_priced"),
        "seasons": d.get("seasons"),
        "total_decision_value_wins": d.get("total_decision_value_wins"),
        "dv_per_bunt_mean": d.get("dv_per_bunt_mean"),
        "cells": d.get("cells"),
        "sentence": _bunt_sentence(d),
        "independent_control": ctl,
        "the_selection_problem": d.get("the_selection_problem"),
        "why_no_plus_metric": d.get("no_per_club_metric"),
        "two_outs_excluded": d.get("two_outs_excluded"),
    }


#: Small counts read as words in this copy, so a derived sentence reads the way
#: the typed one did. Anything larger stays a numeral.
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
          7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
          12: "twelve"}


def _words(n: int) -> str:
    return _WORDS.get(int(n), str(n))


def _headline_sentence(bt: dict, net, n_seasons: int) -> str:
    """DERIVED, not typed (audit F07-02, F07-05).

    The shipped sentence said the running game "is worth about one and a half
    wins to the entire league" and was written against a build whose score
    convention leaked. Correcting the leak flips the net to negative, so a typed
    sentence would not merely be stale, it would assert the opposite of the
    number printed beside it. Every clause here is read off the artifact.
    """
    gap = (bt["2B"]["success_rate"] or 0) - (bt["2B"]["swing_weighted_breakeven_p"] or 0)
    how = ("almost exactly as often as it should" if abs(gap) < 0.01
           else "more often than it should" if gap > 0
           else "less often than it should")
    third = "pay" if (bt["3B"]["sum_dv_wins"] or 0) > 0 else "do not pay"
    home = "do not" if (bt["HOME"]["sum_dv_wins"] or 0) < 0 else "do"
    net = float(net or 0.0)
    if abs(net) < 0.5:
        worth = ("worth nothing the entire league could notice, "
                 "%+.2f wins across all of it" % net)
    elif net > 0:
        worth = "worth about %.2f wins to the entire league" % net
    else:
        worth = "costing the entire league about %.2f wins" % abs(net)
    return (f"Across {_words(n_seasons)} seasons the league steals second "
            f"{how}. Steals of third {third}, steals of home {home}, and the "
            f"whole running game is {worth}.")


def _census_sentence(run: dict):
    """DERIVED, not typed (audit F02-01, F02-02).

    The exclusion table used to sit above a sentence saying the excluded
    attempts "are excluded and counted", and 2,455 of them were not: every
    caught stealing that ENDED a plate appearance lives only on the play's own
    result, and management.py read the events table alone. This sentence states
    the corpus's attempt count beside the priced and excluded counts the page
    renders, so the table can be seen to close. The gap is computed from the
    same two numbers the reader sees, never from a flag, and a gap is SAID
    rather than hidden. None when the running artifact predates the census.
    """
    c = run.get("attempt_census") or {}
    if not c.get("total"):
        return None
    total = int(c["total"])
    n = int(run["n_attempts_priced"])
    ex = int(sum((run.get("excluded") or {}).values()))
    gap = total - n - ex
    if gap == 0:
        tail = "so every attempt in the corpus is one or the other."
    elif gap > 0:
        tail = f"which leaves {gap:,} attempts neither priced nor counted."
    else:
        tail = f"which is {-gap:,} more than the corpus holds."
    return (f"The corpus holds {total:,} steal attempts across "
            f"{_words(len(c.get('seasons') or []))} seasons: "
            f"{int(c.get('from_the_events_table') or 0):,} recorded as events inside "
            f"a plate appearance and {int(c.get('from_the_play_result_only') or 0):,} "
            f"recorded only as the result that ended one, such as a caught "
            f"stealing for the third out. {n:,} are priced and {ex:,} are counted "
            f"in the table above, " + tail)


def build(*, corpus=None, teams=True) -> dict:
    run = json.loads(RUNNING.read_text(encoding="utf-8"))
    gate = json.loads(GATE_EVAL.read_text(encoding="utf-8"))
    we = json.loads(WE.read_text(encoding="utf-8"))
    sh = gate["gate_1_split_half"]
    pub = sh["published"]
    raw = sh["raw_for_comparison"]
    bt = run["by_target"]
    _bunt = _bunt_section()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "mgmt_export.py",
        "gate_doc": "docs/IN_GAME_MANAGEMENT_GATE.md",
        "gate_frozen_at": gate.get("gate_doc_frozen_at"),
        "gate_verdict": gate["verdict"],

        "headline": {
            "league_steals_second_at": bt["2B"]["success_rate"],
            "against_a_breakeven_of": bt["2B"]["swing_weighted_breakeven_p"],
            "sum_dv_wins_second": bt["2B"]["sum_dv_wins"],
            "sum_dv_wins_third": bt["3B"]["sum_dv_wins"],
            "sum_dv_wins_home": bt["HOME"]["sum_dv_wins"],
            "net_dv_all_seasons_wins": _r(
                gate["headline"]["net_dv_all_seasons_wins"], 2),
            "redistributable_pool_abs_dv_wins": _r(
                gate["headline"]["redistributable_pool_abs_dv_wins"], 2),
            "games": gate["team_attribution"]["games"],
            "sentence": _headline_sentence(
                bt, gate["headline"]["net_dv_all_seasons_wins"],
                len(run.get("by_season") or {})),
        },

        "running_game": {
            "n_attempts_priced": run["n_attempts_priced"],
            "by_target": bt,
            "by_season": run["by_season"],
            "excluded": run["excluded"],
            "attempt_census": run.get("attempt_census"),
            "attempt_census_sentence": _census_sentence(run),
            "decomposition": run["decomposition"],
            "why_two_out_attempts_are_excluded": run["two_out_attempts_are_excluded"],
            "why_the_league_average_runner": run["league_average_is_deliberate"],
            "which_breakeven_predicts_the_sign": run["which_breakeven_predicts_the_sign"],
            "third_out_handling": run["third_out_handling"],
            "why_execution_residual_does_not_sum_to_zero":
                run["why_execution_residual_does_not_sum_to_zero"],
        },

        "gate": {
            "verdict": gate["verdict"],
            "split_half_r": _r(pub.get("pearson_mean_dv")),
            "null_band": [_r(pub.get("null_band_lo95")), _r(pub.get("null_band_hi95"))],
            "clears_null": pub.get("clears_null"),
            "agent_seasons": gate["population"]["agent_seasons"],
            "median_attempts_per_agent_season":
                gate["population"]["median_attempts_per_agent_season"],
            "smallest_detectable_per_attempt_sd":
                gate["detection_floor"]["smallest_detectable_per_attempt_sd"],
            "detection_floor_reading": gate["detection_floor"]["reading"],
            "variance_explained_by_season": _r(
                gate["why_the_published_series_is_season_controlled"][
                    "variance_of_agent_summed_dv_explained_by_season"]),
            "variance_explained_by_team": _r(
                gate["why_the_published_series_is_season_controlled"][
                    "variance_of_agent_summed_dv_explained_by_team"]),
            "raw_split_half_r_for_comparison": _r(raw.get("pearson_mean_dv")),
            # DERIVED from the same gate fields this block publishes: the typed
            # version kept quoting the pre-2026-09-10 figures after the repair.
            "why_the_raw_number_is_not_the_finding": _raw_number_sentence(
                raw.get("pearson_mean_dv"), pub.get("pearson_mean_dv"),
                pub.get("clears_null"),
                gate["why_the_published_series_is_season_controlled"][
                    "variance_of_agent_summed_dv_explained_by_season"],
                gate["why_the_published_series_is_season_controlled"][
                    "variance_of_agent_summed_dv_explained_by_team"]),
            "null_construction": (sh.get("null") or {}).get("construction"),
            "n_agent_seasons_in_the_split": pub.get("n_agent_seasons"),
            "why_season_controlled": gate[
                "why_the_published_series_is_season_controlled"]["note"],
            "what_a_null_decides": gate["what_a_null_decides_about_the_manager_entity"],
        },

        "reference": {
            "run_expectancy": _run_expectancy(we),
            "half_inning_start": _half_inning_start(we),
            "model": {
                "kind": we.get("model"),
                "n_plays_fit": we.get("n_plays_fit"),
                "seasons": we.get("seasons"),
                "schema_version": we.get("schema_version"),
                "calibration": we.get("calibration"),
            },
            "why_a_model_not_a_table": we.get("why_a_model_not_a_table"),
            "monotone_by_construction": we.get("monotone_by_construction"),
            "smoothing_costs_the_tails": we.get("smoothing_costs_the_tails"),
            "state_excludes": we.get("state_excludes"),
        },

        "teams": _team_board(corpus) if teams else {"status": "skipped"},

        "sections": {
            "running_game": {"live": True},
            "reference": {"live": True},
            "team_style": {"live": True, "plus_metric": False,
                           "why_no_plus_metric": (
                               "the gate battery found that a club's decision value "
                               "in this family does not repeat between halves of a "
                               "season. A plus metric built on it would be a ranking "
                               "of noise, and the page withholds it for the same "
                               "reason the leverage board withholds its own.")},
            "manager_attribution": {
                "live": False, "blocked_on": "M-MWAR-2, the manager entity",
                "why": ("this module stops at the attempt. A team-season is an "
                        "UPPER BOUND on a manager, because managers change and teams "
                        "do not, and the team-season carries no repeatable signal in "
                        "this family. Building the manager entity to attribute a "
                        "signal that is not there would be work spent to make a null "
                        "more precise.")},
            "sacrifice_bunt": _bunt,
            "bullpen_and_lineup": {
                "live": False, "blocked_on": "not yet measured",
                # DERIVED, not typed (audit F07-02). Both figures in this
                # sentence moved when the score convention was corrected, and
                # one of them changed sign.
                "why": ("two decision families are measured here, the running game "
                        "and the sacrifice bunt, and they disagree in size by two "
                        "orders of magnitude: the running game is worth about "
                        f"{_r(gate['headline']['net_dv_all_seasons_wins'], 2):+.2f} "
                        "wins to the league and the bunt about "
                        f"{(_bunt.get('total_decision_value_wins') or 0):+.0f}. "
                        "That disagreement is the argument for measuring the "
                        "rest rather than generalising from either. The bullpen call "
                        "and the pinch hit have more room and have not been measured, "
                        "so nothing here says anything about them.")},
        },

        "what_this_page_does_not_claim": (
            "that any manager is better than any other. The running game returned "
            "a bounded null: no club's decision value in the "
            "running game repeats between halves of its own season, and the battery "
            "would have seen an effect of 0.0005 wins per attempt if one existed. "
            "That is a ceiling, not a shrug, and it is the reason there is no plus "
            "metric on this page."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-teams", action="store_true")
    ap.add_argument("--corpus", default=None)
    a = ap.parse_args(argv)
    d = build(corpus=Path(a.corpus) if a.corpus else None, teams=not a.no_teams)
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    h = d["headline"]
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e3:.0f} KB)")
    print(f"  league steals second at {h['league_steals_second_at']} against a "
          f"break-even of {h['against_a_breakeven_of']}")
    print(f"  sum DV wins: 2B {h['sum_dv_wins_second']}  3B {h['sum_dv_wins_third']}  "
          f"HOME {h['sum_dv_wins_home']}")
    print(f"  gate: split-half {d['gate']['split_half_r']} in "
          f"{d['gate']['null_band']}, clears={d['gate']['clears_null']}")
    print(f"  teams: {d['teams'].get('status')} "
          f"({d['teams'].get('n_rows', 0)} club-seasons)")
    print(f"  live sections: "
          f"{sorted(k for k, v in d['sections'].items() if v['live'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

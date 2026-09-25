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
import re
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
#: The decision ledger summary (mgmt_decisions.py), the matched-state baseline
#: (mgmt_baseline.py) and the manager ledger (mgmt_managers.py, Wave C, dark until
#: it runs). The board reads them; it never recomputes the ledger.
DECISIONS = ROOT / "data" / "management_decisions.json"
BASELINE = ROOT / "data" / "management_baseline.json"
MANAGERS = ROOT / "data" / "managers.json"
SHARD_DIR = ROOT / "data" / "mgmt_decisions"

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
    # The attribution map carries Baseball-Reference codes (OAK through 2024),
    # while the decision ledger's clubs block keys every season on the canonical
    # org (ATH). The club page joins the two on the code, so both go through
    # the same trades.canonical_org, or an Athletics club page loses its steal
    # block for every OAK season.
    import trades
    df["team"] = df["team"].map(lambda c: trades.canonical_org(c) or c)
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
            "attempts, success rate and target mix are what a club chose to do; "
            "they repeat because running is a policy. Summed decision value is "
            "withheld."),
    }


BUNT = ROOT / "data" / "management_bunt.json"


def _raw_number_sentence(raw_r, ctl_r, clears, v_season, v_team) -> str:
    """Why the raw split-half number is not the finding, from the numbers the
    gate block publishes beside it."""
    def f(x, nd=4):
        return "n/a" if x is None else f"{float(x):.{nd}f}"

    def pct(x):
        return "n/a" if x is None else f"{100.0 * float(x):.1f}"

    return (f"Raw split-half {f(raw_r)}: both halves of an agent-season sit in "
            "the same season, so a league-wide year effect reads as agreement. "
            f"Season explains {pct(v_season)} percent of the variance in a "
            f"club-season's summed decision value, the club {pct(v_team)} "
            f"percent. Controlled for season: {f(ctl_r)}"
            + (", inside its permutation band." if clears is False else "."))


def _bunt_sentence(d: dict) -> str:
    """DERIVED, not typed. A first version asserted the squeeze was "the only
    positive cell" and there are three of them; they simply all share a runner on
    third with one out, which is the more interesting statement and is true."""
    pos = [c for c in (d.get("cells") or []) if (c.get("dv_per_bunt") or 0) > 0]
    tail = "Every cell is negative."
    if pos:
        on_third = all("3B" in (c.get("bases") or "") and c.get("outs") == 1
                       for c in pos)
        best = max(pos, key=lambda c: c["dv_per_bunt"])
        if not on_third:
            tail = (f"{len(pos)} of {len(d.get('cells') or [])} cells are positive; "
                    f"best {best['bases']} with {best['outs']} out.")
        elif len(pos) > 1:
            tail = (f"All {len(pos)} positive cells are squeezes (runner on third, "
                    f"one out); best {best['bases']} at "
                    f"{best['dv_per_bunt']:+.4f} wins a bunt.")
        else:
            tail = (f"The one positive cell is a squeeze (runner on third, one "
                    f"out): {best['bases']} at {best['dv_per_bunt']:+.4f} wins a bunt.")
    n_seasons = len(d.get("seasons") or [])
    sit = d.get("by_situation") or {}
    sac, hit = sit.get("sacrifice"), sit.get("for_a_hit")
    if sac and hit:
        # "Sacrifice" is said only over the runner-on cells (audit M10-02): a
        # bases-empty bunt has no runner to sacrifice and is a try for a hit.
        def _part(v):
            t = v.get("total_decision_value_wins") or 0
            return (f"{'cost' if t < 0 else 'gained'} the league {abs(t):.0f} wins over "
                    f"{v.get('n_bunts_priced'):,} bunts, "
                    f"{abs(v.get('dv_per_bunt_mean') or 0):.4f} wins each")
        return (f"Sacrifice bunts (a runner on, fewer than two out) {_part(sac)}, in "
                f"{n_seasons} seasons. Bunts for a hit with the bases empty {_part(hit)}; "
                f"{hit.get('n_bunt_hits'):,} of them went for hits. " + tail)
    tot = d.get("total_decision_value_wins") or 0
    return (f"Bunts {'cost' if tot < 0 else 'gained'} the league "
            f"{abs(tot):.0f} wins over {d.get('n_bunts_priced'):,} bunts in "
            f"{n_seasons} seasons, "
            f"{abs(d.get('dv_per_bunt_mean') or 0):.4f} wins each. " + tail)


def _vintage(artifact_corpus_built_at, dec: dict) -> dict:
    """Which corpus a hand-built artifact (the running game, the bunt family) was
    priced from, and, when it is the corpus the decision ledger was built from,
    the ledger's through-date for the newest season. Nothing is inferred across
    two corpora: a different build prints its own build date and says so."""
    seasons = [int(x) for x in (dec.get("seasons") or [])]
    newest = max(seasons) if seasons else None
    same = bool(artifact_corpus_built_at) and artifact_corpus_built_at == dec.get("corpus_built_at")
    through = ((dec.get("through_by_season") or {}).get(str(newest))
               if (same and newest is not None) else None)
    return {"corpus_built_at": artifact_corpus_built_at,
            "same_corpus_as_ledger": same,
            "newest_season": newest if same else None,
            "through": through}


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
        "corpus_built_at": d.get("corpus_built_at"),
        "n_bunts_priced": d.get("n_bunts_priced"),
        "seasons": d.get("seasons"),
        "total_decision_value_wins": d.get("total_decision_value_wins"),
        "dv_per_bunt_mean": d.get("dv_per_bunt_mean"),
        "by_situation": d.get("by_situation"),
        "situations": d.get("situations"),
        "what_counts_as_a_bunt": d.get("what_counts_as_a_bunt"),
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
    how = ("almost exactly at" if abs(gap) < 0.01
           else "above" if gap > 0 else "below")
    third = "pay" if (bt["3B"]["sum_dv_wins"] or 0) > 0 else "do not pay"
    home = "do not" if (bt["HOME"]["sum_dv_wins"] or 0) < 0 else "do"
    net = float(net or 0.0)
    worth = (f"costs the league {abs(net):.2f} wins" if net < 0
             else f"is worth {net:.2f} wins to the league")
    return (f"Over {_words(n_seasons)} seasons the league steals second "
            f"{how} its break-even. Steals of third {third}, steals of home "
            f"{home}, and the running game {worth}.")


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
        tail = "so every attempt is one or the other."
    elif gap > 0:
        tail = f"leaving {gap:,} attempts neither priced nor counted."
    else:
        tail = f"which is {-gap:,} more than the corpus holds."
    return (f"The corpus holds {total:,} steal attempts over "
            f"{_words(len(c.get('seasons') or []))} seasons: "
            f"{int(c.get('from_the_events_table') or 0):,} as events inside a "
            f"plate appearance, {int(c.get('from_the_play_result_only') or 0):,} "
            f"only as the result that ended one (such as a caught stealing for "
            f"the third out). {n:,} are priced and {ex:,} excluded in the table "
            f"above, " + tail)


def _decomposition(dec: dict) -> dict:
    """The running artifact's DV / ER definitions without their rhetorical
    questions (owner copy rule, 2026-09-11). The definitions and the identity
    stay the artifact's own; only the sentences ending in "?" are dropped."""
    out = dict(dec)
    for k in ("dv", "er"):
        s = out.get(k)
        if isinstance(s, str):
            out[k] = " ".join(p for p in re.split(r"(?<=[.?!])\s+", s.strip())
                              if not p.endswith("?"))
    return out


def _families_sentence(net, bunt, sacrifice=None, for_a_hit=None) -> str:
    """The still-dark families, with both measured totals and their size ratio
    read off the artifacts (audit F07-02: both figures moved on the score
    repair, and one changed sign). Since M10-02 the bunt family prices every
    bunt; the sacrifice-situation part is named beside the whole when the
    artifact splits it."""
    if sacrifice is not None and for_a_hit is not None:
        bunt = sacrifice
        what = (f"the sacrifice bunt ({sacrifice:+.0f} wins; bunts for a hit with the "
                f"bases empty {for_a_hit:+.0f})")
    else:
        what = f"the sacrifice bunt ({bunt:+.0f} wins)"
    apart = (f", a {max(abs(bunt), abs(net)) / min(abs(bunt), abs(net)):.0f}-fold "
             f"gap in size" if net and bunt else "")
    return (f"two decision families are measured: the running game "
            f"({net:+.2f} wins to the league) and {what}{apart}, so neither generalises to the rest. "
            f"The bullpen call and the pinch hit have more room and have not "
            f"been measured.")


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _decision_blocks() -> dict:
    """The decision ledger's blocks, READ off data/management_decisions.json and
    data/management_baseline.json; the board never recomputes the ledger.

    Key discipline on `clubs.rows`: no key contains "dv" or "decision" (the gate test
    scans this block with the same rule as `teams.rows`); counts are n_all / n_<family>,
    realized columns are mwpa_<family> and there is no cross-family total. DVS is not a
    club-season column: it lives in the drill-down shards and the League census only.
    """
    d = _read_json(DECISIONS)
    b = _read_json(BASELINE)
    # Reader sentences, never an operator instruction: the page prints both.
    dark = {"status": "the decision ledger is not on this build", "live": False}
    if not d or d.get("status") != "built":
        why = ((d or {}).get("status")
               or "data/management_decisions.json is not on this build; the ledger step "
                  "writes it from the play corpus and it ships committed with the site")
        blocked = {"live": False, "blocked_on": "the decision ledger (mgmt_decisions.py, step 6b7e)",
                   "why": str(why)}
        return {"decisions": {**dark, "why": str(why)},
                "clubs": {"status": str(why), "rows": [], "plus_metric": False},
                "managers": {**blocked, "fixture": {"ejection_named_managers": None}},
                "challenges": {**blocked, "seasons": [2026]},
                "lineups": {**blocked, "seasons": [2026]},
                "shards": {"path_template": "/data/mgmt_decisions/{season}-{club}.json", "index": []},
                "league": {"live": False, "why": str(why)}}
    fams = d.get("families") or {}
    decisions = {
        "status": "built", "live": True,
        "produced_by": d.get("produced_by"), "generated_at": d.get("generated_at"),
        "corpus_built_at": d.get("corpus_built_at"),
        "corpus_schema_version": d.get("corpus_schema_version"),
        "seasons": d.get("seasons"), "through_by_season": d.get("through_by_season"),
        "n_all": d.get("n_all"),
        "chain_break": d.get("chain_break"),
        "families": fams,
        "gate_status_by_family": d.get("gate_status_by_family"),
        "floors": d.get("floors"), "games_floor": d.get("games_floor"),
        "realized_sentence": d.get("realized_sentence"),
        "agent_sentence": d.get("agent_sentence"),
        "style_sentence": d.get("style_sentence"),
        "single_pa_caveat": d.get("single_pa_caveat"),
        "overlap_note": d.get("overlap_note"),
        "dvs_note": d.get("dvs_note"),
        "li_note": d.get("li_note"),
        "units": d.get("units"),
        "no_cross_family_total": True, "plus_metric": False,
        "removed_pitcher": d.get("removed_pitcher"),
        "switch_classification": d.get("switch_classification"),
        "hook_hist": d.get("hook_hist"),
        "steal_excluded": d.get("steal_excluded"),
        "club_attribution": d.get("club_attribution"),
        "baseline": {
            "artifact": "data/management_baseline.json",
            "min_cell": (b or {}).get("min_cell"),
            "identity": (b or {}).get("identity"),
            "single_pa_caveat": (b or {}).get("single_pa_caveat"),
            "selection_caveat": (b or {}).get("selection_caveat"),
            "where_dvs_lives": (b or {}).get("where_dvs_lives"),
            "families": {f: {k: v for k, v in blk.items() if k != "cells"}
                         for f, blk in ((b or {}).get("families") or {}).items()},
        } if b else {"artifact": "data/management_baseline.json", "status": "absent"},
    }
    clubs = dict(d.get("clubs") or {})
    clubs.setdefault("plus_metric", False)
    clubs["floors"] = d.get("floors")
    clubs["games_floor"] = d.get("games_floor")
    clubs["live"] = True
    mgr = _read_json(MANAGERS)
    fixture = d.get("managers_fixture") or {}
    if mgr and mgr.get("status") == "built" and mgr.get("managers"):
        managers = {"live": True, "rows": mgr.get("managers"), "source": "data/managers.json",
                    "fixture": fixture, "agent_sentence": d.get("agent_sentence")}
    else:
        managers = {
            "live": False,
            "blocked_on": "mgmt_managers ingest (M-MWAR-2)",
            "why": ("there is no manager entity anywhere on disk: no manager in any game "
                    "feed, no manager transaction, no coach or staff cache. The ledger needs "
                    "/api/v1/teams/{id}/coaches per team-season with schedule-date bisection, "
                    "which is a network ingest. Until it runs every row is a club-season."),
            "fixture": {"ejection_named_managers": fixture.get("ejection_named_managers"),
                        "ejections": fixture.get("ejections"),
                        "note": fixture.get("note")},
            "rows_until_then": "clubs.rows",
            "agent_sentence": d.get("agent_sentence"),
        }
    challenges = {
        "live": False, "seasons": [2026],
        "blocked_on": "mgmt_feeds_2026 (Wave B): the reviewDetails reader over .cache/game_feeds",
        "why": ("the corpus dropped about.hasReview and carries no challenging side; the "
                "2026 game feeds carry reviewDetails on the reviewed play and are read in "
                "Wave B. Pre-2026 side attribution is not sourceable offline."),
        "regime_note": ("ABS pitch challenges (reviewType MJ, a player's challenge) are a "
                        "separate 2026 regime, counted per club as abs_challenges and never "
                        "mixed with replay challenges; crew-chief reviews (N*) are counted, "
                        "not credited"),
        "value_not_observable": ("the feed prices only the final ruling, so a challenge's "
                                 "win-probability value is not observable even in 2026; "
                                 "the family ships counts, overturn rate, timing and LI"),
    }
    lineups = {
        "live": False, "seasons": [2026],
        "blocked_on": "mgmt_feeds_2026 (Wave B): boxscore battingOrder and lineup_captures readers",
        "why": ("game feeds with a batting order exist for 2026 only and are read in Wave "
                "B; pre-2026 lineups need a network fetch (M-CORPUS-2)"),
        "value_not_measured": ("lineup value is not measured; optimality needs the "
                               "per-plate-appearance model (M-ENG-1) and the lineup chain "
                               "(M-ENG-2), neither built"),
    }
    sh = dict(d.get("shards") or {})
    sh["storage_note"] = ("tracked in git by owner decision (spec 14.1, taken 2026-09-23 on the "
                          "measured size): the shards are written to data/mgmt_decisions/ "
                          "(schema 2, compacted to about 41 MB over 240) and committed with the "
                          "board, so the box serves them before its first nightly")
    league = {"live": True, "reads": "decisions.families and decisions.baseline"}
    return {"decisions": decisions, "clubs": clubs, "managers": managers,
            "challenges": challenges, "lineups": lineups, "shards": sh, "league": league}


def build(*, corpus=None, teams=True) -> dict:
    run = json.loads(RUNNING.read_text(encoding="utf-8"))
    gate = json.loads(GATE_EVAL.read_text(encoding="utf-8"))
    we = json.loads(WE.read_text(encoding="utf-8"))
    sh = gate["gate_1_split_half"]
    pub = sh["published"]
    raw = sh["raw_for_comparison"]
    bt = run["by_target"]
    _bunt = _bunt_section()
    blocks = _decision_blocks()
    _dec = blocks["decisions"]
    if _bunt.get("live"):
        _bunt["vintage"] = _vintage(_bunt.get("corpus_built_at"), _dec)
    _n_realized = len([f for f, v in (_dec.get("families") or {}).items() if v.get("has_window")])

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
            # Read off the running artifact whose cards this line sits under
            # (audit M10-05); the frozen gate eval's figures describe the gate's
            # own corpus and fall back only for an artifact that predates them.
            "net_dv_all_seasons_wins": _r(
                run.get("net_dv_wins", gate["headline"]["net_dv_all_seasons_wins"]), 2),
            "redistributable_pool_abs_dv_wins": _r(
                run.get("sum_abs_dv_wins", gate["headline"]["redistributable_pool_abs_dv_wins"]), 2),
            "games": run.get("games_in_corpus") or gate["team_attribution"]["games"],
            "sentence": _headline_sentence(
                bt, run.get("net_dv_wins", gate["headline"]["net_dv_all_seasons_wins"]),
                len(run.get("by_season") or {})),
        },

        "running_game": {
            "n_attempts_priced": run["n_attempts_priced"],
            "by_target": bt,
            "by_season": run["by_season"],
            "excluded": run["excluded"],
            "attempt_census": run.get("attempt_census"),
            "attempt_census_sentence": _census_sentence(run),
            "decomposition": _decomposition(run["decomposition"]),
            "why_two_out_attempts_are_excluded": run["two_out_attempts_are_excluded"],
            "why_the_league_average_runner": run["league_average_is_deliberate"],
            "which_breakeven_predicts_the_sign": run["which_breakeven_predicts_the_sign"],
            "third_out_handling": run["third_out_handling"],
            "why_execution_residual_does_not_sum_to_zero":
                run["why_execution_residual_does_not_sum_to_zero"],
            "vintage": _vintage(run.get("corpus_built_at"), _dec),
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

        # The decision ledger (mgmt_decisions.py), read off its artifact. Realized
        # value per family, never a cross-family total, never a plus metric; the
        # club-season is the agent until the manager ledger lands.
        "decisions": _dec,
        "clubs": blocks["clubs"],
        "managers": blocks["managers"],
        "challenges": blocks["challenges"],
        "lineups": blocks["lineups"],
        "shards": blocks["shards"],

        # Cross-module links the club page draws ONLY when the route is built:
        # /franchise/ is D3 and /ledger/ is D1, neither shipped, and an anchor
        # to a route that does not exist is a 404 on every club page.
        "routes": {"franchise": (ROOT / "franchise" / "index.html").exists(),
                   "ledger": (ROOT / "ledger" / "index.html").exists()},

        "sections": {
            "running_game": {"live": True},
            "reference": {"live": True},
            "league": blocks["league"],
            "decisions": {"live": bool(_dec.get("live")), "plus_metric": False,
                          "realized_not_skill": _dec.get("realized_sentence")},
            "clubs": {"live": bool(blocks["clubs"].get("live")), "plus_metric": False},
            "managers": {"live": bool(blocks["managers"].get("live")),
                         "blocked_on": blocks["managers"].get("blocked_on")},
            "challenges": {"live": bool(blocks["challenges"].get("live")),
                           "blocked_on": blocks["challenges"].get("blocked_on")},
            "lineups": {"live": bool(blocks["lineups"].get("live")),
                        "blocked_on": blocks["lineups"].get("blocked_on")},
            "team_style": {"live": True, "plus_metric": False,
                           "why_no_plus_metric": (
                               "the gate battery found a club's decision value in "
                               "this family does not repeat between halves of a "
                               "season, so a plus metric on it would be a ranking "
                               "of noise. The leverage board withholds its own for "
                               "the same reason.")},
            "manager_attribution": {
                "live": False, "blocked_on": "M-MWAR-2, the manager entity",
                "why": ("the module stops at the attempt. A team-season is an "
                        "UPPER BOUND on a manager (managers change, teams do not) "
                        "and carries no repeatable signal in this family, so a "
                        "manager entity would attribute a signal that is not "
                        "there.")},
            "sacrifice_bunt": _bunt,
            # NARROWED (2026-09-23) to what is still dark once the decision ledger
            # carries realized value for the bullpen call and the pinch hit: the
            # DECISION VALUE of either (the counterfactual) and lineup VALUE.
            "bullpen_and_lineup": {
                "live": False,
                "blocked_on": ("bullpen decision value and lineup value: the pitcher not "
                               "used and the batter not lifted need the availability model "
                               "(M-PIT-9) and the per-plate-appearance model (M-ENG-1); "
                               "lineup optimality needs M-ENG-1 and the lineup chain (M-ENG-2)"),
                "still_dark": ["bullpen_decision_value", "pinch_hit_decision_value",
                               "lineup_value"],
                "now_live_as_realized_value": sorted(
                    f for f, v in (_dec.get("families") or {}).items() if v.get("has_window")),
                # DERIVED, not typed (audit F07-02). Both figures in this
                # sentence moved when the score convention was corrected, and
                # one of them changed sign.
                "why": _families_sentence(
                    _r(run.get("net_dv_wins", gate["headline"]["net_dv_all_seasons_wins"]), 2),
                    _bunt.get("total_decision_value_wins") or 0,
                    ((_bunt.get("by_situation") or {}).get("sacrifice") or {}).get(
                        "total_decision_value_wins"),
                    ((_bunt.get("by_situation") or {}).get("for_a_hit") or {}).get(
                        "total_decision_value_wins"))
                + (f" The decision ledger carries REALIZED value for {_words(_n_realized)} "
                   "families, which is what happened after the decision and not the "
                   "decision's value; the counterfactual for the bullpen call and the "
                   "pinch hit has not been measured." if _n_realized else "")},
        },

        # The detection floor is read off the gate block, never typed.
        "what_this_page_does_not_claim": (
            "that any manager is better than any other. The running game returned "
            "a bounded null: no club's decision value repeats between halves of "
            "its own season, and the battery would have detected "
            f"{float(gate['detection_floor']['smallest_detectable_per_attempt_sd']):g}"
            " wins per attempt. Hence no plus metric on this page."),
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
    print(f"  decisions: {d['decisions'].get('status')} "
          f"({(d['decisions'].get('n_all') or 0):,} rows, "
          f"{d['clubs'].get('n_rows', 0)} club-season rows, "
          f"{len(d['shards'].get('index') or [])} shards)")
    print(f"  live sections: "
          f"{sorted(k for k, v in d['sections'].items() if v['live'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

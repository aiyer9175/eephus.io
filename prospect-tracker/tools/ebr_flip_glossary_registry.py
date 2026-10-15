"""EBR_2F_FLIP's glossary entries and registry rows (prepared by EBR_2_BUILD_DARK,
NOT applied by it). Idempotent: a second run changes nothing. Preserves each
file's line endings (CRLF) and indent (1), the glossary's non-ASCII and trailing
newline, the registry's absence of one.

Usage (from the module root, in the flip commit, AFTER data/ebr_eval.json exists):
    python tools/ebr_flip_glossary_registry.py --check            # dry run into a temp dir, validates
    python tools/ebr_flip_glossary_registry.py                    # apply to data/ and the freshness test
    python tools/ebr_flip_glossary_registry.py --bem-plus PASS    # also the bem_plus entry and row (served)
    python tools/ebr_flip_glossary_registry.py --bem-plus FAIL    # the row only, provisional / measured_not_adopted
    python tools/ebr_flip_glossary_registry.py --look-notes "<the part 12.1 dispositions sentence>"

What it writes (EBR_GATE.md 6.4; baserunning.md 3.10 as the gate doc amends it;
integration.md 2.2 item 4 for the bsr text):
  data/glossary.json: ebr, ebr_sb, ebr_xb, ebr_dp, team_ebr, xbt_pct, steal_attempt_rate,
    outs_on_bases, tag_up_rate, gidp_rate, bsr, wsb, savant_brv, bolts, hp_to_1b; sprint_speed gains
    the mlbstats module; bem_plus only on --bem-plus PASS.
  data/model_registry.json: pbp_runner_moves, ebr, team_ebr (provisional, measurement_only); bem_plus
    only with --bem-plus. Never ewar_v3 or a swar_* row (EBR_3_EWAR_V3 writes those), never the
    ewar row.
  test_methodology_freshness.py: MODEL_GLOSSARY mappings for the rows above.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# tools/ebr_flip_glossary_registry.py: the module root is the parent of tools/.
MODULE_ROOT = ROOT.parent if ROOT.name == "tools" else ROOT

ORIGIN_ARK = "Arkmetric, created by Noah J. Dengler, original to eephus.io."
GATE = "docs/ebr-2026-09-30/EBR_GATE.md"

GLOSSARY_ENTRIES = [
    {"id": "ebr", "term": "eBR (eephus Baserunning Runs)", "category": "custom-index", "section": "Players & Stats",
     "module": ["mlbstats", "projections"], "aliases": ["eBR", "eephus baserunning runs", "baserunning runs"],
     "priority": 23,
     "definition": "Runs a player added or cost on the bases this season against an average runner with the same chances: stealing, taking the extra base, and staying out of double plays. Counted from MLB's play-by-play on this season's run expectancy. Descriptive: what happened, not a forecast.",
     "methodology": "Each chance is valued on this season's run-expectancy table (RE24), shrunk toward the pooled 2018 to 2026 table so a thin cell never swings it: what the inning was worth after what the runner did, minus what it was worth had he held. An average runner scores zero, so each part sums to zero across the league every season. SB runs cover steals, caught stealing and pickoffs, keyed on MLB's movement reason, against what an average runner made of the same times on base with the next base open. XB runs cover taking or not taking the extra base, and outs on the bases, on singles, doubles, caught air balls and ground balls, each against the league's outcomes in the same spot, out count and batted-ball context. DP runs compare double plays grounded into with the league rate for the same base-out state, priced by state. Blocked chances, advances credited to an error, wild pitches, passed balls and balks are left out. No park or fielder-arm term, which is where Baseball Savant's run value differs. Same-season agreement with FanGraphs' BsR, Baseball-Reference's baserunning runs and Savant's run value is measured and published in the eval, never a gate.",
     "formula": "eBR = SB runs + XB runs + DP runs",
     "seeAlso": ["ebr_sb", "ebr_xb", "ebr_dp", "team_ebr", "run_expectancy", "bsr", "savant_brv", "xbt_pct", "steal_break_even"],
     "shelf": "ark", "origin": ORIGIN_ARK},
    {"id": "ebr_sb", "term": "SB runs (eBR)", "category": "custom-index", "section": "Players & Stats",
     "module": ["mlbstats", "projections"], "aliases": ["SB runs", "eBR SB runs", "steal runs"], "priority": 24,
     "definition": "The stolen-base part of eBR: steals, caught stealing and pickoffs, valued on this season's run expectancy, minus what an average runner made of the same times on base with the next base open.",
     "methodology": "Every attempt is priced at its own base-out state (the state after this runner's move only, so a double steal gives each runner his own value), keyed on MLB's movement reason and never on the event type. Pickoffs of a runner who was not attempting are priced the same way against the league's pickoff rate from that base. A two-out caught stealing is priced: run expectancy ends the inning at zero exactly. The league sums to zero every season.",
     "formula": "SB runs = sum of attempt values minus the league value per chance times the runner's chances, by origin base",
     "seeAlso": ["ebr", "wsb", "steal_attempt_rate", "steal_break_even"], "shelf": "ark", "origin": ORIGIN_ARK},
    {"id": "ebr_xb", "term": "XB runs (eBR)", "category": "custom-index", "section": "Players & Stats",
     "module": ["mlbstats", "projections"], "aliases": ["XB runs", "eBR XB runs", "extra-base runs", "advancement runs"], "priority": 25,
     "definition": "The advancement part of eBR: taking or not taking the extra base, and outs made on the bases, on singles, doubles, caught air balls and ground balls, against an average runner in the same spot and out count.",
     "methodology": "Each chance is a runner at contact in one of four classes (a runner on a single or double, the batter-runner on a hit, a runner on a caught air ball with fewer than two out, an unforced runner on a ground-ball out). His outcome is valued on a fixed reference, so a teammate's extra base is never credited to him, against the league's outcome mix for the same class, base, outs, what the runners ahead did and the batted ball (field, trajectory and depth), with thin cells backed off to broader ones. Outs on the bases are split out and published beside it. Chances blocked by the runner ahead are no chance; an advance credited to an error stops before the error.",
     "formula": "XB runs = sum over chances of (value of his outcome minus the league's expected value of the chance), centred to zero by class and season",
     "seeAlso": ["ebr", "xbt_pct", "outs_on_bases", "tag_up_rate", "savant_brv"], "shelf": "ark", "origin": ORIGIN_ARK},
    {"id": "ebr_dp", "term": "DP runs (eBR)", "category": "custom-index", "section": "Players & Stats",
     "module": ["mlbstats", "projections"], "aliases": ["DP runs", "eBR DP runs", "double-play runs"], "priority": 26,
     "definition": "The double-play part of eBR, the batter's: double plays grounded into against the league rate for the same chances (a runner on first, fewer than two out), priced by base-out state.",
     "methodology": "A chance is a plate appearance whose state at its final pitch has a runner on first and fewer than two out. The cost of a double play in each of the eight states is the run-expectancy gap between the ground-ball outs that were not double plays and those that were, so a loaded-base, one-out double play costs more than a runner-on-first one. FanGraphs' served BsR has carried no double-play part since 2016; Baseball-Reference's double-play runs are the nearest published counterpart.",
     "formula": "DP runs = minus the sum over chances of (double play minus the league rate for the state) times the state's cost",
     "seeAlso": ["ebr", "gidp_rate"], "shelf": "ark", "origin": ORIGIN_ARK},
    {"id": "team_ebr", "term": "Team eBR", "category": "custom-index", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["Team eBR", "team baserunning runs"], "priority": 61,
     "definition": "The sum of a club's runners' eBR this season, club today as on every team tab here. Realized runs, not a grade of how a club chose to run.",
     "methodology": "The roster basis (the club MLB lists today) is shown, so a traded player's whole season counts for his new club; the earned basis (every chance credited to the club he ran for) rides in the payload and sums to zero across the league every season. Club running style, the decision rather than the runner, is on In-Game Management.",
     "formula": "Team eBR = sum of eBR over the club's runners",
     "seeAlso": ["ebr", "team_dem_plus"], "shelf": "ark", "origin": ORIGIN_ARK},
    {"id": "xbt_pct", "term": "XBT% (Extra bases taken)", "category": "hitter-stat", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["XBT%", "extra bases taken", "extra-base taken rate"], "priority": 40,
     "definition": "How often a runner takes more than the minimum on a hit: first to third or home on a single, second to home on a single, first to home on a double.",
     "methodology": "A chance counts only when the base ahead was open; an advance credited to a fielding error counts on neither side; an out made trying is a chance not taken. Counted here from MLB's play-by-play, so no parity with any published XBT% is claimed.",
     "formula": "XBT% = extra bases taken / chances", "seeAlso": ["ebr_xb", "tag_up_rate", "outs_on_bases"],
     "shelf": "foundation", "origin": "Standard baseball statistic; counted here from MLB's play-by-play."},
    {"id": "steal_attempt_rate", "term": "Att% (Steal attempt rate)", "category": "hitter-stat", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["Att%", "steal attempt rate", "attempt rate"], "priority": 41,
     "definition": "Steal attempts per chance: plate appearances that began with him on first and second open, or on second and third open.",
     "methodology": "A chance is counted at the start of a plate appearance from the pre-play state, so a runner on first with second open during a four-pitch plate appearance is one chance. Attempts of second and third from MLB's play-by-play, keyed on the movement reason.",
     "formula": "Att% = (SB + CS of second and third) / chances", "seeAlso": ["ebr_sb", "steal_break_even"],
     "shelf": "foundation", "origin": "Standard baseball statistic; counted here from MLB's play-by-play."},
    {"id": "outs_on_bases", "term": "OOB (Outs on the bases)", "category": "hitter-stat", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["OOB", "outs on the bases", "outs on base"], "priority": 42,
     "definition": "Outs made while advancing, stretching a hit, returning to a base or in a rundown. Caught stealing, pickoffs and force outs are not included.",
     "methodology": "Counted from MLB's play-by-play movement reasons (thrown out, out stretching, out returning, doubled off, rundown, runner out); the batter-runner counts once he is a runner.",
     "seeAlso": ["ebr_xb", "xbt_pct"], "shelf": "foundation",
     "origin": "Standard baseball statistic; counted here from MLB's play-by-play."},
    {"id": "tag_up_rate", "term": "Tag% (Tag-up rate)", "category": "hitter-stat", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["Tag%", "tag-up rate", "tag up"], "priority": 43,
     "definition": "Advances on a caught fly ball with fewer than two out, third to home and second to third, over the chances.",
     "methodology": "Second to third is blocked, and no chance, when the runner on third held. Counted from MLB's play-by-play.",
     "formula": "Tag% = advances / chances over both classes", "seeAlso": ["ebr_xb", "xbt_pct"], "shelf": "foundation",
     "origin": "Standard baseball statistic; counted here from MLB's play-by-play."},
    {"id": "gidp_rate", "term": "GIDP% (Double-play rate)", "category": "hitter-stat", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["GIDP%", "double-play rate", "GIDP rate"], "priority": 44,
     "definition": "Double plays grounded into per chance: plate appearances with a runner on first and fewer than two out.",
     "methodology": "Chances from the play-by-play state at the plate appearance; double plays from the play's event type. The count on the row is the official GIDP; the rate's numerator is the play-by-play count, so no rate mixes sources.",
     "formula": "GIDP% = GIDP / chances", "seeAlso": ["ebr_dp"], "shelf": "foundation",
     "origin": "Standard baseball statistic; counted here from MLB's play-by-play."},
    {"id": "bsr", "term": "BsR (FanGraphs baserunning runs)", "category": "general-stat", "section": "Players & Stats",
     "module": ["mlbstats", "projections"], "aliases": ["BsR", "baserunning runs (FanGraphs)", "FanGraphs BsR"], "priority": 45,
     "definition": "FanGraphs' baserunning runs above average as MLB's feed publishes them. Since 2016 they are stolen-base runs (wSB) plus Statcast's extra-base runner runs; before 2016 they also included FanGraphs' UBR and double-play runs (wGDP). Displayed here, never computed.",
     "methodology": "Read verbatim from MLB's bulk sabermetrics feed, joined by player id; a traded player reads one season line. The feed's separate UBR and wGDP fields are not shown: they read zero for 2025 and 2026, and from 2016 BsR is not their sum with wSB, so the board shows BsR and wSB and labels the difference as BsR minus wSB.",
     "seeAlso": ["wsb", "ebr", "savant_brv"], "shelf": "industry",
     "origin": "Industry metric, FanGraphs' baserunning runs as published by MLB. We display it and compute no version of it."},
    {"id": "wsb", "term": "wSB (FanGraphs stolen-base runs)", "category": "general-stat", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["wSB", "stolen-base runs", "weighted stolen base runs"], "priority": 46,
     "definition": "FanGraphs' stolen-base runs above average, from steals and caught stealing on linear weights, as MLB's feed publishes them. Displayed here, never computed.",
     "methodology": "Read verbatim from MLB's bulk sabermetrics feed, joined by player id; a traded player reads one season line.",
     "seeAlso": ["bsr", "ebr_sb"], "shelf": "industry",
     "origin": "Industry metric, FanGraphs' stolen-base runs as published by MLB. We display it and compute no version of it."},
    {"id": "savant_brv", "term": "Baserunning run value (Baseball Savant)", "category": "statcast", "section": "Players & Stats",
     "module": ["mlbstats", "projections"], "aliases": ["BRV", "baserunning run value", "Savant BRV", "runner runs"], "priority": 47,
     "definition": "Baseball Savant's runs above average on the bases from extra bases taken and steal attempts, from Statcast tracking. Displayed here, never computed.",
     "methodology": "The runner total, its extra-base part and its steal part are read from Savant's baserunning and basestealing run-value leaderboards for the season shown. Savant's model carries fielder-arm and batted-ball context that eBR leaves out, so the two differ by design.",
     "seeAlso": ["ebr", "bsr", "sprint_speed"], "shelf": "industry",
     "origin": "Industry metric. MLB Statcast (Baseball Savant) baserunning run value."},
    {"id": "bolts", "term": "Bolts", "category": "statcast", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["bolts", "30 ft/s runs"], "priority": 48,
     "definition": "Runs at 30 feet per second or faster this season, as Baseball Savant counts them.",
     "seeAlso": ["sprint_speed"], "shelf": "industry",
     "origin": "Industry metric. MLB Statcast (Baseball Savant): competitive runs at 30 ft/s or faster."},
    {"id": "hp_to_1b", "term": "HP-1B (Home to first)", "category": "statcast", "section": "Players & Stats",
     "module": ["mlbstats"], "aliases": ["HP-1B", "home to first", "home-to-first time"], "priority": 49,
     "definition": "Home to first in seconds on competitive runs, as Baseball Savant measures it. Lower is faster.",
     "seeAlso": ["sprint_speed", "bolts"], "shelf": "industry",
     "origin": "Industry metric. MLB Statcast (Baseball Savant): home-to-first time."},
]

BEM_PLUS_ENTRY = {
    "id": "bem_plus", "term": "BEM+ (Baserunning Evaluation Metric)", "category": "custom-index",
    "section": "Players & Stats", "module": ["mlbstats"], "aliases": ["BEM+", "baserunning evaluation metric", "baserunning plus"],
    "priority": 27,
    "definition": "A runner's baserunning rate per chance on the 100 + 10z ruler: 100 is the average runner with 100 or more starts on base, ten points is one standard deviation. The baserunning member of the HEM+ / REM+ / SEM+ / DEM+ family: eBR's three parts per chance, each pulled toward zero by sample size, mixed at the league's chances per 100 starts on base so volume never moves it. Served only because its registered gate recorded a PASS.",
    "methodology": "Each part's per-chance rate (SB runs per steal chance, XB runs per advancement chance, DP runs per double-play chance) is shrunk toward zero by its own constant, fitted once on the 2018-2019 and 2021-2022 pairs and frozen; the rate is the mix of the three at league chances per 100 starts on base; raw = 100 + 10 (rate minus the pool mean) / the pool SD over runners with 100 or more starts on base, rounded nearest, no clamp. Its one gate (EBR_GATE.md 5.8) ranked next season's eBR rate against sprint speed, stolen bases, starts on base and the raw unshrunk rate, with a permuted twin that had to fail.",
    "formula": "BEM+ = 100 + 10 x (shrunk rate minus pool mean) / pool SD",
    "seeAlso": ["ebr", "dem_plus"], "shelf": "ark", "origin": ORIGIN_ARK}

RECORD_FORM = ("the form of pbp_corpus_base_state: a reconstruction scored against official counts")


def registry_rows(bem_plus: str | None, look_notes: str) -> list[dict]:
    rows = [
        {"model_id": "pbp_runner_moves",
         "summary": "Measured: the 2026 runner record's SB 3,289 and CS 984 equal MLB's official counts exactly on every player; GIDP 3,138 against 3,145 (0.2 percent). Provisional, measurement only.",
         "surface": "Runner record in the local cache (.cache/pbp_runners); the substrate eBR, the Baserunning board and the eBR eval read",
         "predicts": "Nothing forward. One row per runner movement per play from MLB's win-probability payloads, with the pre-play base-out state from the corpus walk (reconstruct_plays), steals keyed on movementReason",
         "champion": "tools/build_runner_moves.py: one state walk shared with the play corpus, movements applied net per runner and play index, incremental by game_pk, completed seasons frozen, final regular-season games only",
         "baseline": "MLB StatsAPI official season hitting lines (playerPool=All): SB, CS and GIDP per player and league, which the record is scored against and never seeded from",
         "metric": "EBR_GATE.md I1 to I3: league and per-player SB and CS exact; GIDP within 0.5 percent of the league total and exact for 97 percent or more of players with any; every final regular-season game of the schedule in the record",
         "eval_artifact": ".cache/pbp_runners/manifest.json",
         "verdict": "provisional", "provisional_kind": "measurement_only",
         "notes": ("2026-10-09 (EBR_2A_CORE_DARK) and the 2026-10-14 preview build (EBR_2_BUILD_DARK): seasons 2018, 2019 and 2021 to 2026 "
                   "(2,429 of 2,430 games of 2026 at the build). I1 on 2026: SB 3,289 = 3,289 and CS 984 = 984 keyed on movementReason; "
                   "GIDP 3,138 against the official 3,145 (0.2 percent). I2: SB and CS exact for every player with any; GIDP exact for 98.66 "
                   "percent of players with any. " + RECORD_FORM + ". Lives in .cache/pbp_runners, never .cache/pbp_corpus, whose "
                   "manifest is a registered artifact with exactly three tables; pbp_runners is in tools/prune_cache.EXCLUDED. Display only: no "
                   "fitted consumer and no betting module reads it (EBR_GATE.md I9).")},
        {"model_id": "ebr",
         "summary": "Descriptive: runs above average on the bases from MLB's play-by-play on per-season RE24, SB plus XB plus DP runs, each zero-sum across the league. Measurement only.",
         "surface": "/mlbstats/ Baserunning tab (eBR, SB runs, XB runs, DP runs; the history board); the MLB player card's Baserunning section (Hitting tab)",
         "predicts": "nothing forward; DESCRIPTIVE runs above average on the bases from MLB's per-runner play-by-play on per-season RE24: SB runs + XB runs + DP runs",
         "champion": "ebr_v1 (" + GATE + " part 2): per-season RE24 shrunk toward the frozen 2018 to 2026 pool (K by the method of moments, clipped to [500, 5000]); steals, caught stealing and pickoffs priced at their own state on movementReason; four advancement classes with batted-ball context and hierarchical backoff (kappa 20); double plays priced by base-out state; every part centred to zero per season over every runner",
         "baseline": "n/a, descriptive; same-season agreement with FanGraphs BsR (via MLB's feed), Baseball-Reference runs_br + runs_dp and Savant's baserunning run value is measured and published in the eval as aggregate r only, never a gate on validity (part 4 bug bands)",
         "metric": "descriptive: official-count reproduction (I1, I2), zero league sums (I4), monotone RE24 (I5), row identity (I6), coverage (I7), determinism (I8), isolation (I9); concurrent agreement r at PA 300+ and 502+",
         "eval_artifact": "data/ebr_eval.json",
         "verdict": "provisional", "provisional_kind": "measurement_only",
         "notes": ("Registered 2026-10-08 in " + GATE + " before any year-to-year, split-half or forward number of eBR existed; built dark "
                   "by EBR_2A_CORE_DARK (core, previews) and EBR_2_BUILD_DARK (the section and card, previews); served by EBR_2F_FLIP. "
                   "The displayed WAR stays eWAR v2 (EPOCH-Q4): eBR enters no training label, fitted artifact, priced number, board rank or "
                   "betting input, and eWAR v3 (its own row, EBR_3_EWAR_V3) is a display column beside eWAR v2. Never a forecast: no copy "
                   "calls it accurate, better than BsR or a skill. " + look_notes)},
        {"model_id": "team_ebr",
         "summary": "Descriptive: the sum of a club's runners' eBR, club today on the tab and earned basis in the payload, where it sums to zero across the league. Provisional, measurement only.",
         "surface": "/mlbstats/ Baserunning tab, Team Baserunning sub-tab (Team eBR and its three parts); the Teams tab's team_ebr join after the flip",
         "predicts": "nothing forward; DESCRIPTIVE sum of a club's runners' eBR on two club bases (roster today shown, earned in the payload)",
         "champion": "the sum of the season values of the club's runners (bullpen_export.TEAM_BASIS current_roster), with the earned basis credited to the club he ran for through the runner record's batting club and the substrate's stints",
         "baseline": "n/a, descriptive; realized runs, not a rank of how a club chose to run (the /management/ gate found club decision value a bounded null)",
         "metric": "descriptive: the earned basis sums to zero across the league every season (the contract test); every club resolved",
         "eval_artifact": "data/ebr_eval.json",
         "verdict": "provisional", "provisional_kind": "measurement_only",
         "notes": ("A roll-up of the ebr row, " + GATE + " 6.4. No eWAR column on the sub-tab (the Team Defense rule). Never summed with, "
                   "combined with or shown as one number with the /management/ decision value (part 0, Not the Management number).")},
    ]
    if bem_plus:
        passed = bem_plus.upper() == "PASS"
        rows.append({
            "model_id": "bem_plus",
            "summary": ("Validated on its registered gate (EBR_GATE.md 5.8): see the eval for the forward gaps against sprint speed, stolen bases, starts on base and the raw rate."
                        if passed else
                        "Measured on its registered gate (EBR_GATE.md 5.8) and NOT adopted: a PASS clause failed, so BEM+ is not served and the board stays descriptive."),
            "surface": "/mlbstats/ Baserunning tab, BEM+ column" if passed else "not served (the column is wired and withheld)",
            "predicts": "baserunning-rate skill: a sample-shrunk rate of the site's eBR per chance, 100 + 10z over runners with 100+ starts on base",
            "champion": "bem_plus per EBR_GATE.md 5.8 and baserunning.md 2.6: per-part rates shrunk toward zero by constants fitted on the 2018-2019 and 2021-2022 pairs, mixed at league chances per 100 starts on base, 100 + 10z over the 100-starts pool",
            "baseline": "sprint speed, stolen bases, starts on base (playing time) and the raw unshrunk eBR rate (its parent), each in the predictor season",
            "metric": "forward Spearman Y to Y+1 eBR rate per 100 starts on base, predictor seasons 2022 to 2024, 2,000 player-clustered season-stratified bootstrap replicates (DEM+ convention v2), PASS only with lo95 above 0 against the three baselines and at least -0.01 against the parent, the permuted twin failing the stolen-base clause",
            "eval_artifact": "data/ebr_eval.json",
            "verdict": "validated" if passed else "provisional",
            **({} if passed else {"provisional_kind": "measured_not_adopted"}),
            "notes": ("Read once in the outcome look (EBR_LOOK, " + GATE + " part 12.1). " + look_notes
                      + " May claim only: a steadier read of a runner's baserunning than one season's runs, and a better guide to next "
                        "season's eBR rate than his sprint speed or his steal count. Never a WAR input, never an eFV feature, never read by "
                        "betting or projections (EBR-Q3 (a)).")})
    return rows


MODEL_GLOSSARY_LINES = [
    '    "pbp_runner_moves": "internal",',
    '    "ebr": ["ebr", "ebr_sb", "ebr_xb", "ebr_dp"],',
    '    "team_ebr": ["team_ebr"],',
]
MODEL_GLOSSARY_BEM = '    "bem_plus": ["bem_plus"],'


def _read(path: Path):
    b = path.read_bytes()
    return b.decode("utf-8"), (b"\r\n" in b)


def _write(path: Path, text: str, crlf: bool) -> None:
    text = text.replace("\r\n", "\n")
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def apply_glossary(path: Path, bem_plus: str | None) -> list[str]:
    text, crlf = _read(path)
    g = json.loads(text)
    by = {e["id"]: e for e in g["entries"]}
    changed = []
    entries = list(GLOSSARY_ENTRIES) + ([BEM_PLUS_ENTRY] if (bem_plus or "").upper() == "PASS" else [])
    for e in entries:
        if e["id"] in by:
            if by[e["id"]] != e:
                by[e["id"]].clear()
                by[e["id"]].update(e)
                changed.append("updated " + e["id"])
        else:
            g["entries"].append(dict(e))
            changed.append("added " + e["id"])
    sp = by.get("sprint_speed")
    if sp is not None and "mlbstats" not in (sp.get("module") or []):
        sp["module"] = list(sp.get("module") or []) + ["mlbstats"]
        changed.append("sprint_speed: module + mlbstats")
    if changed:
        _write(path, json.dumps(g, indent=1, ensure_ascii=False) + "\n", crlf)
    return changed


def apply_registry(path: Path, bem_plus: str | None, look_notes: str) -> list[str]:
    text, crlf = _read(path)
    r = json.loads(text)
    by = {m["model_id"]: m for m in r["models"]}
    changed = []
    for row in registry_rows(bem_plus, look_notes):
        mid = row["model_id"]
        if mid in by:
            cur = by[mid]
            if any(cur.get(k) != v for k, v in row.items()):
                for k, v in row.items():
                    cur[k] = v
                if row.get("verdict") == "validated":
                    cur.pop("provisional_kind", None)
                changed.append("updated " + mid)
        else:
            r["models"].append(dict(row))
            changed.append("added " + mid)
    if changed:
        _write(path, json.dumps(r, indent=1, ensure_ascii=False), crlf)
    return changed


def apply_model_glossary(path: Path, bem_plus: str | None) -> list[str]:
    text, crlf = _read(path)
    lf = text.replace("\r\n", "\n")
    anchor = '    "pbp_corpus_base_state": "internal",\n'
    assert lf.count(anchor) == 1, "MODEL_GLOSSARY anchor moved"
    lines = list(MODEL_GLOSSARY_LINES) + ([MODEL_GLOSSARY_BEM] if bem_plus else [])
    add = [ln for ln in lines if (ln + "\n") not in lf]
    if not add:
        return []
    lf = lf.replace(anchor, anchor + "".join(ln + "\n" for ln in add))
    _write(path, lf, crlf)
    return ["MODEL_GLOSSARY + " + ln.split(":")[0].strip().strip('"') for ln in add]


def _copy_checks(rows: list[dict], entries: list[dict]) -> list[str]:
    bad = []
    ban = re.compile(r"\b(seamless|robust|delve|comprehensive|crucial|essential|powerful|showcase|utilize|unlock|elevate|"
                     r"game-changing|cutting-edge|tapestry|meticulous|underscore|harness)\b|leverage(?! index)", re.I)
    for obj in rows + entries:
        for k, v in obj.items():
            if not isinstance(v, str):
                continue
            if "\u2014" in v or "\u2013" in v:
                bad.append(f"dash in {obj.get('model_id') or obj.get('id')}.{k}")
            m = ban.search(v)
            if m:
                bad.append(f"banned word {m.group(0)!r} in {obj.get('model_id') or obj.get('id')}.{k}")
        if "summary" in obj and len(obj["summary"].split()) > 30:
            bad.append(f"summary over 30 words: {obj['model_id']}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(MODULE_ROOT))
    ap.add_argument("--check", action="store_true", help="dry run into a temp copy, then validate")
    ap.add_argument("--bem-plus", choices=["PASS", "FAIL"], default=None)
    ap.add_argument("--look-notes", default=("Outcome look dispositions: read from " + GATE + " part 12.1 at the flip (EBR_2F_FLIP "
                                             "passes them through --look-notes)."))
    a = ap.parse_args(argv)
    root = Path(a.root)
    gl, reg, tf = root / "data" / "glossary.json", root / "data" / "model_registry.json", root / "test_methodology_freshness.py"
    bad = _copy_checks(registry_rows(a.bem_plus, a.look_notes),
                       GLOSSARY_ENTRIES + ([BEM_PLUS_ENTRY] if a.bem_plus == "PASS" else []))
    if bad:
        print("COPY: " + "; ".join(bad))
        return 2
    if a.check:
        tmp = Path(tempfile.mkdtemp(prefix="ebr_flip_check_"))
        (tmp / "data").mkdir()
        for src in (gl, reg):
            shutil.copy2(src, tmp / "data" / src.name)
        shutil.copy2(tf, tmp / tf.name)
        gl, reg, tf = tmp / "data" / "glossary.json", tmp / "data" / "model_registry.json", tmp / tf.name
    for label, fn in (("glossary", lambda: apply_glossary(gl, a.bem_plus)),
                      ("registry", lambda: apply_registry(reg, a.bem_plus, a.look_notes)),
                      ("MODEL_GLOSSARY", lambda: apply_model_glossary(tf, a.bem_plus))):
        ch = fn()
        print(f"{label}: " + ("; ".join(ch) if ch else "no change"))
    again = apply_glossary(gl, a.bem_plus) + apply_registry(reg, a.bem_plus, a.look_notes) + apply_model_glossary(tf, a.bem_plus)
    assert not again, "not idempotent: " + "; ".join(again)
    for p in (gl, reg):
        b = p.read_bytes()
        assert b"\r\n" in b and b"\n" not in b.replace(b"\r\n", b""), f"{p.name}: line endings not CRLF"
    sys.path.insert(0, str(root))
    import model_registry
    problems = model_registry.validate(json.loads(reg.read_bytes().decode("utf-8")))
    ok = [p for p in problems if not (a.check and "artifact missing" in p)]
    print("validate():", ok or "clean", ("(artifact-missing lines ignored in --check)" if a.check and len(ok) != len(problems) else ""))
    ids = {e["id"] for e in json.loads(gl.read_bytes().decode("utf-8"))["entries"]}
    missing = sorted({s for e in GLOSSARY_ENTRIES for s in e.get("seeAlso", [])} - ids)
    print("seeAlso unresolved:", missing or "none")
    return 1 if (ok or missing) else 0


if __name__ == "__main__":
    sys.exit(main())

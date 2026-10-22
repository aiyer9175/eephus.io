# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 gate registration pins (docs/ebr-2026-09-30/EBR_GATE.md).

The registration is committed ALONE and BEFORE any year-to-year number of eBR
and any forward number of a skill or position part exists, so that nothing is
tuned after a look. This file is the ratchet on that, in the house form of
test_fwar_label_epoch_registration.py: every clause is pinned by the sentence
that makes it BIND, not by its heading, because a heading with its teeth
removed is a note.

It pins:

  1. The document, its title, that it only registers, and that it names this
     test.
  2. Part 0: the candidate-part table (six rows and BEM+), each row with its
     clauses, null, frame, statistic, margin, Holm family and admission; that
     eWAR v3 exists whatever the looks say; that a part not admitted leaves
     FanGraphs' own number; and the two-kinds-of-test paragraph.
  3. Part 1: a row for every question, the eight needed answers as recorded and
     the seven open ones answered or marked UNANSWERED.
  4. eBR's binding definition, I1 to I9, the bug bands, the outcome look's
     Leg E, guards and DP leg, BEM+, the admission and copy tables, the claims
     and the clocks.
  5. Part 9 (the series, the skill parts' formulas and invariants, the skill
     look and its dispositions, admission, assembly) and part 10's seals.
  6. That NO RESULT is recorded above part 12, or in the registration's own
     closing paragraph and the dated notes after part 12.3. Parts 12.1 and
     12.2 hold the outcome look's and the skill look's results (both
     2026-10-19) and part 12.3 the skill holdout's (2026-10-21), pinned by
     test_ebr_gate_result.py.

It does NOT pin a result. A look's result pin goes in its own file, so that a
result pin never lives beside a criterion pin.

Prose assertions run against a whitespace-flattened copy of the document, so
that re-wrapping a paragraph is not a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"

RESULTS_HEADING = "## 12. Results"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(doc: str, start: str, end: str) -> str:
    return doc[doc.index(start):doc.index(end)]


def _row(region: str, prefix: str) -> str:
    rows = [ln for ln in region.splitlines() if ln.startswith(prefix)]
    assert len(rows) == 1, f"expected exactly one row starting {prefix!r}, got {len(rows)}"
    return rows[0]


def _part0() -> str:
    return _section(_doc(), "## 0. What kind of decision this is", "## 1. Decision record")


def _part1() -> str:
    return _section(_doc(), "## 1. Decision record", "## 2. What eBR is")


# 1. The document ------------------------------------------------------------


def test_the_registration_exists_and_says_it_only_registers():
    assert DOC.exists()
    flat = _flat(_doc())
    assert flat.startswith("# eWAR v3 gate: eBR and the skill parts ")
    assert "STATUS: REGISTERED, RESULTS EMPTY." in flat
    assert "This document only registers: it computes nothing, and nothing in it is a result." in flat
    assert "so that nothing is tuned after a look" in flat
    assert "DRAFT for queue task" not in flat, "the draft banner was not deleted"


def test_the_document_names_the_test_that_pins_it():
    assert "It is pinned by `test_ebr_gate_registration.py`." in _flat(_doc())


# 2. Part 0 ------------------------------------------------------------------


CANDIDATE_ROWS = {
    "| 1 | Baserunning:": (
        "outcome", "2, 3, 5.1 to 5.3, 6.1", "d is not above +0.02",
        "the six season pairs of 5.1, 300 PA in both seasons",
        "Leg E: mean per-pair Spearman self-persistence of (SB + XB runs) per PA minus BsR's",
        "0.02, interval d +/- 1.645 sd", "its own, one test",
        "Leg E SHIP, Leg T passes, the twin RESOLVED_LOSS, d above 0 on frame U and on the club changers (EBR-Q1 (a))"),
    "| 2 | Double plays:": (
        "outcome", "2, 5.4, 6.2", "d_DP is not above +0.02",
        "E-DP: the same statistic, eGDP per PA against Baseball-Reference's `runs_dp` per PA",
        "its own, one test",
        "E-DP SHIP with its guards, DP-1 and DP-2 pass, the E-DP twin RESOLVED_LOSS (EBR-Q2 (a) under EBR-Q1 (a))"),
    "| 3 | Position:": (
        "forward (a convention)", "9.4 S4, 9.5, 9.6", "the gap is not above 0",
        "predictor seasons 2021 to 2024, hitters 200 PA in both seasons",
        "Spearman gap of fWAR + the part's delta over fWAR(Y) in ranking fWAR(Y+1), per PA and in total",
        "point gap +0.02", "{H-rate, H-cum}, k = 2",
        "WIN (components) on H-rate, H-cum not LOSS (SWAR-Q0 (b), EWV3-Q1)"),
    "| 4 | Batting:": (
        "skill", "9.4 S1, 9.5, 9.6", "per arm, the gap is not above 0",
        "{HEM+ H-rate, HEM+ H-cum, xHEM+ H-rate, xHEM+ H-cum}, k = 4",
        "an arm's H-rate WIN (components), its H-cum not LOSS; both arms qualifying go to EWV3-Q2's rule (SWAR-Q3 (c))"),
    "| 5 | Pitching:": (
        "skill", "9.4 S2, 9.5, 9.6", "the gap is not above 0",
        "predictor seasons 2021 to 2024, pitchers 50 IP in both seasons", "as 3, per IP and in total",
        "{P-rate, P-cum}, k = 2",
        "P-rate WIN (components) with era transport, P-cum not LOSS; the home-run term set first by its own transport clause (EWV3-Q1)"),
    "| 6 | Fielding:": (
        "skill", "9.4 S3, 9.5, 9.6", "the gap is not above 0", "{H-rate, H-cum}, k = 2",
        "WIN (components) on H-rate, H-cum not LOSS (EWV3-Q1)"),
    "| BEM+ |": (
        "index", "5.8", "its PASS clauses fail", "forward Spearman gaps, gate X-B1", "its own",
        "served only on PASS (EBR-Q3 (a)); never a part of eWAR v3"),
}


def test_part_0_candidate_table_has_six_parts_and_bem_plus_with_every_column():
    part0 = _part0()
    header = _row(part0, "| # | Candidate part |")
    for col in ("Kind", "Clauses", "Pre-committed null", "Frame", "Statistic", "Margin",
                "Holm family", "Admitted when (under part 1's answers)"):
        assert f"| {col} |" in header, col
    table_rows = [ln for ln in part0.splitlines()
                  if re.match(r"^\| (\d|BEM\+) \|", ln)]
    assert len(table_rows) == 7, table_rows
    for prefix, cells in CANDIDATE_ROWS.items():
        row = _row(part0, prefix)
        assert row.count("|") == 11, f"{prefix} lost a column"
        for cell in cells:
            assert cell in row, f"{prefix} lost {cell!r}"


def test_part_0_ewar_v3_exists_whatever_the_looks_say():
    flat = _flat(_part0())
    assert "eWAR v3 EXISTS whatever the looks say" in flat
    assert ("a candidate part that is not admitted leaves FanGraphs' own number in place" in flat)
    assert ("when no part is admitted the column equals fWAR on every row and its label says so"
            in flat)
    assert "never labelled plain \"eWAR\"" in flat
    assert "No correction is made across parts: each part decides only its own admission." in flat


def test_part_0_two_kinds_of_test_paragraph():
    flat = _flat(_part0())
    assert "**Two kinds of candidate part, two kinds of test, and why.**" in flat
    assert "Candidate parts 1 and 2 are OUTCOME parts" in flat
    assert "Baserunning has no next-season outcome independent of a construct" in flat
    assert "Candidate parts 4, 5 and 6 are SKILL parts" in flat
    assert ("Shrinkage raises self-persistence mechanically, so persistence would reward the shrink "
            "and test nothing") in flat
    assert ("whether it ranks the next season's published fWAR better than fWAR itself did" in flat)
    assert "Candidate part 3, our positional ladder, is a convention, not an event record and not a shrink" in flat
    assert "its honest prior is a LOSS or UNRESOLVED" in flat


def test_part_0_display_and_label_boundaries():
    flat = _flat(_part0())
    assert "Its registry rows are `provisional` with `provisional_kind` `measurement_only`." in flat
    assert "The displayed WAR stays eWAR v2" in flat
    assert ("Under every outcome no training label, fitted artifact, priced number, board rank, "
            "Franchise grade, F-SCORE input or betting input reads eBR, a skill delta, a ladder delta "
            "or eWAR v3.") in flat
    assert "Every candidate part is that document's clause (k) item Z4: display only." in flat
    assert ("candidate parts 2 to 6 never become label candidates under this registration" in flat)
    assert "The two are never summed, combined or shown as one number." in flat


# 3. Part 1 ------------------------------------------------------------------

NEEDED = {
    "EBR-Q0": "(a) eWAR v3 on FanGraphs' frame",
    "EBR-Q1": "(a) only if they repeat clearly more",
    "EBR-Q2": "(a) yes, admitted by the E-DP contrast of part 5.4",
    "EBR-Q3": "(a) BEM+, registered in part 5.8",
    "SWAR-Q0": "(b) a named candidate part of eWAR v3 (candidate part 3)",
    "SWAR-Q1": "(b) inside eWAR v3: one house WAR",
    "SWAR-Q2": "(c) \"eWAR skill\"",
    "SWAR-Q3": "(c) both, HEM+ and xHEM+ as two arms",
}
OPEN = ("EBR-Q4", "EBR-Q5", "EBR-Q6", "SWAR-Q4", "EWV3-Q1", "EWV3-Q2", "EWV3-Q3")


def test_part_1_has_a_row_for_every_question():
    part1 = _part1()
    for qid in ("BR-Q1", "EPOCH-Q4", *NEEDED, *OPEN):
        _row(part1, f"| {qid} |")


def test_part_1_records_the_eight_needed_answers():
    part1 = _part1()
    for qid, answer in NEEDED.items():
        row = _row(part1, f"| {qid} |")
        assert answer in row, f"{qid}: answer changed or missing"
        assert re.search(r"\| answered 2026-10-01 \(`DECISIONS_FOR_OWNER\.md`, '[^']+'\) \|$", row), \
            f"{qid}: status cell lacks the recorded date and heading"
        assert "UNANSWERED" not in row and "[(" not in row


def test_part_1_open_questions_hold_an_answer_or_unanswered():
    part1 = _part1()
    for qid in OPEN:
        row = _row(part1, f"| {qid} |")
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 4, row
        status = cells[3]
        assert status, f"{qid}: empty status cell"
        assert status.startswith("answered 20") or "UNANSWERED" in row, f"{qid}: {status!r}"
    assert "every row below holds a recorded owner answer" in _flat(part1)


def test_part_1_br_q1_and_epoch_q4_as_registered():
    part1 = _part1()
    assert "eBR is built and served" in _row(part1, "| BR-Q1 |")
    epoch = _row(part1, "| EPOCH-Q4 |")
    assert "\"Keep eWAR v2 shown\"" in epoch
    assert "implemented by EPOCH-Q4-IMPL (R1a)" in epoch
    flat = _flat(part1)
    assert ("An owner answer that arrives after this commit replaces its default by a dated amendment "
            "under part 11, committed alone BEFORE the look whose clauses it touches, never after it.") in flat


# 4. eBR's definition, identity gates and bug bands ---------------------------


def test_the_binding_definition_sentences():
    flat = _flat(_section(_doc(), "## 2. What eBR is", "## 3. Identity gates"))
    assert '`mlb_leverage.season_game_pks(season, game_type="R")`' in flat
    assert "No postseason play enters any table, credit or league constant." in flat
    assert ("**Steal events are keyed on `details.movementReason`**, never on `details.eventType`."
            in flat)
    assert "the state at plate-appearance start comes from `reconstruct_plays` in `tools/build_pbp_corpus.py`" in flat
    assert "imported with `tools/` on `sys.path`" in flat
    assert "`.cache/pbp_runners/`, never `.cache/pbp_corpus`" in flat
    assert "nothing here writes `.cache/win_prob/`" in flat
    # The run basis.
    assert "### 2.3 Run basis: per-season RE24, shrunk toward a frozen pool" in flat
    assert "that recipe, re-implemented per season on the fit set" in flat
    assert "P = {2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026}, FROZEN with ebr_v1" in flat
    assert "K = W / tau^2 by the method of moments over the 24 cells" in flat
    assert "clipped to [500, 5000]; computed once on P and frozen with ebr_v1" in flat
    assert "never calls `win_expectancy.run_expectancy`" in flat
    assert "K is ONE pooled constant over the 24 cells" in flat
    assert "a high-variance cell is shrunk less, relative to its noise, than a cell-specific K would shrink it" in flat
    # Five parts, exclusions, centring, no park or arm term, the freeze.
    assert "### 2.5 The five parts" in flat
    for part in ("eSB (steals, caught stealing, pickoff-caught-stealing)", "ePK (pickoffs of a runner not attempting)",
                 "eXB (advancement and outs on the bases), split exactly into eXB_adv and eXB_oob",
                 "eGDP (double-play avoidance, the batter)"):
        assert part in flat, part
    assert "Two-out caught stealing is priced." in flat
    assert ("Advances on wild pitches, passed balls and balks (the battery's); defensive indifference"
            in flat)
    assert "Every part sums to zero over this pool each season." in flat
    assert "no park term and no fielder-arm term in the number" in flat
    assert "### 2.8 Park and fielder arm: measured beside the number, never in it" in flat
    assert ("A completed season freezes on November 1 of its year (the eWAR rule, "
            "`war_source.EWAR_FREEZE_MONTH_DAY`)") in flat


def test_identity_gates_i1_to_i9_and_the_refetch_rule():
    region = _section(_doc(), "## 3. Identity gates", "## 4. Descriptive agreement")
    expect = {
        "| I1 |": "SB and CS exact; GIDP within 0.5 percent",
        "| I2 |": "SB and CS exact for every player with any; GIDP exact for 97 percent or more of players with any",
        "| I3 |": "every final regular-season game of `season_game_pks` is in the record; otherwise the season does not serve",
        "| I4 |": "0 within 0.01 run",
        "| I5 |": "24 cells per season, monotone, K inside [500, 5000], sha256 stamped",
        "| I6 |": "parts sum to eBR within 0.011 (rounding); no NaN; per-season absolute eBR at most 30 runs",
        "| I7 |": "99 percent or more of eligible opportunities priced",
        "| I8 |": "a rebuild is byte-identical; a completed season is unchanged when a later season is added",
        "| I9 |": "no fitted consumer (`efv_*`, `proj_*`, `fa_*`, `arb_*`, `betting_*`, `leaderboard_vintages`) imports `ebr`",
    }
    for prefix, text in expect.items():
        assert text in _row(region, prefix), prefix
    flat = _flat(region)
    assert "triggers ONE re-fetch of that season's games of the mismatched players into `.cache/pbp_runners/refetch/`" in flat
    assert "A miss that survives blocks the season." in flat


def test_the_bug_bands():
    flat = _flat(_section(_doc(), "## 4. Descriptive agreement", "## 5. The outcome look"))
    assert "A miss means \"find the bug\", never \"invalid\"." in flat
    for band in ("r(eBR, B-Ref br + dp) at least 0.60 at PA 502+", "r(SB runs, wSB) at least 0.80",
                 "r(XB runs, Savant XB) at least 0.50", "r(DP runs, B-Ref dp) at least 0.60",
                 "SD ratio of SB + XB runs to BsR inside [0.5, 2.0]",
                 "absolute mean difference at most 1 run at PA 502+",
                 "r(sprint speed, (SB + XB runs) per 600 PA) at least 0.40 at PA 300+ every season"):
        assert band in flat, band
    assert "no per-player FanGraphs, Savant or Baseball-Reference value enters an eval artifact" in flat


# 5. The outcome look --------------------------------------------------------


def _part5() -> str:
    return _section(_doc(), "## 5. The outcome look", "## 6. What each outcome-look result licenses")


def test_leg_e_every_tooth():
    part5 = _part5()
    flat = _flat(part5)
    assert "computes everything in this part ONCE" in flat
    assert "2018-2019, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026" in flat
    assert "players with 300 or more plate appearances in BOTH seasons of a pair" in flat
    assert "FanGraphs' published `baseRunning` (BsR), `wSb`, `ubr`, `wGdp`, `batting`, `plateAppearances` and `numTeams`" in flat
    assert "The look STOPS with 'BLOCKER: other fwar vintage lacks <fields>'" in flat
    assert "Never a fresh fetch, and never the `.cache/statsapi_saber_*` payloads" in flat
    cand = _row(part5, "| Candidate |")
    assert "E = (eSB + ePK + eXB) / PA, approximately scope-matched to BsR since 2016" in cand
    assert "B = BsR / PA from the frozen vintage" in _row(part5, "| Incumbent |")
    stat = _row(part5, "| Statistic |")
    assert "d = mean(rho_E) - mean(rho_B)" in stat and "averaged over the six pairs" in stat
    prec = _row(part5, "| Precedent, stated exactly |")
    assert "eWAR v2's gate 2 (`ewar.gate_pitcher_persistence`" in prec
    assert "AND a forecast leg" in prec
    assert "\"the one that actually matters\"" in prec
    assert "This gate keeps persistence alone, for the reason below" in prec
    interval = _row(part5, "| Interval |")
    for t in ("player-clustered bootstrap", "B = 2,000, seed 20260807", "interval d +/- 1.645 sd"):
        assert t in interval, t
    assert "prints the bootstrap sd, the half-width and the dispositions it can reach BEFORE it prints d" in _row(part5, "| Floors first |")
    disp = _row(part5, "| Dispositions |")
    for t in ("at Delta = 0.02", "SHIP, the interval entirely above +0.02",
              "RULED OUT, entirely inside +/-0.02", "RESOLVED_LOSS, entirely below -0.02",
              "UNDECIDED otherwise"):
        assert t in disp, t
    assert "**Why persistence alone decides**" in flat
    assert "Baserunning has no \"actual\" next-season outcome independent of a construct" in flat
    assert "no outcome of this leg licenses \"more accurate\"" in flat


def test_the_guards():
    flat = _flat(_part5())
    assert "**Leg T, team runs (non-inferiority; required for every admission).**" in flat
    assert "Passes when r(off_E, runs) is at least r(off_B, runs) - 0.005" in flat
    assert ("Its r values (and DP-2's) are written ONLY to part 12.1 and to the look block of "
            "`.cache/ebr/preview/ebr_eval.json`, never to a `data/` file") in flat
    assert "carries Leg T's and DP-2's pass or fail, never an r against runs" in flat
    assert "No exporter relates eBR to runs or wins." in flat
    assert "The twin must come back RESOLVED_LOSS. If it does not, the look is VOID (part 6.5)." in flat
    assert "A SHIP also needs the point estimate of d on frame U alone above 0." in flat
    assert "A SHIP also needs the point estimate of d above 0 on the club-changers subset" in flat
    assert "The look prints the subset's size per pair before d." in flat


def test_the_dp_leg():
    flat = _flat(_part5())
    assert "### 5.4 The DP leg: the E-DP contrast decides; DP-1 is a plumbing floor" in flat
    assert "**The prior, disclosed.**" in flat
    assert "Baseball-Reference `runs_dp` per PA at Pearson 0.428 to 0.576" in flat
    assert "- **E-DP (deciding).**" in flat
    assert "d_DP = mean(rho_G) - mean(rho_R)" in flat
    assert "Its SHIP guards are 5.3's applied to d_DP" in flat
    assert "- **E-DP twin.**" in flat and "must come back RESOLVED_LOSS on E-DP, else the DP leg is VOID" in flat
    assert "- **DP-1, a plumbing floor, not an admission gate.**" in flat
    assert "it never admits anything" in flat
    assert "- **DP-2 (guard).** Leg T with eGDP added: r(off_B + eGDP, runs) at least r(off_B, runs) - 0.005" in flat
    assert "its r values kept as Leg T's are (5.3)" in flat


def test_bem_plus_bindings():
    flat = _flat(_part5())
    assert "### 5.8 BEM+ (rides only if part 1 records EBR-Q3 answer (a))" in flat
    assert "`k_p = hm * (1 - r) / r` (the `positional_fit.fit_signal` rule)" in flat
    assert "fit inside the look BEFORE any gate statistic, then frozen" in flat
    assert "Predictor seasons 2022, 2023 and 2024 (outcomes 2023 to 2025)" in flat
    assert "floors 100 starts on base in Y and 150 in Y+1" in flat
    assert "the twin, BEM+ permuted within predictor season, must FAIL the stolen-base clause" in flat
    assert ("gap against sprint speed, against stolen bases and against starts on base each with lo95 above 0, "
            "and against the raw parent lo95 at least -0.01") in flat
    assert "**Holdout:** the 2025-2026 pairs, read in the same run, reported beside the verdict, never merged." in flat
    assert "**On FAIL** BEM+ is not served." in flat
    assert "(`tools/ebr_gate.py --dry-run`)" in flat
    assert "A second run is forbidden whatever the first printed." in flat
    assert "never a Leg T or DP-2 r, nor any other correlation against runs or wins" in flat


# 6. What the outcome look licenses, and the claims --------------------------


def test_admission_tables_6_1_and_6_2_tied_to_part_1():
    part6 = _section(_doc(), "## 6. What each outcome-look result licenses", "## 7. The clock")
    flat = _flat(part6)
    row_a = _row(part6, "| (a) only if it repeats clearly more")
    assert ("Leg E is SHIP, Leg T passes, the twin is RESOLVED_LOSS, and d is above 0 on frame U and on "
            "the club changers") in row_a
    assert "Part 1 records EBR-Q1 (a), so the first row binds." in flat
    assert "Not admitted, eWAR v3 keeps FanGraphs' BsR." in flat
    assert ("It enters when part 1 records EBR-Q2 answer (a), EBR-Q1 is not (d), DP-1 (the plumbing floor) "
            "and DP-2 pass, the E-DP twin is RESOLVED_LOSS") in flat
    assert ("Not admitted, eWAR v3 carries no double-play part from 2016 on, as FanGraphs' served WAR does not."
            in flat)


def test_copy_table_and_the_repeats_is_not_accuracy_sentence():
    part6 = _section(_doc(), "### 6.3 Copy", "### 6.4 Registry")
    assert ("\"repeats more from one season to the next than FanGraphs' BsR on the same runners\""
            in _row(part6, "| SHIP |"))
    assert "\"repeats about as much" in _row(part6, "| RULED OUT |")
    assert "| none |" in _row(part6, "| UNDECIDED |")
    assert "\"repeats less" in _row(part6, "| RESOLVED_LOSS |")
    assert ("a number that repeats more is not shown to be more accurate" in _flat(part6))


def test_may_not_claim_list_with_clause_l_binding():
    flat = _flat(_section(_doc(), "## 8. What may and may not be claimed", "## 9. eWAR v3:"))
    assert "**May NOT claim,** whatever the outcome:" in flat
    assert "that eBR is more accurate than BsR, Savant's baserunning run value or Baseball-Reference's numbers" in flat
    assert "that eWAR v3 or any of its parts is more accurate than fWAR or eWAR v2" in flat
    assert "(`FWAR_LABEL_EPOCH_GATE.md` clause (l), read as binding here)" in flat
    assert "anything causal about speed, or a forecast word (luck, due, regress, trending, will, clutch, sleeper)" in flat
    assert "never \"regressed\"" in flat


# 7. The clocks ---------------------------------------------------------------


def test_part_7_clocks():
    part7 = _section(_doc(), "## 7. The clock", "## 8. What may and may not be claimed")
    flat = _flat(part7)
    assert "on or after 2026-10-04" in flat
    assert ("never between the fWAR epoch's step A and its step Z entry (step A has started when "
            "`../_pre_epoch_fwar_2026-10/` exists") in flat
    # The outcome look.
    assert "3. the date is on or after 2026-11-17" in flat
    assert "4. the date is not 2026-10-23, 11-06, 11-13, 11-16, 11-20 or 12-01, not the Z1 day and not the skill look's day (7.3)" in flat
    # The skill look.
    assert "`python -u tools/swar_lab.py --out docs/ebr-2026-09-30/swar_eval.json`" in flat
    assert ("the November re-gates have recorded DEM+'s confirmatory holdout AND the result of the 2026-11-16 "
            "HEM+ versus xwOBA re-gate") in flat
    assert "5. the date is not 2026-11-16, 11-20 or 12-01, not the Z1 day and not the outcome look's day (7.2)" in flat
    assert "the one exception is the shared session of 7.5, only if part 1 records EWV3-Q3 (b)" in flat
    # The holdout and the session rule.
    assert "Runs once, by `python -u tools/swar_lab.py --holdout`, on a later day than the skill look" in flat
    assert "Under the default (a), each look runs on its own day in its own writer session" in flat
    assert "a crash in the outcome look ends the session before the skill look starts" in flat
    assert "The frames do not expire" in flat


# 8. Part 9 --------------------------------------------------------------------


def _part9() -> str:
    return _section(_doc(), "## 9. eWAR v3:", "## 10. Disclosure")


def test_part_9_1_ewar_v2_displayed_and_never_written():
    flat = _flat(_part9())
    assert "**The displayed WAR is eWAR v2**" in flat
    assert "`bullpen_export.served_war_basis` keeps returning `war_provider` `ewar_v2`" in flat
    assert "eWAR v2 is NOT frozen or retired" in flat
    assert ("**Never written by any task of this plan:** `data/ewar.json`, `ewar.py`, `tools/build_ewar.py`, "
            "the provider `ewar_v2`, the glossary and registry entries named `ewar`") in flat
    assert "`war_source` refuses `ewar_v3` on the `arb_spine` door" in flat
    assert "nothing is ever stratified by consensus-FV cell" in flat


def test_part_9_2_display_only_column_after_step_z():
    flat = _flat(_part9())
    assert ("The new series shows only as a column labelled \"eWAR v3\", never plain \"eWAR\"; its shrunk-skill "
            "parts are labelled \"eWAR skill\"") in flat
    assert ("provider `ewar_v3`, servable, never `DEFAULT_PROVIDER`; built only after the step Z entry; display "
            "only, a column beside eWAR v2") in flat
    assert "eWAR_v3_i = fWAR_i + d_i / RPW_s" in flat
    assert "the departures sum to zero each season" in flat


def test_part_9_3_not_requested_and_kept():
    flat = _flat(_part9())
    assert "### 9.3 A new provider on eWAR v2's Baseball-Reference frame: NOT REQUESTED (EBR-Q0 (a))" in flat
    assert "The text stays as registered so the alternative remains on the record." in flat
    assert "- **`ewar_v2_ebr`** = a copy of eWAR v2's player-seasons" in flat


def test_part_9_4_rules_formulas_and_invariants():
    flat = _flat(_part9())
    for rule in ("1. **Never sum or scale an index.**",
                 "2. **Delta = skill arm minus actual arm, through the same function.**",
                 "3. **Re-centre every delta to zero per season and side,**",
                 "4. **Shrink with each EM+ module's own constants and pool targets, unchanged.**"):
        assert rule in flat, rule
    # S1, S1x, S2 (both HR variants), S3, S4.
    assert "**S1, candidate part 4, the HEM+ arm**" in flat
    assert "K = uBB 120, HBP 240, 1B 290, 2B 1000, 3B 1600, HR 170" in flat
    assert "g_bat,i = ((wOBA~_i - wOBA_i) / scale_s) * PA_i" in flat
    assert "**S1x, candidate part 4, the xHEM+ arm**" in flat
    assert "xwOBA~_i = xwOBA_i * lgwOBA_s / xbar_s" in flat
    assert "g_batx,i = ((xwOBA~_i - wOBA_i) / scale_s) * PA_i" in flat
    assert "**S2, candidate part 5**" in flat
    assert "q~_j,c = (m_j,c + K_c * nu_j,c) / (TBF_j + K_c), K = (70, 170, 170, 400)" in flat
    assert "dFIP_j = (13*(m~_HR - m_HR) + 3*((m~_BB - m_BB) + (m~_HBP - m_HBP)) - 2*(m~_K - m_K)) / IP_j" in flat
    assert "Delta_j = dwar0_j - IP_j * (sum_k dwar0_k / sum_k IP_k)" in flat
    assert ("S2 is computed in two variants: HR shrunk with REM+'s and SEM+'s shipped K_HOMERUN (400 batters "
            "faced), and HR left at fWAR's own home-run term.") in flat
    assert "**S3, candidate part 6**" in flat
    assert "g_fld,i = rel_i * (Fld_i + Frm_i) - (Fld_i + Frm_i) = -(1 - rel_i) * (Fld_i + Frm_i)" in flat
    assert "**S4, candidate part 3**" in flat
    assert "g_pos,i = Pos~_i - Pos_FG,i" in flat
    # The eight invariants.
    assert "**Invariants** (`test_swar.py`, built by EWV3_SKILL_BUILD_CORE)" in flat
    for n in range(1, 9):
        assert f"({n})" in flat.split("**Invariants**", 1)[1].split("### 9.5", 1)[0], n
    assert "(8) a build leaves the sha256 of `data/ewar.json` unchanged and imports no `fg_leaderboards`" in flat


def test_part_9_5_the_skill_look():
    part9 = _part9()
    region = _section(part9, "### 9.5 The skill look", "### 9.6 What each skill-look result licenses")
    flat = _flat(region)
    assert "does fWAR(Y) + the part's re-centred delta rank published fWAR(Y+1) better than fWAR(Y) does?" in _row(region, "| Question, per candidate part |")
    assert "Y = 2021, 2022, 2023, 2024; 2020 excluded on both sides" in _row(region, "| Pairs |")
    assert "hitters 200 PA in both seasons; pitchers 50 IP in both seasons" in _row(region, "| Floors |")
    assert "published fWAR(Y+1) per PA (hitters) or per IP (pitchers), from the frozen vintage" in _row(region, "| Target |")
    assert "candidate part 4 {HEM+ H-rate, HEM+ H-cum, xHEM+ H-rate, xHEM+ H-cum}" in _row(region, "| Cells |")
    assert "one per candidate part, over that part's cells (k = 2, 4, 2, 2); no correction across parts" in _row(region, "| Holm families |")
    assert "convention v2 primary" in _row(region, "| Statistic |")
    assert "gap <= 0, one-sided bootstrap p" in _row(region, "| Pre-committed null, per cell |")
    assert "B1 = a uniformly shrunk fWAR, (x * n + m * k) / (n + k), one k per side fitted on 2016 to 2018" in _row(region, "| Baselines |")
    assert "the twin's gap lo95 <= 0" in _row(region, "| Twin |")
    assert "positive in BOTH the 2016 to 2018 block and the 2021 to 2024 block" in _row(region, "| Era transport (candidate part 5) |")
    hr = _row(region, "| HR-arm clause (candidate part 5, computed FIRST) |")
    assert "R2e.2" in hr and "consistent with R2e.2's closure" in hr and "R2e.2 is not re-run" in hr
    assert "EQUIVALENT is unreachable for that cell" in _row(region, "| MDE95 |")
    boot = _row(region, "| Bootstrap |")
    assert "B = 2,000" in boot
    assert "<seed>" not in boot and "the writer fills it" not in boot
    seed = re.search(r"seed (\d{8}), the commit date of this document as YYYYMMDD", boot)
    assert seed and seed.group(1).startswith("2026") and seed.group(1) >= "20261004", boot
    # The precedence, verbatim, and the five dispositions.
    assert ("Each cell takes the first disposition that holds in the order WIN, SMALL WIN, LOSS, EQUIVALENT, "
            "UNRESOLVED, so exactly one applies.") in flat
    assert "the point gap is at least the registered margin +0.02" in flat
    assert "**WIN (components)** when also: lo95 > 0 against B1" in flat
    assert "- **SMALL WIN:** Holm rejects and lo95 > 0, but the point gap is under +0.02. It counts as EQUIVALENT for admission and copy." in flat
    assert "- **LOSS:** hi95 < 0." in flat
    assert "- **EQUIVALENT:** the 90 percent interval of the gap lies inside -0.02 to +0.02." in flat
    assert "- **UNRESOLVED:** anything else." in flat
    assert ("whether the 1.645-sd interval lies entirely above +0.02 (`docs/EFV_GATE_STANDARD.md` part 8's SHIP)"
            in flat)
    # Expectations, holdout and the tracked record.
    assert "**Registered expectations**" in flat
    assert "candidate part 3 is LOSS or UNRESOLVED, because its target carries FanGraphs' own positional adjustment" in flat
    assert "**The holdout.** The 2025 to 2026 pairs (predictor season 2025)" in flat
    assert "the TRACKED file `docs/ebr-2026-09-30/swar_eval.json`" in flat
    assert "A second run of either is forbidden whatever the first printed." in flat


def test_part_9_6_admission_and_copy():
    region = _section(_part9(), "### 9.6 What each skill-look result licenses", "### 9.7 The assembled series")
    flat = _flat(region)
    assert ("A candidate part enters eWAR v3 only when its rate cell is WIN (components) and its total cell "
            "is not LOSS (EWV3-Q1 (a)") in flat
    assert "the HEM+ arm enters unless the xHEM+ arm's rate gap over the HEM+ arm's" in flat
    assert "A candidate part not admitted leaves FanGraphs' own component in place." in flat
    assert "\"ranked the next season's fWAR better than fWAR itself did, and better than a uniformly shrunk fWAR\"" in _row(region, "| WIN (components) |")
    assert "| none |" in _row(region, "| UNRESOLVED |")
    assert "No sentence claims \"more accurate WAR\", \"better than FanGraphs\" or \"true talent\"." in flat


def test_part_9_7_assembly_and_labels():
    region = _section(_doc(), "### 9.7 The assembled series", "## 10. Disclosure")
    flat = _flat(region)
    assert "eWAR_v3_i = fWAR_i + d_i / RPW_s" in flat
    assert "their combination is never scored" in flat
    assert ("the column's label reads \"eWAR v3 (equals FanGraphs WAR: no part admitted)\"" in flat)
    assert "\"eWAR skill: pitching\", \"eWAR skill: fielding\"" in flat
    assert "\"eWAR skill: batting (HEM+)\" or \"(xHEM+)\"" in flat


def test_no_training_label_in_this_program():
    flat = _flat(_doc())
    assert ("are never a training label, a driver or an input to a fitted consumer in this program" in flat)


# 9. Part 10 and the amendment rule -------------------------------------------

SEALS = (
    ("proto_brr_2024_runners.csv", "4f1d4632f874b8f5"),
    ("proto_brr_2025_runners.csv", "f77ba2030c72dfbc"),
    ("proto_brr_2026_runners.csv", "e99930bbaec2039e"),
    ("proto_brr_2024.json", "d91b0635d3052025"),
    ("proto_brr_2025.json", "078871abb5989e25"),
    ("proto_brr_2026.json", "3bc4de32c738c256"),
)


def test_part_10_six_seals_and_read_to_write_this():
    part10 = _section(_doc(), "## 10. Disclosure", "## 11. Amendments")
    flat = _flat(part10)
    for name, prefix in SEALS:
        assert f"`{name}` {prefix}" in flat, name
    assert "were never joined across seasons" in flat
    assert "No year-to-year, split-half or forward number of eBR or of any eBR-like construct exists at this commit." in flat
    assert "every year-to-year leg moves to the 2026-2027 pair" in flat
    assert "### Read to write this: the skill and position parts" in flat
    for artifact in ("data/dem_plus_eval.json", "data/sem_plus_eval.json", "data/rem_plus_eval.json",
                     "data/hem_plus_eval.json"):
        assert f"(`{artifact}`)" in flat, artifact
    assert "**xHEM+** (registry `xhem_plus`" in flat
    assert "so the skill look is NOT a blind read on those components" in flat
    assert "No forward number of a skill or position part exists at this commit." in flat


def test_the_amendment_rule():
    flat = _flat(_section(_doc(), "## 11. Amendments", RESULTS_HEADING))
    assert "A dated amendment, committed alone, may only:" in flat
    assert ("An amendment lands BEFORE the look whose clauses it touches: before the outcome look for parts 2 "
            "to 6 and the outcome rows of part 1; before the skill look for parts 9.4 to 9.6") in flat
    assert ("Frames, statistics, thresholds, margins, Holm families, twins, guards, the dates and the claims "
            "never change.") in flat
    assert "after both looks, nothing above part 12 changes" in flat


def test_amendment_11_1_scope_matches_the_sb_band():
    flat = _flat(_section(_doc(), "## 11. Amendments", RESULTS_HEADING))
    assert "### 11.1 2026-10-14: the SB-runs bug band compares like with like (clause (ii))" in flat
    assert ("part 4's \"SB runs against wSB\" comparison and its bug band read eSB against wSB, at the "
            "same 0.80 and the same PA cuts; ePK's sd and r(ePK, wSB) are reported beside it every build.") in flat
    assert "(SB runs stays eSB + ePK), Leg E's E = (eSB + ePK + eXB) / PA" in flat
    assert "Committed alone, before the outcome look" in flat


def test_amendment_11_2_the_skill_look_target_is_next_season_realized_runs():
    flat = _flat(_section(_doc(), "## 11. Amendments", RESULTS_HEADING))
    assert ("### 11.2 2026-10-15: the skill look's target becomes next-season realized runs (clause (i), "
            "owner decision EW3-23)") in flat
    assert ("\"Yes, do your recommendation, with next-season realized runs becoming the target rule.\"") in flat
    assert "| EW3-23 | What the skill look scores candidate parts 3 to 6 against |" in flat
    assert "it is recorded as an owner override of that sentence for these items alone" in flat
    assert "Parts 2 to 6 (the outcome look, candidate parts 1 and 2 and BEM+) are not touched." in flat
    # The primary target and its base, per component.
    assert "#### 11.2.1 The primary target, per component (deciding)" in flat
    for row in ("| Batting | 4 (both arms) |", "| Pitching | 5 |", "| Fielding | 6 |",
                "| Baserunning | none in this registration |", "| Position | 3 |"):
        assert row in flat, row
    assert "B0 is the actual arm of the part's own delta function in season Y" in flat
    assert "a part must add forward signal beyond the player's own realized component" in flat
    assert "RA*_j = R_j - BQS_j + E_BQ_j + (IRS_j - E_IR_j)" in flat
    assert "RA9*_j = 9 * (RA*_j / PF_j + BF_j * F_t / BF_t) / IP_j" in flat
    assert "one k per component (batting, pitching, fielding), k = hm (1 - r) / r" in flat
    # The independent fielding source and the position part's dMAE rule.
    assert "is scored on Baseball-Reference's `runs_field` per player-season" in flat
    assert "the rule that the target never comes from the part's own source is new here" in flat
    assert "candidate part 3 keeps the ladder's own out-of-sample rule in place of the Spearman cells" in flat
    assert "with FanGraphs' published positional adjustment, the base S4 departs from" in flat
    # The team guard.
    assert "#### 11.2.4 The team guard (non-inferiority, deciding)" in flat
    assert "Two bootstraps, B = 2,000 each, seed 20261024: player-clustered" in flat
    assert ("**NON-INFERIOR** when dT - 1.645 sd is above -0.02 under both bootstraps, for every outcome the "
            "part carries.") in flat
    assert "No power figure was computed for this amendment" in flat
    assert "never an r against runs or wins" in flat
    # Secondary, admission, later parts, eWAR realized, disclosure and timing.
    assert "#### 11.2.5 The secondary estimand (reported beside, deciding nothing)" in flat
    assert "No admission, guard or copy sentence reads them." in flat
    assert "and its team guard is NON-INFERIOR" in flat
    assert "None uses a published WAR total as its deciding target." in flat
    assert "#### 11.2.8 eWAR realized has no forward target" in flat
    assert "the skill look is therefore even less blind than part 10 states" in flat
    assert "The skill look (part 7.3) does not run until `tools/swar_lab.py` implements this amendment" in flat
    assert "Committed alone, docs and its pin test only, before the skill look (part 12.2 is empty at this commit)." in flat


def test_amendment_11_3_the_blended_pitching_basis_and_the_realized_basis():
    flat = _flat(_section(_doc(), "## 11. Amendments", RESULTS_HEADING))
    assert ("### 11.3 2026-10-15: the blended pitching basis, a second arm of candidate part 5, and the "
            "realized pitching basis of eWAR realized (clause (i), owner decision EW3-20)") in flat
    assert "| EW3-20 | The pitching basis of eWAR and of eWAR realized |" in flat
    assert "it is recorded as an owner override of that sentence for these items alone" in flat
    assert "its Holm family grows from k = 2 to k = 4" in flat
    assert "\"xwOBA-allowed or contact-quality season estimators (X-S4, 0.377 vs 0.382)\"" in flat
    # S2b, its terms and its rows.
    assert "#### 11.3.1 The blended basis S2b (the second arm of candidate part 5): definition" in flat
    for formula in ("C_j = AB_j - SO_j + SF_j",
                    "X_j = (est_woba_j - woba_j) * D_j / scale_s",
                    "H*_j = W_HR (m*_HR,j - C_j * h_s) / scale_s",
                    "CQ_j = Xc_j - H*_j",
                    "B_j = -X_j + sum over j's clubs t of BF_jt * F_t / BF_t",
                    "L_j = RA*_j - E_j",
                    "dFIP_b,j = dFIP_j (S2, on m*_HR) + 9 * G_j / IP_j",
                    "Delta_b,j = dwar0_b,j - IP_j * (sum_k dwar0_b,k) / (sum_k IP_k)"):
        assert formula in flat, formula
    assert "With every K infinite, S2b equals S2 on every row." in flat
    assert "The club's fielding part F_t is put back once, into the BABIP residual" in flat
    # The constants, the realized basis and the runner reading.
    assert "by B1's rule (`swar_lab.fit_b1`, the DEM+ K_INN precedent)" in flat
    assert "never S2, a delta, a test value or a target" in flat
    assert "eWAR realized, pitcher j = fWAR_j + Delta_r,j" in flat
    assert "the sum over a season of RA*_j equals the sum of R_j" in flat
    # Scoring, admission, expectations, timing.
    assert "{P-rate, P-cum, S2b P-rate, S2b P-cum}, k = 4" in flat
    assert ("S2 enters unless S2b's rate gap over S2's (rho of the S2b test value minus rho of the S2 "
            "test value on the primary target") in flat
    assert "has lo95 above 0, in which case S2b enters" in flat
    assert "xwOBA-allowed 0.377 against FIP 0.382 on the same 592 starter seasons" in flat
    assert "a tie or a loss" in flat
    assert "No number of S2b, R2, CQ, B, L, RA9*, the runner terms or the three constants exists at this commit" in flat
    assert flat.count("Committed alone, docs and its pin test only, before the skill look (part 12.2 is empty at this commit).") == 2


def test_amendment_11_5_the_triangulated_fielding_arm():
    flat = _flat(_section(_doc(), "### 11.5 2026-10-16", RESULTS_HEADING))
    assert ("### 11.5 2026-10-16: the triangulated fielding arm S3t of candidate part 6 (clause (i), owner "
            "decisions EW3-18, EW3-20 and EW3-23)") in flat
    assert "| EW3-20 (defense) | The fielding part of eWAR v3 |" in flat
    assert "it is recorded as an owner override of that sentence for these items alone" in flat
    assert "its Holm family may grow from k = 2 to k = 4" in flat
    assert "`docs/ewar/FIELDING_TRIANGULATION_GATE.md` parts 3 and 4, by reference" in flat
    assert "S3t's cells exist only if the read of `docs/ewar/FIELDING_TRIANGULATION_GATE.md` part 5.5 makes S3t eligible" in flat
    assert "{H-rate, H-cum, S3t H-rate, S3t H-cum}, k = 4" in flat
    assert ("S3 enters unless S3t's rate gap over S3's (rho of the S3t test value minus rho of the S3 test "
            "value on the primary target") in flat
    assert "On the Statcast system B0 shares the target's system" in flat
    assert "eWAR realized (11.2.8) carries no S3t term under this registration." in flat
    assert "The skill look (part 7.3) does not score S3t until `tools/swar_lab.py` implements 11.5.2" in flat
    assert ("Committed alone, docs and their pin tests only, before the skill look (part 12.2 is empty at "
            "this commit).") in flat


def test_amendment_11_6_statcast_catcher_runs_the_catcher_component():
    flat = _flat(_section(_doc(), "### 11.6 2026-10-16", RESULTS_HEADING))
    assert ("### 11.6 2026-10-16: Statcast's catcher runs, the catcher component S3c of candidate part 6 "
            "(clause (i), owner decisions EW3-38 and EW3-23)") in flat
    assert "| EW3-38 (catcher) | The catcher reading of eWAR v3's fielding part |" in flat
    assert "it is recorded as an owner override of that sentence for these items alone" in flat
    # The definition: Statcast's FRP at C replaces the base's catcher fielding, re-centred.
    for formula in ("SC_i = FRP on i's catcher row of FanGraphs' fielding leaderboard for season s",
                    "BC_i = Fld_i + Frm_i - O_i",
                    "g_cat,i = SC_i - BC_i",
                    "d_cat,i = g_cat,i - PA_i * (sum_k g_cat,k) / (sum_k PA_k)",
                    "test value (part 9.4 form) fWAR_i + d_cat,i / RPW_s"):
        assert formula in flat, formula
    assert "The lab reads them as cached on look day, never fetched" in flat
    # Scoring: the catcher frame, 11.2's fielding row with DRS as the independent target.
    assert "restricted to hitters with 300 or more innings at C in season Y" in flat
    assert "The target follows 11.2.2's rule for a part led by Statcast: DRS (Sports Info Solutions) in Y+1" in flat
    assert "{H-rate, H-cum, C-rate, C-cum}, k = 4" in flat
    assert "{H-rate, H-cum, S3t H-rate, S3t H-cum, C-rate, C-cum}, k = 6" in flat
    assert "fitted from B0 and the target only (no SC, delta or test value read)" in flat
    # Admission and the combination rules.
    assert "It is a component, not an arm" in flat
    assert ("g_fld,i = rel_i * (Fld_i + Frm_i - BC_i + SC_i) - (Fld_i + Frm_i), with S3's own rel_i; "
            "g_cat is then not added a second time.") in flat
    assert "S3t's catcher term (the sum of T_C,r over i's catcher rows) is replaced by SC_i" in flat
    assert "eWAR realized (11.2.8) carries no S3c term under this registration." in flat
    # Disclosure and timing.
    assert "so S3c's cells are not blind" in flat
    assert "The skill look (part 7.3) does not score S3c until `tools/swar_lab.py` implements 11.6.1 and 11.6.2" in flat
    assert ("Committed alone, docs and their pin tests only, before the skill look (part 12.2 is empty at "
            "this commit).") in flat


def test_amendment_11_7_s3t_is_scored_by_owner_override():
    flat = _flat(_section(_doc(), "### 11.7 2026-10-19", RESULTS_HEADING))
    assert ("### 11.7 2026-10-19: S3t is scored in the skill look by owner override (clause (i), owner "
            "decision EW3-37)") in flat
    assert "| EW3-37 | Whether S3t is scored in the skill look after the triangulation read's forward leg L1 failed |" in flat
    assert "it is recorded as an owner override of 11.5.2's eligibility sentence" in flat
    assert "{H-rate, H-cum, S3t H-rate, S3t H-cum, C-rate, C-cum}, k = 6 (11.6.2)" in flat
    assert "The override makes S3t eligible to be scored; it admits nothing." in flat
    assert ("Committed alone, docs and their pin tests only, before the skill look (part 12.2 is empty at "
            "this commit).") in flat
    # 11.7 sits after 11.6 and before part 12.
    doc = _doc()
    assert doc.index("### 11.6 2026-10-16") < doc.index("### 11.7 2026-10-19") < doc.index(RESULTS_HEADING)


def test_amendment_11_8_the_displayed_name_is_plain_ewar():
    flat = _flat(_section(_doc(), "### 11.8 2026-10-19", RESULTS_HEADING))
    assert "### 11.8 2026-10-19: eWAR v3's displayed name (clause (i), owner decision EW3-19)" in flat
    assert "| EW3-19 (naming) | The displayed name of eWAR v3 (the label clause of EBR-Q0's recorded answer) |" in flat
    assert ("this replaces \"a column labelled eWAR v3 and never plain eWAR\" in EBR-Q0's row and the "
            "naming sentences of parts 0 and 9.1") in flat
    assert "**What it touches: the displayed name only.**" in flat
    assert "**Unchanged:** part 1's EBR-Q1 to EBR-Q3 rows; every clause either look reads" in flat
    assert ("Committed alone, docs and its pin test only, before the outcome look (part 12.1 is empty at "
            "this commit).") in flat
    # 11.8 sits after 11.7 and before part 12.
    doc = _doc()
    assert doc.index("### 11.7 2026-10-19") < doc.index("### 11.8 2026-10-19") < doc.index(RESULTS_HEADING)


def test_amendment_11_9_coded_steals_count_in_history_seasons_only():
    flat = _flat(_section(_doc(), "### 11.9 2026-10-19", RESULTS_HEADING))
    assert ("### 11.9 2026-10-19: a steal the history feed codes as an advance counts as the steal "
            "(clauses (i) and (ii), owner decision EBR-Q4B-ID)") in flat
    assert "| EBR-Q4B-ID | What the history backfill does when I1 and I2 miss by one stolen base" in flat
    assert "**Fix** (history seasons 2011 to 2017 and 2020 only;" in flat
    assert "(5) only the first such entry of that runner in the play." in flat
    assert "On the scan above the rule reads two entries (288830 and 491962) and none of the other three." in flat
    assert "**Unchanged:** every 2018-and-later season of the record, its files and manifest block" in flat
    assert ("Committed alone with its pin test, docs only, before the skill look (part 12.2 is empty at "
            "this commit).") in flat
    # 11.9 sits after 11.8 and before part 12.
    doc = _doc()
    assert doc.index("### 11.8 2026-10-19") < doc.index("### 11.9 2026-10-19") < doc.index(RESULTS_HEADING)


# 10. No result ----------------------------------------------------------------

RESULT_PATTERNS = (
    r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]",            # a confidence interval
    r"\bp\s*=\s*-?0?\.\d",                               # a p-value
    r"\brho(_[A-Z])?\s*=\s*-?\d",                        # a rho
    r"\bd(_DP)?\s*=\s*[-+]?\d",                          # a Leg E or E-DP estimate
    r"\bgap\s*=\s*[-+]?\d",                              # a forward gap
    r"\bdisposition\s*:\s*(SHIP|RULED OUT|UNDECIDED|RESOLVED_LOSS|WIN|SMALL WIN|LOSS|EQUIVALENT|UNRESOLVED)\b",
    r"\bverdict\s*:\s*\w",                               # a verdict
    r"\badmitted\s*:\s*(true|false|yes|no)\b",           # an admission record
)


def test_no_result_is_recorded_in_part_12():
    doc = _doc()
    assert doc.count(RESULTS_HEADING) == 1
    body = doc.split(RESULTS_HEADING, 1)[1]
    assert _flat(body).startswith(" **EMPTY AT REGISTRATION.** ### 12.1 The outcome look (parts 5 and 6) ")
    # Part 12.1 holds the outcome look's result (2026-10-19). It is pinned by
    # test_ebr_gate_result.py, not here: a result pin never lives beside a criterion pin
    # (the reason test_arb_gate_c2_registration.py gives).
    assert (ROOT / "test_ebr_gate_result.py").exists()
    # Part 12.2 holds the skill look's result (2026-10-19). It is pinned, with the tracked
    # record docs/ebr-2026-09-30/swar_eval.json, by test_ebr_gate_result.py, not here.
    assert body.index("### 12.1 The outcome look (parts 5 and 6)") < body.index(
        "### 12.2 The skill look (parts 9.5 and 9.6)") < body.index("### 12.3 The skill holdout (part 9.5)")
    # Part 12.3 holds the skill holdout's result (2026-10-21). It is pinned, with the
    # tracked record's holdout block, by test_ebr_gate_result.py, not here.
    rest = body[body.index("### 12.3 The skill holdout (part 9.5)"):]
    assert not _flat(rest).startswith("### 12.3 The skill holdout (part 9.5) EMPTY. ")
    tail = rest[rest.index("No identity receipt of the final build"):]
    flat = _flat(tail)
    assert "None may be written anywhere above this line." in flat
    for pattern in RESULT_PATTERNS:
        m = re.search(pattern, tail, re.I)
        assert m is None, f"a result is recorded after part 12.3: {m.group(0) if m else ''!r}"


# Registered thresholds that take an interval's shape. Each is stripped, after
# asserting it appears exactly once, before the result patterns are applied.
REGISTERED_RANGES = (
    "SD ratio of SB + XB runs to BsR inside [0.5, 2.0]",
)


def test_no_result_is_recorded_above_part_12_either():
    above = _flat(_doc().split(RESULTS_HEADING, 1)[0])
    for text in REGISTERED_RANGES:
        assert above.count(text) == 1, text
        above = above.replace(text, "")
    for pattern in RESULT_PATTERNS:
        m = re.search(pattern, above, re.I)
        assert m is None, f"a result is recorded above part 12: {m.group(0) if m else ''!r}"

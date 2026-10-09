# ETA FanGraphs-blend gate (registered 2026-09-25)

Candidates: two fixed-form blends of the served champion ETA with FanGraphs' published `eta_year` (arm A, arm B), plus a keep-or-remove gate for the org promotion multipliers the champion already serves (section 7). Lab: `tools/eta_fg_blend_gate.py`. Artifact of record: `data/eta_eval.json` (blocks `fg_blend_gate_2026_09_25` and `org_timing_gate_2026_09_25`).

This document is committed ALONE, before any read of the frame in section 3. Sections 3 to 7 are frozen at that commit. Section 8 is PENDING and is filled with verbatim lab output only, after the one registered look (section 6).

## 1. Why this gate exists, and what was already seen

Owner ask (2026-09-25): does PV improve ETA? The read-only lane `_finalpass_2026-09-24/pveta/` found PV a LOSS (its pre-declared PV model ran MAE 2.864 against the champion's 1.147). The same lane found that a fixed 50/50 blend of the champion with FanGraphs' `eta_year` beats the champion on the lane's development vintages: MAE 0.981 vs 1.147 (dMAE +0.166, CI95 +0.135 to +0.195), within-1y +0.073 (CI95 +0.058 to +0.088), overdue +52 against the +110 guardrail, better in all four test vintages (2018, 2019, 2022, 2023). FanGraphs alone read 0.874 there but marked +263 more still-active prospects overdue, a C4 failure.

The follow-up lane `_finalpass_2026-09-24/etaroster/` rebuilt the production champion with the 40-man shave (CH40) and found one roster fact that helps inside the blend: a prospect already on the 40-man at the list date. On its frame, "blend, then one year earlier if on the 40-man" read MAE 0.953 against the blend's 0.971 (dMAE +0.018, CI95 +0.011 to +0.025), overdue +0. MLB positional depth, org aggressiveness and org service-time timing were NULL there and are NOT arms of this gate.

Disclosure, frozen here: both arms' forms and the 0.5 weight and the 1.0 shift were chosen on the lanes' development vintages (lists 2017, 2018, 2019, 2022, 2023). Those vintages are spent. They are not scored again by this gate, and their numbers are not evidence for it.

## 2. Champion and arms, exactly

Notation: V is the list year of a row; `rnd(x) = floor(x + 0.5)` (round half up, never Python's banker's rounding).

**Champion CH40 (what serves today).** `eta.estimate_eta` on the `eta_backtest.build_cohort()` reconstruction of the row (level from the StatsAPI ladder through season V-1, the season V-1 line at that level, age at the listing date, the vintage consensus FV, the static norm tables), WITH `level_bias_adj = eta.LEVEL_BIAS_ADJ` and WITH `fortyman_adj = eta.FORTYMAN_ADJ[level]` when on40(V) = 1 (None otherwise), `snapshot_date` = the listing date. Predicted year = V + (eta_year - the compute year), the backtest convention. Not reconstructable per vintage and therefore not applied (disclosed, as in the 08-19 gate): Statcast+, health and IL state, the rolling empirical norms, and the org promotion tendency (section 7 tests that one separately).

**on40(V).** 1 if the player's MLBAM id is on his parent club's 40-man roster on the listing date, from StatsAPI `teams/{id}/roster?rosterType=40Man&date=<listing date>`; the parent club is `trades.canonical_org` of the org on the player's snapshot dated on the listing date. Unknown org or unknown MLBAM id gives 0 (reported as a count).

**FG(V).** The integer `tools_json._extras.eta_year` of the player's EARLIEST FanGraphs snapshot dated in year V that carries one. Never a later revision of that list.

**Arm A.** Where FG(V) exists: `max(V, rnd(0.5 x CH40 + 0.5 x FG))`. Everywhere else: CH40.

**Arm B.** Where FG(V) exists: `max(V, rnd(0.5 x CH40 + 0.5 x FG) - on40(V))`. Everywhere else: CH40. The shift is exactly 1 year.

Fixed constants, never tuned by this gate: the weight 0.5, the shift 1.0, the rounding rule, the floor at V. The lab computes both arms by calling `eta.fg_blend_eta_year`, the function the served path would call, so the gate scores the code that would ship.

## 3. Frame (fresh; never read by either lane)

- Rows: `eta_backtest.build_cohort()` with `VINTAGE_YEARS = (2024,)`, unchanged otherwise: one row per (player, 2024 listing), listing = median of each source's earliest 2024 FV snapshot, listing date = the earliest of them, rows that debuted before the listing date excluded, same input reconstruction.
- Excluded, asserted in code: the 2020 and 2021 lists (eFV's reserved list-vintage frame; never built, fit or scored); the development vintages 2017-2019 and 2022-2023 (spent); every list from 2025 on (under two seasons of follow-up).
- Outcome: debut year, counting only debuts dated on or before 2026-09-27, the final scheduled game of the 2026 regular season (StatsAPI `seasons/2026`). Sources: `build_cohort()`'s own (debuts.json, career_war, career_stats), plus the StatsAPI `mlbDebutDate` of every frame row with an MLBAM id, fetched at the look, so a 2026 debut the repo has not ingested yet still counts.
- Classes: debuted; censored_active = not debuted and professional activity in season 2025 or later; washed_out = the rest. For this frame the last complete season is 2026 (complete once 2026-09-27 has passed).
- Overlap disclosure, reported at the look: frame players also listed in the development vintages, and frame players also on the 2020 or 2021 lists (their 2020/2021 rows are never used). Frame players who debuted in 2025 or 2026 belong to eFV's reserved 2025+ debut cohorts: this gate reads only their debut YEAR and computes no eFV, consensus-FV, source-rank or realized-WAR quantity on any row. FanGraphs' `eta_year` alone is not scored on this frame (a source score), only the two arms and the champion.

## 4. Frozen clauses

Shared machinery: player-clustered bootstrap (resample unique player keys with replacement; a drawn player brings all his rows), B = 2000, seed 20260928, percentile CI95. MDE95 of a delta = 1.96 x its bootstrap standard deviation. dMAE = MAE(comparator) - MAE(arm), positive = arm better; dW1 = within-1y(arm) - within-1y(comparator). Within-1y = |predicted - actual| <= 1.

For each arm k in {A, B}, against CH40:

- **C1 row-matched MAE.** Frame = debuted rows where FG(V) exists and passes C5. PASS iff dMAE > 0, dMAE > MDE95, and the arm survives the Holm step below.
- **C2 row-matched within-1y.** Same frame. PASS iff dW1 > 0 and the 2.5th percentile of the bootstrap dW1 > 0.
- **C3 pooled system.** Frame = every CH40-scoreable debuted row of the frame (FG present or not). The pooled prediction is the arm itself (it already falls back to CH40). PASS iff pooled MAE < CH40 MAE.
- **C4 overdue guardrail (unchanged).** Frame = every censored_active row. Overdue = predicted year <= 2026. PASS iff overdue(arm) - overdue(CH40) <= +110. The pro-rata limit 110 x n_censored / 2311 is reported as a disclosure flag, not a gate.
- **C5 leak check.** Asserted in code, PASS iff all hold: the cohort's vintages are exactly (2024,); no 2020 or 2021 row was built; each FG(V) comes from a snapshot dated in 2024 that is the player's earliest FanGraphs snapshot in 2024 carrying `eta_year`; the roster pull date equals the row's listing date; the FG snapshot date precedes the player's debut date. A row whose FG snapshot is dated on or after his debut keeps CH40 in both arms (counted and reported).
- **Holm across the two arms (C1).** Per arm, the two-sided bootstrap p of dMAE = 2 x min(share of draws <= 0, share of draws >= 0), floored at 1/B. Sort the two p values: the smaller must be <= 0.025; only then is the larger tested, at <= 0.05. An arm that fails its Holm step fails C1.
- **C6 (arm B over arm A).** Same frame as C1. PASS iff the CI95 lower bound of dMAE(A - B) is > 0 and overdue(B) - overdue(A) <= +110.

Decision rule:
- An arm is a SHIP CANDIDATE iff C1 to C5 all pass.
- If both arms are ship candidates, B is recommended only if C6 passes; otherwise A (the simpler form).
- If one arm is a ship candidate, it is the recommendation.
- If neither is, NO SHIP: eta.py serves CH40 unchanged and the loss is written into `data/eta_eval.json` (never a new eval file for a failed challenger).
- The gate never flips the served ETA. A pass hands the owner the question "flip the served ETA to the blend?" with the numbers; the flip is the owner's call. The flag `eta.ETA_FG_BLEND_ARM` stays None until then.

Reported alongside, adjudicating nothing: by-level MAE for CH40 and each arm, the count of rows each arm moves, the count moved earlier and later, bias (mean predicted minus actual), and coverage (share of debuted rows with FG(V)).

## 5. Live shadow (arm B's independent confirmation)

The research frame for arm B is spent, and the 2024 frame carries only about 2.5 seasons of follow-up, so arm B also gets a live shadow. At the look, the lab builds the 2026 list with the same construction (`VINTAGE_YEARS = (2026,)`, inputs as of each listing date, on40 at the listing date) and freezes CH40, arm A and arm B predictions for every row into the `fg_blend_gate_2026_09_25` block. No outcome of a 2026 row is read or stored at the look. The shadow is scored once, on the first run on or after the day after the 2028 regular season's final scheduled game, with the clauses of section 4 (overdue = predicted year <= 2028). It adjudicates nothing about the 2024 read.

## 6. The look

- Once: the first run of `python tools/eta_fg_blend_gate.py` on or after 2026-09-28. The lab refuses to score before that date, and refuses a second scored look once the block records one (it can re-print the stored result).
- The 2020 and 2021 lists stay out even if some later need would want them; only the eFV owner can release them.
- Section 8 receives the verbatim lab output. The registry row `eta_fg_blend` is written with the verdict, `data/eta_eval.json` as its eval artifact.

## 7. Keep-or-remove gate: the served org promotion multipliers

What serves today: `storage.py` computes `org_promotion_tendencies` from the trailing calendar years of promotion and debut events (`run_monthly._derive_all_level_changes`), keyed by each player's CURRENT org, and passes it to `estimate_eta`, where it moves two things: the H1/H2 half-season multiplier (`eta._org_promotion_phase_weight`) and the aggressiveness floor multiplier (`aggressiveness_index`). Neither has ever been inside a backtest champion. The roster-aware lane found point-in-time org timing and org aggressiveness NULL.

- KEEP arm: CH40 with `org_promotion_tendency` built point-in-time for each row: the served computation (the same H1/H2 bucketing, the same `sample_n >= 5` rule, the same median-normalised aggressiveness index) over events dated before the listing date in seasons V-3 to V-1, minus seasons 2020 and 2021 (for the 2024 list: 2022 and 2023), each event's player mapped to the org on his latest snapshot dated on or before the listing date. Players with no org there are skipped, as the served rule skips players with no org.
- REMOVE arm: CH40 with `org_promotion_tendency = None`.
- Frame: the section 3 frame (all CH40-scoreable rows; FG not required). Same bootstrap machinery and seed.
- KEEP survives iff: dMAE(REMOVE - KEEP) > 0 with its CI95 lower bound > 0 on the debuted rows, AND overdue(KEEP) - overdue(REMOVE) <= +110 on the censored_active rows.
- Otherwise the recommendation is REMOVE: the multipliers leave `estimate_eta`'s served call (pass None). If the two arms produce the same year on every row, the multipliers have not earned their place either, and the recommendation is REMOVE. The eta_half bucket they also nudge is not a year and is not scored; a removal takes it with them.
- Removal is a served-number change and the owner's call, recorded as a question with the result. Disclosed deviation from the served rule: seasons 2020 and 2021 are left out (a 60-game season, and the reserved list vintages' debut years), so the point-in-time window is shorter than the served one.

## 8. Results (verbatim lab output)

The one registered look is recorded (second run, below). The first run crashed before recording anything and is disclosed first.

### First run, 2026-09-30 17:59, crashed before recording

Added 2026-09-30. The first run of `python -u tools/eta_fg_blend_gate.py` (17:59:32 to 18:00:02 EDT, no monthly and no pytest running, the monthly's step log ended 13:38) scored and printed every adjudicating clause, then crashed in a line that adjudicates nothing: the by-level table reported alongside (section 4) sorted the set of levels at `tools/eta_fg_blend_gate.py:455`, and some C5-clean debuted rows carry level None (the cohort counts 281 `no_level_age_fallback` rows). The crash came before `decide()`, before the section 7 org-multiplier gate, before the section 5 live-shadow freeze and before the artifact write.

Its stdout, verbatim:

    cohort 2024: {"censored_active": 877, "debut_after_cutoff_ignored": 0, "debut_from_statsapi": 6, "debuted": 497, "dropped_debut_before_listing": 1, "excluded_no_bio": 0, "excluded_post_debut": 146, "fg_present": 1183, "level_from_career_stats": 669, "level_from_statsapi": 462, "listed": 1558, "mlbam_unknown": 1, "no_level_age_fallback": 281, "on40": 56, "org_unknown_at_V": 24, "overdue": 137, "washed_out": 21}
    frame: rows=1394 debuted=503 censored_active=871 fg_debuted_c5_clean=446 fg_rows_failing_c5=0
    arm A C1 ROW-MATCHED MAE: n=446 CH40 1.0224 vs 0.861; dMAE +0.1614 MDE95 0.0563 CI95 [+0.1054, +0.2152] p 0.0005 Holm pass -> PASS
    arm A C2 ROW-MATCHED WITHIN-1Y: CH40 0.7377 vs 0.8453; d +0.1076 CI95 [+0.0762, +0.1435] -> PASS
    arm A C3 POOLED MAE (n=503): 0.8489 vs CH40 0.992 -> PASS
    arm A C4 OVERDUE: censored_active n=871; CH40 205 vs 201; delta -4 vs limit +110 (pro-rata flag 41.5) -> PASS
    arm B C1 ROW-MATCHED MAE: n=446 CH40 1.0224 vs 0.8094; dMAE +0.2130 MDE95 0.0605 CI95 [+0.1547, +0.2735] p 0.0005 Holm pass -> PASS
    arm B C2 ROW-MATCHED WITHIN-1Y: CH40 0.7377 vs 0.8408; d +0.1031 CI95 [+0.0739, +0.1368] -> PASS
    arm B C3 POOLED MAE (n=503): 0.8032 vs CH40 0.992 -> PASS
    arm B C4 OVERDUE: censored_active n=871; CH40 205 vs 201; delta -4 vs limit +110 (pro-rata flag 41.5) -> PASS
    C6 B OVER A: dMAE +0.0516 CI95 [+0.0269, +0.0785]; overdue B-A +0 -> PASS

Its stderr, verbatim:

    Traceback (most recent call last):
      File "C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools\eta_fg_blend_gate.py", line 618, in <module>
        sys.exit(main())
                 ~~~~^^
      File "C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools\eta_fg_blend_gate.py", line 614, in main
        return run_look()
      File "C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools\eta_fg_blend_gate.py", line 555, in run_look
        blend = run_blend_gate(rows, log)
      File "C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools\eta_fg_blend_gate.py", line 455, in run_blend_gate
        for lv in sorted({r["level"] for r in fgdeb})}
                  ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    TypeError: '<' not supported between instances of 'str' and 'NoneType'

No block was written: `data/eta_eval.json` stayed byte-identical to its pre-run copy, with neither `fg_blend_gate_2026_09_25` nor `org_timing_gate_2026_09_25`. The VERDICT line was never printed, the org gate never ran, the 2026 shadow was never frozen, and nothing was committed.

Owner decision (2026-09-30, ETA-1): repair the report-only sort with one line (a None level now sorts last: `sorted(..., key=lambda x: (x is None, x or ""))`), commit that repair alone with this disclosure, and rerun the look once. The rerun must reproduce the `cohort 2024:` line, the `frame:` line and the nine clause lines above byte for byte, or the look is VOID. No scored clause's code changes in the repair; `test_eta_fg_blend_gate.py` gains a synthetic frame with a level-None row so the by-level table is exercised. Before the repair, the parts of the look that run after that line and score nothing were smoke-run once for crashes (the level-change rebuild, the point-in-time org tendencies on one listing date, and the 2026 shadow construction, which reads no outcome); they printed only counts (7,108 players with level changes, 31 orgs with a tendency on 2024-02-01, 4,486 shadow rows) and wrote nothing.

### Second run, recorded look

`python -u tools/eta_fg_blend_gate.py`, run once on 2026-09-30 after commit 6ca2e8f4 (the one-line repair), finished 19:18 EDT with exit code 0. No monthly, pytest or other writer ran. The inputs the frame reads (`prospects.db`, `data/debuts.json`, `.cache/mlbam_ids.json`) were last written before the first run began. Its stdout, verbatim (stderr was empty):

    cohort 2024: {"censored_active": 877, "debut_after_cutoff_ignored": 0, "debut_from_statsapi": 6, "debuted": 497, "dropped_debut_before_listing": 1, "excluded_no_bio": 0, "excluded_post_debut": 146, "fg_present": 1183, "level_from_career_stats": 669, "level_from_statsapi": 462, "listed": 1558, "mlbam_unknown": 1, "no_level_age_fallback": 281, "on40": 56, "org_unknown_at_V": 24, "overdue": 137, "washed_out": 21}
    frame: rows=1394 debuted=503 censored_active=871 fg_debuted_c5_clean=446 fg_rows_failing_c5=0
    arm A C1 ROW-MATCHED MAE: n=446 CH40 1.0224 vs 0.861; dMAE +0.1614 MDE95 0.0563 CI95 [+0.1054, +0.2152] p 0.0005 Holm pass -> PASS
    arm A C2 ROW-MATCHED WITHIN-1Y: CH40 0.7377 vs 0.8453; d +0.1076 CI95 [+0.0762, +0.1435] -> PASS
    arm A C3 POOLED MAE (n=503): 0.8489 vs CH40 0.992 -> PASS
    arm A C4 OVERDUE: censored_active n=871; CH40 205 vs 201; delta -4 vs limit +110 (pro-rata flag 41.5) -> PASS
    arm B C1 ROW-MATCHED MAE: n=446 CH40 1.0224 vs 0.8094; dMAE +0.2130 MDE95 0.0605 CI95 [+0.1547, +0.2735] p 0.0005 Holm pass -> PASS
    arm B C2 ROW-MATCHED WITHIN-1Y: CH40 0.7377 vs 0.8408; d +0.1031 CI95 [+0.0739, +0.1368] -> PASS
    arm B C3 POOLED MAE (n=503): 0.8032 vs CH40 0.992 -> PASS
    arm B C4 OVERDUE: censored_active n=871; CH40 205 vs 201; delta -4 vs limit +110 (pro-rata flag 41.5) -> PASS
    C6 B OVER A: dMAE +0.0516 CI95 [+0.0269, +0.0785]; overdue B-A +0 -> PASS
    VERDICT: SHIP CANDIDATE (owner's call); recommended arm B
    ORG GATE: debuted n=503 rows moved 0; REMOVE 0.992 vs KEEP 0.992; dMAE +0.0000 CI95 [+0.0000, +0.0000]; overdue KEEP-REMOVE +0 -> REMOVE
    live shadow frozen: 2026 list rows=4486; scored after the 2028 regular season
    wrote fg_blend_gate_2026_09_25 and org_timing_gate_2026_09_25 into eta_eval.json

Reproduction (owner rule ETA-1): the `cohort 2024:` line, the `frame:` line and the nine clause lines are byte-identical to the first run's eleven lines above, so the look stands.

Artifact of record: `data/eta_eval.json`, blocks `fg_blend_gate_2026_09_25` (look 2026-09-30, the clauses, the decision, the by-level table, the verbatim lines, and the 2026 live shadow of 4,486 frozen rows, scored after the 2028 regular season) and `org_timing_gate_2026_09_25`.

**Verdict (section 4): SHIP CANDIDATE, both arms; recommended arm B** (C6 passes: arm B beats arm A row-matched by dMAE +0.0516, CI95 +0.0269 to +0.0785, overdue B-A +0). The gate itself flips nothing; the flip is the owner's call (answered 2026-09-30 as ETA-2: flip to arm B if this verdict is recorded).

**Section 7 result: REMOVE.** On the 1,394-row frame the KEEP arm (point-in-time org promotion tendencies) and the REMOVE arm (None) give the same debut year on every row (rows moved 0; debuted MAE 0.992 both; overdue 205 both). Section 7's rule reads: if the two arms produce the same year on every row, the multipliers have not earned their place, and the recommendation is REMOVE. The stored bootstrap p of 2.0 is what the formula gives on an all-zero delta (2 x min(1, 1)) and adjudicates nothing. Removal is a served-number change and the owner's call; the multipliers keep serving until the owner answers.

**Section 7 owner decision (2026-09-30, ETA-3): REMOVE.** Added 2026-09-30, after the recorded results above, which are unchanged. The owner took the registered recommendation: `storage.py`'s one served call to `estimate_eta` passes `org_promotion_tendency=None` and no longer computes the per-org tendencies, so the H1/H2 half-season multiplier (`eta._org_promotion_phase_weight`), the aggressiveness floor multiplier (`aggressiveness_index`) and the org nudge on the `eta_half` bucket are off on every served row. The functions stay in `eta.py` for this lab. The PROSPX ETA breakdown drops its "org promotes X% H1 / Y% H2" line; the Org Tendencies page is display only and unchanged.

Measured on the same inputs (the timeseries of 2026-09-30 20:01, regenerated at 22:13 with `python -u run_monthly.py --rebuild-only`, then `python tools/export_trade_values.py`; the only player fields that differ are `eta` and `surplus`): of 4,665 served ETAs, 45 years move, all one year earlier, all in the three orgs whose H1 share was 70% or more (CLE 22, LAD 12, CHW 11), where the post-break half-season term goes from -0.15 to the league -0.25 on 471 rows and 45 of them cross a rounding boundary (36 unblended, 9 blended; the one top-100 mover is Robert Arias, 2030 to 2029). The `eta_half` bucket moves on 294 rows (249 with the year unchanged: 204 Early to Late, 45 Late to Early; e.g. Grady Emerson Early 2029 to Late 2029). The aggressiveness floor moved two model years one year later (SFG, BAL) on blended rows and no served year. The org line leaves all 4,665 breakdowns. This differs from the gate frame's zero because the frame's listing dates sat before the All-Star break, where the half-season multiplier barely acts, and today's snapshot is post-break (the caveat recorded with the owner question). Downstream: PROSPX surplus value moves on 139 rows (total -$37.9M, from -$2.0M to +$1.8M), eFV `surplus_mm` on 203 rows (total -$42.4M), no eFV grade moves.

Added 2026-10-08. Disclosure from the read-only lane efv2026 (2026-09-30), which counted, with no score joined and before this look's first run (its counts file `facts2026.json` was written 2026-09-30 13:01), V 2024 frame players who debuted in 2026 (63 hitters / 72 pitchers) and in 2025-26 (136 / 153); 212 / 207 of the V 2024 frame's players also sit on the V 2026 list frame, whose raters the frozen 2026 shadow of section 5 joins under `docs/efv-v2/SURROGATE_2026_GATE.md` s2.2 (shadow rows listed before a frame row's window end only). Nothing recorded above changes. The efv2026 owner answer OQ1 reads A at this addendum.

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

PENDING. The look is owed on or after 2026-09-28.

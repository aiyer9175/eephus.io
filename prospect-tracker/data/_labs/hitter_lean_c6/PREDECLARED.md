# C6: the fresh hitter-lean test (PRE-DECLARED, task SG_6)

DESCRIPTIVE PROBE. Not a driver, not a ledger row, not a read of the surrogate gate. Read
once on the rows it touches.

Written 2026-10-19, before any outcome (2025 or 2026 MiLB line of a list player, grade
change, WAR) was read by this lane. Its row policy is the first line of PROBES.jsonl,
written before this file. Nothing below changes after the first outcome read; anything run
beyond it goes to PROBES.jsonl as EXTRA and carries no verdict weight.

## Origin
The 2026-09-25 frame-projectability lane (`_finalpass_2026-09-24/frameproj/`, VERDICT.md s3;
DECISIONS_FOR_OWNER.md:303-306) found, after looking, that LEAN (leaner than expected for
height and age) predicts LESS forward MiLB ISO than the scouts' power grades imply: -0.086 SD
(CI95 -0.127 to -0.042) on the FanGraphs lists 2017-2019 and 2022-2024, negative in all 6
years. Post hoc, so a hypothesis. VERDICT.md named the one fresh slice: the 2025 FanGraphs
list, forward ISO over the 2025 and 2026 seasons, predicted sign NEGATIVE on LEAN, with the
player overlap with the 2024 list disclosed. Owner answer efv2026 OQ5 = A (2026-10-01): run
after the surrogate gate's REGISTERED commit (baffcff7, 2026-10-15) with every lv_2026 player
excluded and counted (OQ2 = A: never included).

## Population
- FanGraphs rows, `snapshots.source='fangraphs'`, interval_label `2025report`; hitter rows are
  those whose `tools_json` has `raw_pwr` (the original lane's rule).
- Required inputs: height, weight, age, future raw_pwr, game_pwr, hit, present raw_pwr,
  present game_pwr; height over 60 inches. Rows missing any are dropped before the index is
  built (counted).
- No 2020 or 2021 list row is read. The 2024report list is read only to count overlap.

## Index (built on every eligible 2025 hitter row, before any exclusion or outcome filter)
- BMI = 703 * lb / in^2. LEAN = z(-(residual of OLS BMI ~ 1 + height + age)).
- TALL = z(height). YOUNG = z(-age). PROJ = z(TALL + LEAN). Exactly the original formulas.

## Identity and row exclusions (in this order; each counted)
1. ABSENT_IDENTITY: the FG player_key has no universe record (efv_vintage_frame.load_universe),
   or efv_identity.resolve_record(rec, 2025, build_index(2024), "hit") gives no person id.
   Counted, not scored.
2. LV_2026: the player is on the frozen V 2026 rater frame (data/efv_surrogate_frame_2026.json,
   either side) by player_key, resolved person id or record id. Counted, never scored.
3. R-VM 2026 cohort: first MLB event (efv_surrogate._mlb_event_ids, ids only) in 2026. Leaves,
   counted (no rvm_look_2 record). The 2025 cohort stays only if look_records() holds
   rvm_look_1 at run time; its count is printed either way. No MLB stat is read.
4. O1 below 150 PA: no outcome, counted.

## Outcome
- O1 = PA-weighted mean over MiLB lines (DSL, CPX, A, A+, AA, AAA; MLB excluded) in seasons
  2025 and 2026 of (ISO - the PURE norm ISO of that level-season), ISO = slg - avg. 2026 norms
  from data/milb_norms_2026_pure.json; 2025 norms from efv_surrogate._pure_norms (the pinned
  store). Lines from the pinned store (efv_surrogate._season_index). At least 150 MiLB PA over
  the two seasons. Regular season only.

## Controls (every model)
FG future raw_pwr, game_pwr, hit; present raw_pwr, game_pwr; age; level at list (the highest
MiLB level with a line in 2024, one-hot, none its own dummy, DSL the reference); consensus FV
at 2025 as a CONTINUOUS control (efv_vintage_frame.frame_row grades, FG FV where absent); the
baseline ISO_rel of season 2024 (at least 100 PA; missing = sample mean plus a missing dummy).
One list year, so no year effect. Height and weight are not controls (they are the index).

## Models, metric
- PRIMARY (the predicted mechanism): O1 (z-scored on the analysis sample) ~ controls + TALL +
  LEAN; the LEAN coefficient. Predicted sign NEGATIVE.
- Secondary S1: controls + PROJ, the PROJ coefficient (the original primary; it read -0.040).
- Secondary S2: controls + LEAN alone, the LEAN coefficient.
- Metric: standardized OLS coefficient (outcome SD per index SD), player-clustered bootstrap
  CI95, B = 2000, seed 20260925 (the original lane's seed).

## Reading rule (descriptive; nothing ships, nothing is admitted)
- REPLICATED: primary coefficient below 0 with CI95 upper bound below 0.
- SAME SIGN, NOT RESOLVED: coefficient below 0, CI95 spans 0.
- NOT REPLICATED: coefficient at or above 0.
Even REPLICATED makes LEAN no driver candidate: it would still need DS-06 and its own
registration (VERDICT.md s3). The rows left after excluding lv_2026 are a SELECTED subset
(players not on any 2026 rater list, plus released 2025 debutants), and the read says so.

## Descriptive strata (no CI, no verdict; no FV-cell stratum anywhere)
side (hitters only); age at list (20 or under, 21 to 22, 23 or over); last level (none,
DSL or CPX, A or A+, AA or AAA); route (international FA, college draft, high school draft,
other or unknown; acquisition known before 2025 only); bonus band (under 250k, 250k to 1M,
1M or over, unknown). Per stratum: n, and the Spearman of LEAN with the residual of O1 from
the controls-only design fitted on the whole analysis sample; n under 20 prints n only.

## Disclosures printed with the read
Counts at every exclusion step; analysis players also on the 2024report FG hitter list (their
2025 ISO entered the original lane's O1 for list 2024, so that season is partly spent); the
selected-subset warning above.

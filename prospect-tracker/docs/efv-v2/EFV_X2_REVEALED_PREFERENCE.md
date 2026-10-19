# EFV_X2_REVEALED_PREFERENCE: team revealed-preference drivers (registration)

Registration status: REGISTERED 2026-10-15, committed alone before any number of this task
exists. Owner decision EW3-12 (2026-10-15, verbatim "Let's do all of the above",
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), step (2) of the expert eFV program. The module
is `efv_x2_revealed.py`; its tests are `test_efv_x2_revealed.py`; its artifact is
`data/_labs/efv_x2/efv_x2_revealed.json` (data/_labs ships in no deploy consumer); the plain
results are `docs/efv-v2/EFV_X2_REVEALED_PREFERENCE_RESULTS.md`.

## 1. The idea

Clubs hold private information about their own players (makeup, health, internal
tracking, what their coaches see). Their decisions leak it: how fast they push a player,
whether they protect him from the Rule 5 draft, whether they invite him to big-league
camp, whether they trade him as the main piece for a major leaguer, whether they release
him, and how much over or under slot they paid him. This task turns those decisions into
per-player columns dated strictly before each row's read, and measures, one column at a
time, whether adding it to PROSPX consensus improves the within (side, vintage) Spearman
rank correlation with the outcome on the development frames. The result is DESCRIPTIVE:
it feeds EFV_X3_POOLED_MODEL as a list of inputs and their development readings. It ships
nothing and moves no served number under any outcome.

## 2. Frames (development only)

| id | rows scored | label | role |
|---|---|---|---|
| lv_dev | list vintages 2017, 2018, 2019, every scored row of `tools/efv_v2_model_class_screen.build_inputs` | W3 on the frozen fWAR label (`efv_labels`, provider fwar, resolved through 2026) | development, spent, not a claim |
| vm_dev | the vm2 vintage-matched frame, debut cohorts 2017 to 2023, every scored row of the same builder | the v1 six-season label on the same provider | development, spent, not a claim |

The training rows of each fold are the fold's own forward-chained training rows from that
builder (lv: frame rows of list vintages before V and not in the V frame; vm: matrix rows
with a decision year before the fold). Nothing is read on R-LV (list vintages 2020 and
2021) or R-VM (the 2025 and later debut cohorts): the builder raises on them
(`efv_vintage_frame.guard_score_request`, `RESERVED_LV`, `R_VM_FIRST_DEBUT_YEAR`) and the
module asserts every fold is a development fold. The owner's 2026 decision (EW3-13) gives
the 2026 season to EFV_2026_HOLDOUT_READ; this task reads no 2026 outcome and no
preseason-2026 list.

## 3. The columns (pre-declared, frozen at this commit)

Every column is read on the person id the base reads use: the OUTCOME-BLIND id on lv rows
(`efv_identity`, never `record_mlbam_id`) and the matrix id on vm rows (partly a debut
proxy, bug B4, disclosed). The as-of date of a row is its read: the lv frame row's
`asof_date` (the latest board point inside the V preseason window), a vm training row's
matrix `asof_date`, a vm test row's pinned preseason read (`efv_v2_model.pinned_inputs`).
A transaction counts only when announced strictly before the as-of date; a MiLB season
counts only when it is earlier than the as-of year; an invitation counts only when its
known date is strictly before the as-of date; a bonus counts only when its draft year is
earlier than the as-of year. The module records the latest input date of every value and
asserts it is before the as-of date.

Promotion aggressiveness, from MiLB season lines (`milb_history.season_splits`, cached,
levels DSL < CPX < A < A+ < AA < AAA; a level counts in a season when the line has at
least 20 PA for a hitter or 20 batters faced for a pitcher):

1. `x2_promos_per_season`: arrivals at a level above every level reached before (the entry
   level is not an arrival), divided by the seasons with a counted line.
2. `x2_promo_age_rel`: mean over those arrivals of the player's season age minus the
   median season age of every counted line at that level and season (same side).
3. `x2_midseason_jumps`: seasons' counted levels beyond the first, summed (moves inside a
   season), divided by the seasons with a counted line.
4. `x2_skipped_levels`: full-season ladder levels (A, A+, AA, AAA) jumped over at an
   arrival from a full-season level, summed.

40-man and Rule 5, from the league transaction feed (`.cache/mlb_transactions`, read
through this module's own loader, never written). On-40-man status at a day replays the
status codes of `efv_drivers` (an add: SE, R5, CLW or a signing whose description names a
major league contract; implied: OPT, CU; a removal: OUT, REL, DES, DFA, RET, RTN, R5M).
The Rule 5 draft day of a year is the December day with the most CLW, R5 and R5M
transactions. Rule 5 eligibility: the signing year S is the last draft year in
`.cache/draft_history` at or before the first season with a MiLB line, or, for a player
never drafted, that first season minus one when his age in it is 17 or less and the first
season otherwise; the first eligible draft is in December of S + 4 when he was 18 or
younger at signing (age on June 5 of S from the birth date, else the first-season age),
S + 3 otherwise. No first MiLB season: every Rule 5 column is None.

5. `x2_add_before_elig`: 1.0 when the first 40-man add came before his first eligible
   Rule 5 draft day, else 0.0.
6. `x2_r5_protect`: at the latest eligible Rule 5 draft day before the read, +1.0 when on
   the 40-man, -1.0 when exposed; 0.0 when no eligible draft day has passed.
7. `x2_r5_exposed_n`: eligible Rule 5 draft days before the read at which he was exposed.
8. `x2_r5_selected`: 1.0 when taken in the major league phase (R5, or CLW by a major league
   club on the draft day) before the read.
9. `x2_r5m_selected`: 1.0 when taken in the minor league phase (R5M, or CLW by a minor
   league club on the draft day) before the read.

Other club decisions, from the same feed:

10. `x2_options`: option transactions (OPT) before the read.
11. `x2_release_events`: releases, designations and outrights (REL, DES, OUT) before the
    read.
12. `x2_trades`: trade transactions (TR) naming him before the read.
13. `x2_trade_principal_mlb`: 1.0 when, before the read, he was one of at most two players
    his club sent in a trade (one transaction id) whose return included a player with a
    major league line in the trade season or the season before; else 0.0. The return's
    consensus value is NOT measured: grading the return players at the trade date needs
    their record ids, which are a debut proxy (bug B4).

Spring camp, from the cached non-roster invitee lists (`.cache/efv4_nri`, 2009 to 2025,
dated by `efv_w2_nri`'s rule) and this task's extension of the same endpoint to 2026 in
`.cache/efv_x2_revealed/nri` (one season, 30 clubs, polite single requests, no fetch from
06:00 to 11:00 UTC):

14. `x2_nri_springs`: distinct springs on a big-league non-roster invitee list, known
    strictly before the read. (The W2 lane read two NRI columns on these frames on
    2026-10-08; this column is the same signal and is re-read here only as one of the X2
    inputs.)

Market price, from `data/draft_bonus_slot.json` (signing bonus and slot value, 2017
onward; earlier drafts carry no money on the endpoint):

15. `x2_bonus_vs_slot`: natural log of bonus over slot, the slot being the pick value when
    the endpoint gives one and 125,000 dollars (the rounds-11-plus allowance) otherwise;
    None before the 2017 draft, for an unsigned pick and for a player never drafted.

## 4. The statistic

For a column f and a fold (side, year) of a frame:

- u: the consensus percentile within (side, decision year), ties averaged, on training and
  test rows alike; t: the training target's percentile within (side, decision year).
- z: f standardized by the training rows' mean and SD; a missing value (no id, no data)
  takes the training mean (z = 0). The slope is fitted on training rows WITH a resolved id
  only, so a missing id (bug B4 on the vm frame) never enters a fit.
- OLS of t on [1, u, z] on those training rows; the test score is b_u u + b_z z. A
  constant column gives b_z = 0 and the score orders exactly as consensus (test pin).
- The joint arm `x2_all` uses every column at once in the same regression.

The reading of a column on a frame is efv_v2_stat.paired_delta, statistic "within" (the
size-weighted mean over (side, year) groups of at least 20 rows of each rater's own
Spearman rho against the outcome), the column's score minus PROSPX consensus, E_cond
(scores fixed, players resampled), paired and player-clustered, B 2000, seed 20261019,
on both sides together and on each side. Coverage receipts (rows with a value, rows with
a non-zero value, by frame, side and year) sit beside every reading.

## 5. The rule (descriptive; it routes inputs to X3 and ships nothing)

- CARRY: point delta above zero on lv_dev AND on vm_dev (both sides together) and the
  lv_dev CI95 lower bound above zero.
- LEAN: point delta above zero on both frames, an interval that includes zero.
- NULL: anything else.

EFV_X3_POOLED_MODEL receives every column with its reading; the reading orders nothing on
the board. Forking paths: 15 columns plus the joint arm on 2 frames is 32 readings, so
about 1.6 intervals excluding zero are expected by chance alone; no correction is applied
because nothing is adjudicated. No served artifact, flag, grade, copy or progress-ledger
row changes under any outcome; a flip of anything served would need a separate registered
rule and an owner answer.

## 6. Bans

No statistic, count or stratum by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`); the
only groups are side and year. No reserved frame read, not even as a smoke test. No
projections retrain, no `backtest.run_backtest`. Fetches only into
`.cache/efv_x2_revealed/`. No paid or login-walled source.

## 7. Results

Empty at registration. The results are written to
`docs/efv-v2/EFV_X2_REVEALED_PREFERENCE_RESULTS.md` after the read.

## 8. Amendment A1 (2026-10-15, before any number of this task)

Two source facts found by the source check (`python efv_x2_revealed.py --check`, receipts
only, no frame, label or statistic read), each fixed here before the read:

1. The 2023 Rule 5 draft is absent from the league feed (one claim on the draft day). A
   December day is taken as the Rule 5 draft day only when it holds at least 20 CLW, R5
   and R5M transactions; a year without one uses 8 December as its draft day for
   eligibility and protection, and its selections are read from R5 and R5M codes only.
   Every other year from 2009 to 2025 is detected (2021: the minor league phase; the
   major league phase was cancelled).
2. The non-roster invitee endpoint returns an empty list for the 2026 season (all 30
   clubs, probed 2026-10-15; the files sit in `.cache/efv_x2_revealed/nri` as the
   receipt). The 2026 list is therefore the people with a spring-training invitation in
   the league feed inside `efv_w2_nri`'s dating range for 2026. No development read
   reaches 2026 (the development books stop at season 2024 and at 2025-01-01), so this
   changes no number in this task; it extends the column for later tasks.

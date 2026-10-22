# eABS v0: registration (EWAR_T4_EABS)

STATUS: REGISTERED, RESULTS EMPTY. Committed 2026-10-15 by queue task EWAR_T4_EABS (eWAR expansion plan T4 steps 2 and 3, owner decisions EW3-16 to EW3-20; EW3-19: "eABS = run the stability check, then the owner chooses eWAR entry"). This document fixes the per-challenge value, the challenge budget walk, the option-value model of a held challenge, the per-player quantities the /mlbstats/ board serves, the refusing invariants, and the one stability check with its frames, statistic, null comparators, power statement and dispositions, before the code that computes any of them exists and before any eABS number, per-player challenge value or persistence statistic has been computed.

What was read before it was written: the ledger's own published counts (docs/eabs-2026-10-15/ABS_LEDGER.md section 8 and commit 1ea7da21: rows, games and overturned counts by role and frame, the AAA coverage by season), the ledger's field list, and the RE288 table's structure (data/count_value.json, docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md). No run value of any challenge, no per-player count and no year-to-year or split-half figure was read.

eABS is a measurement: what a player's challenges of ball and strike calls were worth this season. It is served on /mlbstats/ as a descriptive board (display needs no gate, ewar-map plan T4 pass rule). It enters no WAR, no label, no fitted model, no priced number and no betting input. Whether a part built from it enters eWAR is the owner's decision after the stability check (section 7); this task does not admit it.

## 1. The value of one challenge

Frame: the ledger's zone challenges (`kind` zone), MLB 2026 regular season (data/_labs/abs_ledger/mlb_2026.json). A row is excluded, and counted, when it carries the `call_suspect` flag or when its original call does not fit its side (a batting-side challenge of a call other than a called strike `C`, a fielding-side challenge of a call other than a ball `B`).

- State before the pitch: balls_before, strikes_before, bases_before (three characters, a digit for an occupied base, so `1_3` is first and third; base bits as ebr.base_code: 1 first, 2 second, 4 third) and outs_before.
- The called-pitch value at that state is `count_value.called_pitch_value(t288, re24, balls, strikes, bits, outs)` on the row season's tables in data/count_value.json (`re288` and `re24`): the value after a ball minus the value after a strike, with ball four a forced walk and strike three an out on RE24 (0 at three outs). The table is monotone in the count (an invariant of count_value_v1), so the value is never negative.
- v_i, the value of the challenge if the call is overturned, signed for the challenger's club: v_i = the called-pitch value, for both sides. A batting-side overturn turns a strike into a ball (gain v_i to the offense); a fielding-side overturn turns a ball into a strike (v_i saved by the defense). This is "RV(state after the final ruling) minus RV(state after the original call)" of the plan, from the challenger's club's side.
- o_i = 1 when overturned, else 0. An overturned challenge gains v_i; an upheld one gains 0 and spends a challenge (section 2).

## 2. The challenge budget and the cost of a failed challenge

### 2.1 The budget walk

Per game and club, the ledger rows in game order (inning; top before bottom; at_bat_index; event_index): the club starts with 2 challenges; an upheld challenge spends one; an overturned one is kept; at the start of each inning from the 10th on, a club with none left receives one. k_before is the count the club held at the challenge. A row with k_before 0 is a budget violation: violations are counted and listed, and the build refuses when they exceed 1 percent of rows (the rule as written would then be wrong).

### 2.2 The constant (step 2, disclosed)

C0 = (the sum of v_i over every overturned challenge in the frame) / (the number of club-games in the frame) / 2: the run value a club drew per challenge it started a game with. It is computed once from the frame and printed in the payload.

### 2.3 The option-value model (step 3)

- Observation points: each club in each game, at the start of each half-inning that was played, in either half (batting or fielding). Half-inning index h = 2 x (inning - 1) + (0 top, 1 bottom) for innings 1 to 9; every extra-inning half shares h = 18.
- State at a point: k (0, 1 or 2, from the walk, with the extra-inning grant applied at the start of the 10th and later), and the club's score margin bucket m: -3 or worse, -2 to -1, 0, +1 to +2, +3 or better. Scores at a half-inning start come from the pbp corpus plays (`.cache/pbp_corpus/plays/2026`, `away_score`, `home_score` after the previous play of the game; 0-0 before the first). A game without corpus plays is left out of the fit and counted.
- Outcome at a point: F = the sum of v_i over the club's overturned challenges at or after that point in the game.
- V(h, k) = the mean F over the points in (h, k) (0 when the cell is empty); V(h, k, m) = (n x mean + K_OPT x V(h, k)) / (n + K_OPT) with K_OPT = 100 and n the points in (h, k, m).
- The option cost of a failed challenge in half h, with k_before challenges held and margin bucket m (from the row's bat_score_before and fld_score_before, on the challenger's club's side): dV(x) = V(x, k_before, m) - V(x, k_before - 1, m); c_i = max(0, (dV(h) + dV(min(h + 1, 18))) / 2), the mean of the marginal value at the start of the challenge's half-inning and at the start of the next one (the challenge falls inside the half, so the value still ahead lies between the two). At h = 18 c_i = max(0, dV(18)).
- Disclosed limits: the clubs holding fewer challenges at a point are partly the clubs that challenge more, so dV mixes the value of a challenge with club behaviour; the model is fit and applied on the same season (descriptive, in sample); it is runs, not wins.

The served eABS uses c_i from 2.3. The payload also carries each row's failed-challenge cost under C0, so the two can be read side by side (owner question EABS-Q2).

## 3. Per-player quantities (the served board)

Per player and role (batter, catcher, pitcher: the ledger's `role`; the one unresolved row is excluded from the boards and kept in the league figures):

- challenges n, overturned (won), lost, overturn rate (won / n);
- the mix cell of a challenge is (side, balls_before, strikes_before), side batting or fielding (catchers and pitchers share the fielding cells); p_cell is the league overturn rate of the cell in the frame, unshrunk; x_ovr = the mean p_cell over his challenges (the overturn rate the league reached on the same mix);
- runs gained = sum of o_i x v_i;
- failed-challenge cost = sum of (1 - o_i) x c_i;
- eABS raw = runs gained - failed-challenge cost;
- eABS = sum of (o_i - p_cell) x (v_i + c_i): eABS raw minus what the league's overturn rate on the same mix would have earned at the same values and costs. Zero is a league-average challenger for that mix.

Each club a player challenged for is listed; the row's club is the last one by date. Runs print to one decimal place; rates as percents.

Copy: descriptive, "this season, what happened". The board names eABS "runs above what the league's overturn rate on the same challenges earned". No sentence calls it a skill, a talent or a forecast unless section 5 records PERSISTS for that role; no forecast word appears on it.

## 4. Invariants (refuse the build)

1. Board counts reconcile with the ledger: per role, the sum of challenges and of overturned challenges over the board equals the ledger's count in the frame after the section 1 exclusions.
2. Per row, eABS raw equals runs gained minus failed-challenge cost to 1e-9 before rounding.
3. Per mix cell, the sum over its challenges of (o_i - p_cell) is 0 to 1e-9 (unshrunk cell rates).
4. Every v_i and every c_i is finite and not negative.
5. The budget walk's violations do not exceed 1 percent of rows (2.1).

## 5. The stability check (registered look)

Owner waiver EW3-5 applies to timing; this look runs once, after a dry run of the whole reporting path on fixtures with nulls, its stdout and stderr teed to the task's output directory.

### 5.1 Frames

Primary, AAA (sport id 11), zone challenges in data/_labs/abs_ledger/aaa.json, regular season, feeds with invariant_ok true, section 1's exclusions, seasons 2022 to 2026. Consecutive season pairs (2022-2023, 2023-2024, 2024-2025, 2025-2026); a player enters a pair with at least N_MIN = 8 challenges in each of its two seasons.

- Batters: batting-side challenges (role_by_side batter), the player is batter_id (only the batter challenges for the offense).
- Catchers: fielding-side challenges (role_by_side pitcher_or_catcher), the player is the catcher of record (catcher_id from the ledger's defense walk), in every season including 2026, for one rule across pairs. Pitcher-made challenges ride on the catcher of record (in 2026, where the challenger is named, catchers made 94 percent of AAA fielding-side challenges, ABS_LEDGER.md section 8): this frame measures the battery's challenge decisions through its catcher.

Values in the AAA frame: v_i on the MLB table of the same season (count_value.json; AAA's own run environment is not measured), cost C0 of 2.2 (the AAA budget rules differ by season, so the MLB option model is not transported); p_cell per AAA season, side and count.

### 5.2 Statistic

Per player and season, the decision skill per challenge s = mean over his challenges of (o_i - p_cell) x (v_i + C0), in runs. The persistence rho = the Spearman correlation of s(Y) with s(Y + 1) over all pair observations of the role pooled across the four pairs (a player in several pairs counts once per pair).

### 5.3 Inference, null comparators and power

- Bootstrap: B = 2,000 draws, seed 20261015, resampling players with replacement (a drawn player carries all his pair observations). lo95 = the 5th percentile; p = the share of draws with rho at or below 0 (one-sided).
- Holm over the two roles {batters, catchers}, k = 2, alpha 0.05 one-sided, on the bootstrap p.
- Permuted twin: within each season pair, the s(Y + 1) values are permuted across that pair's players (seed 20261016) and rho_twin, its bootstrap and its lo95 are computed the same way (seed 20261015). The twin fails when its lo95 is at or below 0.
- MDE95 = 1.645 x the bootstrap standard deviation of rho (one-sided), printed before rho.
- Planted recovery (seed 20261017, B_PLANT = 500 draws): on the real frame (the same players, seasons, challenges, cells and values), outcomes are simulated as Bernoulli(expit(logit(p_cell) + u_player)) with u_player drawn once per player from Normal(0, 0.5) and held across seasons; p_cell, s and rho are recomputed. Recovery passes when the planted lo95 is above 0. A null plant (u_player = 0 for everyone, seed 20261018) must give lo95 at or below 0.

### 5.4 Dispositions, per role (precedence top to bottom)

| Disposition | When |
|---|---|
| VOID | the twin's lo95 is above 0, the null plant's lo95 is above 0, or an exception after scoring began |
| UNDERPOWERED | the planted recovery fails (planted lo95 at or below 0): the frame cannot see an effect of that size, and nothing is read |
| PERSISTS | Holm-adjusted p below 0.05 and rho - rho_twin above MDE95 |
| SMALL | Holm-adjusted p below 0.05 and rho - rho_twin at or below MDE95 |
| NULL | otherwise: not distinguishable from zero at this MDE95 |

### 5.5 Reported beside, deciding nothing

- The same rho on the overturn-rate excess per challenge, mean (o_i - p_cell).
- MLB 2026 split-half: per player (batters by role batter, catchers by role catcher, the named challenger), challenges in game order alternate into two halves; players with at least 5 challenges in each half; the Spearman correlation of the two halves' s (runs, with c_i of 2.3) and its Spearman-Brown full-season value, with a player bootstrap (B = 2,000, seed 20261015).
- Counts: players and pair observations per pair and role.

### 5.6 What the look reads and writes

It reads the two ledger files and data/count_value.json, and writes data/_labs/eabs/stability.json (never shipped) and part 9 of this document. It reads no FV, grade, consensus field or prospect list (docs/PROSPECT_ANCHOR_GATE.md is not touched), no WAR series and no betting column.

## 6. What the result licenses

- PERSISTS for a role licenses one sentence of copy on the board: "challenge results carried from one AAA season to the next (Spearman rho X, frame)", and makes that role's part eligible for the owner's decision on the predictive eWAR. Every other disposition licenses no persistence or skill sentence.
- No disposition admits anything into eWAR: the owner chooses (section 7).

## 7. The eWAR part, designed for the owner and NOT admitted

Part 8 "ABS" of eWAR v3 (ewar-map plan T4 step 4), reattribution only, zero-sum per season:

- A catcher's or pitcher's overturned challenge moves v_i from the pitcher's runs allowed to the challenger (the replica's framing convention, fwar_frame.framing_charge_per9).
- A failed challenge's option cost c_i is charged to the challenger and credited back across the league so the part sums to zero per season and side.
- A batter's own overturned challenge is already inside his batting runs (the walk or the extra pitch happened) and is not added again; his part is his failed-challenge cost only, re-centred.

The owner question (OWNER_QUESTION.md in the task's output, EABS-Q1 and EABS-Q2) carries section 5's numbers and the options; nothing in this task writes the part.

## 8. Registry and glossary

Registry row `eabs`: verdict provisional, provisional_kind measurement_only, eval_artifact data/eabs_leaderboards.json. Glossary entry `eabs`. Flag eabs_export.MLBSTATS_EABS_LIVE, True once its tests pass (display needs no gate).

## 9. Results

EMPTY AT REGISTRATION. Nothing above this line changes once an entry is written here, except a dated amendment.

### 9.1 The stability check (2026-10-15)

Run once by tools/eabs_stability.py, the code committed with this entry and run unchanged, after its dry run on fixtures with nulls passed; stdout and stderr were teed to the task's output directory before anything else ran. Output: data/_labs/eabs/stability.json (never shipped). Not a registered-date look, so no owner waiver was needed.

AAA frame: 34,656 zone challenges after the part 1 exclusions (353 call/side mismatches, 9 call_suspect, 152 check-swing rows left out); batters 17,025 rows, catchers of record 17,631. C0 = 0.1073 runs (MLB 2026).

| Role | Pair observations (players) | MDE95 | rho | lo95 | p | p Holm | twin rho (lo95) | planted rho (lo95) | null plant rho (lo95) | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|
| Batters | 259 (187): 2023-24 64, 2024-25 100, 2025-26 95 | 0.1069 | 0.0300 | -0.0757 | 0.334 | 0.334 | -0.0807 (-0.1919) | 0.3305 (0.2210) | -0.0248 (-0.1305) | NULL |
| Catchers | 220 (129): 2022-23 6, 2023-24 65, 2024-25 73, 2025-26 76 | 0.1198 | 0.1215 | -0.0027 | 0.0535 | 0.107 | -0.0664 (-0.1812) | 0.4887 (0.3655) | 0.0014 (-0.1115) | NULL |

Both twins and both null plants fail and both planted recoveries pass, so the frame could see an effect of the planted size; neither role's challenge decision skill is distinguishable from zero at these MDE95s. The batter 2022-2023 pair has no player with 8 challenges in both seasons.

Reported beside, deciding nothing:

- Overturn-rate excess, the same rho: batters 0.0967 (lo95 -0.0097), catchers 0.1206 (lo95 0.0009, unadjusted).
- MLB 2026 split-half (option-value costs): batters 182 players, rho 0.0195 (lo95 -0.1013), Spearman-Brown 0.0382; catchers 91 players, rho -0.0676 (lo95 -0.2537), Spearman-Brown -0.1450.

What part 6 licenses: no persistence or skill sentence for either role. The board says that season-to-season persistence was not distinguishable from chance on AAA 2022 to 2026. Nothing enters eWAR; the owner question (EABS-Q1, EABS-Q2) carries these numbers.

### 9.2 2026-10-21: the owner's answer to EABS-Q1, the part enters eWAR by override (dated amendment)

- **Owner answer, verbatim** (2026-10-15, `DECISIONS_FOR_OWNER.md` EW3-32): "Into eWAR, do not
  disclose, this is the first year of ABS so it's impossible to tell, we have enough to put it in."
- **What it overrides.** The ewar-map plan's T4 pass rule admits the eWAR part only after a stability
  read clears its MDE95; part 9.1 read NULL for both roles (batters rho 0.0300, lo95 -0.0757;
  catchers rho 0.1215, lo95 -0.0027, Holm p 0.107). The owner admitted part 7's reattribution part into
  eWAR v3 anyway, from 2026, in both eWAR and eWAR realized. This entry records the override and the
  NULL read it overrides; nothing in parts 1 to 9.1 changes.
- **Where the part is defined and built.** `docs/ebr-2026-09-30/EBR_GATE.md` 11.10.2 (candidate part 8),
  built by task EWAR_V3_ASSEMBLE (`tools/build_ewar_v3.py`). It reads this document's frame, values and
  option costs through `eabs_export.frame`, unchanged.
- **Copy.** Per the owner, the site carries no stability caveat and no "validated" claim for eABS or for
  the part: it describes plainly what each measures. The board's derived persistence line (part 6) is
  no longer printed; the `stability` block stays in the payload as the record.
- **Registry.** The `eabs` row stays provisional (`measurement_only`), never validated; its notes name
  this override and the NULL read.

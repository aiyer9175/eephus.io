# The pitch-level run value attribution ledger (pitch_ledger_v1)

Task EWAR_INNOVATE_LEDGER, item (a) (owner decisions EW3-16 to EW3-23, 2026-10-15; the ewar-map
plan's innovator item 1). This document is committed ALONE, with its pin test
`test_ewar_innovate_registration.py`, before the ledger's code exists and before any number of
its estimands is computed. It fixes the unit, the components, their owners, the three models the
components read, the refusing invariants and the outputs. A change after the first number is a
dated note in part 9 that says what changed and why, never an edit above it.

STATUS: REGISTERED, RESULTS EMPTY.

## 0. What it is

- **One question, asked of every pitch:** who moved the run expectancy on this pitch, and by how
  much. The ledger splits each step's run value into named components that sum to it exactly,
  and gives each component one owner on the batting side and one on the fielding side.
- **A measurement substrate.** It forecasts nothing, admits nothing and serves nothing. eWAR v3
  parts, catcher value 2.0 (`docs/ewar/CATCHER_VALUE_2_GATE.md`) and swing-decision value
  (`docs/ewar/SWING_DECISION_GATE.md`) read it under their own registrations. No page, exporter,
  registry row or glossary entry reads it while this document stands alone.
- **Zero-sum per pitch.** On every step, the batting side's credits sum to the step's run value
  and the fielding side's credits sum to minus it, so the two sides net to zero exactly. The
  umpire's miss is a named component with its own neutral owner, so no run is created or lost.
- **Never a forecast word on its numbers.** The ledger describes one season's pitches.

## 1. Data (read from caches; this task fetches nothing for the ledger)

- **The corpus:** `.cache/pbp_corpus` pitches, plays and events for 2018, 2019 and 2021 to 2026
  (MLB regular season), and eBR's runner record `.cache/pbp_runners` (states, end states, launch
  speed, spray coordinates, trajectory).
- **RE288 and RE24:** `data/count_value.json` (`count_value_v1`), its season tables, and
  `count_value.walk_play`, `state_value` and `called_pitch_value`, by reference. The ledger's
  steps are exactly the count walk's steps.
- **The feed extract:** one pass over the cached MLB game feeds the corpus was built from
  (`.cache/win_prob/<game_pk>.json`, read only), writing per playEvent the defense alignment
  (pitcher, catcher and the seven fielders), the home-plate umpire, the play's batted-ball data
  (launch speed, launch angle, total distance, hit coordinates) and the play's first credited
  fielder, to `.cache/ewar_innovate_ledger/feed_extract/<season>.parquet`. A pitch is joined by
  `play_id` (the feed's `playId`); a non-pitch event by game, at-bat index and event index.
- **The ABS challenge ledger** for 2026 (`data/_labs/abs_ledger/mlb_2026.json`, EWAR_T4_ABS_LEDGER):
  the original and final call of every challenged pitch and the challenger's role. Before 2026
  the original call is the final call.

## 2. The unit and its run value

- **Step:** one step of `count_value.walk_play` over a fit-set or non-fit-set play: a pitch or a
  non-pitch event (pickoff, steal, wild pitch, passed ball, balk, automatic ball or strike,
  substitution with no state change). Steps after the half-inning's third out carry 0.
- **Run value, batting side positive:** dRE = state_value(after) - state_value(before) + runs
  scored at the step, on the season's RE288 and RE24 tables (`count_value.event_values`). The
  steps of a play telescope to its RE24 change (count_value invariant 3).

## 3. The components (each sums with the others to dRE exactly)

Notation at a pitch: V(.) the state value after a call at the pre-pitch state, v =
`called_pitch_value` (value after a ball minus value after a strike, at least 0 when the table is
monotone); z the rulebook call; s0 the call the umpire made; s1 the call that stood (s1 = s0
unless a 2026 challenge overturned it); for a call, 1 means strike.

**3.1 A called pitch** (call codes `C`, `B`, `*B`; pitchouts `P`, intentional balls `I`, automatic
calls and hit batters are not called pitches):

```
x_duel = V(z)  - V(before)                     the pitch's value under the rulebook call
x_bcs  = - d_b * v                             the batter's called-strike effect
x_pcs  = - d_p * v                             the pitcher's called-strike effect
x_frm  = - d_c * v                             the catcher's framing
x_ump  = - (s0 - z - d_c - d_p - d_b) * v      the umpire's miss, net of the three effects
x_ch   = V(s1) - V(s0)                         the challenge (0 when none or the call stood)
x_oth  = dRE - (V(s1) - V(before))             other movement recorded at the pitch's index
```

`d_c`, `d_p` and `d_b` are the catcher's, pitcher's and batter's shares of the strike probability
the called-strike model of part 4 adds above the league model at this pitch. They sum, with the
umpire's share, to p_full - p0 (part 4.3).

**3.2 A pitch with a swing, a hit batter, a pitchout or an intentional ball** (every other pitch
code): x_duel = dRE when the pitch is not put in play; when it is put in play (codes `X`, `D`,
`E`), x_x = the expected value of the batted ball (part 5.1) and x_fld = dRE - x_x.

**3.3 Blocking** (every pitch thrown with a runner on base and the count not ended): x_bexp = +e
and x_babs = -e, e = the pitch's expected wild-pitch and passed-ball cost (part 5.2). The pair
sums to 0 at the pitch. **A wild pitch or passed ball event:** x_blk = dRE of the event.

**3.4 Steals** (stolen base, caught stealing and pickoff caught stealing events, defensive
indifference): x_sexp = e_s, the season's mean dRE of that event family from that base-out state
(part 5.3), and x_sres = dRE - e_s. **Pickoffs, pickoff errors and balks:** x_pk = dRE.

**3.5 Any other non-pitch event** (an error on a throw, an appeal, an advance on no pitch):
x_oth = dRE.

## 4. The called-strike model

**4.1 The league model p0,** per season, fitted on that season's called pitches (on s1, the call
that stood: in 2026 the framing a challenge undid does not count, which is what "framing net of
challenge exposure" means here):

- Coordinates: xm = plate_x, mirrored (times -1) for a left-handed batter; zn = (plate_z - sz_bot)
  / (sz_top - sz_bot), the feed's own zone edges, so batter height enters through the zone.
- Keys: the batter's and pitcher's hands (four combinations) and four count groups: {3-0, 3-1},
  {0-2, 1-2, 2-2}, {3-2}, every other count.
- Grid: xm in 0.1 ft bins over -2.0 to 2.0, zn in 0.05 bins over -0.75 to 1.75, values outside
  clipped to the edge bin. Counts n and strikes k per cell are smoothed by a Gaussian kernel of 1.5
  bins on each axis, separately per key; p0 = (k~ + 20 * q) / (n~ + 20), q the same smoothed rate
  of the hand combination over all count groups; then one logit shift per season so that the sum
  of p0 equals the season's called strikes exactly.

**4.2 The person effects.** logit P(strike) = logit p0 + a_c + a_p + a_b + a_u, with a ridge
penalty a_g^2 / (2 sigma_g^2) per person, fitted per season by L-BFGS on the season's called
pitches. Each group's effects are re-centred to a pitch-weighted mean of 0 per season (the shift
enters the intercept, which then re-solves the calibration of 4.1). The four sigma_g are chosen
ONCE on the 2018 season from {0.05, 0.10, 0.15, 0.20, 0.30}, each group in turn holding the others
at 0.15, by the held-out log-likelihood of even-numbered games given a fit on odd-numbered games
(game_pk parity), then frozen in `pitch_ledger.py` for every season and never re-chosen.

**4.3 The per-pitch shares.** With L0 = logit p0, L = L0 + a_c + a_p + a_b + a_u, p_full =
expit(L) and the secant slope m = (p_full - p0) / (L - L0) (m = p0 (1 - p0) when L = L0): d_g =
m * a_g for g in {c, p, b, u}, so the four shares sum to p_full - p0 exactly and each has its
effect's sign. The umpire's share stays inside x_ump.

## 5. The cell models (each fitted per season on that season's steps)

**5.1 The batted ball's expected value x_x.** Contact cell: launch speed in 5 mph bins (under 60
and 115 or more pooled), launch angle in 6 degree bins (under -30 and 60 or more pooled), spray
angle atan2(hc_x - 125.42, 198.27 - hc_y) in 15 degree bins over -45 to 45 (outside pooled). A
ball without launch speed or angle falls back to (trajectory, hit location). x_x = m_bo +
r_contact + i_(contact,bo) * n / (n + 30): m_bo the season's mean dRE of balls in play from that
base-out state, r_contact the contact cell's mean of (dRE - m_bo), i the cell-by-state mean of
the remainder, n its count. x_x is then shifted by one constant per season so that x_fld sums to
0 over the season.

**5.2 The blocking expectation e.** f = the share of pitches followed, in the same plate
appearance before the next pitch, by a wild-pitch or passed-ball event, per cell of (zn in 0.25
bins with zn under -0.25 pooled, |xm| in 0.5 ft bins, pitch group FB, BR, OS or other, the base
code); c = the season's mean dRE of wild-pitch and passed-ball events by base-out state; e = f * c
times one constant per season so that the season's e sums to the season's wild-pitch and
passed-ball dRE exactly. Pitch groups: FB = {FF, FA, SI, FT, FC}, BR = {SL, ST, SV, CU, KC, CS},
OS = {CH, FS, FO, SC, KN, EP}, other = everything else and missing.

**5.3 The steal expectation e_s,** the season's mean dRE by (event family: second, third, home;
the base code; outs), so x_sres sums to 0 per season and cell.

## 6. Owners (batting side owner, fielding side owner)

| Component | Batting side | Fielding side |
|---|---|---|
| x_duel | batter | pitcher |
| x_bcs | batter | context (fielding) |
| x_pcs | context (batting) | pitcher |
| x_frm | context (batting) | catcher, framing |
| x_ump | umpire | umpire |
| x_ch | the batter if his side challenged, else context (batting) | the challenging catcher or pitcher if the fielding side challenged, else context (fielding) |
| x_oth | runners | fielders, unassigned |
| x_x | batter | pitcher |
| x_fld | batter | the play's first credited fielder (fielders, unassigned when none) |
| x_bexp | context (batting) | pitcher |
| x_babs | context (batting) | catcher, blocking |
| x_blk | runners | catcher, blocking |
| x_sexp | runners | pitcher |
| x_sres | runners | catcher, throwing |
| x_pk | runners | pitcher |

A batting-side owner is credited +x and a fielding-side owner -x; the umpire row carries x once,
as the runs his misses moved toward the batting side. "Context" rows are the runs a side bore
that no player on it caused; they are kept so each side's ledger closes. The catcher is the
defense alignment's catcher at the step; a step whose catcher is unknown credits "catcher,
unknown" and is counted.

- **Runners are owners only of non-pitch movement** in this version. Their extra bases on a ball
  in play stay inside x_fld's batting-side owner (the batter) and are eBR's to measure; this is a
  disclosed scope limit, not a convention any part relies on.
- **The hitter's own successful challenge is his** (x_ch to the batter), as eABS v0 records it;
  this ledger carries no option cost of a failed challenge (that is eABS's, `docs/eabs-2026-10-15/
  EABS_GATE.md`), so x_ch is 0 on a failed challenge.

## 7. Invariants (each refuses the season's build)

- **I1, the identity:** on every step, the components sum to dRE within 1e-9 runs; the batting
  side's credits sum to dRE and the fielding side's to -dRE.
- **I2, the telescope:** on at least 99.9 percent of the season's fit-set plays the steps sum to
  the play's RE24 change within 1e-6 (count_value's invariant, re-checked on the ledger).
- **I3, the season sums:** x_fld, x_babs + x_blk (blocking net) and x_sres each sum to 0 over the
  season within 1e-6 runs; the sum of p0 over called pitches equals the called strikes within 0.5
  strikes.
- **I4, the join:** at least 99.5 percent of the season's corpus pitches find their feed row and
  catcher, and at least 99 percent of called pitches carry plate_x, plate_z, sz_top and sz_bot.
- **I5, the planted recovery and the null comparator** (on a synthetic fixture, and once on a
  simulated copy of the 2018 season whose calls are drawn from p0 with the plants below): with
  true catcher effects drawn with sd 0.15 logit and one catcher planted at +0.30 on 3,000 called
  pitches, the planted catcher's fitted effect lies between 0.20 and 0.40 and the Pearson r of
  fitted with true catcher effects is at least 0.5; with every true effect 0 (the null
  comparator), the sd of the fitted catcher effects is below one third of their sd in the
  planted run. Both run before any real season is fitted.
- **I6, the 2026 calls:** every 2026 challenged pitch of the ABS ledger is found, with s1 equal
  to the corpus call code.

## 8. Outputs

- `pitch_ledger.py` (pure: the components, the models, the shares, the frozen sigma values),
  `tools/build_pitch_ledger.py` (the run), `tools/extract_feed_fielders.py` (the feed extract),
  `test_pitch_ledger.py`.
- `.cache/ewar_innovate_ledger/ledger/<season>.parquet`: one row per step and component with its
  owners and value (gitignored, never served).
- `data/_labs/ewar_innovate/pitch_ledger_receipts.json` (tracked, never shipped: `data/_labs/`
  is in neither deploy consumer): the invariants, counts, the frozen sigma choice with its
  held-out log-likelihoods, the per-season league sums of each component, and descriptive
  agreement read beside it (part 8.1). No player value is written to a tracked file.

**8.1 Descriptive agreement (reported, never a gate):** per season at 2,000 or more called pitches
caught, Pearson r of the ledger's framing runs with FanGraphs' framing (`saber_feed` frm) and of
its blocking runs with Savant's catcher blocking runs where cached (2026); per season, the sd of
each component's player totals. These are same-season numbers only; no year-to-year, split-half
or forward statistic of any ledger total is computed under this document.

## 9. Results and dated notes

EMPTY.

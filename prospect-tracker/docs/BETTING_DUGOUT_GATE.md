# Sports Betting: the club-policy pricer gate (pre-registered 2026-09-23)

The long form of docs/diamond-betting.md section 5l. Written in the shape of
docs/PROJ_PATH_SHAPE_GATE.md: the honesty clause first, then the read ledger, the
candidate census, the frame, the halves, the decision rule, the power precondition, the
family, the flag, the clock, the stop rule and the open questions. Every threshold here
is the one 5l carries, in the same words; test_betting_mgmt_policy_registration.py pins
the two documents to each other and to the plan's 5.1 calendar. Plain ASCII, no em or
en dash.

Two things sit beside each other on /betting/ and this document keeps them apart:

- The Dugout context block (Layer 1 of the D4 spec): a collapsed "Dugout context, not
  priced" details on every game card and both slot cards, read from the tracked
  data/management_board.json by betting_dugout.py through one seam in
  betting_export.build, rendered by assets/betting.js. It shows the served descriptive
  board's club-season figures beside a price and reads into none of it. It is not a
  candidate, not a column and not a look. test_betting_mgmt_fence.py asserts that no
  pricer module imports a management module or reads the board, and that the block is
  the last key added to the payload and is passed to nothing.
- The registration below (Layer 2): two DATED club-policy columns that do not exist
  tonight, built by the betting lane from the game feeds, registered as one Holm family
  with a first look no earlier than 2027-07-01. No builder, no column, no flag and no
  number exists at the time of this writing.

--------------------------------------------------------------------------------------
## G-0. Honesty clause, first
--------------------------------------------------------------------------------------

No candidate was scored to write this registration. Nothing was fitted, no column was
built, no dated value exists. Everything read during design, and what each read is:

- data/management_board.json (generated 2026-09-24T03:04Z, corpus built
  2026-09-06T07:04Z, 2026 rows through 2026-09-04): the season-to-date club-season rows
  (counts, per-game rates, z_hook through z_visit, mwpa_<family>) and the league
  hook_pitch_count {median 89, p10 64, p90 102, n 37,964}. These are the served
  descriptive board. None of them was related to any game outcome or any price.
- data/betting_model_eval.json vintage block: brier 0.24269, log_loss 0.6784,
  n_graded 705, split_date 2026-08-01, fit_window 305 games 2026-07-06 to 2026-07-31.
  The SERVED model's own eval, read for the power floor in section 6 only.
- docs/IN_GAME_MANAGEMENT_GATE.md (frozen 2026-09-06): the steal family's split-half
  0.1085 inside its null band. A management gate on a management quantity; it relates
  nothing to a betting outcome.
- docs/diamond-betting.md 5c, 5d (the 5d column table and 5d-E), 5f (the sentence
  "nothing the management module measures may be read into this gate"), 5g, 5j, 5k;
  the plan's 5.1 calendar and its stop items X1 to X11.
- Layer 1 renders board values beside prices. A render is not a measurement: no Layer
  1 code, test or fixture relates a management value to a result or to an edge, and
  the fence tests keep it so. Layer 1 shipping before this document is committed does
  not constitute a look.

Looking early disqualifies. 5c rule 1 verbatim in force: "Each candidate gets its own
gate section in this document before any number is computed on it ... A candidate
measured before its section exists is disqualified, whatever it measured." Each
registered column has exactly one look per season, on the date fixed in section 9. A
number computed on a registered column against a game outcome before that date voids
the column for this registration, and it may return only as a new registration that
discloses the early read.

Stop rule. If the builder's parity fixture (section 4) fails, no look is taken. If the
power precondition (section 6) is not on disk, no criterion may be read.

--------------------------------------------------------------------------------------
## 1. The candidate census: lawful ex-ante, already registered elsewhere, or leaks
--------------------------------------------------------------------------------------

| quantity, as the owner or the plan names it | class | ruling |
|---|---|---|
| the club's season-to-date Hook z, Pen z (board z_hook, z_pen) | pregame-knowable POLICY, but in a CONTAMINATED form: the board standardizes across the season's thirty club-seasons through the corpus rebuild date, so a vintage dated 2026-06-01 would read a value that includes July games; and the board moves only when the corpus is rebuilt by hand | NOT the registered form. The registered form is the dated trailing-30-day rate below, built strictly before the vintage date, standardized by the one seam (_assemble_team_inputs) like every other column |
| pitching changes per game (pen_per_game) | pregame-knowable policy | REGISTERED as 5l-A `mg_pen_per_game_l30` |
| starter pitch count at removal (hook_median_pitches) | pregame-knowable policy | REGISTERED as 5l-B `mg_hook_pitches_l30` |
| bullpen usage over the last 3 days | ALREADY REGISTERED: 5d `pen_ip_l3` (bullpen outs over the three prior days), with `pen_b2b_arms`, `pen_arms_avail`, `pen_plus_avail`, look 2026-10-07 | NOT registered here. A management-corpus version is a close variant of a registered column; 5d owns it, and a second registration of the same quantity would be the double look rule 1 forbids |
| bench moves per game (bench_per_game, Bench z) | pregame-knowable policy, but a CLOSE VARIANT of 5f `ph_share` (pinch-hit PA over relief PA), embargoed to the end of the 2027 regular season; 5f states "nothing the management module measures may be read into this gate" | NOT registered. Deferred until 5f's first look is recorded; a later registration must disclose 5f's read |
| intentional walks per game (ibb_per_game, IBB z) | pregame-knowable policy with NO predicted sign and no priceable mechanism named (a frequency with no good direction) | NOT ASKED (owner decision 2026-09-23). Named so it is not reopened by taste; a registration would need its own section and its own family |
| mound visits per game (visit_per_game, Visit z) | counted only in the module (plan M-PIT-8); capped by rule; nothing priceable pregame | NOT a candidate |
| realized mwpa_<family>, same game | the game's own outcome | LEAKS THE OUTCOME. Never a candidate |
| realized mwpa_<family>, trailing window or season to date | a club "decision quality" series: exactly the rank docs/IN_GAME_MANAGEMENT_GATE.md withheld (bounded null on the one family gated; every other family "not run"); a pricer that reads it asserts the skill claim the page refuses | NEVER a candidate, in any window, under any label. Stated so that "but it is lagged" is not an argument |
| DVS, best, worst, per-decision ledger rows, window plays, wp_before / wp_after | post-game by construction | NEVER a candidate |
| steal DV / ER / realized_delta, bunt dv_cell | the running-game model's priced decision values; the steal family's gate returned a bounded null | NOT a candidate |
| defensive-sub timing by lead state | nothing priceable pregame; 5g team_fld_runs (2027) owns fielding | NOT a candidate |
| challenges, lineups, ejections | dark or counted; lineups are 5j's (schema 6) | NOT a candidate |

Two candidates survive. Both are moneyline-calibration estimands in the 5d-E form.

--------------------------------------------------------------------------------------
## 2. The registered columns (5l-A, 5l-B)
--------------------------------------------------------------------------------------

Written before the schema bump exists in code and before any value of either column
has been related to any game outcome. Nothing served reads them and nothing served
changes.

**Why this is a gap and not a double count.** The served model's run prevention is
`z_prev`, a blend of the probable's SEM+ and the club's `bullpen_plus` weighted by the
STARTER's own innings share, w = ip_per_gs / 9 (game_prevention_z). That share is a
fact about the pitcher. How quickly THIS club goes to its bullpen, independent of who
starts, is a fact about the dugout: two clubs with the same probable and the same
bullpen_plus can hand the game to the pen at different points. The candidate asks
whether the club's policy carries information the starter's share and his third-time-
through exposure (5d-E `sp_tto3_bf`) do not. It is a gap only if it beats those two
neighbours, which is why the twin and a variance-inflation read are part of the result.
"A candidate that only reproduces the innings share has found nothing" (5d-E).

**Source.** .cache/game_feeds/{game_pk}.json (the 2026 MLB feeds the 5d builders
already walk; the same source in 2027), read by a builder in betting_usage.py beside
`build_schema4_team_columns`, over the club's games dated STRICTLY BEFORE the vintage
date. Never the management board, never the corpus parquet, never a per-club decision
ledger file, never mgmt_*. The fence tests keep betting_usage free of management
imports.

**The numbers.**
- 5l-A `mg_pen_per_game_l30`: for club C on vintage date D, the count of pitching
  substitutions made by C as the fielding side over C's games in the 30 calendar days
  before D (dated strictly before D), divided by C's games in that window. Source
  event: liveData.plays.allPlays[].playEvents[] entries of type "action" whose
  details.eventType is "pitching_substitution" (the corpus's own event vocabulary).
  Fielding side from the half. Null when the window holds fewer than 10 club games.
  Units: changes per game, never an index.
- 5l-B `mg_hook_pitches_l30`: over the same window, the median pitch count at removal
  of C's FIRST pitcher in each game (liveData.boxscore.teams[side].pitchers[0], his
  players["ID<mlbam>"].stats.pitching.pitchesThrown, the per-arm workload field 5d
  already reads), across games in which he was removed (a complete game has no hook and
  is excluded, the count published in the basis). Null when fewer than 5 hooks in the
  window. Units: pitches. Openers are not separated; a separate opener-aware form is
  not asked.

**Standardization.** Each rides through `_assemble_team_inputs` as `<col>` and
`z_<col>` standardized over the clubs carrying a value on that vintage, None never
zero, exactly as every dark column does. The z is a betting-lane z over the slate's
clubs on the vintage date; it is NOT the board's z (thirty club-seasons, season to
date): two different quantities with the same name shape.

**Vintage safety.** The rule is 5d's (betting_usage.py: a game is skipped when
`d >= on_date`): the window holds C's games dated STRICTLY BEFORE D whose cached feed
is complete (gameData.status.abstractGameState "Final" and liveData.plays.allPlays
present); an incomplete or missing feed is excluded with the count stated in the
basis. The cached feed carries NO fetch time (top keys copyright, gameData, gamePk,
link, liveData, metaData; metaData holds gameEvents, logicalEvents, timeStamp, wait),
so the basis records, per club, the latest `metaData.timeStamp` among the feeds read
(the feed's own last-update stamp, e.g. "20260803_172707") and names it as such; a
stamp later than the vintage night is visible in the basis and is a disclosure, not an
exclusion rule. Old records return None; `inputs_as_of` never fills the column from
live files or from the board. First-write-wins: the column lands on the NEXT vintage
night after the builder ships.

**Candidate terms.** Two additive terms on run prevention, fitted by the same
`fit_coefficients` path on the vintage fit window, computed by a function nothing
served calls:
  runs_S = b0 + b1 z_off_S + b2 z_prev_O + b3 park + b4 home + b7 z_mgpen_O   (5l-A)
  runs_S = b0 + b1 z_off_S + b2 z_prev_O + b3 park + b4 home + b8 z_mghook_O  (5l-B)
Each member is tested ALONE (one test each); the pair together is a reported
diagnostic, not a third test. No sign is predicted for either coefficient (a quick
hook can mean weak starters, already in z_prev, or aggressive leverage relief), so the
5g sign criterion does not apply and the twin plus the VIF read are the controls, in
the 5d-E form. The sign is REPORTED.

**Not asked, each needing its own section.** An opener-aware hook form; the club's
first-reliever LI policy (needs LI, which is post-game in the feed); the season-to-date
form; any interaction with the probable's ip_per_gs; a total or runline estimand; a
bench or intentional-walk rate (section 1).

--------------------------------------------------------------------------------------
## 3. Code that lands AFTER this document, and before Opening Day 2027
--------------------------------------------------------------------------------------

None of it exists tonight, and the registration test asserts that no non-test module
at the repo root or under tools/ contains "mg_pen_" or "mg_hook_" until the "Builder
landed" amendment is in 5l.

- leaderboard_vintages.py: `SCHEMA7_TEAM_COLUMNS = ("mg_pen_per_game_l30",
  "mg_hook_pitches_l30")` appended to TEAM_COLUMNS in order; SCHEMA bumped to the
  number after 5j's. Schema 6 is 5j's (posted lineups, "to be built"). If 5j's bump has
  not landed when this builder is ready, this builder WAITS (its look is 2027 either
  way; a January 2027 landing leaves eleven weeks of accrual before Opening Day and
  the window floor makes April null regardless). No renumbering of 5j.
- betting_usage.py: `build_schema7_team_columns(*, on_date, feed_dir=None, games=None)
  -> dict[org, {mg_pen_per_game_l30, mg_hook_pitches_l30, basis}]`, in the
  `build_schema4_team_columns` idiom (feeds dated strictly before on_date; the
  `_days_before` helper), on the nightly 9e-pre path inside its own try/except so a
  failure costs its two columns a stated null and never the snapshot.
- betting_model.py: `DARK7_TEAM_COLUMNS = ("mg_pen_per_game_l30",
  "mg_hook_pitches_l30")`, added to DARK_TEAM_COLUMNS_BY_SCHEMA and DARK_TEAM_COLUMNS;
  `SERVE_MGMT_POLICY = False` in the SERVE_RUN_DISPERSION idiom, with the comment "TO
  FLIP THIS FLAG: the 5l look must return PASS on a member, the contaminated screen
  must have run without disqualifying, MODEL_VERSION bumps to betting_runs_v3 (or the
  next), --context re-runs, the tripwire in test_betting_mgmt_policy.py and the
  persisted `mgmt_policy_gate` block in betting_model_eval.json change in the same
  commit. The four move together or not at all." No served number moves before the
  flip.
- test_leaderboard_vintages.py: `bm.DARK7_TEAM_COLUMNS == lv.SCHEMA7_TEAM_COLUMNS` and
  the BY_SCHEMA key 7 (replacing test_betting_mgmt_fence.py's no-column assertion,
  which is deleted in the same commit).
- test_schema7_builders.py (NEW): strictly-before rule, the 10-game and 5-hook null
  floors, complete games excluded and counted, incomplete feeds excluded and counted,
  the parity fixture, basis records the latest metaData.timeStamp under that name, and
  a clock test that the schema-7 clock does not open before 2027-07-01, in the
  test_betting_usage idiom.
- test_betting_mgmt_policy.py (NEW): the flag is off at HEAD; no served path reads a
  schema-7 column (expected_runs, game_prevention_z, the slot chooser and record rows
  never reference an mg_ column, by AST and by string); the registration predates the
  builder (the 5l heading's pre-registered date is earlier than the first git commit
  touching SCHEMA7_TEAM_COLUMNS; skips when git is unavailable).
- docs/diamond-betting.md 5l gains "### Builder landed YYYY-MM-DD" naming the first
  vintage night carrying the columns (the X9 same-day amendment).

--------------------------------------------------------------------------------------
## 4. The parity fixture (buildable now, no look)
--------------------------------------------------------------------------------------

On one 2025 game and one 2026 game, the builder's per-game pitching-substitution count
and first-pitcher pitch count at removal must equal the management corpus's (the
decision ledger's events.event_type "pitching_substitution" and starter_hook
pitch_count). The comparison lives in test_schema7_builders.py, which may import the
ledger module as a TEST (the fence forbids pricer modules importing it, not tests).
Comparing two derivations of a count on two games relates nothing to an outcome. If the
fixture fails, no look is taken.

--------------------------------------------------------------------------------------
## 5. Label, frame, halves, decision rule
--------------------------------------------------------------------------------------

**Estimand.** Does adding the club-policy term improve moneyline calibration on the
vintage eval half. The label is the moneyline result (home club wins, 0/1, the served
model's own objective). The score is the paired per-game Brier of p_home against the
served model on the same games; log loss is criterion 2. Regular-season games only;
postseason vintages accrue toward the clock and are not graded. A game enters the pair
only when BOTH clubs carry a populated dated value on that vintage (otherwise excluded
and counted).

**Split.** The existing vintage fit / eval split, 2027 form: the fit window is the
VINTAGE_FIT_TARGET_GAMES (300) games immediately preceding the eval half, on which
`fit_coefficients` fits b0..b4 and the candidate coefficient jointly; the eval half is
every later graded game with a populated value. The 305 games of the 2026 fit window
(2026-07-06 to 2026-07-31) stay ungraded in every mode of every artifact this gate
writes; they are the fit half, named in the eval as fit_window.why_not_graded, and
grading them would open the 600-game gate on in-sample data
(test_min_edge_cannot_be_set_from_the_contaminated_mode). The 2027 look never reads a
2026 game as evidence.

**Decision rule, per member, ALL required.**
1. Paired Brier improvement at one-sided t >= 1.645, and under the family adjustment
   of section 7 the smaller of the two members' p-values must clear alpha / 2 = 0.025
   (Holm, m = 2).
2. Paired log loss not worse on the point estimate.
3. The 5c rule 3 permuted twin: the same fit with the column permuted across clubs
   within each date; the candidate's improvement exceeds the 95th percentile of 200
   twin improvements (the 5f form).
4. At least VINTAGE_MIN_GRADED_GAMES (600) eval-half games with a populated value on
   both clubs, with the 300-game fit window in front of them.
5. The VIF read: the candidate's z against z_prev, z_off, and the neighbours
   ip_per_gs / sp_tto3_bf (as dark columns). A VIF above 5 against the innings share
   fails the member as "reproduces the innings share", whatever (1) and (2) read.
Report whichever way it lands: the coefficient and its sign, the twin distribution,
the VIF table, the pair's joint fit as a diagnostic, coverage per club, the count of
complete games excluded from 5l-B, and the contaminated screen's reading.

**Outcomes.** PASS, FAIL and INDETERMINATE are final for this registration.
UNDERPOWERED and NOT READ wait for the 2028 look. A PASS serves nothing until the
contaminated screen has run without disqualifying (5c rule 4) and the flip commit of
section 8 lands.

**Contaminated screen (5c rule 4's first serve leg, in the 5c-A form as corrected
2026-09-11).** It runs ONCE, AFTER the 2027 look, only on a member that passed
criteria 1-5, on the 2027 season-to-date form of the same rate (the club's pitching
changes per game, or its starter pitch count at removal, over the 2027 regular season
through the look date, built by the betting lane from the feeds; never the board's
z_pen or z_hook, which are standardized across thirty club-seasons and move only when
the corpus is rebuilt by hand), labelled contaminated, and it can only DISQUALIFY. It
is graded in the 5c-A fit-and-grade form on backtest()'s own split of the 2027
completed regular-season dates, and it disqualifies when the paired Brier delta
(served model minus candidate) on the held-out dates is <= 0 on the point estimate;
the 5c-A sign criterion does not apply because no sign is predicted. A contaminated
positive qualifies nothing. No look of any 2026 form exists, contaminated or not, and
no contaminated number exists for a member that did not pass (5c-A: "a column that did
not pass has no serve to block"). It is not the look, it reads no dated column, and it
is taken on a calendar date after the look's, never the same one. This paragraph is
the 5c-A form; the older 5g wording of a contaminated screen on the registration
season's outcomes, which the 2026-09-11 correction superseded for 5j, is not inherited
here.

--------------------------------------------------------------------------------------
## 6. MDE and the power precondition (computed BEFORE the eval read, on the fit half only)
--------------------------------------------------------------------------------------

At n = 600 paired eval-half games, one-sided alpha 0.025 (the Holm-adjusted level for
the harder member) and 80 percent power, the smallest detectable paired Brier
improvement is (1.96 + 0.84) * sd_d / sqrt(600) = 0.114 * sd_d, where sd_d is the
standard deviation of the per-game paired Brier difference. sd_d is unknown until a
candidate exists and is measured ONCE, on the 300-game 2027 fit window from the
candidate fit, before any eval-half game is read, and published as
`mgmt_policy_gate.power_precondition` in betting_model_eval.json. That sd_d is
IN-SAMPLE (the residual sd of the fit that produced it) and therefore smaller than the
eval-half sd, so the precondition is lenient by construction; the gate block records
`power_precondition.basis = "in-sample fit-window sd, lenient"`, and after the eval
read the eval-half sd_d and the MDE it implies are reported beside it as a diagnostic.
No threshold changes. The floor of interest is pre-declared at 0.0024 Brier, one
percent of the served vintage Brier 0.24269 (betting_model_eval.json vintage.brier on
705 graded games, 2026-09-23). If 0.114 * sd_d exceeds 0.0024 the look returns
UNDERPOWERED without reading the eval half and waits for 2028 with the larger n; the
precondition may not be re-measured on a different window to lower it. If a member
passes (1) with an improvement below 0.0024, the result is recorded as
PASS-BELOW-FLOOR and does not ship (an effect the gate can detect but the site would
not serve). Underpowered is a verdict, and it is not a pass.

--------------------------------------------------------------------------------------
## 7. The Holm family MG
--------------------------------------------------------------------------------------

Members, one test each: 5l-A `mg_pen_per_game_l30`, 5l-B `mg_hook_pitches_l30`;
m = 2. Family alpha 0.05, one-sided, Holm: the smaller p at 0.025, the larger at 0.05.
Criteria 2 to 5, the twins and the screens carry no alpha and add nothing to m (the 5k
family's rule). Not members of RE (a total-side family), of the coefficient-vector
family (7e-B/C/D), of the z_prev family (N6), or of 5d's moneyline candidates (5d-A,
5d-B, 5d-D, 5d-E, which the 5k section records as "not members" of any family). Why
one family: both members ask one question of the moneyline (does a dugout policy term
beat the served prevention blend) from two mechanically correlated measurements of one
policy; a reader offered the better of the two has been offered the best of two looks.
Owner decision 2026-09-23: MG = {5l-A, 5l-B}, m = 2; the intentional-walk rate is not a
third member (with it the family would be m = 3 at 0.0167 / 0.025 / 0.05, and that
registration is not made).

--------------------------------------------------------------------------------------
## 8. SERVE flag, MODEL_VERSION, and the flip
--------------------------------------------------------------------------------------

`SERVE_MGMT_POLICY = False` lands with the builder (section 3), in the
SERVE_RUN_DISPERSION idiom, and stays False until a separate flip commit that cannot
exist before the look's artifact does. Whatever the effect size, neither column enters
the model before the look of section 9: not as a served input, not as a slot tiebreak,
not as a badge, not as a "context-adjusted" probability, not as a shadow-ledger tag,
and not through the Dugout context block. A Dugout context figure that appears to
predict is a reason to wait for the look, not to shorten it.

The flip, in ONE commit and only after a PASS the contaminated screen did not
disqualify: SERVE_MGMT_POLICY True, MODEL_VERSION bumped to betting_runs_v3 (or the
next), the --context re-run, the tripwire in test_betting_mgmt_policy.py and the
persisted `mgmt_policy_gate` block in betting_model_eval.json. The four move together
or not at all. MODEL_VERSION does not move on the registration, on the builder, or on
the look; only on the flip. A flip is the owner's call even on a PASS.

--------------------------------------------------------------------------------------
## 9. The clock, and the sentence that binds it
--------------------------------------------------------------------------------------

5c rule 2 AND criterion 4. The 2026 regular season ends 2026-09-27; a column that does
not exist tonight accrues nothing in 2026 and plan stop item X7 forbids registering it
as if a 2026 look existed. The builder lands before Opening Day 2027 (plan 5.1: "every
2027 dark column landed"), after 5j's schema-6 bump. April is null by the window floor;
populated values begin about the third week of the season; 900 games with both clubs
populated (600 eval behind a 300 fit) arrive about mid-June at the league's rate.

**The earliest admissible look is 2027-07-01.** The look is taken on the first nightly
on or after 2027-07-01 on which criterion 4 holds, by
tools/betting_mgmt_policy_gate.py (to be written), which reads vintages only, refuses
a run dated before 2027-07-01 and a second run once a `mgmt_policy_gate` block exists,
and writes that one block. If criterion 4 does not hold by 2027-08-01 the candidate
waits for 2028 (no stretch-run read, and no read on the same date as the season-end
looks of 5j and 5f). The look is never taken on the same calendar date as any other
registered look (5g's first-2027-date look is expected in June; 5e's, if not read in
October 2026, is scheduled by its own section), so a read of two families is never one
commit. If another registered look falls on the nightly 5l would take, 5l yields and
is taken on the next nightly on which criterion 4 holds; the yield is recorded in the
`mgmt_policy_gate` block.

The clocks this look must not collide with, as the plan's 5.1 calendar carries them
tonight: 5c-A 2026-09-28; 5c-B and 5c-C 2026-10-05; 5d (schema 4) and 5k 2026-10-07;
5e about 2026-10-09; 5i-B about 2026-10-10; 5g, 5f and 5j in 2027 (floating). The
plan's 5.1 row for this registration reads "2027-07-01 earliest | 5l club policy
rates, family MG (m = 2)".

Disclosures that will precede the look and are amended into 5l the day each is
recorded, without changing any threshold above: the 5c-B and 5c-C reads (2026-10-05),
the 5d read of `pen_ip_l3`, `pen_b2b_arms`, `pen_arms_avail`, `pen_plus_avail` and
`sp_tto3_bf` (2026-10-07), the 5e read (2026-10-09 or 2027), the 5g read (2027). Each
tells the lane something about the innings-share neighbourhood the 5l members sit in;
none is a read of a 5l column.

**Disqualification.** Any number relating either column, or a close variant (the
board's z_pen or z_hook, the season-to-date rates, a different window length, the
opener-aware form, a per-pitcher hook rate), to game outcomes, to edges or to
shadow-ledger results before 5l is committed, or before 2027-07-01 after it, voids the
member under 5c rule 1.

--------------------------------------------------------------------------------------
## 10. What would falsify this registration's premise
--------------------------------------------------------------------------------------

- If the 5d read of 2026-10-07 shows `sp_tto3_bf` and the innings share already absorb
  the hook, criterion 5's VIF read would fail 5l-B by construction. The member stays
  registered and the look still runs; the disclosure is amended in and the result is
  reported whichever way it lands.
- If the parity fixture fails, the builder does not derive the corpus's count and no
  look is taken until it does.
- If the power precondition is not on disk, no criterion may be read.
- If a member passes criteria 1 to 5 and the contaminated screen disqualifies it, the
  member is FAIL for this registration and the flip commit does not exist.

--------------------------------------------------------------------------------------
## 11. Open questions (Layer 1 properties recorded here, not in 5l's registration text)
--------------------------------------------------------------------------------------

- Redaction guard. No server-side redaction exists today: the word "redacted" does not
  occur in betting_export.py, and the client's redacted branch is client-side only.
  Because the Dugout block's `games` map is keyed by game_pk and covers the whole
  slate, a future server-side redaction that kept `game_pk` on the redacted slot would
  let the map name the redacted matchup. Standing rule: a server-side redaction MUST
  strip `game_pk` from the redacted slot's entry (a stripped key resolves to no block
  on the client), or the preview takes the alternative of slicing `games` to the
  preview cards plus the unredacted slot games. test_betting_mgmt_fence.py asserts
  that, for every slot entry in the preview carrying `redacted: true`, `game_pk` is
  absent.
- Record and Validation tabs. Management context on settled rows needs the per-club
  decision ledger files, which are untracked (D2 owner decision 1) and end 2026-09-04;
  out of scope until they are tracked and a settled-row join exists.
- The management page carries no reciprocal link to /betting/ (owner decision
  2026-09-23): a "not skill" page pointing at a price page invites the reading this
  document forbids; the block links inward only.

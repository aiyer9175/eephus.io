# Sports Betting: the home-plate umpire gate (pre-registered 2026-10-08)

The long form of the docs/diamond-betting.md section "The home-plate umpire: a dark
pregame assignment capture". Written in the shape of docs/BETTING_DUGOUT_GATE.md: the
honesty clause first, then the candidate census, the capture, the code that lands later,
the look's step order, the clock and the open questions. Every threshold here is the one
that section carries, in the same words; where the two could ever disagree, the section
governs. test_betting_umpire_registration.py (to be built) pins the two documents to each
other. Plain ASCII, no em or en dash.

--------------------------------------------------------------------------------------
## U-0. Honesty clause, first
--------------------------------------------------------------------------------------

No candidate was scored to write this registration. Nothing was fitted, no column was
built, no capture exists, no prior-season table exists. Everything read during design,
and what each read is:

- One StatsAPI request, `/api/v1/schedule?sportId=1&startDate=2026-10-08&endDate=2026-10-11&gameType=R,F,D,L,W&hydrate=officials`,
  at 2026-10-09T00:01:42Z. Three postseason games: 849832 (D, `Live` / `Warmup`, first
  pitch 0.0 hours away) carried six officials, the plate umpire among them; 849831 (48
  hours out) and 849809 (72 hours out) carried none. Read for which games carried an
  officials list and the plate umpire's presence only. No score, result, line, price or
  edge was read; the response is not committed.
- docs/diamond-betting.md 5c (rules 1 to 4), 5d-F (the 2026-09-08 probe of game_pk
  824792, an EMPTY officials list in `Preview` state), 5k (the 5k gate's pinned t, twin
  and family rules), 5l and 5m (the registration shape), 8a, and the verdict headings of
  5c-B, 5c-C, 7g, 7h and 11b.
- docs/master-plan-2026-09-24-final-pass.md census item X05-04 and its owner question
  ("Register now, arm at 2027 Opening Day" as the plan's default).
- The served code named in the section: `betting_model` (`expected_runs`,
  `fit_coefficients`, VINTAGE_MIN_GRADED_GAMES 600, VINTAGE_FIT_TARGET_GAMES 300,
  SERVE_RUN_DISPERSION), `betting_ingest` (the `open` and `close` snapshot kinds),
  `tools/betting_lineup_job.py` (the capture shape), `tools/build_pbp_corpus.py` (the
  `call_code` and `home_plate_umpire_id` columns, read as code, never as data).

No umpire's value, count, spread or effect was computed or read. 5d-F recorded that the
size of the umpire effect "has not been run and no number about it exists"; that is still
true at this commit.

Looking early disqualifies. 5c rule 1 verbatim in force: "Each candidate gets its own
gate section in this document before any number is computed on it ... A candidate
measured before its section exists is disqualified, whatever it measured." Each member
has exactly one look, on the date fixed in section U-5.

--------------------------------------------------------------------------------------
## U-1. The candidate census
--------------------------------------------------------------------------------------

| quantity | class | ruling |
|---|---|---|
| the plate umpire's identity, from the schedule's `officials` hydrate, captured before T_price | pregame-knowable once published | CAPTURED (`umpire_capture/1`); it is the key, not a column |
| his called-strike share of taken pitches, prior regular seasons | a fact about him dated before the season | REGISTERED as 5n-A `ump_cs_rate_prior` |
| his runs-per-game effect, prior regular seasons | a fact about him dated before the season | REGISTERED as 5n-B `ump_rpg_prior` |
| the plate umpire from `liveData.boxscore.officials` or any completed feed | dated after the game | NEVER a source (5d-F) |
| a rotation prediction (crew order) before the schedule publishes | a guess, not a published fact | NOT ASKED; its own section if ever wanted |
| a same-season or trailing-window form of either rate | close variant | NOT ASKED |
| his strikeout, walk or run-value rate; a location-adjusted zone; a crew effect | close variants | NOT ASKED |
| third-party umpire figures (accuracy, consistency, favor) | an outside model, unverifiable dating | NEVER a source |
| props (strikeouts, walks) or moneyline estimands | other markets | NOT ASKED |

--------------------------------------------------------------------------------------
## U-2. The capture, in long form
--------------------------------------------------------------------------------------

`tools/betting_umpire_job.py`, step 2 of the owner answer, committed after this document.

- **Source.** StatsAPI `/api/v1/schedule`, `hydrate=officials`, game types R, F, D, L, W,
  one request per acting invocation over the UTC dates D-1 to D+2 (a 36-hour look-ahead
  can cross two UTC dates). Free and keyless: zero Odds API credits. The plate umpire is
  the official whose `officialType` is "Home Plate".
- **Cadence.** Cron `*/15 * * * *` under `TZ=UTC`; the job decides. It calls when its own
  slate is missing, spans the wrong dates or is older than 30 minutes while any game is
  pregame and between 5 minutes and 36 hours from first pitch; it refreshes an idle slate
  hourly; a slate older than 6 hours is a loud error that still calls.
- **The refusal boundary.** No row for a game that is not pregame (abstract state
  `Preview`, not postponed, cancelled, suspended or delayed) or is under 5 minutes from
  first pitch.
- **What a row is.** One row per game whose plate assignment CHANGED since its last row:
  the first sighting with a plate umpire, a different umpire, or a retraction (a row with
  `hp_umpire_id` null after an assignment had been recorded). Fields, the schema
  `umpire_capture/1`, and nothing else: `game_pk`, `game_type`, `official_date`,
  `first_pitch`, `captured_at`, `lead_minutes`, `status`, `double_header`,
  `home_team_id`, `away_team_id`, `venue_id`, `hp_umpire_id`, `hp_umpire_name`, `crew`,
  `last_unassigned_at`.
- **Bracketing publication.** The job keeps a small cache of the newest instant at which
  it saw each game pregame with no plate umpire; a row's `last_unassigned_at` copies it,
  so the publication instant lies after `last_unassigned_at` and at or before
  `captured_at`. This is timing, not outcome, and it is the fact the one allowed T_price
  correction may rest on.
- **Immutability.** One file per acting invocation that wrote rows, named
  `<UTC date>-<HHMM>.json` under `.cache/umpire_captures/`, created exclusively; a second
  write in the same minute loses and writes nothing. The slate, the unassigned cache, the
  heartbeat and a per-day append-only run log share the directory and never match the
  capture name.
- **What it never does.** It reads no game feed, no score, no result, no line and no
  price; it imports no pricer (`betting_model`, `betting_export`, `betting_ingest`,
  `betting_credits`), no settle, scores or results module and no management module; no
  served module imports it; no outcome field sits beside an assignment in any file it
  writes. Tests pin each of these, plus one call per invocation, the refusal boundary,
  the change rule and the immutable file.
- **Where it runs.** Installing the cron entry on the box is a deploy step, deferred
  under the owner's DEPLOY-3 ruling and listed in docs/DEPLOY_PENDING.md. Until it is
  installed nothing accrues, and the clock in U-5 starts from the first 2027
  regular-season capture row whatever the install date.

--------------------------------------------------------------------------------------
## U-3. Code that lands AFTER the capture, and before Opening Day 2027
--------------------------------------------------------------------------------------

None of it exists at this commit, and the registration test asserts that no non-test
module at the repo root or under tools/ names `ump_cs_rate_prior` or `ump_rpg_prior`
until a "### Builder landed" amendment exists in the section.

- `tools/umpire_prior_table.py`: builds `data/_labs/umpire_prior/umpire_prior_2027.json`
  from `.cache/pbp_corpus` (regular season, 2018, 2019, 2021 to 2026), per umpire id: 5n-A
  with k_c = 3000 taken pitches, 5n-B with k_r = 150 games, the counts, the excluded
  call-code census, and the ABS-overturn exclusion count for 2026 (or the statement that
  2026 was dropped from 5n-A). It computes each umpire's value and nothing else: no
  spread, standard deviation, ranking, correlation or stability across umpires.
- `betting_model.SERVE_UMPIRE = False`, with the comment "TO FLIP THIS FLAG: a PASS in
  the umpire look, the contaminated screen run without disqualifying, the MODEL_VERSION
  bump, the --context re-run, the tripwire test and the persisted umpire_gate block, in
  one commit."
- `tools/betting_umpire_gate.py`: the look (U-4), refusing an early run, a run without
  the table hash and a second run.
- Registry row `betting_umpire_dark` (`unvalidated`) with data/betting_umpire_eval.json.

--------------------------------------------------------------------------------------
## U-4. The look, in step order
--------------------------------------------------------------------------------------

1. Refuse unless the date is on or after 2027-06-01, no `umpire_gate` block exists, the
   table's sha256 equals the one recorded in the section's `### Builder landed`
   amendment, and no other registered look falls that day.
2. Build the eligible set: 2027 regular-season games with a counted assignment (the
   newest capture row strictly before T_price and at least 5 minutes before first pitch,
   naming a plate umpire) and a non-null value. Count every exclusion by reason.
3. Criterion 5: at least 600 eval-half games behind the 300-game fit window, and at
   least 28 days since the first 2027 regular-season capture row. If not, write NOT READ
   with the counts and stop.
4. Fit the incumbent and each member on the fit window. Measure sd_d and the floor
   (1 percent of the incumbent's fit-window mean absolute error on the total). If
   0.114 x sd_d exceeds the floor, the member is UNDERPOWERED and its eval half is not
   read.
5. Score criteria 1 to 4 on the eval half, run the 200-seed assignment twin, apply Holm
   in UMP (m = 2: 0.025, then 0.05).
6. Write the one block and append `### Result (run DATE, once): VERDICT` to the section.

--------------------------------------------------------------------------------------
## U-5. The clock, and the sentence that binds it
--------------------------------------------------------------------------------------

**The earliest admissible look is 2027-06-01**, on the first nightly on or after
2027-06-01 on which criterion 5 holds (600 eval-half games behind a 300-game fit window,
and 4 weeks of 2027 regular-season captures), the table's amendment exists and no other
registered look falls that day; otherwise it yields to the next such nightly and records
the yield. If criterion 5 does not hold by 2027-08-01, the look waits for 2028. The 2026
postseason and any spring capture accrue for timing only; no 2026 game is ever graded.
Clocks it must not collide with: 5l and 5m's stage 2 (first nightly on or after
2027-07-01), 5g's first 2027 look, 5j, 5f and any look a docs/*GATE*.md file dates.
**Looking early DISQUALIFIES.**

--------------------------------------------------------------------------------------
## U-6. What would falsify this registration's premise
--------------------------------------------------------------------------------------

- If the capture shows the schedule naming the plate umpire only after the open
  snapshot on most games, the open-form eligible set cannot reach criterion 5; the one
  allowed correction (T_price to the close snapshot, filed before any look number) is the
  only remedy, and without it the look returns NOT READ.
- If the capture shows the schedule never naming a plate umpire before first pitch
  outside the postseason, 5d-F's conclusion stands and the section is closed by a dated
  note.
- If the corpus carries no `home_plate_umpire_id` for a season, the table drops that
  season and says so; it never fills one from a completed feed of a later date.

--------------------------------------------------------------------------------------
## U-7. Open questions for the owner
--------------------------------------------------------------------------------------

- When to install the capture. Default: at the next beta sync (it idles in the
  offseason and records the remaining 2026 postseason's publication timing, zero
  credits). Alternatives: install at 2027 Opening Day (the plan's X05-04 default; the
  first timing facts then arrive in the season the look reads); do not install (the
  section stays registered and accrues nothing).
- Which price vintage counts. Default: the open snapshot, the served board's price.
  Alternative: the close snapshot from the start (more games likely eligible; the price
  it gates is one the board does not serve until the close job is installed).

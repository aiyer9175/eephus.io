# ABS challenge ledger: registration (EWAR_T4_ABS_LEDGER)

STATUS: REGISTERED. Committed 2026-10-15 by queue task EWAR_T4_ABS_LEDGER (eWAR expansion plan T4 step 1, owner decisions EW3-16 to EW3-20). This document fixes the ledger's rows, its rules and its invariant before the builder exists and before any per-player, per-club or per-role number is computed. The only numbers read before it was written are a census of the feed cache (how many cached feeds there are per season and level, and how many review records of each type they hold, which decided which frames exist) and the Scores defect count in section 7.

The ledger is a measurement substrate. It values nothing: it carries no run value, no win value and no player rating. eABS values (EWAR_T4_EABS) and any eWAR part are registered separately. Nothing served moves because of this document or the ledger.

## 1. What a row is

One row per player challenge of a ball or strike call, read from MLB StatsAPI game feeds (`/api/v1.1/game/{pk}/feed/live`).

- ABS zone challenge: `reviewDetails.reviewType == "MJ"`. This is the family the owner's eABS ask is about and the only one in MLB in 2026.
- Check-swing challenge: `reviewType == "MZ"`, seen only in the minor leagues (the play text reads "challenged (check swing)"). It is recorded as its own kind, `check_swing`, and never mixed into the `zone` kind; it is listed because the minor-league feeds count it inside `gameData.absChallenges`.
- Manager replay challenges (the other `M*` types) and crew-chief reviews (`N*`) are not rows.

Where the review sits:

1. On a pitch event (`liveData.plays.allPlays[i].playEvents[j].reviewDetails`): the row is that pitch.
2. On the play (`allPlays[i].reviewDetails`, or an entry of its `additionalReviews`): the challenged pitch is the play's last pitch event. This is the case where the ruling ended the plate appearance (ball four, strike three, or a reversal into one). A play-level review whose last pitch is not a called pitch of its kind is kept and flagged `attach_suspect`.

## 2. Fields

game_pk, season, level (sport id), game_type, official_date, inning, half, at_bat_index, event_index, pitch_number, source (`event`, `play`, `play_additional`), kind (`zone`, `check_swing`), review_type, challenge_team_id, challenge_org (canonical club for MLB, the parent organization's club for a minor-league club), challenger_id, role, batter_id, pitcher_id, catcher_id, overturned, final_call, original_call, balls_before, strikes_before, outs_before, bases_before (three-character occupancy such as `1_3`), bat_score_before, fld_score_before, count_after_final, count_after_original (`b-s`, or `BB` / `K` when the call ends the plate appearance), li_pa, px, pz, sz_top, sz_bot, flags.

Rules:

- final_call is `details.call.code` of the challenged pitch. original_call is final_call when the call stood, and its inverse when overturned: for a zone challenge ball (`B`) and called strike (`C`) invert; for a check-swing challenge ball (`B`) and swinging strike (`S`) invert. A challenged pitch whose final call is outside its pair is kept and flagged `call_suspect`.
- The count before is the count of the previous event in the same plate appearance that carries a count (pitch-clock automatic balls and strikes are events), else 0-0. Outs before come from the same previous event, else from the plate appearance's start.
- Bases before: the plate appearance's start occupancy (the previous play's end), updated by every runner movement of the same play whose `details.playIndex` is below the challenged event's index.
- li_pa is MLB's leverage index of the plate appearance, joined from the pbp corpus plays (`leverage_index`, by game_pk and at_bat_index). It is the plate appearance's value, not the pitch's, and it is null on each game's leadoff plate appearance and in every minor-league frame.

## 3. Role

The challenger is resolved in this order, at the moment of the pitch:

1. `batter`: the challenger is the plate appearance's batter.
2. `pitcher`: the challenger is the fielding side's pitcher by the defense walk.
3. `catcher`: the challenger is the fielding side's catcher by the defense walk.
4. otherwise `unresolved`.

The defense walk starts from the boxscore: the starting pitcher is the first entry of the side's `pitchers`, the starting catcher is the side's starter (`battingOrder` ending in `00`) whose first entry of `allPositions` is catcher. Every substitution action (`isSubstitution` true, a fielding position code 1 to 9) then seats its player at that position for his side, in event order. Two checks are reported: the walk's pitcher equals `matchup.pitcher` on the last pitch of every plate appearance, and the challenge side agrees with the role (a batter challenges for the batting club; a pitcher or catcher for the fielding club). Disagreements are counted and listed, never smoothed.

## 4. Invariant (refuses the build)

For every 2026 MLB feed, for each club: rows with overturned true equal `gameData.absChallenges.<side>.usedSuccessful`, and rows with overturned false equal `usedFailed`, exactly. One mismatched feed refuses the MLB ledger.

Minor-league frames: the same comparison (over both kinds, since those feeds count both) is reported per feed as a match rate. A mismatched feed is listed and excluded from any stability frame built on the ledger.

## 5. Frames

- MLB 2026, regular season, every cached final feed (`.cache/game_feeds`, sport id 1).
- Minor-league frames found in the cache: every cached final feed whose `absChallenges.hasChallenges` is true or that carries a challenge row.
- AAA 2022 to 2025 (not cached). Probe: for each season, the final regular-season sport id 11 schedule, then 40 games per season taken at even steps through the season's final games in schedule order, fetched in full into `.cache/EWAR_T4_ABS_LEDGER/aaa_probe/`. Reported per season: games scheduled, games sampled, share with `hasChallenges`, share with at least one challenge row, rows per game, kinds, invariant match rate.
- If a season's probe holds challenge rows, every final regular-season AAA game of that season is fetched with a StatsAPI `fields` filter into `.cache/EWAR_T4_ABS_LEDGER/aaa_feeds/`, after the filtered and full payloads give identical ledger rows on every probe game. Polite: one request at a time, at least 0.25 seconds apart.

## 6. Outputs

- `abs_ledger.py` (pure readers), `tools/build_abs_ledger.py` (the run), `test_abs_ledger.py`.
- `data/_labs/abs_ledger/` (never shipped): the MLB 2026 ledger, the minor-league ledger, and `coverage.json` (frames, invariant, role checks, the AAA probe).

## 7. The Scores reader (scores_core.play_rows)

The plays tab lists a plate appearance's reviews. It read only the play-level `reviewDetails`, so a challenge on a non-terminal pitch, and a second review in `additionalReviews`, never appeared; and the job's winProbability `fields` filter (tools/scores_job.py `WP_FIELDS`) does not request `reviewDetails`, so a game the job fetched itself shows none at all. The repair reads pitch-level reviews and `additionalReviews`, keeps each review's own type (an ABS challenge `MJ` is never merged with a replay challenge such as `MF`), adds the pitch number, and adds the review fields to `WP_FIELDS`. Measured before the repair on the served files: 46 game files, 36 reviews of type `MJ` listed against 209 ABS challenges in the same games' `info.abs`, and none at all in the 12 postseason games the job fetched itself.

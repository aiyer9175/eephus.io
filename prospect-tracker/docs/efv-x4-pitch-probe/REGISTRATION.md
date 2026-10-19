# eFV expert program X4: StatsAPI pitch-level probe below Triple-A (registration)

Registration status: REGISTERED (development probe, dark; nothing served moves by this
document or by anything it registers)

Written 2026-10-15, worktree lane 202, task EFV_X4_STATSAPI_PITCH_PROBE, under decision
EW3-12 of 2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, owner verbatim "Let's do
all of the above"): step 4 of the expert eFV program, a probe of MLB StatsAPI pitch-level
feeds below Triple-A. Committed ALONE, before any feed was fetched, any coverage share was
counted, or any metric was related to any outcome. Look days are waived (EW3-5): the
probe, the coverage tables and the descriptive read run the same day this document
commits, and the read is recorded as an owner-waived early read. No em-dashes. Nothing
here is cut, counted or averaged by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`):
consensus FV enters only as a continuous covariate and as a comparator score.

Producer: `tools/efv_x4_pitch_probe.py` (imported by no served module). Raw cache:
`.cache/efv_x4_pitch/` only. Artifact: `data/_labs/efv_x4_pitch_probe.json` (role
development; `data/_labs/` ships in neither deploy consumer). Documents:
`docs/efv-x4-pitch-probe/COVERAGE.md` (the coverage tables) and
`docs/efv-x4-pitch-probe/RESULTS.md` (plain language for the owner). Pins:
`test_efv_x4_pitch_probe.py`.

Where this document and the measurement disagree, the measurement is what the read uses
and the disagreement is recorded below section 9, never edited away.

## 0. What was read before this document was written

- The task text (EW3-12) and the decisions EW3-1, EW3-5, EW3-10, EW3-11, EW3-13.
- The published census of the Savant minors fetch (`data/_labs/efv5/tracking_coverage.json`,
  2026-10-14): Savant's public minors search serves Triple-A from 2022 and the Florida State
  League (Single-A, sportId 14) from 2021, and never Double-A or High-A. That is the prior
  this probe tests on a different source.
- The published results of the tracking-era head (`docs/efv-v2/EFV_TRACKING_HEAD_GATE.md`
  and `EFV_TRACKING_HEAD_RESULTS.md`, 2026-10-15), whose label, folds, model form and
  statistics this read borrows so the two reads are comparable. Its numbers choose nothing
  here.
- The code of `milb_pbp_fetch.py` (the eFV v4 playByPlay fetch, whose `fields` filter keeps
  pitch calls, counts and batted-ball trajectory but NO pitchData) and its schedule cache
  `.cache/efv4_pbp/schedule/{sport}_{season}.v2.json.gz` (2021 to 2025), read for its shape
  only. No feed of this probe had been fetched; no coverage share was known for any level
  below Triple-A on StatsAPI.

## 1. The questions

Q1 (coverage). Do StatsAPI game feeds (`/api/v1.1/game/{gamePk}/feed/live`) carry pitch
tracking (release speed, spin, breaks, extension, plate location, and on balls in play
launch speed and angle) for affiliated games at Double-A (sportId 12), High-A (13) and
Single-A (14), and for which seasons (2021 to 2026) and parks? Triple-A (11) is sampled as a
control: Savant serves it from 2022, so its StatsAPI share is a check on the probe itself.

Q2 (signal, descriptive, only if Q1 finds real coverage). On development rows that carry
such a line, does a minimal per-player season aggregate of the tracked fields add to PROSPX
consensus FV in ordering short-horizon outcomes? Ships nothing; adjudicates nothing.

## 2. The coverage sample (Q1), fixed here

Schedules: the final regular-season games of each (sportId, season) by the rule of
`milb_pbp_fetch.schedule` (game type R, abstract state Final, not postponed, cancelled or
suspended, the Mexican League left out). 2021 to 2025 are read from the eFV v4 schedule
cache (read only); 2026 is fetched by the same rule into `.cache/efv_x4_pitch/schedule/`.

Strata: sportId in {11, 12, 13, 14} x season in {2021, ..., 2026} x home team (the park's
proxy; the venue actually played in is read from each feed's `gameData.venue` and the
tables report venues).

Games, deterministic, no random draw: for each stratum, two games: EARLY, the first home
game (date, then gamePk ascending) with officialDate on or after {season}-05-15, and LATE,
the first home game on or after {season}-08-01. When a half has no such game the stratum's
nearest earlier home game stands in, and when the two picks are the same game the stratum
holds one game. Expected size about 30 home teams x 4 levels x 6 seasons x 2, so about
1,440 feeds.

Fetch: the full `/api/v1.1/game/{gamePk}/feed/live` JSON, gzip-compressed, cached raw at
`.cache/efv_x4_pitch/feeds/{sportId}/{season}/{gamePk}.json.gz` (a cached game is never
fetched again). At most 2 concurrent requests, a 0.25 s pause before each request, a
descriptive User-Agent, retry with backoff on 429 and 5xx (Retry-After honoured), no
request while the UTC clock is inside 06:00 to 11:00 (the nightly fetch window). StatsAPI
is public, free and needs no login.

## 3. Coverage statistics and the coverage rule (Q1)

Per sampled game, over its pitch events (`playEvents` with `isPitch` true):

| field | path in the feed | denominator |
|---|---|---|
| release speed | `pitchData.startSpeed` | pitches |
| spin rate | `pitchData.breaks.spinRate` | pitches |
| induced vertical break | `pitchData.breaks.breakVerticalInduced` | pitches |
| horizontal break | `pitchData.breaks.breakHorizontal` | pitches |
| extension | `pitchData.extension` | pitches |
| plate location | `pitchData.coordinates.pX` and `.pZ` | pitches |
| zone | `pitchData.zone` | pitches |
| pitch type | `details.type.code` | pitches |
| launch speed | `hitData.launchSpeed` | balls in play (`details.isInPlay`) |
| launch angle | `hitData.launchAngle` | balls in play |

A game is TRACKED for a field when the field is present (non-null) on at least 80 percent
of its denominator. A (level, season) cell's coverage for a field is the share of its
sampled games tracked for it; its park coverage is the count of distinct venues with at
least one sampled game tracked, over the venues sampled. The tables give every field by
level and season, and release speed by level, season and venue.

The coverage rule, fixed here:

- a (level, season) cell is VELO-COVERED when release speed is tracked in at least 50
  percent of its sampled games;
- it is FULL-COVERED when release speed, spin rate, induced vertical break, extension,
  plate location, launch speed and launch angle are EACH tracked in at least 50 percent of
  its sampled games;
- coverage below Triple-A is REAL when at least one sub-Triple-A cell with season 2021,
  2022 or 2023 (the seasons whose short label resolves, section 5) is VELO-COVERED. If it
  is not, the probe stops after the coverage tables: no aggregate is built and Q2 is not
  read.

## 4. The aggregate (Q2), built only for covered cells

Full fetch: for every sub-Triple-A (level, season) cell with season 2021 to 2023 that is
VELO-COVERED, every final regular-season game of the cell, fetched as the
`/api/v1/game/{gamePk}/playByPlay` payload under a `fields` filter that keeps the pitch
events' calls, counts, pitchData (speed, spin, breaks, extension, coordinates, zone,
strike-zone top and bottom), pitch type, and hitData launch speed and angle, cached raw at
`.cache/efv_x4_pitch/pbp/{sportId}/{season}/{gamePk}.json.gz` under the section 2 fetch
rule (up to 4 concurrent requests for this pass, the eFV v4 fetch's ceiling). Seasons 2024
to 2026 are not fetched for the aggregate (no resolvable short label; section 10).

A pitch counts as tracked when its release speed is present. Per (player, season, level):

Pitchers (qualify: at least 100 tracked pitches):

| metric | definition |
|---|---|
| fb_velo_p50 | median release speed of fastballs (type code FF, SI, FT or FA) |
| fb_velo_p95 | 95th percentile release speed of fastballs |
| fb_spin | mean spin rate of fastballs |
| fb_ivb | mean induced vertical break of fastballs |
| whiff | whiffs over swings, on tracked pitches |
| chase | swings at pitches outside the zone over pitches outside the zone |
| ev_against_p50 | median launch speed of balls in play against |

Hitters (qualify: at least 50 plate appearances whose pitches are all tracked):

| metric | definition |
|---|---|
| ev_p50 | median launch speed on balls in play |
| ev_p90 | 90th percentile launch speed on balls in play |
| hard_hit | share of balls in play at 95 mph or more |
| whiff | whiffs over swings |
| chase | swings at pitches outside the zone over pitches outside the zone |
| zone_contact | contact on swings at pitches in the zone over those swings |

Pitch calls (StatsAPI `details.call.code`): whiff = S, W, M, Q; swing = whiff codes plus T,
F, L, O, R, X, D, E (a foul tip counts as contact). In the zone: `pitchData.zone` 1 to 9;
outside: 11 to 14; when `zone` is absent, |pX| at most 0.83 ft and pZ between the pitch's
own strike-zone bottom and top. A fastball metric needs at least 25 typed fastballs, a
launch metric at least 15 tracked balls in play, a swing metric at least 30 swings (chase:
at least 30 pitches outside the zone; zone contact: at least 30 in-zone swings); below
that the metric is absent.

Candidate metrics for the read: a metric enters only when every one of its source fields
is tracked in at least 50 percent of the sampled games of every cell that contributes rows
(a coverage fact, not an outcome). Metrics left out are named in the artifact. A row needs
every candidate metric of its side present.

No look-ahead: a row's as-of date is V-01-01 with V = S + 1 (the preseason list it is
scored with). The producer asserts that every game feeding a row's aggregate has an
officialDate inside season S and before the as-of date, and records the maximum date.

## 5. The frame and the label (Q2)

Rows: one per (player, S) with S in {2021, 2022, 2023}, the player's qualifying aggregate
line at a covered sub-Triple-A level in S (the highest such level when two qualify: AA over
A+ over A), a PROSPX consensus FV read in the V = S + 1 preseason window taken exactly as
`efv5_atlas.consensus_reads` takes it (consensus vintages 2022, 2023, 2024; R-LV 2020 and
2021 never built), and no MLB season line at or before S.

Label, the tracking-era head's (section 2 of its registration): reach3 (first MLB season in
S+1 .. S+3) and rate3 (fWAR per MLB season over those seasons, 0 without one), from the
frozen fWAR label `data/fwar_vintage.json` and the sport-1 season lines on disk, H = 2026.

Frames: CLEAN = cohort S 2021 (window 2022 to 2024; development, no reserved overlap).
SPENT = cohorts S 2022 and 2023, whose windows reach the 2025 and 2026 debut cohorts (R-VM).
Per EW3-13 the R-VM waiver belongs to EFV_2026_HOLDOUT_READ alone, so every number on a
spent row is labelled spent, is read once here, and is never the sole claim. POOLED = all
three cohorts, labelled spent.

## 6. The model and the statistics (Q2), fixed here

Per side, X = [1, level ordinal (A 0, A+ 1, AA 2), z(consensus FV), z(metric 1), ...,
z(metric k)], z on each fit's training rows. The tracking-era head's two heads and output,
reused unchanged (`efv5_tracking_head.fit_logistic`, `fit_ridge`, `order_head`): a ridge
logistic reach head, a ridge rate head on reached rows, order = P(reach3) * E[rate3 |
reached]. The metric columns carry ONE fixed penalty, lambda = 10, in both heads; the
intercept, level and consensus columns are unpenalised. No penalty or metric selection is
made, so the read has no forking path.

Scores compared on the same rows, all out of fold over 5 player-grouped folds
(`efv5_atlas.player_folds`, seed 20261015):

    head        the model above with the metrics
    base        the same model with lambda = infinity (consensus plus level only)
    consensus   the row's consensus FV as read

The CLEAN read folds and fits on the S 2021 rows only (so no spent label trains it); the
POOLED read folds and fits on all rows. Statistics (`efv5_tracking_head.compare`): AUC of
each score against reach3, within-cohort Spearman against rate3, the paired deltas head
minus base and head minus consensus, each with a CI95 from B = 2000 player-cluster
bootstrap draws, seed 20261015, scores fixed (E_cond). A frame is UNREADABLE when it holds
fewer than 50 rows or fewer than 10 reach3 positives or negatives.

Also reported, description only: the standardised coefficients of each metric in the
CLEAN fit (all S 2021 rows, lambda 10).

## 7. The descriptive signal rule (adjudicates nothing)

A frame shows INCREMENTAL SIGNAL when, on it, head minus base is positive as a point
estimate on BOTH statistics AND the AUC delta's CI95 lower bound is above zero. The label
is a description for the owner and for EFV_X3_POOLED_MODEL's own registration (which may
name these metrics as candidates); it ships nothing, flips nothing, and enters no served
number, registry claim or progress row. The spec's rule stands: nothing served moves unless
a later registered rule passes AND the owner answers a flip question.

## 8. Bans and hygiene

- PROSPECT_ANCHOR_GATE: no mean, residual, count or cohort by consensus-FV cell anywhere in
  the producer, the artifact or the documents; the test scans the source.
- Reserved frames: no R-LV list vintage is built; R-VM overlap labelled spent (section 5).
- No projections retrain; `backtest.run_backtest` is never called; no served module imports
  the producer; fetches write under `.cache/efv_x4_pitch/` only; `prospects.db` is read only.
- No dark betting column is read or related to anything.
- No em-dash anywhere.

## 9. What the probe does not do

It does not change eFV, the board, any grade, the glossary or any served artifact. A
covered level's metrics reach eFV only through a later registration (EFV_X3_POOLED_MODEL or
an amendment of the tracking-era head, whose section 10 says a new tracked level
re-registers its candidate list) and an owner flip.

## 10. Upgrade path

Seasons 2024 to 2026 of any covered cell resolve the short label after the 2027 to 2029
seasons; a later task may fetch them under this document's fetch rule and read them by a
dated amendment. A level found uncovered here is re-probed only by a new registration.

## 11. Dated notes

- 2026-10-15: written and committed alone, before any feed was fetched. The probe and the
  read follow the same day under EW3-5 (owner-waived early read).
- 2026-10-15: THE PROBE (owner-waived early read, EW3-5; `python tools/efv_x4_pitch_probe.py --probe`, then `--read --md`; artifact `data/_labs/efv_x4_pitch_probe.json`). 1,440 sampled feeds fetched in one pass (1,439 fetched and 1 already cached by the producer's smoke test, 0 failed, 1,443 requests in 529.6 s). Coverage below Triple-A is NOT REAL by section 3: no Double-A or High-A sampled game in any season 2021 to 2026 carries any registered field; the Single-A cells hold 27 to 30 percent tracked games, every one in the Florida State League (named Low-A Southeast in 2021), which Savant already serves; the largest release-speed share on any untracked sub-AAA game is 0 percent. The Triple-A control reads 0 percent (2021), 37 percent (2022) and 100 percent (2023 to 2026). By the rule the probe stops at the coverage tables: no full fetch, no aggregate, no outcome read. Recorded, not edited away: two descriptive columns not named above were added after the first sampled feed, the Gameday stringer's pixel location (`pitchData.coordinates.x` and `.y`, present on every pitch, a click on a drawn zone and not a measured location) and the home league's name per sampled game; neither enters any rule. Tables: `docs/efv-x4-pitch-probe/COVERAGE.md`; plain language: `docs/efv-x4-pitch-probe/RESULTS.md`.

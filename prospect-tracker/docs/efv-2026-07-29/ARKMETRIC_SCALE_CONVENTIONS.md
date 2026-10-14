# Arkmetric scale conventions - 2026-07-29

Reference table. Every metric on this site whose name ends in `+` is anchored at 100, and that
is the ONLY thing they have in common. Six different scale conventions ship under that shared
look, so "120" means six different amounts of above-average depending on which metric you are
reading.

The concrete trap this document exists to stop: **HEM+ and SEM+ sit on adjacent tabs of the
same `/mlbstats/` page, and a HEM+ 120 is not the same deviation as a SEM+ 120.** HEM+ carries
`HEM_SPREAD_GAIN = 2.28` (a constant in `hem_plus.py`), a fixed monotone widening applied so the league
reads with visible spread; REM+ and SEM+ are the bare ratio with no gain. A HEM+ of 120 is a
wOBA ratio of about 108.8; a SEM+ of 120 is a FIP ratio of 120. Same tab strip, same suffix,
different units.

## The six conventions

| # | convention | reading | typical shape |
|---|---|---|---|
| 1 | ratio | a point is about one percent better than the pool | `100 * player / pool` |
| 2 | ratio with the HEM gain | a point is about 0.44 percent (2.28x widened) | `100 + 2.28 * (100 * player / pool - 100)` |
| 3 | 100 + 10z | 10 points is one population standard deviation | `100 + 10 * z` |
| 4 | 100 + 15z | 15 points is one standard deviation | `100 + 15 * z` |
| 5 | linear percentile | a rank or a 0-1 normalized signal mapped onto a fixed band | `lo + (hi - lo) * pct` |
| 6 | additive percentage points | a point is one percentage point of the underlying rate gap | `100 + (player_rate - level_rate)` |

## The table

| metric | convention | anchor pool | clamp | computing site |
|---|---|---|---|---|
| HEM+ | 2 (ratio x 2.28) | qualified MLB hitters | none | `hem_plus.py` |
| xHEM+ | 2 (ratio x 2.28) | same hitter pool, xwOBA input | none | `hitter_export.py` (xHEM+ join) |
| HEM+ 3yr | 2 (ratio x 2.28) | hitter pool, 3-season blend | none | `hem_plus.py` via `hitter_export.py` |
| xHEM+ Blend (fwdHEM+) | 2 (ratio x 2.28) | re-standardized blend mapped back onto the HEM+ location and spread | none | `hitter_export.py` (fwdHEM+ join) |
| REM+ | 1 (ratio) | relievers only | none | `rem_plus.py` |
| REM+ 3yr | 1 (ratio) | relievers, 3-season blend | none | `rem_plus.py` via `bullpen_export.py` |
| xREM+ | 1 (ratio, inverted input) | relievers, xwOBA-allowed | none | `bullpen_export.py` (`_join_xrem_plus`) |
| SEM+ | 1 (ratio) | qualified starters only | none | `sem_plus.py` |
| SEM+ 3yr | 1 (ratio) | starters, 3-season blend | none | `sem_plus.py` via `starter_export.py` |
| xSEM+ | 1 (ratio, inverted input) | starters, xwOBA-allowed | none | `starter_export.py` |
| Bullpen+ | 1 (ratio, inherited) | IP-weighted mean of a staff's REM+ | none | `rem_plus.py` (staff roll-up) |
| PAR | 1 (ratio, not inverted, uncoloured, unshrunk) | MLB: the league role line for the season (every start, every relief outing, every non-pitcher PA), pooled; MiLB: the level-season-role line, tracked level-seasons only | none | `pitch_rates.py` (`par`), joined by `pitch_rates_boards.py` and `storage.py` |
| Team PAR | 1 (ratio) | the unweighted mean of the 30 club unit rates (lineup, rotation, bullpen), so the clubs average 100 | none | `pitch_rates.py` (`team_par`) via the three board exporters |
| OPS+ (vs level) | 1 (ratio) | the player's MiLB level | none | `storage.py` |
| ISO+ | 1 (ratio, EB-shrunk by AB) | the player's MiLB level | 0-250 | `prospx/index.html` (`computeIsoPlus`) |
| RPS+ (ACTIVE cohort) | 1 (ratio) | age x position-group cohort, position multiplier applied outside | 0-250 | `prospx/index.html` (`_buildRpsPlusCache`) |
| wRC+ / ERA- / FIP- | 1 (ratio; the minus stats invert) | MLB league (industry) | none | external, displayed as-is |
| SC+ | 3 (100 + 10z) | side-matched active prospect pool | none | `statcast_plus.py` (`_SC_PLUS_PER_SIGMA`); the PROSPX JS fallback matches |
| CS+ | 3 (100 + 10z) | per-year college cohort | 40-160 | `collegesavant/app.js`, `collegesavant/pitcher_app.js` |
| aStuff+ | 3 (100 + 10z) | qualified AAA pool | none | `stuff_plus_aaa.py` |
| FVStuff+ | 3 (100 + 10z) | active prospect cohort | 0-250 | `storage.py` (`_index_plus`) |
| Cmd+ | 3 (100 + 10z) | active prospect cohort | 0-250 | `storage.py` (`_index_plus`), no glossary entry yet |
| pStuff+ | 3 (100 + 10z) | the pitcher's MiLB level | 0-250 | `storage.py` (`_compute_peripheral_stf_plus`); leaderboard JS reconciled onto it 2026-07-29 |
| KRP+ | 3 (100 + 10z) | live eFV pitcher pool | none (de-clamped 2026-07-24b) | `efv_score.py` (`_krp_display_raw`) |
| DvM+ / 7yDvM+ / FVDvM+ | 3 (100 + 10z) | the 30 orgs | none | `storage.py` |
| per-tool DvM+ | 3 (100 + 10z) | the 30 orgs, per tool | none | `storage.py` |
| ToolDvM+ | 3 (inherited) | position-importance-weighted mean OF already-anchored per-tool values | none | `storage.py` |
| $DvM+ | 3 (100 + 10z), eFV-TIER anchored | the player's current eFV tier, not the league | none (the 40-160 clamp was removed 2026-07-29) | `storage.py` (`_dollar_dvm_by_key`) |
| Org $DvM+ | 3 (inherited) | mean of the org's actives' $DvM+ | none | `storage.py` |
| RIV+ | 3 (100 + 10z) | relievers | none | `rem_plus.py` (`RIV_SCALE = 10`) |
| DEM+ | 3 (100 + 10z) | fielders with 200+ defensive innings, shrunk rates | none | `dem_plus.py` |
| Team DEM+ | 3 (inherited) | innings-weighted mean of a club's non-catcher DEM+ | none | `dem_plus.py` (`team_defense`) |
| AP+ (Advancement Pace+) | 3 (100 + 10z) | experience-year peer group | `ap_plus` uncapped (model), `ap_plus_display` capped 70-130 | `advancement_pace_export.py` |
| Farm tiebreaker | 3 (100 + 10z) | the 30 orgs | none | `storage.py` (`farm_tiebreaker`) |
| tjStuff+ | 3 with an INVERTED sign (100 - 10z) | external MLB per-pitch model | 20-180 | `mlb_stuff_plus.py` |
| RPS+ (DRAFT cohort) | 4 (100 + 15z) | the draft class | 60-140 | `draft_export.py` |
| RPS+ (OVERSEAS cohort) | 4 (100 + 15z, sign flipped for pitchers) | the international cohort | 60-140 | `overseas_export.py` (`_cohort_plus`) |
| Tool+ | 4 (100 + 15z) | draft class or overseas cohort | 60-140 | `draft_export.py`, `overseas_export.py` |
| DS+ (Draft Stock+) | 5 (linear percentile) | consensus board rank mapped to about 70-130, plus a college nudge of about 6 | clamped | `draft_export.py` |
| TBS (prospect) | 5 (linear percentile) | signals each normalized to 0-1, renormalized, then health and upside MULTIPLIERS | 0-130 | `prospx/index.html` (`_tiebreakerScoreRaw`) |
| PD+ | 6 (additive percentage points) | BB% minus K% gap to the level, blended 0.7 / 0.3 with the PSel grade | 0-250 | `prospx/index.html` (`_disciplinePlusRaw`) |
| POW+ | mixed: ratio legs + an additive grade map, reliability-weighted | level ISO ratio, Statcast, Power grade | 0-250 | `prospx/index.html` (`computePowerPlus`) |
| HIT+ | mixed: ratio legs + an additive grade map, reliability-weighted | level rates, zone tracking, Hit / BatCtrl grades | 0-250 | `prospx/index.html` (`computeHittingPlus`) |
| CollegeSavant Stuff+ | external ratio (100 = college-average xRV, 0 = worst observed) | college TrackMan season pool | none | vendored payloads, `collegesavant/pitcher_pitch_data_*.js` |

## Consequences worth remembering

- **The Stuff+ name is overloaded six ways.** CollegeSavant Stuff+ (external ratio, measured SD
  about 23 to 24, observed range 3.4 to 185.4), Will's 2026 formula-anchored vintage (same
  formula family, different fit), aStuff+ (100 + 10z), tjStuff+ (100 - 10z, inverted, clamped
  20-180), pStuff+ in Python, and pStuff+ in the leaderboard JS. A CollegeSavant 130 is barely
  plus; an aStuff+ 130 is elite. Never put two of them in one column.
- **A tighter clamp is not a tighter distribution.** CS+ clamps at 40-160 ($DvM+ did until 2026-07-29), the draft
  and overseas 15z metrics clamp at 60-140, KRP+ and SC+ do not clamp at all. The clamp changes
  what the extremes can print, not what a point means.
- **$DvM+ is anchored inside an FV tier**, not across the league, so it answers "is this
  prospect's grade moving faster than his tier's?" (it reads no dollars) and never "is he worth more than that
  prospect?".
- **RPS+ carries three scales under one label** (ratio for actives, 15z for draft, 15z for
  overseas), which is why the three cohorts are never pooled into a single RPS+ ranking.
- **PD+ is the only additive-percentage-point metric in the family.** PD+ 110 means ten
  percentage points of walk-minus-strikeout edge over the level, which is enormous; SC+ 110
  means one standard deviation, which is common.
- **When a display value and a model value must differ, give them different names.** AP+ does
  this correctly: `ap_plus` is the uncapped model value and `ap_plus_display` is the 70-130
  capped one, two fields, no ambiguity. KRP+ takes the other route, one name with the
  divergence written into the glossary entry and the registry row: the eFV model feature zeroes
  the double-bad quadrant, the display pill signs it negative. Both are acceptable. A third
  option, letting them differ silently, is not.

## Governance

Every in-house metric in this table has a row in `data/model_registry.json` and a documentation
decision in `MODEL_GLOSSARY` (`test_methodology_freshness.py`), with three stated exceptions:
`Cmd+` (no glossary entry yet), `OPS+ (vs level)` (a level-relative rate feeding other indices
rather than a surface of its own), and the industry metrics `wRC+ / ERA- / FIP-`, which are
displayed as their publishers compute them.

The display indices carry verdict `unvalidated` with a null eval artifact by design:
`model_registry.validate()` forbids an unvalidated row from carrying an artifact and forbids a
validated row from lacking one, and a descriptive index with no forward backtest must not be
dressed up with an invented one. Registering them `unvalidated` is the accurate statement, not
a demotion.

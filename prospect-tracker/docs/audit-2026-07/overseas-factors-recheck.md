# Overseas factors re-check: hitter wRC+ and CPBL/Cuba (review-queue item 8)

Lane OVERSEAS, 2026-07-02. Scoped, read-only investigation. No code changed.
Question: what still blocks the overseas hitter wRC+ translation factor and the
CPBL/Cuba factors that the phase-4b refit left as priors, and has any blocker
dissolved now that more data is on hand.

## Verdict

- Hitter wRC+ factor, NPB: READY-TO-RUN. The blocker as originally written
  (needs per-season league offense context, a register league-page scrape) has
  DISSOLVED. FanGraphs publishes park-and-league-adjusted wRC+ directly for NPB
  and KBO seasons and for actual MLB seasons on a single player page, and the
  project already has a FanGraphs player-page parser (overseas_stats.py) that
  reads wRC+ and drops the projection rows. No separate league-context scrape is
  needed because wRC+ already bakes league and park context in. NPB hitter n=6
  matches the K% delta factor (also n=6) that this same refit already shipped, so
  the sample clears the project's own shipped-precedent bar under the k=8 shrink.

- Hitter wRC+ factor, KBO: READY-TO-RUN but marginal-n. FanGraphs coverage lifts
  the KBO hitter cohort from the n=1 that blocked it (only Hyun Soo Kim resolved
  under the current B-Ref path) to roughly n=3 to 4 (adds Ha-Seong Kim and Jung
  Hoo Lee, both currently dropped as no_foreign_line, plus Byung Ho Park). Ship
  only under shrink with the thin-n disclosed, or keep the KBO prior if the LOO
  gate below does not clear.

- CPBL factor: BLOCKED-ON-cohort-existence. This is not an acquisition problem.
  There are effectively zero direct CPBL-veteran to MLB transitions in the
  2015-2026 window. CPBL is a destination for ex-MLB and ex-NPB arms, not a
  source. There is no matched-pair data to buy because the transitions do not
  happen. Keep the scaled prior, documented as prior-only.

- Cuba factor: BLOCKED-ON-Serie-Nacional-source-and-defection-gap-rule.
  FanGraphs does not publish Serie Nacional wRC+, B-Ref register coverage of
  Serie Nacional is unreliable, and the typical one-to-two-year defection gap
  between a player's last Cuban season and his MLB debut contaminates the
  "final foreign season strictly before entry" rule the harness depends on. Keep
  the prior. Low priority.

## What each factor needs

### Hitter wRC+ factor

The shipped form is a multiplier: MLBe wRC+ approximately equals league wRC+
times hitter_wrc_factor (overseas_export.py:159 for NPB 0.87, :185 for KBO 0.81).
To refit it credibly the harness needs, per transition hitter:

1. Final qualifying foreign-season wRC+ (the league-relative, park-adjusted
   offense rate in NPB or KBO, not raw OPS).
2. First MLB-season wRC+ at adequate exposure.

The current refit (tools/refit_overseas_factors.py) cannot produce these because
its two sources carry neither number:

- Foreign side is the B-Ref register page, which exposes only
  onbase_plus_slugging (raw OPS). Verified: the Suzuki register page has 43
  onbase_plus_slugging cells and zero league-relative OPS-plus or wRC cells.
- MLB side is StatsAPI (milb_history sport-1 cache), which carries OPS but not
  wRC+.

So the harness measures the raw OPS ratio (data/overseas_translation_eval.json:
NPB 0.802, KBO 0.819) as an analog and retains the wRC+ prior. The raw OPS ratio
is the wrong quantity for a wRC+ multiplier because it conflates the talent
haircut with the change in league run environment and park. That conflation is
exactly the "needs per-season league offense context" note in the registry row
and in the refit docstring.

### CPBL and Cuba factors

Same two inputs (final foreign wRC+ or ERA, first MLB wRC+ or ERA) but the
binding need is a cohort at all. The TRANSITIONS ledger
(tools/refit_overseas_factors.py:76-115) has 16 NPB and 12 KBO entries and zero
CPBL and zero Cuba entries. CPBL and Cuba factors in overseas_export.py:194-215
are hand-set priors with no measured basis.

## What exists in the caches today

- data/overseas_translation_eval.json (the phase-4b artifact, generated
  2026-06-11): 34 listed transitions, 28 resolved. NPB pitchers n=15, NPB hitters
  n=6, KBO pitchers n=6, KBO hitters n=1. Carries the full per-player foreign and
  MLB stat lines used for the ERA and K% refit.

- .cache/bref_register/ : 33 register pages plus 33 search pages for the exact
  transition cohort, dated 2026-06-11. These are OPS-only for the foreign side.

- .cache/fg_player_*.html : 181 FanGraphs player pages from the overseas board
  build. These are the key asset. Verified in-repo that FanGraphs publishes
  per-season wRC+ for both foreign and MLB rows on one page:
    - KBO hitter, Do Yeong Kim (sa3018059): KBO 2022 wRC+ 89, 2023 129, 2024 168.
    - NPB hitter, Shugo Maki (sa3063879): NPB 2021 wRC+ 145 ... 2024 152.
    - KBO graduate, Jung Hoo Lee (33824): KBO 2017-2023 wRC+ 112 to 178, then
      actual MLB 2024 wRC+ 83 and 2025 wRC+ 107 on the same page, level-labeled
      KBO / MLB, with ST and PROJ rows present and skippable.
    - KBO graduate, Ha-Seong Kim (27506): KBO 2020 wRC+ 144 (final foreign),
      MLB 2021 wRC+ 71 (first MLB), full career on one page.

- overseas_stats.py already parses this exact page shape: HITTER_KEYS maps
  "wRC+" to wrc_plus (overseas_stats.py:102), _pick_dashboard_table reads the
  Level column, and refresh_overseas_stats drops ROS/PROJ/ST synthetic rows
  (overseas_stats.py:258). scrape_fg_player_stats(fg_player_id) returns the
  per-season rows ready to use.

## What is genuinely absent

- fg_player_id for the graduated cohort hitters. Most are not on the current
  board or carry a null FG id: Seiya Suzuki and Masataka Yoshida both have
  fg_player_id None; Ohtani, Tsutsugo, Akiyama, Murakami, Byung Ho Park, and
  Hyun Soo Kim are not board rows at all. Resolving about 7 to 10 FG ids is the
  only new acquisition the NPB and KBO wRC+ refit needs, and it is the same
  owner-extendable curated-ledger pattern the TRANSITIONS list already uses.

- A Serie Nacional (Cuba) per-season stats source with league context or wRC+.
  FanGraphs does not carry it. B-Ref register coverage is spotty. Genuinely
  absent.

- A CPBL to MLB transition cohort. Genuinely absent because the transitions do
  not exist, not because the data is hard to fetch. FanGraphs does carry CPBL
  wRC+ (the scraper's level set already includes CPBL and TWN), so if a CPBL
  veteran ever signs an MLB deal the metric side is ready; only the cohort is
  missing.

- A historical foreign pitch-velocity source (fb_velo_delta). Unchanged, still
  absent. Out of scope for this item but noted so the registry row stays honest.

## Blocker status

| Factor | Was blocked on | Status now |
|---|---|---|
| NPB hitter wRC+ | league-relative wRC+ for foreign and MLB seasons | DISSOLVED via FanGraphs; refit is ready to run |
| KBO hitter wRC+ | same, plus n=1 | wRC+ dissolved; n rises to about 3-4; marginal, ship only if the LOO gate clears |
| CPBL (all) | no transition cohort | STILL BLOCKED; cohort does not exist |
| Cuba (all) | no reliable source, defection gap | STILL BLOCKED; needs a Serie Nacional source and a gap rule |

## Ready-to-run experiment spec: NPB (and KBO) hitter wRC+ refit

Pre-registered here, not run. Follows the same discipline as the shipped ERA and
K% refit: curated cohort, weighted ratio, shrink toward the incumbent, coverage
counted, one eval artifact, registry row update.

Design:

1. Extend the TRANSITIONS ledger with an optional fg_id per hitter row (curated,
   owner-extendable). For the NPB hitters (Ohtani, Tsutsugo, Akiyama, Suzuki,
   Yoshida, Murakami) and the KBO hitters (Byung Ho Park, Hyun Soo Kim, Ha-Seong
   Kim, Jung Hoo Lee) resolve the FanGraphs id once, by FG search or by hand.

2. For each hitter, scrape the FanGraphs page with the existing
   overseas_stats.scrape_fg_player_stats. Take the final qualifying foreign row
   strictly before mlb_entry_year (Level in {NPB, KBO}, PA at least MIN_FOREIGN_PA
   = 150) as the foreign wRC+, and the first row at Level MLB in the entry year or
   the year after with PA at least MIN_MLB_PA = 100 as the MLB wRC+. Skip ST, ROS,
   and PROJ rows (the scraper already does).

3. Measured factor per league = PA-weighted ratio of means, weight
   min(foreign PA, mlb PA), matching the ERA factor's ratio-of-means construction
   so a single extreme season cannot dominate. Shrink k=8 toward the incumbent
   prior (NPB 0.87, KBO 0.81), matching SHRINK_K in the existing refit.

4. Report resolved / dropped counts per league, the same accounting block the
   artifact already writes.

Gate (all must hold; marginal is a fail):

1. Coverage: at least 5 resolved NPB hitters with both a qualifying foreign
   wRC+ line and a qualifying MLB wRC+ line. KBO reported honestly; ship KBO only
   if at least 3 resolve, otherwise KBO keeps its prior.

2. Leave-one-out validation beats the prior. For each hitter, compute the factor
   from the other hitters and predict MLBe wRC+ = factor times that hitter's
   foreign wRC+; compare to his realized first-MLB wRC+. The fitted-factor LOO
   MAE must be lower than the incumbent-prior LOO MAE on the same set. If it only
   ties, keep the prior (the null wins ties).

3. Stability. Bootstrap the PA-weighted ratio with SEED=8 (documented; the only
   stochastic step; 2000 resamples). The shrunk factor's bootstrap band must
   exclude neither being a pure no-op nor an implausible value; report the band.
   Leave-one-out refactoring must not swing the shipped factor by more than about
   0.05, or the factor is n-unstable and stays prior.

4. Functional-form caveat is surfaced, not hidden. Every transition hitter is an
   elite who earned a posting, so the measured MLB-over-foreign wRC+ ratio is an
   elite-cohort ratio applied as a global multiplier down to wRC+ 100. This is the
   same elite-selection extrapolation the shipped pitcher ERA multiplier already
   accepts, so it is allowed, but the eval must state it and the registry note
   must carry it. n is far too small to fit a slope-plus-intercept form, so the
   multiplier stays.

Ship path on pass: update overseas_export.LEAGUE_CONTEXT NPB (and KBO if it
cleared) hitter_wrc_factor with the eval as provenance; refresh
data/overseas_translation_eval.json to carry the wRC+ factor block and its LOO
and bootstrap numbers; update the overseas_translation registry row from
"wRC+ retained as prior" to the measured champion; regenerate
data/overseas_timeseries.json so the Overseas tab MLBe wRC+ lines
(overseas_export._mlb_translate) reflect the new factor. Expected-CHANGED tracked
payload: data/overseas_timeseries.json (wrc_plus_mlbe fields only). On fail or
marginal: loss-ledger entry in the eval, no ship, prior retained.

Effort: small. The only new work is curating up to ten fg_ids and adding a
FanGraphs branch to the refit that reuses the existing scraper; the weighting,
shrink, and artifact plumbing already exist.

## Cheapest acquisition path for the still-blocked items

- CPBL: none available and none worth building pre-Beta. The cohort does not
  exist. Keep the prior, and if it must be defended, scale it from the measured
  NPB and KBO factors the way NPBF is scaled (overseas_export.py:170-179), with a
  note that it is prior-only. Revisit only when a CPBL-veteran MLB signing
  actually occurs; the FanGraphs metric side is already wired for CPBL.

- Cuba: not cheap. It needs two things the project does not have. First, a
  reliable Serie Nacional per-season source (FanGraphs does not carry it; a
  specialist source or manual curation would be required). Second, a defensible
  rule for the defection gap, because the last competitive Cuban season is often
  one to two years stale by MLB debut and several notable imports (Robert,
  Moncada, Arozarena) reached MLB through the affiliated minors rather than a
  clean league-to-league jump, so they are not clean matched pairs. Recommended
  disposition: keep the prior, mark it prior-only in the registry, and leave it
  out of scope for Beta.

## Files referenced (all read-only)

- tools/refit_overseas_factors.py (the refit harness and TRANSITIONS ledger)
- overseas_export.py:135-216 (LEAGUE_CONTEXT factors) and :219-254 (_mlb_translate)
- overseas_stats.py:95-114 (HITTER_KEYS wRC+ mapping), :181-199 (scraper),
  :258 (drops ROS/PROJ/ST)
- data/overseas_translation_eval.json (phase-4b artifact)
- data/model_registry.json (overseas_translation row, lines 298-307)
- .cache/bref_register/ (OPS-only foreign pages) and .cache/fg_player_*.html
  (wRC+ pages, verified above)

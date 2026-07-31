# eFV Data-Source Audit (2026-07-24)

Portfolio-allocation pass on external data for eFV (and PROSPX / CollegeSavant).
Every URL in this audit and in `data/sources/registry.yaml` was hit live this
session with recorded HTTP evidence and a saved sample under
`data/sources/samples/` (135 files, 61 MB). Discovery ran as four parallel tier
agents (A/B, C, E/F/G, D/H/I); scoring is reproducible via
`scripts/score_sources.py`. Phase-0 baseline is `docs/CURRENT_INGESTION.md`.

The headline is not a source. It is a diagnosis: **eFV's binding constraint is
identity resolution, not data availability.** The largest hole in the feature
matrix (MiLB production, 47% covered) collapses on exactly the cohorts with
resolved labels, and its ceiling equals the mlbam-id coverage. Two eFV
experiments were run to the number this session (below); the source registry is
what remains after that finding reorders everything.

## Ranked shortlist (weighted score / engineering-day)

| # | source | tier | net | eng-d | ratio | join | legal | what it uniquely adds |
|---|---|---|---|---|---|---|---|---|
| 1 | **tj_surgery_list** | I | 3.76 | 1.0 | 3.76 | mlbam 99% | low | deep-history (1974-2026) injury/surgery; un-starves the injury ledger |
| 2 | **draft_statsapi** | D+H | 3.54 | 1.0 | 3.54 | mlbam 100% | low | official slot (pickValue) + signingBonus 2017+ |
| 3 | **statsapi_venues_meta** | F | 3.19 | 1.0 | 3.19 | venueId 100% | low | park elevation/dims/azimuth for MiLB normalization |
| 4 | **mlb_pipeline_graphql** | C | 3.60 | 1.5 | 1.82 | mlbam 99% | ambig | NATIVE grade vintages 2011-2026 (de-leak the top feature) |
| 5 | **statsapi_sport22_college** | E | 3.48 | 2.5 | 1.24 | mlbam ~100% | low | amateur players WITH an mlbam id (solves the join) |
| - | statsapi_sport17_23_leagues | D+G | 2.94 | 2.0 | 1.34 | mlbam 95% | low | AFL + Caribbean winter + LMB reps |
| - | pitchiq_prospecttilt | B | 3.07 | 1.5 | 1.13 | mlbam 92% | ambig | MiLB Filth+/Stuff+ model to Complex/DSL |
| - | statsapi_abs_challenge | F | 3.27 | 3.5 | 0.76 | mlbam 100% | low | 2026 ABS challenge per-pitch signal (new) |
| - | prospect_savant | A | 2.82 | 2.5 | 0.68 | mlbam 100% | ambig | AAA percentiles + bat-tracking + AFL/ST (2023+) |

`awards_statsapi` (ratio 2.92) and `intl_bonus_pools` (1.84) score high on the
raw ratio but are deliberately kept OFF the shortlist: awards are downstream of
WAR (the eFV label itself) and intl pools have no player join. The ratio metric
over-rewards cheap-but-tangential endpoints; the shortlist is filtered to
eFV-relevance >= 3.

Recommended set (top 5) total engineering cost: **~7 engineering-days.**

## The top 5, one paragraph each

**1. Tommy John surgery list.** A community-maintained Google Sheet, exported as
CSV, with a native `mlbamid` column at 99% fill and surgery dates back to 1974.
This is the only injury source with both deep history and a clean join, which
matters because the owner's own 2026-07-24 injury-history experiment ledgered
`COVERAGE-STARVED`: StatsAPI IL tracking effectively begins 2026-06, so
resolved-cohort IL coverage is ~0. The TJ list lifts that to 92 resolved pitcher
rows with a pre-decision signal. It was tested this session (see below) and is a
registered candidate, not yet a ship.

**2. StatsAPI draft.** `/api/v1/draft/{year}` carries the official `pickValue`
(slot) and actual `signingBonus` from 2017 on, and pick/team/school back to 1965,
all keyed on mlbam. It fills the matrix's thinnest priors (`bonus_usd` 28%,
`pick_overall` 40%) from the authoritative source rather than a scrape, and it
absorbs the separate "slot values" candidate entirely. The eFV lift is bounded by
the same id wall on old rows and by the lean-sweep finding that pick/bonus are
noisy, so this is a data-quality and PROSPX win more than an eFV rank win.

**3. StatsAPI venues.** One hydrate call returns elevation, lat/lon, azimuth, and
field dimensions for every MLB and MiLB park, joined on `venueId` which is already
linked to our games. These are the physical drivers behind the self-built
`milb_park_factors.json`, and the cheapest item on the board. It does not provide
weather; that still needs a lat/lon-keyed weather API.

**4. MLB Pipeline vintage boards.** `data-graph.mlb.com/graphql` is an open,
unauthenticated endpoint, and `getPlayerRankingsFromSelection(slug:"sel-pr-YYYY-top100")`
returns point-in-time boards for 2011 through 2026, joined on mlbam (verified
live: the 2021 board returns Franco/Rutschman/Torkelson with ids). We already
ingest Pipeline grades; the new capability is the native vintage layer, which is
what makes historical grades training-eligible without leakage and enables the
grader-calibration in the runbook (fit each outlet's bias and precision against
realized WAR). The only gap is the hidden tool-grade subfield names, ~0.5 day of
XHR capture.

**5. StatsAPI college (sportId 22).** The single most useful discovery for the
amateur join problem, and it is an endpoint we already own. College, Cape Cod,
Appalachian, and Draft-League players carry real mlbam ids under sportId 22, so
CollegeSavant and eFV's recent-draftee prior can join cleanly instead of
name-matching (our current `college_stats.py` is name-only, ~60-80%). Coverage is
the prospect-tracked subset, not the full ~10k D1 population, which is a coverage
ceiling rather than a join failure.

## eFV experiments run to the number this session

The user asked to test the acquired data against eFV. Two clean experiments were
run; both are honest, and one is a NO-SHIP that was reverted to protect the
shipped model.

### Experiment 1 - identity resolution + MiLB backfill (NO-SHIP, reverted)

Premise: the matrix's MiLB-production features are 0% covered on 2011-2014 debut
cohorts, 3-61% on 2015-2018, and those old cohorts are exactly the ones with
fully-resolved 6-year WAR labels. StatsAPI serves pre-2014 MiLB stats richly
(verified: AA hitting ~1000+ player-seasons every year 2005-2013); the local
cache stopped at 2014 by config and the builder loop hard-stopped at 2013.

Execution: warmed the milb cache to 2005-2013; resolved 735 missing mlbam ids for
old debuted rows via `/people/search` validated on debut-year + birthDate (0
ambiguous, 1 correctly rejected; spot-checks confirmed against StatsAPI ground
truth, including separating Syndergaard from Ryne Stanek); lowered the builder
floor; rebuilt. MiLB coverage on 2011-2018 cohorts went from 0-61% to 98-100%
(matrix-wide 47% -> 60%).

Result: the forward-chained model REGRESSED. On the two debuted cuts where the
baseline is unchanged (identical test sets), deterministic ridge fell
0.3854 -> 0.3678 on `debuted_km`, the shipped blend 0.3787 -> 0.3705, and
`debuted_resolved` fell across the board; MAE rose everywhere. Per-year is mixed
(2021 up, 2020/2022 down), the signature of no robust signal. The frozen model was
co-adapted to treat old rows as feature-neutral (`milb_missing` / `milb_unavailable`),
and old-era production is era-shifted; filling it shuffles predictions without net
gain and fails the both-metrics gate.

Salvage arms (execution round, both tested and reverted): (a) adding a `cohort_era`
feature does NOT recover the loss - ridge 0.3645, marginally worse than the
no-control backfill, because forward-chaining always tests on eras unseen in
training, so a linear era term extrapolates; (b) restricting the backfill to the
era-proximate 2015-2018 cohorts (dropping the 2011-2014 all-survivor rows that go
0% to 100%) recovers to NEUTRAL - the shipped blend returns to exactly 0.3787, ridge
to 0.3775. So the 2011-2014 era-distant survivor cohorts caused the regression, and
the best achievable outcome is neutral, not a gain.

Disposition: NO-SHIP, reverted (coverage back to 904, ridge back to 0.3854,
verified). The 735 resolved ids are kept as a verified asset at
`data/sources/mlbam_id_overrides.json` (resolver at `tools/efv_oldcohort_id_resolve.py`).
Landing them into debuts.json was tested and deferred: it moves the shipped blend
only -0.0005 (neutral) but shifts served eFV numbers with no rank gain, so it would
force a golden restamp for nothing. They stay a standalone asset that display/join
surfaces can consult without touching the training path.

### Experiment 2 - TJ surgery history as a pitcher feature (candidate, not shipped)

The TJ list gives 92 resolved pitcher rows a pre-decision surgery signal (vs 0
from StatsAPI IL). The cheap decisive pre-check: among resolved pitchers, does
`tj_pre` carry conditional signal on WAR after controlling for consensus FV? It
does, at z~+2.59, but the sign is survivorship-POSITIVE: post-TJ pitchers who
still debuted overperform their grade (scouts over-discount TJ arms who prove
healthy). The clean test is a censored full-pool eval where TJ washouts count as
0-WAR busts, but bust coverage is gated by the same id wall, and running it with
asymmetric id coverage would reproduce the spurious "has-id correlates with
survival" leakage seen in Experiment 1.

Execution round: `tj_pre` was wired into the pitcher model (as-of, native + resolved
ids; 22% of the 2020-2023 test cohorts covered) and forward-chained. Result: no
clear lift - `debuted_km` blend +0.0011 (noise), ridge -0.0057, and full-pool no
help. The survivorship-positive signal (z+2.59) does not survive as an OOS rank gain
because consensus FV already prices most of it and the risk direction (busts) is
under-covered. Disposition: honest non-ship, reverted. TJ remains a real,
deep-history injury source (data/tj_surgery.json landed) whose best use is the
survival-labeling backbone of the surrogate program, not a standalone feature.

## Execution round: five sources built (local, uncommitted, owner-integration deferred)

Each is a standalone module with a disk cache, an offline join/feature helper, and a
passing offline test; none is wired into `run_monthly` / `build_site` / the model.

- **`tj_surgery.py`** -> `data/tj_surgery.json`: 2,711 surgeries, 2,511 players, 99.4%
  native mlbam, 1974-2026. `tj_features(mlbam, cutoff)` is as-of/leakage-safe. 6 tests.
- **`draft_bonus.py`** -> `data/draft_bonus_slot.json`: 7,009 mlbam across 2017-2026,
  official slot + signing bonus. Cross-check: near-zero NEW fill on the current matrix
  (its missing-bonus rows are IFAs or pre-2017 draftees), so the value is forward-looking
  (5,262 signed bonuses ready as the 2021-2026 classes debut). 9 tests.
- **`venue_meta.py`** -> `data/venue_meta.json`: 228 parks, lat/lon + elevation +
  dimensions + azimuth (Sahlen Field AAA: 585 ft, dims, azimuth 157). **`amateur_leagues.py`**
  -> `data/amateur_leagues.json`: 17,883 players across sportId 22/17/23, 100% native mlbam,
  `playerPool=all`. NPB/KBO re-confirmed empty and pinned by test. 10 tests.
- **`pipeline_vintage.py`** -> `data/pipeline_vintages.json`: point-in-time boards 2015-2026,
  100% mlbam. GRADE SUBFIELDS CRACKED via the GraphQL error oracle: `gradesHitting` /
  `gradesPitching` = `{key,value}` lists (`Overall` = FV; Franco 2021 = 80/60/55/55/50/70).
  20-80 tool grades populated 2015-2021 (a subset per year) - which is exactly the pre-debut
  vintage window the 2017-2023 training cohorts read. 6 tests.

## Rejected on legal / access grounds (with the specific clause)

- **Prospects Live** - working public Ghost API with dated per-player tool grades,
  but `robots.txt` declares Cloudflare `Content-Signal: ai-train=no` plus
  `Disallow: /` for GPTBot / Google-Extended / meta-externalagent, an express
  reservation of rights citing the EU DSM Directive. Licensing path only.
- **PitchProfiler** - `/api/scouting/*` returns 401, promotions reveal a Patreon
  paywall, and robots sets `Content-Signal: ai-train=no` + `Disallow: /` for
  ClaudeBot. Paid + gated + no-train.
- **FanGraphs (board and Stuff+)** - Cloudflare 403 on both the HTML and the JSON
  API, via curl and WebFetch. robots permits the board; Cloudflare is a deliberate
  technical control, so scripted access is a ToS breach. Manual CSV drops stay the
  only path. Stuff+ is also MLB-only (no MiLB signal).
- **Baseball America** and **The Athletic / Keith Law** - paid, and BA is
  additionally Cloudflare-blocked. Both are the most method-independent graders
  (pure in-person scouting), so they are the best LICENSING targets for pre-debut
  calibration, not scrape targets.
- **Baseball-Reference Register** - broadest foreign/amateur coverage (CPBL, NPB,
  KBO, Cape Cod, indy), but the Sports-Reference ToS explicitly restricts
  scraping and bulk use, and there is no mlbam id. Documentation only.
- **Perfect Game / PBR** - the showcase TrackMan metrics that matter are
  subscription-gated, and neither carries an mlbam id for HS players.

## Rejected as duplicate / unjoinable / dead (verified, not assumed)

- `bdfed.stitch` host: live 200 but the same data as StatsAPI `/stats` (throughput
  only, zero new information).
- `people` hydrate roster mechanics: only the 40-man boolean is new; options-remaining
  and the Rule-5 clock are not exposed by StatsAPI at all.
- OpenBiomechanics (Driveline): repo is live and downloadable, but subjects are
  anonymized with no mlbam or name, so it is unjoinable. Reference only.
- NPB / KBO sportIds (31 / 32): exist in the sports list but `/stats` returns
  `totalSplits: 0`. Listed but unserved.
- Pointstreak: 301-redirects to a marketing homepage (dead).

## The single biggest coverage hole still unfilled

Not a source, a structure: **the label-horizon trap.** The cohorts with the best
measurement features (MiLB Statcast 2023+, bat-tracking, pitch models) are exactly
the cohorts whose 6-year outcomes are not yet resolved, and the resolved cohorts
(2011-2018) predate that measurement. Experiment 1 confirms that even filling
*ordinary* deep-history features on the resolved cohorts does not lift the model.
No public scrape closes this; it is closed by time, by short-horizon surrogate
labels (reached-MLB, survived-to-AA, MLE at the next level), and by a two-stage
measurement -> surrogate -> WAR design. That surrogate-label program, not another
source, is the highest-value next investment.

## Total engineering estimate for the recommended set

- tj_surgery_list + draft_statsapi + statsapi_venues_meta: ~3 days (all cheap
  StatsAPI-or-CSV, native joins).
- mlb_pipeline_graphql (incl. tool-grade subfield capture): ~2 days.
- statsapi_sport22_college: ~2.5 days.
- **Recommended set total: ~7 engineering-days**, of which the eFV-lift-bearing
  work (TJ censored eval, Pipeline vintage calibration) is ~3 days and the rest is
  data-quality / PROSPX / CollegeSavant breadth.

# Master Plan 2026-07-30: the nine owner asks - defense-aware conversions, MLB product uplift, and the next eFV accuracy round

Executor: Claude Opus 5. Author: Fable, 2026-07-30 (evening), written after the
outcome-calibration program (commits de14020..7a4f61a) landed locally. Everything below
is grounded in a 7-lane research sweep of the CURRENT tree; every number cited was pulled
from a committed artifact or live data file today. Repo root for paths: `prospect-tracker/`.

Owner directives this plan implements, verbatim in intent:

1. More defensive stats (arm strength, range/OAA, DRS, per-position history with
   sample-size calibration) into the Alchemy Lab for position-player conversions.
2. Surface all new MLB data on MLB player cards; rework MLB Projections and MLB Free
   Agency tables to the PROSPX standard (cleaner rows, no cramping, sortable incl. rank);
   uplift MLB module lists and player detail pages generally.
3. Improve starter/reliever/hitter leaderboards; include WAR/PA+ and WAR/IP+; adjust
   HEM+/SEM+/REM+ for sample size "to some degree".
4. Accuracy-weight tool grades grounded in outcomes per the ingested industry framework;
   into Tools+, each displayed grade, and eFV's tool consumption.
5. Brayden Taylor / Enrique Bradfield Jr / similar older-mediocre prospects out of
   top-100-grade territory, without shipping a loss.
6. Franklin Arias to #1 if achievable without shipping a loss.
7. Why are WAR/PA+ and WAR/IP+ so compressed (Judge "only 25% above average")? Verify
   optimal measurement and implementation.
8. Why is eFV weak at ~FV50? Improve eFV to win across all cohorts/lanes without
   Spearman/AUC losses; improve AUC further.
9. Updated eFV prospect-valuation-curve artifact.

Plus the standing riders: polish the site, fix bugs found along the way, improve any
model/metric where a gated win exists.

---

## EXECUTION STATUS (updated 2026-07-30 late evening)

**DONE and PUSHED** (main `b4b1f67`, beta `f07cf9c`, trees byte-identical):

- **Phase 0, all 8 runbook steps.** Data stability verified by two readings; the box's
  churn committed as its own pipeline-regen commit after adjudicating
  `wire_fv_first_seen.json` (1,205 unchanged, 60 re-dated against a real grade change,
  zero re-dated without one, so the ledger's contract was working); ingest nulled the
  fabricated BA FV on all 41 rows with the 7 orphans keeping identity; TWO export passes
  (the second because `overall_rank` lags `xfv.json` by one run by documented design, and
  across a basis change that lag is visible); three coordination points verified; golden
  restamped to `4f791d2f` from the regen output before pytest touched the tree; suite run
  serially; pushed main then beta via the `Sync beta to main@<sha>` full-tree snapshot
  (a fast-forward, NOT a force push - beta is an orphan ops branch and its 30 commits are
  intact).
  **ACCEPTANCE MET:** arias 60.4 rank 2, brayden_taylor 48.2 rank **125** (was 100),
  enrique_bradfield_jr 48.2 rank **127** (was 91). Ask 5 is delivered.
- **Lane C (asks 3 and 7).** `war_pa_plus_adj` / `war_ip_plus_adj` companion columns
  (arm-S shrink, mu/sd from the SHRUNK pool per the defect-C3 guard, pinned by a test at
  10.0 points per sigma), plus the 1yr percentile chip. Served effect: the raw hitter
  board is topped by a 121-PA line at 125; adjusted, the top five are all full seasons.
  Three glossary entries, three registry rows, MODEL_REGISTRY.md regenerated.
- **Lane A2.** DRS probed and measured UNREACHABLE from this box (HTTP 403 behind a
  Cloudflare interstitial in 50ms). Out of scope, documented, do not retry-loop.
- **Lane G.** Valuation-curve artifact rebuilt on the fresh regen and republished to its
  existing URL (`03e424cb`), keeping the established visual identity and adding the
  outcome-curve foundation, a live-board third view, and the $0-floor defect.

**Suite state at push:** 2,521 passed, 5 failed, 22 skipped, 1 xfailed. All five failures
are the documented expected reds (C5 inert anchor, michael_oliveto, team-outlook recenter,
$0-bottom-block tripwire) plus one NEW finding: `test_prospx_sort_a11y::
test_aria_sort_reflects_state_and_enter_resorts` fails ONLY inside the full suite and
passes in isolation and with neighbours, i.e. a test-isolation artifact from build
artifacts being dirtied mid-suite, not a product defect. Added to Lane H below.

**NOT STARTED:** Lanes A (conversion engine build), B (MLB frontend uplift), D (tool-grade
weighting), E (B3 level blend, repeat-level feature), F (pitcher FV50). These are the
multi-day gated engineering lanes; the plan below is their specification.

---

## 0. Ground rules (binding, carried forward + measured today)

All rules from `docs/master-plan-2026-07-29-efv-fa.md` section 0 and
`docs/master-plan-2026-07-30-fv-calibration.md` section 0 stand. Repeated here because
each one was violated at least once historically:

1. **One serial pytest run, orchestrator only, after lanes land.** conftest's session
   fixture (`conftest.py:148-187`) git-checkouts every tracked file the TESTS dirtied -
   a suite run concurrent with lane edits silently destroys them.
2. **The box writes data at unpredictable hours.** Documented window is ~00:30-04:00
   but mtimes today show writes at 08:42, 09:19, and 17:29. Never trust the clock; use
   the runbook's two-stable-readings check before committing data churn. Explicit paths
   only; `git add -A` is banned.
3. **Tree is source-clean right now.** All 70 modified files are generator/nightly
   output (50 data JSON, 17 regenerated HTML, 2 generated JS payloads, sitemap). Code
   commits must exclude them. One file needs adjudication before commit-or-discard:
   `data/wire_fv_first_seen.json` (append-only ledger with rewritten values - runbook
   step 2).
4. **Registry discipline:** a new `data/*_eval*.json` without a registry row turns the
   suite red. Loss rows: `verdict: deprecated` WITH artifact + MODEL_GLOSSARY entry in
   `test_methodology_freshness.py`; `unvalidated` REQUIRES `eval_artifact: null`.
   Regenerate MODEL_REGISTRY.md via `python tools/gen_audit_docs.py` in the same commit.
5. **Board-ordering changes** bump `storage.BOARD_RANK_BASIS_EPOCH`, restamp
   `BOARD_BASIS_FINGERPRINT` (current pin:
   `xfv_grade|scale=off|grademap=outcome_pooled@6dbe8353f3bb|roles=usage_both`), and
   update `PINNED_MIX` in `test_board_basis_coherence.py` in the same commit.
6. **Copy gates** on any user-facing prose: `python tools/strip_emdashes.py --check` and
   `python tools/copy_lint.py --check` from `prospect-tracker/` (both wrapped in-suite
   by `test_copy_gates.py`). FV/tool grades display CEILING; eFV and '+' Arkmetrics
   round to nearest.
7. **Golden restamp comes from a box production regen only**, never a post-pytest tree
   (`test_efv_export.py:488`).
8. **Never restamp a pin/band/golden purely to green the suite.** The expected residual
   red set after the Phase 0 regen is documented below; those reds are tripwires, not
   bugs.
9. **Frontend generation:** all module `index.html` shells are written by
   `build_site.py`; never edit them directly. PROSPX (`prospx/index.html`) is the one
   hand-maintained exception. `site.css` changes require bumping the MANUAL `?v=` pins
   in `prospx/index.html:57` and `collegesavant/index.html:27`.
10. **node is not installed** - JS labs run via `Code.exe ELECTRON_RUN_AS_NODE`.
11. **No push without explicit owner instruction**; after any push, sync beta via
    `push HEAD:refs/heads/main` (disjoint webmaster branch).
12. **eFV changes clear `docs/EFV_GATE_STANDARD.md`:** pre-registered gate doc BEFORE
    measuring, paired bootstrap + zero-information control + permutation null + >=4 time
    splits, pooled MDE95 ~0.017 hit / ~0.016 pit for feature work, lambda-shift floors
    0.0076-0.011 hit / 0.005-0.008 pit.

### Corrections to standing memory this plan encodes (trust these over older docs)

- **The surrogate-label program is SPENT.** `docs/SURROGATE_LABEL_PROGRAM.md:113-149`:
  executed 2026-07-24, NO-SHIP. Hitters sit at their label ceiling (oracle 0.312 does
  not beat KM 0.334); the pitcher oracle gap is a measurement artifact (zero-info
  controls capture 87-113% of headroom). Do NOT schedule it as the eFV lever; any memory
  or plan text recommending it is stale.
- **Lambda state:** hit 0.70 (hard re-select override, `efv_model.py:271`, revert=0.85),
  pit dynamic (served 0.54). The remembered "0.70/0.54 per-cohort" pair is per-SIDE;
  both per-cohort lambda labs are NO SHIP.
- **The FV50 weakness is pitcher-only.** Hit tier 50 is eFV's biggest per-tier WIN
  (+0.4594). Never "fix" the hitter side of this.

---

## Phase 0: serve the already-shipped answers (BLOCKING - run first)

**Why first:** 52 commits sit unpushed (last push 71ea151, 2026-07-19); every served
artifact is on pre-program box code. Two of the nine asks are ALREADY substantially
answered in the tree and invisible to the owner:

- Ask 5: age-penalty onset 23.0 (owner decision D2, `efv_score.py:597`, taken
  specifically about Bradfield) + the pooled outcome refit (c4adead) land Bradfield at
  48.1 FV / rank ~107 (paired capture, `docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md:
  321-331`) and Taylor computes to ~48.1 / outside the top 100. The served board still
  shows them #91 and #100 on the retired grade map.
- Ask 8's measurement basis (`data/xfv_scoreboard_eval.json`) is dated 2026-07-24 and
  must be regenerated before any per-tier claim is re-measured.

**Do:** execute `docs/efv-2026-07-30/REGEN_AND_PUSH_RUNBOOK.md` verbatim - its 8 steps:
(1) two-stable-readings data check, (2) adjudicate churn incl. `wire_fv_first_seen.json`
and commit as a pipeline-regen commit or discard, (3) ingest (BA fv=NULL + 7 orphans to
PROVISIONAL), (4) `python efv_export.py --all`, (5) verify the three coordination points
(fingerprint pin at `storage.py:4646`, `xfv_history_is_on_board_basis()` flips True,
side-mix band holds), (6) golden restamp from THIS regen, (7) full suite serially,
(8) push main + sync beta - step 8 only on owner go-ahead.

Also in this phase, same regen: `python tools/efv_scoreboard.py` (it writes; refreshes
the per-tier table this plan's Lane F reads), and re-run `pal_export.py` (served
`data/pal.json` predates the staged watch schema of 23a7f44 - `prospect_watch_rule` key
absent).

**Expected residual reds after Phase 0 (do not fix):** history tilt-gap xfail (417
tails), C5 inert-anchor tripwire, $0-bottom-block calibration tripwire
(`test_value_framework.py:82-94`), michael_oliveto (heals on identity rebuild), and
team-outlook recenter (REAL, owed to Lane H - do not widen the bound).

**Acceptance:** served ranks/grades for franklin_arias (expect ~#2 / 60.3),
enrique_bradfield_jr (~107 / 48.1), brayden_taylor (expect high-40s FV, outside top
100 - his exact rank has never been captured; record it) match the paired-capture
predictions within churn tolerance. Report the three served rows to the owner as the
Ask-5 baseline before any new lever is considered.

---

## Lane A - Position Conversion Lab (ask 1)

**The home is `positional_fit.py`, not a new module.** The tree already has: a validated
MLB conversion model (rate transfer MAE 5.68 vs carry-over 6.73, n=169 conversions),
per-(player,position,season) OAA/FRP 2016-2026 (`savant_oaa.py` -> `data/savant_oaa.json`,
13,001 player-position-seasons incl. directional splits), innings denominators 2000-2026
(`fielding_innings.py`), BRef defensive runs (`data/mlb_def_history.json`, war_def/
runs_position, 17,016 rows), the def_home migration model, and fitted per-position
shrinkage constants (`positional_fit.json fit.signal`: k_inn 632 CF ... 2539 1B - the
sample-size calibration the owner asks for, already measured).

**A1. New ingests (the actual gaps).** Clone the `savant_oaa.py` pattern (1.05s throttle,
`.cache/` CSVs, fail-soft, compact JSON):
   - `savant_arm_strength.py` -> `data/savant_arm.json`:
     `https://baseballsavant.mlb.com/leaderboard/arm-strength?type=player&year={Y}&minThrows=q&csv=true`.
     MEASURED TRAP: the param is `year`; `season` is silently ignored. Per-position arm
     mph + max + throw counts, keyed by_mlbam[id][season].
   - `savant_sprint.py` -> `data/savant_sprint.json`:
     `.../leaderboard/sprint_speed?year={Y}&min=10&csv=true`, 2015+.
   - Optional catcher sub-lane: framing + poptime endpoints are probed-working (framing
     CSV ignores year - parse embedded page JSON; poptime `?year=`). OAA is structurally
     blind for C (zero rows every season).
   - Wire all defensive feeds + `positional_fit.py` into run_monthly behind freshness
     gates (the three existing feeds are manual-run, last 2026-07-24; use the
     `_lab_should_skip` cadence pattern).

**A2. DRS: probe before promising.** One curl with a browser UA against
`fangraphs.com/api/leaders/major-league/data?stats=fld&type=8&season=2025&season1=2025`
(worked from Will's machine 2026-06-16 carrying DRS + components + UZR + Inn; FG legacy
endpoints are Cloudflare-403 from this box). On 403: declare DRS out of scope in the
plan ledger and satisfy the "DRS history" ask with what is on disk - bWAR `war_def`/
`runs_position` (aggregate, 2000-2026) + OAA/FRP (per-position, 2016-2026). Do not
retry-loop a blocked host.

**A3. The conversion engine extension.** Extend `positional_fit.py` Feeds (:105-163)
with arm strength and sprint speed as indicators; encode the owner's rules as per-move
indicator weights on the existing feasibility-gated candidate set (`fit_feasibility`,
:481-541), reusing `_shrunk_z` + per-position k_inn:
   - Struggling OF + big arm -> 3B/RF weighting (arm-gated infield candidates).
   - Struggling SS -> 3B if arm clears, else 2B/1B (arm strength as the 3B gate).
   - Best-OF projection for infielders: existing s(p)*z range transport + sprint speed
     as second indicator.
   Priors from the defense-plus reports (measured, reuse as constants not code): arm y2y
   r .72-.86 (most reliable defensive signal), OAA rho_true 0.60 / n0=269 innings, OAA
   and FRP are redundant - never both.
**FRAMING CONSTRAINT (measured):** the demotion WHO-moves backtest is NULL (AUC 0.4953
vs raw OAA 0.6183). Every surface says "value at position X" / "profile fits X", never
"will/should be moved" as a prediction. The raw-OAA superiority on who-moves is itself
an unexplored arm - register it as a candidate, don't ship it untested.

**A4. Per-position defensive history UI (the owner's per-position OAA/DRS ask).** Emit
per-player season x position x {oaa, frp, inn, shrunk z, reliability = inn/(inn+k_inn)}
from `savant_oaa.json` x `fielding_innings.json` into the positional-fit payload
(`build_site.build_positional_fit_payload`, `build_site.py:3681`) and render in
`assets/pal.js` posfit section. "Which position has he performed best at, calibrated for
sample size" = the shrunk-z column, not raw OAA.

**A5. Prospect side (no MiLB tracking exists).** Bump `fielding_positions._lean` to a v3
schema keeping [g, gs, inn, po, a, e, dp] (filename versioning forces clean refetch,
~154 cached league-seasons, throttled) -> MiLB range-factor and error-rate proxies.
Join with tool_throw grades (2017-2020 coverage only - disclose) + the def_home
MIGRATION matrix. Ship prospect conversion reads through the def_home chip pattern
(risk-context display contract). **HARD FENCE: nothing from this lane enters eFV** -
defense-into-eFV is a twice-measured loss ledger (`prospect_def_value` eFV swap
REJECTED; `xfv_defense_tools` deprecated: every arm regresses, binding constraint is the
offense-dominated 6yr-WAR target).

**A6. Hygiene owed inside this lane:** resolve the duplicate positional ladder
(`prospect_def_value.POS_ADJ` canonical vs positional_fit's per-run refit, disagree up
to 0.35 runs, flagged in `data/positional_ladder_eval.json`) - point positional_fit at
POS_ADJ or ledger why not. Registry rows + eval artifacts for every new ingest.

---

## Lane B - MLB product uplift: cards, Projections, FA (ask 2 + owed Phases D and H)

Sequence is exporter-first so every render step has data waiting. All display-only; the
bounded display-movement battery + copy gates apply per step.

**B1. Card data bakes (`mlb_player_export.py`).** Extend `_skill_index` (:367-419) with:
war_pa_plus(+_3yr), pwoba, fwdhem_plus, luck_gap, tier (hitters); war_ip_plus(+_3yr),
gmli(+_3yr), saves/holds, wpa (pitchers); a leverage block from
`leverage_leaderboards.json` (wpa/wpa_li/pli/clutch by mlbam); a pal block (fit +
direction + proj_relief_rem_plus from `pal.json`, posfit gain/gloveRuns from
`positional_fit_ui.json`); TJ history join (`tj_surgery.json`, 2,512 players). Payload
is 3.7MB against the 6MB soft budget (`mlb_player_export.py:691`) - account for size in
the commit message.

**B2. Card render (`assets/projections.js`).** Expand `pitchingStatsBlock` (:1344-1376)
with xREM+/xSEM+, WAR/IP+ (remCell banding - sd=10 by construction), gmLI, leverage
tiles; expand the HEM tile group (:1566-1571) with xHEM+, WAR/PA+, luck_gap, tier; add
a PAL/positional-fit section linking to /pal/; TJ chip gated by origin like aaaStuffPlus
(:568-572). Render the per-year contract surplus `sur[]` array (baked, never rendered).

**B3. Projections board rework.** Split the overloaded Player cell (6 elements in one
320px ellipsized td) into columns (pos, age, contract chip); adopt the `fa.js` sHead
a11y sort pattern (:527-533 - tabindex/role/aria-sort) for ALL headers including #,
name, age (currently only season/5yWAR/surplus sort, with no keyboard a11y - the one
module below standard); move the ~30 inline style attrs into named `site.css` classes
under `.proj-app` (:1797-1837); keep the board-rail layout, sticky thead, and season
metric toggle.

**B4. FA board rework + Phase H (owed, spec at `master-plan-2026-07-29-efv-fa.md:
475-491`).** Render the computed-but-hidden fields (confirmed in the live payload:
warCvar10 223/228, pAnyStar 223/228, opt* decomposition 42, optPrice 77): surplus
P10/P90 band as its own column, option decomposition chips, risk columns, QO flag,
age-decimal, pace mini-cell; fits need-decomposition; player-card 3yr realized bWAR +
Spotrac market AAV + rate path; `fa_meta.park_factors` + QO tax surface. Add a search
input (projections has `#proj-q`; FA has none). De-cram via a two-row card-style row
(identity row + band tape, borrowing the PROSPX toolstrip `grid-column 1/-1` row-2
pattern) or the declarative `mlbstats.js` renderTable architecture - pick ONE approach
and apply it to both boards for consistency.

**B5. PROSPX-standard patterns to adopt (extracted, concrete):** fixed-height cards
(`height:136px` + `grid-template-rows: minmax(0,1fr) auto`), `minmax(0,1fr)` flexible
tracks, `content-visibility:auto` virtualization, org-color stripe, diamond rank chip,
universal sort-header map with direction arrows. The declarative column-def alternative
is `mlbstats.js:296-328`.

**B6. Phase D - wRC+ display program (owed, spec at `master-plan-2026-07-29-efv-fa.md:
277-330`):** D1 persist counting stats discarded in `_combine_stints`; D2
ops_plus_level -> wrc_plus_level chip swap (producer `storage.py:8915-8967`, browser
twin `prospx/index.html:42476`, RPS+ hitter leg, bayes_trade_value call sites, glossary);
D3 industry wRC+ column beside HEM+ on the hitter leaderboard; D4 prospect FV->rate
bridge for projections. D5 (eFV feature swap) is a closed loss - DO NOT RE-RUN.

**B7. Derived-tables surface.** `data/tool_grade_tables.json` and
`data/fv_outcome_curves*.json` have ZERO frontend consumers. Give them a display home -
a Model Accountability card (the `projections.js:838-898` registry-reader pattern) or a
glossary visual. Zero model math in JS; read committed artifacts verbatim.

**Ship checklist per step:** bump manual `?v=` pins on any site.css change; dark
refractor tokens untouched (`site.css:154-193`); var() tokens only
(`test_no_hardcoded_colors.py`); wide content scrolls in its own wrapper, never the
page; farm grid gets NO overflow-x; re-run `build_site.py` after any generator change.
Open owner question (non-blocking): does the uplift include the Fantasy module?

---

## Lane C - Leaderboards + WAR-rate scale (asks 3 and 7)

**C1. The Judge answer (report to owner, no scale change).** WAR/PA+ is 100 + 10z over
role-anchored pools, verified live at exactly 10.0 points per sigma on all three pools.
Judge 2026: war 2.1 / 261 PA -> raw rate 0.00805 = **3.50x the pool mean** (0.002297) -
but the pool sd (0.004289) is 1.87x the mean, so that is z +1.34 -> 113; his 3yr 125
means +2.5 sigma and pct=100, literally the best 3yr value on the board. "25% above
average" read the z-scale as a ratio. A ratio index is UNDEFINED on this rate (league
mean ~+0.0023 with negative WAR common - sign flips and blow-ups;
`bullpen_export.py:444-455`). The metric is measured and implemented correctly; the fix
is LEGIBILITY:
   - Add a 1yr percentile chip mirroring the existing 3yr `pct` pattern (compute in
     `bullpen_export.score_war_rate`, render next to remCell in `mlbstats.js`).
   - Add a "3.5x avg" hover line computed from the served row (war, denom,
     pool_mean_rate) shown only when war > 0 - display copy, not a scale.
   - Glossary copy via `build_glossary_war_rate_add.py` restating the z semantics
     plainly.

**C2. Sample-size adjustment - what it actually means here.** HEM+/SEM+/REM+ ALREADY
carry per-component empirical-Bayes shrink (HEM+ K_UBB=120/K_HBP=240/K_1B=290/K_2B=1000/
K_3B=1600/K_HR=170; REM+/SEM+ K_STRIKEOUT=70/K_WALK=170/K_HBP=170/K_HOMERUN=400) plus
two-tier volume floors - report this to the owner; no new shrink there, keep K constants
intact. The UNSHRUNK columns are WAR/PA+ and WAR/IP+ (floors only - hence Edman topping
the 1yr board on 117 PA). The owner's ask 3 is treated as CLOSING the open owner_call in
`data/war_rate_plus_eval.json` (shrink_ruling): ship the measured arm-S shrink as a
COMPANION column, not a replacement:
   - Port `tools/war_rate_plus_lab.py:311-326` (K = pool median denominator,
     rate_shrunk = (war + pool_rate*K)/(denom + K), mu/sd FROM THE SHRUNK POOL - the
     aStuff+ C3 defect class avoided) into `bullpen_export.score_war_rate` under NEW
     field names (`war_pa_plus_adj` / `war_ip_plus_adj`), per the scale-conventions rule
     that a shrunk number may not reuse the raw column's name.
   - Update the six glossary entries, registry notes, and record the owner_call CLOSED
     citing this directive; copy must cite the tercile volume-control caveat (the pooled
     shrink gain is mostly a volume leak).
   - Alternative/complement with precedent: raise DISPLAY_MIN_PA 100 -> 150-200
     (re-check row counts first - RP kept 30 IP because 40 left only 95 arms).
**C3. Standing fence:** G2 FAILED on all three pools - WAR-rate columns predict nothing
forward; plain season bWAR beats them everywhere. They must NEVER enter eFV,
projections, or FA. Any forward WAR-rate want uses war_total.

**C4. Leaderboard improvements round.** Wire `tools/war_rate_plus_lab.py --window-only`
into run_monthly cadence-gated next to 6b4c/6b4e (the frozen 3yr vintage currently ages
silently - every sibling lab has a step, this one has none). Fix the null-team batter
row in `leverage_export._build_batters` (:64-77, fall back to pitcher map or StatsAPI
people). Keep the SP 3yr window case labeled unresolved (G4 failed for SP). Add the B6
wRC+ column when Lane B lands it. Spot-check found boards otherwise healthy (no dupes,
no null headline metrics, UTF-8 correct).

---

## Lane D - Outcome-grounded tool grades (ask 4)

The substrate shipped today (commit 6340679): `data/tool_grade_tables.json` - 47
grade->measurement tables, INV-1 measurement-implied grades (9/13 cells PASS), INV-2
per-source drift (Pipeline runs HOT vs FanGraphs on the same players: fb -3.35, hit
-2.54, speed -2.50, field -2.33, game_pwr -1.47 grade points, every CI excluding zero,
n up to 526). Its contract says no scoring path reads it without a new gated lane. This
lane IS that gated lane. Pre-register everything in a new dated gate doc before fitting.

**D1. PRIMARY ARM - per-tool cross-source normalization (bias fix, real measured
signal).** Today `consensus.py:718-727` takes an UNWEIGHTED mean of per-source tool
grades - Pipeline's measured +1.5..+3.9-point heat flows straight in. Build a per-tool
per-source offset/quantile map modeled on `grade_normalization.py` (currently FV-only),
correcting Pipeline toward the FG frame (or both toward the INV-1 measurement frame for
the 9 passing cells). This corrects a CI-clean bias rather than reweighting noise - it
is the arm with the best prior. Gate: tools_consensus shift audit + downstream blast
radius (Tools+ pills, TBS tool legs, eFV features tool_hit/tool_speed/tool_fb) with the
display-movement battery; the eFV feature path additionally requires the full
EFV_GATE_STANDARD forward gate (any tools_consensus change reaches efv_dataset).

**D2. SECONDARY ARM - per-(source x tool) accuracy weights.** Reuse the draft machinery
verbatim (`draft_source_backtest.py`: relative accuracy -> shrink k=150 toward equal ->
clamp 0.6-1.5), scored per source x tool against the measurement targets already joined
in `tools/tool_grade_tables_lab.py` (velo, statcast batter, OAA+innings), reading
per-source history from prospects.db snapshots via `load_source_grades_db()` (:874-904;
timeseries prunes old per-source tool blocks - never read the JSON exports for this).
**Pre-declare the likely null:** only FG (23,117 rows) and Pipeline (17,438) clear the
per-source floor (TJStats 113 players, JB 126, ESPN 101; BA carries ZERO tool grades in
the entire 2011-2026 history), and both existing FV-weight lanes measured gains inside
the noise floor and shipped equal weights. The ship bar is gain > resolvable MDE, same
as `source_backtest.py` enforces.

**D3. Tools+ composite grounding.** `storage.py _compute_tool_composites` (:261-400)
weights are hand-assigned (hitter p=4 power-mean; O-Tool HIT .40/PWR .40/...; pitcher
0.65 stuff/0.35 cmd) with NO eval artifact. First create the missing baseline eval
(predictive value of the current composite against realized outcomes - that artifact
alone satisfies "ground Tools+ in outcomes" honestly if the refit fails), then gate an
outcome-weighted alternative against it. Registry rows for tool_plus/dvm_plus_tools
currently `unvalidated` - this lane must leave them measured.

**D4. eFV tool consumption.** The shipped ridge uses exactly tool_hit +1, tool_speed +1
(hit) and tool_fb +1 (pit). If D1 normalization ships, re-run the eFV gate on the
normalized inputs (matrix rebuild required). Do not add new tool features without
independent gates.

**D5. Closed nulls this lane must not re-run:** game_pwr into the hitter ridge (three
confirmations), defense/field tools into eFV (xfv_defense_tools), tools into the
provisional prior (ARM-T +0.003 DEAD, `docs/efv-provisional-prior/GATES.md:107-109`),
college stuff+ (r=-0.005), frame/athl as trainable (0/843 coverage), arsenal-shape
composites (xfv_relief_shape). Also: speed/arm grades have NO measurement anchor on
disk today - Lane A's sprint + arm ingests CREATE those anchors; sequence D's speed/arm
cells after A1 lands and extend the tables lab with speed_vs_sprint and
throw_vs_arm_mph tables (the missing arm table is called out in the tables doc).

**D6. Passing fix:** `consensus.py:17` docstring still cites the reverted 0.939/1.061
FV weights - correct it.

---

## Lane E - Board credibility: Taylor, Bradfield, Arias (asks 5 and 6)

**E0. Baseline = Phase 0 output.** The empirical case, carried with pulled numbers (use
these in any owner-facing copy, not vibes):
- Arias: .318/.407/.587 (.994 OPS, 19 HR) in 332 AA PA at age 20.6; ops_rel +0.248 =
  98.8th pctile of 1,971 live hitters, #10 of 375 AA-primary. AAA is a 19-PA cameo -
  below the 50-PA primary-level gate, so features still read AA. Owner's read CONFIRMED.
- Bradfield: .657 OPS at 24.7 repeating AAA; ops_rel 6.5th pctile; comp cohort (AAA,
  age>=23.5, ops_rel<0, n=83) realized 0.50 WAR / 77.1% bust / implied FV 39.8. Owner's
  read CONFIRMED.
- Taylor: age 24.2, THIRD AA season, 2025 collapse (.575 OPS in 437 PA) - but his 2026
  line is .901 OPS = 94.2th pctile. The model cannot see 2025 (only final-season rates
  enter `_milb_features`). Owner's read confirmed on age/track-record, NOT on current
  performance - public rationale must say age/history, never "mediocre 2026".

**E1. Taylor lever (new, un-tested, principled): repeat-level feature.** No
seasons-at-current-level / repeat-level encoding exists anywhere in the feature set, and
the structure sweep never covered it - it is the one untested feature shape for "third
AA season after a collapse". Pre-register a gate (EFV_GATE_STANDARD, the
`tools/_sweep_structure.py` numpy-replica protocol), compute `seasons_at_current_level`
in `_milb_features`, append to `_FEATURES_HIT` (probably also `_FEATURES_PIT`), and
test forward-chained. Do NOT expect prod_trend to do this (it reads +0.063 for Taylor
because 2026 > 2025, and it is not even in the shipped feature list).

**E2. Arias lever (the only un-refuted one, and TIME-CRITICAL): B3 continuous level
blend.** `_milb_features` is winner-take-all (highest level with >=50 PA is the ONLY
production source). The day Arias clears 50 AAA PA, his .994 AA line VANISHES from every
production feature and the model spuriously drops the player the owner wants at #1.
Execute B3 per its spec (`master-plan-2026-07-29-efv-fa.md:171-179`): PA-weighted blend
across levels, weights pa/(pa+K) per level, matrix-rebuild-coupled, full gate standard,
secondary metric Spearman(old,new) on the top |ops_rel| decile. This is both the Arias
lever AND a correctness fix for every multi-level season. Priority: run its gate EARLY
in the program.

**E3. The honest Arias ceiling (state in the plan, restate to owner).** The #1 gap to
jesus_made is a pure consensus-anchor gap: FG and Pipeline publish Made a full grade
higher (65/65 vs Arias 60 across all five sources); normalization is additive per
(source,role,cycle) on an equal-weight mean, so the -2.0 gap survives any basis setting
(`ARIAS_COUNTERFACTUAL_GATE.md` section 8). The model leg ALREADY credits Arias more
than consensus (+6.1 xfv_minus_consensus; model war6 11.17 vs Made 11.49). If B3 ships
and Arias is still #2, the remaining routes are: (a) accept #2 behind a 19.2-year-old
with age_rel -3.4 at AA, or (b) an owner POLICY overlay declared as policy (the
`_age_factor` precedent) - never consensus machinery. Present (b) as an owner decision
with the tradeoff stated; do not build it unbidden.

**E4. Refuted/forbidden for this lane (cite, never re-run):** gradenorm basis flip
(NULL/NO-SHIP, worse than random on pitchers), reliability-K revert (NULL both
directions), age-x-level / age-x-prod / level-x-prod interactions and age hinges (all
null vs MDE95 0.017 in `tools/_sweep_out/structure_point.json`), tool_speed removal
(HURTS -0.0068), C2 empirical age norms (would make Bradfield read YOUNG for AAA -
`data/_c_agenorms.json`), surrogate labels (spent, ground rule above).

**E5. Escalation dial: DECIDED - keep 23.0, no code change.** Direction, for the record:
a LOWER onset is HARSHER. The shipped 23.0 already lands Bradfield at 123 and Taylor
outside the top 100 with zero pitcher-share cost. The only true escalation is 22.0
(Bradfield 131) and it costs two top-100 pitchers, taxing the side this program has been
repairing. 24.0 would be a DE-escalation (Bradfield back to 100). See the correction in
the decision queue above. Owner dial, not a model change.

**E6. Odds coherence audit (register as owner call).** Served p_bust: Taylor 0.264,
Bradfield 0.243 - against comp-cohort bust rates of 70-77%. Odds are PINNED to the
retired map by design (re-key measured and rejected against its own null; recalibration
NULL vs base rate). Neither basis prices the owner's risk read; frame as a
calibration-vs-cohort audit with the measured counterfactual
(`POOLED_OUTCOME_REFIT.md:268-276`), decision to owner.

---

## Lane F - eFV: the pitcher FV50 cell, weak-cell program, AUC (ask 8)

Current headline (post-refit semantics, accuracy lanes unchanged): hit pooled OOS
Spearman 0.3834 vs consensus 0.332, pit 0.303 vs 0.2638; head-to-head 0.3711 vs FG
0.2469 / Pipeline 0.2819 / PROSPX consensus 0.2839 (n=2,200); aucC 0.7762/0.7197 vs
consensus 0.7446/0.7102.

**F1. Re-measure first (Phase 0 dependency).** All per-tier numbers below are from the
2026-07-24 scoreboard; the fresh `tools/efv_scoreboard.py` run in Phase 0 is the
baseline. The tier convention is nearest-5 consensus FV (tier 50 = [47.5, 52.5)),
TIER_MIN_N=15.

**F2. The target cell and its gate.** pit.fv_tier.50: eFV 0.1697 vs consensus 0.3123
(n=40, margin -0.1426) - the single largest weak cell. There is NO registered per-tier
MDE and the cell has never been bootstrap-tested against a floor. Before any model
change: pre-register a per-tier gate doc (paired bootstrap per tier, per-tier MDE95
derived like EFV_GATE_STANDARD section 1 - expect it to be LARGE at n=40; state
honestly whether -0.1426 even clears it), plus an exact-FV50 diagnostic split in
`tools/efv_scoreboard.py` or `efv_lab_runner.py`.

**F3. Mechanism diagnosis (untested suspects, in order):** pitcher lambda sizing (pit is
dynamic 0.54 vs hit hard 0.70; per-cohort lambda labs are NO SHIP but a pit-side
re-select validation is legal), reliever-ceiling/role tilts inside the tier (the tier-55
sign flip in the same table suggests role composition), and consensus-anchor quality for
mid-tier arms. Output: a diagnosis memo BEFORE any lever, each lever its own
pre-registered gate.

**F4. The whole weak-cell list (11 cells) as the "win everywhere" program:** hit tier
60, hit cohort hs (tie -0.0008), hit era <=2018, pit tier 50, pit eras <=2018 and
2019-2021, archetype hs_arm and intl_bat aucC. Era cells <=2018 are old-era training
composition - diagnose but expect structural. WARNING to encode: chasing 11 cells
invites overfitting; the gate standard's pooled no-loss constraint is the binding
protection, and a cell "win" that fails its own per-cell MDE is noise, not a win.

**F5. AUC levers.** The gate standard has a full-pool AUC carve-out for
missingness-sensing candidates - that is the sanctioned AUC path. The open, measured,
gated candidates list (`docs/efv-2026-07-29/GATED_CANDIDATES.md`): C1 SC+ sample
gate/shrink (reorders eFV for 2,887 players - needs the full forward gate), C3 aStuff+
denominator fix (7.16 pts/sigma vs advertised 10, atomic with overlay re-fit), C2
15z->10z re-band (atomic with 4 _tbsNorm call sites), C4 dormant TBS term. Plus the
hitter-only-refit alternative named in `POOLED_OUTCOME_REFIT.md` 2.9#1 (untested). These
are the open inventory; nothing else is scoped-and-alive.

**F6. Fences:** the full refuted list in the ground rules and Lane E4; additionally the
odds re-key and Defect C candidates (refit AND C-prime both refuted - the 68.5%-$0
floor needs a NEW owner-approved design, do not improvise one inside this lane; C6
reliever bridge inversion must not be attempted jointly with sub-cutover anchor work).
Surplus-dollar claims stay in rank terms until the raw-vs-normalized calibration P0
closes (EFV_GATE_STANDARD section 4).

---

## Lane G - The valuation-curve artifact (ask 9)

Update the EXISTING artifact titled "eFV Prospect Valuation Curve" (last updated
2026-07-23, so it pre-dates the outcome refit): run the Artifact tool with
`action: "list"`, match that exact title (id begins `03e424cb`), and pass its URL via
the `url` parameter so the owner's link stays stable; keep the same favicon. Load the
dataviz skill before building. Read ONLY committed artifacts:
`data/fv_outcome_curves_pooled.json` (FV -> E[WAR6] curve + CI90 + n_cell + w_prior,
hash 6dbe8353), `data/fv_outcome_curves.json` (per-side Phase-1 curves, shown as the
measured NULL they are), `data/value_framework.json` (surplus_by_grade_mm: hitter FV50
$23.1M / pitcher FV50 $16.7M ... FV80 $204.6M/$185.5M; fv_to_6yr_avg_war; dollars_per_war),
`data/xfv.json` by_player (xfv_grade_quantile vs surplus_mm scatter),
`config/valuation_sets/prospx_current.yaml` tier table.

**Honesty requirements (non-negotiable, from the refit doc):** label the three regimes -
sub-FV45 is a display re-spread NOT outcome-calibrated (71% of live rows), FV57.5+ knots
are 57-97% Clemens prior (FV70 cell is one player), and the $0 floor (68.5% of served
rows) is a known open defect. House copy rules apply inside the artifact (no em-dashes,
FV ceiling display, no LLM filler).

---

## Lane H - Polish + bug punch list (the riders)

Confirmed items, cheapest first:
1. `leverage_export._build_batters` null-team row (one-line fallback).
2. `efv_score.py:520` stale comment (asserts age_rel_level weight "effectively zero" -
   the exact number c26c6d6 adjudicated as moved).
3. Register C6 (reliever Edwards-bridge inversion) in GATED_CANDIDATES.md with its
   measured numbers - cited there today but ABSENT.
4. Document the luis_hernandez suffix-key convention; clean fa_meta AVERAGES/OAK keys.
5. `consensus.py:17` stale weights docstring (Lane D6).
6. **Team-outlook recenter red (REAL bug, owed by the FA lane):** the 89112f5 FA ship
   bought WAR MAE with league-total level (1018 -> 910 vs ~1000 actual); fix per
   c26c6d6 section C - re-anchor the playing-time refit to ~1000 league WAR or refit
   cohort intercepts under holdout. The bound must NOT be widened.
7. Locate or re-run the per-side age-for-level norms gate verdict - RESOLVED by the
   research sweep: C2 verdict is NULL/NOT-SHIPPED (`EFV_LANE_GATES.md:266-311`),
   `_TYPICAL_LEVEL_AGE` stands, C3-CLIP shipped default-off, C3-ETA gate still OWED.
   Close the C3-ETA gate or ledger it.
8. Console/smoke sweep: the only existing check is the manual LAUNCH_DAY five-page
   smoke; after Lane B lands, run it on all five MLB surfaces + prospx in both themes.
9. `data/pal.json` schema refresh: still OWED. Phase 0 did not re-run `pal_export`, so
   the served payload predates 23a7f44's staged watch (121 entries, no
   `prospect_watch_rule` key). Do it before any /pal/ surface work.
10. **NEW 2026-07-30: `test_prospx_sort_a11y::test_aria_sort_reflects_state_and_enter_resorts`
    is order-dependent.** It fails deterministically in the full suite and passes in
    isolation, with neighbours, and in every pairwise combination tried. The fixture is
    module-scoped over a real browser page reading `data/timeseries.json`, and the suite
    dirties build artifacts mid-run (the documented conftest-restore hazard), so the board
    the page loads is not the board the test was written against. Fix is test isolation,
    not the a11y feature, which passes whenever it is measured against a clean tree.
11. **NEW: Windows console logging crashes on `→`.** Seven `UnicodeEncodeError`
    tracebacks during the regen, all from `_log.info` calls containing a right-arrow
    against a cp1252 console (`bayes_trade_value.py:4188` and siblings). Cosmetic only,
    the exports completed, and it cannot fire on the Linux box, but it makes a clean run
    look alarming. Either ASCII the arrows or force UTF-8 on the stream handler.

Zero TODO/FIXME markers exist in source - the backlog above IS the bug list, plus
whatever Lanes A-G surface (file new findings into this section rather than fixing
drive-by).

---

## Owner decision queue

### TAKEN 2026-07-30 evening (binding on the executor)

| # | Decision | RULING |
|---|----------|--------|
| 1 | Push to main/beta after Phase 0 regen | **PUSH once the acceptance checks pass.** Run the runbook end to end including step 8 (main, then sync beta). |
| 2 | WAR-rate shrink owner_call | **CLOSE it: ship the arm-S shrink as NEW `_adj` companion columns** (raw columns keep their meaning) **plus the 1yr percentile chip.** Lane C2 as written. |
| 3 | Age-onset dial | **KEEP 23.0. No code change.** See the correction below. |
| 4 | Arias policy overlay | **Do NOT build it.** Run the B3 gate and accept the outcome; revisit only if his AAA line moves consensus. |

**Correction on record (author error, caught before execution).** The decision queue as
first put to the owner described onset **24.0 as an escalation**. It is the opposite: a
LOWER onset is the harsher setting. Verified against `_age_ramp` and the measured board
table (`EFV_LANE_GATES.md:329-339`):

| onset | bradfield age factor | bradfield rank | top-100 pitchers |
|---|---|---|---|
| 25.0 (retired) | 1.00 | 88 | 8 |
| 24.0 | 0.93 | 100 | 8 |
| **23.0 (shipped)** | **0.83** | **123** | **8** |
| 22.0 | 0.75 | 131 | 6 |

Applying 24.0 would have returned Bradfield to the top-100 edge and cut Taylor's penalty
to 0.98, reversing ask 5. The owner was re-asked with the direction corrected and chose
to keep 23.0, which already satisfies the ask at zero pitcher-share cost. Onset 22.0
remains the only true escalation and carries a measured cost of two top-100 pitchers.

### STILL OPEN (collect before the dependent step)

| # | Decision | Default if silent | Blocks |
|---|----------|-------------------|--------|
| 5 | Odds re-key / p_bust basis | Keep pin, publish audit | E6 |
| 6 | Fantasy module in the Lane B uplift | Exclude | B |
| 7 | FA fits concentration-vs-MRR; rate_line OFF | Untouched (need pre-registration) | none in this plan |
| 8 | Defect C new design ($0 floor) | Out of scope this program | F6 |

---

## Sequencing for Opus (lane split, dependencies, effort)

```
Phase 0 (blocking, serial)  ->  everything else
LANE-A (conversions)   independent after Phase 0; A1 ingests unblock D5's arm/speed cells
LANE-B (frontend)      independent; B1 exporter bakes before B2-B5; B6/B7 last
LANE-C (leaderboards)  independent; C2 waits on owner row 2 only if contested
LANE-D (tool grades)   D1 before D2; D3 parallel; D4 after D1 ships (matrix rebuild)
LANE-E (board)         E1/E2 gates early (E2 is time-critical vs Arias's AAA PA clock);
                       E3/E5/E6 are owner-facing reports
LANE-F (eFV)           F1 rides Phase 0; F2-F3 before any lever; F5 candidates each gated
LANE-G (artifact)      after Phase 0 (needs served state coherent); quick
LANE-H (polish)        items 1-5 anytime; 6 coordinated with FA lane; 8 after B
```

Orchestrator holds: Phase 0, every commit, the serial suite runs at merge points, the
owner decision queue, and the final REGEN_AND_PUSH endgame (a SECOND regen/restamp is
owed at program end if any lane moved served numbers - do the golden dance once per
regen, not per lane). Every lane pre-registers its gate doc before measuring, every
artifact gets its registry row in the same commit, and every null is reported as a null.
The last three sessions' lesson stands: the nulls are where the accuracy lives, and
"without shipping a loss" means the gate standard decides, not the wish.

# Master plan 2026-08-16: SDR + eWAR as the site's primary defense and WAR metrics

PLAN ONLY. Written 2026-08-16 on branch `efv-conviction-2026-08-08` (22 Diamond commits
ahead, NOT pushed; suite baseline TWO reds; owner data churn in the working tree,
untouched). Owner directive: implement Will's SDR (defense) and eWAR (WAR) across all
modules as the primary metrics, use them to improve models site-wide, calibrate eFV to
eWAR, test MiLB SDR as an eFV driver, add eWAR/SDR leaderboards, and generate the full
ideas backlog.

Everything below was planned against a fresh code recon (2026-08-16) plus the execution
record. File:line citations verified against the current tree.

---

## 0. Where we actually start (the record, so nobody re-derives it)

**eWAR exists and is deliberately unwired.** `ewar.py` (v2, `data/ewar.json`, 15,512
player-seasons 2016-2026, `data/ewar_eval.json`, registry row `ewar` provisional).
Formula: `eWAR = bWAR + delta_pitch/RPW` (pitching re-priced on FIP; offense,
baserunning, fielding, positional adjustment stay on B-Ref runs; replacement re-derived
so league sums match, max deviation 0.0). The measured verdict on the row:

- LOSES the descriptive gate: team-wins r 0.8595 vs bWAR 0.8803, zero-param MAE 4.306
  vs 3.787. This is BY CONSTRUCTION for any FIP-based WAR and will not change.
- WINS the forward gate: pitching self-r 0.36 vs 0.18 (2.1x), and forecasts next-season
  team runs better than bWAR (0.2524 vs 0.2481).
- The fielding swap (Statcast OAA/FRP) measured OUT on a monotone w-grid; default
  `fielding_blend_w = 0.0`. The grid machinery was KEPT with an explicit re-open clause
  at `ewar.py:806-812`: re-run the grid if a fielding model with arm, framing, blocking
  and the DP pivot ever lands. **SDR is that model.** Note the standing ban: an
  OAA/rfield blend at any w is a settled loss; the SDR grid registration must state
  what is NEW (components beyond range; catcher coverage).

**The provider seam exists.** `war_source.py`: `PROVIDERS = ("bwar", "ewar_v2",
"ewar_merged")`, `DEFAULT_PROVIDER = "bwar"`, ten facade call sites, a last-good
parquet cache, and `ewar_merged` already DECLARED as "Will's pitcher eWAR plus
SDR-bearing fielding on the ewar.py frame", raising `DataUnavailable` until the drop
arrives. `ewar.ewar_for(mlbam, season)` is the per-row provider call shape.

**The re-anchor trap is documented at `war_source.py:33-39`.** Beyond the facade, five
bWAR-pinned artifact families exist: the empirical FV outcome curve
(`value_framework.py:2887`), `FV_EXPECTED_WAR` (`storage.py:5292`) + survivor anchors,
the draft slot curve, the `war_rate_plus` frozen vintages, and copy gates literally
asserting "bWAR" (glossary: "the one WAR source used site-wide"). A SIXTH is MANUAL:
`FV_WAR_ANCHORS` at `prospx/index.html:22490` (`fvExpectedWarPerYr` at :22495) is a
hand-synced client-side snapshot of `value_framework.survivor_expected_war` with NO
test binding it to the backend curve; a refit desyncs it silently (prior burn:
audit-2026-07-18 A7, stale-mirror WAG pills; the hazard is written up in
docs/computed-stats-handoff-2026-08-01.md:1376, whose quoted line numbers are stale).
A partial flip desyncs fingerprinted artifacts. The Stage-2 cascade runbook
(docs/master-plan-2026-08-03-eight-asks.md, D3) is an OWNER CHECKPOINT.

**SDR does not exist in the repo.** No code, data, registry row, or eval. What exists:
the B2 intake spec (docs/master-plan-2026-08-04d-omnibus.md:412-467, six items, five
integration points each with its own gate), the positional-ladder export built FOR
Will's SDR work (`tools/export_positional_ladder.py`, `positional-adjustments/`), and
`milb-projections/manifests/BENCHMARK_MANIFEST.yaml` naming Will's pitcher-eWAR parquet
(`~/pitcher_ewar/data/pitcher_ewar.parquet`, data-blocked locally).

**Defense-into-eFV carries three standing refutations** (2026-06-24 x2, 2026-06-29):
tool_field, Defense+ prior, and `prospect_def_value` (a VALIDATED defensive predictor,
Spearman 0.68 vs FG fFld 0.28) all flat-to-negative on the flagship. Root cause on the
record: "the binding constraint is the TARGET, not measurement quality" (first-6yr WAR
is offense-dominated). The reopen condition is a LABEL change, which is exactly what
the eWAR label swap is. The eFV feature frontier is otherwise CLOSED (39 gated arms,
zero survivors, 2026-08-14b): do not open feature lanes on the current labels.

**Current display state**: bWAR everywhere (three /mlbstats/ boards, /fa/,
/projections/, $/WAR, PROSPX career chips, hub, PAL, trade machine, arbitration
features). Defense display: OAA/FRP via /pal/ Position Fit (+ Rng+ LF/CF), the
def_home chip on prospect cards (display only, never a rank input), no catcher metric
anywhere (Savant OAA has zero catcher rows; framing ingest REFUSED 2026-08-04, season
param inert; DRS unavailable, proprietary).

---

## 1. The honest frame (copy and claims discipline)

1. eWAR-primary display is a PRODUCT decision, not an accuracy claim. The precedent is
   eFV vs consensus FV: our metric leads, the incumbent stays as reference. Copy MAY
   say eWAR is built to forecast (measured: 2.1x pitching persistence, better
   next-season team runs). Copy MAY NOT say eWAR describes the season more accurately
   (measured loss, permanent). The `ewar` registry note keeps BOTH gate readings and
   gains a dated owner-decision line superseding "DO NOT flip the site basis" for
   DISPLAY only.
2. The "most advanced MiLB defensive metric on the market" claim is TESTABLE and must
   be DERIVED from `milb_sdr_eval` (vs FG field grade, vs prospect_def_value), never
   hardcoded. Hardcoded accuracy claims are a banned defect class (2026-08-13).
3. One WAR basis per pricing path, ever. Dollars, surplus, trade values stay on the
   bWAR-derived anchors until a separately gated re-anchor. Mixing bases inside one
   column, one comparison, or one $ path is the Quantity A/B trap, third edition.
4. eFV-vs-consensus margins are only meaningful on SAME labels (the R3 rule). After
   any label swap the whole accuracy story is re-measured; cross-label quotes banned.

---

## 2. Owner decision queue (lock before the display wave)

- **D1 Intake path.** Recommended: versioned parquet/CSV drop from Will under a
  manifest with a `--validate` preflight (the cards feed-seam pattern), keyed mlbam
  with consensus-alias fallback, vintage-stamped. Alternative (not recommended):
  running Will's multi-stage pipelines in-repo (fetch-blocked, hours, unowned).
  Also confirm attribution/licensing line for publishing SDR values.
- **D2 Display semantics.** Recommended: eWAR primary + bWAR reference chip wherever
  both exist (eFV pattern), leaderboards get both columns; NOT a bWAR removal.
- **D3 Dollar basis.** Recommended: $ paths stay bWAR-anchored until the eFV label
  gate AND a dedicated $/eWAR re-anchor gate both pass (they may never; that is fine).
- **D4 Leaderboard placement.** Recommended: a new Defense section inside /mlbstats/
  (the section nav is built to grow) + eWAR columns on the three existing boards +
  MiLB SDR surfaces inside PROSPX; no new top-level module. A standalone module only
  if the MiLB glove boards prove out and deserve their own page.
- **D5 eFV label flip (R3c).** The MEASUREMENT is pre-authorized here; the FLIP stays
  an owner checkpoint with the full epoch cascade quoted, per the 2026-08-04 plan.
- **D6 Display timing vs the merge.** If the SDR drop lands promptly, display ships as
  `ewar_merged` after W1. If intake stalls, OPTION: ship eWAR v2 display first
  (fielding is bWAR's own rfield, so only pitching attribution changes) with the basis
  disclosed. Recommended: wait for merged unless the stall exceeds ~2 weeks.
- **D7 Diamond.** Recommended: SDR/eWAR surfaces launch FREE (standing rule: outside
  Diamond, free forever). Revisit premium defense intel later as its own decision.

---

## 3. Wave plan

### W0. Intake contract + census (BLOCKING; everything gates on this)

1. Send Will the B2 intake form (it was specced for exactly this): what SDR measures
   (range / arm / framing / blocking / DP pivot), outcome-based vs grade-based, units
   (runs), MLB coverage by season/position (catchers?), MiLB coverage by level/season,
   keying (mlbam preferred), refresh cadence, uncertainty/innings fields (the
   positional-ladder README already promises `k_inn`-style shrinkage constants).
2. Build the drop seam: `sdr_intake.py` + manifest + `--validate` preflight (schema,
   identity, coverage declaration, vintage stamp). Identity: mlbam join, alias
   fallback, NEVER name-only (the bind_player_ids trap). Same seam accepts Will's
   pitcher-eWAR parquet for `ewar_merged`.
3. PRE-REGISTER the validation harness before data arrives (B2 step 4): registry rows
   `sdr_mlb`, `sdr_milb` (provisional), named eval artifacts, `MODEL_GLOSSARY`
   entries, freshness map. Gates written with frozen clauses and empty Results.
4. On arrival: commit the CENSUS FIRST (the D-2 discipline). Coverage by
   season/level/position decides every later frame. Expect tracking-era cliffs; a
   has-SDR indicator is an ERA INDICATOR and inadmissible in any trainable use.

### W1. Validation core (measure before any display)

- **G-A `sdr_eval` (MLB).** SDR vs rfield vs OAA/FRP on: year-over-year
  self-persistence; forward prediction of next-season team runs allowed (defense
  leg); agreement with realized defensive value against the two named baselines
  (fFld 0.28, prospect_def_value 0.68). Face-validity panel. Descriptive leg reported,
  forward legs gated.
- **G-B eWAR v3 = the merge.** Re-run the kept w-grid at `ewar.py:806-812` with SDR as
  the fielding input; pre-committed selection rule on the SAME two forward legs the
  v2 grid used; the registration states what is NEW vs the banned OAA blend. Assemble
  `ewar_merged` (Will's pitcher eWAR + SDR fielding + B-Ref offense/baserunning/
  positional on the ewar.py frame); league-sum accounting gate, coverage gate,
  attribution arms, catcher handling explicit. Wire the `war_source` provider so
  `ewar_merged` stops raising. Update the `ewar` registry row; run
  `tools/gen_audit_docs.py`.
- **G-C `milb_sdr_eval`.** Does MiLB SDR predict MLB defensive value (and MLB SDR)?
  Forward-chained, leakage rules, baselines = FG field grade + prospect_def_value.
  This artifact is the source of every public claim about MiLB SDR.

### W2. Display flip (product wave; ships on W1's validated-descriptive basis)

- **Seam**: a display-WAR accessor pair (py + js, the `_level_plus`/`_lvlPlus`
  two-accessor rule) serving eWAR where covered (2016+, MLB) with bWAR fallback and a
  `basis` field on every row. `DEFAULT_PROVIDER` in model code STAYS `bwar`; every
  model keeps the provider that won its gate. The five pinned artifact families are
  NOT touched in this wave.
- **Leaderboards**: eWAR column primary + bWAR reference on hitter/starter/bullpen
  boards (column defs + glossary `term` wiring); NEW Defense board in /mlbstats/
  following the 8-step module pattern (builder with `score_war_rate`-style pooling,
  payload envelope, nav button + tabpanel in `build_site.build_mlbstats`, mlbstats.js
  renderer, `data_catalog.py` row, run_monthly 6b wiring, contract test,
  gen_audit_docs). Columns: SDR runs, SDR/inn index (a display index needs its own
  registry row, the `war_pa_plus` precedent), innings, position filter, OAA/FRP +
  rfield reference columns.
- **Player surfaces**: PROSPX career chips + graduate cards, hub panel, PAL warCell
  and Position Fit tables (SDR column beside OAA/FRP), player-page defense section
  led by SDR. Prospect cards: MiLB SDR chip beside the def_home chip, SAME contract
  (display only, never a grade/rank/sort input without its own gate) plus a
  by-season SDR trajectory on the detail page.
- **Held back deliberately**: /fa/ and /projections/ WAR paths keep bWAR-basis labels
  (the models predict bWAR; relabeling them eWAR without retraining is a basis lie);
  team outlook accounting stays bWAR; arbitration features untouched; trade machine
  pricing untouched (D3).
- **Copy**: glossary `sdr` + `ewar` entries, methodology section, the "one WAR source
  site-wide" line rewritten, copy gates that assert "bWAR" updated in the SAME
  commits, all claims derived from the three W1 artifacts. No em-dash. Publish
  manifest ships the new eval artifacts (never data_exclude an `*_eval.json`); cache
  stamps for new payloads.

### W3. eFV recalibrated to eWAR (R3 executed; the flip is the D5 checkpoint)

1. **Label build**: first-6yr eWAR_merged labels on the SAME KM/censoring frame as
   `_label_6yr`. Census label availability by decision year FIRST: eWAR coverage
   starts 2016 (`FIRST_OAA_SEASON`), so early cohorts have partial windows. Options,
   decided at registration, not after: backcast the FIP pitching swap (needs no
   tracking) with fielding falling back to rfield pre-tracking (disclosed per-season
   basis flags, which `ewar.json` already carries), or restrict folds. Do not pool
   uncovered folds (the pitcher-stuff 0.0-delta lesson).
2. **Harness**: `--war-source` flag on `tools/efv_lab_runner.py` (B3 as specced);
   check `tools/efv_label_replacement_lab.py` for prior art before writing new code.
3. **Decision metric**: margin-vs-consensus on SAME labels, both sides, AUC
   co-primary (owner lock 2026-08-14), floors RE-DERIVED on the new label as a
   blocking first step (never reuse the 0.017/0.016 or 0.0193/0.0172 floors, they
   belong to bWAR labels and their frames), Holm, noise twins, zero-info controls.
   Publish the full cross-label matrix; lead with the honest cell.
4. **Pre-registered mechanism**: pitcher labels get less noisy (FIP persistence 2.1x),
   so pitcher-side movement is the expected signal; hitter labels barely move
   (offense unchanged, fielding share small). A null on hitters is expected and fine.
5. **If the gate wins and the owner flips (R3c)**: the FULL grade-basis epoch, priced
   up front: re-derive `fv_outcome_curves_pooled` + `outcome_implied_fv` +
   `realized_implied_fv` + `FV_EXPECTED_WAR` + survivor anchors + slot curve +
   `war_rate_plus` vintages as ONE coordinated Stage-2 cascade (the war_source.py
   trap list IS the checklist), INCLUDING the manual `FV_WAR_ANCHORS` frontend
   mirror at `prospx/index.html:22490` and the `outcome_implied_fv` call sites the
   recon mapped (`efv_score.py` x8, `efv_export.py:214/:313`, `storage.py:4912/:8237`);
   `test_board_basis_coherence.py:145/:192/:395` pins score_history to the board's
   own map and will need coordinated attention; re-fit every fitted constant on the
   new frame (the
   a_c 0.0102 = 44.7% regrade lesson); apply at all FOUR scoring sites (run,
   run_live, run_backgrade, score_history); route floors on the uncorrected grade;
   epoch bump + fingerprint + prospx_current re-capture INSIDE its valuation set +
   golden restamp; three rebuild passes (one-run lag); regenerate `efv_model.py`
   both sides + `source_backtest` BEFORE reading any margin (the vacuous-margin
   trap); WAG, DvM+ family, farm surplus-mass follow the label; movement epoch
   bumped so the re-rank does not read as movement. Accuracy hero/glossary copy
   re-derives on the new basis.
6. **Dollars do NOT move in this wave** (D3). Surplus keeps pricing off the current
   bWAR-anchored maps; a `$/eWAR` re-anchor is its own later gate if ever.

### W4. MiLB SDR as an eFV driver (runs after W3 defines the label)

- Honest prior: three refutations; B2's own expected outcome is NULL. What is
  genuinely new and justifies ONE registered attempt: (a) under eWAR labels the
  label's fielding component IS SDR-based, giving the feature a direct mechanism the
  bWAR attempts never had; (b) SDR is an outcome-based measurement, not a scout
  grade or a position-migration proxy, so it is not a re-run of a banned arm.
- Protocol: coverage census first; frame restricted to SDR-covered decision years
  (expect few folds; the honest first outcome may be an underpowered null recorded
  as underpowered, never "SDR does not predict"); floors derived on that frame;
  missingness inadmissible; Holm; noise twin; the registered-repeat bar applies to
  any second family.
- Pre-declared fallback so the lane cannot fail into nothing: the COMPONENT model.
  MiLB SDR -> predicted MLB defensive runs ships as display/context (prospect card
  chip, PAL prospect cells with per-position validity gates, def_home/p_hold
  refresh input) on `milb_sdr_eval`'s strength, independent of the driver verdict.
  That is where prospect_def_value's precedent says defensive skill lives.

### W5. Model improvement sweep (each consumer keeps the model that wins ITS gate)

- **proj_ml (MLB projections)**: add an SDR quality prior to
  `DEF_FEATURE_CANDIDATES`, forward-chained through the `def_feature_backtest`
  protocol, must beat the incumbent `pos_adj_prior` alone (B2 point ii). Mechanism:
  pos_adj_prior is realized position-runs; SDR prior adds fielding QUALITY with
  better measurement than the failed `def_war_share` ratio. FA pricing inherits
  automatically via `contract_war_path` if it ships.
- **def_home / positional migration**: SDR-conditioned position-hold (P(stays at SS |
  SDR percentile)); refresh the migration matrix behind prospect_def_value; per-B2
  each PAL cell gets a validity gate.
- **Org tendencies**: org-level defensive development deltas (do orgs improve
  defenders?), descriptive board, descriptive registry row.
- **aStuff+ triangulation**: eWAR pitching vs aStuff+ convergent-validity panel,
  descriptive note in the eval, no gate.
- **Explicit non-lanes, recorded here so they are not re-derived**: team outlook
  accounting stays bWAR (league-sum conventions); betting is FROZEN (standing; the
  only future note is SDR team-defense as a schema-4 candidate after the B3/B4
  window opens ~2026-09-13); fantasy scoring prices no defense; arbitration is
  comps-driven and defense is not an arb driver; proj_lgbm retraining on eWAR
  labels is possible but is a separate heavy lane (4-pin cascade) only worth
  opening if W3 wins decisively.

### W6. Ideas backlog (ranked; anything predictive goes through a gate)

Display/product:
1. /mlbstats/ Defense board (W2, committed).
2. MiLB Glove Boards by level: top defenders per level/position. Unique public
   content if `milb_sdr_eval` validates; every superlative derives from it.
3. SDR trajectory sparklines + age-curve context bands on player pages.
4. Team defense view: org SDR sum, by-position heat strip (projections teams view
   gains a column; entity pages gain a trend).
5. "eWAR vs bWAR: biggest disagreements" watch table (Model Watch pattern), with the
   FIP-vs-runs explanation chip per pitcher.
6. Defense-share chip: % of a player's value from the glove (the value identity
   already lives in `positional_fit_ui`).
7. Catcher defense board IF SDR covers catchers (fills the refused-framing hole; if
   not, the out-of-scope note stays and says why).
8. Farm org defensive-value sums on farm detail (display only; the farm composite
   does not change without its own gate).
9. GFX cards: SDR badge + eWAR line; compare cards (#cmp) gain eWAR rows.
10. Editorial spotlights: "gloves nobody ranks" from MiLB SDR (editorial_eval
    machinery already scores flag hit rates).
11. Time Machine: eWAR historical views (ewar.json holds 2016-2026).
12. positional-adjustments round-trip: publish the SDR-derived ladder beside the
    B-Ref inversion in `positional-adjustments/` (the README already promises it).
Model/measurement:
13. eWAR labels for the FA model backtests (R3's FA half; mind the R3b trap: a more
    persistent label raises the carry-forward BASELINE before it raises the model).
14. eWAR/PA+ and eWAR/IP+ display indices (fresh harness runs; frozen-vintage
    discipline).
15. SDR-consistent positional adjustment inside eWAR itself (replace B-Ref rpos;
    risky, later, own gate).
16. SDR uncertainty bands from innings shrinkage (`k_inn` equivalents).
17. Farm-grade defensive depth signal from org MiLB SDR (farm grades gate).
18. Two-way audit: eWAR rows for Ohtani-class players keyed (mlbam, side) (the
    fantasy collision precedent).
19. Draft/College SDR: no data exists; research note only, do not build.

---

## 4. Standing-rule compliance (the checklist that has burned sessions)

Registry row + eval artifact + freshness-map entry for every model; failed
challengers land as blocks in the parent artifact, never standalone; derived copy
only, no hardcoded claims or numbers; no em-dash anywhere in site copy; gates
pre-registered with frozen clauses, census before clauses, floors derived on the
frame being tested, Holm + noise twins + zero-info controls; the artifact is the
evidence, not the exit code; explicit `cd prospect-tracker` in every shell call;
pytest only from prospect-tracker/, never while editing, commit before starting a
suite (conftest revert hazard); two-to-three rebuild passes for any scoring change
(one-run lag joins); golden restamp + fingerprint + epoch discipline for any grade
basis move; `tools/gen_audit_docs.py` after registry edits; restamp hand-authored
pages after asset edits; ML quantile points are never summed; never put an
`*_eval.json` in data_exclude; leaderboard JSON consumers (betting, fantasy, cards,
projections.js, build_site) must survive new fields; suite baseline is TWO reds and
any new red needs a written leave condition.

## 5. Risks, ranked

1. **Intake risk dominates.** Every wave gates on Will's drop; the manifest paths are
   data-blocked locally today. W0 can complete in a day; nothing else starts until
   the census lands.
2. **Coverage cliffs.** eWAR starts 2016; MiLB SDR is likely shallower. Labels and
   driver frames must restrict folds honestly; era indicators are inadmissible;
   thin folds produce underpowered nulls that must be recorded as underpowered.
3. **The re-anchor cascade.** Five pinned bWAR families; a partial flip is the named
   failure mode; the epoch checklist in W3.5 is the only sanctioned route.
4. **Label affinity.** Judging eFV-vs-consensus on our own eWAR labels tilts our
   way; the cross-label matrix is mandatory and the honest cell leads.
5. **Basis mixing in dollars or columns.** One basis per path, tests pin it.
6. **Claims discipline.** Forecast-not-describe framing for eWAR; every SDR
   superlative derives from `milb_sdr_eval`.

## 5b. Decision record (2026-08-18)

Owner said "proceed" with Will reporting his stack in the repo. Census
finding, verified: his METHOD is in the repo (defense-plus 25 pipeline
stages incl. 05_skill_composites + 25_catcher_components, so the metric is
genuinely SDR-class under the re-open clause; milb-projections contracts +
adapters + fixtures) and his DATA is not (no parquet anywhere, no raw
inputs, no handoff dir, and NO export adapter exists for the defense card).
The recommendations for D1, D2, D3, D4, D6, D7 are ADOPTED as written. D5
stays an owner checkpoint exactly as section 2 states: the W3 measurement is
pre-authorized, the flip is not.

W0 EXECUTED 2026-08-18: sdr_intake.py (drop seam validated against Will's
own pitcher_ewar contract and fixture; declared defense-card contract with
the range-only refusal; census-first acceptance; append-only manifest),
test_sdr_intake.py (11 tests), three frozen gates under docs/sdr-2026-08-18/
(SDR_EVAL, EWAR_V3_MERGE, MILB_SDR_EVAL), pre-registration stubs
data/sdr_eval.json + data/milb_sdr_eval.json, registry rows sdr_mlb +
sdr_milb (provisional, registered-and-waiting), the intake request
docs/sdr-intake-request-2026-08-18.md naming the defense-card adapter as
the one real gap. W1 and everything after remain DATA-BLOCKED until Will's
drop passes the preflight.

## 6. Sequencing

W0 now (intake form + seam + pre-registrations do not need data). W1 one heavy
session once the drop lands. W2 one to two sessions after W1 goes green. W3 is the
big one: a measurement session, then (only on an owner yes at D5) a dedicated epoch
session. W4 a half-session of measurement plus the component-model ship. W5
distributed, one gate per session alongside other work. W6 continuous.

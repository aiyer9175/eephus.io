# Master Plan 2026-07-29: eFV evaluation, FA module repair, and platform improvements

Executor: Claude Opus 5. Author: planning session 2026-07-29 (Fable), grounded in seven
read-only investigation agents that measured everything below against the live tree,
`data/xfv.json` (generated 2026-07-28), `data/fa_class.json` (2026-07-29), `prospects.db`,
and the scored-live artifacts. Nothing in this document is speculative unless marked
HYPOTHESIS. Every number was reproduced from served artifacts or live code during planning;
the Chisholm price and the served board ranks were reproduced bit-for-bit.

Repo root for all paths: `prospect-tracker/`.

---

## 0. Ground rules for the executor (non-negotiable)

1. **Gate standard.** Every model-output-moving change goes through a pre-registered gate
   under `docs/EFV_GATE_STANDARD.md` (MDE95 floors, zero-information control, permutation
   null, >=4 time splits, paired bootstrap with refit). A sub-floor effect is a NULL, not a
   "small win". FA-side changes ride `tools/fa_market_feature_lab.py` (Gate 2) or
   `fa_fit_backtest.py` (Gate 3) with criteria written before any arm runs.
2. **Never compare grade bases on the scored artifact.** `efv_score.run()` fits ridge AND
   output calibration on the rows it scores, so raw-grade bias is ~0 by construction there
   and reverses OOS. Use forward-chained frames only (`DEFECT_C_LOSS_LEDGER.md:176-181`).
3. **Registry discipline.** Every new model/metric: `data/model_registry.json` row + eval
   artifact + `MODEL_GLOSSARY` mapping + glossary entry. Failed challengers are blocks inside
   the parent artifact, never standalone `*_eval.json`. A registry row can describe code that
   does not exist; when they disagree, the row moves, never the code.
4. **conftest gotchas.** Never edit tracked files while pytest runs (session-end git-restore
   churn, more aggressive now that the tree is committed). After a full suite, restamp the
   golden ONLY from a production `efv_export.py --all` run.
5. **Data-write hazards.** `run_market_gate(persist=True)` rewrites `data/fa_dpw_series.json`
   (the whole valuation engine): md5 `fa_dpw_series.json` + `value_framework.json` before and
   after any value_framework/fa work. Agents must not re-run ingest/export modules casually;
   generated-artifact churn was the 07-29 sweep's biggest cleanup cost.
6. **Copy rules.** No em-dashes in user-facing prose (`tools/strip_emdashes.py --check`,
   `tools/copy_lint.py --check`); FV/tool grades display CEILING, eFV and "+" stats round to
   nearest; bWAR site-wide.
7. **Commit policy.** Owner's current policy is commit-locally-per-phase, NO push. 19+ local
   commits sit unpushed on main. Do not push without an explicit owner instruction.
8. **Fabrication check.** Independently re-verify every claimed PASS on the real path before
   shipping (the W-SB mean-imputation fabrication is the precedent; the mean-impute
   sensitivity block in `data/xfv_wrc_eval.json` is exactly the trick to look for).
9. **Read WHICH LINE a test fails on** before reasoning about what it detects (the 07-29
   "dead tripwire" lesson).
10. **Do not re-attempt closed loss lanes blind.** The ledger list relevant here: surplus map
    refit (REFUTED), C-prime (REFUTED), dollar-basis flip to raw (DO-NOT-FLIP), wRC+ eFV
    feature arms A1/A2/A3/A4 (all NULL), K-prior lane, peak-WAR training target, decayed
    multi-year plus-metrics, defense/physical eFV features, platoon features.

---

## 1. The headline diagnosis (read before touching anything)

**One structural defect explains three of the owner's five eFV complaints.** The served
board rank basis changed twice in five days with no model change:

- 2026-07-25: `storage.py:4577` `BOARD_GRADE_FIELD = "xfv_grade"` - the board left the
  side-normalized quantile and began ranking on the RAW model grade.
- 2026-07-29: `efv_board_scale.py:183` `ENABLED_DEFAULT = False` - the per-side affine that
  partially compensated was disabled (correctly: its primary gate was a measured null).

The raw grade is not cross-side comparable. Measured on the live board: at consensus 46-54+,
the model's WAR head lifts hitters +5.3 to +5.6 FV over consensus while pitchers sit at
-0.2 to -1.6. Raw-grade marginal: mean 25.07 / sd 10.25 vs consensus 36.79 / 3.61. Result:

| symptom | measured |
| --- | --- |
| Pitchers vanish from the top 100 | served 8 P/100 (1 P/25) vs consensus 28 P/100 (6 P/25); the four named pitchers moved 39->148, 8->15, 12->50, 48->143 across the two flips with ZERO grade changes |
| Bradfield inside the top 100 | #87 on raw basis vs #118 on quantile basis |
| Arias "lost #1" (second-order) | the 07-25 build also carried the gradenorm re-map and the Wave-H matrix rebuild (Section 4); the basis flip changed the shape of every number the owner sees |
| Rank churn published as player movement | Seth Hernandez card reads "down 33, confidence: high" off a basis flip; `BOARD_RANK_BASIS_EPOCH` (storage.py:4584) is still "2026-07-25" and did not gate the 07-29 re-rank |
| Two inconsistent bases served at once | surplus is priced on the quantile (`efv_score.py:1580`), `xfv_history.json` + movement are on the quantile, fantasy dynasty ranks are on the blend; the board is on raw. Luis Hernandez's "low grade" (49.1) IS the retired quantile field on a stale surface while the board serves him 55.0 at #61 |

Displaced, not marked down: most consensus-top-100 pitchers missing from the served top 100
carry xfv_minus_consensus of ~0.0 (dzierwa +0.0, hardin +0.0, scarborough -0.0). The model
does not hate pitchers; the basis lets inflated hitter raw grades pass them.

Also load-bearing: `efv_board_scale.py:101-107` already documents that the raw basis puts
top-25 pit share at 0.04 against the repo's own F-SIDE calibration-honest reference of
0.09-0.11. The board currently over-corrects pitchers DOWNWARD relative to the repo's own
fairness line, and no side correction of any kind is active on the board number.

**Phase A fixes this before any model work.** Do not tune pitcher features to compensate for
a display-basis defect.

---

## 2. Owner decision queue (blocking; collect these before executing the dependent phase)

- **D1 (Phase A): board rank basis.** Options in A1. Recommendation: rank on a
  cross-side-calibrated basis (quantile, or raw passed through a properly gated per-side
  calibration); do NOT keep raw-uncorrected. Pricing stays on quantile per the 07-29
  DO-NOT-FLIP analysis regardless.
- **D2 (Phase C): age-penalty onset.** The current hard gate is 25.0 with no effect below.
  A continuous ramp from ~23.0 is what actually moves Bradfield out of the top 100
  (rank 83 -> 104). Onset age is a policy dial the owner must pick (offer 22/23/24 with the
  measured board effect of each).
- **D3 (Phase E): FA verdict banding per side.** Pooled terciles currently produce
  "52% of pitchers = overpay, 2% = value" vs "51% of hitters = value". Per-pos-group
  banding is a display-policy change.
- **D4 (Phase B6): gradenorm re-map.** The 07-25 consensus re-map moved 5,036 players
  (pool mean -1.14 FV, top prospects -4.89) off a mechanical alias fix. Keep (it is more
  correct per-source) or re-tune; either way the owner should know it, not just live it.
- **D5: push policy** for the accumulated local commits (out of scope to execute; flag it).
- **D6 (Phase D): wRC+ into eFV features.** Recommendation: NO (measured null 2026-07-24,
  ledger in `data/xfv_wrc_eval.json`); the wRC+ program below ships it everywhere the owner
  actually sees OPS+ instead. If the owner insists on the model arm, only the two untested
  variants (Section D5) may run, pre-registered, with the expected-null stated.

---

## Phase A: board basis + single-basis coherence (P0, do first)

### A1. Restore a cross-side-comparable board rank basis
- Files: `storage.py:4535-4584` (BOARD_GRADE_FIELD, BOARD_RANK_BASIS_EPOCH),
  `efv_board_scale.py`, `efv_score.py:1543-1561` (quantile map), `prospx/index.html:32033`.
- Options, with measured top-100 pitcher share: (i) revert board rank to
  `xfv_grade_quantile` -> 28 P/100 (consensus-pinned by construction, per the confirmed
  F-SIDE analysis: the per-side quantile map reproduces each side's consensus multiset
  exactly); (ii) keep raw but re-enable a per-side calibration fitted under a REAL gate
  (the disabled affine moved top-100 share 8 -> 16; its gap@55 gate was null, so a new fit
  needs a new gate design - e.g. calibrate per-side to the OOS realized-WAR frame from
  `CALIBRATION_FINDINGS.md` Defect A: eFV pit slope 0.587 vs hit 0.654); (iii) rank on
  rank_war (blend) - never evaluated as a board basis, needs its own gate.
- Constraint: whatever wins must keep pricing on the quantile basis (dollar-basis
  DO-NOT-FLIP stands; domain of the anchor curve + surplus map is consensus-scale FV).
- Gate: forward-chained frame only (ground rule 2). Acceptance: basis is identical across
  board sort, display grade, movement input, and history append; top-100 side shares within
  the F-SIDE reference band; documented in a new
  `docs/efv-2026-07-29/BOARD_BASIS_DECISION.md`.

### A2. Single-basis coherence sweep
Surfaces still on the quantile or mixed today: surplus pricing (stays), `xfv_history.json`
(flat-by-construction for Arias since 05-22 because it re-maps through the current grade
map - `efv_score.py:1180`), `movement.xfv_movement`, fantasy dynasty ranks (rank_war),
`efv_board_scale.py:121-134` drift notes, any page still reading `xfv_grade_quantile` as
"the grade" (the Luis Hernandez 49.1 sighting). Deliverable: a table of every surface and
its basis, then align or explicitly label each. Add a test that asserts the board, movement,
and history all read BOARD_GRADE_FIELD.

### A3. Movement/epoch guard
`BOARD_RANK_BASIS_EPOCH` did not gate the 07-29 re-rank; the movement engine published a
basis flip as player movement with high confidence. Fix: bump the epoch on ANY change to
(BOARD_GRADE_FIELD, efv_board_scale.ENABLED_DEFAULT, quantile-map definition), and make the
movement engine suppress/re-baseline across an epoch boundary. Pin with a test.

### A4. Board-composition tripwire
New test: served top-100 side share may not deviate from the consensus top-100 share by more
than a registered band without a registered decision artifact. This is the test that would
have caught both the 07-25 and 07-29 flips.

---

## Phase B: eFV targeted defects (case-study driven)

### B1. Injury factor else-branch (Seth Hernandez, -1.25 FV off 4 IL days)
`efv_score.py:613-642`: "60" in type -> 0.70, "15"/"10" -> 0.82, **else -> 0.90** - so a
7-day IL (and any unclassified type) prices as a serious injury. Hernandez: il_on=1,
il_type='7-day', 4 days, factor 0.90 = -1.25 FV = 18 board spots; removing it moves him
joint rank 44 -> 26. Fix: add the 7-day branch (mild, e.g. 0.97 or days-scaled), make the
else-branch days-aware rather than type-string-aware. Gate: bounded board-movement battery
+ per-side incidence check (pit 13.1% at 0.760 vs hit 10.2% at 0.792). Pin
test_injury_factor_bounds companion.

### B2. Backgrade-path coverage gap
`efv_score.py:1746-1754`: the prior-anchored path applies ONLY `_injury_factor` - no age,
role, statcast tilt, overlay, or side-fairness. 2,525 rows (1,280 P), and jackson_flora
reaches served rank 76 through it. Decide and gate: apply the same factor stack, or
document the exemption and exclude the path from top-100 eligibility.

### B3. Primary-level 50-PA cliff -> continuous level blend (Arias forward cliff + Luis Hernandez)
`efv_dataset.py:321,347-372`: highest level with >=50 PA is the season's ONLY production
source. Two live harms: Luis Hernandez prices at CPX (level_rank 1.0) despite the site
showing Single-A, costing ~+0.48 WAR vs an A-ball read; Arias will lose his .994 AA OPS
from every production feature the day he clears 50 AAA PA (his current AAA line is 14 PA of
.476 - expect a second, larger, spurious drop). Fix: PA-weighted blend of per-level season
rows (weights = pa/(pa+K) per level against that level's norm), replacing the winner-take-all
gate. This is a matrix-rebuild-coupled model change: full EFV_GATE_STANDARD gate, and note
the peak-block interaction (`efv_dataset.py:432-440`). Expected effect is accuracy-neutral
to positive with large single-player corrections; if the gate reads null on pooled metrics,
ship-decision rests on the case-repair value with owner sign-off (it moves grades).

### B4. Statcast overlay level-reliability (Luis Hernandez -0.64 WAR from CPX tracking)
SC+ 77 -> x0.965 tilt plus S-XLINE lean -0.88 FV, at COMPLEX level, on a 17-year-old -
triple his entire youth credit. The overlay/tilt applies one reliability everywhere.
Fix candidate: level-conditional overlay weight (AAA full, A-ball reduced, CPX/DSL heavily
shrunk or excluded), gated. Related registered candidate: C1 SC+ sample gate/shrink in
`GATED_CANDIDATES.md` - execute C1's registered gate design as part of this item rather
than as a separate lane.

### B5. Re-gate the Wave-H shrink loosening (K_REL_PA 50) - the Arias mechanism
`efv_dataset.py:236-244,289` `_K_REL_PA=50` (was 100). Wave-H's own ledger: hit -0.0024,
`regression_flag: true`, kept on a no-regression arbiter - and it is the single largest
contributor to Arias's -0.88 model WAR on 07-25 (his ops_rel CONTRIBUTION halved while his
raw feature improved 21%). Re-run 50 vs 100 under EFV_GATE_STANDARD on repaired current
matrices with the zero-info control. If unresolvable, prefer the setting that does not
reorder multi-sigma production outliers (measure Spearman(old,new) on the top decile of
|ops_rel| as a registered secondary). Blast radius: whole board; coordinate with B3.

### B6. Gradenorm re-map audit (D4)
`consensus.py:137-147,236-262,554-573`, `grade_normalization.py:43-44`,
receipt `data/_gn_lab/consensus_modes.json` (arias/made/de_vries -4.89, cholowsky 0.00,
pool mean -1.14, 5,036 movers). The Pipeline-International alias fix is mechanically
correct; what is unaudited is the JOINT effect of re-mapping top-band grades down 4-5 FV
while draft-signing provisional rows (Cholowsky path) are untouched. Deliverables:
(a) per-source before/after mapping curves at the top band, (b) verify the intl-board FV65
exclusion rule (n_sources) is intentional for cases like Luis Hernandez, (c) an owner-facing
one-pager: who moved and why. No code change without a gate; this is an audit item.

### B7. Pitcher-side model head (the real modeling question)
The wedge (hit +5.3/+5.6 vs pit ~0 at consensus 50+) partly reflects the model's own
head: 8 pitcher features vs 14 hitter, pit blend lambda floating ~0.54, pit age term
inverted (+0.0589, handled by hiding the chip - `efv_score.py:501-519`), no pit
age-for-level term (w=-0.0077). After Phase A lands (so the board is no longer amplifying
it), run ONE registered program: pitcher feature-parity arms (age handled in C4, k/bb
trends, level_rank interaction), scored under the gate standard on the pit weak cells
(FV45-50, 2019-2021 era). Prior consensus: the flagship is at ceiling; expect nulls; the
deliverable is the honest ledger either way. Do NOT ship blanket pitcher boosts (F-SIDE S4
ban stands: mid-board pitchers OUTperform).

---

## Phase C: age pipeline modernization (decimal + gradual)

Evidence base: the model never sees a decimal age (4,260/4,260 live rows integer;
`age_missing` doubly dead at `efv_dataset.py:396-401`/`efv_model.py:588-589`); mean floor
loss 0.52 yr; birth-month bias up to 0.91 yr (July-born flattered most); 17.6% of rows have
age_rel_level exactly 0.0 as an integer artifact; three disagreeing norm tables with the
model's static `_TYPICAL_LEVEL_AGE` 2.4 yr younger than the live empirical AAA norm; the
tested "site table" swap (`tools/_av_agelevel_verify.py:25`) tested `eta.EXPECTED_AGES`,
NOT the empirical norms - the empirical swap has never been evaluated.

### C1. Decimal ages into the model
`efv_dataset.py:395-403`: use the season-midpoint decimal age unconditionally (code exists,
gated behind `if age is None`). Justification: correctness + birth-month de-bias, NOT
accuracy (a prior decimal swap read slightly negative: 0.3308 -> 0.3291; expect ~neutral;
Bradfield moves 1 spot, Luis Hernandez gets slightly WORSE - say so in the ship note).
Ship as a correctness change with a no-regression gate + zero-info control.

### C2. One norm table: per-level-season, decimal, prospect-filtered
Replace `_TYPICAL_LEVEL_AGE` (efv_dataset.py:117-121) with empirical per-level-season norms
computed on a prospect-filtered cohort (current empirical table embeds org vets/rehabbers:
AAA 26.37). Reconcile with `eta.EXPECTED_AGES` and `level_norms` so the site and model stop
telling opposite stories (site: Bradfield "young for AAA, -1.7"; model: exactly neutral).
NEVER evaluated - full gate. Coupled to C1.

### C3. Replace hard age gates with continuous ramps
- `efv_score.py:576` age factor: no penalty below exactly 25.0, then -0.10/yr. Replace with
  a ramp from the D2 onset (owner picks 22/23/24; measured: onset 23 moves Bradfield
  83 -> 104; onset 22 -> 109). Keep the 0.75 floor.
- `efv_score.py:608-610` role factor staircase (1.0 / 0.80 / 0.70 at 25/26): same ramp.
- `eta.py:413-428` integer-diff staircase (0.35-0.40 yr ETA jumps): linear interpolation.
- `age_level.py:70-78` 5-tier TBS boost: derive tier label from a continuous value; keep
  labels for display.
- `efv_dataset.py:412-414` +-3.5 clip: replace hard clip with soft saturation (489 rows
  pinned at +3.5 vs 4 at -3.5 - the cap currently shields old-for-level org filler).
- `storage.py:4976` graduate WAG step, spotlight gates (spotlights.py) - convert or
  explicitly exempt with a comment.
Each is a separate gated arm; ETA changes re-run `eta_backtest` (KM protocol); TBS changes
are board-order-affecting via fvCmpDesc tie-break.

### C4. Pitcher age terms
`efv_model.py:150,189` + hidden chip at `efv_score.py:501-519`. The pit ridge fits age
POSITIVE (+0.0589) and age_rel_level ~0. Registered arms: (a) drop pit `age` from the
feature set (it is fitting a survivorship artifact), (b) pit age_rel_level with the C2
norms. Un-hide the chip only when the sign is defensible.

### C5. Pricing-layer age coherence
`value_framework.py:1260-1262` 0.5-yr debut-age quantization (24.3/24.5/24.7 identical);
`expected_surplus_usd` INCREASES with age at fixed grade ($27.83M at 24.0 -> $29.16M at
25.5) because the aging renormalization front-loads pre-arb WAR - directionally wrong as a
prospect-age signal. Quantization: shrink the grid (cheap). The surplus-age slope: document
and put to the owner; changing it moves dollars and needs the surplus gate.

---

## Phase D: the wRC+ program (display everywhere the owner sees OPS+; model NO)

Ground truth: `wrc_rates.py` (complete MiLB wOBA/wRC machinery, frozen),
`.cache/milb_full_stats/` (84,039 rows, ALL components 100% populated, 99.3% coverage),
`data/xfv_wrc_eval.json` (the 2026-07-24 rejection: A1 +0.0003 / A2 +0.0000 / A4 -0.0001
vs MDE95 ~0.017 - eFV already consumes the decomposed pieces). MLB Stats has NO OPS+
(HEM+ is already the wOBA-family index; `build_site.py:3869-3871` discloses "this site
computes no wRC+"). A true industry wRC+ already sits in the DB (`sabermetrics` table,
1,116 rows) and veterans' projections already export wRC+ (`fa_projection.py:1047-1074`).

### D1. Persist the counting stats (enabler, zero network cost for statlines path)
`stats.py:1608-1631, 1684-1705, 1916-1941, 1413`: `_combine_stints` ALREADY sums
PA/H/2B(via TB path)/BB/HBP/SF/SO and discards them - persist into `statlines` +
`career_stats` (~10 lines across 4 sites). `milb_history.py:141-148`: add the ~9 missing
keys to the lean row (needs the one-time 308-file cache refetch; the W-WRC refetch proved
the pattern). Backfill sportId 15 while there.

### D2. MiLB display chip: `ops_plus_level` -> `wrc_plus_level`
Producer `storage.py:8915-8967` (note: shrinks on AB with K_AB=170 because PA was missing -
after D1, shrink on PA); browser twin `prospx/index.html:42476-42478`. Coordinated swap,
because the chip feeds: RPS+ hitter leg (= ops_plus_level - 100, browser-computed),
`bayes_trade_value.py` reads (199-266, 2280-2297, 3114-3118, 3386-3388), glossary entries
(ops_plus, rps_plus x3 implementations, wrc_plus "MiLB uses RPS+ proxy" copy), and the
asserted copy string "Mirrors the wRC+/OPS+ shape" (`build_glossary_data.py:104-105`).
Method: `wrc_rates.build_index()` constants (already per level-season); keep the 0-impute
convention. Ship checklist per the Arkmetric pattern (Section G). This moves published
chips for everyone: bounded display-movement battery + owner heads-up, but it is a display
metric (no eFV grade moves).
- Bradfield note for the owner: his OPS+ 93 becomes a wRC+-basis number; do not promise it
  reads worse/better until measured.

### D3. MLB Stats: industry wRC+ column beside HEM+
Surface `sabermetrics.wrc_plus` (already ingested) as a display column on Hitter
Leaderboards with provenance "MLB StatsAPI published value" (the ARKMETRIC conventions doc
already carries the exception for industry metrics displayed as published). Exporter join in
`hitter_export.py` + column def in `assets/mlbstats.js` HITTER_COLS + glossary. Optionally
retitle HEM+ tooltips to sharpen "HEM+ is our shrunk wOBA index; wRC+ is the industry
number" (respect the `build_site.py:3915-3919` disclosure).

### D4. Projections: prospect rate path
Veterans already ship woba[]/wrc[]/fip[]; prospects render a dash (FV-anchored outcome
model has no rate machinery). Build the FV->rate bridge: map each outcome bucket's WAR to a
wRC+ via the same fitted WAR<->wRAA relation used in `fa_projection.war_from_projection`,
or fit p50 wRC+ by FV x age from resolved cohorts. Registered new model row (provisional),
own eval artifact; display with the same dash-until-covered honesty.

### D5. eFV feature swap: DO NOT RE-RUN (D6 default)
A1/A2/A3/A4 measured null with an a-priori-null prediction recorded BEFORE the run. Only
two arms were never tested: (i) true replacement including `prod_trend` (efv_dataset.py:447
also switches), (ii) full-block replacement of obp_rel+iso_rel+ops_rel by wrc_rel. Both
expected null; both delete/alter features that pass their own gates (gate standard s129
applies). Run only on explicit owner insistence, pre-registered, AUC carve-out noted
(wrc_rel senses milb-block presence).

---

## Phase E: FA projection + market repair (the Chisholm class)

Diagnosis (reproduced to the dollar): projAav $7.35M = warY1 1.68 through a ~2.5-power
market amplifier. WAR-path misses: defense/position blindness in the WAR map (-1.1 on his
2025 alone; only positional term is a catcher dummy - `fa_projection.py:1125-1135`), PT
model caps regulars near 590 PA (`fa_config.yaml:78`; measured mean projPA 456 vs actual
511), [5,3,2] weights put 41% on the 2/3-complete down season (docstring and gate1 notes
claim 5/4/3 - `fa_projection.py:10` vs `fa_config.yaml:53`), regression+aging -0.37.
Market-stage misses: log_rational elasticity 0.676 with log(dpw) -0.193 (net $/WAR
pass-through 0.483), RECAL_MODE="off" while `_fit_recal`'s own docstring documents top
deciles realizing 1.3-1.6x predicted, AAV divisor rounds years (guar priced at 1.7765 yr,
divided by 2; 1,006/1,528 corpus rows distorted >10%; `fa_market.py:100,1508`), rate_line
wOBA coefficient wrong-signed (-1.28) and self-documented as noise (`fa_market.py:1008-1022`).
Systemic: 30 members with a 3+ bWAR season in 3 years project under $15M AAV; engine
projected 6 hitters >=4 WAR in a season when 42 achieved it; top-tier ($10-20M) bias -$5.02M.

Priority-ordered, each through its own pre-registered Gate-1/Gate-2 arm:

### E1. Per-side/per-tier measurement FIRST (cheap, blocking nothing)
Add side/pos-group slices to both gates: `fa_backtest.py:195-196,301-303` (Gate 1 war:{side}
accumulators - rows already carry side) and `:393-395,460-476` (Gate 2 guarantee:{group}
MAE AND bias). Plus a Deal+/verdict distribution slice per group vs the 33/33/33 design
(`tools/_am_fa_dealplus.py` is the home). This turns the owner's "overprojecting pitchers /
underprojecting hitters" perception into a measured target; note the existing artifacts
already show hitters over-projected at WAR level (+0.050 vs +0.036/season) while the
verdict layer inverts it - the fix target is price/verdict, not WAR sign.

### E2. Defense/position into the WAR reconstruction (the biggest single lever)
Options, gated against Gate 1 war MAE + the >=4-bWAR compression cell (predicted 4.17 vs
actual 5.43): (a) add a realized-WAR channel to `war_from_projection` (e.g. blend map-WAR
with a 3yr PA-weighted realized bWAR rate, the owner's instinct - measured for Chisholm:
3.09 WAR/600 vs engine 1.68); (b) add position-group dummies + a fielding-runs Marcel to
the WAR map. (a) is simpler and directly answers the owner ask; guard against
double-counting the rate signal.

### E3. Playing-time model
`pt = 0.5 e1 + 0.1 e2 + 200` cannot reach 700 (max 684 measured). Refit coefficients or add
an established-workload channel; gate on projPA vs actual (mean 456 vs 511) without
regressing the thin-platform protections (`fa_projection.py:906-930` Lindor logic stays).

### E4. Marcel weights + in-progress season
Fix the doc/config mismatch ([5,3,2] vs "5/4/3" - decide which is intended, gate both).
Add the missing distinction the owner actually wants: a partial season currently gets full
weight-per-PA with no pace/decline separation. Candidate: weight the in-progress season by
completeness (w1_eff = 5 * frac) so a 2/3-complete season cannot dominate three full ones.
Pre-register; this moves every in-season projection.

### E5. Market-stage recalibration ON
`RECAL_MODE` "fit" moves Chisholm $7.35M -> $8.69M and cuts the $10-20M tier bias
-5.02 -> -3.39; per-pos-group recal (dict keyed by `_pos_group`, riding the existing
`fa_market.py:1487-1489` hook) is the minimal-surface fix for the side asymmetry. Also:
AAV_CONSISTENT=True (divide by the continuous years the guarantee was priced at), and
decide rate_line OFF (it is documented noise with a wrong-signed hitter coefficient - turn
it off in the same lab, expect no Gate-2 movement, ledger it). POS_GROUP_MODE v2: measured
DOWN for Chisholm ($7.22M) - do not flip blind; include as a lab arm only.

### E6. Verdict banding per side (D3)
`fa_market.py:1575-1586`: per-pos-group terciles or group-normalized Deal+ before banding.
Display-policy change + registry note; fixes the 51%-value/2%-value split that reads as
"overprojecting pitchers".

### E7. Hygiene
`fa_meta.json` stale vs `fa_class.json` (baseWins 83.5 vs 82.0 served); rebuild
fa_class_2028/2029 alongside; comps set improves automatically once E2 lifts war_y1
(comps match on (age, war_y1) - Pedro Alvarez/Chris Carter for a 28yo CF is a symptom).

---

## Phase F: FA team fits v4 (kill Giants-for-all-pitchers AND Dodgers-for-everyone)

Measured: SFG #1 for 85% of pitchers with warY1>=1.0 (100% top-3); LAD #1 for 69% of ALL
members (behavior term near-constant per club at weight 0.45); only 12/30 clubs ever appear
in a top-3; median #1-vs-#2 gap 0.018 (noise). Root causes, all traced: need matrix reads
only signed Spotrac contracts (`fa_fit.py:150` - arb/pre-arb invisible; 104.8 WAR / 14% of
2027 production unseen; SFG SP5 slot = 0.00 while its true 5th starter projects 0.26), the
SP slot rule `fa_fit.py:246-247` gives max need to any club with <=4 contracted SP, the
window term is symmetric bubble-proximity (0%-playoff SFG scores 3.6x locked-in LAD;
playoffPct exists unused in `mlb_projections.json`), affordability saturates at 1.0 for
49% of pitcher rows, behavior is `min(...,1)`-clipped into a club constant. Also: clubs
with zero qualifying contracts are silently dropped from fit vectors (MIA baseWins absent),
`fa_meta.teams` carries pseudo-club AVERAGES and legacy OAK beside ATH.

### F1. Projected-roster need source
`_projected_roster(class_year)` from `data/mlb_projections.json` vets (thru + the 361
thru=None arb/pre-arb rows) + prospects (eta <= class_year), keyed org -> [{pos, war_proj,
control_kind}]; primary source, Spotrac scrape as flagged fallback (mirrors the
baseline_source pattern at `fa_fit.py:338-345`). Removes the live-scrape serve-path
dependency too.
### F2. Slot rule + completeness
With full rosters `len(inc) > slot` nearly always holds; add `roster_completeness` to the
need decomposition (`fa_fit.py:496-500`) so "thin because cheap+young" is visibly distinct
from "empty". Fix the silent-drop: score missing clubs at explicit max need, never absent.
### F3. Contention term
Replace/blend `win_leverage` (`fa_fit.py:350-362`) with `team_outlook[].current.playoffPct`
(+ lockedPct / ctrlWar5y for window length). A 0%-playoff club must not out-window a lock.
### F4. Behavior discrimination + re-weight
Drop the min(...,1) clip on maxGuar/guar or replace with price-percentile-of-club-history;
re-weight so need+contention jointly out-weigh behavior (current .40/.05/.05/.05/.45 is
Gate-3-fitted but produced the LAD constant).
### F5. Gate + concentration tripwire
Re-run `fa_fit_backtest.py` (MRR/top-k, 1,173 signings; artifact is 49 days stale; registry
row provisional). ADD the registered concentration gate: max share of #1 fits by any club +
distinct clubs in top-3 (currently 12/30) - the metric that catches both failure modes.
Keep the pinned tests green (`test_fa_fit.py`, `test_fa_fit_gate.py`).
### F6. Display
Surface the need decomposition fields already shipped (`displaced_war`/`unit_war` unused by
UI) in the Fits view so the owner can see WHY a club ranks (Phase H item).

---

## Phase G: WAR/PA+ and WAR/IP+ (new Arkmetrics)

Full recipe verified against the conventions doc; the executor should follow it exactly:
- **Convention 3 (100+10z)** - a ratio index is undefined on a signed near-zero-mean rate.
  Anchor pools: qualified hitters; pitchers SPLIT BY ROLE (starter-pool WAR/IP+ in
  starter_export, reliever-pool in bullpen_export - SEM+/REM+ precedent; never one column).
- **WAR source**: bWAR via the side-separated reader (`mlb_player_export._war_daily`
  pattern, `mlb_player_export.py:245-265`); NEVER `fa_projection._war_age_maps` (sums
  sides - Ohtani's pitching WAR over his PA). Two-way: bat WAR/PA and pit WAR/IP separately,
  no discount factor needed (state why in a comment; TWO_WAY_PIT_PTH_FACTOR is display-path
  only). Copy the fail-soft degenerate-fetch refusal (`fa_projection.py:191-201`).
- **Shrink decision must be pre-registered**: WAR/PA is noisier than wOBA; if shrunk,
  mu/sd from the SHRUNK pool (the aStuff+ 7.16-per-sigma defect class), and shrink is
  non-monotone so it cannot ride a "ranking preserved" defense. Two-tier floors: pool 50 PA
  / 20 IP, display gate 100 PA (house pattern). No clamps (true-to-model policy); if a cap
  is ever wanted, the AP+ two-field pattern.
- **Plumbing**: exporter join fns modeled on `hitter_export._join_xhem_plus`; JS column defs
  in HITTER_COLS/STARTER_COLS/REL_COLS with `term:` slugs; **remCell banding, not hemCell**
  (sd=10 by construction; comment it); add to the three *_HISTORY_DROP maps; 1yr live +
  3yr FROZEN-vintage companion with the `*` provisional marker and vintage meta block.
- **Ship checklist**: glossary via a new `build_glossary_war_rate_add.py`; registry rows +
  `data/war_rate_plus_eval.json` (+ multiyear); MODEL_GLOSSARY mapping; copy gates.
  Lab `tools/war_rate_plus_lab.py` on plus_lab_harness v2 (unrounded raw predictors,
  clustered bootstrap, complete-season pairs).
- **FA integration LAST and allowed to lose**: a war_rate arm through
  `fa_market_feature_lab` with pre-registered criteria, collinearity check vs war_y1 and
  rate_line, placebo column; guarantee-MAE MDE95 is ~0.16$M and the arm is expected
  unresolvable. The metric's value is the MLB Stats display surface. Note E2's realized-WAR
  channel is the projection-side version of the same idea and is the one that moves prices.

---

## Phase H: FA display enrichment ("more details on FA pages and list")

Baseline inventory is in the FA audit (16-point list). Ship, in order of value:
1. Payload fields already computed but unrendered: `warCvar10`, `pAnyStar`,
   `surplusP10/P90` as a visible band column, option decomposition
   (`optValue/optTeamValue/optKind/optHeldBy`), `enterProbSrc` detail.
2. Fits view: on-screen need decomposition (`displaced_war`, `unit_war`, `outgoing`,
   roster_completeness from F2) instead of tooltip-only component bars.
3. Player card: 3yr realized bWAR line (24/25/26) next to the projection so the
   Chisholm-class gap is visible instead of mysterious; Spotrac
   `market_value_aav_usd` + prevAav as reference rows; rate path (wOBA/wRC+/FIP per season)
   which vets already carry in the wire.
4. List: age-decimal display, QO flag, platform-season pace vs 3yr baseline mini-cell.
5. `fa_meta.park_factors` + `qo_tax_by_payor_tier` (currently unused payload) surfaced on
   the Fits/team header where relevant.
All display-only; copy gates apply; no new model rows required except where a number is
newly derived.

---

## Phase I: standing backlog (fold into the program; do not lose)

1. **C6 registration**: the reliever Edwards-bridge inversion (surplus falls as grade rises
   for RP/SIRP/MIRP/CL between FV40-40.5; 4/20 curves non-monotone; hidden only by the v5
   zero floor) is cited in DEFECT_C_LOSS_LEDGER.md:144 as registered in GATED_CANDIDATES.md
   but IS NOT THERE. Add C6 with the measured numbers + the position-parametrized tripwire
   note. Fixing it moves reliever dollars below FV45: own gate.
2. **Defect C** (68.5% of board at $0; anchor branch owns 6,336/6,384): C-prime and the
   refit are both REFUTED - the remaining honest path is a redesign of the sub-cutover
   anchor-x-calibration interaction with a NEW gate design (the ledger's open P0). Do not
   re-run the refuted candidates.
3. **C5 inert MLB projection anchor** (`bayes_trade_value.py:3282,3347,3353`): posterior
   precedence must be written down before any fix; the naive re-apply broke 10 policy tests.
4. **Gated candidates C1-C4** (SC+ gate/shrink - now folded into B4; 15z->10z atomic
   re-band with the four `_tbsNorm` call sites; aStuff+ denominator atomic with overlay
   re-fit; TBS RPS+ revival decision).
5. **Remaining suite reds** (4, all genuine): $0-bottom-block tripwire (item 2), inert
   anchor (item 3), golden restamp (owed on next BOX production regen - do not stamp from a
   pytest tree), michael_oliveto (heals on rebuild).
6. **Identity hygiene**: luis_hernandez is CLEAN (three humans, three keys, verified) but
   the implicit suffix-minting convention is undocumented - add the two suffix keys to the
   _SPLIT_KEYS documentation or a comment so the next audit doesn't re-investigate.
7. **prospx_current re-freeze** if any surplus-affecting phase ships (the captured
   production snapshot convention; re-capture + restamp test literals).
8. **Team outlook recenter** (worst team 53.6 wins; remainder 3.49/team by 2031) - still
   open from 07-29.
9. **fa_meta AVERAGES/OAK key hygiene** (F-adjacent, trivial).

---

## Execution protocol

- **Order**: A (basis) -> B1/B2 (cheap case fixes) -> E1 (measurement) -> C (age) and
  B3-B7 in parallel lanes -> D (wRC+ display program) -> E2-E7 -> F -> G -> H -> I
  throughout as capacity allows. A MUST precede B7 and any pitcher-side tuning.
- **Per phase**: pre-registered gate doc in `docs/efv-2026-07-29/` (or a new dated dir),
  eval artifact + registry row, bounded blast-radius battery for anything touching grades/
  ranks/dollars, adversarial verify pass on any multi-lane fan-out (the 07-29 sweep pattern:
  2 of 4 lanes needed reverting and the verify phase caught it), local commit per phase.
- **Regen discipline**: after board-affecting ships, regen via production `efv_export.py`
  paths only; verify `fa_dpw_series.json`/`value_framework.json` md5 unchanged unless a
  coordinated re-anchor is the intent; re-freeze prospx_current when surplus moves.
- **Honesty**: expected-null items above (C1 decimal ages, D5 arms, G's FA arm) ship or
  close on their measured result, stated plainly. The owner's questions get direct answers
  in the ship notes: Arias (basis + 07-25 double recalibration, not his play), Bradfield
  (age ramp onset decision), Luis Hernandez (no collision; stale-surface + level-gate +
  overlay), Chisholm (WAR-path blindness x market amplifier), pitchers (board basis),
  Giants fits (arb-blind rosters + behavior constant).

# Changelog

Running changelog for holistic pass 3 (started 2026-07-01, Beta launch
2026-07-11). One entry per landed package, newest first inside each day.
Curated by hand; the generated audit deliverables (MODEL_REGISTRY.md,
SITE_MAP.md, DATA_SOURCES.md) are NOT logged here on regeneration, only when
their generator changes behavior.

Companion ledgers: docs/audit-2026-07/AUDIT_FINDINGS.md (findings +
pre-registered experiment gates), REVIEW_QUEUE.md (deferred work),
BETA_READINESS.md (go/no-go).

## 2026-07-04 (research sweep + model frontier)

Discovery ran as a 20-agent read-only audit (registry / glossary census /
correctness / frontier feasibility) with adversarial verification of every
blocker/fix-now claim. That pass refuted or downgraded 4 of 6 checked fix-now
claims: the zone/plate-discipline models are regime-safe by construction
(percentiles rank within-level; chase comes from a geometric MLB-trained zone
applied uniformly, not the ABS zone) and value_framework verified exemplary on
transform-first-aggregate-last. Deliverables: docs/audit/current_state_map.md,
docs/audit/research_check.md, docs/plans/sweep_and_frontier_plan.md,
docs/roadmap/post_launch_frontier.md.

Research-check fixes:
- OPS+ published formula corrected to the level-relative OPS ratio the code
  actually computes (was the Bill James OBP/SLG decomposition, which the shipped
  level norms cannot even reproduce). Copy-only.
- ABS-challenge-era caveats added to Chase% and CSW% (the site was silent on the
  2026 league-wide ABS regime; AAA since 2023, FSL since 2022). RPS+ headline now
  states its two scales plainly (draft z-score vs active ratio). pStuff+
  leaderboard tooltip corrected to the shipped per-batter formula. The two
  player-card "Stuff+" labels disambiguated (pStuff+ / Stuff+ (Statcast)).
- NUMBER CHANGE (owner-approved with output diff, docs/audit/rc6_shrink_impact):
  per-season ops_plus_level / era_minus_level now apply the same K_AB=170 /
  K_IP=50 empirical-Bayes shrink the headline statline uses, killing the "OPS+
  374 on 4 AB" cameo blowups. Qualified rows barely move (OPS+ median 5, ERA-
  median 10); every small-sample extreme is tamed.
- em-dashes in storage.py generated card-flag / statline notes (which bake into
  debuts.json / inactive.json outside the copy-gate scope) replaced with ' - ';
  a narrow regression test guards the note strings. statcast_plus docstring
  corrected (10 pts/sigma, z-scale not the ratio family).

Glossary reclamation (the "reclaim the glossary" mandate):
- Three shelves via a new `shelf` field: 143 Arkmetric / 23 industry / 82
  foundation (universal standard stats moved off the industry shelf).
- An `origin` credit line on every Arkmetric and industry entry: Arkmetrics say
  "original to eephus.io"; 23 industry metrics name their creator and source
  (Tango/FanGraphs for wRC+/wOBA/FIP/WPA/leverage index; Studeman xFIP; MLB
  Statcast for the bat/batted-ball/tracking suite; Alex Fast/Pitcher List CSW%).
- Three displayed-but-undefined metrics added (xwOBA, BABIP, VAA). Shelf badge +
  Origin line now render on every card (eephus-gl.js passes the fields through).
- DEFERRED to the roadmap: 41 weak-stub rewrites, 7 near-duplicate merges, 13
  multi-resolving alias disambiguations (touching aliases/permalinks 8 days from
  launch was needless risk).

Tier 1 frontier (all five owner-approved, each behind a flag, each with a
registry row + glossary entry at birth):
- Model Report Cards v0: inline champion-vs-baseline proof bars on 8 flagship
  Models & Proofs rows, behind #cards=1. Every card number traces to its eval
  artifact (a test is the anti-drift fence; the field survives refresh_stamps).
- System Duration / Window Alignment: surplus-weighted farm ETA vs the
  controlled-core WAR center on the Team Outlook board, behind #window=1. An
  economic lens no public farm ranking uses (5/30 orgs aligned, median +0.39).
- Risk-adjusted Surplus (Sortino): downside-deviation + bust column on the Trade
  Machine, behind #risk=1, from the persisted eFV fan. Local half-lambda; the
  global risk_aversion_lambda is untouched (no re-ranking).
- FV Tape: candlesticks + momentum / RSI / volatility on the consensus FV
  history, dark by default (localStorage, set via ?tape=1). Descriptive market
  signals, not predictions; RSI drops flat re-confirmations so a static grade
  never pins the gauge.
- Draft War Room: a cron (tools/draft_live_poller.py) writes a READ-ONLY
  data/draft_live.json on draft night and the PROSPX War Room view prices each
  live pick against our board and the historical pick-value curve (reach/steal
  in surplus dollars). The poller never touches prospects.db /
  draft_timeseries.json (a test asserts byte-invariance), so it cannot kill the
  mock or trigger promotion. Ships dark until the artifact appears.

Down-tiering: three "frontier" ideas (Crunch Index, Portfolio Frontier, IFA
Efficiency) are largely already built and become small display adds post-launch.
Blocked (spec, no start): Catcher/Challenge Value (no catcher-defense or ABS data
ingested), sequencing/judgment/matchups (only aggregates retained). Polish:
sticky Projections/FA headers shipped; money formatter, origin badges, qualifier
chips, nav naming deferred to the roadmap.

## 2026-07-02 (review-queue round)

- E-ISO4, the owner-approved final eFV bucket-calibration attempt, closes the
  line honestly. Tying both sides to one shared monotone grade map solved the
  cross-side ranking churn that failed the prior three attempts (cross-side
  Spearman delta is exactly 0 by construction), which isolated the real
  blocker: the pitcher bench bucket comes out materially worse no matter how
  the grade is remapped, because fixing the large and real FV45+ calibration
  gap pulls pitcher mid-grade mass toward bust. No grade-space monotone map
  can ship; the fix needs resolved 2024+ cohorts and a method below the
  grade-monotone constraint. Four attempts, four honest loss ledgers; eFV
  published numbers unchanged. Registry row xfv_grade_recal4.
- F-01 total-WAR bands DROPPED from the FA and Projections display (the
  owner-approved fallback after the R-BAND gate failed). The R-BAND
  experiment found the displayed total bands were miscalibrated beyond the
  summing bug: the incumbent summed band covers only 63% of realized
  multi-year totals (vs 80% design) because roughly a quarter of realized
  totals fall below its floor path, since players who wash out realize about
  zero WAR while the decayed p10 never reaches zero. The bands are
  mis-centered high, not merely too wide, so a narrower dependence-correct
  band covers even less (41%). Point estimates and the per-year bands stay;
  the real long-term fix (recalibrating the per-year quantile marginals to
  carry league-attrition zero mass) is REVIEW_QUEUE item 13. Loss ledger:
  data/total_band_eval.json.
- PROSPX grade cluster refactor (review-queue item 5) plus a grade-scale
  outcome band (item 4). One gradeBlock() helper now single-sources the
  eFV-round-to-nearest vs consensus-FV-ceiling decision; five duplicated
  sites route through it with byte-identical output (verified by a
  py_mini_racer golden harness), and six sites with genuinely different
  fallbacks are left in place and documented. The player-detail hero gains
  an "Outcome band" on the 20-80 grade scale, derived by inverting the
  published surplus pricing anchor at the outcome P10/P90 (a faithful
  re-expression, reproducing the grade to 0.4 MAE), hidden for provisional
  and degenerate rows, tooltip disambiguating it from scout disagreement.
- Gated experiments, all resolved honestly with loss ledgers and registry
  rows: MiLB park factors (item 2) are infeasible on cached data (the
  minors feed has no venue dimension and the Single-A statlines have no park
  key); the ERA-shrink unification (item 6) confirms the two pseudo-counts
  should stay (no shared value beats both objectives); the eFV bucket
  calibration re-attempt under a production-relevant gate (E-ISO3) fails on
  a per-side materiality check and year-dependent cross-side rank churn, the
  final attempt against this data vintage. eFV published numbers unchanged.
- Overseas re-check (item 8): the hitter wRC+ factor blocker has dissolved
  for NPB (FanGraphs already supplies league-and-park-adjusted wRC+ that
  overseas_stats.py parses; the only missing input is curating about ten
  FanGraphs player ids), upgraded to READY-TO-RUN and queued with a
  pre-registered gate; CPBL and Cuba stay blocked on cohort and source
  gaps. docs/audit-2026-07/overseas-factors-recheck.md.
- Country/IFA entity pages (item 9) deferred: the build lane failed on a
  structured-output error, not a data problem; re-run queued as item 14.

## 2026-07-02

- Wave 2 close-out: adversarial verification of the whole pass (4 read-only
  lanes, 16 findings, none P0) plus the owner-directed eFV improvement round
  (3 gated experiments, gates pre-registered before any run, all NO-SHIP).
  Fixes landed from the verification: the track-record panel's glossary deep
  link now uses the hash form the glossary actually parses; the gmLI
  consistency tool derives its seasons from the leaderboards payload instead
  of freezing at 2026 (gate numbers unchanged: pooled rho 0.4683, split-half
  0.5294) and writes atomically; the SC+ component diagnostic pins its
  keep/reweight decision to closed outcome seasons (the in-progress 2026
  season had made committed numbers drift) and its now-firing reweight signal
  is queued as REVIEW_QUEUE item 12 rather than shipped (n=23 per side); the
  monthly pipeline regenerates the generated audit docs right after registry
  restamps; the Upside strip lays out evenly at any season count; static
  pages rebuilt so their cache-busters match the shipped JS. eFV round
  verdicts, all honest loss ledgers with registry rows: the grade-space
  monotone recalibration fixed the isotonic candidate's rank-flattening and
  doubled the calibration gain but still fails the rank tolerance (which the
  identity transform itself fails, a gate-design fact recorded for any future
  attempt); per-cohort blend lambdas are noise-dominated at current cohort
  depth; the AA/AAA pitcher tracking overlay has zero trainable coverage
  until the 2024 debut cohort resolves. eFV stays at its trainable-data
  ceiling on ranking; its published numbers are unchanged.
- PROSPX display work (lane P): the player-detail Surplus card now shows the
  eFV surplus credible band in plain dollars ("Surplus band P10 to P90",
  explicitly surplus dollars, never a grade band; hidden when the band is
  degenerate); Generate GFX prospect badges follow the board's Rank-by toggle
  (eFV rounded to nearest when eFV leads, consensus FV ceiling otherwise) and
  graduate badges follow the Debuted lead-grade toggle, with footer legends
  tracking the mode; new collapsed "eFV vs consensus FV" track-record panel on
  the Debuted tab (pooled OOS Spearman per side, per-era and per-tier splits,
  resolved-disagreement receipts from committed eval artifacts); new inline-SVG
  reliability diagram of the shipped 5-bucket outcome distribution (the
  rejected isotonic candidate's "before" curves, which are the live model).
- Module apps (lane H1): every MLB module app (projections, mlbstats, pal, fa,
  both collegesavant apps) now renders a visible error state with a retry
  affordance when its data payload fails to load, replacing silent blanks;
  /mlbstats/ leads with 2-sentence REM+ and Bullpen+ explainers deep-linked to
  the glossary; projections player cards gained a per-year P90 "upside"
  element (per-year percentiles only, never a summed total; the flagged
  warTotalP90 surfaces are byte-unchanged); prospect grade language on the
  projections board and #cmp compare is eFV-primary (round to nearest) with
  consensus-FV-ceiling fallback. Five smoke-test files extended/added.
- Experiments X-D1 and X-D2 evaluated against their pre-registered gates.
  X-D1 (reliever leverage consistency) PASSED cleanly: pooled Y to Y+1 gmLI
  Spearman 0.4683 (CI floor 0.412 vs the 0.30 bar), split-half 0.5294;
  ships as a deployment-context column (wiring follows this pass). X-D2
  (age-relative outperformance, AgeRel+) met the numeric bar on its face
  (pooled r 0.1237, n=369) but is NOT a clear pass (post-hoc stability
  instruments, out-predicted by the plain level-relative comparator, upper-
  level selection confound): NOT wired, queued for owner decision. Both
  artifacts registered (registry now 44 rows).
- Audit deliverables (lane G): MODEL_REGISTRY.md, SITE_MAP.md and
  DATA_SOURCES.md are generated by tools/gen_audit_docs.py and drift-guarded
  by test_generated_docs_in_sync.py; CHANGELOG.md, REVIEW_QUEUE.md and
  BETA_READINESS.md are curated. REVIEW_QUEUE.md carries specs for every
  deferred item, including the F-01 summed-quantile WAR bands.

## 2026-07-01

- d60c4d3: wave-1 experiments. The surplus $/WAR stress test shipped
  (ordering level-invariant: zero top-50 churn at 20 percent shifts, FV45+
  rank rho at or above 0.9999); SC+ per-component isolation shipped (barrel
  rate carries the hitter signal, whiff rate the pitcher signal; composite
  stays per the pre-set rule); the eFV per-bucket isotonic candidate was
  REJECTED at its pre-registered gate (calibration improved but rank
  Spearman fell 0.0165 vs a 0.002 tolerance from PAVA tie-flattening) and
  lives on as a loss ledger with a deprecated registry row.
- f894429: glossary version stamp single-sourced (payload 2026-07-01); the
  copy-audit backlog cleared (22 of 24 open verdicts were already fixed in
  the live payload, 3 real fixes applied); PWR+ formally a legacy alias of
  POW+; copy gates (copy_lint + strip_emdashes) suite-enforced via
  test_copy_gates.py.
- 8570cf7: stabilization constants centralized in rate_stabilization.py
  (K_AB, K_IP, NEED_ERA_SHRINK_IP, BF_PER_9, SLOPE_SHRINK_K) plus the
  REPLACEMENT_WINS=47.7 team-roll-up baseline (was two literals); values
  byte-identical, output-neutrality proven by pipeline_artifact_diff;
  docs/aging-curves.md documents the intentional three-way aging fork.
- 9fe4852: fixed the pre-existing red test
  `test_fv50_active_prospect_gets_trade_rarity_floor`. The tune in 2a00e00
  plus the surplus realignment moved the fixture 0.2 above the rarity floor,
  so the final-value clamp tag legitimately stopped firing while the policy
  invariant (trade_value_mm at or above the active rarity floor) held
  throughout. The test now asserts the rarity-floor invariant instead of the
  clamp tag, and the floor is exposed in the in-memory result only
  (board_slim drops it from the written payload; data/trade_values.json is
  byte-unchanged). Suite fully green after the fix.

<!-- APPEND PACKAGE ENTRIES BELOW THIS LINE (newest first within each day;
     add a new "## YYYY-MM-DD" heading when the day changes) -->

## 2026-07-03 (follow-up Wave B2: starter metrics)

- New Starter Leaderboards section on /mlbstats/, the starter counterpart to the
  Bullpen Leaderboards. Three gated experiments (pre-registered; harness
  tools/sem_plus_lab.py, seed 20260703):
  - SEM+ (Starter Evaluation Metric, X-S1) ships VALIDATED. A starter-pool-
    anchored, sample-shrunk FIP (100 = average qualified starter), pure run-
    prevention skill. Forward-chained out of sample over 2018-2025 (excluding
    2020, 702 season-to-season pairs), SEM+ predicts a starter's next-year
    runs-allowed rate at a Spearman correlation of 0.39, beating ERA (0.26; gap
    confidence floor above zero) and edging its raw-FIP parent (0.36). It is a
    stronger forward predictor than the reliever REM+ (0.24) because starters
    carry larger, steadier single-season samples. Durability (innings, games
    started, average start length) is shown as context, never mixed into the
    skill number.
  - A "more than FIP" test (X-S3, a ground-ball-adjusted home-run expectation)
    was REJECTED: it scored 0.3905 versus plain FIP 0.3923 out of sample, so the
    plain core ships. Starter samples are large enough that the observed home-run
    rate is already a strong estimate, the same finding as the reliever SwStr
    test. Loss ledger inside data/sem_plus_eval.json.
  - 3-year SEM+ (X-S2) ships PROVISIONAL as a companion column: it forward-
    predicts a touch better than a single season (0.41 versus 0.39 on the same
    starters, gap not statistically separable) and is steadier by construction.
  - Team Rotation+ rolls SEM+ up by starter innings; yearly history tabs read
    per-season boards from data/starter_history.json (2021-2025).
- New modules sem_plus.py (reuses the validated REM+ FIP machinery) and
  starter_export.py; run_monthly steps 6b4e (starter lab) and 6b4f (starter
  export + history); registry now 57 rows; glossary adds sem_plus and
  sem_plus_3yr. Golden artifacts byte-unchanged.

## 2026-07-02 (follow-up Wave B1: reliever metrics)

- Bullpen Leaderboards gains a richer, honest reliever picture. Three gated
  experiments (pre-registered before any number was computed; harness
  tools/rem_plus_lab.py, seed 20260702):
  - REM+ skill overhaul (X-R1) was REJECTED at its gate. The owner's central
    "make REM+ more than a FIP proxy" ask was tested directly: shrink the K
    component toward a SwStr-implied expected-K prior instead of the pool mean.
    Candidate forward rho 0.2277 vs the incumbent FIP core 0.2246, bootstrap gap
    lo95 -0.0066, a wash within noise. The incumbent already regresses K% by
    sample; at reliever volumes observed K% is a strong enough estimate that a
    SwStr prior adds no forward signal. The FIP-based REM+ skill core stays
    unchanged and REM+ published numbers are unchanged. Loss ledger
    data/rem_plus_swstr_eval.json.
  - 3-year REM+ (X-R2) ships PROVISIONAL as a companion display column. An
    IP-weighted trailing-3-season REM+ forward-predicts next-year run prevention
    at least as well as one season (0.2366 vs 0.2316 on the same 668 arms; the
    gap is not distinguishable from zero), and it is more stable by construction,
    since single reliever seasons are noisy. Its value is stability, not sharper
    prediction. Joined into the leaderboard by MLBAM like gmLI 3yr.
  - RIV+ (Reliever Impact Value, X-R3) ships as a new realized-VALUE column, the
    two-number design the owner asked for: REM+ stays pure skill, RIV+ carries
    the leverage-weighted impact. RIV+ is a 100-anchored index of the wins a
    reliever actually added (WPA-primary, with a shutdowns-minus-meltdowns
    overlay). Both pre-registered checks passed: RIV+ is materially less
    repeatable year to year than REM+ (0.209 vs 0.352, confirming why leverage
    stays out of the skill scale) and it tracks what teams pay relief free agents
    better than REM+ (0.576 vs 0.508). Computed live in rem_plus.score_riv_plus;
    accountability artifact data/riv_plus_eval.json.
- Yearly reliever history: data/bullpen_history.json carries per-season
  qualified-reliever boards (2021-2025) for the /mlbstats/ history tabs, so users
  can read past seasons and see how REM+ (skill) and RIV+ (impact) played
  forward. Monthly refresh wired as run_monthly steps 6b4c (reliever lab) and
  6b4d (history). Registry now 55 rows; glossary adds riv_plus and rem_plus_3yr.

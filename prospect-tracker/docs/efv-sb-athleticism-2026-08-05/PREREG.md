# Pre-registration: eFV stolen-base driver (B4) + athleticism blend (B5)

Date: 2026-08-05. Lane: B4+B5 of docs/master-plan-2026-08-04d-omnibus.md.
Written BEFORE any model fit was run. Every variant, gate clause, control, and
declared deviation below was fixed before the first fold was scored.

## 0. Standing refutations this pre-registration is scoped by

Three defense-into-eFV refutations stand in the registry and are NOT re-litigated here:

1. `xfv_defense_tools` (2026-07-15, data/xfv_defense_tools_eval.json): isolated
   tool_field, the D-Tool proxy (0.7*field + 0.3*speed), and the field x pos_prem
   interaction ALL regress every gate metric (best pooled 0.3768 vs base 0.3782;
   t45 collapses 0.0876 -> 0.0414 on the pure-field arm).
2. `xfv_pitcher` registry row, rejected item (d) (2026-06-24): ALL Will's-model
   features as WAR inputs (Defense+ field/position prior + p_hold + Decision+
   MLB-equivalent K%/BB%, faithful proxies) are flat-to-negative on every gate on
   both sides, with the decisive control: raw bb_rel + level_rank reproduces the
   Decision+ proxy delta to the digit, so the translation added nothing eFV lacked.
3. `prospect_def_value` (2026-06-29, data/prospect_def_value_eval.json): the
   def_value swap into the lean eFV model regresses every gate (pooled rho
   0.3701 -> 0.3661, within-tier 0.2055 -> 0.1847, fringe 0.0916 -> 0.0715) even
   though def_value beats FG fFld as a defensive predictor (0.68 vs 0.28).
   Recorded cause, quoted: the binding constraint is the TARGET, which is
   offense-dominated first-6yr WAR, not defense measurement quality
   (prospect_def_value.py:37-42).

Adjacent physical-tools null, also standing: `xfv_physical_position` (2026-07-15,
data/xfv_physical_eval.json): BMI/height/weight arms regress decisively;
frame/athl grades are UNTRAINABLE outright (0/843 debuted coverage in
tools_consensus). BMI-for-arms is banned.

### Why B4 is a genuinely new lane

No SB-adjacent ban exists anywhere in the ledgers. Verified 2026-08-04 by the
master plan (section B4: "Verified: no SB-adjacent ban anywhere in the ledgers")
and RE-verified 2026-08-05 by grep over data/model_registry.json,
docs/efv-2026-07-15/GATES.md, docs/efv-2026-07-30/*.md, and
docs/EFV_GATE_STANDARD.md: "stolen"/"sb_rate"/"sb600" appear only in the
DESCRIPTIVE tool-grade tables lane (`xfv_tools`, which wires nothing into eFV)
and in SPRINT_RANGE_GATE.md as a published anchor. MiLB stolen-base volume has
never been tested as an eFV feature. It is a production-side (outcome-basis)
signal, not a grade re-expression, and its face validity is measured: SB/600PA
by speed grade corr 0.57 (docs/efv-2026-07-30/TOOL_GRADE_TABLES.md section 2.6,
n=301, Spearman 0.577).

### Why B5 is scoped to debuted-coverage tools only

frame/athl are FG-only (-2..+2 -> 30-70, consensus.py:823-847) with 0/843
debuted-cohort coverage (data/xfv_physical_eval.json): UNTRAINABLE, excluded.
BMI-for-arms: banned outright, excluded. The blend is therefore built from the
tools that actually cover the debuted pool, measured on the current hitter
matrix (845 runner-eligible debuted rows, 2026-08-05):
tool_speed 747/845, tool_field 747/845, tool_throw 717/845.
NOTE: the xfv_defense_tools ledger line "tool_throw untestable
(2017-2020-only coverage)" is STALE relative to the current matrix; coverage is
now broad across debut years 2014-2024 (85%). Recorded here so the ledger
discrepancy is on the record before the run.

## 1. Protocol (the shipped one; deviations declared in section 5)

Harness: tools/efv_lab_runner.py semantics, which reuse the SHIPPED model
machinery (efv_model._vec / _feature_spec / _fit_ols_fv / blend_lambda +
prospect_path._fit_ridge / _predict / _spearman) on the committed matrix
data/xfv_hitter_matrix.json:

- Pool: kind == "debuted" rows with target_censored and consensus_fv_raw present
  (n = 845 hitters).
- Forward chaining: for each fold year in SCORED_YEARS = (2020, 2021, 2022,
  2023): train = decision_year < fold year, test = decision_year == fold year;
  fold skipped if test < 12 or train < 50 rows.
- Model: served ridge feature set _FEATURES_HIT plus the variant's ADDED
  column(s), ridge fit with KM weights, blended with the within-fold consensus
  OLS at the shipped lambda blend_lambda("hit") = 0.70 (pinned).
- Target: target_censored (the shipped headline target).

BOTH experiments are HITTER-side only: tool_speed/field/throw are hitter tools
(_HIT_TOOLS) and pitchers carry no such grades; SB is a hitting stat. The pit
MDE floor 0.016 quoted by the plan is therefore inapplicable; the binding floor
is the hitter 0.017.

## 2. The B4 feature, exact spec

MiLB SB is a season COUNT (milb_history.py lean hitting rows, `sb` key,
milb_history.py:173). caughtStealing is NOT captured at MiLB, so success rate
is not computable from the cache. CS ingest was evaluated and DECLINED as not
cheap/safe: the lean-row schema migration pattern would mark every hitting
cache stale and refetch ~10 seasons x 7 sports of paginated StatsAPI calls
against a cache shared with other in-flight lanes; a bare one-line ingest
without the migration leaves `cs` None on 100% of cached rows (a dead field).
The honest v1 spec is therefore SB volume per 600 PA, level-relative:

    sb_rate_rel = w * ( (sb / pa * 600) - sb600_norm(season, level) )

- Final pre-decision season, primary level, exactly as-of like every other
  level-relative rate: computed inside efv_dataset._season_rates /
  _milb_features, which enforce strictly-pre-decision seasons (the 2026-07-24
  bust-season repair included).
- Reliability shrink w = pa / (pa + 50), the same _K_REL_PA shrink as
  k_rel/obp_rel/ops_rel.
- sb600_norm = contemporaneous league MEDIAN SB per 600 PA for (season, level),
  qualifier pa >= 100 and n >= 30 (the league_norms convention), falling back to
  the prior season, then to a static per-level prior (empirical 2015-2024 pooled
  medians, computed 2026-08-05 from the milb_history cache):
  DSL 20.4, CPX 15.6, A 11.4, A+ 10.9, AA 9.4, AAA 7.4, MLB 4.8.
  A missing norm NEVER lets the raw rate masquerade as an edge (the obp_rel
  guard pattern).
- Rows with no milb block: 0.0 (neutral), behind the existing milb_missing /
  rates_missing indicators. 581/845 eligible rows carry a milb block.

## 3. Variants (all ADDITIONS; nothing served is removed or replaced)

The runner protocol is add-only by construction (keys = _feature_spec("hit") +
extra keys), so a tool_speed REPLACEMENT is inexpressible as well as banned
(replacing tool_speed measured -0.014; it is protective). Consequence, recorded
before running: the plan's "sb_rate_rel ALONE" and "sb_rate_rel + tool_speed
(ADD)" coincide under add-only semantics; tool_speed is served and stays in
every variant. One added-column variant covers both names.

z(x) below = (x - pool_mean) / pool_sd using OBSERVED-value pool statistics
over the 845 eligible rows (feature-only statistics, labels untouched);
a missing component contributes z = 0 (neutral), matching the _TOOL_IMPUTE
philosophy. Tool constants (computed 2026-08-05, recorded before the run):
tool_speed mean 47.79 sd 12.23 (n 747); tool_field mean 51.00 sd 6.58 (n 747);
tool_throw mean 53.96 sd 7.12 (n 717). sb_rate_rel constants are computed from
the built feature column over rows with a milb block, and recorded in
RESULTS.md before scoring.

B4 (side hit, target censored):
- B4-1 `b4_sb`      : + sb_rate_rel
- B4-2 `b4_blend50` : + spd_sb_50 = 0.5*z(tool_speed) + 0.5*z(sb_rate_rel)
- B4-3 `b4_blend70` : + spd_sb_70 = 0.7*z(tool_speed) + 0.3*z(sb_rate_rel)

B5 (side hit, target censored):
- B5-1 `b5_athl3`   : + athl3   = mean of {z(tool_speed), z(tool_field), z(tool_throw)}
- B5-2 `b5_sf`      : + athl_sf = mean of {z(tool_speed), z(tool_field)}
- B5-3 `b5_st`      : + athl_st = mean of {z(tool_speed), z(tool_throw)}

Controls: for EVERY variant, a zero-information control = the identical variant
with its added column ROW-PERMUTED across the pool (numpy default_rng seed
20260805) and KEPT in the set (the house control from the age/k_rel drop
gates). Run unconditionally for all six variants.

## 4. Gate (all clauses required to SHIP; ledger entry either way)

Margins are variant minus the same-run baseline (the served feature set run
through the identical extended harness).

1. Pooled OOS Spearman margin >= +0.017 (the hitter MDE95 rank floor). The
   margin-to-floor ratio is reported for every variant.
2. Pooled OOS MAE (mean |blend - target_censored| over the identical pooled
   pairs) strictly improves (variant MAE < baseline MAE).
3. Fold robustness: per-fold Spearman win vs baseline in >= 3 of the 4
   SCORED_YEARS folds.
4. Zero-information control: the permuted control's pooled Spearman margin must
   reproduce LESS than 50% of the candidate's margin; a control at or above 50%
   voids the candidate's clause-1 pass (the hit-age precedent, where the control
   at 93% voided the "gain").
5. If every clause passes: the variant is reported SHIP-ELIGIBLE with exact
   numbers and STOPS THERE. Nothing is wired into the served model this wave;
   serving a new feature is a basis change with its own regen runbook, owned by
   the orchestrator.

Expected outcomes, stated now: B5 field/throw loads are EXPECTED null (the
target is offense-dominated first-6yr WAR; all three standing refutations above
found exactly this); the informative B5 variant is speed+field. B4 has no
prior; the face-validity correlation (0.57) is against the GRADE, and
tool_speed is already served, so the live question is whether realized SB
volume carries incremental signal beyond the priced grade.

Secondary metrics (reported, NOT gate clauses): within-tier weighted Spearman,
t45, per-cohort, per-era, KM-weighted MAE as a sensitivity.

## 5. Declared deviations from the stock runner (with equivalence checks)

The stock tools/efv_lab_runner.py cannot express these variants and cannot
report MAE, so the run uses a driver (run_lab.py in this directory) with three
and only three deviations, each carrying an equivalence check reported in
RESULTS.md:

1. Feature availability. The runner's per-row feats dict is efv_model._vec
   output, a FIXED named-key mapping: it emits neither sb_rate_rel (new matrix
   key) nor tool_throw. The driver augments the runner's own cached rows
   (efv_lab_runner.data_for("hit")) with the new columns at load time; all
   fitting/scoring machinery is imported from the shipped modules unchanged.
   CHECK: the driver's baseline must reproduce efv_lab_runner.run_variant's
   baseline pooled Spearman exactly (same rounding, 4 decimals).
2. sb_rate_rel provenance. Values are computed in-memory per row by calling the
   PRODUCTION code path (efv_dataset._milb_features with the row's own
   mlbam_id/decision_year/cutoff) after the production-block edit, NOT by
   rebuilding data/xfv_hitter_matrix.json. The committed matrix artifact stays
   byte-identical this wave (other lanes share the tree; the golden-fingerprint
   tripwires stay quiet; a rebuild is the orchestrator's call). All relevant
   seasons are >= 2014 past-season caches (final; every one carries `sb`), so
   the recompute is deterministic and offline.
   CHECK: on every row with a stored milb block, the recomputed k_rel, obp_rel
   and level_rank must match the stored values; mismatches are counted and
   reported, and a mismatch rate above 1% blocks the run.
3. MAE. run_variant reports rank metrics only. The driver's run_variant_ext is
   a line-copy of run_variant extended to collect pooled and per-fold MAE from
   the identical (blend, target) pairs. No fitting logic is changed.

Composite z constants are full-pool feature statistics (section 3): they see
feature values from future folds (never labels). The ridge re-standardizes
every column on TRAIN per fold (prospect_path._fit_ridge), so the constants
only set the fixed component weighting inside a composite; declared anyway.

## 6. What ships regardless of verdict

The efv_dataset/level_norms sb plumbing (norms + production-block key) is KEPT
even on an all-null verdict: it is inert until efv_model's served feature list
(_FEATURES_HIT via _feature_spec, consumed by fit_production_stack) names the
key, which this wave does not do. RESULTS.md must verify and state that
inertness by reading the efv_model feature-selection path. Registry ledger rows
are recorded in data/model_registry.json either way, in the house loss-ledger
prose style (dated, quantified, "do not re-attempt blind" only where earned).

Wall-clock per run is recorded in RESULTS.md.

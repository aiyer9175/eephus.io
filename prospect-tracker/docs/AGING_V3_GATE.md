# Aging v3 gate (pre-registered 2026-10-08)

Covers aging v3, the one aging service of Part 9 (PLAN section 9.3 'Aging v3 (the one aging
service)'; design in the Part 9 bundle `_finalpass_2026-09-24/part9/LANE_B.md` sections 2
'Design' and 3 'Gates and frames'), ordered by the owner on 2026-10-01 (message 1, the aging
sentences, verbatim):

> "can we model prospect aging curves better by noting that aging curves aren't just a straight
> decline, and players should be getting better until they hit their prime? Can we positionally
> bucket aging curves across the site, as well as improve our aging curve model by identifying
> archetypes of players that age differently, as well as incorporating health modelling and
> archetype modelling to project which players will age better or worse, and adjust their aging
> curve accordingly?"

It registers three families, each with exactly one look:

- **The ladder** (registry row `aging_v3`): four arms on the veteran champion engine, adjudicated
  in the fixed order T (playing time), S (the rate estimator), P (positional buckets), R (skill
  archetypes out of window).
- **PS, the prospect shape gate** (registry row `aging_v3_prospect_shape`): the v3 `shape()`
  against the incumbent prospect tent, read in the same session as the ladder.
- **H, the health family** (registry row `aging_v3_health`): a playing-time hazard, read at its
  own look.

Producers, none of which exist at this commit: `aging_v3.py`, `aging_v3_sidecar.py`,
`tools/aging_v3_lab.py`. Artifacts, none of which exist: `data/aging_v3_mde.json`,
`data/aging_v3_eval.json`, `data/aging_v3_curves.json`. Pinned by `test_aging_v3.py` and
`test_aging_v3_gate.py`, neither of which exists. The three registry rows are written
"registered, not read" by AG_5_AGING_SERVICE_BUILD_DARK, not by this commit.

Written and committed BEFORE any candidate, curve, bucket, archetype or health feature exists,
in the form of `docs/PROJ_PATH_SHAPE_GATE.md`. Where this document and a later measurement
disagree, the measurement is what this gate uses, and the disagreement is recorded rather than
edited away.

---

## G-0. Honesty clause, first

**No candidate was computed to write this document.** Nothing was fitted, no arm was run, no
curve, bucket, archetype or health feature was built, and no candidate was compared against the
shipped engine. Every number below is one of: a constant read from code or config at HEAD; a
value quoted from LANE_B.md section 1, whose numbers are themselves values in committed or cached
artifacts or descriptive counts over the served payloads `data/mlb_projections.json` and
`data/trade_values.json` (2026-10-01); or a threshold, grid or frame fixed here.

The writer of this registration opened no data artifact for its numbers. It read the schema of
`data/fwar_vintage.json` (its `fields` lists and its season keys, 2000 to 2026) to name the run
parts ARM R reads; it read no value in it.

**Looking early disqualifies.** A candidate measured before its look is disqualified, whatever it
measured. Each family below has exactly one look, on the day section 13 defines. A GATE, TIER-2 or
CONFIRM number computed on a candidate before that day voids the family for this battery, and the
family may return only as a new registration that discloses the early read.

### G-0.1 The priors read during design, recorded so a run cannot quietly beat them

All pre-epoch, all on the incumbent or on the served payload: priors, never comparators
(LANE_B.md 3.1).

- `data/proj_calibration_eval.json` (all cells, champion engine, bWAR, pooled bases 2014-2021),
  including `resolvable_biases_ranked`: `age:<=24:hit` -0.1982, `age:25-27:hit` -0.1573,
  `age:31-33:hit` +0.0970, `age:34+:hit` +0.1273, `age:<=24:pit` +0.2217, `age:25-27:pit` +0.0960,
  `role:C` +0.2453.
- `data/war_cohort_eval.json` (`by_age_band`, `by_role`; champion and proj_lgbm, bWAR).
- `data/proj_horizon_eval.json`.
- `data/fa_pt_risk_eval.json` (W1 PT-RISK, 2026-07-23, both arms FAIL).
- The cached incumbent fits `.cache/fa_fits_*` (ewar_v2) and `data/fa_aging_curves.json` (bWAR,
  2026-06-10).
- The served `data/mlb_projections.json` and `data/trade_values.json` (2026-10-01).

Those reads touch label seasons this gate scores, and that is recorded rather than denied:
`proj_calibration_eval.json` pools bases 2014-2021, so its cells include label seasons in TIER-2
and in the H GATE frame (2015-2018). Each read is of the CHAMPION, pooled, on bWAR, never of a v3
candidate; the champion is this gate's comparator, so an incumbent read burns nothing here.

### G-0.2 Disclosures, each made before any number exists

1. **The path-shape battery.** Label seasons 2008-2014 are also the DEV and GATE frames of
   `docs/PROJ_PATH_SHAPE_GATE.md`, whose candidates are ML challengers (a different candidate
   family). This document commits on 2026-10-08, before that battery's ARM A look (2026-10-23).
   At this commit `data/proj_shape_blast.json`, `data/proj_shape_mde.json` and
   `data/proj_shape_gate.json` do not exist and section 19 of that document records no look, so
   no path-shape result shaped any line here. An incumbent number that battery later publishes
   burns nothing here.
2. **The prospect path.** Label seasons 2019-2023 were read on the incumbent prospect path by
   `data/prospect_path_eval.json` (debut cohorts 2019-2021, a level model). That is an incumbent
   read; PS (section 9) reads debut cohorts 2014-2018 only.
3. **Cross-family overlap.** The H frames overlap the ladder's: H fits on label seasons 2011-2014
   (the ladder's GATE and one TIER-2 season) and is adjudicated on 2015-2018 (ladder TIER-2).
   The ladder's look reads those seasons on ladder candidates only; no H candidate (the hazard of
   section 10) is scored before the H look. PS windows reach label seasons 2014-2024, also ladder
   TIER-2 seasons, on a different candidate (a shape, not a level).
4. **The reserved debut cohorts (R-VM).** LANE_B.md 3.4 does not state it, so it is registered
   here: every row of a player whose first MLB corpus season with exposure is 2025 or later
   (`efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR`) is dropped from every frame of every family before
   scoring, and the lab raises if one reaches a scorer. CONFIRM's n >= 1,000 condition is counted
   after that drop.
5. **The label.** Every label in this gate is FanGraphs' WAR from the frozen vintage
   `fwar@2026-10-02-0341299c20ec` (`data/fwar_vintage.json`, seasons 2000 to 2026, frozen at the
   fWAR label epoch, step Z recorded 2026-10-03), read through the corpus built on
   `war_provider fwar`; never the live StatsAPI sabermetrics cache (`.cache/statsapi_saber_*`) and
   never a house eWAR v3 part. The displayed WAR stays eWAR (v2 until EBR_3); a projected line
   names its frame ('FanGraphs frame').

### G-0.3 Owner answers read before writing, and the completions this registration makes

From `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (standing instruction), the
projections, aging, tools and team program (Part 9)', each the recommended option accepted under
the owner's standing instruction of 2026-10-01; no later override is recorded:

| question | answer |
|---|---|
| AG-Q1 bucket set | Seven hitter buckets C, SS, 2B/3B, CF, LF/RF, 1B, DH, plus SP and RP |
| AG-Q2 archetype families | Two per side: hitters OLD_SKILLS vs YOUNG_SKILLS, pitchers POWER vs COMMAND (family (a)) |
| AG-Q3 health arm | Register the health family with its own look (the answer named 2027-01-12; see section 13) |
| AG-Q5 interim fix | 'Fix both now': the comparator carries the PT cap, computed call-scoped (section 4) |

No owner question was defaulted. Owner decision EPOCH-NOW (2026-10-02) governs how look days are
written (section 13). The completions below fill gaps LANE_B.md left; each is fixed now, before
any number, and none loosens a LANE_B threshold:

- C1. Look days are written as conditions (EPOCH-NOW), section 13.
- C2. R-VM rows are dropped from every frame (G-0.2 item 4).
- C3. TIER-2 is read at full depth: every base whose cell lands on a TIER-2 label season
  (section 6).
- C4. Each arm's DEV grid is selected with every earlier arm on, once, and never re-selected
  after GATE opens (section 8).
- C5. The tie rules name the incumbent direction for every knob (section 8).
- C6. A veto withdraws every later arm adjudicated against a composition that contained the
  vetoed arm (section 7).
- C7. Archetype z-scores are taken against the season's players at or above the engine's pair
  floor (section 5, ARM R).
- C8. H cells need a feature window inside the transactions cache (bases 2011 and later,
  section 10).
- C9. ARM R's run parts come from the frozen vintage reader (PLAN 9.3 unifier addition), never
  the live saber cache.
- C10. The protocol hash covers sections G-0 to 17 (section 17).

---

## 1. What is being fixed, from the findings at HEAD (LANE_B.md section 1)

The owner's premise ("better until they hit their prime") is met on the prospect path and on the
veteran engine for players 23 and under, and is not met in three places: the /projections/ ML
headline path for young veterans (owned by the path-shape battery and, later, AG_14 to AG_16);
the veteran champion curve, whose hitter WAR rate peaks near 24.5 because the survivorship
correction (lambda 1.0) subtracts 0.020 to 0.037 WAR/600 at every age from 23 to 27; and the
Trade Machine fallback factor, whose pre-peak branch is inverted. A served 22-year-old 650-PA
regular is walked to 798 PA by an uncapped pool-average PT delta. Positional bucketing exists
only as catcher vs non-catcher.

The served age treatments at HEAD (LANE_B.md 1.2, PLAN 9.3 round 4):

| # | treatment | code anchor (function) | disposition under aging v3 |
|---|---|---|---|
| A1 | prospect tent | `value_framework._aging_multiplier()`, `_trajectory_shape()`, `prospect_prime_path()`, `prospect_peak_war()` | consumer: `shape()` and `level()` (flags `proj_display`, `prospect_surplus`) |
| A2 | veteran champion curves | `fa_projection.fit_aging_curves()`, `curve_delta()`, walked by `fa_market._decay_path()` | the estimand's engine; consumer through `fitted_models(..., aging=)` |
| A3 | ML learned age response | `proj_ml.build_features` (`age`, `age_sq`, `age_x_war`, champion path stacked) | not a consumer: pinned to `aging="v2"` until AG_16 |
| A4 | contract tail seam | `fa_market.chain_aging_tail()` | consumer (flag `contract_tail`) |
| A5 | trade fallback factor | `bayes_trade_value._aging_factor()` | consumer: `factor()` (flag `trade_fallback`) |
| A6 | glove decline | `positional_fit.fit_aging()`, served on /pal/ | EXCLUDED: a fielding z-score decline outside the WAR aging curve, served on /pal/ only |
| A7 | trade audit decline | `mlb_trade_lookup._compute_surplus()` (-0.4 WAR a year past 29) | EXCLUDED: a historical trade audit, not a projection |
| A8 | catcher late-peak bonus | `bayes_trade_value` `catcher_dev.late_peak_bonus` (0.08 at age 24 and under) | handled inside AG_12 (b): zeroed when the C-bucket `factor()` applies under `trade_fallback`, with a test |

---

## 2. The service (LANE_B.md 2.1, 2.5, 2.8)

New module `aging_v3.py`: one fitted object, many consumers.

```
fit(corpus, max_season, cfg, *, sidecar) -> AgingModel
AgingModel.rate_delta(side, comp, age, bucket=None, archetype=None) -> float
AgingModel.pt_next(side, role, pt_prev, age, bucket=None, health_z=None) -> float
AgingModel.level(side, age, bucket=None, archetype=None) -> float
AgingModel.shape(side, debut_age, n_years, bucket=None, reliever=False) -> list[float]
AgingModel.factor(age_now, yr_offset, side, bucket=None) -> float
AgingModel.component_curve(side, comp, bucket=None) -> dict
AgingModel.meta -> {version, provider, corpus_sig, max_season, buckets, archetypes, k values, lambda, caps}
```

- `level()`: `m(a) = (R_ref + C(a)) / max_a (R_ref + C(a))`, `C(a)` the cumulative sum of the
  cell's smoothed deltas from the youngest supported age, `R_ref` the exposure-weighted median WAR
  rate of regular-tier players of that side and bucket in the fit window, floored at 0.25.
- `shape()`: `level()` times the regular-tier PT curve (relative to its maximum) at each age of
  the window, renormalized to mean 1.0, exactly like `_trajectory_shape`, so the FV-anchored
  window mean is unchanged and only the timing moves. Prospects get a bucket only (board position;
  `C/1B` reads its first token; SIRP and RP read `RP`), never an archetype and never a health
  term.
- `factor()`: `level(age + k) / level(age)`, the A5 replacement.
- `component_curve()`: the v2 component curves (K%, BB%, ISO, BABIP, HR) returned unchanged under
  every arm, read-only for lanes PJ and TL. Two NEW outputs are registered here (unifier
  amendment U6): `component_curve(side, 'bsr')` and `component_curve(side, 'fld')`, fitted with the
  incumbent delta-method estimator on the frozen-vintage run parts for lane PJ's heads. They are
  not an arm of this battery, this gate never adjudicates them (PJ-C does), and they change none
  of the existing curves.
- Call-scoped selection, never a module global (the `use_def` precedent in `fitted_models()`):
  `fa_projection.fitted_models(..., aging="v2"|"v3")`, `fa_market.contract_war_path(..., aging=)`
  and `_decay_path`, `value_framework._trajectory_shape`, `prospect_prime_path` and
  `prospect_peak_war` (`aging=`), `bayes_trade_value._aging_factor(..., aging=)`. Default `"v2"`
  everywhere. `proj_ml.build_features` and `proj_eval` pass `aging="v2"` explicitly (train/serve
  parity; a test pins it).
- Cache (2.8): the incumbent `fa_fits_{max_season}_{first}_{last}_{sig}[_def].pkl` name is
  unchanged and never deleted while the path-shape battery holds its pins (until its ARM B look
  is recorded); a v3 fit writes
  `aging_v3_fits_{max_season}_{first}_{last}_{sig}_{AGING_V3_VERSION}_{cfg8}.pkl`,
  `AGING_V3_VERSION` carrying a hash of the fit function's source, `cfg8` a hash of the
  `aging_v3` config block and the bucket and archetype definitions. The sidecar is
  `.cache/aging_v3_sidecar_{first}_{last}_{sig}.pkl`, keyed by (mlbam, season); its run parts come
  from the frozen vintage reader (`fwar_vintage.load()`). `.cache/fa_corpus.pkl` is never
  rewritten. Labs pass `use_cache=False` and never read a path-shape cache.

---

## 3. The estimand (LANE_B.md 3.2)

For a player-side line observable at the end of season B-1, the champion engine's expected WAR
in seasons B to B+4: `fa_market.contract_war_path(use_ml=False)` with point-in-time
`fa_projection.fitted_models(corpus, B-1, use_cache=False, aging=X)`, under aging configuration
X. Cell (B, h), h = 1..5, scores label season L = B + h - 1. It does NOT estimate the ML heads,
the band widths, the two-way workload discount or any prospect level.

---

## 4. The comparator (LANE_B.md 3.3, AG-Q5 'Fix both now')

The v2 champion curves refit point-in-time per base on the same corpus and rows, **with the PT
cap computed call-scoped**, whatever the served flag `projection.pt_cap_enabled` says on the look
day. The cap is the one AG_4_CHAMPION_PT_CAP commit 1 defines: the 99.5th percentile of
single-season exposure (PA for hitters, BF for pitchers) by side and base role (hit C, H; pit SP,
RP) over corpus rows with season <= B-1, computed by the fit and never tuned; exposure is clamped
at the cap in every path step and in the year-1 PT. If AG_4's call-scoped `pt_cap` argument exists
on the look day the lab passes `pt_cap=True`; otherwise the lab applies the same definition
through `aging_v3.py`, and `test_aging_v3_gate.py` pins that the two agree on fixtures. The
comparator is identified in the artifact by its config hash.

---

## 5. The arms (LANE_B.md 2.2)

Each arm is a configuration of the one service; no arm is active by default.

**ARM T, playing time.** Replaces the additive pool-average PT delta with
`pt_next = min(cap[side, role], pt_prev * rho[side, role, tier, age])`, at every PT step the
champion walks (the year-1 step in `project_player` and every `_decay_path` step).
- `rho`: the exposure-weighted mean ratio of next to current exposure over surviving pairs in the
  cell; pair floor 100 PA / 70 BF (`min_exposure_pair`); the v2 survivorship correction form
  applied to log rho; cells need `n_pool >= 12`; the nearest-supported-age rule of `curve_delta`
  is kept.
- tier: `regular` if `pt_prev >= 450` PA (hitters), `>= 500` BF (SP), `>= 200` BF (RP), else
  `part`.
- `cap`: the 99.5th percentile of single-season exposure by side and role in the fit window
  (the section 4 quantity), computed by the fit, never tuned.

**ARM S, the rate estimator.** Two knobs on the existing delta method; nothing else in the
regressed-rate v2 fit changes.
- survivorship lambda in {0.0, 0.5, 1.0} (incumbent 1.0);
- smoother: the incumbent 3-age moving average, or a second-difference penalized fit of the
  per-age deltas weighted by their pair weights, penalty in {1, 4, 16}.
The grid is the 12 combinations, chosen on DEV by section 8.

**ARM P, positional buckets (AG-Q1).** Bucket curves for `war_rate` and `pt` only; component
curves stay per base role.
- Hitter buckets: `C`, `SS`, `2B/3B`, `CF`, `LF/RF` (LF, RF, OF), `1B`, `DH`. Pitcher buckets:
  `SP`, `RP` (the incumbent GS/G >= 0.5 rule).
- Assignment: the primary position of the pair's START season t from the StatsAPI season split
  (`position.abbreviation`); IF, UT, TWP or missing go to the pooled hitter curve; a two-way
  player's hitting side is `DH` and his pitching side `SP` or `RP`.
- Shrinkage: `delta_b(a) = w * delta_b_raw(a) + (1 - w) * delta_parent(a)`,
  `w = n_b(a) / (n_b(a) + k_P)`, `k_P` in {50, 100, 200, 400} chosen on DEV. The parent of every
  hitter bucket, C and DH included, is the POOLED hitter curve `HALL` (all hitters), not `H`; the
  parent of SP and RP is the pooled pitcher curve. C and DH are separate cells shrunk toward the
  same parent, never toward each other. The nearest-age rule is kept.

**ARM R, skill archetypes, out of window (AG-Q2, family (a) only).**
- Window: a pair (t to t+1) takes its archetype from seasons t-3 to t-1 ONLY, never season t,
  pooled over at least 2 seasons with exposure and at least 600 PA (hitters) / 500 BF (pitchers).
  The lab raises if a fit row's window contains its start season.
- Rates are regressed toward the season league mean at the `fa_config.yaml` `regression_k`
  constants (hit k_pct 60, bb_pct 120, iso 160; pit k_pct 70, bb_pct 170) before pooling, then
  expressed as a z-score against that season's MLB players at or above the pair floor (100 PA /
  70 BF) (completion C7).
- Hitters:

  | archetype | rule over the window |
  |---|---|
  | OLD_SKILLS | (ISO z >= +0.75 OR BB% z >= +0.75) AND baserunning runs per 600 PA <= 0 |
  | YOUNG_SKILLS | baserunning runs per 600 PA >= +2.0 OR K% z <= -0.75 OR fielding runs per 600 PA >= +4.0 |
  | NEUTRAL | neither, or both |

- Pitchers (SP and RP):

  | archetype | rule over the window |
  |---|---|
  | POWER | K% z >= +0.75 |
  | COMMAND | BB% z <= -0.75 AND K% z < +0.75 |
  | NEUTRAL | neither |

- Shrinkage toward the BUCKET curve: `w = n / (n + k_R)`, `k_R` in {100, 200, 400, 800} chosen on
  DEV.
- Serve: deltas from year 2 on use the archetype from B-3 to B-1; the year-1 step inside
  `project_player` uses the bucket curve with no archetype.
- Sources (2000-2026): the StatsAPI season splits already cached for the corpus
  (`fa_sources.fetch_statsapi_season_range`: K, BB, ISO, groundOuts, airOuts, gamesStarted,
  inningsPitched, stolenBases, caughtStealing, position) and the frozen vintage's `baseRunning`,
  `fielding` and `batting` run parts (C9). If a window season's run parts are absent from the
  vintage, ARM R STOPs with `BLOCKER: other run parts absent` before any number.
- Not registered: family (b) (the fine sets), Statcast sprint speed, bat speed, velocity and
  xISO (2015+ only, no GATE frame can adjudicate them), body size (current values, a lookahead),
  and any tool-grade archetype for prospects (needs list vintages). Each is a successor that needs
  its own registration.

**ARM H, health (its own family, section 10).** A PT hazard on the next-season exposure only,
never on the rate: `pt_next *= exp(gamma . z)`, clipped to [0.80, 1.05] and recentred within each
season so the league's projected exposure is unchanged by construction.
- Features as of the end of season t, each z-scored WITHIN its season across all MLB players
  with exposure that season: IL days and IL stints in seasons t-2..t; 60-day placements in
  t-2..t (`tools/pt_risk_lab.py`'s reconstruction and stint truncation rules, a-priori choices 3
  and 4, imported, not copied); `tj_prior` (pitchers, surgeries with year <= t from
  `data/tj_surgery.json`); age x IL days.
- `gamma` by ridge (alpha 1.0, z-features, no intercept) on the H DEV frame only.
- Sources: the league transactions cache `.cache/mlb_transactions/` (tx_2008_01 onward, refreshed
  to the current month by the existing fetch code into `.cache/` only, never on a look day) and
  the TJ list.
- Expected effect, stated now: W1-B's best development gain was 2.84 PA of 164 (1.7 percent) and
  did not transfer; a null is the likely outcome and is a finding.

---

## 6. The frames, by LABEL season L = B + h - 1 (LANE_B.md 3.4)

**Corpus.** The fWAR corpus built after the epoch's step M: `war_provider fwar` for every season
2000-2026. Before any frame is built the lab loads `.cache/fa_corpus.pkl` read-only and checks
the provider and the season coverage: another provider STOPs with `BLOCKER: task EPOCH_RUN`; any
season 2000-2010 not on fwar STOPs with `BLOCKER: other pre-2011 fWAR absent`, and no frame moves
without an owner answer.

| frame | label seasons | used for | verdict |
|---|---|---|---|
| DEV | 2008, 2009, 2010 | the grids (lambda, smoother, k_P, k_R) and the power artifact | none |
| GATE | 2011, 2012, 2013 | every ladder adjudication | yes |
| TIER-2 (read) | 2014-2025, 2020 excluded | veto only (a significant reversal) | veto |
| CONFIRM | 2026 | opened once at the look if row-matched n >= 1,000 | veto, reported |

- Bases: DEV and GATE cells come from bases 2004-2013 (h5 of 2004 is L 2008); CONFIRM cells
  from bases 2022-2026, (2022, h5) to (2026, h1); TIER-2 cells from every base 2010-2025 whose
  cell lands on a TIER-2 label season (completion C3, the full-depth read).
- Universe per base: the `proj_eval` universe (a corpus season in B-1..B-3, an age-carrying row,
  a non-None `project_player`), absent season = 0, two-sided rows excluded (path-shape L1), R-VM
  rows dropped (G-0.2 item 4). Label season 2020 is masked from every frame; 2020 stays an input
  season where the engine reads it.
- The DEV, GATE, TIER-2 and CONFIRM label-season sets are pairwise disjoint (pinned by
  `test_aging_v3_gate.py`).
- Era: GATE seasons are 2011-2013 and the serve is 2027; CONFIRM 2026 is the transport check.

---

## 7. The statistics and the pass rule (LANE_B.md 3.5)

- Cells: age at target (age in season L) in bands 24 and under, 25-27, 28-30, 31-33, 34 and over;
  sides hit and pit: 10 cells. `ACAL(X) = sum_c n_c |mean_c(pred_X - act)| / sum_c n_c` over the
  GATE rows.
- **PRIMARY, per arm:** `D = ACAL(predecessor) - ACAL(arm)`. Player-cluster bootstrap (players
  resampled with all their rows), B = 2,000, seed 20261124, one-sided:
  `p = (1 + #{b : D*_b <= 0}) / (B + 1)`. PASS iff p < 0.0125 (Bonferroni over the four ladder
  arms) AND every guard holds.
- **G1, pooled MAE non-inferiority:** the upper 95 percent bound of `MAE(arm) - MAE(pred)` on the
  same resamples is <= +0.003.
- **G2, star slice** (base-year WAR, season B-1 on the side, >= 4): `|bias(arm)|` is not worse
  than `|bias(pred)|` by more than 0.05.
- **G3, h5 tail ratio** (rows with pred >= 3 over rows with act >= 3, h = 5): not lower than the
  predecessor's by more than 0.02.
- **G4, bucket veto:** no position bucket (section 5 ARM P, assigned at season B-1) with n >= 200
  GATE rows is worse in MAE by more than 0.02.
- **Ladder order T, S, P, R.** Each arm's predecessor is the composition of the arms already
  passed (the comparator of section 4 for T). A failed or UNDERPOWERED arm is skipped; the next
  compares against the last passed composition.
- **Veto.** After PS (section 9), each passed arm is read on TIER-2 and then on CONFIRM against
  the same predecessor it was adjudicated against. It is VETOED if D is significantly reversed:
  `#{b : D*_b >= 0} + 1` over `B + 1` below 0.0125 on that frame. A vetoed arm is withdrawn, and
  so is every later arm adjudicated against a composition that contained it (completion C6); no
  arm is re-adjudicated in the same look. A TIER-2 or CONFIRM number is never cited as support
  for a PASS.
- **Reported for every arm, never adjudicated:** ACAL and MAE by age band x bucket and by age band
  x archetype, the peak age and slopes of each cell's `level()`, n and w per cell.

---

## 8. DEV selection and power (LANE_B.md 3.6; artifact `data/aging_v3_mde.json`)

- **Selection rule, one, fixed now:** the DEV ACAL minimum; a value within 0.002 of the minimum
  that is nearer the incumbent wins the tie. Nearer the incumbent means (C5): lambda nearer 1.0;
  the 3-age moving average before a penalized fit, then the larger penalty; the larger k_P; the
  larger k_R.
- **Order (C4):** each arm's grid is selected on DEV with every earlier arm on (S with T; P with
  T and S at their selections; R with T, S and P), once, in AG_6. The selections are fixed for the
  look and are never re-selected after GATE opens, whatever the GATE verdicts.
- **Power:** plant a correction of 0.05 WAR into the 24-and-under and 31-and-over cells of DEV
  rows and measure detection at p < 0.0125 over 200 simulated plants; an arm whose MDE95 of D
  exceeds 0.03 is **UNDERPOWERED** and does not ship (a verdict, not a pass).
- The artifact carries the selections and n and w for every bucket x age and archetype x age cell
  on DEV. **A GATE, TIER-2 or CONFIRM row in it is an automatic VOID that consumes the look.**

---

## 9. PS, the prospect shape gate (LANE_B.md 3.7)

Run in the look session after the ladder verdict and before the TIER-2 veto.

- **Population:** MLB debutants defined from the corpus itself (first corpus season with
  exposure, 2001 or later), debut cohorts d = 2014-2018, with at least 2 seasons of 150 PA / 30 IP
  in seasons d..d+6. Cohorts 2020, 2021, 2025 and 2026 are never read. No FV, grade, list vintage
  or prospect database row is read, and no statistic is computed by consensus-FV cell
  (`docs/PROSPECT_ANCHOR_GATE.md`).
- **Window:** seasons d to min(d+6, 2026), label season 2020 masked from both sides.
- **Predicted shape:** the incumbent `value_framework._trajectory_shape` against the v3 `shape()`
  under whatever composition the ladder accepted at GATE (the v2 curves through `shape()` if
  none), bucket from the debut-season position, both fit point-in-time through d-1, truncated to
  the available seasons and renormalized to mean 1.0.
- **Score per player (level-free):** `L* = sum(y s) / sum(s^2)`,
  `SSE = sum((y - L* s)^2) / T_i`.
- **PRIMARY:** the mean paired `SSE_inc - SSE_v3`; player bootstrap B = 2,000, seed 20261124,
  one-sided lo95 > 0.
- **Guards:** no debut-age band (21 and under, 22-23, 24-25, 26 and over) and no bucket with
  n >= 40 worse by more than 10 percent of its incumbent mean SSE.
- **Strata:** debut age and position only.
- **Composition change:** PS's verdict holds only for the composition it scored. If a TIER-2 or
  CONFIRM veto changes that composition, PS records 'composition withdrawn' and its consumers
  (`proj_display` prospect part, `prospect_surplus`) stay off until a new registration.

---

## 10. H, the health family (LANE_B.md 3.8; its own look)

- **Frames by label season:** DEV 2011-2014 (the ridge fit), GATE 2015-2018, CONFIRM 2026 (n >=
  1,000 after the R-VM drop), forward 2027 at the ML forward read (reported, never adjudicated
  here).
- **Coverage (C8):** a cell enters only if its feature window t-2..t (t = B-1) lies inside the
  transactions cache, so bases 2011 and later: DEV label 2011 at h1, 2012 at h1-h2, 2013 and 2014
  at h1-h3; GATE 2015-2018 at h1-h3.
- **PRIMARY:** paired exposure MAE over h1-h3 (realized PA, or IP x 4.3 for pitchers, against the
  projected exposure; absent = 0), H applied on top of the ladder's accepted composition against
  that composition alone; player-cluster bootstrap B = 2,000, seed 20261124, lo95 of the MAE
  reduction > 0.
- **Guards:** the h1-h3 WAR MAE upper bound <= +0.003; per-season projected league exposure drift
  < 1 percent; CONFIRM not significantly reversed (the section 7 rule).
- One family, alpha 0.05. A pass adjusts playing time on the surfaces already on aging v3
  (AG-Q3); the `health` flag stays false until the H record exists.

---

## 11. Dollar guards before the money flips (LANE_B.md 3.9; regression guards, not adjudications)

- **FA (AG_10):** `fa_backtest` Gate 2 run once with `aging="v3"` on the champion against the
  comparator, identical rows: the upper 95 percent bound of the guarantee MAE change <= +1
  percent of the comparator's. Gate 2's own artifact is not rewritten (`persist=False`).
- **Prospect surplus (AG_11):** PS PASS plus a blast artifact over the served payload (max and
  median absolute surplus move, Spearman of the Trade Machine prospect order).
- **Tails, trade fallback, fantasy (AG_12):** blast artifacts only (no realized statistic).

---

## 12. Consumers, flags, and the served numbers that move (LANE_B.md 2.7)

All flags live in `fa_config.yaml` under `aging_v3: {consumers: {...}, health: false}`, default
false; a false flag keeps every served byte of its consumer identical (a golden test per
consumer). A consumer outside lane AG calls the service with `aging="v2"` until this document
records a pass. Which surfaces may move after a pass is owner answer AG-Q4 ('Staged, each after
its guard'); the ML path is AG-Q7 ('Shadow, read after 2027').

| flag | consumer and code door | served numbers that move | task |
|---|---|---|---|
| `proj_display` | `proj_export` vets `warChamp`, `warY1Champ` on the player Projection tab and compare; prospects `warPTH*`, `warPeak` | champion line, prospect prime display; no $ | AG_8 |
| `team_outlook` | `proj_export._team_outlook` champion sums | Team Outlook wins and lockedPct; Franchise OUTLOOK leg; F-SCORE outlook leg; Ledger Cost+ and $ per projected win; /betting/ Futures win totals | AG_9 |
| `fa_pricing` | `fa_market.contract_war_path(use_ml=False)` in fa_export | /fa/ guarantees, AAV, P10/P90, Fit inputs that read paths | AG_10 |
| `prospect_surplus` | `value_framework._trajectory_shape` on the surplus path | prospect surplus $ (xFV `surplus_mm`, Sur+/OrgSur+, Trade Machine prospect rows, Ledger prospects leg), `war` path timing | AG_11 |
| `contract_tail` | `fa_market.chain_aging_tail` champion ratios | `warTail`, `surTotal` past 2031, Trade Machine, Ledger | AG_12 |
| `trade_fallback` | `bayes_trade_value._aging_factor` (and A8, zeroed under the C bucket) | the `bayes_unrepointed` rows of the trade board | AG_3 (defect fix on the incumbent tent), then AG_12 |
| `fantasy` | `fantasy_rank` curve reads | dynasty values | AG_12 |
| (none) | `proj_ml.build_features` | /projections/ ML `war` h1-h5, surNpv h1-h5, arbitration forward WAR | only via AG_14 to AG_16 (the 2027 forward read) |
| (none, pinned) | component curves (K%, BB%, ISO, BABIP, HR) | betting `woba[0]`, `rates_by_year` | never |
| (excluded) | A6 `positional_fit.fit_aging()` | /pal/ glove decline | not a consumer (section 1) |
| (excluded) | A7 `mlb_trade_lookup._compute_surplus()` | the historical trade audit | not a consumer (section 1) |

---

## 13. The clock (LANE_B.md 3.10, written under owner decision EPOCH-NOW)

Owner decision EPOCH-NOW (2026-10-02) has a look registered as the earliest day on which its
build and its frame are complete, never a fixed later calendar date. The 2026 season is final
(last game 2026-09-27) and the frozen vintage holds 2000 to 2026, so every frame in sections 6,
9 and 10 is complete at this commit.

| what | day |
|---|---|
| this registration | committed alone, 2026-10-08, before the path-shape ARM A look |
| AG_5 build (fixtures only) | after this commit and the step Z entry |
| AG_6 DEV selection, power artifact, fixture dry run of the look | after AG_5; DEV only |
| **THE LOOK, once** (ladder on GATE, then PS, then the TIER-2 veto, then CONFIRM) | **the first day after AG_6_AGING_V3_DEV_AND_POWER lands (`data/aging_v3_mde.json` and the fixture dry run committed) on which the frames of sections 6 and 9 are complete and no other registered look is recorded that day** |
| **THE HEALTH LOOK, once** | **the first day after the ladder's record is written in section 19 on which the frames of section 10 are complete and no other registered look is recorded that day** |

- A day is never a look day of this gate if it is a look day another gate registers or defines
  by rule from recorded inputs (docs/*GATE*.md and docs/**/*GATE*.md, docs/diamond-betting.md),
  including the floor list registered on 2026-10-01: 2026-10-20, 10-21, 10-23, 10-28, 10-31,
  11-02, 11-06, 11-13, 11-16, 11-17, 11-18, 11-20 (the Prospect Anchor floor), 11-25, 12-01 (the
  eFV reserved read floor), 12-02, 12-03, 12-08, 12-10, 2027-02-15. Such a day is skipped and the
  condition moves to the next free day.
- The plan's design dates (2026-11-24 for the look, 2027-01-12 for the health look, AG-Q3) are
  superseded by the condition and are not floors of this document.
- **Looking early disqualifies:** a look before its condition holds voids the family.
- **A late look** (a run on a day after the first day the condition held) first files a dated,
  docs-only amendment to this document naming the new day and the reason, committed alone, and
  only then runs.

---

## 14. The crash protocol (LANE_B.md 3.11)

Dry-run the whole reporting path on fixtures carrying nulls first (AG_6: a player with no age, a
bucket with no rows, a base with no CONFIRM cells, an empty archetype). At the look, tee stdout
and stderr to the output directory before anything runs. On an exception after scoring began,
STOP without rerunning and write OWNER_QUESTION.md. A rerun only on an owner answer and only if it
reproduces every line printed before the crash byte for byte (the ETA precedent), else VOID; a
second VOID on the same family closes it (VOID_CLOSED).

---

## 15. Bans, enforced in the lab (LANE_B.md 3.12)

- No archetype window containing its start season; no season-stat cohort under any name.
- No Statcast feature in any arm; no component curve change (K%, BB%, ISO, BABIP, HR).
- No FV, grade, list vintage, prospect database row, eFV matrix, reserved list vintage (R-LV) or
  reserved debut cohort (R-VM); no statistic by consensus-FV cell.
- No threshold, grid or frame change after this commit.
- No GATE, TIER-2 or CONFIRM number before the look's day; no H GATE or CONFIRM number before the
  health look's day.
- No ML bundle trained or scored; no pooled (side-free) age correction.
- No write to `.cache/fa_corpus.pkl` or any path-shape cache; no read of a path-shape cache.
- No label from the live sabermetrics cache or from a house eWAR v3 part.
- No `value_framework.py --fit`; no change to the FV anchors, P(bucket|FV) or
  `efv_score._age_factor`.
- No citation of a TIER-2 or CONFIRM number as support for a PASS.
- Nothing runs on another gate's look day (section 13).

---

## 16. Registry rows, producers and artifacts (LANE_B.md 3.13)

- Registry rows `aging_v3` (the ladder), `aging_v3_prospect_shape` (PS) and `aging_v3_health`
  (H), written "registered, not read" by AG_5_AGING_SERVICE_BUILD_DARK, not here. The
  `fa_aging_curves` row's notes point at this gate; `fa_war_paths_decay`'s notes name the
  call-scoped v2 pin of the ML features.
- Producers (none exist at this commit): `aging_v3.py`, `aging_v3_sidecar.py`,
  `tools/aging_v3_lab.py` (subcommands `dev`, `mde`, `look`).
- Artifacts (none exist): `data/aging_v3_mde.json` (DEV only), `data/aging_v3_eval.json` (the
  look), `data/aging_v3_curves.json` (the committed full fit, written by the flip that serves it,
  with `fetched_at` and `corpus_sig`).
- Tests (none exist): `test_aging_v3.py`, `test_aging_v3_gate.py`.

---

## 17. The protocol hash

`tools/aging_v3_lab.py` carries a protocol hash constant: the sha256 of this document's bytes
from the line that begins `## G-0.` up to (not including) the line that begins `## 18.`, line
endings normalized to LF. `test_aging_v3_gate.py` recomputes it, so an edit to sections G-0 to 17
after this commit fails the test. An amendment (section 18) is appended after section 19 and
never edits those sections.

---

## 18. The append-only record

Every run this gate authorises appends a row here with its date, family, verdict, artifact hash
and wall time, VOID runs included. A run is never deleted and a verdict never edited; a
correction is a new row. An amendment is admissible only before its family's look, on an
established fact about the data, filed with what moved on disk since this commit, appended as a
dated section after section 19, and never loosens a threshold.

| date | family | verdict | artifact | notes |
|---|---|---|---|---|
| 2026-10-08 | - | registered | - | registration committed alone; no candidate computed, no look spent |
| 2026-10-09 | ladder (DEV only) | DEV selection and power: lambda 1.0, smoother pen (penalty 16), k_P 400, k_R 800; T UNDERPOWERED (MDE95 0.0428), S, P and R powered (MDE95 0.0057, 0.0079, 0.0007) | data/aging_v3_mde.json sha256 6d8976929d69 | AG_6_AGING_V3_DEV_AND_POWER, tools/aging_v3_lab.py dev then mde on the DEV frame (26,249 rows, 3,018 players, label seasons 2008 to 2010), wall 316.7 s and 181.3 s; no GATE, TIER-2 or CONFIRM row scored; the look and health paths dry-run on fixtures with nulls only; committed 2026-10-14 |

---

## 19. Results

Empty at registration. Entries are appended only by AG_7_AGING_V3_LOOK (the ladder, PS, the
TIER-2 veto and CONFIRM) and AG_13_HEALTH_LOOK (H).

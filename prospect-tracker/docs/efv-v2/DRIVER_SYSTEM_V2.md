# eFV Driver System V2: synthesis of lanes I1 to I5 and A1

Synthesis lane S0, 2026-09-25. Read-only on the repo. Inputs: `efv3/<lane>/IDEAS.md` and
`PROBES.jsonl` for I1_consensus_bias, I2_new_information, I3_alignment_audit,
I4_disagreement_dynamics, I5_combination_structure, A1_driver_audit, plus
`docs/efv-v2/PROGRAM.md`. This lane ran one reconciliation probe (S1, `S0_synthesis/s1_reconcile.py`,
`s1_out.json`) and one code check, both logged in `S0_synthesis/PROBES.jsonl`. No reserved row
was read. Nothing is tabulated by consensus-FV cell. `docs/efv-v2/EFV_V2_GATE.md` does not exist
yet; only `PROGRAM.md` is in `docs/efv-v2/`.

Frame names used below: vm1 (vintage-matched, n 806, `data/source_backtest.json`), vm2
(timing-pinned, n 803, `data/efv_v2_dev_eval.json`), lv_dev / F-LV dev (list vintages 2011-2019,
W3 label, n 4,702 to 5,646 depending on the lane's row filter). All three are spent development
frames and share most of their players, so they are not independent replications.

---

## 1. The answer to the owner's question

Consensus plus outcome-derived drivers can fail to beat consensus because the drivers carry
almost no information that consensus has not already priced: eFV correlates 0.9175 with
consensus, and its partial correlation with the outcome given consensus is only 0.076 (E1), so
the best combination of v1-level information is bounded near +0.0085 on the vintage-matched
frame (E3). The scoreboard is a rank statistic, so drivers that make consensus a better WAR
estimate (calibration, side scaling, the zero floor) move it by nothing; only information beyond
the grade moves a Spearman (I2). v1 then adds its own losses: it pins the model leg at 0.70
(hitters) and 0.57 (pitchers) where the forward-chained fitted weight is about 0.1 to 0.35 at
AA and AAA and zero or below at A+ and lower (I5); its pitcher block learns "has a MiLB record"
as a debut signal (pitchers with a record debuted 70.1% of the time, without one 10.7%) and so
orders pitchers worse than an FV-only model (vm1 0.3759 vs 0.4007, A1); and it pools separately
fitted hitter and pitcher WAR scales, which costs 0.009 to 0.016 of pooled Spearman (I3, I5,
A1). The consensus errors that drivers can see are not stable: every context correction loses
out of fold (all context -0.059, CI95 -0.088 to -0.030) because its sign flips between vintages
(I1). Removing every defect at once, selected on these same frames and so an upper bound, gives
vm1 +0.0146 (CI95 -0.005 to +0.035), vm2 +0.0033 and lv_dev -0.0025 against consensus (A1): a
tie, not a lead. What changes that is information consensus does not hold at the read,
scored where consensus is weakest (list vintages, consensus rho 0.16 to 0.19 against 0.41 at
the debut year): protection status (R3 +0.0173, CI95 +0.0071 to +0.0283; W3 +0.0080, CI
includes 0; I2), pitcher strikeout rate at list vintages (pitchers +0.0274, CI95 -0.0006 to
+0.055; I1), and physical data, which has zero rows on any labelled vintage today (I2).

---

## 2. Bugs and hazards, first

These change what every number below means. B1 to B4 are defects in the served artifact or the
training data; B5 to B9 are hygiene items the gate must carry.

| id | defect | proof | effect | fix |
|---|---|---|---|---|
| B1 | **Harness ties eFV before scoring.** `source_backtest.run_source_backtest` (source_backtest.py 3569-3581, "Remap the raw eFV score onto a 20-80 grade") overwrites `grades["xfv"]` with pooled consensus quantiles rounded to 0.1; `_vm2_frame_rows` (line 2188, remap at about 2216) does the same. The comment says Spearman/AUC are unchanged; they are not. | 806 distinct raw scores collapse to 100 values on vm1 (I3). Raw eFV 0.3990 vs scored 0.3973, +0.0018 (CI95 -0.0003 to +0.0039); vm2 +0.0015; AUC 0.7484 raw vs 0.7471 scored vs consensus 0.7485. The mechanism is visible in the code: 806 ranks mapped onto a sorted list with about 161 distinct values must create ties. | eFV understated by 0.0015 to 0.0018 on every head-to-head cell. Does not explain the loss. | Score `raw_vm1` / `raw2`; keep the remap only for tier tables and archetype views. Test asserts the scored column equals the raw score and that distinct counts are preserved. About 5 lines. Log the move in `efv_progress.json` as a harness correction, never as model progress. |
| B2 | **The board serves a different object than the page scores.** Board sort `xfv_grade` (`storage.BOARD_GRADE_FIELD`, storage.py 5003) is the model leg through `apply_dispersion_correction`; Source Comparison scores `rank_war`, the blend. | vm1: served object 0.3872 vs blend 0.3990, -0.0119 (CI95 -0.0222 to -0.0024), the only resolvable difference in I3. Served object vs consensus -0.0250; pitchers only -0.052. | The page credits eFV with an ordering 0.012 better than the one users see. | One ordering (DS-02). The 2026-08-14 open question "rank-equivalence unresolved" is resolved: not equivalent. |
| B3 | **Training label leaks through MiLB missingness.** Rows with no MiLB block take raw 0.0 on every rate and level key (`efv_model._vec`); `milb_missing` is zeroed for `milb_unavailable` rows, so no indicator carries it. Block presence mostly means "identity resolved", which mostly means "debuted". | Decision years 2016-2024: pitchers with a block debuted 70.1%, without 10.7%; hitters 52.8% vs 13.3% (A1 `p3_structural.json`). Pitcher peak_k_rel marginal Spearman with the target +0.103 on all rows, -0.016 on debuted rows; pitcher age +0.051 vs -0.105; hitter n_milb_seasons +0.011 vs -0.140. | The pitcher block spends its slopes on the bust contrast, then scores players who nearly all have a block. Main cause of the pitcher-leg drag. | DS-04 (impute at has-block mean, absence indicator only in a reach head, rate slopes fit on has-block rows). |
| B4 | **Identity resolution is an outcome proxy.** Players got mlbam ids mostly when they debuted. | I1: rows without an mlbam id are 100% non-debuters at V 2017-2019 (953 rows). I2: a name-plus-debut-year resolver made age plus level "beat" consensus by +0.0304 (CI95 +0.0125 to +0.0496); outcome-blind resolution gives +0.0003 (CI95 -0.0174 to +0.0176). Repo records: rows with an mlbam id have W3 > 0 in 29.6% of cases vs 22.5% for rows resolved by name. Training matrices: 475 hitter and 672 pitcher bust rows with no id and no rates. | Any F-LV frame (EV-04) that drops unresolved rows or lets a model see missingness is selected on the outcome. A fake win of about 0.03 is available by accident. | DS-03: outcome-blind resolver (never reads a debut or MLB column) plus a label-balance test on every missingness indicator, before EV-04. |
| B5 | Pooling separately fitted WAR maps. | Same input, fv-only pitcher score on lv_dev: 0.1466 pooled vs 0.1569 remapped within (side, V) (A1 `p4_stack.json`). | About 0.010 of pitcher Spearman lost to scale alone. | DS-07. |
| B6 | Served overlays never graded. `_age_factor` (efv_score.py 1081; onset 23, -0.10/yr, floor 0.75), `_role_factor`, `_injury_factor`, `_statcast_factor`, dispersion correction, side fairness (`run_live`, around 2291-2376) are absent from `oos_grades`. | A1 bug 5. The age ramp pushes against the fitted age weights (+0.086 hit, +0.102 pit standardized). | Unknown sign on the served board. | DS-11. |
| B7 | Placeholder debut dates. 138 debuted matrix rows (56 hit, 82 pit) carry `{year}-07-01` from `storage._safe_in_year_placeholder`. | A1 bug 3. Debut year agrees with the first eWAR season on all 1,834 rows, so labels are safe; the vm1 input cutoff and any service-window arm read the day. | Part of vm1's 247-row timing tilt; vm2 immune. | DS-12. |
| B8 | Identity collisions in training. Five critical hitter bust rows (adrian_hernandez, michael_perez, enmanuel_rodriguez, miguel_gomez, david_rodriguez); two bind an mlbam id that postdates the row cutoff. | A1 bug 4. | Small count, feeds B3. | DS-13. |
| B9 | Reserved-frame hygiene. (a) I4's first P5 run read 3,270 E1 rows without the vintage-matched filter, 1,127 at list years 2020-2021 (R-LV overlap), for three statistics (spread and Pipeline-minus-consensus partials given consensus); void and unused, logged at I4 PROBES line 6. (b) The served lv_dev read keeps 32 rows with status `reserved_vm` (players who debuted 2025+, W3 = 0 because they did not debut within V+3; `efv_labels.py` 235-244). No 2025+ WAR is read, but the gate should state the policy. | I4 disclosure. | (a) is one exposure of R-LV-overlapping rows: the FG-vs-Pipeline spread cannot be credited on R-LV as a rank or P(bust) finding. (b) is a policy gap. | DS-15 records both. |

**A scoring fragility found in this lane (S1).** I4 reported that Pipeline alone beats consensus
within (V, side) on F-LV dev (+0.018, CI95 +0.006 to +0.032, n 5,646); I5 reported that Pipeline's
lead on lv is entirely group level (remapped within side x vintage: -0.0042). S1 reads both on
I4's rows (n 5,646, V 2011-2019, reserved_vm dropped, B 500): consensus pooled 0.1957; Pipeline
raw pooled 0.2126 (+0.017, CI95 +0.004 to +0.029); Pipeline remapped within (V, side) onto the
consensus values, pooled 0.1877 (-0.008, CI95 -0.023 to +0.011); size-weighted within-group mean
Pipeline 0.2064 vs consensus 0.1884 (+0.018). V 2014-2019 (n 4,646) repeats the pattern (+0.022
raw, -0.010 remapped, +0.019 within). The code check reproduces 0.2064 within and 0.1957 pooled
exactly. Both lanes were right about their own statistic. **The same ordering can read +0.018
or -0.008 against consensus depending only on how groups are pooled.** Until the gate fixes the
statistic, a dev lead or loss of 0.02 on F-LV is not interpretable. This is why DS-15 comes
before any reserved read, and why the V2 design below competes on within-group order.

---

## 3. Ranked ideas across lanes

Deltas are against PROSPX consensus unless marked "vs v1". CIs are player-clustered bootstrap
from the named lane. "Expected reserved effect" is my argued estimate for R-LV (V 2020-2021, floor
about 0.017 to 0.021) and R-VM (look 1 floor 0.0596), not a measurement.

| rank | idea (lanes) | mechanism | dev evidence | expected reserved effect | overfit risk | cost |
|---|---|---|---|---|---|---|
| 1 | **Fix B1 to B4** (I3, A1, I1, I2) | Harness, serving and training defects, section 2. | B1 +0.0018; B2 +0.012 on the served board; B3 drives the pitcher drag; B4 guards against a fake +0.03. | +0.002 on every look from B1; B3/B4 are validity, not margin. | None (correctness). | S to M |
| 2 | **Compete on within-(side, list year) order; consensus sets the level** (I3 idea 1, I5 idea 1, A1 idea 3) | Consensus FV is one scale across sides and years; eFV's is refit per fold and per side, and the pooled rank pays for the drift. | v1 within side x year: vm -0.0040, lv -0.0033 (raw -0.0199 / -0.0059; I5 `level_probe.json`). Within side only: vm1 +0.0091 vs v1 (CI95 -0.003 to +0.021), vm2 +0.0067 (I3). No parameter. | Removes a 0.007 to 0.016 loss; creates no lead. S1 shows the remap is not always benign under a pooled statistic, so register the statistic with it. | Low (no fit); interpretive risk only. | S |
| 3 | **Scrap the pitcher block; pitcher eFV = consensus until new pitcher data earns a slot** (A1 idea 1) | B3: the block's training signal is missingness. Consensus already absorbed the pitcher MiLB record at the debut read (E1 b_p3, -0.003). | Pitchers only, fv-only vs v1 block: vm1 0.4007 vs 0.3759, vm2 0.3856 vs 0.3614, lv 0.1466 vs 0.1376. Pooled vs v1: vm1 +0.0086 (CI95 -0.007 to +0.027), vm2 +0.0096, lv +0.0006. Same sign on all three frames. | Pitchers tie consensus instead of trailing by about 0.02. | Low (removes 8 terms). | Trivial plus restamp |
| 4 | **Replace the pinned 0.70 / 0.57 with a small constant weight fixed by a rule that reads no frame row** (I5 idea 2) | Forecast combination with a weak, highly correlated second input wants a small weight; the fitted forward-chained coefficient is about 0.1 to 0.35 at AA/AAA. | With idea 2 (weights 0.28 hit / 0.22 pit): lv +0.0075 (CI95 -0.0035 to +0.0194), hitters +0.0142 (CI95 -0.0006 to +0.0289); vm -0.0008 (CI95 -0.0098 to +0.0075). Inside groups on vm it beats v1's weight by +0.011 (CI95 +0.0017 to +0.0198). | R-LV +0.003 to +0.008; R-VM about 0. Under 10% odds of clearing the R-LV floor. | Moderate: one of about 25 structures on these frames. Lambda family closed by TOST; new frame, new output map and the new owner instruction make it registrable, not creditable. | S |
| 5 | **Driver pruning and the age scrap** (A1 ideas 4, 5) | Age has opposite signs on the reach and WAR-given-reach populations (hitter age marginal -0.059 all vs -0.214 debuted), so one slope flips by fold (5/11 positive). | Drop hitter age: vm1 +0.0055 (CI95 +0.001 to +0.011), vm2 +0.0060 (CI95 +0.002 to +0.012), lv +0.0037 (CI95 +0.001 to +0.007) vs v1, the only single change excluding zero on all three frames. k_rel, peak_k_rel, n_milb_seasons, ops_rel, is_ifa, milb_missing each point "drop helps" on vm1 and lv. obp_rel is the one hitter driver that earns on lv (drop costs -0.0083, CI95 -0.014 to -0.003). | +0.003 to +0.006 vs v1; a smaller share against consensus. | Low for age; subset choice is a forking path. | Trivial |
| 6 | **Protection status (40-man, November adds) in a timing/REACHED head** (I2 idea 1, PROGRAM D3/EV-08) | A club spends a roster spot on a player it expects to use or fears losing; graders see it but grade talent, not arrival, and W3 has a fixed window. | n 4,159, V 2016-2019: R3 +0.0173 (CI95 +0.0071 to +0.0283); W3 +0.0080 (CI95 -0.0018 to +0.0182); inside a hurdle +0.0046 (CI95 -0.0044 to +0.0143). | +0.005 to +0.010 on R-LV W3; about 0 on R-VM (rows already at debut). | Low: two binary pre-specified features, one expected sign. | S, plus a StatsAPI transactions backfill 2008-2014 (about 84 calls) |
| 7 | **Pitcher strikeout rate as a list-vintage residual, under a sign-stability admission rule** (I1 ideas 1, 2) | Scouts discount sub-AA performance; consensus absorbs bat-missing about a year late (E2: MiLB stats predict next-year revisions, OOS R2 0.041 to 0.059 for pitchers). By the debut year it has caught up, which explains the 39 debut-frame nulls. | Stats-only stability-selected arm, V 2017-2019 folds, n 2,622: +0.0092 (CI95 -0.011 to +0.027); pitchers +0.0274 (CI95 -0.0006 to +0.055), n 1,022. Pitcher K-rate sign positive in 5 of 5 vintages. Hitter OBP/ISO faded once FanGraphs joined (0.048 to 0.011). | +0.01 to +0.02 on R-LV pitchers, diluted to about +0.004 pooled; 0 on R-VM. | Moderate: 18 reads in the lane, rule chosen after p2/p3. Same lever as E2 L2 and D1 (register once). | Low; the frame (B4 fix) is the cost |
| 8 | **Modern physical-data panel on a surrogate chain** (I2 idea 2, PROGRAM D6) | Pitch physics, bat speed, sprint and arm are measured, not graded; the only candidate with information outside the public record. | 0 rows on labelled vintages; next-level legs PASS (`xfv_statcast_line4_eval.json`, whiff 788 pairs, velo 699). | Unknown, the only idea with room above +0.01. First W3 read 2027 (FSL) or 2029 (AAA). | High if gated on today's 57 / 52 first-2 rows; chain surrogates instead. | S for retention (urgent: DB tables hold 2026 only), M for the lab |
| 9 | **Anchor on a repaired consensus (pre-shrink, Pipeline-heavy)** (I4 idea 1, I1 idea 3) | Consensus pulls single-instance players a third of the way to FV 35 (consensus.py 1493-1501, 1,851 of 5,646 dev rows) and weights FG about equal to Pipeline although FG orders worse (-0.031 vs consensus within group). | Within-group Pipeline +0.018 (CI95 +0.006 to +0.032); buildable rules +0.006 (CI spans 0), hitters +0.014 (CI95 +0.001 to +0.030), F-VM +0.002. S1: the same Pipeline order reads -0.008 pooled after remap. | +0.005 on R-LV at best; shrinks on R-LV because 2020-2021 consensus is multi-source (I2 H2: 1.00 real source per row in 2011-2016). | Moderate to high: metric-fragile (S1), tilt chosen after seeing P1, mostly the closed weight A/B. It also "beats consensus by building a better consensus". | S to M |
| 10 | **FG-vs-Pipeline spread for P(bust) calibration, not rank** (I4 idea 3) | Disagreement marks risk. | Partial rank corr given consensus -0.054 (CI95 -0.095 to -0.008), n 2,064; every rank conversion lost (skeptic -0.020, discount -0.0017). | 0 on rank. Exposed on R-LV-overlapping rows (B9a), so not creditable there. | Low (one scalar). | S after a reach head |

**Measured and closed by these lanes (do not build as rank drivers):** context bias corrections
(side -0.0109, age -0.0105, age-for-level -0.0083, route -0.0388, draft capital -0.0093, position
-0.0317, org -0.0525, staleness -0.0061, FG-PL gap +0.0001; I1); org opportunity (club win%
-0.0042, org conversion -0.0030, org depth -0.0042, org list position -0.0041), Rule 5 exposure
-0.0001, trade +0.0032, Tommy John +0.0002, prior volume -0.0048, in-season climb -0.0088,
over-slot bonus -0.0145 (I2); consensus momentum -0.0027 OOS, stat-line arbiter -0.0027, skeptic
rule -0.020 (I4); credibility weights (-0.0041 vs flat), side switch (vm -0.0125), regime rank
stacks (-0.015 to +0.0008), reach-conditional heads (vm -0.028, lv -0.026) (I5); debuted-only
training (lv -0.0229, CI95 -0.035 to -0.011; A1), rank target (-0.0116; I3). The D1 revision
front-runner did not reproduce on dev vintages (`efv_drivers.py`). The recent-mover arbiter
(I4 idea 2, +0.0045, CI95 +0.0002 to +0.009, the 13th of 16 probes on 116 decided rows) is within
chance and stays a note until R-LV brings more sources per row.

---

## 4. DRIVER SYSTEM V2

### 4.1 Design principles, each from a measured failure

1. **Consensus is the scale; the model may only reorder inside (side, list year).** (I3, I5, A1;
   B5.) Consensus's cross-side and cross-year placement is already near rank-optimal on vm1 (an
   in-sample pitcher shift gains consensus +0.0003 and eFV +0.0087; I3).
2. **The weight on anything that is not consensus is small, constant, and fixed by a rule that
   reads no frame row.** (I5: fitted 0.1 to 0.35; per-row credibility weights add nothing.)
3. **A driver enters only if its sign held in every prior training vintage and its mean |t| is
   at least 1.** (I1 admission rule: cuts the all-feature loss from -0.075 to -0.027.) The
   per-vintage signs are stored beside the driver in the arm ledger.
4. **Timing is not talent.** Arrival drivers (age, level, protection, route) go only into a
   REACHED/timing head, never into the skill residual (I1 idea 5, I2 idea 3, A1 idea 4).
5. **Missingness never reaches a skill slope.** Skill slopes are fit on has-block rows; block
   absence may enter only the REACHED head, and only after the outcome-blind resolver (B3, B4).
6. **One ordering** for board, Source Comparison, pricing and P(bust) chips (B2, PROGRAM 3.1).

### 4.2 Scrap, keep, rewrite, add

| action | drivers and pieces |
|---|---|
| **SCRAP** | Pitcher block as built: peak_k_rel, k_rel, bb_rel, age_rel_level, x_era_k, tool_fb, age, seasons_at_level. Hitter age, milb_missing (weight 0.0001), n_milb_seasons, ops_rel (collinear with obp_rel), is_ifa as a slope. Pinned blend weights 0.70 / 0.57. The pooled output remap. Debuted-only training (never adopt). Any context bias-correction layer over consensus (I1). D1 as specified (did not reproduce). D5 as rank features. |
| **KEEP** | Consensus FV as anchor (served PROSPX consensus; see Q4 for repairing it). Hitter obp_rel, tool_hit, tool_speed, is_college. Bust rows in training. The consensus-leg clip fix (coherence, worth +0.0004 to +0.0015). |
| **REWRITE** | Missingness (has-block-mean imputation; absence flag only in the REACHED head). level_rank (after the missingness fix). k_rel and peak_k_rel into one hitter contact term. Output scale (within side x list year onto consensus values). Served overlays (age, role, injury, Statcast, dispersion, side fairness): graded out of sample inside `oos_grades` or moved to labelled chips. |
| **ADD** | Protection status (on 40-man at the read; November add in V-1) in the REACHED head. Pitcher list-vintage K-rate residual, only if it passes the admission rule inside each training fold. FG-vs-Pipeline spread in the P(bust) chip only (not in any R-LV claim, B9a). Physical-data retention now (EV-03), entry through a surrogate chain in 2027+. |

### 4.3 Architecture

For every player at read date t, side s, list year V (or debut-year read on F-VM):

    u_c        = within-(s, V) percentile of consensus FV                (the anchor, no fit)
    z_skill    = standardized residual score of the skill head, s-specific:
                   hitters: ridge on [obp_rel, contact, tool_hit, tool_speed, is_college,
                            level_rank(rewritten)] vs the within-(s, V) W-target percentile,
                            offset u_c, fit on has-block rows only
                   pitchers: 0 (consensus only), or the stability-admitted K-rate residual
                            if it passes the admission rule in every training fold
    z_time     = standardized residual score of the REACHED/timing head:
                   logistic on [u_c offset, age-for-level, level_rank, on_40man, nov_add,
                            milb_absent (outcome-blind ids only)] for debut within the window
    order_idx  = u_c + w_s * (z_skill + a * z_time)
    eFV grade  = consensus FV value of (s, V) at order_idx's within-group rank (ties averaged)
    eFV WAR    = continuous consensus-FV-to-WAR map evaluated at the eFV grade (pricing only)

- **Heads.** Two ridge residual heads, not a hurdle product. I5 measured the reach-conditional
  head alone at vm -0.028 and lv -0.026, and H0 (the product form) read below v1 on vm2 (0.3807)
  and on lv (0.1575). The residual form keeps H0's idea (fit only what consensus does not
  explain) without multiplying two noisy heads.
- **Weights.** w_hit and w_pit are fixed by one stated rule before any read: the pooled
  forward-chained OLS coefficient on (model leg minus consensus) over decision years up to
  2016, which reads no frame row (I5's proposal). Expect about 0.2 to 0.3 for hitters. a (the
  timing share) is fixed at the same rule's ratio of the two heads' coefficients. If the rule
  gives w_pit at or below 0, pitcher eFV equals consensus.
- **How consensus enters.** Only as u_c (percentile offset in both heads and in order_idx) and
  as the value set the grade is drawn from. Consensus is never a feature with a free slope.
- **Side treatment.** Hitters get the skill and timing heads. Pitchers get timing only by
  default, plus the K-rate residual if admitted. Each side is ordered and scaled separately;
  sides meet only through consensus's own values.
- **Why this maximizes the expected reserved delta rather than the dev fit.** It has at most
  two fixed weights and about eight slopes, all admitted by a rule; its variance against
  consensus is the smallest of any structure measured (I5: CI width 0.017 on vm, 0.023 on lv);
  and it removes the three self-inflicted losses (pooled scales, pinned weight, pitcher proxy)
  that would otherwise hide any new information at full size.
- **Scoring statistic.** Primary: size-weighted within-(side, vintage) Spearman for F-LV and
  R-LV, with pooled Spearman as a registered secondary (I3 idea 4, I5 gate finding, S1). Under
  this statistic the level map is a no-op and eFV competes on ordering alone, which is the only
  thing drivers can change. The choice must be disclosed as made after vm1 showed it favours eFV
  (-0.0131 pooled to +0.0058 within, I3) and after S1.

### 4.4 Honest expectation

On the dev evidence, V2 should land at about consensus plus 0.003 to 0.010 on R-LV and about 0
to +0.005 on R-VM. The R-LV floor is about 0.017 to 0.021 and the R-VM look-1 floor 0.0596.
P(resolvable win on R-LV) is under 10%; on R-VM look 1 about 0. The modal outcome is a tie.
Two things raise the odds: protection status and pitcher K rate both live on list vintages,
where consensus is weakest, and physical data arrives from 2027. Two things lower them: the
R-LV consensus is multi-source while dev consensus was one list for 2011-2016 (I2 H2), and the
structural and driver choices above were all informed by spent frames.

---

## 5. Build list

Order is top to bottom. Effort: S under a day, M one to three days, L more. Every DS item that
changes a served number records its before and after in `data/efv_progress.json` as a
correction or a model change, never mixed.

### Buildable now, on development frames and training cohorts

| id | item | files | tests | effort |
|---|---|---|---|---|
| DS-01 | Score raw eFV in the harness (B1). | `source_backtest.py` (3569-3581, `_vm2_frame_rows` about 2216) | scored column equals raw score; distinct count preserved; head-to-head moves by +0.0018 / +0.0015 | S |
| DS-02 | One ordering: board sort, Source Comparison, pricing and P(bust) all from the same order index (B2). Conditional on Q1. | `efv_score.py` (1748-1769), `storage.py` (`BOARD_GRADE_FIELD`), `efv_export.py` | board order equals scored order on every row | M |
| DS-03 | Outcome-blind identity resolver for list rows (B4); balance test on every missingness indicator. Precondition for EV-04. | `efv_vintage_frame.py`, resolver module | resolver imports no debut/MLB column (AST check); W3 > 0 share by indicator reported; I2 H1 regression test (+0.03 fake gain must vanish) | M |
| DS-04 | Missingness rewrite (B3): has-block-mean imputation (`NEUTRAL_MILB_IMPUTE`) plus `milb_absent` used only in the REACHED head; skill slopes on has-block rows. | `efv_model.py` (`_vec`), `efv_v2_model.py` | skill head training rows all have blocks; absence flag absent from the skill design matrix | S to M |
| DS-05 | Driver pruning (4.2 SCRAP list); hitter contact term; pitcher skill head = none by default. | `efv_model.py` (`_FEATURES_HIT`, `_FEATURES_PIT`), goldens | feature lists pinned; golden restamp | S |
| DS-06 | Admission rule: per-training-vintage sign and mean |t| check; signs stored per driver. | `tools/efv_driver_admission.py`, `data/xfv_arm_ledger.json` schema | a driver with one flipped sign is refused; ledger carries per-vintage signs | S |
| DS-07 | Level/order output map within (side, list year) onto consensus values; separate WAR pricing number (B5). | `efv_score.py`, `efv_model.oos_grades`, `tools/efv_v2_dev_read.py`, `source_backtest.py` | within-group rank equals order_idx rank; group value multiset equals consensus's | S |
| DS-08 | Combiner with fixed w_s and a from the stated rule (decision years up to 2016). | `efv_v2_model.py` | rule reads no frame row (row-set assertion); weights written to the registration before any read | S |
| DS-09 | Protection status features and the 2008-2014 transactions backfill (EV-08). | `efv_drivers.py` (`forty_man_asof`, `nov_add_asof`), `.cache/mlb_transactions` | as-of cutoff respected; coverage by V reported | S + S |
| DS-10 | Pitcher list-vintage K-rate residual, gated by DS-06 inside each fold. | `efv_v2_model.py`, `efv_dataset._milb_features(cutoff=)` | admitted or refused per fold, recorded | S |
| DS-11 | Grade served overlays out of sample or move them to chips (B6). | `efv_score.run_live`, `efv_model.oos_grades` | live path and OOS path produce the same order when overlays are off | M |
| DS-12 | `debut_date_is_placeholder` flag; re-date the 138 rows from StatsAPI people (B7). | `storage.py`, matrix builders | no scored row reads a placeholder day | S |
| DS-13 | Resolve the five critical collision rows; check michael_perez's label (B8). | `data/identity_collisions.json`, matrices | collision list empty for training keys | S |
| DS-14 | Physical-data retention now (EV-03); one fetch to check Savant minors FSL 2021-2022. | `tools/snapshot_modern_signals.py` | nightly snapshot exists and is append-only | S |
| DS-15 | Draft `docs/efv-v2/EFV_V2_GATE.md` sections that can be written now: primary statistic within (side, vintage), pooled secondary; identical output map for every rater; the V2 candidate spec (4.3) with weights; the B9 disclosures; the forking-path count (section 6); reserved_vm W3 = 0 row policy. | `docs/efv-v2/EFV_V2_GATE.md` | doc lint (no em-dash); a test that the look runner refuses without the committed file (EV-13) | M |
| DS-16 | ONE pre-declared dev read of the assembled V2 on lv_dev and vm2, after DS-01 to DS-10, under the DS-15 statistic. It is the selection-rule input, not a claim. | `tools/efv_v2_dev_read.py` | frame guards (V at most 2019, debut year under 2025) asserted | S |
| DS-17 | P(bust) chip: spread plus REACHED head, scored by Brier / log loss on dev. | `efv_v2_model.py`, board chip | calibration reported by side | S |

### Must wait

- **After the fWAR label freeze (about 2026-10-05):** EV-04 labels on fWAR; EV-05 measured floors;
  DS-16 re-run once on the frozen label (the registered dev number); DS-10's admission on the
  frozen label; EV-12 registration commit with DS-15 content and empty results.
- **Not before 2026-12-01, and only after `EFV_V2_GATE.md` is committed:** any R-LV read
  (V 2020-2021) and any R-VM read (2025+ debuts). One look each, one primary candidate (V2),
  Holm across frames if Q2 = A.
- **2027 and later:** physical-data surrogate chain (FSL-era V 2022 resolves at RT 2027, AAA-era
  V 2024 at RT 2029); R-VM looks 2 and 3.

---

## 6. Forking-path count (from the PROBES.jsonl files)

| lane | logged lines | notes |
|---|---|---|
| A1_driver_audit | 40 | 36 lines each scored on three frames (vm1, vm2, lv_dev); 2 descriptive, 1 input check |
| I1_consensus_bias | 19 | 1 frame build, 18 scored reads |
| I2_new_information | 38 | 18 under the outcome-leaking resolver (superseded), 17 + 2 outcome-blind, 1 in-sample screen |
| I3_alignment_audit | 22 | 20 on vm1, 2 on vm2 |
| I4_disagreement_dynamics | 16 | includes 1 VOID read on R-LV-overlapping rows (B9a) |
| I5_combination_structure | 138 | 30 in buggy round r1 (kept), about 25 structures on two frames |
| S0_synthesis | 2 | S1 reconciliation, S1b code check |
| **total** | **275** | about 347 frame-level reads counting A1's three-frame lines three times |

Carry 275 logged probes (about 347 frame reads) into the gate as this program's forking-path
count for 2026-09-25, on top of the 39 closed arms in `data/xfv_arm_ledger.json`, plus one R-LV
exposure (B9a). At nominal 95% intervals, roughly 14 to 17 spurious CI-excluding reads are
expected from this many looks, so no single dev CI in this document is evidence on its own; only
the reserved reads can be.

---

## 7. Owner questions (default first)

**Q1. What the board leads with until a candidate beats consensus on a reserved frame.**
- **A (default). PROSPX consensus FV leads the board now; eFV (v1, then V2) becomes a column
  with its P(bust) and timing chips, and the Source Comparison page keeps the head-to-head.** The
  served eFV object trails consensus by 0.025 on vm1 (pitchers -0.052), and no repair measured
  on dev produces a lead.
- B. V2 leads once built (DS-07 puts it on the consensus scale, so it differs from consensus
  only by a small reorder), labelled "ties consensus".
- C. v1 re-sorted to the scored blend (PROGRAM Q1 A), status line only.

**Q2. The primary scoring statistic for the reserved frames.**
- **A (default). Within (side, vintage) primary, pooled secondary, the same output map for every
  rater, registered in EFV_V2_GATE.md with the disclosure that vm1 and S1 were seen first.**
- B. Pooled Spearman primary (today's headline), within-group secondary.
- C. Both co-primary with Holm.

**Q3. Scrap the pitcher feature block.**
- **A (default). Yes: pitcher eFV equals consensus until stuff or K-rate data passes the admission
  rule; the pitcher factor chips leave the board.**
- B. Keep the block with the missingness rewrite (DS-04) only.

**Q4. Repair the served PROSPX consensus itself (single-instance shrink toward FV 35, FG weight).**
- **A (default). Not before the reserved reads; register it as a separate consensus-method item
  afterwards. Repairing it first would raise the bar eFV is scored against and blur the result.**
- B. Repair it now and score eFV against the repaired consensus.
- C. Anchor eFV on the repaired consensus but keep the served consensus as the comparator
  (I4 idea 1; metric-fragile per S1).

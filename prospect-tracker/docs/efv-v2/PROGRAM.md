# eFV v2: the program to beat consensus and the industry

Program synthesis, 2026-09-24. Branch `efv-conviction-2026-08-08`. PLAN ONLY: nothing below
has been built, registered or read on a reserved frame. Written to the standard of
`docs/master-plan-2026-09-09-fangraphs-ewar-betting.md` and `docs/EFV_GATE_STANDARD.md`.
Every number carries its artifact and key, or the probe that produced it. No em-dashes.

The owner's instruction, 2026-09-24: eFV has to beat the industry and PROSPX consensus by as
much as possible, or the model and its drivers are redone entirely, and the glossary Source
Comparison page has to show the progress throughout. This is a NEW OWNER INSTRUCTION. It
meets the reopen standard for a redesign of the model class, frame, label and drivers. It
does not license re-running the 39 closed arms on the same frame and keeping the best one
(`docs/master-plan-2026-08-19-holistic-audit.md` s2; `docs/EFV_GATE_STANDARD.md`).

**Source keys.**

| key | artifact or probe |
|---|---|
| [SB] | `data/source_backtest.json`, generated 2026-09-24T19:26:45Z |
| [SC] | `data/xfv_scoreboard_eval.json`, generated 2026-09-24 |
| [XE] | `data/xfv_eval.json`, `data/xfv_eval_pitcher.json` |
| [AL] | `data/xfv_arm_ledger.json` |
| [E1] | `scratchpad/efv2/E1_diagnosis/b_p2_decompose.json`, `b_p3_ceiling.json`, `b_p4_withinyear.json`, `b_p5_anchor.json` |
| [E2] | `scratchpad/efv2/E2_data_labels/probe_labels.json`, `probe_timing.json`, `probe_consensus_lag.json`, `probe_statcast_rows.json` |
| [E3] | `scratchpad/efv2/E3_model_class/probe_ceiling_power.json`, `probe_r12_labelfree.json` |
| [S] | `scratchpad/efv2/S_program/probe_power_plan.py` -> `.json` (sqrt-scaled MDEs, O'Brien-Fleming bounds; arithmetic only, no data read) |

**Gate compliance.** No statistic in this program, its probes or its planned artifacts is cut
by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, look not before 2026-11-20). No
reserved fold was read. Strata used: side, age, last level, acquisition route, bonus band,
vintage, source disagreement.

---

## 0. Corrections to the brief

1. The artifacts were regenerated 2026-09-24. Vintage-matched, n 812: eFV 0.4061, consensus
   0.4134, MLB Pipeline 0.4120, FanGraphs 0.3672; AUC 0.7536 / 0.7505 / 0.7404 / 0.7166;
   delta -0.0073, mde95 0.0303, `resolvable: false` ([SB] `accuracy.head_to_head_verdict`,
   `accuracy.pooled_efv_common_vintage_matched`). The brief's 0.4064 / 0.4135 / 0.4117 /
   0.3682 are the 2026-09-23 build.
2. The per-side pair was reversed. On `xfv_vs_consensus.sides` (six-season label, n 755 / 892)
   hitters are eFV 0.3925 vs consensus 0.3821 and pitchers eFV 0.2828 vs 0.2957. On the
   vintage-matched frame itself: hitters eFV 0.4401 vs 0.4199 (+0.0201, CI95 -0.004 to
   +0.048), pitchers 0.3785 vs 0.3985 (-0.0199, CI95 -0.068 to +0.025) ([E1] `by_side`).
3. The disagreement share is now 0.561 on 289 rows, CI95 0.5052 to 0.6125 ([SC]
   `disagreement_receipts`). It is NOT on the vintage-matched frame: its consensus side is the
   latest pre-debut read (`source_backtest._xfv_vs_consensus_detail`, fed from every base
   year at :3775-3783), which can predate eFV's decision-year read. It carries part of the
   timing tilt measured in 1(5) and is a secondary, not a lead.
4. The vintage-matched frame is not fully timing-neutral. On 247 of 812 rows eFV's
   consensus input was read after May 1 of the debut year; that later read alone beats the
   preseason consensus by +0.0312 (CI95 +0.008 to +0.057). On the 565 in-window rows eFV
   trails by -0.0205 (CI95 -0.053 to +0.015) ([E1] `timing`). EV-01 repairs it.
5. Top-20 capture is eFV 0.7037 vs consensus 0.7133 on a 3,660 pool ([SB]
   `accuracy.capture_curve`).

---

## 1. The verdict on eFV v1

(1) eFV v1 ties consensus on the only admissible frame (0.4061 vs 0.4134, delta -0.0073
against a floor of 0.0303, [SB]) because it is a small perturbation of the consensus it reads:
Spearman(eFV, consensus) is 0.9175, and its partial correlation with the label given
consensus is 0.076 against 0.1105 the other way ([E1] `overlap`). (2) The estimator is not
the constraint: every model class on record lands within about 0.035 of the ridge and none
clears its floor ([E3] s2), and the best possible linear combination of eFV and consensus
reaches about 0.422, +0.0085 ([E3] `best_combo`). (3) Explanation 2 (the information is not
in the features) holds strongly for pitchers and moderately for hitters: in the debut-year
frame the consensus has already absorbed the upper-minors record, so leakage-optimistic CV
finds +0.033 of feature signal for hitters and -0.003 for pitchers ([E1] `b_p3`), and 0 of 39
scoreable arms cleared their own floor ([AL] `n_cleared_own_floor`). (4) Explanation 3 (the
frame cannot resolve the lead wanted) also holds: every lead the current inputs can produce
(+0.003 to +0.03) sits at or under the floor, and a +0.02 lead needs n about 1,864 on a frame
that grows about 155 rows a year ([E1] `n_needed_for_lead`, `future_frame_rows`).
(5) Explanation 1 (the model under-uses what it has) holds only narrowly: the pitcher model
leg scores 0.3446 against its own consensus input's 0.4107 while carrying 0.57 of the blend,
and the zero-WAR clip ties 131 rows and costs 0.0091 ([E1] `b_p5`). Both are real and both
are now seen on this frame, so neither can be credited on it.

**Consequence.** The redo is a redo of INFORMATION, FRAME and LABEL. A redesign of the
estimator alone is expected to produce a tie and is registered as a coherence repair, not as
the source of a lead.

---

## 2. The success contract

### 2.1 Metrics

- **Spearman rho is the gate.** An arm that does not clear the rho boundary is NULL,
  whatever its AUC did (`EFV_GATE_STANDARD.md` s3.1, A-CLAIM-11).
- **Contributor AUC may veto.** Positives are realized WAR at or above
  `efv_model._CONTRIB_WAR` (3.0) on the six-season label; on the W3 label (2.3) the threshold
  is `w*`, the W3 value whose exceedance share equals the six-season contributor share on
  vintages 2011-2016. `w*` is a RECORDED convention derived from label distributions only,
  fixed in the gate before any grader is scored. AUC enters as a veto only, so it does not
  enlarge the Holm family.
- **Estimator.** E_refit (paired, player-clustered bootstrap with every head and the
  consensus map refit per draw, B 2000), E_cond reported beside it. MAE stays a labelled
  diagnostic (`EFV_GATE_STANDARD.md` s4; today it loses on all four cuts: hit 4.279 vs
  4.142, pit 2.668 vs 2.615, [XE] `evals.debuted_km.pooled_oos`).
- **The claim is the one-sided 95% lower bound** of the delta, printed beside the point.

### 2.2 Frames

| id | unit | label | timing | role |
|---|---|---|---|---|
| **F-VM** (vm1 today, vm2 after EV-01) | debuted player, graded at the preseason read of his debut year; window 2017-2023 ([SB] `window`) | career WAR to date ([SB] `outcome_defs`) | vm1: 247 rows tilted toward eFV (0.4); vm2: every input pinned to the preseason window | headline today (`HEADTOHEAD_FRAME_GATE.md`) |
| **F-LV** (new, EV-04) | (player, list vintage V): every prospect with a real-grader preseason read in V, not yet debuted | W3: WAR over the first three MLB seasons, 0 if no debut within 3 seasons of V | eFV, consensus and every source graded as of the V preseason window, MiLB inputs through V-1. Timing-matched by construction and test-enforced | co-primary if owner Q3 = A; otherwise a second panel |
| predebut | [SB] `head_to_head_by_frame.predebut`, n 2,708, +0.079 | career WAR | tilted TOWARD eFV; the lead is about one year of consensus updating (+0.066 hit / +0.070 pit, [E2] `probe_timing`) | tilted, never a headline, never on the progress chart |
| all_vintages | same key `.all_vintages`, n 3,270, +0.0439 | career WAR | tilted TOWARD consensus | tilted, same treatment |
| bust-inclusive | [SB] `accuracy.claim_instruments.bust_inclusive`, n 1,598 | registered 2026-09-06 | no consensus cell today | secondary |

Why F-LV and not a friendlier cut of F-VM: it is the population and timing at which the
industry publishes (every prospect, every preseason), it includes busts, and W3 has a fixed
three-season exposure, which removes the between-vintage scale term that moved the F-VM
delta by about 0.015 ([E1] `b_p4`). It was chosen after E2 read the consensus's level on it
(0.252 hit / 0.232 pit vs W3, V 2011-2016, [E2] `faithfulness_list_vintage_frame`); no eFV
number has ever been computed on it. The gate must say both things.

W3 is a faithful surrogate on the resolved vintages: rho(W3, six-season) 0.787 hit / 0.821
pit, and it keeps the grader's ordering (consensus vs W3 0.252 against 0.278 vs six-season;
pitchers 0.232 against 0.272) ([E2]). W2, R3 and AA2 lose the grader ordering or are hazard
components; they are not scoring labels.

### 2.3 Comparators

On identical rows, per frame: PROSPX consensus (primary); MLB Pipeline and FanGraphs
(secondary Holm family); Baseball America where it has rows (136 on F-VM, [E1] `per_source`;
not in SCORED_SOURCES and not promoted by this program). ESPN, Just Baseball and TJStats have
0 rows on F-VM ([E1]) and are listed as "no rows", never dropped silently. For ranking,
consensus is effectively Pipeline on F-VM (oracle Pipeline weight 0.95, [E1] `overlap`), so
Pipeline is the industry bar that matters; eFV already reads +0.0388 over FanGraphs (CI95
-0.004 to +0.077) and -0.0059 under Pipeline ([E1] `per_source`).

### 2.4 Reserved frames

| id | content | readable | hard guard |
|---|---|---|---|
| **R-LV** | F-LV vintages V 2020 (W3 resolvable now: 821 hit / 478 pit rows) and V 2021 (W3 resolves at the 2026 freeze: 906 / 462) ([E2] `counts_by_vintage_side`). Only counts have been read on it | once, after EFV_V2_GATE.md commits | `efv_vintage_frame.RESERVED_LV = {2020, 2021}`; any score on these vintages raises unless the look runner passes the committed gate's sha |
| **R-VM** | F-VM prospective: the 2025 debut cohort (joint with Z1c, owner Q4), then 2026 and 2027 | group-sequential looks at RT 2026, 2027, 2028 | `source_backtest.CANDIDATE_YEARS` may not include 2025+ and `efv_model.SCORED_YEARS` may not include 2025+ until the look record exists (test pin) |

Disclosures the gate must carry: R-LV is a vintage hold-out, not a player hold-out (many
2020-2021 list players sit in F-VM rows already read), and its W3 outcomes are seasons
2020-2026, of which 2020-2025 have been used as training labels for OTHER players. R-VM is
clean: no artifact scores eFV against 2025-debut outcomes (matrix holds zero 2025 debuted
rows; SCORED_YEARS ends 2024; the Source Comparison window ends 2023), a receipt EV-12
re-verifies. Z1's serving confirmation for passers also names the 2025 fold at the 2028 run
(`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` s2.4); the joint registration
covers it.

### 2.5 The floor at each data stage

mde95 scaled as sqrt(812/n) from [SB] 0.0303, order of magnitude only ([S]
`mde95_by_stage_sqrt_scaled`, [E3] `mde95_by_n`):

| stage | n | mde95 |
|---|---|---|
| F-VM today | 812 | 0.0303 |
| F-VM at the 2027 run (vintage 2024 enters by `min_lag_years` 3) | about 975 | 0.0277 |
| F-VM with 2025 and 2026 after the reserved looks release them | about 1,266 | 0.0243 |
| R-VM look 1 / 2 / 3 (2025, +2026, +2027 cohorts) | 210 / 420 / 630 | 0.0596 / 0.0421 / 0.0344 |
| R-VM with O'Brien-Fleming spending, one-sided alpha 0.05: z 3.205 / 2.141 / 1.694 ([S]) | same | delta needed 0.116 / 0.055 / 0.035 |
| R-LV, about 1,700 distinct players (assumed) to 2,667 rows | | about 0.021 to 0.017 |
| F-LV all W3 players V 2011-2020 | 3,511 | about 0.015 |

The F-LV figures ignore the frame's own tie structure and clustering; EV-05 measures them
before the gate commits, and the gate uses the measured values.

### 2.6 What "beat by as much as possible" can honestly mean

| frame | consensus rho | lead v2 can plausibly reach | ceiling on that lead | floor at the claim | resolvable? |
|---|---|---|---|---|---|
| F-VM | 0.4134 | +0.003 to +0.03 ([E1] s6) | +0.0085 from v1-level information ([E3] `best_combo`); +0.03 needs a new component of validity 0.436 at r 0.85 with consensus, or 0.404 at r 0.70 ([E3] `required_new_component_validity_by_r_with_consensus`) | 0.0303 now; 0.035 at R-VM look 3 (2028 run) | no, before about 2029, unless new information arrives |
| F-LV | about 0.25 vs W3 | +0.01 to +0.02 hitters, less pitchers, from D1 ([E2] s4 L2) | one year of consensus updating: +0.066 hit / +0.070 pit ([E2] `probe_timing`) | about 0.017 to 0.021 (to be measured) | only near the top of the plausible range |

So the honest reading: "as much as possible" means maximize the expected reserved-frame
delta by a selection rule fixed on the development frame, then report the one-sided 95%
lower bound. On current information the widest lead this data can certify in 2026-27 is about
+0.02, on F-LV, if the revision front-runner (D1) works. F-VM cannot certify any lead before
the 2028-29 runs. A tie remains the modal outcome, and the plan says so in advance
(FWAR_LABEL_EPOCH_GATE (k): the honest prior for Z1 is zero survivors).

---

## 3. The build

### 3.1 Champion and challengers

**Champion H0: consensus-offset hurdle, ridge heads** ([E3] s5).

    score_v2          = P(REACHED | x) * E[WAR | REACHED, x]
    logit P(REACHED)  = f_R(consensus_fv) + ridge_R(x)
    E[WAR | REACHED]  = f_W(consensus_fv) + ridge_W(x)

- f_R, f_W: within-fold logistic and OLS maps on consensus FV, fixed as offsets, continuous,
  never tabulated by FV cell. No zero-WAR clip (removes the 131-row tie, [E1] `b_p5`).
- ridge heads fit only what consensus does not explain; penalties by nested forward-chained
  CV inside the training years. The pinned lambda 0.70 / 0.57 disappears into the penalty,
  which removes the pitcher leg's drag by construction rather than by a lambda shift (lambda
  shifts are closed by TOST; this is a redesign under the new owner instruction, and it is
  adjudicated only on reserved frames).
- training targets: the six-season label with v1's censoring rule, or the censoring-native
  alternative (f2 in [E3] s4), decided in the gate; REACHED per the BUST2 definitions
  (`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` s3.2), CENSORED-NEVER excluded.
  W3 is a SCORING label only, so no training row waits on it.
- ONE ordering: the board grade, the Source Comparison score, the pricing grade and the
  P(bust) chips all derive from score_v2. Today they do not: the board sorts on `xfv_grade`
  (model leg, `storage.BOARD_GRADE_FIELD`, storage.py:4920), the Source Comparison scores
  `rank_war` (the blend), and `oos_grades` trains on busts while the headline frame holds
  none ([E3] s1).
- registered as NON-INFERIOR to v1 plus coherent. Not registered as a source of lift.

**Challenger C1:** H0 with the E[WAR | REACHED] residual head as the existing monotone
LightGBM (`efv_model._fit_lgbm_mono`, untouched config). Takes the Z1b slot; Z1's
registration must cede it in writing.

**Challenger C2:** H0 with E[WAR | REACHED] = E[PA or IP | REACHED] x E[WAR rate | REACHED],
each a ridge residual head over consensus. The one structure that gives non-scouting
information (playing time) a place to enter.

**Rejected** ([E3] s2, s4): learning-to-rank (hit -0.027, pit -0.021,
`data/xfv_model_class_sweep_eval.json`), standalone stacking (bounded near +0.007, needs
about 14,000 rows), standalone hierarchical lambda (NO SHIP,
`data/xfv_cohort_lambda_hier_eval.json`).

**Selection rule, fixed in the gate.** On the development frame (F-LV V 2011-2019 and F-VM
dev folds, both spent), the candidate with the highest E_refit rho delta vs consensus among
those non-inferior to v1 on both legs (TOST 0.02) is THE candidate. Only it is read on the
reserved frames as a primary hypothesis. The other two are read beside it as labelled
secondaries with no ship weight. Selecting on dev and confirming one candidate keeps the
primary family at m = 1 per frame.

### 3.2 Drivers, ranked by information (not by estimator)

| rank | driver | evidence | expected effect | where it enters |
|---|---|---|---|---|
| D1 | **Consensus-revision front-runner**: predicted c(V+1) - c(V) from as-of MiLB production, fitted in grade space only | OOS R2 hit 0.013 -> 0.053 (2,008 rows), pit 0.041 -> 0.059 (1,243) ([E2] `probe_consensus_lag`) | +0.01 to +0.02 hitters on F-LV, less pitchers; about 0 on F-VM, which explains the 39 nulls there | ridge_W and ridge_R, F-LV |
| D2 | **Pitcher-leg repair**: offset formulation, no clip, no pinned weight | pitcher eFV 0.031 under its own anchor; clip costs 0.0091 ([E1] `b_p5`) | up to about +0.03 on pitchers vs eFV's anchor, seen on F-VM so creditable only on R-LV / R-VM | H0 architecture |
| D3 | **Org-private signals**: November 40-man adds, contract selections, Rule 5 protection, as of V | 2,955 contract selections on disk since 2016; not in the arm ledger ([E2] L6) | small; mostly the REACHED head | ridge_R, C2's playing-time head |
| D4 | **Playing-time drivers** (C2 only): debut age, position, 40-man status, org depth; pick and bonus as org investment | [E3] f1 | unknown; pick and bonus stay CLOSED as rank features (D-1 null) and enter only the PA/IP head, disclosed | C2 |
| D5 | **Thin-evidence segments**: HS draftees -0.057 (CI95 -0.105 to -0.010), last level A+ or lower -0.062, FG vs Pipeline gap 10+ -0.079 ([E1] s3, about 35 cells read) | hypotheses only | registered as descriptive strata on the reserved read; any evidence-count interaction is a per-row-shrinkage arm, which is on record as wrong-signed (`EFV_FRONTIER_AUDIT.md` s3), so it enters only as a named C-arm if at all | strata |
| D6 | **Modern Statcast panel** (A-ball whiff, FB velo, aStuff+ per season, Savant minors AAA, CSW) | next-level PASS (`xfv_statcast_line4_eval.json`); pre-debut rows with a resolved first-2 label 57 hit / 52 pit now, 141 / 137 after the freeze ([E2] `probe_statcast_rows`) | 0 before about 2028; the only candidate with information the grader does not already hold | preserve now (EV-03), gate 2028+ |
| D7 | Z1 passers on the frozen fWAR label | honest prior zero survivors (FWAR gate (k)) | expected 0 | enter the frozen feature list if any pass |
| - | New grade sources, estimator changes | raise the consensus bar by the same amount ([E2] L7); [E3] s2 | about 0 | not levers |

### 3.3 Labels

- **L-A, training.** Published fWAR at the epoch, RESOLVED_THROUGH 2025 -> 2026
  (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`). Adds 92 hitter and 102 pitcher debuts to
  six-season resolution ([E2] `debut_cohorts`), about 10% off the floor, no margin on its
  own (clause (l): copy never claims accuracy from a basis change).
- **L-B, F-LV scoring.** W3 on the frozen fWAR provider: 4,435 hitter / 3,520 pitcher rows
  today on eWAR v2 ([E2] `totals`); EV-04 re-measures its faithfulness on fWAR (label-only
  arithmetic, no grader cut by cell).
- **L-C, hurdle head.** REACHED / CENSORED-NEVER per BUST2; 395 full-weight still-affiliated
  rows today ([E3] s4b).
- **L-D, R-VM look 1.** Two observed seasons: first-2 vs six-season 0.739 hit / 0.705 pit
  ([E2] `debuted_frame_firstk_vs_L6`).
- **Surrogate program standing.** Inside the debuted frame a faster label adds nothing (the
  2026-07-24 NO-SHIP stands, `docs/SURROGATE_LABEL_PROGRAM.md`); W3's value is as the scoring
  instrument of a different frame.

### 3.4 Items

Effort: S under a day, M one to three days, L more. "Now" means buildable before the label
freeze without reading a reserved frame; engineering reads on the eWAR v2 label are
published as development rows and adjudicate nothing.

**EV-00 Source Comparison progress ledger (M, now, no deps).** Section 5. Ships first so every
later step lands on the page the owner checks.

**EV-01 F-VM timing pin, frame version vm2 (M, now).** `efv_model.oos_grades` scores each
vintage-matched row with the consensus read inside the same preseason window the raters use;
`efv_dataset` gains an as-of consensus accessor; `source_backtest` stamps
`head_to_head_verdict.frame_version` and the same pin applies to `_xfv_vs_consensus_detail`.
Expected direction: DOWN (in-window rows -0.0205, [E1] `timing`); the owner is told before it
lands. vm1 and vm2 rows both stay in the ledger. Tests: `test_headtohead_frame.py` (every vm2
row's eFV consensus input dated inside the window), `test_scoreboard_h2h_frame.py`.

**EV-02 One served ordering for v1 (M, now, conditional on Q1 = A).** Board sort from the
scored blend (`xfv_grade_display`, efv_score.py:1841-1862) instead of the model leg;
`storage.BOARD_GRADE_FIELD`, `board_basis_fingerprint()` and `BOARD_RANK_BASIS_EPOCH` move
together. Lands by 2026-10-04 or after epoch step Z, never inside the epoch (clause (l)
attribution). Test: served board order equals the `oos_grades` order on common rows.

**EV-03 Modern-signal retention (S, now).** `tools/snapshot_modern_signals.py` writes
per-season, as-of-dated snapshots under `data/signal_snapshots/<season>/` (tracked), because
`statcast_metrics`, `zone_metrics`, `pitch_arsenals`, `sabermetrics`, `statlines` hold 2026
only and the sidecars keep the latest season per player ([E2] s1). One fetch checks whether
Savant minors returns 2021-2022. Test: a later season never overwrites an earlier file.

**EV-04 F-LV frame and labels (L; code now, labels after the freeze).** `efv_vintage_frame.py`
(`build_frame(side, V)` via `efv_dataset._milb_features(cutoff=)` and
`source_backtest._rater_grades_for_year`; `RESERVED_LV`), `efv_labels.py` (W3, W2, R3,
six-season, REACHED on `war_source.DEFAULT_PROVIDER`). Tests `test_efv_vintage_frame.py`: no
input dated after the V window; W3 = 0 iff no debut within 3 seasons; the reserved guard
raises; no group-by on FV cell anywhere in the module.

**EV-05 F-LV floors first (M, after the freeze, deps EV-04).** `tools/efv_lv_floor.py` ->
`data/efv_lv_floor.json`: E_cond and E_refit sd and mde95 for v1 vs each rater on dev vintages
2011-2019, plus the `w*` derivation. Emits no point delta (test).

**EV-06 B0-LV (S, deps EV-05).** v1 on F-LV dev vintages, every rater on identical rows, to the
ledger as frame `lv_dev`, role development.

**EV-07 D1 revision front-runner (M, now).** `efv_drivers.consensus_revision_hat(side, V)`,
forward-chained, target c(V+1) - c(V). Test: the module reads no WAR column and imports no
label module.

**EV-08 D3 org signals (S, now).** `efv_drivers.forty_man_asof`, `contract_selections_asof`
from `player_transactions`. Test: as-of cutoff respected.

**EV-09 H0 champion (L; code now, adjudication after the freeze).** `efv_v2_model.py`. Tests
`test_efv_v2_model.py`: the offset-only model reproduces the consensus order exactly
(liveness); no clip; one output drives board, score and price; fixed seed reproduces
bit-exact.

**EV-10 C1 (S, deps EV-09).** Monotone residual head. **EV-11 C2 (M to L, deps EV-09 and epoch
step F).** Per-season MLB PA / IP from the saber feed on the fWAR provider.

**EV-12 The registration (M).** Section 4. Deps: freeze receipt (P1), Z1 registration and its
results recorded, EV-05 floors, EV-04 guard, owner answers Q2 to Q4.

**EV-13 Look runner (M, deps EV-12).** `tools/efv_v2_look.py`: refuses without the committed
gate sha; sha256 pins on matrices, floors, model files at start and end with the nightly
idle; writes `data/efv_v2_gate.json`; appends a `look` row to the ledger; refuses a second
run of a spent look (test).

**EV-14 Frame growth (S, scheduled).** Vintage 2024 enters F-VM at the 2027 run on its own;
2025 and 2026 enter `CANDIDATE_YEARS` / `SCORED_YEARS` only after R-VM consumes them (test
pin).

**EV-15 Serving under the outcome (M, deps EV-13).** `efv_score.py`, `efv_export.py` read
`efv_v2_model`; new grade-basis epoch; `MODEL_REGISTRY.md` row `efv_v2` with eval artifact;
every accuracy string derived from `data/efv_v2_gate.json`. Not on a PROJ_PATH_SHAPE look day
and after the PROSPECT_ANCHOR_GATE verdict, so surplus re-prices through `value_framework`
once.

### 3.5 Sequence

| date | step |
|---|---|
| 2026-09-25 to 10-04 | EV-00, EV-01, EV-03, EV-07, EV-08; EV-04 and EV-09 code on the eWAR v2 label (development rows only); EV-02 if Q1 = A |
| 2026-09-27 | regular season ends (FWAR gate E6) |
| about 2026-10-05 | freeze fetch (O3 default); epoch step M not before 2026-10-05 |
| after epoch step Z | Z1 `LABEL_V3_DRIVER_RETEST_GATE.md` commits alone, runs (about 4.5 h, one process), results recorded |
| after the freeze | EV-04 labels on fWAR, EV-05, EV-06, EV-11 |
| 2026-10-23, 2026-11-13 | PROJ_PATH_SHAPE ARM A / ARM B looks: no eFV lab process on those days (both gates pin inputs with the nightly idle). eFV is outside that gate's blast radius (`PROJ_PATH_SHAPE_GATE.md` "Every eFV number ... do not enter this path"), so no other coupling |
| not before 2026-11-20 | PROSPECT_ANCHOR_GATE look. No v2 artifact carries an FV-cell stratum before or after it |
| 2026-11 (target) | EV-12 commits alone, empty results |
| not before 2026-12-01 | R-LV look, once; R-VM look 1 (2025 cohort on RT 2026) in the same session if Q4 = A. After the anchor look so no session reads two gates |
| RT 2027 run, about 2027-10 | R-VM look 2 |
| RT 2028 run, about 2028-10 | R-VM look 3 (final boundary) |

Buildable now on training cohorts: EV-00 to EV-04 code, EV-07 to EV-10 code, development
reads on the eWAR v2 label. Must wait for the frozen label: every floor, every adjudicated
number, EV-11, EV-12 and every reserved read.

---

## 4. The registration: `docs/efv-v2/EFV_V2_GATE.md`

Committed ALONE, results section empty, before any number exists on R-LV or R-VM, and before
any v2 arm is scored under the frozen label.

**Clauses.**

- (a) Suspends CONVICTION_PROGRAM stop clause 1 for this registration only, citing the
  2026-09-24 owner instruction, and states that the closed arms are not re-run.
- (b) Preconditions: P1 label freeze receipt with per-side coverage; P2 floors from EV-05
  and re-derived F-VM floors on the new label; P3 parity (the v2 lab reproduces v1's
  `xfv_eval*.json` bit-exact with H0 switched off); P4 input sha256 pins; P5 the frozen arm
  list (H0, C1, C2), feature lists per head, hyperparameter rules and seeds.
- (c) Frames: F-LV and F-VM definitions verbatim from 2.2, with the frame-choice disclosure;
  R-LV and R-VM from 2.4 with the player-overlap disclosure; the Z1c and Z1-confirmation
  joint text (Q4).
- (d) Hypotheses: primary, the selected candidate beats consensus on rho, per co-primary
  frame, one-sided; Holm across frames (m = 2 if Q3 = A, else 1). Secondary Holm family: the
  candidate vs MLB Pipeline and vs FanGraphs on each frame. Non-inferiority vs v1, TOST 0.02,
  on dev, both legs.
- (e) R-VM boundaries: Lan-DeMets O'Brien-Fleming, one-sided alpha 0.05, looks at 1/3, 2/3,
  1 of information: z 3.205 / 2.141 / 1.694 ([S]); the exact values are recomputed in the
  gate's tool and written into the document before commit.
- (f) Controls on every cell: E_refit B 2000 player-clustered; zero-information twin
  (non-consensus columns permuted within vintage); 500-draw permutation null; at least 4 time
  splits with signs published; mde95 stated before the read; the contributor-AUC veto.
- (g) Descriptive strata only: side, age, last level, draft / IFA, bonus band, vintage,
  archetype, source disagreement (including the D5 hypotheses). Never FV cell.
- (h) Copy contract: the page prints the lower bound, the frame and the verdict word from the
  artifact; no accuracy claim from the label change (FWAR gate (l)).

**Kill rules.**

1. Frozen list: nothing added after commit.
2. One read per reserved frame per look; no friendlier frame, estimator or seed; no smoke
   number cited.
3. Early read: a guard trip, or any found score on R-LV or R-VM before the look, turns that
   frame into development permanently for v2, and the ledger records it.
4. Dead instrument: if dropping consensus from H0 does not resolve as harmful on dev, BLOCKED.
5. Twin at or above the candidate: no result.
6. AUC veto: rho pass with contributor AUC adverse beyond its floor is a FAIL.
7. Stale inputs void the run.
8. Program close: if the candidate does not clear R-LV and does not clear R-VM by look 3, the
   record reads "eFV v2 ties consensus on label build X". No new model-class arm until either
   a new information source enters (a column absent from `xfv_arm_ledger.json` with as-of
   coverage of at least half the frame) or the 2027 label epoch.

**What ships under each outcome.**

| outcome | served | Source Comparison says |
|---|---|---|
| WIN: rho boundary cleared on a co-primary frame after Holm, no veto, controls pass | v2 as the board grade, new grade-basis epoch | "eFV leads PROSPX consensus by at least X (95% lower bound) on <frame>"; per-source lines only where the secondary family clears |
| TIE: non-inferior to v1, no reserved win | per Q2 (default: v2 ships for coherence) | "ties consensus"; the F-VM prospective looks continue |
| INFERIOR to v1 on dev | v1 stays; v2 not read on reserved | "v2 did not pass development" |
| RESOLVED LOSS vs consensus on a reserved frame | v2 not served. If v1 also resolvably loses on R-VM, the board leads with PROSPX consensus FV and eFV becomes a column | "consensus leads by at least X" |

If v2 cannot beat consensus by a resolvable margin, the board leads with whatever Q1 and Q2
fix, and in no outcome does the page show the tilted +0.079 as progress.

---

## 5. The Source Comparison progress ledger

### 5.1 `data/efv_progress.json`

    {
     "schema": 1,
     "generated_at": "...",
     "headline_frame": "vm",                  // mapped from head_to_head_verdict.basis
     "frames": {
      "vm":        {"basis_key": "pooled_efv_common_vintage_matched", "role": "headline", "tilted": false},
      "lv_dev":    {"role": "development", "tilted": false, "note": "spent, not a claim"},
      "lv_res":    {"role": "reserved", "tilted": false},
      "vm_pros":   {"role": "reserved", "tilted": false},
      "predebut":  {"role": "tilted", "tilted": true, "tilt_toward": "efv", "note": "<basis_note from artifact>"},
      "all_vintages": {"role": "tilted", "tilted": true, "tilt_toward": "consensus"},
      "disagreement": {"role": "secondary", "note": "latest pre-debut consensus read"}
     },
     "rows": [{
      "run_id": "<source generated_at>|<frame>|<content hash 8>",
      "date": "2026-09-24",
      "trigger": "nightly | efv_change | look | backfill",
      "model_id": "efv_v1", 
      "model_version": {"fingerprint": "<storage.board_basis_fingerprint()>", "commit": "<sha>",
                        "label": "ewar_v2@2026-09-03T12:35:09", "resolved_through": 2025},
      "frame": "vm", "frame_version": "vm1", "window": [2017, 2023],
      "n": 812, "n_by_side": {"hit": 391, "pit": 421},
      "raters": {"efv": {"spearman": 0.4061, "auc": 0.7536},
                 "prospx_consensus": {"spearman": 0.4134, "auc": 0.7505},
                 "mlb_pipeline": {"spearman": 0.4120, "auc": 0.7404},
                 "fangraphs": {"spearman": 0.3672, "auc": 0.7166}},
      "deltas": {"vs_prospx_consensus": {"spearman": {"delta": -0.0073, "ci95": [lo, hi], "mde95": 0.0303,
                                                      "estimator": "E_cond, player-clustered", "resolvable": false},
                                         "auc": {...}},
                 "vs_mlb_pipeline": {...}, "vs_fangraphs": {...}},
      "resolvable": false,                    // copied from the artifact, never recomputed
      "verdict": "not resolvable at this power",
      "sources": [{"path": "data/source_backtest.json", "generated_at": "...", "sha256": "..."}],
      "note": "",
      "last_verified_at": "..."
     }]
    }

Honest by construction:

1. The ledger layer computes no statistic. Every number is copied from a named artifact key;
   the row stores the artifact's path, `generated_at` and sha256.
2. CIs come from the producer: `source_backtest` gains `_paired_delta_ci(rows, a, b, metric)`
   (player-clustered, reusing `_cluster_layout` / `_cluster_draw`, fixed seed) and writes
   `accuracy.head_to_head_verdict.ci95` plus a new `accuracy.head_to_head_vs_sources` block
   (each source, both legs, delta, ci95, mde95 from `_econd_floor`).
3. Append-only. `efv_progress.update(data_dir, trigger)` builds candidate rows for every
   frame present, compares a content hash (model version, frame version, n, raters, deltas)
   with that frame's last row, appends on change, and otherwise only moves
   `last_verified_at`. Nightly runs with no change add no row.
4. Backfill: `tools/efv_progress_backfill.py` walks `git log -- data/source_backtest.json`,
   reads each committed version with `git show`, emits `backfill` rows only where
   `head_to_head_verdict` exists, with `ci95: null` (not recomputable) and the commit date.
   Run once, committed once.
5. Tilted frames are rows with `role: tilted`; they are never the headline and never on the
   chart.

### 5.2 Producers

- `efv_progress.py` (new): `build_rows(sb, sc, fingerprint)`, `update(data_dir, trigger)`,
  written through `storage._atomic_replace`.
- `run_monthly.py`: call `efv_progress.update(out_dir, "nightly")` after the 9g scoreboard
  refresh (daily block at :3396-3423) and after `run_source_backtest` in the monthly block
  (:6104-6113), each under `_hb.record("efv_progress", ...)`.
- `tools/efv_scoreboard.py main()`: after writing `xfv_scoreboard_eval.json`, call `update`
  with trigger `efv_change` when invoked by hand.
- `tools/efv_v2_look.py` (EV-13): trigger `look`; `tools/efv_lv_floor.py` / EV-06 runner:
  `lv_dev` rows.

### 5.3 Render (glossary Source Comparison)

- `assets/glossary.js`: `_loadProgress()` (same lazy idiom as `_loadScoreboard`, fetch
  `/data/efv_progress.json`), called from `renderSourceComparison()` (:3312).
- `_methProgressLedger(prog)` under `_methHeroBanner`: a one-line headline from the latest
  headline-frame row (eFV, consensus, delta, CI95, floor, verdict word from the row); a stale
  chip when its `last_verified_at` trails `source_backtest.json`'s `generated_at`.
- `_methProgressChart(rows)`: inline SVG, x = date, y = eFV minus consensus rho; one dot with
  a CI95 whisker per row; a shaded band of plus and minus mde95 around zero; filled markers
  for headline rows, hollow for `lv_dev` (legend: "development frame, spent, not a claim"),
  distinct markers for `look` rows. Tilted frames are excluded from the series.
- A dated table: date, model and version, frame with role chip, n, eFV rho / AUC, consensus,
  Pipeline, FanGraphs, delta (CI95), floor, verdict, note. Tilted rows sit in a collapsed
  "Tilted frames (not evidence of skill)" block carrying the artifact's own `basis_note`.

### 5.4 Tests

- `test_efv_progress.py`: row numbers equal the [SB] keys exactly; a second update on
  unchanged artifacts appends nothing; append-only prefix property; `headline_frame` equals
  the frame of `head_to_head_verdict.basis`; tilted frames carry `role: tilted`;
  `resolvable` equals the artifact's; no key or stratum names an FV cell (whitelist of
  strata); em-dash lint on `note`.
- `test_efv_progress_backfill.py`: a version without `head_to_head_verdict` yields no row;
  backfilled `ci95` is null.
- `test_source_comparison_basis.py` (extend): `_methProgressLedger` and `_methProgressChart`
  contain no numeric literal for a rho, AUC or delta; the chart's series filter excludes
  `role: tilted`. `test_glossary_page_loads.py`: the new fetch resolves.
- `conftest.py` restore list gains `data/efv_progress.json` (pytest pollutes build artifacts).

---

## 6. Owner questions

**Q1. What the PROSPX board leads with while v2 is built (now to about 2026-12).**
- A. eFV v1, re-sorted to the ordering the Source Comparison scores (EV-02), with a status
  line "ties consensus, v2 in build". **Recommended:** it removes the three-orderings defect
  now and changes the lead grade once.
- B. eFV v1 as served today, status line only.
- C. PROSPX consensus FV leads; eFV becomes a second column until v2 passes.

**Q2. If v2 ties consensus on the reserved frames (non-inferior, not resolvably ahead).**
- A. v2 ships as the board grade for coherence (one ordering, the bust heads as model heads),
  copy says "ties consensus". **Recommended.**
- B. v1 stays served; v2 stays in the lab.
- C. The board leads with PROSPX consensus FV; eFV (v2) becomes a column.

**Q3. Does the list-vintage full-pool frame scored on W3 count as beating the industry?**
- A. Co-primary with the vintage-matched frame, registered before any eFV number exists on it,
  Holm across the two frames, W3 disclosed as a surrogate, six-season confirmation at later
  epochs. **Recommended:** it is the only frame where a resolvable lead is plausible before
  2029, and it is timing-matched by construction.
- B. A second panel only; the vintage-matched frame stays the only headline.
- C. It counts only after its six-season confirmation (V 2020 resolves about 2029 or later).

**Q4. The prospective reserved cohort for the vintage-matched frame.**
- A. One joint registration with Z1c on the 2025 debut cohort, one Holm family, first look
  after the RT 2026 labels. **Recommended:** the earliest first look.
- B. v2 takes the 2026 debut cohort alone; first look at RT 2027.
- C. No prospective leg; the vintage-matched frame is reported as development only.

---

## 7. Do-not-reopen additions from this program

1. The predebut +0.079 and all_vintages +0.0439 are timing, not skill ([E2] `probe_timing`);
   never plotted as progress, never a headline.
2. Estimator-only arms on existing columns are not registered as lift; the combination bound
   is +0.0085 on F-VM ([E3]).
3. New grade sources are not a margin lever; they move the bar they are scored against ([E2] L7).
4. The within-vintage F-VM reading (+0.0079, AUC +0.0125, [E1] `b_p4`) and the pitcher-leg
   observation were read on F-VM in this program; they may be registered only for fresh
   vintages or reserved frames.

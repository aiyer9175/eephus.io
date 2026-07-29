# eFV holistic improvement plan (2026-07-23, planning only - no arm has run)

Owner directive: push eFV + eFV surplus (and every model holistically) to the highest
possible Spearman/AUC, winning across eras, FV tiers, cohorts, biggest disagreements, and
head-to-head accuracy; create new metrics/blends as needed; hunt bugs in eFV, its data
feeds, and surplus; test wRC+ vs OPS+ for MiLB rates; sweep the full pitcher pitch-physics
and hitter Statcast component lists; test platoon splits; improve the tiebreaker.

Discipline (unchanged, non-negotiable): every lane pre-registers in a dated GATES.md before
any data is seen; one attempt per arm; marginal = FAIL; amendments only via the
retract-amend-rerun protocol with a-priori bounds; losses ledger + register; no re-attempt
of spent arms outside named keep-alives. Local-only until the owner says push.

## Where Spearman can actually still move (the honest lever map)

The training matrix is spent at its current vintage (2024-fold unlock consumed; model-class
sweep closed; ridge at the trainable-data ceiling on existing features). The five levers
that remain, in expected-value order:

1. NEW trainable feature families the matrix has never seen (platoon splits - verified
   fetchable back to 2015+; in-house linear-weights rate).
2. Measurement-layer amendments (S-XLINE weight/scope; the input line, not the model).
3. Correctness (bug hunts in feeds, score path, surplus chain - past audits moved real
   rank accuracy via labels alone).
4. Rank-adjacent surfaces that do not touch the trained core (tiebreaker stack, overlay
   revival under a display-space ceiling, proxy v2).
5. Calendar unlocks (Nov-15 sitting; 2025-debut folds ~2027; sub-AAA cohorts ~2028).

---

## PHASE 0 - Scoreboard + adversarial bug hunts (correctness before experiments)

0a. eFV SCOREBOARD artifact (data/xfv_scoreboard_eval.json + glossary panel): one unified,
regenerable matrix = pooled Spearman/AUC, per-era (<=2018 / 2019-21 / 2022-23), per-FV-tier,
per-cohort (ifa/college/hs/draft), t45/wm, head-to-head vs consensus/FG/Pipeline (same
players, OOS), top-20-percent capture, and a biggest-disagreements receipts table. Every
later gate cites this same-run baseline. Also becomes the "wins everywhere" tracker the
owner asked for: each cell carries win/loss vs consensus so weak cells are visible
(known: int'l bats is the one cohort consensus still wins; top-25 pitcher share).

0b. Bug hunt, three adversarially-verified fronts (workflow: finders -> refuters -> fix
only CONFIRMED; correctness fixes ship without gates, any served-number change runs the
standard battery + golden note):
- FEEDS/efv_dataset: label integrity at current vintage (veteran-debut guard counters,
  career_war merge-preserve, bust_recent weights), norms vintage, exposure fallbacks,
  S-XLINE row handling on multi-season AAA players, P1 V3 (pick,bonus) shared-key
  approximation (named residual risk from the V3 ship), level_rank fallback, DSL/CPX norms.
- SCORE/efv_score: factor application order + blend rebuild invariants, quantile-map edge
  cases (ties, pool boundaries), KRP+ vector exposure gate, provisional queue keying,
  reliability artifact consistency.
- SURPLUS chain: units invariant (6yr exposure vs 7yr control - test-pinned, re-verify all
  call sites), eta_years propagation, role/position arg (listed vs measured positions_played),
  display-quantile reprice band, isotonic calibration layer vs raw split, valuation-curve
  monitor vs served medians, trade-value tie-break consistency.

0c. Feed freshness/coverage audit: Savant-minors coverage vs live board, statsapi feed
cache gaps, 2026 draft bonus sync after the signing deadline (P1 slot-trust expires into
real bonuses - verify the handoff), snapshot staleness map.

## PHASE 1 - Measurement + rate-metric lanes (registered arms, run now)

1a. S-XLINE-W re-registration: shipped primary is W_HIT=0.5 (registered); the lab grid
carried 0.5/0.6/0.7 and the measurement study's optimum was w=0.7. Register S-XLINE-W:
single arm W_HIT=0.7 (pit side untouched), full clause structure (M re-read, invariance,
in-matrix no-harm >= -0.003, existing caps unchanged, post-flip served ceiling 3.0).
One attempt. Honest framing: parameter amendment on a shipped measurement layer, justified
by the layer's own measurement evidence, not by gate data.

1b. wRC+ lane (owner ask). Three steps:
- Data: refetch full-component MiLB stat lines (2B/3B/HBP/SF/SB) via the same statsapi
  season-stats family (cache .cache/milb_full_stats/), seasons 2011-2026, all levels.
- Build in-house wOBA-lite/wRC-lite: league-season linear weights (fixed FG-style weights
  scaled to league run environment; NO park layer - the W2 M-FAIL stands), level-relative
  and reliability-shrunk exactly like existing rates -> wrc_rel.
- Registered arms: (i) wrc_rel REPLACES ops_rel; (ii) wrc_rel alongside; (iii) fringe-gated
  variant (t45 bar +0.015, pooled/wm at noise floor). A-priori null stated in the
  registration: eFV already consumes the decomposed pieces (k/bb/iso/obp rel), which
  usually dominates any composite; the win condition is linear-weight shape information
  the pieces miss. FG's own MiLB wRC+ stays a manual-CSV-drop option only (FG 403-blocks
  our infra; the fangraphs_csv drop folder is the sanctioned route if the owner wants the
  literal FG number for display).
- Beat-both stretch: a shrunken component-weighted composite fitted to next-season wOBA
  (measurement-style clause M) as a THIRD candidate; only registered if (i)/(ii) read
  suggests composite information exists.

1c. Hitter Statcast expected-stat scope check (S-XLINE hit side today blends avg/obp/slg
gaps): register ONE extension arm - xISO gap as a fourth capped delta (savant_minors
carries xslg/xba so xiso derives) - same clause family. Skip anything K-measurement
shaped (CSW/xK lane closed permanently).

## PHASE 2 - NEW trainable data: platoon + discipline (the headline hope)

2a. PLATOON (verified: statsapi statSplits vl/vr for MiLB exist back to 2015+; probe
2011-2014 first - if present, full training coverage; if 2015+, features enter as
missing-flagged for early cohorts exactly like other vintage-limited features).
- Pull: vl/vr hitting + pitching splits, sportIds 11-14+16, seasons (2011|2015)-2026,
  cached + checkpointed.
- Candidate features (frozen list at registration): hitter platoon_gap_rel (wOBA-proxy gap
  vs same-hand share, reliability-shrunk), pitcher platoon_gap_rel (opposite-hand
  vulnerability), same_hand_exposure (usage context), bats L/R/S indicator interactions
  (bats_s never tested).
- Gates: standard efv_lab_runner arms per side, pooled + t45 + wm + per-cohort read.
  Cohort hypothesis stated a priori: int'l bats (the one consensus-wins cohort) and the
  top-25 pitcher cell are the target weak cells - a young hitter's platoon robustness and
  a pitcher's opposite-hand vulnerability are exactly what scouts price that stats have
  not carried. PAL reverse-platoon cross-feed for prospects ships as display regardless.
2b. Discipline-from-feeds for the UNGRADED model: compute call-code swing-decision
components (take share, zone-recognition proxy, 2K-called share) from our cached A/CPX/AAA
game feeds (2023+, our own data - no Decision+ contract issues) as features for
xfv_ungraded ONLY (its own OOS harness; low-minors is where components add per Will's own
report). The flagship matrix lane stays closed (2023+ starvation). Provisional-grade
improvements flow to the board via the existing provisional fold.
2c. SB/speed production: hit_sb_rel (SB rate vs level norm) - one lean arm, never tested,
low prior, cheap once 1b's refetch lands.

## PHASE 3 - Pitcher pitch-physics program (the owner's metric list, mapped)

Status map (what exists today for AAA arms, from .cache/aaa_pitches + stuff sidecar):
- ON DISK now: velo, iVB (pfx_z), HB (pfx_x), spin, extension, release height, arm angle,
  pitch usage/mix, per-type aStuff+ (W3 by_type), pooled aStuff+, delta_run_exp labels.
- REFETCH NEEDED: VAA + VAAOE (cache lacks plate-crossing vectors; refetch adds columns to
  the same Savant-minors pulls - bounded, cached), HorzRelAngle.
- DEAD (ledgered, not re-run): raw EV/barrel/hard-hit forward features at AAA
  (anti-correlated), CSW-implied xK (closed permanently), p90ev incremental (ISO absorbs).
- MLB-ONLY (pStuff+/external Stuff+, Savant percentile components for debuted players):
  no pre-debut history -> proxy v2 + post-debut surfaces only, never the prospect matrix.

3a. Descriptive foundation (no gate needed): per-pitcher AAA physics profile sidecar
(velo/iVB/HB/spin/ext/relH/arm-angle/mix depth by type) -> prospx pitcher card pills +
PAL cross-links. VAA/VAAOE added after the refetch.
3b. FORWARD screen (registered, one shot): each physics feature + owner-suggested blends
(velo-adjusted iVB, mix entropy, per-type stuff spread) screened for next-season K%/BB%/ERA
prediction on 2023->2025 AAA pitcher pairs, CI bars fixed a priori. Survivors become:
- 3c. OVERLAY REVIVAL under a display-space ceiling (the sanctioned S-XLINE-4 keep-alive
  path, now owner-authorized): whiff (hit K-channel, +0.0965 CI-clean) and FB velo (pit,
  +0.1423 CI-clean) already validated; NEW registration with the ceiling defined where the
  mechanism can bound it - clamp the DISPLAYED quantile against a no-overlay shadow ranking
  at <= 3.0 FV + a rank-displacement bound. Any 3b survivors join as additional overlay
  legs under the same clamp. This is the one path that can move served pitcher ranks NOW.
- 3d. E-STUFF matrix lane: stays closed (zero trainable coverage) - calendar 2027 when
  2025 debuts enter SCORED_YEARS. Explicitly not re-run.

## PHASE 4 - Proxy v2, tiebreaker v2, head-to-head targets

4a. xfv_proxy v2 (trainable NOW - targets first-MLB Statcast quality, resolves fast):
expand features with the full owner list (hitters: whiff/chase/z-contact/xwOBAcon/EV90/
maxEV/barrel/hard-hit/pull-air from savant_minors + feeds; pitchers: physics profile +
per-type stuff + mix). Gate: OOS r vs shipped proxy (hit 0.25 / pit 0.19 baselines).
4b. TBS v2 tiebreaker (owner ask): current tie arbiter is TBS on exact-decimal eFV ties.
Register a tiebreak stack - xfv_proxy score, then star odds (p_bucket), then aStuff+ for
pitchers - judged on resolved cohorts: within displayed-grade ties, does the stack order
realized 6yr WAR better than incumbent TBS? (Trainable now; changes ordering only among
visually-identical grades.) CONSTRAINT recorded: AP+ is contractually barred from any
ordering role.
4c. Weak-cell targeting: the scoreboard's per-cell wins drive which arms get fringe/cohort
gates (int'l bats, top-25 pitchers, FV45-50 pit 2019-21 era = the three named weak cells).
4d. Joint display map fairness fork: ledgered NO-SHIP with an open owner option (re-register
G1 as no-harm to ship the top-band fairness fix at pooled-accuracy neutrality). OWNER CALL,
not auto-run.

## PHASE 5 - eFV surplus program

- Isotonic surplus calibration refresh at current vintage (WS-6 layer; maintenance refit,
  registered bars on held-out slope/coverage).
- eta_years refinement: 40-man-selection + level + age debut-hazard-lite (own data;
  AP+ contractually excluded) -> surplus timing reprice; gate on eta_backtest (the harness
  already reruns monthly).
- Role/position arg: measured position (positions_played) vs listed position feeding
  sv_distribution role layer - registered A/B on resolved pitchers/movers.
- Units/basis audit (0b surplus front) + $/WAR anchor left untouched (fa_dpw coordination
  rule stands).
- Bucket-mixture consistency read: p_bucket vs realized by tier/age at current vintage
  (probabilities refresh; the closed BUCKET-AGE-HEAD lane stays closed).

## PHASE 6 - All-modules holistic sweep (each on its own harness)

| Module | Next eligible lane | Harness | When |
|---|---|---|---|
| FA market | pwoba xwOBA-blend re-gate (likely PASS) | pwoba_blend_regate_lab | Nov 15 |
| FA market | supply/age keep-alives at extended n | fa_market_feature_lab | next winter fold |
| Projections | star-slice-only mean head (the one unexplored variant) | mean_head_backtest | now |
| Projections | PT-risk era-standardized re-gate | pt_risk_lab (substrate cached) | 2027 |
| MLB Stats | rem_plus_3yr flat re-gate at extended n | rem_plus_lab | when n clears bar |
| MLB Stats | bat-tracking arm B + NOV-A/B Swing+ arms | bat_tracking_lab | Nov 15 |
| PAL | per-type stuff blend re-gate at coverage | pal_xrv_lab | ~2028 |
| Fantasy | startscore opp-K% arm | fantasy_startscore_lab | season end |
| Trade Machine | first true forward backtest (snapshots accruing since 6d) | trade_value_history | when window matures |
| CollegeSavant | stuff covariate re-gate | college_stuff_translation_lab | next class resolution |
| eFV core | 2024-cohort resolution unlock (every closed matrix lane) | governance battery | ~2027 |
| eFV sub-AAA | tracked A/CPX cohorts as trained features | statcast_alevel sidecar (frozen) | ~2028 |

## Owner decision queue

1. Joint display map fairness re-registration (4d) - output-changing, needs explicit
   authorization of the no-harm framing.
2. Will's private export bundle request (park factors v2 / MiLB eWAR / latent talent) -
   the only untested external signal set, data-blocked until he ships it.
3. FG wRC+ manual CSV drop (display-grade) vs in-house-only (1b default).
4. Overlay revival ceiling (3c) - the registration will state the display-space clamp;
   flag if the 3.0 bound should differ.

## Closed lanes appendix (will NOT be re-run; ledger locations)

Raw EV/barrel/hard-hit forward at AAA (anti-correlated; statcast line2/3 ledgers) · CSW/
whiff-implied xK vs raw K% (closed permanently) · pwoba_ev_arm · defense into eFV (3x,
prospect_def_value ledger) · physical/BMI/frame (untrainable) · ETA-as-feature · level
weighting/AA columns · age x level, K-BB explicit, level-jump, fv_trend, decimal age,
signing-bonus/slot as matrix features · power features (the founding correction) · scout
disagreement · model-class sweep (ridge stands) · per-cohort/hierarchical lambda · lambda
band raise (retracted; adjudication closed) · calibration line E-ISO/recal x4 · tail fix ·
relief shape into eFV · park measurement blend (W2, just failed) · DS+ pedigree (P1 V3
ARM-B) · IL features for eFV (E-LEAN spent) · Decision+/AP+ into any predictive head
(contract + redundancy) · college stuff into translation (W4) · K-strength sweep, velo
decline, FB-HR xFIP-lite, park shrink targets, HEM+ age hinge (plus-stat ledgers).

Registration files: docs/efv-2026-07-24/GATES.md (phases 0-5 lanes as they run),
docs/wills-2026-07-23/GATES.md + docs/efv-provisional-prior/GATES.md (this week's record),
docs/efv-2026-07-23/RECHECKS.md (calendar).

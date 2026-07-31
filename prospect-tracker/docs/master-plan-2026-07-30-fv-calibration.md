# Master Plan 2026-07-30: outcome-anchored FV calibration, derived tables, and the eFV framework

Executor: Claude Opus 5. Author: Fable, 2026-07-30, after the execution session that
landed commits eb065b4..07abfc8. Owner directives this plan implements:

1. Calibrate eFV by OUTCOME-EXPECTATION, not just relative to consensus FV (the Caden
   Hunter case: 48.6 today; he should read what his predicted production is actually
   worth on the industry scale).
2. Pitchers and hitters graded on DIFFERENT scales.
3. Use the industry FV framework (FanGraphs + MLB Pipeline + Baseball America, extracted
   to `docs/reference/FANGRAPHS_FV_FRAMEWORK.md`) as the STRUCTURAL BASIS - and TEST the
   tables, derive our own, invent rather than copy. The goal is not beating consensus by
   the most; it is the most ACCURATE, CALIBRATED, BACKTESTED FV grades on the market,
   anchored to real outcomes.
4. Correct position assignment: hitters by most-played MiLB position, pitchers SP/RP by
   games started.
5. Capstone: an explainer artifact for OUR FV grade and tool grade semantics, built from
   the derived tables.

Everything below is grounded in measurements already in the tree. Nothing is speculative
unless marked HYPOTHESIS. Repo root for paths: `prospect-tracker/`.

---

## 0. Ground rules (carried forward, plus new ones learned 2026-07-30)

All rules from `docs/master-plan-2026-07-29-efv-fa.md` section 0 stand (gate standard,
registry discipline, copy gates, commit-local-no-push, never compare grade bases on the
scored artifact, fabrication checks, read-which-line-failed). New ones:

1. **Never run pytest while any concurrent agent edits the tree** - conftest's session
   fixture git-checkouts files dirtied during the run and silently destroys other lanes'
   work. One suite run, serially, from the orchestrator, after all lanes land.
2. **The nightly box pipeline runs ~00:30-04:00 local** and regenerates data artifacts
   (observed live: tj_surgery.json restamped mid-session by a non-session python
   process). Do not run regens or commit data churn in that window; always commit
   explicit paths, never `git add -A`.
3. **A new `data/*_eval*.json` without a registry row turns the suite red.** Loss rows:
   `verdict: deprecated` (legal WITH an artifact) + a `MODEL_GLOSSARY` entry
   (`"internal"` for ledgers, `["xfv"]` for live eFV scoring behaviour). `unvalidated`
   REQUIRES `eval_artifact: null` with the artifact cited in `notes`. Regenerate
   MODEL_REGISTRY.md via `python tools/gen_audit_docs.py` in the same commit.
4. **Any change to the board ORDERING must bump `storage.BOARD_RANK_BASIS_EPOCH`,
   restamp `storage.BOARD_BASIS_FINGERPRINT`, and update `PINNED_MIX` in
   `test_board_basis_coherence.py` in the same commit** - the pins exist precisely so
   this plan's grade-scale flip cannot ship silently.
5. **Read `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` before Phase 1** - especially the
   five-way FV-to-WAR comparison, the Quantity A vs Quantity B section, and the 30 open
   questions. Do not re-fetch the articles; the extraction is verbatim and complete.

## The two measured facts this plan is built on

**FACT 1 (docs/efv-2026-07-30/CROSS_SIDE_WAR_FINDING.md):** consensus FV is not
cross-side comparable. At consensus FV 55+ hitters realized 11.653 first-6yr bWAR against
pitchers' 5.270 (2.21x, n=75/53); the ratio INVERTS below FV45 (0.76-0.85). The industry's
own role ladders imply different WAR per grade per side; consensus flattens it.

**FACT 2 (measured in-session):** our served grade map `value_framework.
realized_implied_fv` is (a) EXPECTED-frame - FV80 implies 20.4 WAR over 6 years, 3.4/yr,
the bust-inclusive Quantity B - and (b) SIDE-NEUTRAL to within 0.12 FV across the whole
WAR range. Demanding equal WAR for equal grade caps pitchers structurally: caden_hunter's
3.54 predicted WAR6 reads 48.6 on the neutral map and ~50-51 against the empirical
pitcher outcome curve. This - beneath the board-basis question settled on 07-30 - is the
deep cause of the 8-pitchers-per-100 top 100.

**The design consequence:** the owner's two asks are ONE mechanism. "Grade by
outcome-expectation" and "grade the sides on different scales" are both delivered by
replacing the side-neutral WAR-to-FV inversion with per-side (and eventually
per-position-group) OUTCOME CURVES: eFV grade G means "the industry FV whose
side-specific realized outcome distribution matches our prediction for this player."

---

## Phase 1: the outcome-scale foundation (per-side FV-to-outcome curves)

**Goal:** replace the single `fv_to_6yr_avg_war` inversion inside `realized_implied_fv`
(`value_framework.py:2750`) with per-side empirical outcome curves, fit from our resolved
cohorts, with the industry tables as PRIORS.

1.1 **Build the curve dataset.** Pool: the resolved uncensored rows behind FACT 1
(`data/xfv_scored.json` + `data/xfv_scored_pitcher.json` joins to consensus FV and
realized first-6yr bWAR; ~1,500 per side). Fit, per side: E[WAR6 | consensus FV] as a
monotone curve (isotonic or constrained spline), with player-clustered bootstrap CI
bands, plus the same for P(bust), P(star), and the outcome-bucket distribution. This
generalizes the sub-45 empirical anchors (which did exactly this for FV20-40 and beat
the published constant 2.2-10x) to the whole grade range, per side.
   - Censoring: use the same KM/censored-target conventions as the eval harness
     (`target_censored`); do not silently drop censored rows without reporting the
     sensitivity.
   - Vintage discipline: consensus FV as-of the pre-debut anchor (the disagreements-table
     lesson: never a post-debut re-read).
1.2 **The bake-off (owner directive: test the tables).** Score, on held-out folds of the
same pool, every candidate FV-to-outcome mapping as a predictor of realized WAR6:
   - McDaniel 2014 (7.0 at 80, per-season true-talent, converted honestly to 6yr),
   - the modern primer bands (avg annual x 6),
   - Clemens 2026 totals (the B-side table),
   - our shipped `fv_to_6yr_avg_war` (with the 07-29 sub-45 empirical anchors),
   - our shipped `fv_to_prime_war` (converted via the aging machinery),
   - the NEW per-side empirical curves from 1.1.
   Metrics: calibration slope/bias of realized on implied (per side, per FV band),
   MAE, and CI coverage. Report a full table. EXPECTED RESULT: the per-side empirical
   curves win on calibration by construction ON THE FIT POOL - which is why the scoring
   must be HELD-OUT (forward-chained by decision year) and why the industry tables serve
   as shrinkage priors for thin cells (FV 65+ has n in the tens; blend toward the prior
   there and SAY SO in the artifact).
1.3 **Deliverables:** `tools/fv_outcome_curves_lab.py`, `data/fv_outcome_curves.json`
(the fitted curves + CIs + the bake-off table), a registry row, and a new section in
`docs/efv-2026-07-30/` pre-registering the whole thing BEFORE the first fit. The curves
artifact is the single source of truth every later phase reads.

## Phase 2: the eFV grade re-scale (the ship)

**Goal:** `xfv_grade` = per-side outcome-calibrated industry-scale FV.

2.1 **Mechanism.** In `efv_score`, grade = inverse of the Phase-1 per-side curve applied
to the model's predicted WAR6 (`xfv_war_6yr`), replacing the `realized_implied_fv`
side-neutral inversion at `efv_score.py:1478`. Keep the low-end concave re-spread
behaviour (FV 20-45 display granularity) unless the Phase-1 curves make it moot; decide
and document.
2.2 **What CANNOT move and why this is shippable:** within a side the new map is monotone
in predicted WAR, so within-side ordering, the per-side quantile display map, and
therefore SURPLUS PRICING are byte-identical (surplus prices off the per-side rank
quantile; verified seam). What moves: the grade VALUE (industry-comparable now) and the
CROSS-SIDE interleaving of the board (pitchers rise to where the pitcher outcome curve
says their predicted WAR belongs). Verify byte-identical surplus in the ship commit.
2.3 **Gate design - learn from efv_board_scale's failure.** Its gap@55 statistic was
unstable (five time splits spanning +1.34 to -8.82) because it read a single top-band
point. Gate the re-scale instead on:
   - per-side OOS calibration curves (realized on implied), full grade range,
     forward-chained: the new scale must dominate the old on slope/bias per side
     (the old pit arm: Defect A slope 0.587);
   - cross-side interleave quality on the joint resolved board: rank-order of realized
     WAR6 across the MERGED top-N under old vs new interleaving (this is a real
     cross-side accuracy claim the within-side Spearman cannot see);
   - the composition tripwire: report (do not target) the resulting top-100 side mix.
     Phase A's finding stands: a higher pitcher share is NOT automatically better.
2.4 **Ship mechanics (coordinated, one commit each):** bump BOARD_RANK_BASIS_EPOCH,
restamp BOARD_BASIS_FINGERPRINT (extend it to name the outcome-curve version), update
PINNED_MIX, re-freeze `config/valuation_sets/prospx_current.yaml` if any surplus tier
literal moves (it should not - verify), golden restamp owed on next box regen, and the
movement-engine suppression below (Phase 3). Owner sign-off REQUIRED before the flip:
this changes every displayed grade's meaning from "expected-WAR-equivalent FV" to
"industry-scale FV per side" - that is the point, but it is a semantics change the site
copy must follow (glossary `xfv` entry, methodology page, tooltips).
2.5 **Positions within side (Phase 2b, gated separately):** the FG framework makes FV
position-conditional (catcher/SS vs 1B; SP vs RP role ladders). After the side split
ships, fit position-group curves where n supports them (C, MI, CF, corner; SP, RP) with
the side curve as prior. The C6 reliever-bridge inversion and the position-blind
monotonicity test are the cautionary precedents: every curve position-parametrized,
every gate run per group.

## Phase 3: display semantics + history coherence (carry-over A2, coordinated here)

3.1 **Two scales, both shown, labeled.** The grade is the industry-scale FV (Phase 2).
The player card shows BOTH quantities the industry conflates: "if he arrives" prime WAR
(`fv_to_prime_war` / Quantity A) and bust-inclusive expected WAR (Quantity B, the
model's xfv_war_6yr). The framework doc's A-vs-B section is the copy source. No
em-dashes; copy gates.
3.2 **A2, the third-basis repoint, DONE INSIDE THIS PROGRAM:** `efv_score.score_history`
builds the eFV history series on the retired quantile scale (1,504 of 1,568 players
disagree with the board; franklin_arias history 58.1 vs board 64.2). Since Phase 2
re-scales the board grade ANYWAY, repoint history to the board basis in the SAME
transition: one history restamp, one movement-suppression window, not two. The
strict-xfail in `test_board_basis_coherence.py` flips green and its marker must be
removed in the same commit. Movement engine: suppress/re-baseline the eFV-delta signal
across the epoch (the Seth Hernandez "down 33, confidence high" defect class).
3.3 **BA risk vocabulary (display-only candidate):** map our computed p_bust/outcome
buckets onto BA-style risk tier LABELS (Low/Mild/Average/High/Extreme) as an optional
chip. Adopt the labels, NEVER the flat 5-points-per-tier arithmetic (bust rates fall
non-linearly: 51% at FV45 vs 14% at 60 - framework doc Q26). Owner decision on whether
it ships visible.

## Phase 4: derived tool-grade tables (the audit nobody else has)

**Feasibility proven in-session:** 312 joined player-seasons of consensus tool grades x
savant-minors tracking; raw_pwr -> avg launch speed is monotone (30 -> 84.7 mph,
50 -> 86.9, 60 -> 88.7, 70 -> 90.0).

4.1 Build `tools/tool_grade_tables_lab.py`: for each tool with measurable ground truth -
raw power (EV percentiles, barrels), speed (sprint/run value), hit (contact/whiff/xBA),
pitcher velocity (FB velo by grade), arm where data exists - fit grade -> measurement
distributions (median + IQR per grade), AAA-context, with an explicit MLB-context
translation note. Compare against: FG's published bands, BA's (velocity +2mph, power
+4-6 HR drift - measured in the framework doc), and Pipeline (publishes NOTHING - our
table is the only audit that exists).
4.2 Deliverable: `data/tool_grade_tables.json` + registry row + a docs table. These feed
the explainer (Phase 6) and become a scout-grade QA instrument: flag source grades that
disagree with measurement by 2+ grades (a data-quality signal for consensus weighting,
NOT an automatic override - register any use as its own gated lane).
4.3 **Inventions welcome here (owner directive):** candidate original extensions, each
its own small pre-registered lane, shipped only on evidence: measurement-implied tool
grades as a THIRD opinion in consensus disagreement displays; per-tool aging curves from
our longitudinal grades; a "tool grade minus measurement" drift index per source.

## Phase 5: position + role assignment (owner ask 4)

5.1 **Hitters: observed position = most-played non-DH MiLB position** from
`data/positions_played.json` (2,675 players, g/gs per position, already built). Ship as
a NEW field (`position_observed`) alongside the FG forward-projection (which
`consensus._latest_meta` deliberately prefers today and which stays the scouting
projection field). Then flip consumers deliberately, one decision each: display primary
position, `realized_implied_fv(position=...)` (Phase 2b), positional scarcity in
valuation, archetype comps. Do NOT silently swap the semantics of the existing
`position` field - the FG projection is load-bearing in normalization (grade_norm is
role-aware).
5.2 **Pitchers: SP/RP by usage.** Generalize rule D (`role_usage.
usage_position_override`: GS-share >= 0.50, IP/G >= 3.0, IP >= 20, opener guard
validated in the Montgomery work) into the primary role source BOTH directions
(SP -> RP too), with the FG designation as fallback for no-usage rows. Blast radius to
measure before shipping: `_role_factor` (reliever ceiling), `_RP_DESIGNATIONS`
membership, PAL fit direction gates, and the Phase-2b RP curve population.
5.3 **BA ingestion audit (from the framework extraction):** BA's headline grade carries
risk SEPARATELY; the FG-comparable field is BA's ADJUSTED grade (printed only since
2026), and BA reset its baseline in 2026 with no crosswalk. Audit what our scraper
ingests per source (Luis Hernandez's row showed BA rank-only, no FV - verify globally).
If we ingest BA headline grades anywhere, they are +1 tier hot at the median vs FV and
must be normalized against the adjusted scale or the 2026-era map.

## Phase 6: the capstone explainer artifact (owner ask 5)

Built LAST, from the derived tables, because an explainer written first would document
the tables this program replaces. One published artifact (claude.ai Artifact, private
until owner shares): "eFV grades and tool grades - what our numbers mean."
Contents: our per-side FV -> outcome tables with CIs (Phase 1), the role ladders in our
own words anchored to our measured outcomes, the two-quantities distinction (prime vs
expected) shown side by side, our derived tool-grade measurement tables (Phase 4), the
continuous-scale rationale (why 51.3 exists), bust/risk semantics (and the BA-label
mapping if shipped), and a lineage section crediting the industry framework as
structural basis with our measured departures from it. Every number traceable to a
committed artifact. House copy rules apply INSIDE the artifact too (no em-dashes, no
LLM filler, grades round per the display rules).

## Phase 7: carry-overs from the 07-29/07-30 program (do not lose)

- **Phase D (wRC+ display program)** and **Phase H (FA display enrichment)** from
  `docs/master-plan-2026-07-29-efv-fa.md` - unchanged, still owed.
- **Owner decision queue standing:** D2 age-onset dial (table shipped; 24.0 vs 25.0 is
  the real choice), B1b full-season IL factor (recommend 0.70), FA verdict per-group
  bands (`VERDICT_BAND_MODE`, moves 19.7% of historical verdicts), WAR-rate shrink
  override (owner_call OPEN), FA fits concentration-vs-MRR tradeoff, `rate_line` OFF as
  a per-side bias fix (needs pre-registration).
- **Per-side age-for-level norms**: gate verdict lands with the running agent; its
  result slots into Phase 2b (the norms and the outcome curves are the same
  side-conditioning idea at two different layers). If it shipped default-off, the
  Phase 2b executor decides jointly.
- Pre-existing reds (goldens, C5 inert anchor, calibration version tripwire,
  michael_oliveto) stand as documented; the golden restamp remains owed on the next box
  production regen and Phase 2.4 adds one more reason to do it once, not twice.

## Sequencing and effort

1 -> 2 -> 3 are strictly ordered (curves, then scale, then display/history) and are the
heart of the program. 4 and 5 are parallel lanes that can run beside 1-2 (5.3 the BA
audit is cheap and should go first within its lane). 6 is last by definition. 7 rides
along. Suggested lane split for Opus: LANE-CURVES (1+2), LANE-TOOLS (4), LANE-POS (5),
orchestrator holds 3, 6, 7, the suite, and every commit. No lane runs pytest; the
orchestrator runs the suite serially after each merge point. Every lane pre-registers
its gates in `docs/efv-2026-07-30/` before measuring, every artifact gets its registry
row in the same commit, and every null is reported as a null - the program's stated goal
is the most ACCURATE grades, and the last two sessions proved the nulls are where the
accuracy lives.

# Master plan 2026-08-07: omnibus-3

Written for the executing session (Claude Opus 5). Planning session ran a 14-lane
read-only recon (~2.0M tokens, 770 tool calls, every claim below carries file:line
evidence from it) plus four AskUserQuestion rounds. All 14 owner decisions are LOCKED
and recorded in section 1; do not re-ask them. Where a lane says "gate", it means the
full docs/EFV_GATE_STANDARD.md battery unless the lane narrows it.

## 0. How to use this document

1. Read section 2 (standing rules) and section 3 (memory corrections) before any lane.
2. Lane 0 runs first, in the first hour. After that, lanes are largely independent;
   the suggested order is A, B, D, F, M (eFV integrity and owner-visible bugs), then
   E, C, N (gated model work), then G, H, I, J, K, L (modules and polish).
3. VERIFY EVERY PREMISE BEFORE WORKING IT. The omnibus-2 plan had 4 of 5 checked
   premises turn out false. This plan's evidence is from 2026-08-07 recon and is
   cited per item, but the nightly box rewrites data/ between 00:30-04:00 local and
   artifacts drift. If a number does not reproduce, stop and re-diagnose.
4. Every model-affecting change needs: a pre-registered gate doc, a registry row +
   eval artifact (verdict enum: validated/provisional/unvalidated/deprecated; a
   measured no-ship is `deprecated`, never `rejected`), a MODEL_GLOSSARY entry, and
   a fingerprint/epoch bump when it re-ranks anything (a fingerprint only guards
   what it NAMES; three prior incidents).
5. Losses are committed with artifacts. Marginal = FAIL. One attempt per registered
   experiment.

## 1. Owner decisions, LOCKED 2026-08-07

1. EVAL BASIS: 11-fold pair-weighted is the published headline everywhere; legacy
   4-fold shown as a labeled, dated footnote. Diamond scoreboard regenerates onto the
   new basis. Re-derive MDE95 under the new protocol first.
2. 20.0 FLOOR: serve the spread provisional grade for the ~2,636 fv_synthetic_only
   constant-cohort players (make the routing partition real on the board) PLUS an
   order-preserving sub-decimal sort key from unrounded model WAR for residual floor
   rows. Verify and kill the suspected double-listing.
3. STALE ANCHOR: build the mover table, then flip STALE_ANCHOR_DATE_BASIS
   'point' -> 'source' with fingerprint/epoch bump and test pin in the same commit.
4. DRIVERS: run ALL FOUR programs: C3 re-tests (sb_rate_rel + positions_played),
   handedness build + gate, gated-pair sweep + elite-band probe + lambda re-sweep,
   and ONE wRC+ re-run (the owner's ask is the ledger's re-open instruction; one
   attempt, marginal = FAIL).
5. STATCAST+: shrink first (EB shrink + volume gates, the reverted C1 build), THEN
   the true 10-per-sigma re-standardization as a second gated ship with every
   consumer threshold mapped through the transform (populations preserved) and the
   eFV tilt slope preserved at ship.
6. PINAZZI / EXPLAINER: skip the pit age_rel_level chip (display-only) AND fix the
   renderer (numeric magnitudes, bar saturation, biggest-first ordering). Model
   untouched; no constrained fit this program.
7. BETTING LONGSHOT: honest empty state at the shared 0.06 policy floor. POTD = max
   model win probability among floor-clearing sides in [-199, +199], tiebreak price
   nearest -110 then EV. Flat units (1u POTD, 0.5u longshot) with quarter-Kelly as
   an informational chip. All three markets POTD-eligible with a caveat chip on
   runline/total picks.
8. ARIAS: COMMISSION the attribution replay lab (name the features behind the 08-04
   -0.13 WAR move). No served change expected; narrative deliverable.
9. CARD PRICES: owner's answer verbatim: "See if there's any other source we can
   scrape from." Run the source survey in H2. Regardless of outcome: disarm the
   eBay fetcher and ship the fetch_blocked ingest RED.
10. FANTASY: FULL MERGE into one /fantasy/ module (lazy sub-mounts, namespaced
    hashes, redirect stubs) plus the fantasy player-card overlay.
11. REDRAFT SCORING: keep all four formats, SCOPED to the three ROS tabs they
    affect, with the FGP/SABR hitter-identity note.
12. LOGO: PixelMplus12 at real bold 700 everywhere the logo font renders, including
    canvas GFX exports and regenerated social/share art; DotGothic16 fully retired.
13. PROJ/FA CARDS: condense to a 96px floor (chrome-only removal, clip invariant
    preserved, stress-test gated).
14. PROSPX BOARD CARD: keep the v43 uniform 136px height and ADD the missing clip
    guards so overgrown cells truncate cleanly instead of bleeding.

Defaults set by the planning session (recommendations the owner did not override,
recorded here so the executor does not re-ask): provisional single-season prospects
get a single-dot chart; graded single-snapshot players keep the text fallback; the
compare overlay chart stays on its 20-80 frame; farm board auto-switches to cards
view under ~1300px unless the user pinned table mode; PAL sp2rp tier cuts become
per-direction (~55/45/35), tier chips colored by TIER; shadow ledger MAX_PER_SLATE
3 -> 5 with slot tags; the 6 dirty data files from 08-07 are discarded (measured
content-neutral); elite-band probe fallback on null is a display-side conviction
annotation, not a model overlay.

## 2. Standing rules and environment (violations have burned sessions)

- Run pytest ONLY from prospect-tracker/. NEVER edit source while it runs
  (conftest git-restores dirtied tracked files by git state, not authorship).
- efv_ungraded.py has NO argparse: ANY invocation, including --help, rebuilds and
  writes artifacts.
- The nightly box pipeline runs ~00:30-04:00 local and rewrites data/ under you.
  Check `git status prospect-tracker/data/` and artifact mtimes before diagnosing
  any red. Do not run regens or commit data churn in that window.
- The deploy box is a single writer; nightly runs `git checkout -- .`. Commit and
  push; never leave the tree dirty. Push needs `http.sslBackend schannel`.
- Explicit paths on every `git add`. Pathless `git add -u` swept 55 files into an
  unrelated commit once.
- No em-dash in any copy, comment, or doc (owner rule, lint-gated). Grades: scouting
  FV displays CEILING; eFV and the +stat family round NEAREST.
- Color: tokens only (var(--accent-*), var(--text-*)); test_no_hardcoded_colors caps
  hex in the prospx style block.
- Identity fixes use alias maps (PLAYER_KEY_ALIASES, fa_ident seam), NEVER a DB remap.
- NEVER sum ML quantile points. Never present sub-45 eFV grades as outcome-calibrated.
- Ledger numbers dated before 2026-08-06 are on the retired 4-fold eval basis and no
  longer reproduce; never compare a new 11-fold result to a pre-promotion figure.
- source_backtest.json is gitignored and overwritten nightly. Capture the current
  copy BEFORE any regen if the pre-regen value matters (the legacy-basis number is
  otherwise unrecoverable; this already happened once).
- Banned-experiment ledger: docs/master-plan-2026-08-05-omnibus2.md plus the lane C
  list in this doc. Key entries that touch this program: RP->SP event-set expansion;
  monotone tail fixes; peak-WAR target; lambda cap raise (pins move only via a sweep
  clearing the re-derived MDE95, rule written at efv_model.py:480-483); per-cohort
  lambda; platoon-split production features (handedness IDENTITY is untested and
  allowed); power/ISO hitter features; K-prior; statcast-into-projections;
  re-pointing efv_ungraded._grade onto the outcome map; quantile board basis;
  blanket pitcher penalties; hard display clamps.

## 3. Memory corrections established by this recon (do not re-fix, do not re-open)

- Betting park leak F1.1 is FIXED (leaderboard_vintages SCHEMA=2 carries parks;
  betting_model.py:469-575, 1650-1658, shipped dc8c8f1). The omnibus-2 memory line
  "CONFIRMED still open" is stale.
- CLV grading is WIRED in code (betting_export.py:292-370, close job
  tools/betting_close_job.py:336-352). Only the box crontab installation is
  unverified (N4).
- Golden fingerprint restamp is DONE (live canonical sha 5430ea7b == pin at
  test_efv_export.py:501). The pin is on the volatile-stripped CANONICAL form, not
  raw file bytes.
- The /pal/ meta description is FIXED (build_site.py:3701-3722, corrected
  2026-08-05). Do not touch.
- Card-ingest scheduling is WIRED (steps 6g-pre/9f, commit 54474aa). The 2026-08
  root cause is the fetch layer (eBay 403), not scheduling.
- test_efv_stale_anchor_basis.py is IMPLEMENTED and running (since 2026-08-06), not
  skipped. Lane C's stale-anchor CODE exists; only the basis flip is open.
- efv_ungraded.UNCAPPED_GRADE is False (restored 2026-07-25), not True.
- Doubleheader odds collapse is FIXED (betting_export.py:742-762).
- The chart functions are makeProvisionalEfvChart / getEfvHistory (not *Xfv*).
- Board ordering field is xfv_grade (storage.py:4838); xfv_grade == xfv_grade_realized
  on all 9,382 rows today, and ordering on realized/quantile is code-forbidden
  (prospx/index.html:32401-32404).

## Lane 0: protective actions (first hour)

0.1 DONE AT PLANNING TIME: the 55-finding Diamond QA record was copied out of OS
    temp space into docs/diamond-qa-2026-08-05/ (qa_0/1/2.txt + INDEX.md). Verify it
    is committed.
0.2 Discard the 6 dirty data files (draft_bonus_slot_report, efv_alerts, fa_meta,
    mlb_current_lines, pipeline_vintages, tj_surgery): measured content-neutral
    (5 are generated_at-only; fa_meta's war_input_divergence regenerates from
    current code). `git checkout --` them with explicit paths. Gate: git status
    clean under data/.
0.3 Disarm the card scraper: prospect-tracker/.env:22 EEPHUS_CARD_SCRAPE -> 0 (and
    /etc/eephus.env on the box if set). It fires 22 doomed 403 requests nightly.
    Re-arm only when H2 lands a fetchable source.

## Lane A: eFV eval integrity (the Spearman answer, made visible)

Root cause recap (MEASURED): the .390 -> .351 drop is protocol arithmetic from the
owner's own 2026-08-06 promotion (SCORED_YEARS 4-fold -> 11-fold at efv_model.py:81,
pair-weighted headline at prospect_path.py:366-396). oos_grades trains each fold on
all rows with decision_year < yr (efv_model.py:757-758), so old grades are
bit-identical; the pool simply added ~1,000 rows from thin 2014-2019 folds and the
censored 2024 fold (n 2200 -> 3210). The 4-fold numbers REPRODUCE on fresh matrices
(hit .3882/.3521). The flagship hit rho went UP under weighting (.3993). The owner
sees .351 at data/source_backtest.json accuracy.pooled.xfv.spearman, rendered at
assets/glossary.js:650, 753-760, 1674-1679; AUC .7328 at glossary.js:651. Diamond
(assets/diamond.js:32) still prints the legacy-basis 0.384/0.7572 from the frozen
data/xfv_scoreboard_eval.json (2026-07-30): two pages disagree today.

A1. Re-derive XFV_VS_CONSENSUS_MDE95 under the 11-fold pair-weighted protocol.
    Paired bootstrap B=2000 seeded, resampling train AND test, per side and pooled.
    Replace the stale 0.045 at source_backtest.py:373; add the 11-fold row to
    docs/EFV_GATE_STANDARD.md section 1. Re-adjudicate the published resolvability
    verdicts (current deltas: hit +0.0074 / pit +0.0067 weighted, +0.0113/+0.0108
    unweighted; the plan-estimated new floor is ~0.012, so the unweighted deltas may
    genuinely resolve). Also implement the sanctioned block-rho instrument
    (EFV_GATE_STANDARD.md:49-50, MDE95 0.0149) beside the headline. Gate: published
    mde95 equals the fresh measurement; verdict strings regenerate on both glossary
    render paths.
A2. Kill the two stale beats-consensus claims: (a) the HARDCODED honest_note at
    efv_model.py:2193-2198 still claims eFV "BEATS consensus on out-of-sample rank"
    while the same artifact says rank_win=false; make it derive from the verdict.
    (b) glossary.js:657 asserts a head-to-head win from a bare 0.3511-vs-0.2846
    inequality with no MDE; MEASURE the common-set gap's own MDE (it is +0.0665,
    roughly 6x the flagship delta, and probably clears) and keep the claim only if
    it does. Gate: no served claim whose backing delta lacks an MDE beside it.
A3. Resolve the mixed-basis split: regenerate data/xfv_scoreboard_eval.json under
    the new protocol (tools/efv_scoreboard.py imports XM.SCORED_YEARS, so a re-run
    lands on 11-fold automatically), and stamp BOTH surfaces (diamond.js, glossary)
    with basis + generated_at. Add the legacy 4-fold value as the dated footnote per
    owner decision 1. CAPTURE the current gitignored source_backtest.json and the
    legacy scoreboard values into the ledger BEFORE regenerating (they are otherwise
    unrecoverable).
A4. Headline surface honesty: where the site narrates eFV skill, prefer the
    era-split framing the data supports (edge concentrates in recent cohorts:
    2022-23 hit +0.032, pit +0.077) alongside the pooled number. Optional deliverable
    (report, not ship): the 2x2 protocol table (chain start 2014 vs 2017 x 2024-fold
    weight 0 vs 0.333) so the owner sees what each dial buys; no served basis change
    without a separate decision.
A5. Optional: C6 leak-lab (per-fold RESOLVED_THROUGH censoring, omnibus-2 plan
    :465-469) to size the one optimism-shaped caveat on the eval.

## Lane B: eFV board repair (20.0 floor, stale anchor, double-listing)

Evidence: value_framework.py:2983-2984 maps every war <= 0 to exactly 20.0;
fv_outcome_curves_pooled.json spans only 0.069 WAR across FV20-35 and its own schema
note says the sub-35 knots are NOT a measurement. 4,533 of 9,382 rows serve exactly
20.0 (3,358 actives, 73.2%); the open interval (20,30) holds 32 active rows. 2,636
player_keys exist in BOTH xfv.json actives (flagship 20.0, consensus exactly the
fabricated 35.0) AND xfv_ungraded.json (spread grades, median 27.4). fvCmpDesc's own
comment (prospx/index.html:11441-11443) says ~3.1k of ~4.5k board rows sit on the
floor and order by the +/TBS/name chain.

B1. Measure the double-listing at runtime FIRST: load the board, count duplicate
    player_keys in the joined pool (DATA.players + provPlayers(), concat at
    prospx:15550/32431, no visible dedupe; synthesis at prospx:31384-31401). If
    confirmed, dedupe with the provisional row winning exactly when rosters stamp
    fv_synthetic_only (routing seam efv_ungraded.flagship_owns,
    efv_ungraded.py:599-647). Gate: duplicate count 0; board row count change equals
    the measured duplicate count.
B2. Serve the provisional grade for the constant cohort (owner decision 2): the
    2,636 fv_synthetic_only players stop serving the flagship 20.0 and serve their
    provisional grade on the board. This makes the 2026-08-05 routing partition real.
    Add a sub-decimal SORT KEY derived from unrounded model WAR for the residual
    genuinely-graded floor rows (order-preserving; display unchanged; the 20.0
    display stays for true org filler). DISCLOSURE: the flagship and provisional
    WAR->FV maps disagree +7 to +12 FV through 0.5-3.5 WAR and invert at war <= 0
    (efv_ungraded.py:107-115 vs the outcome curve); serving both on one board needs
    the two-scale disclosure shipped with this change. Do NOT re-point
    efv_ungraded._grade onto the outcome map (recorded no-ship, 3 of 6 stop
    conditions). Fingerprint gains a term naming the provisional-serve change AND the
    provisional scale (a registered gap: BOARD_BASIS_FINGERPRINT does not name it
    today). Gate: before/after tie-count at the floor; Spearman of served 20-30
    ordering vs the provisional model's own WAR ordering on the cohort; zero
    movement above FV30; suite green.
B3. Stale-anchor flip (owner decision 3): build the mover table the tests say the
    flip owes (per-row deltas under 'source' basis; expected ~182 decayed rows at
    +12mo, ~2,691 at +24mo on a frozen board; top-N membership changes), then flip
    STALE_ANCHOR_DATE_BASIS at efv_dataset.py:110-128 with the epoch bump and the
    test_efv_stale_anchor_basis default-pin update in the SAME commit. The 3-tier
    anchor-date precedence (real-FV > folded constant > rank-only) already protects
    real grades from fabricated stamps. Note the stale-anchor constants are
    test-pinned to data/xfv_stale_anchor_eval.json; restamp it with any ramp change.
    Gate: flip changes only rows whose real anchor is >18mo old; mover table artifact
    + registry row committed.
B4. Explainer chip coherence rides Lane D; the "Stale list coverage" chip currently
    reads as the cause of a 20.0 that 3,101 chip-free actives also print. After B2
    the chip should only appear where the discount actually moved the grade.

## Lane C: eFV driver program (all four arms, owner decision 4)

Protocol for every arm: 11-fold pair-weighted basis, freshly re-derived floors (A1
first), zero-information control, permutation null, paired bootstrap B=2000, >= 4
time splits, block-rho for side-agnostic candidates, full-pool debut AUC INADMISSIBLE
for any candidate that can sense a missing MiLB block (EFV_GATE_STANDARD.md:55-78).
Losses committed. Budget order as listed.

C1. C3 re-tests (pre-authorized, cheapest): (a) sb_rate_rel named into _FEATURES_HIT
    (column already emitted at efv_dataset.py:494, present 1,134/1,134 train); (b)
    positions_played census rebuild WITHOUT the pre-debut filter (the only blocker
    on POS_PREMIUM_USES_OBSERVED, efv_model.py:759-797), then re-gate it. Spec at
    docs/master-plan-2026-08-05-omnibus2.md:436-449.
C2. Handedness (the one never-tested candidate): build a cached sidecar joining
    batSide/pitchHand onto every matrix row with an mlbam_id (StatsAPI people batch;
    patterns at hitter_export.py:640-669, pal_export.py:181-185; FG _extras as
    cross-check; optional bust-coverage lift from data/sources/mlbam_id_overrides*.json).
    Gate pit is_lhp first, hit bats-side second (owner default (a) then (b)). Neutral
    imputation, NO missing indicator, and pre-register the stop clause: if the
    indicator's information reduces to id-missingness, the arm FAILS (id coverage is
    62.1% hit / 54.0% pit train vs 99.6% live, and missingness correlates with bust
    status). Platoon-split PRODUCTION features stay banned (W-PLATOON FAIL);
    handedness identity only.
C3. Gated-pair sweep: 3-5 pre-registered threshold interactions via lab_runner's
    thr()/expr mechanism (tools/efv_lab_runner.py:38-40, 115-124), e.g.
    thr(tool_game_pwr,60)*(-k_rel_excess), thr(tool_hit,60)*obp_rel, pit
    thr(tool_fb,60)*k_rel. MANDATORY live-robustness clause from the col_x_k lesson
    (efv_model.py:351-358): score the live matrix with each candidate and bound the
    max served-grade move; sparse 0/1-gated columns hand thin-sample players extreme
    boosts when standardized. Joint coverage measured: 1,096/1,917 train rows have
    power tool AND k_rel; 387 carry power >= 60.
C4. Elite-band conviction probe (Witt/Julio ask): two arms, both pre-registered as
    probably unresolvable (FV>=55 = 105 hit rows / 59 pit, uncensored 75/53): (a)
    lambda band RAISE restricted to FV>=55 (lab_runner lam band with negative dip);
    (b) elite-cohort-restricted eval (add fv_min filter, ~10 lines) of the strongest
    candidates. Do NOT re-attempt monotone tail transforms (all committed losses;
    Spearman-invariant; tail-lab protocol recoverable via
    `git show 8fecb2f~1:tools/efv_tail_lab.py`). On null (expected): the deliverable
    degrades to a display-side "elite conviction" annotation driven by
    xfv_minus_consensus (default locked). Known context: the top tier is
    OVER-predicted in level (bias +2.7/+2.5 WAR) and the real gap is WITHIN-elite
    discrimination (realized spread ~2x predicted).
C5. Lambda re-sweep (conviction vs consensus): one sweep per side under the new
    protocol with a fresh lambda-shift MDE95 (old floors 0.0076-0.011 hit /
    0.005-0.008 pit at n 353/438; n is now 755/890, the one gate class the promotion
    made MORE resolvable). Pins {hit 0.70, pit 0.57} at efv_model.py:483 move ONLY on
    a floor-clearing win; quote the churn cost beside any proposed move (the
    0.85 -> 0.70 precedent). Do not re-run cohort-lambda variants (both NO SHIP).
C6. wRC+ re-run (owner re-opened): one 11-fold re-run of the A2 add-arm ONLY via the
    frozen tools/efv_wrc_lab.py protocol. One attempt, marginal = FAIL. Do not build
    the park layer (W2 M-FAIL stands, wrc_rates.py:23).
C7. Record as closed in the plan ledger, do not build: POW+/HIT+/PD+/ISO+ as
    training drivers (frontend-only composites; trainable parts already adjudicated;
    Statcast parts have no history), SC+ components as training features (no
    pre-2023 history; the live overlay already carries whiff/velo at component level;
    the component reweight is queued to season close per docs/archive/REVIEW_QUEUE.md item 12
    item 12 and its pre-set trigger).

## Lane D: driver explainer display (Pinazzi + magnitude scaling)

Evidence: contributions ARE continuous end-to-end (efv_score.py:556-582 w*(x-mu)/sd;
150 distinct mags 0.01-5.0 in xfv.json); the renderer discards it
(prospx/index.html:32938-32946: binary arrow + bar saturating at mag 1.6 with an 8%
floor, number never shown, overlay chips insert(0)-prepended so "biggest first" is
false). Pinazzi (xfv_grade 42.6, consensus 35, age 26.8 at A+, age_rel_level capped
+3.5 from true +5.7): his positive "Age for level" chip is the inverted pit
age_rel_level suppressor coefficient (+0.0418 fitted, declared 0 on 2026-07-30)
honestly rendered; 1,221 of 1,559 live pitcher cards read UP on it; his age is in
fact heavily penalized by the overlays (age ramp 1.5 DOWN + reliever 1.8 DOWN, net
0.525x on the model leg).

D1. Add "age_rel_level" to _EXPLAINER_SKIP_SIDE["pit"] (efv_score.py:553) with the
    standard adjudication comment; the exact precedent as the pit/hit "age" skips.
    The HITTER chip stays (its -0.2159 agrees with intuition; 0 of 576 old hitters
    read UP). Display-only. Gate: before/after diff of xfv.json touches ONLY factors
    arrays; zero pitcher entries carry an Age-for-level UP chip with age_rel_level>0;
    every grade/rank/surplus byte-identical; suite green.
D2. Renderer fix (efvDetailCard, prospx:32935-32947): print the mag as monospace
    text beside each bar; rescale the bar (per-card max or log above the 1.6 knee)
    so 1.8 and 5.0 differ; sort ALL chips by mag at render time so the "biggest
    first" header is true. Gate: headless render of Pinazzi's card shows six
    distinguishable, correctly ordered chips (1.8 > 1.5 > 0.98 > 0.56 > 0.15 > 0.04).
D3. Sign-audit hygiene: re-run efv_sign_audit on current matrices (ledger is
    2026-07-25 vintage and contradicts shipped code); implement SIGN_AUDIT_PATCHES
    follow-up 1 (emit served_ridge_std_weights beside the debuted-only diagnostics
    so nobody reads the wrong table as the served model) and follow-up 3 (stability
    columns: fold-sign agreement + production-only refit sign) so the next rebuild
    that flips pit peak_k_rel (+0.1787 served, -0.1322 production-only) or x_era_k
    is caught by the guard, not an owner bug report. Register both ledgers.
D4. The "Stale list coverage" chip: after B2, verify it renders only where the
    discount moved the grade (today 257 of 278 chip rows grade 20.0 for reasons the
    chip did not cause).

## Lane E: Statcast+ recalibration (owner decision 5: shrink, then rescale)

Evidence: statcast_plus.py:49-54 (nominal 10/sigma), measured served sd 6.19 (one
point = ~1/6.2 sigma); site max 130 = Harrison Kreiling, 87 pitches, no batted-ball
or velo data, currently firing the eta -0.5y elite nudge and the stat-only breakout
gate; Kenni Gomez 128 = 1 batted ball. Real best full-sample profiles sit 115-120.
Reverted C1 fix recorded at docs/efv-2026-07-29/GATED_CANDIDATES.md:14-44.

E1. Pre-register ONE gate doc covering both ships: floors 0.017/0.016, zero-info
    control, bounded board-movement battery, and the ~295 gate-band crossings report
    (eta nudges, breakout gates, TBS band). Registry row update + eval artifact.
E2. Ship C1 (shrink) FIRST: EB shrink (n*value + K*prior)/(n+K) with contact floor
    10/K=50, zone floor 25/K=100, velo floor 10/K=50; fix the rows[0].keys()
    column-set defect and the sd>0 near-zero guard. Known blast radius: 2,887
    players' tilt, Spearman(old,new)=0.925 reorder. Gate: battery passes; served
    top-10 SC+ contains no player with <10 BBE or <100 pitches after the next export.
E3. Ship the 10-per-sigma re-standardization ATOMICALLY with every consumer:
    z-score the composite against the per-side composite-sd inside
    compute_statcast_plus AND identically in arkmetric_forward_eval.sc_analog_index
    (AAA override stays on the same scale). Same commit remaps: eta.py:544-549
    thresholds 130/115/85 -> transform-mapped equivalents; storage.py:637/643;
    statcast_plus.py:53-54 quintiles; spotlights.py tiers + the stale "sigma x 15"
    tooltip at :1715; prospx _tbsNorm(sc,80,130) at :11369 (weight 0.20 feeds
    _tbsSurplusMult :22577 = dollars, re-band atomically); chip label :11599; pill
    colors :34795; glossary copy via build_glossary_data.py. POPULATIONS preserved
    (a calibration fix must not 7x the elite-nudge population; measured drift if
    thresholds stayed numeric: >=115 goes 31 -> 210). eFV tilt slope divided by the
    rescale ratio so served tilt is unchanged at ship; the intent-sized tilt is a
    separate gated question. Gate: served sd 9.5-10.5 per side; max ~135-148 with
    every top-10 row on real volume; per-gate populations within +/-2 of pre-ship;
    _statcast_factor tilt distribution unchanged; efv_statcast_overlay output
    byte-identical (the overlay consumes raw component z's, not the composite, but
    verify anyway).
E4. Fix the free-standing stale copy now (spotlights.py:1715) regardless of E2/E3
    timing.

## Lane F: eFV charts

Evidence: FV_MIN/FV_MAX at prospx/index.html:12858; nothing chartable has ever
exceeded 65.0 (max eFV history point 61.4; the "Franco 73" memory is a card value on
a player absent from every chart series). Missing charts: 1,635 of 5,983 provisional
rows have xfv_history=None, ALL single-pro-season (structural, not a bug); 2,818
graded actives have <2 snapshots and no series (score_history skips them,
efv_score.py:1547).

F1. FV_MAX 75 -> 70 (prospx:12858, comment at 13070). Gate: detail chart ticks read
    35..70, top eFV point sits ~75% up the plot, sparkline top label 70, sub-35
    floor behavior intact.
F2. Add the defensive clamp makeProvisionalEfvChart already has (12916) to both
    other yScales (12966, 43112) so a future >70 point pins at the frame instead of
    drawing off-viewBox.
F3. Single-dot chart for the 1,635 single-season provisional prospects:
    frontend-only branch in the chartSection ladder (47446-47455) synthesizing the
    point from _xfv_entry.xfv_grade + career_stats[0].season; replace the misleading
    "Not enough FV updates yet" copy for provisional players with a one-pro-season
    note (no em-dash). No pipeline regen. Graded single-snapshot players keep the
    text fallback (self-heals on the next list ingest). Gate: a known 1-season DSL
    row renders the dot; 2+-season pages unchanged; no-chart provisional count
    ~1,635 -> ~0.
F4. Do not touch the strict xfail at test_board_basis_coherence.py:188-207 (tilt
    gap, kept deliberately; 399 tails >= 0.5 FV measured).

## Lane G: Betting two-tier picks + casual layer (owner decisions 7)

Constraints that bind everything: both slots provisionally labeled until the gates
open (first honest grade May/June 2027); resolve_min_edge() is the only floor
source; candidate enumeration MUST reuse board rows built through _consensus_point +
_best_price_on_line (betting_export.py:573, 609); never a second invented threshold;
flat 1u recorded stakes everywhere; no backfill, no 2026+2027 pooling; budget 500
credits/month.

G1. provisional_picks() in betting_export (replacing the 1537-1538 call):
    pick_of_the_day = max model_prob among floor-clearing sides in [-199,+199],
    tiebreak min |odds+110| then max EV (on the 2026-08-06 fixture this lands
    ATH +1.5 -136, p 0.696, edge +13.8%); longshot_of_the_day = max EV among
    floor-clearing sides >= +200 (fixture: WSN ML +304), honest empty state
    otherwise. Keep the pick_of_the_day payload key; add longshot_of_the_day +
    per-slot reason + suggested_units (1.0 / 0.5); pick_meta keeps its top-level
    shape and gains slot sub-blocks; ADD pick_meta to the preview slice
    (1642-1664, currently omitted). Runline/total POTD picks carry the Poisson
    underdispersion caveat chip.
G2. Extend the five-condition provisional guard (test_betting.py:532-578) to iterate
    EVERY published slot; pin band membership, floor identity (longshot never lowers
    it), and row identity-equality to team_bets (no re-pricing).
G3. Shadow ledger: slot tags on new rows ('potd_band'/'longshot'/'ev_rank'),
    MAX_PER_SLATE 3 -> 5 (two slot picks + top-3 EV) to accelerate the gate-3
    sample; append-only and flat stakes untouched; per-slot splits in
    betting_shadow.summary(). data/betting_shadow.json stays UNTRACKED.
G4. Client (assets/betting.js): two pick cards with PROVISIONAL badges (the payload
    flag currently never reaches the reader; grep 'provisional' in betting.js = 0
    matches), plain-English pick sentences built from served fields, unit line +
    quarter-Kelly info chip (kelly_full/4), honest empty state naming the floor,
    validation/model panels collapsed behind a details toggle. LEGAL block and
    21+/1-800-GAMBLER placement untouched; no affiliate links.
G5. Per-game "Best value" badges in gameCard (max-edge floor-clearing side per game,
    threshold from pick_meta so badge and pick floors can never disagree; ~half the
    games badge on the fixture slate; absence is information).
G6. Betting vocabulary into the glossary (build_glossary_data.py new 'betting'
    group: edge, vig/hold, de-vig, fair line, implied probability, EV per unit,
    unit, Kelly, moneyline, runline, total, parlay, CLV, provisional pick, policy
    floor, Brier) then wrap first-use terms in betting.js with the existing gl()
    spans (contract at betting.js:108-127).
G7. Runbook section in docs/diamond-betting.md: both slots, both selection rules,
    shared floor, slot tags, and the date the selection rule changed so the future
    min-edge sweep can condition on slot.

## Lane H: Diamond cards (owner decision 9: survey scrapeable sources)

Root cause recap: eBay 403-blocks the module UA AND a plain Chrome UA (1832-byte
block page, measured live); card_scrape_runs shows 22/22 fetch_errors both armed
nights; card_comps 0 rows; data/drops/ never existed; frontend verified fine and the
Bowman Auto buy screen (top-30 eFV Bowman Chrome Prospect Auto PSA 10, buy signal =
talent percentile - price percentile within tier, card_market_export.py:656-671)
is dark purely for lack of prices.

H1. fetch_blocked ingest RED: extend ingest_state() (card_market_export.py:426-444)
    to read fetch_errors; attempted>=N, fetched==0, errors==attempted classifies
    'fetch_blocked', added to INGEST_RED_STATES, with a fixture test. Two fully
    blocked nights currently read as the honest empty state with red:false, the
    exact silent-failure shape omnibus-2 spent a wave killing.
H2. Price-source survey (owner-directed): evaluate alternative sources for sold-comp
    or price-guide data for Bowman Chrome Prospect Autos. Candidates to check, in
    order: PSA Auction Prices Realized public pages; SportsCardsPro public price
    pages (they also sell a documented CSV guide, the licensed fallback);
    130point.com search; COMC/eBay-adjacent aggregators; Card Ladder (enterprise,
    likely out). Acceptance criteria for any source: (a) fetchable with an honest UA
    and the pinned 5s throttle, no bot-evasion or headless-browser circumvention of
    an explicit block (the module's stated ToS posture, docs/diamond-cards.md:18-43,
    treats the scraper as the deletable half; if a source requires evasion, it
    fails); (b) terms compatible with publishing ONLY the aggregate index (raw
    comps/prices/dates/titles are test-pinned unpublishable, test_card_market.py:217,
    258); (c) maps onto the existing drop contract or SEARCH_URL_TEMPLATE
    (card_prices_ingest.py:108-111) without schema change. Deliverable: a short
    source-survey doc + the chosen source wired and one successful priced run
    (n_priced > 0), or an honest "no compliant source; recommend manual drops or the
    SCP CSV purchase" verdict back to the owner. Re-arm the scraper only on success.
H3. Bowman ROI board polish once prices flow: verify the buy screen ranks by gap;
    add a $/talent-point or index_usd display column; parallels enter via set_desc
    naming (card_id stays player|set_desc|grade); the +/-20 bands stay labeled
    conventions until the pre-registered gate (n_priced>=30, two 90-day windows)
    runs.
H4. Cross-module QA leftovers sweep (from the rescued record, see
    docs/diamond-qa-2026-08-05/INDEX.md): clamp the GFX board sub-text
    (eephus-gfx.js:228, reuse the tile fitTxt), fix the METHOD prose fragments
    (card_market_export.py:500-528), gate-or-label per-card GFX on unpriced cards,
    add the screen banner to the Method tab, section-sub ellipsis at 390px,
    "Developers" nav clip at 768/1366. The My Bets mergeLocalBets orphan waits for
    the account-layer enablement (path inert without Supabase).
H5. DFS slate freshness check rides Lane I (I3).

## Lane I: Fantasy merge (owner decisions 10, 11)

Context the merge must honor: the three-page split shipped 2026-08-05 (ca6f394) with
a written rationale; the merge keeps the separation as lazy sub-modules so the
dynasty board is never again buried behind redraft tabs. Measured constraints:
all three clients fall back to the SAME #fantasy-app-root mount id (double-mount
hazard); each owns '#section=' with a hashchange listener that rewrites the URL
(router collision); payloads are 576KB + 253KB (lazy-boot); redirect precedent is
/teams/ -> /projections/#view=teams; test_fantasy_split.py shell tests must be
retargeted; assets/fantasy.js is the frozen pre-split parity reference, do NOT
resurrect or edit it.

I1. Redraft scoring scoped (owner decision 11): render the format bar only on
    ros_sp/ros_rp/ros_hitter (it currently sits on all 7 tabs including the landing
    tab where it affects nothing); one-line note on ROS Hitters that FGP and SABR
    share one hitter table by real Ottoneu rules. Gate: py_mini_racer harness
    asserts bar absent/disabled on the four non-scored sections; parity tests green.
I2. Dynasty relabel: build_site.py:3781 aria-label "League scoring format" -> "Board
    lens" (the control IS the lens, not scoring). Regenerate the shell.
I3. DFS freshness: (a) client self-check in dfs.js (slate_date < viewer-today
    without stale_slate -> render the stale banner variant; parse date parts
    locally, redraft.js:364-371 pattern); (b) diagnose why step 9d-bis left dfs.json
    at Aug-5 while 9d rewrote fantasy.json (run_monthly.py:1891-1896 swallows the
    exception; dfs_export.py:869-873 returns 0 without restamping stale_slate on
    the crash path; restamp the previous payload there too). Gate: a yesterday-dated
    payload without stale_slate renders the banner in the JS harness; the crash path
    leaves a stamped payload.
I4. The merge: repurpose build_fantasy() into the combined /fantasy/ shell
    (module switcher Redraft | Dynasty | DFS above each module's own section nav);
    emit each client's OWN mount ids (NEVER the fantasy-era fallback ids);
    coordinator lazy-boots the active sub-client on first activation; namespaced
    hash (#m=redraft&section=ros_sp) with alias mapping for EVERY legacy form
    (pre-split aliases in docs/diamond-fantasy.md:52-55 plus current three-page
    hashes); /dynasty/ /redraft/ /dfs/ become hash-preserving redirect stubs on the
    /teams/ template; nav collapses three Diamond-dropdown items into one "Fantasy";
    update homepage card, hub links, sitemap, publish_paths (all four dirs keep
    shipping; a redirect that does not ship is a 404). Gate: URL-migration test
    enumerating every legacy hash; double-mount guard test (no fantasy-era ids in
    the shell); full test_fantasy_split.py green; visual pass on all three
    sub-modules.
I5. Fantasy player card overlay (#player=<mlbam>, namespaced): assembled
    client-side from data already in the browser: identity + elig chips; four-format
    score line; ROS projection tape; HEM+/SEM+/REM+ with glossary terms; luck/
    buy-sell + swing_trend; upcoming starts from schedule; closer-depth role for
    RPs; dynasty block (efv/rank/tier/star/bust/surplus/band + keeper break-even)
    when present; tonight's DFS line lazy-fetched only when on the slate; outbound
    "Full MLB card" link via player_links byMlbam (coverage 1,234/1,249). Served efv
    verbatim only (extend the test_no_local_efv_basis source guard to the new file).
    Gate: JS-engine render for four archetypes; missing dfs.json degrades to a note.
I6. G3 DFS context joins, sequenced AFTER the merge (separate blast radius): MLB
    park factors by reusing fa_meta.json park_factors through the waiting interface
    at dfs_export._park_factors (every MLB park leg is neutral today and the
    disclosure says so; the disclosure must not survive the change it describes);
    Vegas implied team totals from the already-paid .cache/odds snapshots; confirmed
    lineups/batting order from the free StatsAPI lineups endpoint. All joins, no new
    models, honest labels.

## Lane J: Projections + FA visualization (owner decision 13: 96px floor)

The invariant (verified at site.css:3548-3571 + test_board_card_typography.py):
height:auto + min-height (never height), minmax(min-content,auto) identity rows,
.mlb-name untouched. Condense CHROME ONLY. Grid tracks are set by JS inline styles
(projections.js:1260 CARD_TRACKS, fa.js:715 FA_TRACKS); editing site.css tracks
silently does nothing.

J1. Condense to 96px: card padding 8 -> 6 top/bottom (keep 12/16 horizontal for the
    org stripe), tape padding-top 5 -> 3, chip padding 3px -> 2px vertical + chip
    line-height 1.35 -> 1.2 (scoped to .fa-card/.proj-card, NOT bare .mlb-chip,
    which fantasy shares), min-height + contain-intrinsic-size 108 -> 96 (unifies
    with the existing mobile floor). Gate: test_board_card_typography green all 4
    route x theme cases; the stress test (inject line-height 2.1 @19px, assert 0
    clipped .mlb-name and cards grow); desktop offsetHeight == 96 at 1226x900 in
    both themes.
J2. Compare picker button: .proj-cmp-btn has NO appearance rule anywhere (renders as
    a raw UA button; picked state invisible; the comment at projections.js:1175-1177
    is false). Add the missing rules in the site's active-control language
    (retro-mono, var(--border)/var(--accent-cyan), :focus-visible ring); keep the
    coarse-pointer hit-area overlay in sync.
J3. Compare view re-dress (minimal pass): newsprint-eyebrow header ("Head-to-Head")
    replacing the player-page dialect at projections.js:1427; 2-3 y-axis WAR tick
    labels on the SVG (x ticks only today); identity-head upgrade (org stripe +
    24px photo well via existing rowPhoto/fillRowPhotos) as additive polish.
J4. FA photo rail port: move .fa-row-photo out of .mlb-name into a rail child of
    .fa-id (projections markup shape), extend the .proj-id grid rules to cover it.
    Removes the documented 7px line-box tax and gives .fa-id the min-content row
    floors the invariant prescribes (it relies on min-height alone today).
J5. Spend the projections identity slack (~670px for content needing ~half): add
    Peak WAR and Contract-thru as real row-1 columns >= 1025px (the sort keys
    already exist in the tape sortbar, projections.js:1282-1283); each new header
    MUST sort by the value its column shows (the 2026-07-31 defect class); tracks
    change in the JS constant; re-verify the 13px header alignment device
    (site.css:3674).
J6. Tap-to-open band popover (the open omnibus-2 item): one ~40-line component;
    click/tap/Enter on [data-band] cells opens a positioned panel with the P10-P90
    text sourced from the existing aria-label so the aavWild flat-ratio disclosure
    rides along verbatim; Esc/outside closes. Wire the 446 aav/guar cells AND give
    surplusSpan (fa.js:90-95) the tabindex+aria-label treatment it missed. Do NOT
    re-inline bands into row-1 cells (rejected at fa.js:629-634).
J7. Quick wins: restore the .fa-statustext 2-line clamp at <=720px (site.css:3723
    resets display:block which disables the clamp; long SIGNED strings grow phone
    cards unbounded); delete the dead --card-tracks property or make it the real
    mechanism; delete the self-documented dead rule at site.css:1704-1707; give the
    projections board the newsprint-eyebrow head the FA board has.

## Lane K: Pitcher Alchemy Lab (tiers, colors, ladder)

K1. Server-stamped tier rules per direction (mirror the prospect_watch_rule pattern,
    pal_export.py:508-525): rp2sp keeps 70/55/42 (the 70+ annotation is load-bearing
    and the 'successful' flag already splits the premium case); sp2rp gets its OWN
    absolute cuts ~55/45/35 (measured live: fit max 62.8, >=70: 0 rows, so the
    advertised top tier is empty today; ~55/45/35 gives 6/26/~44 members). Absolute
    cuts, never per-build quantiles (tier churn). pal.js tierTitle/tierLegend read
    thresholds + counts from the payload with a stale-payload fallback. rp2sp tier
    NAMES stay screen/profile language (that direction's backtest is sign-wrong;
    expansion is banned).
K2. Color by TIER, not direction: restyle .pal-tier (8.5px all-cyan/all-orange
    today) into a bordered chip on the severity ramp: top var(--accent-cyan),
    second var(--accent-green), third var(--accent-gold), bottom var(--text-tertiary);
    reuse the .pal-flag bordered-chip pattern; optional left-border row accent. Add
    the Tier column to the sp2rp GFX board (rp2sp already has it). Zero new hex.
    Gate: both-theme screenshots show four distinct tiers; no hex additions outside
    token definitions.
K3. Prospect Watch severity tiers: extend prospect_watch_rule with structural band
    cuts >=20 / >=15 / >=10 (full/three-quarter/half of the 20-pt swing band;
    measured 9/10/37 rows); severity chip on each card (warn-orange/gold/default)
    replacing the plain "past the band" text; all copy reads thresholds from the
    payload rule.
K4. Copy-drift sweep: pal.js:1131 loading placeholder attribution; the stale
    comment at pal.js:919-921 (0.9779/9,101 vs the payload's 0.9759/4,968); verify
    then correct the positional_ladder 'surface' field in model_registry.json:2407 +
    _am_crossmodel_map.json:1479 against the eval's consumers block (proj_ml and
    eFV are recorded NON-consumers; read proj_ml.py/efv_model.py first; registry
    rows may be tool-written, find the authoring source); homepage Alchemy xmod card
    gains one word of screen-framing ("conversion screen"). The /pal/ meta
    description is FIXED; do not touch build_site.py:3701-3722.
K5. Positional ladder current-era gate: the ladder is an inversion of BRef's own
    constants (positional_fit.py:229-234) with measured era drift beyond its CIs
    (2021-2026: SS 9.44 vs shipped 8.92, 2B 5.17 vs 4.73). Pre-register a
    recency-weighted or windowed champion vs the shipped 2012-2026 fit, scored
    forward-chained (fit through 2023, predict 2024-2026 runs_position/650),
    paired-bootstrap dMAE CI excluding zero to ship. Fallback on a failed gate:
    publish the 2021-2026 era rung as a labeled secondary column on /pal/.
    Identification tests stay green; POS_ADJ picks changes up via the artifact read;
    one-owner rule: positional_fit.fit_ladder is THE fit.
K6. Defensive-components research lane (deferred until K1-K5 land; run only if
    session budget remains): savant_oaa.json carries directional OAA (in/bk/l3/l1),
    platoon splits, and actual-vs-expected success rates that positional_fit never
    reads; pre-register a component-informed cross-position transfer challenger
    against the existing conversion-accuracy harness (MAE on n=169 real movers,
    champion 5.682 vs carry-over 6.733) + demotion AUC non-degradation. Do NOT
    attempt catcher framing (refused; Savant season param inert), do NOT re-blend
    team Statcast fielding into WAR (measured monotone worse), no DRS/arm data
    exists to reach for.

## Lane L: Logo font swap (owner decision 12: PixelMplus12 bold, art regen)

Verified: --font-logo is defined once (site.css:179, DotGothic16-led); the shipped
PixelMplus12 subsets carry full ASCII + Latin-1 in BOTH weights (276 codepoints, no
re-subsetting needed); today's logo renders effective-regular (DotGothic16 has no
bold + font-synthesis:none) despite 700 declarations, so the swap makes it genuinely
bold, which the owner approved. Note the omnibus-2 plan recorded "default NO (logo
stays DotGothic16) pending owner veto"; this decision IS that veto, cite it in the
commit.

L1. Build the specimen page first (both weights, masthead/nav/sidebar/prospx-h1/GFX
    header/share-card sizes, both themes) as the sign-off artifact; owner has chosen
    700, so the specimen is a verification device, not a decision gate.
L2. CSS swap: --font-logo -> PixelMplus12-led (site.css:179); delete the DotGothic16
    @font-face (site.css:19-25) + assets/fonts/dotgothic16-latin.woff2 (keep the
    vendored TTF + OFL license in branding/fonts/); rewrite the now-false comment
    blocks (site.css:13-18, 27-55, 160-165, 175-178; prospx:242-246, 1023). Do NOT
    touch --font-retro/--font-retro-mono (copy tokens; Windows must keep MS Gothic
    first; test-pinned).
L3. Re-tune the merged-wordmark arc/ball em offsets for the shorter face
    (PixelMplus12 cap 717 vs DotGothic16 787; advances identical so widths cannot
    change): .eephus-wordmark-merged padding-top, .ew-arc top/height, .ew-ball top
    (site.css:1155-1157) + dark-mode glow (1240-1242), checked at masthead/nav/
    sidebar sizes, both themes.
L4. Canvas + warmups: eephus-gfx.js:106 and eephus-hub.js:219 MONO constants ->
    PixelMplus12-led; eephus-export.js:443/452/463; warmup specs eephus-gfx.js:621-622
    and prospx:33389 -> PixelMplus12 400+700. Add the missing document.fonts.load
    waits to eephus-hub.js shareCard and eephus-export.js _brandCompose (clone gfx
    awaitFonts) so the first cold-session export does not rasterize the fallback.
    Leave _GFX_SVG_MONO (prospx:34219) as a system stack (serialized SVG cannot load
    webfonts) but fix its comment.
L5. PIL brand art: tools/generate_brand_assets.py:112 _LOGO_TTF ->
    branding/fonts/PixelMplus12-Bold.ttf; regenerate share-default.png (og:image),
    Twitter banners/avatars, animated gif. PixelMplus12 is 12px-native: generator
    sizes 108/120 are clean 9x/10x; if 34/40 render ragged, snap to 36/48. NOTE for
    the owner: the social banner/avatar files need hand re-uploading to the actual
    accounts; no script does that.
L6. Rebuild the site (asset ?v= hashes restamp on every page including the
    hand-kept prospx/collegesavant copies), commit, push.
L7. Test pins: extend test_board_card_typography.py: --font-logo leads with
    PixelMplus12; zero 'DotGothic16' strings remain in site.css, eephus-gfx.js,
    eephus-hub.js, eephus-export.js, prospx/index.html (kills silent canvas-constant
    drift, the failure mode _GFX_SVG_MONO already demonstrated).

## Lane M: UI bug fixes (owner decision 14 + reported bugs)

M1. Hot Sample spotlight overflow (owner-reported): the chip inherits .row-delta's
    flex:none + min-width:46px + text-align:right (site.css:1367), so the 150-200px
    statline cannot shrink into the ~124px sidebar text column and pokes through the
    card border; the earlier white-space:normal fix never got a chance to wrap
    because the box is never narrowed. Fix: extend the inline style at
    build_site.py:2024-2026 with 'flex:1 1 100%;min-width:0;text-align:left;'
    (statline takes its own full-width row under the FV pill; the row's flex-wrap
    already supports it); optional overflow:hidden backstop on .spotlight
    (site.css:1381). Do NOT touch .row-delta itself (shared by module rows + OTD
    chips). Gate: render the hot-sample slot with the longest live statline (28
    chars) at 1320px+; statline wraps inside the border; scrollWidth <= clientWidth
    on .spotlight; riser/faller slots unchanged.
M2. prospx 136px card clip guards (owner decision 14): add the guards the comment
    at prospx:2095-2100 claims exist but do not: min-height:0 + overflow:hidden on
    .milb-cell (3476-3482) and .player-row-col1, overflow:hidden on
    .player-row:not(.is-expanded); correct the false comment. Gate: with real fonts
    (a Windows browser, not headless-only), a data-rich 4-line pitcher row does not
    paint over the row-2 tool tape or the border; scrollHeight <= clientHeight per
    cell.
M3. Glossary model-registry table: <table class="meth-tier-table meth-registry-table">
    (glossary.js:1493) has ZERO style rules anywhere; add the styled class
    (meth-table) to the emitter + a scoped overflow-x:auto wrapper (the
    .detail-table display:block pattern; NEVER blanket overflow on a sticky-rail
    parent). Gate: 1280px and 375px render; document scrollWidth == clientWidth at
    375px.
M4. prospx bare-fr column alignment pass (measure FIRST): compare computed track
    widths of .col-header vs 10 sampled rows at 1440/1280/1024 across the main
    list, injured, traded, leaderboard, draft variants; where rows diverge, convert
    the offending template tracks to minmax(0,Nfr) (the teaser-row precedent) and
    confirm the cell content ellipsizes. Do not blanket-convert.
M5. Farm board under ~1300px: auto-switch to the existing cards view (width check on
    the farmViewMode machinery) unless the user explicitly pinned table mode; the
    16-col grid's fixed min is 1268px and the v45 note deliberately has no overflow
    wrapper (sticky header).
M6. Browser-check the short suspect list and file-or-clear each with a measured
    number: prospx mobile line-chart-cell (42px box, ~60px chart, overflow:visible)
    vs the toolstrip; glossary .meth-cmp at 375px; betting .bt-markets frozen
    columns in 280px scrollports. Diamond pages were browser-QA'd 2026-08-05; do
    not re-sweep them statically.

## Lane N: Correctness backlog (leaks, silent failures, owed items)

N1. Run-summary single-writer restructure: stamp data/timeseries.json ONCE after the
    run_daily chain returns, with a fallback stamp on the chain-raise path; remove
    the superseded call at run_monthly.py:4507 only as part of the restructure. This
    is the file the two-writer race truncated. Gate: a test asserting one
    _patch_export_run_summary invocation per monthly success path AND a stamped
    summary on a simulated chain-raise.
N2. FA identity aliases: read-time alias in the fa_ident seam for jake_junis ->
    "Jakob Junis" (BBRef spelling); then root-cause Woo Jin An, Trevor Stephan,
    Rowan Wick individually (do not assume spelling; An may be KBO/no-BBRef).
    Tyler Austin is no_recent_seasons and likely legitimate. Alias map, never a DB
    remap. Gate: fa_class.json identity_unresolved drops by exactly the aliased
    count after a BOX rebuild (this sandbox's SSL fails for baseball-reference);
    no other member's projection moves.
N3. Per-tier AAV band gate: pre-register and run the location-scale band fit already
    wired behind BAND_SCALE_GUAR=False (fa_market.py:168, fit at 1591-1616,
    ridge-shrunk toward flat, fail-to-flat). T1.2 measured null 2026-07-25, so this
    is a NEW gate, never a blind flip. Ship on held-out interval coverage closer to
    80% without MAE regression; else keep the >2.5x disclosure and ledger the null.
    The $39.4M-AAV -> $140M P90 band is a live credibility cost.
N4. CLV crontab verification (OWNER ACTION, one minute on the box): crontab -l must
    show deploy/betting-crontab.example:28 (close job */15 12-23 UTC). Until
    confirmed, every passing CLV test tests code that may never run. After the next
    close capture: data/betting_clv.json exists with n_graded > 0.
N5. Silent-empty triage (post-dc8c8f1 residue): apply the two approved postures
    (None-as-sentinel, or keep-previous + ingest RED with the source name added to
    SCHEDULED_EXPORTS) to mlb_player_export._load (:378-382, blanks HEM+/REM+ tiles
    on every MLB card), pal_export.load_player_links (:222-228, the join
    substrate), pal_export BBRef WAR parse (:216-218). Mark proj_export.py:1042-1049
    (+ verify :1205, :1815) as conservative-direction guards with a comment if they
    are. Gate per site: a failed load yields None/keep-previous + a RED row that
    survives the drain under the __main__ launch shape, or a written justification.
N6. J1 model accountability hub: one build_site.py-generated page rendering
    data/model_registry.json rows + every eval verdict with dates and deep links;
    no hand-written verdicts. (J4 stays blocked on the D-lane by design.)
N7. Arias attribution replay (owner-commissioned): paired single-process replay of
    the 08-03 (7626fd0) vs 08-04 (d50c1af) vintages, rebuilding features as-of, to
    name the feature(s) behind his -0.13 WAR move. Lab-only; zero served artifacts
    written. Gate: attribution table sums to the observed -0.13 within rounding.
N8. Betting close-job + shadow items are in Lane G. The park leak, doubleheaders,
    module-identity trap, FA bwar_pitch cache, and golden restamp are FIXED (section
    3); do not re-open.

## Appendix: recon provenance

14-lane read-only recon workflow (wf_2db20c82-a0f, 2026-08-07): eval-protocol,
drivers-scaling-pinazzi, new-drivers-inventory, provisional-stale-arias, charts,
statcast-plus, diamond-cards, betting, fantasy, proj-fa-viz, pal, fonts-logo,
ui-bugs, leaks-silent-failures. Per-lane structured findings (file:line evidence,
plan items, decision options, banned/prior-art lists) are preserved in the planning
session's scratchpad and summarized faithfully above; where an executor needs more
detail than a lane section carries, the cited file:line locations are the ground
truth. Owner decision rounds: 4 AskUserQuestion calls, 14 decisions, all recorded in
section 1.

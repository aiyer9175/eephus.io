# Master plan 2026-08-04b: repair what the eight-asks execution surfaced, and take eWAR further

Written for Claude Opus 5 to implement. This plan is the successor to
`docs/master-plan-2026-08-03-eight-asks.md` and consumes the findings recorded in
`docs/EXECUTION_2026-08-04-eight-asks.md` (14 commits, `5325440..0828b15`, all pushed;
suite 3,001 passed / 1 failed with the single red deliberate). Every claim below was
measured in that session; file:line references are from that tree. Re-verify anything the
tree has moved under.

The owner's directive for this plan: fix ALL of the open issues from those results, and
improve eWAR further. That directive AUTHORIZES resolving items previously parked as owner
calls, with two exceptions marked [CHECKPOINT] below (the dpw re-anchor and the eFV label
flip), which change every price or every grade on the site and get an AskUserQuestion with
the measured deltas before the switch is thrown - the work up to the switch is authorized.

## 0. Ground rules (updated with what this session taught)

1. **NEVER run pytest while any agent is editing.** conftest git-checkouts whatever became
   dirty during a run. This session ran a 2-file pytest mid-lane and survived by luck (the
   dirty file predated the run). Run the suite once, serially, from the orchestrator, after
   all lanes land. Targeted guard checks during work = re-implement the assertion in a
   scratch script, never pytest.
2. **The nightly box pipeline runs ~00:30-04:00 local** and rewrites data artifacts. Check
   `git status prospect-tracker/data/` + mtimes before diagnosing any red. Box is the
   single writer of gitignored artifacts.
3. **Eval-artifact regens are not like-for-like across matrix vintages.** The 07-24 vs
   08-03 comparison moved the hitter consensus BASELINE +0.0201, above its own MDE, with a
   byte-identical feature list. Any cross-vintage delta smaller than the baseline drift is
   data vintage, not model quality. Same-rows, same-matrix comparisons only.
4. **A python `str.replace` anchored on a line with a trailing comment silently no-ops.**
   Cost a broken registry mapping this session; only verification caught it. After every
   scripted text edit, re-grep for the inserted text.
5. **Editing `data/model_registry.json` desyncs MODEL_REGISTRY.md and SITE_MAP.md** - run
   `python tools/gen_audit_docs.py` in the same commit. **Editing assets/site.css or any
   stamped asset desyncs the three hand-authored pages** - run
   `build_site.restamp_hand_authored_pages()` (stamps only; verify the diff is stamps
   only).
6. **Scratchpads do not survive sessions.** The fresh side-fairness eval the 08-04 lane
   left "ready to install" is GONE; anything below that references a prior session's
   scratch output must be RE-RUN, not recovered.
7. Standing rules unchanged: no em/en dashes; eFV rounds NEAREST, consensus CEIL; every
   model claim forward-chained on the existing harness vs the shipped champion with MDE
   floors (hit 0.017 / pit 0.016) and a zero-information control; two-metric gates must
   agree in sign; measured no-ships are `verdict: deprecated` + MODEL_GLOSSARY mapping;
   new `data/*_eval.json` without a registry row turns the suite red; commit explicit
   paths; ruff `--select F821` on touched python; node-check the prospx inline script
   after editing it; adversarial-verify any single-agent measurement that gates a ship.
8. **The banned ledger grew this session.** Additions to DO-NOT-RE-ATTEMPT: pace_from_entry
   (kill criterion fired; the triple variant is a RESOLVED HARM, CI excludes zero), level
   blend rates/anchor/joint arms (anchor a measured loss), continuous ETA age ramp, the
   LGBM market challenger (third loss), the cohort-intercept refit (three consecutive
   losses). The full prior ledger in master-plan-2026-08-03 rule 7 still binds.
9. Network: FanGraphs is 403 and stays untouched. Baseball Savant IS reachable (direct
   urllib + User-Agent, house precedent) and lane R2 uses it. pybaseball bwar pulls are
   routine. Nothing else.

Suggested order: R1a and R4 first (small, unblock the suite story), then R2 (the eWAR
program, heavy), R3 gated on R2, with R5, R6 and R8 in parallel lanes, and R7 last
(box-coupled). Lanes are file-disjoint except where noted.

---

## LANE R1: the projections level program

The execution session proved the platform's one deliberate red is mostly a stale constant,
and separately that the vet engine's roster LEVEL regressed while its shape improved.
These are different problems; do not conflate them.

### R1a. Drop the stale intercept vector (turns the deliberate red green)
The served cohort-intercept vector was fit 2026-06-12 and has now lost its own holdout
three consecutive times (7.71-won at 06-12; 7.29 vs 7.19 on 07-31; 7.27 vs 7.21 today).
It contributes sum_coh -69.6, which is 77% of the 3.02 remainder; without it the remainder
is 0.70 (the genuine roster+depth gap) and the vector is MAE-NEUTRAL on today's paths
(7.18 vs 7.21). The sanctioned mechanism already exists: `cd prospect-tracker && python
proj_backtest.py` persists `retro_backtest.ship_decision.challenger_wins: false` into
`data/team_outlook_eval.json`, and `proj_export._cohort_intercepts()` (proj_export.py:713-720)
then returns `{}` so the vector stops serving on the next export. Do exactly that. Then:
- verify `test_recenter_remainder_near_zero` goes GREEN on the box's next export (the
  committed artifact turns first; the served remainder needs the box pass);
- update the `team_win_projections` registry notes (the 08-04 note already records the
  decomposition; append the action + date);
- reconcile the `_depth_pool` docstring "sums to ~870-930" vs the 900 test floor
  (proj_export.py:776-778, test_team_outlook_calibration.py:145) - state one truth.

### R1b. Fix the harness blind spots the session exposed
All in proj_backtest.py + the artifact it writes:
1. The gate scores a FRESH refit but never the SERVING vector. Add a third arm that scores
   whatever `_cohort_intercepts()` currently returns, so "is what ships helping" is a
   number the artifact carries every run.
2. Pooled bias dilutes 1.75x: 4,019 of 8,866 scored rows are players with no roster spot
   whose actual WAR is 0 by construction. Emit `bias_assigned_only` (+0.086 today) and
   `mae_assigned_only` alongside the pooled figures, and make the registry quote the
   assigned figure.
3. Emit the assigned-roster LEVEL series (actual vs predicted assigned WAR per season,
   the table that exposed the -88.1) as a first-class artifact block, so the next
   regression is visible in the committed record rather than in a scratch script.

### R1c. The roster level repair (gated program, the real model work)
The engine under-projects real 2025 assigned rosters by 88.1 WAR where the 06-12 engine
was within 8.3; attribution says the bulk arrived with E3 (the 07-31 playing-time refit)
and F-DEF partially recovered it (8.56 -> 8.31 raw holdout MAE). The 07-31 verdict
rejected a PT re-anchor because E3's own panel measures its PA level as BETTER
(projected-PA error +51.3 -> -13.6). Both measurements are real, so the deficit is NOT a
simple PT level story - decompose before fixing:
1. On the retro chain, split each season's assigned-WAR deficit into an EXPOSURE leg
   (predicted PA/IP vs actual, priced at actual rate) and a RATE leg (predicted rate vs
   actual, priced at actual exposure). This tells you which leg E3 broke.
2. Pre-register candidates against the leg the decomposition convicts, e.g. a
   rate-level recalibration on assigned rows only; an exposure floor for
   established-roster players; a survivor-conditional PT head. Do NOT re-run the two
   candidates already measured and rejected (cohort refit, uniform PT re-anchor) without
   new structure.
3. Gate, pre-registered before any fit: assigned-level deficit shrinks by more than half
   on the 2025 holdout AND player-level shape not-worse (pooled and per-cohort MAE within
   noise) AND recentered team MAE not-worse. A candidate that trades shape for level or
   level for shape fails.
4. Whatever ships or fails, the loss ledger goes in the registry and the
   `REVIEW_QUEUE.md` h5 star item gets re-pointed at the refreshed war_cohort_eval.

---

## LANE R2: eWAR v2 (the improvement program)

v1's verdict (data/ewar_eval.json, registry `ewar_v1`): the FIP pitching swap earns its
place (persistence 0.3664 vs 0.1769, forecasts next-year actual runs better than actual
runs do), the fielding swap loses BOTH gates and did not. v1 facts that shape v2, verified
in ewar.py: the fielding read is Savant **FRP** (not raw OAA), centred within each
position's own pool because raw FRP double-counts B-Ref's runs_position
(ewar.py:295-336); coverage is the seven OAA positions, 2016+, catchers a leaderboard
blind spot (ewar.py:104-108); `data/savant_arm.json` is arm STRENGTH in mph (2020+), not
runs. The eval's own "what would change the verdict" list is the spec; run it.

### R2a. Fielding: BLEND, not replace
Replace v1's hard swap with `w * FRP_centred + (1 - w) * rfield` per player-position-season
where both exist (they correlate 0.63 on full-time covered seasons). Fit nothing fancy:
grid w in {0, 0.25, 0.5, 0.75, 1.0}, per position GROUP (IF, OF) if the grid says the
groups differ, chosen on the pre-registered gate below. w=1.0 must reproduce v1
byte-identically and w=0.0 must reproduce the bWAR fielding arm - those are the harness
validity checks, run them first.

### R2b. Season-decompose the fielding loss before trusting the mechanism story
The "OAA is range-only" account predicts the fielding-swap loss CONCENTRATES in seasons
where FRV genuinely lacked arm value and shrinks where Savant folded OF arm (and later
infield throwing) into FRV. Split the attribution arms by season. If the loss is flat
across eras, the range-only story is incomplete and the blend weight should not be
era-conditional; if it shrinks post-2022, make w era-aware. Either answer is progress;
record which.

### R2c. Catcher defense: build the missing ingest
Catchers are the one position with ZERO Statcast coverage in our tree, falling back to
rfield entirely. Savant publishes catcher framing (runs) via the catch-framing leaderboard
CSV, reachable with the house direct-urllib pattern. Build `savant_catcher.py` (ingest +
cache under .cache/, artifact `data/savant_catcher.json`, seasons 2016+ as available) and
add a catcher fielding read: framing runs (+ blocking/throwing where the CSV carries
them), centred within the catcher pool like every other position, playing-time shrunk
with a k fit the same way positional_fit's k_inn were. Where absent, rfield fallback as
today. If the endpoint shape defeats the ingest, STOP and record the blocker - do not
scrape HTML speculatively.

### R2d. Sharpen gate 1: regress components against what they actually cause
Team WINS inherit Pythagorean noise. Add, without removing the wins gate: team RUNS
SCORED regressed on the offensive component sum, team RUNS ALLOWED on pitching+fielding,
run differential on the total, all 2016-2025 on identical rows for eWAR and bWAR. This is
the eval's own suggested refinement and it is the gate on which a fielding improvement can
actually show up (fielding is a rounding error inside wins but not inside runs allowed).

### R2e. Pitching refinements, each separately gated on the persistence pair
The pitching component's case is persistence + next-year forecast; every candidate is
measured on exactly those two, same rows, against the v1 pitching arm:
1. Park-adjust the FIP inputs (the Savant park factors already ingested for the FA lane).
2. HR/FB regression (xFIP-style) as a VARIANT, expected to help persistence and hurt
   same-season fit further - ship only if the forecast leg improves.
3. Reliever leverage: v1 kept B-Ref's leverage treatment; confirm what that is in the
   decomposition and test crediting relievers with our own gmLI (mlb_leverage) instead.
   If the decomposition shows leverage is already priced upstream, record and stop.

### R2f. Re-run everything, honestly
Full gate battery + single-swap attribution arms on v2; rewrite data/ewar_eval.json;
update the `ewar_v1` registry row (rename to `ewar` with a version field, or add
`ewar_v2` and deprecate v1 - follow whichever convention the registry already uses for
versioned champions, check prospect_surplus's history). Face-validity spot checks stay
(Nola 2018, Minor 2019). eWAR still ships to NO consumer in this lane.

---

## LANE R3: eWAR as a forward label (gated; the payoff if it works)

The owner's original hypothesis: a better WAR label makes eFV more accurate. v1's
measured story says the PITCHING side is where the label is cleaner (2.1x persistence).
Run the experiment properly and let it die properly if it dies.

1. **R3a eFV label swap gate.** Rebuild first-6yr labels from eWAR v2 (or, if R2 leaves
   the fielding verdict unchanged, from the pitching-swap-only variant - the attribution
   arms make that a legitimate championed configuration) for the resolved cohort, and run
   the efv_lab_runner protocol with the TARGET swapped. Decision metric, pre-registered:
   the model-vs-consensus MARGIN (both scored on the SAME labels), both sides, MDE floors,
   permutation control. Secondary: reliability curves + WAG calibration re-run on the new
   label. Note the label changes what "right" means, so absolute rho moves are
   uninterpretable; ONLY the margin is the decision quantity.
2. **R3b FA gate.** fa_backtest Gate-1 with realized labels swapped to eWAR, pitcher slice
   especially. Same margin logic vs the Marcel baseline scored on the same labels.
3. **R3c the flip [CHECKPOINT].** If and only if R3a widens the margin outside noise:
   assemble the Stage-2 runbook (fv_outcome_curves refit, FV_EXPECTED_WAR + survivor curve
   + prospx FV_WAR_ANCHORS mirror, empirical anchors, draft slot curve, Platt re-check,
   reliability regen, prospx_current re-freeze captured INSIDE
   `vf.valuation_set("prospx_current")`, `label=` term added to BOARD_BASIS_FINGERPRINT,
   epoch bump, two-pass export, box choreography) and put the measured deltas in front of
   the owner via AskUserQuestion before executing. If the gates fail, the loss ledger
   closes the owner's hypothesis with numbers, which is a fine outcome.

---

## LANE R4: eFV harness hygiene (small, do early)

1. **`composite_at_shipped` is mislabeled** (found by the E0 re-measurement): the
   rank-gate block records the composite at the lambda the selector CHOSE this run (0.50)
   under a key that claims the SHIPPED lambda (hit is pinned at 0.70). Fix efv_model.py to
   record the composite at the actually-shipped lambda (and keep the selector's choice
   under its own key), regen both eval artifacts, confirm the hitter truth at 0.70 is
   rho 0.3882 / wm 0.2349 / t45 0.2777.
2. **Pin the pitcher blend lambda.** The dynamic reselect is an argmax over noise (band
   spread 0.16x the pitcher MDE, driven by a Spearman on 60 rows) and has produced three
   quoted values in three weeks. Pin `_BLEND_LAMBDA_RESELECT["pit"]` at the served 0.57,
   mirroring the hit 0.70 churn-pin precedent and its rationale (non-inferiority inside
   the band, run-to-run grade stability). Registry + provenance slot updated; this is a
   correctness/stability change, not an accuracy claim - say so in the commit.
3. **Re-baseline the side-fairness gate.** data/xfv_side_fairness_eval.json is stamped
   07-24 with lambdas {hit 0.85, pit 0.54}, neither shipped. The 08-04 lane's fresh run
   showed the MEDIAN leg losing its CI90 exclusion of zero while the coded B4 check reads
   only the MEAN, and S1 declares mean and median co-primary. RE-RUN the joint eval on the
   shipped lambdas (the prior session's copy is gone with its scratchpad), commit it,
   and extend the B4 check to both legs. If the median leg now fails S1, that is a
   standing-gate breach to surface, not to paper over.
4. **Doc corrections**: the pace-gate documents cite a -0.5943 `efv_ungraded` weight that
   does not reproduce under any spec (measured 08-04); annotate the citing doc(s). Sweep
   any remaining "rank-mapped to the 20-80 scale" phrasing (one was fixed in
   projections.js; grep assets + glossary for stragglers).

---

## LANE R5: pricing coverage + identity hardening

1. **Price the 167 `no_contract` pre-arb vets** - the largest open coverage hole, with the
   modelling decision already registered in-source (bayes_trade_value.py ~:4376: price at
   league-minimum salary basis). Implement: surplus = projection value minus prorated
   league-min-scale salary over the pre-arb window, through the same convex curve as
   priced vets; stamp a distinct surplus_source; update the coverage census and the
   unpriced ledger; add a policy test. Gate: no rank inversion against comparable
   modeled vets (a pre-arb 2-WAR player must not price below a priced 2-WAR arb player
   with the same projection).
2. **Star-rental premium harness** (registered at proj_export.py:337-342). Build the
   deadline backtest: historical deadline trades (the trades ledger + mlb_trade lookups
   already in the tree), realized rest-of-season WAR of the rentals, price paid vs the
   full-season convex curve's prorated value. Measure whether a concentration premium
   exists and its size; ship a constant ONLY if the measurement supports one, else ledger.
3. **Backfill `roster_status.mlb_seasons`** - 782 of 2,681 debuts.json rows carry an empty
   list, which is the blind spot that let the kelvin_herrera-class rows through. The data
   to fill it already exists in the career_war table (season keys per player). Backfill in
   the debuts builder (find it in storage.py), regenerate, and the TM inactive rule
   becomes structurally sound instead of guard-rescued. Keep the age-incoherence guard as
   belt-and-suspenders.
4. **Identity sweep for retired-vs-current slug fusions.** The TM guard catches the three
   known rows; the monitor (identity_collisions.json) cannot see the class because it
   censuses the CURRENT roster feed only. Add a sweep to the identity audit: for every
   career_war key, age implied at last MLB season vs birth_date; below 17 (or above ~50)
   is two humans on one key. Ledger the hits with proposed splits; repair the worst
   through the existing identity-repair path.

---

## LANE R6: fit-engine concentration (Gate 3)

State: accuracy passes (MRR 0.1669 vs random 0.1332), concentration FAILS and worsened
with fresh data (LAD max_top1_share 0.5833 vs 0.25 threshold; the 07-29 SFG-pitchers
pattern was a roster-vintage artifact). No need/behaviour re-weight tested passes. Plan:
1. **Decompose before repairing**: per-component top-1 share (need alone, behavior alone,
   afford alone) on the current class. If LAD tops the need component too, the need signal
   itself is saturated (their roster holes + money swamp the per-player term) and
   re-weighting can never fix it.
2. Candidate repairs, pre-registered, in order of preference:
   (a) per-club need SATURATION (a club's aggregate fit mass is capped, softmax
   temperature on the club axis) so one club cannot top every list;
   (b) DISPLAY-side relative fit: rank clubs for a player by fit MINUS that club's
   baseline propensity (its mean fit across the class), which directly de-monopolizes
   the view while leaving the raw model intact;
   (c) per-player z-scoring across clubs.
   Gate: concentration PASS (max_top1_share <= 0.25, distinct_top1 >= 12, distinct_top3
   >= 20) with MRR not-worse on the same forward chain.
3. If nothing passes both: ship (b) as the VIEW with a disclosure line, keep the model
   untouched, keep the tripwire red and honest, and register the loss.

---

## LANE R7: dpw re-anchor + box choreography [CHECKPOINT]

1. **fa_dpw_series re-anchor.** The frozen +16% $/WAR drift (14.92 -> 17.29) means every
   served price is on a stale winter market. Run the coordinated re-anchor exactly per the
   sanctioned pattern: regenerate the series with `persist_dpw=True` on the gate harness,
   re-freeze `config/valuation_sets/prospx_current.yaml` by capturing surplus_value_mm
   INSIDE `with vf.valuation_set("prospx_current")` (the 07-24 lesson: capturing on the
   default set silently yields a different grid), restamp the 18 valuation-set test
   literals and the golden, TWO export passes. Measure the board/TM/surplus deltas,
   present via AskUserQuestion, THEN flip. This cannot ride along with anything else.
2. **Box choreography** (unchanged debts, now larger): the RUNBOOK_2026-08-03 two-pass
   regen; the Wave-1 exporter changes (proj_export display grade, fantasy display,
   TM exclusions) and the homepage build serve only after the box runs; golden fingerprint
   restamp after the box eFV regen; verify `xfv_history_is_on_board_basis()` flips true;
   beta sync only after everything is pushed.

---

## LANE R8: frontend residue

1. **fantasy.js has no hash router** (verified: zero location.hash reads), so the new
   homepage Fantasy card can only link the bare page and section state dies on refresh.
   Add `#view=`/`#player=` read/write mirroring the mlbstats writeHash/readHash pattern,
   then deep-link the homepage card rows.
2. **projections.js inline-style burn-down, remainder**: 58 lines remain (from 92); the
   08-04 report enumerates them (accountability table margins and static spacing). Finish
   the enumerated list; leave computed values inline (bar widths, metric colors).
3. **GFX browser-truth pass.** The geometry shipped verified by node-level recomputation;
   close the loop in a real browser: Playwright over a local server, export the matrix
   (rows + tiles, all 7 formats, light + dark, n in {10, 100}), assert non-blank canvas,
   expected pixel dimensions, and save the PNGs to the session record so the owner can
   SEE the new boards. Also verify one hero card and one compare card still carry
   headshots (the carve-out).
4. Sweep stragglers: any copy still describing the quantile as displayed; the TM
   `excluded` ledger could use a one-line footnote on the board page; confirm the
   aStuff+ pill tooltip landed with the prospx commit (it did; verify it survived).

---

## Acceptance shape

Each lane: measured before/after in the commit body; registry + glossary + gen_audit_docs
+ restamp in the same commit as the change that desyncs them; suite run ONCE serially at
the end - expected end-state is 3,002+ passing with ZERO deliberate reds if R1a lands
(the recenter red goes green), or a documented reason why any red remains; session record
under docs/ + memory updated. The two [CHECKPOINT] items (R7 dpw flip, R3c label flip)
stop for an AskUserQuestion with deltas attached; everything else proceeds without
asking. Bugs and stale claims found along the way get fixed at the source and recorded,
per the standing pattern - this session's biggest wins (the aStuff+ scale, the id theft,
the retired-grade delta field) were all found "along the way" by agents told to look.

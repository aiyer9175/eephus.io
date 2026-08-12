# Master plan 2026-08-12: omnibus-4

Betting program (close capture, model improvement, props value bets), L/R splits for
HEM+/SEM+/REM+, Baseball America levers for consensusFV/eFV/tools/surplus, the eFV
rookie-window unlock, the pitcher cross-side parity program, Arbitration Predictor
theming + logos, the positional-adjustment export for Will, and the GFX tile ordering
fix. Plus carried debt and a polish sweep.

**Status: PLAN ONLY, not executed. Written for Claude Opus 5 to execute.**
Written at branch `efv-conviction-2026-08-08`, 53 commits ahead of origin/main, NOT
pushed. Grounded in a 6-lane read-only recon (2026-08-12) plus direct measurement;
every file:line below was verified on this tree unless marked "verify first".

---

## 0. Read this first: execution discipline (violating these has burned sessions)

1. **No lane runs pytest.** `conftest.py:227-268` git-checkouts anything the suite
   dirtied, so a run concurrent with an edit silently reverts work. The orchestrator
   runs the suite BETWEEN waves, from `prospect-tracker/`, via the chunked runner
   (8 test files per subprocess, judge chunks by RETURN CODES, never parsed totals).
   The runner is rebuilt per session in scratchpad; lane I commits it to `tools/`.
2. **Suite baseline is exactly 2 reds**: `test_efv_export.py::test_xfv_golden_fingerprint`
   and `test_proj_export.py::test_vet_surplus_only_on_contracted_seasons`. Both need a
   real box `rebuild_only`. Do NOT "fix" them locally; do not count them as regressions.
   `test_atomic_artifact_write` is a known load-dependent flake: pre-classified, re-run
   in a fresh process before treating as a regression.
3. **Exclusive file ownership per lane.** Two lanes never edit one file in a wave.
4. **Every lane gets adversarial verification** (house pattern: 3 verifiers per lane;
   every verifier MUTATES the code under each new test and reports the mutation table).
   Phase 3 of the 2026-08-09 program shipped unverified; that debt is Wave 0 here.
5. **Artifact churn**: classify every data/ diff after each wave; revert anything no
   code change requires. `git add -A` and `git add -u` are banned; leaderboards cannot
   regenerate in this sandbox (SSL fails), so their diffs are always churn here.
6. **Copy rules**: no em-dashes anywhere on copy surfaces (`tools/copy_lint.py --check`
   gates it); LLM ban-list words hard-fail in pure-copy files; every new Arkmetric
   glossary entry carries "Arkmetric, created by Noah J. Dengler, original to
   eephus.io." Grades round UP for FV/tools; eFV and "+" stats round NEAREST.
7. **Registry edits**: `data/model_registry.json` is indent=1; any edit requires
   `python tools/gen_audit_docs.py` or `test_generated_docs_in_sync` goes red; a new
   `data/*_eval.json` trips `test_every_eval_artifact_is_registered` AND forces a
   `MODEL_GLOSSARY` decision in `test_methodology_freshness.py`; data_catalog rows
   need `stability` or build_site dies at /sources/; `pinned_by` receipts must name a
   test that actually asserts on the artifact.
8. **PowerShell mangles `python -c`**; use scratchpad script files. Use explicit paths
   for git commands (cwd drifts). Push needs `http.sslBackend schannel`.
9. **Pre-registration discipline**: every gated lane commits its gate doc with an empty
   Results section BEFORE the lab exists, so git timestamps it. Claims name their
   estimator. No spec-shopping: never pick a criterion because of how it resolves.
10. **Section 15 is the banned ledger.** Nothing on it may be re-proposed without new
    data or a new owner instruction. Several lanes below sit NEXT to banned ground;
    each one names the fence it must not cross.

---

## 1. Owner decisions LOCKED 2026-08-12 (all nine, via decision queue)

1. **Close capture: both machines, box primary.** Box crontab is the system of record;
   this Windows dev box gets a temporary Task Scheduler stopgap; de-dupe so two
   captures never double-spend credits.
2. **Props value bets: capped per-event pull.** Book prop odds for 2-3 selected
   games/day (POTD game + largest team-market edges), ~60-180 credits/month inside the
   500/month tier. Same de-vig/edge/EV machinery and provisional labeling as team bets.
3. **eFV unlock: rookie window.** eFV keeps updating from new source grades until
   rookie eligibility exhausts (130 AB / 50 IP; the 45-day roster criterion is
   approximated and disclosed), then anchors at the last in-window point. Drivers stay
   frozen to the at-debut computation in every case.
4. **Positional-adjustment export: top-level repo folder** `positional-adjustments/`,
   versioned JSON + CSV + README, sliced read-only from the pinned artifact.
5. **L/R splits: full program.** Leaderboard columns/tabs (gated labs first),
   platoon-aware props, AND a schema-3 vintage column so a betting split feature starts
   accruing honest history now.
6. **Betting posture: full program + provisional publishing.** Keep the picks surface
   live with the existing honesty rails while the validation clock accrues.
7. **BA: gated levers only**, nulls recorded as knowledge, weights stay `{}` unless a
   pre-registered gate clears.
8. **BA fence to re-examine: the SCORED_SOURCES common-set design** (pre-registered
   re-derivation; per-pair or matured-subset scoring; no verdict flips by fiat).
9. **Pitcher share remedy: cross-side parity.** FV means the same value percentile for
   both sides on the served board; within-side order preserved; ships as one
   coordinated epoch gated on the audit lane (E2).

---

## 2. Wave 0: baseline, carried debt, owner/box actions

### W0.1 Suite + tree baseline (serial, first)
- Run the chunked suite; expect exactly the 2-red baseline. Anything else belongs to
  the unverified Phase 3 (2026-08-09) and is triaged before any new lane starts.
- Adversarially verify the four Phase-3 lanes that shipped unverified (script
  `<scratchpad>/phase3.js`, run id `wf_f3019378-f95` per memory). Every prior wave's
  verifier found something that would have shipped wrong.
- Confirm the shadow ledger is accruing: `include_board_all=True` volume policy should
  be producing rows nightly since 2026-08-09 (`.cache/betting/shadow.json`; gate-3
  `have` was 6 on 2026-08-10). If it is not accruing, that is a P0 in Lane B.

### W0.2 Owner/box actions this plan depends on (queue them now, do not block waves)
- **Box crontab install** for the close job (Lane A ships the runbook; owner runs it).
- **Box `rebuild_only`** to clear the 2-red baseline and restamp the golden
  fingerprint. Sequence per memory: rebuild, run_source_backtest,
  run_source_cohort_accuracy, build_site.
- **`tools/repair_sabermetrics_stint_rows.py --apply` on the box** (owed since
  2026-07-31; scope on `numTeams > 1`).
- Decide push timing for the 53-ahead branch (this plan adds more; recommend pushing
  after Wave 1 lands green).

---

## 3. Lane A: betting close capture + CLV (P0 infrastructure)

**Root cause, verified**: `betting_close_capture` is a watchdog row, not a job.
run_monthly step 9e calls `betting_export.snapshot_health(days=14)` over `.cache/odds/`
and files `ok = not red` (`run_monthly.py:2222-2232`); red is true whenever zero
close-kind snapshots exist (`betting_export.py:1259-1291`), which has been true
forever: all 5 snapshots on disk are kind="open". The real job,
`tools/betting_close_job.py`, has never executed anywhere: the only cron artifact is
`deploy/betting-crontab.example` (manual install, never installed), and
`logs/betting-close.log` does not exist. `decide()` is pure/tested and exonerated.

### A1. Box install path (primary)
- Extend `deploy/betting-crontab.example` into a verified runbook section in
  `deploy/WEBMASTER.md`: the `*/15 * * * *` TZ=UTC line (owner decision 2026-08-09,
  recorded in the job docstring), `/etc/eephus.env` sourcing, log path creation, and a
  post-install verification: run `tools/betting_close_job.py --why` once by hand and
  confirm the decision trace.
- Add `--selfcheck` to betting_close_job: prints UTC now, the computed slate, window
  anchors, once-per-slate state, and exits 0. The runbook has the owner run it after
  `crontab -e`.

### A2. Job heartbeat so the RED can name its failure mode
- The job writes `.cache/betting/close_job_heartbeat.json` (last_run_utc, decision,
  slate) on EVERY invocation including refusals. NEVER a data/ heartbeat: the box
  nightly runs `git checkout -- .` which reverts tracked files
  (`betting_export.py:1201-1207` documents this trap).
- `snapshot_health` gains a three-way diagnosis: (a) heartbeat absent or stale >24h =
  "close job is not running (cron not installed or dead)"; (b) heartbeat fresh but no
  close snapshot on a slate day = "job runs but never fires (window/anchor defect)";
  (c) capture fired but snapshot unreadable. Update the RED message accordingly;
  `test_betting.py:1318` pins the current string, so update that test deliberately.

### A3. Windows dev-box stopgap (temporary, owner-disabled later)
- `deploy/betting-close-task.ps1` + a `schtasks` XML that runs the same job every 15
  minutes; the wrapper sets UTC reasoning via the job itself (decide() is already
  UTC-pure; no TZ env needed).
- **De-dupe policy (owner decision)**: the stopgap runs only while
  `EEPHUS_CLOSE_STOPGAP=1` is set in the task definition. The runbook's final step,
  after the box cron is verified, is deleting the task. Two machines each have their
  own once-per-slate guard against their own cache; the credit budget is API-level, so
  the stopgap period plans for double spend: ~12 credits/day worst case, still under
  budget (verify with `betting_ingest.write_status` planned_monthly_credits math and
  update it to account for the stopgap).
- Note in the runbook: whichever machine captures the close must be the machine whose
  cache the grader reads. While the stopgap runs, the dev box is the grading
  environment of record; when the box takes over, its cache is. Do not merge caches.

### A4. CLV chain verification + edge cases
- End-to-end test with a synthetic close snapshot: `grade_record_clv` produces
  `data/betting_clv.json`, the client Record tab renders the decile histogram, and the
  close_snapshot publish blocker opens (`betting_export.py:1349-1489`).
- Verify `closing_snapshot`'s filename fallback tolerates the 2026-08-06 snapshot that
  predates `slate_date` (recon flag).
- The once-per-slate guard's fail-closed unreadable-snapshot stop must stay fail-closed
  (re-arming the 15-minute re-fire against the credit budget is the named defect).

**Honesty note for the copy**: CLV is unrecoverable for every slate before the first
close capture. The record page already says the close was never captured; after the
fix, the copy should state the start date of gradable CLV rather than pretending
history exists.

---

## 4. Lane B: betting model audit + improvement program

**State, measured**: the model is a fitted 5-input run regression (team Offense+ z,
opponent prevention z blending probable SEM+ with Bullpen+, park, home field) through a
Skellam margin (`betting_model.py:15-40`). It is UNVALIDATED and currently LOSES to
"always take the home team": n_graded 221/600, skill delta -0.000907, t=-0.248
(`data/betting_model_eval.json`, 2026-08-10). Gate 3 has 6 pooled settled rows, 0 tags
cleared; min_edge is None; picks ship on the PROVISIONAL_MIN_EDGE=0.06 policy floor.
The honest gate cannot open before ~May 2027. Owner posture: full program, keep
publishing provisional.

**The audit deliverable (B0)** is a doc, `docs/betting-audit-2026-08.md`: feature map,
ledger flows (record/shadow/calibration), gate states, credit budget, known-defect
table with receipts, and the benchmark definition below. Everything after B0 is a
pre-registered lab lane.

### B1. Market-anchored probability (the single most likely Brier gain)
Today the model prices from fundamentals alone and its probabilities lose to the
market-implied baseline. Add a market-blend layer: final_prob = shrink(model_prob,
market_fair_prob at OPEN), with the shrink weight fitted on the calibration ledger
(`.cache/betting/calibration.jsonl`, every priced side since 2026-08) via
forward-chained folds. Gate: proper score (Brier + log loss) with a
calibration/discrimination decomposition where a constant fails by construction, must
beat BOTH raw model and market-open baselines on held-out slates. Edges are then
computed against the CURRENT market from the blended probability, which mechanically
shrinks fabricated edges. Pre-register that the blend weight may go to ~0.8+ market;
that is a finding, not a failure. NOTE: `_market_view`'s de-vig discipline
(consensus-point-first, min-hold fair book, staleness guards,
`betting_export.py:1949-2114`) is reused verbatim; never re-shop lines per side.

### B2. Platoon/splits feature (rides Lane C data)
- Schema-3 vintage columns (see C4): lineup-vs-hand offense composite + probable-hand.
  Copy the park precedent exactly: SCHEMA bump, null on old records, explicit neutral
  fallback, per-game marking, no silent live borrow (`leaderboard_vintages.py:142-175`).
- Both live and vintage paths MUST route through `_assemble_team_inputs`
  (`betting_model.py:435-483`); a second standardization path is the named failure mode.
- The feature's honest clock starts at n=0 (split aggregates were never captured; git
  backfill is impossible). Pre-register the refit as a CANDIDATE alongside the
  incumbent; it can ship into the provisional board only if it beats the incumbent on
  the contaminated-forward diagnostic AND does not degrade calibration; the honest
  verdict waits for the vintage clock.

### B3. Rolling form (rolling xwOBA, hot/cold)
- Team rolling xwOBA (14/30-day windows) from Savant/StatsAPI, captured as new vintage
  columns (same schema-3 bump as B2, one coordinated schema change).
- Pre-registered gate with a permuted-team control; the literature prior is that
  short-window team form adds little; expect a small or null effect and record it
  either way. Never fold a live rolling stat into pricing without a vintage column.

### B4. Availability: injuries + lineup strength
- Feature candidates: starting-lineup strength vs season aggregate (uses the daily
  lineups already fetched for props), star-out indicator from IL data, probable-pitcher
  change-after-open flag (a classic CLV driver).
- Same vintage discipline; same pre-registered candidate protocol as B2/B3.

### B5. Calibration layer
- Fit a global 2-parameter Platt/temperature layer on the calibration ledger (the eFV
  odds precedent: slope repair with zero cohort info). Gate: proper score + reliability
  diagram deciles on held-out slates; ships into served probabilities only if it beats
  identity. This is separate from B1 (B1 changes the information set; B5 repairs the
  response scale).
- Re-run the dispersion sweep only under the amended both-runline-sides criterion and
  the all-three-quantiles ship rule (`betting_model.py:143-228`); flipping
  `SERVE_RUN_DISPERSION` requires the constant + tripwire + eval block in one commit.

### B6. Benchmarks ("beat other top models")
Define and publish on the validation tab: (1) home-team constant (current baseline),
(2) de-vigged market open, (3) de-vigged market CLOSE (the gold standard; becomes
measurable when Lane A lands), (4) a simple Elo built from game results only
(implemented internally, no scraping). The model's public claim ladder: beat (1), then
(2), then hold its own CLV vs (3). Never claim a tier that is not measured. CLV
percentile vs close becomes the headline once close capture accrues.

### B7. Props value bets (owner: capped pull)
- `betting_ingest` gains a per-event props mode: for 2-3 selected games/day (the POTD
  game + the largest team-market edges), pull player-prop markets; extend
  `credits_for` and `write_status` budget math; hard monthly guard so the pull skips
  itself before it would breach the tier.
- Value computation reuses the exact team-bets discipline: consensus point first,
  min-hold fair book on that line, staleness/hold/consensus-distance rejection ledger,
  push handling on the row, edge/EV/Kelly columns. Props edges live under NEW shadow
  tags (`props_*`); min_edge is swept per tag and NEVER pooled with team tags
  (`betting_model.py:2557-2563` discipline extends to props).
- The props tab gains a "Value" sub-table with the same best-value badge + provisional
  labeling contract as team bets (`pick_meta.provisional`, policy-floor note). The
  fair-lines tables stay, labeled model-only where no book line was pulled.
- Platoon upgrade rides Lane C: price hitter props off `orders.vl` when the opposing
  probable is a LHP (today props read `orders.vr` only with a published vs-RHP
  assumption, `betting_export.py:2475-2568`).
- Update the shell/client/test three-file tab contract if any tab changes
  (`build_site.py:4209-4216`, `betting.js SECTIONS:40`, `test_betting.py:1029`).

### B8. Wiring + honesty rails
- New scheduled steps land in `run_monthly.SCHEDULED_EXPORTS` (self-filed ok) or their
  RED rows are dropped at drain time; never in SCHEDULED_GRADE_SOURCES.
- The trust topline ("this model is NOT validated") stays until gate 2 turns positive;
  every model change updates `data/betting_model_context.json` provenance; the
  600-game constant is pinned and must NOT be re-derived from drifting margins
  (`betting_model.py:341-358`); if the owner ever wants the clock re-derived, that is
  section 15's fence 8-adjacent and needs its own pre-registration (the E_cond-style
  paired re-derivation was offered and NOT selected this cycle).

---

## 5. Lane C: L/R splits for HEM+/SEM+/REM+ (full program)

**Feasibility, verified**: StatsAPI `stats=statSplits&sitCodes=vl,vr` works bulk at
MiLB sport ids (164-file `.cache/milb_platoon` archive) and per-person at MLB
(`pal_export.py:136-158`); split payloads carry every counting stat HEM+/SEM+/REM+
need. `bat_side` is now stamped 697/697 and pitcher hand is one bulk call
(`pal_export.load_pitch_hand`).

### C1. Data: bulk MLB splits fetch + cache
- One-call probe first: confirm the BULK statSplits endpoint paginates at sportId=1
  (tree proves MiLB bulk + MLB per-person; the bulk MLB path needs the probe before
  committing). Fallback: per-person ThreadPool like pal_export, bounded to the
  qualified pool.
- New fetcher in `fa_sources` (sibling of `fetch_statsapi_season_stats`) with its own
  lean cache dir `.cache/mlb_platoon/{group}_{season}.json` (the park_line_lab
  pattern; `scrapers._fetch` cannot host pagination). Nightly fetch wired into step
  9e-pre0; filed under SCHEDULED_EXPORTS.

### C2. Metric labs (pre-registered, one per metric family)
- **Estimand registration must be distinct from W-PLATOON** (which FAILED for prospect
  eFV forward value and is one-attempt-spent; `docs/efv-2026-07-24/GATES.md:69-84`).
  The new estimand is MLB in-season vs-hand skill and its forward stability, plus its
  value as a betting/props input. State this in the gate doc explicitly.
- Design decisions to pre-register (not decide by results): serve DISPLAY columns as
  true vs-L/vs-R indices with per-split pools (league vs-LHP exposure is
  platoon-selected, so pools must be per-split); the GATED forward claim rides the
  shrunk platoon-GAP overlay (gap stabilizes far slower; The Book approach). K
  constants for split rates re-derived by lab sweep, not assumed; HEM_SPREAD_GAIN is
  NOT applied to splits (it was calibrated on full-sample spread); qualification
  floors roughly halve per split and the vs-LHP side will be thin (~25-30% of PA),
  disclosed on the column tooltip.
- FIP denominator care: a batter-hand split's innings are outs-vs-that-hand; use a
  per-TBF rate formulation so cfip derivation never mixes denominators
  (`rem_plus.py:214-217`).
- Each shipped variant incurs the full model-hygiene checklist (section 14): registry
  row, eval artifact, MODEL_GLOSSARY, glossary entries with Arkmetric attribution.

### C3. Leaderboard UI
- New vs-L/vs-R columns or a splits sub-view per board (mlbstats.js), with sample-size
  chips and the platoon-availability disclosure posture reused from
  `hitter_export._platoon_availability`. Sortable, glossary-tooltipped, on the
  existing `.mlbstats-table` dialect. Phone: columns join the existing horizontal
  scroll container; never widen the page.

### C4. Betting/vintage integration
- Schema 3 in `leaderboard_vintages.py`: add lineup-vs-hand composite columns +
  probable-hand to TEAM_COLUMNS/PITCHER_COLUMNS in ONE bump shared with B3's rolling
  columns (a single schema migration, not two). Old records read as null with explicit
  neutral fallback and per-game marking, park-precedent style.
- `fantasy_schedule`'s probable block carries only {mlbam, name}; join hand via
  load_pitch_hand at assembly, never a second fetch path.

### C5. Supersede the heuristic platoon lens
- `hem_plus._platoon_adj` (PLATOON_ADV=4.0) exists because there was "no split HEM+
  yet" (`hem_plus.py:285-290`). Where real split indices exist, the lineup builder and
  props switch to them; the heuristic remains only as fallback for unstamped players,
  disclosed. Re-check every consumer of `orders.vr/vl` and `platoon_adv`
  (betting_export props, assets/mlbstats.js) in the same wave.

---

## 6. Lane D: Baseball America levers (gated only)

**Standing constraints (do not cross)**: BA never enters `SCORED_SOURCES`
(`source_backtest.py:64`; the one global common set collapses 4,284 -> 295 and flips
`consensus_wins`); zero consensus weights ship (0 of 200 admissible reweightings beat
the served consensus; oracle ceiling +0.004 rho); the eFV head-to-head is NULL under
both estimators and `XFV_HEADTOHEAD_MDE95=0.0352` is not stale; BA is
`scoreable_from_run_year: 2027` under MIN_LAG_YEARS=3. The honest statement of the
"absolute data ceiling" ask: the rank frontier is measured CLOSED; the open levers are
calibration, risk, tools, and scoring-basis design, below.

**Data inventory, verified 2026-08-12**: 4,597 BA rows in `snapshots` (4 preseason
vintages + 2026-06-03 rank-only + 2026-08-05 Top 100 + 2026-08-10 midseason), 4,456
carrying tools_json; per-row RISK lives at `tools_json._extras.ba_risk` with an
era-varying vocabulary: High 2,087 / Extreme 1,004 / Average 767 / Medium 367 /
Mild 127 / Very High 92 / Low 12. `draft_snapshots.risk` is first-class (High 758 /
Med 435 / Low 151). BA tool grades sit in the standard slots plus `ba_tools_raw`.
`adjusted = raw - 5*risk_ordinal` exactly, so raw+adjusted+risk carry TWO degrees of
freedom; risk is the one new dimension.

### D1. Risk normalization + the p_bust lever
- Ship `ba_risk_ordinal`: a single normalization map for the 7 observed labels
  (Low < Mild/Medium/Average < High/Very High < Extreme; resolve Medium-vs-Average and
  Very High-vs-Extreme per era by checking which vintages use which vocabulary, and
  pin the map with a test that fails on any unseen label).
- Pre-registered gate: does BA risk add out-of-sample bust discrimination BEYOND
  consensus FV + eFV features? Power check FIRST: the resolvable BA-graded outcome
  rows are thin (2023 vintage resolving 2026+); if the MDE swamps any plausible
  effect, the lane records "underpowered until <year>", wires the feature dark
  (computed, not consumed), and sets the registry revival clock. If powered, the seam
  is the bust-probability chain (`efv_odds_calibration` inputs or the bucket
  assignment), NEVER a new consensus weight.
- The risk-conditioned bucket/surplus recalibration is registered as a DISTINCT
  question from B-L5's IDR (which is NO_SHIP on Holm); it conditions on risk rather
  than refitting the marginal maps. Same power-check-first rule; expected verdict this
  cycle is "prep + clock", and that is an acceptable ship.

### D2. BA tool votes into Tools+ / tool_xfv
- First fix ingestion: 35 tool-slot collisions silently dropped a grade with an
  arbitrary keep (32 sweeper-over-slider, 3 split-over-changeup). Deterministic rule:
  keep BOTH under distinct slots where the schema allows, else keep the max with the
  dropped grade recorded in `_extras`; pin with a test.
- Re-run the pre-registered tool gate (the 2026-08-06 paired-bootstrap MDE gate whose
  hitter arm FAILED and reverted to grade-only) with BA votes added to the tool pool.
  New data = legitimate reopen; the gate doc must cite the prior verdict and register
  ONE attempt. If it fails again, tool_xfv stays grade-only and the loss is recorded
  on the registry row.

### D3. The fence re-derivation: SCORED_SOURCES common-set design (owner pick)
- Pre-register `docs/SOURCE_SCORING_BASIS_GATE.md`: replace the single global common
  set with per-pair common sets (each source scored on its pairwise overlap) or
  matured-subset scoring (each source scored on its own resolvable base years with
  explicit selection disclosure). Acceptance criteria, registered before any code:
  (a) the new basis REPRODUCES the current FG/MLBP ordering and verdicts on the old
  common set (regression control); (b) BA gets scored only on its resolvable years
  with its retention/selection printed beside every number; (c) `consensus_wins` and
  every public claim stay on the OLD registered basis until the 2027 vintages mature
  (no verdict laundering); the new basis ships as a labeled additional view on the
  source-accuracy page.
- Expected value: honest BA accuracy numbers years earlier than 2027, and a scoring
  page that stops needing the common-set-collapse footnote. Expected risk: per-pair
  bases are non-comparable across sources; the gate doc must pre-commit the
  presentation so readers cannot cross-compare bases by accident.

### D4. Cycle hygiene
- Measure the midseason-vs-preseason grade-normalization cell question (registered
  threshold: >3.0 FV apart means separate cycles; memory says this was never
  measured). File the answer in the consensus notes either way.
- 2027 accuracy-weighting prep: confirm the registry revival clocks (BA risk 2027-28,
  vintage-disciplined precision A/B 2027) are rows in the registry with owners and
  trigger conditions, not just memory.

---

## 7. Lane E: eFV rookie-window unlock + pitcher parity

### E1. Rookie-window unlock (owner decision 3)

**Mechanism, verified**: there is no lock flag; the freeze is architectural.
`efv_score.run_backgrade` (2346-2618) re-scores graduates every cycle but anchors at
the last snapshot strictly BEFORE `debut_date` (2406-2414) with the MiLB year pinned
to debut year; graduates left the actives universe so `run_live` never sees them.
Sources keep grading until rookie eligibility exhausts, so 209 players already carry
post-debut board points we ignore (`xfv_postdebut_anchor` rows).

Implementation spec:
- **Serve-path only.** The unlock changes run_backgrade's point ADMISSION for
  kind='debuted': admit points with `snapshot_date <= eligibility_exhausted_date`,
  where eligibility_exhausted_date = the date cumulative MLB AB > 130 or IP > 50
  (compute from StatsAPI game logs or season splits; if only season granularity is
  available, use season end of the crossing season and disclose). The 45-day roster
  criterion is NOT computable here (`active_roster_days` is not service time, standing
  memory) and is disclosed as an approximation.
- **Training/eval frames untouched.** `efv_dataset._asof_point` and every training
  cutoff stay pre-debut (leak-guard tests `test_efv_export.py:718, 735` pin them).
  This is the B-L6 frame-drift lesson: the eval basis must not move. State in the gate
  doc that eval cuts remain on the pre-debut basis by design.
- **Drivers freeze at debut.** run_backgrade computes TWO rows per graduate: the
  debut-anchored row (produces `factors`/`factors_more`, persisted) and the
  rookie-window row with milb_yr still pinned to debut year (produces the grade).
  MiLB legs freeze naturally; only the consensus-anchor leg moves. Tag rows
  `xfv_rookie_window: true`; keep `xfv_postdebut_anchor` for the fallback shape.
- **WAG pin.** `storage.py:10286-10288` sets the WAG baseline from the served grade
  "locked at debut"; make that literal: persist the at-debut grade and pin WAG to it,
  so the unlock cannot silently move WAG (the future-leak is contained only by the
  lambda pins; do not feed it).
- **Basis coordination.** Add the debut-anchor/rookie-window rule to
  `storage.board_basis_fingerprint` (it currently does NOT encode the anchor rule), so
  the movement-suppression gate covers the transition run.
- **Bust rows untouched** (kind='bust' shares run_backgrade; scope by kind).
- **Retroactive at next regen** with a movers table: how many of the 2,554 debuted
  rows move, by how much, worst 20 with receipts. Trade-machine/prearb pricing reads
  `surplus_source='xfv_backgrade'`, so dollar moves are part of the disclosure.
- Registry note on xfv_hitter/xfv_pitcher rows + a glossary methodology update
  (the lock line in the prospx UI copy and the 🔒 tooltip semantics change to
  "locked when rookie eligibility exhausts").

### E2. Pitcher share: audit, then cross-side parity (owner decision 9)

**Measured 2026-08-12**: eFV Top 100 has 8 pitchers; consensus Top 100 has 27. In the
consensus-top-300 band the mean eFV-minus-consensus is +1.96 FV for hitters and -0.17
for pitchers: the share gap is hitters being PROMOTED past pitchers, not pitchers
being marked down. Whether that is signal or miscalibration is exactly what E2a
answers.

**E2a. WAG-relative audit (read-only, pre-registered, runs first)**
- Per-side calibration of eFV E[6yr WAR] against realized WAR on the resolved frame
  (reliability curves by side and FV tier), and the same for consensus FV. The
  owner's framing is binding: source bias is measured against REALIZED OUTCOMES, not
  against other sources; a source is not "overinflating pitchers" if pitchers deliver
  the WAR it forecasts.
- Where does the shared `realized_implied_fv` map put each side: is the WAR->FV
  inversion fit pooled (hitter-dominated at the top) or per-side? Quantify the Top-100
  share under (i) the current map, (ii) value parity, (iii) percentile parity.
- Case receipts: the Dzierwa class (pitchers the model flagged before the industry).
  Verify the early-call record is real (as-of dates) and check whether the model's
  current pitcher rankings still contain that signal (rank-level, since memory says
  pit full_pool rank delta is positive while the LEVEL sits low).
- Publish the audit as `data/xfv_side_calibration_eval.json` + registry row.

**E2b. Cross-side parity ship (gated on E2a, one coordinated epoch)**
- Definition (locked): at every served FV, the within-side percentile equals the
  within-side percentile consensus assigns for that side. Implementation: a per-side
  monotone display recalibration of the WAR->FV grade map; within-side order is
  UNCHANGED (rank-invariant per side); cross-side interleaving moves toward industry
  convention. Underlying WAR, buckets, and surplus EV stay pure-model.
- **Fence check** (section 15): quantile mapping was REJECTED as the served map for
  cross-SOURCE consensus harmonization. This is a different object: a cross-SIDE
  display convention inside one model, owner-directed. Cite the distinction in the
  gate doc so the ledger is not violated silently.
- Blast radius to handle in ONE epoch (the R1 pattern: every basis moves together
  inside `vf.valuation_set`): board order (pitchers rise), golden fingerprint
  (restamp on the box, already owed), farm composites and $DvM+ (ride xfv_grade),
  `_reprice_surplus_on_display` quantile path (all THREE call sites,
  `efv_score.py:1584/2219/2600`), WAG baselines (pinned by E1), movement basis
  fingerprint (bump), `test_board_grade_comes_from_the_outcome_curve` (all three
  writer paths go through the same new seam or the test is updated deliberately),
  and the E1 unlock (ship E1 and E2b in the SAME epoch so graduates re-anchor once,
  not twice).
- Disclosure: board copy explaining the parity convention; the grade explainer names
  it; movers table by side; honest note that this is a display-comparability decision,
  not an accuracy claim, UNLESS E2a found true miscalibration, in which case the
  recalibration is an accuracy fix and says so.

---

## 8. Lane F: Arbitration Predictor theme + logos + data completeness

**Verified**: the page is mostly on-theme already; the off-theme elements are the club
filter `<select id="arb-team">` (native UA select in system font,
`arbitration.js:259-277`), and two unclassed native buttons `#arb-retry` (227) and
`#arb-clear` (282). Team logos: `EEPHUS_HUB.teamLogo()` (ESPN CDN pattern,
`eephus-hub.js:47-60`) is ALREADY LOADED on the page and unused.

- **F1**: restyle the club select by joining the existing selector family: wrap the
  filter bar so `.mlbstats-bar select` applies (site.css:2124-2127 precedent:
  font-retro-mono, bg-secondary, 1px var(--border)), or add `.arb-app select` to that
  rule block. Retry/Clear become `button.chip` (`.fa-app button.chip` family,
  site.css:1594-1617, gold active border). No new styling language; tokens only; no
  border-radius (dead under the universal rule anyway); no literal colors
  (arbitration.js:11-13 pins tokens-only).
- **F2**: team logos via `EEPHUS_HUB.teamLogo(org)` in the board's Club column and the
  Team View table (and the club select's adjacent header once a club is filtered).
  Check the ladder strip's fixed 62px column alignment tolerates the 17px logo on
  phones (arbitration.js:49-57); if not, logo goes in the section header instead.
  ESPN CDN dependency is the established site-wide pattern; keep `onerror` removal.
- **F3 (data completeness, carried debt)**: `scrape_spotrac_team_contracts` never reads
  the fourth table (`id="table"`, optioned players), which is why the
  arbitration-board/projection-board overlap was 0 and GATE C is blocked. Widen the
  table set behind its own byte-diff guard, measure recovery, THEN run the
  pre-registered GATE C C1-C6.
- **F4**: verify against section 13's theme checklist and the scaffold tests
  (`test_arbitration_scaffold.py`); mobile pass (pointer:coarse 44px targets).

---

## 9. Lane G: positional adjustments audit + export for Will

**Verified state**: the ladder is a BRef runs_position/650PA inversion on innings
shares (`positional_fit.fit_ladder`), exposure-weighted sum-to-zero IMPOSED and
measured at machine zero; the displayed fielder-centred column's 8 fielding rungs sum
to -0.01 (2dp rounding of exact zero) with DH below the line at -15.18 tagged "not in
the sum"; the old 9-rows display bug is FIXED and pinned by
`test_positional_ladder_sum.py`. Current values (model basis, 2021-2026, n=2023,
R2 0.9737): C +10.88, SS +9.38, 2B +5.12, CF +4.14, 3B +3.62, LF -6.39, RF -6.52,
1B -8.40, DH -13.70.

- **G1 (real bug found by recon, fix it)**: the folklore comparison never rescales
  bases: fitted values are runs/650 PA, the Tango table is per-162-games (~700 PA),
  and both the artifact's `folklore_ladder` diff and pal.js's Difference column
  subtract them directly, overstating folklore magnitudes ~7%. Rescale folklore by
  650/700 in the comparison (label it), artifact + pal.js + tests together.
- **G2 (accuracy)**: the era question is live: era_splits move SS 8.62 -> 9.65 across
  2021 -> 2024-26, and `prospect_def_value.py:120-123` records the shipped spec LOSING
  OOS on the 2019-2026 universal-DH era to a residual spec. Pre-register ONE
  re-examination through the existing recency-gate framework
  (`docs/gate-2026-08-07-positional-ladder-recency.md` pattern): does a universal-DH
  era window (2022+) beat rolling-6 forward? If yes it ships through the same gate;
  if no, publish the DH-era sensitivity as a labeled secondary column in the export.
  The one-owner rule is absolute: `positional_fit.fit_ladder` is THE fit; the export
  never refits.
- **G3 (export)**: new top-level `positional-adjustments/` folder (repo root, beside
  prospect-tracker/):
  - `positional_ladder_v1.json` + `positional_ladder_v1.csv` + `README.md`.
  - Content: BOTH bases explicitly labeled (`values` exposure-weighted zero, what
    internal valuation uses and what matches the bWAR/eWAR frame;
    `values_fielder_centred` folklore-comparable, DH outside the sum), the
    identification block (all three sums with the explanation, so a receiver cannot
    "correct" the -1.87 unweighted sum into a bug report), ci95, seasons, n, min_pa,
    R2, method string (BRef INVERSION, not Statcast, and what that means for SDR
    work), era_splits, window_sensitivity, the rescaled folklore comparison, the
    `fit.signal` per-position k_inn reliability constants (ewar.py consumes exactly
    those; SDR shrinkage will want them), dh_exposure_spec, and provenance
    (artifact date, gate references, registry model_id `positional_ladder`).
  - Builder `tools/export_positional_ladder.py`: read-only slice of
    `data/positional_fit.json`; a test pins slice == artifact; version bumps are
    manual and append a CHANGELOG line in the README. The folder is repo-only:
    confirm it is NOT in `deploy/publish_paths.txt` and does not enter the site build.
  - README states the intended consumer (Will's eWAR + SDR) and the basis-choice
    guidance (use `values` for anything riding the bWAR frame).

---

## 10. Lane H: GFX Top-100 tiles read top-to-bottom

**Verified**: the Tiles ("chips") layout builds a CSS grid that fills row-major
(`prospx/index.html:36032`), while the Rows layout is already column-major by design
(35975-35999, "ranks read top-to-bottom down a column").

- Reorder tile emission column-major using the SAME geometry the search scored:
  with `rows = fit.rows` from `_gfxTileGeoFor`, place item i at
  column = floor(i / rows), row = i % rows (i.e. #1-#10 down column 1, #11-#20 down
  column 2 for a 10-row grid). Two equivalent implementations: reorder the array into
  row-major paint order, or emit explicit grid-column/grid-row styles; prefer the
  array reorder (keeps the grid template untouched). The last column may be short;
  ranks must stay contiguous within each column.
- Update the comment block to match the Rows layout's language; keep
  `_gfxWarnUnnormalized` behavior; verify the overflow computation (36021) is
  unaffected (it depends on rows x cellH only).
- Verify across counts (10/25/50/100/200-cap), formats (1080/wide/landscape), and the
  photos toggle. Add or extend the existing GFX test coverage if a JSDOM-style test
  reaches this renderer; otherwise verify with the headless-browser harness used for
  prior GFX work and record the check in the lane notes.

---

## 11. Lane I: polish + hygiene sweep

- **I1**: fix the run-summary double write: `main()` stamps the 74MB timeseries.json,
  then the chained run_daily stamps it again (the file the two-writer race truncated
  once). Move the stamp after the chain with a fallback.
- **I2**: commit the chunked suite runner to `tools/run_suite.py` (it currently lives
  in per-session temp dirs that Windows purges); keep the 8-files-per-chunk floor and
  return-code discipline in its docstring.
- **I3**: gitignore `.claude/settings.json` (the only untracked item making status
  dirty).
- **I4**: off-theme control sweep: grep every module page for native `<select>` and
  unclassed `<button>` outside the token families (the arb defects generalize); fix
  within existing selector families only. Also sweep for literal colors added since
  the last audit (`test_client_uses_theme_tokens_for_colour` pattern).
- **I5**: betting feed-health strip: after Lane A lands, verify the "close NEVER
  CAPTURED" all-caps state transitions correctly to the healthy state and the copy
  names the CLV start date.
- **I6**: mobile/phone pass on every surface this plan touches (arb filter bar, new
  leaderboard split columns, props value table, GFX preview): pointer-coarse target
  sizes, horizontal scroll containment (wide content scrolls inside its container,
  the page never scrolls horizontally).
- **I7**: glossary entries for every new user-facing metric/term this plan ships
  (split metrics, parity convention, props value bets, CLV) with correct shelf +
  attribution; `EEPHUS_GL.wire` tooltips on new columns.

---

## 12. Wave Z: close-out protocol (every wave feeds it)

1. `python tools/gen_audit_docs.py` after any registry/nav/source change.
2. `python tools/copy_lint.py --check` (0 em-dash, 0 hard fails).
3. Chunked suite between waves; verdict = chunk return codes; expected baseline 2 reds
   until the box rebuild, then 0.
4. Classify and revert data/ churn per wave; leaderboards and wire_fv_first_seen.json
   are known churn files in this sandbox.
5. Movers tables + disclosure copy for every serve-path change (E1+E2b epoch, C3
   columns, B7 props).
6. Registry/catalog/pinned_by receipts verified (a receipt must name a test that
   actually asserts on the artifact).
7. Commit per lane with descriptive messages; the branch push (53+ commits) is an
   owner action queued in W0.2.
8. Update the execution memory file and MEMORY.md index (the orchestrator owns this).

---

## 13. Theme checklist (Y2K retro cybergothic / newspaper-baseball-card)

Everything user-facing this plan ships must pass:
- Tokens only, zero literal colors; every var() referenced must be defined (the
  currentColor fallback bug class). Light = warm paper #F4F0E6 family; dark =
  near-black refractor with phosphor starfield; both palettes live at site.css:59+
  and are MIRRORED in prospx/index.html :root (edit together).
- No border-radius anywhere (universal `!important` zero at site.css:236; local radii
  are dead code and forbidden).
- Fonts through --font-retro / --font-retro-mono / --font-logo only; stack order is
  test-pinned (test_board_card_typography.py).
- Hairline 1px borders via --border/--border-light; dim text via --text-dim color,
  never opacity; gold reading text uses --text-gold bronze, fills keep --accent-gold.
- Tables join the `.mlbstats-table`/`.mlbstats-scroll` dialect; selects join
  `.mlbstats-bar select`; buttons join `button.chip`; team logos via
  `EEPHUS_HUB.teamLogo` with `.eephus-teamlogo`.
- Injected-style house pattern for module CSS (betting.js:2411 model); dark starfield
  and light newsprint texture are mutually exclusive by design.
- Copy: no em-dashes, no LLM ban-list words, Arkmetric attribution on new entries,
  disclosure beats pretense (label provisional, label assumptions, label sample size).

## 14. Model-hygiene checklist (every new metric/model/eval)

1. Pre-registered gate doc committed with empty Results before the lab exists.
2. Lab under tools/ with seeded bootstrap, offline-capable via caches.
3. `data/*_eval.json` artifact; registry row (indent=1) with valid verdict/artifact
   pairing; MODEL_GLOSSARY decision; gen_audit_docs regen; data_catalog row with
   `stability`; honest pinned_by or none.
4. Losses are committed as loss ledgers on the registry row, not deleted.
5. New scheduled steps in run_monthly.SCHEDULED_EXPORTS (never
   SCHEDULED_GRADE_SOURCES); RED paths proven end to end under the `__main__` launch
   shape.

## 15. Banned ledger (do not re-propose; reopen burden = new data or owner instruction)

Consolidated at `docs/master-plan-2026-08-05-omnibus2.md:84-143` plus later additions.
The ones adjacent to this plan's lanes:
- RP->SP event-set expansion (e3-rp-sp-closure.md:66).
- consensusRank / Plackett-Luce over lists (J1 NULL/FAIL).
- Quantile-map/OT as the served CONSENSUS harmonization map (mechanistically
  explained). E2b's cross-SIDE display parity is a different object and must cite
  this distinction.
- K-prior; Statcast-into-projections blind port; blend-lambda shifts
  (TOST RULED OUT 0.65/0.60/0.51); the `fv` feature-add (TOST RULED OUT).
- Consensus source reweighting (0 of 200 beat served; weights stay `{}`; reopen only
  via the 2027 vintage-disciplined A/B beating its MDE).
- W-PLATOON prospect-eFV platoon features (FAILED, one-attempt-spent). Lane C
  registers a DIFFERENT estimand (MLB in-season, betting/props).
- BA into SCORED_SOURCES on the CURRENT basis (Lane D3 re-derives the basis itself
  under pre-registration; until that gate ships, the fence stands).
- Re-deriving VINTAGE_MIN_GRADED_GAMES=600 from drifting margins; floor-shopping a
  third eFV estimator; ECE-only calibration gates; summing ML quantile points;
  eFV tail fix; ETA feature; hard-coded accuracy numbers in copy.

## 16. Sequencing

- **Wave 0** (serial): W0.1 baseline + Phase-3 verify debt; W0.2 owner/box queue.
- **Wave 1** (parallel, exclusive files): A (close capture), F (arb UI + Spotrac),
  G (pos-adj audit + export), H (GFX tiles), I1-I4.
- **Wave 2** (labs + data, parallel): C1-C2 (splits fetch + labs), B0/B1/B5 (audit,
  market blend, calibration), D1-D2 labs, E2a audit, E1 implementation behind a flag.
- **Wave 3** (gated ships): C3-C5 (UI + props platoon + heuristic supersede), B2-B4
  (schema-3 features, one coordinated schema bump), B6 benchmarks, B7 props value
  bets, D3 basis gate, E1+E2b as ONE coordinated serve epoch with movers disclosure.
- **Wave Z** after every wave; final close-out at the end.

Estimated program shape: ~5 waves, 20+ lanes, every gated lane capable of returning a
null that ships as recorded knowledge. The plan's success condition is not "every
number improved"; it is "every shipped change verified, every claim floored, every
null honest, and the seven owner asks either delivered or measured to their ceiling
with receipts."

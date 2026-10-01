# Master plan 2026-09-24: the final pass before the port

Written for: the executing agent (Opus 5.5) that will carry this plan out, with the owner
answering decisions in chat. PLAN ONLY at commit. Branch `efv-conviction-2026-08-08`, HEAD
`c78f1e7c` (2026-09-24 01:38 -0400), 371 commits ahead of `main`, nothing pushed, the only
remote is the OLD one (github.com/aiyer9175/eephus.io). Written to the standard of
`docs/master-plan-2026-09-09-fangraphs-ewar-betting.md` and `docs/EFV_GATE_STANDARD.md`:
every number below carries the artifact path or file:line it was read from; every item
names its files, its test, its gate or owner decision, and its effort; nothing in this
document was measured behind a clock.

The owner's ask (2026-09-24, verbatim intent): audit, upgrade, improve, optimize and
perfect every module, model and metric and the site as a whole; make sure everything works
as intended, is on theme, and checks out mathematically and economically; ship every
improvement that is on-theme and useful; this is the final pass before the local site is
ported to the production repository, so clean the code and make sure everything is wired
correctly; bring every module to the PROSPX bar; make the site cohesive with easy
navigation; make every model and metric industry-leading by the widest mathematical gap
possible, verified, and maximized for Spearman / AUC / logic up to the data ceiling; wire
modules into each other where it helps; find public data sources and metrics not yet used;
expand tables and features; improve layout; ask design questions in chat.

The plan has eight parts.

- Part 0: how to execute this plan (read first; the rules that have cost sessions).
- Part 1: the state pin (what is true on 2026-09-24, verified).
- Part 2: the constraints: locked decisions, do-not-reopen, the clock calendar.
- Part 3: the industry scoreboard: where we lead, tie, trail, and the legit next test.
- Part 4: the module program, one section per module (defects, upgrades to the PROSPX bar,
  wiring, measurements, decisions).
- Part 5: the cross-cutting programs: math and economics, wiring, data sources, UX parity,
  copy and claims, code hygiene and port readiness.
- Part 6: waves, dependencies, and the definition of done.
- Part 7: the owner decision queue, with a recommended default for each.

The census bundle (20 lanes plus critic gap lanes, adversarial verification, drafts) lives
at `C:/Users/noah/baseball-projects/_finalpass_2026-09-24/` (copied from the session
scratchpad). Each lane directory holds `FINDINGS.md` (long form with evidence),
`served_state.md`, `SECTION.md` (the draft this document's Part 4 and 5 were built from),
screenshots, and any probe scripts. The workflow script is `census.js` in the same bundle.

---

## Part 0. How to execute this plan

### 0.1 Read these before touching anything

1. This document, whole.
2. `docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` (the epoch program this
   plan sits inside; its section 5.1 is the clock calendar this plan inherits).
3. `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` (registered, results empty; it governs
   every fitted rebuild).
4. `docs/master-plan-2026-08-19-holistic-audit.md` section 2 (do-not-reopen, 18 items).
5. `C:/Users/noah/baseball-projects/_audit_2026-09-09/DECISIONS_FOR_OWNER.md` (every
   answered and open decision since 2026-09-11; append this plan's answers there too).
6. `docs/port/PORT_SPEC.md` sections 0, 1.8, 5.2 and gates A to E (the port this pass
   precedes; Part 5.6 of this plan feeds its Phase 0).
7. The memory index (`MEMORY.md`) rows under "Standing rules and traps".

### 0.2 The rules that have cost whole sessions (non-negotiable)

- **One writer at a time in the repo tree.** `conftest.py` snapshots dirty files at
  pytest session start and restores them at session end, so a pytest session running
  while another lane edits or a pipeline writes REVERTS those writes silently. Run
  `python tools/run_suite.py` from `prospect-tracker/` only between edit batches, never
  during a regen, retrain or export. Parallel work is allowed only as read-only authoring
  (patch + report to the scratchpad, applied by the main loop one at a time) or in a git
  worktree that holds its own copy of the gitignored artifacts.
- **Patches.** Apply from the repo root with `git apply --directory=prospect-tracker -v`
  and read the output for "Checking patch prospect-tracker/..." (a patch applied from
  inside the subdirectory skips every path and exits 0). Working-tree files are CRLF;
  never pass `-c core.autocrlf=false`. Two patches sharing a file: apply one, commit, then
  the other (`git add <file>` sweeps both hunks into the first commit).
- **Heredocs mangle backslashes on this box.** Write files with the Write tool or build
  the backslash with `chr(92)`.
- **After any `proj_export` run, run `tools/export_trade_values.py`** before
  `test_calibration_vintage` (a one-cycle lag, not a defect).
- **After any edit to `assets/site.css` or a shared runtime**, call
  `build_site.restamp_hand_authored_pages()`; the hand pages carry a content-hash stamp.
- **A JS comment naming `x.json` lands in SITE_MAP.md** (the generator reads comments).
- **Never sum ML quantile points.** Team roll-ups sum champion means.
- **Grades round UP** (FV and tool grades ceiling); eFV and every plus stat round nearest.
- **Copy:** no em-dash anywhere (run `python tools/copy_lint.py --check` and
  `python tools/strip_emdashes.py --check` before every commit that touches copy or a
  served label); terse, math-first voice; the ban list in `tools/copy_lint.py`; scraped
  scout reports are third-party and are cleaned, never re-voiced.
- **Every new model ships with a `data/model_registry.json` row and a committed eval
  artifact** (test-enforced). A failed challenger is a block inside the parent artifact,
  never a standalone `*_eval.json`.
- **Every accuracy claim derives from an artifact.** Hardcoded accuracy claims are a
  banned defect class. Copy may say eFV is indistinguishable on discrimination; it may not
  say eFV discriminates better.
- **Looking early disqualifies.** Part 2.3 lists every clock. A measurement taken before
  its date is not a weak result, it is a spent look and the candidate is dead.
- **Do not push. Do not configure the new remote.** The owner pushes; the port is a
  separate session (`port-to-git-eephus-io` memory, DEFERRED by the owner 2026-09-18).
- **Commit per item**, message in the house style visible in `git log` (one plain sentence
  saying what changed and what it measured, then the details), ending with the
  attribution line the session provides. Every served number that moves is named in the
  commit message with its before and after.
- **Decisions go to the owner through AskUserQuestion, four per call**, most
  outward-facing first, the recommended default as the first option, each option stating
  what flipping it changes. Record every answer in DECISIONS_FOR_OWNER.md immediately.
  Read free-text "Other" answers carefully (the Rays/Tropicana note arrived that way).

### 0.3 The work pattern that has worked

Census (read-only lanes, one per file group so hunks cannot collide) -> adversarial
verification on the SERVED path (about 2 in 5 findings in this repo's history overstated
blast radius by measuring the compute path) -> owner decisions in batches of four ->
sequential builders, one at a time, each with its own tests -> suite between batches ->
commit -> the next builder. For multi-file changes, author the patch in a lane and apply
it in the main loop. For anything that moves a fitted number, register the gate document
first, commit it alone, then build.

### 0.4 Definition of done for the whole pass

1. `python tools/run_suite.py --out suite.json` from `prospect-tracker/`: zero unexpected
   reds. The two baseline reds in `KNOWN_BASELINE_REDS` (`test_efv_export::
   test_xfv_golden_fingerprint`, `test_proj_export::test_vet_surplus_only_on_contracted_
   seasons`) clear only on a box `rebuild_only`; any other red is a regression or a real
   defect and is fixed, never baselined. The committed `suite.json` is STALE (file dated
   2026-09-04, last committed in `944502c5`); its dispersion red was retired to a dated
   reading on 2026-09-06 (`63541afe`) and every assertion of that test holds on the
   2026-09-23 artifact (re-checked read-only 2026-09-24). The one red known on today's
   data is `test_calibration_vintage::test_the_same_player_is_worth_the_same_on_every_
   surface` (50 `archetype_posterior_floor` rows at the 0.15 tolerance; it reads
   `trade_values` and `mlb_projections` only). The whole-suite state on 2026-09-24 is
   UNMEASURED, so Wave 0 runs it first and commits the fresh `suite.json`.
2. `python build_site.py` runs clean; `python tools/gen_audit_docs.py` regenerated
   SITE_MAP.md, DATA_SOURCES.md and MODEL_REGISTRY.md and `test_generated_docs_in_sync`
   is green.
3. `python tools/copy_lint.py --check` and `python tools/strip_emdashes.py --check` exit 0.
4. `data/model_registry.json` `validate()` clean; every served model has a row; every row's
   verdict matches its artifact; no `*_eval.json` without a row.
5. Every route in SITE_MAP.md renders at 1280 and 390, light and dark, with zero console
   errors and zero failed fetches, verified by the Playwright sweep in Part 5.4.
6. Every item in this plan is either shipped (commit hash recorded in the execution log),
   explicitly deferred with the owner's answer recorded, or blocked with the blocker
   named. The execution log is `_finalpass_2026-09-24/EXECUTION.md`.
7. The owner has answered Part 7 or the defaults are recorded as taken.
8. Memory updated: one `project` note for the pass with the commit list and the owed
   items, plus the traps met.

---

## Part 1. The state pin (verified 2026-09-24)

- **Git.** HEAD `c78f1e7c` on `efv-conviction-2026-08-08`, 371 ahead of `main`. Working
  tree: 76 modified paths, ALL under `prospect-tracker/data/` (standing regeneration churn
  from the 2026-09-23 monthly), zero source files modified. One untracked directory at the
  repo root, `_pre_epoch_2026-09/` (pre-epoch archive; decide whether it is deleted or
  moved out of the tree, Part 5.6). `beta` has no common ancestor with this branch; it
  is not a merge target.
- **Suite.** The committed `suite.json` is from 2026-09-04 (41 chunks, 492.5 s) and says
  nothing about today; see 0.4 item 1. Chunk size 8 is measured and banned from
  reduction. The 2026-09-17 execution log recorded 53 chunks, so the file count has grown.
- **Registry.** `data/model_registry.json`: 316 rows, 53 validated / 133 provisional /
  43 unvalidated / 87 deprecated; zero rows past the 90-day stale line on 2026-09-24.
- **Epoch.** `RESOLVED_THROUGH = 2025` (`efv_dataset.py:274`; shadow at
  `tools/build_star_odds_artifacts.py:38`, must move in the same commit). The fWAR label
  epoch is REGISTERED (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`, results empty);
  preconditions E5 (5c looks on 09-28 and 10-05, GRPO forward read) and E6 (season end
  09-27 plus the D9 freeze fetch ~10-05) are NOT met on 2026-09-24. Step M (projections
  retrain) may not run before 2026-10-05.
- **eWAR.** `data/ewar.json` carries `generated_at 2026-09-03T12:35:09` BY DESIGN (the
  frozen series' build and the board fingerprint's label term, `run_monthly.py:2036-2058`)
  and `live_built_at 2026-09-21T13:36:31` (the nightly live-season re-price, owner decision
  D11). `data/job_heartbeat.json` `ewar_nightly` last succeeded 2026-09-21 (8 of 8) while
  every other nightly job succeeded 2026-09-23: the live season is two nights stale on the
  monthly-chained runs (the monthly's 3-pre step skips the daily d8b). Confirm on the
  first nightly of this pass that `live_built_at` advances; if it does not, that is a
  Wave 0 ops defect.
- **Pipeline health** (`data/ingest_health.json`, 2026-09-23 monthly): three REDs.
  `betting_close_capture` (never run; the owner SKIPPED the close job on 2026-09-17, so
  this red is a standing disclosure, not a defect to fix without an owner reversal),
  `betting_lineup_capture` (armed by the owner 2026-09-17 under O17, but NEVER SCHEDULED
  ANYWHERE: `.cache/lineup_captures/` holds one capture, `2026-09-17-2148.json`, from the
  hand run that built the job; no Windows task exists on the dev box; and
  `deploy/betting-crontab.example` has no line for `tools/betting_lineup_job.py` at all,
  so the production box cannot run it either. A capture cannot be rebuilt after the
  fact, so every night from 09-18 to 09-23 is lost to 5j. REGISTERED 2026-09-24 at the
  owner's explicit request: Windows task `EephusLineupCapture` on the dev box runs
  `python tools\betting_lineup_job.py` from `prospect-tracker\` every 15 minutes, the
  job's own gate doing all window reasoning (remove with `Unregister-ScheduledTask
  -TaskName EephusLineupCapture`). It runs only while this machine is awake; the
  heartbeat gaps it leaves are recorded honestly for 5j's Leg M. Wave 0 item W0-OPS-1:
  add the missing cron line to `deploy/betting-crontab.example` so the production box
  can take over, and record the 09-18 to 09-23 gap in 5j's text),
  `vintage_capture_gap` (nights 2026-09-20 and 2026-09-22 missing; lost). Every other
  source green on 2026-09-23.
- **Surfaces.** 30 generated `index.html` pages plus three hand-maintained (PROSPX
  3,243,605 bytes; CollegeSavant hitter and pitcher apps with embedded JS data). Module
  scripts: mlbstats.js 314,855 bytes, glossary.js 287,717, betting.js 229,175,
  projections.js 213,819, fa.js 127,776, ledger.js 105,598, dfs.js 98,231, pal.js 97,201;
  site.css 323,965. NAV_ITEMS: 20 leaves, two groups (MLB Modules: Franchise, Free
  Agency, Projections, MLB Stats, Alchemy Lab, Trade Machine, Arbitration, Club Ledger,
  In-Game Management, Hall of Fame; Diamond: Fantasy, Sports Betting, Diamond Pass).
  `/parks/`, `/player/`, `/models/`, `/news/`, `/history/`, `/sources/`, `/report/` are
  reachable only by link or URL.
- **Owed from the 2026-09-23/24 sessions** (memory `modules-program-2026-09-23`):
  `fa_sources.scrape_spotrac_payroll` Averages-row parser (the Club Ledger footer
  reference row never refreshes); D4 Commit D (schema-7 builder) only before Opening Day
  2027 after 5j; 5l disclosures to amend on 10-05, 10-07 and ~10-09; one watched nightly
  d10e on the box; Management Waves B/C/D; Club Ledger trailing dark blocks (dead money
  and retained tag, payroll history backfill, IFA 2009-2018); the O15 third slot-policy
  value (held until the slot-lock repair lands); the years_impl workflow's two open
  defects (`#hseason=2019` renders an empty board; the Overall board and `data/ewar.json`
  disagree on 173 of the top 400 rows, must build from one substrate).
- **Test rot calendar** (`docs/TIME_ROT_BACKLOG.md`): `test_storage_export.py:114` fires
  2026-12-02; four more on 2027-02-01. Fix inside this pass (Part 5.6) so the port's Gate
  A baseline does not inherit a calendar bomb.

---

## Part 2. Constraints

### 2.1 Locked owner decisions this plan inherits (do not re-ask)

From 2026-09-03, 09-09, 09-11, 09-16, 09-17, 09-23 (all recorded in DECISIONS_FOR_OWNER.md
and the memory notes): fWAR is the frame; published fWAR frozen per season is the fitted
label, bundled with the RESOLVED_THROUGH 2025 to 2026 advance at the 2026 season close;
freeze fetch ~2026-10-05 and the 2000-2010 sabermetrics cache; bust taxonomy: fix the
label and split the display, two chips summing to P(bust), regression target unchanged;
engine WAG "bust" renamed; Z1 full driver re-test, one read per arm, a passer served
provisional in its own epoch with no accuracy copy; $/WAR nominal on both surfaces
(escalate 4.09 percent, discount at the matching nominal rate); fielding.py repointed to
the nightly innings feed; WAG_EXPOSURE_STINTS_FIRST widened; pitcher replica park factor
by leave-one-out FIP- back-solve; weather archive held to 2027 with CC BY attribution
required before any weather number serves; O14 serve the graded pricer on a 7e-D fail;
O15 publishable markets only (third policy value owed); O16 close job SKIPPED; O17 lineup
capture ARMED; O18 post-lineup price capture FUNDED (~93 credits a month); O21 intraday
rebuilds re-pick slots (disclosure, not lock); O12/O22 Futures changelog and archive
provenance labelled per row; O24 props pull after cards post; A-3 three value-ruler
legend chips; ask C salary_path ON; multi-year plus index BUILT (lab-recomputed windows,
Overall first and default); Franchise first in MLB Modules, Club Ledger after
Arbitration; OUTLOOK branch graded on projected 2027 wins with a provisional chip;
mgmt_decisions shards and ledger_clubs shards TRACKED; every NEVER list in the D1 to D5
specs (Part 4.9, 4.10, 4.12 restate them).

STILL OPEN from the 09-11 queue (ask them in this pass's first decision batch if the
executor reaches an item that needs them): O5 displayed WAR at the flip; O7 which
label-definition arms ride the epoch; O10 model-class re-adjudication; O11 step M
sequencing (partly fixed by the 5c correction: not before 2026-10-05); O19/O20 5j Leg M
form and backfill (reshaped by O18); O23 the 7h re-read (registered on its default).

### 2.2 Do-not-reopen

`docs/master-plan-2026-08-19-holistic-audit.md` section 2 (18 items) plus the additions in
`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` section 7.1. The reopen
standard: a NEW data source or a NEW owner instruction, never a hunch. Every item in Parts
4 and 5 that touches a closed question says so and names the reopen condition it
satisfies; the executor drops any item that cannot.

### 2.3 The clock calendar this pass runs inside

The 2026 regular season ends **2026-09-27**. This pass starts on 2026-09-24. Everything
that touches a fitted number is sequenced against these dates; everything else is not.

| Date | Clock | Consequence for this pass |
|---|---|---|
| 2026-09-28 | 5c-A `xwoba_14/30` look (once) and the 7h total-map re-read (once, kill 2026-10-06) | no betting pricer change lands between now and the read; no candidate related to an outcome |
| 2026-10-05 | 5c-B `lineup_strength` and 5c-C `star_out` looks (once each, last day 2026-10-31); D9 freeze fetch; the epoch starts; 5l disclosure amendment day 1 | no projections retrain (step M) before this date; no star or lineup variant computed on outcomes |
| 2026-10-07 | 5d A to E (schema 4) and 5k run environment, one Holm family with 5d-C and 5h; 5l disclosure day 2 | |
| ~2026-10-09 | PROJ_PATH_SHAPE ARM A look (`docs/PROJ_PATH_SHAPE_GATE.md` section 13); 5l disclosure day 3 | |
| 2026-10-11 | 5e handedness (postseason counted) and 5i-B park by hand: both clocks started on `2026-09-13.json` (no 09-11 or 09-12 vintage was written; corrected 2026-09-25, M12-05); `leaderboard_vintages.dark_clock` derives the date and `dark_look_allowed` refuses an earlier look | a look on 10-09 or 10-10 disqualifies the candidate |
| 2026-10-31 | last day for the B4 looks (else INDETERMINATE) | |
| after 2026-11-15 | `pwoba` re-gate on the new-label bundle; HEM_RIV pair set may extend | |
| 2026-11-16 or later | HEM+ construction re-gate, own document | |
| later of 2026-11-20 and epoch step Z + 14 days | PROSPECT_ANCHOR_GATE one look | never compute an FV-cell realized mean before it |
| 2026-12-02 | `test_storage_export.py:114` rots | fix in Part 5.6 before then |
| before Opening Day 2027 | N9 protocol; every 2027 dark column landed; D4 Commit D (schema 7) after 5j's schema 6 | |
| 2027-07-01 earliest | 5l club policy rates (family MG, m = 2) | |
| 2027 season close | next label epoch (RT 2027) | |
| not before 2027-10-15 | PROSPECT_ANCHOR fresh read | |

**The sequencing consequence, stated once.** The final pass and the port bracket the
epoch. The epoch rebuild (runbook A to Z) moves every fitted artifact once, in days, from
~2026-10-05. So: (a) everything in this plan that does NOT touch a fitted number ships
now, before the epoch, in Waves 0 to 3; (b) everything label-dependent rides the epoch
under FWAR_LABEL_EPOCH_GATE.md and is listed here only so the executor knows it is coming
(Wave 4); (c) the port's Phase 0 equivalence harness is built on the post-epoch numbers,
so the port waits for the epoch's step Z (Wave 5). Doing the port on pre-epoch numbers
would mean porting a site whose every fitted number is about to move, which makes the
port's "no errors" claim unverifiable. This is decision Q-0 in Part 7 (default: pass ->
epoch -> port Phase 0).

---

## Part 3. The industry scoreboard

From lane X01 (read-only, 2026-09-24; full file and probes under `_finalpass_2026-09-24/finalpass/X01_registry_scoreboard/`). The honest headline: on identical rows against the best comparator on disk, NO flagship leads by a resolvable margin; wins are against internal baselines or thin; the public LOSSES are arbitration vs Swartz (MdAPE 2.66x), HoF vs the B-Ref HoF Monitor, ETA vs FanGraphs published ETA (indicative, not row-matched), WAR/PA+ vs plain WAR, and betting vs Elo (point) and the market. Widening a lead therefore means (a) adding the missing public comparators so a WIN can be claimed at all (Steamer/ZiPS, MLBTR contract predictions, xFIP/SIERA, published farm rankings, market win totals), and (b) the registered measurements in the 'next legit measurement' column, each on its own clock.

Lane X01. Read-only. Every number below is quoted from a committed artifact (path : key = value) or from a read-only probe in this directory. Registry prose, docs and memory were used only as location hints. Where the registry prose and the artifact disagree, the artifact wins and the disagreement is listed in section C.

Registry: `data/model_registry.json` version 2026-06-11, checked_at 2026-09-23, 316 rows (53 validated, 133 provisional, 43 unvalidated, 87 deprecated), `problems` = []. Of the 229 non-deprecated rows, 158 are served somewhere (33 validated, 83 provisional, 42 unvalidated) and 71 are model-dev or unserved (classification from the `surface` field; full census in `appendix_census.md`).

Verdict key. WIN = ours beats the comparator with a lower 95% bound above zero (or the artifact's own resolvable flag). TIE = inside the artifact's floor or CI straddles zero. LOSS = the comparator is ahead on the point estimate with a resolvable margin, or the artifact itself says so. NO COMPARATOR = no public or strong comparator is scored on disk. "(internal)" means the only comparator is a naive or in-house baseline.

Gap sign: ours minus theirs, in the metric's own direction (for MAE / Brier / MdAPE a negative gap is ours better; the column says which).

### 3.A. Served predictive models, scored

| # | model_id (verdict) | served where | our metric (path : key = value) | best comparator on disk | gap (sign) | verdict | ceiling evidence | next legit measurement | freshness |
|---|---|---|---|---|---|---|---|---|---|
| 1 | xfv_hitter + xfv_pitcher (provisional) | /prospx/ primary grade and rank | `data/source_backtest.json` accuracy.head_to_head_verdict.xfv_spearman = 0.4064 (n 812, vintage-matched) | same key consensus_spearman = 0.4135; accuracy.pooled_efv_common_vintage_matched.mlb_pipeline.spearman = 0.4117; fangraphs 0.3682 | -0.0071 vs consensus, -0.0053 vs Pipeline (rho, higher better) | TIE (artifact: "not resolvable at this power", mde95 0.0303) | 39 closed feature arms (do-not-reopen 1); 812 vintage-matched rows; per side E_cond MDE95 hit 0.0206 / pit 0.0251 (`data/xfv_eval.json` honest_note) | label epoch at 2026 season close: published fWAR label + RESOLVED_THROUGH 2026 (owner O1/O2 2026-09-11), one registered attempt. PROSPECT_ANCHOR_GATE is a separate clock, not before 2026-11-20 (describe only) | xfv_eval.json 2026-09-04 (20 d); source_backtest.json 2026-09-23 |
| 1b | same, MAE leg | /prospx/ | `data/xfv_eval.json` evals.debuted_km.pooled_oos.blend.mae = 4.279 (hit), `xfv_eval_pitcher.json` same key = 2.668 | baseline (consensus OLS) mae 4.142 hit / 2.615 pit; full_pool_km 2.257 vs 1.884 hit, 1.5 vs 1.358 pit | +0.137 / +0.053 WAR MAE (lower better, ours worse) | LOSS on MAE, all four cuts | dispersion correction reverted to identity by owner (glossary xfv entry); tail-preserving refit 5/5 NO_SHIP (`data/xfv_tail_preserving_eval.json`) | none admissible before the label epoch; do not reopen correction families (item 4) | same |
| 1c | same, capture | /glossary/ Source Comparison tile | `source_backtest.json` accuracy.capture_curve.xfv.top20 = 0.7037 (pool 3661) | capture_curve.consensus.top20 = 0.7134 | -0.0097 (higher better) | TIE (no CI) | same | same | same |
| 2 | consensus_fv (validated) | every PROSPX surface | `source_backtest.json` accuracy.consensus_vs_inputs.auc.consensus = 0.7362 | auc.best_input = 0.7204 (MLB Pipeline) | +0.0158, mde95 0.0078 | WIN (AUC); Spearman 0.285 vs 0.2861 TIE (mde95 0.0121) | n 4316 common set; BA excluded until 2027 (do-not-reopen 6) | none owed; BA scoreable 2027 | 2026-09-23 |
| 3 | eta (validated) | PROSPX ETA on every prospect | `data/eta_eval.json` champion_heuristic.mae = 1.425, within_1y = 0.588, bias = 0.992 (n 4221) | (a) baseline_naive_level_table.mae 1.975 (internal). (b) FanGraphs published ETA, on disk in prospects.db snapshots.tools_json._extras.eta_year, 100% of FG rows 2017-2026: MAE 0.881, within_1y 0.801, bias +0.249 (n 3895, probe_fg_eta.py, NOT row-matched) | vs naive -0.550 yr (WIN); vs FG +0.544 yr indicative (lower better, ours worse) | WIN vs naive; LOSS (indicative) vs FanGraphs | own challenger challenger_empirical_table_forward_chained.mae = 0.869 failed only clause C4 (empirical_table_gate_2026_08_19.overdue_guardrail.delta 453 vs limit 110) | register a row-matched FG-ETA comparator plus an FG-anchored arm under the same C1-C5 clauses (new data source; not a reopen of the 08-19 no-ship) | 2026-09-23 |
| 4 | fa_market (validated) | /fa/ class board + tracker | `data/fa_gate2_eval.json` pooled.guarantee.mae_model = 9.690 ($M), aav 2.909, years 0.433 (n 1199) | pooled.guarantee.mae_base = 11.120 (nearest comps, internal). No MLBTR / FanGraphs crowd contract predictions on disk (fa_market_preds table rows = 0) | -1.430 $M (WIN internal) | NO PUBLIC COMPARATOR | 9 winters, 1199 signings, mega slice n 50 | capture MLBTR Top-50 predictions + FG crowd for the 2026-27 class (published November) and score after the class closes; AAV modeling stays closed (do-not-reopen 10), this is measurement only | 2026-08-19 (36 d) |
| 5 | fa_projection_marcel (validated) | /fa/ + /projections/ | `data/fa_gate1_eval.json` pooled.war.mae_model = 0.5157 (n 20721), coverage_p10_p90 = 0.7955 | pooled.war.mae_base = 0.6242 (5/4/3 carry-forward, internal). No Steamer / ZiPS / Depth Charts anywhere in the repo (grep of *.py returns nothing) | -0.1086 WAR (WIN internal) | NO PUBLIC COMPARATOR | 10 winters | forward-capture FanGraphs Steamer/ZiPS/Depth Charts at 2027 preseason; score at 2027 close. Statcast-into-projections stays closed (item 17) | UNDATED artifact (no generated_at) |
| 5b | pWOBA column (phem_marcel_lite, validated) | /mlbstats/ hitters pWOBA | `data/phem_marcel_lite_eval.json` hitters: fa woba_proj rho 0.5189 | textbook Marcel 0.4944, hem_plus_3yr 0.4939 | +0.0250 vs hem3, lo95 +0.0010 (v1) | WIN (thin) | 918 gate pairs | the dated pwoba re-gate after 2026-11-15 (item 17 exception) | 2026-07-15 (71 d) |
| 6 | fa_war_paths_decay / mlb_projections_vets (validated) | /fa/ + /projections/ paths | `data/proj_horizon_eval.json` rowmatch_champion_vs_challenger.horizons.1.challenger.mae = 0.5846 (proj_lgbm_v1) | champion marcel_decay_v2 mae 0.5988 (n 8053) | -0.0142 (lower better) | WIN internal, no CI in block; NO PUBLIC COMPARATOR | h1 tail_ratio 0.351 vs 0.273 | PROJ_PATH_SHAPE_GATE ARM A look 2026-10-23, ARM B 2026-11-13 (not run here) | 2026-08-19 |
| 7 | arb_award (provisional) | /arbitration/ | `data/arbitration_eval.json` a6_swartz.ours_mdape = 0.2156 (n 261) | a6_swartz.swartz_mdape = 0.0811 (MLBTR / Swartz, published pre-settlement) | +0.1345 MdAPE, ratio 2.66 (lower better, ours worse) | LOSS (artifact verdict NULL, disclosed on page) | 261 identical rows; single-season comparisons pre-committed NULL (ARBITRATION_GATE A6) | capture Swartz 2026-27 projections (October) and decide serve-Swartz-where-published vs ours (owner); C3' "gap does not widen" clause | 2026-08-09 (46 d) |
| 8 | control_window_salary_path (provisional) | /projections/ Control, /trademachine/, PROSPX, /fa/ | `arbitration_eval.json` gate_c_verification.c1_per_player_vs_ladders.mae_usd.served = 2,214,803 | clemens_2026 ladder 4,926,804 | -2.71 $M, 4.98x the one-sided MDE95 | WIN (internal) | 264 paired | realized-2026-award MdAPE (C2 clause) after awards settle | 2026-08-09 |
| 9 | betting_game_prob (provisional) | /betting/ | `data/betting_model_eval.json` benchmarks.tiers.model_vintage.brier = 0.24269 (n 705) | elo_literature.brier = 0.24228 (fixed K 4, HFA 24, never fitted); home_constant 0.24787; market_open_devig same_games: model 0.24314 vs market 0.22613 (n 390) | +0.00041 vs Elo; -0.00518 vs home; +0.01701 vs market (Brier, lower better) | LOSS vs Elo (point, no CI in block), WIN vs home (min_edge_gate out_of_sample_skill have t = 2.919), LOSS vs market | 705 vintage games; close tier n 0; market blend pinned at w=1 until 150 ledger games (item 13) | register an Elo-rating-difference arm on the vintage window (Elo is not a dark family); market-blend gate at 150 ledger games | 2026-09-23 |
| 10 | win_expectancy_state (provisional) | /management/ engine | `data/win_expectancy.json` calibration.brier = 0.157678, ECE 0.00572 | calibration.feed_brier = 0.157516 (MLB wp_home_before, same plays) | +0.000162 (lower better) | TIE by design (team-blind engine) | in-sample on the play corpus | none owed | 2026-09-11 |
| 11 | hof_public_bakeoff (validated as a measurement) | /hof/ Bake-off panel | `data/hof_bakeoff_eval.json` labels.bbwaa.discrimination_full_frame.per_arm.career_war.auc = 0.944208 (best in-house) | per_arm.hof_monitor.auc = 0.969664 (B-Ref HoF Monitor) | -0.0255 AUC | LOSS (disclosed) | n 1219, 139 positives; hof_monitor vs JAWS E_cond mde95 0.0151 | H-PRED-3 predictor (not built) registered against hof_monitor | 2026-09-06 |
| 12 | hem_plus (validated) | /mlbstats/ HEM+ column | `data/hem_plus_eval.json` forward_spearman_vs_wOBA_next.hem_plus = 0.4119 (n 3372) | raw_woba 0.4087 (parent), ops 0.4108; Savant xwOBA 0.4456 vs HEM+ 0.4084 on 1871 pairs (registry hem_plus notes, 2026-09-17 bake-off, a PRIOR not a gate) | +0.0033 vs wOBA (lo95 -0.0096); -0.0372 vs xwOBA (prior) | TIE vs parent; LOSS vs xwOBA (prior); WIN only vs AVG 0.2347 | 1871-3372 pairs, gap sd about 0.013 | HEM re-gate vs xwOBA, written 2026-11-16 or later (docs/HEM_RIV_REGATE_GATE.md R1-12) | 2026-08-30 |
| 13 | hem_plus_3yr (validated) | /mlbstats/ HEM+ 3yr | `hem_plus_multiyear_eval.json` hem_3yr_forward_rho = 0.4546 | hem_1yr_forward_rho_on_3yr_set 0.4278 | +0.0269 lo95 +0.0045 | WIN vs 1yr; LOSS vs pWOBA (row 5b) | 2382 pairs | as row 12 | 2026-08-30 |
| 14 | xhem_plus (validated) | /mlbstats/ xHEM+ + Luck | `xhem_served_regate_eval.json` verdict summary: A1 rho 0.4619 | actual wOBA 0.4108 | +0.0508 v1 lo95 +0.0241 | WIN vs wOBA; TIE by construction vs xwOBA (monotone map within season) | 1871 pairs | none owed | 2026-09-18 |
| 15 | fwdhem_plus (provisional) | /mlbstats/ xHEM+ Blend | same artifact A2 rho 0.4613 | xwOBA alone 0.4543 | +0.0071 v1 lo95 -0.0012 | TIE | 1871 pairs | none before 2026-11-16 | 2026-09-18 |
| 16 | sem_plus (validated) | /mlbstats/ SEM+ | `sem_plus_eval.json` forward_spearman_vs_RA9_next.sem_plus = 0.4167 (n 592) | raw_fip 0.3821; era 0.2843. xFIP / SIERA not on disk | +0.0346 vs FIP, lo95 +0.0177 | WIN vs FIP; NO PUBLIC COMPARATOR beyond FIP | 592 pairs | score vs FanGraphs xFIP and SIERA on identical pairs (new source) | 2026-08-30 |
| 17 | rem_plus (validated) | /mlbstats/ Bullpen REM+ | `rem_plus_eval.json` forward_spearman_vs_RA9_next.rem_plus = 0.2363 (n 878) | raw_fip 0.211 | +0.0252 lo95 +0.0013 | WIN (thin); no xFIP/SIERA | 878 pairs | as row 16; restamp exists (`rem_plus_eval_restamp.json` 2026-08-30, v1 lo95 +0.0023) | self-stamp 2026-06-30, age 86 d, STALE on 2026-09-29 (STALE_DAYS 90) |
| 18 | rem/sem/dem 3yr (provisional) | /mlbstats/ 3yr columns | gaps 3yr-1yr: rem +0.0093 (lo95 -0.0409), sem +0.0152 (-0.0347), dem +0.0110 (-0.0263) | single-season same set | as stated | TIE (artifacts: "MARGINAL") | 542 / 363 / 971 pairs | none | 2026-08-30 / 09-11 |
| 19 | dem_plus (validated) | /mlbstats/ DEM+, Team DEM+ | `dem_plus_eval.json` forward_spearman_vs_rate_next.dem_plus = 0.4597 (n 1255) | raw_rate 0.4531 (FanGraphs fielding runs, the parent); fld_pct 0.0111 | +0.0067 vs raw, lo95 -0.0039 | TIE vs parent; WIN vs fld% | OAA/FRV comparator only via SDR gate G-B (item 14) | SDR gate (data-blocked, `data/sdr_eval.json` status "pre-registered, data-blocked") | 2026-09-11 |
| 20 | war_pa_plus / war_ip_plus_sp / _rp (unvalidated in registry) | /mlbstats/ WAR/PA+, WAR/IP+ | registry war_pa_plus notes (G2): hitters 0.3711 (n 3845); artifact `data/war_rate_plus_eval.json` (no row claims it as eval_artifact) | plain season WAR 0.4058 | -0.0347, lo95 -0.0479 | LOSS (hitters resolvable; SP/RP CIs span zero) | 3845 / 1396 / 1621 pairs | none; move verdict to the measured result | 2026-08-30 per notes |
| 21 | riv_plus (DEPRECATED, still served) | /mlbstats/ Bullpen RIV+ incl. phone default | `data/riv_market_regate_eval.json` (row verdict deprecated 2026-09-18) | REM+ | refuted | LOSS (the market claim) | 232 matched RP signings | next market re-read 2027-03-01 (clock) | 2026-09-19 |
| 22 | leverage_consistency (provisional) | /mlbstats/ gmLI 3yr | `leverage_consistency_eval.json` gate.pooled_rho = 0.4683 lo95 0.412 | bar 0.30 (no external comparator) | +0.168 over bar | WIN vs bar; NO COMPARATOR | 878 pairs | none | 2026-08-21 |
| 23 | farm_grades (provisional) | PROSPX farm systems | `farm_grade_eval.json` mean_spearman.sum_surplus_mm = 0.5093 | count 0.227 (card baseline); count_fv50plus 0.4646 (strongest in artifact); no FG/BA/Pipeline org ranking on disk | +0.0447 vs fv50 count (no CI; 3 of 5 vintages) | WIN vs count; TIE vs fv50+ count; NO PUBLIC COMPARATOR | 30 orgs x 5 vintages (2018-2022) | bootstrap vs count_fv50plus; ingest published farm rankings as comparators | 2026-08-19 |
| 24 | mlb_projections_prospects (provisional) | /projections/ prospects | `prospect_path_eval.json` baseline_pooled_oos.spearman = 0.1931 (fv_outcome_v1, n 487) | challenger ridge 0.1539; MAE 1.548 (ours) vs 1.509 (ridge) | +0.039 rho; +0.039 MAE (ours worse) | WIN rank / LOSS MAE, internal only | 487 rows, cohorts 2019-21 | none admissible (label pool) | 2026-08-19 |
| 25 | team_win_projections (provisional) | /projections/ Team Outlook | `team_outlook_eval.json` retro_backtest.ship_decision.holdout_mae.recentered = 7.21 (2025, 30 teams); served_recentered 7.18 | baseline_prior_wins 7.24; no market win totals / FG standings on disk | -0.03 wins (lower better) | TIE (one season, no CI) | 30 team-seasons per year | forward gate end of 2027 (`forward_gate.first_scoreable`); capture preseason market totals as comparator | 2026-09-23 |
| 26 | trade_machine_surplus (provisional) | /trademachine/ value + sort | `trade_machine_eval.json` slice_a.pooled.spearman = 0.3289 (n 2333) | slice_a.baseline_consensus_fv.spearman 0.3312; xfv_grade_orderer 0.3433 | -0.0023 vs consensus | LOSS point / TIE (ship false; tiers won 1/4) | hindsight frame, not forward | TRADE_FORWARD_GATE on trade_value_history (22 partnered origin dates so far) | 2026-08-19 |
| 27 | mock_draft (provisional) | PROSPX draft mock view | `mock_draft_eval.json` mock.spearman_rho = 0.7413 (n 70) | baseline_consensus.spearman_rho 0.7407; public mocks not on disk | +0.0006 | TIE (clause C3 reads "BEAT") | one class | 2027 draft vs Pipeline/BA/FG final mocks; archive path missing (registry note) | 2026-08-19 |
| 28 | draft_consensus_weight (provisional) | PROSPX draft board | `draft_consensus_weight_eval.json` pooled.equal.spearman = 0.2258 (n 672) | per_source_spearman.fangraphs 0.2304 | -0.0046 | TIE (no CI in block) | 672 rows | none | 2026-09-23 |
| 29 | draft_slot_curve (validated) | farm finance + QO tax | `draft_slot_curve.json` realized_career_by_bucket_2005_14.1.mean_war = 29.511 (card) | holdout_mae.fitted_first8 2.664 vs incumbent 0.642 (artifact: "censoring-confounded, not used as criterion") | holdout loses | NO COMPARATOR that counts (card is a pick-1 vs picks 301-500 contrast, not model vs baseline) | 6596 picks | censoring-aware first-6 holdout at RESOLVED_THROUGH 2026 | 2026-09-04 |
| 30 | stuff_plus_aaa (provisional) | PROSPX aStuff+ pill | `stuff_plus_aaa_eval.json` forward_gate.r_vs_mlb_kpct = 0.4855 (n 22), r_vs_mlb_era_inv 0.0149 | none scored (raw FB velo or AAA K% would be the baseline) | n/a | NO COMPARATOR | n 22 | add raw-velo and AAA K% baselines on identical rows; next debut cohort | 2026-09-23 |
| 31 | statcast_plus / SC+ (provisional) | PROSPX SC+ pills | `statcast_plus_eval.json` hitters.rho_sc_vs_war2y = -0.0343 (n 100), rho_sc_vs_mlb_ops 0.1129 (n 58) | none | n/a | NO COMPARATOR (weak signal, published) | 30-46 per cohort | literal composite forward-scoreable as 2026 trail debuts | 2026-08-19 |
| 32 | xfv_proxy (provisional) | /prospx detail tile | `xfv_proxy_eval.json` sides.hit.spearman = 0.2234 (n 129), pit 0.1577 (n 158) | none (consensus FV on the same rows never scored) | n/a | NO COMPARATOR | 3 cohorts | score consensus FV and eFV vs first-MLB xwOBA on identical rows | UNDATED |
| 33 | xfv_ungraded (provisional) | /prospx farm-detail | `xfv_ungraded_eval.json` battery.by_side.hit.rho_grade_weighted = 0.26729, E_refit verdict "RESOLVABLE WIN" | zero-information null (no FV exists for this cohort) | +0.267 vs null | WIN vs null | 1032 hit rows | none | 2026-08-08 |
| 34 | xfv_tools (provisional) | /prospx | `xfv_tools.json` meta.modeled_tools.hit.oos_validation.margin = -0.0033 (blend_weight_applied 0.0) | consensus tool grade | -0.0033 hit, -0.0009 power | TIE by construction (served = grade) | 541 rows | none | UNDATED |
| 35 | xfv_odds_calibration_slope (validated) | served p_bust / p_bucket | `xfv_odds_calibration_slope_eval.json` gate_primary.vs_incumbent.d_brier.obs = 0.030139 CI95 [0.0211, 0.0391] | incumbent grade-only curve | +0.030 Brier gain | WIN | 7 folds | none | UNDATED |
| 36 | positional_ladder (validated) | def_value, /pal/ Position Fit | `positional_ladder_eval.json` gate_accuracy_4splits.dmae_runs_per_650pa_mean = 0.4819 CI [0.4577, 0.5028] | folklore table, level-corrected | -0.48 runs/650 PA error | WIN | 4 eras | none | 2026-07-26 |
| 37 | pal_conversion (provisional) | /pal/ | `pal_eval.json` per_direction.SP->RP.rho_fit_war_delta = 0.2916 (n 61) | kbb_pre -0.097 | +0.387 lo95 +0.0745 | WIN SP->RP; LOSS RP->SP (-0.2062 vs 0.1023, n 25) | 96 conversions | none (stamina gate closed, item 18) | 2026-07-15 |
| 38 | prospect_surplus (validated) | PROSPX Sur+, trade lookup | `surplus_backtest_real.json` resolved_only.cross_validated_correction.held_out_calibration.slope = 1.078, held_out_bias -0.62 | identity correction | slope toward 1.0 | WIN internal; NO PUBLIC COMPARATOR | 2236 players | none | 2026-07-31 |
| 39 | ewar (provisional) | site-wide WAR series | `ewar_eval.json` gate_1_team_wins.ewar.r = 0.8595; gate_2 self_r_ewar_fip 0.3617 | bwar r 0.8803; self_r_bwar_ra 0.1768; next_season_wins_full_schedule_only r 0.592 vs 0.5913 | -0.021 r (describe), +0.185 (persist), +0.0006 (forward) | LOSS describe / WIN persistence / TIE forward | 300 team-seasons | owner-locked fWAR frame replaces eWAR at the 2026 season-close epoch | 2026-09-03 |
| 40 | fwar_replica (provisional, unserved instrument) | none | `fwar_replica_eval.json` summary: hitters 0/16 failing seasons on every component; pitchers.rar 10 failing seasons, pitchers.war_runs 12 | FanGraphs published components | n/a | pitchers not replicated | 2011-2026 | W1.1 pitcher arm (UNFINISHED) before the epoch | 2026-09-11 |
| 41 | spotlights_movement (provisional) | PROSPX spotlights: Risers / Rebounders / Fallers | `editorial_eval.json` by_flag_type.riser.horizons.h60.hit_rate 0.2661 vs control 0.2005; h30 0.1756 vs 0.205; rebound h30 0.2384 vs 0.2332, kill_rule verdict_recommendation "deprecated"; faller h30 0.1601 vs control_rate 0.0 (n 4827) | fv-band matched controls | riser h60 +0.066 / h30 -0.029; rebound +0.005 | riser mixed; rebound LOSS (kill rule fired); faller unreadable (zero-rate control) | 61 matured cohorts | owner call on rebound; repair the faller control | 2026-09-23 |
| 42 | fa_team_fit (provisional) | /fa/ fits | `fa_gate3_eval.json` results.live_analog.top5 = 0.2293 | behavior_only 0.208, random 0.1667 | +0.021 | WIN internal | n 1173 | none | 2026-08-04 |
| 43 | betting_props_pmf (provisional) | /betting/ props fair lines | registry notes: binomial beats Poisson by 0.001045 Brier (K market) | blanket Poisson | -0.001 Brier | WIN (intervals exclude zero per notes) | props ledger | market-graded read when props capture accrues | 2026-09-08 |
| 44 | playoff_odds_sim (provisional) | /projections/ outlook, /betting/ Futures | `data/futures.json` (no backtest) | none | n/a | NO COMPARATOR (registry says so) | none | capture a futures market; backtest 2026 season on frozen start-of-September inputs after the World Series | 2026-09-23 |
| 45 | grpo_prospect (unvalidated) | PROSPX breakout badge | no eval yet | zero-information + FV-only controls (docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md) | n/a | NO MEASUREMENT (30-day look admissible since 2026-09-18, not run) | one cohort per month since 2026-08-19 | run the 30-day look now; 60-day 2026-10-18; 90-day 2026-11-17 | n/a |
| 46 | milb_translation (unvalidated) | PROSPX MLBe statline context | `data/milb_translation.json` validation.hit_k.r2 = 0.327, mae 3.99, coverage 0.801 (n 287) | raw untranslated rate (named baseline, never scored) | n/a | NO COMPARATOR scored | 287 hit / 122 pit | add raw-rate baseline MAE to the same block; point the row at it | undated in registry |
| 47 | college_translation (provisional) | CollegeSavant Projected Single-A | `college_translation_eval.json` factors.hit_k.loo.mae = 5.323, r2 0.172 (n 217); hit_ops r2 0.007 | predict-the-Single-A-mean (named, not scored in the artifact) | n/a | NO COMPARATOR scored | 217-232 pairs | score the mean baseline in the same LOO | UNDATED |
| 48 | star_odds (provisional) | PROSPX board + detail | served = FanGraphs published table (exact); `star_odds_eval.json` gate.pass = false (model odds diagnostic only) | the published table itself | n/a | NO MODEL SERVED (public table relabelled) | window-resolved debuts 834 | none | 2026-09-23 |

### 3.B. Served rows with no scored comparator by design (descriptive or composite)

Rows the registry itself calls descriptive, composite or convention, served, with no forward test: archetype_comps, cs_plus, draft_stock_plus, dvm_plus_dollar, dvm_plus_org, dvm_plus_tools, fv_stuff_plus, fv_tape, hit_plus, iso_plus, krp_plus, pd_plus, pwr_plus, rps_plus, stf_plus, tool_plus, composite_cmd_plus, org_sur_plus, tbs_farm, tbs_prospect, farm_movement, rank_movement, versa_positions, multiposition_bonus, fa_aging_curves, pitcher_role_usage, position_observed, stuff_plus_external, swing_plus_external, franchise_index, franchise_branch_score, fantasy_dynasty_blend, fantasy_roto_valuation, fantasy_buy_sell, fantasy_closer_depth (closer share RED, item 11), dfs_slate_pricing (archive exists since 2026-08-16 at .cache/dfs_history), leverage_board, xrem_plus, xsem_plus, mgmt_decision_ledger, mgmt_state_baseline, mgmt_style_z, org_tendencies, advancement_pace, surplus_downside_risk, prospect_greeks, upgrade_option, draft_war_room, xfv_backgrade, fantasy_ros_rankings.

Served with NO registry row at all (grep of assets vs registry text):
- `debuted_value` (trade_value_mm, posterior buckets, true_talent_war): 21 references in prospx/index.html, 2 in assets/ledger.js; ledger_export.py:1640 says "debuted_player_value carries no registry row of its own".
- Bullpen+ (assets/mlbstats.js, betting.js, dfs.js, fantasy-card.js; glossary bullpen_plus), Lev Deploy+ (mlbstats.js, 4 refs), Front 3 / Rotation+ (mlbstats.js), Offense+ (team). Descriptive roll-ups of rowed metrics.
- Cost+ (ledger): rowless on purpose (ledger_export.py:1554 "predicts nothing").
- 08-19 rowless list now all carry rows: GRPO (grpo_prospect), Cmd+ (composite_cmd_plus), OrgSur+ (org_sur_plus), mock draft, versa, multiposition bonus, aging curves (fa_aging_curves), milb_translation.

### 3.C. Verdicts or copy contradicted by their own artifact

| row | registry / card says | artifact says | served where |
|---|---|---|---|
| eta card | n 4159, MAE 1.43 vs 1.98, within 0.585 vs 0.378 | `eta_eval.json` champion n 4221, mae 1.425, within_1y 0.588; baseline 1.975 / 0.381 (0.378 and 4159 appear nowhere in the artifact) | /glossary/#view=models card with a star |
| fa_projection_marcel card | WAR MAE 0.63 vs 0.73 | `fa_gate1_eval.json` pooled.war 0.5157 vs 0.6242 (ewar_v2 provider) | same |
| consensus_fv metric prose | AUC 0.7254 vs 0.7130, delta 0.0124; Spearman 0.2897 vs 0.2883 | accuracy.consensus_vs_inputs.auc 0.7362 vs 0.7204, delta 0.0158; spearman 0.285 vs 0.2861 | /models/ "How it is measured" (models/index.html) and glossary card |
| team_win_projections metric | "now BEATS the prior-wins carry-forward" | holdout 7.21 vs 7.24 (0.03 wins, 30 teams, no CI) | /models/, glossary card |
| spotlights_movement | provisional, notes last dated 2026-07-14 | rebound kill_rule verdict_recommendation "deprecated" at 61 matured cohorts | Rebounders chip served (prospx/index.html:9407) |
| war_pa_plus / war_ip_plus_* / war_rate_plus_3yr | unvalidated, no eval_artifact | `data/war_rate_plus_eval.json`, `war_rate_plus_multiyear_eval.json` hold a measured G2 LOSS | /models/ shows "No eval artifact"; same files listed as "Unregistered evals" |
| riv_plus glossary | "tracks what teams pay ... 0.58 against 0.51" | row deprecated; notes: "That sentence is refuted" | /mlbstats/ bullpen tooltips + glossary |
| hem_plus glossary | "Validated ... beating batting average" | ties raw wOBA (lo95 -0.0096); prior loses to xwOBA | glossary + card |
| draft_slot_curve | validated, card 29.5 vs 0.29 | only holdout loses (2.664 vs 0.642), labelled censoring-confounded | glossary card |
| fa_war_paths_decay | champion proj_lgbm_v1 | `proj_horizon_eval.json` champion_model "marcel_decay_v2", challenger "proj_lgbm_v1", "measurement only, no ship decision" | /models/ |

### 3.D. Registry wiring gaps

- Rows pointing at missing artifacts: 0.
- Rows whose artifact is not published (outside data/ depth one): efv_board_floor_routing (docs/...json), efv_il_severity (docs/...md), pbp_corpus_base_state (.cache/...). Shown on /models/ as "not published".
- data/*eval*.json files no row names as eval_artifact (20): betting_props_slot_pa_eval, consensus_weight_eval, fa_lane_eval, fa_market_feature_lab_wave3_eval, fa_projection_lab_eval, positional_ladder_recency_eval, rem_plus_eval_restamp, riv_plus_eval, war_rate_plus_eval, war_rate_plus_multiyear_eval, xfv_disagreements_eval, xfv_generality2/3/4_eval, xfv_measurement_calibration_eval, xfv_side_fairness_fix_eval, xfv_surplus_recal_eval, xfv_surrogate_eval_pit, xfv_wave_h_eval, xhem_plus_eval. /models/ lists 18 of them as "Unregistered evals"; test_model_registry.py::test_every_eval_artifact_is_registered passes because it also accepts a path cited in any row's notes. Two different definitions of "registered".
- Undated served artifacts (age shown from file mtime, not evidence): fa_gate1_eval, value_framework_fitted (fv_to_war_anchors, wag), proj_def_feature_eval, xfv_lambda_reselect_eval, xfv_odds_calibration_slope_eval, college_translation_eval, prospect_def_value_eval, xfv_generality_eval, xfv_proxy_eval, xfv_overlay_uncapped_eval, xfv_tools, EFV_LANE_GATES.md. The committed registry JSON still carries `artifact_age_days` for them without `age_source`.
- Freshness cliff: rem_plus (validated, card) self-stamp 2026-06-30 goes stale 2026-09-29; upgrade_option 82 d; age_rel_outperformance 84 d, proj_def_prior 85 d (mtime), prospect_def_value 85 d (mtime), sc_plus_component 83 d, surplus_sensitivity 83 d.

### 3.E. Ten measurements most likely to widen a lead or convert a LOSS / TIE

Ranked by (expected gap x chance of resolving x reach of the surface). None looks behind a forbidden clock.

1. ETA vs FanGraphs published ETA, row-matched, then an FG-anchored ETA arm. Why first: the served ETA is "validated" against a naive table while the FanGraphs ETA already in prospects.db runs about 0.54 years better on an indicative, non-matched read (MAE 0.881 vs 1.425, within-1y 0.801 vs 0.588). Data ceiling: 3,895 FG debuted rows 2018-2023 (probe); the eta gate MDE95 on MAE is 0.05 (`eta_eval.json` empirical_table_gate_2026_08_19.row_matched.mde95_mae), so a 0.5-year gap resolves by ten times the floor. Constraint: clause C4 (overdue guardrail, limit 110) must bind the new arm too; the FG ETA is itself optimistic for non-debuted prospects, so the guardrail is the real test. Reopen basis: a data source never consumed (FG eta_year), new pre-registration required.
2. eFV at the 2026 season-close label epoch (fWAR label, RESOLVED_THROUGH 2026). The only admissible frontier reopen (item 1 and O1/O2). Ceiling: vintage-matched n 812 with MDE95 0.0303; a one-year roll of RESOLVED_THROUGH adds one more season of outcomes to every open window, so the floor narrows by roughly sqrt(n ratio). It moves the TIE only if the current -0.0071 point estimate turns; the MAE LOSS repair stays closed (item 4). Clock: after the 2026 season closes; PROSPECT_ANCHOR_GATE not before 2026-11-20.
3. HEM+ re-gate against Savant xwOBA (and the display order that follows). Ceiling: 1,871 pairs, gap sd about 0.013 (xhem_served_regate arms), the prior gap -0.037 is near three floors. Converts the primary hitter column from a straw-baseline WIN to either a real verdict or a demotion behind xHEM+ / pWOBA. Clock: document written 2026-11-16 or later (HEM_RIV_REGATE_GATE R1-12).
4. SEM+ and REM+ vs FanGraphs xFIP and SIERA on identical pairs. The industry's own next-year RA estimators; our gates stop at raw FIP. Ceiling: 592 SEM pairs (lo95 margin over FIP +0.0177), 878 REM pairs (+0.0013, thin). A SIERA loss is likely for REM+ given the thin FIP margin. New source: the FanGraphs pitching leaderboard JSON (reachable via pybaseball per memory). No clock.
5. Betting: register an Elo-difference arm on the vintage window and the market-blend gate at 150 ledger games. The fixed-constant Elo already beats the model by 0.00041 Brier on 705 games; Elo is a public baseline, not a dark column family. Ceiling: market open 0.22613 vs model 0.24314 on 390 games, so the market is the ceiling and a public-feature model should aim at Elo, not the market. Do-not-reopen 13 holds the blend at w=1 until 150 ledger games.
6. FA market vs MLB Trade Rumors Top-50 predictions and the FanGraphs crowd, 2026-27 class. Forward capture in November, score once the class signs (not before the class closes). Ceiling: about 50 predicted contracts per winter, so only a gap above roughly $1M AAV resolves in one winter; capture every year. Measurement only (item 10 closes modeling, not comparison).
7. Projections vs Steamer / ZiPS / Depth Charts, captured at 2027 preseason and scored at 2027 close. Ceiling: 1,000+ players per season, MDE well under 0.05 WAR; the incumbent beats only a 5/4/3 carry-forward today (0.5157 vs 0.6242). No clock besides the season.
8. Arbitration: capture Swartz 2026-27 projections (October) and decide serve-Swartz-where-published with ours as the labelled fallback. Converts a disclosed 2.66x LOSS into a served number that matches the best public comparator; registered clause C3' (gap does not widen) keeps measuring ours. Owner decision.
9. GRPO forward gate, 30-day look now (admissible since 2026-09-18), 60-day 2026-10-18, 90-day 2026-11-17. Converts a served unvalidated badge into a verdict; the kill rule runs through 2027-02-18.
10. Farm grades vs published org rankings (FanGraphs / Baseball America / MLB Pipeline farm rankings, 2018-2022 vintages) plus a bootstrap against count_fv50plus. Ceiling: 150 org-vintages, per-vintage rho SE about 0.15, pooled MDE about 0.08; the current +0.045 over the strong count baseline does not resolve. New source.

Also cheap, no clock: stuff_plus_aaa and xfv_proxy need their named baselines on identical rows (raw FB velo + AAA K%; consensus FV); mock draft needs a 2027 pre-draft archive path and public final mocks; team wins needs preseason market totals captured before the 2027 forward gate.

### 3.F. Ten places copy overclaims

1. /glossary/ Source Comparison findings tile "eFV ranking skill 0.361, best of every grader" (assets/glossary.js:1433-1440) reads accuracy.pooled_efv_common (all-vintages frame: xfv 0.3607 vs consensus 0.3163) directly under a hero that reads the vintage-matched verdict 0.406 vs 0.413 "unresolved". Rendered: glossary_source_comparison.png.
2. Same page, _methAccuracyChart (assets/glossary.js:1192-1211) stars eFV "0.361 ★" and "0.757 ★" from accuracy.pooled, where eFV is scored on 3,272 OOS rows and the raters on 4,316 different rows. The function's own comment says "SAME ROWS OR THE COMPARISON IS NOT ONE".
3. "eFV posts the best ordering skill in 7 of 7 resolved preseason cohorts" (assets/glossary.js:1515-1529): per-year eFV on its OOS subset vs raters on full cohorts; the sentence admits the n mismatch and claims the win anyway.
4. Generate GFX share card "Does eFV outperform its sources?" (assets/glossary.js:3127-3215) builds its bars and "best public" tiles from accuracy.pooled with a star for the best. This leaves the site as an image.
5. eFV AUC tile "0.757, consensus 0.724" (assets/glossary.js:1450-1452) invites the read that eFV discriminates better; the AUC leg is adjudicated null (row xfv_auc_floor) and do-not-reopen item 3 forbids copy saying so.
6. riv_plus glossary: "RIV+ tracks what teams pay relief free agents at least as closely as REM+ (0.58 against 0.51 over 271 signings)"; refuted by the 2026-09-18 re-gate (riv_plus row, deprecated).
7. /glossary/#view=models cards for ETA (1.43 vs 1.98, n 4159, 0.585 vs 0.378) and FA Projection (0.63 vs 0.73) carry numbers that are not in their artifacts, with stars.
8. Straw-baseline stars: HEM+ card vs AVG 0.235 (parent wOBA 0.4087 ties), DEM+ card vs fielding pct 0.0111 (parent raw rate 0.4531 ties), REM+ / SEM+ cards vs ERA (the gate that matters is raw FIP), farm grades vs raw count 0.227 (fv50+ count 0.4646 in the same artifact). HEM+ glossary: "Validated out of sample ... beating batting average".
9. Registry prose rendered verbatim on /models/ and the glossary cards: consensus_fv "0.7254 vs 0.7130" (artifact 0.7362 vs 0.7204); team_win_projections "now BEATS the prior-wins carry-forward baseline 7.24" on a 0.03-win one-season difference.
10. ETA glossary methodology "AAA about 0.8 years, AA 1.5, A+ 2.5" vs `eta_eval.json` live_base_years AAA 0.75, AA 1.5, A+ 3.0 (before the -0.5 LEVEL_BIAS_ADJ shave), and no accuracy statement beside a "validated" badge that a public source on disk beats.

### 3.Appendix

- appendix_census.md: all 229 non-deprecated rows, served flag, artifact, self-stamp, age.
- probe_fg_eta.py: the FanGraphs ETA read (read-only).
- probe_card_truth.py: every card number searched in its artifact.
- probe_orphans.py, probe_appendix.py, render.py (port 8714; server terminated), render_result.json, glossary_source_comparison.png, glossary_models.png, models_hub.png.

---

## Part 4. The module program

Built mechanically on 2026-09-24 from the census journal (run `wf_55a8ec4b-fa8`): 14 of 14 module/scoreboard lanes returned, 349 findings, 349 carried below after verification. Verdict tally over findings: CONFIRMED 50, PARTLY 78 (row text carries the verifier's narrowing), REFUTED 0 (dropped), unverified 221 (P2/P3 or ideas that were not sent to a verifier, or whose verifier died at the usage limit; treat as leads, re-check on the served path before building). Severity is the MOST severe adjusted severity any verifier gave. Evidence for every row is in the lane's directory under `_finalpass_2026-09-24/finalpass/<lane>/` (FINDINGS.md where the harness allowed it, served_state.md, probes, screenshots) and in the structured journal. The 25 verified P0 rows are Wave 0 (Part 6); two landed on 2026-09-24 (`93b80921` M07-02, `8100ce49` M12-03) and twelve groups are in flight as sequential fixers.

### 4.1 PROSPX: board and player detail (lane M01_prospx_board)

**Census summary.** I rendered and drove the PROSPX board and detail page on port 8701 at 1440 px and 390 px. The board has 8,071 rows: 4,679 graded actives plus 3,392 provisional rows from xfv_ungraded. It sorts on the xfv_grade decimal, then board_sort_key, then the +, TBS and name tiebreaks. It loads with 0 console errors, 0 page errors and 0 HTTP 4xx. I opened 110 detail pages and clicked every tab: none crashed, and none printed NaN or undefined. The eFV column never goes up as you read down the list.  Two P0 defects: - **Consensus sort does nothing.** The Consensus FV sort and the Rank-by Consensus toggle have no sort branch, so the rows stay in eFV order, consensus badges print out of order, and every provisional row is pinned to the bottom. - **Two P(bust) numbers on one card.** Jesus Made's detail card shows P(bust) 35% (eFV) and P(bust) 5% (consensus engine). The board surplus cell switches between the two when the toggle is clicked.  P1 defects: - **Rank chip vs row order.** The printed #rank is not the row's position on 3,201 of 8,071 rows, because the rank map and the board sort use different tiebreaks. - **Baked rank vs live rank.** The saved overall_rank differs from the live rank on 4,493 of 4,679 graded rows, because they count different player pools. So the "Last board #N" pill shows on about 96% of cards. - **Stale ETA.** 414 prospects still show a Late 2026 ETA after the minor-...

**Served state (evidence in the lane's served_state.md).**

- Board pool is 8,071 rows: 4,679 graded actives plus 3,392 provisional rows folded in from data/xfv_ungraded.json (6,076 entries, deduped). 162 pages of 50. The first provisional row is at position 190: mlbam_835219 Anthony Potestio, provisional eFV 47, NYY #3  [probe_board.json board.n_filtered 8071, n_prov 3392; page text 'Showing 1-50 of 8071'; probe_counts.json first_prov 189;]
- Default sort (state.sort 'xfv') orders by the xfv_grade decimal, falling back to consensus fv_close where eFV abstains. Ties break on board_sort_key, then fv_close_plus, then TBS, then name. Displayed grades have 0 inversions over all 8,071 rows. [prospx/index.html:15996-15999 efvRankValue; fvCmpDesc 11518; probe_board.json grade_inversions 0]
- The Consensus FV sort has no code branch: after switching to it, the top-15 order is identical to the eFV order and all provisional rows sit below row 4,679. [probe_board.json sort_fv_same_as_default true, first_prov_index 4679; comment at prospx/index.html:33106]
- The xfv_grade basis stamp is 'xfv_grade/scale=off/grademap=outcome_pooled@1f3fa0a970bd/.../label=ewar_v2@2026-09-03T12:35:09/injsides=pit'. The rank rebake ran at 2026-09-23T18:33:38 and moved 3,913 rows. [data/timeseries.json board_rank_rebake]
- Active eFV rows by grade_basis: outcome_pooled 2,065, provisional_capped 2,474, null (prior-anchored xfv_provisional) 140. 1,141 rows sit at exactly 20.0; 894 have xfv_grade_is_floor and 2,689 have consensus_is_placeholder. The maximum is 61.8 (jesus_made). [data/xfv.json by_player kind=active]
- By eFV the top 100 is 95 hitters / 5 pitchers (94/6 once provisional rows are folded in). By consensus FV it is 69/31. The first pitcher is ryan_sloan at #29. This basis was accepted by the owner and the side-scale is off. [data/xfv.json; probe_counts.json side_top100; efv_board_scale.py ENABLED_DEFAULT False]
- Accuracy receipts: data/source_backtest.json has no head_to_head key; the block is xfv_vs_consensus. Hitters (n 755): consensus 0.3821 vs eFV 0.3925, not resolvable (MDE95 0.0458). Pitchers (n 892): 0.2957 vs 0.2828, not resolvable (MDE95 0.0436). Block rho: d [data/source_backtest.json xfv_vs_consensus and accuracy.xfv_vs_consensus_detail; xfv_eval.json and xfv_eval_pitcher.json]
- Registry: xfv_hitter and xfv_pitcher are provisional (19 days old). The xfv_ungraded surface text ('farm-detail') is stale. upgrade_option says 'opt-in', but the column is on by default and labelled PLUS%. grpo_prospect is unvalidated and claims a board badge  [data/model_registry.json models[]]
- Chip coverage on the 8,071-row board: SC+ 3,671; aStuff+ 273; Swing+ 2; breakout 35; Star Odds and PLUS% 4,679 (graded rows only); IL 454; nonzero rank delta 5,567. AP+ appears on the detail page only: 2,177 of 3,588 hitters. [probe_board.json chips and ap_cov]
- There are two P(bust) bases. eFV p_bust comes from the Platt-dispersed p_bucket read at xfv_grade_odds (median 0.899 across actives). Consensus p.surplus.dist.p_bust is separate. For jesus_made they are 0.349 and 0.0543. [data/xfv.json; data/timeseries.json players[jesus_made].surplus.dist]
- eFV surplus_mm is priced on xfv_grade_quantile. It is within $1M of the consensus surplus on 89.8% of graded actives, and on 43.4% of those at eFV >= 45. [data/xfv.json surplus_mm vs consensus_surplus_mm]
- Star Odds shows the FanGraphs 2026 published tier value at consensus FV, with realized calibration disclosed beside it. The model version is diagnostic only (gate pass false, max_abs_dev 0.6533). [data/star_odds_eval.json gate and realized_calibration; prospx/index.html:36762-36800]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M01-01 | defect | CONFIRMED | Consensus FV sort and Rank-by Consensus toggle do not sort the board | prospx/index.html | Playwright: select sort fv; assert consensus decimal is non-increasing over the first 500 rows of getFilteredActives() and that no placeholder row precedes a re | S | conflict: none. The fix keeps eFV as the default board sort and the default Rank-by. It does not touch SCORED_SOURCES, the consensus weighting or the blend lambda. It doe |
| P0 | M01-02 | defect | PARTLY | Two P(bust) values for the same player on one card; board cell flips basis with the toggle (narrowed: Keep only the detail-page part of this finding. In the default eFV mode, bakedDetailRow in prospx/index.html (lines 48304-48322) adds the consensus engine's P(bust) and risk-adj to the Surplus value card. That card is he) | prospx/index.html | Playwright on #player=jesus_made in eFV mode asserts exactly one distinct 'P(bust) N%' value in #player-detail-body. | S | conflict: The display fix itself (suppressing or labelling the consensus P(bust) and risk-adj in eFV mode) conflicts with no do-not-reopen item, clock or locked owner dec |
| P0 | M01-04 | defect | CONFIRMED | Baked overall_rank ranks a different pool than the live rank, so 'Last board #N' shows on 96% of cards | storage.py, prospx/index.html | Extend test_board_rank_rebake: baked overall_rank equals the client rank computed from the same artifacts for every graded active. | M | GATE conflict: None on the do-not-reopen list, clocks or NEVER lists. The pool-rebase variant is a board rank-basis change. It requires a BOARD_RANK_BASIS_EPOCH bump (pinned b |
| P1 | M01-03 | defect | CONFIRMED | Printed #rank differs from row position on 3,201 of 8,071 board rows | prospx/index.html | JS-eval test: for the default sort, getEfvRank(f[i]) === i+1 for every i. | S | conflict: none. The fix changes only how exact ties are ordered. It leaves efvRankValue, the served grade, serve-basis and blend lambda untouched, so no do-not-reopen ite |
| P1 | M01-05 | defect | CONFIRMED | 414 prospects show a 'Late 2026' ETA after the minor-league season ended | eta.py, storage.py | eta unit test: snapshot 2026-09-24 with an AA prospect whose pull-ins land in 2026 returns eta_year 2027. | S | conflict: none. The fix is a calendar rule in the live caller. It does not touch the KM BASE_YEARS held at v39 (re-adjudicated 2026-08-04), does not revive eta_age_contin |
| P1 | M01-06 | defect | PARTLY | Glossary and registry describe provisional eFV as off-board and capped at 43/40, but the board ranks them up to 47.4 (narrowed: Magnitudes are overstated.  (a) The 47.4 and 37.8 figures are the artifact maxima (meta.grade_dist.max). They are not the served maxima. The 47.4 row (drew_brutcher) and the other hitter twins lose to their graded rows i) | data/glossary.json, data/model_registry.json, MODEL_REGISTRY.md | Glossary-claims test: any cap the entry names must equal meta.grade_map KNEE/CEIL. | S | conflict: None. The fix changes copy only.  Hazard: do not change efv_ungraded._GRADE_MAP or UNCAPPED_GRADE while fixing the text: - Registry row xfv_provisional_grade_ma |
| P1 | M01-08 | defect | CONFIRMED | eFV P(bust) contradicts the eFV dollar fan on the top-4 cards | efv_score.py, value_framework.py, prospx/index.html | Invariant over xfv.json: if p_bust >= 0.10, then dist.p10_mm is at most the bust bucket value plus epsilon. | M | GATE conflict: Pricing the fan from the served p_bucket needs a gate or owner decision: - The Platt odds map was wired under a pre-registered gate whose stated scope is that n |
| P1 | M01-10 | improvement | CONFIRMED | No CSV or data export on the flagship 8,071-row board | prospx/index.html, assets/eephus-csv.js | Row-builder unit test: column set, row count equals getFilteredActives().length, stamp present. | M | conflict: None. The export only serializes values already served; no fitted model, served accuracy claim, clock or dark betting family is touched, and card scraping is un |
| P1 | M01-11 | cleanup | unverified | Cold board load is 147.8 MB raw (about 18.4 MB gzip); a third of the boot file is detail-only | storage.py, efv_ungraded.py, prospx/index.html | Payload budget test on the timeseries gzip size; test_prospx_board_paints_rows stays green. | L | - |
| P2 | M01-07 | defect | PARTLY | Copy claims the outcome-mix grade is 'honest (typically lower)'; it is higher for every eFV>=50 prospect (narrowed: Confirmed: the footnote's direction claim is false at the top of the board. The odds grade that keys the outcome mix is above the headline eFV on 243 of 244 active cards at eFV >= 45, and on all 58 at eFV >= 50 (Made: 65) | prospx/index.html | Copy lint for 'typically lower'; card test that the printed odds grade equals round(xfv_grade_odds,1). | S | conflict: None for the copy fix. Watch two adjacent lines. First, re-keying p_bucket onto xfv_grade instead of fixing the copy would be an unmeasured re-key. The xfv.json |
| P2 | M01-09 | ux | PARTLY | Phone board has no ETA, surplus or stock: the phone signals strip is hidden by the forced compact density (narrowed: Build a narrower fix, all in prospx/index.html: 1. Delete line 3462 ('body.density-compact .row-phone-signals { display: none !important; }'). It has no effect on desktop. 2. In _rowPhoneSignalsHTML (38774), drop the RAN) | prospx/index.html | Playwright at 390: the first row's .row-phone-signals is visible and contains ETA and SV; no overlap with the tool strip. | S | conflict: No gate is needed and no owner decision is needed. The change is layout only and reads existing payload fields: p.eta.year, p.surplus.value_mm, the eFV surplus_ |
| P2 | M01-12 | defect | unverified | Two prospect counts on one screen and a stale board eyebrow | prospx/index.html | Masthead count equals the sum of its breakdown. | S | - |
| P2 | M01-13 | defect | unverified | Archetype comps panel never renders: the artifact has no per-player map | archetype_comps_export.py, prospx/index.html | Detail test that a hitter with a MiLB record renders the panel, or that no fetch fires if the panel is dropped. | M | - |
| P2 | M01-14 | cleanup | unverified | Dead code and a tracked 5.8 MB backup file to remove before the port | prospx/index.html, data/xfv_ungraded.json.pbust-backup-20260725 | Assert no *backup* file under data/ in the publish manifest. | M | - |
| P2 | M01-15 | defect | unverified | Stock arrow and Up/Down stock filter disagree on 1,813 of 4,679 graded rows | prospx/index.html, movement.py | Agreement test across the board pool. | S | - |
| P2 | M01-16 | ux | unverified | Board headers and chips carry no glossary hooks | prospx/index.html | Every board header maps to a glossary id. | S | - |
| P2 | M01-17 | defect | unverified | Detail header delta prints 'eFV 0', which reads as a grade of zero | prospx/index.html | Add a zero case to test_efv_delta_chip_display. | S | - |
| P2 | M01-18 | improvement | unverified | Show the per-tier resolved outcome receipt beside the projected outcome mix | prospx/index.html | Card test prints the tier row from the artifact. | S | - |
| P2 | M01-19 | data_source | unverified | ProspectTilt PitchIQ could put a pitch-quality chip on about 4,100 MiLB pitchers (aStuff+ covers 273) | new ingest module, storage.py, prospx/index.html | Join-rate test plus a guard that the field is absent from the efv_dataset feature spec. | M | GATE |
| P2 | M01-20 | data_source | unverified | Prospect Savant is wired to manual CSVs that are absent, so its pill renders on 0 rows | prospect_savant.py, storage.py, prospx/index.html | Join-rate test on MLBAM; the pill renders for covered AAA hitters. | M | GATE |
| P2 | M01-21 | wiring | unverified | GRPO breakout score is published nightly but not served on PROSPX | data/model_registry.json, prospx/index.html | Registry surface text matches an actual served path. | S | GATE |
| P2 | M01-22 | ux | unverified | Rank-delta chip below the top few hundred mostly reflects how tightly grades are packed | prospx/index.html | No row whose grade moved less than 0.5 prints more than N spots. | S | - |
| P2 | M01-23 | defect | unverified | Track-record panel stars unresolved deltas; conviction banner omits its CI | prospx/index.html | With the current artifact the pooled bars render no star. | S | - |
| P3 | M01-24 | ux | unverified | Level filter 'MLB' chip matches no prospect; 137 rows vanish under any level filter | prospx/index.html | Every level chip matches at least one row on the current artifact. | S | - |
| P3 | M01-25 | cleanup | unverified | Board number formatting bypasses formatMetric; a provisional card probes a graduate shard (404) | prospx/index.html | Format unit tests; no 4xx on a provisional detail load except external headshots. | M | - |

**Owner questions raised by this lane (defaults in bold).**
- Which pool defines the canonical board rank: graded plus provisional (what the board shows) or graded only (what storage bakes)? Options: Graded + provisional, baked server-side; Graded only; provisional rows shown unranked or ranked separately. **Default: Graded + provisional, baked server-side with an epoch bump.** Why: The mismatch drives M01-03 and M01-04: rank chips out of order, and 'Last board' pills on 96% of cards.
- Suppress the consensus-basis P(bust) and risk-adj on eFV-led cards now, ahead of the O6 two-chip taxonomy? Options: Suppress now; Label as consensus basis now; Wait for O6. **Default: Suppress now (display only).** Why: The #1 prospect's card shows P(bust) 35% and 5% on the same page (M01-02).
- Full third-party scouting writeups (FanGraphs, MLB Pipeline, ESPN, Just Baseball) are reprinted verbatim with attribution links on every card. Keep full text through the port, or cut to an excerpt plus link? Options: Keep full text; Excerpt + link; Link only. **Default: No change until the owner decides.** Why: This is a licensing question for the port; the ESPN and FanGraphs writeups sit behind paywalls on the source sites.
- ETA season-roll date: MLB regular-season end (2026-09-27) or the MiLB season end? Options: MLB regular-season end; MiLB season end; Nov 1 fixed. **Default: MLB regular-season end.** Why: 414 prospects show 'Late 2026' after their season ended (M01-05).
- Approve display-only ingest of ProspectTilt PitchIQ and Prospect Savant (source registry legal_risk 'ambiguous')? Options: Approve both with attribution; Approve PitchIQ only; Neither. **Default: Neither until approved.** Why: Pitch-quality coverage on the board is 273 of 8,071 rows, and the Prospect Savant pill renders on 0 (M01-19, M01-20).

### 4.2 PROSPX: Farm Systems, Leaderboards, Transactions, IL, Spotlights, Debuted, Time Machine, Scatterplots (lane M02_prospx_farm_lb)

**Census summary.** I rendered all eight lane tabs (Farm Systems plus farm detail, Leaderboards, Transactions, Injured List, Spotlights, Debuted, Time Machine, Scatterplots) at 1440 px and 390 px on port 8702. None throws a JS error; the only console errors are 404s on mlbstatic headshots.  Three P0 defects, where a reader sees a wrong number: 1. The Transactions trade audit prices MLB veterans and graduates at sunk career WAR x $/WAR. Adley Rutschman shows $201.6M there against $31.6M on /trademachine/. Across the 230 veterans that appear in both files the two valuations rank players in opposite directions (Spearman -0.40). 2. The farm Finances tab subtracts signing bonuses twice. For STL it prints three org surplus totals ($470.0M, $395.6M, $507.4M) where there should be one gross and one net figure. 3. IL stints never close when no activation transaction arrives. 22 of the 23 players on the IL since 2025 played in 2026, and 12 of them are pitchers carrying an eFV injury haircut of 0.9 or 0.7.  Other key problems: - **Spotlights eval:** editorial_eval scores flags and controls on different FV bases. On one basis, faller 30-day hits fall from 16.0% to 4.2%. The controls are the alphabetically first players never flagged, and the faller control rate is 0.0 over 4,827 draws. The registered kill-rule verdicts cannot be trusted until this is fixed. - **Org tendencies:** the trade labels count duplica...

**Served state (evidence in the lane's served_state.md).**

- All eight lane tabs live in prospx/index.html (3,243,605 bytes, 56,673 lines). Routes are #tab=farm, leaderboards, traded, injured, spotlights, debuts, timemachine and charts; farm detail is #farm-org=XXX with sub-tabs Overview, Roster, Development, Tendencies [prospx/index.html:9041-9052 (section tabs), :13736 (redirect), :30497 (renderTradeBoard has no caller)]
- Boot file data/timeseries.json is 85.9 MB raw, generated_at 2026-09-23T18:22:28Z, active_count 4679, debut_count 2764. org_summary is 30 rows and 3,449,925 bytes serialized. [data/timeseries.json keys generated_at, active_count, debut_count, org_summary]
- Headless render at 1440 and 390 px shows no JS or page errors on any lane tab; the only console errors are img.mlbstatic.com 404s. On a phone, Time Machine overflows (scrollWidth 515 at a 390 viewport) and the IL page is 44,871 px tall. [scratchpad probe_render.py, probe_mobile.py, render_report.json; shots/m_timemachine_full.png, shots/m_injured_full.png]
- Farm ranks: LAD #1 (farm_score 114.6, A+, tiebreaker 130.6); SDP #30 (90.9, F). Branch weights ACQ 8 / DEV 9 / FIN 65 / PROD 18. Spearman of farm_score against _active_surplus_net_mm is 0.812; against count it is 0.036. [data/timeseries.json org_summary[*].farm_rank, farm_score, letter_by_window['7y'], farm_tiebreaker.score, _active_surplu]
- The farm grade eval is a 2026-08-19 reduced analog. Mean Spearman: sum_surplus_mm 0.5093, sum_expected_war 0.4714, count_fv50plus 0.4646, count 0.2270. The registry row farm_grades is provisional. farm_grade_backtest.py is not wired into run_monthly. [data/farm_grade_eval.json mean_spearman; data/model_registry.json models[farm_grades].verdict]
- Storage computes the Value branch with the v40 weights 0.68/0.10/0.10/0.04/0.04/0.04. The Finances tab hardcodes the v38 weights 42/18/18/7/8/7. [storage.py:4825-4832 FARM_LEAF_WEIGHTS.financial; prospx/index.html:41288-41295 LEAF_WEIGHTS_FIN]
- The org surplus roll-up _active_surplus_net_mm is the sum of eFV surplus minus signing bonus. For STL it is 470.0 with cost 74.4; xfv.json surplus_mm sums to 544.9 and payload surplus.value_mm sums to 507.4. [storage.py:12465-12473; data/timeseries.json org_summary STL; data/xfv.json by_player surplus_mm]
- Spotlights has 60 risers, 7 rebounders and 9 fallers; 'hot' is an exact alias of risers, and all 9 fallers carry why='Rebound'. [data/timeseries.json spotlights.{risers,rebounders,fallers,hot}; spotlights.py:677]
- Editorial eval (2026-09-23), 5,585 of 7,134 flags matured. Riser: 30-day hit 0.1756 vs control 0.205, 60-day 0.2661 vs 0.2005. Rebound: kill rule 'deprecated'. Faller: 30-day hit 0.1601 against a control rate of 0.0 on control_n 4,827. [data/editorial_eval.json by_flag_type.*.horizons, kill_rule]
- 0 of 4,679 boot rows carry statcast_metrics.standout_games, so the Standout Performances ribbon always shows its fallback 'season aggregate (refresh pending)'. [data/timeseries.json players[*].statcast_metrics.standout_games; storage.py:16581-16600; prospx/index.html:16703]
- The leaderboard window slice holds 185 players (146 hitters, 39 pitchers) and 12,632 games, as_of 2026-09-20, 1,445,029 bytes, gitignored. It is built for the top 200 by overall_rank; hitter games carry no hbp or sf fields. [data/leaderboard_gamelogs.json players, as_of; run_monthly.py:2539-2548 limit=200 deadline_s=210]
- The full-season 2026 OPS board has 1,675 qualifying hitters (ab >= 50). Season chips 2021-2025 read career_stats of current actives only (2021: 179 rows). [data/timeseries.json players[*].statline, players[*].career_stats season counts]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M02-01 | defect | CONFIRMED | Transactions trade audit prices MLB vets and graduates at sunk career WAR, contradicting /trademachine/ | prospx/index.html | New test_trade_audit_basis.py: (1) the audit value path no longer multiplies career_war by _WAR_DOLLAR_VALUE; (2) for 5 named vets the audit chip value equals t | M | conflict: None. No do-not-reopen item, clock or locked owner decision covers the Trade Audit valuation basis. Two notes: - data/glossary.json documents the current two-re |
| P0 | M02-02 | defect | CONFIRMED | Farm Finances tab subtracts bonuses twice and prints three different org surplus totals | storage.py, prospx/index.html | test_farm_tree.py: gross - cost == net within 0.1 for all 30 orgs; the tile source reads the named keys. | S | conflict: none. The change is display and labels only. It does not touch the farm grade inputs, the eFV serve basis or blend, the FA AAV rule or any betting clock. The Le |
| P0 | M02-03 | defect | PARTLY | Stale open IL stints: players who played for months stay on the IL, and 12 pitchers keep an eFV injury haircut (narrowed: The core defect is confirmed and reaches readers. About 23 of the 454 IL-tab rows are players who have clearly played since their placement, and the tab, the player header pill and the farm IL count all show them as side) | stats.py, storage.py, run_monthly.py, efv_score.py | test_il_staleness.py: a placement followed by games and no activation returns not-on-IL. Artifact invariant: no is_on_il row has games dated after since. | M | conflict: none. The fix corrects the IL input only. The penalty constants and the pitcher-only scope stay as the owner set them (2026-07-15, 2026-07-17, 2026-09-04). It i |
| P0 | M02-05 | defect | PARTLY | Org-tendency trade labels built on duplicated inferred trade rows; 19 of 30 volume labels flip after de-duplication (narrowed: The trade panel on the 30 Tendencies pages is wrong, but de-duplication is only one of four stacked causes, and fixing it alone makes the labels worse (28 of 30 trade-happy).  1. Daily duplicate inferred rows: 2,827 rows) | trades.py, storage.py, org_tendencies.py, tools/ | Running inference twice on shifted snapshot windows adds no rows; trades_panel counts duplicate rows for one move once. | M | conflict: none. Org tendencies are not on the 2026-08-19 do-not-reopen list, and no betting, prospect-anchor, PROJ_PATH or HEM gate touches the trades table. Hazards (not |
| P1 | M02-04 | defect | CONFIRMED | editorial_eval scores flags and controls on different FV bases, with alphabetical controls; kill-rule verdicts unreliable | editorial_eval.py, data/editorial_eval.json, data/model_registry.json | test_editorial_flags.py: a flag and a control with identical histories score identically; the control sample is not key-sorted. | S | GATE conflict: None of the 18 do-not-reopen items and no clock is involved. Movement hit rates are not an FV-cell realized-WAR read, and no betting column family is touched. T |
| P1 | M02-06 | defect | CONFIRMED | Standout Performances ribbon permanently stuck on 'season aggregate (refresh pending)' | storage.py, prospx/index.html | Artifact invariant: standouts is non-empty in season; the ribbon source no longer contains 'refresh pending'. | S | conflict: none. The v33 payload diet (storage.py _harvest_player_detail) is a size convention, not a do-not-reopen item. No clock, locked owner decision or NEVER list tou |
| P1 | M02-07 | defect | CONFIRMED | Date-window leaderboards and player splits cover only the top 200 by rank, undisclosed | run_monthly.py, tools/build_leaderboard_gamelogs.py, prospx/index.html | The caption count equals the slice player count; with limit=0 the builder covers every active prospect with an mlbam_id. | M | conflict: none. The fix uses the MLB StatsAPI game-log feed already in use, which is not card scraping. It touches no DNR item, clock or locked owner decision. Hazards, n |
| P1 | M02-08 | defect | PARTLY | Window OBP/OPS and FIP drop HBP and sacrifice flies (narrowed: Confirmed at P1 for the leaderboard only. With a Timeframe window selected (Last 7d/14d/30d/Custom), the OBP and OPS boards and the Context slash line compute OBP as (H+BB)/(AB+BB). That runs 0.0078 low on average (worst) | tools/build_leaderboard_gamelogs.py, prospx/index.html | For a fixture player, a full-season window OBP matches the served season OBP within 0.002. | S | conflict: none. The fix touches no do-not-reopen item, clock or locked owner decision. It is not Statcast-into-projections, it adds no betting feature column, and the Sta |
| P1 | M02-09 | defect | unverified | Finances tab shows superseded v38 leaf weights; mislabeled version and two contradictory IFA ROI figures | storage.py, prospx/index.html | test_farm_tree.py: served weights equal FARM_LEAF_WEIGHTS and sum to 100; no 'v31' string in the farm masthead. | S | - |
| P1 | M02-10 | ux | PARTLY | Time Machine on a phone hides every player name and overflows the viewport (narrowed: Build it, with four corrections.  (a) Width arithmetic. The fixed tracks total 416 px. Adding 81 px of gaps (9 x 9) and 16 px of row padding gives 513 px, and the measured docW is 515. The finding's figure of 522 px is w) | prospx/index.html | Playwright at 390 px: scrollWidth equals the viewport and .tm-name has nonzero width. | S | conflict: None. This is a layout-only change: no fitted model, served accuracy claim, clock or DO-NOT-REOPEN item is touched. The hindsight WAR/yr and WAG values are alre |
| P1 | M02-11 | defect | unverified | Served Debuted rows with hitter/pitcher side conflicts the identity audit misses | identity_audit.py, data/position_overrides.json, storage.py | Identity invariant: no served debuted row whose position side disagrees with both statline and sabermetrics sides, outside the allow-list. | M | - |
| P1 | M02-12 | defect | unverified | Farm detail header mixes denominators (273 tracked beside a total FV of 156 graded) | prospx/index.html | String test: the hero line names both counts and matches the GFX wording. | S | - |
| P1 | M02-13 | defect | unverified | Debuted 'MLB stats' cell prints MiLB lines with no level tag | prospx/index.html | String test: the cell emits the level for non-MLB statlines; no wRC+ is shown under the PA floor. | S | - |
| P2 | M02-14 | improvement | PARTLY | Spotlights serves a Rebounders bucket the registered kill rule marks deprecated, with no receipt on the tab (narrowed: Build a narrower version in three ordered steps. Do not hide Rebounders now.  (a) Fix the eval as part of M02-04. Score the flags and the controls on the same basis: the snapshot median at both ends. Draw controls with a) | prospx/index.html, spotlights.py, data/model_registry.json | test_spotlights_three_buckets.py: a deprecated bucket is not emitted (or carries an editorial flag); receipt numbers equal the artifact. | S | GATE conflict: No do-not-reopen item applies, and the dark betting families, PROSPECT_ANCHOR_GATE and the proj/HEM gates are untouched. Two items need sign-off: - Owner decisi |
| P2 | M02-15 | improvement | PARTLY | Leaderboards rank raw cross-level rates at thin floors; add a Regressed view and fix $DvM+ and historical-season scope (narrowed: Do not build the SPLIT_STABILIZE Regressed toggle. The measurements above show it makes rookie-level dominance on All MiLB worse, it cannot work for ERA, and the career rows do not carry its PA/BF inputs. It would also a) | prospx/index.html | Unit port of the shrink formula; a fixture where a 60-AB 1.200 OPS ranks below a 400-AB .950 OPS under Regressed. | M | conflict: No pre-registered gate is needed: nothing fitted changes and no accuracy claim is made. One owner decision conflicts with the proposal: the code comment in rend |
| P2 | M02-16 | ux | unverified | Injured List renders all 454 rows at once and labels eFV as 'FV' | prospx/index.html | String test for the cap and the header label. | S | - |
| P2 | M02-17 | defect | unverified | Org post-TJ counts ignore the FanGraphs TJ flags that player cards show | storage.py | Invariant: org post_tj_count sum equals the count of active pitchers with is_post_tj. | S | - |
| P2 | M02-18 | improvement | unverified | Scatterplots: one dead farm axis, and no eFV or value axes | prospx/index.html | Every axis getter returns a value for at least one entity in its group. | S | - |
| P2 | M02-19 | defect | unverified | Depth chart subtitle claims level order while the default is FV, and name suffixes replace surnames | prospx/index.html | Unit test: shortName('James Tibbs III') returns Tibbs or J. Tibbs. | S | - |
| P2 | M02-20 | defect | unverified | Copy and sort keys that disagree with the displayed grade or source | prospx/index.html | String tests; artifact invariant on career_war source share. | S | - |
| P2 | M02-21 | improvement | unverified | Debuted track-record panel stars a winner inside the noise | prospx/index.html, data/xfv_eval.json | The panel renders 'tie' when the artifact interval spans 0. | S | - |
| P2 | M02-22 | data_source | unverified | Benchmark farm ranks against published farm rankings; re-run the stale farm eval on the current label | farm_grade_backtest.py, run_monthly.py, data/model_registry.json | Artifact schema test; the registry card reads the fresh figures. | M | GATE |
| P2 | M02-23 | improvement | unverified | Time Machine and the Debuted scatter download the 75 MB debuts monolith | storage.py, prospx/index.html | Slice contract test: required fields present and row count equals debut_count. | S | - |
| P2 | M02-24 | ux | unverified | Mobile farm cards repeat the logo and drop the value metrics | prospx/index.html | Playwright at 390 px: one logo and a surplus figure per card. | S | - |
| P3 | M02-25 | cleanup | unverified | Dead trade-board code, a stale AAA Statcast sidecar and dead payload fields | prospx/index.html, run_monthly.py, spotlights.py, build_site.py, storage.py | tools/dead_code_scan.py plus a payload-key reference test. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Once editorial_eval uses one FV basis (M02-04), should a Spotlights bucket that still fails its matched control be removed per the registered kill rule, or kept as labeled editorial copy? Options: Apply the kill rule as registered (hide the bucket); Keep the bucket, labeled editorial-only with its receipt; Keep as is. **Default: Apply the kill rule as registered (hide the bucket).** Why: The artifact calls the kill rule owner-committed, and the corrected eval may change which buckets clear.
- Date-window leaderboards and splits cover the top 200 prospects only. Expand to the full active pool (bigger nightly step and payload), or keep the scope and disclose it? Options: Disclose now, expand with a pre-aggregated slice; Disclose only, keep top 200; Expand raw game logs to all actives. **Default: Disclose now, expand with a pre-aggregated slice.** Why: Raw games for about 4,000 players would reach roughly 30 MB; expansion trades payload and runtime for coverage.
- In the Transactions trade audit, price MLB players on the /trademachine/ trade_value_mm basis and tag missing ones 'unpriced', or drop the verdict for trades that include an unpriced MLB player? Options: trade_value_mm plus an unpriced tag; Suppress the verdict when any party is unpriced; Remove the trade audit card. **Default: trade_value_mm plus an unpriced tag.** Why: Today the audit uses sunk career WAR, which contradicts the Trade Machine; the choice changes how many trades show a winner.
- May the pipeline close an IL stint automatically when a game is logged after the placement date (and when the roster status reads active)? Options: Yes, keep the placement in il_history; Only flag it for review; No. **Default: Yes, keep the placement in il_history.** Why: This removes stale IL rows and lifts the eFV injury penalty on 12 pitchers, which moves their grades and ranks.

### 4.3 PROSPX Draft, International, Overseas, and CollegeSavant (lane M03_amateur_college)

**Census summary.** Read-only census of the PROSPX MLB Draft/HS, International Amateurs and Overseas tabs and the two CollegeSavant apps. I rendered 38 routes on port 8703 (0 console errors), read every lane artifact and measured the college translation against its registered null. Four P0s. (1) The 2027 draft board drops all 41 high-school players from BA's Top 100, BA #1 Dylan Seward included. Cause: draft_export._consensus reads the latest BA snapshot per source, and the HS Top 150 has no rank. (2) The draft header hardcodes 'sources: FanGraphs, ESPN draft, MLB Pipeline draft' for every class; 2027 and 2028 are BA-only. (3) Six CollegeSavant deep links (leaderboards, team tendencies, draft prospects on both apps) crash on direct load with a TDZ error that the app prints into the page, so the console stays empty. (4) The pitcher projections page, and the glossary for hitters, say strikeout rate carries the signal. The table below it flags pitcher K% LOW SIGNAL, and a read-only LOO shows pitcher K% loses to the Single-A mean (MAE 4.013 vs 3.995) while BB% wins (3.138 vs 3.380). P1s: the translation eval never scores its registered null (hitter OPS ties it). The PROSPX bridge pins 75 of 505 CollegeSavant projections to HS draft records. Two classes carry is_current, so college pages call 2028 the current class. The upcoming 2027 class has 0 FV, 0 college lines and one source, and 2028 prints alpha...

**Served state (evidence in the lane's served_state.md).**

- PROSPX draft tab lazy-fetches data/draft_timeseries.json (gitignored, 15,509,029 bytes raw / 2,408,678 gz), generated_at 2026-09-23T18:11:08Z. Classes 2017-2028; 2027 and 2028 both is_current true. [data/draft_timeseries.json generated_at, classes[].is_current; prospx/index.html:23282]
- Draft class sources: 2027 and 2028 baseballamerica_draft only (251 / 150 prospects); 2018-2025 mlb_pipeline_draft + fangraphs; 2017 fangraphs only (100); 2026 mlb_pipeline_draft 255, fangraphs 188, espn_draft 155. [data/draft_timeseries.json classes[].prospects[].points[].source]
- 2027 class: consensus_rank 59/251, consensus_fv 0/251, college_stats 0/251, headshots 0/251. 2028: no rank and no FV on any of its 150. 2026: FV 276/276, drafted_pick 217, signing_bonus 202, college_stats 131. [data/draft_timeseries.json per-class field coverage]
- Default draft landing year is hardcoded PREFERRED_DRAFT_YEAR = 2026. Mock Draft and Simulate chips are hidden because no class carries mock_draft.picks (2027 draft_order empty). The Lottery view shows 30 Tankathon rows as of 2026-09-23. [prospx/index.html:23302, 23364-23371; mock_draft.py:284; data/draft_timeseries.json 2027 lottery_odds (30)]
- mock_draft_eval (2026 draft): mock rho 0.7413 vs consensus 0.7407, top10 exact 0.40 vs 0.40, top30 0.167 vs 0.133, MAE 33.27 vs 33.30; C1 PASS, C2 PASS, C3 BEAT (margin trivial per the gate doc). Served nowhere. [data/mock_draft_eval.json mock, baseline_consensus, clauses; docs/draft-2026-08-19/MOCK_DRAFT_SCORE_GATE.md:166]
- draft_consensus_weight_eval: ship false; FG Spearman 0.2304 vs Pipeline 0.1957 on n=672 (2018-2021); pooled equal rho 0.2258 / AUC 0.7069. draft_source_weights.json weights {} (equal weight). [data/draft_consensus_weight_eval.json; data/draft_source_weights.json]
- draft_live.json is a committed placeholder: year 2026, status idle, 0 picks. The War Room copy hardcodes 'draft night (July 11-13)'. [data/draft_live.json; prospx/index.html:24276]
- draft_bonus_slot_report: 7,491 picks 2017-2026, slot on 2,980, bonus on 6,269, pool_pct median 0.9378. draft_bonus_slot.json (844 KB) is read only by the pipeline, no frontend. [data/draft_bonus_slot_report.json; grep consumers]
- IFA tab: data/ifa_timeseries.json (2,567,035 bytes), classes 2021-2026; 2026: 834 signings, $187,356,680, 346 tracked, all tracked on fv_basis xfv; pool_pct on 513 of 834. [data/ifa_timeseries.json classes[0]]
- IFA rows at exactly FV 20.0: 467 across 2021-2026 (2026: 55 of 346), 364 of them flagged xfv_grade_is_floor in xfv.json; ifa_export does not carry the flag. org_spending has 31 rows (OAK + ATH $0) in 2021-2024. [data/ifa_timeseries.json signings[].fv, org_spending; data/xfv.json by_player[].xfv_grade_is_floor]
- Overseas: 41 prospects (NPB 29, KBO 10, CPBL 2, CUBA 0) and 22 curated past signings. League factors: NPB ERA 1.642 / K% +0.045 / wRC 0.87 (kept incumbent); KBO 1.249 / +0.059 / 0.749; CPBL and CUBA are priors. [data/overseas_timeseries.json leagues[].league_context; data/overseas_translation_eval.json factors (NPB n_pitchers 15, ]
- RPS-Intl+ has no IP/PA floor: Taneichi 7.2 IP -> 126, Yoon 4.2 IP -> 77. The three KBO hitters get None (cohort under 5). [data/overseas_timeseries.json prospects[].rps_intl_plus, stats; overseas_export.py:817-831]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M03-01 | defect | CONFIRMED | 2027 draft board drops all 41 HS players from BA's Top 100, BA #1 included | draft_export.py, test_draft_export_polish.py | Unit: a player with a global-rank snapshot then a later scope-only snapshot from the same source keeps rank 1. Artifact: every is_current point with ba_rank_is_ | S | conflict: none. The fix touches only the draft rank vote in draft_export.py. It does not touch consensus.py SCORED_SOURCES (BA-out rule), draft_source_weights (weights {} |
| P0 | M03-03 | defect | CONFIRMED | Six CollegeSavant deep links crash on direct load (TDZ) | collegesavant/app.js, collegesavant/pitcher_app.js, test_collegesavant_smoke.py | Extend the smoke test to boot each app with location.hash preset to every cs-tabs route and assert no 'before initialization' text. | S | - |
| P0 | M03-04 | defect | CONFIRMED | Pitcher projections copy and glossary contradict the page's own table | collegesavant/pitcher_app.js, collegesavant/app.js, data/glossary.json | Copy test: no CollegeSavant or glossary literal names which stat 'carries the signal'. Glossary example recomputed from college_translation_eval.json. | S | conflict: none. The fix fits the do-not-reopen rule that treats hardcoded accuracy claims as a banned defect class, since it replaces a literal with an eval-derived sente |
| P0 | M03-09 | defect | CONFIRMED | 2028 board prints alphabetical order as rank | prospx/index.html | DOM: no 2028 card renders a #n badge without a rank. | S | conflict: none. Showing BA's own scope rank as a label and a within-scope sort key does not touch SCORED_SOURCES, which is source_backtest.py:85 ('fangraphs', 'mlb_pipeli |
| P1 | M03-02 | defect | PARTLY | Draft header claims FG, ESPN and Pipeline sources on every class (narrowed: The main defect reproduces exactly on the served page. The rendered header names FanGraphs, ESPN and Pipeline on every class. Only 2026, the default landing class, has all three. 2018-2025 have FG and Pipeline, 2017 has ) | prospx/index.html | DOM test: the 2027 header names Baseball America and not FanGraphs. Source test: no literal source list in renderDraft. | S | conflict: None. Naming Baseball America as the display source for 2027 and 2028 is attribution only. It does not add BA to consensus SCORED_SOURCES, which the do-not-reop |
| P1 | M03-05 | defect | CONFIRMED | College translation never scores its registered null; pitcher K% loses, hitter OPS ties | college_translation.py, collegesavant/app.js, collegesavant/pitcher_app.js, data/model_registry.json | The eval carries null_mae for every factor. A served leg with skill <= 0 has no exp in the translations payload. The registry baseline appears in the artifact. | M | GATE conflict: none for the disclosure fix. Adding null_mae/skill to the eval and gating flags/copy off it changes no model, so it is display honesty like the H-6 r2 gate. The |
| P1 | M03-07 | defect | CONFIRMED | Two 'current' draft classes; college pages call 2028 current and file 2027 under history | draft_export.py, prospx/index.html | Artifact: exactly one class has role 'upcoming'. DOM: the college page's current block equals it. | S | - |
| P1 | M03-08 | data_source | PARTLY | Upcoming 2027 class has no FV, no college line and one source (narrowed: Build the college-line half now as a code change. Do not simply re-run the refresh. Calendar the FV/second-source half.  (1) Decouple the NCAA season from the draft class in college_stats.refresh_ncaa_stats. For class Y,) | college_stats.py, run_monthly.py, draft_export.py | Artifact: the upcoming class has college_stats on at least 50% of COL rows, and at least 2 sources once a second one is ingested. | M | conflict: None blocking. Filling statlines changes only display conventions: draft_stock_plus post-college nudge (±6) and rps_draft_plus (100+15z). Their registry rows ha |
| P1 | M03-10 | defect | unverified | CollegeSavant serves a Big Ten slice and a 73-pitch sample as 'the class', unstamped | collegesavant/app.js, collegesavant/pitcher_app.js, collegesavant/index.html, collegesavant/pitcher_index.html | Smoke: the default year is the largest pool, and the year option text carries n and scope. | S | GATE |
| P1 | M03-11 | defect | unverified | 216 of 518 college team codes render invented school names | collegesavant/team_names.js, collegesavant/pitcher_app.js, college_stats.py | Extend test_shared_team_resolver_resolves_codes: every payload code resolves without the titleCase fallback. | M | - |
| P1 | M03-12 | defect | unverified | IFA tab prints the eFV floor as a resolved grade with a decline arrow | ifa_export.py, prospx/index.html | Artifact: every IFA row whose xfv record is a floor has fv_is_floor true. DOM: floor rows render no arrow. | S | - |
| P1 | M03-13 | wiring | PARTLY | CollegeSavant and PROSPX never link players, so college-to-pro receipts are missing (narrowed: Build a narrower version with a corrected data source. (1) In college_translation.build, add the following to each CS_TRANSLATION entry and each bridge entry: draft_key (from the M03-06 identity fix, not the setdefault n) | college_translation.py, collegesavant/app.js, collegesavant/pitcher_app.js, prospx/index.html | Condon's entry carries milb_key and an actual A line. The draftee card renders the CS block when the bridge has the key. | M | conflict: No DO-NOT-REOPEN item covers college_translation, and display-only receipts need no gate. The hazard as written points the executor at load_single_a's source (s |
| P2 | M03-06 | defect | PARTLY | PROSPX bridge pins CollegeSavant projections to HS draft records (75 of 505) (narrowed: Re-scope the finding. The PROSPX 'Proj A (CollegeSavant)' column currently renders 0 cells for any reason: curYear is 2028 and that class has 0 bridge rows. Fixing the join alone changes nothing on PROSPX. The misjoin's ) | college_translation.py, test_college_stats.py | The Caglianone fixture maps to draft_2024_jac_caglianone. No bridge key resolves to an HS* record. | S | - |
| P2 | M03-14 | improvement | unverified | Serve the 2026 mock scorecard; revive Mock/Simulate from the lottery order | prospx/index.html, mock_draft.py, draft_export.py | The scorecard numbers come from the artifact (no literals). The provisional mock carries provisional: true. | M | - |
| P2 | M03-15 | defect | unverified | RPS-Intl+ scores 4-inning samples and mixes seasons | overseas_export.py, prospx/index.html | No row with ip < 30 or pa < 100 carries rps_intl_plus. | S | - |
| P2 | M03-16 | defect | unverified | IFA org spending lists the Athletics twice (2021-2024) | ifa_export.py, test_ifa_export.py | Every class has exactly 30 org_spending rows. | S | - |
| P2 | M03-17 | ux | unverified | War Room promises last year's draft dates | prospx/index.html, tools/draft_live_poller.py, data/draft_live.json | No literal month-day in the War Room copy. | S | - |
| P2 | M03-18 | data_source | unverified | Strength of schedule, wood-bat and combine data for the college translation | college_translation.py, college_stats.py, docs gate file | The gate artifact carries null and incumbent columns. | L | GATE |
| P2 | M03-19 | improvement | unverified | OPS leg uses the weakest predictor; 'pro profile' copy is unverified | college_translation.py, collegesavant/app.js, collegesavant/pitcher_app.js | Gate artifact. Copy test on the two phrases. | M | GATE |
| P2 | M03-20 | ux | unverified | CollegeSavant has no side gutter and no freshness stamp | collegesavant/styles.css, collegesavant/index.html, collegesavant/pitcher_index.html, data/glossary.json | Playwright: the first content box has left >= 16px at 390px and the stamp text is present. | S | - |
| P2 | M03-21 | cleanup | unverified | draft_timeseries.json ships 15.5 MB to one tab and duplicates itself | draft_export.py, prospx/index.html | Size budget test (index plus current class under 6 MB raw). | M | - |
| P2 | M03-22 | improvement | unverified | Overseas is 41 players on a factor fit from 29 transitions | overseas_export.py, overseas_promotion.py, prospx/index.html, tools overseas cohort lab | Eval accounting n rises. No zero-count chip renders. | M | GATE |
| P2 | M03-23 | ux | unverified | Glossary gaps and a contradictory CollegeSavant attribution | data/glossary.json | The glossary coverage test lists these ids. | S | GATE |
| P3 | M03-24 | cleanup | unverified | CollegeSavant asset hygiene: stale stamps, dead paths, duplicate code, root CSVs | collegesavant/index.html, collegesavant/pitcher_index.html, collegesavant/app.js, collegesavant/pitcher_app.js, build_site.py, run_monthly.py, college_stats.py | test_asset_versioning covers the CS JS files. collegesavant_box_scores has rows after a run. | M | - |
| P3 | M03-25 | ux | unverified | Small copy and label defects; IFA history window | prospx/index.html, collegesavant/pitcher_app.js, ifa_export.py | Copy tests; an artifact test for the history window if adopted. | S | GATE |

**Owner questions raised by this lane (defaults in bold).**
- CollegeSavant data: acquire the full 2025 and 2026 D1 TrackMan seasons from the vendor, or freeze at the 2024 national season and say so on the page? Options: Acquire full 2025/2026 seasons; Freeze at 2024 national, label other years as partial; Drop the partial years entirely. **Default: Freeze at 2024 national as the default view and label 2025 (Big Ten) and 2026 (partial) in the year select until full data arrives.** Why: The default views today rank a 184-row Big Ten slice and 73-pitch samples as 'the class' (M03-10). Refreshing needs the external data owner.
- BA draft report text (249,971 characters, excerpted on every 2027/2028 draft card): keep, shorten to one line with a link, or drop before the port? Options: Keep full excerpts; One-line excerpt plus source link; Drop report text. **Default: One-line excerpt plus source link.** Why: It is BA editorial copy republished on a public site, a licensing exposure similar in kind to the banned card scraping.
- Draft tab landing after the draft: stay on the last draft (2026) until results settle, or land on the upcoming class (2027)? Options: Land on 2026 until a date; Land on upcoming class (2027); Remember the reader's last class. **Default: Land on the upcoming class once it has at least one ranked source, else the last draft.** Why: PREFERRED_DRAFT_YEAR is hardcoded 2026 and two classes carry is_current (M03-07).
- CollegeSavant attribution: the glossary says both 'created by Joseph Gillis' and 'created by Noah J. Dengler, original to eephus.io'. Which line is correct? Options: Joseph Gillis (data and module), eephus integration by Noah; Noah J. Dengler; Joint credit. **Default: Credit Joseph Gillis for the data and module and eephus for CS+ and the translation.** Why: The GFX captions credit Gillis while the glossary origin claims Arkmetric. The port should carry one consistent credit (M03-23).

### 4.4 Free Agency (lane M04_fa)

**Census summary.** The /fa/ page renders cleanly. 20 Playwright captures on port 8704 (board, detail, card tabs, fits, tracker, archive, model, dpw, the 2028 and 2029 classes, dark mode, 390px) showed zero console or HTTP errors and no horizontal overflow. The problems are in what the numbers mean, not in the rendering.  The main issues: - **Bands:** 221 of 232 priced rows have an all-zero P10 WAR path, so the surplus P10 is the whole guarantee lost. That band prices a path with every season at its P10, which breaks the never-sum-quantiles rule, while the same row's total WAR P10 comes from the MC copula. - **Gate 1:** Model Accountability serves a superseded reading (0.574/0.728) while the committed artifact says 0.516/0.624. - **Gate 2:** it predates the eWAR epoch. Since then served guarantees rose 16.4% on the same 226 rows and value verdicts fell from 53 to 26. - **Archive:** the realized "eWAR" is bWAR, and the ledger is only rebuilt by hand. The 2025-26 winter has 0 of 169 rows filled. - **$/WAR:** the board prices on one series and the rail, the $/WAR view, the archive and the Club Ledger print another. - **P(enter) eval:** the pre-registered eval opens 2026-10-01 but nothing snapshots served P(enter), and the daily scrape skips October. - **Club options:** P(enter) compares the strike to multi-year AAV. Acuna's $17M option shows a 0.67 chance of being declined beside a Deal+ of 255. - **...

**Served state (evidence in the lane's served_state.md).**

- /fa/ is a static shell (build_site.build_fa, build_site.py:3620). Every view loads fa_class.json (347,021 B, 56.0 KB gz), fa_archive.json (325,929 B) and fa_meta.json (72,621 B). Board headshots also pull player_links.json (1,877,420 B, 382 KB gz). [assets/fa.js:309 Promise.all([load(clsName), load('fa_archive'), load('fa_meta')]); fa.js:447-461 EEPHUS_HUB.links(); os]
- The class is 236 members: 232 projected, 165 locked UFA, 71 pending options (club 30, mutual 26, opt_out 7, player 5, conditional club 3). n_signed 0, events []. generated_at 2026-09-23. [data/fa_class.json n_members/n_projected/members[].status,type/events/generated_at]
- Verdict split is market 142 / overpay 64 / value 26 / none 4. On 2026-08-19 it was 121 / 52 / 53. [data/fa_class.json members[].verdict; git show 56388cf7:prospect-tracker/data/fa_class.json]
- The board prices at winter $/WAR $17,143,642 with a 0.0416 escalator. The rail and dpw view print fa_dpw_series.json (2026 = $17,293,779), last written 2026-08-04. [data/fa_class.json dpw_usd, dpw_infl; data/fa_meta.json dpw_series.usd_per_war_by_winter; git log cfcba76b]
- Served fa_meta.gate1 is stale: WAR MAE 0.5736 vs 0.7279, coverage 0.7975. Committed fa_gate1_eval.json (b6b6f089, 2026-09-23 16:07) says 0.5157 vs 0.6242, coverage 0.7955. [data/fa_meta.json gate1.pooled.war; data/fa_gate1_eval.json pooled.war, coverage_p10_p90]
- Gate 2 artifact generated_at 2026-08-19T22:15:29Z, before the 2026-09-03 eWAR epoch. Pooled guarantee 9.690 vs 11.120, aav 2.909 vs 3.249, years 0.433 vs 0.487, mega 79.81 vs 95.27 (n=50). [data/fa_gate2_eval.json generated_at, pooled]
- Guarantee bias by predicted tier: lt10 -2.18, 10to20 -7.50, 20to50 -12.88, ge50 -23.46 $M. [data/fa_gate2_eval.json pooled_by_pos_group['guarantee:ptier:*'].bias_model]
- Served verdict edges are group mode: SP 86/182, RP 65/146, C 101/243, POS 103/237 (pooled 89/198). On the current basis the groups' own terciles are C 120.4/279.4 and POS 115.6/256.3. [data/fa_gate2_eval.json verdict_edges.group, recut_2026_08_19.group_own_terciles]
- 221 of 232 priced rows have an all-zero warPathP10. On those rows surplusP10 == -projGuar. [data/fa_class.json members[].warPathP10, surplusP10, projGuar]
- The Gate-1 band covers 0.915 in the top prediction decile (z +20.3) and 0.640 in decile 6. Marginal coverage is 0.7999. [data/fa_gate1_eval.json band_scale_conditional_coverage.by_pred_decile, marginal]
- Team fit Gate 3 is dated 2026-08-04. MRR 0.1669 vs random 0.1332. It is not rendered on /fa/. Served top-1 fit: WSN 60/232, CHW 56, NYM 47. [data/fa_gate3_eval.json generated_at, results; data/fa_class.json members[].fits[0].org; assets/fa.js renderModel]
- The archive holds 12 winters (2015-2026). Realized warTd is B-Ref bWAR from a CLI-only backfill. Winter 2026 has warTd on 0 of 169 rows. [data/fa_archive.json winters[]; fa_pipeline.py:60-120,462; ewar.json join (median /warTd-bw/ 0.0)]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M04-02 | defect | CONFIRMED | Model Accountability serves a superseded Gate 1; registry quotes a third number | fa_export.py, data/model_registry.json, test_fa_meta_gate_parity.py | fa_meta['gate1']['pooled'] == fa_gate1_eval['pooled'] and coverage equal; same for gate2 | S | conflict: None. The fix changes no model and reopens nothing: Gate 1 was already re-measured and committed in b6b6f089, and re-exporting only syncs the served files to it |
| P1 | M04-01 | defect | PARTLY | Surplus and season P10-P90 bands are degenerate and price a comonotone quantile path (narrowed: Scope is 56 of 232 priced rows (the multi-year terms), not 221. On those rows the card note "Surplus range, P10 → P90", the Surplus cell tap text and the expanded row detail price the comonotone per-season quantile path.) | fa_export.py, fa_mc.py, assets/fa.js, data/glossary.json | For every priced row: surplusP10 <= surplus <= surplusP90, and surplusP10 > -projGuar whenever warTotalP10 > 0. A fixture pins the MC-priced quantiles. | M | conflict: None blocks the fix. - It keeps the use_ml=False champion paths, so it does not touch "ML paths as market inputs failed" or "FA AAV stays derived". - The "never |
| P1 | M04-03 | defect | CONFIRMED | Gate 2 predates the eWAR label epoch while served prices moved +16% | fa_backtest.py, data/fa_gate2_eval.json, data/model_registry.json | test_fa_ptier_gate.py keeps generated_at and verdict_edges; assert gate2.generated_at >= the war_source epoch date | S | conflict: No do-not-reopen item is touched. A Gate 2 re-run is measurement only. It does not reopen ML market paths, the recal fit/fit_group modes or FA AAV derivation, a |
| P1 | M04-04 | defect | PARTLY | Archive 'realized eWAR' is bWAR, and the realized ledger never refreshes (narrowed: **Mechanism is wrong.** fa_pipeline.py:56-66 already reads WAR through war_source.stint_frame(side), and the default provider there is 'ewar_v2' (war_source.py:136 and 554-605). "bwar_bat" and "bwar_pitch" are only log l) | fa_pipeline.py, fa_class.py, run_monthly.py, assets/fa.js, assets/fa_dpw.js, ledger_export.py | A fixture pitcher's warTd equals the war_source season sum. The latest completed winter has non-null warTd after the scheduled step. | M | conflict: None. No clock or do-not-reopen item is touched: the realized ledger feeds no betting column or prospect-anchor cell, and FA AAV derivation is unchanged. Schedu |
| P1 | M04-05 | wiring | CONFIRMED | The frozen P(enter) eval has no snapshot writer, and October decisions are never scraped | run_monthly.py, fa_export.py, storage.py | After export the log gains one row per pending_option member for today; d10 runs when month == 10 | S | conflict: No pre-registered gate is needed, and nothing in the DO-NOT-REOPEN list is touched. The writer supplies the snapshot input that the frozen prereg (section 1.2)  |
| P1 | M04-07 | ux | PARTLY | Default board rank ignores P(enter): unlikely options sit at #2 to #4 (narrowed: Build a narrower, economically honest version. Do not ship P(enter) x projGuar as "expected guarantee" or "expected spend".  (a) Default board order: two tiers. First, rows with enterProb >= 0.5, which are the 165 UFAs p) | assets/fa.js, test_fa_table_fit.py | Under the default sort, no row with enterProb < 0.5 ranks above a UFA with a larger expected guarantee | S | conflict: No gate needed. The change is display order and labels only; no fitted model or served accuracy claim moves. Hazard: fa_penter is provisional, and docs/fa-2026- |
| P1 | M04-08 | defect | CONFIRMED | Two $/WAR series: the board prices on one, every other surface prints another | fa_export.py, assets/fa.js, assets/fa_dpw.js, ledger_export.py | fa_class.dpw_usd == winter_dpw(served series, class_year) within $1 | M | GATE conflict: Serving the in-run pricing series next to the committed one, with a basis note, conflicts with nothing. Two other routes do: (1) Re-anchoring data/fa_dpw_series |
| P1 | M04-09 | improvement | PARTLY | No qualifying-offer board; the QO tax the registry puts on /fa/ is not there (narrowed: Build a descriptive QO layer. Do not build P(offer).  (a) Views on /fa/: - Add a "QO" chip to the board type filter (fa.js renderBoard, boardState.type at 964-965). - Add a QO line to the detail/card (the parts list near) | fa_cba.py, fa_export.py, assets/fa.js, data/cba_rules.json, data/glossary.json | Every eligible UFA with projAav > the QO value appears with P(offer); cards render the QO tax | M | conflict: No gate blocks the descriptive board. The limits: - PENTER_DECISION_EVAL_PREREG freezes the enterProb champion and scores QO decisions from served snapshots (wi |
| P1 | M04-10 | data_source | PARTLY | No industry benchmark: MLBTR Top-50 and the FanGraphs crowd are never scored (narrowed: Build it MLBTR-first, and let arbitration's A6 protocol decide the result. Do not build it as a co-equal two-source live WIN/LOSS/NULL.  1. PREREQ, before early November. Add an FA prediction snapshot writer, for example) | fa_benchmarks.py, data/fa_industry_benchmarks.json, docs/fa-2026-09-24/INDUSTRY_BENCHMARK_PREREG.md, assets/fa.js | Artifact carries n, both MAEs and a CI; tracker shows the benchmark column once deals are signed | M | GATE conflict: GATE NEEDED. This adds a served accuracy claim, so a pre-registration doc must be committed before (a) any MLBTR or FanGraphs figure is joined to our backtest r |
| P1 | M04-12 | improvement | unverified | Top-decile WAR band over-covers (0.915); the known fix failed only at decile 0 | docs/fa-2026-09-24/BAND_DECILE_GATE_V2.md, fa_bands.py, fa_projection.py, data/fa_gate1_eval.json | Fold-out per-decile coverage within 0.02 of 0.80 in every decile; permuted control does not improve | M | GATE |
| P1 | M04-13 | improvement | unverified | Top-tier guarantees under-priced by $23M: re-gate the per-tier level shift with a bootstrap | fa_market.py, tools/fa_market_feature_lab.py, data/fa_gate2_eval.json, test_fa_ptier_gate.py | test_fa_ptier_gate.py carries the bootstrap fields and clause verdicts | M | GATE |
| P2 | M04-06 | improvement | PARTLY | Club-option P(enter) compares the strike to multi-year AAV, not one-year value (narrowed: Build a narrower version:  (1) Fix the diagnosis. The term discount moves Acuna's P(enter) by 0.035 (0.671 to 0.636). The visible clash (Deal+ 255 'value' beside P(enter) 67%) comes from the market model's price basis ve) | fa_market.py, fa_export.py, docs/fa-2026-09-24/PENTER_V3_PREREG.md | Unit test: a row with Deal+ > 200 and y1 rational > strike gives P(exercise) > 0.5 | M | GATE conflict: This touches the frozen P(enter) prereg (docs/fa-2026-08-19/PENTER_DECISION_EVAL_PREREG.md). The champion is frozen as v2 band-priced. 'Any deviation is a new,  |
| P2 | M04-11 | data_source | PARTLY | Dated StatsAPI transactions would replace first-seen stamps (narrowed: This is a narrower build than the finding proposes: dated signings and dated market entry, not dated option decisions. (a) Leave fa_events.event_date and the PRIMARY KEY untouched. They stay the first-seen stamp that the) | fa_pipeline.py, storage.py, assets/fa.js | A fixture transaction sets event_date; first_seen is retained; the window guard still applies | M | conflict: No gate is needed if event_date keeps its first-seen meaning. PENTER_DECISION_EVAL_PREREG.md section 1 ties the scored P(enter) to 'the decision's first-seen ev |
| P2 | M04-14 | defect | PARTLY | Team-fit concentration tripwire fails on the served class; Gate 3 invisible and stale (narrowed: Four sub-claims need correcting.  1. The tripwire fails only on the uncommitted 2026-09-23 regen, and by 2 members on 1 of 4 criteria. The committed artifact reads 0.2371 and passes. 2. The material served defect is the ) | fa_fit_backtest.py, fa_export.py, assets/fa.js | fa_meta.gate3.concentration.max_top1_share equals the value recomputed from fa_class; the Model view renders a Gate 3 table | M | conflict: Two conflicts.  1. Re-running run_fit_gate on today's class breaks the frozen ship record. fa_fit_backtest.run_fit_gate (lines 1318-1460) regenerates teamfit_co |
| P2 | M04-15 | improvement | unverified | Signing-destination probability with incumbency (ceiling MRR 0.268 vs 0.167) | fa_fit.py, fa_fit_backtest.py, fa_export.py, assets/fa.js, data/glossary.json | Forward-chained MRR beats live_analog with a bootstrap CI; probabilities sum to 1 per player | L | GATE |
| P2 | M04-16 | wiring | unverified | Afford uses Spotrac space and ignores projected arbitration the Club Ledger already has | fa_fit.py, fa_export.py, assets/fa.js | fa_meta.teams[ORG].space_net == ledger threshold - committed - arb_projected for a fixture club | M | - |
| P2 | M04-17 | defect | unverified | Verdict edges stale (group re-cut and the 7.4% quadrature), both owner-deferred | fa_market.py, fa_mc.py, data/fa_gate2_eval.json | test_fa_verdict_tooltip.py plus a per-group corpus tercile balance within 1 point | S | GATE |
| P2 | M04-18 | defect | unverified | Glossary and tooltip content errors on /fa/ | data/glossary.json, assets/fa.js, fa_market.py | Claims-freshness test: a glossary rate matches config discount_rate | S | - |
| P2 | M04-19 | improvement | unverified | Player card is thin next to PROSPX: comps without context, band without disclosure | fa_export.py, assets/fa.js | Card contains comp age/WAR and the disclosure when projAavP90 > 2.5 x projAav; JS pricer parity with rational_value_usd | M | - |
| P2 | M04-20 | improvement | unverified | Archive analytics across twelve winters | assets/fa.js, fa_export.py | Aggregates reconcile to per-winter rows; CSV exports the aggregate | M | - |
| P2 | M04-21 | cleanup | unverified | Board pays 382 KB gz for 24px photos and loads the archive on every view | fa_export.py, assets/fa.js | Board view network log has no player_links.json or fa_archive.json request | S | - |
| P2 | M04-22 | cleanup | unverified | Park factors ride in fa_meta.json and are read by betting and DFS | fa_export.py, betting_model.py, betting_ingest.py, dfs_export.py | Betting park fixture reads the new artifact; fence shows no priced betting number moves | M | - |
| P2 | M04-23 | ux | unverified | Model view prints raw keys; mobile hides views and winters | assets/fa.js, assets/site.css | Playwright at 390: all view and winter chips visible or behind a visible overflow cue | S | - |
| P2 | M04-25 | data_source | unverified | Deferral ledger misses sub-$200M deferred deals | data/deferrals.json, fa_market.py | Coverage test lists deferred-flag signings with no ledger entry | S | - |
| P3 | M04-24 | cleanup | unverified | Registry and suite hygiene for fa_* rows | data/model_registry.json | Registry claims-freshness test | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Re-cut the FA verdict group edges on the current basis, and converge the 7.4%-low quadrature in the same commit? Options: Re-cut and converge together after Gate 2 re-runs; Re-cut only; Leave as is and disclose. **Default: Re-cut and converge together after Gate 2 re-runs.** Why: Served value verdicts halved (53 to 26) after the eWAR epoch; C and POS edges sit below their own terciles; both changes move published verdicts.
- Should FA serve a signing-destination probability that includes incumbency, beside the existing fit score? Options: Yes, as a separate P(signs with) column; No, keep fit only. **Default: No, keep fit only.** Why: Incumbency was excluded by product design. The measured ceiling is MRR 0.268 vs 0.167 today.
- Re-anchor the platform $/WAR series (fa_dpw_series.json) on the current WAR label now, or at the fWAR epoch step? Options: At the fWAR epoch step; Now, on the eWAR basis; Serve the pricing series alongside and defer. **Default: Serve the pricing series alongside and defer.** Why: The board prices on an in-run series that differs from the one every other surface prints; re-anchoring cascades into prospect surplus.
- Register the club-option challenger (one-year value vs strike) as a second arm of the 2026-27 P(enter) eval before 2026-10-01? Options: Register a separate arm now, log both, keep the champion served; Skip this winter. **Default: Register a separate arm now, log both, keep the champion served.** Why: The frozen prereg forbids changing the champion mid-clock; a parallel arm is the only way to test the fix on this winter's decisions.

### 4.5 MLB Projections, player pages, Team Outlook (lane M05_projections)

**Census summary.** The MLB Projections module works: 16 routes rendered at 1400 and 390 px with 0 console errors and 0 failed requests, and the Team Outlook 2,430-win pin holds in every season. But several served numbers are wrong or contradict each other.  Worst problems: 1. The Team Win Totals accountability card contradicts itself. Its registry prose says "7.21 now BEATS 7.24". Its table prints a cohort arm that is not served (7.27 vs 7.24). Its foot says "baseline retained". 2. Pitch arsenal RV/100 colours are inverted: rv100 correlates -0.728 with BA against, n = 3,364 pitch rows. 3. Surplus is priced only through 2031 but is labeled "club control window". 39 veterans have about $2.1B committed beyond 2031 (Soto, Guerrero, Yamamoto, Ohtani). 4. /fa/ and /projections/ print different five-year WAR paths for 175 of 221 free agents (Skubal 18.4 vs 12.2). This is by design (FA uses the Marcel champion) but not disclosed. 5. The Overview "games by position" strip reads a June 22 file that nothing refreshes. 6. The player-page payload is one export behind the board: 143 surplus values differ, and one control window differs (this would fail test_the_card_and_the_board_agree_on_every_row on today's artifacts). 7. The coverage receipt shows 81-82% pooled while players who actually play are covered 43-67% of the time. 8. The "Validated" badge rests on an eval of the pre-retrain bundle. The served trai...

**Served state (evidence in the lane's served_state.md).**

- /projections/ is a static shell (projections/index.html 8,791 B) from build_site.build_projections. All logic is in assets/projections.js (213,819 B raw, 67,452 B gzip, 3,271 lines, ?v=bfdf843e). Views are hash routes: board, #view=teams, #view=accountability, [build_site.py:3763-3793, 6080-6094; projections/index.html]
- Board payload data/mlb_projections.json is gitignored, 1,270,786 B raw (239,302 B gzip), generated_at 2026-09-23 (mtime 15:58). first_season 2027, horizon 5, n_vets 1390, n_prospects 182, dpw_usd 17,971,003, dpw_infl 0.0, ros_fraction 0.024. [data/mlb_projections.json top-level keys; .gitignore:46]
- FIRST_SEASON=2027 and HORIZON=5 are hardcoded constants, so the season rollover is manual. [proj_export.py:67-68]
- League sums over vets. Served war h1..h5: 846.1/715.7/586.4/402.9/353.1. Champion warChamp: 899.2/760.8/620.0/489.8/375.4. If-healthy warPTH: 1286.0/1102.6/916.6/736.3/625.9. [data/mlb_projections.json vets[].war, warChamp, warPTH summed]
- The live bundle's train_hash is cb42b96eb5ea533c (retrained 2026-09-23; max_label_season 2025; ewar_v2; side_keyed_v1). Blend lambdas: mean 1/1/1/0.5/0.5, star 0/0/0/0/1. The registry itself says the backtests are UNMEASURED on this bundle. The brief's 6a691e0 [model/proj_lgbm/meta.json; data/model_registry.json fa_war_paths_decay notes]
- proj_horizon_eval (2026-08-19, pre-retrain, 2022-24 holdout): h1..h4 MAE 0.5394/0.4862/0.4377/0.3985 vs champion 0.6179/0.5477/0.4845/0.4239. Pooled coverage 0.81-0.82. Coverage for players who played 0.6728/0.6134/0.5489/0.4333. Star MAE 1.96/1.81/1.72/1.98. [data/proj_horizon_eval.json challenger_blocks.holdout_2022_2024 and holdout_2022_2024_champion]
- The served blend's holdout bias is -0.027/-0.046/-0.076/-0.143 at h1..h4, with MAE 0.559/0.514/0.467/0.412. [data/proj_mean_blend.json holdout_2022_2024]
- No public projection system is on disk in this repo. The only carry-forward comparison is FA Gate 1 at h1: 0.5157 vs 0.6242. On seasons of 4+ actual WAR the model is worse than carry-forward (hit 2.948 vs 2.361, pit 2.746 vs 2.404). [data/fa_gate1_eval.json pooled.war, pooled_by_side war:hit:act_ge4, war:pit:act_ge4]
- Player pages read data/mlb_player_detail.json: 5,015,382 B (1,166,697 B gzip), 1,726 players, mtime 15:48, older than the board. All 1,390 vets have a page; none of the 182 prospect rows do (they link to /prospx/). [data/mlb_player_detail.json; probe_text.py request log]
- On today's artifacts the player card and the board disagree: surTotal on 143 rows, salPath on 224, and the control keys on alec_gamboa. [diff of detail players[].proj vs mlb_projections vets]
- The games-by-position strip reads data/mlb_fielding_positions.json, generated_at 2026-06-22T21:29:00Z and never refreshed. The nightly data/fielding_innings.json is dated 2026-09-23. [assets/projections.js:2807-2916; file headers]
- Team Outlook has 30 rows. Wins sum to 2429.9-2430.4 in every season 2027-31. 2027 wins run 65.8 (COL) to 95.7 (LAD), SD 6.23. depthWar is 39.6 in 2027 and 703.6 in 2031. Roster WAR sums warChamp. Cohort intercepts are not applied. [data/mlb_projections.json team_outlook; proj_export.py:1508-1537]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M05-02 | defect | PARTLY | Team Win Totals card contradicts itself on the 2025 holdout (narrowed: The contradiction stands at P0: Metric line 7.21 beats 7.24, table 7.27 loses to 7.24, and the foot's "baseline retained" reads as if the carry-forward baseline won. Correct the finding in four places.  1. The served arm) | proj_export.py, assets/projections.js, data/model_registry.json | test_proj_export: accountability per_season[].mae == retro served_recentered.mae. Copy guard: every decimal in a registry string rendered by _accountability_blo | S | conflict: None for the display, label and registry-prose fixes. The fix must not change which arm is served: the cohort-intercept ship decision stays pinned by challenger |
| P0 | M05-07 | defect | CONFIRMED | '2026 games by position' reads a June snapshot nothing refreshes | mlb_player_export.py, assets/projections.js, test_projections_smoke.py, test_mlb_player_pages.py | The strip's as-of date equals fielding_innings.generated_at, and projections.js no longer references mlb_fielding_positions.json (mirror test_dfs_served_counts. | S | conflict: none. The fix follows the locked owner decision 24 (2026-09-11, repoint to the nightly fielding_innings.json feed). It touches no clock, do-not-reopen item or d |
| P1 | M05-01 | defect | PARTLY | Surplus stops at 2031 but is labeled 'club control window' (narrowed: Core defect confirmed as served: 39 rows (Surplus column, player hero tile, compare Surplus row, Trade Machine, Club Ledger surplus rows) price only 2027-2031 while the surrounding copy says the number covers the club co) | assets/projections.js, build_site.py, data/glossary.json, proj_export.py | No hero label says 'club control window' unless the priced seasons reach ctrlThru. After step 2: max(salPath season) == ctrlThru on contract rows. | M | GATE conflict: Step 1 (relabel): none.  Step 2 (price seasons 6+ on the decay path) collides with docs/PROJ_PATH_SHAPE_GATE.md: - Its ARM B names the fa_war_paths_decay regist |
| P1 | M05-03 | defect | CONFIRMED | Pitch arsenal RV/100 colours are inverted | assets/projections.js, test_projections_smoke.py | A smoke render with rv100 > 0 carries proj-pos. Update the fixture at test_projections_smoke.py:111. | S | conflict: none. This is a display-only colour change. It touches no model, clock, do-not-reopen item or locked owner decision. |
| P1 | M05-06 | defect | PARTLY | One player, two five-year WAR paths: /fa/ vs /projections/ (175 of 221 FAs differ) (narrowed: The core claim holds and reaches further than reported: 221 of 221 on the current class, plus the 2028 and 2029 class views. Five details are wrong.  1. The /fa/ figures in the examples (Skubal 18.4, Contreras 10.0, Lowe) | assets/projections.js, assets/fa.js, mlb_player_export.py | The detail proj carries warChamp for every vet. The Projection tab renders both totals when they differ by >= 0.5. | S | conflict: None for the display-only fix as proposed. There are two hazards. First, unifying /fa/ onto the served ML path would reopen DNR 10: ML paths as market inputs fa |
| P1 | M05-08 | defect | CONFIRMED | The player card is one export behind the board (143 surplus diffs, one control-window diff) | assets/projections.js, mlb_player_export.py, test_served_control_window_coherence.py | Extend the coherence test to sur/surNpv/surTotal/salPath, or assert the page overlays them (smoke test with a stale fixture). | S | conflict: None. The fix touches pipeline step order and the coherence test. No do-not-reopen item, clock or locked owner decision covers it. Two hazards: - The rebuild_on |
| P1 | M05-09 | defect | unverified | Glossary, footer and registry prose describe an engine that is not served | data/glossary.json, assets/projections.js, data/model_registry.json, proj_export.py | A copy guard: every decimal in glossary mlb_projections and in the rendered registry strings exists in the linked eval artifact. copy_lint passes. | S | - |
| P1 | M05-10 | wiring | PARTLY | No frozen forward vintage: the 2027 forward gate and per-player receipts cannot be scored (narrowed: Build a narrower version: a pre-registered, tracked forward vintage plus a rollover guard. Split the FIRST_SEASON derivation into its own item.  1. Add a gate doc, `docs/PROJ_FORWARD_VINTAGE_GATE.md`, committed before an) | proj_export.py, storage.py, run_monthly.py, docs/ | The ledger file hash is pinned once written. proj_history gains exactly one snapshot per run date. | M | GATE conflict: It needs a pre-registered gate doc before the vintage exists: the freeze rule, the player metric and one look after the 2027 close. It reopens no DO-NOT-REOPEN  |
| P1 | M05-11 | improvement | PARTLY | Team Outlook only ties naive carry-forward; a pre-registered stack with prior Pythag (narrowed: Build a narrower version in two steps. Leave the 2027 roll-up alone.  STEP 1 (S, no gate: measurement and copy only, no served model changes). (a) Report the served arm: - proj_export.py:2562-2575 should export the arm t) | proj_backtest.py, proj_export.py, docs/ | Registered gate criteria. test_team_outlook_calibration keeps the 2,430 sum under the new arm. | M | GATE conflict: Not a DO-NOT-REOPEN item. The exhausted correction families (section 2) are eFV-only, and nothing here touches eFV, the blend lambda or ML quantile sums (the ro |
| P1 | M05-12 | data_source | PARTLY | No public projection benchmark: archived Steamer/ZiPS WAR is reachable (narrowed: Build the benchmark, with four changes to the proposal.  A) SOURCING (owner decision). No scripted fangraphs.com pull. Two paths: - (a) The owner saves the archived Steamer bat and pit runs for 2011-2025 and ZiPS 2023-20) | public_proj_ingest.py, proj_eval.py, assets/projections.js | The artifact is dated and hashed. Eval blocks carry n and the universe definition. The render test shows the column only when the block exists. | M | GATE conflict: - Scripted access to fangraphs.com is barred by docs/SOURCE_AUDIT.md:180-183 (the ToS disposition) and the 2026-08-03 no-re-probe rule, so the proposed pull met |
| P1 | M05-15 | ux | PARTLY | Projection tab fan chart prints no numbers; projected stat lines missing (narrowed: Build a narrower version.  (a) Fan y-ticks: port the three-label yTicks block from renderCompare (projections.js:2000-2011) into fanChart unchanged. Put the numeric range into the aria-label, as compare does.  (b) Per-se) | assets/projections.js, mlb_player_export.py | A smoke render asserts the table has horizon rows and the SVG has three y labels. | S | conflict: No gate is needed. The change is display-only: no fitted model, blend lambda, or served accuracy claim moves, and the numbers already ship in data/mlb_projectio |
| P2 | M05-04 | defect | PARTLY | Coverage receipt reads 81-82% while players who play are covered 43-67% (narrowed: This is a wiring and presentation gap at P2, not a wrong number.  **What is wrong on the served card.** The pooled 81-82% coverage and its "target ~80%" tooltip read as a calibrated band. Survived-only coverage is 0.67 /) | assets/projections.js | A smoke test that the rendered table carries coverage_survived for every horizon row. | S | conflict: None. This is display surfacing of numbers already committed to the payload; it is not a model or band change, so no distribution-lane, dispersion or calibratio |
| P2 | M05-05 | cleanup | PARTLY | No binding between the eval and the served bundle; 'Validated' rests on the pre-retrain bundle (narrowed: The badge reads Validated. The only receipts shown are the 2022-24 holdout measured on 2026-06-10 (commit d957773b, challenger_blocks.holdout_2022_2024, h1 MAE 0.5394). Four changes to the recipe came after that: - the d) | proj_eval.py, proj_export.py, assets/projections.js, test_proj_eval.py, data/model_registry.json | Every proj_horizon_eval block carries bundle_train_hash. accountability.bundle_hash == meta.train_hash, or the row carries an explicit unmeasured flag. | S | GATE conflict: Fix step 3 (the badge qualifier) changes the displayed verdict. The fa_war_paths_decay registry note reserves "whether that costs this row its validated verdict |
| P2 | M05-13 | improvement | PARTLY | The 'expected' path sits under the mean at h4/h5 and is summed and priced as one (narrowed: Build a narrower version in two parts.  **(A) Now, no gate, effort S: disclose the schedule.** Read data/proj_mean_blend.json lambda_by_horizon and state, derived rather than hardcoded: - Where: the player fan subtitle () | tools/apply_mean_blend.py, proj_ml.py, data/proj_mean_blend.json, proj_eval.py | The eval block reports bias per horizon under the registered rule. Serve reads only committed parameters. | L | GATE conflict: Yes. docs/PROJ_PATH_SHAPE_GATE.md (pre-registered 2026-09-18, owner-ordered) already covers this lever: - 4.2: ARM A refits the mean-blend and star-blend lambda |
| P2 | M05-14 | improvement | unverified | Calibrate bands for players who play (conditional coverage) | proj_ml.py, proj_eval.py | Holdout coverage_survived in [0.75, 0.85] at h1-h3, and pooled coverage >= 0.78. | M | GATE |
| P2 | M05-16 | wiring | unverified | Playing time is computed but never shown; a validated PA model sits in a sibling project | fa_projection.py, proj_export.py, assets/projections.js | The payload carries pa[]/ip[] of horizon length for every vet. | L | GATE |
| P2 | M05-17 | wiring | unverified | Player pages do not link the modules that own their numbers | mlb_player_export.py, assets/projections.js | A smoke test that the Ledger/Arbitration links render on a contract+arb fixture. | M | - |
| P2 | M05-18 | improvement | unverified | No per-club drill-down in Team Outlook | assets/projections.js, assets/franchise.js, proj_export.py | Depth-chart WAR reconciles to Roster WAR within the champion-vs-served gap. | L | GATE |
| P2 | M05-19 | defect | unverified | Two $/WAR for the same 2027 season: /fa/ 17.14M escalating vs /projections/ 17.97M flat | fa_export.py, proj_export.py, fa_market.py | fa_class.dpw_usd for class Y == mlb_projections.dpw_usd when first_season == Y. | M | GATE |
| P2 | M05-20 | improvement | unverified | Sawtooth out-year paths from independent per-horizon heads | proj_ml.py | No rise above tolerance past peak age unless the champion path also rises. | M | GATE |
| P2 | M05-21 | ux | unverified | Team Outlook on a phone: 7 of 11 columns sit behind an unmarked side-scroll | assets/site.css, assets/projections.js | Extend the playwright width test in test_projections_table_fit.py to #view=teams. | S | - |
| P2 | M05-22 | cleanup | unverified | A player page costs about 8.8 MB raw; shard the 5 MB detail | mlb_player_export.py, assets/projections.js, .gitignore, deploy/ | test_publish_manifest covers the new shard dir. A smoke test that renderPlayer requests exactly one shard. | M | - |
| P2 | M05-23 | data_source | unverified | Swing+ covers 109 of 262 regulars; the Bat speed chip says 'no data' for stars | swing_plus_ingest.py, run_monthly.py | The coverage block exists, and qualified-hitter coverage is >= 0.95 after catch-up. | M | - |
| P3 | M05-24 | cleanup | unverified | Dead and stale payload fields in mlb_projections.json | proj_export.py, mlb_player_export.py, test_proj_export.py | A payload key whitelist test. | S | - |
| P3 | M05-25 | ux | unverified | Season-line formatting and tab accessibility on player pages | assets/projections.js, build_site.py | A smoke test that ISO renders three decimals and tabs carry aria-controls. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Contracts longer than the 5-season horizon (39 vets, about $2.1B beyond 2031): relabel only, or also price seasons 6+ on the champion decay path? Options: Relabel now and price 6+ later after a registered look; Relabel only; never price past the validated horizon; Price 6+ now. **Default: Relabel now and price 6+ later after a registered look.** Why: Pricing 6+ moves trade values, Ledger and Franchise surplus, and uses an unvalidated horizon.
- The /fa/ card (Marcel champion) and /projections/ (ML path) show different 5y WAR for the same player. Disclose both, or unify the displayed path? Options: Disclose both, FA pricing stays champion; Unify the display on the ML path, FA pricing stays champion; Unify on champion everywhere. **Default: Disclose both, FA pricing stays champion.** Why: DNR 10 pins use_ml=False for FA pricing. Only the display is open.
- The dark 'Current (2026)' Team Outlook slate: retire it at season end or surface postseason odds? Options: Retire from /projections/, keep /betting/ Futures; Flip on for the postseason; Keep dark. **Default: Retire from /projections/, keep /betting/ Futures.** Why: It re-runs 20,000 sims per club each export and duplicates Futures.
- Vet surplus dollar frame: keep clemens_2026 flat $/WAR with a net 7% discount, or escalate like /fa/ (4.16%/yr)? Options: Keep flat, unify the level source only; Escalate vet surplus like FA. **Default: Keep flat, unify the level source only.** Why: The frame is an owner-locked valuation set; the level mismatch (17.14M vs 17.97M) is a plain defect.
- Wire Will Cahoon's playing-time model (proprietary) as the exposure input to projections? Options: Show the engine's own exposure now, decide the license later; License and wire the PTM; Neither. **Default: Show the engine's own exposure now, decide the license later.** Why: The PTM reports better PA accuracy than the internal exposure, but the code is proprietary.

### 4.6 MLB Stats (lane M06_mlbstats)

**Census summary.** The /mlbstats/ numbers are right, but four claims and stamps are out of date. I recomputed every row of every index from the served inputs and all of them match: HEM+ 661/661, SEM+ 236/236, REM+ 510/510, DEM+ 654/654, WAR/PA+ and its _adj column 459/459. The six boards use the same 30 club codes, no row lacks an mlbam, and eWAR matches war_leaderboards on every board. All six sections load at 1440 px and 390 px with no console errors and no horizontal scroll.  The four things readers see that no longer match the artifacts: - **REM+ scorecard (P0):** it prints "market fit rho 0.5157 vs AAV". That is the leverage-weighted variant's number, from the 271-signing name-matched set the 2026-09-18 re-gate threw out. REM+ reads 0.5665 on 232 canonical signings. - **RIV+:** deprecated in the registry, but still in the Standard view, the window boards and the page meta description. Its glossary entry still carries the refuted AAV sentence. - **Freshness stamp:** past seasons and windows show "Season 2026 · through 2026-09-23". Example: the 2023 board with Judge at 458 PA. The window's 2026 slice was built 2026-09-18, so 3-season hitters are short a mean 10.3 PA. In season that gap can grow to 45 days because of the lab cadence. - **fwdHEM+ glossary:** it still claims a positive gap floor that the served-column re-gate removed. The row is provisional now.  Accuracy gaps against the owner's...

**Served state (evidence in the lane's served_state.md).**

- Route /mlbstats/ is a static shell with six tabs (Overall default, Hitters, Starters, Bullpen, Defense, Leverage). assets/mlbstats.js fills them: 314,855 B, 5,614 lines, 83,416 B gzip, ?v=7347d4f0. [build_site.py:3983-4063; mlbstats/index.html; gzip measured locally]
- All 12 renders (6 sections x desktop 1440 / phone 390) show zero console errors, zero 4xx, no horizontal page scroll. Default rows: Overall 914, Hitters 356, Starters 174, Bullpen 267, Defense 335, Leverage 309. [scratchpad/finalpass/M06_mlbstats/shots/render.json (probe_render.py, port 8706)]
- Board payloads, all stamped as_of 2026-09-23: hitter_leaderboards 842,497 B (661 hitters, 356 qualified), starter 221,438 B (236), bullpen 457,475 B (510, coverage 2358/2358 games), defense 476,941 B (654), leverage 222,987 B (662 batters, 368 starters), war_l [data/*_leaderboards.json generated_at/as_of, league, coverage keys]
- The landing section fetches war_leaderboards (42,156 B gz), war_seasons.json (1,001,614 B / 286,486 gz) for Age and G, mlbstats_windows (5,651 gz), and site-wide glossary (126,884 gz) and player_links (382,271 gz). [probe_a11y.py requestfinished list; assets/mlbstats.js:5494-5518]
- Every served plus value recomputes from its served inputs. HEM+ = 100 + 2.28*(100*woba/0.321 - 100), 661/661. SEM+ = 100*4.10/fip, 236/236. REM+ likewise, 510/510. DEM+ = 100 + 10*(rate_1000_shrunk - 0.0312)/3.2626, 654/654. WAR/PA+ and _adj, 459/459. [data/hitter_leaderboards.json pool.mean_woba, war_rate; starter/bullpen pool.mean_fip; defense_leaderboards.scale]
- The six boards share one set of 30 club codes, no row lacks an mlbam, and eWAR on every board equals the matching side on war_leaderboards (0 mismatches). [cross-join probe over data/*_leaderboards.json]
- One eWAR build everywhere: label_build_at 2026-09-03T12:35:09, provider ewar_v2, covered bat 16,857 / pit 12,527 on the boards and 16,850 / 12,519 on the history files (stamped 2026-09-17). [ewar_vintage blocks on all 12 artifacts; data/ewar.json generated_at]
- History boards: hitter/starter/bullpen/leverage cover 2021-2025, defense 2016-2025. Hitter history rows carry no wRC+, xHEM+, pWOBA or WAR/PA+. [data/hitter_history.json history.2025.hitters[0] keys; data/defense_history.json seasons]
- Windows: mlbstats_windows.json (generated 2026-09-18) serves only Last 3 (2024-2026) and Last 5 (2022-2026) to the five role boards. The live 2026 panel was built 2026-09-18. Any other span is refused. Overall folds war_seasons (2011-2026) for any span. [data/mlbstats_windows.json windows; data/mlbstats_window_l3.json panel_built_at; test_mlbstats_windows_page.py test_an_i]
- The frozen 3-year columns are read verbatim from lab artifacts: hem/sem/rem_plus_multiyear_eval (2026-08-30), dem_plus_multiyear_eval and war_rate_plus_multiyear_eval (2026-09-11), leverage_consistency_eval for gmLI 3yr (2026-08-21). [multiyear blocks on the board payloads; eval generated_at]
- Forward legs: HEM+ 0.4119 vs raw wOBA 0.4087 / OPS 0.4108 / AVG 0.2347 (3,372 pairs; gap vs OPS lo95 -0.0126). SEM+ 0.4167 vs raw FIP 0.3821 (592 pairs, lo95 +0.0177). REM+ 0.2363 vs raw FIP 0.211 (878 pairs, lo95 +0.0013). DEM+ 0.4597 vs raw rate 0.4531 (1,25 [data/hem_plus_eval.json, sem_plus_eval.json, rem_plus_eval.json, dem_plus_eval.json, xhem_served_regate_eval.json verdic]
- Registry verdicts served here. Validated: hem_plus, hem_plus_3yr, xhem_plus, sem_plus, rem_plus, dem_plus, phem_marcel_lite. Provisional: fwdhem_plus, sem/rem/dem_plus_3yr, xrem_plus, xsem_plus, leverage_board, leverage_consistency. Unvalidated (lost G2): war_ [data/model_registry.json models[].verdict for surfaces containing /mlbstats/]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P1 | M06-01 | defect | PARTLY | REM+ scorecard prints a retired market rho (the leverage-weighted variant's) under REM+'s name (narrowed: The core claim holds. Four details are wrong or overstated: (1) The 232 signings are not all canonical-MLBAM. riv_market_regate_eval.json coverage.matched_by_identity_method = {canonical_mlbam 226, normalized_name 6}. (2) | bullpen_export.py, assets/mlbstats.js | test_rem_plus.py or test_mlbstats_smoke: backtest.market_rho is absent or equals riv_market_regate_eval B1_primary.v1.rho_baseline; the scorecard never renders  | S | conflict: None. Removing the value, or copying the already-computed B1_primary.v1.rho_baseline, is a re-label of an existing artifact number, not a new measurement. Do no |
| P1 | M06-02 | defect | PARTLY | RIV+ is deprecated but still a Standard column, a window column and the meta description, and its glossary keeps the refuted AAV claim (narrowed: The defect is the refuted AAV sentence in the RIV+ glossary methodology. It is served at /glossary/#g=riv_plus, with the fold open on a deep link. The same page's Models view shows RIV+ as DEPRECATED, so the site contrad) | data/glossary.json, assets/mlbstats.js, build_site.py, mlbstats/index.html | test_claims_freshness: the riv_plus text must not contain 'at least as closely as REM+'. test_mlbstats_views: riv_plus is not in the Standard view keys. | S | conflict: The copy fix has no conflict. It reads no market data, and the next RIV+ market re-read is 2027-03-01 per registry notes; a partial-winter look is disqualifying |
| P1 | M06-03 | defect | CONFIRMED | Past-season and window views stamp 'Season 2026 · through 2026-09-23'; the window's 2026 slice is older than the stamp | assets/mlbstats.js, tools/mlbstats_window_lab.py, run_monthly.py | test_mlbstats_windows_page: render hyears=2023-2023 and hyears=2024-2026 and assert the banner names that season or window and the panel date, never the live as | S | conflict: None for the label fix. The optional nightly live-panel rebuild changes a lab cadence, not STALE_DAYS, so the do-not-reopen item 'STALE_DAYS may not be lowered' |
| P1 | M06-04 | defect | PARTLY | fwdHEM+ ('xHEM+ Blend') glossary still claims the edge the served-column re-gate took away; the range entry prints drifting live figures (narrowed: Served paths: - /glossary/#g=fwdhem_plus, "+ methodology" fold. This contradicts the same page's Models & Proofs view, which shows fwdhem_plus as provisional and "not separable". - /glossary/#g=range, "+ methodology" fol) | data/glossary.json, test_claims_freshness.py | Add fwdhem_plus (served rho and gap) and range (row count and mean) rows to the test_claims_freshness claim table, each tied by regex to its artifact key with a | S | conflict: none. The copy change is the display debt that docs/HEM_RIV_REGATE_GATE.md section 9 item 1 records for the lane that owns assets/mlbstats.js and the /mlbstats/ |
| P1 | M06-05 | defect | PARTLY | Per-hand HEM+ regresses each split toward the league instead of toward the player's own level (narrowed: Three corrections to the lane's finding.  (1) Served path. The served path is the Lineup Charts cards only. Per toggle hand, that means: - 270 slot lead numbers - 150 bench per-hand values - 30 club headers showing the v) | hem_plus.py, hitter_export.py, test_platoon_split_hem.py, docs/diamond-betting.md | Invariant: for hitters with 300+ PA, the PA-weighted mean of the two hands is within 1 point of season HEM+. The slope of that gap on (season - 100) on the serv | M | GATE conflict: 5e handedness clock (docs/diamond-betting.md section 5e, construction restarted 2026-09-10, first look ~2026-10-09). off_vs_lhp/off_vs_rhp are built from teams[ |
| P1 | M06-06 | defect | PARTLY | Two different 2024-2026 values for one player on one page (frozen HEM+ 3yr vs the Last 3 window) (narrowed: The core defect holds on the served page, but four details need correcting.  1. **The REM+ 'delta 7 on a row with all three seasons complete' is wrong.** That row is Daniel Lynch IV (mlbam 663738).    - The frozen eval h) | hitter_export.py, starter_export.py, bullpen_export.py, defense_export.py, tools/mlbstats_window_lab.py | test_mlbstats_windows: for every mlbam present on both, the board's *_3yr equals the L3 window index. | M | conflict: none. I found no conflict with any do-not-reopen item, clock, locked owner decision or NEVER list. The recipe is unchanged; only the build date differs. The hem |
| P1 | M06-09 | improvement | PARTLY | The headline hitter index ties its parents and trails xwOBA; the R1-12 re-gate is owed (narrowed: Build a narrower version in three parts. Do not bundle a v2 construction into the R1-12 registration. (A) Now, no gate, owner display decision needed (effort S to M). Show the owner the lead-column and default-sort choic) | docs/ (new gate), tools/hem_plus_lab.py, hem_plus.py, hitter_export.py | Gate artifact plus registry row update; test_hem_plus pins the v2 construction if it ships. | L | GATE conflict: Three constraints bind: - R1-12 clock in docs/HEM_RIV_REGATE_GATE.md. The pair set cannot be extended before 2026-11-15, and the hem_plus vs xwOBA re-gate runs  |
| P1 | M06-10 | improvement | PARTLY | SEM+ and REM+ were never gated against xFIP or K-BB%; no pitcher projection column (narrowed: Build a narrower version, in two parts.  (A) The load-bearing part: one pre-registered comparator gate for SEM+ and REM+ with two new baseline arms. - K-BB% in year Y, from the K, BB and TBF counts the labs already load.) | tools/sem_plus_lab.py, tools/rem_plus_lab.py, docs/ (gate file), data/model_registry.json | Gate artifacts and registry rows. test_claims_freshness entries for any new copy. | M | GATE conflict: No DO-NOT-REOPEN item is violated, with two caveats. (1) Adding comparator baselines is a new measurement, not a model change. But it moves a served accuracy co |
| P2 | M06-07 | improvement | PARTLY | No park adjustment on HEM+, SEM+, REM+ or Offense+/Rotation+/Bullpen+ (narrowed: Build in two phases, and fix the framing. Phase A (S, no gate, ship now): (i) glossary entries hem_plus, sem_plus, rem_plus, offense_plus, rotation_plus, bullpen_plus (and their _3yr/x variants) state "not park adjusted") | hem_plus.py, sem_plus.py, rem_plus.py, hitter_export.py, starter_export.py, bullpen_export.py, tools/hem_plus_lab.py, data/glossary.json | New pre-registered eval artifact; a unit test that a neutral park (100) is the identity; a join test via trades.canonical_org (CHW/SFG spellings). | L | GATE conflict: Phase A needs no gate: it is disclosure and a descriptive context column. Phase B needs a pre-registration, and three conflicts must be declared in it. (1) Ther |
| P2 | M06-08 | wiring | PARTLY | The FanGraphs line (fWAR, BsR, published wOBA, FIP-) is already fetched and discarded; only wRC+ is kept (narrowed: Build a narrower version now and route fWAR through O5.  (A) Build now, no decision needed: (A1) Backfill published wRC+ on the Hitters history boards 2021-2025. - Join in hitter_export.export_history using load_publishe) | hitter_export.py, starter_export.py, bullpen_export.py, war_board_export.py, assets/mlbstats.js, data/glossary.json | Mirror test_hitter_wrc_plus: id-join hit rate, multi-team rows read once, no derived value, a source stamp on the payload. | M | conflict: Owner decision needed for the fWAR part. O5 ("Displayed WAR at the flip") is listed STILL OPEN in _audit_2026-09-09/DECISIONS_FOR_OWNER.md:227, with plan rows a |
| P2 | M06-11 | defect | unverified | Pos (FG) includes DH time while Pos (ours) excludes it; the team sums differ by about 930 runs league-wide | defense_export.py, assets/mlbstats.js | test_defense_export_contract: team Pos (FG) is computed over fielding innings, or the team tooltip contains 'DH'. | S | - |
| P2 | M06-12 | data_source | unverified | No plate-discipline, batted-ball, speed or arsenal columns on MLB boards | new savant_leaderboards.py, hitter_export.py, starter_export.py, bullpen_export.py, defense_export.py, assets/mlbstats.js, data/glossary.json | Contract tests in the style of test_hitter_wrc_plus: join hit rate, source stamp, no derived values. | M | - |
| P2 | M06-13 | improvement | unverified | Vs-hand splits exist only inside the lineup cards; there is no sortable split view | hitter_export.py, starter_export.py, bullpen_export.py, assets/mlbstats.js | Contract test: split fields are present on every row that has a split line and blank otherwise. | M | GATE |
| P2 | M06-14 | improvement | unverified | Role boards refuse every year span except Last 3 and Last 5, and hitter/pitcher history starts in 2021 | tools/mlbstats_window_lab.py, hitter_export.py, starter_export.py, bullpen_export.py, leverage_export.py, assets/mlbstats.js | The client fold reproduces L3 and L5 exactly (the lab's reproduction block is the oracle). | L | - |
| P2 | M06-15 | improvement | unverified | No in-season date windows (last 7/14/30 days) on MLB boards; PROSPX has them | new exporter step in run_monthly.run_daily, assets/mlbstats.js | Contract test that date-window rows carry no plus index and carry the date span. | M | - |
| P2 | M06-16 | wiring | unverified | No #player= deep link into the boards and no links from team rows to Franchise/Ledger | assets/mlbstats.js, assets/projections.js, assets/fa.js | test_mlbstats_views: #section=hitters&player=670541 renders Yordan Alvarez highlighted. | S | - |
| P2 | M06-17 | defect | unverified | Leverage board refreshes monthly while the other five boards refresh nightly | run_monthly.py | A run_monthly structure test that the daily path names leverage_leaderboards. | S | - |
| P2 | M06-18 | defect | unverified | The 'wOBA' column says 'as recorded' but is recomputed with frozen 2013 weights | hitter_export.py, assets/mlbstats.js | Served woba equals the feed value for every id-joined row. | S | - |
| P3 | M06-19 | ux | unverified | Defense seasons 2016-2020 stay hidden until a history load; single-year hash ignored | assets/mlbstats.js | test_mlbstats_windows_page: 2016 is in the from-select on arrival; hyears=2023 renders the 2023 board. | S | - |
| P3 | M06-20 | cleanup | unverified | The landing section pays 286 KB gzip for the Age and G columns | war_board_export.py, assets/mlbstats.js | test_war_board_export_contract asserts age and g are present; a page test asserts war_seasons is not fetched on Current. | S | - |
| P3 | M06-21 | ux | unverified | Standard view uses 45% of desktop width; the phone tab strip clips two sections with no scroll cue | assets/site.css, assets/mlbstats.js | test_mlbstats_control_theme: the strip has an overflow affordance class at 390 px. | S | - |
| P3 | M06-22 | ux | unverified | 'Luck' means HEM+ points on hitters and wOBA units on pitchers | starter_export.py, bullpen_export.py, assets/mlbstats.js, data/glossary.json | Contract test: luck == xsem_plus - sem_plus on every starter row. | S | - |
| P3 | M06-23 | cleanup | unverified | mlbstats.js ships 1,113 comment lines and six copies of the board machinery | assets/mlbstats.js, build_site.py | The existing 85 view tests plus the windows and smoke suites must stay green. | L | - |
| P3 | M06-24 | improvement | unverified | Team boards cannot switch to 'produced for the club'; Leverage has no team view | hitter_export.py, starter_export.py, bullpen_export.py, defense_export.py, leverage_export.py, assets/mlbstats.js | Contract test: the earned-basis team sums reconcile to the stint rows. | M | - |
| P3 | M06-25 | ux | unverified | Unvalidated WAR-rate indexes sit in the Standard view beside validated ones | assets/mlbstats.js | test_mlbstats_views: the Standard view holds no key whose registry verdict is unvalidated. | S | GATE |

**Owner questions raised by this lane (defaults in bold).**
- Which hitter column should lead the board and the default sort: HEM+, which ties OPS and raw wOBA and trails xwOBA in a registry prior, or xHEM+, validated at 0.4619 on the served column? Options: Keep HEM+ first until the R1-12 re-gate reads; Lead with xHEM+ now, HEM+ second; Lead with a HEM+ v2 only if its pre-registered gate clears. **Default: Keep HEM+ first until the R1-12 re-gate reads.** Why: The owner wants the lead number to be industry-leading. The registry already records the display question as open.
- Should published fWAR sit beside eWAR v2 on Overall now, before the 2026 season-close label epoch? Options: Yes, as a published reference column like wRC+; Wait for the epoch step and switch the served WAR then; Show only the eWAR minus fWAR difference in a tooltip. **Default: Yes, as a published reference column like wRC+.** Why: fWAR is the locked frame (2026-09-09), but O1/O2 bundle the served label change at season close. A reference column does not touch the eFV label.
- Is RIV+ kept as a realized-value column (Leverage view only) or removed from /mlbstats/ entirely? Options: Keep in the Leverage view with the corrected glossary; Remove the column and the window column; Keep in Standard with a deprecated tag. **Default: Keep in the Leverage view with the corrected glossary.** Why: The registry deprecated the claim, not the arithmetic. The next market re-read is 2027-03-01.
- Should the Last 3 / Last 5 live-season slice rebuild nightly in season, costing about 75 s of winProbability walk per night? Options: Nightly live panel only; Keep the 45-day cadence and fix the stamp; Rebuild weekly. **Default: Nightly live panel only.** Why: Today the window can trail the Current board by up to 45 days while the page stamps the live date.

### 4.7 Alchemy Lab and MiLB Park Factors (lane M07_pal_parks)

**Census summary.** Both pages render clean: 0 console errors and 0 failed requests on all 7 /pal/ tabs and all 3 /parks/ tabs, at 1400 px and 390 px. I could not write FINDINGS.md: the harness refused it ("Subagents should return findings as text"), so the long-form findings are in this object. served_state.md and the probe scripts did save.  The biggest problem is the math behind SP->RP. The verdict "SP to RP is validated" rests on regression to the mean. The gate compares FIT against baselines that all assume a better pre-season predicts a bigger WAR gain, and the war_delta outcome rewards the opposite. On the live eWAR v2 series (n=61, which reproduces pal.json backtest.per_direction exactly): - FIT correlates with pre-season ERA at rho 0.623. - A "need" baseline beats FIT: +ERA_pre scores 0.521 and -WAR_pre 0.728, against FIT at 0.271. - Once pre-season ERA is controlled, the partial rho is -0.081. - On post-role WAR level, SP->RP FIT does keep a signal (0.228 against baselines from -0.21 to 0.04), so a pre-registered re-gate at the fWAR season-close epoch may keep it. - The masthead writes this verdict as static text.  Other P1 defects: - Prospect Watch prints eFV under the label "FV". 49 of 60 cards differ from ceil(consensus FV), including "FV 38" on a list whose floor is FV 40. - The park-factor glossary types split-half figures of 0.735 and 0.760 and says venue 401 (TBD) is excluded. The...

**Served state (evidence in the lane's served_state.md).**

- /pal/ is built by build_site.build_pal (build_site.py:4065-4126) and rendered by assets/pal.js (97,201 bytes). It sits in NAV_ITEMS under MLB Modules and has 7 tabs. The client defaults to sp2rp (pal.js:39), but the server nav lists rp2sp first and marks it ac [build_site.py:346, 4088-4096; assets/pal.js:39]
- The masthead verdict is static text: 'SP to RP is validated; RP to SP is a screen'. pal.js derives every other validity word from pal.json backtest.gate. [build_site.py:4086-4087; pal.js:647-760]
- data/pal.json generated_at 2026-09-23. It is 1,200,552 bytes pretty-printed, 800,269 minified and 119,636 gzipped. It is produced by run_monthly step 6b5 and is tracked in git. [data/pal.json generated_at; run_monthly.py:5880-5891]
- pal.json row counts: rp2sp 275, sp2rp 195, history 118, pitch_add 240, reverse_platoon 529 (164 shown), prospect_watch 60, prospect_watch_all 140 (no client reads this one), n_prospects 1,799. [data/pal.json list lengths]
- Live backtest on eWAR v2: RP->SP rho 0.023 (n=25), SP->RP rho 0.271 (n=61). Both reproduce exactly from pal.json history for post seasons <= 2025. [data/pal.json backtest.per_direction; probe_pal_meanrev.py]
- The gate is carried from pal_eval.json (2026-07-15, bWAR basis, same_basis_as_live false). RP->SP fails: -0.2062 vs neg_era_pre 0.1023, lo95 -0.7517. SP->RP passes: 0.2916 vs kbb_pre -0.097, lo95 0.0745. SP->RP neg_era_pre = -0.62. [data/pal.json backtest.gate; data/pal_eval.json per_direction]
- The registry row pal_conversion is provisional with provisional_kind measured_not_adopted, age 70 days. Its notes say the eWAR v2 re-gate is still owed. PAL reads war_source.DEFAULT_PROVIDER, so its live numbers will move at the fWAR epoch. [data/model_registry.json pal_conversion]
- The Pitch-Add flags EEPHUS_PAL_XRV and EEPHUS_PAL_XRV_RECO are unset in every pipeline. The served recommendations follow the incumbent rule order: Changeup 142, Slider 69, Splitter 19, Cutter 8, third pitch 2. [pal_export.py:917-918; data/pal.json pitch_add rec.add counts]
- positional_fit_ui.json is baked from positional_fit.json, which is dated 2026-08-12 and is only ever run by hand. positional_fit.json also feeds ewar.py k_inn, prospect_def_value.POS_ADJ and defense_export.py. [build_site.py:6126; positional_fit.py:1814; ewar.py:239-249; prospect_def_value.py:168]
- Position Fit numbers: nQualified 248, nFlagged 65, rows 245. Ladder r2 0.9737 on 2,023 player-seasons (2021-2026). Move-size MAE 5.682 vs carry-over 6.733 on 169 moves. Demotion AUC 0.4809, which is null. [data/positional_fit_ui.json nQualified, ladder, accuracy, demotionNull]
- /parks/ is built by build_site.build_parks with assets/parks.js (37,868 bytes) and parks.css. It is not in NAV_ITEMS. Inbound links come from the footer, the homepage card, the glossary module list, the sitemap and the Franchise club pages; 25 index.html files [build_site.py:477, 3060-3084, 4731-4776, 6054; franchise_export.py:559]
- data/milb_park_factors.json generated_at 2026-07-23; no pipeline produces it. It holds 202 venues (including 401 TBD), 1,211 club-seasons, 969 venue-seasons (930 with an HR factor). The data catalog's pinned_by field is empty. [data/milb_park_factors.json; data_catalog.py:575-580]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M07-02 | defect | CONFIRMED | Prospect Watch prints eFV labelled 'FV'; 49 of 60 cards disagree with consensus FV | assets/pal.js | test_pal_smoke: a fixture with fv 40 and fvE 37.9 renders 'FV 40' (and 'eFV 38' if both are shown). | S | conflict: none. This is a display-label fix. It does not touch serve-basis or blend lambda (pinned), the AUC leg, or any correction family, and it follows the locked owne |
| P1 | M07-01 | defect | CONFIRMED | SP->RP 'validated' verdict rests on regression to the mean; FIT adds nothing once pre-season ERA is controlled | tools/pal_backtest_lab.py, data/pal_eval.json, pal_export.py, build_site.py, data/glossary.json, data/model_registry.json, docs/ (new pre-registration) | test_pal_smoke: the masthead verdict equals verdictPhrase(gate['SP->RP']). A pal_eval test: the need baselines and the partial rho are present in the artifact. | M | GATE conflict: It does not reopen any item on the 18-item do-not-reopen list. The closed item nearest to it is "PAL stamina and naive arm gates closed", which is a different l |
| P1 | M07-03 | defect | PARTLY | Park-factor glossary types stability numbers and a venue count that /parks/ contradicts (narrowed: Replace the finding's sentence 'Only a six-season-complete subset reaches 0.751 / 0.809, so the typed figures are not reproducible' with the actual cause. The glossary figures 0.735 / 0.760 come from the deleted park_fac) | data/glossary.json, assets/parks.js, data/model_registry.json | A glossary test that milb_park_factor carries no decimal stability figure. A parks payload test that the venue count and TBD policy match the glossary. | S | conflict: none. The fix only removes or derives display copy, so it follows the do-not-reopen rule that hardcoded accuracy claims are a banned defect class. It does not t |
| P1 | M07-04 | data_source | PARTLY | MiLB park table stopped on 2026-07-23 and no pipeline rebuilds it (narrowed: Build a narrower, corrected version.  1. **One-shot refresh now.** Add a current-season staleness rule to tools/park_line_lab.py fetch_schedules, fetch_team_stats and fetch_team_splits. For a season at or after this year) | run_monthly.py, tools/park_line_lab.py, data_catalog.py, test_parks_payload.py (new), data/milb_park_factors.json | test_parks_payload: shape, contiguous window keys, stop_d.pass, generated_at recent in season. | M | conflict: None for the refresh itself. The table is display-only, the method is frozen (K_G=70, league centering, 3-season window) and no fitted model or served accuracy  |
| P1 | M07-05 | data_source | PARTLY | Position Fit rows are six weeks stale, and a naive refit would move eWAR and POS_ADJ (narrowed: Build a narrower, correctly ordered version.  The regular season ends within days, so the monthly rows mode pays off from 2027 onward. For 2026, what matters is one post-season run done before 2026-11-01.  1 (S). Put sav) | positional_fit.py, run_monthly.py, build_site.py | A rows-only run leaves fit.ladder and fit.signal byte-identical. | M | GATE conflict: Steps 1, 2 and 4 need no gate. No fitted parameter moves, and the served accuracy blocks (conversion_accuracy, demotionNull, ladder r2) are carried byte-identic |
| P1 | M07-06 | ux | PARTLY | On a 390 px phone the number each board ranks by is off screen on /pal/ and /parks/ (narrowed: Build a narrower version that reuses the /mlbstats/ phone-fit contract. No new card layout, and no title-only glyphs.  1) PAL candidate boards and Position Fit, below 641 px (same breakpoint as .mlbx), in site.css scoped) | assets/site.css, assets/parks.css, assets/pal.js, assets/parks.js | A Playwright check at 390 px that the ranked column's left edge sits inside the viewport. | M | conflict: None. Display-only layout: no fitted model, served accuracy claim, clock or DO-NOT-REOPEN item is involved.  Hazards: - pal/index.html and parks/index.html are  |
| P2 | M07-07 | wiring | unverified | Franchise MLB park-factor tiles link to a MiLB-only board; add an MLB Parks tab from fa_meta | assets/parks.js, build_site.py, franchise_export.py, test_franchise_export.py | Extend test_franchise_export.py:447 so the link keys resolve to a hash that parks.js reads. | M | - |
| P2 | M07-08 | ux | unverified | /parks/ cannot deep-link a venue, season or level | assets/parks.js, prospx/index.html, franchise_export.py | A hash round-trip unit test; the Franchise link regex. | M | - |
| P2 | M07-09 | defect | unverified | Registry claims xRV-ranked pitch-add shipped; served recommendations use the old rule order | run_monthly.py, data/model_registry.json | test_pal_export: the flag state and the rec distribution match the registry claim. | S | GATE |
| P2 | M07-10 | improvement | unverified | Pitch-add targets and a FIT component read platoon splits from under 100 TBF | pal_conversion.py, pal_export.py | A 41-TBF split yields target None. Backtest arm output. | M | GATE |
| P2 | M07-11 | improvement | unverified | SP->RP conversion_need ranks on raw ERA from as few as 20 innings | pal_conversion.py, pal_export.py, assets/pal.js | A 25-IP, 7.00 ERA line with league-average FIP does not max the component. Backtest arm. | M | GATE |
| P2 | M07-12 | wiring | unverified | Prospect Watch says 'no minors pitch tracking' while the site holds tracked stuff for a third of the list | pal_export.py, assets/pal.js | A payload test that the receipts never change mismatch_margin or ordering. | M | - |
| P2 | M07-13 | improvement | unverified | Replace the pitch-add lookup with arm-slot comps, backed by numbers and a backtest | pal_pitchadd_comps.py (new), pal_export.py, assets/pal.js, data/model_registry.json | Eval artifact plus a gate test. | L | GATE |
| P2 | M07-14 | ux | unverified | RP->SP tier names sell a ranking its gate rejected, and the server nav leads with it | pal_export.py, build_site.py | Extend test_pal_smoke's default-tab test to the server HTML. | S | - |
| P2 | M07-15 | defect | unverified | Two Position Fit glossary terms are styled as links but show no definition | data/glossary.json, assets/pal.js | A site-wide test that every data-gl slug in assets/*.js resolves to a glossary id or alias. | S | - |
| P2 | M07-16 | cleanup | unverified | test_pitch_plot_baseline pins 21 offenders that are now fixed; predicted red on the next run | test_pitch_plot_baseline.py, suite.json | The test itself. | S | - |
| P2 | M07-17 | cleanup | unverified | Pitch-plot dedupe never reached disk; 975 MB still ships | data/pitch_plots/ (regenerated), test (new budget) | Directory under 450 MB; resolve_pitch_plot_entry round trip over every file. | S | - |
| P2 | M07-18 | cleanup | unverified | Lane registry and catalog rows describe things that are not served | data/model_registry.json, data_catalog.py, tools/parks_stability_receipt.py (new) | The receipt's split-half equals the value recomputed from the served artifact. | S | - |
| P2 | M07-19 | defect | unverified | 'No model reads these factors' is false: DFS reads the MiLB table for non-MLB-home venues | dfs_export.py, build_site.py, assets/parks.js, test_fantasy_split.py | test_fantasy_split updated to match the choice. | S | - |
| P2 | M07-20 | improvement | unverified | Park estimator skips the road-mix correction and has no component factors | tools/park_line_lab.py, assets/parks.js, data/glossary.json | On a synthetic league with a known 1.20 park, the corrected estimate lands within 0.005. | M | - |
| P2 | M07-21 | wiring | unverified | Position Fit values positions on the Baseball-Reference ladder while the site frame is fWAR | positional_fit.py, build_site.py, assets/pal.js | Both ladders sum to zero over the eight fielding slots on the same basis. | M | GATE |
| P3 | M07-22 | cleanup | unverified | pal.json ships 400 KB of whitespace and about 90 KB that is unused or duplicated | pal_export.py, assets/pal.js, build_site.py | Update test_pal_json_carries_the_shape_the_catalog_promises; add a size budget. | S | - |
| P3 | M07-23 | ux | unverified | Two owner-banned words render on /pal/ | assets/pal.js, pal_export.py | A string check in test_pal_smoke, or a lint rule on pal.js label maps. | S | - |
| P3 | M07-24 | wiring | unverified | Prospect Watch is unlinked in both directions | assets/pal.js, prospx/index.html | test_pal_smoke asserts the href. | S | - |
| P3 | M07-25 | ux | unverified | Pitcher tabs carry no build date | assets/pal.js | test_pal_smoke banner string. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- When the PAL gate is re-registered at the fWAR epoch, which outcome should it use? Options: Keep war_delta and add the need baselines (+ERA_pre, -WAR_pre); Switch the primary outcome to post-role WAR level, with signed baselines; Report both, and require a pass on both for 'validated'. **Default: Report both, and require a pass on both for 'validated'.** Why: On war_delta, SP->RP FIT loses to a naive need baseline (0.271 against 0.521 and 0.728; partial rho -0.081). On post-role WAR level it beats the quality baselines (0.228 against at most 0.04). Which outcome counts decides whether the only v
- Should /parks/ add an MLB tab built from the Savant tables already in fa_meta? Options: Yes: an MLB tab plus deep links, and Franchise tiles link into it; No: keep /parks/ MiLB-only and point the Franchise MLB tiles to the glossary instead. **Default: Yes: an MLB tab plus deep links, and Franchise tiles link into it.** Why: Franchise currently sends MLB park-factor readers to a MiLB-only board. The data is already on disk and needs no fetch.
- Should the xRV-ranked pitch-add flag (EEPHUS_PAL_XRV_RECO) be switched on? Options: Flip it on in step 6b5; Leave it off and correct the registry; Leave it off and build the comp-based pitch-add (M07-13). **Default: Leave it off and correct the registry.** Why: A league-mean xRV per pitch type is a population read, so it would tell almost every pitcher to add a sweeper or a splitter. That is a served change, and it has not been adopted.
- Should Position Fit add an fWAR-frame positional column at the epoch? Options: Add an fWAR column beside the fitted ladder; Make fWAR primary and relabel the fitted ladder as the BRef-frame estimate; Leave it as is. **Default: Add an fWAR column beside the fitted ladder.** Why: The owner locked fWAR as the frame on 2026-09-09. The served ladder inverts Baseball-Reference, and POS_ADJ and eWAR sit downstream of it.

### 4.8 Trade Machine and Arbitration (lane M08_trade_arb)

**Census summary.** Both modules render with zero console errors at 1400px and 390px, and neither page scrolls sideways (the Trade Board scrolls inside its own wrapper, 620px in a 358px box). Deep links work on a fresh load: #tm=mlb:key, #tm=prospect:key and /arbitration/#teams&team=PIT. There are three P0s. (1) Every served arbitration-1 award is at or under $2.0M. There are 202 of them (median $1.34M), and Paul Skenes shows $887K at 3.96 projected WAR. The same model's backtest has arb-1 predictions up to $17.4M, and the rank correlation between WAR and award is 0.546 in the backtest against 0.151 on the served board. The cause is a gap between the features the model is trained on and the features it gets when serving: war3 and career_war are only computed for scored rows (arb_export.py:343-349), and skill metrics are looked up at the award season (arb_model.py:387). This flows through salary_path into /projections/ surplus, the Trade Machine board and evaluator, the Club Ledger and Franchise. Examples: Caminero's arbitration years 1 to 3 are priced at $0.83M, $1.36M and $2.31M, and 60% of the 1,569 arbitration-priced seasons on served paths are under $2M. (2) Arbitration Team View labels every row "Arb-eligible" and adds league-minimum pre-arb seasons into "arbitration cost". Franchise shows PIT with 13 players in arbitration class 1-4 and links to a page that says 34. League-wide, $780M of the...

**Served state (evidence in the lane's served_state.md).**

- Routes and generators: /trademachine/ is built by build_site.build_trademachine (build_site.py:3960, body _TRADE_MACHINE_BODY about line 3659, init shim 3739-3775 forwards old #view=trademachine bookmarks). /arbitration/ is built by build_site.build_arbitratio [trademachine/index.html nav block; build_site.py:351, 3801, 3915, 3960]
- data/trade_values.json (gitignored, written by tools/export_trade_values.py via bayes_trade_value): generated_at 2026-09-24, 6,434 rows (4,679 active, 1,755 debuted), 4,847,291 bytes (294,838 gzip). surplus_source counts: xfv 4,679, projection 1,126, xfv_backg [python read of data/trade_values.json keys generated_at, count, players[].surplus_source; .gitignore:24]
- Trade Board tiers: low 5,498, mid 286, minimal 285, high 196, elite 169. Grades: D 5,102, C 396, F 285, B- 229, B+ 131, B 122, A- 69, A+ 55, A 45. The 285 negative rows sum to -$3,206.8M, and 258 rows are exactly $0.0. Server trade_value_grade and trade_value_ [data/trade_values.json players[].trade_value_tier / trade_value_grade / trade_value_mm]
- The two price fields are identical on every row (posterior_surplus_mm == trade_value_mm). For the MLB evaluator path, mlb_player_detail proj.surTotal/1e6 is within $0.5M of the board value on 1,127 of 1,128 projection-priced rows. The one miss is the fernando_ [data/trade_values.json vs data/mlb_player_detail.json players[key].proj.surTotal; test_board_evaluator_price_parity.py]
- Coverage block: vets 1,390, priced_vets 1,128, unpriceable 262 (152 published as unpriced: 89 past_prearb_window, 54 service_unknown, 9 other), salary_path_rows 897, salary_path_seasons 2,299 (arb_ladder 1,101, class_closure 470, contract 728), salary_path_mod [data/trade_values.json coverage, unpriced]
- The evaluator fetches data/mlb_player_detail.json (gitignored, 5,015,382 bytes, 1,138,146 gzip, 1,726 players, generated 2026-09-23) and uses only name/pos/team/proj.surTotal/surNpv/surRos. It also eagerly fetches data/grpo_public.json (3,912,145 bytes, 504,88 [assets/trademachine.js:182, :1422; file sizes; grpo_public.json scored_count/included_count]
- Default Trade Board sort is 'eFV grade' (value trade_desc maps to xfv_grade). 1,582 of 1,755 debuted rows carry a locked backgrade xfv_grade, so the served order puts Correa 6th, Seager 10th, Bryant 13th and Bogaerts 14th, all with negative surplus. [assets/trademachine.js:560-637; render probe_facts.json tm_desk_first_rows]
- data/trade_machine_eval.json generated 2026-08-19, ship false. slice_a: n 2,333, pooled Spearman 0.3289 vs consensus 0.3312, xfv_grade 0.3433, AUC 0.7707, tiers won 1/4. slice_a_prime (2026-06-25): projection 0.0152 (n 621), xfv_backgrade 0.5596 (n 701). forwa [data/trade_machine_eval.json; data/model_registry.json models[model_id=trade_machine_surplus]]
- prospects.db trade_value_history now holds 64 snapshot dates (2026-06-25 to 2026-09-23), 389,094 rows. Read-only rank stability of trade_value_mm: 08-23 to 09-23 all 0.807 / active 0.954 / MLB 0.764. 09-16 to 09-23: MLB 0.804, which shows the salary-path epoch [sqlite mode=ro query on trade_value_history; scipy spearmanr]
- Registry rows touching the lane: arb_award provisional; control_window_salary_path provisional (gate_c2 not scored); trade_machine_surplus provisional; surplus_downside_risk provisional (no eval); xfv_backgrade provisional; grpo_prospect unvalidated (forward g [data/model_registry.json models[]]
- data/arbitration.json (tracked, arb_export.py): generated_at 2026-09-23, season 2027, 853 rows, 162,651 bytes. Class counts c: 0 588, 1 57, 2 111, 3 80, 4 17. tot sums $2,041.2M, of which $780.0M is PRE-ARB minimum. 87 rows have tot null. Flags: 13 on 711 rows [python read of data/arbitration.json rows[].c/e/tot/l]
- The served ARB 1 steps (n 202) have median $1.34M and max $2.0M. Paul Skenes is at $887K with w 3.96. Spearman(w, award) is 0.151 on the served board versus 0.546 in the arb_history backtest. [data/arbitration.json rows[].l, w; data/arb_history.json rows[4]==1]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M08-01 | defect | CONFIRMED | Served arb-1 awards collapse to the league floor because the model gets different features when serving than in training | arb_export.py, arb_model.py, test_arb_export.py, test_salary_path_must_not_move.py | test_arb_export.py::test_served_arb1_responds_to_production: on data/arbitration.json, Spearman(w, ARB 1 usd) >= 0.35, and the median ARB 1 step for w>=3 is wit | M | conflict: None of the 18 do-not-reopen items or the owner's locked decisions apply. The GATE A frozen champion tuple is kept, because the fix fills existing keys and adds |
| P0 | M08-07 | defect | PARTLY | Trade Machine masthead, meta, GFX caption and glossary describe Bayesian scarcity/opt-out pricing the board no longer uses (narrowed: The defect holds and is worse than stated: it is not a 'stale second currency' but a category error, because career WAR counts pre-trade seasons. Build this narrower, cheaper fix inside the audit block of prospx/index.ht) | build_site.py, assets/trademachine.js, build_glossary_data.py, data/glossary.json, data/model_registry.json | Copy test: the /trademachine/ shell may not contain 'positional scarcity' or 'opt-out adjusted' while the bayes_unrepointed share is under 5%, and the glossary  | S | conflict: No pre-registered gate: this changes neither a fitted model nor a served accuracy claim. It is valuation wiring on a display surface and completes the already-p |
| P0 | M08-08 | ux | CONFIRMED | Arbitration History renders 400 of 772 rows with no pager, filter, sort or the promised per-season summary | assets/arbitration.js, arb_export.py | Render test: every history row is reachable by pager or filter, and the per-season means equal the artifact. | M | conflict: none. This is a relabel and column split of served sums. It does not touch the arb_award model, the FA AAV derivation, any betting clock, or any do-not-reopen i |
| P1 | M08-02 | defect | CONFIRMED | Arbitration Team View labels pre-arb players as arb-eligible and adds league minimums to arbitration cost, contradicting Franchise | assets/arbitration.js | Render test: for every club, the Team View class 1-4 count equals franchise_board.json n_arb, and no column labelled as arbitration cost includes a PRE-ARB step | S | conflict: The proposed order (repair M08-01 first, then run the lab "verbatim") conflicts with three things: - The ship-day invariant in section 11f of docs/ARBITRATION_G |
| P1 | M08-03 | defect | CONFIRMED | Trade Board default order ranks MLB veterans by a hidden, frozen prospect-era eFV grade | assets/trademachine.js, test_trades.py | test_trade_board_default_order: under the default sort in the MLB pool, no debuted row with trade_value_mm<0 ranks above a debuted row with trade_value_mm>0. | S | conflict: none. The summary strip must print the vs Market and vs Value sums separately. test_arb_export.py::test_no_combined_residual_column_exists regex-bans `ou_mkt +  |
| P1 | M08-04 | defect | PARTLY | The MLBTR ledger loader discards 633 Swartz projections, blanking the History MLBTR column and shrinking the Swartz comparison to one season (narrowed: Build a narrower fix than proposed. No name resolver, no collision publication. (a) Add arb_dataset.load_ledger_projections(). It returns {key: {class_year: projected_usd}} from projection-kind entries only, keyed by bbr) | arb_dataset.py, arb_export.py, tools/arb_gate_a.py, data/arbitration_eval.json, test_arb_dataset.py | test_arb_dataset.py::test_ledger_keeps_both_kinds_per_class_year, plus an artifact test that arb_history.json Swartz coverage per season is at least 80% of the  | S | conflict: No do-not-reopen item is hit. The Swartz ledger rows are on disk, and this repairs a join, not a feature arm; A6 is a recorded NULL, not a closed family. The Hi |
| P1 | M08-05 | defect | CONFIRMED | Gate A scores the award model with same-season production, which the estimand forbids | arb_model.py, arb_export.py, arb_dataset.py, tools/arb_gate_a.py, data/arbitration_eval.json, docs/ARBITRATION_GATE.md | Unit test: for a season-S row, no feature reads a season >= S. | M | GATE conflict: None on the do-not-reopen list, no clock, and no locked owner decision. The grade default was an agent change (H-1, 2026-07-05), not an owner lock, and its prem |
| P1 | M08-06 | defect | PARTLY | Gate C2 is registered and its lab exists, but it has never been scored while the salary path has been served since 2026-09-16 (narrowed: **Confirmed:** - There is no method or version column, and the snapshot writer stamps none. - 64 dates and 23 flagged pairs. - The four example rhos and dollar deltas; they are common-key sums.  **Overclaims to fix:** 1.) | data/arbitration_eval.json, build_site.py | test_gate_c2_is_scored_when_salary_path_mode_is_full: fail rather than skip when SALARY_PATH_MODE is 'full' and the block is absent. | S | GATE conflict: No do-not-reopen item, clock or owner decision is touched. TRADE_FORWARD_GATE is frozen for the 2026-08-19 run, so the epoch-segmentation clause has to be regis |
| P1 | M08-09 | improvement | unverified | Arbitration board renders 4 of 11 payload fields and has no player links or working sort | assets/arbitration.js, arb_export.py | Render test: every documented payload key is rendered or explicitly listed as hidden; header click reverses the order. | M | - |
| P1 | M08-10 | improvement | unverified | Add an arbitration comparables table from the site's own settled cases | arb_export.py, assets/arbitration.js | Comps share the row's step, are sorted by distance and never include the row's own player. | M | - |
| P1 | M08-11 | wiring | unverified | Trade Machine has no salary side: add payroll, CBT and salary matching from Club Ledger | assets/trademachine.js, ledger_export.py | Evaluator salary totals equal the sum of the moved players' salPath values, and the club payroll delta equals the moved salaries. | M | - |
| P1 | M08-12 | improvement | unverified | /trademachine/ carries no receipts panel even though its eval exists | build_site.py | Rendered numbers equal the artifact (test_claims_freshness pattern). | S | - |
| P1 | M08-13 | improvement | unverified | Re-run the trade-value forward backtest at 60/90 days with a split at the 2026-09-16 salary-path change | tools/trade_value_forward_backtest.py, data/trade_machine_eval.json, docs/trade-2026-08-19/TRADE_FORWARD_GATE.md | test_trade_forward_backtest.py plus an epoch-split key assertion. | S | GATE |
| P1 | M08-15 | data_source | unverified | Pre-register a 2027 forward arbitration ledger against MLBTR and a filing-vs-award tracker before the tender deadline | docs/ARBITRATION_GATE.md, tools/ingest_arbitration_ledger.py, assets/arbitration.js, arb_export.py | Frozen snapshot hash test: the 2027 predictions cannot change after the freeze date. | M | GATE |
| P1 | M08-17 | improvement | PARTLY | Deals cannot be shared or re-opened; encode both sides in the URL (narrowed: Build a narrower version, in this order.  (1) FREEZE NOW, effort S, before 2026-10-01. The MLBTR projection post has landed in October every year. Copy these fields per row of data/arbitration.json into a tracked data/ar) | assets/trademachine.js | DOM test: a deal hash restores both sides and their totals. | S | conflict: 1. docs/ARBITRATION_GATE.md section 4 A6 and section 8 pre-commit that single-season Swartz comparisons are NULL and that none is published. A standalone 2027 o |
| P2 | M08-14 | defect | unverified | GRPO forward look became due 2026-09-18 and was not run, while the breakout chip flags 35% of prospects | assets/trademachine.js, data/model_registry.json | Chip count stays at or under 10% of active rows while the registry verdict is not validated. | S | GATE |
| P2 | M08-16 | wiring | unverified | Org filter on the Trade Board should open a club needs and depth strip from Franchise | assets/trademachine.js, franchise_export.py | Strip values equal the franchise_board.json leaves for that club. | M | - |
| P2 | M08-18 | defect | unverified | Negative evaluator totals print as '$-59.1M' | assets/trademachine.js | Extend test_number_format_parity.py to the evaluator totals. | S | - |
| P2 | M08-19 | defect | unverified | Three key collisions put two different people behind one key in the evaluator | tools/repair_fernando_cruz_collision.py (new, pattern), prospects.db | test_identity_collisions.py: no key may resolve to different people (mlbam) across trade_values.json and mlb_player_detail.json. | M | - |
| P2 | M08-20 | cleanup | unverified | Evaluator downloads 9 MB for six fields plus an unused sidecar | assets/trademachine.js, tools/export_trade_values.py, .gitignore, deploy/data_exclude.txt | Payload budget test in the pattern of test_arb_export first-paint budget. | S | - |
| P2 | M08-21 | improvement | unverified | CBA expires in 68 days: pre-register the response and stop hardcoding 2027 in arb_export | arb_export.py, docs/ARBITRATION_GATE.md | No literal season years in arb_export.py outside the rules source. | S | GATE |
| P2 | M08-22 | ux | unverified | Trade Machine layout: empty evaluator fills the first screen, 79% of rows grade D, and the tier filter misses 90% of the board | build_site.py, assets/trademachine.js, assets/trademachine.css | Render test: the tier chips cover every served trade_value_tier value. | M | - |
| P2 | M08-23 | defect | unverified | 87 arbitration rows publish no price at all | arb_export.py, assets/arbitration.js | No row with a non-empty ladder publishes tot null without a stated reason. | S | - |
| P2 | M08-24 | wiring | unverified | Price the 2026 deadline's real deals at the snapshot before each deal | tools/export_trade_deals.py (new), assets/trademachine.js | Each deal's side totals equal the snapshot values of its players. | M | - |
| P3 | M08-25 | cleanup | unverified | Stale comments, a payload doc that contradicts the page, and small interaction gaps | assets/trademachine.js, assets/arbitration.js, arb_export.py, build_site.py | field_key wording assertion; hashchange DOM test. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Once the arb-1 serving fix (M08-01) and the look-ahead amendment (M08-05) land, should Gate A be re-run before Gate C2 is scored, even if arb-1 might drop from PASS to NULL? Options: Fix M08-01, register the M08-05 lag amendment, re-run Gate A, then score Gate C2; Fix M08-01 only and score Gate C2 now; defer the look-ahead amendment; Score Gate C2 on the current artifact as registered, accepting that C2' probably reverts SALARY_PATH_MODE to off. **Default: Fix M08-01, register the M08-05 lag amendment, re-run Gate A, then score Gate C2.** Why: Gate C2 clause C2' scores the served salary path against realized 2026 awards. On today's artifact it would score the feature-skew defect and, per the pre-registered 11e responses, turn the whole salary path off.
- When the MLBTR/Swartz 2027 projection is available, may /arbitration/ show it next to our 2027 figure with attribution? Options: Show Swartz beside ours with attribution; ours stays the served number; Show only ours; keep Swartz for the scored ledger after the winter; Serve Swartz for the next season and ours for later seasons. **Default: Show only ours; keep Swartz for the scored ledger after the winter.** Why: Swartz is 2.66x more accurate (about 2.9x on a fuller descriptive re-join). Showing it helps readers but involves republishing third-party figures, and serving it would replace our model for that step. Both need an owner decision on sourcin
- Should the Trade Board's default sort be Surplus for the All and MLB pools, with eFV grade kept only for the MiLB pool? Options: Surplus default for All and MLB; eFV grade for MiLB; Surplus default everywhere; Keep eFV grade everywhere but show the key in the FV column. **Default: Surplus default for All and MLB; eFV grade for MiLB.** Why: The current default ranks veterans by a frozen prospect grade, and that choice has no evaluation behind it. The eFV grade ordering is only evaluated on prospects.
- How should the arbitration board respond if the CBA expires on 2026-12-01 without a new agreement, or if a new agreement changes arbitration? Options: Keep carry-forward with a louder flag; Unprice seasons from 2027 on until terms are published; Price under published terms once they are available and flag the change. **Default: Keep carry-forward with a louder flag.** Why: Every row assumes the 2022 CBA carries forward. A response should be pre-registered before any outcome is known so it is not chosen after the fact.

### 4.9 Club Ledger and Franchise (lane M09_ledger_franchise)

**Census summary.** Club Ledger (/ledger/) and Franchise Overview (/franchise/) both render cleanly: 30 captures at 1280 and 390 in both themes, 0 console errors, 0 failed requests. The only overflow is 4 px on the Ledger Method tab at 390. The CBT math is exact: the computed 2026 bill matches Spotrac to the dollar for all 9 payors. The Franchise branch scores and the Franchise Index recompute from the served pools.  The served defects: - The ledger's Graduates block prints debuted_player_value with 7 control years left on all 2,239 valued rows and consumed control 0 on all 2,456 debuts_lite rows. 36 rows sit at a 523.6 $M ceiling, including Kevin Ginkel at an 83% bust posterior (P0). Likely cause: service_years_decimal is absent from 2,764 of 2,764 rows and the code falls back to 0. - Cost+ divides contract-only CBT payroll by full-roster projected WAR. Spearman with payroll is -0.867, 21 of 30 clubs print below 100, and TBR sits at 140. A same-coverage version puts TBR at 104 (rho 0.718 with the served index). This needs an owner decision because the index is re-served on /franchise/. - The Spotrac 2027 CBT payroll is below the AAV of the club's own guaranteed 2027 contracts for BOS (-24.3M), TBR (-18.0M) and TEX (-4.1M). - /franchise/ says futures.json has no registry row, but playoff_odds_sim is registered (provisional). - /franchise/ labels the Trade Machine currency as "Roster surplus EV" be...

**Served state (evidence in the lane's served_state.md).**

- /ledger/ shell is build_site.build_ledger (build_site.py:4866): tabs League, Club, Rules, Method. Hash grammar: #section=..., #section=club&team=CODE[&season][&block], shorthand #team=CODE. Assets: ledger.js (1,231 lines, 105,615 chars), ledger.css 20,548 B. [build_site.py:4866-4912; wc on assets]
- /franchise/ shell is build_site.build_franchise: tabs Club and Board. Hash: #team, #view=board/club, #tree=hidden/canopy/full, #sec. Assets: franchise.js (820 lines, 61,439 chars), franchise.css 15,849 B. Nav: Franchise first in MLB Modules, Club Ledger after  [build_site.py:346,356,4916-4960]
- data/ledger_board.json is 932,530 B (234,501 gzip), generated 2026-09-24T05:28:32Z. It has 30 clubs and 125 copy strings; the what_this_page_does_not_claim list has 22 lines. [ledger_board.json generated_at, copy, what_this_page_does_not_claim]
- 30 tracked shards, data/ledger_clubs/CODE.json, 84,252 to 96,761 B. Settings: preview_n 10, cap 160,000, board guard 950,000. The shards are fetched after paint. [ledger_board.json shards; ledger.js:130]
- data/franchise_board.json is 1,032,936 B (262,048 gzip); clubs[] makes up 1,005,417 of 1,033,492 compact bytes. The test budget is 1.5 MB. [test_franchise_export.py:485; byte probe]
- Cost+ as served: 21 of 30 clubs below 100, median 96, max TBR 140. Spearman(tax payroll 2027, Cost+) is -0.867; the skew of WAR per $M is 2.47. [ledger_board.json league.rows[].cost_plus; probe_costplus.py]
- The computed 2026 CBT bill equals Spotrac's estimate for all 9 payors (LAD 180,377,935 ... ATL 2,557,055). [ledger_board.json clubs[].cbt.2026.computed_bill_usd vs spotrac_est_bill_usd]
- Footer means: Spotrac average committed_2027 is 127,764,025 (fetched 2026-07-07); the mean of the 30 club rows is 144,788,882.1 (fetched 2026-09-23). copy.footer_means_note calls the 17.0M gap a vintage gap. [ledger_board.json league.averages_row, league.means]
- arbitration_eval on the board: n 261, our MdAPE 0.2156, Swartz 0.0811, ratio 2.659, verdict NULL. [ledger_board.json arbitration_eval]
- Franchise Index weights: roster 0.4, outlook 0.3, farm 0.3. The raw weighted mean has sd 8.813 and is re-standardised to 10.012. Branch correlations: roster-outlook 0.752, roster-farm 0.586, outlook-farm 0.639. [franchise_board.json weights, league.pools/scores; board correlations]
- Dark ledger blocks: payroll_history, dead_money, retained, ifa_history, draft_pool_2021, qo_pending, single_payroll_line (not served by decision), arb_quantiles, arb_comps, arb_filing, opt_out_value, farm_trade_cost_basis, grad_contract_per_graduate, farm_year [ledger_board.json sections]
- Registry rows for the lane: franchise_index and franchise_branch_score unvalidated; org_sur_plus unvalidated; team_win_projections, farm_grades and arb_award provisional; playoff_odds_sim provisional (eval data/futures.json, last validated 2026-09-06). No row  [data/model_registry.json models[]]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M09-01 | defect | CONFIRMED | Graduates block prints debuted_player_value with 7 control years left on every row (Ginkel 523.6 $M) | storage.py, value_framework.py, ledger_export.py, assets/ledger.js, data/model_registry.json | New test_debuted_value_control_clock.py. On debuts_lite: no row with a debut year of 2024 or earlier has consumed 0; remaining<=7-consumed; no dv trade value ex | M | conflict: none. This is Club Ledger arithmetic on draft_results and the published team pools. It touches no do-not-reopen item, clock, betting column family or locked own |
| P0 | M09-02 | defect | CONFIRMED | Cost+ divides contract-only payroll by full-roster WAR, so it ranks roster youth, not cost | ledger_export.py, assets/ledger.js, franchise_export.py, data/glossary.json | test_ledger_export: numerator and denominator row keys are equal; mean 100 and sd 10 on the log basis; TBR's Cost+ reads its 2027 contract cells, not tax_payrol | M | GATE conflict: none. The fix is a display change and a source change for one served column. It touches no do-not-reopen item, clock, locked owner decision or NEVER list. The D |
| P1 | M09-03 | defect | PARTLY | Spotrac 2027 CBT payroll is below the club's own guaranteed 2027 AAV for BOS, TBR and TEX (narrowed: Build it, with corrected numbers, a wider scope and a different source.  Numbers: - 161 counts only contracts (rows or unpriced) against rows_debuted. The full count is 196 keys on two club pages. The war-board split is ) | ledger_export.py, fa_sources.py, assets/ledger.js | test_ledger_export: accountability.tax_floor_census names exactly the failing clubs with their gaps; a render test checks the chip appears. | M | conflict: None. This changes no fitted model and no served accuracy claim, and it is not on the DO-NOT-REOPEN list.  The current_roster basis was an owner choice for the  |
| P1 | M09-04 | defect | CONFIRMED | /franchise/ ODDS says futures.json has no registry row; playoff_odds_sim is registered | franchise_export.py, assets/franchise.js, test_franchise_export.py, test_franchise_render.py | Invert the pins: the odds verdict equals the registry row's verdict. Add a registry-parity test over every section with a verdict_model. | S | conflict: none. No do-not-reopen item, clock or locked owner decision covers graduate attribution. Changing PROSPX org_summary moves the served farm letters (FARM_LEAF_WE |
| P1 | M09-05 | defect | CONFIRMED | /franchise/ 'Roster surplus EV' is the trade currency and already contains the Farm surplus printed beside it | franchise_export.py, assets/franchise.js | test_franchise_export: the FIN surplus equals ledger_board clubs[c].surplus.total_mm, or it carries the overlap copy key. | S | - |
| P1 | M09-06 | defect | CONFIRMED | 2026 draft picks read 'still active' only when the prospect tracker carries the player (357 of 565 untracked) | ledger_export.py, assets/ledger.js | test_ledger_export: picks_summary carries n_signed, n_tracked and n_untracked, with n_tracked + n_untracked == n_signed. | S | conflict: none. The fix adds copy that comes from an exact-match reconstruction and changes the display. It does not touch any clock, any do-not-reopen item or any locked |
| P1 | M09-07 | wiring | PARTLY | Option and opt-out calendar from the FA module's 71 pending-option rows (narrowed: Build a narrower, concrete version in two steps.  Step 1 ships now and needs no decision (copy only): - Add one sentence to the glossary cost_plus methodology and to the ledger column notes for cost_plus, usd_per_win and) | ledger_export.py, assets/ledger.js, franchise_export.py, data/glossary.json | test_ledger_export: every pending_option row appears exactly once in the calendar with holder and price, and no calendar row enters commitments.by_season. | M | conflict: No pre-registered gate is needed. Cost+ has no registry row and makes no accuracy claim ('no registry row: Cost+ predicts nothing'), and nothing here touches a  |
| P1 | M09-08 | ux | unverified | The club ledger (19,588 px at 1280) and the franchise club page have no block index | assets/ledger.js, assets/ledger.css, assets/franchise.js, assets/franchise.css | test_ledger_render: the index lists every rendered block in order. Playwright sweep: no overflow at 390. | S | - |
| P2 | M09-09 | improvement | unverified | Payroll history 2016-2025: the cache-only seam does not exist yet | fa_pipeline.py, fa_sources.py, scrapers.py, run_monthly.py, ledger_export.py, assets/ledger.js | test_fa_pipeline: refresh_payroll(cache_only=True) makes no network call (monkeypatched socket). Each history row prints its own season's threshold. | M | - |
| P2 | M09-10 | data_source | unverified | The Spotrac Averages-row parser is owed; the footer claims a cause for the 17.0M gap without a measurement | fa_sources.py, fa_pipeline.py, ledger_export.py | A parser fixture with an Averages row. A ledger test: the averages and club rows share a fetched_at, or the note says unmeasured. | S | - |
| P2 | M09-11 | improvement | unverified | Dead-money and retained blocks need one table_id tag; released players ride the vet set | spotrac.py, ledger_export.py, assets/ledger.js | accountability.contract_set_sha is unchanged; the dead block sums equal the dead table per club; released players leave n_vets. | M | - |
| P2 | M09-12 | ux | unverified | Copy defects: run-on joins, a 'Sur+ sums' mislabel, and a truncated roster note | ledger_export.py, assets/ledger.js, franchise_export.py | Copy lint over both payloads: sentence strings end with a stop, and no rendered paragraph has a lowercase word after '. '. | S | - |
| P2 | M09-13 | ux | unverified | Raw field names and mixed units printed as reader labels | franchise_export.py, assets/ledger.js, ledger_export.py | A render test: no leaf label matches ^[a-z_]+$, and each farm leaf renders its unit. | S | - |
| P2 | M09-14 | ux | unverified | The League table never prints the CBT payroll 2027 that four of its columns rest on | ledger_export.py, assets/ledger.js | test_ledger_export: space_2027_spotrac + cbt_payroll_2027 == 247,000,000 on every row. | S | - |
| P2 | M09-15 | ux | unverified | One number, three names: Arb exposure 2027, Ladder sum 2027, Projected 2027 cost | ledger_export.py, franchise_export.py, assets/franchise.js | The franchise leaf label and the ledger column copy come from one source. | S | - |
| P2 | M09-16 | cleanup | unverified | Cost+ and controlled surplus have no registry rows while the other descriptive indexes do | data/model_registry.json, ledger_export.py, MODEL_REGISTRY.md | Every coloured league column names a registry row that exists. | S | - |
| P2 | M09-17 | cleanup | unverified | franchise_board.json ships 1.03 MB to draw one club | franchise_export.py, assets/franchise.js, deploy/publish_paths.txt, deploy/nightly-build.sh | Port the ledger shard tests: index sha, a file naming another club is refused, both deploy consumers ship the directory. | M | GATE |
| P2 | M09-18 | improvement | unverified | The Franchise Index has no trend | franchise_export.py, assets/franchise.js | The series is append-only (immutability check); arrow = rank difference against the dated row. | M | - |
| P2 | M09-19 | wiring | unverified | Franchise roster tables do not link players, and no route opens the club's lineup card | franchise_export.py, assets/franchise.js | A render test: every roster row renders an anchor whose route the target module's hash parser accepts. | S | - |
| P2 | M09-20 | data_source | unverified | HISTORY is on bWAR while the site frame is fWAR | fa_sources.py, franchise_export.py, data/franchise_spine.json | Coverage census of clubs x seasons since first_year; each season's league sum falls within a stated band of the FanGraphs league total. | M | - |
| P2 | M09-21 | improvement | unverified | League tables a finance reader expects, inside the NEVER list | ledger_export.py, assets/ledger.js, assets/ledger.css | League values equal the per-club values, and no column sums contract, arb and pre-arb. | M | - |
| P2 | M09-22 | cleanup | unverified | suite.json predates both modules (129 of 455 test files missing) | suite.json | set(glob('test_*.py')) is a subset of suite.json files. | S | - |
| P3 | M09-23 | ux | unverified | 4 px horizontal overflow on the Ledger Method tab at 390 | assets/ledger.css | Add #section=method to the Playwright 390 sweep (T7). | S | - |
| P3 | M09-24 | cleanup | unverified | The design specs behind both NEVER lists exist only in a session scratchpad | docs/ | Every 'D1 L' or 'D5-D' reference in ledger_export.py and franchise_export.py resolves to a heading in the copied spec. | S | - |
| P3 | M09-25 | ux | unverified | Rank-based letters split printed ties; the HISTORY dark HoF leaf needs a ruling | franchise_export.py, assets/franchise.js | No two clubs share a printed score with different letters. | S | GATE |

**Owner questions raised by this lane (defaults in bold).**
- Should Cost+ be redefined on matched coverage (2027 contract-segment dollars over the projected WAR of those same rows, log ratio, 100+10z)? Options: Redefine on matched coverage; Keep the current definition, print a coverage chip and drop the colour; Retire Cost+ and serve the plain ratios only. **Default: Redefine on matched coverage.** Why: The served index has Spearman -0.867 with payroll and puts TBR at 140 because of the numerator's coverage. /franchise/ uses it as the FIN headline, so the choice is the owner's.
- Until the debuted value engine gets a service clock, should the ledger's Graduates dv columns go dark or stay with a warning chip? Options: Dark with blocked_on; Serve with a 'control clock not started' chip; Leave as is until the upstream fix. **Default: Dark with blocked_on.** Why: The column prints 523.6 $M on relievers with an 83% bust posterior; this is the same field PROSPX debuted cards use.
- Split franchise_board.json into per-club files: tracked or gitignored? Options: Tracked (the ledger precedent, D5-D2); Gitignored and rebuilt nightly. **Default: Tracked (the ledger precedent, D5-D2).** Why: The payload is 1.03 MB against a 1.5 MB budget; the ledger's shards were tracked by owner decision.
- May the /franchise/ HISTORY branch keep a dark 'Hall of Fame plaques' leaf? Options: Keep the dark leaf; Remove it (no HoF anywhere on /franchise/). **Default: Remove it (no HoF anywhere on /franchise/).** Why: The module's NEVER list says no HoF tile, and a dark leaf reads as a promise.

### 4.10 In-Game Management and Hall of Fame (lane M10_mgmt_hof)

**Census summary.** Both pages render cleanly: 29 loads at 1280 and 390 px in both themes, 0 console errors, 0 failed requests, no page overflow. Sampled numbers match the artifacts. The main problems are in the data, not the rendering. (1) P0: the steal family's "realized mWPA" measures the batter's plate appearance after the steal, not the steal. The feed's plays-row wp_before is taken after in-PA events. Across all 13,973 steal rows the per-row Pearson with the model's own realized change is -0.011. Successful steals average -0.0028, and the league sum is -33.48 wins against the model's +3.24. The artifact still says "two estimators of one quantity". The number is served on the Clubs board, club pages, the drill-down (a caught stealing shows +0.0120 in green) and /franchise/. (2) P0: the bunt family selects on outcome. Bunt hits, errors and fielder's choices are not counted as bunts and are counted in the alternative instead. The bases-empty cells are outs by construction (1,280 bunts, -28.7 of the headline -127.2 wins), and the page calls all of it "sacrifice bunts". (3) P1: OAK vs ATH split across two boards, which blanks six Athletics steal blocks. "Best/Worst decision" labels imply skill. The play corpus is not in the pipeline, so 2026 stops on 09-04. /franchise/ re-serves both broken families with stale copy. HoF prints bWAR as "WAR" and never renders payload basis. The 4,440-row ballot re...

**Served state (evidence in the lane's served_state.md).**

- /management/ is ten tabs over one payload plus 240 per club-season shards; hash router #section=&team=&season=&family=&game=&ab= [build_site.py:4787 build_management; assets/management.js SECTION_HASH_RE line 109; data/management_board.json shards.in]
- management_board.json is 297,725 bytes (54,574 gzip), generated 2026-09-24T03:04:58Z by mgmt_export.py [data/management_board.json generated_at, produced_by; gzip measured]
- Shards data/mgmt_decisions/*.json: 240 files, 41 MB, all tracked, schema_version 2 compact codec read by expandShard [du -sh data/mgmt_decisions = 41M; git ls-files count 240; shard key schema_version = 2]
- Decision ledger: 298,701 decisions, nine families, per-family sums only, no cross-family total, plus_metric false [management_board.json decisions.n_all, decisions.no_cross_family_total true, decisions.plus_metric false]
- 2026 ledger is frozen at 2026-09-04 (corpus built 2026-09-06); run_monthly never calls tools/build_pbp_corpus.py; 2026 club rows partial at 140-143 games [decisions.through_by_season['2026']; decisions.corpus_built_at; grep run_monthly.py; clubs.rows season 2026 games]
- Running game: 13,973 priced attempts; 2B success 0.75 vs swing-weighted break-even 0.7529; net DV -0.69 wins; pool 47.5 [running_game.n_attempts_priced; running_game.by_target.2B; headline.net_dv_all_seasons_wins; headline.redistributable_po]
- Gate leg 1 on page: split_half_r 0.1085 inside null band [-0.1501, 0.1272]; legs 2-4 only in management_gate_eval.json [management_board.json gate.split_half_r, gate.null_band; data/management_gate_eval.json gate_2..gate_4]
- Steal row mwpa is the batter's PA after the attempt: per-row Pearson vs model realized_delta -0.011, league sums -33.48 vs +3.24 wins [probe_steal.py over data/mgmt_decisions/*.json families.steal]
- Bunt DV: 6,825 bunts, -127.198 wins, feed control -75.33; outcome-selected event list; no dedicated registry row [sections.sacrifice_bunt.n_bunts_priced, total_decision_value_wins, independent_control.total_wins; mgmt_bunt.py:57-60]
- Win engine: 7-feature logistic, 1,448,965 plays, 8 seasons pooled; Brier 0.157678 vs MLB feed 0.157516 [data/win_expectancy.json features, n_plays_fit, calibration.brier, calibration.feed_brier]
- Club code split: teams rows use OAK 2018-2024, clubs rows use ATH; ATH 2018-2024 club pages print 'No priced steal row' [set difference of teams.rows vs clubs.rows keys = 6 each way; r3.py render of #section=clubs&team=ATH&season=2023]
- Franchise Dugout re-serves clubs realized families (incl. steal, bunt) and carries a stale 'once the next families land' sentence [franchise_board.json clubs[].sections.dugout.realized.families; copy.dugout_sentence]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M10-01 | defect | unverified | Steal family realized mWPA measures the batter's PA after the steal, not the steal | mgmt_decisions.py, mgmt_baseline.py, mgmt_export.py, franchise_export.py, test_mgmt_decisions.py, data/glossary.json, data/management_decisions.json, data/manag | Over every shard, steal rows have sign(mwpa)==sign(realized_delta) on >=0.99 of rows and Spearman >=0.99. League steal mwpa sum equals running_game sum(by_targe | M | - |
| P0 | M10-02 | defect | unverified | Bunt family selects on outcome: bunt hits, errors and fielder's choices are not counted as bunts | mgmt_bunt.py, mgmt_decisions.py, mgmt_export.py, test_mgmt_bunt.py, test_mgmt_decisions.py, data/management_bunt.json, data/management_board.json, data/mgmt_dec | A fixture PA with description 'singles on a bunt ground ball' is a bunt with a positive realized change. No bases-empty cell consists only of outs. The bunt cou | M | - |
| P1 | M10-03 | defect | unverified | OAK vs ATH split: six Athletics club pages lose their steal block and the style board shows two clubs | mgmt_teams.py, data/management_board.json, test_mgmt_style.py | For every season, the set of team codes in teams.rows equals the set in clubs.rows. | S | - |
| P1 | M10-04 | ux | unverified | 'Best decision' / 'Worst decision' columns make a skill claim on a page that forbids one | mgmt_export.py, assets/management.js, test_management_render.py | A render test forbids the strings 'Best decision' and 'Worst decision' in management.js and the payload. | S | - |
| P1 | M10-05 | wiring | unverified | Play corpus not in the pipeline: the 2026 ledger stops on 2026-09-04 and will stay partial after season close | run_monthly.py, tools/build_pbp_corpus.py, assets/management.js | A freshness test fails in-season when the 2026 through-date lags the newest cached game by more than 3 days. | M | - |
| P1 | M10-06 | data_source | unverified | Manager entity from Retrosheet game logs (per-game manager ids), StatsAPI coaches for 2026 | mgmt_managers.py, mgmt_export.py, assets/management.js, test_mgmt_managers.py, DATA_SOURCES.md | The ejection fixture's manager ids agree with the ingested manager on >=0.98 of those games. A club with an interim change yields two manager rows whose family  | M | - |
| P1 | M10-07 | wiring | unverified | /franchise/ Dugout re-serves the broken steal and bunt families with a stale family sentence | franchise_export.py, data/franchise_board.json, test_franchise_export.py | Every family in dugout.realized.families has decisions.families[f].summed true, and the dugout sentence does not contain 'once the next families land'. | S | - |
| P1 | M10-08 | ux | unverified | HoF prints bWAR under the bare label 'WAR' on an fWAR-framed site; the payload basis is never rendered | assets/hof.js, data/glossary.json, hof_export.py, test_hof_export.py | A render test asserts the header contains 'bWAR' and the basis line appears. The glossary lint rejects 'site's eWAR' in the jaws entry. | S | - |
| P1 | M10-09 | data_source | unverified | Add an attributed fWAR twin of the HoF shelf (career fWAR, fWAR7, in-house fJAWS) | hof_data.py, hof_export.py, assets/hof.js, data/glossary.json, DATA_SOURCES.md, test_hof_export.py | Career fWAR for 5 hand-checked players matches FanGraphs to the tenth. The coverage count by era is published. fjaws is not a bake-off arm unless a sensitivity  | M | - |
| P1 | M10-10 | improvement | unverified | Serve the 4,440-row ballot record: vote-share columns, trajectories and a 2027 ballot view | hof_export.py, assets/hof.js, assets/hof.css, test_hof_export.py | last_pct equals the latest ballot row's vote_pct for every player with a ballot row. The 2027 band contains no player who has been elected or dropped. | M | - |
| P1 | M10-11 | data_source | unverified | Lahman HallOfFame.category and awards tables close the plaque blocker and the bake-off's missing inputs | hof_data.py, tools/hof_ballot_ingest.py, hof_export.py, tools/hof_merit.py, docs/HOF_MERIT_GATE.md, test_hof_ledger.py | Joe Torre reads Manager; every player_bbwaa inductee reads Player; plaque_role_unverified drops to the non-player count. | L | GATE |
| P1 | M10-12 | wiring | unverified | 'No franchise spine' is stale: data/franchise_spine.json and franchise_export's team_ID mapping already exist | data/franchise_spine.json, franchise_export.py, hof_export.py, assets/hof.js, docs/HOF_FRANCHISE_ATTRIBUTION.md, test_hof_export.py | Every war_daily team_ID from 1871 maps to an org or an explicit defunct bucket. The sum of a player's franchise WAR equals his career WAR. | M | GATE |
| P2 | M10-13 | defect | unverified | HoF reproduction note blames Negro Leagues and pre-1901 players; the largest gaps are two-way careers | hof_export.py, test_hof_export.py | When any top-five disagreement has pitching WAR > 1, what_it_means contains 'two-way'. | S | - |
| P2 | M10-14 | defect | unverified | Kershaw and 62 others listed as active; AS_OF and ACTIVE_FROM hard-coded | hof_export.py, assets/hof.js, test_hof_export.py | No watch row has last < AS_OF, the bands still partition, and AS_OF equals max(war_daily year). | S | - |
| P2 | M10-15 | defect | unverified | Bake-off footer prints half a sentence | tools/hof_bakeoff.py, hof_export.py, test_hof_bakeoff.py | gate_frozen matches ^Frozen \d{4}-\d{2}-\d{2}\.?$ | S | - |
| P2 | M10-16 | defect | unverified | Two hof_monitor AUCs one card apart with no population sentence | hof_export.py, test_hof_export.py | predictor.why names its n and the phrase 'out-of-fold' and cites the bake-off frame n. | S | - |
| P2 | M10-17 | improvement | unverified | Club Gate tab shows one leg of four; the frozen doc says all are published | mgmt_export.py, assets/management.js, test_mgmt_export.py | The board carries three captured-share values, each with its policy string; the placebo median cell size is present. | S | - |
| P2 | M10-18 | improvement | unverified | Style persistence receipt: 'these repeat because they are policy' is asserted, not measured on the page | mgmt_decisions.py, mgmt_export.py, data/model_registry.json, test_mgmt_style.py | The artifact carries a persistence value and n for each z; the style sentence contains no number that is not in the payload. | S | - |
| P2 | M10-19 | cleanup | unverified | Registry rows for this lane are missing, unfresh or misdescribe the served surface | data/model_registry.json, tools/gen_audit_docs.py, MODEL_REGISTRY.md | Every artifact fetched by management.js or hof.js, or summarised into their boards, has a registry row carrying last_checked. | S | - |
| P2 | M10-20 | ux | unverified | /hof/ is a flat table: no deep links, no player card, no outbound links, 100-row CSV, JAWS off-screen on mobile | assets/hof.js, assets/hof.css, hof_export.py, test_hof_export.py | A render test: /hof/#band=watch&player=troutmi01 opens the Watch band with the card; CSV row count equals the filtered band size. | M | - |
| P2 | M10-21 | ux | unverified | /management/ repeats a 94-word paragraph on four tabs, widens its census table to 1,800 px, caps the drill-down at 500 rows | assets/management.js, assets/management.css, test_management_render.py | The render test counts one realized-sentence block per tab; census table scrollWidth <= 1.2x container at 1280; rows are focusable. | S | - |
| P2 | M10-22 | improvement | unverified | Win engine and RE matrix pool eight seasons; publish per-season receipts and season-centred realized columns | win_expectancy.py, mgmt_export.py, assets/management.js, data/glossary.json, test_win_expectancy.py | Per-season RE matrices re-weight to the pooled matrix within 0.005 runs; season-centred columns sum to zero within each season. | M | GATE |
| P2 | M10-23 | data_source | unverified | Wave B 2026 feeds unbuilt: replay and ABS challenges, mound-visit budgets, lineups | mgmt_feeds_2026.py, mgmt_export.py, assets/management.js, run_monthly.py | The existing test_mgmt_feeds_2026 tests switch to their live branch and pass. Club ABS totals match the external cross-check within 2 percent. | M | - |
| P3 | M10-24 | cleanup | unverified | Stale typed numbers in the management docstring, dead section key, typed stage sigil and typed HoF copy | build_site.py, assets/management.js, assets/hof.js, hof_export.py | A lint test: no digits in build_management's docstring gate paragraph; hof.js has no prose outside labels. | S | - |
| P3 | M10-25 | ux | unverified | HoF labels: 'WAA+' reads as a plus index; Monitor, Standards and WAA sum have no glossary; bake-off arms print as code ids | assets/hof.js, data/glossary.json, hof_export.py | No served HoF header ends in '+' unless its glossary entry is a 100-centred index. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- The frozen IN_GAME_MANAGEMENT_GATE.md says a steal-family null makes fetching the manager entity 'not worth building for this family'. The owner's 2026-09-23 ask wants manager leaderboards on realized decision WPA. Build the descriptive manager ingest (Retrosheet game logs plus StatsAPI 2026) now? Options: Build it now, descriptive only (realized per family, style z, volume sort); Wait until a family with a priced counterfactual clears its own gate; Keep club-season as the agent through the port. **Default: Build it now, descriptive only (realized per family, style z, volume sort).** Why: The gate doc speaks to attributing a steal-family signal; the owner's ask is a descriptive ledger. The executor needs to know which instruction governs before spending M effort on the ingest.
- For the steal family's realized value, which number should the Clubs board, club page and franchise Dugout carry? Options: The model's realized change (DV + ER) only; retire the feed PA figure; The model's realized change, plus the feed figure relabelled 'plate appearance after the attempt' on the drill-down only; A new feed-based estimator from the chain gap around the steal event. **Default: The model's realized change, plus the feed figure relabelled 'plate appearance after the attempt' on the drill-down only.** Why: The current feed number is uncorrelated with the steal (r -0.011). The choice decides whether 'realized' stays feed-only across families, as the glossary currently states.
- Freeze a HoF franchise attribution rule so the Franchises section and the /franchise/ History HoF tile can go live? Options: WAR by franchise summed per stint; primary franchise = max WAR; Plaque logo (needs a hand-kept list); Keep both tiles dark. **Default: WAR by franchise summed per stint; primary franchise = max WAR.** Why: The spine now exists for 1969 on. The blocker text itself asks for a frozen rule with the rejected alternative named.
- Should the Hall of Fame shelf gain an fWAR twin (career fWAR, fWAR7, an in-house fJAWS) beside the reproduced bWAR JAWS? Options: Add the twin as display columns with FanGraphs attribution; Relabel to bWAR only and add nothing; Switch the shelf to fWAR and drop the bWAR reproduction. **Default: Add the twin as display columns with FanGraphs attribution.** Why: The owner locked fWAR as the frame. JAWS is defined on bWAR and the bake-off is frozen on it, so this is a presentation decision the executor should not make alone.

### 4.11 Fantasy: Dynasty, Redraft, DFS (lane M11_fantasy)

**Census summary.** The fantasy module is mostly dark as served, and it will stay that way through the port window. Redraft, DFS and betting props are all empty because the season-end ROS floor dropped every player in data/fantasy.json (n_players 0 at season_fraction 0.976). The monthly export then overwrote the 652-player file with the empty one. The fraction is 1.0 in the off-season, so this lasts until opening day. The nightly refresh is a no-op with an empty corpus, which also freezes Dynasty and Call-up Watch, and those already read the previous eFV cycle (19 of 177 grades differ from /projections/).  The committed copy (09-07) has its own served defects: - The Closer Grid covers 17 of 30 clubs, with split codes, and lists starters as CLOSER. Brayan Bello is shown for BOS, where Chapman has 34 saves. - Player rows carry 34 club codes for 30 clubs. - Every home start prints as '@': 28 of 56 streamer rows and 70 of 132 two-start legs. The card contradicts itself. - The Keeper Calculator compares a prospect-only rank with an overall pick. Placed on overall boards, prospect #10 sits at overall 84 (BA dynasty 500) or 102 (our own surNpv). - Call-up Watch hardcodes the years 2026 and 2027. - The DFS tables keep DK's retired CS penalty and omit FD's quality-start points. - Four DFS glossary slugs do not exist, and there are zero fantasy glossary entries.  On-theme upgrades: - One dynasty board cover...

**Served state (evidence in the lane's served_state.md).**

- /fantasy/ is one page, built by build_site.build_fantasy (build_site.py:4163), with Redraft (default), Dynasty and DFS behind a module bar. The #m=<module>&section=... hash is owned by assets/fantasy-hub.js. /dynasty/, /redraft/ and /dfs/ are hash-preserving r [build_site.py:4163-4276; assets/fantasy-hub.js SECTION_HOME table]
- Clients are lazy-injected from data-src stamps: redraft.js (71,635 B), dynasty.js (51,902 B) and dfs.js (98,231 B), plus the shared fantasy-card.js. The frozen assets/fantasy.js (55,709 B) is loaded by no page and exists only as a parity fixture. [build_site.py:100-149; ls -la assets]
- The working data/fantasy.json is 115,219 B with n_players 0, players [], season_fraction 0.976 and generated_at 2026-09-23T17:46:10Z. ROS, buy/sell and streamer sections are empty, closer_depth is {}, two_start has 30 rows (all total_fgp 0.0), dynasty has 300  [data/fantasy.json keys n_players, players, sections.*; git status]
- The HEAD data/fantasy.json is 413,767 B, generated 2026-09-07 at fraction 0.891. It holds 652 players (435 hitters, 189 SP, 28 RP) and sections ros_hitter 350, ros_sp 189, ros_rp 28, closer_depth 17 keys, daily_streamers 56 and two_start 66. There are 21 commi [git show HEAD:prospect-tracker/data/fantasy.json; git cat-file -s; git log -- data/fantasy.json]
- The working data/dfs.json is 3,859 B: slate 2026-09-23, 0 games, empty_reason_kind no_corpus. The HEAD copy is 194,258 B: slate 2026-09-07, 11 games, 260 players, with a Savant park factor on 10 of 11 games. [data/dfs.json empty_reason_kind; HEAD dfs.json integrity.park_sources]
- ROS rows are dropped below 20 ROS PA or 8 ROS IP. On the HEAD corpus, every pitcher is gone past fraction 0.953 and every hitter past 0.969, and the off-season fraction is 1.0. [fantasy_export.py:459, :468; HEAD max implied PA 653.2, IP 171.6]
- refresh_live (daily step 9d) returns early when players is empty, so the nightly roster, eligibility, schedule and prospect-section rebuilds all stop with it. [fantasy_export.py:1510-1514]
- The downstream betting props are empty: data/betting.json props_fair_lines.pitchers has 0 rows and .hitters has 0. [data/betting.json props_fair_lines]
- The monthly step 6b6 builds fantasy before the eFV regen. On 2026-09-23 the mtimes were fantasy.json 13:46, xfv.json 14:33 and mlb_projections.json 15:58, and 19 of 177 dynasty eFVs differ from /projections/. [run_monthly.py:6027; file mtimes; fantasy.json vs mlb_projections.json prospects]
- The Dynasty board holds prospects only: 300 rows, none of them an MLB vet. ETA distribution is 2026 x144, 2027 x57, 2028 x64, 2029 x27, 2030 x2 and 2031 x6. /projections/ shows ETA 2027 on 76 of these rows. [data/fantasy.json sections.dynasty; data/mlb_projections.json prospects[].eta]
- Registry rows: fantasy_ros_rankings is provisional with no artifact; dfs_slate_pricing, fantasy_dynasty_blend, fantasy_roto_valuation, fantasy_buy_sell, fantasy_closer_depth and versa_positions are unvalidated (the closer gate was RED on 2026-08-16); fantasy_s [data/model_registry.json models[]; data/fantasy_startscore_eval.json results_2026.B0.holdout_mean_date_rho]
- The pre-registered fantasy_startscore second look (arms B and C, after 2026-09-15) is due. B0 has to be re-baselined on matchup_mult first. [model_registry fantasy_startscore notes]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M11-01 | defect | CONFIRMED | The ROS corpus empties at season end and stays empty all off-season (Redraft, DFS and props go dark) | fantasy_export.py, assets/redraft.js, dfs_export.py, betting_export.py | test_fantasy_export.py: at fractions 0.976 and 1.0, build_players returns >0 rows and the right mode; export() refuses an empty overwrite of a populated file. | M | conflict: none. The floor change and the next_season mode reuse the shipped fa_projection rate engine, which fantasy already calls at target cur+1. It does not touch the  |
| P0 | M11-03 | defect | PARTLY | The Closer Grid covers 17 of 30 clubs, splits club codes, and lists starters as CLOSER (narrowed: Coverage: the grid covers 14 distinct clubs, not 17. It misses 16 clubs, not 13, because the 17 keys include three split pairs (CHW/CWS, SD/SDP, WSH/WSN). Everything else in the behaviour reproduces: - 16 of 28 RP rows h) | fantasy_export.py, assets/redraft.js, assets/fantasy-card.js | test_fantasy_export.py: 30 canonical keys, every id is on the reliever board, and an empty ROS pool still yields 30 clubs. | S | conflict: None if the fix only changes which arms are in the grid and keeps role-order copy with no likelihood. The closer save-share gate is RED (docs/fantasy-closer-gat |
| P1 | M11-02 | defect | PARTLY | DFS reports the season end as a pipeline outage because the season_over branch is unreachable (narrowed: The defect is a misclassification. When fantasy.json exists but holds zero players, /dfs/ labels it "corpus missing / not built yet / Pipeline outage" (styled is-broken, all four tabs). That empty corpus is structural. T) | dfs_export.py, assets/dfs.js | test_dfs_served_counts.py: an empty-players corpus at fraction 1.0 yields season_over; a missing file yields no_corpus. | S | conflict: None of the proposed changes touches a do-not-reopen item, a clock, or a locked decision. The ROS floors are display thresholds, not a closed model item. One in |
| P1 | M11-04 | defect | PARTLY | Player rows carry 34 club codes for 30 clubs (narrowed: This is a real defect, and its served impact is wider than the lane stated. _enrich (fantasy_export.py:725) copies the leaderboards' MLB-style codes. The mlb_player_detail fallback (:728) is itself mixed at 38 codes. Of ) | fantasy_export.py | Every served players[].team is one of the 30 canonical codes. | S | conflict: None. The change is a code-canonicalization fix. It does not touch the closer save-share model, whose gate went RED on 2026-08-16. The Closer Grid stays a role- |
| P1 | M11-05 | defect | CONFIRMED | Home starts print as '@' on streamers, two-start, GFX and the card, and the card contradicts itself | fantasy_export.py, assets/redraft.js, assets/fantasy-card.js | test_fantasy_two_start fixture with a home leg asserts 'vs'; a JS-engine render assertion in test_fantasy_split. | S | conflict: none. This is a display label. The streamer and two-start scoring (_start_score) has no home term and is unchanged. The fix touches no betting column family, cl |
| P1 | M11-06 | defect | CONFIRMED | The Keeper Calculator compares a prospect-only rank with an overall draft pick | assets/dynasty.js, build_site.py, fantasy_export.py | dynasty.js engine test reads the combined rank when present; test_fantasy_claims pins the blurb. | S | conflict: None for the interim fix (relabel the verdict, correct the blurb, add a basis toggle). The M11-07 combined-rank route sits next to DNR item 'dynasty weights are |
| P1 | M11-07 | wiring | PARTLY | Build one dynasty board for MLB players and prospects from the projection engine's multi-year path (narrowed: Build the narrow wiring, not a second WAR board and not a fantasy-points value. (a) proj_export writes one integer rankAll on every vets[] and prospects[] row. It is the rank on the /projections/ default sort: season-ali) | fantasy_export.py, assets/dynasty.js, data/glossary.json, data/model_registry.json | Every prospect row appears in dynasty_all with the same eFV; ranks are a permutation; value is monotone in discounted WAR at equal age. | L | conflict: No pre-registered gate. rankAll is a display order over served numbers and makes no fit or accuracy claim. Conflict with the proposal as written: making the pro |
| P1 | M11-08 | improvement | PARTLY | Receipts: measure ROS and DFS accuracy forward from vintages and archives that already exist (narrowed: Build it in four pieces, ordered by what can run now. Each piece needs a pre-registration written before its first run.  1. TWO-START LEDGER READOUT (S, now). - Serve two_start_ledger_summary on the Two-Start SP tab of t) | tools/fantasy_ros_eval.py, tools/dfs_pricing_eval.py, data/model_registry.json, assets/redraft.js, assets/dfs.js, fantasy_export.py | The registry rows carry eval_artifact and freshness; claims tests pin that the copy reads the artifact rather than a hardcoded number. | M | GATE conflict: No do-not-reopen item is touched. This adds measurement and does not change a model in the closed eFV or projection frontiers. Items 1, 3 and 4 each need a pre- |
| P1 | M11-09 | defect | PARTLY | Dynasty and Call-up Watch go stale: the monthly build reads the previous eFV, and the nightly fix-up dies with an empty corpus (narrowed: The served board lags the eFV regen, but the reader sees less contradiction than the finding says, and the fix needs a third change.  What the reader sees today: - The fantasy.json that /fantasy/ serves was built at 13:4) | fantasy_export.py, run_monthly.py | refresh_live over a payload with players [] rebuilds sections.dynasty from a fixture xfv; a run_monthly order assertion. | S | conflict: none. The fix leaves the dynasty_blend weights alone (those are the do-not-reopen conventions), does not reorder proj_export against export_trade_values, and to |
| P2 | M11-10 | defect | PARTLY | Call-up Watch hardcodes 2026/2027 and does not roll ETAs at season end (narrowed: The 2026/2027 hardcode is real and no test pins it. It does not break at the first rollover, though, because eta.py rolls ETAs on its own. Through Oct 31 2026 the 41 ETA-2026 rows stay. They come from the ETA model, and ) | fantasy_export.py | _callup_watch with season 2027 keeps 2027 and 2028; ETA 2026 at fraction >= 0.97 serves 2027. | S | conflict: None for the fantasy_export window change. Note: the single-seam fix in eta.py touches a registered model that has its own eval (data/eta_eval.json) and a histo |
| P2 | M11-11 | improvement | PARTLY | League settings: custom points weights and roto categories (narrowed: Build a narrower version, in this order.  (a) CUSTOM POINTS, client side in redraft.js. - Add an in-memory catalog row, id "custom", kind points. - Weights cover only the keys each role carries, plus derived tb (single+2) | assets/redraft.js, assets/fantasy-card.js, fantasy_scoring.py, test_fantasy_split.py | A custom table equal to FGP reproduces FGP cell for cell in the JS engine. | M | conflict: None. This re-weights the served projection deterministically: no fitted model changes, no served accuracy claim moves, and no DO-NOT-REOPEN item is touched. Dy |
| P2 | M11-12 | defect | unverified | DFS scoring tables disagree with the sites' current rules (DK caught stealing, FD quality start) | dfs_export.py, test_dfs_anchors.py | Pin the tables and the rules_checked stamp. | S | - |
| P2 | M11-13 | defect | unverified | Four DFS glossary links point at nothing, and no fantasy term exists | data/glossary.json, test_fantasy_claims.py | A slug-existence test over redraft.js, dynasty.js, dfs.js and fantasy-card.js. | S | - |
| P2 | M11-14 | defect | unverified | The corpus role 'H' is shown as a position on the card and in Buy/Sell | assets/fantasy-card.js, assets/redraft.js | Card render test asserts no bare 'H'. | S | - |
| P2 | M11-15 | defect | unverified | Two-Start: 'this scoring week' is a rolling 7 days, and unpriced legs total 0.0 | fantasy_schedule.py, fantasy_export.py, assets/redraft.js, test_fantasy_two_start.py | A fixture on a Wednesday yields the next Mon-Sun window; an unpriced leg yields total null. | S | - |
| P2 | M11-16 | improvement | unverified | Roto value has no replacement level or roster-size pool | assets/redraft.js, assets/fantasy.js, test_fantasy_split.py, data/model_registry.json | JS-engine test: the value of the replacement-level player equals 0 at each position. | M | GATE |
| P2 | M11-17 | data_source | unverified | ADP and Ottoneu average salaries as market context | fantasy_export.py, assets/redraft.js, assets/dynasty.js, DATA_SOURCES.md | The ingest reports its mlbam match rate; the join is covered by a fixture. | M | GATE |
| P2 | M11-18 | improvement | unverified | Run the due, pre-registered streamer-score second look | tools/fantasy_startscore_lab.py, data/fantasy_startscore_eval.json, data/model_registry.json | The eval artifact carries the second-look block and its verdict. | S | GATE |
| P2 | M11-19 | wiring | unverified | No module links into a player's fantasy view | build_site.py, prospx/index.html | Link targets resolve in fantasy-hub's route table. | S | - |
| P2 | M11-20 | defect | unverified | Fantasy ROS talent basis differs from /projections/ for the same player | fantasy_export.py | A basis stamp on the payload is asserted equal to the /projections/ stamp, or disclosed. | S | GATE |
| P3 | M11-21 | ux | unverified | The Dynasty board leads with real-life salary surplus instead of production | fantasy_export.py, assets/dynasty.js | Band fields present and ordered P10 <= P90. | S | - |
| P3 | M11-22 | cleanup | unverified | Stale numbers in comments and registry prose | build_site.py, prospx/index.html, data/model_registry.json | None beyond the registry freshness checks. | S | - |
| P3 | M11-23 | cleanup | unverified | The frozen assets/fantasy.js ships as a public asset | build_site.py, test_fantasy_split.py, test_fantasy_claims.py | Tests load the fixture from its new path. | S | - |
| P3 | M11-24 | improvement | unverified | Two eligibility rules on one site, and no league threshold choice | fantasy_export.py, assets/redraft.js, assets/dfs.js | A threshold of 20 removes a 6-game position in a fixture. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Off-season behaviour of Redraft: should the ROS tabs switch to next-season full-season projections (draft prep), or show a closed state until opening day? Options: Switch to next-season projections (mode next_season); Closed state with last season's final ranks; Hide Redraft entirely until opening day. **Default: Switch to next-season projections (mode next_season).** Why: M11-01 needs a target behaviour for the six-month off-season that covers the port window.
- Should fantasy ROS lines adopt the de-aged talent basis that /projections/ ships for its rental leg? Options: Adopt de_aged site-wide; Keep the aged first-season basis and disclose it; Decide after the ROS eval (M11-08) runs. **Default: Decide after the ROS eval (M11-08) runs.** Why: The 2026-08-05 DECISION is scoped to surplus, so fantasy is outside it; the two modules differ by up to about 20% by age.
- What drives the combined MLB plus prospect dynasty value? Options: Discounted projected fantasy points; Discounted 5-year WAR (warTotal path); Salary surplus NPV (surNpv). **Default: Discounted 5-year WAR (warTotal path).** Why: M11-06 and M11-07 need one overall scale. Salary surplus rewards cheap control, which fantasy does not.
- Which market sources may the fantasy module ingest for ADP and prices? Options: NFBC ADP; Fantrax ADP; FantasyPros consensus ADP; Ottoneu average salaries; None. **Default: None.** Why: M11-17 needs a terms and access decision. FanGraphs HTML blocks Python on this box, and card-price scraping is a banned class.

### 4.12 Sports Betting and Diamond Pass (lane M12_betting_diamond)

**Census summary.** Read-only census of /betting/ and /diamond/ at HEAD c78f1e7c, with both pages rendered on port 8712. The server was terminated afterwards. Neither page logged a console error or a failed request, and neither scrolls sideways at 1366 or 390 px.  The pricer's arithmetic checks out. All 14 served moneyline and total probabilities reproduce from the served lambdas to 4 decimal places. The de-vig, EV and Kelly on a sampled card also re-derive exactly.  The problems are in what the page shows and how it is run:  - **Diamond scoreboard contradicts itself.** The /diamond/ tiles show eFV ahead by 0.044 on 3,272 players. The sentence under them says -0.007 on 812 players and calls it a tie. The tile gap is larger than the 0.030 floor printed on the same card. - **Green badges contradict the caveat.** Team Bets shows a green BEST VALUE badge on 13 of 14 games. 11 of them are Overs whose own row caveat says "Known model shape, not value". - **The Pick of the Day slot rewards the known bias.** Its rule picks the highest model probability, which the disclosed Over lean maximises. Today's pick is Over 6.5 at 83.4% against a 52.4% market price, with a full Kelly of 63.7%. - **Player Props is empty.** fantasy.json now has 0 players because its rest-of-season volume floors fail at 97.6% of the season. The tab says "No slate is loaded" while 14 games are loaded. - **Five places still say picks ar...

**Served state (evidence in the lane's served_state.md).**

- /betting/ payload is one slate old at read time: generated 2026-09-23T18:57Z, slate 2026-09-23, 14 games; on 2026-09-24 17:47Z the page shows all 14 (every one already started) with an 'odds feed live' chip [data/betting.json generated_at, slate_date, n_games; render_report.json desktop:potd; assets/betting.js has no Date.now(]
- The served pricer (betting_runs_v2, fitted on season-to-date rows) is not the pricer the vintage backtest grades [betting.json model.coefficients b1 0.2411 b2 -0.3317 b3 3.9820 r2 0.0468 n_rows 4714 vs betting_model_eval.json vintage.]
- All 14 served totals and moneylines reproduce from lam_home/lam_away: Poisson total with the push removed; Skellam regulation plus 0.49 of the tie mass [recomputation over betting.json team_bets[*].model; league_context.extra_inning_home_rate 0.4902]
- Serve flags: SERVE_RUN_DISPERSION, SERVE_PROB_CALIBRATION and the three SERVE_TOTAL_* flags are False; SERVE_RUNLINE_TIE_SPLIT and SERVE_ATH_PARK are True; SLOT_MARKET_POLICY is 'any'; SERVE_CLV is False; SERVE_PRICER does not exist [betting_model.py:316, 403, 438, 600, 892, 920, 940, 1401; betting_export.py:1233]
- Vintage backtest: 705 graded of 1,010 gradable (2026-08-01 to 09-22); Brier 0.24269 vs home 0.24787, t 2.919; Elo 0.24228 on the same 705 games; market open 0.22613 on 390 games (model 0.24314 on those games); close tier n 0 [data/betting_model_eval.json vintage.*, benchmarks.tiers.*]
- Leaderboard snapshots: 45 on disk (35 live, 10 backfilled); 15 of 51 nights missing since 2026-08-04, including 09-11; 1,347 games skipped for lack of a snapshot [betting_model_eval.json vintage_coverage.missing_dates, vintage.n_skipped_no_vintage; ls .cache/leaderboard_vintages]
- Odds cache: 35 snapshots for 35 slates, all 'open'; no close ever captured and the close job never ran [ls .cache/odds; betting.json status.feed_health.ever_captured_close false, close_job_ever_ran false]
- September odds-API credits: the provider meter shows 48 used and 452 remaining; the local ledger shows 39 (all open captures) [data/betting_status.json latest_credits; .cache/betting/credits-2026-09.json total]
- The only scheduled task on the dev box is EephusLineupCapture (registered 2026-09-24). Weather forecast capture is armed but runs only with the manual nightly (8 captures since 09-13) [schtasks query; betting_weather.py:106 FORECAST_CAPTURE_ENABLED True; ls .cache/weather_forecasts]
- Pick of the Day is Over 6.5 -118 (lowvig) in MIA at CHC: model 0.83361, market fair 0.52354, edge 0.31007, full Kelly 0.63728, locked. The long-price slot is empty. 20 sides clear the 0.06 floor (11 totals, 5 runlines, 4 moneylines) [betting.json pick_of_the_day, slot_lock, pick_meta.n_floor_clearing_sides]
- The slate-level Over lean check fires: mean_lean 0.14452, t 5.473, 13 of 14 positive-edge totals are Overs, mean gap 1.237 runs [betting.json total_level_check]
- The total market's ledger leg reads 'worse than a coin' (Brier 0.262622, t 1.7651 on 233 games) yet its status is open, reopened 2026-09-23T18:57, the same build that locked the Pick of the Day [betting.json market_publishability.markets.total.ledger_leg; .cache/betting/market_gate_state.json]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | M12-01 | defect | PARTLY | Diamond receipts: tiles show a +0.044 eFV lead, the sentence under them says -0.007 and calls it a tie (narrowed: Accurate part: the headline slot and 11 of the 13 served badges sit on total Overs. The slate lean fires: total_level_check has mean_lean 0.14452, t 5.473, and 13 of 14 positive-edge sides are Overs. Every one of those r) | assets/diamond.js | test_diamond_scaffold.py: load the artifact and assert the tile pair and the verdict sentence use the same n and basis. | S | conflict: Changing the 7b hysteresis windows (full-window close vs trailing-200 reopen, dwell 3) so a ledger_gated flip holds the total out is blocked by do-not-reopen it |
| P0 | M12-03 | defect | CONFIRMED | Player Props tab is empty and says 'No slate is loaded' over a loaded 14-game slate | betting_export.py, fantasy_export.py, assets/betting.js | Fixture at season_fraction 0.98 asserts props_fair_lines is non-empty for a named probable; client copy names the missing source. | M | conflict: none. The fix carries out what HEADTOHEAD_FRAME_GATE.md already decided: the vintage-matched frame is the published verdict, and the all_vintages and predebut f |
| P0 | M12-04 | defect | CONFIRMED | Five surfaces still promise 'graded against the closing line'; CLV is retired and no close was ever captured | build_site.py, assets/diamond.js, assets/betting.js, betting_export.py | test_betting_policy_copy.py: with SERVE_CLV False the built shell and diamond page contain no closing-line grading claim and the payload has no clv_url. | S | conflict: none. The fix leaves MIN_BETS_FOR_SWEEP (100), the gate 3 constants and the market-blend boundary untouched. It relates no dark column family (5c through 5l) to |
| P1 | M12-02 | defect | PARTLY | Green BEST VALUE badges sit on 11 Over rows whose own caveat says 'not value' (narrowed: Four served surfaces promise closing-line grading, and serve_clv is false. 1. The /betting/ masthead (build_site.py:4453-4455), which contradicts the page's own Record tab (betting.js:2432-2435, 'Graded on realized resul) | betting_export.py, assets/betting.js | test_betting_slot_market_policy.py: a firing total_level_check fixture yields zero badges on totals. | S | GATE conflict: None. The fix makes the copy follow the locked owner decisions: CLV retired 2026-09-07 (SERVE_CLV False) and the close job skipped 2026-09-17. It reopens no do- |
| P1 | M12-05 | defect | CONFIRMED | 5e handedness and 5i-B park-by-hand looks are dated two days early; the first qualifying snapshot is 2026-09-13 | docs/diamond-betting.md, docs/master-plan-2026-09-24-final-pass.md | Unit test: a snapshot list missing 09-11 yields earliest look 2026-10-11 for both families. | S | GATE conflict: None. The change is display-only. It does not move any probability, edge, slot, badge or record row. It stays within the 2026-09-05 any-market policy (docs/diam |
| P1 | M12-06 | defect | PARTLY | A board built yesterday is served as live today (narrowed: Four copy defects render today: the banner chip on 8 of 8 tabs, the POTD trust sentence that blames the wrong gate, Clock A's "Short by -105 games" beside "705 of 600", and "grows toward 600". Most of the fix belongs in ) | assets/betting.js | Playwright check in the px_sweep set with a clock override; a string sentinel in test_betting_copy_sentinel.py. | S | conflict: None. The fix is copy only. It does not move the 600 vintage floor, the t >= 1.645 bar, the 100-row sub-ledger requirement or the 6.0% policy floor, and it does |
| P1 | M12-09 | defect | PARTLY | The Validation headline leads with the weakest baseline and grades a pricer that does not serve (narrowed: Build a narrower version with the same projection basis and no season-to-date fallback.  (a) Root fix, shared with M11 because one floor also empties dfs.json and stops refresh_live (fantasy_export.py:1510-1514): - fanta) | assets/betting.js, betting_export.py | test_betting_policy_copy.py: the headline names the best measured tier and the served-vs-graded line is present. | S | conflict: No gate is needed, and none of the 18 DO-NOT-REOPEN items is touched. Props are labelled model-only with no calibration or accuracy claim ("No props row has set |
| P1 | M12-11 | improvement | unverified | Re-run the market-blend lab: its 150-game clock is met and its result file is six weeks old | data/betting_market_blend_eval.json, data/model_registry.json | Existing lab tests plus a registry freshness assertion. | S | - |
| P1 | M12-12 | cleanup | unverified | The free nightly leaderboard snapshot misses 29% of nights because nothing schedules it | deploy/betting-crontab.example | The existing vintage_capture_gap sentinel reads green; a parameter test for the new .ps1 as for the close task. | S | GATE |
| P1 | M12-13 | improvement | CONFIRMED | The public record has never started; The Record tab and the Diamond card are empty | betting_export.py, assets/betting.js, build_site.py | test_betting_publish_hygiene.py | S | GATE conflict: None. The change discloses arithmetic that already serves. No coefficient, flag, served price or accuracy claim moves, so no pre-registered gate or owner decisi |
| P1 | M12-14 | defect | PARTLY | /diamond/ will say 'No pick published yet' the day the first record row posts (narrowed: Build 7e-D exactly as its "to be built" list says. The finding's interim "one Validation line" is not the registered interim. The registered one is landing `SERVE_PRICER = "context"` with its tripwire, which docs/diamond) | assets/diamond.js | A harness feeding a two-row array and asserting the 'posted, none settled' card. | S | conflict: No ban conflict: 7e-D is pre-registered (docs/diamond-betting.md:7902). Its window is on or after 2026-09-28, after the 7h re-read, and by 2026-10-31.  Hard rul |
| P1 | M12-15 | ux | unverified | 22 glossary links on /betting/ define nothing | data/glossary.json | New test_betting_glossary_slugs.py: every gl() slug in betting.js and the shell resolves. | M | - |
| P2 | M12-07 | defect | PARTLY | One tag, three counts on one page: potd_band reads 24, 12 and 25 (narrowed: Severity drops from P1 to P2. This is prominence and framing, not a wrong or contradictory number. The headline truthfully reports the pre-registered publish gate against the home constant. The one confirmed defect is th) | run_monthly.py, betting_export.py, assets/betting.js | test_betting_subledgers.py: after one nightly fixture, payload tag_record equals the sub-ledger by_tag counts. | S | conflict: The proposed headline text breaks the pre-registered benchmark-ladder claim rule. docs/diamond-betting.md section 6 (lines 6916 and 6922-6927, pre-registered 20 |
| P2 | M12-08 | improvement | PARTLY | The Pick of the Day rule is maximised by the disclosed Over bias, and its label describes a different rule (narrowed: Build it as the execution of N10's first leg, not as a new item. Run it after the 2026-09-28 sequence (7i, then the 7h re-read, then 5c-A) and the 7e-D replay, as the 09-11 plan's W4 already orders.  1. Before any number) | betting_export.py, betting_model.py, assets/betting.js | test_betting_slot_market_policy.py: a firing-lean fixture yields a non-total Pick of the Day. | S | GATE conflict: No ban conflict. DNR item 12's own reopen condition (150+ distinct ledger games) is met: the 09-11 plan recorded 179, and the ledger now holds 238 canonical mon |
| P2 | M12-10 | wiring | PARTLY | SERVE_PRICER and its tripwire are missing; the 7e-D run is void unless they land by 2026-10-31 (narrowed: Where it is served: - the pick-of-the-day and longshot slot caveat, only when that slot is a runline or total. Today that is 1 row in betting.json and 1 in betting_preview.json. - model.known_limits[0], one click away in) | betting_model.py, betting_export.py, betting_shadow.py, tools/betting_calibration.py | Byte-identical payload with SERVE_PRICER 'context'; tripwire test flips gate 2 to 'not graded' on a mismatch. | M | GATE conflict: None for a wording change. It moves no price and leaves SERVE_RUN_DISPERSION False (do-not-reopen) as it is. Two constraints on the new text: - It must not type |
| P2 | M12-16 | improvement | unverified | Add a 'why this price' breakdown per game that sums exactly to the expected runs | betting_model.py, betting_export.py, assets/betting.js | Sum identity on every served game; payload priced fields byte-identical. | M | - |
| P2 | M12-17 | improvement | unverified | Add a results calendar and a model-vs-open ledger from data already on disk | betting_shadow.py, assets/betting.js | The daily net units sum to the by_market net units. | M | - |
| P2 | M12-18 | data_source | unverified | 452 of 500 September credits are unused; close and futures pulls fit the budget | betting_credits.py | Credit ledger equals the provider meter after one run. | S | GATE |
| P2 | M12-19 | improvement | unverified | The extra-inning split is a flat 0.49 whatever the matchup | betting_model.py, docs/diamond-betting.md | Gate harness on held-out games. | M | GATE |
| P2 | M12-20 | wiring | unverified | The futures ledger has no scorer, and division and playoff odds resolve on 2026-09-27 | data/model_registry.json | Synthetic-season scorer test. | M | GATE |
| P2 | M12-21 | ux | unverified | Full Kelly up to 63.7% is printed on rows the page calls 'not value' | assets/betting.js | Copy sentinel test. | S | - |
| P2 | M12-22 | ux | unverified | Copy reads '705 of the 600 games needed' and 'Short by -105 games' | betting_export.py, assets/betting.js | test_betting_policy_copy.py | S | - |
| P2 | M12-23 | wiring | unverified | The Dugout block beside today's price reads a management corpus 20 days old | run_monthly.py, assets/betting.js | Freshness assertion on dugout_context.through. | S | - |
| P3 | M12-24 | cleanup | unverified | Stale disclosure field in the eval file and stale registry prose | betting_model.py, data/model_registry.json | A registry-note freshness lint if one exists. | S | - |
| P3 | M12-25 | ux | unverified | The share card exports fair totals with no market line or caveat | assets/betting.js | GFX config snapshot test. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Should totals be barred from the Model Watch slots and the green badges while the slate-level Over lean check fires? Options: Yes, a structural rule keyed on total_level_check.fires; Flip SLOT_MARKET_POLICY to ledger_gated (O15) only; note it would not have barred today's total; Keep 'any' and only relabel the badge. **Default: Yes, a structural rule keyed on total_level_check.fires.** Why: Today's headline slot and 11 green badges sit on the known Over bias. ledger_gated would not have stopped it: the total reopened on its trailing window in the same build.
- Arm the public record now (publish_armed), with results-only grading and no CLV? Options: Arm now for the last regular-season slates and the postseason; Keep closed until 2027 and relabel The Record tab; Keep closed and surface the paper ledger calendar as the interim record. **Default: Keep closed and surface the paper ledger calendar as the interim record.** Why: The Record tab and the Diamond card have been empty since launch; arming is irreversible by design.
- Register free Windows scheduled tasks for the leaderboard snapshot and weather capture on the dev box now? Options: Yes, both, mirroring EephusLineupCapture; Snapshot only; No, wait for the box cron (O16). **Default: Yes, both, mirroring EephusLineupCapture.** Why: 29% of nights are missing and cannot be rebuilt later; the 09-11 gap already moved the 5e look date.
- Spend part of the unused credit budget (452 of 500 left in September) on a close capture and weekly futures outrights for the postseason? Options: Close capture only; Close plus futures outrights; Neither (keep the 2026-09-17 skip). **Default: Neither (keep the 2026-09-17 skip).** Why: CLV, the benchmark's close tier, a line-movement view and any futures edge all need these captures; the default respects the owner's recorded skip.

### 4.13 Site shell, navigation, glossary, models hub (lane M13_shell_nav_glossary)

**Census summary.** The shell is mechanically clean. I rendered 15 routes at 1280 and 390 wide in light and dark themes (60 renders): 0 console errors, 0 failed requests, 0 horizontal overflow. All 29 top bars match NAV_ITEMS (20 leaves; Franchise first, Club Ledger after Arbitration, per owner decision). Every page, hand pages included, carries the current site.css stamp (v=3c75b078), and the crawl found no dead internal page links. The gaps are served-number honesty, glossary coverage and cohesion: (1) Home Top Movers serves 5 of 5 rows that are eFV-floor transitions labelled 'FV', and /news/ carries at least 34 of 79 FV rows of the same kind. efv_alerts.py already fixed this; the home page never did. (2) 24 glossary ids referenced by betting.js, dfs.js and the /betting/ masthead do not exist. BETTING_ENTRIES was written in build_glossary_data.py on 2026-08-07 and never reached data/glossary.json. (3) data/fantasy.json and data/dfs.json in the working tree have 0 players (HEAD has 652), so the Fantasy home card silently drops. Do not commit these files. (4) The home module strip has no card for Franchise, Club Ledger, Arbitration, Management, Hall of Fame or Betting. (5) Ctrl+K cannot find a club, a module or a betting term. (6) The player hub strip covers 3 modules. The /player/ router is orphaned and has a dead branch. (7) Franchise already carries 26 deep links per club, but no module links b...

**Served state (evidence in the lane's served_state.md).**

- Generated shell routes: / (page_home: no top bar, sidebar nav), /news/, /history/, /articles/ (1 article page), /forums/, /models/, /glossary/, /team/, /sources/, /report/, /404.html, /teams/ (redirects to /projections/#view=teams), robots.txt, sitemap.xml. /p [build_site.py:6642-6690 main(); ls player/index.html]
- NAV_ITEMS has 20 leaves in two groups. MLB Modules order: Franchise, Free Agency, Projections, MLB Stats, Alchemy Lab, Trade Machine, Arbitration, Club Ledger, In-Game Management, Hall of Fame. This matches the owner decisions. All 29 pages with a top bar, the [build_site.py:334-380; probe_nav.py output; rendered dropdown on /ledger/ at 1280]
- Every page links site.css?v=3c75b078, which equals md5(assets/site.css)[:8]. The brief's claim that hand pages load site.css unversioned is stale. [probe_nav.py css column; build_site._asset_ver; restamp_hand_authored_pages build_site.py:6613]
- 60 renders (15 routes x 1280/390 x light/dark) produced 0 console errors, 0 failed requests and 0 horizontal overflow. The 7 glossary views and the shell pages show no NaN/undefined/[object leaks. [scratchpad/finalpass/M13_shell_nav_glossary/render_results.json, views_results.json]
- The dead-link crawl over all served HTML found 0 missing internal page targets, apart from template strings inside prospx JS. JS literals with no target on disk: /auth/ and /auth/reset/ (eephus-account.js:152-174, account layer dormant), and /data/betting_clv. [probe_links.py]
- Footer-only routes, absent from NAV: /news/, /history/, /parks/, /models/, /sources/, /report/. The CollegeSavant pages have no footer. [build_site.py:466-512 _footer; probe_nav.py footer=False for collegesavant/index.html and pitcher_index.html]
- Uncompressed page transfer: / 1.90 MB (39 requests), /news/ 2.53 MB, /glossary/ 1.47 MB, /models/ 1.40 MB, /franchise/ 2.31 MB. Every page eagerly fetches site.css (323,965 B) and data/glossary.json (455,541 B). [interact_results.json sizes]
- site.css is 323,965 B, of which 126,783 B are comments. gzip -9: 83,544 B as shipped, 29,785 B with comments stripped. The deploy strips comments only from prospx/index.html. [inline python gzip probe; deploy/nightly-build.sh:257-262]
- data/glossary.json is version 2026-09-24 with 355 entries: formula 184, example 149, methodology 323. The Arkmetrics group has 132 entries (99 with formula, 83 with example). The groups map lacks the categories 'industry' and 'method'. [data/glossary.json entries/groups; inline probe]
- Served code references 156 distinct glossary slugs. 24 resolve to no entry: 20 in betting.js (clv and devig also in the /betting/ masthead) and 4 in dfs.js. [probe_glslugs.py; build_site.py:4453-4455; build_glossary_data.py:222 BETTING_ENTRIES never merged]
- The glossary Models view groups data/model_registry.json (878,888 B) with _modelFamily into PROSPX/eFV 102, Internal 96, Other 60, MLB Stats 20, FA 12, Draft 11, Projections 10, Trade Machine 5. [assets/glossary.js:3920-3931; rendered #view=models group heads]
- The registry has 316 rows (validated 53, provisional 133, unvalidated 43, deprecated 87), checked_at 2026-09-23, version '2026-06-11'. /models/ reports 54 rows with no eval artifact, 5 artifacts behind 6 rows unpublished, 18 'unregistered' evals, and 0 stale p [data/model_registry.json; models/index.html Gaps section]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P1 | M13-01 | defect | CONFIRMED | Home Top Movers and the wire serve eFV-floor transitions as grade moves, labelled 'FV' | prospect-tracker/build_site.py, prospect-tracker/efv_alerts.py | New test_home_movers_floor.py: from a fixture with one floor transition and one regrade, build_home/build_news; assert no Top Movers row has an eFV 20.0 endpoin | S | conflict: none. This is a presentation-layer selector change. It does not touch the eFV floor model, sub-45 anchors, the blend lambda or any correction family, and it rel |
| P1 | M13-02 | defect | CONFIRMED | 24 served glossary slugs (betting, DFS) resolve to nothing; BETTING_ENTRIES never reached glossary.json | prospect-tracker/data/glossary.json, prospect-tracker/build_site.py | New test_glossary_slugs_resolve.py: scan assets/*.js, build_site.py and the generated HTML for data-gl=, #g=, _gl( and gl(label, slug); assert every slug is an  | S | conflict: None as a reopen; this is a copy fix. The new entry text has to respect these owner flags and bans: - CLV is retired (SERVE_CLV, owner 2026-09-07). - SERVE_RUN_ |
| P1 | M13-03 | defect | PARTLY | fantasy.json and dfs.json have 0 players in the working tree; the home Fantasy card silently disappears (narrowed: Keep the home-strip part: render the Fantasy card in an empty state that shows the artifact date instead of dropping it (build_site.py:3055). Fix the line citation to 3042-3059. Add that HEAD index.html has lacked the ca) | prospect-tracker/build_site.py, prospect-tracker/fantasy_export.py | Fixture with fantasy.json players=[]: assert the home strip still carries a Fantasy card with an empty-state line, and that fantasy_export refuses to overwrite  | S | conflict: None. No clock, gate, do-not-reopen item or locked owner decision is involved. The ROS floors and the empty-state reason are display-layer rules with no registe |
| P2 | M13-04 | improvement | PARTLY | Home module strip omits Franchise, Club Ledger, Arbitration, Management, HoF and Betting (narrowed: Build 5 cards, not 6. Put them in _cross_module_strip() (build_site.py:2874) in NAV order, with Franchise first among the MLB cards. (a) Franchise: top 3 of franchise_board.json board[] by index_score. Rows show code, na) | prospect-tracker/build_site.py | test_home_strip_covers_nav.py: every MLB Modules and Diamond leaf key has an xmod card, or an entry in an explicit exemption tuple with a reason. | M | conflict: No pre-registered gate is needed: no fitted model, threshold or served accuracy claim changes. Three conflicts shape the narrower build. (1) The Management 'rea |
| P2 | M13-05 | ux | CONFIRMED | No universal search: Ctrl+K cannot find a club, a module or a betting term; home search covers prospects only | prospect-tracker/assets/eephus-gl.js, prospect-tracker/build_site.py | Extend test_glossary_page_loads::test_quick_search_palette_finds_terms: 'NYY' leads to /franchise/#view=club&team=NYY, 'Club Ledger' leads to /ledger/, 'kelly'  | M | conflict: None. This is a navigation and index change only. No fitted model, served number, accuracy claim or clock is touched, and it reopens no DO-NOT-REOPEN item. The  |
| P2 | M13-06 | wiring | PARTLY | Player hub strip covers 3 modules on 3 cards; /player/ router is orphaned with a dead branch (narrowed: Build a narrower version.  (1) S, highest value. Link the arbitration name cell at arbitration.js:331 to /projections/#player=<byMlbam[m].key>. Load EEPHUS_HUB.links() once at init and copy the mlbstats.js:2020-2029 play) | prospect-tracker/mlb_player_export.py, prospect-tracker/assets/eephus-hub.js, prospect-tracker/assets/arbitration.js, prospect-tracker/assets/mlbstats.js, prosp | test_player_links_presence.py: flag counts match the source artifacts (arb 853). Playwright: clicking an arbitration row name lands on the same player's project | M | GATE conflict: None of this conflicts with a DO-NOT-REOPEN item or a betting or prospect clock. It is pure navigation wiring over served identity joins. The finding's /player/ |
| P2 | M13-07 | wiring | PARTLY | Franchise is the club hub, but no module links back to it; /teams/ still redirects to Projections (narrowed: Build a narrower, safer version. (a) Add EEPHUS_HUB.clubLink(x) to assets/eephus-hub.js next to club() (about line 99). Build it on the existing club(x): it returns '/franchise/#team=' + club(x).code, or '' when x is not) | prospect-tracker/assets/eephus-hub.js, prospect-tracker/assets/ledger.js, prospect-tracker/assets/arbitration.js, prospect-tracker/assets/mlbstats.js, prospect- | Playwright on /arbitration/#teams, /ledger/ and /mlbstats/#section=war&wview=teams asserts an a[href^='/franchise/#view=club&team=']. Unit test of clubLink over | M | conflict: None. This is pure navigation wiring. It changes no fitted model, served number or accuracy claim, and it reopens no DO-NOT-REOPEN item. The owner decision to p |
| P2 | M13-08 | defect | unverified | Glossary Models view files 60 registry rows, every 2026-09 module included, under 'Other' | prospect-tracker/data/model_registry.json, prospect-tracker/model_registry.py, prospect-tracker/assets/glossary.js, prospect-tracker/build_site.py, prospect-tra | test_model_registry: every row has an allowed module. Playwright on #view=models: the 'Other' group count is 0. | S | - |
| P2 | M13-09 | defect | unverified | /models/ lists 18 evals as 'unregistered' although at least 14 are cited in registry notes | prospect-tracker/build_site.py | test_models_orphans.py: a fixture registry citing an eval in notes renders it under 'cited by <model_id>', not as an orphan. | S | - |
| P2 | M13-10 | defect | unverified | Glossary How to Read, the stock entry and the Library view describe an older site | prospect-tracker/assets/glossary.js, prospect-tracker/data/glossary.json, prospect-tracker/build_site.py | test_glossary_page_loads: every NAV leaf href appears in the Library, and the guide names eFV as the headline grade. | S | - |
| P2 | M13-11 | defect | unverified | Glossary category hygiene: raw 'industry'/'method' chips, Valuation misfiled, duplicate p_enter/enter_prob | prospect-tracker/data/glossary.json | test_glossary_provenance: test_every_category_maps_to_a_group, test_no_duplicate_terms. | S | - |
| P2 | M13-12 | improvement | unverified | 33 of 132 Arkmetrics carry no formula; 184 of 355 entries overall | prospect-tracker/data/glossary.json | test_glossary_provenance::test_every_arkmetric_has_formula, with an allowlist that carries reasons. | M | - |
| P2 | M13-13 | ux | unverified | Nav gives top-level slots to inert or thin surfaces while receipts are footer-only | prospect-tracker/build_site.py, prospect-tracker/prospx/index.html, prospect-tracker/collegesavant/index.html, prospect-tracker/collegesavant/pitcher_index.html | The nav sync test still passes; /models/ and /news/ are in nav_leaves(); a skip link exists on every generated page. | M | GATE |
| P2 | M13-14 | ux | unverified | Dormant account layer shows a Sign in button on every page and costs 166 KB per page | prospect-tracker/build_site.py, prospect-tracker/assets/eephus-ui.js | Playwright with the blank config: no Sign in control and no request for eephus-account.js. | S | GATE |
| P2 | M13-15 | cleanup | unverified | Every page ships 127 KB of CSS comments and fetches a 455 KB glossary it mostly does not use | prospect-tracker/deploy/nightly-build.sh, prospect-tracker/build_site.py, prospect-tracker/assets/eephus-gl.js | test_asset_versioning covers glossary_tips.json; a size budget keeps it under 150 KB; the Playwright tooltip test still resolves. | S | - |
| P2 | M13-16 | improvement | unverified | No unified freshness: module stamps use mixed formats, and pipeline reds never reach a page | prospect-tracker/build_site.py, prospect-tracker/assets/accountability.js | Fixture artifacts with mixed stamp formats: assert the normalized age, and that a red ingest source appears on /models/. | M | - |
| P2 | M13-17 | improvement | unverified | No daily page: build a Today view out of /news/ | prospect-tracker/build_site.py, prospect-tracker/assets/site.css | test_news_page: the slate and alerts panels render, including their empty states. | M | - |
| P2 | M13-18 | data_source | unverified | /sources/ omits five upstreams the code reads; the TJStats card misstates the wire | prospect-tracker/build_site.py, prospect-tracker/deploy/data_exclude.txt, prospect-tracker/tjstats.py | test_sources_cover_hosts.py: every https host in an allowlist of ingest modules maps to a /sources/ card. | S | - |
| P2 | M13-19 | ux | unverified | Module pages end in dead ends: thin in-content cross-links, no related footer, no breadcrumbs | prospect-tracker/build_site.py | Every generated module page carries a related strip with at least 2 targets that exist on disk. | S | - |
| P2 | M13-20 | cleanup | unverified | Two renderings of one registry: /models/ and /glossary/#view=models | prospect-tracker/build_site.py, prospect-tracker/assets/accountability.js, prospect-tracker/assets/glossary.js | test_model_report_cards passes against /models/. Update test_glossary_page_loads::test_view_chips_match_whitelist deliberately. | M | - |
| P3 | M13-21 | improvement | unverified | The one article's board counts have moved; add a dated 'same cut today' receipt | prospect-tracker/build_site.py, prospect-tracker/content/articles/shortstops-galore-why-mlb-teams-love-ss.md | A fixture board asserts the receipt counts. | S | GATE |
| P3 | M13-22 | cleanup | unverified | 74 MB of scraped third-party pages are tracked inside the site tree | prospect-tracker/data/sources/samples | Port-readiness check: no tracked *.html under data/ exceeds 100 KB. | S | GATE |
| P3 | M13-23 | ux | unverified | Small shell inconsistencies: About vs Developers, a stale registry version, hardcoded colors, floor chips on veterans | prospect-tracker/build_site.py, prospect-tracker/data/model_registry.json | Extend test_no_hardcoded_colors to build_site.py inline style strings. | S | - |
| P3 | M13-24 | cleanup | unverified | Sitemap and robots are hand lists beside NAV_ITEMS; lastmod is always the build date | prospect-tracker/build_site.py | test_sitemap_diamond_sync extended: the sitemap set equals NAV hrefs plus SHELL_ROUTES plus articles. | S | GATE |
| P3 | M13-25 | cleanup | unverified | Stale comments that will mislead the executor | prospect-tracker/build_site.py, prospect-tracker/assets/eephus-gl.js, prospect-tracker/tjstats.py | None needed. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Restructure the top nav: add a 'Data & Methods' group (Glossary, Model Accountability, Park Factors, Data Sources) and a 'Newsroom' group (News, This Day, Articles), and hide the Forums leaf until accounts are live? Options: Yes to all three; Groups only, keep Forums visible; No change. **Default: Yes to all three, with the MLB Modules order unchanged.** Why: The owner set the nav order (2026-06-11, 2026-09-23). /models/ and /news/ are footer-only while Forums is inert and Articles has one piece.
- Hide the Sign in control and its preview-mode modal until Supabase is configured? Options: Hide until LIVE; Keep preview mode visible. **Default: Hide until LIVE.** Why: Every page shows a sign-in that cannot sign anyone in and loads 166 KB for it. Preview mode may be an intentional demo.
- Should /player/#key become the canonical cross-module player page (drop the robots Disallow), or should the orphaned router be deleted? Options: Make it canonical as a small hub page; Fix the router only, keep noindex; Delete it. **Default: Make it canonical as a small hub page.** Why: It is the natural share URL for one player across all modules. Today nothing links to it.
- Move data/sources/samples (157 tracked files, 74 MB of scraped third-party pages) out of the site tree before the port? Options: Move to a research path outside prospect-tracker/; Delete and keep only _MANIFEST.json; Leave in place. **Default: Move to a research path outside prospect-tracker/.** Why: It is not served, but it would travel into the production repo with the port.

### 4.14 Model registry and industry scoreboard (lane X01_registry_scoreboard)

**Census summary.** On identical rows against the best public comparator on disk, no flagship model wins.  - **eFV:** ties the consensus and MLB Pipeline. Vintage-matched n 812: 0.4064 vs 0.4135 and 0.4117, delta -0.0071 against an MDE95 of 0.0303 (data/source_backtest.json : accuracy.head_to_head_verdict). - **Ties:** HEM+ vs wOBA (+0.0032), xHEM+ and fwdHEM+ vs xwOBA (lo95 -0.0012), DEM+ vs its own raw rate (+0.0066), the mock draft (+0.0006), and win expectancy vs the MLB feed (-0.00016). - **Losses:**   - Arbitration vs Swartz: MdAPE 0.2156 vs 0.0811, 2.66x worse on n 261.   - HoF vs the HOF Monitor: -0.0255 AUC against an MDE95 of 0.0142.   - Betting vs Elo: Brier 0.24269 vs 0.24228.   - Betting vs the market open line: 0.24314 vs 0.22613 on the same games.   - Star-odds model vs the published table.   - Trade machine vs consensus FV: 0.3289 vs 0.3312.   - ETA vs FanGraphs' published ETA, per a read-only probe: MAE 0.878 vs our 1.425. That ETA is on disk in 23,954 snapshots and no eval uses it. - **Real public wins:** SEM+ vs raw FIP (+0.0346, lo95 +0.0177), REM+ vs raw FIP (+0.0261, lo95 +0.0023), the consensus blend's AUC over each public input (+0.0158 vs an MDE95 of 0.0078), and the eFV disagreement receipts (CI [0.510, 0.621]).  Most urgent defect: the /glossary/ Source Comparison chart, its 1200x675 share card and its per-year chart read accuracy.pooled. That scores eFV on 3,272 rows an...

**Served state (evidence in the lane's served_state.md).**

- Registry is 878,888 bytes, version 2026-06-11, checked_at 2026-09-23, problems []. It has 316 rows: 53 validated, 133 provisional, 43 unvalidated, 87 deprecated. 17 rows carry a card block and 1 carries depends_on. verdict_enum has no WIN/TIE/LOSS state and no [data/model_registry.json top-level keys version/checked_at/verdict_enum/problems; Counter over models[].verdict]
- 229 rows are non-deprecated. By surface text, 158 serve something (84 provisional, 41 unvalidated, 33 validated) and 71 are measurement-only or dark. Every eval_artifact path on a live row exists on disk. [scratchpad X01_registry_scoreboard/served_ids.json; os.path.exists over the eval_artifact regex]
- The Models & Proofs view is /glossary/#view=models. assets/glossary.js renderModels fetches /data/model_registry.json. Report cards are on by default (_CARDS_DEFAULT = true; #cards=0 hides them). With every card open the page renders 819,889 characters of text [assets/glossary.js:25-30, 4040-4052; render.py on port 8714, glossary_models.txt]
- The Source Comparison view reads data/source_backtest.json (gitignored, generated_at 2026-09-23T18:03:48Z) and data/xfv_scoreboard_eval.json (2026-09-23). No console errors on render. [glossary_srccomp.txt / .png; source_backtest.json generated_at]
- The artifact's headline verdict (vintage-matched, n 812): eFV 0.4064 vs PROSPX consensus 0.4135, MLB Pipeline 0.4117 and FanGraphs 0.3682. Delta vs consensus is -0.0071 against an MDE95 of 0.0303. resolvable is false and xfv_beats is false. [data/source_backtest.json : accuracy.head_to_head_verdict and accuracy.pooled_efv_common_vintage_matched]
- Four functions on the Source Comparison page read other frames. _methAccuracyChart and the _scxGfxSpec share card read accuracy.pooled (eFV n 3272 vs sources n 4316). _methEfvFindings reads pooled_efv_common (all vintages). _methPerYearChart reads per_year, wh [assets/glossary.js:1193, 3128, 1433, 1475/1529]
- STALE_DAYS is 90 and may not be lowered. No row is stale today. rem_plus, proj_def_prior and prospect_def_value are at 85 days, so rem_plus crosses the line about 2026-09-29. 28 served rows have artifacts 60 days old or older. 23 validated served rows predate  [model_registry.py:63; data/model_registry.json artifact_age_days]
- There are 220 data/*_eval*.json files. 20 are no row's eval_artifact (all cited in some row's notes). 79 are referenced only by deprecated rows. [glob vs registry eval_artifact set; test_model_registry.py:54 counts notes citations]
- The card trace test tolerates any number anywhere in the artifact within max(0.02, 2%). REGENERATED_CARD_ARTIFACTS lists only data/source_backtest.json. The fa_projection_marcel card (0.63/0.73) passes by coincidence. [test_model_report_cards.py:57-71, 110; findnum.py hits pooled_by_side.war:hit.mean_actual 0.6346, per_season[3].fip_mae_]
- BANNED_CLAIM_FRAGMENTS does not include 'best of every grader' (glossary.js:1440) or 'leads the pooled ordering comparison' (glossary.js:3301). Only fa_market's card is pinned to its artifact. [test_claims_freshness.py:45]
- The /fa/ Gate 1 table serves data/fa_meta.json gate1 (WAR MAE 0.5736 vs 0.7279, written 2026-09-23 15:51). data/fa_gate1_eval.json was rewritten at 16:06 (0.5157 vs 0.6242, war_provider ewar_v2). fa_backtest is not in run_monthly. [file mtimes; fa_export.py:1283; assets/fa.js:1864-1890]
- data/eta_eval.json is regenerated on every run_monthly: champion MAE 1.425 (n 4221) vs naive level table 1.975 (n 3508). prospects.db holds 23,954 FanGraphs snapshots with tools_json._extras.eta_year, and no eval reads them. [run_monthly.py:6166; sqlite snapshots query by source]

| ID | kind | sev | verdict | item | files | test | eff | gate/owner |
|---|---|---|---|---|---|---|---|---|
| P0 | X01-01 | defect | CONFIRMED | Source Comparison chart, share card and per-year chart print eFV's lead on mismatched rows | prospect-tracker/assets/glossary.js, prospect-tracker/source_backtest.py, prospect-tracker/test_claims_freshness.py | New test: no Source Comparison function reads accuracy.pooled or accuracy.per_year (static read of glossary.js), and every rater in per_year_efv_common[y] has e | M | conflict: The fix as written conflicts with do-not-reopen item 3 (docs/master-plan-2026-08-19-holistic-audit.md:53-54): copy may not say eFV discriminates better. The vin |
| P0 | X01-02 | defect | CONFIRMED | Hard-coded eFV superiority prose ('best of every grader', 'leads the pooled ordering', 'The lead grows') contradicts the verdict | prospect-tracker/assets/glossary.js, prospect-tracker/test_claims_freshness.py | Ratchet the fragments in test_claims_freshness. Add a static test that _methEfvFindings contains no literal comparative claim. | S | conflict: None. The fix enforces three existing rules and reopens nothing: - do-not-reopen #3: copy may not say eFV discriminates better. - do-not-reopen #9: hardcoded ac |
| P1 | X01-03 | defect | PARTLY | Report Cards star each model against the weakest baseline in its artifact (narrowed: Four literal or derived cards bar the model against the weakest baseline in their own artifact: - HEM+: AVG 0.2347, while OPS 0.4108 (lo95 -0.0126) and raw wOBA 0.4087 (lo95 -0.0096) are both ties. - DEM+: fld_pct 0.0111) | prospect-tracker/data/model_registry.json, prospect-tracker/model_registry.py, prospect-tracker/test_model_report_cards.py | test_card_baseline_is_the_strongest_listed: each card declares baseline_family keys, and its baseline equals the best value over them. | S | conflict: docs/HEM_RIV_REGATE_GATE.md R1-10 forbids adding a post-hoc baseline (Savant xwOBA) to the settled hem_plus row before the separately pre-registered re-gate, wh |
| P1 | X01-04 | defect | CONFIRMED | Stale literal cards and a card trace test that cannot fail; /fa/ Gate 1 lags its artifact | prospect-tracker/data/model_registry.json, prospect-tracker/model_registry.py, prospect-tracker/test_model_report_cards.py, prospect-tracker/fa_backtest.py, pro | test_every_card_is_derived; test_fa_meta_gate1_equals_artifact. | M | conflict: none. The fix removes an instance of a banned defect class (hardcoded accuracy claims, do-not-reopen list, docs/master-plan-2026-08-19-holistic-audit.md section |
| P1 | X01-05 | data_source | PARTLY | ETA never faces FanGraphs' published ETA, which is on disk and beats it in a read-only probe (narrowed: Build the receipt. Do not build the substitution arm as proposed.  (a) Comparator block. Add a fangraphs_comparator block to eta_backtest.run(): - Join each build_cohort row to FanGraphs' earliest same-year snapshot eta_) | prospect-tracker/eta_backtest.py, prospect-tracker/data/eta_eval.json, prospect-tracker/docs/eta-2026-09/ETA_FG_COMPARATOR_GATE.md | test_eta_backtest asserts a fangraphs_comparator block with equal n on both arms and an overdue count. | M | GATE conflict: Not a do-not-reopen item. The only closed ETA items are eta_age_continuous (deprecated) and the eta_hazard_lite owner history; this touches neither. The 2026-08 |
| P1 | X01-06 | improvement | PARTLY | Arbitration loses to Swartz by 2.66x; the counting stats it omits are known at hearing time (narrowed: Build a narrower version in this order.  Step 0 (S, defect, no new arm): make arb_dataset.load_ledger keep projection and tracker entries separately, keyed by (class_year, kind). Then re-score A6 under its registered pro) | prospect-tracker/tools/arb_gate_a.py, prospect-tracker/docs/ARBITRATION_GATE.md, prospect-tracker/data/arbitration_eval.json | Gate artifact gains an a7_known_season block with a paired bootstrap and its own MDE95. | L | GATE conflict: Conflicts with a pre-registered ban. docs/ARBITRATION_GATE.md section 4, "Banned from the champion, diagnostics only: ... counting stats", is enforced by test_a |
| P1 | X01-07 | data_source | PARTLY | HoF loses to the HOF Monitor, the artifact names the missing data, and that data is public (narrowed: Build a narrower version in three steps, and do not block it on Lahman.  Step 1, no network (S). Extend tools/hof_ballot_ingest.parse to keep the columns already in the 91 cached ballot pages: H, HR, RBI, batting_avg, W,) | prospect-tracker/hof_data.py, prospect-tracker/tools/hof_bakeoff.py, prospect-tracker/docs/HOF_BAKEOFF_GATE.md | Reproduction check of award counts vs Monitor inputs for 20 known players; the gate artifact carries merit_v2 vs hof_monitor with MDE95. | L | GATE conflict: Not on the do-not-reopen list: none of the 18 items in master-plan-2026-08-19 section 2 covers the Hall of Fame. Two gates are involved: 1. The bake-off (docs/H |
| P1 | X01-10 | defect | PARTLY | Spotlights rebound kill rule fired; faller control reads exactly 0.0; registry notes two months stale (narrowed: Three parts of the finding are confirmed. The rebound kill rule has fired (and has read 'deprecated' since at least the committed 2026-09-05 artifact), yet 7 Rebounders still ship in data/timeseries.json and render in th) | prospect-tracker/editorial_eval.py, prospect-tracker/spotlights.py, prospect-tracker/prospx/index.html, prospect-tracker/data/model_registry.json | A synthetic control row with a -5 FV move counts as a faller hit. | S | GATE conflict: Deprecating or relabeling the Rebounders is an owner call under the owner-committed kill rule (data/editorial_eval.json conventions.kill_rule). Ask it via AskUs |
| P2 | X01-08 | improvement | PARTLY | Serve the industry-gap scoreboard: a derived comparator block per registry row (narrowed: Build a narrower version on the machinery that already exists. Do not add a third parallel comparator schema, and do not add a new glossary sub-view: the glossary already has Models & Proofs and Source Comparison.  (a) E) | prospect-tracker/model_registry.py, prospect-tracker/data/model_registry.json, prospect-tracker/assets/glossary.js, prospect-tracker/test_model_registry.py | Every served row has a comparator block or an explicit 'none' with a reason; every derived value equals its artifact key. | M | conflict: No model changes, so no pre-registered gate is needed, as long as every outcome label is copied or computed from the artifact's own resolvable, CI or verdict fi |
| P2 | X01-09 | defect | PARTLY | Validated rows whose own notes say the gate is unmeasured on the served bundle; label-basis drift (narrowed: Keep the finding for fa_war_paths_decay. The /projections/#view=accountability card "Veteran WAR paths" shows a Validated badge, the legend "forward-chained backtest beats the baseline", and the 2022-2024 holdout table () | prospect-tracker/data/model_registry.json, prospect-tracker/test_model_registry.py, prospect-tracker/data/proj_horizon_eval.json | test_verdicts_are_honest fails any validated row whose notes contain 'UNMEASURED' or 'none has been re-measured'. | M | GATE conflict: 1. docs/PROJ_PATH_SHAPE_GATE.md section 15 makes re-measuring the engine-vs-champion edge on ewar_v2 legal at any time, and that re-measure may not move M. 2. T |
| P2 | X01-11 | improvement | unverified | Measure SEM+, REM+ and HEM+ against SIERA, xFIP and wRC+ | prospect-tracker/data/sem_plus_eval.json, prospect-tracker/data/rem_plus_eval.json, prospect-tracker/data/hem_plus_eval.json | The eval carries the new baseline keys with equal n and a v1/v2 gap CI. | M | GATE |
| P2 | X01-12 | ux | unverified | Unvalidated composite pills are coloured green/red with hand-set weights and no forward eval | prospect-tracker/prospx/index.html, prospect-tracker/data/model_registry.json | Static test: no pill for an unvalidated row uses is-pos or is-neg. | M | GATE |
| P2 | X01-13 | cleanup | unverified | Club Ledger has no registry row, and composites declare no dependencies | prospect-tracker/data/model_registry.json, prospect-tracker/model_registry.py, prospect-tracker/test_model_registry.py | Every served composite lists depends_on, and every id in it exists. | S | - |
| P2 | X01-14 | data_source | unverified | FA market has only an internal comparator; MLB Trade Rumors publishes annual contract predictions | prospect-tracker/fa_sources.py, prospect-tracker/fa_backtest.py, prospect-tracker/data/fa_gate2_eval.json | A comparator block in fa_gate2_eval with equal n. | M | GATE |
| P2 | X01-15 | defect | unverified | Trade machine surplus orders realized WAR worse than consensus FV and worse than its own grade | prospect-tracker/tools/trade_value_forward_backtest.py, prospect-tracker/bayes_trade_value.py, prospect-tracker/data/trade_machine_eval.json | The forward block carries 60d and 90d entries with CI. | M | GATE |
| P2 | X01-16 | improvement | unverified | Team outlook and playoff odds lack a public comparator, and the glossary line over-reads the retro | prospect-tracker/data/glossary.json, prospect-tracker/data/team_outlook_eval.json, prospect-tracker/data/futures_ledger.json | A GLOSSARY_CLAIMS pin for mlb_projections to team_outlook_eval. | M | GATE |
| P2 | X01-17 | data_source | unverified | Farm grades are scored only against prospect counts; public org rankings exist | prospect-tracker/farm_grade_backtest.py, prospect-tracker/data/farm_grade_eval.json | Comparator block per vintage with n 30 and a pooled CI. | M | GATE |
| P2 | X01-18 | cleanup | unverified | Verdict vocabulary: a 2.66x loss filed as NULL, a +0.0006 tie as BEAT, served displays shown as deprecated | prospect-tracker/tools/arb_gate_a.py, prospect-tracker/model_registry.py, prospect-tracker/assets/glossary.js | Registry enum test; a lint that no artifact says NULL where the gap exceeds its floor. | S | GATE |
| P2 | X01-19 | defect | unverified | WAR/PA+ loses to plain WAR forward yet shares the validated-index colour ladder; its rows point at no artifact | prospect-tracker/data/model_registry.json, prospect-tracker/assets/mlbstats.js, prospect-tracker/data/glossary.json | A GLOSSARY_CLAIMS pin for war_pa_plus to war_rate_plus_eval. | S | - |
| P2 | X01-20 | cleanup | unverified | consensus_weight_eval governs the live consensus weights and has no row | prospect-tracker/data/model_registry.json, prospect-tracker/test_model_registry.py | Tighten test_every_eval_artifact_is_registered so run_monthly-regenerated artifacts must be an eval_artifact, not a notes citation. | S | - |
| P2 | X01-21 | data_source | unverified | aStuff+ has a forward n of 22 and no public comparator | prospect-tracker/data/stuff_plus_aaa_eval.json | The eval carries a comparator block with n. | S | GATE |
| P2 | X01-22 | defect | unverified | Two artifacts give two archetype win counts on one page | prospect-tracker/assets/glossary.js | Static test that both functions use the same accessor. | S | - |
| P3 | X01-23 | improvement | unverified | Betting: the close-line tier is empty, betting_clv.json never exists, and Elo edges the model | prospect-tracker/assets/betting.js, prospect-tracker/betting_export.py | CLV panel empty-state test with the file missing. | S | GATE |
| P3 | X01-24 | data_source | unverified | Mock draft ties the board; public final mocks are the natural comparator | prospect-tracker/data/mock_draft_eval.json | The scorer handles several comparators with the shared alias map. | S | GATE |
| P3 | X01-25 | ux | unverified | Models & Proofs renders all 316 cards (820K characters) with no served filter | prospect-tracker/assets/glossary.js | The default filter shows only served rows; test_every_registry_row_is_on_the_page still passes via an 'All' chip. | S | - |

**Owner questions raised by this lane (defaults in bold).**
- Should the Report Cards and the new scoreboard name each metric's strongest public baseline even though HEM+, xHEM+ and DEM+ lose their stars? Options: Yes, the strongest public baseline only; Show both the strongest public baseline and the current internal baseline, labeled; Keep the current baselines. **Default: Show both the strongest public baseline and the current internal baseline, labeled.** Why: It is a copy decision about how the accountability page frames TIE results; the numbers are already in the artifacts.
- Two validated rows (mlb_projections_vets, fa_war_paths_decay) say in their own notes that their gate is unmeasured on the served bundle. Should they drop to provisional until the re-run? Options: Demote to provisional now; Keep validated and re-run before the port; Keep validated until the season-close fWAR epoch batch. **Default: Keep validated and re-run before the port.** Why: The registry notes explicitly refer this verdict question to the owner.
- The spotlights rebound kill rule has fired. Deprecate the Rebounders bucket or keep it as editorial-only copy? Options: Deprecate Rebounders; Keep as editorial-only with no predictive framing; Keep as is. **Default: Keep as editorial-only with no predictive framing.** Why: The kill rule is owner-committed (editorial_eval conventions).
- Register an ETA comparator gate against FanGraphs' published eta_year (already on disk) before the port? Options: Yes, register and run now; Register now, run after the port; No. **Default: Register now, run after the port.** Why: A read-only probe suggests FanGraphs' ETA beats ours on the conditional frame. A look needs pre-registration and the C4 overdue guardrail.

---

## Part 5. The cross-cutting programs

Lanes X02 (math and economics) and X03 (wiring) returned on 2026-09-24; X04 (hygiene and port readiness), X05 (data sources), X06 (UX parity) and X07 (copy and claims) returned later the same day as 5.3 to 5.6. These lanes ran WITHOUT a verify stage to save the usage window: every row below is a lead that its fixer reproduces on the served path before changing anything.

**New Wave 0 P0s from these lanes** (three duplicate groups already queued: X02-02 = M08-01 in G11, X03-03 = M09-02 in G13, X03-04 = M11-01 in G12): **G15** X02-01 hitter Luck sign artifact; **G16** X03-01 trade board merges different humans sharing a key; **G17** X03-02 monthly contract club overrides the current club for 134 vets; **G18** X04-01 + X04-06 withheld data exposure (the label matrix `xfv_hitter_matrix__E0.json` ships to the webroot because `deploy/data_exclude.txt` matches exact names only; the 1.9 GB untracked `_pre_epoch_2026-09/` at the repo root holds withheld label files and is not ignored); **G19** X07-01 / X07-02 / X07-06 / X07-07 copy truth (a refuted RIV+ claim, /sources/ denying the wholesale republication of 27,461 third-party reports, a 'Range ---' placeholder, FV defined as a ceiling). X06-01 = M11-01 (G12).

### 5.1 Mathematics and economics (lane X02_math_econ, unverified leads: each item is reproduced by its fixer before any change)

**Census summary.** I verified the plus family, the fWAR frame constants, the value framework, arbitration, the FA $/WAR level, the Franchise Index, the betting price math and the DFS/fantasy scoring, formula by formula, against the served artifacts. Most of it recomputes exactly: REM+, SEM+, HEM+, WAR-rate+, DEM+, the Franchise Index, the league-constant identities, the CBT and QO tables, and the Ottoneu points tables.  Two P0 defects show up on served pages: - **Hitter luck is backwards on 131 of 460 hitters.** The hitter Luck column (luck_gap = xHEM+ minus HEM+) compares a shrunk HEM+ with an unshrunk xHEM+ on two different anchors. It tracks how good the hitter is (corr 0.41 with raw wOBA), not luck. The committed fantasy buy-low list opens with Will Smith, Yordan, Witt and Judge. - **Every forward arb-1 salary collapses to about the minimum.** war3 and career_war are only computed on scored panel rows, so every pre-arb player enters the arb-1 model with zero career WAR. Served arb-1 has median $1.35M and max $2.0M. Skenes gets $886K and Caminero $896K, while realized arb-1 medians are $2.9-4.0M at 2+ WAR. The low ladders chain into salary paths, $366M trade values, Club Ledger rows and the Franchise board. The same model also trains on award-season performance, which is look-ahead.  The main economic defect is three $/WAR bases on one site: - prospects at $11.74M (clemens_2026, net 7 percent, no escalation); - vets on /projections/ at $17.97M (from a stale committed series); - the FA board at $17.14M, escalating 4.16 percent.  That is a 1.53x prospect-to-vet unit gap inside the Trade Mach

| ID | kind | sev | item | files | test | eff | gate |
|---|---|---|---|---|---|---|---|
| X02-01 | defect | P0 | Hitter Luck (xHEM+ minus HEM+) is a shrinkage artifact with the wrong sign on 131 of 460 hitters (Read Savant's own 'woba' next to 'est_woba' from the expected-leaderboard rows _join_xhem_plus already fetches, and publish luck = est_woba - woba in wOBA points (the pitcher convention). Alternative: 2.28*100*(est_woba - woba)/pool_xwoba o) | hitter_export.py, fantasy_export.py, assets/mlbstats.js, assets/fantasy.js, assets/fantasy-card.js, assets/redraft.js, data/glossary.json | test_hitter_export_contract: sign(luck) == sign(est_woba - woba) for every tracked row with /gap/ >= 0.005, and Spearman(luck, hem_plus) < 0 | S | - |
| X02-02 | defect | P0 | Forward arb-1 salaries collapse to about the league minimum, understating every arbitration ladder and inflating surplus ((1) Compute war3 and career_war over the full panel before build_board, and assert that no forward row is scored with default features (publish the count). (2) Gated: re-key every feature to the platform season Y-1 in both training and serv) | arb_export.py, arb_model.py, arb_dataset.py, data/arbitration.json, data/arb_history.json, data/mlb_projections.json, data/trade_values.json | test_arb_export: served arb-1 Spearman(w, usd) >= 0.4, and the served median for w >= 3 is at least 0.5x the realized band median. A feature | M | GATE |
| X02-03 | defect | P1 | Three $/WAR bases: prospects at $11.74M, vets at $17.97M, FA at $17.14M, and glossary copy that contradicts all three (The owner picks one open-market $/WAR level and one escalation rule for all surplus, supplied by one function. fa_export writes the series it prices with, or proj_export and ledger_export read fa_meta.dpw_series. Prospects and vets share th) | proj_export.py, fa_export.py, fa_market.py, value_framework.py, config/valuation_sets/clemens_2026.yaml, ledger_export.py, fa_config.yaml, d | A cross-artifact invariant: mlb_projections.dpw_usd == fa_class.dpw_usd for the same class year, and the prospect and vet per-win price are  | M | GATE |
| X02-04 | defect | P1 | FanDuel DFS scoring omits the quality start (+4) and keeps a retired per-out penalty; the DK caught-stealing -2 is not in the public rules (Add qs 4.0 to FD_PITCHER and drop out from FD_HITTER. Verify DK CS on the live DK rules page and drop it if absent. Stamp each table with source_url and verified_on.) | dfs_export.py, data/dfs.json | test_dfs_anchors pins the tables to the dated transcription, and every weight key must be a key the line builder produces (qs included). | S | - |
| X02-05 | improvement | P1 | Prospect arb years are priced at 1.5-1.8x the site's own realized awards; debuted arb years at about 0.3x (After X02-02, fit the per-step fraction from the corrected arb model on its own history, or price prospect arb seasons through the same arb chain with a league-minimum prior. Publish both ladders in value_framework.json and refit the v6 cal) | config/valuation_sets/clemens_2026.yaml, value_framework.py, arb_export.py, value_framework_config.yaml | The fitted fraction per step and the served clemens fraction agree within a tolerance, or the divergence is published and pinned. | M | GATE |
| X02-06 | defect | P2 | The signings-implied $/WAR divides nominal guarantees by discounted WAR (8-11 percent high as a per-season price) (Keep the FA ratio internal and export a separate per-season price, PV(guarantee)/PV(WAR), to consumers. Or discount every deal's level schedule in npv_guarantee_usd and re-run Gate 2.) | fa_market.py, fa_export.py, proj_export.py | For a synthetic 5-year level deal with flat WAR, the exported per-season price equals AAV/WAR. | M | GATE |
| X02-07 | defect | P2 | xHEM+ glossary formula omits the 2.28 gain; fwdhem and HEM+ SD scale claims do not match the artifact (Generate the formula strings and SD figures from the code constants and the artifact at build time.) | data/glossary.json, build_glossary_data.py | Evaluate the glossary xHEM+ formula's constants against hitter_export on one row; SD phrases must match the artifact within 0.5. | S | - |
| X02-08 | wiring | P2 | HEM+, wrc_rates and fa_projection still use the frozen 2013 wOBA weights while league_constants solves each season exactly (Read league_constants.weights(season) in hem_plus and wrc_rates, with the frozen set as fallback before 2011, then re-run the HEM+ eval.) | hem_plus.py, wrc_rates.py, fa_projection.py, hitter_export.py | hem_plus weights for 2025 equal league_constants 2025, and hem_plus_eval Spearman does not lose. | M | GATE |
| X02-09 | defect | P2 | SC+ glossary describes a deleted JS fallback and omits the EB shrink and the coverage-conditional divisor (Rewrite the entry from the statcast_plus.py docstring.) | data/glossary.json | The glossary methodology names the shrink and the coverage divisor (string test). | S | - |
| X02-10 | improvement | P2 | KRP+ display raw is a product, monotone in neither ERA nor K leg (Change the display raw only to a monotone composite such as min(z(-era_rel), z(k_rel)) or a weighted sum. The eFV model feature stays untouched.) | efv_score.py, data/glossary.json | A property test that the display raw is nondecreasing in -era_rel and in k_rel on a grid. | S | GATE |
| X02-11 | defect | P2 | Win-expectancy boundary table pools extra innings into ninth-inning cells, sampled after the ghost runner is gone (Exclude inning >= 10 from the boundary table, or add an extra-inning start table keyed on runner-on-second. Measure the contaminated row count on .cache/pbp_corpus (this lane may not read .cache).) | win_expectancy.py, data/win_expectancy.json | test_win_expectancy: no boundary cell includes inning >= 10 rows, and 9/bottom/0 n equals the count of bottom-9 tied starts. | S | - |
| X02-12 | defect | P2 | '120 is a top-2.5-percent season' is a normality assumption; 1.3 percent is measured (Derive the shares from the artifact at build time or drop the percentile phrasing.) | data/glossary.json, build_glossary_data.py, test_claims_freshness.py | test_claims_freshness flags 'top-N-percent' phrases that are not derived. | S | - |
| X02-13 | defect | P2 | The prospect engine prices pre-arb seasons at the 2025 minimum ($760K) while the 2026 CBA minimum ($780K) is on file (Read league_min_by_year[season] with carry-forward (reuse salary_path.league_min_usd).) | value_framework.py | The engine's pre-arb salary equals salary_path.league_min_usd(first_season). | S | - |
| X02-14 | cleanup | P2 | The base value config reads as production but the clemens_2026 overlay is what serves (Publish the resolved config and set id in value_framework.json, and relabel the base blocks as the prospx_current identity set (not served).) | value_framework.py, value_framework_config.yaml, fa_config.yaml | value_framework.json carries valuation_set and the effective inflation and discount, equal to vf._config(). | S | - |
| X02-15 | improvement | P2 | The pitcher fWAR replica misses its gate in 12 of 16 seasons ahead of the fWAR label epoch (List the residual pitcher rows over 1 run by role (swingmen, openers, traded pitchers) and close the leverage-chain and role-innings terms before the epoch. Do not move the label early.) | fwar_frame.py, tools/ (replica lab) | The replica gate passes on at least 14 of 16 seasons before the epoch flips. | M | GATE |
| X02-16 | defect | P2 | The working-tree fantasy.json has 0 players (HEAD has 652) (The fantasy lane diagnoses the input loss. Add a publish-manifest floor that refuses an artifact whose player count drops to 0 against HEAD.) | fantasy_export.py, deploy publish manifest | test_publish_manifest: fantasy.json n_players >= 0.5 x the committed count unless offseason is declared. | S | - |
| X02-17 | cleanup | P3 | The isotonic surplus calibration is in absolute $M with no stamp of the $/WAR level it was fit at (Stamp fit_dpw_level in the calibration block, rescale when the live level differs, and assert the stamp in test_calibration_vintage.) | value_framework.py, tools/fit_surplus_calibration.py, value_framework_config.yaml, test_calibration_vintage.py | A fit_dpw_level stamp equals the live level, or the rescale path is exercised. | S | - |
| X02-18 | cleanup | P3 | Two log-loss clamps (1e-9 in the model eval, 1e-6 in the settled ledger) (One constant imported by both.) | betting_model.py, betting_settle.py | Both functions return an identical log loss on a clipped fixture. | S | - |

**Owner questions.**
- Which single $/WAR level and escalation should price all surplus (prospects, vets, FA, ledger)? Options: FanGraphs graduated 2024-26 rate ($11.74M flat, no escalation, net 7%) everywhere; FA signings-implied winter level (about $17.1-18.0M) everywhere, with the clemens tier shape rescaled; Keep both, but publish the ratio and label each surface's basis. **Default: Keep both and publish the ratio until the owner decides; unify fa_export and proj_export on one written series immediately.**
- After the arb-1 fix, should prospect arbitration years keep the clemens 0.15/0.35/0.50/0.75 ladder or use fractions fit on the site's own arb history (about 0.10/0.20/0.30)? Options: Keep clemens (published FanGraphs convention); Fit from arb_history on the corrected model; Price prospects through the same arb chain with a league-minimum prior. **Default: Keep clemens and publish the fitted ladder beside it.**
- Should the arb model's look-ahead (award-season WAR and metrics as features) be removed even if GATE A's arb-1 margin shrinks? Options: Yes, re-key to the platform season and re-score the gate; No, keep the frame and fix only the missing war3/career_war. **Default: Fix war3/career_war now and re-score the platform-season frame as a registered re-gate.**
- Hitter luck in wOBA points (the pitcher convention) or in index points? Options: wOBA points (est_woba - woba); Index points on one unshrunk anchor. **Default: wOBA points.**

### 5.2 Cross-module wiring (lane X03_wiring, unverified leads: each item is reproduced by its fixer before any change)

**Census summary.** Cross-module census, read-only, of the tree as of 2026-09-24 (HEAD 8100ce49 plus the dirty working tree). I mapped all 440 data files to their producers and consumers (probe_matrix.py, producer_consumer_matrix.csv). There are no ghosts: every filename a page fetches exists or is a gitignored build output. But 47 files (18.9 MB) ship to the webroot with no page fetch, no /sources/ link and no /models/ receipt link, and 6 of them have no code reference at all. I traced 12 players across 20 artifacts and rendered 9 pages on port 8716 (the server is stopped). Four problems are P0: - **Merged identities on the trade board:** it merges different humans who share a key. 'Max Muncy ATH age 24.1 FV 43' carries the LAD veteran's $54.3M, and the same happens with jose_ramirez and jose_fermin. The surplus-parity test joins on key, so it certifies these rows. - **Stale contract club:** /projections/, player pages, player_links, the FA 'from' column and Team Outlook use the monthly Spotrac contract club. 134 of 1,129 vets are on a different club than the live war board (Skubal shows DET on /projections/ and LAD on /mlbstats/). 48 of 236 FA members have the wrong 'from'. - **Ledger Graduates:** it prints a capped at-debut engine as 'Debuted value'. 35 rows sit at exactly $523.6M (Mason Miller, an FV 35 reliever), the Control column is a constant '7 yrs' on 2,241 of 2,241 rows, and 230 pre-2020 debuts are labelled arb_eligible. - **Fantasy empty at season end:** the /fantasy/ Redraft board is empty. At season_fraction 0.983 the remaining-season (ROS) playing-time floors drop every player (

| ID | kind | sev | item | files | test | eff | gate |
|---|---|---|---|---|---|---|---|
| X03-01 | defect | P0 | The trade board merges different humans who share a key, and the parity test certifies the merged rows (Join apply_platform_surplus and the vet seeding on mlbam. When a key is an identity_collisions board key, refuse the re-point unless the mlbam ids match. Seed the missing veterans (571970, 608070) under their collision-safe keys. Join ledge) | bayes_trade_value.py, ledger_export.py, test_calibration_vintage.py | For every trade_values row with surplus_source projection, the source mlb_projections row has the same mlbam and /age difference/ < 1.5. A m | M | - |
| X03-02 | defect | P0 | The monthly contract club overrides the current club for 134 vets; projections, FA, player_links and Team Outlook all inherit it (Resolve team in proj_export from the current-club resolver (war_board_export's transaction-feed club, or trade_values org) and ship the contract club as a separate 'payer' field. fa_export reads 'from' from the same resolver; mlb_player_exp) | proj_export.py, fa_export.py, mlb_player_export.py, war_board_export.py | One-club invariant: for every mlbam present in mlb_projections, war_leaderboards, trade_values and fa_class, the canonical club is identical | M | - |
| X03-03 | defect | P0 | Ledger Graduates prints a capped at-debut engine as 'Debuted value' and a constant 7-year control (Serve dv_realized_mm (sunk realized value) and drop dv_trade_value_mm. Or repair value_framework.debuted_player_value to consume service time and cap control at the real window; take service phase from the contract and arbitration tables; l) | value_framework.py, ledger_export.py, assets/ledger.js | No served graduate row equals the engine maximum; the Control column has more than one distinct value per club; no pre-2020 debut is labelle | S | - |
| X03-04 | defect | P0 | /fantasy/ Redraft goes empty in the last weeks of the season (Offseason mode: when remaining < 0.05, serve next-season ranks from mlb_projections (Y1 WAR, rates, playing time) with a banner. Streamers use per-game rate projections instead of ROS totals so the final series still price.) | fantasy_export.py, assets/redraft.js | build_players on the fixture corpus at season_fraction 0.99 returns at least 300 rows or an explicit offseason payload with rows. | M | - |
| X03-05 | wiring | P1 | The PROSPX trade audit prices traded vets at career WAR x $/WAR although trade_values.json is in its payload (Look up vets in trade_values (key, then mlbam) as kind 'trade_board'. Keep career WAR only as a labelled tooltip. Retire mlb_trade_players.json.) | prospx/index.html, storage.py | Static test that the audit valuation prefers trade_value_mm; a fixture Gausman trade scores 0.7, not 348. | S | - |
| X03-06 | defect | P1 | One debuted player gets three different surplus figures across PROSPX, the Trade Machine and /projections/ (For status debuted with a projection-sourced trade row, lead with trade_value_mm and relabel the eFV figure 'prospect valuation at debut' in makeSurplusCell, displaySurplusMM, the phone row and the GFX card.) | prospx/index.html | A data-level parity assertion: for debuted keys with a projection trade row, the value PROSPX leads with equals trade_value_mm. A node harne | S | - |
| X03-07 | defect | P1 | /arbitration/ ladders ignore signed next-season salaries; /projections/ applies the 80% max-cut floor (arb_export reads the signed contract table as the prior rung and applies the max-cut floor, sharing salary_path's helper.) | arb_export.py, salary_path.py | Every served arbitration rung is at least 0.8 x the prior signed salary, and arbitration l equals salPath for arb_ladder seasons. | S | - |
| X03-08 | wiring | P1 | A June fielding file still feeds /projections/, PROSPX and position resolution (Have d9b1 also write mlb_fielding_positions.json from fielding_innings (same shape), or repoint the three consumers.) | fielding_innings.py, run_monthly.py, fielding.py, assets/projections.js, prospx/index.html | Freshness: mlb_fielding_positions.generated_at is within 2 days of fielding_innings; coverage of projections non-pitchers is at least 95%. | S | - |
| X03-09 | defect | P1 | ETA is 2026 on PROSPX and Dynasty but 2027 on /projections/ for the same prospect (After the MiLB season ends, roll the ETA year forward for prospects not on the active roster (eta.py season_phase).) | eta.py, fantasy_export.py | No active, non-rostered prospect has eta.year equal to the current season after the MiLB end date. | S | - |
| X03-10 | ux | P1 | The player hub strip spans 3 of 10 player-level modules; /hof/ has no player links and no mlbam (Add tm/arb/mlbstats/hof/pal flags to player_links through mlbam joins, add chips, and add #player= scroll-and-highlight handlers. Add mlbam to hof rows and link watch and active names to /projections/#player=.) | mlb_player_export.py, assets/eephus-hub.js, assets/trademachine.js, assets/mlbstats.js, assets/arbitration.js, assets/hof.js, assets/pal.js, | test_player_hub: Skubal's strip lists every module holding his row, and each chip's hash resolves a row in its artifact. | M | - |
| X03-11 | wiring | P1 | Graduates and farm finance credit the current club with another club's development and bonus (Attribute DEV and FIN leaves to the developing club (the acquiring club at signing, or the club at debut) and keep a 'now with' display column.) | storage.py, ledger_export.py, franchise_export.py | A traded graduate's WAR counts in the acquiring club's WAR-per-bonus and not in the current club's. | M | GATE |
| X03-12 | wiring | P1 | The Trade Machine has no payroll or CBT context, although the Ledger already computes it (A display-only line per side: tax payroll before and after, bracket, and marginal tax on the salary moved, read from ledger_board. The per-player evaluator number stays single (decision D4, 2026-09-16).) | assets/trademachine.js, build_site.py | Byte-identical guard on trade_values.json plus a unit test of the tax arithmetic against fa_cba rates. | M | - |
| X03-13 | wiring | P2 | Forward FA classes lack platform salaries that the arbitration board already has (Fill a display-only 'projected platform salary' from the last arbitration rung. It never enters AAV pricing.) | fa_export.py, assets/fa.js | projAav and projGuar are byte-identical before and after; the new field is non-null wherever a ladder exists. | S | - |
| X03-14 | defect | P2 | Arbitration WAR comes from an older projections vintage on three pages (Join w from mlb_projections at ledger and franchise export time, or add arb_export to the daily chain after d9.) | ledger_export.py, franchise_export.py, run_monthly.py | Served arbitration w equals projections war per season within 0.005. | S | - |
| X03-15 | cleanup | P2 | 47 files (18.9 MB) ship to the webroot and nothing reads them (Add the 47 to deploy/data_exclude.txt (or move pipeline inputs to data/_internal/), delete the 6 no-reference files, and have gen_audit_docs report shipped-unconsumed files.) | deploy/data_exclude.txt, tools/gen_audit_docs.py | The shipped set minus (fetched ∪ catalog-linked ∪ registry-linked) is empty. | S | - |
| X03-16 | ux | P2 | Two club code families print on served pages (Render every club cell through EEPHUS_HUB.club(code).code; exporters keep their join spelling.) | assets/mlbstats.js, assets/redraft.js, assets/betting.js | DOM test: no StatsAPI-only code in a rendered club cell. | S | - |
| X03-17 | ux | P2 | One player shows three ages; /projections/ mixes two age definitions in one column (Label the header 'Age (2027)' and ship prospects on the same basis, or use one decimal age everywhere.) | proj_export.py, assets/projections.js, assets/fa.js | Vets and prospects on /projections/ share one age_basis field. | S | - |
| X03-18 | ux | P2 | The Franchise page prints two 2026 team WAR totals on different bases, and its history links land on /hof/ (Label the two figures ('current roster, eWAR' vs '2026 club, bWAR') and link the history leaves to /mlbstats/#section=war&wview=teams&team=CODE.) | franchise_export.py, assets/franchise.js | Copy test: each war-kind leaf names its basis; no leaf links a route that has no club view. | S | - |
| X03-19 | wiring | P2 | Fantasy streamers ignore the per-hand lineup splits that MLB Stats already serves (Add a display column with the PA-weighted opponent HEM+ vs the streamer's throwing hand. Adopt it in the start score only after a measured lift.) | fantasy_export.py, assets/redraft.js | Byte-identical start score until the gate passes; the column matches the orders arithmetic. | M | GATE |
| X03-20 | wiring | P2 | The gated DFS park leg is not applied to Redraft streamers (Reuse the DFS park multiplier on the streamer score after its own gate.) | fantasy_export.py | Byte-identical streamer output with the flag off; gate artifact on file before it is switched on. | S | GATE |
| X03-21 | wiring | P2 | FA team fit and the Ledger use different payroll-space numbers for the same club (FA afford and Franchise read the ledger's platform-basis space, with the Spotrac figure as a labelled sibling.) | fa_fit.py, franchise_export.py | fa_class projAav is byte-identical; afford recomputed on one basis; fa_gate3 re-run. | S | - |
| X03-22 | wiring | P2 | Betting futures rows do not link to the Franchise pages (Link club cells to /franchise/#team=CODE. Link only; no Franchise figure on a priced cell.) | assets/betting.js | test_betting_mgmt_fence stays green; a DOM test that each futures row has one franchise link and no new numeric cell. | S | - |
| X03-23 | wiring | P3 | HoF watch could show projected career WAR once a forward backtest exists (After a forward backtest, show 'career bWAR + projected WAR through 2031' labelled by basis (projection is eWAR v2, the board is bWAR).) | hof_export.py, assets/hof.js | Forward backtest artifact on file; the displayed sum reproduces from the two artifacts. | L | GATE |
| X03-24 | wiring | P3 | DEM+ can sit beside HEM+ on MLB Stats lineup cards (Display-only join of dem_plus on mlbam.) | assets/mlbstats.js | Byte-identical hitter_leaderboards.json; the card shows dem_plus equal to the defense row. | S | - |
| X03-25 | cleanup | P3 | SITE_MAP omits the shard payloads and the /ledger/ note (Have gen_audit_docs introspect the shard URL templates and the ledger generator docstring.) | tools/gen_audit_docs.py, build_site.py | test_generated_docs_in_sync covers the new rows. | S | - |

**Owner questions.**
- Farm credit for graduates: should DEV and FIN leaves (WAR per $M of bonus, graduate contract surplus, WAG) count against the club that developed the player or the club that holds him now? Options: Developing club (acquiring club at signing); Club at MLB debut; Current club (today's behaviour); Both, served as two labelled columns. **Default: Developing club for the DEV/FIN leaves, with 'now with' as a display column.**
- Ledger Graduates 'Debuted value': stop serving the at-debut engine, or repair it and register it? Options: Remove the column and show realized value only; Repair debuted_player_value (service-time consumption, real control window) and add a registry row; Keep it, labelled 'at debut'. **Default: Remove now and re-serve only after repair plus a registry row.**
- /fantasy/ after the regular season: switch to next-season ranks from mlb_projections, or show an empty-state banner? Options: Offseason mode from mlb_projections Y1; Freeze the last non-empty build; Empty state with a banner. **Default: Offseason mode from mlb_projections Y1.**

### 5.3 Code hygiene, pipeline health and port readiness (lane X04_hygiene_port, unverified leads: each item is reproduced by its fixer before any change)

**Census summary.** Read-only census of code hygiene, pipeline health and port readiness on 2026-09-24. The rendered surface is clean: all 34 routes load with 0 console errors and 0 responses of 400 or above (route_render.json). The problems are in data, wiring and port preconditions.  The top defect is a leak. data/xfv_hitter_matrix__E0.json (2.32 MB, 1,899 rows) has the same 35 keys as the withheld xfv_hitter_matrix.json, including the label fields target_resolved and target_censored. It is tracked and ships, because deploy/data_exclude.txt matches files by exact name only.  The top wiring defect is data/mlb_fielding_positions.json. Its stamp is 2026-06-22 and nothing in the tree writes it, yet it still feeds three things: trade-value position resolution (fielding.py -> bayes_trade_value.py:551/2792), the /projections/ usage slot and the PROSPX detail line. 56 of 1,184 players (4.7%) now have a different primary position in the nightly fielding_innings.json. Seven more page-fed artifacts come from producers no pipeline phase runs, and they are 43 to 63 days stale.  Most of PORT_SPEC Phase 0 is not started: - Not done: P0.1, P0.2, P0.3, P0.4, P0.5, P0.7, P0.8, P0.11 and P0.13. - Partly done: P0.6, P0.10 (2 REDs left: betting_close_capture and vintage_capture_gap) and P0.12 (17 unsorted walks remain). - Done: P0.14, and P0.16 is largely done (pitch_plots now carry top_ref and a per-level stuff_baseline).  Port risks: - 199 commits exist only on this laptop, and CI has never run on them because the workflow triggers only on pushes to main. - There is no dependency lock. The swing_plus bundle wa

| ID | kind | sev | item | files | test | eff | gate |
|---|---|---|---|---|---|---|---|
| X04-01 | defect | P1 | Withheld-class label matrix xfv_hitter_matrix__E0.json ships to the webroot (1. Add xfv_hitter_matrix__E0.json to deploy/data_exclude.txt now. 2. Change build_label_arms.arm_path to write under data/_labs/ (depth 2, not shipped by either deploy path) or .cache/label_arms/. 3. Move the E0 file there and update the ga) | deploy/data_exclude.txt, tools/build_label_arms.py, docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md, test_publish_manifest.py | test_publish_manifest.py: every data/*.json matching xfv_*matrix*, *_matrix__*, xfv_scored* or star_label* must be in data_exclude.txt or ab | S | - |
| X04-02 | wiring | P1 | mlb_fielding_positions.json has no producer and still feeds trade values, /projections/ and PROSPX (Repoint fielding._load_mlb_fielding_usage, projections.js and the prospx fetch to fielding_innings.json seasons[current season] (same g/gs/inn fields; map mlbam through player_links.json). Retire the June file, or add a daily producer. Rend) | fielding.py, assets/projections.js, prospx/index.html, bayes_trade_value.py, data_catalog.py | Unit test: fielding.position_usage for a moved player reflects fielding_innings.json. Plus the per-artifact cadence test from X04-13, which  | M | - |
| X04-03 | cleanup | P1 | PORT_SPEC Phase 0 status: 9 of 16 preconditions not started, 3 partial; ranked pre-port top 10 (Execute the ranked top 10. Add docs/port/PHASE0_STATUS.md generated by a script that re-measures each row, so status is never transcribed by hand.) | docs/port/PORT_SPEC.md, docs/port/PHASE0_STATUS.md, docs/audit/current_state_map.md, test_proj_ml.py, data/model_registry.json | The status script exits nonzero while any precondition is NOT MET. test_proj_ml asserts meta.train_hash appears verbatim in every registry r | L | GATE |
| X04-04 | cleanup | P1 | No dependency lock; swing_plus bundle pickled under sklearn 1.8.0 already loads under 1.7.2 with a version warning (1. Commit pip freeze from the box and the laptop as constraints-box.txt / constraints-local.txt. 2. Declare numpy, pandas, scipy, statsmodels and joblib in requirements.txt. 3. Add requirements-dev.txt (playwright, ruff, pytest pinned). 4. ) | requirements.txt, constraints-box.txt, constraints-local.txt, requirements-dev.txt, deploy/nightly-build.sh, .github/workflows/deploy-prospe | test_model_bundles_load_clean.py loads each shipped bundle with InconsistentVersionWarning promoted to error. It fails today on swing_plus a | M | - |
| X04-05 | cleanup | P1 | 199 commits exist only on this laptop and CI has never run on them (Push the branch to a private remote now, or write a git bundle off-machine. Record the tip sha. Either run the chunked suite on a schedule until cutover or add the working branch to the workflow trigger.) | .github/workflows/deploy-prospect-tracker.yml | git rev-list --count HEAD --not --remotes == 0 is an entry condition for PORT_SPEC Phase 1. | S | GATE |
| X04-06 | cleanup | P1 | 1.9 GB untracked, unignored _pre_epoch_2026-09/ at repo root holds withheld label files; 5 GB of DB backups beside the live DB (Move _pre_epoch_2026-09/ and the .bak-* sets to a dated archive outside the working tree with a sha256 manifest (keep them; they are pre-epoch evidence). Add _pre_epoch_*/ and prospects.db.bak* to the root .gitignore. Delete the 0-byte root) | .gitignore (repo root), data_analysis.py (repo root) | test_repo_root_hygiene.py: git ls-files --others --exclude-standard at the repo root returns no *.json outside prospect-tracker/data/. | S | - |
| X04-07 | cleanup | P1 | Full-history push per PORT_SPEC 6.2 carries 91 versions of the withheld scout_reports.json and a pre-FanGraphs-purge DB backup (Owner picks one of two options. (a) Push the full history to a remote readable only by the owner, and give the webmaster a filtered mirror. (b) Run git filter-repo --invert-paths on data/scout_reports.json and .backup-fangraphs-purge on a c) | docs/port/PORT_SPEC.md | On the new remote: git log --all -- prospect-tracker/data/scout_reports.json returns nothing (option b), or the remote ACL lists the owner o | M | GATE |
| X04-08 | cleanup | P1 | Suite record is 20 days old, never covered 134 of 460 test files; baseline reds list disagrees with the record (After the fixer's queue is empty (conftest reverts in-flight edits), run python tools/run_suite.py --out suite.json with --durations=25 in the chunk command. Reconcile KNOWN_BASELINE_REDS. Commit the summary, pip freeze, python version and ) | suite.json, tools/run_suite.py, docs/port/BASELINE_PYTEST.txt, docs/port/PORT_SPEC.md | test_suite_record_fresh.py: every test_*.py on disk appears in suite.json chunks[].files, and KNOWN_BASELINE_REDS equals the record's baseli | S | - |
| X04-09 | cleanup | P1 | Box publish gate silently skips 26 browser modules and the NameError guard (Install requirements-dev.txt (pinned playwright, ruff, pytest) plus python -m playwright install --with-deps chromium on the box. Replace py_mini_racer with the maintained mini-racer or run the JS smoke tests through playwright. Record the ) | requirements.txt, requirements-dev.txt, deploy/nightly-build.sh, conftest.py, test_collegesavant_smoke.py | Deploy-mode pytest asserts skipped <= the baseline skipped count from BASELINE_PYTEST.txt. | S | - |
| X04-10 | improvement | P1 | Frozen-input mode (P0.2) belongs at the HTTP layer: 34 modules fetch directly through 7 private cache helpers (Add netguard.py, imported first by run_monthly.py and build_site.py. When EEPHUS_CACHE_ONLY=1 it patches requests.Session.request, urllib.request.urlopen and socket.create_connection to raise NetworkForbidden(url) and log the URL. Cache hit) | netguard.py, run_monthly.py, build_site.py, deploy/nightly-build.sh | test_netguard.py: under the flag, requests.get raises and a cache-hit path returns. A subprocess run_monthly.py --rebuild-only under the fla | M | - |
| X04-11 | improvement | P1 | 82 of 407 shipped payloads carry no vintage, including the three largest boot files; catalog covers 13% (Do not reshape the bare arrays (that is a served-shape change). Write data/_manifest.json at the end of run_monthly and again at the end of build_site: {file: {bytes, sha256, generated_at (own stamp or writer run time), writer_module, caden) | data_catalog.py, run_monthly.py, build_site.py, manifest_export.py | test_manifest.py: every shipped file is present, every sha matches, no withheld file appears, and every row has a non-empty generated_at. | M | - |
| X04-12 | improvement | P1 | The only artifact differ covers 5 files with whole-document hashes and has never shown it can detect a change (Add tools/gate_c_diff.py: - snapshot <label> copies the manifest set (X04-11) outside data/. - diff A B parses both sides, sorts keys, compares numbers as Decimal of the serialized text, and prints every differing leaf path with both values) | tools/gate_c_diff.py, docs/port/NAMED_FIX.json, tools/pipeline_artifact_diff.py | test_gate_c_diff.py: the self-test; identical inputs give 0 differences; key reordering lands only in ORDERING. | M | - |
| X04-13 | wiring | P1 | Seven page-fed artifacts come from hand-run producers with no clock (43 to 63 days stale) (Add an ARTIFACT_CADENCE table in data_catalog.py (it already has a cadence field for 55 rows) naming each served artifact's producer and max_age_days, or frozen with a reason. Add a monthly phase for the cheap producers (statcast_aaa_hitter) | data_catalog.py, run_monthly.py, prospx/index.html, assets/parks.js, assets/glossary.js, assets/pal.js | test_artifact_cadence.py: every artifact a page fetches is in the table, and its stamp age is within max_age_days or it is marked frozen wit | M | - |
| X04-14 | cleanup | P2 | conftest artifact guard does not cover the 32 gitignored served artifacts or the per-player directories (Add a fourth half: record (size, mtime_ns) for every ignored data/*.json at depth 1 at session start. At session end, name any file that changed in the terminal summary and fail the run. Do not copy 283 MB aside; these files regenerate.) | conftest.py | Subprocess pytest self-test that touches an ignored fixture file and asserts the summary names it and the run fails. | S | - |
| X04-15 | defect | P2 | ingest_health.json publishes duplicate and cross-wired source rows (Give each writer a real scope: class year for fa_prospect_arc, players/teams for war_leaderboards, pass name for ifa_efv_join. Dedupe on (source, scope), keeping the last row. Add a severity field and a yellow[] array; keep red[] for red on) | run_monthly.py, test_ingest_health.py | No two rows share (source, scope); last_ok_rows equals the same scope's own stamp; a YELLOW message never lands in red[]. | S | - |
| X04-16 | defect | P2 | Betting public-record panel links /data/betting_clv.json, which does not exist since CLV was retired (Wrap the clv link and the closing-line clause in clvEnabled(); the chain copy then reads two files.) | assets/betting.js | Render test (test_betting_policy_copy.py pattern): with serve_clv false, the record panel has no betting_clv href and no 'closing-line' text | S | - |
| X04-17 | defect | P2 | Em-dash placeholder renders on 128 inactive-prospect cards as 'Range  - - -  · O 0 · C 0' (Emit null for both labels and open/close in the empty case; the renderer already falls back to ' - '. Skip the Range line when fv_high_date is empty.) | consensus.py, prospx/index.html | test_consensus.py: the empty case has no U+2014 and no 0.0 open/close. Add a payload lint that fails on U+2014 in any data/*.json string val | S | - |
| X04-18 | ux | P2 | PROSPX boot depends on HTTP Range; a host that ignores Range downloads the 86 MB board twice (Write data/timeseries.version.json ({generated_at}) next to the board, fetch it no-cache, then the ?v= URL. Keep feeding _dataVersion from it. Update the size comment. Add PORT_SPEC B7's byte budget with a Range-disabled check.) | prospx/index.html, storage.py, build_site.py | Playwright test serving the site with Range disabled asserts exactly one timeseries.json body transfer on /prospx/ boot. Gate B7 asserts the | S | - |
| X04-19 | wiring | P2 | Port scope misses the ../milb-projections dependency of sdr_intake and its test (Vendor the 4 contract JSON and 3 fixtures into prospect-tracker/contracts/ with a provenance note (Will's repo and commit) and repoint both paths. Mark the two lab paths local-only in their docstrings. Remove the stray sys.path inserts.) | sdr_intake.py, test_sdr_intake.py, contracts/, test_age.py, test_consensus.py | A test that no production or test module resolves a path outside prospect-tracker/ (grep ROOT.parent / parent.parent outside tools/). | S | - |
| X04-20 | improvement | P2 | Eleven point-in-time accessors, no shared as-of contract or property test (Add asof.py: a small protocol with a required cutoff, strictly-before by default and explicit inclusive=True where intended. Add a parametrised property test that runs a fixture row dated exactly at the cutoff through each accessor. Migrate) | asof.py, test_asof_contract.py | test_asof_contract.py with a deliberately leaky fixture accessor as the positive control. | M | - |
| X04-21 | cleanup | P2 | Safe deletes: 6 dead tools, xwoba.py, an unreferenced 1.6 MB tracked file, 2 orphan lab dirs, player_news fetch (Delete the 6 candidates, xwoba.py, tools/_contact_out, tools/_lab_prospect, data/_gn_lab, and the player_news fetch and file. Move (do not delete) the 29 top-level lab outputs under tools/_lab_outputs/, since their stems are cited by docs.) | tools/build_grade_normalization.py, tools/census_game_feeds.py, tools/efv_grade_space_lab.py, tools/purge_source.py, tools/repair_asterisk_n | Re-run tools/dead_code_scan.py: 0 candidates. test_no_orphan_pages still green. | S | - |
| X04-22 | cleanup | P2 | Repo weight 405.7 MB tracked; derived shards and probe samples dominate (Apply PORT_SPEC 6.5 on the new remote: stop tracking data/mgmt_decisions/ (it regenerates and both deploy paths already ship it from disk), move data/sources/samples/ to a fixtures archive, and move tools/_*_out/ beside the gate docs that c) | .gitignore, data/mgmt_decisions/, data/sources/samples/, tools/_comb_out/, tools/_frontier_out/, tools/_sweep_out/ | test_publish_manifest.py still finds every shipped directory, and tests that read samples point at the new fixture path. | S | GATE |
| X04-23 | cleanup | P2 | Publish-time weight: strip site.css comments (40%), add both strips to CI, version the data scripts (Add a CSS block-comment strip (sibling tool) run on the webroot site.css after rsync and before gzip. Add both strips to the CI staging step. Stamp the three data scripts with build_site's md5 ?v=.) | tools/strip_prospx_comments.py, deploy/nightly-build.sh, .github/workflows/deploy-prospect-tracker.yml, prospx/index.html, collegesavant/ind | test_asset_versioning.py: no /data/*.js script tag without ?v=. Strip test: the stripped CSS parses to the same rule count as the source. | S | - |
| X04-24 | cleanup | P2 | Mega-functions: export_timeseries_json is one 8,269-line function; refactor only after Gate C exists (Do not split before the Gate C pin: the gate relies on identical code on both stacks. After cutover, split export_timeseries_json into per-block builders, using tools/gate_c_diff.py (X04-12) to show zero uncategorised leaves per commit. Mov) | storage.py, run_monthly.py, build_site.py | Gate C differ at zero uncategorised leaves for each refactor commit. | L | - |
| X04-25 | cleanup | P3 | Lint debt (60 unused imports, 15 unused variables) and two stale comments; secrets scan clean (Run ruff --fix for F401/F541/F811 in one commit and fix F841 by hand. Fix the two comments. Then add F401 and F811 to test_no_undefined_names' select list.) | bayes_trade_value.py, storage.py, trades.py, run_monthly.py, consensus.py, prospx/index.html, test_no_undefined_names.py | test_no_undefined_names extended to F401,F811 passes. | S | - |

**Owner questions.**
- Should the full git history (91 versions of withheld scout_reports.json, 19 of star_label_view.json, a pre-FanGraphs-purge prospects.db.bak) go to git.eephus.io unfiltered as PORT_SPEC 6.2 recommends? Options: Full history to an owner-only remote, filtered mirror for the webmaster; filter-repo those paths out, verify backfill_vintages, push the filtered history; Push full history to a shared remote as PORT_SPEC says. **Default: Full history to an owner-only remote, filtered mirror for the webmaster.**
- Push the 199 local-only commits to a private remote now, or keep NOT PUSHED until the port? Options: Push the branch to a private remote now; Write a git bundle off-machine, keep remotes untouched; Keep NOT PUSHED. **Default: Write a git bundle off-machine, keep remotes untouched.**
- Fix for mlb_fielding_positions.json (no producer since 2026-06-22, feeds trade-value position resolution)? Options: Repoint readers to fielding_innings.json seasons[current] and retire the file; Add a daily producer for the existing file; Leave as is with an as-of stamp. **Default: Repoint readers to fielding_innings.json seasons[current] and retire the file.**
- Which pytest runner is Gate A: the chunked tools/run_suite.py or single-process pytest -q as the nightly uses today? Options: Chunked everywhere (box and new host); Single process, after proving it fits box RAM; Both, recorded separately. **Default: Chunked everywhere (box and new host).**

### 5.4 Public data sources not yet used (lane X05_data_sources, unverified leads: each item is reproduced by its fixer before any change)

**Census summary.** Read-only census of public data sources the platform does not use yet, checked against what it already reads (60 StatsAPI URL literals, 9 Savant leaderboards, FanGraphs leaderboard JSON through fg_leaderboards.py, B-Ref war_daily, Spotrac, MLBTR, The Odds API, Open-Meteo, the TJ list, NCAA and a RotoWire sidecar that has been empty since June). Each candidate source got one or two access requests, with every number traced to an artifact. The full catalogue of about 45 sources, scored 1-5, is in CATALOGUE.md. The harness blocked FINDINGS.md and served_state.md, so their content is in this object.  The largest gains that need no gate are display columns from free Savant CSVs that were confirmed per season: - **Custom leaderboard:** discipline and batted-ball columns join 661/661 hitters, 236/236 starters and 502/510 relievers. It also fills the starter SwStr% gap that starter_export.py:12 admits. - **Catcher defense:** blocking, throwing, pop time and fielding run value are all season-resolved. So is catcher framing on the /catcher_framing path. This contradicts ewar.py:1489-1512, positional_fit.py:53 and savant_oaa.py:19, which call the catcher hole unfillable. - **Bat tracking:** already cached on disk (595/619/557 rows for 2024-2026) but served nowhere.  Four measured receipts: - The self-computed gmLI matches FanGraphs' published gmLI, which already sits in the cache: Spearman 0.983, n 498. - DEM+ fielding runs agree with Savant Fielding Run Value at Spearman 0.930 (n 651). DEM+ has never been scored against it. - The home-plate umpire can be known before the game. The ne

| ID | kind | sev | item | files | test | eff | gate |
|---|---|---|---|---|---|---|---|
| X05-01 | data_source | P1 | Savant custom leaderboard fills the MLB boards' missing discipline and batted-ball columns at 100% join (New savant_leaderboards.py: one season-stamped cached CSV per side-season that refuses a changed shape, with the column list in one constant. Join in hitter_export.py, starter_export.py and bullpen_export.py. Derive starter SwStr% = swing% ) | savant_leaderboards.py, hitter_export.py, starter_export.py, bullpen_export.py, assets/mlbstats.js, data/glossary.json, run_monthly.py | Contract test in the style of test_hitter_wrc_plus: join rate >= 0.99 on qualified rows, source stamp on every column, no derived column exc | M | - |
| X05-02 | data_source | P1 | Season-resolved Savant catcher defense exists; three modules document the catcher hole as unfillable (savant_catcher.py sidecar for 2018+: blocking runs, blocks above average, CS above average, catcher stealing runs, pop time, exchange, arm. Add a catcher view to the Defense board as descriptive columns. Rewrite the three stale comments to ) | savant_catcher.py, defense_export.py, assets/mlbstats.js, ewar.py, positional_fit.py, savant_oaa.py, data/glossary.json, run_monthly.py | Sidecar contract: season stamp, >= 60 catchers per full season, MLBAM join >= 0.98 to Defense-board catcher rows. A grep test that 'did not  | M | - |
| X05-03 | data_source | P1 | Awards and realized counting stats for a known-season arbitration arm against Swartz (Register a post-season known-season arm: CEILING_KEYS plus platform-season award indicators from a new StatsAPI awards cache, scored on the A6 rows against Swartz with the same MdAPE/MDE conventions. The forward arm keeps CHAMPION_KEYS. Ser) | arb_awards.py, arb_model.py, arb_dataset.py, arb_export.py, docs/ARBITRATION_GATE.md, test_arb_known_season.py | Frozen protocol hash before the fit is read. Award join rate reported. The banned-key test in test_arb_export.py is extended so the forward  | M | GATE |
| X05-04 | data_source | P1 | The home-plate umpire is knowable before the game; the 5d-F 'not servable' premise rests on one Preview-state probe (Register a new dark family (5m umpire) in docs/diamond-betting.md before any capture: rotation prediction at the open with a flag, schedule-hydrate value at the close, and as-of umpire zone tendency from own called pitches. Every value carr) | betting_umpire.py, betting_export.py, run_monthly.py, docs/diamond-betting.md, test_betting_umpire.py | Every stored umpire value has captured_at < first pitch; rotation accuracy is reported from officials only; no outcome column is read before | M | GATE |
| X05-05 | data_source | P2 | Bat-tracking data already cached for 2024-2026 is served nowhere (Promote the loader from tools/bat_tracking_lab.py to bat_tracking.py on the monthly path. Add bat speed, squared-up per swing, blast rate, swing length and attack angle as display columns and strip metrics.) | bat_tracking.py, hitter_export.py, mlb_player_export.py, assets/mlbstats.js, data/glossary.json, run_monthly.py | Sidecar contract: season stamp, >= 500 batters per full season, MLBAM join rate. Render test on three hitters. | S | - |
| X05-06 | improvement | P2 | DEM+ has never been scored against Statcast Fielding Run Value; same-season agreement is 0.93 (Add a comparator block to the DEM+ eval: DEM+ vs raw rate vs FRV persistence against next-season FRV per inning, on identical rows, with n and MDE. Publish the same-season agreement as a receipt.) | defense_export.py, dem_plus.py, tools/dem_frv_comparator.py, data/defense_leaderboards.json | The eval block carries n, seasons, label source and MDE; the render shows it only when present. | S | GATE |
| X05-07 | wiring | P2 | Self-computed gmLI matches FanGraphs' published gmLI at Spearman 0.983; the proof sits unused in the cache (A tools/ script reads the cache and writes an fg_replication block (season, n, rho, MAE, mean gap) into data/leverage_consistency_eval.json. It lives in tools/ so the fg_leaderboards import guard holds. Fix the 403 copy (X05-13).) | tools/gmli_fg_replication.py, data/leverage_consistency_eval.json, mlb_leverage.py, data/model_registry.json | The block is present with n >= 400 for a complete season; rerun after the season-close fetch. | S | - |
| X05-08 | data_source | P2 | FanGraphs Stuff+, Location+, Pitching+ and PitchingBot are downloaded and thrown away (With owner approval, run once with --keep-raw to read the field names, extend the kept column list, and add a tjStuff+ vs FanGraphs Stuff+ comparator block. FanGraphs values stay labelled as FanGraphs' and are never blended.) | fg_leaderboards.py, test_fg_leaderboards.py, tools/stuff_comparator.py, mlb_stuff_plus.py | Column-presence test on the cached schema; comparator block with n. | S | GATE |
| X05-09 | defect | P2 | Franchise tells readers attendance history does not exist; StatsAPI serves it back to at least 1980 (Correct blocked_on now to name decision D11, not data. Ask the owner whether to light team-season attendance (1980+, with 2020/2021 flags) and a titles/pennants column.) | franchise_export.py, assets/franchise.js, test_franchise_export.py | Copy test that blocked_on no longer says '2026 only'. If lit, a 30-club x season coverage census. | S | GATE |
| X05-10 | data_source | P2 | eFV v2 driver D3 can reach vintages before 2016 through StatsAPI dated transactions and 40-man snapshots (Backfill dated selections and protection-deadline 40-man snapshots for 2011-2015 into the same as-of tables, parsed by typeCode, and report coverage by vintage.) | efv_drivers.py, storage.py, tools/backfill_transactions_2011.py | As-of cutoff test (no transaction after V); coverage census by vintage. | M | GATE |
| X05-11 | data_source | P2 | Baserunning is the only fWAR component with no column on the hitter board (Serve FanGraphs BsR verbatim from the existing feed (no new fetch) and Savant runner runs as a second labelled column.) | hitter_export.py, saber_feed.py, assets/mlbstats.js, data/glossary.json | Contract test in the style of test_hitter_wrc_plus: verbatim value, MLBAM join, source stamp. | S | - |
| X05-12 | data_source | P2 | Served overseas factors come from scripted Sports-Reference Register pages; NPB publishes the same stats first-party (Owner rules on Sports-Reference use before the port. If refused, rebuild foreign-side lines from npb.jp and eng.koreabaseball.com and evaluate hitter_wrc_factor on NPB league totals.) | tools/refit_overseas_factors.py, overseas_export.py, data/overseas_translation_eval.json, test_phase4b_evals.py | The refit artifact records its source per row; the factor test is unchanged or re-pinned with provenance. | M | GATE |
| X05-13 | cleanup | P2 | Two versions of the FanGraphs access policy; four docstrings and three served registry rows still say 403-blocked (The owner pins which FanGraphs endpoints are allowed and for which purposes. Record it in DATA_SOURCES.md's curated block and SOURCE_AUDIT.md, and replace the 403 text in the three registry rows and four docstrings.) | docs/SOURCE_AUDIT.md, DATA_SOURCES.md, tools/gen_audit_docs.py, data/model_registry.json, model_registry.py, pal_export.py, bullpen_export.p | Grep test: no served string says '403-blocked' while fg_leaderboards.py is in the tree. | S | GATE |
| X05-14 | data_source | P2 | Steamer's own site lists pre-season projections for 2017-2024: a benchmark path that avoids fangraphs.com (The owner downloads the archive once (manual, dated, hashed). Build per M05-12, with ZiPS as a manual FanGraphs export.) | public_proj_ingest.py, proj_eval.py, assets/projections.js | Per M05-12: dated, hashed artifact; n and universe per block; the column renders only when the block exists. | M | GATE |
| X05-15 | data_source | P2 | Lahman 2025 is out (2026-01-02) and carries a ShareAlike license (Download directly from SABR, pinned by version and hash. Feed M10-11 and the Franchise titles/managers columns (Teams.WSWin/LgWin/DivWin, Managers). Keep Lahman-derived rows out of the CSV export unless the owner accepts ShareAlike.) | hof_data.py, tools/hof_ballot_ingest.py, franchise_export.py, sources/ (via build_site.py) | Version-pin test; Joe Torre reads Manager (M10-11 test). | M | GATE |
| X05-16 | data_source | P3 | Pre-2026 closing lines exist for a market backtest; one public archive is gone (Owner rules on the license. If yes, pre-register a market-calibration backtest on pre-2026 seasons.) | docs/diamond-betting.md, tools/betting_hist_odds.py | Registered protocol hash before any read. | M | GATE |
| X05-17 | cleanup | P3 | PROSPX fetches an empty news sidecar on player views (Skip the fetch when the sidecar is empty, or fill it with dated per-player StatsAPI transaction lines already cached by d4.) | prospx/index.html, player_news.py, run_monthly.py | No player_news.json request when the sidecar is absent or empty. | S | - |
| X05-18 | data_source | P3 | Savant percentile ranks, pitch movement, active spin and arm angle for the MLB player page (Source the raw values from these CSVs and keep the in-house percentile math for consistency.) | mlb_player_export.py, assets/mlbstats.js | Render test on three hitters and three pitchers. | S | - |
| X05-19 | data_source | P3 | Chadwick register as the crosswalk that X05-14 and X05-15 depend on (already planned in PORT_SPEC) (No new work; order X05-14 and X05-15 after PORT_SPEC D5.) | docs/port/PORT_SPEC.md | Per PORT_SPEC D5 coverage measurement. | M | - |
| X05-20 | data_source | P3 | Cot's Contracts for deferrals and options (Owner rules on terms. If yes, a manual per-winter check of deferred deals against Cot's.) | data/deferrals.json, fa_market.py | Coverage test listing deferred signings with no ledger entry (per M04-25). | M | GATE |

**Owner questions.**
- Which FanGraphs endpoints may production call, and for what? Options: Replica inputs only (status quo 14a); Leaderboard JSON for replica plus comparators (Stuff+, gmLI, SwStr%); Leaderboard plus projections JSON; Manual CSV drops only (revert to SOURCE_AUDIT). **Default: Leaderboard JSON for replica plus comparators (Stuff+, gmLI, SwStr%).**
- Keep scripted Sports-Reference Register pulls behind the served overseas factors? Options: Keep, with a rate limit and attribution; Replace with npb.jp / koreabaseball.com first-party pages; Freeze the current factors and stop refitting. **Default: Replace with npb.jp / koreabaseball.com first-party pages.**
- Light Franchise attendance (StatsAPI team-season history) and a titles/pennants column? Options: Both; Titles only; Neither, but fix the '2026 only' copy. **Default: Neither, but fix the '2026 only' copy.**
- Register a dark umpire family (5m) now so the capture clock starts this postseason or in spring 2027? Options: Register and arm now; Register now, arm at 2027 Opening Day; Do not pursue. **Default: Register now, arm at 2027 Opening Day.**

### 5.5 UI/UX parity with PROSPX (lane X06_ux_parity, unverified leads: each item is reproduced by its fixer before any change)

**Census summary.** I rendered 38 routes at 1280 and 390 px wide in light and dark (152 renders) with headless Chromium on port 8719. A second probe held back every /data/ request to capture the loading state, 404'd every /data/ request to capture the error state, and walked 30 Tab stops on 21 module pages. I then read each module's JS, CSS, exporter and payload.  The harness refused to let me write FINDINGS.md and served_state.md, so their full text is in the findings and served_state fields here. MATRIX.md, the probe scripts, render_results.json, state_results.json and every screenshot are in the lane directory.  Baseline results: - No page scrolls sideways at 390 px. - No console errors or failed fetches on any route. One exception: a transient PROSPX SyntaxError (`_orgFas` declared twice) caught while the fixer was mid-commit. It cleared on the next render and is not reported. - The focus ring shows on every Tab stop. - The shared kit (CSV button, glossary tooltips, stage chip) is present on most modules.  The worst problem as served: the Fantasy Redraft and DFS boards are empty. data/fantasy.json has 0 players and data/dfs.json has 0 games; the HEAD copies had 652 players and 11 games. The cause is the rest-of-season filter at 98.3% of the season played. DFS also tells readers there is a pipeline outage.  Modules farthest from PROSPX: 1. **Arbitration.** 853 rows with no column sort, no search and no player links, although all 853 resolve in player_links.json. No GFX card and no data-as-of stamp. 2. **Hall of Fame.** No links out to any module and no aria-sort. Its count line says "3620 p

| ID | kind | sev | item | files | test | eff | gate |
|---|---|---|---|---|---|---|---|
| X06-01 | defect | P0 | Fantasy Redraft and DFS serve empty boards; DFS claims a pipeline outage (Make the rest-of-season filter season-aware. Below remaining 0.05, either serve next season's full projection labeled '2027 preseason' or scale the PA/IP floors by remaining. In dfs_export, add empty_reason_kind 'season_complete' separate f) | fantasy_export.py, dfs_export.py, assets/redraft.js, assets/dfs.js | test_fantasy_export: build_players at season_fraction 0.983 returns > 0 players; test_dfs_served_counts: empty_reason_kind != 'no_corpus' wh | M | - |
| X06-02 | defect | P1 | Player page 'games by position' is frozen at 2026-06-22 (Add the fielding-positions refresh to the nightly, or feed the chip from positions_played.json.) | assets/projections.js, run_monthly.py | test_served_invariants: every artifact projections.js stamps 'as of' is within STALE_DAYS of mlb_projections.generated_at | S | - |
| X06-03 | ux | P1 | Tertiary text token and stage chip fail WCAG AA on card surfaces (Raise dark --text-tertiary to at least #868A95 (or alias --text-dim #8C919C). Darken light tertiary to about #67624F. Give the stage chip a darker light-theme orange or bold 11px. Restamp hand pages.) | assets/site.css, prospx/index.html | Extend test_theme_tokens.py: every text token >= 4.5:1 against bg-primary, bg-secondary and bg-tertiary in both themes | S | - |
| X06-04 | wiring | P1 | Arbitration, HOF, Management and Betting rows link to no player or club page (arbitration.js: resolve m via EEPHUS_HUB.links() and link to /projections/#player= (or /prospx/ for pre-arb prospects). hof_export: emit mlbam from the crosswalk and link. management.js: link club cells to /franchise/#view=club&team= and /l) | assets/arbitration.js, assets/hof.js, hof_export.py, assets/management.js, assets/betting.js | DOM test: count of a[href*='#player='] equals the resolvable rows on the first painted page | M | - |
| X06-05 | improvement | P1 | Arbitration board has no column sort and no search across 853 rows (Add sortable <th scope=col aria-sort> heads on player, club, class, ladder years, next rung and total. Add a name search bound to the class pills and club picker. Persist the sort in the hash (the mlbstats readSort idiom).) | assets/arbitration.js, build_site.py | DOM test: Enter on each head flips aria-sort and reorders tbody; search 'Skenes' leaves 1 row | M | - |
| X06-06 | ux | P1 | aria-sort is invisible to assistive tech on 11 modules (Add one shared EephusUI helper that renders <th scope=col aria-sort><button>label</button></th> with a delegated key handler; migrate every call site.) | assets/eephus-ui.js, assets/mlbstats.js, assets/pal.js, assets/parks.js, assets/trademachine.js, assets/betting.js, assets/dynasty.js, asset | Site-wide DOM test: no [aria-sort][role=button]; every sortable th carries aria-sort (generalize test_prospx_sort_a11y.py) | M | - |
| X06-07 | improvement | P2 | PROSPX boot downloads about 145 MB of raw JSON; the code comment says 42 MB (Split timeseries.json into a board slice plus lazy per-tab slices. Defer the warm until the user opens a tab that needs it. Verify .gz twins exist for every sidecar in deploy.) | prospx/index.html, run_monthly.py, storage.py | Byte budget on the built data/timeseries.json; Playwright test that the boot request list excludes draft_timeseries.json and debuts_lite.jso | L | - |
| X06-08 | improvement | P2 | Trade Machine and the player page load 5 to 9 MB of JSON they do not paint (Shard mlb_player_detail per player (the PROSPX player_detail/{key}.json pattern) and fetch on card open. Load grpo_public only when its board opens. Ship a slim player_links index.) | mlb_player_export.py, assets/trademachine.js, assets/projections.js, assets/eephus-hub.js | Per-page Playwright boot byte budget | M | - |
| X06-09 | defect | P2 | Missing values and dollar formats differ by module, contradicting the glossary (Move EM_DASH ' - ', moneyM (one decimal), war (one decimal) and the plus family (integer) into eephus-ui.js and migrate every module formatter.) | assets/eephus-ui.js, assets/ledger.js, assets/franchise.js, assets/management.js, assets/hof.js, assets/arbitration.js, assets/trademachine. | Extend the MIRRORS check to every module; DOM test that no visible td is empty unless marked data-empty-ok | M | - |
| X06-10 | wiring | P2 | Six module mastheads show no 'data as of' stamp (Add a masthead stamp slot in the shared shell, filled from each payload's generated_at by one eephus-ui.js call.) | build_site.py, assets/eephus-ui.js, assets/arbitration.js, assets/hof.js, assets/parks.js, assets/pal.js, assets/ledger.js, assets/franchise | DOM test per module: masthead stamp equals the payload generated_at date | S | - |
| X06-11 | improvement | P2 | No GFX share card on Arbitration, Club Ledger, Management, HOF, Parks or DFS (Include eephus-gfx.js in these shells and add a kind:'board' spec per primary table (the mlbstats pattern).) | build_site.py, assets/arbitration.js, assets/ledger.js, assets/management.js, assets/hof.js, assets/parks.js, assets/dfs.js | Extend test_gfx_chip_layout.py to every module shell | M | - |
| X06-12 | wiring | P2 | /models/ has no per-model anchors, so no module links to its registry row (Add id='m-<model_id>' to each /models/ row. Add a masthead registry chip per module listing its served model ids with verdict, each linking to /models/#m-<id>. Replace the Franchise raw-id chips with that link.) | build_site.py, assets/franchise.js | test_model_report_cards: every model id a surface cites resolves to an anchor on /models/ | M | - |
| X06-13 | ux | P2 | Management League table pushes three columns off-screen with a nowrap sentence (Move within_family_windows to a footnote row or a details disclosure, or give that column white-space:normal and max-width 36ch.) | assets/management.js, assets/management.css | DOM test: the census table scrollWidth <= clientWidth at 1280 | S | - |
| X06-14 | defect | P2 | Franchise prints a garbled sentence and raw JSON paths as reader copy (Author one sentence in franchise_export. Show module names on tiles with the path in a title attribute.) | franchise_export.py, assets/franchise.js | test_franchise_render: no rendered text matches a dotted snake_case path outside title attributes | S | - |
| X06-15 | defect | P2 | HOF count line says 3620 shown under 100 rows (Print min(rows.length, state.shown) shown of rows.length matching, then the band total.) | assets/hof.js | DOM test on the count text after first paint and after one Show more | S | - |
| X06-16 | defect | P2 | PROSPX masthead count (7,952) disagrees with the board count (8,071) (Derive the masthead total from the same pool as the board, or label both and name the difference.) | prospx/index.html | DOM test: with no filters the two counts agree | S | - |
| X06-17 | ux | P2 | Error states use five wordings; three lack Retry; PROSPX shows developer setup text (Add a shared EephusUI.errorState(host, {what, status, retry}) and adopt it everywhere; drop the README copy from PROSPX.) | assets/eephus-ui.js, prospx/index.html, assets/management.js, assets/ledger.js, assets/franchise.js, assets/trademachine.js, assets/diamond. | Playwright test that 404s every /data/ request (probe_states.py logic) and asserts a Retry control on each module | S | - |
| X06-18 | ux | P2 | No skip link: 13 Tab stops before any module content (Add a skip link to #main in the shared shell and PROSPX, with id='main' on main.) | build_site.py, prospx/index.html, assets/site.css | DOM test: the first Tab stop is the skip link and activating it focuses main | S | - |
| X06-19 | ux | P2 | Long tables without a sticky header row: Ledger, Franchise, Trade Machine (Reuse the .mlbstats-scroll sticky-thead container (site.css:1930-1985).) | assets/ledger.js, assets/ledger.css, assets/franchise.js, assets/franchise.css, assets/trademachine.js, assets/trademachine.css | DOM test: thead th computed position sticky after scrolling the container | S | - |
| X06-20 | improvement | P2 | No in-board name search on FA, PAL, Arbitration, Ledger club, Management or Betting props (Add a shared EephusUI.searchBox bound to each board's row list, with the query persisted in the hash.) | assets/eephus-ui.js, assets/fa.js, assets/pal.js, assets/arbitration.js, assets/ledger.js, assets/management.js, assets/betting.js | DOM test per board: typing a known name leaves exactly its rows | M | - |
| X06-21 | improvement | P2 | CollegeSavant lacks CSV, glossary tooltips and a 2026 hitter season, and has no page gutter (Add a CSV host and [data-gl] on metric heads, add the page-head gutter, use short team labels, and ingest 2026 B1G hitter tracking if the source publishes it.) | collegesavant/index.html, collegesavant/pitcher_index.html, collegesavant/app.js, collegesavant/pitcher_app.js, collegesavant/team_names.js | test_collegesavant_smoke: CSV button present and >= 1 [data-gl] after load | M | - |
| X06-22 | defect | P2 | Management default view reads a decisions corpus 20 days old (Put the decisions corpus build on the nightly or weekly cadence and report the corpus age in ingest_health.json.) | mgmt_decisions.py, mgmt_export.py, run_monthly.py | test_mgmt_export: in season, corpus_built_at is within N days of generated_at | S | - |
| X06-23 | ux | P3 | View pills lack tab semantics on FA, Projections, Trade Machine, PROSPX and Diamond (Add role=tablist/tab with aria-selected on the view pills.) | assets/fa.js, assets/projections.js, assets/trademachine.js, prospx/index.html | DOM test: exactly one [role=tab][aria-selected=true] per tablist | S | - |
| X06-24 | ux | P3 | Emoji glyphs in PROSPX and the account layer are off-theme (Swap to site glyphs: ▤ for GFX, a text 'Link' or ⧉ for share, ◆ for Diamond.) | prospx/index.html, assets/eephus-ui.js | Lint: no U+1F300-1FAFF outside the brand glyph U+1F70E in assets/*.js and prospx/index.html | S | - |
| X06-25 | cleanup | P3 | 26 dead border-radius declarations in module CSS (Delete the declarations and add a lint to test_design_tokens.py.) | assets/hof.css, assets/management.css, assets/trademachine.css, test_design_tokens.py | test_design_tokens: no border-radius in assets/*.css outside ::-webkit-scrollbar rules | S | - |

**Owner questions.**
- When the MLB season is over, what should Fantasy Redraft show? Options: Next season's full projection labeled '2027 preseason'; The final 2026 ROS board frozen at the last in-season build; An explicit 'season complete' state with the dynasty board promoted to default. **Default: Next season's full projection labeled '2027 preseason'.**
- Should missing values render as the ' - ' token everywhere, including ledger grid cells where blank means 'no contract year'? Options: Dash everywhere, with a distinct marker for no-contract-year cells; Dash for missing data only, keep deliberate blanks with data-empty-ok; Keep module-local conventions and fix the glossary copy instead. **Default: Dash for missing data only, keep deliberate blanks with data-empty-ok.**
- Is a per-module masthead registry chip (model ids and verdicts linking to /models/#m-<id>) wanted on every module? Options: Yes, on every module masthead; Only on modules that serve a model (not Ledger/Parks/HOF); No, keep receipts inside Method tabs. **Default: Only on modules that serve a model (not Ledger/Parks/HOF).**

### 5.6 Copy, claims and documentation truth (lane X07_copy_claims, unverified leads: each item is reproduced by its fixer before any change)

**Census summary.** Both copy gates pass. strip_emdashes --check and copy_lint --check exit 0 (copy_lint with 1,312 advisory hits), and all 31 rendered pages have 0 em-dashes and 0 console errors in their default state. Behind that clean result there are four gate blind spots and a small set of real claim defects.  The two P0s are claim-truth problems: - **X07-01:** The glossary RIV+ entry still says RIV+ tracks reliever AAV at least as closely as REM+ (0.58 vs 0.51, 271 signings). data/riv_market_regate_eval.json refuted that (0.5733 vs 0.5665 on 232 signings, gap lo95 -0.0953), and the registry row riv_plus is deprecated while the column still ships. - **X07-02:** /sources/ says no reports are republished wholesale. The served chunks data/scout_reports_0..7.json hold 27,461 full third-party reports: FanGraphs, MLB Pipeline, 3,764 paywalled Baseball America reports, ESPN and Just Baseball. Only FanGraphs gets a link back.  Wiring gaps: - 24 glossary hooks on /betting/ and DFS resolve to nothing. 16 are defined in build_glossary_data.BETTING_ENTRIES but were never merged; 10 are defined nowhere. Betting has 1 glossary entry and fantasy/DFS have 0. - 48 served models are mapped 'internal', so they have no glossary entry.  Drift: - 7 glossary numbers disagree with their artifacts (sem/rem 3yr, FA guarantee/years MAE, the FA engine h1 MAE, team outlook MAE), and 49 numeric claim sentences are unpinned. - An en-dash reaches /glossary/ Source Comparison through data/source_backtest.json window.note. The file is written with ensure_ascii, so both gates miss it. - consensus.py writes an em-dash into 

| ID | kind | sev | item | files | test | eff | gate |
|---|---|---|---|---|---|---|---|
| X07-01 | defect | P0 | RIV+ glossary entry serves a claim its own re-gate refuted (Delete the sentence. Replace it with: 'On 232 matched reliever signings RIV+ and REM+ track AAV about equally (rho 0.573 against 0.567); the gap is inside the noise floor.' Pin riv_plus in test_claims_freshness Part 2 against data/riv_marke) | data/glossary.json, test_claims_freshness.py | A test_claims_freshness Part 2 row for riv_plus, plus the banned fragment 'at least as closely as REM+' | S | GATE |
| X07-02 | defect | P0 | /sources/ says no reports are republished wholesale while 27,461 full third-party reports are public JSON (Owner picks one: (a) serve an excerpt of N words plus a source link for all five sources and keep full text out of /data/; (b) keep the full text and rewrite the /sources/ copy to state it; (c) drop BA full text. In every option, add a 'Vie) | storage.py, prospx/index.html, build_site.py, deploy/data_exclude.txt | A test asserting that the served chunk text length per report is at most N words (if excerpting), or that the /sources/ copy matches the pay | M | GATE |
| X07-03 | wiring | P1 | 24 glossary hooks on /betting/ and DFS resolve to nothing; the betting vocabulary was never merged (Lint BETTING_ENTRIES for em-dashes, banned words and accuracy claims, then run the merge. Write the 10 missing entries and tag them module betting or fantasy. Add a test that every data-gl slug under assets/*.js, */index.html and build_site) | data/glossary.json, build_glossary_data.py, test_glossary_hooks_resolve.py (new) | test_glossary_hooks_resolve: every data-gl, #g= and gl() slug is present in data/glossary.json | M | - |
| X07-04 | defect | P1 | Seven glossary numbers drifted from their artifacts; 49 numeric claim sentences are unpinned (Correct the numbers and add each cell to the test_claims_freshness Part 2 table (entry_id, pattern, artifact, keypath, tolerance). Then work through the remaining 43 unpinned numeric sentences listed in glossary_claims.txt.) | data/glossary.json, test_claims_freshness.py | test_glossary_numbers_match_artifacts, extended with the 7 rows | M | - |
| X07-05 | cleanup | P1 | The copy gates have four blind spots: escaped dashes, missing owner words, missing exporters, and third-party noise (In both tools, json-decode *.json targets and scan string values. Add the owner words to BAN with an allowlist for 'Leverage Index/high-leverage/gmLI/leverage_' and 'showcase circuit'. Add the exporters to TARGETS. Skip report, text and exc) | tools/strip_emdashes.py, tools/copy_lint.py, source_backtest.py, data/glossary.json, build_site.py | test_copy_gates: a fixture JSON with an escaped en-dash must fail --check, and a fixture 'harness' in glossary.json must fail | S | - |
| X07-06 | defect | P1 | Inactive and graduate cards print 'Range  - - - ' from an em-dash placeholder label (Emit None for the labels and values when there is no history, and skip the Range line when both labels are null.) | consensus.py, prospx/index.html | A test asserting no string value equals ' - ' in the data/inactive.json and data/debuts_full payloads, plus a prospx render assertion | S | - |
| X07-07 | defect | P1 | The FV glossary definition calls FV the projected MLB ceiling (Definition: 'Future Value: the 20-80 grade for the MLB role a prospect is most likely to settle into. 50 is an average regular.') | data/glossary.json | A test_claims_freshness banned fragment: 'projected MLB ceiling' | S | - |
| X07-08 | data_source | P1 | Attribution gaps: MLB Trade Rumors, The Odds API, Open-Meteo/NWS and ESPN logos, and a republished MLBTR dataset (Add /sources/ rows for MLBTR (comparator only), The Odds API, Open-Meteo/NWS (dark until wired) and team logos (ESPN CDN, club trademarks). Add arb_ledger.json to deploy/data_exclude.txt. Write per-source terms into NOTICE.md. Add curated D) | build_site.py, deploy/data_exclude.txt, NOTICE.md, DATA_SOURCES.md (curated block) | test_sources_page_names_every_ingest: every external host in *_ingest.py and betting_*.py maps to a /sources/ row | M | GATE |
| X07-09 | cleanup | P1 | README, CHANGELOG, BETA_READINESS and REVIEW_QUEUE are stale (Generate the README routes table from NAV_ITEMS in tools/gen_audit_docs.py and add README.md to test_generated_docs_in_sync. Write CHANGELOG entries for 09-04 to 09-24. Move BETA_READINESS.md and REVIEW_QUEUE.md to docs/archive/ and start L) | README.md, tools/gen_audit_docs.py, test_generated_docs_in_sync.py, CHANGELOG.md, BETA_READINESS.md, REVIEW_QUEUE.md | test_generated_docs_in_sync parametrized with README.md | M | - |
| X07-10 | ux | P1 | Launch copy: the 'β v1.0' version and 14 'β beta' chips, with exact replacement strings (Route every chip through _stage_chip (one dict), set EEPHUS_VERSION, and replace the prospx literals with a build-stamped attribute via restamp_hand_authored_pages. Apply the strings above once the owner confirms the version name.) | build_site.py, prospx/index.html | test_copy_gates: no 'β beta' literal outside MODULE_STAGE, and the version string appears exactly once in build_site.py | S | GATE |
| X07-11 | defect | P2 | Diamond scoreboard asserts an AUC tie that no floor measured (Change the text to 'statistically indistinguishable on ordering; the discrimination leg carries no floor on these rows', or publish an E_cond AUC floor into verdict_vs_consensus (source_backtest claim_instruments already computes AUC floors) | assets/diamond.js | A diamond render test: the discrimination clause appears only when the artifact carries an AUC floor | S | - |
| X07-12 | defect | P2 | /team/ carries a hard-coded betting claim that picks its baseline, plus stale counts (Replace with: 'a vintage backtest scored against the home-team constant (beats it) and the market open (does not)'. Use 'ten MLB modules' and 'nearly 10,000 players', or derive both at build.) | content/team.json | test_claims_freshness: content/team.json betting sentence pinned to betting_model_eval, and the module count derived from NAV_ITEMS | S | - |
| X07-13 | defect | P2 | '316 models with a predictive claim' overstates what serves; the VALIDATED legend contradicts two rows (Add a structured served:bool field per row. Print '316 registered claims, N serving'. Reword VALIDATED as 'a committed forward test whose stated result the surface reports', or add a measured-loss label. Drop or maintain the version line.) | data/model_registry.json, model_registry.py, build_site.py, tools/gen_audit_docs.py | test_model_registry: served is required; the home and Diamond counts are derived from it | M | GATE |
| X07-14 | ux | P2 | Registry notes render 574K characters of developer log in the reader's view (Add a reader-facing summary field (280 characters or fewer: claim, verdict, one number with its artifact key) per row, render it by default, and keep the notes behind 'developer notes'. Lint the summaries.) | data/model_registry.json, assets/glossary.js, build_site.py, tools/copy_lint.py | test_model_registry: summary is present and 280 characters or fewer for every serving row; copy_lint covers summaries | L | - |
| X07-15 | defect | P2 | Concatenated copy fragments render as run-on sentences on /ledger/ and /management/ (Add a joinSentences() helper that terminates each fragment, use it in ledger.js and management.js, and rename raw keys in the copy.) | assets/ledger.js, assets/management.js, ledger_export.py, mgmt_export.py | test_ledger_render and test_management_render: no fragment boundary where a lowercase word follows text with no stop | S | - |
| X07-16 | defect | P2 | /arbitration/ bolds a failed claim and hard-codes verdict labels (Render 'Claim tested: ...' plus a NULL chip. Derive the tile label from the ratio (above 1: Swartz more accurate; below 1: ours). Derive the masthead from results.*.verdict.) | build_site.py | test_arbitration_scaffold: a fixture with ratio below 1 flips the label; the Losses entries are prefixed 'Claim tested' | S | - |
| X07-17 | ux | P2 | Trade Machine shows two conflicting bylines (Give the build banner a byline parameter, for example 'Created by Anirudh Iyer · built on eephus.io by Noah J. Dengler'.) | build_site.py | A render test: /trademachine/ has exactly one creator byline | S | GATE |
| X07-18 | defect | P2 | The QO acceptance history is unverified and has at least one wrong row (Source every row from MLB.com transactions or the MLBTR QO tracker, correct 2025 to Nick Martinez (CIN), add any 2026 acceptances, and set verify_status to 'sourced' with a URL.) | data/qo_history.json | test_fa_cba: no acceptance row is curated-unverified; every row has a source URL | S | - |
| X07-19 | improvement | P2 | Glossary coverage: formulas, examples, orphan categories, and 48 served models with no entry (Write formulas for every custom-index entry first, add 'industry' and 'method' to groups, and write entries for Cmd+, betting game probability, DFS pricing and the fantasy boards. Re-map those rows in MODEL_GLOSSARY.) | data/glossary.json, test_methodology_freshness.py | test_glossary: every category custom-index entry has a formula, and every category is in groups | L | - |
| X07-20 | cleanup | P2 | The claims ratchet scans 5 files and misses 25 served surfaces (Widen CLAIM_SURFACES to assets/*.js, */index.html, build_site.py and data/*_board.json string values, stripping JS comments before matching.) | test_claims_freshness.py | test_banned_claim_fragments_absent over the widened set | S | - |
| X07-23 | ux | P2 | Voice: 40 served sentences scored (mean 3.4 of 5); worst 15 with rewrites (Apply the 15 rewrites. Items 1-2, 7-8 and 14 are one-line edits; 3-5 need the registry summary field (X07-14).) | assets/glossary.js, assets/ledger.js, assets/management.js, ledger_export.py, mgmt_export.py, franchise_export.py, assets/betting.js, assets | copy_lint with the owner ban list extended (X07-05) plus render tests on the rewritten strings | M | - |
| X07-25 | defect | P2 | The Diamond founding-price promise covers users the site cannot identify (Owner rewrite, for example 'Founding rate: $9.99 a month for a year for accounts opened in the first N days after launch', or open a signup list before making the promise.) | build_site.py | test_diamond_gating_contract: update the pricing copy expectations | S | GATE |
| X07-21 | defect | P3 | Dated history numbers no current artifact reproduces, and a '9% platform rate' that is not the platform default (Cite dated readings as '2026-07-25 reading (commit sha)'. Change the note to 'priced at 9%, the legacy prospx_current rate this table was built on'.) | assets/glossary.js, fa_export.py | test_served_gate2_note_names_the_rate_its_table_was_priced_at: update the expected wording | S | - |
| X07-22 | cleanup | P3 | Scout report cleaning residue: stat headers, grade lines and raw FanGraphs labels (Extend scrapers._clean_report_prose to lift header and grade lines into structured fields and leave the prose verbatim. Add cleaner tests. Map the tradedeadline labels in fgPrettifyInterval.) | scrapers.py, test_report_cleaner.py, prospx/index.html | test_report_cleaner: the Just Baseball header and the Pipeline grade line are stripped from text and preserved in fields | S | - |
| X07-24 | ux | P3 | Masthead style drift across modules (One masthead helper in build_site.py enforcing sentence case, with a shared number formatter, and align H1s with nav labels.) | build_site.py, assets/projections.js | test_no_orphan_pages or a new masthead test: each H1 equals its NAV_ITEMS label | S | - |

**Owner questions.**
- Scout reports: excerpt, keep full text with corrected /sources/ copy, or drop Baseball America full text before the port? Options: Excerpt about 60 words plus a source link, full text out of /data/; Keep full text and state it on /sources/; Keep FG/Pipeline/ESPN/JB full, drop BA full text; Leave as is. **Default: Excerpt about 60 words plus a source link, full text out of /data/.**
- What version string does the ported site carry, and do the module 'β beta' chips survive? Options: v2.0, chips removed; v2.0, chips replaced by the flagship registry verdict; Keep β v1.0 until Diamond launches; Date-based (2026.10). **Default: v2.0, chips replaced by the flagship registry verdict.**
- Does the RIV+ column stay on /mlbstats/ Bullpen after its registry row went deprecated? Options: Keep it as a descriptive value record with the refuted claim removed; Drop the column; Keep it and mark 'deprecated' in the header tooltip. **Default: Keep it as a descriptive value record with the refuted claim removed.**
- Should the registry VALIDATED legend distinguish 'measured, our metric loses' rows such as hof_public_bakeoff? Options: Add a measured-loss verdict; Reword the VALIDATED legend; Leave the legend and annotate the rows. **Default: Reword the VALIDATED legend.**

### 5.8 eFV v2: the owner's 2026-09-24 instruction (eFV must beat consensus and the industry, or be redone)

The full program is `docs/efv-v2/PROGRAM.md` (design lane `wf_de3038f3-267`, evidence under
`_finalpass_2026-09-24/efv2/`). Verdict: eFV v1 ties consensus on the only admissible frame
(0.4061 vs 0.4134, n 812, mde95 0.0303) because it is a small perturbation of the consensus it
reads (Spearman(eFV, consensus) 0.9175); the estimator is not the constraint; the redo is a redo
of INFORMATION, FRAME and LABEL. Champion H0 = consensus-offset hurdle with ridge heads (one
served ordering), challengers C1 (monotone GBM residual) and C2 (playing-time x rate). Drivers
ranked: D1 consensus-revision front-runner, D2 pitcher-leg repair, D3 org-private signals (40-man
adds, selections, Rule 5), D4 playing-time, D6 modern Statcast panel (preserve now, gate 2028+).
New frame F-LV (every listed prospect per preseason, W3 label); reserved R-LV = vintages
2020-2021, R-VM = the 2025+ debut cohorts, both code-guarded before any read. Honest ceiling: the
widest lead certifiable in 2026-27 is about +0.02 on F-LV if D1 works; F-VM cannot certify a
lead before the 2028-29 runs; a tie is the modal outcome and the program says so in advance.

Execution in this pass (single writer, after the W0 fixers): EV-00 the Source Comparison progress
ledger FIRST (owner ask), then EV-03 modern-signal retention, EV-04 F-LV frame code with the
RESERVED_LV guard, EV-07 D1, EV-08 D3, EV-01 the vm2 timing pin as an ADDITIONAL ledger frame
(the headline flips to vm2 once the owner has seen it; expected direction down, in-window rows
-0.0205), EV-09 H0 code on development frames only. Waits: EV-02 (board re-sort) on owner Q1;
EV-12 registration on the freeze, Z1, the EV-05 floors and owner Q2-Q4 (target 2026-11); every
reserved read not before 2026-12-01.

#### 5.8.1 Driver system v2 (owner 2026-09-25: rewrite or scrap the drivers; new ideas)

Spec `docs/efv-v2/DRIVER_SYSTEM_V2.md` (research run `wf_3d43e2d5-80f`, 275 logged development
probes, evidence under `_finalpass_2026-09-24/efv3/`). Bugs found: B1 the harness ties eFV into
100 grades before scoring (-0.0018 on every cell); B2 the board serves an ordering 0.012 worse than
the one the page scores (pitchers -0.052 vs consensus); B3 the pitcher block learns MiLB
missingness, a debut proxy; B4 identity resolution leaks the outcome (a fake +0.03 win vanishes
under an outcome-blind resolver). Design: consensus is the scale, the model only reorders inside
(side, list year) with a small fixed weight; drivers admitted only if their sign holds in every
training vintage; timing drivers only in a REACHED head; protection status and the pitcher
list-vintage K rate are the only drivers with independent signal. Honest expectation consensus
+0.003 to +0.010; under 10% odds of a resolvable reserved win; physical data from 2027 is the one
lever with more room. Owner answers (DS-Q1..Q4): V2 LEADS the board once built, labelled as tying
consensus; the pitcher block is SCRAPPED; within-(side, vintage) statistic primary; consensus repair
after the reserved reads. Build queue 5 (six tasks, DS-01..DS-17) runs after the P1 wave, before the
pixel build.

### 5.7 The pixel system (PX): icons, states and motion, pixel visualizations

Owner ask, 2026-09-24: "see if there's any on-theme pixel art designs/animations/visualizations
we could create across the site to improve the UI/UX further (ex. for module logos, etc.)".

Three directions were built and judged by three judges: A Scorebook ink (8.5, 7.0, 7.5), C Ballpark
scoreboard (7.0, 7.5, 7.0), B Card foil (5.0, 5.0, 5.0). A won two of three. This section ships
**A's system** (text-only top bar, 12 px crop, wire pictograms, state split, conservative viz
placement) redrawn in **C's weight** (2 px stems), with C's arc loader, foul-ball 404 and tied-game
line score, and B's card-back miss and ruler key. Nothing here touches a mark, the wordmark, the ramp
colours, the starfield or the WIRE marquee. No em-dashes.

Prototypes, all measured at 1280 and 390, light and dark, port 8745, server stopped:
`_finalpass_2026-09-24/pixelart/synthesis/final/` (`icons.svg`, `icons.json`, `sheet.html`, `motion.html`,
`viz.html`, `icons_4x.png`, `sheet_{1280,390}_{light,dark}.png`, `shots/`). Generators in
`synthesis/src/` (`icons_src.py` is the source of truth; `gen_icons.py`, `pieces.py`,
`gen_pages.py`, `shoot.py`). The repo was not touched.

#### What the merge fixes (every judge violation, with the fix)

| Found by judges | Fix in the merged set |
|---|---|
| A, C: symbols carry no fill, so external `<use>` paints black, invisible on dark | `fill="currentColor"` and `shape-rendering="crispEdges"` on EVERY `<symbol>`; measured: the external-ref menu icon paints 2 colours (ink + bg) in both themes |
| B: `--` inside a sprite comment, not well-formed XML, external use renders nothing | the sprite has no comments; the generator runs `ElementTree.fromstring` and refuses on `--` outside `--ico-accent` |
| A: 1 px outlines a step lighter than the Bold labels | stroke rule copied from PixelMplus12 Bold: vertical stems 2 px, horizontal rules 1 px, masses solid |
| A, B: Ledger, Management, News, Models are the same ruled rectangle | distinct outlines: Ledger = bound book (3 px spine), Management = flag (the rail's existing ⚑), News = dog-eared page, Models = check over a calibration ruler, History = calendar rings, IL = kit with handle |
| C: Fantasy, Park Factors, Diamond Pass are three diamonds | Park Factors redrawn as a fan (round outfield, straight foul lines, lilac infield); Fantasy stays hollow ◈, Diamond Pass solid ◆ (both are existing sigils, brief rule) |
| C: Transactions reuses ⇅ (the Leverage Index idea) | Transactions = arrow entering a roster box; ⇅ stays with Leverage Index |
| C: Debuted cap and Draft mortarboard are both domes | Draft = flat board with a hanging tassel; Debuted = cap with panel seam and bill |
| A: typewriter cursor; C: hover flicker (1.09:1, invisible) | no menu motion; hover, focus and current page change the accent group to lilac, nothing moves |
| A: 12 px loader dots read faint | C's 46 x 18 lamp loader at 2x on the wordmark's own arc |
| A: E4 copy conceit on the 404 | 404 keeps its copy; E4 is art only, on failed fetches |
| C: red border on failed and 404 | neutral `--border` frame everywhere; red keeps meaning below zero |
| C: six state scenes | four kinds: loading, filtered to zero, not measured or built, failed |
| C: lamp-mask masthead, a third anchor that lives in dark mode | dropped; light newsprint drives every drawing |
| C: V1 replaces `.bt-game-probs` in the priced card; A: 4 hollow squares draw a 3.3-pt edge (+20%) | no betting picture at all |
| C: V3 dithered spray field (rule 6) | dropped |
| B: ramp as a tier legend and as 4-sided rings, new hex, per-row rarity badges, pack-tear loader | none of it; the ruler key sits once per board header, FV key prints numbers only |
| A (inherited): trade in gold on the dark wire panel | prototype draws trade in panel ink; owner question Q3 |

---

#### 5.7.1. The system in 15 lines

1. Grid: every icon is a 12 x 12 core placed at (2,2) in a 16 x 16 `<symbol>`. One drawing, three sizes.
2. Sizes: 12 px (the core, `viewBox="2 2 12 12"`) in 12.5 px menus and PROSPX tabs; 16 px in the rail and cards; 24 px (core at 2x) on /team/; 32 px (full at 2x) on mastheads. Nothing else; 18 px and em sizes are banned.
3. Strokes: vertical stems 2 px, horizontal rules 1 px, masses solid, diagonals step one row per row; the PixelMplus12 Bold rule, so an icon weighs what its label weighs.
4. Colour: ink = `currentColor` (the label's own token). One accent group per icon = `var(--ico-accent,currentColor)`: ink at rest, `--accent-lilac` on hover, focus and current page.
5. Zero raw hex, zero gradients, zero `rx`, zero circles, zero opacity in the sprite. Canvas and PNG exports may use raw hex.
6. The ramp never enters an icon. It stays the 2 px active underline and appears in new work once: the loader's dotted 1-lamp track, behind a mask.
7. Gold: never. Red: never as a frame. Green and red only where the site already uses them (sparkline direction).
8. No ball, no monogram, no wordmark letters in any icon. PROSPX gets a card-with-portrait glyph, which retires the 14, 16 and 24 px monogram uses.
9. The top bar stays text. Icons live where a reader scans a list: two dropdowns, phone drawer, rail, cards, tabs, mastheads.
10. Motion: two pieces only. The loader loops while loading; the 404 foul ball plays once in 0.9 s. Both are CSS `step-end`, no JS, no rAF.
11. Every animated piece: base style is the still frame; explicit `@media (prefers-reduced-motion:reduce){animation:none}`; the old 2.4 s reduced-motion spin is deleted.
12. Everything else (menus, empty, not measured, failed, card back) is static.
13. Decoration is `aria-hidden`; labels and messages carry meaning; charts carry `role="img"`, an `aria-label` and a real `<table>` with every number.
14. Budgets: sprite at most 40,960 B (measured 15,436 B, 2,409 gzip, 53 symbols); each animation at most 8 KB (loader 2,951 B, 404 3,597 B with CSS); each static state at most 1.6 KB.
15. Fractional DPR (1.25, 1.5 Windows scaling) softens every pixel set, including all three directions; accepted, measured crisp at DPR 1, 2 and 4.

#### 5.7.2. Asset inventory

#### 2.1 Icons (53 symbols, id `i-<key>`, key = the NAV_ITEMS key where one exists)

| Group | Symbols | Placement (file : selector) | Pri |
|---|---|---|---|
| Top-nav leaves (7) | home, prospx, collegesavant, articles, forums, glossary, team | rail `build_site.py:3342 sidebar_icons` / `_sb_link` 3363 `.sb-nav .sb-ico`; phone drawer | P1 |
| MLB Modules (10) | franchise, fa, projections, mlbstats, pal, trademachine, arbitration, ledger, management, hof | `_nav()` 921 `.eephus-nav-menu a[role=menuitem]` (12 px), rail (16 px), mastheads (32 px) | P1 |
| Diamond (3) | fantasy, betting, diamond | same | P1 |
| Footer routes (4) | models, parks, news, history | mastheads 5398, 4754, 2032, 2712; `_cross_module_strip()` 2874 cards | P2 |
| PROSPX tabs + Watchlist (13) | px-prospects, px-spotlights, px-farm, px-transactions, px-il, px-leaderboards, px-debuted, px-draft, px-intl, px-overseas, px-timemachine, px-scatter, watchlist | `prospx/index.html:9040-9057 .section-tab[data-section]` + `.section-tabs-toggle` list (12 px); rail sub-nav `build_site.py:3384 .px-glyph` (replaces "›") | P1 |
| Optional (5) | li, defense, dynasty, redraft, dfs | xmod cards (⇅ Leverage Index, ⌖ Defense); fantasy sub-tabs | P2 / P3 |
| Nav controls (3) | search, theme-dark, theme-light | `_nav()` `.eephus-nav-ctrl`, THEME_BTN; ships only on Q2 | gated |
| Wire (6 + 2 aliases) | ev-up, ev-down, ev-promo, ev-demo, ev-il, ev-signing; ev-debut = px-debuted, ev-trade = trademachine | `_feed_html` 1776, `_ticker_html` 1787 `<span class="{typ}">`; /news/, /history/; newsday GFX | P2 |
| /team/ badges | the same symbols at 24 px | retires `_M_*` 5585-5627 and `_badge_for()` (the fourth vocabulary) | P2 |

Contrast: icons inherit label ink, so they match their labels (menu rest `--text-secondary` 6.11 light / 6.79 dark at worst, on hover bg); the lilac accent is 4.33 / 5.65 at worst. All above the 3:1 non-text floor.

#### 2.2 States and motion

| Piece | What | Placement | Bytes | Pri |
|---|---|---|---|---|
| Loader | wordmark arc on a 46 x 18 lamp grid at 2x, ramp as dotted track, ink ball steps and settles; still = apex | replaces `site.css:1751-1762 .state-message.is-loading::before` and its reduce rule; bare strings in franchise.js:742, ledger.js:1132, hof.js:335, parks.js:676, management.js SHARD.loading, prospx:4206/8898 | 2,951 | P1 |
| Filtered to zero | blank at-bat box, static | fa.js:1049, hof.js:213, parks.js:425, projections.js:1871, dynasty.js:409, betting.js:222 `empty()` (2842, 2845, 3209, 3315, 3688), betting.js:1466, diamond.js:387, dfs.js:610, build_site.py:3386 (also removes hardcoded `#6f8a76`), 3464 | 831 | P1 |
| Not measured / not built | unlit `- -` board, static | betting.js:1660 `chartAbsent()`, arbitration.js:297, dynasty.js:511, management.js:791 | 991 | P1 |
| Failed | E4 box, static, `role=alert`, Retry kept | fa.js:315, projections.js:3008/3256, mlbstats.js:2451 and 5 twins, pal.js:1435, dynasty.js:883, fantasy.js:807, redraft.js:1161, eephus-ui.js:941, ledger.js:167, management.js:232, franchise.js:742 | 976 | P1 |
| 404 | foul ball: the arc hooks left of the pole, board reads 404; one shot; still = final frame | `build_404()` 5996, above the existing nav rail; h1 copy unchanged | 3,597 | P2 |
| Player miss | card back "No. 404" with dashed stat lines | PROSPX `#player=` miss path (a grep for a player not-found message found none: an unknown id falls through to the board today) | 1,580 | P3 |
| Accent states | colour only | every `.ico` host | 0 new motion | P1 |

Left as text on purpose: Ctrl+K `.qk-empty` (eephus-gl.js:250), comment and post empties (eephus-ui.js:979, 1268): the art would outweigh the row.

#### 2.3 Visualizations

| ID | Reads | Placement | Pri |
|---|---|---|---|
| V1 Tied-game line score (C) | `data/management_board.json reference.half_inning_start.tied_game[]` (18 measured rows); 1 lamp = 1 point from 50%; top dim, bottom ink; bottom grows +8 to +13 by the 9th | `management.js:420-443`, above the existing table, which stays | P2 |
| V2 CBT bar (A) | `data/ledger_board.json league.rows[].cbt_payroll_2026` vs 2026 threshold $244.0M; $20M blocks, halftone over the line, lilac tick | `ledger.js` league table, one narrow column beside the dollar cell | P2 |
| V3 Step sparkline (A) | `p.points[].consensus_fv_raw`; held flat per board snapshot; dotted 45/50/55 grade rules | `_fv_sparkline` 2057 (callers 1384, 2083); later prospx `_miniSparkline` 43834 | P2 |
| V4 Key strips (B) | ruler: 6-cell meter per `--vt-*` step with its word; FV: the real `.rank-num.card-rarity-*` borders with "FV 45+ ... 70+", no tier names | ruler key via a new `EephusTiers.key(el)` in `assets/eephus-tiers.js`, once per ruler board header; FV key in the PROSPX board header | P3 |

#### 5.7.3. Implementation sequence

**Sprite location: external `assets/eephus-icons.svg`, not inlined by `page()`.** Reasons: (1) one
15.4 KB file (2.4 KB gzip) cached once, instead of 15 KB in every generated page and in four
copies (generated + three hand-kept pages) that would each need a sync test; (2) the hand-kept pages
reference the same file, so there is no drawing to mirror by hand; (3) per-symbol fill and crispEdges
make external `<use>` safe when a consumer forgets `.ico` (measured). Costs: one parallel request on
first view, and external `<use>` does not render over `file://` (prototypes and local checks run
through `http.server`). Cache-busting: `href="/assets/eephus-icons.svg?v=<_asset_ver>#i-key"`.

**Trap found in the tree:** `restamp_hand_authored_pages()` (build_site.py:6613) only stamps
`<link rel=stylesheet>` and `<script src>`, so a `<use href>` in PROSPX or CollegeSavant would never
be restamped; and `_ASSET_URL_RE` (6610) `(?:\?v=[^"]*)?` would swallow the `#i-key` fragment if
reused as-is. PX-09 fixes both before any hand page carries an icon.

| ID | What to build | Files | Test that pins it | Effort | Deps |
|---|---|---|---|---|---|
| PX-01 | Move the 12-core ASCII source and generator into the tree; emit the sprite, the canvas bitmap table and the branding sheets. Writes assets/ and branding/ only, never data/ (the pytest-revert trap). | new `tools/pixel_icons.py`; out `assets/eephus-icons.svg`, `assets/eephus-icons.json`, `branding/pixel/icons-sheet-{light,dark}.png` | T1 | M | none |
| PX-02 | `ICON_FOR` map (NAV_ITEMS key, footer route, PROSPX `data-section`, wire type to symbol) and `_ico(key, size)`; asserts size in {12,16,24,32}; `_ICONS_VER = _asset_ver("assets/eephus-icons.svg")` | `build_site.py` near 58-72 and 334 | T2, T3 | S | 01 |
| PX-03 | Shared rules: `.ico{display:inline-block;flex:none;vertical-align:top;fill:currentColor;shape-rendering:crispEdges}`, menu flex row with `line-height:16px` (whole-pixel rows), accent states; mirrored in the PROSPX `<style>` | `assets/site.css` near 625-635, 1134-1155; `prospx/index.html` `<style>` | `test_no_hardcoded_colors.py` (budget unchanged), `test_design_tokens.py`, T4 | S | 01 |
| PX-04 | Dropdown leaves and phone drawer: 12 px icon before the unchanged label | `_nav()` 921 | `test_collegesavant_nav_in_sync.py` (checks `>Label<`, which still matches after `</svg>`), T2 | S | 02, 03 |
| PX-05 | Rail: `_ico(key,16)` in `.sb-ico`; PROSPX monogram at 16 and 14 px becomes `i-prospx`; sub-nav "›" becomes the tab icons | `build_site.py:3342, 3363, 3370, 3384, 3410` | T2, T3 (no `prospx_ball_logo` call below 40 px) | S | 02 |
| PX-06 | xmod card titles: drop the second glyph set | `_cross_module_strip()` 2874 | T2 | S | 02 |
| PX-07 | Mastheads: `_masthead_icon(key)` at 32 px before the h1 text at the 23 module h1 sites; `_stage_chip()` untouched | `build_site.py` h1 sites 2032 ... 5986 | T2 (every page() `active` key renders one 32 px icon, one per masthead) | M | 02 |
| PX-08 | /team/ badges become the symbols at 24 px (core at 2x) | `build_site.py:5585-5627` `_M_*`, `_badge_for()` | T3 | S | 02 |
| PX-09 | Restamp `<use href="/assets/eephus-icons.svg?v=..#id">` in hand pages, fragment preserved: add `_USE_TAG_RE`, URL regex `((?:href\|src)=")(/assets/[^"?#]+)(?:\?v=[^"#]*)?(#[^"]*)?(")` | `build_site.py:6608-6636` | `test_asset_versioning.py`: use refs stamped and current; round-trip unit test on a fixture string keeps `#i-ledger` | S | 01 |
| PX-10 | Hand-kept pages: PROSPX nav menus, 12 section tabs, phone toggle list, watchlist; both CollegeSavant navs. Run `restamp_hand_authored_pages()` through a normal `build_site.py` pass, never by hand | `prospx/index.html`, `collegesavant/index.html`, `collegesavant/pitcher_index.html` | nav-sync test; T2 extension: each static `<a>` carries the icon id `ICON_FOR` gives its key | M | 03, 04, 09 |
| PX-11 | State component `EephusState.render(el, kind, html)`, kinds `loading / empty / unmeasured / failed`; `.px-state` CSS; loader replaces the steps(8) square and DELETES the 2.4 s reduce rule | `assets/eephus-ui.js`, `assets/site.css:1748-1762` | T5, T6 | M | 03 |
| PX-12 | Module swaps, one line each, every message text kept (sites in 2.2) | 14 module files + build_site.py:3386, 3464 | T5 (each listed site calls `EephusState`), `test_copy_gates.py` | L | 11 |
| PX-13 | 404 foul ball | `build_404()` 5996 | T6, T7 | S | 11 |
| PX-14 | V1 tied-game line score, JS renderer at most 3 KB (the prototype's static SVG is 21 KB of unit rects; the renderer merges runs) | `management.js:420-443` | `test_glossary_management_ids.py` untouched; new `test_management_tied_lamps.py`: lamp count per half = round(100 x (p - 0.5)), table unchanged | M | 03 |
| PX-15 | V2 CBT bar column | `assets/ledger.js` league table | new `test_ledger_cbt_bar.py`: under-line FLOORS, over-line CEILS (a club $11M under never touches the tick; $13M over shows a block) | M | 03 |
| PX-16 | V3 step sparkline, same signature, integer w and h (58 becomes 56: 8 columns x 7) | `_fv_sparkline` 2057 | new `test_fv_sparkline_step.py`: one run per snapshot, grade rules at multiples of 5 | S | none |
| PX-17 | Wire pictograms: `<span class="{typ}">{glyph}</span>` becomes `_ico("ev-"+typ, 12)`; per-type colours kept; trade per Q3 | `build_site.py:1776, 1787`; `site.css:1100-1105, 1222-1227` | T2 (every event type in `_collect_events` 1580 has an `ev-` symbol) | S | 02, Q3 |
| PX-18 | GFX canvas: `_pxIcon(ctx, key, x, y, scale, hex)` paints `eephus-icons.json` bitmaps with `fillRect` at integer scale; newsday frame draws wire pictograms, board exports draw the module icon left of the title; JSON fetched lazily at export time only | `assets/eephus-export.js` near `_brandCompose` 468; `assets/eephus-gfx.js` | `test_gfx_chip_layout.py` stays green; new check: painter scale is an integer | M | 01 |
| PX-19 | V4 key strips | `assets/eephus-tiers.js`, PROSPX board header | T4 (key prints words; no tier names shine/foil/chrome/holo/legendary in the key) | M | 03 |
| PX-20 | PROSPX player-miss card back (new message: owner may drop) | `prospx/index.html` hash router | T7 | S | 10 |
| PX-21 | Brand README: new section "Pixel icon set" after "Logo usage" (lines 1-3 and 5-8 of Part 1, the size list, the one-accent rule, "extends the marks, draws none of them"); Asset index rows for `assets/eephus-icons.svg`, `tools/pixel_icons.py`, `branding/pixel/`. The `.io` colour disagreement (README gold, site.css lilac, eephus-export.js:483 gold) is flagged there, not resolved | `branding/README.md`, `branding/pixel/` | `test_copy_gates.py` (no em-dash, no banned words) | S | 01 |
| PX-22 | Nav controls (Q2 only) | `_nav()` `.eephus-nav-ctrl`, THEME_BTN, three static navs | nav-sync, T7 | S | Q2 |
| PX-23 | Hinted clean ball at 16 and 32 px (Q4 only): same anatomy, hand-placed pixels | `tools/generate_brand_assets.py`, `assets/favicon-32.png`, `favicon.ico`, footer `_footer()` 466 | T7 (footer mark at 16 px) | M | Q4 |

Order: 01, 02, 03, 09 (the trap) first; then 04-08 and 10 (navigation, one commit per surface);
then 11-13 (states); then 14-17; then 18-21; 22-23 wait on the owner. Every step is a static
asset or render change: no pipeline, no data key, no priced number moves.

#### 5.7.4. Tests

| ID | File | Pins |
|---|---|---|
| T1 | `test_pixel_icons.py` | sprite bytes at most 40,960; parses with ElementTree; no XML comments; every `<symbol>` has `viewBox="0 0 16 16"`, `fill="currentColor"`, `shape-rendering="crispEdges"`; zero matches of `#[0-9a-fA-F]{3,8}\b` outside `href="#i-"`; no `gradient`, `rx`, `<circle`, `opacity`, `stroke`; path coordinates are integers inside [2,14] (the 12 px crop loses nothing); at most two paths, the second styled exactly `fill:var(--ico-accent,currentColor)`; regenerating from `tools/pixel_icons.py` is byte-identical |
| T2 | `test_pixel_icon_coverage.py` | every `nav_leaves()` key, every PROSPX `data-section`, the four footer routes and every `_collect_events` type have a symbol; `_nav("ledger")` emits one 12 px icon per dropdown leaf and none in the top-bar leaves; the unicode `sidebar_icons` map is gone |
| T3 | `test_pixel_icon_sizes.py` | every `.ico` width/height emitted by build_site helpers and in site.css / prospx `<style>` is 12, 16, 24 or 32; no `em` sizing on `.ico`; 12 and 24 use `viewBox="2 2 12 12"`; no monogram call below 40 px |
| T4 | `test_no_hardcoded_colors.py` + `test_design_tokens.py` (existing) | PROSPX `<style>` hex budget unchanged; `.ico`, `.px-state`, key-strip rules use tokens only |
| T5 | `test_state_component.py` | each site in 2.2 routes through `EephusState`; each keeps its original message string (grep before and after); failed kinds keep `role=alert` and Retry where it existed |
| T6 | `test_reduced_motion_px.py` | every `@keyframes px-*` in site.css has a `prefers-reduced-motion` rule setting `animation:none` on its selector; `animation-duration: 2.4s` is gone from site.css; no `requestAnimationFrame` in the state code |
| T7 | `tools/px_sweep.py` + `test_px_sweep.py` (marked `browser`, skipped by default) | Playwright, headless Chromium: `/`, `/prospx/`, `/ledger/`, `/management/`, `/betting/`, `/404.html` at 1280 and 390, light and dark: no horizontal scroll; every `svg.ico` box integer and in {12,16,24,32}; each icon paints at least 2 colours and is not pure black on dark; reduced motion: 4 frames over 1.3 s identical and 0 running animations excluding the starfield canvas and the WIRE marquee (owner exemptions); `.bt-game-probs` DOM unchanged (the Dugout fence) |

The prototype sweep already passes the T7 checks on the three prototype pages: no horizontal scroll
in 12 of 12 captures, icon sizes only 12/16/32, reduce frames identical, 0 running animations.

#### 5.7.5. What NOT to build

| Idea | Source | Why not |
|---|---|---|
| Icons on the one-line top-bar leaves | A, B, C mocks | redesigns the nav chrome the README says to extend; 7 leaves + 2 groups + 4 controls already fill 1280 |
| Typewriter cursor, hover flicker, foil sweep, flip-on-mount | A, C, B | new motion in menus; "nothing else loops"; C's flick is 1.09:1 |
| Ballpark lamp-mask masthead, 48 px plates, scoreboard as an anchor | C | a third anchor, dark-first, competes with the starfield; 48 px is taller than the h1 and byline |
| Six state scenes (on-deck, dugout, grounds crew, park at night) | C | dilutes the filter / pipeline / failed signal; four kinds |
| Card blanks around every icon, per-row FV rarity badges, tier names on a key, pack-tear loader, a gold "legendary" stone | B | collectible framing (owner removed Card Market); 24 px plates set 32 px rows; 2.13:1 gold corner |
| Ramp colours as a tier legend, ramp as 4-sided rings, new hex (`--chrome-hi`, `--chrome-lo`, `--tier-*`) | B | README: the ramp is an accent stripe; the palette is fixed |
| Any betting picture: C's 100-lamp block replacing `.bt-game-probs`, A's model-minus-market squares | C, A | a picture beside prices reads as an edge the Model Watch program does not call; A's rounding drew 4 points for 3.3 |
| C's "Fair total 8.79 = 4.14 + 4.65 · Park 1.04" receipt line | C | good, but text, and it sits in the priced card: route it to the betting backlog under the Dugout fence, not this program |
| Dot-matrix spray field, dot-matrix strike zone | C, brief | rule 6: the removed heatmap; ordered dither implies location precision the feed lacks |
| Pixel fan chart | B | coarser than the served quantile fan |
| Per-cell ruler meters | B | key only; revisit only if the key earns it |
| A second, hand-drawn 12-grid set | C weak point | the 12 px crop of the same drawing does the job with nothing to keep in sync |
| Pixelated team logos, headshots, third-party marks; any pixel wordmark or monogram; the ball as an icon | preferences 1, 7 | recognition beats texture; one mark per surface |
| Health-tag pictograms | A option | the rotated-square dots already work; not by default |

#### 5.7.6. Owner questions (four, one batch): ANSWERED 2026-09-24

**Answers (recorded in DECISIONS_FOR_OWNER.md).** Q1 "all", clarified as **each style in its
place**: Scorebook ink (the merged drawing below, which is A's system in 2 px stems) in menus,
rail, PROSPX tabs, mastheads and wire; **Ballpark scoreboard (C's lamp grid) for the loader, all
four state kinds, the 404 and the V1 tied-game line score**; **Card foil (B) only on PROSPX player
cards and the FV key** (one rarity sprite per player card keyed to the audited FV thresholds, the
refractor edge shimmering in dark only and still under reduced motion; B's per-row board badges,
tier names, card blanks around menu icons and pack-tear loader stay killed). Q2 **swap the three
control glyphs** (PX-22 ships). Q3 **trade in panel ink**. Q4 **hint favicon and footer** (PX-23
ships). Consequences for the inventory: PX-11/12/13 draw the four state kinds and the 404 in C's
lamp idiom (C's scenes, capped at the four kinds); PX-19 draws the FV key in B's card treatment;
a new PX-24 adds the B rarity sprite to the PROSPX player card header (`prospx/index.html`
detail render, next to the existing `.card-rarity-*` border), with T4 extended to cover it.

The questions as asked:

**Q1. Which drawing style ships?** The same three icons (Club Ledger, In-Game Management, PROSPX) in
each candidate, one `#` per lit pixel, accent pixels shown as `#`:

```
Merged (recommended): 12 core, 2 px stems
############   ##........   ##########
###.......##   ##########   ##......##
###.####..##   #########.   ##..##..##
###.......##   ########..   ##.####.##
###.#####.##   #########.   ##..##..##
###.......##   ##########   ##.####.##
###.###...##   ##........   ##.####.##
###.......##   ##........   ##......##
###.#####.##   ##........   ##.####.##
###.......##   ##........   ##......##
###.#####.##   ####......   ##.##...##
############   ####......   ##########

A Scorebook: 12 core, 1 px outlines
############   ...####...   ########
#..#.......#   ###....###   #......#
#..#..####.#   #..####..#   #.####.#
#..#.......#   #........#   #.#..#.#
#..#...###.#   #.#.####.#   #.#..#.#
#..#.......#   #........#   #.####.#
#..#.#####.#   #.#.####.#   #......#
#..#.......#   #........#   #.####.#
#..#.#####.#   #.#.####.#   #......#
#..#.......#   #........#   #.###..#
#..#.#####.#   #.#.###..#   #......#
############   ##########   ########

C Ballpark: 16 grid, 2 px silhouettes, no 12 px size
############   ..##..........   ############
##.........#   ..############   #..........#
##.####.##.#   ..###########.   #.########.#
##.........#   ..##########..   #.#......#.#
##.####.##.#   ..###########.   #.#..##..#.#
##.........#   ..############   #.#.####.#.#
##.####.##.#   ..##..........   #.#.####.#.#
##.........#   ..##..........   #.########.#
##.####.##.#   ..##..........   #.########.#
##.........#   ..##..........   #..........#
##.....###.#   ..##..........   #.########.#
##.........#   ..##..........   #..........#
##.....###.#   .####.........   #.#####....#
############   ######........   ############

B Card foil: 16 grid, drawn inside a 24 px card blank
############   ...######...   .###......###.
###........#   ############   .#.#......#.#.
###.######.#   #..######..#   ##.##....##.##
###........#   #..........#   #...#....#...#
###.######.#   #.#.######.#   #...######...#
###........#   #..........#   #...#.##.#...#
###.######.#   #.#.######.#   #...######...#
###........#   #..........#   #...#....#...#
###.######.#   #.#.######.#   #...#....#...#
###........#   #..........#   #####....#####
###.####...#   #..........#   #####....#####
###........#   #.#.######.#   #####....#####
############   #.#.####...#   #####....#####
               #..........#
               ############
```

- **Merged (recommended):** ships everything in this section. Icons match the Bold labels, and the
  12 px menu size comes from the same drawing.
- **A as built:** lighter 1 px icons, and Ledger, Management, News and Models stay near-identical
  boxes. Everything else in this plan is unchanged.
- **C as built:** heavy 16 px icons in 12.5 px rows, with no 12 px crop, so the menus grow 4 px
  per row. C's three-diamond clash (Fantasy, Park Factors, Diamond Pass) and ⇅ reuse come back.
- **B:** card blanks around every icon, 32 px menu rows, and the collectible framing listed in
  Part 5. Not recommended.

**Q2. The nav controls (⌘K, ★, ☾/☀).** ⌘ and ☾ are outside the PixelMplus12 subset and fall back to
a system face.
- **(a) Keep them as they are (recommended default):** the top bar changes in no way.
- **(b) Swap only the three control glyphs for `i-search`, `i-watchlist`, `i-theme-dark` and
  `i-theme-light`:** same buttons, same boxes, same aria-labels and same ramp hairline. This retires
  the system-font fallback (PX-22).
- **(c) Do (b), and also put icons on every top-bar leaf:** this widens a bar already full at 1280.
  Not recommended.

**Q3. Trade in gold on the dark wire panel** (`site.css:1102` ticker `.glyph`, `:1105` ticker
`.trade`, `:1226` feed `.trade`). This already breaks "gold on dark = elite FV only", and the new
pictogram would inherit it.
- **(a) Trade in the panel's own ink (`#e6fbef`), with the ⇄ shape carrying the type
  (recommended):** the gold on the panel goes away entirely, and the prototype shows this.
- **(b) Keep gold:** the rule break is written into the README as a named exception.
- **(c) Violet:** this clashes with signing (`#b47cff`).
- **(d) Cyan:** this clashes with debut (`#4ee0ff`).

**Q4. The 16 px ball.** The favicon-16 and the 18 px footer ball blur to an "O". Any fix touches a
mark, so it needs your decision.
- **(a) Leave both as they are:** no change.
- **(b) Hand-hint the SAME clean ball (cream face, navy rim, two ramp seams) at 16 and 32 px for
  the favicon only:** this replaces `favicon-32.png` and `favicon.ico`.
- **(c) Do (b), and also render the footer mark at 16 px (not 18) from the hinted ball
  (recommended):** this changes `_footer()` 466 and adds T7's footer check (PX-23).
- **(d) Drop the footer ball and keep the text line only:** one mark fewer.

---

## Part 6. Waves, dependencies, and the definition of done

One writer at a time throughout (Part 0.2). Read-only lanes may run beside a writer. Every
wave ends with `python tools/run_suite.py --out suite.json` from `prospect-tracker/`, the
copy checks, and a committed `suite.json`. Execution log: `_finalpass_2026-09-24/EXECUTION.md`.

| Wave | Window | What | Gate / dependency |
|---|---|---|---|
| **W0 ops** | now | W0-OPS-1 lineup capture: DONE 2026-09-24 (Windows task `EephusLineupCapture`, owner-registered; first capture 16:43Z); add the cron line to `deploy/betting-crontab.example`; record the 09-18 to 09-23 gap in 5j. Confirm `ewar.json` `live_built_at` advances on the next nightly | none |
| **W0 team logos** | DONE 2026-09-24 | shared picker on 21 team selects in 10 modules: `2ea0f07e`, `d7e60bb7`, `cf0b26bd`, keyboard review fixes `780a1984` | rendered review of every picker page at 1280/390 x light/dark was lost to the usage limit: re-run it read-only in W1 |
| **W0 P0** | 2026-09-24 onward | the 25 verified P0 defects (Part 4 rows marked P0), in 14 groups: `93b80921` (M07-02 PAL FV/eFV), `8100ce49` (M12-03 Diamond frame) landed; 12 groups run as sequential fixers (`_finalpass_2026-09-24/w0p0/<group>/FIX_REPORT.txt`) | each fixer reproduces on the served path first; owner questions batched into Part 7 |
| **W1 P1** | after W0 | the verified P1 rows of Part 4 (defects first, then upgrades judged CONFIRMED), grouped by file so hunks cannot collide, sequential writers; the lost rendered team-picker review | none of them may touch a fitted number (those are W4) |
| **W2 pixel system** | after W1 or interleaved by file | Part 5.7 PX-01 to PX-24 in its own order (01, 02, 03, 09 first), with the owner's answers: Scorebook ink icons in menus/rail/tabs/mastheads, Ballpark lamp idiom for the loader, four states, 404 and V1, Card foil only on the PROSPX player card and FV key; PX-22 and PX-23 ship | touches build_site.py, site.css, prospx/index.html and eephus-*.js: never concurrent with another writer on those files |
| **W3 cross-cutting** | after W1 | Part 5.1 to 5.6 items (math/econ repairs, wiring, data-source ingests that are DISPLAY-only, UX parity, copy and claims, hygiene) | a data source feeding a fitted model needs its own registered gate, never a quiet feature |
| **W4 epoch** | from the ~2026-10-05 freeze | the fWAR label epoch under `FWAR_LABEL_EPOCH_GATE.md` (runbook A to Z, step M not before 2026-10-05), and every item in Parts 3 and 4 marked GATE that needs the new label | the betting and projections clocks of Part 2.3 run beside it untouched |
| **W5 port Phase 0** | after the epoch's step Z | `docs/port/PORT_SPEC.md` Phase 0 on the old stack: frozen-number equivalence harness, artifact manifest with hashes, vintage stamps, as-of accessor; the time-rot tests fixed before 2026-12-02 | owner reopens the port (deferred 2026-09-18) |

**Definition of done** is Part 0.4.

---

## Part 7. Owner decisions

Asked through AskUserQuestion, four per call, most outward-facing first, default first.
Answers are recorded in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md` the moment they land.

**Answered 2026-09-24:** the pixel system (PX-Q1 to PX-Q4, Part 5.7.6); the lineup-capture
task registration.

**Q-0 (this plan).** Sequencing: final pass (W0 to W3) -> fWAR label epoch (W4) -> port
Phase 0 (W5). Default: as written. Alternative: port first on pre-epoch numbers (not
recommended: every fitted number moves days later, so "no errors" becomes unverifiable).

**Still open from 2026-09-11** (ask when an executing item reaches them): O5 displayed WAR
at the flip; O7 label-definition arms on the epoch; O10 model-class re-adjudication; O11
step M sequencing (partly fixed: not before 2026-10-05); O19/O20 5j Leg M form and
backfill; O23 the 7h re-read (registered on its default).

**Raised by the census lanes:** listed under each lane in Part 4 ("Owner questions raised
by this lane"), each with its default. The executor takes the default for a reversible,
display-only item and batches the rest. The most outward-facing, to ask first:
1. M01: which pool defines the canonical PROSPX board rank (graded plus provisional, baked
   server-side, default) vs graded only.
2. M01: suppress the consensus-basis P(bust) and risk-adjusted value on eFV-led cards now
   (default), label them, or wait for the O6 two-chip taxonomy.
3. M01: third-party scouting writeups reprinted in full on every card: keep through the
   port, cut to excerpt plus link, or link only (a licensing question for the port;
   default: no change until the owner decides).
4. M01: display-only ingest of ProspectTilt PitchIQ and Prospect Savant (source registry
   legal_risk "ambiguous"; default: neither until approved).

**Raised by the W0 fixers (every default below is SHIPPED and reversible; ask these in
batches of four when the owner is back, most outward-facing first).** G06: the PAL card grade
form, default A. G09: the Diamond tiles frame, default (a). Verbatim from the fixer reports
(`_finalpass_2026-09-24/EXECUTION.md` carries the context for each):

- OWNER-Q Per-year chart: (a) DEFAULT shipped: no eFV line and no win count, public boards only; (b) draw eFV vs consensus only from the existing per-year vintage-matched block, no win count, and 2017 has 39 rows, below the 40-row floor; (c) pre-register a per-year vintage-matched block with a floor for each cohort and draw every grader, which needs a source_backtest change and a regen.
- OWNER-Q Findings strip ranking card: (a) DEFAULT shipped: dropped, because the hero already shows the verdict ranking; (b) keep it, labelled "all-vintages frame, tilted toward consensus", with wording derived from head_to_head_by_frame.all_vintages (eFV +0.044 vs floor 0.035, resolved), which the gate's stop clause arguably forbids as an alternative headline.
- OWNER-Q 1: the glossary says "star bucket" where the cards say "Elite". (a) DEFAULT: leave it. (b) Add "(labelled Elite on the cards)" and rebuild 26 pages. (c) Fold it into the O6/O13 bust-taxonomy decision.
- OWNER-Q 2: in Consensus mode, "risk-adj" is the plain simulated mean, because risk_lambda is 0 on all 4,679 rows. For Made that is $69M against a $99.8M headline. (a) DEFAULT: leave it unchanged (M01-04 covers the gap). (b) Relabel it "sim mean". (c) Drop it from the card.
- OWNER-Q (optional, default applied): add the leave-one-out mean-baseline MAE as a column in the two "How accurate is this" tables? Default: not added, because the trust sentence already prints it.
- OWNER-Q: In what order should the unranked BA prospects appear? (a) default, implemented: HS list first, then College list, each in BA's order, no number. (b) College list first, then HS. (c) Hide them behind the Pool (HS/COL) filter by default, so only one BA list shows at a time. A merged HS+College order is not offered; the BA ingest contract says it needs a separate gated model first.
- OWNER-Q: How should the Team View sort? Options: (a) remaining arbitration $ [default, shipped; WSN #5, SEA #2]; (b) the old combined total including pre-arb minimums [WSN #2]; (c) 2027 arbitration $ [SEA #1].
- OWNER-Q: The Ledger and Franchise copy still says "upper bound", and tests pin that wording. Options: (a) keep it [default]; (b) say instead that every player is assumed tendered and a non-tender lowers the figure.
- OWNER-Q: A first arb trip with no salary on file now raises off the prior season's league minimum. Options: (a) keep [default, matches the 145 rungs that follow a pre-arb season]; (b) leave the prior missing, about 14% lower on the 57 direct class-1 rungs.
- OWNER-Q: The band's low end can sit below the league minimum ($608K on a $780K rung). This predates the fix and was not changed. Options: (a) leave it [default; the band is published as uncalibrated]; (b) floor it at the league minimum.
- OWNER-Q Q1: Every graduate's "Debuted value" (Ledger and PROSPX) is priced on 7 years of control, because `roster_status.service_years_decimal` is never written. Ohtani reads $523.6M and Betts $47.9M. Options:
- OWNER-Q Q2: Pool used leaves out round 11+ bonuses above $150,000, which the CBA charges to the pool. Options:
- OWNER-Q1: When a trade party has no trade value: A) no verdict on that card (shipped; 4 of 109 default cards, 49 of 271 overall), B) score only the priced parties with a footnote, C) price unpriced parties at $0.
- OWNER-Q2: Time basis: A) "value today" on both sides, stamped on the card (shipped), B) add a leg for value realized at the receiving club after the trade (a separate large item that needs per-team fWAR), C) no verdict on trades from before this season.
- OWNER-Q3: Payload: A) the Transactions tab fetches the existing 4.8 MB trade_values.json (shipped), B) add a slim sidecar output to tools/export_trade_values.py.
- OWNER-Q4: Farm Surplus details: A) keep the per-player engine value, which matches the prospect list, and note the basis difference (shipped), B) switch to eFV surplus_mm so the section total matches the tiles (65 of 157 STL rows would then differ from the list).
- OWNER-Q: Should a move to a complex or DSL club end an IL stint? (a) Default, shipped: yes, like any other non-rehab move (17 rows closed; 2 late-season moves, elaineiker_coronado and jecsua_liborius, have no later games to confirm it). (b) No: those 17 rows go back on the IL until an activation, release or game for the placing club. (c) Only when a later game at the complex club exists; the 2 late-season moves stay on the IL.
- OWNER-Q: serve_vector_tripwire still compares served_recentered, which scores the retired 2026-06-12 vector. Options: (1, default, done) keep it, labelled vector_serving false with a note; (2) re-run proj_backtest so served_recentered collapses onto recentered (this refits the intercepts and rewrites the retro block); (3) retire the tripwire while no vector serves.
- OWNER-Q (MH-01): What should the steal realized column measure? (a, shipped default) realized_delta, DV + ER on the house win expectancy table; (b) the feed chain-break gap, which also picks up other in-PA events (+52.6 vs +9.9); (c) drop the realized steal column and show DV/ER only (removes 225 board cells and 30 franchise leaves).
- OWNER-Q (MH-01): When should the /betting/ Dugout steal context refresh? (a, default) the nightly; (b) run betting_export by hand now, which hits the odds feed and the public record chain.
- OWNER-Q (MH-02): HOF_BAKEOFF_GATE G-1/G-9 frozen figures (17 of 286, base rate 286 of 3,620): (a, default) keep them frozen and read with the G-8 addendum; (b) cut a dated v2 of the gate with 21 / 290 in the body.
- OWNER-Q: What level should the pool floors be? Default shipped: 100 projected full-season PA and 30 IP, which gives 1,220 players and 582KB, inside the 600KB budget. Option b: the finding's literal 20 PA / 8 IP, which gives 1,487 players and 697KB and fails the budget test. Option c: 20 / 8 and raise the budget to about 720KB.
- OWNER-Q: What should Redraft show in the off-season? Default shipped: the 2027 full-season projection, with streamers, two-start, DFS and props turned off. Option b: hide the three ROS boards until opening day. Option c: freeze the final ROS boards under a "season over" banner.
- OWNER-Q: How should /fa/#view=model get its Gate figures? (a) DEFAULT, implemented: keep the copy inside fa_meta.json, with the new test catching any lag and the re-export step printed after a gate run. (b) Have fa.js fetch the two gate files directly: the table can never lag, but the class bands still can, so the test stays. (c) Have fa_backtest rerun fa_export itself after saving a gate: no lag, but a lab run then rewrites five served files and makes cached Spotrac and Savant fetches.

**Raised by writer queue 1 (defaults SHIPPED unless a line says otherwise).**

- OWNER-Q1: The live row is n 806 because of the uncommitted matrix rebuild. Options: (A, done) record what the tree measures now; (B) rerun `tools/efv_scoreboard.py` after the rebuild is committed, which appends a new row; (C) investigate the matrix rebuild as a possible defect first.
- OWNER-Q2: The disagreement measure (eFV closer on 56.5% of 283) could read as a win. Options: (A, done) a collapsed secondary block in neutral colour; (B) drop it from the ledger; (C) show it in the main table.
- OWNER-Q3: Per-source cells have no correction for comparing three sources, and the FanGraphs AUC leg clears its floor (+0.0328, CI +0.0075 to +0.0573). Options: (A, done) show intervals only, with no verdict word; (B) label such cells "clears floor (uncorrected)"; (C) apply a Holm correction across the three sources now.
- OWNER-Q4: `.cache/efv_progress/ledger.jsonl` is the only copy of rows added on the box between commits. Options: (A, recommended, not done) add it to the backup list in `deploy/WEBMASTER.md`; (B) accept losing those rows if the box cache is wiped.
- OWNER-Q: Unit for hitter Luck. (a) default, implemented: wOBA points (xwOBA minus wOBA), the same unit as the pitcher Luck columns. (b) Index points on one unshrunk anchor, keeping a "pts" column. (c) Drop the hitter Luck column and keep only the Luck row on the player card.
- OWNER-Q: The /projections/ xHEM+ tile note "+N vs HEM+" is the gap between a shrunk index and an unshrunk one, labelled as a difference. (a) default, implemented: keep it, now computed on the page from the two numbers (value unchanged). (b) Remove it, since the card's Statcast block already shows Luck (wOBA-xwOBA).
- OWNER-Q: When two players share a slug on the trade board, which one keeps the plain key? (a) DEFAULT, implemented: the prospect-feed row keeps it and the veteran becomes slug__mlbam; nothing visible changes. (b) The projections player keeps it and the prospect row is re-keyed; this breaks key history for about 7 rows. (c) Key every board row by mlbam id; this is a schema change that every consumer must re-join, and it pairs with the storage.py lane.
- OWNER-Q: Should the Spotrac contract club also appear on each projection row? (a) default, as implemented: no per-row field, and the payload gives a count of rows off their contract club (138); (b) add an audit-only field on the rows where it differs (no page reads it); (c) add a "payer" field shown on player cards, which would print the old club after a trade because the new club pays.
- OWNER-Q (X04-06): what should happen to `_pre_epoch_2026-09/` (1.9 GB) and the `prospects.db.bak-*` sets? (a) DEFAULT, as done: leave both in place, ignored. (b) Move both to a dated archive outside the tree with a sha256 manifest, and re-cite the gate doc's `../_pre_epoch_2026-09/` path. (c) Keep the pre-epoch snapshot and delete the older bak-vintage-2026-08-13 and bak-identity-2026-08-19 sets, which frees about 3 GB and loses those restore points.
- OWNER-Q (X04-01): should `data_exclude.txt` also list `xfv_hitter_matrix__E0.json`? (a) DEFAULT: no; the pattern test catches any new label file at the top level of `data/`, and listing the name now would keep rsync from deleting the webroot copy. (b) Add it once one nightly has confirmed the URL returns 404; the withhold count goes 30 -> 31.
- OWNER-Q: X07-02 licensing. (a) default, applied: keep the full third-party report text and say so; (b) serve an N-word excerpt plus a "View on <source>" link and keep full text out of /data/; (c) link only, no report text; (d) drop Baseball America full text only. Baseball America has no "View on" link under any option today.
- OWNER-Q: X07-01 display. (a) default, applied: keep the RIV+ column on /mlbstats/ with the corrected copy; (b) keep it and add a "realized record, not validated against pay" note to the column tooltip; (c) drop the column until the 2027-03-01 market re-read.
- OWNER-Q1: Should the 2021-2022 Savant minors data be fetched into the snapshots? (a, default) No; the answer is recorded and nothing is fetched until a later gate asks for it. (b) Four requests for 2021-2022 into the cache, which the snapshot then stores as frozen 2021 and 2022 files. (c) The same as (b), but first one request to learn which levels those seasons cover.
- OWNER-Q2: The 2026 AAA Statcast snapshot is dated 2026-06-23, because nothing refreshes that season's cache file once it exists. (a, default) Leave it; the file's date says so. (b) Refresh the 2026 files once at season end (2 requests) so the frozen 2026 file holds the full season. (c) Give the current-season cache file an expiry, the way the aStuff+ refresh handles its current season.
- OWNER-Q: F-LV membership window. A (built): the preseason window, January 1 to April 30 of V, the same window the raters are scored on. B: any real-grader read in calendar year V, as the E2 probe did; more rows, but it is no longer preseason-matched. C: preseason grades, but membership from any read in V-1 or V, which keeps busts who fell off the boards.
- OWNER-Q (EV-07): D1 does not reproduce on development vintages. Which way?
- OWNER-Q1: When should vm2 become the headline? A) keep vm1 as the verdict and show vm2 as a "headline candidate" (default, done); B) promote vm2 now; C) keep both, with vm2 as a labelled sensitivity.
- OWNER-Q2: Pin the disagreement receipts too? A) leave them as the labelled secondary (default); B) add a pinned twin beside them later; C) re-pin in place, which moves the served 56.5% share.
- OWNER-Q3: Three 2020 postseason-only debuts (Weathers, McClanahan, Kirilloff) are in vm1 but not vm2. A) drop them from vm2 (default, done); B) pin them to their 2020 preseason read so vm2 keeps all 806 rows.
- OWNER-Q4: vm2's floor is vm1's 0.0303, labelled as carried. A) keep it (default); B) re-measure it on vm2 before promotion.
- OWNER-Q1: H0 trails consensus on the vintage-matched development frame and does not reach non-inferiority to v1. Next step for the v2 selection?
- OWNER-Q2: Where should v1 appear on the development ledger?

**Raised by the eFV v2 program** (`docs/efv-v2/PROGRAM.md` section 6): Q1 what the PROSPX board
leads with while v2 is built (A: eFV v1 re-sorted to the scored ordering, recommended; this is
EV-02 and waits for the answer); Q2 whether a v2 that ties ships (A: yes, for coherence); Q3
whether the list-vintage frame counts as beating the industry (A: co-primary, registered first);
Q4 the prospective reserved cohort (A: joint with Z1c on the 2025 debut cohort). Only Q1 is
needed before November.


## Part 8. The owner's 2026-09-30 asks

Written 2026-09-30 for the executing agent, from ten read-only design lanes run that day against
commit `64bf1bb3` (2026-09-25 20:22 -0400) while the owner's hand-run `run_monthly.py` (started
12:29) rewrote `data/`. The lanes were `pitch_metrics`, `league_team_stats`, `links_efv_display`,
`dvm_difficulty`, `staff_gems`, `intensity_index`, `finance_to_fa_arb`, `wiring_ideas`,
`pixel_branding` and `epoch_calendar`. No lane edited the repo, ran pytest, ran an exporter, fitter
or ingest, took a registered look, read a reserved eFV frame or computed a realized statistic by
consensus-FV cell. Data files were read from committed copies except where a row says "working
tree" (gitignored artifacts with no committed copy).

**State pin, revised after round 1 (2026-09-30 evening).** Since the lanes ran, queue 7 landed VAL_1
as `410cccce` (2026-09-30 17:54, the one $/WAR level), VAL_2 as `36b93e16` (guaranteed contracts
priced to their last season) and VAL_3 as `fc90703d`, `79a637e3`, `27ee25f9` and `4fb990de` (the
surplus-odds gate registered, built behind a flag, read as a FAIL on its primary clause, and the
eFV card note corrected). The ETA FanGraphs-blend look ran at 17:59 and crashed before recording
anything; the owner answered ETA-1, ETA-2, VAL1-Q1 and VAL1-Q2 the same evening
(`DECISIONS_FOR_OWNER.md`, section "ANSWERED 2026-09-30 (AskUserQuestion), VAL_1 landing (410cccce)
and the ETA blend look"), and queue 8's three tasks carry those answers (8.B, 8.C). The first of
them has since run: `6ca2e8f4` (19:17) repaired the one report-only line and `be53132d` (19:22)
recorded the look, reproduced byte for byte: SHIP CANDIDATE for both arms with arm B recommended,
and the section 7 org-multiplier gate recommends REMOVE (the owner's call). HEAD at this revision is
`be53132d`; `eta.ETA_FG_BLEND_ARM` was still None there, and the flip to arm B (ETA-2) is that task's
last step, served only if it lands before 2026-10-04.

**Citations.** Every line number in this part is pinned to a commit: `path@64bf1bb3:N` (the lanes'
base) for every file, and `path@410cccce:N` for the files VAL_1 changed (`ledger_export.py`,
`proj_export.py`, `run_monthly.py`, `fa_backtest.py`, `fa_export.py`, `fa_market.py`,
`value_framework.py`, `assets/fa.js`, `assets/fa_dpw.js` and the rest of its commit), re-cited at
VAL_1 with the mapped line. A continuation `:N` belongs to the file cited just before it in the
same line or table cell. A bare number carries an anchor beside it, "(in fn())", "(at 'string')" or
"(under '## heading')", read at the pinned commit; at any later HEAD the anchor locates the code and
wins over the number. "HEAD" in prose means the pinned commit unless a date says otherwise. The
queue specs follow the same convention (`@64bf1bb3 N`, `@410cccce N`). Two files outside the repository
are cited as they stood on 2026-09-30 (`@2026-09-30`): `DECISIONS_FOR_OWNER.md` in `_audit_2026-09-09/`
and `PROVISIONAL_V2.md` in `_finalpass_2026-09-24/provisional/`, each with its table row or heading
beside the number.

**Evidence bundle.** `<part8>` below means the lane bundle, today at
`C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/part8/`
(the ten lane documents, their probes, prototypes, renders and the generator prototype). Copying it
to `C:/Users/noah/baseball-projects/_finalpass_2026-09-24/part8/` is the orchestrator's first action
(8.C); every queue spec reads the durable copy and falls back to the scratchpad path. The queue file
built from this part is `<part8>/QUEUE_TASKS.json` (84 tasks in four queues: p8_metrics 16, p8_wiring 36, p8_research 22, p8_branding 10), the preamble every Part 8 task
carries is `<part8>/P8_COMMON.txt` (reproduced in 8.A), and the decision file is
`<part8>/OWNER_QUESTIONS.json` (48 questions in 12 batches of four, each with its `needed_by`).
The queues are not run as static chains: the orchestrator inserts their tasks into the one dynamic
single-writer queue (8.C), where each task's `not_before` and `requires` fields decide when it may
run.

**The asks, verbatim, and where each lives.**

| Ask | Words (owner, 2026-09-30) | Item |
|---|---|---|
| 1 | "Use $/war data we already have to project $/war for future years, then use these projections to improve surplus value" | referenced only (VAL_5, designed outside this workflow), P8.11 |
| 2 | "Can we do pixel art animations/designs for our logos and branding as well? I like the way they currently look, I just want to make them even better and more beautiful." | P8.10 |
| 3 | "Can we wire the financial module into the Free Agency / arbitration modules to make them more accurate? Ex. to make team fit projections more accurate based on which teams actually spend money in free agency." | P8.5 |
| 4 | "Think of ideas we can use to wire more modules together in order to improve them both / one of them with data/metrics/models (or combinations) with the other one." | P8.6 |
| 5 | "Make sure eFV is being used as the only displayed FV source across PROSPX, I saw some spots where it was using consensusFV to display FV instead of eFV (specifically within farm system pages and drilled down detail pages for high schools/countries/different PROSPX sections)." | P8.4 |
| 6 | "Weight DvM+ by difficulty of developing FV / different traits in different groups (HS prep prospects vs college prospects vs IFA prospects: what traits are easier / harder to develop?). Additionally, it is probably harder to develop from 60 FV -> 70 FV than it is to develop from 40 FV -> 50 FV, can we check to see if this is true and weight DvM+ accordingly?" | P8.7 |
| 7 | "'Staff Gems' module that uses DvM+ / graduate WAR / associated prospects and cross-references it with a list of player development personnel to identify which staff members in each organization have been developing their position above the mean? Could also extend to Club Tendencies to identify which 1B/3B coaches are best at baserunning, etc.?" | P8.8 |
| 8 | "For the Sports Betting module: an 'intensity index' based on game intensity (playoff games are more intense, divisional matchups are more intense, matchups with key playoff implications in the regular season / matchups between elite teams are more intense, games where both teams are starting their ace pitcher, etc.): see if game intensity impacts games measurably, which players / archetypes tend to shine in these games, what types of teams tend to perform well in the playoffs / high intensity games?" | P8.9 |
| 9 | "Connect the site more, ex. link directly to the White Sox franchise page if you click on 'White Sox' on the lineup charts / elsewhere on the site. Link directly to team franchise pages wherever a team is referenced (or, on PROSPX/in relation to their farm system, their farm system page)." | P8.3 |
| 10, 11, 12 | P/IP; P/PA; PAR ("the league mean of P/IP for starters and relievers (varies for each) and the delta between a pitcher's P/IP and the league mean ... for hitters, the league mean of P/PA and each hitter's delta") | P8.1 |
| 13, 14, 15 | "League Averages" section of MLB Stats with extensive filters, both averaged individual stats and averaged team stats; standalone pages or charts of league averages over time; a "Team Stats" section built from the EM+ family plus sortable club tendencies | P8.2 |
| 16 | "Plug P/IP into the sports betting module to project how many pitches / IP a pitcher will throw in each game; use P/PA for hitters and lineups to tweak this based on the lineup each pitcher faces to calculate expected pitches and expected innings pitched." | P8.1 (the betting candidate) |
| 17 | "Show P/IP and PAR on the starter and reliever sections of MLB Stats; show P/PA on hitter sections." | P8.1 |
| 18 | "Show stat visualizations for each player when clicked on in the MLB Stats module." | P8.2 (the drawer) |
| 19 | "Calculate P/IP, P/PA and PAR relative to each level for prospects, show on prospect pitcher cards, check if any can be used as a driver for eFV." | P8.1 |
| 20 | "Calculate P/IP and P/PA on a team level for team lineups, rotations, bullpens; derive a team-based PAR score (based on team league averages); display these in the lineup / bullpen / starter charts section of MLB Stats." | P8.1 |

Two other items are handled outside this workflow and are only referenced: the PLUS% board
column removal and the 2026 MiLB season for eFV drivers (P8.11). Five later asks of the same day
have their own plans (Baserunning, eBR, a skill WAR and F-SCORE, MLB Scores, League Trends); 8.E
says which plan owns every piece they share with this part.

**Model routing.** The runner gives every writer Opus 5.5 (owner preference 2026-09-30: Opus
wherever possible). Each task keeps a `model` field as an advisory note only: `fable` marks the
eight rules-dense registrations and looks where a slip voids registered work (the starter-workload
section Q10_01, the FA destination gate Q9_02, its lab Q9_04a and its look Q9_04b, the arbitration
section 12 amendment Q9_20, the intensity stage-1 lab and look Q10_07 and Q10_08, the eFV
pitch-rate admission Q10_11). The runner does not
read the field; an Opus writer that executes one of these follows its STOP list literally, first.

### 8.A Rules this part adds to Part 0.2

- **Landing.** Part 2.3's rule stands: a served change lands before 2026-10-04 or after the fWAR
  label epoch's step Z (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9, '## 9. Results').
  Queue 7's landing window closes Sat 2026-10-03 23:59 and will not clear its tiers (8.C), so
  nothing in this part serves before the epoch except, if a window slot frees, three class-1 fixes
  (Q9_01, Q10_03 and Q8_01). The gap from 2026-10-04 to step A takes docs and registrations only,
  with ONE owner-sanctioned exception stated here so the rule and the calendar agree: the epoch's
  own precondition repairs EPOCH_E2 and a late queue-7 B4_IDENTITY_SPLIT must precede step A's
  snapshot, so they land in the gap and name every served number they move; queue 7's
  M15_PROJECTIONS_FREEZE_TRIPWIRE part (3), which edits served disclosures on /projections/ and
  /fa/, moves after step Z (its part (1), the gate document, stays gap-safe). Between step A and
  step Z nothing writes the repo. The Part 8 tasks run after step Z, after queue 7's post-Z tasks,
  queue 3 (pixel) and queue 6 (display), in the order p8_metrics, p8_wiring, p8_research,
  p8_branding, except the head tasks that 8.C pulls forward; the dynamic queue's `requires` fields
  carry every ordering this part relies on.
- **Flags, three classes.** (1) Nothing served moves: a relabel, a link, a copy fix, a rendering fix, or an additive display of a number the site already serves elsewhere (the HoF line on player pages, the PROSPX IL chip on Dynasty rows). It ships as built, but only before 2026-10-04 or after step Z: every task that touches a served file carries a SERVED-CHANGE GUARD that keeps it off the site from 2026-10-04 until the step Z entry exists. (2) A new served number, column, tab,
  page, payload or file ships behind a module flag defaulting off, and while the flag is off the
  exporter writes only `.cache/.../preview` (a new `data/` file ships to the webroot, census
  X03-15): `SERVE_PITCH_RATES`, `MLBSTATS_LEAGUE_TEAMS_LIVE`, `MLBSTATS_DRAWER_LIVE`,
  `LEDGER_FA_SPEND_PROFILE`, `ARB_CLUB_PROCESS_CHIPS`, `MLB_EVENTS_LIVE`, `FA_DESTINATION_SERVE`,
  `SHOW_INTENSITY_CHIP`, `FA_MODEL_VIEW_LIVE`, `PIXEL_BRAND`, and later `STAFF_GEMS_LIVE` and
  `TRADE_PARTNER_SCREEN_LIVE`. (3) An EXISTING served number that moves (a changed printed digit counts: the eFV rounding fixes ride `EFV_DISPLAY_SWAPS`) ships behind a flag and flips after step Z AND after its own gate or owner answer, with
  the blast radius in the flip commit: `TEAM_OUTLOOK_WINTER_FRAME`, `EFV_DISPLAY_SWAPS` (one
  constant, `storage.EFV_DISPLAY_SWAPS`, read by the PROSPX payload and imported by `proj_export`),
  `DRAFT_CURRENT_FV_EFV`, `DVM_DIFFICULTY_ARM`, and the owner-only `SERVE_WORKLOAD_PROPS`, which may
  not flip before 5l's `mgmt_policy_gate` block AND the starter-workload stage-2 look both exist
  (a stage-1 pass licenses nothing served; the only earlier form is the registered fence, P8.1).
  Every flip is ONE commit carrying the flag, the new `data/` files, the registry rows and the
  glossary entries together, naming every key, file and row count it adds (8.D rows 14 and 15).
- **Registration first, and one of them is dated.** Every predictive number here has a gate
  document committed alone, with an empty results section, before any code, flag, column or
  number exists, and every registration task first checks whether its section or document already
  exists at HEAD (if it does, NOT A DEFECT, stop). The starter-workload section (P8.1, ask 16) is
  inserted in the dynamic queue right after queue 8's LEDGER_TRIM_PREVIEW_10 and must commit
  before 2026-10-05, the 5c-B and 5c-C look day; its STOP S8 is keyed to what is recorded, not to a
  date: if a 5c-B, 5c-C or 5d result is recorded in `docs/diamond-betting.md` when it commits, its
  text discloses that result first (the posted-lineup precedent voids a registration only once
  the neighbouring look is recorded, `docs/diamond-betting.md@64bf1bb3:5268-5272` (under '## 5j. Posted lineups')). The game-intensity
  section (P8.9) commits before any intensity code and before the 2026 World Series ends, so the
  postseason stays a sample nobody has related to it. Neither may commit between step A and step Z.
- **Section letters and schema numbers by commit order** (8.D row 3). A betting registration takes
  the next free letter after the last `## 5x.` heading when it commits (the workload section is
  expected to be 5m, intensity next; queue 7's umpire family may take one first); a Part 8 dark
  schema takes the next number after the last landed BUILDER in commit order and does NOT wait for
  5j's or 5l's builder: `docs/diamond-betting.md` lets 5j's number move by a dated correction
  (`docs/diamond-betting.md@64bf1bb3:5501-5506` (under '## 5j. Posted lineups')) and makes only 5l wait for 5j (`:6789-6791` (under '### The clock, and the sentence that binds it')), so no
  amendment is needed. Specs and tests name sections by title and columns by name.
- **Descriptive means descriptive.** No correlation, fit, slope, trend line or verdict word is
  computed or printed between a descriptive number and wins, runs, prices or outcomes. A
  descriptive row gets verdict `provisional`, `eval_artifact` null and a `provisional_kind` of
  `measurement_only`, or `inherits_parent_gate` where it is a weighted mean of a gated parent
  (`model_registry.py@64bf1bb3:47-54` (at 'shipped_partial_measurement')); its `baseline` or `metric` field must say "descriptive" or
  "inherits" and name the parent, because `test_model_registry.py@64bf1bb3:128-168` (in test_a_provisional_row_without_an_artifact_says_why()) fails a provisional row
  that carries no artifact and no such word. Words that imply a forecast (luck, due, regress,
  trending, will, clutch as a skill, sleeper) stay out of this part's copy.
- **Looks and the calendar.** Every one-look task carries a crash protocol (a full dry run of the
  reporting path on fixtures with nulls; the look's stdout teed to the output directory before
  anything else runs; on any exception after scoring, STOP without rerunning and write the owner
  question), and every task that runs an exporter, a lab, a fetch for a registered frame or a
  look stops on 2026-10-23, 11-06, 11-13 and 11-20, the eFV reserved-read day and any other
  registered look's date (8.B). The ETA look's record, a recorded verdict or a VOID, counts as
  "the ETA look record exists" everywhere in this part; a task that needs arm B's verdict treats
  VOID as "champion kept".
- **What binds every item.** `docs/PROSPECT_ANCHOR_GATE.md` (no realized MLB statistic by FV cell
  before its one look, the later of 2026-11-20 and step Z + 14 days); the eFV reserved frames R-LV
  (list vintages 2020 and 2021) and R-VM (the 2025+ debut cohorts), never scored, and one rule for
  Part 8's research frames, set by the owner's Q-DVM-1 answer and applied to DvM+ and Staff Gems
  alike (default: a table of grade movement reads 2020-2021 list endpoints only after the R-LV look
  record exists, 8.D row 6); no chart or table pairs eFV at debut with an outcome axis for a debut
  cohort from `efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR` on until that cohort's R-VM look is
  recorded; every dated look in `docs/*GATE*.md` and
  `docs/diamond-betting.md` is one look, and looking early disqualifies; the 5l close-variant rule
  (`docs/diamond-betting.md@64bf1bb3:6849-6854` (under '### The clock, and the sentence that binds it'): a per-pitcher hook rate or club bullpen usage related to an
  outcome before 2027-07-01 voids 5l); no vs-hand team or league group before the 5e and 5i-B looks;
  grades round up, eFV and plus stats nearest; no em-dash and the `tools/copy_lint.py` ban list in
  every string; one writer at a time; never pytest while a pipeline writes;
  `restamp_hand_authored_pages()` after any `site.css` or shared runtime edit;
  `tools/export_trade_values.py` after any `proj_export` run; a JS comment naming a `.json` file
  lands in SITE_MAP.md.
- **Findings for other owners.** Each lane found defects in modules it does not own. They are
  listed once in 8.F and handed to their owners; none is fixed inside a Part 8 task unless the row
  says so.

### P8_COMMON, the preamble every Part 8 task carries

The orchestrator copies `<part8>/P8_COMMON.txt` to the dynamic queue's `preambles/P8.txt`; `qctl`
prepends it to every task whose `preamble` is `P8`. It replaces the eFV program's EV preamble for
Part 8 (that block said development reads use the current eWAR v2 label and that no served grade
changes, both wrong here). Its text, verbatim:

```text
PART 8 TASK RULES (the owner's 2026-09-30 asks). The plan is Part 8 'The owner's 2026-09-30 asks' of prospect-tracker/docs/master-plan-2026-09-24-final-pass.md, also PART8_ADDENDUM.md in the Part 8 bundle C:/Users/noah/baseball-projects/_finalpass_2026-09-24/part8/ (fallback C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/part8/); every spec names a section by number AND title (for example 8.D 'Conflicts between lanes, resolved'), so either copy can be searched.
- WHERE THINGS ARE: owner answers and recorded defaults in C:/Users/noah/baseball-projects/_audit_2026-09-09/DECISIONS_FOR_OWNER.md; the fWAR label epoch in docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md (its step Z entry is in part 9, '## 9. Results'); the lane designs in the Part 8 bundle.
- CITATIONS: a line number is pinned to the commit written beside it: @64bf1bb3 (the lanes' base) or @410cccce (VAL_1, for the files VAL_1 changed). Read the cited lines with git show <commit>:./<path>, then find the same code at HEAD by the anchor beside the number (in fn(), at 'string', under '## heading'). If the anchor and the number disagree at HEAD, the anchor wins; never edit a line because only its number matched.
- FIRST CHECKS: tasklist (no run_monthly.py, nightly job, other writer or pytest session running); git status; the spec's preconditions in order. A registration first checks whether the section or document it registers already exists at HEAD and, if it does, reports NOT A DEFECT and stops.
- CLOCK: served changes land only before 2026-10-04 or after the step Z entry; between step A and step Z nothing writes the repository (step A has started when ../_pre_epoch_fwar_2026-10/ exists and part 9 has no step Z entry). Class 1 (nothing served moves) ships as built outside that gap. Class 2 (a new served number, column, tab, page, payload or file) ships behind a module flag that defaults off, and while it is off the exporter writes only under .cache/.../preview. Class 3 (an existing served number moves; a changed printed digit counts) ships behind a flag flipped after step Z and after its own gate or owner answer. A flip is ONE commit carrying the flag, the new data/ files, the registry rows and the glossary entries together, naming every new key, file and row count.
- CALENDAR: a task that runs an exporter, a lab, a fetch for a registered frame or a look stops if today is 2026-10-23, 2026-11-06, 2026-11-13 or 2026-11-20, the eFV reserved-read day, or any other registered look's date (docs/*GATE*.md, docs/diamond-betting.md, plan Part 8 section 8.B 'The clock: the fWAR epoch calendar').
- LOOKS: a registered look runs once. Before it, dry-run the whole reporting path on fixtures with nulls; tee the look's stdout and stderr to your output directory before anything else runs; on any exception after scoring began, STOP without rerunning and write OWNER_QUESTION.md.
- FRAMES: never score the reserved eFV frames R-LV (list vintages 2020 and 2021) or R-VM (the 2025+ debut cohorts); never compute a realized MLB statistic, or a bust, debut or graduation rate, by consensus-FV cell before docs/PROSPECT_ANCHOR_GATE.md's one look; a development read uses the frozen fWAR label once the epoch has frozen it, never the retiring eWAR v2 label, unless the spec says otherwise; no dark betting column is related to an outcome or a price before its own look (docs/diamond-betting.md).
- THE ETA LOOK: Queue 8's ETA_LOOK_REPAIR_RERUN leaves either a recorded verdict or a VOID in docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md section 8 (it recorded SHIP CANDIDATE, arm B recommended, at be53132d on 2026-09-30); either one counts as 'the ETA look record exists', and a task that needs arm B's verdict treats a VOID as 'champion kept'.
- COPY: no em-dash or en-dash anywhere; none of tools/copy_lint.py's banned words; no forecast word (luck, due, regress, trending, will, clutch as a skill, sleeper) on a descriptive number; eFV and plus stats round to nearest, FV and tool grades round up.
- HOUSE RULES: one writer at a time; never pytest while a pipeline writes; run only the relevant test files with -p no:cacheprovider; restamp_hand_authored_pages() after a site.css or shared runtime edit; tools/export_trade_values.py after any proj_export run; data/glossary.json and data/model_registry.json only through an idempotent script that keeps the file's line endings; stage only your own paths; never push.
- STOP: commit nothing further, write REMAINING.md in your output directory ending with one line 'BLOCKER: date YYYY-MM-DD', 'BLOCKER: task <id>', 'BLOCKER: answer <question id>' or 'BLOCKER: other <text>', and end; the orchestrator records it and re-arms the task. Take an owner question's default only where the spec says so, and record it in DECISIONS_FOR_OWNER.md.
- WRITER: every task runs on an Opus 5.5 writer; the task's model field is advisory. Follow a look's or a registration's STOP list literally, before anything else.
```

### 8.B The clock: the fWAR epoch calendar (Part 8's clock section)

From lane `epoch_calendar` (`<part8>/epoch_calendar.md`, 2026-09-30 12:53 EDT), revised after round 1
against the state of 2026-09-30 evening. **State pin.** HEAD is `be53132d` (2026-09-30 19:22): VAL_1
landed as `410cccce` (17:54), VAL_2 as `36b93e16` and VAL_3 as `fc90703d` to `4fb990de` (its gate read
FAILS on the primary clause, so the surplus-odds flag stays off), and queue 8's ETA_LOOK_REPAIR_RERUN
committed the repair `6ca2e8f4` and the recorded look `be53132d` (below). `docs/master-plan-2026-09-24-final-pass.md`
is still untracked and ends at Part 7; about 360 `data/` files and the generated pages carry pipeline
churn. The one registered ETA look (`ETA_FG_BLEND_GATE.md`) ran at 17:59, scored C1 to C6 and then
crashed at `tools/eta_fg_blend_gate.py@64bf1bb3:455` (in run_blend_gate()) in a report-only table before recording anything; the
rerun at 19:18 reproduced the nine clause lines byte for byte and is recorded (SHIP CANDIDATE, arm B
recommended; the section 7 org multipliers: REMOVE recommended, the owner's call). The owner
answered ETA-1 (repair that one line, rerun once, byte for byte or VOID), ETA-2 (flip to arm B once
recorded: served if landed before 10-04, else behind `eta.ETA_FG_BLEND_ARM` until step Z), VAL1-Q1
(trim the Ledger payload, restore 10 preview rows) and VAL1-Q2 (one knots-only calibration refit at
$17.14M once `backtest.fit_calibration_knots` exists) in `DECISIONS_FOR_OWNER.md`, section "ANSWERED
2026-09-30 (AskUserQuestion), VAL_1 landing (410cccce) and the ETA blend look". Queue 8's three tasks
carry those answers: ETA_LOOK_REPAIR_RERUN, LEDGER_TRIM_PREVIEW_10 and CAL_KNOTS_REFIT_17M. Step A's
first check (`WAR_BASIS_RUNBOOK.md@64bf1bb3:54` (under '### A. Preconditions and the pre-epoch snapshot'), a clean code tree apart from `data/`) fails until the plan
document and the churn are committed or explained (8.C action 0).

**Epoch preconditions (part 3, `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:135-161` (under '## 3. Preconditions E1 to E8, with today's status'), re-checked read-only):**

| # | Status 2026-09-30 | Evidence | Blocks |
|---|---|---|---|
| E1 | O7 and O5 OPEN (batch 1 asks O7 as EPOCH-Q3, batch 2 asks O5 as EPOCH-Q4); O10 answered in effect | `DECISIONS_FOR_OWNER.md@2026-09-30:227` (under 'ANSWERED 2026-09-17 (evening), the decision queue, 16 in four batches'), `:252` (under 'OWNER INSTRUCTION 2026-09-24 (chat): eFV must beat consensus and the i') | O7 blocks step F (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:154` (under '## 3. Preconditions E1 to E8, with today's status')) |
| E2 | NOT MET | no identity tripwire test at HEAD; the 13 label players E2 names are unrepaired | C and after (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:155` (under '## 3. Preconditions E1 to E8, with today's status')) |
| E3 | NOT MET, five parts | no `fwar` provider (`war_source.py@64bf1bb3:133` (at 'ewar_v2'), `:136` (at 'DEFAULT_PROVIDER')); hitting-only feed (`saber_feed.py@64bf1bb3:40` (in SABER_URL)); only `tools/rebase_career_war_to_ewar.py`; no frozen vintage; no pre-2011 cache | C, D+U (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:156` (under '## 3. Preconditions E1 to E8, with today's status')) |
| E4 | in hand | the registration | |
| E5 | NOT MET | 5c-A, 7h and 7i due 09-28 not run; 5c-B/5c-C look code absent (`diamond-betting.md@64bf1bb3:2867` (under '### 5c-C. The B4 availability gate')); no `data/grpo_forward_eval.json`, no GRPO lab | D+U, E, M (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:158` (under '## 3. Preconditions E1 to E8, with today's status')) |
| E6 | the season ended 09-27; the D9 freeze fetch is NOT taken (it needs E3) | `DECISIONS_FOR_OWNER.md@2026-09-30:212` (row 'O3 + O4') (O3, about 10-05) | A, C (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:159` (under '## 3. Preconditions E1 to E8, with today's status')) |
| E7 | NOT MET | the independent rebuild tool is still a planning template | F (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:160` (under '## 3. Preconditions E1 to E8, with today's status')) |
| E8 | MET | `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:144` (under '## 3. Preconditions E1 to E8, with today's status') | A |

Also owed now and not taken: the ETA flip to arm B (ETA-2, the last step of queue 8's task, served
only before 10-04); the 7h re-read, 5c-A and 7i (due 09-28, kill date Tue 10-06); GRPO's 30-day forward read (admissible since
09-18 and an epoch precondition). Missed already: PROJ_PATH_SHAPE's 09-25 blast artifact (no producer
exists), which keeps amendment A-2 admissible (`PROJ_PATH_SHAPE_GATE.md@64bf1bb3:1735-1738` (under '## 19. The append-only record')).

**Plan of record (the PROPOSED dates depend on batch 1 of 8.G):** Sat 10-03 23:59 the landing window
closes; Sun 10-04 to Wed 10-07 the preconditions are built (the critical path); the D9 freeze fetch on or
after Mon 10-05; **step A Wed 10-07 or Thu 10-08; step Z about Sun 10-11 to Tue 10-13**; the
PROSPECT_ANCHOR look Fri 11-20; the eFV reserved reads on or after Tue 12-01. Fallback if E5 is neither
met nor waived: step A about Sun 11-01 (after the 10-31 INDETERMINATE records), step Z about 11-05, and a
blackout of about a month for served work. Every Part 8 task that needs step Z carries `not_before`
2026-10-11 (the earliest proposed step Z) and still checks part 9 itself; if step Z slips, it STOPs on
its first check and the orchestrator re-arms it with the real date.

| Date | What must happen | Who runs it | Must NOT run with | Source |
|---|---|---|---|---|
| Wed 09-30, until the monthly exits | nothing writes the repo; the queue restarts only when `tasklist` shows no `run_monthly.py` | orchestrator | every writer, pytest | memory 09-30 resume note; plan 0.2 |
| Wed 09-30 (repair `6ca2e8f4` and record `be53132d` done at 19:22), then the flip | the ETA look's repair and rerun: the one report-only line at `tools/eta_fg_blend_gate.py@64bf1bb3:455` (in run_blend_gate()) committed alone with the crash disclosed, one rerun that reproduced the nine clause lines byte for byte (recorded: SHIP CANDIDATE, arm B recommended); the flip to arm B lands served only before 10-04, else behind `eta.ETA_FG_BLEND_ARM` until step Z | queue 8 ETA_LOOK_REPAIR_RERUN | `run_monthly.py` (its `eta_backtest` rewrites `data/eta_eval.json`, `run_monthly.py@410cccce:6300`), pytest, any writer | `DECISIONS_FOR_OWNER.md` ETA-1, ETA-2; `ETA_FG_BLEND_GATE.md@64bf1bb3:66-70` (under '## 6. The look'), `:85` (under '## 8. Results') |
| Thu 10-01, after the ETA rerun | the Ledger trim: trajectories move into the per-club shards and /ledger/ shows 10 preview rows again under the 950,000-byte guard; served before 10-04, else behind `LEDGER_TRIM_TRAJECTORIES` until step Z | queue 8 LEDGER_TRIM_PREVIEW_10 | run_monthly; pytest while exporters write | `DECISIONS_FOR_OWNER.md` VAL1-Q1 |
| **right after LEDGER_TRIM_PREVIEW_10, and before Mon 10-05** | **the starter-workload section, docs only, alone (Q10_01); its S8 discloses any 5c-B, 5c-C or 5d result already recorded when it commits** | Part 8 head task Q10_01 | any other writer | P8.1; STOP S8 |
| Thu 10-01 | the FA P(enter) eval window opens; nights without a pipeline run are a disclosed gap | nightly `d10p` | | `PENTER_DECISION_EVAL_PREREG.md@64bf1bb3:13-14` (under '# fa_penter decision-level eval') |
| Thu 10-01 to Sat 10-03 | the landing window: queue 7's Tier A, then B, then C (8.C); Part 8's optional class-1 inserts Q9_01, Q10_03 and Q8_01 only if a slot frees | queue 7 writers, one at a time | each other, pytest, run_monthly | `DECISIONS_FOR_OWNER.md@2026-09-30:273` (row 'DS-Q1'), `:375` (row 'FP2-1') |
| Fri 10-02, only under EPOCH-Q2 (a) | PROJ_PATH_SHAPE amendment A-2 before any PROJ artifact, docs only, alone (in Tier A; if the window is full, the first gap slot on 10-04, still before any artifact); under (b) or (c) no amendment is written | NEW PROJ_SHAPE_A2 | epoch D and E | `PROJ_PATH_SHAPE_GATE.md@64bf1bb3:243-248` (under '## 2. Label-quality gates. Nothing ships if these fail.'), `:734-741` (under '#### 4.6d Held fixed across every arm, so the contrast is the pen'), `:1505-1506` (under '## 13. The clock. One look per arm, on a fixed date') |
| when `backtest.fit_calibration_knots` exists (VAL_3 landed at `27ee25f9` without it; M11_PROSPECT_ARB_VIA_MODEL is the other task told to build it) | one knots-only calibration refit at $17.14M, no consensus-FV cell and no held-out statistic; served before 10-04, else behind `CALIBRATION_REFIT_LIVE_LEVEL` until step Z | queue 8 CAL_KNOTS_REFIT_17M | the epoch A to Z; 11-20; any valuation writer | `DECISIONS_FOR_OWNER.md` VAL1-Q2 |
| Sat 10-03 23:59 | the window closes; an unfinished queue-7 task commits flag-off code or nothing and writes REMAINING.md | orchestrator | | the specs' landing rule |
| Sun 10-04 (latest Mon 10-05) | the 7h one re-read (O23 default) in a detached worktree at `37e9382d`; if the 5c-A and 7i look code is still unbuilt, their closure records the same day | NEW BET_7H_REREAD (Opus) | run_monthly; any lab on 2026 totals; 7i first if both run | `diamond-betting.md@64bf1bb3:8853-8862` (under '### The one re-read, on 2026-09-28'), `:8914-8947` (under '### The one re-read, on 2026-09-28') |
| Sun 10-04 | GRPO 30-day forward read: build `tools/grpo_forward_lab.py`, run once, `data/grpo_forward_eval.json`, section 6, registry row `grpo_prospect` | NEW GRPO_FWD_30D (Opus) | the suite; it must precede the first `rebuild_only` after step C (which retrains GRPO, `run_monthly.py@410cccce:1712-1717`) | `GRPO_FORWARD_GATE.md@64bf1bb3:94-95` (under '### 2.6 Gate clauses'), `:102-103` (under '## 3. First admissible look') |
| Sun 10-04 to Wed 10-07 | preconditions built: E3's five parts, E2's repair and tripwire, Arm R's flag, the arm matrices and the fWAR epoch lab (step H's producer), E7's rebuild tool, B6_ARCHIVE_PATHS; E2's repair and a late B4_IDENTITY_SPLIT are the gap's one sanctioned served exception (8.A), each naming what it moves | NEW EPOCH_E3, EPOCH_E2, EPOCH_ARMS_LAB; EPOCH_E7_TOOL and queue 7 B6_ARCHIVE_PATHS | each other; no other served change | `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:135-161` (under '## 3. Preconditions E1 to E8, with today's status'), `:146-150` (under '## 3. Preconditions E1 to E8, with today's status') |
| gap, only if a slot is free after the preconditions | the game-intensity section (Q10_02), the FA destination gate (Q9_02) and the arbitration 12b pre-registration (Q9_17a), docs only, each alone; otherwise the first slots after step Z | Part 8 head tasks | any writer between step A and Z | P8.9; P8.5 |
| Mon 10-05 | the D9 freeze fetch of the 2026 fWAR vintage plus the 2000-2010 cache (22 calls); committed with `fetched_at` | NEW EPOCH_D9_FREEZE (Opus) | any writer | `DECISIONS_FOR_OWNER.md@2026-09-30:212` (row 'O3 + O4'); `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:142` (under '## 3. Preconditions E1 to E8, with today's status'), `:159` (under '## 3. Preconditions E1 to E8, with today's status') |
| Mon 10-05 (to Sat 10-31) | 5c-B `lineup_strength` and 5c-C `star_out`: the first look day; look code to be built, else INDETERMINATE on 10-31 | NEW BET_5C_BC | epoch D/E/M before the look unless EPOCH-Q1 waives with pins | `diamond-betting.md@64bf1bb3:2357-2362` (under '### 5c-B. The B4 availability gate'), `:3219-3224` (under '### 5c-C. The B4 availability gate'), `:3418-3425` (under '### 5c-C. The B4 availability gate') |
| Mon 10-05 | the step M floor (no projections retrain before it) | epoch | | `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:566-569` (under '### (j) `star_out`, `lineup_strength` and the dark betting colum'), `:714` (under '## 7. The rebuild') |
| Mon 10-05, Wed 10-07, the 5e day | the 5l disclosure amendments on the days the 5c, 5d and 5e looks are recorded | betting lane (docs) | | plan Part 1 |
| **Tue 10-06** | the kill date for 5c-A, 7h and 7i; any not run closes for 2026 with its reason in the text | BET_7H_REREAD | | `diamond-betting.md@64bf1bb3:1785-1790` (under '### 5c-A. The B3 rolling-form gate'), `:8945-8947` (under '### The one re-read, on 2026-09-28'), `:9549-9551` (under '### The look') |
| Wed 10-07 (to Sat 10-31) | the run-environment family RE (5d A-E schema 4, 5k, 5h-A at p = 1): read day R = the first day on or after 10-07 with both look runners ready; queue 7 B5_WEATHER_NWS's 5h amendment committed first | NEW BET_RE_FAMILY | epoch steps, the suite; after 7h and 7i | `diamond-betting.md@64bf1bb3:6432-6449` (under '### When 5k is read') |
| **Wed 10-07 or Thu 10-08 (PROPOSED)** | **epoch step A, then C, D+U, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, X, T, V, W, Y, Z contiguously (about 17 to 20 writer-hours, 2.5 to 3 calendar days)** | NEW EPOCH_RUN | every queue writer; the owner's `run_monthly` (daily or monthly); any lab during Y; the box nightly before C lands there | `WAR_BASIS_RUNBOOK.md`; `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:728-732` (under '## 7. The rebuild') |
| Fri 10-09, conditional on EPOCH-Q2 | under (a) the PROJ S2 pre-flight and B0-COMPARE move after step Z (amendment A-2 re-dates them on the fWAR corpus); under (b) or (c) they run as registered, outside the A to Z window | projections lane | eFV labs | `PROJ_PATH_SHAPE_GATE.md@64bf1bb3:1507` (under '## 13. The clock. One look per arm, on a fixed date') |
| Sat 10-10 | the last day for M17-HEM's docs amendment (the 5e/5f restart) before any 5e look; land it in the window or the gap | queue 7 M17_HEM part (a), docs alone | epoch steps | `DECISIONS_FOR_OWNER.md@2026-09-30:487` (row 'M17-3') |
| Sun 10-11 | 5e and 5i-B earliest looks (`dark_look_allowed` refuses earlier); with M17's amendment in, 5e restarts at the next night's vintage plus 28 days, so it reads in 2027 (no Part 8 task waits for either, Q10_02) | betting lane | | `diamond-betting.md@64bf1bb3:4150-4157` (under '### Amendment'), `:5122-5130` (under '### 5i-B. Park by bat side for the TOTAL') |
| **Sun 10-11 to Tue 10-13 (PROPOSED)** | **step Z: margins re-read, the part 9 entry; served changes may land again; the `not_before` of every post-Z Part 8 task** | EPOCH_RUN | | `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:726` (under '## 7. The rebuild'), `:760-772` (under '## 9. Results') |
| first day after Z | the Z1 driver re-test, about 4.5 h, one process, P4 pins, pipeline idle | NEW Z1_RUN | the suite, other labs, any writer, pipelines | `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:604-617` (under '### (k) The registration that follows this one') |
| on or after 10-11, after PM-Q3 | the starter-workload stage-1 run, once, never on another look's date (Q10_04b, after its build Q10_04a) | Part 8 | any registered look that day | the workload section |
| after Z | the FA realized ledger rebuild on fWAR (M14-3), queue 7 M14; Q9_04a (the FA destination lab) and Q9_04b (its one look) right after it | queue 7; Part 8 | | `DECISIONS_FOR_OWNER.md@2026-09-30:465` (row 'M14-3'); P8.5 |
| Sun 10-18 | the GRPO 60-day window admissible | GRPO lab | the suite | `GRPO_FORWARD_GATE.md@64bf1bb3:104` (under '## 3. First admissible look') |
| Fri 10-23 | PROJ ARM A look, once | projections lane | no eFV lab that day; no writer touching projections inputs; pipeline idle; every Part 8 task with the calendar exclusion | `PROJ_PATH_SHAPE_GATE.md@64bf1bb3:1508` (under '## 13. The clock. One look per arm, on a fixed date') |
| **Sat 10-31** | the last day for 5c-B/5c-C (else INDETERMINATE), the RE family (5d-C decided at p = 1 if not ready; 5k reads that day) and the 7e-D replay (else VOID; it needs `SERVE_PRICER`, absent at HEAD); no props flip follows from any date: `SERVE_WORKLOAD_PROPS` waits for 5l's block and the workload stage-2 look | betting lane | | `diamond-betting.md@64bf1bb3:2360` (under '### 5c-B. The B4 availability gate'), `:3224` (under '### 5c-C. The B4 availability gate'), `:6446-6449` (under '### When 5k is read'), `:8344-8358` (under '#### The run') |
| Sun 11-01 | eWAR v2's 2026 season freezes in the nightly (`war_source.py@64bf1bb3:149` (at 'EWAR_FREEZE_MONTH_DAY')); the fallback step A date if E5 is held; the first Team Outlook frame freeze, if Q9_03's commit 1 registered the monthly freezes | nightly; Q9_03a (`not_before` 2026-11-01) | the calendar exclusions | `EWAR_FREEZE_MONTH_DAY`; P8.6 |
| the later of 11-02 and the day after the World Series | the intensity stage-1 look, one run, after 5c-B, 5c-C, 5d, 5k and 7e-D are recorded or closed (5e and 5i-B share no game with stage 1 and are not waited for, Q10_02) | Q10_08 (`not_before` 2026-11-02) | any other look that day | P8.9 |
| about 5 days after the World Series | option and QO decisions resolve (the P(enter) eval population); queue 7 M13_OPTIONS_CALENDAR must be live before | queue 7 | | `docs/master-plan-2026-08-04d-omnibus.md@64bf1bb3:739-743` (under '# PART D') |
| Fri 11-06 | PROJ B0-GATE; FanGraphs' early team lists expected 11-06 to 11-13 (the first first-grade events for the provisional freeze; PV_A's scorer must be live) | projections lane; queue 7 PV_A | no source-list ingest between step A and step Z; every Part 8 task with the calendar exclusion | `PROJ_PATH_SHAPE_GATE.md@64bf1bb3:1509` (under '## 13. The clock. One look per arm, on a fixed date'); `PROVISIONAL_V2.md@2026-09-30:145-148` (under '4. Prospective freeze spec (commit at the first writer slot, before 20') |
| Fri 11-13 | PROJ ARM B look, once | projections lane | eFV labs; every Part 8 task with the calendar exclusion | `PROJ_PATH_SHAPE_GATE.md@64bf1bb3:1510` (under '## 13. The clock. One look per arm, on a fixed date') |
| about mid-November (CBA-contingent) | the qualifying-offer acceptance deadline: the FA destination vectors and the Fit's teamFits (pre-free-agency frame) are frozen for the 2026-27 forward read only if Q9_04b passed and froze before it; else the first forward read is the 2027-28 class | Q9_04b | | P8.5 |
| Mon 11-16 | the pWOBA xwOBA-blend re-gate, bat-tracking arm B, NOV-A and NOV-B, the DEM+ confirmatory holdout, the HEM/RIV pair set extension; one lab at a time | NEW NOV15_REGATES | the suite, each other, the PROJ look days | `RECHECKS.md@64bf1bb3:6-35` (under '## 2026-11-15 - pWOBA xwOBA-blend re-gate'); `DEM_PLUS_GATE.md@64bf1bb3:131-132` (under '## 7. Disclosure, added 2026-09-11 after the first and only run'); `HEM_RIV_REGATE_GATE.md@64bf1bb3:272-276` (under '## R1-12 Hard dates') |
| Tue 11-17 | the GRPO 90-day window admissible | GRPO lab | the suite | `GRPO_FORWARD_GATE.md@64bf1bb3:105` (under '## 3. First admissible look') |
| **Fri 11-20** | **the PROSPECT_ANCHOR one look** (the later of 11-20 and 14 days after part 9's step Z entry); producers at the look; never `value_framework.py --fit` between Z and this look | NEW PROSPECT_ANCHOR_LOOK | the PROJ look days; the eFV reserved read (a different day and session); any writer touching `data/value_framework_fitted.json`; every Part 8 task with the calendar exclusion | `PROSPECT_ANCHOR_GATE.md@64bf1bb3:970` (under '## 14. The clock. One look, on a fixed condition and a fixed ea'), `:975-981` (under '## 14. The clock. One look, on a fixed condition and a fixed ea') |
| about 11-20 (CBA-contingent) | the 40-man protection deadline; eFV V2's protection driver moves on the next nightly | pipeline | | `DRIVER_SYSTEM_V2.md` |
| November | eFV v2: EV-04 labels on fWAR, EV-05 floors, then EV-12 `EFV_V2_GATE.md` REGISTERED alone after PROGRAM Q2-Q4; the pitch-rate sidecar (Q10_10, under PM-Q4 (a)) and admission (Q10_11) run only after this | NEW EFV_V2_EV12 | no read of R-LV or R-VM | `PROGRAM.md@64bf1bb3:343-359` (under '### 3.5 Sequence') |
| October and November | captures: the Swartz 2026-27 projections (M12-3); MLBTR's top-50 and FanGraphs' crowd FA predictions with MLBTR's named team kept (FA-DEST-3) | queue 7 M11_M12 part 2; NEW FA_PRED_CAPTURE | | plan 3.E items 6 and 8 |
| **Tue 12-01** | the CBA expires (a lockout would freeze transactions and pause the FA destination forward read); a copy tense pass on or after 12-02; the second Team Outlook frame freeze | NEW CBA_COPY_1202; Q9_03b (`not_before` 2026-12-01) | the eFV reserved-read session | `fa_cba.py@64bf1bb3:14` (at 'effective_to'), `:59` (in regime_as_of()) |
| **Tue 12-01** | the eFV reserved reads earliest: R-LV once and R-VM look 1 in one session, after the anchor look and after EV-12; the DvM+ difficulty look (Q10_15, `not_before` 2026-12-01) and, by the same rule, Staff Gems' gate frame wait for this record | NEW EFV_V2_RESERVED_READ | the anchor session; the suite; every Part 8 task with the calendar exclusion | `PROGRAM.md@64bf1bb3:353` (under '### 3.5 Sequence'); `EFV_V2_GATE.md@64bf1bb3:32` (under '## 1. Preconditions') |
| Wed 12-02 | `test_storage_export.py@64bf1bb3:114` (in test_extras_present_flag_reflects_data()) rots | NEW TIMEROT_1202, any quiet slot outside A to Z | | `TIME_ROT_BACKLOG.md@64bf1bb3:40` (under '## RANKED BACKLOG, with the calendar date each will fire') |
| Thu 12-31 | the PROSPECT_ANCHOR slip line | | | `PROSPECT_ANCHOR_GATE.md@64bf1bb3:970` (under '## 14. The clock. One look, on a fixed condition and a fixed ea') |
| 2027-01-01, 02-01, 03-01 | the third, fourth and fifth Team Outlook frame freezes, each at the first writer slot on or after its date, never back-dated | Q9_03c, Q9_03d, Q9_03e | the calendar exclusions | P8.6 |
| 2027-01-15 | the promo watch h1 window opens; the IFA signing period and Pipeline international lists | NEW PROMO_WATCH | the suite | `tools/xfv_promo_watch.py@64bf1bb3:43-45` |
| 2027-01-31 | the DvM+ difficulty look's complement-frame fallback date if no R-LV record exists (the PROSPECT_ANCHOR record is required on this path too); the P(enter) window closes | Q10_15 | | P8.7 |
| before Opening Day 2027 | N9, every 2027 dark column (the workload and intensity schema builders Q10_19 and Q10_20 take the next schema number by commit order and do not wait for 5j's or 5l's builders), D4 Commit D after 5j; the M15 forward freeze (with the Team Outlook flag state settled before it) | betting and projections lanes; Part 8 | | Part 2.3 |
| 2027-07-01 earliest | 5l club policy rates; then the workload stage-2 look, after 5l's block exists, with at least 600 eval-half games, written as a stage2 block of `data/starter_workload_eval.json` | betting lane; Q10_21's tool | | `BETTING_DUGOUT_GATE.md@64bf1bb3:352-356` (under '## 9. The clock, and the sentence that binds it') |
| 2027 season close | the next label epoch (RT 2027); the intensity stage-2 look on the first nightly after the last scheduled regular-season game, kill 2027-11-30; the Team Outlook frames scored | | | P8.9; P8.6 |

**Every dated Part 8 task and every freeze.** Dated tasks (their `not_before` in `QUEUE_TASKS.json`):
Q9_03a 2026-11-01, Q9_03b 2026-12-01, Q9_03c 2027-01-01, Q9_03d 2027-02-01, Q9_03e 2027-03-01 (the
Team Outlook frame freezes), Q10_08 2026-11-02 (the intensity stage-1 look; it also waits for the day
after the World Series), Q10_15 2026-12-01 (the DvM+ difficulty look; or 2027-01-31 on the complement
frame), and every post-Z task at 2026-10-11 (the earliest proposed step Z). Owner-gated tasks stay in
their queues and STOP with 'BLOCKER: answer <id>' until the answer is recorded. Freeze dates and the
task that performs each: the D9 fWAR vintage fetch on or after 10-05 (NEW EPOCH_D9_FREEZE); eWAR v2's
2026 season on 11-01 (the nightly, `war_source.py@64bf1bb3:149` (at 'EWAR_FREEZE_MONTH_DAY')); the Team Outlook frames on 11-01, 12-01,
2027-01-01, 02-01 and 03-01 (Q9_03a to Q9_03e, only if Q9_03's commit 1 registered them); the FA
destination vectors and the Fit's teamFits before the QO acceptance deadline (Q9_04b, only on a
pass); the M15 forward freeze on the last nightly before the first 2027 game (queue 7's M15 part (4)).

**When step A may start (all six must hold):** the queue is paused after a committed task, and the
generated churn and the plan document with Part 8 appended (8.C action 0) are committed or explained;
E6 (the D9 freeze fetch, on or after 10-05, with E3 built); E2 done (B4_IDENTITY_SPLIT included) and
E7's tool exists; E5 met or waived (EPOCH-Q1) and the GRPO 30-day read exists; O7 answered and
recorded in part 9 after every part-3 amendment, Arm R's flag, the arm matrices and the epoch lab in
place, the Z1 registration ready to commit before step G; the owner's pipelines idle and held,
`data/` stable twice 300 s apart, no lab or suite running.

**Part 9 ordering.** Nothing above part 9 may change once anything is written below it
(`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:765-767` (under '## 9. Results')): first B6_ARCHIVE_PATHS's history line and any E5 waiver (a dated part-3 amendment
BEFORE the step it waives, `FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:163-165` (under '## 3. Preconditions E1 to E8, with today's status')), then the O7 arm-set record, then the step Z entry.

**Conflicts the calendar carries (C1 to C6 in the lane document):** E5 against missing look code
(EPOCH-Q1); PROJ_PATH_SHAPE pins the eWAR v2 corpus that step E deletes (EPOCH-Q2); VAL_1's loose
patches blocked step A (resolved: VAL_1 committed as `410cccce`); hand-run pipelines during the epoch
wrote a mixed basis on 2026-09-04 (ask the owner to hold `run_monthly.py` from step A to step R; the
scheduled captures write `.cache/` only and may continue); M17-HEM's restart covers 5e and 5f only,
so its switch must leave the 5i-B and 5j inputs byte-identical or stop; the anchor look, the PROJ
looks and the eFV reserved read never share a day.

### 8.C Queue sequencing recommendation

**One dynamic single-writer queue.** The Part 8 queues are not run as static chains. The orchestrator
drives one queue, `C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/dq/queue.json`,
through its controller `qctl.py` beside it and a runner that dispatches the first eligible task to
one writer at a time. A task is eligible when its status is pending, its `not_before` (an ISO date
or null) has come, and every id in its `requires` is done. The orchestrator inserts, reorders and
re-arms tasks at any time; each task's spec is a file read at dispatch, so an owner answer or an
amendment appended to a spec file before dispatch reaches the writer. A task that STOPs on a
precondition is recorded; its REMAINING.md ends with one line `BLOCKER: date <d>`, `BLOCKER: task
<id>`, `BLOCKER: answer <question id>` or `BLOCKER: other <text>`, and the orchestrator re-arms it
(`qctl set <id> --status pending` with a new `--not-before`, an added `--requires`, or a note until the
answer is recorded). The runner gives every writer Opus 5.5; the `model` field in `QUEUE_TASKS.json`
is advisory only.

**Orchestrator actions before any Part 8 writer runs.** (0) Append `<part8>/PART8_ADDENDUM.md` to
`prospect-tracker/docs/master-plan-2026-09-24-final-pass.md` as Part 8 and commit the plan (docs only,
alone) before step A; the plan is untracked at HEAD and ends at Part 7, and every spec that cites
"plan Part 8" also gives the section title, so a writer finds the text in either place. (1) Copy
`<part8>` to `C:/Users/noah/baseball-projects/_finalpass_2026-09-24/part8/` with a sha256 manifest.
(2) Dropped after round 1: the three test files the xwar lane saw change at 14:20 on 2026-09-30
(`test_bayes_trade_value_policy.py`, `test_rest_of_season_control.py`,
`test_value_framework_integration.py`) are part of VAL_1's commit `410cccce`. (3) Load the tasks:
copy `<part8>/P8_COMMON.txt` to the queue's `preambles/P8.txt`; write each task's spec from
`QUEUE_TASKS.json` to a spec file and insert the task with `qctl add` (preamble `P8`, its
`not_before` and `requires`); positions: Q10_01 `--after LEDGER_TRIM_PREVIEW_10`; the window's class-1
inserts Q9_01, Q10_03 and Q8_01 in Tier C; Q10_02, Q9_02 and Q9_17a on the gap list; Q11_01
`--after PX_D_visualizations` (before PX_E_gfx_brand_sweep; Q11_01 carries no `not_before`, so position
alone orders it, and the orchestrator also adds it to PX_E's requires with `qctl set PX_E_gfx_brand_sweep
--requires Q11_01_PIXEL_BRAND_GENERATOR` so first-eligible dispatch cannot run PX_E first); the rest after queue 6's DISPLAY tasks in
the order p8_metrics, p8_wiring, p8_research, p8_branding, with the later plans interleaved as 8.E
recommends. When the F-SCORE plan's FS-1 task is inserted, add its id to the `requires` of Q8_10,
Q8_13b and Q8_15 (until then those specs check FS-1's commit 1 themselves). (4) When COSTPLUS-1 is
answered, append the answer to the `M13_LEDGER_FRANCHISE_FIGURES` spec file before it is dispatched:
"Owner answer COSTPLUS-1: <a or b>. Under (a), in the same commit as the M13-4 denominator, take every
locked free agent's 2027 WAR out of the Cost+ numerator (and out of $ per projected win and $ per
projected WAR) and publish the moved clubs; under (b), keep the numerator and add one sentence naming
the mismatch." If M13 lands first unanswered, Q9_03 carries the correction. (5) Amend queue 3's PX_E
spec file so PX-23 reads the ball bitmaps of `tools/pixel_brand.py` (P8.10); Q11_01 runs between
PX_D and PX_E with the P8 preamble, never the PX preamble (whose brand rule "never redraw the wordmark
or the P/X monogram" is the plan 5.7.5 row the owner's ask 2 reopened). (6) Record every default a
task takes in `DECISIONS_FOR_OWNER.md` as the task reports it.

**The landing window (first slot to Sat 10-03 23:59).** VAL_1, VAL_2 and VAL_3 are done. The window
will not clear Tiers A to C (VAL_1 alone ran from 09-25 to 09-30, including a usage-limit death), so
the order protects the dated items first. Tier A (must): the end of queue 8's ETA_LOOK_REPAIR_RERUN (its look is
recorded at `be53132d`; the flip to arm B is time-bound, ETA-2 serves it only if it lands before 10-04), LEDGER_TRIM_PREVIEW_10 (a served owner decision),
then Part 8's Q10_01 (the starter-workload section, docs only, before 10-05), then PROJ_SHAPE_A2
(under EPOCH-Q2 (a), due 10-02), B4_IDENTITY_SPLIT, M26_TIER_CUTS_MLBSTATS_VIEWS, REPORTS_EXCERPT,
M17_HEM_SPLIT_PLATOON_RATIO (its docs amendment committed first). CAL_KNOTS_REFIT_17M runs as soon as
`backtest.fit_calibration_knots` exists at HEAD (not at `4fb990de`), served only before 10-04. Tier B
(should): B4_BOARD_SURPLUS, M9_M10_TRADE_AUDIT_LEDGER_COPY, M27, M24, M13_LEDGER_FRANCHISE_FIGURES
(after COSTPLUS-1 if possible), M7_M8_PROSPX_COPY_DISPLAY, M13_OPTIONS_CALENDAR. Tier C (only if
ahead): M25, M17_MLBSTATS_WINDOWS_3YR_SWSTR, B6_HOF_FRANCHISE_RULE, M19, M23, B4_SPOTLIGHTS_RESCORE,
M21 part 1, PV_A, and the Part 8 class-1 inserts Q9_01 (the Futures postseason stamp, time-valued while
October lasts), Q10_03 (DvM+ copy truth) and Q8_01 (two /mlbstats/ bugs). Stop rule: no served task
starts unless its regen, tests and commit fit before 23:59 10-03; if Tiers A to C finish early, start
EPOCH_E3 at once.

**The gap (Sun 10-04 to step A), in order:** Q10_01 if it has not landed (its S8 then discloses any
recorded 5c-B, 5c-C or 5d result first); PROJ_SHAPE_A2 if it missed the window (under EPOCH-Q2 (a),
before any PROJ artifact); BET_7H_REREAD; GRPO_FWD_30D; EPOCH_E3 then EPOCH_D9_FREEZE (on or after
10-05); EPOCH_E2 (plus a late B4_IDENTITY_SPLIT): the one sanctioned served exception, because both
must precede step A's snapshot (8.A); EPOCH_ARMS_LAB and EPOCH_E7_TOOL; B6_ARCHIVE_PATHS; the E5 waiver
amendment (if EPOCH-Q1 = a); the O7 arm-set record; the Z1 registration (after the freeze, before G).
Fill waits with gap-safe docs: M17_HEM (a) if not landed, B5_WEATHER_NWS (before 10-07),
B5_UMPIRE_DARK_FAMILY, B5_ARB_KNOWN_SEASON_GATE (registration), M22_PAL_SPRP_REGATE_PREREG, the M7
per-year pre-registration, M15 part (1) only (the gate document; part (3) edits served disclosures and
moves after step Z), TIMEROT_1202, then the Part 8 registrations Q10_02 (intensity), Q9_02 (the FA
destination gate, after the batch 2 and 3 answers) and Q9_17a (arbitration 12b, after ARB-CLUB-2). No
other served change in the gap, not even class 1.

**From step A to step Z:** nothing else writes. No queue writer, no hand-run pipeline, no lab while
step Y runs, no box nightly before step C lands there.

**After step Z, in order.** (1) Z1_RUN. (2) The Part 8 time-valued heads: Q10_02, Q9_02 and Q9_17a if
they did not land in the gap (Q10_02 before the World Series ends), Q9_01 if it missed the window,
then Q9_03 (the Team Outlook winter frame; its value runs from October to Opening Day), with queue 7's
M13_LEDGER_FRANCHISE_FIGURES (its `requires`) and M15 part (1) pulled ahead of it if they missed the
window; Q9_03's commit 1 (the monthly freeze registration) lands only after the OUTLOOK answer, and
its five freezes are the dated tasks Q9_03a to Q9_03e. (3) The flips and re-reads owed: the ETA flip
if it was recorded after 10-04 (ETA-2), LEDGER_TRIM_PREVIEW_10's and CAL_KNOTS_REFIT_17M's flips if
they were built behind flags, M26's second tier-cut recompute, M15 parts (3) and (4) off the PROJ look
days. (4) The label-dependent queue-7 tasks (M11_M12, M11_PROSPECT_ARB, B5_ARB build, M10 re-price, M9
realized leg, M14, M21 (2)(3), VAL_4), with Q9_04a (the FA destination lab) and Q9_04b (its one look)
run IMMEDIATELY after M14 lands so the model can freeze before the qualifying-offer acceptance
deadline, and Q9_19 pulled forward behind them only if Q9_04b passes and the owner flips it for the
winter. (5) PV_A if missed, PV_B, PV_C, PV_D, M20, the M7 per-year build, B6_MGMT_NIGHTLY, Tier B and C
leftovers. (6) Queue 3 (PX_A to PX_D, then Q11_01, then PX_E), then queue 6 (17 DISPLAY tasks). (7) FS-1
commit 1 lands in the landing window or in the first slots after step Z, before Q8_10 (the orchestrator inserts the
F-SCORE tasks into the dynamic queue in that order; Q8_10, Q8_13b and Q8_15 stop without it). Then the Part 8 queues
in order: p8_metrics (16 tasks), p8_wiring (the rest of its 36),
p8_research (the rest of its 22, whose dated looks and 2027 builders carry their own
`not_before` and preconditions) and p8_branding (the rest of its 10), with the later
asks' plans interleaved as 8.E recommends. The betting lane takes its own single-writer slots between
tasks, never beside one, for 5c-B/5c-C, the RE family and 7e-D by 10-31. Keep 10-23, 11-06 and 11-13
free of projections writers, 11-20 free of valuation writers and 12-01 free of every eFV writer; every
Part 8 task that runs an exporter, a lab, a fetch or a look carries that exclusion in its spec.

**Why this order.** p8_metrics first because its `pitch_rates.py` definitions, the `g` and `t` hash
keys, the viz tokens, the drawer shell and the per-game frame are read by the Baserunning plan,
F-SCORE's Teams column and League Trends, and because it must follow queue 7's M17, M26 and M27 and
queue 6's mlbstats lane (the same `assets/mlbstats.js`, exporters and `test_mlbstats_fit.py`).
p8_wiring second because the eFV display tasks must follow queue 7's PV_C (it re-routes `gradeBlock`)
and the link tasks must follow queue 6's PAL org sorting, queue 7's B6_HOF and queue 6's home_shell
lane. p8_research third because its served builds need VAL_4 (queue 7, post-Z) and its looks are
dated; its registration-only commits already sit before the builds that depend on them. p8_branding
last because it builds on queue 3's sprite (PX-01), masthead icons (PX-07), hand-page navs (PX-10),
export painter (PX-18), README (PX-21), player-card foil (PX-24) and T7 sweep. Inside every queue a
registration-only commit precedes the build that depends on it, and every task that moves a served
number after 2026-10-04 builds behind its flag and says so; the `requires` fields in
`QUEUE_TASKS.json` encode each of these dependencies by task id.

### 8.D Conflicts between lanes, resolved

Each row names the lanes, what collided, the resolution this part adopts, and why. The queue specs
carry the resolution, not the lanes' original text.

| # | Lanes | Conflict | Resolution | Why |
|---|---|---|---|---|
| 1 | league_team_stats vs the served page (found by the Baserunning and eBR plans) | The League tab's proposed hash keys `lview` and `lseason` already belong to Leverage (`assets/mlbstats.js@64bf1bb3:2776` (in readHash()) `lview=(batters\|starters)`, `:2793` (in readHash()) `readWindow(h, "leverage", "lseason", "lyears")`, written at `:2834`, `:2840`) | League takes the `g` prefix: `gview` (avg\|time), `gside`, `gseason`, `gpos`, `grole`, `ghand`, `gage`, `gqual`, `glg`, `gstat`, `gcmp`; Teams keeps `tseason`, `tcols`, `tbasis`, `tsort` (unused at HEAD); Baserunning keeps its `b` keys; `player=` is the drawer's; every new section adds its id to the one `section=` regex. A later section picks a prefix none of r, s, h, l, d, w, g, t, b uses | a shared key would make a Leverage deep link open the League sub-view and round-trip wrong through `writeHash` |
| 2 | pitch_metrics vs league_team_stats | Team pitch figures on two bases: P8.1's roll-ups on the boards' club-today basis (the Offense+/Rotation+/Bullpen+ membership), P8.2's Teams tab on the earned basis (`teams/stats` and the club `sp`/`rp` splits); the LTS lane proposed one test pinning "the two equal", which fails for every traded player | Both bases ship, labelled, exactly like the EM+ rollups: `pitch_rates.py` owns the definitions and `team_par()`, which takes unit rates on either basis; the pins are (i) the league role anchors from the player splits equal those from the club splits within 0.1 percent, (ii) club-today values equal the boards' team fields, (iii) earned values reconcile to StatsAPI team totals; never club-today equal to earned. The Teams tab's "Rotation IP/GS" is the club `sp` split's innings per start (starts only), never the served `ip_per_gs` | one definition, two memberships, each honest about its basis |
| 3 | pitch_metrics, intensity_index, queue 7's B5_UMPIRE_DARK_FAMILY | Both lanes wrote their betting registration as section "5m" and both claimed dark schema 8; the umpire family (queue 7, docs first) also adds a section and a schema | Section letters and schema numbers are assigned by COMMIT order: a registration takes the next free level-2 letter after the last `## 5x.` heading present when it commits (the dated workload section commits first, so it is expected to be 5m; intensity next), and a Part 8 dark schema takes the next number after the last landed BUILDER in commit order and does not wait for 5j's or 5l's builder (the doc allows it: 5j's number may move by a dated correction, `docs/diamond-betting.md@64bf1bb3:5501-5506` (under '## 5j. Posted lineups'), and only 5l waits for 5j, `:6789-6791` (under '### The clock, and the sentence that binds it'); so no docs amendment task is needed). Later specs name sections by title ("the starter-workload section", "the game-intensity section"); tests pin titles and column names, never letters or schema numbers | two queues can land in either order without a renumbering commit, and the 2027 dark captures do not hang on builders no queue holds |
| 4 | finance_to_fa_arb vs wiring_ideas | The Team Outlook winter frame: finance recommends keeping the registered pre-free-agency headline and adding a probability-weighted "expected after free agency" line once the destination model passes; wiring recommends serving an as-of-signings frame (unsigned free agents to a labelled pool, signings joining nightly) | One merged owner question (OUTLOOK). Recommended: the as-of-signings frame as the winter headline with the pre-free-agency frame as a labelled line, both frozen monthly by the dated tasks Q9_03a to Q9_03e and scored once at the 2027 close (an amendment to M15's forward gate, whose Opening Day freeze stays primary, registered only after the OUTLOOK answer); the FA Fit stays on the pre-free-agency frame and byte-identical under every answer, because repointing its WINDOW input is a Gate 3 lever that needs its own registration (P8.5 F-1, F-2); the probability form becomes a later upgrade of the unassigned pool, only after the destination model passes | the headline feeds a GRADED leg (Franchise OUTLOOK, 30 percent of the Index) and Cost+, and on CHC it counts about 10 wins of players whose contracts ended; an arithmetic frame fixes that without waiting on a model; the finance lane's dissent is option (b) |
| 5 | the same two lanes | Two measurements of the same gap: finance counts 172 of 190 locked free agents carrying 84.5 of 961.8 Team Outlook roster WAR (CHC 11.2 of 41.1); wiring counts 179 with a projection row carrying 99.5 year-1 champion WAR, 80.8 on the 156 whose contract rows end in 2026 (CHC 9.7) | Both are right on their own bases (roll-up WAR versus the FA champion's year-1 WAR; different memberships). The question quotes the roll-up figure because Cost+ and OUTLOOK read the roll-up; the builder recomputes on its own date and reconciles `fa_class.json` against the contract table first (23 locked members carry rows signed or controlled through 2027 or later) | no number in a spec is a constant; each is recomputed and printed in the commit |
| 6 | staff_gems vs dvm_difficulty | Staff Gems' manager leg reads the per-snapshot eFV series and its gate frame spans pairs from 2017 to 2026-09-30; the DvM lane forbids any eFV input (F-R5) and excludes 2020-2021 endpoints until the R-LV look record (F-R1), because a structured table of those lists' grade movement reads the reserved rows' outcome proxies | Staff Gems reads same-source FV grade pairs for the manager leg (the eFV retrospective series is today's model re-scoring old lists, the wrong object for crediting past staff), and both research frames follow one rule, the one the owner's Q-DVM-1 answer sets (default: pairs with a 2020 or 2021 endpoint enter a look only if the R-LV look record exists when it runs; otherwise the look runs on the complement frame and says so) | one reserved-frame rule across Part 8; it also removes Staff Gems' only reason to wait for step Z at its gate |
| 7 | dvm_difficulty vs staff_gems | DvM exports its residuals for Staff Gems; Staff Gems accepts a difficulty weighting only "in a compliant form (continuous eFV, never consensus-FV cells)" | Staff Gems may add DvM's frozen expectation table (source-grade start rung, origin, level, age) as a baseline term only after DvM's look has run, and only through a registration naming the artifact in its forking-paths count (DvM's firewall). Conditioning GRADE movement on a source's own start rung is not an FV-cell realized statistic (P8.7); no realized outcome by rung, ever, in either module | keeps both firewalls and answers the compliance worry |
| 8 | intensity_index vs the Scores and F-SCORE plans | The intensity lane proposed a Postseason tab on /betting/ (bracket, series state, bracket-state odds) and a Franchise "playoff performance" leaf; the Scores plan builds the live bracket with no odds; F-SCORE builds `postseason.py` and the Franchise postseason record | `postseason.py` (F-SCORE FS-1) is the one postseason results ingest; the Scores module owns the live bracket and series state; no betting Postseason tab is built; bracket-state odds only under INT-A2 (b), for 2027, with a registry row; the Franchise postseason record is F-SCORE's (its amendment lifts the pennant and title ban for results only), so the intensity lane's B3 is dropped | one ingest, one bracket, one Franchise record |
| 9 | links_efv_display vs wiring_ideas | The wiring lane found two consensus-FV displays off PROSPX (the MLB player page origin line prints the consensus arc, `assets/projections.js@64bf1bb3:3126-3131` (in renderPlayer()) via `mlb_player_export.py@64bf1bb3:359-379` (in _debut_origins()); Call-up Watch falls back to ceil(consensus), `assets/dynasty.js@64bf1bb3:532-533` (in renderCallups()), `fantasy_export.py@64bf1bb3:985` (in _callup_watch())) and W06 would print the origin line again | Both join P8.4's E5 under Q-E4; W06 prints the eFV arc only | the ask's rule is one display rule |
| 10 | links_efv_display vs the open W0 item G06 | Q-E4 (extend the eFV-only rule to PROSPX-derived FV elsewhere) covers /pal/ Prospect Watch, which is open item G06 (the PAL card grade form, default A shipped, never recorded as answered) | Q-E4 is asked once and its answer settles G06 too; the question says so | no second question about the same card |
| 11 | wiring_ideas W-OQ2 vs this part's landing classes | W-OQ2 asked whether additive display wirings ship when built or wait behind a flag | Resolved by the class rule in 8.A (class 1 ships as built after step Z; class 2 and 3 flag), so it is not asked | a rule, not a preference |
| 12 | finance_to_fa_arb FA-DEST-1 vs FA-DEST-2 | Two questions about one choice (a new registered destination model, or moving Ledger spending into the Fit itself) | Merged into one question with four options | the second only makes sense as an alternative to the first |
| 13 | intensity_index F2 vs the projections lane | The `playoff_odds_sim` registry row and the code disagree about the simulator's talent input | Q9_01 corrects the registry text to what the code does (class 1); whether the simulator SHOULD use the blended estimate is a lead for the projections lane (M12-20 owns the futures scorer), because changing the input moves every served Futures odd and needs its own read | describe first, change under a gate |
| 14 | league_team_stats vs the flag convention of P8.1 and the Baserunning plan | The LTS lane wrote `data/mlb_league_panel_*.json` and the other payloads directly and relied on page flags | While `MLBSTATS_LEAGUE_TEAMS_LIVE` and `MLBSTATS_DRAWER_LIVE` are False the exporters write `.cache/league_teams/preview/` only; `data/` files appear in the flip commit; the same holds for every Part 8 flag (`fa_destinations.json` under `.cache/fa_destination/preview/`, the events files under `.cache/mlb_events/preview/`) | a new `data/` file ships to the webroot (census X03-15), so "dark" must mean no new served file |
| 15 | pitch_metrics PM-05 vs the eBR plan's registry convention | PM-05 lands the `par` registry row and glossary before the flip | Registry rows and glossary entries for a new served number land in the flip commit (the eBR plan's rule; `par` included), and every flip is ONE commit carrying the flag, the new `data/` files, the rows and the glossary together (Q8_06, Q8_15, Q9_16, Q9_18, Q9_19, Q9_22c); rows that describe numbers ALREADY served (Q8_10's five rollup rows) may land earlier but name only the club-today basis until the flip adds the earned basis | a registry row naming a surface that does not serve it yet is a false statement |

### 8.E Overlaps with the later plans (reference only; which plan owns each shared piece)

Five later owner asks of 2026-09-30 have their own plans and queues, and none of their work is
planned here: a Baserunning section on /mlbstats/ (`<part8>/baserunning.md`, queue task
`BR_BASERUNNING_SECTION`), eBR for eWAR (`<part8>/ebr/`, tasks `EBR_1_REGISTRATION`,
`EBR_2_BUILD_DARK`, `EBR_3_EWAR_V3`; EBR_2 IS the Baserunning task plus additions, so only one of
the two is queued), a skill WAR from the EM+ family and F-SCORE (`<part8>/xwar.md`, tasks
`SWAR_REGISTRATION`, `SWAR_BUILD_AND_LOOK`, `SWAR_INTEGRATION`; `<part8>/fscore.md`, tasks FS-1
`fscore_data` and FS-2 `fscore_index_surfaces`), an MLB Scores module with embedded MLB.com
highlights (`<part8>/scores/`, build P0 to P7; the owner's answer S8-1 of 2026-09-30 is to EMBED
the highlight player), and a League Trends section (`<part8>/league_trends.md`, not yet written
when this part was assembled; the rules below bind it when it lands).

| Shared piece | Plans that touch it | Owner of the piece | Rule for the other |
|---|---|---|---|
| The Teams tab on /mlbstats/ (ask 15) and F-SCORE | P8.2, F-SCORE FS-2, Baserunning (team block), sWAR | P8.2 owns the tab, `team_stats_export.py`, `data/mlb_team_stats.json`, the earned basis and the club-today copy | F-SCORE owns the number, its pillars, `data/fscore.json`, the Franchise card, section, board mode and HISTORY marks; its Teams column joins through `team_stats_export.py` copying `fscore.json` verbatim with one equality test, added by whichever of Q8_10/Q8_13b and FS-2 lands SECOND. Team eBR joins the same way from the Baserunning payload's `teams[]` blocks after that plan's flip. sWAR never enters the Teams tab or F-SCORE (`xwar.md` 3.5) |
| Standings and division titles | P8.2 (W-L, xW-L, one-run records), F-SCORE (RESULTS pillar) | F-SCORE FS-1 owns the fix (derive each division champion as the unique `divisionRank` 1; the 2026-09-30 cache flags PHI `divisionChamp: true` beside ATL) | P8.2 reads standings only through `franchise_export._standings`, never the feed's `divisionChamp`, and never a second parser; FS-1's commit 1 is a precondition of Q8_10, Q8_13b and Q8_15 (their specs STOP without it, and the orchestrator adds FS-1's task id to their `requires` when that plan's task is inserted), and the Teams tab shows no division-title field in any case |
| League Averages over time (ask 14) and League Trends | P8.2, League Trends | P8.2 owns the league-wide series (`data/mlb_league_series.json`, `STAT_DEFS`, the Over time sub-view) and the per-game player frame (`mlbstats_games.player_game_frame`, built in Q8_11) | League Trends owns its trend detector, bar, false-trend arithmetic and Trends section; its league cards READ P8.2's series and never re-pool it; its player and team series import the per-game frame; it uses a hash prefix no other section uses |
| The player drawer (ask 18) | P8.2, Baserunning, League Trends, P8.1 | P8.2 owns the drawer shell, its payloads and the `player=` deep link | Baserunning supplies its panels into the shell (its 3.7); P8.1's P/PA and P/IP percentile rows appear after PM's flip; League Trends links a trend card to the drawer rather than building a second one |
| Intensity and the Scores module | P8.9, Scores | P8.9 owns the index, `betting_intensity.py`, the `intensity` block in `data/betting.json` and `SHOW_INTENSITY_CHIP` | Scores renders the block before first pitch only and never computes an intensity number; Scores owns the live scoreboard, the bracket and series state with no odds |
| Postseason results | F-SCORE FS-1, P8.9 IX-H2, Scores | F-SCORE FS-1 owns `postseason.py` and its cache (2000-2026) | IX-H2 builds it to FS-1's section 4.1 spec if FS-1 has not landed (built once, whichever runs first); the postseason winProbability feeds go to `.cache/win_prob_post/`, never `.cache/win_prob/` (the play-by-play corpus globs that directory and cannot tell a postseason game apart), and only the intensity lab reads them; the Scores live tier keeps its own intraday job |
| Pitch metrics and the Baserunning tab | P8.1, Baserunning | no shared payload or key | both edit `assets/mlbstats.js`, `build_site.build_mlbstats`, `site.css` and `run_monthly.py`, so they serialize: P8.2 takes run steps 9e-pre0d and 6b4l, Baserunning 9e-pre0e and 6b4m, eWAR v3 9e-pre0f and 6b4m2; the League tab's official SB, CS and SB% rows are P8.2's, and the runner-record rates join from Baserunning's league block after its flip |
| Expected pitches and innings | P8.1 (the workload section), Scores | P8.1 | the Scores page shows expected pitches only after the workload section's serve flag, and props context only after `SERVE_WORKLOAD_PROPS`, which may not flip before 5l's `mgmt_policy_gate` block and the workload stage-2 look both exist, exactly as the Scores plan already defers |
| Club links | P8.3, Scores, F-SCORE, Baserunning, Staff Gems | P8.3 owns `clubHref`, `clubLinkHTML` and the Python mirror | a plan landing first uses a local stopgap that maps through `EEPHUS_HUB.club(x).code` (never a raw payload code: `#team=CWS` opens Arizona today) and switches when L1 lands |
| The eFV-only display rule | P8.4, Scores (debut eFV), Staff Gems (prospect lists) | P8.4 | every surface prints eFV nearest and labels any consensus grade |
| Chart tokens and helpers | P8.2, Scores, F-SCORE | P8.2 owns `--viz-1`, `--viz-2`, `EEPHUS_HUB.lineChart` and `spark` (values validated in the LTS lane: light `#1D4ED8`/`#C9A227`, dark `#3B7FCC`/`#B08526`) | whichever lands first adds them with exactly these values; the other reuses |
| The payroll-history reader | P8.5 FAA-2, F-SCORE OPERATIONS | P8.5 (the cache-only reader, plan item M09-09's seam) | F-SCORE ships OPERATIONS dark until FAA-2 lands (its Q7 default) |
| eWAR v3 and the WAR columns | eBR, sWAR, P8.2 | the eBR plan owns eWAR v3; the sWAR plan owns sWAR | P8.2's WAR columns follow `war_seasons.war_provider` and O5; neither series appears on Part 8 surfaces except through its own plan's integration task |

**Cross-plan order recommended.** FS-1 commit 1 lands in the landing window or in the first slots after
step Z, before Q8_10 (the orchestrator inserts the F-SCORE tasks into the dynamic queue in that order). After
the Part 8 head tasks and queue 7's post-Z chain: queue 3, queue 6, then p8_metrics (so the drawer shell, the
`g`/`t` keys, the viz tokens and the per-game frame exist first), then the Baserunning task (or EBR_2) and
the rest of FS-1 and FS-2, then p8_wiring and League Trends,
then the Scores P5 context step (after P8.3's resolver in p8_wiring; its intensity chip waits for
Q10_09 and its own flag), then p8_research and p8_branding. FS-1's division-title fix is a served correction that the F-SCORE plan
may land in the landing window; it is not Part 8's to schedule, but its commit 1 must precede Q8_10,
Q8_13b and Q8_15.

### P8.1 Pitch metrics: P/IP, P/PA, PAR, the betting projection, the eFV driver (asks 10, 11, 12, 16, 17, 19, 20; lane pitch_metrics)

**Lane summary** (`<part8>/pitch_metrics.md`, 858 lines; probes saved beside it). MLB pitch
counts are on disk for every player-season 2000 to 2026 and nobody serves them:
`numberOfPitches` is in the cached StatsAPI season lines (`.cache/fa_statsapi_*`, on 100 percent
of hitter rows with PA > 0 and pitcher rows with BF > 0 in 2019 and 2021 to 2026). The pitcher
boards load it (`bullpen_export.py@64bf1bb3:633` (in rows_from_pitching_splits())) and use it only inside SwStr% and Strike%
(`bullpen_export.py@64bf1bb3:680-685` (in build_relievers()), `sem_plus.py@64bf1bb3:105` (in derive_rates())); the hitter loader drops it
(`hitter_export.py@64bf1bb3:148-160` (in load_season_hitting())), so P/PA costs one field and no request. StatsAPI splits every
pitcher into a starter line and a reliever line in one bulk call per season
(`stats=statSplits&sitCodes=sp,rp`; MLB 2025: 1,082 rows): starts ran 16.394 P/IP (4,860
starts, 85.0 pitches per start) and relief 16.614, and the play-by-play corpus reproduces those
numbers exactly (4,860 starts, 85.03 pitches, 16.392 P/IP). MiLB pitch counts are real only where
every pitch was tracked (an untracked level-season prints 1.7 to 2.5 pitches per PA): usable from
AAA 2011, AA 2014, A+ 2018, A 2016, complex 2024, DSL 2025, so a tracking guard is a
requirement. All 4,549 active prospects with career rows have a usable latest row; 86.9 percent
of career rows (17,072 of 19,648) are usable, the gaps being DSL 2022-2024 and complex 2022-2023.
Stability argues for a P/BF companion: starter P/BF year to year r 0.697 against P/IP 0.512 (334
pairs, 100+ IP both years); hitter P/PA r 0.778; reliever P/IP r 0.351. One served defect found
and left alone: `ip_per_gs` divides ALL innings by starts (`sem_plus.py@64bf1bb3:104` (in derive_rates())); in 2025, 48 of
249 true starters were overstated by 0.5 IP or more (max 3.83); the betting pricer reads it
(`betting_model.py@64bf1bb3:2620` (in _starter_share()), `betting_export.py@64bf1bb3:4489-4491` (in props_fair_lines())) and three registrations freeze it, so it
is never redefined and a starts-only length ships as a new key. No pitch count has ever been a
model input here (the 2026-09-05 plan listed P/PA as a driver idea; never run).

**Definitions (exact, `pitch_rates.py`).** Innings are outs / 3, always ("6.1" is 19 outs).
P/IP = pitches / (outs / 3) on the pitcher's line IN HIS ROLE (the `sp` split on Starters, the
`rp` split on Relievers; the season line is a stamped fallback). P/BF = pitches / batters faced.
P/PA = pitches seen / PA (an automatic intentional walk is one PA and zero pitches, as MLB counts
it). P/GS and starts-only `sp_ip_per_gs` are new keys. League anchors are POOLED (sum over sum),
never an average of player rates: MLB pitchers against the league role line, hitters against
every non-pitcher's line, prospects against their (level, season) and majority role, teams
against the mean of the 30 club unit rates (so the 30 values average 100). **PAR = round(100 x
player rate / anchor rate)**, nearest, not inverted (lower means fewer pitches, the FIP- shape),
uncoloured, with the owner's literal delta in pitches in the tooltip ("PAR 95, 0.8 fewer pitches
an inning than the 2026 starter average"). The ratio form beats 100 + 10z because a z index
divides by a cross-player spread that widens as the level drops (hitters 5.8 percent of the
mean at AAA against 7.5 at complex level), so 110 would mean different pitch loads at different
levels; one ruler serves pitchers, hitters and teams; it composes multiplicatively; and it pulls
in no value colour. Display floors: MLB boards show a rate whenever pitches > 0; PROSPX rows need
PA >= 50 or outs >= 30 (the `efv_dataset._milb_features` floors, `efv_dataset.py@64bf1bb3:950`).

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| PM-01 | registration | The starter-workload section of `docs/diamond-betting.md` (5m unless another section took the letter first; 8.D row 3): the candidate N6(d), G4-10 "expected outs", items 1-14 of the lane's 6.3 with the schema written as the next number in builder commit order, AS AMENDED in round 1: (1) two tested attribution contrasts in a Holm family of 2, T1 against D2 (r_L = 1, the lineup term) and T2 against C1, a same-window, same-shrinkage starts-only outs-per-start comparator (the pitch-rate term), with the wording pre-committed: without a T2 pass nothing credits pitch rates, only 'starts-only length over a 365-day window'; (2) the 2025 `ip_per_gs` measurement and corpus parity named as reads of a season stage 1 scores; (3) props: `SERVE_WORKLOAD_PROPS` waits for 5l's `mgmt_policy_gate` block AND the stage-2 look, with a registered fence as the only earlier display; (4) stage 1 and stage 2 write the section's own artifact `data/starter_workload_eval.json`, never `data/betting_model_eval.json`; plus two disclosure-only amendments (a dated note in 5d-E after `:3925` (under '### 5d-E. Times through the order'); a line in 5l's disclosure list after `:6813` (under '### The clock, and the sentence that binds it')); committed ALONE before 2026-10-05 | `docs/diamond-betting.md`; then `test_betting_workload_registration.py` | the section predates any builder by git date; no non-test module names `sp_xouts`, `sp_budget`, `sp_ppo`, `bat_ppa_l30` before a `### Builder landed` amendment; no `SERVE_STARTER_WORKLOAD` symbol before a stage-2 block | predictive, registered, no number computed | S | dated: before 10-05, inserted right after queue 8's LEDGER_TRIM_PREVIEW_10; S8 keyed to a recorded 5c-B, 5c-C or 5d result, never to a date; Fable advisory |
| PM-02 | build | `pitch_rates.py`: `SERVE_PITCH_RATES = False`, `tracking()`, `fetch_season_lines`, `fetch_role_splits` (MLB `gameType=R`, `playerPool=ALL`, paginated), `league_rates`, `player_lines`, `par`, `team_par`, `build()` writing `.cache/pitch_rates/preview.json` while the flag is off; a new sibling cache `.cache/pitch_rates/`, never `.cache/milb_stats`; `bullpen_export.record_ingest` for both fetchers; one-time warm (about 340 requests) outside any pipeline window; two parity receipts (role-split BF equals season BF within 0.5 percent, a level-season off by more than 5 percent excluded and stamped untracked for P/IP rather than a stop, which is reserved for an MLB season or a usable AAA or AA season; producer MiLB totals equal the orphan `.cache/milb_platoon` vl+vr totals) | `pitch_rates.py`, `test_pitch_rates.py` | outs-based innings incl. "6.1"; None on zero denominators; pooled anchors equal sums over sums; `tracking()` reproduces the lane's table on a fixture (CPX 2023 untracked, A+ 2017 partial, AA 2014 usable); `par()` rounds nearest; `team_par` averages 100; season-line fallback stamped; nothing under `data/` while the flag is False | none (flag off) | M | Opus |
| PM-03 | build | Exporters: `hitter_export.py@64bf1bb3:148-160` (in load_season_hitting()) gains `NP`; `starter_export.py` and `bullpen_export.py` join role lines by mlbam; new row keys (starters `p_ip`, `p_bf`, `par`, `par_delta`, `pit_per_gs`, `sp_ip_per_gs`, `role_line_basis`; relievers `p_ip`, `p_bf`, `par`, `par_delta`, `pit_per_g`, `role_line_basis`; hitters `p_pa`, `par`, `par_delta`, `pit`); a payload `pitch_rates` block; team roll-ups `pen_p_ip`, `pen_par`, `rot_p_ip`, `rot_par`, `rot_pit_per_gs`, `lineup_p_pa`, `lineup_par` on the boards' current-roster basis; history exporters get the same keys; all only when `SERVE_PITCH_RATES` | `hitter_export.py`, `starter_export.py`, `bullpen_export.py`, contract tests | `leaderboard_vintages.reduce_current` (`:1555`) byte-identical on fixture boards; `betting_model.starter_inputs()` (`:1178`) unchanged; every existing key byte-identical; new keys typed and None where no pitches | none until the flip; then descriptive | M | S4, S5; Opus |
| PM-04 | display | `assets/mlbstats.js`: columns in `REL_COLS` (528), `STARTER_COLS` (2915-3012), `HITTER_COLS` (3427-) in the `{key, label, term, fmt, num, title}` shape, PAR uncoloured (no `EephusTiers.cls`); a "Pitches" view per board in `COL_VIEWS` (761-807) with the phone subsets the lane lists; All keeps every column (M26-3); team columns in `TEAM_COLS` (686-), `STARTER_TEAM_COLS` (3016-3027), `HITTER_TEAM_COLS` (3570-); header chips `P/IP 16.1 · PAR 98` on Bullpen Charts (`renderDepth` 2329-2349), Rotation Charts (`rotationLadders` 3237-3268) and Lineup Charts (`lineupLadders` 3934-3995, computed on the page for the displayed nine, missing slots skipped, "Display only: nothing here reaches betting"); optional scatter PAR (starts) against IP/GS (starts) in `starterViz`, 2026 only until the workload stage-1 record exists (2024 and 2025 are the seasons that look scores on the same relation); column titles as drafted in the lane's 5.1 | `assets/mlbstats.js`, `test_mlbstats_views.py`, `test_mlbstats_fit.py`, smoke | the new view fits at 768 and its phone subset at 390 (drop `p_bf` from the view first, keep it in All; if it still fails, S16); render sweep 390/768/1024/1280/1440 both themes, zero console errors | descriptive display | M | PM-Q2 default (a); Opus |
| PM-05 | copy | Glossary entries `p_ip`, `p_bf`, `p_pa` (standard stats, no registry rows) and `par` (Arkmetric, shelf "ark") as drafted in the lane's 5.5; registry row `par` (`predicts` "nothing forward; DESCRIPTIVE DISPLAY INDEX ...", `champion` "pitch_rates.par (convention 1 ratio, unshrunk, nearest point)", `eval_artifact` null, `verdict` provisional, `provisional_kind` `measurement_only`, the word "descriptive" in `baseline` and `metric`); `test_methodology_freshness.MODEL_GLOSSARY` gains `"par": ["par"]`; ARKMETRIC conventions rows; `tools/gen_audit_docs.py` | `data/glossary.json`, `data/model_registry.json`, `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md`, `MODEL_REGISTRY.md` | `test_model_registry`, `test_methodology_freshness`, `test_generated_docs_in_sync`, glossary provenance, copy lint; a typed year list in copy gets a `test_claims_freshness` pin to `data/pitch_rates.json` | descriptive; registry row | S | lands in PM-07's flip commit, not before (8.D row 15); Opus |
| PM-06 | display | PROSPX: `storage.py` attaches per career row (`:11604` (at 'career_stats'); graduates `:13004` (at 'career_stats'), `:13013` (at 'career_stats')) `p_pa` or `p_ip` + `p_bf`, `par`, `par_anchor`, `par_basis`, `par_role`, only for usable level-seasons at or above the floor, joined on (mlbam, season, level) to `pitch_rates.player_lines`; `prospx/index.html` `makeCareerTable` (44825-), `makeCareerByLevelTable` (45101-, exposure-weighted anchor), `levelNormTooltip` (14452-14491), the detail header chip sub-line; nothing on board rows | `storage.py`, `prospx/index.html` | a usable row gets PAR and an untracked CPX 2023 row gets none; floors hold; a JS string test on the career table header; no NaN or undefined on 20 sampled detail pages; boot gzip delta under 150 KB else the detail shard (S15); `restamp_hand_authored_pages()` | descriptive display; level PAR is not an eFV input | M | Opus |
| PM-07 | flip | `SERVE_PITCH_RATES = True`; run the three exporters and storage on the monthly path; the commit lists every new served key and its row counts; render sweep | flag flip commit | the exporters' contract tests; `test_mlbstats_fit`; smoke | class 2 (new served numbers) | S | after step Z (S7); Opus |
| PM-08 | lab | `tools/starter_workload_lab.py` and `data/starter_workload_eval.json` (the section's own tracked artifact) per the workload section: corpus seasons 2018, 2019, 2021-2025 (never 2026), the unit a start, incumbent A0 = 3 x clip(season-to-date IP/GS, 2.0, 7.5), walk forward by date, priors chosen on 2018-2019 only from the frozen grid, the floor set on 2021-2023 before any 2024 row, 2024-2025 scored once; PASS needs a game-clustered bootstrap lower bound above 0 (B 2000, seed 20260930), positive points in 2024 and 2025 separately, the floor met, and `budget`'s pitches MAE no worse than the season-to-date mean; T1 (against D2) and T2 (against the starts-only comparator C1) tested as one Holm family of 2 and deciding the wording; D1 reported, never tested; built (Q10_04a) and run once (Q10_04b) in separate tasks under the crash protocol | `tools/starter_workload_lab.py`, `data/starter_workload_eval.json`, `test_starter_workload_lab.py`, registry row `starter_workload_xouts` | a start's own pitches never enter its inputs; burn-in constants frozen; refusal of 2026 seasons, an early date and a second run; fixture arithmetic; corpus parity (2025: 85.0 pitches per start) | predictive; the row lands `unvalidated` with the code, the run sets the artifact and verdict (PASS provisional and dark, FAIL deprecated); a failed stage 1 stays in its own artifact because `data/betting_model_eval.json` is rebuilt from scratch every night (8.F) | M build, S run | the run once, on or after 2026-10-11, after PM-Q3, never on another look's date, never reading `sp_tto3_bf`, `sp_rest_days` or any `mg_` column (S10); Opus |
| PM-09 | flip | `SERVE_WORKLOAD_PROPS` (default False, added only with its flip commit): sets `expected_ip = xIP` and `expected_bf = xPitches / P's EB P/BF` in `props_fair_lines` (`betting_export.py@64bf1bb3:4444-4513`); moves the four fair-line rows per probable; because `props_value_bets` turns any cached props snapshot into edge, EV and Kelly rows armed or not and hands them to `provisional_picks` as slot candidates (`betting_export.py@64bf1bb3:4883-4899`, `:7017-7026` (in build())), the only earlier form is the registered FENCE: candidate-derived props rows carry no market comparison, value row, slot candidacy, shadow row or record row, pinned by a test in the `test_betting_mgmt_fence.py` style | `betting_export.py`, tripwire, fence test | the flip commit names every moved row | class 3, owner action | S | only after 5l's `mgmt_policy_gate` block AND the workload stage-2 look both exist (a stage-1 PASS licenses nothing served; 5l's close-variant rule, `docs/diamond-betting.md@64bf1bb3:6849-6854` (under '### The clock, and the sentence that binds it')); the fence earlier only if the owner asks; Opus |
| PM-10 | dark | The schema builder per the workload section's item 9: pitcher columns `sp_n365`, `sp_budget`, `sp_ppo`, `sp_xouts`; team column `bat_ppa_l30`; `betting_usage.build_schema*_*` beside `build_schema4_team_columns`; source `.cache/game_feeds` strictly before D; first-write-wins, None never zero, `inputs_as_of` never fills; `DARK*_*` tuples; a `### Builder landed` amendment naming the first vintage night | `leaderboard_vintages.py`, `betting_usage.py`, `betting_model.py` (DARK tuple only), `test_schema_builders.py` | strictly-before, floors, parity with the corpus on one 2025 and one 2026 game, basis stamp, clock test; AST and string tests that no served path reads the columns | dark, unread | M | before Opening Day 2027; the next schema number by builder commit order, NOT waiting for 5j's or 5l's builders (8.D row 3); Opus |
| PM-11 | look tool | `tools/betting_workload_gate.py` per the workload section's item 8: the stage-2 moneyline read (candidate replaces `w` in `game_prevention_z`, `betting_model.py@64bf1bb3:2627-2645`; paired Brier t >= 1.645 Holm in N6 m = 4; log loss not worse; permuted-pitcher twin 200 draws; at least 600 eval-half games with both probables; VIF against `ip_per_gs`, `sp_tto3_bf`, `mg_hook_pitches_l30` under 5); refuses early and second runs | `tools/betting_workload_gate.py`, a `stage2` block of `data/starter_workload_eval.json` (never `data/betting_model_eval.json`) | fixtures; the 5l floor 0.0024 and the power precondition; the one-run guard reads the artifact and the section's result block | predictive; the look | S | the first nightly on or after 2027-07-01 with 5l's `mgmt_policy_gate` block present and no other look that day; if the 600-game floor is unmet by 2027-08-01 it waits for 2028; Opus |
| PM-12 | lab | The eFV sidecar `data/_labs/efv_pitch_rate_features.json` keyed (player, list vintage): hitters `ppa_rel` (PA-weighted `ln(P/PA / L(level, season))` over the up-to-3 most recent usable pre-V seasons, PA >= 50, shrunk PA / (PA + 100)), pitchers `pbf_rel` (majority-role P/BF against its role anchor, BF >= 60); source `pitch_rates.player_lines` through the outcome-blind resolver; steps (a) coverage count by (V, side), (b) the balance probe (W3 > 0 share by has-block on lv_dev), (d) descriptive correlations with `obp_rel` and `k_rel`; logged in `data/xfv_arm_ledger.json` as probes | `tools/` lab, `data/_labs/`, `data/xfv_arm_ledger.json` | the matrices' sha256 pins do not move; absence imputed at the has-block TRAIN mean; no absence flag in any head; no R-LV or R-VM row read | research, adjudicates nothing | S-M | after the fWAR freeze, on the frozen label, AND under PM-Q4 (a) only after `EFV_V2_GATE.md` is REGISTERED (EV-12), because step (b) reads an outcome split tied to V2's candidate blocks; under (b) step (b) runs only after Q10_11's amendment commits; step (d) also reports the correlation with the closed `bb_rel` arm; Opus |
| PM-13 | admission | Step (c): the DS-06 admission inside folds V 2017, 2018, 2019 on each fold's own training vintages (sign held in every vintage with t, at least 60 rows and 2 vintages, mean abs t >= 1.0), arm ids `PM19:hit.skill.ppa_rel`, `PM19:pit.skill.pbf_rel`; under PM-Q4 (a) after `EFV_V2_GATE.md` is REGISTERED, pre-declared for the NEXT registration if admitted in all three folds; under (b) an s4.2 amendment before the frozen-label DS-16 re-run, disclosed in s3.4 and s6 | `tools/efv_driver_lab.py` path, `docs/efv-v2/EFV_V2_GATE.md` (only under (b)) | reproducibility of the three per-vintage signs; no served eFV change | research; the honest expectation is "refused" or a tie under 0.005; the arms touch the closed eFV feature frontier (plan Part 2.2) and, for pitchers, DS-Q2 (pitcher eFV stays consensus order until pitch-quality or K-rate data passes): they are reopened only by a new data field (MiLB pitch counts) plus the owner's ask 19 of 2026-09-30, `pbf_rel` goes beyond DS-Q2 on that authority, and the report states each arm's correlation with the closed `bb_rel` arm | S | under (a) after EV-12 (November); under (b) the amendment commits first, before any W3 read; Fable advisory |
| PM-14 | optional | Last 3 / Last 5 windows fold pitches and outs against the window's pooled anchor (after M17's nightly panel); MLB player page season lines show P/IP and P/PA (the ask-18 hook); PROSPX Leaderboards P/PA, P/IP and PAR boards | `tools/mlbstats_window_lab.py`, `mlb_player_export.py`, `prospx/index.html` | the window reproduction test; render | descriptive | M | P3; Opus |

**Queue tasks.** PM-01 is Q10_01 (a head task, before 2026-10-05); PM-02 Q8_02; PM-03 Q8_03; PM-04
Q8_04; PM-06 Q8_05; PM-05 and PM-07 together Q8_06 (one flip commit); PM-08 Q10_04a (the build) and
Q10_04b (the one run; PM-09 recorded as an owner action that waits for 5l's block and the stage-2 look);
PM-10 Q10_19; PM-11 Q10_21; PM-12 Q10_10; PM-13 Q10_11. PM-14 is not queued (P3; it returns
as a task once the League, Teams and drawer work has landed). **Team basis (8.D row 2):** the
team roll-ups in PM-03 are on the boards' club-today basis, the membership Offense+, Rotation+ and
Bullpen+ use; P8.2's Teams tab adds the earned basis from the club `sp`/`rp` splits through the same
`team_par()`; the tests pin the shared league anchors, never the two bases to each other.

**Honesty status of every number.** P/IP, P/PA and P/BF are standard statistics (glossary rows,
no registry rows, the K-BB% precedent). PAR is a descriptive ratio index with a registry row
that predicts nothing forward. Team PAR is arithmetic on the boards' current-roster basis (and, on P8.2's Teams tab, on the earned basis). The
`stability` block of `data/pitch_rates.json` carries the year-to-year r values, and any copy that
prints one reads it from there. The betting candidate (ask 16) is predictive and registered in
two stages: stage 1 is a WORKLOAD estimand (outs and pitches per start) scored on pre-2026
corpus games against the served innings share, in no Holm family; stage 2 is the moneyline price
on the 2027 vintage frame, member N6(d) of the z_prev family (m = 4, conservative Holm, the
smallest p read at 0.0125), never before 2027-07-01 and never before 5l's own look because 5l
names a per-pitcher hook rate as a disqualifying close variant. A stage-1 pass by itself shows only
that the candidate beats the served innings share; whether pitch rates add anything is T2 (against a
starts-only comparator on the same window and shrinkage) and whether the lineup's P/PA adds anything
is T1 (against D2), and the wording follows those two contrasts, never the headline pass. The eFV candidates (ask 19) are
sidecar research through the Driver System V2 admission rule on development folds V 2017-2019
on the frozen fWAR label; they never enter a pinned matrix, never score R-LV or R-VM, and never
tabulate PAR by FV grade or tier against an outcome. They touch the closed eFV feature frontier
(plan Part 2.2) and, for pitchers, DS-Q2; this item reopens them only on a new data field (MiLB pitch
counts, never a model input before) plus the owner's ask 19, `pbf_rel` goes beyond DS-Q2 on that
authority, and the admission report states each arm's correlation with the closed `bb_rel` arm. Nothing in this item moves a served number
until PM-07 flips after step Z.

**Dependencies on queued tasks.** After queue 7's `M17_MLBSTATS_WINDOWS_3YR_SWSTR`,
`M17_HEM_SPLIT_PLATOON_RATIO`, `M26_TIER_CUTS_MLBSTATS_VIEWS` and `M27_HEM_PARENT_TRADE_CBT`
(the same `assets/mlbstats.js`, exporters and `test_mlbstats_fit.py`). P8.2 imports these
definitions and reads `data/pitch_rates.json` and the board keys rather than recomputing. PM-10
takes the next schema number by builder commit order and waits for no other builder. PM-12 and
PM-13 wait for EV-12 under PM-Q4 (a); under (b) PM-13's amendment commits first. The ask-9 lane covers
the new team chips' club names through the resolver when it lands.

**Landing rule.** PM-01 docs only, before 2026-10-05 (S8, keyed to what is recorded: if a 5c-B,
5c-C or 5d result is recorded in `docs/diamond-betting.md` when it commits, its text discloses that
result before any other content; nothing stops it on a date). PM-02 to PM-06 build behind `SERVE_PITCH_RATES = False` after step Z (class
2); PM-07 flips after step Z. PM-08's run on or after 2026-10-11 after PM-Q3. PM-09 only after 5l's
`mgmt_policy_gate` block and the stage-2 look both exist (the fence earlier only on the owner's
request). PM-10 before Opening Day 2027. PM-11 in 2027. PM-12 after the freeze;
PM-13 after EV-12. Seventeen STOP conditions S1 to S17 are in the lane document's section 11;
the ones that bite most: never redefine `ip_per_gs` (S5); never refetch or reshape
`.cache/milb_stats`, `milb_history` lean rows or the eFV matrices mid-epoch (S6); no flip
between the freeze and step Z (S7); the team statSplits read always passes `limit=100` and
asserts 60 rows, because the default returns 50 (S17).

**Effort.** PM-01 S (Fable), PM-02 M, PM-03 M, PM-04 M, PM-05 S, PM-06 M, PM-07 S, PM-08 M plus
a dated run, PM-09 S, PM-10 M, PM-11 S, PM-12 S-M, PM-13 S (Fable), PM-14 M optional.

**Owner questions raised (defaults in bold; batch 8 of 8.G).** PM-Q1 PAR's form (**ratio index,
delta in the tooltip, uncoloured**; the raw delta as the column; 100 + 10z). PM-Q2 placement (**a
new "Pitches" view per board plus All**; also in Standard, which must still fit at 768): not asked,
the default is taken and S16 asks it only if the view fails the 768 fit. PM-Q3 may stage 1 run now (**yes: pre-2026 corpus games only, the starter's own outs and
pitches as the only labels, the workload section committed first, on or after 2026-10-11; a pass licenses
nothing served, the props change still waits for 5l's block and the stage-2 look unless the owner later asks
for the fence**; wait for 5l's look, July 2027 or later). PM-Q4 the eFV drivers (**kept out of V2's 2026 registration; the sidecar and the admission
diagnostic after V2 registers; pre-declared for the next registration if admitted**; added to
V2's candidates now, disclosed as added after DS-16 with the balance probe in the forking-path count).

### P8.2 League Averages, over-time charts, Team Stats and the player drawer on /mlbstats/ (asks 13, 14, 15, 18; lane league_team_stats)

**Lane summary** (`<part8>/league_team_stats.md`; prototype, probes and 88 rendered states in
`<part8>/lts_work/`). Two new tabs, Teams and League, go after Leverage; Overall stays the
landing (owner decision 2026-09-17, `build_site.py@64bf1bb3:4154-4161` (in build_mlbstats()), `assets/mlbstats.js@64bf1bb3:2886-2891`)
and fetches nothing new, because both tabs and the drawer lazy-load their own script and data.
League is a descriptive table (rows are statistics; columns are the pooled league value, the
filtered delta against all players, and the player distribution mean, median, SD, n) with
filters season 2000-2026, side, position, role, the player's own hand, age band, sample rule
and league, plus an Over time sub-view drawing any statistic 2000-2026 with one comparison group,
small multiples and a numbers table, deep-linked with no new routes. Teams puts the EM+ family
on one sortable 30-club table (Offense+, Rotation+, Bullpen+, Team DEM+, each against the
league's own weighted mean, on both club bases: club today as served and a new earned basis)
beside the club's record, runs, MLB's expected record, pitch counts and the In-Game Management
club tendencies (style, not skill, uncoloured). The drawer opens from a caret on every board row
and shows the board index's season trend, percentile bars against that board's qualified pool
and a rolling window of the last 15 games (5 starts); the name still opens `/projections/#player=`.
Nothing predictive is added, no served number changes, and the six board payloads stay
byte-identical. The prototype ran on real payloads built from the caches: 88 states at
390/1024/1280/1440 in both themes, no horizontal page overflow, every SVG with `role="img"` and
an `aria-label`. Two live bugs were found and reproduced on the rendered page: opening a season
row on Overall makes the next player's rank print 3 instead of 2 (`site.css@64bf1bb3:2378-2382`
increments `mlbx-rank` on the inserted `tr.mlbx-seasonrow`), and every /mlbstats/ chart prints
its axis labels about 5 px tall at 390 px (`histogram` and `scatter` draw on a 640-unit viewBox
with 9-unit labels; both helpers already accept `width`, `eephus-hub.js@64bf1bb3:143` (in histogram()), `:177` (in scatter())).

**What data exists (served state, HEAD unless noted).**

- StatsAPI season lines `playerPool=All`, 2000-2026, both groups (54 files), one row per
  player-season with age, position, counts and `numberOfPitches`; a traded player's row sits
  under his LAST club (`bullpen_export.py@64bf1bb3:11-16`); no handedness. [`fa_sources.py@64bf1bb3:485-506` (at '_STATSAPI_SEASON_URL'); `.cache/fa_statsapi_*`]
- People feed `/api/v1/sports/1/players?season=Y` (bats, throws, birth date, primary position;
  1,512 people for 2026), the call `hitter_export.load_bat_side` already makes for the live
  season (`hitter_export.py@64bf1bb3:686-721` (in load_bat_side())); not cached for past seasons today.
- League constants 2011-2026 solved, served from 2015; the committed 2026 FIP constant 3.0978 on
  38,966 IP against 3.1021 on today's totals (the live block is solved on its own date).
  [`league_constants.py@64bf1bb3:311-355` (in league_totals()), `:368-370` (in served())]
- Window-lab per-season panels 2022-2025 plus the live panel: the only league-wide source of
  per-season index values (`hem`, `sem`, `rem`, `dem`, gmLI, WPA). [`tools/mlbstats_window_lab.py@64bf1bb3:531`]
- Standings 2000-2026 with `expectedRecords` (`xWinLoss`, which sums to games played for every
  club in 2000, 2001, 2020, 2025 and 2026; never `xWinLossSeason`, which projects the full
  schedule: the 2001 Yankees read 95 against an `xWinLoss` of 89-72 on 161 games) and
  `splitRecords`. [`.cache/statsapi_standings_*`, `franchise_export.py@64bf1bb3:288-313`]
- StatsAPI team season lines: nothing in the repo fetches `teams/stats` today; the `sp`/`rp` team
  splits return 50 of 60 rows without `limit` and 60 with `limit=100` (2005, 2025, 2026 probes).
- Management club rows for 2018, 2019, 2021-2026 (240 club-seasons; `clubs.rows`, `teams.rows`).
  [`data/management_board.json`, `management.js@64bf1bb3:483-532`, `:621-640` (at 'boardCols')]
- Play-by-play corpus 2018, 2019, 2021-2026 (2026 built 2026-09-25 on 2,385 games), the only
  source for rolling windows that needs no network call; game times in `.cache/win_prob/<pk>.json`.
- Two identities hold on all 27 completed seasons: league PA equals league batters faced, and
  pitches seen equal pitches thrown (2025: 182,926 PA and BF; 710,084 pitches both sides). The
  live season drifts by at most 0.1 percent between the two group reads (09-27: 183,295 PA
  against 183,297 BF).
- League trend, pooled: 2000 P/PA 3.773, K% 15.9, ERA 4.77, SP IP/GS 6.17; 2019 3.936, 22.4, 4.51,
  5.63; 2025 3.882, 22.2, 4.16, 5.50; 2026 to 09-27 3.886, 22.1, 4.18, 5.55.
- The league's own weighted means of the served rollups on the HEAD boards: Offense+ 99.85 (team
  SD 3.50), Rotation+ 102.09 (7.77), Bullpen+ 101.62 (7.42), Team DEM+ 100.81 (3.53); 100 is the
  average QUALIFIED PLAYER on each board, not the average team, and the payload carries these
  means so no page hard-codes one. Coverage: Offense+ 179,767 of 183,295 league PA (98 percent);
  Rotation+ and Bullpen+ 23,801 + 15,149 of 42,946 IP (about 91 percent); swingmen and arms
  under the board floors are in neither rollup and the EM+ view says so.
- Both team eWAR bases are already served on Overall (MLB Stats spec O8, `mlbstats.js@64bf1bb3:5352-5356`),
  the precedent the Teams tab extends: Detroit reads 76-86 against an expected 89-73, eWAR 29.3
  club today against 35.7 earned after the 2026-08-02 Skubal trade; the Dodgers 52.0 against 48.7.

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| LT-01 | bug fix | Rank counter: one rule inside the mlbx block, `.mlbx .mlbstats-table tbody tr.mlbx-seasonrow { counter-increment: none; }` (and the same for `tr.mlbx-drawer`); chart width: every `histogram` and `scatter` caller passes `width` close to the cell's real pixel width (the prototype's `vbw()`), and every new chart follows the rule | `assets/site.css`, `assets/mlbstats.js` | a DOM test that opening the Overall caret keeps the next row at rank 2; every /mlbstats/ chart at 390 px renders its first label at 8 px or taller; `restamp_hand_authored_pages()` | none | S | class 1, ships as built; Opus |
| LT-02 | refactor | Move `mlbstats_window_lab._hitter_rates`, `_pitcher_rates`, `_pooled` (`:760-851`) into a public `mlbstats_rates.py` and have the lab import them back, so League and the window boards share one recipe | `mlbstats_rates.py`, `tools/mlbstats_window_lab.py` | two fresh exports compared, never the committed files: `export(write=True, out_dir=tmpA)` before the refactor and `out_dir=tmpB` after it, the same day and cache memo, with `bullpen_export.record_ingest` monkeypatched; the JSON compared with `generated_at`, `build_seconds`, `built_at`, `block_built_at` and `panel_built_at` removed (the lab stamps them on every run, `tools/mlbstats_window_lab.py@64bf1bb3:584-588` (in season_panel()), `:1901` (in build()), `:1953` (in build()), `:1983` (in export())); stop only when another key differs; nothing written under `data/` | none | S | Opus |
| LT-03 | ingest | `mlb_people.py` (`load(season)` into `.cache/mlb_people/people_<Y>.json`, permanent for completed seasons) and `mlb_team_season.py` (`teams/stats` hitting and pitching; `statSplits sp,rp` with `limit=100`, assert 30 clubs per code, into `.cache/team_stats/`) | two new modules, tests on saved fixtures | refusal when a `statSplits` code returns fewer than 30 clubs or a people feed covers under 90 percent of a completed season's panel rows; no network in tests | none | S-M | Opus |
| LT-04 | exporter | `league_averages.py`: `build_panel(season)`, `build_series()`, `export()` writing `mlb_league_panel_<Y>.json` (one per season 2000 to live, 47-74 KB gzip each, completed seasons frozen, the live one nightly) and `mlb_league_series.json` (about 40 KB gzip with the hand, age and league groups) under `.cache/league_teams/preview/` while `MLBSTATS_LEAGUE_TEAMS_LIVE` (defined here) is False, and under `data/` only in the flip (8.D row 14); `STAT_DEFS` shared with Over time and the drawer; pooled through the shipped derivations (`hem_plus.derive_rates`, `sem_plus.derive_rates` `sem_plus.py@64bf1bb3:95-110`, `rem_plus.derive_rates`) on summed counts; standard FIP with the season constant from `league_constants.league_totals`, labelled apart from the boards' shrunk Skill FIP; `guard_nonempty_block` refusals | `league_averages.py`, `test_league_averages_export.py`, `data_catalog.py` rows | pooled groups equal a direct recompute; the FIP constant equals `league_totals` within 0.0005 on completed seasons; PA == BF and seen == thrown on every completed season (live tolerance 0.1 percent); the `all` group reproduces the lab recipe through `mlbstats_rates`; no group or filter key contains `fv`, `efv` or `grade`; no vs-hand group | descriptive; no registry row | M | Opus |
| LT-05 | exporter | `team_stats_export.py`: `export()`, `earned_rollups(season)` (each player's season index weighted by the PA or IP he took for the club, from `war_source.stint_frame` `war_source.py@64bf1bb3:554-599`, the frame `war_board_export._earned_by_club` already reads `:290-377`), `history()`; the club-today block COPIED unchanged from the four boards and `war_leaderboards.json`; records only through `franchise_export._standings` after the F-SCORE plan's FS-1 commit 1 (never the feed's `divisionChamp`, 8.E; no division-title field on the tab) and `xWinLoss` only; pitch figures on BOTH bases through `pitch_rates.team_par` (club today from P8.1's roll-ups, earned from the club `sp`/`rp` splits; rotation IP/GS is the club `sp` split's, never the served `ip_per_gs`), pinned per 8.D row 2, never club today to earned; tendencies read unchanged from `management_board.json`; the F-SCORE column joined verbatim from `data/fscore.json` by whichever lands second; writes `mlb_team_stats.json` (about 7 KB gzip plus 15 KB history) to the preview directory while dark | `team_stats_export.py`, `test_team_stats_export.py`, `data/model_registry.json` | club-today values equal the boards value for value; earned rollups recompute from stints on a fixture; `xWinLoss` W + L == G for every club; 30 clubs per `sp`/`rp` code; the league weighted means equal a recompute; tendency cells equal the management rows; the six board payloads byte-identical with and without the exporter; `leaderboard_vintages.TEAM_COLUMNS` inputs untouched (`leaderboard_vintages.py@64bf1bb3:184-196`) | descriptive; registry rows `offense_plus`, `rotation_plus`, `bullpen_plus`, `leverage_deploy_plus`, `team_dem_plus` (verdict provisional, `provisional_kind` `inherits_parent_gate`, `eval_artifact` null, `predicts` "nothing; a descriptive weighted mean of <parent>" on the club-today basis the team sub-tabs serve today, the earned basis and the Teams tab added in LT-10's flip commit), which closes the Part 3.A gap for the rollups already served; no row for xW-L (MLB's number, credited) or W - xW (arithmetic) | M | X01 may already add the rows: whichever lands first, the other drops the item; Opus |
| LT-06 | exporter | `mlbstats_games.py` with a public `player_game_frame(season)` (the per-game frame the League Trends plan imports, 8.E); `mlbstats_trends_export.py` (`data/mlbstats_trends.json`: every player-season index 2016-2026, about 2,922 players, 66 KB gzip, fetched on the first drawer open) and `mlbstats_rolling_export.py` (`data/mlbstats_player/<mlbam>.json`, raw per-game counts from the corpus ordered by first-play start time, about 2 KB gzip each, gitignored, plus `mlbstats_player_index.json`); refuses when the corpus's last game date (`covers_through`, computed from the corpus) is more than 2 days before the boards' last game date, never by comparing build stamps (the boards' `as_of` moves nightly all winter while the corpus's `built_at` does not; the page then shows "rolling window not built") | two new exporters, tests, `.gitignore` (`data/mlbstats_player/`), `deploy/nightly-build.sh@64bf1bb3:240-247` and the workflow staging include, a copy of the `test_publish_manifest.py@64bf1bb3:132-156` (in test_slices_dir_shards_ship_in_both_deploy_consumers()) guard for the new directory | lab panel and history agree on shared (player, season) index values; per-player game sums equal the board's season counts within the corpus's game coverage; refusal when stale; an off-season fixture (boards built in November with the last game on 09-27 and a corpus covering 09-27) that must not refuse; the directory ships in both deploy paths | descriptive | M | Opus |
| LT-07 | pipeline | Daily step `9e-pre0d` after 9e-pre0c (`run_monthly.py@410cccce:2996-3005` (at '9e-pre0c')) and monthly `6b4l` after 6b4k (`:5989-6009` (at '6b4k')) running the four exporters with the `chained` skip pattern, after the vintage snapshot, never on the epoch's frozen rebuild list (`FWAR_LABEL_EPOCH_GATE.md@64bf1bb3:690-737` (under '## 7. The rebuild')); cost about 4 s for all 27 panels plus the series, a few seconds for the rolling pass, four network calls a night | `run_monthly.py`, `data_catalog.py` | a structure test that the new step runs after the snapshot; catalog rows `pinned_by` their contract tests | none | S | Opus |
| LT-08 | display | `EEPHUS_HUB.lineChart` (promoted from `fa_dpw.js@410cccce:101-154`, exported beside `histogram` and `scatter` at `eephus-hub.js@64bf1bb3:658` (at 'EEPHUS_HUB'): inline SVG, `var()` tokens only, end-of-line value labels, round 1-2-5 ticks with the range snapped, no tick crowding the last one, hollow markers for a partial season, only the last point marked past 30 points, drawn at real width) and `spark`; tokens `--viz-1` and `--viz-2` on `:root` and dark (light `#1D4ED8` / `#C9A227`, dark `#3B7FCC` / `#B08526`, validated: light on `#FAF5E6` colour-blind difference 38.0, dark on `#1A1A1E` 24.2; the gold's 2.22:1 contrast is covered by end labels and the table); `assets/mlbstats-league.js` (League and Teams) lazy-injected by `showSection` from `data-league-src` on the root; `build_site.build_mlbstats` (`build_site.py@64bf1bb3:4119-4200`) emits the two buttons and panels with `_csv_optin` only when `MLBSTATS_LEAGUE_TEAMS_LIVE`; hash keys `section=league|teams`, League with the `g` prefix (`gview`, `gside`, `gseason`, `gpos`, `grole`, `ghand`, `gage`, `gqual`, `glg`, `gstat`, `gcmp`; the lane's `lview` and `lseason` belong to Leverage at HEAD, 8.D row 1), Teams `tseason`, `tcols`, `tbasis`, `tsort`; a `teams` GFX spec in `_mlbstatsBoardSpec` (`mlbstats.js@64bf1bb3:5061`); every new `site.css` rule inside the mlbx block (`site.css@64bf1bb3:2363-2514`); glossary entries `league_average`, `team_basis_earned`, `xwl`, `w_minus_xw`, `lineup_depth`, `relief_ip_share`; `gen_audit_docs.py` | `assets/eephus-hub.js`, `assets/site.css`, `assets/mlbstats.js` (`readHash` `:2768`, `showSection` `:5706-5720`, `writeHash`), `assets/mlbstats-league.js`, `build_site.py`, `data/glossary.json` | `test_mlbstats_league_page.py` (py_mini_racer, the `test_mlbstats_smoke.py` setup): each view renders rows, `vs all` appears only when filtered, the Teams table sorts, tendency cells carry no `vt` class, the landing requests no new URL, hash keys round-trip; `test_mlbstats_fit.py` PAGES extended (`:61-92`); `test_value_ruler.py` (EM+ team columns use the boards' families, style z columns none); `test_design_tokens.py`, `test_text_token_contrast.py`, `test_mlbx_css_scope.py`, `test_claims_freshness.py` (the weighted means and the coverage sentence read from the payload); copy checks; `restamp_hand_authored_pages()` | descriptive; the value-ruler legend chip on the table (A-3); `vs all` and W - xW in text ink, signed, never coloured; RD and W - xW never called luck | L | class 2 behind `MLBSTATS_LEAGUE_TEAMS_LIVE = False`; Opus |
| LT-09 | display | The drawer (`assets/mlbstats-drawer.js`, `data-drawer-src`): a caret on every row of Hitters, Starters, Bullpen, Defense and Leverage (Overall's caret gains the charts under its text line), `aria-expanded` and `aria-controls`, Enter and Space, one `tr.mlbx-drawer` with `counter-increment: none`, one drawer open at a time; deep link `player=<mlbam>` on any section opens the board, highlights the row and opens its drawer (census M06-16); panels per board as the lane's 6.2 table (trend by season with the 100 line; percentile bars against this board's qualified pool reusing `projections.js@64bf1bb3:2153-2155` (at 'pctClass'), `:2229-2243`, flipped where lower is better with one line saying so; rolling last 15 games or 5 starts drawn only once a window is full, with a 30/10 toggle needing no refetch); no hot or cold labels, no arrows, no "trending"; the hub player strip in the footer; three panels stack below 700 px | `assets/mlbstats-drawer.js`, `assets/mlbstats.js` (`renderTable` hooks `opts.nameExtra` and `opts.child` `:2019-2024, :2064, :2081`), `assets/site.css`, `data/glossary.json` (`rolling_window`) | the page test's drawer row carries `mlbx-drawer`; `section=hitters&player=665742` fits at every width; percentiles cost no download; the first open costs about 66 KB gzip plus 2 KB, later opens about 2 KB | descriptive | M | class 2 behind `MLBSTATS_DRAWER_LIVE = False`; Opus |
| LT-10 | flip | Flip both flags after step Z with the flags turned on locally first and the render sweep green at 390/768/1024/1280/1440 both themes (no overflow, no console error other than an aborted external request, no failed local request, no chart label under 8 px); ONE commit carrying the flags, the new `data/` files, the glossary entries and the registry surface text | flag flip commit | the sweep; the page tests | class 2 | S | after step Z; Opus |

**Queue tasks.** LT-01 is Q8_01; LT-02 Q8_07; LT-03 Q8_08; LT-04 Q8_09; LT-05 Q8_10; LT-06 and
LT-07 together Q8_11; LT-08 in three, Q8_12 (the hub chart helpers and viz tokens), Q8_13a (the League tab) and
Q8_13b (the Teams tab); LT-09 Q8_14; LT-10 Q8_15 (one flip commit with the data, glossary and rows).

**Honesty status of every number.** Every number is a sum, a pooled ratio, a served value
re-weighted, or MLB's published expected record. The League tab needs no registry row. The five
rollup rows are descriptive `inherits_parent_gate` rows. The earned basis re-weights served
per-player season indexes by stint PA or IP and scores nothing new; the tooltip says exactly
that; past seasons show the earned basis only, because a club-today rollup of 2023 would put 2023
seasons under 2026 clubs (`bullpen_export.py@64bf1bb3:390-409` (in team_basis_meta())). No correlation, fit, slope or r between
any Teams column and wins, runs or outcomes is computed or printed; the Runs view's two scatters
(wins against expected wins with the identity diagonal; run differential against earned eWAR
with a zero line) carry no fit. Three filters are left out and the page states each reason once:
club (a season row sits under the last club), any grade grouping (never computed,
`docs/PROSPECT_ANCHOR_GATE.md`, test-pinned), and matchup splits vs LHP/RHP (the team split is
the input to the pre-registered 5e test, first look 2026-10-11, and the per-hand HEM+ estimator
just changed under M17-3). Pooled wOBA waits for X02-08 / M06-18 (the boards compute wOBA with
frozen 2013 weights while `league_constants` solves each season). The eWAR-labelled columns
follow `war_seasons.war_provider` through the epoch and O5. The management tendency columns
keep the registry's own display rule (`mgmt_style_z`: a frequency has no good direction; realized
columns carry the "realized" tag, a dash under the family floor, and the sort tooltip that a sort
by a realized column ranks what happened after decisions, not how well clubs chose).

**Dependencies on queued tasks.** After queue 7's M17 (nightly live panel; `M17-1`) and M26
(views) and after queue 3's `site.css` work, because they touch the same three files. Imports
P8.1's definitions (PM-02 and PM-03 first; until they land the exporter pools its own pitch
figures and one test pins the two equal, and the league's own PAR reads 100 with a delta of 0).
The Teams club cells link through `EEPHUS_HUB.club(x).code` today (`eephus-hub.js@64bf1bb3:52-109`) and
through `clubHref` once P8.3's resolver lands. Staff Gems (P8.8) may reuse the management
tendency columns; this item only displays them. Registry lane X01 may already be adding the
five rows. The later asks' plans read this item's pieces (8.E): F-SCORE adds its Teams column,
the Baserunning plan its team and league blocks and drawer panels, League Trends the series and
the per-game frame; each join is added by whichever of the two lands second.

**Landing rule.** LT-01 ships as built (class 1). LT-02 to LT-07 add modules and pipeline steps
whose outputs stay under `.cache/league_teams/preview/` until the flip (no new served file before
it). LT-08 and LT-09 build behind
`MLBSTATS_LEAGUE_TEAMS_LIVE = False` and `MLBSTATS_DRAWER_LIVE = False`; LT-10 flips after step Z.
Stop conditions at every step: a new predictive claim or a word that implies one; a printed fit
between any Teams column and outcomes; any vs-hand group before the 5e and 5i-B looks; any new
fetch on the landing section; an index shown on a window or pooled group where no lab computed
it; any write under `data/` while the monthly runs.

**Effort.** LT-01 S, LT-02 S, LT-03 S-M, LT-04 M, LT-05 M, LT-06 M, LT-07 S, LT-08 L, LT-09 M,
LT-10 S; about 5 to 6 writer-days in all.

**Owner questions raised (defaults in bold; batch 7 of 8.G).** LTS-1 placement (**two tabs, Teams and League,
after Leverage**; one League tab with Teams as a sub-view; fold Teams into each board's team
sub-tab). LTS-2 team basis (**both bases, earned the default in this section, club today
labelled**; club today only; earned only). LTS-3 how player charts open (**a caret opens a
drawer in place and the name keeps opening the player page**; the name opens the drawer; no
drawer, extend /projections/ instead). LTS-4 over-time charts (**a sub-view of League with deep
links**; also standalone routes `/mlbstats/league/<stat>/`, which adds pages to
`deploy/publish_paths.txt`, SITE_MAP.md and the render sweep; small multiples only). Defaults
taken without asking (display-only, reversible): no club filter on League (Teams is the club
view); box-score statistics 2000-2026 with indexes where they exist; a 15-game / 5-start window
with a 30 / 10 toggle; the phone chart fix ships with this item. Already binding: Overall stays
the landing; 93/107/120 on the z scale (decision 25); the legend chip (A-3); two team eWAR bases
(O8); All keeps every column (M26-3). Still open and relevant: O5 decides the WAR label.

### P8.3 Team links: one club resolver and a link on every club mention (ask 9; lane links_efv_display, Part A)

**Lane summary** (`<part8>/links_efv_display.md`; probes and census JSON in `<part8>/lx/probe/`).
The franchise page is `/franchise/#team=CODE` (`assets/franchise.js@64bf1bb3:137-172`; a code is honoured
only if `clubOf(code)` finds it in `franchise_board.json` `clubs[]`, the 30 FanGraphs spellings)
and the farm page is `/prospx/#farm-org=CODE` with `&ftab=`; the `#team=CODE` shape is pinned by
`test_franchise_export.py@64bf1bb3:635-636` (in test_back_links_land_on_the_projections_open_cell_and_the_prospx_farm_header()), `test_franchise_render.py@64bf1bb3:316-317` (in test_back_links_from_projections_and_prospx_and_the_native_picker()) and
`test_management_render.py@64bf1bb3:395` (in test_club_page_links_only_to_routes_the_payload_says_are_built()). The trap, measured on the served path: `/franchise/#team=CWS`,
`#team=KC`, `#team=OAK` and `#view=club&team=CWS` all render the Arizona Diamondbacks page with
no warning, and `/prospx/#farm-org=CWS` renders "Unknown organization". StatsAPI codes (AZ, CWS,
KC, SD, SF, TB, WSH) live in the five MLB Stats boards and `pal.json`; FanGraphs codes in
`franchise_board`, `ledger_board` (which already carries a `franchise` href per club),
`management_board`, `fa_class`, `mlb_projections`, `trade_values`, `betting`, `dfs`, `fantasy`,
the draft and PROSPX timeseries; `ifa_timeseries` carries OAK for 2021-2024; transaction
`from_org`/`to_org` carry affiliate and foreign club names. The right base is
`EEPHUS_HUB.club(x)` (`assets/eephus-hub.js@64bf1bb3:43-109`, exported at 658), which resolves the 30
codes, the aliases, MLBAM ids and exact names, with one defect: `_CLUB_BY_NAME` is a plain
object, so `club("constructor")` returns `Object` through the prototype. Not safe for links:
`trades.canonical_org` (`trades.py@64bf1bb3:375-403`, passes any 4-character uppercase string through, so
"TEX" the Texas League survives, and token-searches free text so "Worcester Red Sox" becomes BOS)
and `build_site._org_from_team_name` (`:2569-2578`, a nickname suffix matcher). The site has six
logo helpers and no link helper. The census counted every unlinked club mention at 1440 px
(A1 to A25 in the lane document): MLB Stats boards 926+926 on WAR alone, the depth charts (the
owner's White Sox example prints "CWS" plus the logo, `assets/mlbstats.js@64bf1bb3:3979`), betting 110
codes + 44 logos, Trade Machine 100+100 per page inside `tr.prospect-row` whose inline onclick
calls `preventDefault` (`trademachine.js@64bf1bb3:1085-1087`), Arbitration 854+854, Projections 100+100
inside the row header `th` of a clickable row, FA 230 sub-ids + 247 logos inside clickable rows,
PROSPX board-family rows stamped `role="button"` by `decorateA11yRows` (`prospx/index.html@64bf1bb3:54219-54224`)
that already nest buttons (an existing defect), the IFA `.ifa-org-link` span with onclick and no
href or tabindex (348 on the default view), and home, news and history logos inside whole-row
player anchors. Not clubs: `/parks/` "TEX" cells are the Texas League (`assets/parks.js@64bf1bb3:393` (in boardTable())).

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| L1 | build | The resolver: `clubHref(x, ctx)` ("" when `club(x)` is null; ctx "farm" gives `/prospx/#farm-org=CODE`, else `/franchise/#team=CODE`) and `clubLinkHTML(x, opts)` (`<a class="club-link" href data-club title>`, opts ctx, text code or name or the surface's own string, logo only where the surface shows one, stop inside a clickable row; unresolved input keeps the escaped text plus `data-club-nolink="unresolved"`, never a guess); harden `club()` with own-property lookups; a Python mirror `_club_code`, `_club_href`, `_club_link` beside `_team_logo` (`build_site.py@64bf1bb3:1178`) accepting the exact 30-code set, the 9 aliases, exact full and former names and MLBAM ids via `trades.canonical_org_from_id` (`:357-372`), never `canonical_org`'s token search; one table both sides read; defensive routers: `franchise.js` readHash (145-155) maps `t[1]` through `EEPHUS_HUB.club(...).code` before `clubOf` and rewrites the hash, PROSPX `13787` and `findOrg` (44063) convert aliases; `.club-link` styled from tokens with a visible `:focus-visible`; the three pinned tests updated deliberately | `assets/eephus-hub.js`, `build_site.py`, `assets/franchise.js`, `prospx/index.html`, `assets/site.css`, `test_club_resolver.py`, `test_club_links_render.py` (skeleton) | resolves to the canonical code and href: all 30 codes, aliases AZ CWS KC SD SF TB WSH OAK FLA, 30 full names, 6 former names, MLBAM ids; resolves to "": "Texas", "Arizona State", "Worcester Red Sox", "ACL D-backs", "DSL NYY Bombers", "Arizona Complex League", "constructor", "", null, "FA", "AAA"; JS and Python tables identical; `/franchise/#team=CWS` shows Chicago White Sox and `/prospx/#farm-org=OAK` shows Athletics | none (moves no number) | S | class 1; Opus |
| L2 | build | MLB modules A1 to A13: MLB Stats `nameCell` team span (`mlbstats.js@64bf1bb3:2115`, logo 2139), team views (2067), depth charts (3979, 3261, 2343, 4893); betting game head (`betting.js@64bf1bb3:3144-3145` (in gameCard())), SP org (3223/3227), numchip (2565), Dugout org (1448), futures club cell (2392, links only, no Franchise figure on a priced cell, X03-22, `test_betting_mgmt_fence` green), props org (3396/3409); Ledger payor cell (244) and club-view heading (1015) keep the in-page `#section=club&team=`; Trade Machine org cell (1122) with `stop: true` and an `a,button` guard on the row handler (prospect rows to the farm page, MLB rows to the franchise page); Arbitration `club()` (213-219); Projections sub-id (1798), Team Outlook (1054/1064), compare (2078), player page (3149); FA former club (936-937) and rails; fantasy, redraft, DFS and fantasy-card logo mentions (Q-L3 default: link them with a 24 px hit area and full-name alt); PAL (`pal.js@64bf1bb3:365` (in candTable()), `:817` (in renderHistory()), `:844` (in renderMix()), `:863` (in renderPitchAdd()), `:896` (in renderPlatoon()), `:1003` (in renderProspects()), `:1207` (in pfTable()), after queue 6's org sorting); Management club heading; HoF defunct franchises `data-club-nolink="defunct"` | the listed assets | `test_club_links_render.py` per route at 1280 and 390: every `img[src*="teamlogos/mlb"]` and every `[data-club]` is inside `a.club-link[href]` or carries an allowed `data-club-nolink` reason (row-anchor, unresolved, defunct, self); every href matches `^/franchise/#team=(30 codes)$` or `^(/prospx/)?#farm-org=(30 codes)$`; no `a.club-link` has an ancestor `a, button, [role=button], summary, label, select`; one sampled link per route lands on a page naming the club | none | M | class 1; after queue 6 PAL and queue 7 B6_HOF; Opus |
| L3 | build | PROSPX A17 to A24 under Q-L1: board-family rows (`playerMetaHTML` 38466-38468; Transactions, Injured, Debuted, Leaderboards, Spotlights) move to a stretched primary player link with a separate club link above it (`position:relative; z-index:1`), which also clears the buttons-inside-`role=button` defect; Farm Systems `buildRow` (43797) makes the org name a real `<a href="#farm-org=CODE">`; the player card header org, `_playerOriginHTML` (28286) prose and the rail title; draft cards (24333-24339), results (25322, 25334), signing trends (25762); IFA `.ifa-org-link` (25922) becomes an anchor through the resolver (OAK to ATH); overseas league club column (29148) and signed-team text (26762-26768, 29608-29610); Time Machine `a.tm-row` logos marked `row-anchor` unless Q-L1 converts them; farm detail header and context rail; a reverse "Farm system" link on the Franchise club view if missing | `prospx/index.html`, `assets/franchise.js` | the same render test on the PROSPX routes; keyboard order player link then club link; the draft card's `closest('a,button')` guard (24435) pattern on every converted row | none | M | after Q-L1; `restamp_hand_authored_pages()`; Opus |
| L4 | build | Generated pages A14 to A16: home (`build_site.py@64bf1bb3:1410-1434` (in _row_mover()), 1525-1528, 1556-1560, 1581), the news wire (`:1767-1775` (in _feed_item_html()), 1802-1818; the ticker `:1831-1846` (in _ticker_html()) is `aria-hidden` decoration and stays), history (2376, 2391-2393, 2698; never reuse `_org_from_team_name` for links) through the Python mirror; under Q-L1 (a) the home and news feed rows keep one target and mark their logos `row-anchor`; the full sweep and `gen_audit_docs.py` | `build_site.py` | the render test on `/`, `/news/`, `/history/` | none | S | after queue 3 and queue 6's home_shell lane (same `build_site.py`); Opus |

**Accessibility rules (binding on every task above).** Link text stays the name or code the
surface already prints; no icon-only link where text exists. No interactive content nested
inside interactive content (never inside `a`, `button`, `[role=button]`, `summary`, `label`,
`select/option` or a sortable header; commit `4b7d2509` put `th[aria-sort]` heads on 8 boards):
convert the container first or mark the mention `data-club-nolink="row-anchor"`. Clickable
rows: the club link stops propagation and the row handler skips `a,button` targets. Hit area at
least 24 x 24 CSS px at 390 px (WCAG 2.2, 2.5.8). Tokens only, visible focus, restamp after any
`site.css` change.

**Honesty.** No number moves. The betting change adds links only (the Dugout and priced-cell
fences stay green).

**Dependencies.** L1 any time after step Z (small; it also gives P8.2's Teams tab and P8.8's pages
their hrefs). L1 IS Part 4's census item M13-07 ("Franchise is the club hub, but no module links
back to it", plan line 1098, which proposed `EEPHUS_HUB.clubLink` beside `club()`): if a fixer has
already added that helper, L1 extends it and adds no second one. L2 after queue 6's PAL org sorting
and queue 7's B6_HOF (franchise credit). L3 after Q-L1 and after queue 6's prospx lane. L4 after queue 3 and queue
6's home_shell lane. Stop conditions: any href built from a raw payload code without the
resolver; any substring, suffix or token match; a link inside interactive content; a row handler
that swallows the link; a /betting/ change that adds a number to a priced cell; a `site.css`
change without a restamp.

**Effort.** L1 S, L2 M, L3 M, L4 S; every task fits Opus 5.5.

**Queue tasks.** L1 is Q9_05; L2 is split in two for one sitting each, Q9_06 (MLB Stats, Sports
Betting, Club Ledger, Arbitration, In-Game Management, the Franchise reverse link) and Q9_07 (Trade
Machine, Projections, Free Agency, the fantasy family, the Alchemy Lab, Hall of Fame); L3 is Q9_08;
L4 and the full sweep are Q9_09. The resolver is also what the Scores, F-SCORE, Baserunning and
Staff Gems pages link through (8.E).

**Owner questions raised (defaults in bold; Q-L1 in batch 8, Q-L3 in batch 9).** Q-L1 row targets on PROSPX board-family rows and
the home and news feeds (**PROSPX rows move to a stretched primary player link with a separate
club link, which also clears today's nested-button defect; home and news feed rows keep one
target and mark their logos row-anchor**; convert both; leave every club inside a row unlinked).
Q-L3 logo-only mentions in dense player rows (**link them, with a 24 px hit area and full-name
alt text**; leave them decorative). Default taken: Q-L2, a prospect's club on MLB modules (Trade
Machine prospect rows, dynasty prospects) links to the farm page, which is what the owner's ask
says in its own words.

### P8.4 eFV as the only displayed FV on PROSPX (ask 5; lane links_efv_display, Part B)

**Lane summary.** The rule: where a single grade is displayed, it is eFV; consensus FV appears
only where the spot names it as consensus or as a source grade. The census used a sentinel
method on scratch copies of the payloads (consensus grades set to 76.4, per-source grades to
68.2, eFV grades to 33.4), so any visible 77, 76 or 76.4 is consensus on screen and any 34 is an
eFV rounded up. The fields: E1 graded actives read `xfv.json by_player[key].xfv_grade` through
`getEfv` (31797) and `efvGradeDisplay` (33278-33281, nearest); all 4,686 actives carry one
(1,993 `efv_v2`, 2,687 `provisional_capped`, 6 null basis). E2 provisional rows read
`xfv_ungraded.json` labelled "Provisional eFV" today and, after queue 7's PV_C, the expected
first grade plus the chance of a first grade with the map value relabelled "production grade";
every display routes through `gradeBlock` so PV_C edits one place. E3 debuted players read the
grade locked at debut (2,614 of 2,766 rows; 152 fall back). E4 eFV over time (`xfv_history.json`)
covers 1,905 of 4,686 actives with 2 or more points; 2,781 have no eFV series. E5 IFA rows carry
`fv` on the xfv basis rounded nearest server-side (`ifa_export.py@64bf1bb3:188` (in _enrich()); floor rows follow
M20-2). E6 draft classes have no eFV before signing; `draft_export.py@64bf1bb3:942` (in _ingest()) fills `current_fv`
from `fv_close` (consensus), which feeds "FV now", "Exp", `overperf_fv` and every "vs slot"
figure. E7 overseas has no eFV. E8 org aggregates are already eFV with a consensus fallback
(`storage.py@64bf1bb3:12697-12713` (at 'player_key')). Rounding: eFV nearest (`efvGradeDisplay`; `build_site._round_half_up`
1188-1199); consensus and tool grades up (`fvCeil` 13078-13083); means one decimal; a delta
subtracts the printed integers (33415-33421). Violations found: the country page rounds eFV up
("77 -> 34" on 60 rows per country), `fvBadgeTooltip`, "Top FV" and the farm GFX distribution
round consensus to nearest, and the Time Machine fallback rounds consensus to nearest. Measured
on the served page: `#tab=injured&grade=fv` prints 611 consensus grades, 362 unlabelled; the farm
roster 161, 84 unlabelled; the HS boards 92 (states) and 156 (schools) unlabelled; colleges 302;
Vanderbilt 47; TX 73; NPB 29; the draft rankings 50 per page and the leaderboard 50; the
Overperformers 100; the IFA board's signing grade is named only in a tooltip on 346 rows. The
wiring lane added two off-PROSPX finds: the MLB player page origin line prints the consensus
arc "FV open -> close" (`assets/projections.js@64bf1bb3:3126-3131`, fed by `mlb_player_export.py@64bf1bb3:359-379` (in _debut_origins()))
and Call-up Watch falls back to ceil(consensus) when eFV is absent (`assets/dynasty.js@64bf1bb3:532-533` (in renderCallups()),
`fantasy_export.py@64bf1bb3:985` (in _callup_watch())).

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| E1 | display | Shared helpers B-S1 to B-S8: the Rank-by Consensus toggle (9265-9270, 56654-56670, `grade=fv` 13829-13830, `_gradePrimary` 33498) and the Debuted "Lead grade" toggle (9815-9822) under Q-E1; `efvBadgeHTML`'s consensus branch (33569-33572) and the `gradeBlock` fallback (33297-33318) get a visible "C" mark, a dashed border, the tooltip "Consensus FV (no eFV for this player)" and round up; `fvBadgeTooltip` (11175-11229) says "Consensus FV" and rounds up, and the compare cart's eFV badge (55724-55725) uses `efvTooltip`; `efvCompactBadge` (33587-33594) and the `efvRankValue`/`fvCmpDesc` fallbacks label the chip; first paint before `xfv.json` (`loadEfv` 31744-31756) shows a neutral placeholder and "eFV unavailable" on failure, never unlabelled consensus; the FV sparkline's H/L chips (13290-13312) come from the eFV series, the consensus line is named in the legend, rows with no series say "no eFV history"; `_ohlcTooltip` (13414-13420) reads eFV high and low else "Consensus FV history"; the headshot ring keys on `rarityFvOf` (18544-18561) | `prospx/index.html` | unit tests: `gradeBlock` and the `efvBadgeHTML` fallback labelled and rounded up; `fvBadgeTooltip` rounds up and says "Consensus FV"; the sentinel regression (below) in both modes | pure relabels move no number; the toggle behaviour under Q-E1 | M | after PV_C (it re-routes `gradeBlock`); Opus |
| E2 | display | Farm pages B-F1 to B-F15: Recent movers (52676-52720) on E4 deltas and an E1 badge ("moved >= 5 eFV"); Promotion candidates (52725-52790) gate and badge on E1 ("eFV >= 50"); On the IL (53113) and Recent debuts (52873) on E1 and E3; Toolsiest and Versa watch (52901-52958) sorted on `efvRankValue`; the depth heatmap (52963-53000) sums E1 instead of `fv_close || 40`; Comparable farms (53025) bin `prospects[].xfv_grade`; the promotion ladder (43032, 43048); Positional depth "Top FV" (52016, 52023) as an E1 max with `efvGradeDisplay`; Recent graduates (52043, header 52053) as E3 "eFV at debut"; the roster-tab rail "top by FV" (17399-17410) as eFV; Finances Surplus details (53638-53660) keep the engine value (M9-3) relabelled "Consensus FV" and "Consensus FV 60+"; the farm GFX distribution (52362-52363) bins E1; the trade and waiver scoreboard (41648-41770) shows E1 badges and relabels the tiles "consensus FV net" (the storage sums are farm-grade inputs and are not re-keyed); the alumni badge (43735-43746) on E3, gated on eFV | `prospx/index.html` | the sentinel regression on `#farm-org=CHW` every sub-tab; `test_farm_header_counts.py@64bf1bb3:50` updated deliberately | value swaps in gates and sums move served display numbers (class 3, behind `EFV_DISPLAY_SWAPS`); relabels move none | M | Opus |
| E3 | display | Drill-downs B-DD1 to B-DD8: HS boards (`_hsAggregate` 27609, `_hsRenderLeaderboard` 27852-27855) and the HS entity page (28016-28096), colleges (28393, 28433-28437) and college detail (28563-28577), draftee, class-context and overseas detail (29183-29214, 29278-29296, 29599-29606) and league detail (29094-29137) label the amateur grade "Draft FV (consensus)" or "Consensus FV" and add an "eFV now" column for signed players (E6); the country page signee column (28960-28981) uses `_ifaFvProgHTML(s)` (25955), which rounds eFV nearest and mutes the labelled signing grade, the tiles and global rows (28930-28953) relabel "eFV", and the "FV drift" tile and rows (28934, 28948, 28953, `_countryAggregate` 28719) are dropped or rebuilt on one basis; the Countries board "Shrunk FV" (28758) relabels; B-DD6 switches `draft_export.py@64bf1bb3:942` (in _ingest()) `current_fv` to the eFV grade with `current_fv_basis` "efv" so `expected_fv_for_pick` and `overperf_fv` recompute on it, behind `DRAFT_CURRENT_FV_EFV` (default off) | `prospx/index.html`, `draft_export.py`, draft_export tests | the country signee cell equals `_ifaFvProgHTML`; `draft_export` sets `current_fv_basis` behind the flag; the sentinel regression on `#tab=draft`, the HS, college, country and league routes | relabels move none; B-DD6 moves served numbers (Overperformers, "vs Slot": class 3) and flips after step Z under Q-E3 | M | Opus |
| E4 | display | Boards, card, sorts, CSV B-SB1 to B-PC3: draft cards (24445-24451) and leaderboard (25472, 25489) print a visible "Cons. FV" and "eFV now" for signed players; class strength (25567), War Room, fit chips and Simulate (24633, 24718, 24748, 25121, 25150, 25161, 25181) label consensus; the IFA board header reads "Cons. at signing -> eFV now" with a "C" mark on the muted badge and "eFV pts" (28852); overseas cards, leaderboard and table (26881-26885, 30297, 30367) label "Consensus FV"; the Time Machine fallback pill (20924-20929, 20951-20960) gets a "C" mark and rounds up, eFV rows first and consensus-only rows as a labelled tail (`_tmGradeVal` 21043-21045); scatterplots gain eFV axes (E1, E3 at debut) as the default Y, but eFV at debut is never paired with an outcome axis (Career WAR or any realized MLB statistic) for a debut cohort from `efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR` on until its R-VM look is recorded (those rows drop out of such a pairing with a one-line note), "Prospect FV" becomes "Consensus FV at debut", the "FV >=" filter and colour-by read eFV (`_chartDims` 19183-19200, 10249-10252, 19419-19426); Transactions sorts on `efvRankValue` with the header "eFV · stock" (21973-22000) and the trade audit party badge, tooltip and side totals (22601-22667) switch to E1 (coordinate with queue 7 M9_M10 and M9 realized leg); Debuted `classStrengthStrip` (31472-31474) on E3 nearest and the header "eFV" (31199); IL and Leaderboards headers say "eFV" (21676, 9487, 20765); board sorts "Upside first" (16060-16074), "Stock movers" (16217-16226) and the Tool tiebreak use `efvRankValue` and E4 movement, the named "Consensus FV" sort stays; the quick-read (38584-38587) prints "eFV 61"; the header range line (48064-48091) reads E4 nearest or "Consensus range" rounded up; the eyebrow (48016-48020) reads "eFV N · consensus M"; the board CSV keeps `efv`, `efv_printed`, `consensus_fv`, `consensus_fv_printed`, `basis` and names M8-2's per-source columns by source; the sentinel regression test ported from `build_taint.py` and `probe_fv.py` (temp-dir payload copies, never `data/`; no visible or FV-headed cell prints 76, 77 or 76.4 unless its container carries `data-grade-basis="consensus"` or a source name; no eFV prints 34; both modes) | `prospx/index.html`, `test_prospx_efv_sentinel.py` (new), `test_prospx_board_csv.py@64bf1bb3:101` (in test_the_download_holds_the_whole_filtered_board()), `test_prospx_consensus_sort.py`, `test_ungraded_orphan_routing.py`, `test_ifa_floor_display.py`, `test_ifa_export.py@64bf1bb3:74-75` (in test_signing_vs_current_enrichment()) (`fv_signing` stays consensus) | the sentinel regression on every route in B.2 to B.4 | relabels move none; sort-key swaps reorder rows (class 3, same flag) | M-L | after PV_C and M9_M10; Opus |
| E5 | display | Off PROSPX under Q-E4: the home Top Movers sparkline (`build_site.py@64bf1bb3:2100-2110` (in _fv_sparkline()), 1412-1428) and the wire's `_mover_unit` (1405-1408, 1673-1678) label consensus-basis moves; `/pal/` Prospect Watch (`assets/pal.js@64bf1bb3:986-989` (in gradeText()), open item G06) prints eFV first; the /projections/ Team Outlook top prospect reads `xfv_grade` instead of `fv_label` (`proj_export.py@410cccce:1863-1871`, `projections.js@64bf1bb3:1040-1041`); the Trade Machine FV fallback (1003-1027) is labelled; the MLB player page origin line prints the eFV arc (open at grading -> at debut) with the consensus arc labelled; Call-up Watch labels its consensus fallback | `build_site.py`, `assets/pal.js`, `proj_export.py`, `assets/projections.js`, `assets/trademachine.js`, `mlb_player_export.py`, `fantasy_export.py`, `assets/dynasty.js` | string tests per surface; `tools/export_trade_values.py` after any `proj_export` run | relabels; the Team Outlook top-prospect value changes (class 3, flag) | S-M | Q-E4; Opus |

**Where consensus stays, named and never replaced.** Source Comparison in the glossary
(SC_HEADLINE_HOLM owns it); the per-source tables (50085, "FV as PUBLISHED" 50205); the FV tape
and source history (47549-47797); the detail header reference line "Consensus FV N · eFV +-d"
(33676-33681); the consensus clause in `efvTooltip` (33456-33459); the "At a glance" signal
(17085); the "Consensus FV" sort option and axes; the CSV consensus columns; the eFV track-record
tables (32860-33060, the registered scoring frame); Star Odds (the FanGraphs tier value at
consensus FV, 37371-37410); labelled IFA-at-signing, draft and overseas amateur grades; the
wide-spread and "+" upside marks from the sources (11693-11698, 11808-11830).

**Not display, so never re-keyed here (stop conditions).** The WAG anchor (`fvExpectedWarPerYr`
22744, already eFV via `engine_at_debut`); farm-grade inputs (org `fv_history` credit
`storage.py@64bf1bb3:8635-8831` (in _build_org_fv_history()); tx `net_fv` 14538, 14714; the M9-3 engine value; PG-Q2 freezes farm
points and trade values until 2027-04-15); trade values, P(bust) and the surplus engines; Star
Odds. Never compute a realized statistic by FV cell to check a switch (PROSPECT_ANCHOR_GATE: one
look, not before the later of 2026-11-20 and step Z + 14 days); never read a reserved eFV frame;
do not touch eFV V2 serving or its claim; do not pre-empt PV_C (route through `gradeBlock`
only); never round an eFV up or a consensus grade to nearest.

**Honesty status.** Pure relabels (words only) move no number and ship as built (class 1). Value swaps in gates, sums, sorts and axes, and every rounding fix that changes a printed digit (the country page's '77 -> 34', the consensus tooltips and Top FV rounded to nearest, the Time Machine fallback), change what a reader sees on farm and detail pages, and B-DD6 moves served draft numbers; those build behind `EFV_DISPLAY_SWAPS` and `DRAFT_CURRENT_FV_EFV` (class
3) and flip after step Z. `EFV_DISPLAY_SWAPS` is defined once, as `storage.EFV_DISPLAY_SWAPS`, emitted
into the PROSPX payload the page reads and imported by `proj_export.py` for the Team Outlook top
prospect; its flip (Q9_15) is one commit that re-runs the storage export, `proj_export` and then
`tools/export_trade_values.py`. No model input, served engine or accuracy claim changes.

**Dependencies.** After queue 7's PV_C (provisional section and receipts), M7_M8 (per-source CSV
columns), M9_M10 and M9 realized leg (the trade audit code E4 touches). E5's /pal/ line is
G06's shipped default A, so Q-E4 is asked once for both.

**Effort.** E1 M, E2 M, E3 M, E4 M-L, E5 S-M; all Opus 5.5.

**Queue tasks.** E1 is Q9_10; E2 Q9_11; E3 Q9_12; E4 Q9_13 (with the sentinel test); E5 Q9_14; the
flip of `EFV_DISPLAY_SWAPS` and `DRAFT_CURRENT_FV_EFV` is its own task, Q9_15, after step Z and the
answers, with the blast radius in its commits.

**Owner questions raised (defaults in bold; batch 6 of 8.G).** Q-E1 the Rank-by Consensus toggle and the
Debuted Lead-grade toggle (**they order the board only; grades stay eFV with a labelled
consensus chip**; keep the swap but mark every consensus badge "C"; remove the toggle). Q-E2
amateur and overseas boards where no eFV exists (**label them "Consensus FV" / "Draft FV
(consensus)"**; hide the grade). Q-E3 draft `current_fv` on eFV (**switch behind the flag, flip
after step Z**; keep consensus and label it). Q-E4 extend the rule to PROSPX-derived FV on other
pages, which re-asks G06 for /pal/ (**yes**; PROSPX only).

### P8.5 The financial module into Free Agency and Arbitration (ask 3; lane finance_to_fa_arb)

**Lane summary** (`<part8>/finance_to_fa_arb.md`; HEAD source copies in `<part8>/fa_arb_head/`).
The Fit already scores "which teams spend": BEHAVIOR carries weight 0.45, the largest of five
(`fa_config.yaml@64bf1bb3:156` (in fit)), and reads each club's own major-league-deal history from the signings
corpus (`fa_fit.py@64bf1bb3:954-986` (in behavior_priors())): the share of the club's past guarantees at least this large, plus
its last-three-winter outlay and deal count inside the player's price band (`:1115-1139`, band
`[g/2.5, g*2.5]`). Payroll space alone is indistinguishable from random: on the Gate 3 backtest
(1,173 signings, winters 2018-2026) `payroll_only` MRR is 0.1350 against random 0.1332, inside
the frame's 0.0139 floor (`data/fa_gate3_eval.json`); the final-winter logistic without
incumbency signs the space term negative (clubs with LESS space sign more), so what payroll
carries is its level, not its room. The one large signal the product leaves out is re-signing:
the backtest's own logistic with incumbency reaches MRR 0.2679 and top-1 0.1787 against the served
analog's 0.1669 and 0.0520, excluded "by product design"
(`docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md@64bf1bb3:83` (under '## Clauses')). What the owner most likely saw: on the
served 2027 class (`fa_class.json`, 232 priced members with fits) CHW is the first fit for 50 and
WSN for 46, while the two clubs took 1.4 and 0.7 percent of league free-agent dollars over the
2024-2026 winters ($129.3M and $69.5M of $9.45B); all 96 are cheap players (median projected
guarantee $2.6M and $3.2M, none at $20M or more), where need is near zero for every club (the
1.0-WAR floor, `fa_fit.py@64bf1bb3:1088` (in fit_scores())) and the banded will-spend term decides; the 9 members priced at
$50M or more have first fits NYY 4, NYM 3, LAD 1, PHI 1. The concentration tripwire passes at
0.2155, so this is not a defect by the Fit's gate; a fit RANK cannot say how flat the cheap end
of the market is, a calibrated PROBABILITY can. The Fit stays byte-identical (its will-spend term
is the product of four gated repairs and any other behavior-only rewrite is barred,
`fa_fit.py@64bf1bb3:1117-1131` (in fit_scores())); Gate 2 and the frozen Gate 3 artifact stay untouched (the lab imports
`fa_fit_backtest.build_rows` and never calls `run_fit_gate(persist=True)`); the spending signal
goes into a new registered object beside the Fit. Arbitration today knows nothing about the
process: no filing figure, settlement date or hearing flag is served (`build_site.py@64bf1bb3:3955` (in _arb_model_panel())), the
club on a history row is the club of the award season's last stint (`arb_dataset.py@64bf1bb3:127` (in _collapse()), `:184` (in war_daily_spine());
Tarik Skubal's 2026 award reads LAD $32.0M while the cached MLBTR tracker lists him under the
Tigers heading; the Ledger's LAD realized 2026 of 7 cases and $55.8M contains a Detroit case),
and the award band is deliberately uncalibrated (`arb_export.py@64bf1bb3:251-258` (in build_board())). The MLBTR trackers on
disk (2024-2026) carry 30 club headings and 57 exchanged cases (22, 17, 18) that the parser drops
(`tools/ingest_arbitration_ledger.py@64bf1bb3:103-109` (in _OUTCOME_PATTERNS)); its hearing classes never fire because the cached
pages are January snapshots.

**Three legs and the reverse wiring.**

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| FAA-0 | registration | `docs/fa-2026-10/FA_DESTINATION_GATE.md`, committed alone: registry row `fa_destination` predicting P(club signs player given a major-league deal this winter), a 30-vector per free agent summing to 1; frame the Gate 3 forward chain (winters 2018-2026, `fa_fit_backtest.build_rows`) with step 0 reproducing the registered numbers bit-exact (random 0.1332, payroll_only 0.1350, behavior_only 0.1515, live_analog 0.1669, fitted_full 0.2679 on its 1,080), the PRIMARY frame replacing the price input with Gate 2's forward-chained predicted guarantee and AAV through the `GATE2_COLLECT` hook (`fa_backtest.py@410cccce:486-491`, `:603-607` (in run_market_gate())) with `persist=False, persist_dpw=False` (the Gate D precedent, `tools/arb_fa_gate_d.py@64bf1bb3:123-130`) and an optional price-override argument on `build_rows` whose default leaves the Gate 3 rows byte-identical (row-hash test); features F fit_analog (the Fit's backtested reduced twin), L1 fa_share_3 (club share of league NPV guarantees, winters Y-3..Y-1), L2 payroll_level (z of the club's Y-1 CBT tax payroll), L3 tax_multiplier (1 + the marginal CBT rate on his predicted AAV at the club's tier, through `computed_cbt_bill` `ledger_export.py@410cccce:305-341`), L4 qo_cost, I1 incumbent (per FA-DEST-1); a conditional logit over the 30 clubs fitting only tau, beta (fixed L2 penalty written before any fit) and gamma; arms P (fit_analog + L1-L4), N (fit_analog alone), L_perm (L1-L4 permuted across clubs within each winter); baselines random, payroll_space, payroll_level, behavior_only, live_analog, incumbency_only; metrics top-1/3/5, MRR, multinomial log loss (uniform ln 30 = 3.4012), reliability slope and ECE; floors paired MRR MDE95 0.0139 and a log-loss floor from the same cluster bootstrap (unit one signing with its 30 rows, B 2,000, seed 7) written before any arm is read; clauses C1 (beats payroll_space and payroll_level on MRR by more than MDE95 and on top-5), C2 (beats live_analog on MRR by more than MDE95), C3 (the ask's own test: P beats N on MRR or log loss after Holm, and L_perm reproduces under 60 percent of the P minus N lift), C4 (out-of-fold log loss below ln 30 by more than its floor; reliability slope 0.8 to 1.2), C5 (P at or above payroll_space MRR in at least 7 of the scored winters); ship rule (all five: serve P; C3 fails: serve N and record the Ledger block as a NULL in the loss ledger; C1 or C2 fails: serve nothing); the forward read on the 2026-27 class only if frozen before the QO acceptance deadline, else the 2027-28 class; the MLBTR named-team comparator; the lockout clause; under FA-DEST-1 (a) the statement, before any number, that C1 and C2 are expected to pass from re-signing alone (incumbency already scores MRR 0.2679 against the analog's 0.1669 on these winters), so only C3 answers the owner's ask; a 'Read to write this' section disclosing every read of this frame that shaped the design (the no-incumbency final-winter logistic whose negative space term motivated `payroll_level`, `fitted_full`, the per-winter and final-winter refits, the served first-fit counts and the dollar shares) | `docs/fa-2026-10/FA_DESTINATION_GATE.md`, registry note | `test_fa_destination_gate.py`: the doc's protocol hash, the clauses and floors present, the 'Read to write this' section present, no number in the results section | predictive, registered, unread | S-M | after FA-DEST-1, FA-DEST-3, FA-DEST-4; Fable 5.1 |
| FAA-1 | registration | `docs/ARBITRATION_GATE.md` section 12 in two commits: FIRST, alone and before the tracker re-capture (FAA-3) and any club label (FAA-4) exist, 12b with its frame, label rule, thresholds, power precondition and a scored-winter rule (only winters captured after the registration, the January and February 2027 captures on, because the 2024-2026 pages were read to design it, disclosed under 'Read to write this'), 12c and 12d; THEN, by a dated amendment after GATE C2, 12a band calibration (out-of-fold residual quantiles by rung and chain depth from the champion's forward-chained residuals; coverage target 0.80 for P10-P90; interval score against the fixed band; player-clustered floors; the M12-4 league-minimum floor on both bands); 12b one scale multiplier on the calibrated band for cases at clubs labelled "File and trial" from winters strictly before the case's, with a power precondition written first (about 62 scoreable cases at 0.80 coverage for a coverage MDE95 of 0.10; short of that a pre-committed NULL, the A6 precedent); 12c what never moves (the champion point award, the frozen feature tuple, `projectable_keys`; the banned-key test in `test_arb_export.py` extends to every club-process key); 12d the response | `docs/ARBITRATION_GATE.md` | a doc-section presence test naming its look order and the scored-winter rule | predictive, registered, unread | S | 12b first, after ARB-CLUB-2 and before FAA-3 (Q9_17a); 12a after the M11/M12 sequence, GATE C2 scored (held by M12-1) and B5_ARB registered (Q9_20); Fable advisory |
| FAA-2 | build (Leg A) | The club FA spend profile, descriptive: per club in the shard (`data/ledger_clubs/CODE.json`, 84-97 KB against a 160 KB cap) the share of league free-agent guarantee dollars (nominal, reconciling to the Spend by winter table) over the last 3 winters and since 2015 with rank of 30, the band mix (under $10M, $10-50M, $50-100M, $100M+), the re-sign share of departing free agents who signed major-league deals, QO in and out, and payroll and CBT tier by season 2016-2026 parsed from the cached `spotrac_tax_2016..2027` and `spotrac_payroll_2017..2027` pages (which lights the dark `payroll.history` block and IS plan item M09-09's cache-only seam, network structurally disabled); one league column "FA $ share, 3 winters"; Franchise MARKET gains the two shares and the band mix; glossary; registry row `club_fa_spend_profile` (provisional, `provisional_kind` `measurement_only`, `eval_artifact` null, "descriptive, no forward claim" in `baseline` and `metric`: a served payload is not an evaluation); copy "Share of league free-agent dollars, by the winter each deal was signed. Realized spending, not a forecast." | `fa_sources.py`, `ledger_export.py`, `franchise_export.py`, `assets/ledger.js`, `assets/franchise.js`, `data/glossary.json`, `data/model_registry.json`, `test_club_fa_profile.py` | winter shares sum to 1 over 30 clubs within 1e-9; the club's dollars equal the Spend by winter cell exactly; payroll history rows reproduce the cached tax-page parse and each prints its own season's threshold; a monkeypatched socket proves no network; the key walker still refuses `projected_payroll` and `payroll_forecast`; the built board keeps `shards.preview_n == 10` with its full-preview size at or under `PREVIEW_GUARD_BYTES` (950,000) after the new column, so the owner's VAL1-Q1 answer is not undone silently; every shard under 160,000 (re-measure the largest after the trajectories move into the shards) | descriptive; WAR-free | M | class 2 behind `LEDGER_FA_SPEND_PROFILE`; after queue 8's LEDGER_TRIM_PREVIEW_10 and M13's board changes (at `410cccce` the full-preview board measured 955,452 bytes against the 950,000-byte guard, so `data/ledger_board.json` fell back to 5 preview rows at 934,587 bytes; the trim restores 10 and this item must keep them); Opus |
| FAA-3 | lab data (Leg C) | The tracker parser records the club heading on every row; one dated re-capture of the 2024, 2025 and 2026 tracker URLs (MLBTR keeps them updated through the February hearings) under a new dated cache key so the permanent January snapshots and their committed sha1 stay reproducible (`tools/ingest_arbitration_ledger.py@64bf1bb3:20-25`); the three "Players Exchange Filing Figures" posts for the player and club numbers; six requests in one invocation under the tool's own limits (8 s delay, 6 per run, circuit breaker); from this winter an exchange-day capture (January 2027) and a post-hearing capture (February 2027), the filing-vs-award half of plan item M08-15; the attribution rule: a case belongs to the club under whose heading the tracker lists the player on exchange day, never `arb_history`'s season-end club (Skubal 2026 is a Detroit case; the FP2-4 spirit) | `tools/ingest_arbitration_ledger.py`, `data/_labs/arb_ledger.json` (after M23-3's move) | parser fixtures on the three cached pages give 22 / 17 / 18 exchanged and 30 club headings each; Skubal 2026 attributes to DET; hearing lines classify on a fixture | lab file, not served | S | after M23-3 and after FAA-1's 12b pre-registration (Q9_17a); ARB-CLUB-1; Opus |
| FAA-4 | build (Leg C) | Chips per club (window = the captured winters, n and window on every chip, no colour): Cases, Exchanged (n and share), Hearings (n and W-L from the re-capture on), and a label only when the data carry it ("File and trial" when exchanged >= 2 and settled after the exchange = 0; "Settles before the exchange" when exchanged = 0 on at least 10 cases); `/arbitration/#teams` gains Cases and Exchanged columns and the label, the club-narrow view a Process card, the Ledger's dark "Filing figures and hearings" block lights per club, Franchise ARBITRATION gains the chips; registry row `arb_club_process` (descriptive); copy "Process record from the MLB Trade Rumors arbitration trackers, credited to the club that held the player on exchange day. Descriptive; it changes no projected award."; plus FAA-9: the Ledger realized-arbitration block labels its season-end-club basis and names traded cases | `arb_export.py`, `assets/arbitration.js`, `ledger_export.py`, `assets/ledger.js`, `franchise_export.py`, `test_arb_club_process.py` | every chip carries n and window; no label below its floor; the banned-key test fails if a club-process key reaches `projectable_keys`; `arbitration.json` under its 220,000-byte cap (+5 KB of 57 KB headroom); renders at 1280 and 390 both themes | descriptive; the point award never reads club features (`docs/ARBITRATION_GATE.md@64bf1bb3:239-244` (under '## 4. GATE A - the per-player model')) | M | class 2 behind `ARB_CLUB_PROCESS_CHIPS`; Opus |
| FAA-5 | lab + look (Leg B) | `fa_destination.py` (the ONE feature builder the lab and the export import), `tools/fa_destination_lab.py`, the optional price override on `build_rows`, `data/fa_destination_eval.json`, the registry row; the one gate read per FAA-0, in a separate task from the build, under the crash protocol (a dry run of the reporting path on fixtures with nulls, stdout teed first, STOP without rerun on any exception) | `fa_destination.py`, `tools/fa_destination_lab.py`, `fa_fit_backtest.py`, `data/fa_destination_eval.json`, `data/model_registry.json`, `test_fa_destination.py`, `test_fa_destination_byte_identity.py` | each member's 30 probabilities in (0, 1) summing to 1 within 1e-9; identical inputs give identical bytes; a winter-Y signing cannot change any feature of winter Y (leak fixture); `build_rows()` without the override reproduces the registered Gate 3 rows and five arm metrics; the lab never writes `fa_gate3_eval.json` and never calls `fa_export` (both monkeypatched to raise); with the flag on and off `fa_class.json`, `fa_meta.json`, `fa_gate2_eval.json`, `fa_dpw_series.json`, `fa_gate3_eval.json` byte-identical; the gate document's protocol hash equals the artifact's; the registry verdict matches | predictive; artifact and registry only | M-L | after FAA-0, the M14-2 Gate 2 re-save and epoch step Z (prices on fWAR); the lab must never trigger M14-1's auto re-export; Fable 5.1 |
| FAA-6 | serving (Leg B) | `data/fa_destinations.json` (about 30 KB: `{model_id, generated_at, class_year, arm, coef_hash, members: {key: {top: [[org, p] x 8], rest_p}}, clubs: {org: {expected_mlb_deals}}}`, counts only, no club dollar figure); /fa/ board "Likely destination" column, card "Where he signs" (top 5 with P and the three largest drivers), Fits view "P(signs)" beside Fit with the head note "Fit asks whether he helps them; P(signs) asks whether they sign him."; `/fa/#view=model` shows the Gate 3 table (census M04-14, invisible today) and the destination receipts from the artifacts; pending-option members read "if he reaches the market" and P(enter) is never multiplied in (the frozen P(enter) eval clock 2026-10-01 to 2027-01-31 is untouched); expected deal COUNTS per club beside realized means 2018-2026; the served `coef_hash` equals the artifact's; claims-freshness pins any printed number | `fa_export.py`, `assets/fa.js`, `data/glossary.json`, `test_claims_freshness.py` | the served vector reproduces from the frozen coefficients; no client code multiplies P(enter) into P(signs); renders of board, card, fits and model views at 1280 and 390 | predictive, served only on a pass and the owner's flip | M | class 2 behind `FA_DESTINATION_SERVE`: while it is off the payload goes to `.cache/fa_destination/preview/` and `data/fa_destinations.json` appears first in the one flip commit with the glossary; on a FAIL the Model view (the Gate 3 table and the loss record) ships behind its own `FA_MODEL_VIEW_LIVE`; Opus |
| FAA-7 | registration + build | R3 "expected after free agency": the headline roster WAR minus every locked free agent's 2027 WAR, plus for each priced class member P(club given player) times his year-1 WAR (the re-sign term is the from-club's own P; unpriced members add nothing; pending-option members stay where the headline puts them), served beside the headline on /projections/ and in Franchise OUTLOOK from the day after the QO deadline to Opening Day, never replacing the headline or the Index input under OUTLOOK-1 (a); its own registration first (freeze both frames on the destination freeze date; score both against actual 2027 wins with the registered MAE as a separate arm; the registered gate untouched) | `docs/`, `proj_export.py` (a separate field), `franchise_export.py`, `assets/projections.js`, `assets/franchise.js` | the field reproduces from `fa_destinations.json` and the headline; `tools/export_trade_values.py` after the run | predictive, registered; a labelled second figure | M | after FAA-6 passes and OUTLOOK-1; registration Fable, build Opus |

**Queue tasks.** FAA-0 is Q9_02 (a head task: the gap if a slot is free, else the first slot after
step Z); FAA-5 is Q9_04a (the build) and Q9_04b (the one look), run immediately after queue 7's M14
lands, so the model can freeze before the qualifying-offer acceptance deadline, about mid-November,
and give the 2026-27 class a forward read; FAA-2 Q9_16 (after queue 8's LEDGER_TRIM_PREVIEW_10);
FAA-1's 12b pre-registration Q9_17a (before the capture); FAA-3 Q9_17; FAA-4 with FAA-9 Q9_18; FAA-6
Q9_19 (on a FAIL it still renders the Gate 3 table and the loss record in the Model view behind its own
flag, finding F-6); FAA-1's 12a amendment Q9_20; FAA-7 Q9_21 (only on a pass and under OUTLOOK (a) or
(b)); FAA-8 is not a task but the orchestrator's note appended to queue 7's M13 spec file (8.C action 4).

**Reverse wiring, the full matrix (served, queued, lead, closed, barred, new).** Arbitration
ladders into Ledger commitments (`ledger_export.py@410cccce:924-941` (in build_all())) and the arbitration board into
Ledger C5 and Franchise ARBITRATION (`:1009-1043`; `franchise_export.py@64bf1bb3:767-801`): SERVED.
Arbitration into the Cost+ denominator (M13-4), prospect arbitration through the model (M11-3),
the 80 percent max-cut after a contracted season (M11-2), FA option prices into the options
calendar (M13-3, M14-4), the FA realized ledger rebuild (M14-3), Ledger CBT into the Trade
Machine (M27-4): QUEUED in queue 7. Projections WAR into arbitration WAR on three pages (X03-14)
and the arbitration last rung into the 2028 and 2029 classes as a display-only platform salary
(X03-13): plan leads, not queued. Arbitration into the FA market price: CLOSED, a recorded NULL
(`data/arb_fa_link_eval.json`). FA destinations into Ledger commitments in dollars: BARRED by
the Ledger's NEVER list (`ledger_export.py@410cccce:14-20`, `:187` (at 'FORBIDDEN_KEY_FRAGMENTS')); arrivals may enter only as the
player-level probability ("Likely arrivals": the members with the highest P for the club, each
with his own P and projected guarantee), never as a club sum of dollars. The real gap is R3: Team
Outlook is a pre-free-agency frame (`proj_export.py@410cccce:1921` (in _team_outlook()); `_last_controlled_season`
`:1668-1715` keeps a veteran without a live contract on his club for the first projected season
when he is 29 or older). On the 2026-09-27 `mlb_projections.json` (working tree, gitignored)
the finance lane counted 172 of 190 locked free agents carrying a 2027 WAR on their current club,
84.5 of 961.8 roster WAR (CHC 11.2 of 41.1, 27.3 percent; HOU 5.9 of 27.5; SDP 5.5 of 30.4; SEA
6.1 of 35.2; LAD 7.1 of 52.6, Skubal at 4.2 behind Ohtani's 6.4). Consumers: the /projections/
2027 headline, the Franchise OUTLOOK branch (graded, 0.30 of the Index), the Fit's WINDOW
baseline (`fa_fit.py@64bf1bb3:750-782` (in _outlook_wins())) and the Cost+ numerator, whose denominator no longer carries
their pay. That frame is P8.6's W03 and the merged OUTLOOK question (8.D rows 4 and 5); under every
OUTLOOK answer the Fit keeps reading the pre-free-agency frame and stays byte-identical, because
repointing its WINDOW is a Gate 3 lever (F-1, F-2) that needs its own registration, so the Fit
tables Q9_04b freezes are the pre-free-agency ones.

**Findings for the Fit's own maintenance (leads, not built here).** F-1 the served AFFORD reads
the class-year page (2027 forward space, `fa_fit.py@64bf1bb3:933` (in affordability())) while Gate 3 scored Y-1 season space
(`fa_fit_backtest.py@64bf1bb3:349` (in build_rows()), `:391-394` (in build_rows())), so the served afford has never been scored on its served
definition (any repointing is a Gate 3 lever with its own registration). F-2 the Fit's WINDOW
reads Team Outlook wins that include departing free agents while NEED drops them
(`fa_fit.py@64bf1bb3:584-586` (in _projected_roster())). F-6 Gate 3 is invisible on /fa/ (FAA-6 renders it). Rejected forms and
why: rewriting the Fit's behavior or afford with Ledger data (the R6.3 bar; the recorded
one-for-one trade of concentration against MRR); Ledger space or projected arbitration into the
live afford (the historical afford cannot be rebuilt with projected arbitration, so the served
input would again differ from anything scored; print both space bases labelled instead);
destination or spending into the market price (Gate 2 frozen; Gate D NULL); club effects in the
arbitration point award (the section 4 ban); a club FA-dollars forecast on the Ledger (NEVER
list); market-size keys on the Ledger (`FORBIDDEN_KEYS`).

**Honesty status.** Leg A is descriptive (registry `club_fa_spend_profile`, verdict provisional,
no forward claim). Leg B is predictive and registered before any number: the registered contrast
"with versus without the Ledger block" (C3) is the direct test of the owner's ask; with re-signing
in (FA-DEST-1 (a)) a serve is expected from incumbency alone, so a serve says nothing about the
Ledger unless C3 passes, and a null there is a real possibility (the Fit's analog MRR 0.1669 leaves little room; no refit of its five
features has beaten it: 0.1479 per-winter, 0.1660 final-winter). Leg C's chips are descriptive
(registry `arb_club_process`); a club term enters the award BAND only under section 12 after
its power precondition, and the point award never reads club features. Inputs that will move the
served destination vector without touching its gate: `projGuar` (M14-2's re-save, VAL_1, the
epoch's step S), the 2026 standings and Spotrac pages, and the class itself as options resolve.

**Dependencies.** VAL_1 committed (the files carry its patches); M13 board changes and the
COSTPLUS-1 answer; M23-3 (the arb ledger move); M14-2 (Gate 2 re-save) and step Z before FAA-5;
the M11/M12 sequence, GATE C2 and B5_ARB before FAA-1; P8.6's W03 for the winter frame. Nothing
here reads a betting clock, a PROSPECT_ANCHOR cell or a reserved eFV frame, and nothing scores
GATE C2 (held by M12-1).

**Landing rule.** FAA-0 and FAA-1 docs, any writer slot after their answers, alone. FAA-3 lab
file, any time after M23-3. FAA-2, FAA-4 and FAA-9 behind flags, flipped after step Z (class 2).
FAA-5 after step Z and M14-2. FAA-6 and FAA-7 only after their gates and the owner's flip.
Nothing here can land before 2026-10-04 behind queue 7. The most useful date is before the
2026-12-01 CBA expiry, when a lockout would freeze signings.

**Effort.** FAA-0 S-M (Fable), FAA-1 S (Fable), FAA-2 M, FAA-3 S, FAA-4 M, FAA-5 M-L (Fable),
FAA-6 M, FAA-7 M (registration Fable, build Opus).

**Owner questions raised (defaults in bold; COSTPLUS-1 in batch 1, OUTLOOK and FA-DEST-1 in batch 2,
FA-DEST-3, FA-DEST-4 and the two ARB-CLUB questions in batch 3).** FA-DEST-1, merged with FA-DEST-2:
should /fa/ serve a registered "where he signs" probability, with re-signing in it, while the Fit
stays byte-identical (**yes; a serve is then expected from re-signing alone, and only C3 answers the
ask**; without re-signing; a Gate 3 lever moving Ledger spending into the Fit
itself, which moves every fit list and is unlikely to pass; Fit only with the spend profile).
COSTPLUS-1 the Cost+ numerator for the queued M13 builder (**take locked free agents' 2027 WAR
out of the numerator in the same commit**; keep the roster and name the mismatch). OUTLOOK-1,
merged with the wiring lane's W-OQ1 (8.D row 4). ARB-CLUB-1 (**chips from the trackers on disk plus the
6-request re-capture and the two captures each winter**; also backfill 2011-2023 from Cot's,
which needs the X05-20 terms ruling; no chips). ARB-CLUB-2 (**register section 12 as a document: 12b before the tracker re-capture,
12a by amendment after M11/M12 and C2; the point award never reads club features**; chips only; also
test club process in the point award, which collides with the section 4 ban). FA-DEST-3 the
comparator (**keep MLBTR's predicted team in the November capture, forward only**; also fetch the
2015-2025 top-50 posts once for a retro on about 500 players; none). FA-DEST-4 a market-size signal
(**none in the first registration: payroll level and dollar share carry the club effect**; a second
arm on StatsAPI attendance, which needs the open X05-09 call and stays off the Ledger; a
metro-population arm).

### P8.6 New cross-module wirings (ask 4; lane wiring_ideas)

**Lane summary** (`<part8>/wiring_ideas.md`). The lane read Part 4's wiring rows, Part 5.2
(X03-01 to X03-25), the X05 to X07 leads, every answered decision, the do-not-reopen lists, the
betting clocks and queues 3, 6 and 7 before proposing anything, so nothing below duplicates a
served, queued, registered or closed item. The owner's 11 examples became 15 rows: 7 are already
served, queued, registered or closed (PAL arsenal and aStuff+ on prospect pitcher cards, served
at `prospx/index.html@64bf1bb3:31701-31720` (at 'stuff_plus_aaa'); Stuff+ in eFV V2's admission queue, `DRIVER_SYSTEM_V2.md`
ideas 7 and 8; parks into betting and DFS, `betting_model.park_index_from_meta` and
`dfs_export.py@64bf1bb3:42-48` (at 'fa_meta'); management tendencies into betting, 5l; CollegeSavant into the draft board,
M20 and M03-06; Ledger space into FA fit, X03-21 and P8.5), 1 belongs to P8.9 (Team Outlook wins
into the intensity index), 3 are blocked or not recommended (weather into DFS until 5h's read and
L2's attribution rule, the earliest honest form a display-only forecast chip on 2027 DFS cards;
CollegeSavant into the mock draft, which beats consensus by 0.03 picks on the one scored draft;
the arbitration model into fantasy keeper costs, which are draft picks by design,
`assets/dynasty.js@64bf1bb3:447-456`; IL into projections playing time, closed until 2027 after the W1
PT-RISK fail), and 4 became proposals. Seventeen new wirings are ranked by V x H x E (value,
honesty, effort; the scores are judgement, printed so this part can re-weight them); the top 8
are BUILD. One proposal, W03, corrects a graded served number and is the most consequential item
in this family.

| Rank | ID | Wiring | V | H | E | Score | Ready | Queue |
|---|---|---|---|---|---|---|---|---|
| 1 | W01 | MLB transactions into MLB player pages, the wire, This Day and an FA IL column | 5 | 5 | L | 50 | now | p8_wiring Q9_22a, Q9_22b, Q9_22c |
| 2 | W02 | PROSPX IL and Tommy John status into Dynasty and Call-up Watch rows | 3 | 5 | S | 45 | now | p8_wiring Q9_23 |
| 3 | W03 | FA status and signings into Team Outlook's winter frame, then Franchise and Cost+ (the FA Fit stays on the pre-free-agency frame) | 5 | 4 | M | 40 | after the merged OUTLOOK question | p8_wiring head Q9_03 and the dated freezes Q9_03a to Q9_03e |
| 4 | W04 | Provisional P(first grade) as a Dynasty 'Next to be graded' lens | 3 | 4 | S | 36 | after PV_A, PV_B and PV_C | p8_wiring Q9_24 |
| 5 | W05 | The HoF shelf on MLB player pages | 3.5 | 5 | M | 35 | now (S after X03-10) | p8_wiring Q9_25 |
| 6 | W06 | PROSPX graduates into MLB Stats (chip, debut-season filter) and the player page origin block | 4 | 4 | M | 32 | now (AAA line after M25) | p8_wiring Q9_26 |
| 7 | W07 | Trade Audit comparable real trades in the Trade Machine | 4 | 4 | M | 32 | after M9 | p8_wiring Q9_27 |
| 8 | W08 | Franchise, Ledger and Outlook into a Trade Machine partner screen (v1 descriptive) | 5 | 3 | M | 30 | now (v1) | after W-OQ4 (not queued; spec below) |
| 9 | W09 | Spotlights flags on Dynasty rows | 3 | 3 | S | 27 | after B4 re-score | later |
| 10 | W10 | Park factors on PROSPX cards and MLB player pages | 3 | 4 | M | 24 | after M07-04 | later |
| 11 | W11 | Sprint speed and pop time in the Management steal family (stage 1 display; stage 2 registered) | 3 | 4 | M | 24 | W-OQ3 | later |
| 12 | W12 | Competitive Balance picks as Trade Machine assets | 3 | 4 | M | 24 | after VAL_1 | later |
| 13 | W13 | Odds implied totals in Redraft streamers (a registered arm on the start-score protocol) | 2.5 | 4 | M | 20 | gate before OD 2027 | later |
| 14 | W14 | FA fit need v2: positions played and handedness complement (two arms, one Holm family) | 2.5 | 4 | M | 20 | gate before the first signing | later |
| 15 | W15 | PAL reads on MLB pitcher pages and MLB Stats cards | 3 | 3 | M | 18 | now | later |
| 16 | W16 | Team Outlook rosters as 2027 opponent context for Fantasy (a registered arm) | 3 | 3 | M | 18 | gate before OD 2027 | later |
| 17 | W17 | DvM+ on Trade Machine prospect rows | 3 | 2.5 | M | 15 | after VAL_4 and P8.7 | later |

**The eight BUILD items.**

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| W01 | build | League-wide StatsAPI transactions (`.cache/mlb_transactions/tx_YYYY_MM.json.gz`, 2008-01 to 2026-07 on this box, plus the reconstructed `il_table.json`), arbitration awards (`data/arb_history.json`) and FA events into (a) `/projections/#player=` a dated Timeline strip (IL placements and activations with type and days, trades, signings with terms, options, DFA, releases, awards), (b) `/news/` MLB veterans' trades, IL placements and signings, (c) `/history/` MLB trades and signings on this date since 2008, (d) `/fa/` an "IL days, last three seasons" column; a nightly step for the current and previous month (2 calls, zero credits, heartbeat and `ingest_health` row; `run_monthly.py` has no reference to the league-wide cache today, its loader is `efv_drivers.py@64bf1bb3:397-445` (at 'TX_DIR') and `tools/backfill_mlb_transactions.py@64bf1bb3:10-39` (at 'mlb_transactions')); an events builder keyed by mlbam (`mlb_events.py`, the one `MLB_EVENTS_LIVE` definition); a lazy per-player events payload (`mlb_player_detail.json` is already about 5 MB) written only to `.cache/mlb_events/preview/` while the flag is off and served from `data/mlb_events/` (gitignored, with its `.gitignore` line, the `deploy/nightly-build.sh` and workflow includes, a copy of the publish-manifest guard and the unused daily step label `9e-pre0g`); X05-17 (the PROSPX news sidecar, `data/player_news.json` is `{}`) and M04-11 (dated FA signings) built on the same events table | `run_monthly.py`, a new events builder, `mlb_player_export.py`, `assets/projections.js`, `build_site.py` (`:1611-1744` (in _collect_events()) wire, `:2517-2522` (in _load_history_db()) history), `assets/fa.js` | per-player IL days reconcile with the `il_table.json` stints; per-season placement counts match the audited series in `data/fa_pt_risk_eval.json` (850 placements in 2025); no event outside the cache window; one row per (person, date, type code); StatsAPI description text printed verbatim, never re-voiced; no medical inference beyond the listed IL type | descriptive; no availability forecast may ride on it (the IL playing-time adjustment failed both sides, `fa_pt_risk_eval.json` w1b.verdict; registry `fa_pt_risk` deprecated) | L, in three tasks (the builder and nightly step; the player-page strip; the news, history and FA rows with the flip) | class 2 behind `MLB_EVENTS_LIVE` (the IL-days column and the new wire and history rows are new served numbers), after queue 3 and queue 6's home_shell lane (both edit `build_site.py`); Opus |
| W02 | build | PROSPX `il_status` (type, since, days) and `health_profile.is_post_tj` (`storage.py@64bf1bb3:11585`, `:11683` (at 'il_status')) as a chip on Dynasty board rows and Call-up Watch rows (`fantasy_export.py@64bf1bb3:964-988` (in _callup_watch()), `:1014-1094` (in _dynasty_prospects()); `assets/dynasty.js` has no injury field) | `fantasy_export.py`, `assets/dynasty.js`, one test | each chip equals the PROSPX card's `il_status` for the same player_key on the same build; the chip stays out of the dynasty blend score (do-not-reopen item 14) | descriptive | S | class 1; Opus |
| W03 | build | The winter frame in `_team_outlook`: unsigned locked free agents leave their 2026 club for a labelled unassigned pool (their WAR visible as one line, never assigned by fit probability: fit MRR 0.167); signed players join the `fa_events` club the night the signing posts; pending options weighted by the FA export's P(exercise) where it exists (6 of 46 rows) and otherwise held at the club, labelled; the 2,430-win league pin holds by construction (the working-tree roll-up sums to 2,429.9); the builder reconciles `fa_class.json` against the contract table first (23 locked FA-class members carry a projection row signed or controlled through 2027 or later: joe_ryan MIN, isaac_paredes HOU, sonny_gray BOS, yandy_diaz TBR, eugenio_suarez CIN and others); the Cost+ numerator counts only players whose salary is in its denominator (COSTPLUS-1); Franchise OUTLOOK, `projections.js` and `franchise.js` read the frame the merged OUTLOOK question picks, with a frame label and the pool line, while the Fit keeps reading the pre-free-agency frame, byte-identical (repointing its WINDOW is a Gate 3 lever, P8.5 F-1 and F-2); glossary (`team_win_projections`, `cost_plus`) and registry notes in the flip commit; the M15 gate amendment (docs, commit alone, only after the OUTLOOK answer is (a) or (b)): freeze both frames on the 1st of each month from November to March through the dated tasks Q9_03a to Q9_03e, each at the first writer slot on or after its date and never back-dated, and score both once against final 2027 standings at the 2027 close, the Opening Day freeze staying the primary read | `proj_export.py` (`:1675-1677` (in _last_controlled_season()), `:1704-1718` (in _last_controlled_season()), `:1920-1922` (in _team_outlook()), `:1960-1968` (in _team_outlook())), `franchise_export.py@64bf1bb3:465` (in build()), `ledger_export.py@410cccce:708-711` (in build_all()), `:1080` (at 'usd_per_win'), `:1478` (at 'club_docs'), `fa_fit.py@64bf1bb3:750-829` (in _outlook_wins()), `:1098-1103` (in fit_scores()), `assets/projections.js@64bf1bb3:716` (in viewChips()), `assets/franchise.js`, `data/glossary.json:7868`, `docs/PROJ_FORWARD_VINTAGE_GATE.md` (created by M15), tests | no player on two clubs; the unassigned pool equals the sum over unsigned members; the Cost+ numerator counts only players whose salary is in its denominator; `tools/export_trade_values.py` after every `proj_export` run | the roll-up is a registered predictive model (`team_win_projections`, provisional, forward gate MAE against final standings); the winter frame is model-free arithmetic on contract status; the registered read is amended before any 2027 number exists | M | class 3 behind `TEAM_OUTLOOK_WINTER_FRAME` (moves OUTLOOK letters, the Franchise Index and Cost+ for clubs losing free agents: CHC, LAD, SDP, SEA most; never a fit list); flips after step Z and the merged OUTLOOK answer; the flag state must be settled before the M15 forward freeze; Opus |
| W04 | build | Provisional grades v2 (P(first source grade by the next list date), queue 7 PV_A to PV_C) as a Dynasty lens named "Next to be graded" (never "Sleepers": the model predicts who a source grades next, not undervalued fantasy value) of never-graded prospects ordered by that probability; every figure the copy prints is read from `data/provisional_track_eval.json`, which PV_A and PV_B produce (it does not exist at `64bf1bb3`, `410cccce` or in today's tree; the lanes read AUC 0.826 against a 0.615 level-rank null on 6,066 rows, Spearman 0.017 on the level and MAE 6.21 against 4.54 from their design); the probability of a grade, never an expected FV; the PROSPX "Not yet graded" section (PG-Q1) and the lens read one field | `fantasy_export.py`, `assets/dynasty.js` | the lens order equals the PROSPX section order for the same build; a claims-freshness pin on every printed figure | predictive number measured and registered by PV_A and PV_B; no new claim | S | class 1; after PV_A, PV_B and PV_C; Opus |
| W05 | build | The /hof/ shelf (career bWAR, WAR7, JAWS, WAA, ink, band; `data/hof_board.json` watch 231 rows, not_yet_eligible 141, keyed by B-Ref id) as one line on the `/projections/#player=` overview for the 372 veterans on those lists, linking to /hof/; labelled "B-Ref bWAR" until O5 is answered or M10-09's fWAR twin lands; no position-standard comparison (the shelf's six groups have no 3B group and put Pujols and Cabrera in OF), so v1 prints the player's own numbers; "Watch" is a band, not a forecast (the /hof/ predictor stays dark; registry `hof_merit` deprecated) | `mlb_player_export.py` (join; S once X03-10 adds mlbam to hof rows), `assets/projections.js` | the line's numbers equal the shelf's for the same B-Ref id | descriptive (the shelf reproduces B-Ref's published JAWS definition) | M (S after X03-10) | class 1; W-OQ5 default taken; Opus |
| W06 | build | PROSPX debut date, last eFV before debut, the developing org and the final AAA Statcast hitter line (`statcast_aaa_hitters.json`, a PROSPX-only sidecar at `prospx/index.html@64bf1bb3:32151`) into `/mlbstats/` boards (a "PROSPX graduate" chip and a debut-season filter; a rookie-eligible filter once M10's service days exist) and the `/projections/#player=` origin block (the hitter AAA line beside the aStuff+ pitchers already get); prints eFV, never the consensus arc (P8.4 E5); `player_links` gains the graduate flag and debut season | `mlb_player_export.py@64bf1bb3:359-379` (in _debut_origins()), `player_links`, `assets/mlbstats.js` (no PROSPX, graduate or rookie reference today beyond a comment at `:41-43` (at 'formatMetric')), `assets/projections.js` | per-player rows only: no realized MLB statistic aggregated by FV or eFV band anywhere (PROSPECT_ANCHOR_GATE); the AAA hitter line waits for M25's refresh (the file reads "as of Jun 23") | descriptive | M | class 1 (the chip and filter add no number); after M25; Opus |
| W07 | build | The PROSPX Transactions Trade Audit (real trades priced at the snapshot before each deal on the Trade Machine value; queue 7 M9 adds the realized-value leg and a slim sidecar from `tools/export_trade_values.py`) into `/trademachine/`: a "Comparable real trades" panel under the evaluator, the five nearest real deals by value moved per side, prospect and MLB mix, positions and month, each with its value-today and realized-to-date legs; the similarity rule published; the verdict band stays the shared `BALANCED_THRESHOLD_MM` (`trademachine.js@64bf1bb3:322-326`); comparables are not a price precedent, each prints its time basis and names parties priced at $0 (M9-1) | `assets/trademachine.js`, the M9 sidecar, tests | the five comps reproduce from the sidecar under the published rule | descriptive | M | class 1; after M9_M10 and M9 realized leg; Opus |
| W08 | build | A Trade Machine partner screen v1: for a selected player, clubs ranked by a PUBLISHED rule with every factor visible: need by slot (Franchise lineup HEM+ by position, rotation+, bullpen+, team DEM+), Team Outlook 2027 wins and in-season playoff odds, the Ledger's 2027 tax payroll against the threshold and payor status (never "space", the Ledger NEVER list; the M27 form), farm surplus (ability to pay in prospects) and, after M8-3, the org trade profile; read from one slim slice of `franchise_board.json` (club sections `roster`, `outlook`, `fin` with `space_2027`, `tax_payroll_2027`, `payor_2027`, `farm` with `farm_surplus_mm`, `odds` with `playoff_pct`); labelled a screen, never a rumor board; in the winter the contention factor inherits W03's frame; M08-16 (a club needs strip) is its first half; v2 (a registered 2027-deadline read: daily frozen, hashed screen output from the build date; the share of real acquirers inside the top five per traded player against contenders-only and random baselines) only under W-OQ4 (a), because the 2026 deadline cannot be scored honestly (`franchise_export.py` first shipped 2026-09-23, `mlb_projections.json` is gitignored, so as-of inputs do not exist) | `assets/trademachine.js` (no partner code today; "needs" appears in a comment at `:348`), `build_site.py`, a slim slice exporter | the rule reproduces the ranking from the slice; no cap-space cell; no verdict word | descriptive v1; v2 predictive only under its own gate doc | M | class 1; W-OQ4; Opus |

**W08, ready to queue once W-OQ4 is answered (a) or (b)** (p8_wiring holds only the wiring candidates that need no owner answer, so this spec waits here): "OWNER ASK 4 (2026-09-30). Wiring W08 of wiring_ideas.md in the Part 8 bundle: a Trade Machine partner screen v1. For a selected player, rank the 30 clubs by a PUBLISHED rule with every factor visible: need by slot (Franchise lineup HEM+ by position, Rotation+, Bullpen+, team DEM+), Team Outlook 2027 wins (the frame the OUTLOOK answer serves) and in-season playoff odds, the Ledger's 2027 tax payroll against the threshold and payor status (never a 'space' cell: the Ledger NEVER list; the M27 form), farm surplus as the ability to pay in prospects and, after M8-3, the org trade profile; read one slim slice of franchise_board.json (club sections roster, outlook, fin, farm, odds) exported beside it; label it a screen, never a rumor board, with no verdict word. Under W-OQ4 (a) also register, docs first and alone, a 2027-deadline read: daily frozen and hashed screen output from the build date, one read after the 2027 deadline scoring the share of real acquirers inside the top five per traded player against contenders-only and random baselines. Tests: the rule reproduces the ranking from the slice; no cap-space cell; renders at 390 to 1440 in both themes. Class 2 for v1 (a new ranking the site does not serve today): build it behind TRADE_PARTNER_SCREEN_LIVE = False and flip it in its own commit after step Z."

**The nine not built now, what each would need.** W09 after B4_SPOTLIGHTS_RESCORE, with a
coloured chip only for a flag type that clears its matched control (today Rebounders) and the
rest muted "not scored". W10 after M07-04's 2026 park refresh; it is the registered fallback of
the W2 PARK-LINE gate (`data/xfv_park_line_eval.json` verdict M-FAIL-DISPLAY-CANDIDATE: the
eFV arm failed, hitters +0.0005 CI -0.0011 to +0.0021), so the chip must not imply an
adjustment, and the registry row `milb_park_factors` still describes the older infeasible R-PARK
experiment and needs its text corrected in the same change. W11 stage 1 (runner sprint-speed
percentile on each steal decision row, catcher pop time after X05-02) under W-OQ3; stage 2 (a
runner-aware success probability reported as an additive split of the execution residual, DV
untouched: the module prices DV at a league-average runner on purpose, `management.py@64bf1bb3:14-34`)
needs a gate doc, a fit on 2018-2023 attempts, tuning on 2024, one score on 2025, and it is the
substrate P8.8's base-coach question would need. W12 after VAL_1 at the unified level with
VAL_5's future seasons, the pick valued at expected first-six-season WAR x $/WAR minus the slot
bonus from the validated `draft_slot_curve`, only Competitive Balance Round picks (confirm
against `data/cba_rules.json`). W13, W16 as registered arms on the pre-registered start-score
protocol before Opening Day 2027, read on April to July 2027 starts (the 2026 split is spent:
arms J, A, B and C read on it, all null). W14 two need-side arms in one Holm family (m = 2) with
a permuted-position twin on the Gate 3 metric, read once on the 2026-27 winter signings,
registered before the first signing (the financial side belongs to P8.5). W15 the PAL reads on
MLB pitcher pages (each direction's verdict printed; `pal_conversion` downgraded, RP to SP failed
its gate, M22-2; pitch-add follows the old rule order, M07-09). W17 after VAL_4 and P8.7, behind
a split-half persistence check of org DvM+ across non-overlapping windows.

**Considered and not proposed.** Market-implied team strength into the playoff-odds simulation
(circular with the betting futures edge; no futures scorer yet, M12-20); the betting model's run
totals into DFS (the market beats the model: Brier 0.22995 against 0.24414 on 299 open-capture
games); GRPO breakout scores on Dynasty (`GRPO_FORWARD_GATE.md` section 6 PENDING); the
management hook tendency in DFS or fantasy innings (a 5l dark column related to outcomes before
2027-07-01); posted lineups in DFS pools (5j's clock; DFS dark until 2027); the Trade Audit's
realized leg as a Franchise trade record (Franchise NEVER list); org promotion timing as a
Call-up Watch predictor (NULL, `DECISIONS:336-345`); CollegeSavant CS+ into PV_D; article
backlinks (one article at HEAD).

**Honesty status.** W01, W02, W05, W06, W07 and W08 v1 add descriptive display only. W04 prints a
number measured and registered by PV_A and PV_B, read from their artifact, under a name that claims
only what the model predicts (who is graded next). W03 changes the frame of a registered
predictive model's served roll-up; its registered read is amended before any 2027 number exists
and both frames are scored once. Every later predictive item (W03's winter read, W08 v2, W11
stage 2, W13, W14, W16) needs a gate document before any number, and apart from W11's
historical backtest none can be read before 2027.

**Dependencies.** W01 and W10 edit `build_site.py` and `prospx/index.html`: after queue 3 and
queue 6's home_shell and prospx lanes. W03 and W16 touch the projections path: after any
`proj_export` run, run `tools/export_trade_values.py`; W03 after M13 and M15 part (1) (queue 7). W04 after
PV_A, PV_B and PV_C. W05 after X03-10 if it has landed (else the mlbam join). W06 after M25. W07 after M9. W01,
W05, W06, W07 and W08 link clubs through P8.3's resolver and players through the hub links.

**Landing rule.** W02, W04, W05, W06 and W07 are class 1 (additive displays of numbers the site already serves) and ship as built after step Z; W01 is class 2 behind `MLB_EVENTS_LIVE` and W08 v1 class 2 behind `TRADE_PARTNER_SCREEN_LIVE`, each flipped in its own commit after step Z. W03 is class 3 behind `TEAM_OUTLOOK_WINTER_FRAME`, flipped after step Z and the merged
OUTLOOK answer, before the M15 forward freeze, with the blast radius (OUTLOOK letters, the
Franchise Index, Cost+; the Fit unchanged) in the flip commit.

**Effort.** W01 L (three tasks), W02 S, W03 M plus five small dated freezes, W04 S, W05 M (S after X03-10), W06 M,
W07 M, W08 M; all Opus 5.5.

**Owner questions raised (defaults in bold; W-OQ3 and W-OQ4 in batch 12 of 8.G, prefixed W- because the
eFV 2026 plan asks its own numbered OQ questions of the same owner).** W-OQ1 is merged with
P8.5's OUTLOOK-1 (8.D row 4). W-OQ2
(landing scope for additive display wirings) is resolved by the flag rule in 8.A and not asked.
W-OQ3 the Management steal family (**stage 1 only, as context columns; DV and ER unchanged, the module's league-average-runner convention, `management.py@64bf1bb3:14-34`**; also register stage 2; neither). W-OQ4 the trade partner screen (**build v1
now as a labelled rule-based screen and register the 2027-deadline read**; v1 only, no read;
after the port). W-OQ5 (the HoF line's basis) default taken: bWAR JAWS now, labelled "B-Ref bWAR",
switching under O5 or M10-09.

### P8.7 DvM+ weighted by development difficulty (ask 6; lane dvm_difficulty)

**Lane summary** (`<part8>/dvm_difficulty.md`; count-only probes `_inventory*.py` and
`_inventory*.json` beside it, run on the archived 2026-09-04 database copy opened read-only and
immutable, never the live `prospects.db`). Nothing in the DvM+ family compares a player's growth
with what similar players usually gain. FV-DvM+ credits each grade step at its value on the fixed
`FV_EXPECTED_WAR` table (`storage.py@64bf1bb3:5690-5729`; a 60 to 70 step is 13.0 expected career WAR, a 40
to 50 step 2.5, so the first already counts 5.2 times as much, and 
`test_dvm_tail_weight.py@64bf1bb3:6-11`, `:32-41` (in test_70_to_80_dominates_40_to_50()) pins the owner's earlier "70 to 80 at least 10x a 40 to 50" callout); ToolDvM+ runs single
tool grades through the same table with level weights (`storage.py@64bf1bb3:6243-6257`, `:12755-12790`);
$DvM+ z-scores a player's pace inside his CURRENT eFV tier (`storage.py@64bf1bb3:12504-12533`), which
conditions on the outcome. Origin group, starting grade, age, the expected move for similar
players and its spread are weighted nowhere, so a club that acquires many young high schoolers
and 16-year-old signees can earn their ordinary growth as "development". Committed league means
of tool development are NEGATIVE for most future tools (`data/org_tendencies.json` toolDev: hit
-1.08, bat control -0.84, fastball -0.67 grade points per prospect-year), so "raw growth" is mostly
a race against a falling expectation that today's index never states. The DvM+ family carries
about 11 points of `farm_score` (4.5 through two Development leaves, 6.5 through Org $DvM+), about
3 points of the Franchise Index and a quarter of the farm tiebreaker (arithmetic on the weights at
`storage.py@64bf1bb3:4869-4916` (at 'FARM_TREE_WEIGHT_ACQUISITION_STRATEGY'), `:15545-15552` (at 'dev_hitter'), `:15849-15927`; `franchise_export.py@64bf1bb3:80` (at 'outlook'), `:881` (at 'development_score')).

**Nine served defects found while reading** (D-1 to D-9, each reproducible from the cited lines):
the Ledger says $DvM+ is "clamped 40-160" while served values run from -95.3 to 145.4 on 4,688 rows
(D-1, `ledger_export.py@410cccce:1801-1802` (at 'dvm_within_tier')); 57 of those rows sit beyond 3 sigma against about 13
expected, because the tier is keyed on the END grade and a small tier uses its own tiny spread
(D-2); the tier conditioning itself (D-3); FV-DvM+ and $DvM+ read the eFV retrospective series, so
club development history rewrites itself whenever eFV is refit (D-4, `efv_score.py@64bf1bb3:2086-2125` (in score_history()),
`storage.py@64bf1bb3:8730-8738`); ToolDvM+ credits source-mix changes as development (D-5); stale
Development-tab copy (principal window 6y vs the served 7y, blend weights, the movers basis; D-6,
`prospx/index.html@64bf1bb3:41044-41195` (in makeFarmDvmMultiWindowPanel())); four glossary entries misdescribe the math (D-7); two registry
notes are stale (D-8); and `farm_grade_backtest.py@64bf1bb3:65-67` (at 'VINTAGE_YEARS') scores list vintages 2018-2022 against
realized graduate WAR, so the re-run plan item M02-22 proposes would read the reserved R-LV
vintages with an outcome (D-9, a hazard handed to that item in 8.F).

**Design.** (1) One expected-growth model fitted on same-source list-to-list pairs (a source's
preseason list in V against its list in V+1 and V+2; Pipeline, FanGraphs, BA), conditioning on the
START grade rung, origin group (HS draft, college draft, IFA amateur, pro or overseas, unknown),
side, level band, age for level, source and list year, every cell shrunk (weighted least squares
with each player-year counted once; the origin-by-rung interaction shrunk by a method-of-moments
prior frozen into the table; spreads shrunk toward the side spread with 30 pseudo degrees of
freedom). (2) DvM+ becomes growth above expected: each player-year earns observed minus expected
growth, split by days across the clubs that held him (VAL_4's tenure table), averaged per club
with shrinkage (Kish effective n, `k_org` bounded to [5, 50]) and scaled to 100 + 10z across the
30 clubs; a club-window needs an effective n of 10 to publish. (3) Tools use the difficulty
residual in tool-grade spread units with the existing position-importance weights (the FV-to-WAR
table means nothing for a single tool). (4) The per-prospect figure is recomputed on the player's
own start grade, shrunk, so the -95.3 tail cannot recur. How a 60 to 70 move weighs against a 40
to 50 move is then MEASURED, never assumed: under the recommended value-above-expected statistic
the ratio is `(13.0 - E_W[60]) / (2.5 - E_W[40])`, read at the look.

**Frame rules (the spent, non-reserved frame).** F-R1: no pair with an endpoint in list vintage
2020 or 2021 before the R-LV look record exists (Q-DVM-1); F-R2: no end read that is an R-VM input
grade; F-R3: the lab does not run before the ETA look record exists (queue 8's ETA_LOOK_REPAIR_RERUN; a
VOID record counts, and a VOID keeps the served champion; censoring reads the debut facts of the
2024 listings); F-R4: no WAR, `career_war`, label module, debut, graduation or
bust rate by rung, and no read of `value_framework.fv_to_6yr_avg_war`, ever; F-R5: no eFV input of
any kind. Excluding 2020-2021 costs 36 percent of 12-month and 45 percent of 24-month pairs (7,007
and 3,752 remain before 2024). **Why the FV-cell ban does not bind:** `docs/PROSPECT_ANCHOR_GATE.md`
protects realized MLB WAR by consensus-FV cell (`:139-175`, banned list `:1040-1064`); this study
tabulates GRADE movement (a scout's revised opinion) by starting rung and joins no outcome. Where
it WOULD bind (a debut, graduation or bust rate by rung, WAR valuing a step, the realized anchor)
is excluded by F-R4 and pinned by an AST test.

**The owner's two hypotheses, as a registered descriptive read.** H1 (traits easier or harder to
develop by origin group): 13 traits x 3 contrasts, two estimands (total, and direct given age and
level), one Holm family each, player-clustered bootstrap (B 2000, seed 20261201), 100 completed
pairs per group or "unpowered", and a verdict word only when the sign agrees on both censoring
sensitivities, on Pipeline and FanGraphs separately and in two of three eras. H2 (the next rung is
harder from a higher rung): the trend in P(one rung up) by start rung and the owner's own contrast
P(two rungs from 60+) against P(two rungs from 40), Holm family of 8, all three censoring frames
agreeing. Stated before any read because each can make H2 hold with no development story at all:
the bounded scale, regression to the mean, and graduation removing the fastest top-rung risers.
So a pass reads "list grades rise less often from higher rungs", never "developing talent is
harder there". Power from counts only: about 9 points (hitters) and 11 (pitchers) of one-rung rate
difference detectable between 40 and 60+; two-rung events from 60+ will likely read unpowered.

**Validation before serving (registered with the read).** Club indices rebuilt as of each past
preseason 2012-2025 from the same grades (no DvM+ was ever stored before 2026-06); three
statistics against today's logic rebuilt on the same frame (C0): V-C composition neutrality (the
index must stop tracking the share of HS, college and IFA players), V-P1 next-year raw farm growth
(non-inferiority, margin -0.05), V-P2 next-year growth above expectation, and V-S year-to-year
persistence on disjoint windows, read only beside V-C because composition persists. Club-clustered
bootstrap over 30 clubs; resolvable only near 0.1 of mean Spearman, so a tie is the modal outcome
and the decision rule says what ships on a tie (Q-DVM-3).

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| DVM-0 | copy | Copy truth, no number moves: the Ledger clamp claim (D-1), the Development-tab labels and blend weights read from the payload instead of typed (D-6), the four glossary entries (D-7), the two registry notes (D-8) | `ledger_export.py` (VAL_1 committed as `410cccce`), `assets/ledger.js`, `prospx/index.html`, `data/glossary.json`, `data/model_registry.json`, `MODEL_REGISTRY.md` | `test_dvm_copy_truth.py` (no "clamped" claim while no clamp exists; the arc panel names the principal window from the payload; the blend weights in copy equal the code's); copy checks; `restamp_hand_authored_pages()` | class 1 | S | window Tier C if a slot frees after VAL_1 commits, else first after step Z |
| DVM-1 | frame | Origin backfill and coverage audit, counts only (P-2 to P-4): list-printed origin first, draft data, acquisitions, Pipeline report text, the age rule last; the FanGraphs-vs-acquisitions disagreement table; level and age coverage from the outcome-blind identity (never `players.birth_date`, which is largely "debuted"); the 2026 Pipeline preseason list backfilled or the 2025-2026 step declared FanGraphs and BA only | `tools/dvm_difficulty_lab.py` (frame module only) | `test_dvm_difficulty_frame.py` (F-R1 to F-R5 in code) | counts only | M | after Q-DVM-1 and Q-DVM-4 |
| DVM-2 | registration | `docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md`, committed ALONE with an empty results section: frames, model, censoring rules, H1 and H2 families, the validation statistics and decision rule, seeds, margins, the power block recomputed from DVM-1's counts, the clock and the refusal rules | `docs/dvm-difficulty-2026-09-30/`, `test_dvm_difficulty_gate.py` | the pin test (frames, seeds, Holm families, margins, clock, results EMPTY) | registered, unread | M | after DVM-1; registration before any growth is computed |
| DVM-3 | lab | The lab: frame, model, censoring, H1, H2, validation, guards; refuses before its clock and a second scored look; computes no growth before the look | `tools/dvm_difficulty_lab.py`, `data/dvm_difficulty.json`, `data/dvm_difficulty_eval.json` (both written only by the look) | `test_dvm_difficulty_stat.py` (shrinkage, the spread floor, Kish n, tenure shares sum to 1, the censoring rules, the 60-70 vs 40-50 ratio formula on a fixture table) | built, unread | L | after DVM-2 |
| DVM-4 | look | The one look, under the crash protocol | none | none | adjudicates | S | on or after the later of the ETA look record (a VOID counts) and the R-LV look record (not before 2026-12-01), or 2027-01-31 on the complement frame if no R-LV record exists; on EVERY path only after the PROSPECT_ANCHOR look record exists (the S2 frame codes graduates, so its by-rung difference from the primary frame is arithmetic on graduation share by FV rung); own session, pipeline idle, inputs sha256-pinned |
| DVM-5 | build | Served build behind `storage.DVM_DIFFICULTY_ARM = None` ("value" or "difficulty" when on; None byte-identical to today): `_build_org_dev_residuals` reading VAL_4's tenures and the frozen `data/dvm_difficulty.json`; `dvm_plus[window]` and its cohort and bucket versions; a `dev_expectation` block per club and window (actual, expected for this farm's mix, residual, n, the mix); the per-tool pass on tool residuals; `_dollar_dvm_by_key` on the player index; the Development tab's "Expected vs actual" strip and "Development difficulty" explainer; relabels on the farm list, leaderboards, cards and the Ledger; glossary entries including the new `dvm_expected_growth` | `storage.py`, `org_tendencies.py`, `prospx/index.html`, `ledger_export.py`, `assets/ledger.js`, `franchise_export.py`, `data/glossary.json`, `data/model_registry.json` | `test_dvm_flag_identity.py` (flag None: every DvM+ field of `org_summary` byte-identical to a golden); updates to `test_tool_dev.py`, `test_farm_rolling.py`, `test_ledger_export.py`, `test_ledger_render.py`, `test_franchise_export.py`; `test_dvm_tail_weight.py` stays green | class 3 (moves farm letters, ranks, Org $DvM+, the Franchise FARM leg) | L | after VAL_4 and DVM-3; flip (DVM-6) only after DVM-4 passes, after step Z, by the owner, with the blast radius published and "farm letters move" said plainly |

**Queue tasks.** DVM-0 is Q10_03 (a class-1 insert for the landing window if a slot frees after
VAL_1 commits); DVM-1 Q10_12; DVM-2 Q10_13; DVM-3 Q10_14; DVM-4 Q10_15 (dated, refuses early); DVM-5
Q10_16 (the build only; the flip is the owner's).

**Honesty status.** The expectation table and its read predict nothing about MLB outcomes; they
describe how list grades move. New registry row `dvm_difficulty` (the table plus its read and
validation; eval artifact `data/dvm_difficulty_eval.json`, refit once a year after the preseason
lists). Rows `dvm_plus_org`, `dvm_plus_tools`, `dvm_plus_dollar` get their notes corrected now
(DVM-0) and, at the flip, name the arm and point at the eval artifact; they become provisional only
if the decision rule passes. Firewall: no output of the lab (tables, residuals, club indices) enters
any eFV head, driver or stratum without its own registration naming the artifact in its
forking-paths count. The per-(club, season, player) residuals with tenure shares are exported for
Staff Gems (P8.8) and enter it only as 8.D item 6 says. Honest priors, recorded so the read can be
checked against them: H2 will probably read "higher rungs rise less often" for the structural
reasons above; the HS and IFA advantage in raw growth is probably mostly age, so the direct origin
effect may be small; validation will probably tie on prediction, which is why the composition check
carries the decision.

**Dependencies.** VAL_4 (queue 7, post-Z) supplies the tenure table (P-1; its design doc
`docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md` does not exist yet); the ETA look
record (queue 8's ETA_LOOK_REPAIR_RERUN; a VOID counts); the PROSPECT_ANCHOR look record (for DVM-4 on
every path); the R-LV look record (EFV_V2_GATE part 9, not before 2026-12-01). DVM-0 touches
`ledger_export.py`, whose VAL_1 edits are committed (`410cccce`).

**Landing rule.** DVM-0 class 1 (the landing window if a slot frees, else after step Z; never in the
gap between 10-04 and step A). DVM-1 to DVM-3 write no served file. DVM-4 is dated. DVM-5 builds
behind the arm flag with None byte-identical; the flip is an owner action after the read passes and
after step Z.

**Effort.** DVM-0 S, DVM-1 M, DVM-2 M, DVM-3 L, DVM-4 S (session), DVM-5 L; all Opus 5.5 (the lane
names Fable 5.1 for DVM-3 only if its guard and parity tests fail twice).

**Owner questions raised (defaults in bold; Q-DVM-1 to Q-DVM-4 in batch 11, Q-DVM-5 and Q-DVM-6 in batch 12 of 8.G).** Q-DVM-1 the reserved list vintages 2020-2021 for
this study (**exclude them; one read after the R-LV look record, not before 2026-12-01, complement
frame on 2027-01-31 if no record exists**; run now on the complement frame; read them now with a
disclosure, which an auditor can call a found read on R-LV and which kill rule 3 would punish by
turning R-LV into development for v2). Q-DVM-2 how a move is valued (**value above expected**;
difficulty only, which reverses the owner's recorded callout that a 70 to 80 move counts at least 10x a
40 to 50 move; keep today's DvM+). Q-DVM-3 what ships on a tie (**ship if the composition check
passes, labelled "difficulty-adjusted; ties the previous index on prediction"**; only on a resolved
win; keep today's as the grade and show the new one beside it). Q-DVM-4 which grades the statistic
reads (**each source's own published grades; every displayed grade beside DvM+ stays eFV**; the eFV
retrospective series, today's basis, which rewrites development history at every refit and cannot
be fitted without scoring eFV on the reserved vintages). Asked when DVM-5 starts (Q10_16 takes the recorded defaults if they are
unanswered and records them): Q-DVM-5 cadence (**annual preseason steps**; add FanGraphs midseason
steps) and Q-DVM-6 the per-prospect figure (**recompute as "DvM+ (player)"**; keep the tier-z formula and
fix its copy; retire it).

### P8.8 Staff Gems: development staff above their organization's mean (ask 7; lane staff_gems)

**Lane summary** (`<part8>/staff_gems.md`; saved StatsAPI responses and the count-only coverage
script in `<part8>/staff_gems_work/`; about 250 public StatsAPI requests at 0.2 to 0.5 s spacing).
The repo holds NO personnel data: the management export says so in its own words ("there is no
manager entity anywhere on disk", `mgmt_export.py@64bf1bb3:493-499` (in _decision_blocks())), and the only staff-shaped object is a
92-row 2025 ejection fixture used as validation (`mgmt_decisions.py@64bf1bb3:1087-1110` (in detect_ejections()),
`test_mgmt_managers.py@64bf1bb3:56-84` (in test_ejection_named_managers_agree_with_the_ledger())). One public source carries dated, identified staff history: the MLB
StatsAPI coaches endpoint (`/api/v1/teams/{id}/coaches?season=` or `?date=`), with an MLBAM person
id on 331 of 331 probed rows, MLB staffs back to at least 1960 (base-coach titles by 1995), minor
league affiliate staffs from 2008 (thin at complex and DSL clubs before about 2012), and mid-season
changes resolvable to the day by bisection (Nationals 2025: the old staff through 07-06, the interim
from 07-07, found in 9 requests). Every payload carries MLBAM's notice ("Only individual,
non-commercial, non-bulk use of the Materials is permitted"). NOT obtainable from any dated,
identified source: minor-league coordinators and roving instructors, directors of player
development, analysts, strength, mental-performance and medical staff; who worked with which
player; instructional league, winter and spring assignments; minor-league base coaches. Press
releases and the paid Baseball America Directory carry some of it as names only, and a name never
creates a person here (the site already served two humans merged under one key, census X03-01).

**The measurement problem, measured.** Of 25,802 same-source, same-org tool-grade pairs (the unit
org Tendencies already uses), 0.6 percent sit inside one April to September window and 64.2 percent
touch an October to March offseason; the median pair spans 197 days. Credit can only be apportioned
by exposure (days with each staff member), with the offseason credited to the organization and to
nobody by name. Today's cross-org spread of tool development is 0.23 to 0.64 grade points per
prospect-year noise included (committed `data/org_tendencies.json`); arithmetic on stated
assumptions says the persistence gate can see coach effects about as large as today's whole org
spread and nothing smaller. **A null is the likely result, and the module is designed to ship under
one** (the In-Game Management running game read null on 13,973 attempts and withheld its plus
metric; that is the precedent).

**Attribution design.** Role-matched traits (hitting coach: hit, power, pitch selection, bat
control; pitching coach: pitch grades and command; defensive coach: field and arm; manager: overall
FV growth; bench, performance and generic "Coach" titles: none; speed stays with the org);
exposure-weighted against a baseline of level, age, source, season and park; empirical-Bayes
shrinkage toward the ORG mean with the prior variance estimated from the data (if it estimates at
zero, nobody is a gem, and the shrinkage and the gate say the same thing); units in grade points per
player-year, never a 100 + 10z index for individuals; a gem needs the floors (12 players with 30+
days, 3.0 player-years, 2 seasons in the role, 30 effective pair-trait observations; below any floor
nothing is computed at all), the role's persistence gate PASSED, the 90 percent band above zero for
both the total and the within-org effect, Benjamini-Hochberg at q 0.10 across the role, and survival
of any one player's removal. Parallel role ledgers are never summed (the manager, hitting and
defensive coach share every player-day; the data cannot say which moved a hitter's grades, and the
page prints that assumption). Graduate WAR enters only through VAL_4's club share, split inside the
club by time with each staff member, labelled "an accounting share, not what he added", and never
compared to any expectation or FV cell.

**Persistence gate (registered first, one look).** `docs/staff-gems/STAFF_GEMS_GATE.md`, committed
alone before any staff spell meets a grade pair: split-half persistence per role against a null that
permutes staff within (org, level, season) cells (2,000 permutations, the management gate's
construction); a pre-tenure placebo (the same affiliate the season before he arrived must NOT clear
its null); a movers leg that only decides wording; a detection floor by injection; Holm across four
roles at family alpha 0.05; an artifact `data/staff_gems_gate.json` with aggregate statistics and NO
person id.

**Publication rule (SG-Q1 default).** Name gems only, each with players, player-years, seasons, the
90 percent band and the attribution caveat; never rank, list, sort, colour, export or describe anyone
below the mean, by name or by any identifying combination; one indistinguishable state for "not
measured", "not above" and "below" (the org view never counts staff measured, because "1 gem of 3"
names two people by elimination); say who else developed the player; removal and corrections on
request through /report/ with an ids-only opt-out list applied before any payload is written and kept
OUTSIDE the webroot (`config/staff_optout.json` or `.cache/staff/optout.json`, never `data/`, because
every top-level `data/*.json` ships, `deploy/publish_paths.txt` and census X03-15); a named manager or
base-coach row carries style fields only (attempts, the share of steals of second and third, break-even
faced), never a success rate, realized value, mWPA or letter in the same row or leaf; every org-by-role
cell has a floor on distinct persons (at least 4, none over half the cell's exposure) besides the
20-player floor, or it is shown unsigned; no
photo, age, personal links or contract detail; no /news/ rows; per-person estimates for non-gems
only in gitignored `.cache/staff/`, never committed. Why: minor-league staff are private employees,
the measurement cannot separate a coach from his org, co-workers or players, and a wrong negative
statement can cost someone a job.

**Two changes this part makes to the lane's design (8.D items 5 and 6).** (1) The manager leg reads
same-source FV grade pairs, not the per-snapshot eFV series: the eFV retrospective series is
today's model re-scoring old lists (the DvM defect D-4), which is the wrong object for crediting
past staff, and reading it would put eFV scores on the reserved 2020-2021 lists into a coach table.
This also removes the lane's only reason to wait for step Z at the gate (the epoch rebuilds the eFV
series). (2) The gate frame follows the same reserved-vintage rule as P8.7, the one the owner's Q-DVM-1
answer sets (default: pairs with an endpoint in list vintage 2020 or 2021 enter the one look only if
the R-LV look record exists when it runs; otherwise the look runs on the complement frame and says
so). The registration states which, before
any spell meets a grade pair.

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| SG-0 | registration + fetch | Commit the design as `docs/staff-gems/DESIGN.md`; register `docs/staff-gems/STAFF_GEMS_GATE.md` ALONE (with the two changes above, the floors, the publication rule and the look timing); add `statsapi_coaches` to `data/sources/registry.yaml` with the probe samples and regenerate `DATA_SOURCES.md`; then `staff_ingest.py --fetch` (the fetch half): season lists for MLB clubs and every affiliate 2008-2026 via `teams/affiliates`, first- and last-game dates, date bisection only where a role has two holders or a person two roles, all raw into `.cache/staff/` (about 15,000 requests once at 3 per second, about 80 minutes; about 800 a season after) | docs, `data/sources/registry.yaml`, `data/sources/samples/`, `staff_ingest.py` | gate-doc presence test; fetch tests on saved fixtures, no network in tests | docs and a cache fill; nothing served | S-M | after SG-Q1 to SG-Q4; SG-Q2 (d) stops after the design commit |
| SG-1 | schema + identity | Parse the cache into `prospects.db` tables (persons, spells, units) after a database backup; the role map `config/staff_roles.yaml` with its review queue (an unmapped title never gets a guessed role); identity rules (a person is the MLBAM id; a name-only row joins only when it matches exactly one StatsAPI person holding a spell at the same org and season, else the review queue); location spells from transactions (day resolution, 76.4 percent of pair players) and career rows (season resolution) | `staff_ingest.py` (parse half), `staff_identity.py`, `config/staff_roles.yaml`, `storage.py` (tables) | `test_staff_ingest.py` (role map total, every row an MLBAM id, the WSH 2025 and Trenton 2019 bisection fixtures, season union equals the union of spells), `test_staff_identity.py` (a two-people-one-name fixture stays two) | not served; hand-run, not in `run_monthly` | M | after SG-0; never during a pipeline run or a pytest session (it writes `prospects.db`) |
| SG-2 | attribution + look | The exposure splitter shared with VAL_4 (whichever lands first builds it; the org calendar and the unit and staff calendars must never disagree about where a day went), `staff_gems.py`, `tools/staff_gems_gate.py` run once, registry rows `staff_gems` and `org_role_development` (provisional, `measurement_only`, the gate artifact) | as named | `test_staff_exposure.py`, `test_staff_gems_model.py` (synthetic recovery; at zero true SD the false-discovery rule names at most its share; floors block estimates; leave-one-player-out; the placebo flags a synthetic that sends the best prospects to one affiliate), `test_staff_gems_gate.py`, `test_staff_gems_war_share.py` (no import of `fv_to_6yr_avg_war` or any FV-cell table) | the look adjudicates per role | L | NOT QUEUED NOW: after VAL_4, after the R-LV rule above; its own queue task later |
| SG-3 | pages | `/staff/` (gems, person card, org-by-role view on the DvM+ scale with the distinct-person floor, base coaches by style only, method), the farm Development "Staff" panel, Franchise FRONT OFFICE and a DUGOUT names leaf with no realized figures (today's DUGOUT leaf prints realized mWPA per decision family, `franchise_export.py@64bf1bb3:757-763` (at 'success_rate'), beside the `manager_skill` and `decision_quality` keys the NEVER list bans, `:105-106`), the Tendencies base-coach panel, behind `STAFF_GEMS_LIVE = False` | as in the lane's 6.1 | `test_staff_publication.py` (payloads name gems only; no numeric field on a non-gem; "worst", "bottom", "below the mean" and "least" never appear; a non-gem id and an unknown id render identically; the opt-out wins), `test_staff_render.py` | class 2; flip after the gate result and a private preview | M-L | NOT QUEUED NOW: after SG-2 and step Z |

**Honesty status.** Stage 0 and 1 serve nothing and compute no development number for any person.
The gate is the only look; its artifact names no person. What the page may never claim: that a named
coach caused his players' development; anything about a person who is not named; that coordinators,
rovers, analysts, strength and medical staff, the offseason or the players contributed nothing; that
graduate WAR on a card was added by the coach; any skill of first- or third-base coaches; anything
before 2017, or at complex and DSL levels before 2012. **Base coaches (SG-Q4):** the running game's
club-season decision value does not repeat (split-half 0.1085 inside its null band -0.1501 to
0.1272, `data/management_gate_eval.json`), and the gate document already rules that a club-season
signal bounds anyone inside it (`docs/IN_GAME_MANAGEMENT_GATE.md@64bf1bb3:24-28` (under '## The agent')), so the default is names
as context beside the club's running-game STYLE fields only (never its success rate or realized value),
sorted by season or volume and never by value, plus two tests registered (not run) for 2027. The wiring item W11 (runner speed on steal decisions,
P8.6) is the substrate those tests would need.

**Dependencies.** VAL_4 (queue 7) for the WAR line and the shared splitter; P8.7's frame rule and,
once its read has run, optionally its frozen expectation table as a baseline term (8.D item 6);
M10-06 (the management module's manager entity) stays open and is not asked here: answering SG-Q2
(a) supplies its data and leaves only whether /management/ consumes it. Queue placement: SG-0 is
Q10_17 and SG-1 is Q10_18; SG-2 and SG-3 are later tasks written after the owner's answers and VAL_4.

**Landing rule.** SG-0 writes docs and `.cache/` only; SG-1 writes `prospects.db` only (never during a
pipeline or pytest); nothing is served before SG-3's flag flips after step Z and after the gate.

**Effort.** SG-0 S-M plus about 80 minutes of fetching; SG-1 M; SG-2 L; SG-3 M-L; all Opus 5.5 (a
Fable 5.1 review of the gate code is the lane's suggestion for SG-2).

**Owner questions raised (defaults in bold; batch 4 of 8.G).** SG-Q1 who may be named (**gems only**; a full named
ledger in both directions, not recommended; no individuals, org-by-role only; MLB staff only).
SG-Q2 the source (**the StatsAPI coaches endpoint only, about 15,000 requests once; that is bulk use
outside MLBAM's 'individual, non-commercial, non-bulk' notice, a paid tier would also breach its
non-commercial term (the owner already moved weather to NWS over commercial terms, FP5-2), so the
registry rates the source 'ambiguous', as it rates `mlb_pipeline_graphql`, until the owner rules**; plus hand-curated
coordinator lists from press releases; license the Baseball America Directory; build nothing now).
SG-Q3 what ships when a role's gate reads null (**the descriptive module without gems for that role:
org-by-role development with the distinct-person floor or unsigned, the gate sentence and its detection
floor**; name individuals anyway,
labelled, not recommended; hold all of /staff/). SG-Q4 base coaches (**names beside style fields only, plus two
registered 2027 tests**; context only; drop the extension; rank base coaches by steal value now, not
recommended because it contradicts the frozen management gate).

### P8.9 The game intensity index (ask 8; lane intensity_index)

**Lane summary** (`<part8>/intensity_index.md`; the synthetic stakes scripts and outputs
`<part8>/stakes_*.py`, `stakes_od_300k.json`, `intensity_work/series_stakes.py`, none of which read
repository data). **The board prices no postseason game, this week or any week:** the betting slate
is `fantasy.json` `schedule.games` (`betting_export.py@64bf1bb3:2498-2524`), filled at `game_type="R"`
(`fantasy_export.py@64bf1bb3:1371-1373` (in _attach_schedule()), `fantasy_schedule.py@64bf1bb3:129` (in fetch_probables())); the DFS slate is R-only
(`dfs_export.py@64bf1bb3:1174` (in _schedule_for_day())); the results cache refuses non-R games at both doors
(`betting_model.py@64bf1bb3:3329-3334` (in _row_from_schedule()), `:3514-3515` (in build_game_cache())); only the lineup capture job sees this week's Wild Card
cards, and it prices nothing. Two served findings, handed off (8.F): **F1** the Futures tab reads only
the regular-season schedule (`proj_current.py@64bf1bb3:114` (in _fetch_schedule_raw())) and plays the bracket from final standings, so it
republishes pre-bracket odds for the whole postseason (the served `data/futures.json` was built
2026-09-27T20:45Z with four clubs still strictly between 0 and 1); **F2** the `playoff_odds_sim`
registry row says the simulator runs "at a blended true-talent estimate", while the code feeds it the
pure 2027 roster prior (`proj_export.py@410cccce:2403` (in _attach_current_season()), `:2438` (in _attach_current_season()); `_talent_prior_pct` :2291-2297).

**The index, `ix_v1` (frozen at registration).** Stakes S: the change in each club's World Series
probability between winning and losing this game, from `proj_current`'s rest-of-season plus bracket
simulation run twice with the result forced each way under common random numbers (postseason games by
exact series recursion times the bracket probability of advancing), talent from the literature Elo
(`tools/betting_elo.py@64bf1bb3:40-83` (at 'LITERATURE_K'), 1500, K 4, 24 points of home field, flat start each season; not the
Futures prior, because of F2), `G = dWS_h + dWS_a`, `L = G / G_REF` (the stakes multiple; `G_REF` the
mean G of an Opening Day game between average clubs, synthetic draft value 0.01145 at 300,000
simulations and seed 20260930, written once by the gate tool's own commit (Q10_07) from the
synthetic league, so the dark builder can use it before any look), `S = ln(1 + L) / ln(1 + 2 / G_REF)`.
Matchup quality Q: the smaller of the two clubs' percentile ranks of projected full-season wins.
Starters A: the smaller of the two probables' SEM+ percentiles (null, never zero, when a probable is
unannounced). Division D. `II = round(100 x (0.60 S + 0.15 Q + 0.15 A + 0.10 D))`, bands under 30
routine, 30 to 49 raised, 50 to 69 high, 70 and over peak; weights and bands are POLICY, never fitted.
Rivalry is a label with weight 0 unless INT-A4 says otherwise before the gate tool's commit; season
phase is a label only, never scored (as a scored run-environment term it is a close variant of 5k-B,
`docs/diamond-betting.md@64bf1bb3:6500-6512` (under '### When 5k is read')). Worked values: an Opening Day game between average clubs 23;
a winner-take-all final-day wild card between division rivals 56; Wild Card game 3 between strong
clubs with good starters 70; World Series game 7 between elite clubs with aces 89. Not knowable
pregame: same-day results elsewhere, posted lineups, in-game leverage, the home-plate umpire,
observed weather, manager intent, real tiebreakers (the simulator flips coins), schedule changes.

**What can be measured, and the ceilings (the part the owner most needs).** The 2026 vintage eval
half holds 763 graded games: at 80 percent power it could see 4.5 points of win probability per SD of
a regressor and 0.41 runs per SD of total, so the 2026 vintage-mode read is FORGONE on counts now, before
any number exists (plan stop X7). The power is in 2018, 2019 and 2021-2025: 17,008 regular-season
finals (one StatsAPI request per season; the same pull 5k and 7i register) against the leak-free
literature Elo can see about 1 point per SD and 0.09 runs per SD. That frame answers the owner's
questions; it cannot license a price. **Structural limit, stated once:** the effects asked about
are concentrated (lopsided stakes late in the season, decisive games in October); rule 4 grades one
season at a time without pooling; a 5-point effect on a focused tenth of the schedule needs about
1,080 focused games for an expected t of 1.645 and one season holds about 240; so under the current
rules a stakes term will very likely never pass the served-price gate, however real it is (INT-B4
asks whether to register a multi-season rule). **Clutch:** Cramer (1977), James (2004), Tango,
Lichtman and Dolphin (2007) and FanGraphs' own Clutch page agree that clutch hitting is at most a
small spread of talent; 50 high-intensity plate appearances carry a standard error of about 0.071
wOBA; so no per-player "big-game" number is ever published, and the archetype read (IX-D) is
expected to be null.

**Registered reads (stage 1 on 2018-2025, model-free; stage 2 on the 2027 vintage).**

| Family | Member | Estimand | Frame and baseline | Ceiling (80% power) |
|---|---|---|---|---|
| IX-ML (m 2, Holm) | IX-A asymmetric stakes | does the club with more at stake (playoff-odds swing difference) win more often than a quality-only price says; sign b > 0 registered | fit 2018, 2019, 2021, 2022 (9,719 games), grade 2023-2025 (7,289) against Elo; focus set `|ds| >= 0.05`; the B3 permuted-team twin (200 draws, 95th percentile, strict); a quality re-entry control (regressed run differential) | about 1.5 points per SD on the graded half |
| IX-ML | IX-A2 home field under symmetric stakes | the "home choke" claim for decisive games (Baumeister and Steinhilber 1984; not replicated, Schlenker et al. 1995) | same, two-sided | same |
| IX-TOT (m 1; not a member of RE, whose membership is fixed) | IX-B | do high-stakes games score differently than their clubs, park and calendar imply | club-season, venue-season and season-month fixed effects panel (5k's row rules), CR1 date clusters, twin, starter and club quality controls | 0.087 runs per SD |
| IX-TYPE (m 4) | rotation quality, bullpen QUALITY, contact, power | do team types beat their price when stakes are high | Elo price, types as of D-1 from the play corpus; bullpen USAGE and team defense EXCLUDED until the 5l and 5g looks are recorded | about 3 points per SD of type gap in the top decile |
| IX-ARCH (m 6) | six prior-season archetypes | do player archetypes shine in high-stakes games | PA-level wOBA residual against a matchup expectation, difference in differences, game-clustered | expected null |
| IX-E (descriptive, intervals only) | postseason team types | what types of teams do well in October | home win rate, totals and team types in 2018-2025 postseasons (about 270 games) against end-of-season Elo | about 7.5 points per SD (about 4 with the 2000-2017 postseasons, INT-B1 (b)) |

Stage 1 reads once, on the later of 2026-11-02 and the day after the 2026 World Series, after every
2026 look whose sample it shares is recorded or closed (5c-B, 5c-C, 5d, 5k, 7e-D; the lane also listed
5e and 5i-B, but stage 1 reads 2018-2025 only and those two score only 2026 vintage games, 5e's
postseason games included, so no game is in both samples and neither is waited for, which keeps the
read in 2026), in one run with every block written before any is opened, under the crash protocol, into
its own tracked artifact `data/game_intensity_eval.json` with a registry row (never a block in
`data/betting_model_eval.json`, which the nightly rebuilds from scratch, 8.F); a dry run of any fit, score or twin on real data before then counts as
the look. Stage 2 reads only members that resolved in stage 1, with the parameter frozen at its stage-1
value (never refit on a 2027 game), rule 4's vintage leg on the focus set, a feature-only power
precondition in 5f's form (short of t 1.645 the look records UNDERPOWERED and reads nothing), on the
first nightly after the last scheduled 2027 regular-season game, kill date 2027-11-30. A pass speaks
for the vintage refit; the served pricer follows 7e-D and O14.

| ID | kind | item | files | test | honesty | eff | gate / owner |
|---|---|---|---|---|---|---|---|
| IX-R | registration | The game-intensity section of `docs/diamond-betting.md` (the next free letter after 5l in commit order; 5n if the workload section took 5m and nothing else landed), committed ALONE, the lane's section 5 text verbatim with three edits: the letter and the schema by commit order; A2 recorded as INT-A2's answer; B3 removed (the Franchise postseason record is the F-SCORE plan's, 8.E) | `docs/diamond-betting.md`, `test_betting_intensity_registration.py` | the pin test: literals equal the text, the look date rule, no `ix_` symbol in any non-test module before its builder amendment | registered, no number | S | the gap if a slot is free after the epoch preconditions, else the first slot after step Z; before the World Series ends; never between step A and step Z |
| IX-H1 | code | `intensity_core.py`: the Elo walk, the conditioning simulator with common random numbers, the series recursion, both postseason formats (five clubs a league in 2018, 2019, 2021; six from 2022), percentiles, the frozen literals copied (never imported from a served module, X4) | `intensity_core.py`, `test_intensity_core.py` | a World Series game 7 gives S = 1; two eliminated clubs give 0; the forced CRN runs are identical except the forced game; literals equal the registration | no real game computed | M | after IX-R |
| IX-H2 | fetch | 2018-2025 finals (the pull 5k and 7i register), postseason game lists through the F-SCORE plan's `postseason.py` (built here to FS-1's section 4.1 spec if FS-1 has not landed), about 270 postseason winProbability feeds into `.cache/win_prob_post/`, never `.cache/win_prob/` (the play-by-play corpus globs every `*.json` there, `tools/build_pbp_corpus.py@64bf1bb3:912`, `:938` (in build()), and cannot tell a postseason game apart); only the intensity lab reads them; counts only | a lab tool under `tools/` | counts reconcile to the corpus census | `.cache/` only | S | INT-B1 |
| IX-H3 | lab | `tools/intensity_lab.py`: panel, logistic with offset, twins, controls, CR1, the one-run guard (reading the artifact and the section's result block) and the date guard, a counts-only mode; the synthetic G_REF computed and recorded in this commit; fixtures only | `tools/intensity_lab.py`, `test_intensity_lab.py` | refuses before its date and a second run | built, unread | L | after IX-H1, IX-H2 |
| IX-LOOK | look | Stage 1, once, under the crash protocol; writes `data/game_intensity_eval.json` and the registry row `game_intensity_effects` | as above | none | adjudicates stage 1 | S | the later of 2026-11-02 and the day after the World Series, after 5c-B, 5c-C, 5d, 5k and 7e-D are recorded or closed, never on another look's date |
| IX-S1 | chip | `betting_intensity.py` in the `betting_dugout.py` idiom (no write target; returns no probability, edge, expected value, Kelly figure, slot, badge or record field), one seam in `betting_export.build` passed to nothing, the /betting/ game-card and Model Watch chip, the DFS slate chip (INT-A3), glossary "Game intensity" and "Stakes multiple", registry row `betting_intensity_index` (descriptive, the `leverage_board` precedent) | `betting_intensity.py`, `betting_export.py`, `assets/betting.js`, `dfs_export.py`, `assets/dfs.js`, glossary, registry | `test_betting_intensity_fence.py` (no pricer module or `tools/betting_*.py` imports it or names the key; no shadow, record, calibration or slot row carries an `ix_` key; the renderer never draws the chip on a started or settled game); DFS vocabulary test | disclosure only | M | class 2 behind `SHOW_INTENSITY_CHIP = False`; no slate exists before Opening Day 2027 |
| IX-D1 | dark | The dark builder: team columns `ix_elo`, `ix_po_pct`, `ix_ws_pct`, `ix_proj_wins` and an `ix_games` block per vintage; schema = the next number after the last landed BUILDER in commit order, not waiting for 5j's or 5l's builders | `leaderboard_vintages.py`, `betting_model.py` (DARK tuple only) | schema pins; strictly-before; no served path reads `ix_` (AST and string) | dark | M | before Opening Day 2027; the next schema number by builder commit order, not waiting for the 5j and 5l builders (8.D row 3); G_REF from Q10_07 |

**Queue tasks.** IX-R is Q10_02 (a head task: the gap if a slot is free, else the first slot after
step Z, before the World Series ends); IX-H1 Q10_05; IX-H2 Q10_06; IX-H3 Q10_07; IX-LOOK Q10_08
(dated, refuses early); IX-S1 Q10_09; IX-D1 Q10_20 (before Opening Day 2027). The Futures stamp for
finding F1 and the registry text for F2 are Q9_01.

**Not built (and why).** A Postseason tab of odds on /betting/: the MLB Scores plan owns the live
bracket and series state with no odds (8.E), and the Futures simulator is stale in October (F1); a
bracket-state simulator for the 2027 postseason is INT-A2 (b), a new predictive number with its own
registry row and forward record. A Franchise "playoff performance" leaf: the Franchise NEVER list
(`franchise_export.py@64bf1bb3:105-106` (at 'FORBIDDEN_KEYS'), `:1191` (at 'divisionChamp'), `:1194` (at 'ou_mkt')) forbids pennants and titles as served fields and any
decision-quality grade, and the F-SCORE plan now owns the postseason record on Franchise (its
amendment lifts the pennant and title ban for results only); the lane's B3 is therefore not asked.

**Honesty status.** The chip is a rendering beside a price, not a candidate, column or look, and a
rendered value is not a measurement (the fence test pins it). Every relation of an `ix_` column, the
index, a component or a close variant (odds swings, games behind, magic numbers, clinch flags, Elo or
projected-wins asymmetry offered as stakes, a calendar term, the chip's values) to an outcome or a
price before that stage's look disqualifies the stage. Not a relation: the Futures board and its
ledger, the chip on a game not yet started, counts-only runs, other sections' own looks.

**Dependencies.** F-SCORE FS-1 (`postseason.py`); the listed 2026 looks (5c-B, 5c-C, 5d, 5k, 7e-D)
for stage 1; the Scores plan renders the chip only from the `intensity` block
`betting_export` writes, behind the same flag, pregame only.

**Effort.** IX-R S, IX-H1 M (one Fable 5.1 review of the conditioning code), IX-H2 S, IX-H3 L (Fable
5.1 recommended), IX-LOOK S (Fable 5.1 recommended), IX-S1 M, IX-D1 M.

**Owner questions raised (defaults in bold; INT-A1 to INT-A3 in batch 9, INT-A4 and the INT-B questions in batch 10 of 8.G).** INT-A1 should /betting/ price postseason games
(**no: the incumbent has never been fitted or graded on one; the board stays regular-season only**;
price them labelled "never graded on a postseason game" and keep them out of the slots and the
record; price them and let them fill the slots and the record). INT-A2 postseason odds (**none: the
Scores plan's bracket is the October view, and the Futures tab is labelled "as of the end of the
regular season"**; a registered bracket-state simulator for the 2027 postseason). INT-A3 the chip on
DFS (**yes, with the DFS copy**; betting only). INT-A4 rivalry (**a label with no weight; division
pairs already carry D**; MLB's designated interleague rival pairs at weight 0.05 taken from Q; a
curated historic list). INT-B1 the free fetches (**about 285 requests into `.cache/`**; also the
2000-2017 postseasons; no fetch). INT-B2 postseason games in the pricing read (**their own
descriptive frame, never pooled, not graded in stage 2**; graded in stage 2 as 5e does). INT-B4 the
serving standard for concentrated effects (**unchanged; the index stays a disclosure**; register a
multi-season rule that combines per-season statistics without pooling).

### P8.10 Pixel branding: the logos and marks, made better on their own grid (ask 2; lane pixel_branding)

**Lane summary** (`<part8>/pixel_branding.md`; renders, candidates, the generator prototype and
the measurements under `<part8>/branding/`). Half of every mark is already pixel art: the
PixelMplus12 Bold letters. The other half (the lob arc and the ball) is vector. The refinement redraws
the vector half on the letters' own grid (u = 1/12 em: advance 6 u, x-height 6 u, stems 2 u, rules
1 u, the queue-3 icon stroke rule), keeping every shape, colour, proportion and position the owner
likes. **The ask reopens exactly one row of plan 5.7.5** ("any pixel wordmark or monogram",
the row of section 5.7.5 that begins "Pixelated team logos, headshots, third-party marks") under the reopen standard (a new owner instruction); the
rest of that row stands (no pixelated team logos, headshots or third-party marks; no ball as an
icon), and queue 3's brand rule "never redraw the wordmark or the P/X monogram" (in queue 3's PX
preamble, `preambles/PX.txt` of the dynamic queue) keeps binding every queue-3 task, which is why
Q11_01 carries the P8 preamble instead. README `:139`
("Do not redraw or re-letter the wordmark, or swap the font") holds literally: the letters ARE the
font's own bitmap, sampled from `branding/fonts/PixelMplus12-Bold.ttf`.

**Sixteen defects in today's marks, measured on the served pages** (`<part8>/branding/current/`,
board `current_overview.png`). The two that matter most: **F1** in dark mode the arc and the apex
ball's rim use the LIGHT ramp (four literal hex stops, `build_site.py@64bf1bb3:653-656` (in eephus_merged_wordmark())); the navy end reads
1.22:1 on the dark nav, so the right third of the arc disappears; **F2** the load animation never
traces the arc in Chromium (`pathLength="100"` with `vector-effect="non-scaling-stroke"`,
`build_site.py@64bf1bb3:657-658` (in eephus_merged_wordmark()), makes the dash slide with a gap and the whole arc pop in at about 0.8 s).
Others: F3 leaving the hero replays the load animation; F4 four different ball drawings across the
SVG masters, the PIL rasters, the apex and the hand-kept navs; F5 the wordmark sizes sit off the
font's grid (53 percent of letter pixels partial at 22 px); F6 the 16 px favicon reads as an "O"
(PX-23 answers it); F7 the PROSPX monogram depends on fonts this machine lacks (it renders in
Georgia); F8 the portable wordmark is not in the brand face; F9 the share card writes "EEPHUS.IO" in
capitals with a second ball and a stale module list in a machine-dependent system font; F10 every
module shares one OG image; F11 the `.io` colour disagrees (site lilac, README and export frame gold);
F12 the GFX headers write capitals; F13 the nav apex ball is a dark disc in dark mode; F14 the mark
depends on the webfont arriving; F15 the PROSPX title and CollegeSavant bar are off the grid; F16 the
homepage sidebar `.io` is ink, not lilac.

**Three directions, rendered in place on the real pages** (each at 1280 light and dark and 390, in
`<part8>/branding/candidates/<name>/`):

| Direction | What it is | Page equals the PNG export | Motion | Change against today |
|---|---|---|---|---|
| **B Stepped (recommended)** | the same lockup as pixel art: stepped arc runs in eight ramp bands mixed from the existing stops (so the arc finally switches to the dark ramp), hand-tuned ball bitmaps, a 22 x 22 pixel PROSPX mark, module lockups and a share card per module | yes, 0 pixels off at s 2 and s 6, both themes, DPR 1 and 2 | the arc lights run by run, the ball drops in whole pixels | moderate |
| A Hinted | today's smooth ramp made crisp: a hard-edged stroke, letters snapped to the grid, the ball hand-tuned | no (up to 12 levels off on 565 of 41,580 pixels in dark) | a column wipe | smallest |
| C Lamps (rendered, not offered) | the arc lit on every other cell, so the logo at rest looks like the loader at rest | yes | a lamp chase | largest; the nav arc reads as a dotted line, and it would reopen the 09-24 rejection of the scoreboard as an identity anchor (plan 5.7.5, 'scoreboard as an anchor ... a third anchor'), which ask 2 did not reopen, so PB-Q1 does not offer it |

Boards: `candidates/B_stepped/B_stepped_overview.png`, `candidates/A_hinted/A_hinted_overview.png`,
`candidates/C_lamps/C_lamps_overview.png`; side-by-side `candidates/compare_hero_1280.png`,
`compare_nav_masthead_1280.png`, `compare_prospx_mark_1280.png`; the system sheets under
`candidates/system/`; the real CSS for all three in both themes in `candidates/motion_demo.html`.
Layout cost, measured: nav height unchanged (72 px at 1280, 63 at 390); homepage masthead +27 px at
1280 with the s 6 hero (72 px letters against today's 64; a 48 px s 4 hero would be about 23 px
shorter than today, a reversible default); 0 horizontal scroll on every page. Motion, measured in
Chromium: 0 layout-shift entries, 0 animations running after 3.2 s, reduced-motion frames identical,
nothing replays when the pointer leaves, nothing plays under reduced motion. Byte cost about +220 B
gzip per page for the nav and +1.9 KB gzip on the homepage.

**Production method.** One deterministic generator, `tools/pixel_brand.py` plus the plain-data
source `tools/pixel_brand_src.py` (prototype in `<part8>/branding/proposed/tools/`): letters sampled
from the font file with fontTools at cell centres (exact, because every outline point sits on the
83.33-unit lattice), hand-tuned ball bitmaps for 8, 12, 13, 16, 24 and 32 px, token-only SVG
fragments, favicons, app icons, share cards, portable marks and the animated export, 57 outputs in
8.8 s; `--check` regenerates into a temp folder and reproduces all 57 (text byte for byte, images
pixel for pixel); no system font, no randomness, no anti-aliasing; writes only `assets/`,
`branding/` and `favicon.ico`, never `data/`. It replaces `tools/generate_brand_assets.py` (whose
Consolas and Georgia picks make today's committed images depend on the machine that ran it).

| ID | kind | item | files | test | eff | gate / owner |
|---|---|---|---|---|---|---|
| PB-01 | generator | `tools/pixel_brand_src.py` and `tools/pixel_brand.py`, writing `branding/pixel/` sheets and `assets/brand/` fragments that nothing references yet; all three styles behind `--style`, the committed default per PB-Q1 (stepped until answered); both seam styles, the committed default per PB-Q2 (inward until answered) | two new tools | `test_pixel_brand.py` (`--check` reproduces every output; glyph bitmaps equal a fresh font sample; `RAMP`/`TOKENS` equal the `site.css` blocks; fragments token-only, integer coordinates, `aria-hidden`, at most 6 KB; ball size 4 s (+1 at odd s); ICO carries exactly 16/32/48 each equal to its bitmap) | M | none; runs between queue 3's PX_D_visualizations and PX_E_gfx_brand_sweep with the P8 preamble, never the PX preamble (8.C) |
| PB-02 | tokens | `--ramp-1..5`, `--arc-1..8`, `--iridescent-steps`, `--ball-face`, `--seam-1..4` (and `--wm-g*` for A) in both theme blocks, derived from colours the site already has | `assets/site.css` (`:59-272` (in :root), `:332-434` (in [data-theme="dark"])) | `test_design_tokens.py`; token parity | S | after PB-01 |
| PB-03 | swap | `eephus_merged_wordmark()` returns the committed fragment per placement (s 2 nav and sidebar; s 6 hero with the s 4 phone variant), wrapped with visually hidden `eephus.io` text; the three hand-kept navs carry the s 2 fragment verbatim; motion per PB-Q4 (`step-end` only, reduced motion stops everything, hover included); the dark glow moved to `drop-shadow`; ALL behind `build_site.PIXEL_BRAND = False`; the flag-off path (today's markup) gets the four defect fixes that hold in every direction (F1 the arc stops as tokens with a dark block; F2 the dash drawn without the vector-effect so it traces; F3 the hover replay on inner groups; F16 the sidebar `.dot` rule) | `build_site.py@64bf1bb3:649-705` (in eephus_merged_wordmark()), `:977-978` (in _nav()), `:3465` (in build_home()), `:3491` (in build_home()); `assets/site.css@64bf1bb3:525-531` (in .eephus-nav .eephus-wordmark), `:1140`, `:1264-1379`; `prospx/index.html@64bf1bb3:8821` (at 'preserveAspectRatio'); `collegesavant/index.html@64bf1bb3:34` (at 'preserveAspectRatio'), `collegesavant/pitcher_index.html@64bf1bb3:34` (at 'preserveAspectRatio') | `test_brand_sync.py` (the three navs equal the s 2 fragment byte for byte), `test_pixel_brand_motion.py`, `test_collegesavant_nav_in_sync.py`, `restamp_hand_authored_pages()` | M | after PX-10 (the same hand-page nav lines) and PB-02 |
| PB-04 | icons | Favicon 16/32/48 from the ball bitmaps, `favicon-32.png`, apple-touch, icon-192/512, maskable, the 16 px footer mark; written to `assets/brand/` while the flag is off and copied to the served paths only at the flip (browsers fetch `/favicon.ico` without a link); if queue 3's PX-23 already shipped a hand-hinted ball, regenerate from the same anatomy | `favicon.ico`, `assets/favicon*`, `assets/apple-touch-icon.png`, `assets/icon-*.png`, `build_site.py@64bf1bb3:500-503` | ICO bitmap checks; the footer check of T7 | S | after PB-01 |
| PB-05 | PROSPX mark | The 22 x 22 pixel mark at 2x; the title at 36 px on the grid with 0 tracking; a banded 3 px rule; the monogram font stack deleted; `prospx_ball_logo()` callers at 40 px and up use the pixel mark; behind the flag | `prospx/index.html@64bf1bb3:965-1017` (at 'MLB Prospect Portal'), `:1052-1059`, `:8882-8907` (at 'goToProspectsBoard'); `build_site.py@64bf1bb3:669-691` (in prospx_ball_logo()) | `test_no_hardcoded_colors.py` (the PROSPX hex budget unchanged) | M | after queue 3's PX_D (PX-24 edits the same file) |
| PB-06 | mastheads | After PX-07's 32 px icon: module titles on the grid (24 px, 0 tracking) with a 1 u `--iridescent-steps` rule; the CollegeSavant bar gets the 12 px icon crop | the 16 `build_site.py` h1 sites, `site.css@64bf1bb3:734`, `collegesavant/index.html@64bf1bb3:72` (at 'CollegeSavant'), `collegesavant/styles.css@64bf1bb3:49-52` (in .cs-bar-title) | a T2 extension (one masthead icon and one rule per page) | M | after PX-07; never beside queue 6's masthead text work |
| PB-07 | share cards | A new lowercase default card (one ball, no stale module list) and `assets/og/<module>.png` per module passed as `image=` at each `page()` call; the hand pages' `og:image` pointed at their cards; the one-line descriptions cut from each page's own meta description, owner-approvable | `build_site.py@64bf1bb3:455` (at 'DEFAULT_SHARE_IMAGE'), `:984-1037` (in _social_meta()) and module builders; `prospx/index.html@64bf1bb3:23` (at 'summary_large_image'); `collegesavant/index.html@64bf1bb3:14` (at 'summary_large_image') | a page-to-card map test; copy checks | M | after PB-01 |
| PB-08 | exports | `_brandCompose` paints the pixel lockup at integer scale; the GFX headers draw the lockup instead of "EEPHUS.IO" (F12) | `assets/eephus-export.js@64bf1bb3:466-503`; `assets/eephus-gfx.js@64bf1bb3:150-161` (in renderBoard()), `:379-390` (in renderNewsDay()), `:528-539` (in renderSourceComp()) | `test_board_card_typography.py`, `test_gfx_chip_layout.py`, an integer-scale check | M | with or right after PX-18 |
| PB-09 | README | Regenerate `branding/marks`, `branding/animated`, `branding/social`; README "Logo usage", a "Pixel marks" section after PX-21's "Pixel icon set", the asset index; the `.io` answer (PB-Q3) recorded; "hand-authored" becomes "generated from `tools/pixel_brand_src.py`" | `branding/README.md@64bf1bb3:110-145` (under '## Logo usage'), `:168-183` (under '## Share cards'), `:192-222` (under '## Asset index') | copy checks | S | after PX-21 |
| PB-10 | sweep + flip | Extend T7: the page's lockup equals the committed bitmap (0 px off, DPR 1 and 2, both themes); reduced-motion frames identical; zero layout shift on `/` during the load animation; the nav height unchanged; then flip `PIXEL_BRAND` in its own commit | `tools/px_sweep.py`, `test_px_sweep.py`, `build_site.py` | itself | S | after PX_E's T7; flip after step Z and PB-Q1 not "None" |

**Queue tasks.** PB-01 to PB-10 are Q11_01 to Q11_10 in order (PB-10 carries the flip).

**How it fits queue 3.** PB-01 (Q11_01) runs between PX_D_visualizations and PX_E_gfx_brand_sweep in
the dynamic queue with the P8 preamble; queue 3's PX preamble carries the brand rule "never redraw the
wordmark or the P/X monogram", which is the plan 5.7.5 row ask 2 reopened, so Q11_01 never runs under
it. The orchestrator amends the PX_E spec file so PX-23 reads: "PX-23 emits favicon-32.png, favicon.ico and the 16
px footer mark from the ball bitmaps of tools/pixel_brand.py (committed by Q11_01) instead of hand
pixels in tools/generate_brand_assets.py; if Q11_01 has not landed, PX-23 runs as written and Q11_04
regenerates the files later." The ball bitmaps are the same in every direction, so this holds even if
the owner answers PB-Q1 "None". Overlaps checked: PX-05 retires `prospx_ball_logo` under 40 px (agrees
with PB-05 at 40 px and up); PX-07 is PB-06's base; PX-10 and PB-03 share the hand-page nav lines
(PB-03 goes after); PX-11's loader keeps its own grid under A or B and reads `ARC_RUNS` only under C;
PX-18 and PB-08 share the export files; PX-21 and PB-09 share the README; PX-24 and PB-05 share
`prospx/index.html` in different blocks; queue 6's masthead text work shares the h1 strings with PB-06.

**Honesty status.** Display and asset work only: no served number, data key, model, registry row,
eval artifact, gate or clock is touched. Do not build: an animated favicon, any looping logo motion
(the glint plays once per page view; the starfield and the WIRE marquee stay the only loops), a second
hand-drawn letter set, foil or rarity framing on any mark, a lamp-mask masthead, numbers or grades on
any share card, pixelated club logos, a gold `.io` on dark.

**Landing rule.** Served visual swaps sit behind `PIXEL_BRAND = False` (next to `EEPHUS_VERSION`,
`build_site.py@64bf1bb3:518` (at 'EEPHUS_VERSION')) and flip after step Z; with the flag off, `eephus_merged_wordmark()`,
`FAVICON_LINKS` and `DEFAULT_SHARE_IMAGE` keep today's files and the generator writes only new paths.

**Effort.** PB-01 M, PB-02 S, PB-03 M, PB-04 S, PB-05 M, PB-06 M, PB-07 M, PB-08 M, PB-09 S, PB-10 S;
all Opus 5.5.

**Owner questions raised (defaults in bold; batch 5 of 8.G; the PNG boards are named in each option).** PB-Q1 the
direction (**B Stepped**; A Hinted; none, fixes only; C Lamps is not offered because it would reopen the
09-24 rejection of the scoreboard as an identity anchor). PB-Q2 the seams (**inward `) (`, the
classic, already on the favicon PNGs, app icons and share card**; outward `( )` as in the SVG masters,
which at 16 px still reads as the "O" PX-Q4 set out to fix). PB-Q3 the `.io` colour (**lilac in both
themes, as the site serves it**; gold on light as the README says, 2.22:1 on the nav, the faintest
colour in the lockup). PB-Q4 motion (**pitch on the hero, replay on hover, one glint per page view**;
without the glint; the hero only; none). Defaults taken without a question (display-only,
reversible): the s 6 desktop hero; the P/X in the bold serif the page renders today, not a blackletter
drawing; the 1 u rule under every module title; a share card per module; the default card keeps
"sabermetrics" and drops the stale module list.

### P8.11 Referenced only (handled outside this workflow)

- **Ask 1, the projected $/WAR path (VAL_5).** Designed in `scratchpad/dpw_path/` (DESIGN_v2.md,
  REGISTRATION_DRAFT_v2.md, QUEUE_TASK_v2.md) and queued as the first queue-3 task,
  VAL_5_projected_dpw_path, in the dynamic queue; owner batch 1 answered 2026-09-30 (OD-6 serve at the
  past-winter pass, OD-7, OD-2, OD-1; `DECISIONS_FOR_OWNER.md@2026-09-30:600-611` (under 'ANSWERED 2026-09-30 (AskUserQuestion), projected $/WAR path, batch 1')), batch 2 asked before its flip.
  Part 8 touches it only through W12 (Competitive Balance picks priced at VAL_5's future seasons, not
  queued) and the valuation inputs FAA-5 reads (`projGuar`), which move with VAL_1 and the epoch, not
  with VAL_5's gate.
- **The PLUS% board column removal.** Answered (M29-1, M29-2) and queued as
  `M29_PROSPX_PLUS_PCT_OFF_BOARD` in `scratchpad/writerq7b_tasks.json`. P8.4's board tasks run after it
  and must not reintroduce a ninth column.
- **The 2026 MiLB season for eFV drivers.** Handled in its own workflow. P8.1's eFV sidecar (PM-12,
  PM-13) reads MiLB pitch counts only for folds V 2017-2019 through `pitch_rates.player_lines` and never
  refetches or reshapes `.cache/milb_stats`, `milb_history` lean rows or the eFV matrices (STOP S6), so
  it cannot collide with that work.

### 8.F Findings handed to other owners (reproduce on the served path before any change)

| Found by | Finding | Evidence | Goes to |
|---|---|---|---|
| intensity | F1: the Futures tab republishes pre-bracket odds through the postseason | `proj_current.py@64bf1bb3:114` (in _fetch_schedule_raw()); `data/futures.json` built 2026-09-27T20:45Z, four clubs strictly between 0 and 1 | Q9_01 (label, class 1); INT-A2 |
| intensity | F2: the `playoff_odds_sim` registry text says blended talent; the code uses the pure 2027 roster prior | `proj_export.py@410cccce:2403` (in _attach_current_season()), `:2438` (in _attach_current_season()), `:2291-2297` (in _talent_prior_pct()) | Q9_01 (text); the projections lane decides the input under a read |
| pitch_metrics | `ip_per_gs` divides ALL innings by starts: 48 of 249 true 2025 starters overstated by 0.5 IP or more (max 3.83); the betting pricer reads it and three registrations freeze it | `sem_plus.py@64bf1bb3:104` (in derive_rates()); `betting_model.py@64bf1bb3:2620` (in _starter_share()); `betting_export.py@64bf1bb3:4489-4491` (in props_fair_lines()); `leaderboard_vintages.py@64bf1bb3:196` (at 'PITCHER_COLUMNS'); `docs/diamond-betting.md@64bf1bb3:5439-5444` (under '## 5j. Posted lineups') | never redefined; P8.1 ships `sp_ip_per_gs` as a new key; the betting lane owns any change |
| league_team_stats | Opening a season row on Overall makes the next rank print 3; every /mlbstats/ chart label is about 5 px tall at 390 px | `site.css@64bf1bb3:2378-2382`; `eephus-hub.js@64bf1bb3:143` (in histogram()), `:177` (in scatter()) | Q8_01 |
| baserunning, eBR | the League tab's `lview`/`lseason` collide with Leverage | `mlbstats.js@64bf1bb3:2776` (in readHash()), `:2793` (in readHash()) | 8.D row 1 (resolved in the specs) |
| dvm_difficulty | D-1, D-6, D-7, D-8 copy and registry text; D-2 to D-5 method defects; D-9 `farm_grade_backtest.py@64bf1bb3:65-67` (at 'VINTAGE_YEARS') scores list vintages 2018-2022 against realized graduate WAR, so the re-run plan item M02-22 proposes would read R-LV with an outcome | lane Part A.7 | DVM-0 (Q10_03); DVM-5 under its arm; D-9 to the owner of M02-22: exclude vintages 2020-2021 or wait for the R-LV look record before any re-run |
| links_efv_display | `club("constructor")` resolves through the prototype; `/franchise/#team=CWS`, `KC`, `OAK` render Arizona; `/prospx/#farm-org=CWS` renders "Unknown organization"; PROSPX rows nest buttons inside `role=button` rows; the IFA org link is a span with no href or tabindex | `eephus-hub.js@64bf1bb3:90` (at '_CLUB_BY'), `:108` (in club()); `franchise.js@64bf1bb3:139-160` (at 'TEAM_RE'); `prospx/index.html@64bf1bb3:54219-54224` (at 'decorateA11yRows'), `:25922` (in _ifaOrgLink()) | Q9_05, Q9_08 |
| links_efv_display | eFV rounded up on the country page ("77 -> 34" on 60 rows per country); consensus rounded nearest in `fvBadgeTooltip`, "Top FV", the farm GFX distribution and the Time Machine fallback | `prospx/index.html@64bf1bb3:28960-28965` (in renderCountryDetail()), `:11175-11229` (at 'fvBadgeTooltip'), `:52016` (in makeFarmPositionalNeed()), `:52362` (in _renderFarmDetailBody()), `:20924-20929` (at '_tmFvPill') | Q9_10 to Q9_13 |
| finance | F-1 the served AFFORD reads the class-year page while Gate 3 scored Y-1 space; F-5 realized arbitration credited to the season-end club (LAD 2026's $55.8M includes Skubal's $32.0M Detroit case); F-6 Gate 3 is invisible on /fa/; F-7 the tracker parser drops club headings | `fa_fit.py@64bf1bb3:933` (in affordability()), `fa_fit_backtest.py@64bf1bb3:349` (in build_rows()), `:391-394` (in build_rows()); `arb_dataset.py@64bf1bb3:127` (in _collapse()), `:184` (in war_daily_spine()); `tools/ingest_arbitration_ledger.py@64bf1bb3:103-109` (in _OUTCOME_PATTERNS) | F-1 a Gate 3 lever with its own registration (not built); F-5 Q9_18; F-6 Q9_19 renders the Gate 3 table even if the destination model fails; F-7 Q9_17 |
| wiring | the registry row `milb_park_factors` still describes the infeasible R-PARK experiment | `data/model_registry.json` | the registry lane X01 (text fix) |
| xwar (orchestrator note) | at 14:20:23 on 2026-09-30 three test files changed in the working tree while two `python.exe` processes ran | `xwar.md` header | resolved: the three files (`test_bayes_trade_value_policy.py`, `test_rest_of_season_control.py`, `test_value_framework_integration.py`) are in VAL_1's commit `410cccce`; 8.C's former action (2) is dropped |
| round-1 review (betting pipeline) | `data/betting_model_eval.json` is rebuilt from scratch every night: the daily step 9e-pre1 calls `betting_model.backtest()`, which builds `result = {...}` fresh and writes the whole file, so a foreign block written there by a one-time look is erased by the next nightly, and 5l's "persisted `mgmt_policy_gate` block" assumes a carry-forward that does not exist | `run_monthly.py@410cccce:3065-3076` (at '9e-pre1'); `betting_model.py@64bf1bb3:6360` (in backtest()), `:6417` (in backtest()) | Part 8's looks write their own tracked artifacts (`data/starter_workload_eval.json`, `data/game_intensity_eval.json`); the betting lane owns 5l's block and must give it a carry-forward or its own artifact before 2027-07-01 |
| fscore | the standings feed flags PHI `divisionChamp: true` beside ATL (2026 NL East) and `franchise.js@64bf1bb3:451` (in secSeason()) prints it | `franchise_export.py@64bf1bb3:311` (in _standings()) | the F-SCORE plan's FS-1 commit 1 |

### 8.G Owner questions

`<part8>/OWNER_QUESTIONS.json` holds 48 questions in 12 AskUserQuestion batches of exactly four, most
urgent first by their `needed_by`, then most outward-facing. Each question says what is decided and by
when; the recommended option is first with " (Recommended)" at the end of its label; every label is
under 60 characters and every option says in one sentence what choosing it changes. None re-asks an
answered decision in `DECISIONS_FOR_OWNER.md` (O5 and O7 are still open there; COSTPLUS-1 is the
numerator, M13-4 answered only the denominator; Q-E4 also settles the never-recorded G06; ETA-1,
ETA-2, VAL1-Q1 and VAL1-Q2 were answered on 2026-09-30 and are carried by queue 8's tasks). The wiring
lane's third and fourth open questions carry the ids W-OQ3 and W-OQ4 because the parallel eFV 2026 plan
asks its own numbered OQ questions of the same owner.

| Batch | Needed by | Questions |
|---|---|---|
| 1 | 2026-10-01 to 2026-10-06 (COSTPLUS-1 before M13 runs on 10-01; EPOCH-Q2 before the 10-02 amendment; EPOCH-Q1 by 10-03; EPOCH-Q3 before step A) | EPOCH-Q1 E5 path; EPOCH-Q2 PROJ_PATH_SHAPE against the epoch; COSTPLUS-1 the Cost+ numerator; EPOCH-Q3 O7 arm set |
| 2 | 2026-10-03 to step Z (EPOCH-Q5 by 10-03 23:59 and only after a 'hold' answer to EPOCH-Q1; FA-DEST-1 before Q9_02; OUTLOOK before Q9_03) | EPOCH-Q4 O5 displayed WAR; EPOCH-Q5 landing under a hold; OUTLOOK (merged W-OQ1 and OUTLOOK-1); FA-DEST-1 (merged with FA-DEST-2) |
| 3 | before Q9_02 and Q9_17a register (the gap or the first slots after step Z) | FA-DEST-3; FA-DEST-4; ARB-CLUB-1; ARB-CLUB-2 |
| 4 | before Staff Gems stage 0 (Q10_17) | SG-Q1; SG-Q2; SG-Q3; SG-Q4 |
| 5 | before Q11_01 (just before queue 3's PX_E; the PNG boards are named in the options) | PB-Q1; PB-Q2; PB-Q3; PB-Q4 |
| 6 | before p8_wiring's eFV display tasks (Q9_10 on) | Q-E1; Q-E2; Q-E3; Q-E4 |
| 7 | before p8_metrics' League and Teams tabs (Q8_13a, Q8_13b, Q8_14) | LTS-1; LTS-2; LTS-3; LTS-4 |
| 8 | before Q8_04, Q10_04b (from 10-11), Q10_10 and Q9_08 | PM-Q1; PM-Q3; PM-Q4; Q-L1 |
| 9 | before Q9_07, Q10_02 (before the World Series ends) and Q10_09 | Q-L3; INT-A1; INT-A2; INT-A3 |
| 10 | before Q10_02 registers (before the World Series ends) | INT-A4; INT-B1; INT-B2; INT-B4 |
| 11 | before DVM-1 (Q10_12) | Q-DVM-1; Q-DVM-2; Q-DVM-3; Q-DVM-4 |
| 12 | when their items start (Q10_16 takes the Q-DVM-5 and Q-DVM-6 defaults if unanswered) | W-OQ3 (W11); W-OQ4 (W08); Q-DVM-5; Q-DVM-6 |

**Not asked, and why.** W-OQ2 (resolved by the class rule, 8.D row 11); Q-L2 (the ask itself says a
prospect's club links to its farm-system page); PM-Q2 (the Pitches view plus All, display-only and
reversible; S16 asks it only if the view fails the 768 fit); LTS-5 to LTS-8 (no club filter on League,
box-score statistics 2000-2026, a 15-game or 5-start window with a 30/10 toggle, the phone chart fix:
display defaults, reversible, taken); W-OQ5 (the HoF line's basis follows O5, EPOCH-Q4); INT-B3 (the
Franchise postseason record is F-SCORE's, 8.D row 8); PB-Q1's lamp direction (it would reopen the 09-24
rejection of the scoreboard as an identity anchor); the pixel lane's secondary defaults (the s 6 hero,
the serif P/X, the 1 u title rule, a card per module, the default card's line); the LTS lane's choice to
track the frozen completed-season panels (repository hygiene, taken). Every default taken is recorded
in `DECISIONS_FOR_OWNER.md` by the task that relies on it.

### 8.H What can and cannot be claimed (the ceilings, stated before any build)

- **Pitch metrics.** P/IP, P/PA and P/BF are records; PAR is a descriptive ratio index and predicts
  nothing. Starter P/BF is steadier than P/IP (year-to-year r 0.697 against 0.512, 334 pairs), and
  any copy that prints a stability figure reads it from `data/pitch_rates.json`. The workload model can
  claim only what its stage 1 measures (outs and pitches per start on 2024-2025 against the served
  innings share), and it credits pitch rates only if T2 beats the starts-only comparator and the
  lineup's P/PA only if T1 beats D2; otherwise the words are "starts-only length over a 365-day
  window". Nothing about game prices OR PROPS PRICES before a stage-2 pass, which cannot come before
  July 2027: `SERVE_WORKLOAD_PROPS` waits for 5l's `mgmt_policy_gate` block and the stage-2 look, and
  the only earlier display is the registered fence (no market comparison, value row, slot, shadow or
  record row).
  The honest expectation for P/PA as an eFV driver is "refused" or a tie under 0.005.
- **League and Teams.** Every number is a sum, a pooled ratio, a served value re-weighted or MLB's
  published expected record. 100 on a team rollup is the average QUALIFIED PLAYER, not the average
  team (league means 99.85, 102.09, 101.62, 100.81 ride the payload). W minus xW is the gap between
  the record and the record the runs imply, never "luck". No fit, correlation or slope between any
  Teams column and wins or runs is computed or printed.
- **Links and eFV display.** No number moves from a link. The eFV-only display rule is a display
  rule: eFV still TIES consensus on the scored frame (vm2 0.4074 against 0.4129, not resolvable,
  commit `12bf26eb`), and no page may present the switch as an accuracy gain.
- **Finance into FA.** Payroll space alone is indistinguishable from random in the Gate 3 backtest
  (MRR 0.1350 against 0.1332, floor 0.0139); the Fit's analog leaves little room (0.1669; no refit of
  its features has beaten it). The Ledger block's contrast may read NULL, and the plan ships the
  plain temperature-scaled Fit in that case and records the null. Club arbitration process is
  descriptive until section 12's power precondition says otherwise.
- **Wiring.** The winter frame is contract arithmetic, not a better forecast, until the 2027 read,
  and it never moves an FA fit list. The transaction timeline carries no availability forecast (the IL
  playing-time adjustment failed on both sides). The Dynasty lens is "Next to be graded": the model
  predicts who a source grades next and has no skill on the grade's level, so no copy calls anyone a
  sleeper.
- **DvM+ difficulty.** A pass on H2 says list grades rise less often from higher rungs, never that
  developing talent is harder there (the bounded scale, regression to the mean and graduation all
  produce it). Validation will probably tie on prediction; the composition check carries the decision.
- **Staff Gems.** The gate can see coach effects about as large as today's whole organization spread
  and nothing smaller; a null is the likely result. The data cannot separate a coach from his
  organization, his co-workers or his players, so no page may say a coach caused anything, and nobody
  is ever shown below the mean.
- **Intensity.** 2026 cannot answer a pricing question (763 graded games). Stage 1's moneyline
  members IX-A and IX-A2 fit on 2018, 2019, 2021 and 2022 and grade only 2023-2025 (7,289 games, about 1.5 points of
  win probability per SD at 80 percent power), and IX-A's first criterion reads only the focus set
  (`|ds| >= 0.05`, a subset whose size is counted before the look), where a 5-point effect needs about
  1,080 focused games for an expected t of 1.645; the full 17,008-game frame's figure of about 1 point per SD applies only to
  reads that use the whole frame, never to the graded moneyline members. That answers the owner's questions at a useful resolution and
  licenses no price; under rule 4 a stakes term will very likely never pass. Clutch is
  a record of when production came, not a repeatable skill, so no per-player big-game number exists.
- **Branding.** Display only.

### 8.I Definition of done for Part 8

0. Part 8 appended to `docs/master-plan-2026-09-24-final-pass.md` and the plan committed before step A
   (8.C action 0).
1. The starter-workload section committed alone before 2026-10-05, disclosing first any 5c-B, 5c-C or
   5d result recorded when it committed (S8); the game-intensity section committed before the 2026
   World Series ends and before any intensity code.
2. Every task in `QUEUE_TASKS.json` done in the dynamic queue (commit hash in
   `_finalpass_2026-09-24/EXECUTION.md`), deferred with the owner's answer recorded, or stopped with its
   blocker line in its REMAINING.md and re-armed.
3. Every flag in 8.A flipped in its own commit after step Z (keys, row counts and the blast radius
   in the message) or recorded as held with the reason.
4. Registry rows added and `validate()` clean: `par`, `starter_workload_xouts`, `offense_plus`,
   `rotation_plus`, `bullpen_plus`, `leverage_deploy_plus`, `team_dem_plus`, `club_fa_spend_profile`,
   `arb_club_process`, `fa_destination`, `game_intensity_effects`, `betting_intensity_index`,
   `dvm_difficulty` (and, when their
   tasks run, `staff_gems`, `org_role_development`); `MODEL_REGISTRY.md` regenerated;
   `test_generated_docs_in_sync` green.
5. Every registered look in this part taken once on its date under the crash protocol with its results
   section filled verbatim in its own tracked artifact and document, or recorded NOT READ, UNDERPOWERED,
   INDETERMINATE or VOID by its own text.
6. Every new surface rendered at 390, 768, 1024, 1280 and 1440 in both themes (the shared render clause
   every spec carries) with zero page overflow and zero console errors beyond aborted off-loopback
   requests; `tools/copy_lint.py --check` and `tools/strip_emdashes.py --check` exit 0.
7. The questions in `OWNER_QUESTIONS.json` answered or their defaults recorded.
8. The Part 8 bundle copied to `C:/Users/noah/baseball-projects/_finalpass_2026-09-24/part8/` and the
   memory note for the pass updated with the commits and the owed looks.

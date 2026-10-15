# Re-baseline: the served HEM+ family on the 2016 to 2026 pair set, and HEM+ against xwOBA (pre-registered 2026-10-15)

This is the ONE document that `docs/HEM_RIV_REGATE_GATE.md` R1-12 owes: "the next
re-baseline, including the separately pre-registered `hem_plus` against xwOBA re-gate, in
its own document, written before its own numbers". It covers two things that R1-12 binds
together and that NOV15_REGATES item 5 (2026-10-14) refused to split:

1. **The re-baseline** of re-gate 1's arms A1 (`xhem_plus`) and A2 (`fwdhem_plus`) on the
   pair set EXTENDED by the 2025 to 2026 block, which R1-12 said could not be added before
   2026-11-15.
2. **The new leg A3**: `hem_plus`, as served, against Savant xwOBA, with verdict weight,
   which R1-10 recorded as a prior and refused to bolt onto the old row post hoc.

Owner answer of 2026-10-14 (DECISIONS_FOR_OWNER.md, "NOV15 answers"): "pre-register the
proper comparison, then run once today". Under EW3-5 the registered date (2026-11-16 or
later) is WAIVED; the run is an **OWNER-WAIVED EARLY READ** and is recorded as one in this
document, in the artifact and in every registry row it moves. The only thing a waiver cannot
supply is data that does not exist: section 2 says what exists and section 10 says when the
run refuses.

Producers: `tools/hem_xwoba_regate_lab.py` (new, this registration's one producer) ->
`data/hem_xwoba_regate_eval.json`; `tools/register_hem_xwoba_regate.py` (the idempotent
registry mover); `tools/plus_lab_harness.py` (conventions v1 and v2, the logged
season-complete override); `tools/efv_power_lab.holm_family`; `tools/xhem_plus_lab.py`
(loaders only). Registry rows under test: `xhem_plus` (validated), `fwdhem_plus`
(provisional), `hem_plus` (validated against AVG and raw wOBA, never against xwOBA).

Written in the shape of `docs/HEM_RIV_REGATE_GATE.md`. Where this document and a later
measurement disagree, **the measurement is what this gate uses**, and the disagreement is
recorded rather than edited away.

**NOTHING IN THIS DOCUMENT WAS COMPUTED.** No lab was run on the extended pair set, no
2025 to 2026 Savant pair was scored by this family's labs (the 2026-09-18 run dropped every
one of them as a partial-outcome pair), and the run happens after this file is committed
alone. Every figure quoted below is a PRIOR, labelled as one in section 0.

---

## 0. HONESTY CLAUSE, and it comes first

| object | status on 2026-10-15 | consequence |
|---|---|---|
| the 2026-09-18 served-construction cells on the 1,871-pair set (A1 D4: rho 0.4619 vs 0.4108, v1 gap lo95 +0.0241, v2 lo95 +0.0317; A2 D4: rho 0.4613 vs 0.4543, v1 gap lo95 -0.0012, v2 lo95 -0.0076) | **READ** (`data/xhem_served_regate_eval.json`, the registry notes) | the 2016 to 2024 predictor rows are not virgin for A1 and A2; only the 2025 block is. The re-baseline is therefore a CONFIRMATORY read on an extended set, labelled so in the artifact, and the frozen-subset reproduction in section 5 is a reproduction check, never pre-registration |
| served HEM+ integer against next-year wOBA on those rows: rho 0.4148 (the A1s sensitivity, "served xHEM+ 0.4619 against served HEM+ 0.4148") | **READ** (registry notes of `xhem_plus`) | the A3 candidate's forward rho on the 2016 to 2024 rows is known to four decimals; A3 is CONFIRMATORY on those rows and virgin only on the 2025 block |
| HEM+ losing to Savant xwOBA outright, eval-normalized, on 1,871 pairs (0.4084 vs 0.4456, lo95 -0.0601 v1, -0.0705 v2; the 2026-09-17 bake-off) | **READ** (R1-10, the `hem_plus` notes) | A3's direction is a strong prior. A3 is pre-registered as EXPECTED TO BE REFUTED (section 8) so the deprecation, if it lands, cannot be read afterwards as a surprise, and so nobody hunts for a convention that rescues it |
| the pWOBA re-gate's xwoba_alone rho 0.4948 on its own 953-pair frame (NOV15 item 1, 2026-10-14) | **READ**, on a different frame (FA projection pairs, PA floors and seasons of its own) | not a prior for this pair set; quoted only so the reader knows it was seen |
| anything on the 2025 to 2026 block of THIS pair set | **NOT READ.** The 2026 Savant expected-statistics leaderboard sits in `.cache/savant_mlb/expected_batter_2026.csv` (captured 2026-10-14, 662 rows, max PA 726, 86 hitters at 600+ PA: a complete regular season); no lab of this family has scored it against anything | the block is virgin; its n is a prior expectation (section 2), not a count |

Calling the 2016 to 2024 cells pre-registered would be false. The rest of this document is
pre-registration in the ordinary sense.

---

## 1. Standing rules inherited, restated so they bind

1. **The +stat lab conventions module v2** (`tools/plus_lab_harness.py`): complete-outcome
   pairs only, unrounded `*_raw` predictors except where the served object is itself an
   integer (rung D4, declared here), both target conventions and both bootstrap designs
   published side by side for every cell, always.
2. **Season completeness is the owner's logged override, not a guess.** The run passes
   `--season-complete-asof 2026:2026-10-01` (EW3-6's instrument, `PLUS_LAB_SEASON_COMPLETE_ASOF`),
   which the conventions module logs to stderr once and writes into the artifact's
   `harness.season_complete_override` block. The Nov 15 default never moves. A read taken
   under it is an OWNER-WAIVED EARLY READ, never the registered date's read.
3. **No grandfather clause.** R1 rule 3 spent it: a re-gated row holds validated only by
   clearing BOTH conventions after Holm.
4. **Forward-chained and out of sample.** One pair set per comparison; coverage reported
   separately and never used to explain a gap.
5. **No floor from a stored constant.** Every MDE95 is derived in run as 1.645 times the
   bootstrap sd of the gap, published with its sign.
6. **A NULL OR A LOSS IS A COMPLETE RESULT.** If a shipped construction fails, the verdict
   moves to match and no third convention is invented afterwards.
7. **No re-tuning inside a re-gate.** The 0.7/0.3 blend weights, `HEM_SPREAD_GAIN` 2.28,
   `POOL_MIN_PA`, the Savant PA floors (200 eval, 100 served), the reliability constants of
   `hem_plus.py` and the season list are FIXED at their shipped values.
8. **Seeds and replicates, declared now:** `SEED_R3 = 20261015`, `BOOT = 2000` for every
   new draw. The frozen-subset reproduction (section 5) re-draws under `SEED_R1 = 20260918`
   because reproducing a published number requires its own draw.
9. **The run happens once.** Before it, the whole reporting path is dry-run on fixtures
   carrying None values (`--dry-run-fixtures`); stdout and stderr are teed to the task's
   output directory before anything else runs; on any exception after scoring began the
   lane STOPS without rerunning and writes OWNER_QUESTION.md.

---

## 2. Pair set and floors, frozen

The X-H3 rule, unchanged, applied to one more block:

- Rows: one per (player, Y) with Savant PA >= 200 in Y AND in Y+1, predictor seasons
  `2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025` (ex-2020), outcome season Y+1
  complete under rule 2 above. Only the 2025 block is new; its outcome season 2026 is
  admitted by the override and by nothing else.
- Predictors: Savant `woba` and `est_woba` (raw, unrounded), the HEM+ core
  `hem_plus_raw` re-scored per predictor season (section 3), and the served integers.
- A2 and A3 additionally require a HEM core for that (player, Y); the drop count is
  published (it was 0 of 1,871 in 2026 09).
- **The same pair set carries every arm and every baseline inside a comparison.** A1 reads
  the full set; A2 and A3 read the HEM-core subset; A1s and A3s read the HEM-core subset.

**Prior expectation for n, not a count:** the 2016 to 2024 blocks carry 261 to 278 rows each
(1,871 in all); the 2025 block is expected to carry 250 to 290 rows, so the extended set is
expected near 2,120 to 2,160. The run publishes its own n per predictor season. A 2025 block
under **200 rows** means the 2026 capture is not a complete season after all: the run is
REFUSED (section 10), coverage is published, nothing moves.

**Approximations disclosed in advance, inherited from R1-2:** the served normalizers (the
Savant PA >= 100 pool for xHEM+ and fwdHEM+, the StatsAPI hitting pool for HEM+) are
rebuilt on COMPLETE season captures, which are larger and wider than the mid-season pools
the nightly pipeline normalizes over. Biased in one direction; written here so it cannot be
produced afterwards to explain away a loss. The predictor-season statlines and the 2016 to
2025 Savant files are cached, immutable captures (unchanged since 2026-07-05 or earlier);
the 2026 Savant file is the current-season file with a one-day refresh rule, so the lab
records the sha256, row count and max PA of every Savant file it reads.

---

## 3. Estimands

Each arm is a paired difference of Spearman rank correlations with next-year actual wOBA on
one pair set.

- **A1 (`xhem_plus`), unchanged from R1-1:**
  `delta_A1 = rho(xHEM+_served(Y), wOBA(Y+1)) - rho(wOBA(Y), wOBA(Y+1))`.
- **A2 (`fwdhem_plus`), unchanged from R1-1:**
  `delta_A2 = rho(fwdHEM+_served(Y), wOBA(Y+1)) - rho(xwOBA(Y), wOBA(Y+1))`.
- **A3 (`hem_plus`), NEW:**
  `delta_A3 = rho(HEM+_served(Y), wOBA(Y+1)) - rho(xwOBA(Y), wOBA(Y+1))`,
  where **HEM+_served is the column exactly as `/mlbstats/` serves it**: the season's
  StatsAPI hitting statlines (`hitter_export.load_season_hitting` -> `build_hitters`),
  scored by `hem_plus.score_pool`'s path: every bat with a wOBA denominator above zero
  enters, the pool means and the anchor (`Pool.mean_woba`, the denominator-weighted mean of
  the shrunk wOBA over bats at `POOL_MIN_PA`) are built by `hem_plus.build_pool`, each
  component rate is empirical-Bayes shrunk by its own constant, recombined with the fixed
  linear weights, and `hem_plus_raw = 100 + 2.28 * (100 * shrunk wOBA / anchor - 100)`;
  the served value is `int(round(hem_plus_raw))`. Re-scored per predictor season on that
  season's complete statlines, then read on the pair-set rows. This is byte-for-byte the
  path `tools/xhem_plus_lab.load_hem_core` already walks, and the served integer is what
  the 2026-09-18 A1s sensitivity already rounded; nothing about the construction is new,
  only its standing.
  Baseline: raw Savant `est_woba(Y)` on the same rows, the same baseline A2 carries.

**What A3 is not.** It is not a test of the row's existing claim (HEM+ beats AVG, ties raw
wOBA; that gate stands as history in the notes). It is the claim R1-10 said must be tested
in its own registration: that the served HEM+ column, offered on the board as the hitter
SKILL read, forecasts next-year offense at least as well as the freely available Savant
xwOBA it sits beside. The decision rule in section 6 says what each answer does to the row.

**Labelled sensitivities, zero verdict weight:**

- **A1s** (inherited): served xHEM+ integer against served HEM+ integer, HEM-core subset.
- **A3s** (new): served HEM+ integer against raw actual wOBA(Y), HEM-core subset: the
  parent comparison the `hem_plus` gate names, re-read on the Savant frame so the row's
  "ties its parent" sentence can be kept or dropped on this frame's evidence.

---

## 4. Conventions

v1 and v2 exactly as `plus_lab_harness` defines them, both published for every cell, at
`BOOT = 2000` and `SEED_R3 = 20261015`. v2 z-scores the target within the outcome season
and resamples players, stratified by first predictor season. Each gap carries an in-run
MDE95 published with its sign. The bootstrap keeps its draws so Holm reads the gap
distribution's sd and the artifact asserts the cell summaries equal the conventions
module's own `iid_boot_gaps` / `cluster_boot_gaps` on one declared cell per arm.

---

## 5. The ladder, and the frozen-subset reproduction

**A1 and A2** keep R1-5's five rungs (D0 eval construction, D1 served pool, D2 served
recipe, D3 unrounded, D4 served integer); **only D4 carries the verdict**, and the rungs
are published so a move between 2026 09 and now can be located.

**A3** has two rungs, because the eval object of `hem_plus_lab` and the served object share
one normalizer: **D3** = `hem_plus_raw` unrounded; **D4** = `int(round(hem_plus_raw))`,
THE VERDICT. The tie count at D4 is published.

**Frozen-subset reproduction (a stop rule, zero verdict weight).** On the rows whose
predictor season is 2024 or earlier (the 2026-09-18 set, in the same construction and row
order), the lab recomputes A1 and A2 at D4 under `SEED_R1 = 20260918` and compares
`rho_primary`, `rho_baseline` and the v1 and v2 gap CIs to `data/xhem_served_regate_eval.json`
to four decimals, and compares n to 1,871. The inputs are unchanged captures, so exact
agreement is expected. **If it does not reproduce, the run STOPS and the reproduction
failure is the finding**; nothing downstream is reported as a verdict.

---

## 6. Decision rule, with the registry consequence fixed in advance

Per arm, at D4, after Holm (section 7), **R1-6's table verbatim:**

| outcome at D4 | registry consequence |
|---|---|
| gap lo95 > 0 under BOTH v1 and v2 | **validated** |
| gap lo95 > 0 under v1 only | **provisional** (the grandfather is spent; the note records both reads) |
| gap lo95 > 0 under v2 only | **provisional** (an undeclared convention cannot promote a row) |
| the gap CI straddles 0 under both | **provisional**, claim text "not separable from its baseline on the served construction at this n" |
| gap hi95 < 0 under either convention | **the claim is REFUTED: deprecated**, with a loss-ledger note; the column continues to ship until the display lane acts, recorded as a display debt in section 9 |

Applied to each row, because the rows start from different verdicts:

- **`xhem_plus` (validated).** The table as written: validated stays validated; anything
  else demotes; hi95 < 0 refutes.
- **`fwdhem_plus` (provisional since 2026-09-18).** This re-baseline is the registered
  re-read R1-12 named, so the first row of the table PROMOTES it back to validated; the
  three middle rows leave it provisional (the note records that the extended n did not
  separate it either); hi95 < 0 refutes.
- **`hem_plus` (validated against AVG and raw wOBA).** The table as written, on A3:
  lo95 > 0 under both: validated, and the row's `baseline` line adds Savant xwOBA as a
  beaten baseline. v1 only, v2 only, or a straddle under both: **provisional**, with the
  claim text "not separable from Savant xwOBA on the served construction at this n"; the
  AVG win stays in the notes as the row's history. hi95 < 0 under either convention:
  **deprecated**, the loss-ledger note saying that the served HEM+ column is forecast
  better by the Savant xwOBA beside it; the column continues to ship, and whether HEM+
  stays the primary hitter skill column beside xHEM+ is the display lane's question in
  section 9, not a softened verdict. The row's `predicts` line keeps the construction
  (a sample-shrunk wOBA); the registry grades the claim, not the pixel.

**Standing consequence, whatever the outcome, inherited from R1-6:** the headline number on
a served column is the served construction's number. Therefore, in the result commit:

- the three rows take `data/hem_xwoba_regate_eval.json` as `eval_artifact`, and each card
  derives from it (`xhem_plus`: A1 D4 v1 vs actual wOBA; `fwdhem_plus`: A2 D4 v1 vs xwOBA
  alone; `hem_plus`: A3 D4 v1 vs Savant xwOBA and A3s D4 v1 vs raw wOBA, the parent its
  gate names, resolvable read off the gap's lo95), with n from the artifact;
- the 2026-09-18 artifact `data/xhem_served_regate_eval.json` and the original
  `data/hem_plus_eval.json` are retained unedited and cited by path in the rows' notes as
  the prior reads; the `hem_plus` AVG and OPS gaps survive in the notes as labelled
  history;
- `summary` and `notes` are rewritten from the artifact by `tools/register_hem_xwoba_regate.py`,
  which types no number and is idempotent (a marker in the notes stops a second call);
- the three pins in `test_hem_riv_regate_2026_09_18.py` that name the 2026-09-18 artifact
  as the rows' `eval_artifact`, the rows' verdicts and the card headline source are
  amended in the same commit to read the re-baseline artifact, keeping every pin on the
  2026-09-18 artifact's own content; `MODEL_REGISTRY.md` is regenerated.

No served column, page, glossary entry or JSON payload other than the registry moves.

---

## 7. Multiplicity family

The family is **the three primary arms A1, A2 and A3**, corrected by Holm through
`tools/efv_power_lab.holm_family` with **k = 3**, applied SEPARATELY within each
convention (two reads of one decision, not two chances at it). One-sided p per cell comes
from the bootstrap gap distribution. The rungs D0 to D3, the frozen-subset reproduction,
A1s, A3s and every coverage figure sit OUTSIDE the family by declaration and carry zero
verdict weight. Total primary tests in this document: three. k moves from R1-7's two to
three because A3 joins the family; it is declared here, before the run, and the artifact
prints the family it corrected.

---

## 8. Pre-registered expectations

1. **A1 survives.** Prior v1 lo95 +0.0241 and v2 +0.0317 on 1,871 rows; another block of
   the same shape widens nothing. Wrong if A1 loses its lower bound at D4.
2. **A2 stays provisional.** Prior v1 lo95 -0.0012 at n 1,871; about 270 more pairs
   narrows the interval by roughly seven percent, so a v1 pass is possible and v2 (prior
   lo95 -0.0076) is expected to straddle. The expected outcome is the "v1 only" or the
   "straddles under both" row, either of which keeps provisional. Wrong if A2 clears both
   conventions after Holm (promotion) or if hi95 falls below zero (refutation).
3. **A3 is REFUTED.** The eval-normalized prior is a loss at lo95 -0.0601 and -0.0705; the
   served integer on the 2016 to 2024 rows reads 0.4148 against an xwOBA baseline near
   0.4543, and rounding is expected to cost HEM+ little. The expected row of the table is
   hi95 < 0 under both conventions: `hem_plus` deprecated. Wrong if A3's hi95 clears zero
   under either convention.
4. **A3s is a tie or a small win for HEM+**, the parent comparison the row's own gate
   found (lo95 -0.0096 on the 2012 to 2024 StatsAPI frame). Wrong if served HEM+ loses to
   raw wOBA on this frame at hi95 < 0.
5. **The 2025 block looks like the others.** Its n sits in 250 to 290 and its per-season
   served pool at PA >= 100 near 435 to 470. Wrong if either is outside, which is reported
   as a capture question, not absorbed.

---

## 9. Display consequences recorded, not decided

This lane owns the lab, the artifact, `data/model_registry.json`, `MODEL_REGISTRY.md` and
this document. It owns no served page, so every display consequence is recorded here and
left to the lane that owns it:

1. **If `hem_plus` is deprecated:** the HEM+ column on `/mlbstats/` Hitter Leaderboards,
   the "HEM+: skill" note under the board, the Lineup Charts scatter's "HEM+ (skill)" axis
   label, the Team Offense+ roll-up and the glossary's HEM+ entry (`data/glossary.json`)
   keep shipping with copy that calls it the skill read. Whether HEM+ stays the primary
   hitter skill column beside xHEM+, is relabelled, or moves behind xHEM+ is a display and
   copy question (R1-10, the old section 9 item 3). The eWAR v3 skill look (SWAR-Q3 (c))
   reads this result; it is not this lane's call what the batting part does with it.
2. **If `fwdhem_plus` moves (either way):** the column title at `assets/mlbstats.js`
   ("Provisional: as served, not separable from xwOBA alone ... (2026-09-18 re-gate)"),
   the glossary's xHEM+ Blend entry and the glossary receipt reader
   (`assets/glossary.js`, which reads `/data/xhem_served_regate_eval.json` A2 D4) quote
   the 2026-09-18 read. They stay true as history and stale as the latest read; the lane
   that owns them decides whether to point them at the re-baseline artifact.
3. **If `xhem_plus` holds:** the glossary's xHEM+ entry quotes 1,871 pairs and 0.46
   against 0.41; the re-baseline's n and digits may differ. Same owner, same choice.
4. The glossary receipt reader for `hem_plus` reads `/data/hem_plus_eval.json` (the AVG
   and raw-wOBA legs). It stays correct about that gate; it does not show A3. Display
   lane.

Nothing in this document edits a served page.

---

## 10. Stop and refusal rules

- The frozen-subset reproduction (section 5) fails: STOP, the reproduction failure is the
  finding, no verdict is reported.
- The 2025 block carries fewer than 200 pairs: REFUSED as an incomplete capture; coverage
  published under `refused`, no row moves, and the lane ends with
  `BLOCKER: date <the date a complete 2026 capture exists>`.
- Any exception after scoring began: STOP without rerunning; OWNER_QUESTION.md.
- Three nulls is a complete result.

---

## 11. Hard dates and order

- This document is frozen and committed **2026-10-15, ALONE**, before any number is
  computed; the lab and the mover are committed after it and before the run.
- The battery runs **2026-10-15, ONCE**, with `--season-complete-asof 2026:2026-10-01`, as an
  OWNER-WAIVED EARLY READ of the date R1-12 registered (2026-11-16 or later), under
  EW3-5. The registered date is not reached; the owner waived it; both facts are printed in
  the artifact (`owner_waived_early_read`), in the rows and in section 12.
- The artifact, the registry rows, the amended pins, `MODEL_REGISTRY.md` and this
  document's section 12 move in **ONE commit**. A verdict that lands without its artifact is
  a defect.
- The pair set is not extended again before **2027-11-16**, when the 2026 to 2027 block
  completes under the default rule (or earlier only under an owner-logged override of the
  same instrument). The next re-baseline is its own document, written before its own
  numbers.

---

## 12. Results

(Empty at registration. Filled by the one run, in the result commit, with: the run date
and the waiver; n per predictor season and the drops; the frozen-subset reproduction
receipt; A1, A2 and A3 at D4 under both conventions with their in-run MDE95; the Holm
k = 3 table per convention; A1s and A3s; the verdict and the registry consequence applied
per row; the display debts opened; and which of section 8's expectations were wrong.)

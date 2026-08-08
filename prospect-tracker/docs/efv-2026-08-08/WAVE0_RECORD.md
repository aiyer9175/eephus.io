# Wave 0 execution record, 2026-08-08

Plan: `docs/master-plan-2026-08-08-efv-conviction.md`. HEAD at start `82a13e37`.

**Status of everything below: WAVE 0 PREMISE MEASUREMENT, not a gated result.**
None of it carries the four mandatory controls or the three adversarial verifiers the
plan requires for a shippable claim. Numbers here exist to decide what wave 1 builds,
and any of them may be revised by the lane that owns it.

---

## 1. Suite baseline (P0.1, partial)

Chunked runner, 264 test files, 33 chunks of 8, wall 334s.
**Return codes: 30 chunks rc=0, 3 chunks rc=1. No chunk crashed.**
(Read the return codes, not the parsed totals. The runner's summary parser was keying on
a leading `=` that `pytest -q --no-header` does not emit; fixed, but the return codes were
correct throughout.)

The three reds, all pre-existing at HEAD, none caused by this program:

| test | classification |
|---|---|
| `test_calibration_vintage::test_the_same_player_is_worth_the_same_on_every_surface` | **EXPECTED.** One of the two reds the 2026-08-07b program documented as unable to clear from the trade-board P0 fix, because it compares the two artifacts AS THEY SIT ON DISK. Clears only after a real regen. |
| `test_rest_of_season_control::test_expiring_contracts_are_no_longer_unpriced_when_a_salary_exists` | **EXPECTED**, same cause, same remedy. |
| `test_atomic_artifact_write::test_a_concurrent_reader_never_sees_a_partial_document` | **REAL, reproduces in isolation** (1 failed, 8 passed, 33.7s alone), and NOT a degraded-run artifact. See below. |

**The atomic-write red, diagnosed and deliberately NOT fixed.** The product code is
correct: `storage.py:7948` retries the replace for 30s and then raises loudly rather than
writing in place, so the previous artifact is never corrupted. The test's reader thread
(`test_atomic_artifact_write.py:86-98`) calls `read_bytes()` in a tight loop with no
sleep; on Windows an open handle without share-delete blocks `os.replace`, so on a fast
machine the reader starves the writer for the entire window (125 attempts over 30s).
This is environment-dependent and outside this program's scope. **It is not fixed here
because the only cheap "fix" is to slow the test's reader, which would weaken a
regression test written for a real corruption incident.** Flagged for the owner.

---

## 2. Premise battery (P0.2), and four refutations that change the plan

CONFIRMED, unchanged: `_reprice_surplus_on_display` still keys on the retired quantile
(`efv_score.py:1131`, `gq` at :1160) and overwrites `surplus_mm`, both band fields and the
whole `dist` fan; `efv_board_scale.ENABLED_DEFAULT = False` (:184);
`storage.BOARD_GRADE_FIELD = "xfv_grade"` (:4866) with the client mirror in sync
(`prospx/index.html:31387`); `consensus.MIN_OFFSET_EXACT_FRAC = 0.90` (:150) and the
enforcement gate at :541; the three consensus flags at `consensus.py:153-155`;
`SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = True` (`efv_score.py:119`);
`_BLEND_LAMBDA_RESELECT = {"hit": 0.70, "pit": 0.57}` (`efv_model.py:586`) and
`_WAG_LAMBDA_IS_ASOF = False` (:601); the D5 defects at `source_backtest.py:530`, `:783`
and the bare `>=` at `:947`.

### REFUTATION 1: two of the three hygiene items in P0.3 are NO-OPS in code

`honest_note` is **already derived**, not hardcoded: `efv_model._honest_note` at
`efv_model.py:1690-1743`, assigned at `:2652-2654`, built from `verdict_vs_consensus`
(`:1540-1555`). `block_rho_eval()` exists at `:1619-1687` and is **already emitted** at
`:2647-2651`. Both landed 2026-08-07 in `c7593e00`; the served artifacts were last
written 2026-08-06 in `4d1f96dc`.

**So the stale "eFV beats consensus on both cuts" prose and the missing block-rho are a
STALE ARTIFACT, not a source defect. The fix is the regen, not an edit.** Budgeting a
code lane for these would have produced a no-op diff. This raises the priority of the
regen and shrinks P0.3.

Related: `block_rho` is **ABSENT** from both eval artifacts, not `null`. Any test or lane
written against `block_rho is None` passes vacuously against a missing key.

### REFUTATION 2: `data/timeseries.json` has no `meta` object

The provenance fields are TOP-LEVEL keys of the `boot` dict at `storage.py:15906`
(`generated_at` :15907, `calibration` :15913, `run` :15914). The consensus-flag stamp
belongs immediately after :15914, not inside a `meta` block that does not exist.

### REFUTATION 3: the undated-artifact item is a program, not a hygiene batch line

Machine-classified all 180 `data/*_eval.json`: **129 carry a bare `YYYY-MM-DD` with no
`produced_by`, 27 carry no `generated_at` at all, 24 carry a full ISO timestamp, and only
4 are fully compliant.** That is 156 of 180 failing the bar. Rescope: fix the artifacts
this program touches, and register the rest rather than pretending a batch closes it.

### REFUTATION 4: `_reprice_surplus_on_display` has THREE call sites, not two

`run()` at `efv_score.py:1584-1585`, `run_live()` at `:2219`, and **`run_backgrade()` at
`:2600`**, which the plan omitted. R1's re-basing must touch all three or backgrade rows
silently keep the retired quantile.

### Prior-art warning that makes M5 adversarial, not open

`efv_reliability._realized_bucket` (`:126-149`) does divide by a constant
`TARGET_SEASONS = 6.0` (:60) while rows carry `observed_seasons` 2-5, so the D4 carrier is
real. **But its docstring at `:130-147` is an explicit pre-registered do-not-reopen that
records the season-share-corrected relabel as already run, moving pooled bust ECE only
0.07908 to 0.07660 (3.1%).** M5 must engage that measurement rather than re-deriving it.

### Small true defects found in passing (candidates for the shrunk P0.3)

- `tools/efv_oldcohort_id_resolve.py:76` writes `data/mlbam_id_overrides.json` while every
  reader reads `data/sources/`; `:10` uses a cwd-relative `Path("data")`; `:37` defaults
  its cache to a POSIX `/tmp/` path on a Windows box.
- `efv_board_scale.py:117` docstring claims `ENABLED_DEFAULT is True`; it is `False` at
  `:184`, in the same file.
- `docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_GATE.md:187` claims
  `SERVE_PROVISIONAL_FOR_CONSTANT_COHORT` defaults False; it is True.
- `_odds_grade` is a local in all three scorers (`efv_score.py:1480`, `:2048`, `:2542`)
  and is never stamped on the row, so exporting it is a two-part edit, not a one-line
  addition to `efv_export._entry`.

---

## 3. Per-source noise is identified with no labels (section 9.3 item 1)

Producer `scratchpad/sigma_s_probe.py` + `sigma_s_peryear.py`, read-only against
`prospects.db`. Pairing rule: each publisher's EARLIEST board per calendar year, so the
three are compared at a comparable vintage.

**Coverage over 18,327 player-years: k=1 on 10,659 (58.2%), k=2 on 6,516 (35.6%), k=3 on
1,152 (6.3%).** The single-source regime is therefore most of the corpus, which is the
population `SINGLE_SOURCE_K` shapes.

**Independent reproduction of the research constants.** Measured FanGraphs-vs-Pipeline
paired sd **3.982** against 3.842 derived from the published SE, and a pooled offset of
**-4.005** against the published +4.367 (opposite sign convention, different pairing
basis). Close enough to treat the derivation as reproduced.

**THE FIRST HEADLINE WAS WRONG AND ITS OWN CONTROL CAUGHT IT.** Pooling 2023-2026 gave
Baseball America sigma **5.89** against FanGraphs 2.69 and Pipeline 2.12, a ratio of
2.78. That is an artifact of pooling across BA's 2026 basis change and the offset drift.
Re-measured WITHIN year:

| year | FanGraphs | MLB Pipeline | Baseball America | max/min |
|---|---|---|---|---|
| 2023 | 2.585 | 2.440 | 3.236 | 1.33 |
| 2024 | 2.565 | 2.660 | 3.113 | 1.21 |
| 2025 | 2.880 | 2.246 | 3.540 | 1.58 |
| 2026 | 2.569 | 2.302 | **2.160** | 1.19 |

(Sheppard-corrected, subtracting h^2/12 = 2.083 for the 5-point lattice.)

**Consequence for M4: the precision-weighting prize is REAL but MARGINAL and
year-dependent, not the 2.78x the pooled number advertised.** The ratio straddles the
lane's own 1.25 ship bar, clearing it in 2023 and 2025 and failing it in 2024 and 2026.
In 2026 Baseball America is the QUIETEST of the three, which is consistent with the
2026-08-07b finding that 2026 has the tightest residual spread of the four BA years.
M4 must gate per-year or on a properly pooled within-year estimate, never on the
cross-year pool.

Residual confound not yet removed: median publication gap is 1-8 days for BA vs
FanGraphs but **24 days** for BA vs Pipeline, so BA's pair variances still carry some
true-talent drift.

## 4. The single-global-offset premise is REFUTED

FanGraphs-to-Pipeline offset by year, n 594-852 per year, SE 0.131-0.160:

```
2017 +4.175   2018 +4.747   2019 +4.222   2020 +4.487   2021 +4.165
2022 +4.181   2023 +3.903   2024 +3.790   2025 +3.312   2026 +3.269
```

The 2018-to-2026 decline is **1.478 FV at a pooled SE of about 0.19, roughly 7.7
sigma**, and it is close to monotone after 2022. A single global offset is therefore not
admissible, and any thin-cell normalization that pools across years applies roughly +4.0
where the truth ranges 3.27 to 4.75. This is direct evidence for M7a's C-4 options and
against the status quo. It also means the drift test the research costed at two hours is
already answered in the affirmative.

## 5. The covariate shift and the effective sample size (section 9.3 item 5)

Producer `scratchpad/ess_probe.py`.

Labeled pool, rows that HAVE a MiLB block (2,161 of 3,957): **AA 34.1%, AAA 22.7%,
A+ 17.9%, A 15.1%, CPX 7.7%, DSL 2.5%.** Served provisional pool (5,993): **DSL 34.7%,
A 17.3%, A+ 14.0%, CPX 12.9%, AA 10.9%, AAA 10.2%.** Both research figures (34.1% AA,
2.6% DSL) reproduce exactly on that subset.

**Kish ESS = 404.9 of 2,161, i.e. 18.7%** (research predicted 390 of 2,000, 19.5%).
Stratum weights run from 0.584 (AA) to **24.97 (DSL)**, and **the DSL third of the served
board rests on 55 labeled rows.**

**NEW, and it bounds every reweighted claim: 1,796 of 3,957 labeled rows (45.4%) carry no
MiLB block at all**, which is the identity-resolution ceiling reported in the 2026-07-24
data-sourcing program. Those rows cannot enter a level-stratified reweighting, so the
served-population estimate rests on 2,161 rows before weighting and ~405 after.

This confirms the plan's ESS gate as written: a pooled served-population accuracy number
is not supportable at ESS/n = 0.187, and M6 must publish strata.

---

## 6. The regen (P0.1), and the margin movement it produced

Producer `scratchpad/regen_efv.py`: `efv_dataset.run(persist=True, side=...)` then
`efv_model.run(persist=True, side=...)`, both sides. Timings 22.5s / 3.0s / 58.4s / 63s.

**Deliberately NARROWER than `run_monthly.rebuild_only()`**, and the deviation is recorded
here rather than hidden: the wave-1 measurement prerequisite is a current TRAINING MATRIX
and current EVAL artifacts. The served artifacts (trade_values, mlb_projections, baked
pages) matter for wave-2 ships, not for wave-1 measurement, and regenerating them would
dirty a large tracked surface this session has no intention of committing. Upstream
`data/timeseries.json` was already fresh (2026-08-08T05:05:44Z), so the consensus the
matrices read is current. **Consequence to carry: the two expected suite reds in section 1
are NOT cleared by this regen**, because they compare `trade_values.json` against
`mlb_projections.json`, neither of which was rebuilt. They clear on a full rebuild.

Files changed, exactly the five the regen owns, with the nine pre-existing owner-churn
files untouched: `xfv_eval.json`, `xfv_eval_pitcher.json`, `xfv_dataset_report.json`,
`xfv_pitcher_dataset_report.json`, `xfv_side_fairness_eval.json`. Matrices are gitignored.
Targeted tests after the regen: **90 passed** across `test_efv_model`, `test_efv_export`,
`test_efv_score`, `test_model_registry`, `test_methodology_freshness`, `test_efv_levers`,
`test_efv_sign_declarations`.

**Refutation 1 is confirmed by execution.** The regenerated `honest_note` now reads "eFV
does not beat consensus FV on out-of-sample rank on every cut (debuted_km +0.0112,
full_pool_km -0.0190)". The stale "beats consensus on both cuts" prose is gone with no code
edit, and `block_rho` is now PRESENT in both artifacts (n 1,644, delta +0.0085 against
0.0325, not resolvable).

### THE HEADLINE: every published margin moved, and the one resolvable cell stopped resolving

| cut | pre-regen delta | POST-REGEN delta | E_cond floor | pre x | **post x** |
|---|---|---|---|---|---|
| hit `full_pool_km` | -0.02143 | **-0.01900** | 0.0204 | **1.049x RESOLVABLE LOSS** | **0.93x, NOT resolvable** |
| hit `debuted_km` | +0.00741 | +0.01120 | 0.0213 | 0.35x | 0.53x |
| pit `full_pool_km` | +0.01571 | +0.01390 | 0.0218 | 0.72x | 0.64x |
| pit `debuted_km` | +0.00669 | +0.00610 | 0.0301 | 0.22x | 0.20x |
| block-rho (joint) | +0.01204 | **+0.00850** | 0.0325 (E_refit) | 0.37x | 0.26x |
| pit `debuted_resolved` | -0.0176 | -0.01760 | not derived | - | loss, unfloored |

**`EFV_GATE_STANDARD.md` section 7.5 is now STALE.** It publishes hitter `full_pool_km` as
the one cell E_cond resolves ("1.049x its floor, a RESOLVABLE LOSS", bootstrap
p(delta>0) = 0.0415). On a matrix rebuilt against the current consensus that margin is
**-0.0190, i.e. 0.93x of the same floor, and it no longer resolves.**

**State the caveat with the finding: this is only half the calculation.** The floors are
themselves functions of the data, so a fresh delta must be read against a FRESHLY DERIVED
floor, not against the registered one. M1 must re-derive both estimators on the rebuilt
basis before anything is published. What is established here is narrower and still
important: **the direction and size of every conviction margin depend on a regen that was
two days stale, and one of them crosses a verdict boundary.** That is precisely why P0.1
is a prerequisite rather than a formality, and it retroactively justifies the plan's rule
that no margin is adjudicated on pre-regen artifacts.

Note also the hitter and pitcher notes now disagree in kind: pitchers rank ahead on every
cut (both null), hitters do not (`full_pool_km` negative). Any single-sentence site claim
covering "eFV" has to survive both.

## 7. What wave 1 should change as a result

1. P0.3 shrinks: `honest_note` and `block_rho` need a REGEN, not edits. The remaining
   real items are the id-resolver path bug, the two stale comments, the timeseries
   provenance stamp (top-level, not `meta`), the curve_area floor attachment, and the
   two-part `_odds_grade` export.
2. M4 re-gates per year. Its expected value is lower than section 9.3 assumed, and the
   lane must say so up front rather than discovering it at the gate.
3. M7a gains a measured input: the offset drift is real at ~7.7 sigma, so "one global
   offset" is off the table before the C-4 options are even scored.
4. R1 must touch three call sites.
5. M5 must engage the pre-registered do-not-reopen at `efv_reliability.py:130-147`.
6. The regen is now the critical path for M1/M3, because the eval artifacts that every
   conviction number is read from are a day stale and already contradict their own code.
   **DONE, see section 6.** M1 inherits a new obligation from it: re-derive BOTH estimators
   on the rebuilt basis and supersede `EFV_GATE_STANDARD.md` section 7.5, which now
   publishes a resolvable loss that no longer resolves.

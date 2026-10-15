# Bat-tracking blend: the SERVED construction and its one re-read (pre-registered 2026-10-14)

Owner answer NOV15-BT-ARMB = (a), 2026-10-14: register a served construction for the
bat-tracking blend arm (arm B of `tools/bat_tracking_lab.py`), build it behind a flag that
defaults OFF, re-read it ONCE on the served construction, and flip it only if that re-read
passes the rule written here. This document is that registration. It is committed ALONE,
before the builder, before the re-read lab and before any served-construction number
exists.

Producers: `tools/bat_tracking_lab.py` (arm B, the eval construction),
`tools/xhem_served_regate_lab.py` (the served fwdHEM+ reconstruction and the ladder this
document copies), `hitter_export._join_fwdhem_plus` (the sibling served column).
Registry row under test: `bat_tracking_hitters` (provisional). Re-read lab and artifact,
named now so they cannot drift: `tools/bat_tracking_served_lab.py` and
`data/bat_tracking_served_eval.json`.

---

## 0. HONESTY CLAUSE, first

| object | status on 2026-10-14 | consequence |
|---|---|---|
| arm B on the EVAL construction (rho 0.4598 vs fwdHEM+ 0.4465, n 528, v1 gap mean +0.0133 lo95 +0.0015 hi95 +0.0256; v2 lo95 +0.0025) | **READ**, `data/bat_tracking_eval.json`, run once today as an owner-waived early read | D0 below is a REPRODUCTION CHECK, never a test |
| the served fwdHEM+ normalizer cost 38 percent of its v1 edge, localized at the leg normalizers (D0 0.4658 to D1 0.4600 on the 1,871-pair X-H3 set) | **READ**, `data/xhem_served_regate_eval.json` | the served-pool cost is a known risk for this candidate too; it is named here as the reason for the ladder, not as an expectation of a number |
| arm B against xwOBA alone on the eval construction (gap mean +0.0113, lo95 -0.0039) | **READ** | it is a DISCLOSURE leg below with zero verdict weight; it was never arm B's bar |
| any served-construction number for the bat-tracking blend, and the served fwdHEM+ on the 528-pair bat-tracking set | **NOT COMPUTED** | the primary estimand below is pre-registered in the ordinary sense |

The re-read is CONFIRMATORY on a pair set already scored once: the same 528 pairs, a
different construction. It cannot add n. Its only job is to say whether the edge the eval
construction measured survives the normalizer the board would actually use.

---

## 1. Standing rules inherited

1. **Harness v2** (`tools/plus_lab_harness.py`), both conventions for every cell: v1 raw
   pooled target with iid paired resample; v2 within-outcome-season z target with
   player-clustered, season-stratified resample.
2. **Both conventions bind** (docs/HEM_RIV_REGATE_GATE.md rule 3, which retired the v1
   grandfather for the +index family): a served column clears its bar under v1 AND v2 or it
   does not clear.
3. **No re-tuning.** The blend weights 0.595 / 0.255 / 0.15, the composite's three
   components (bat speed, squared-up rate, blast rate) and their equal weights, the
   competitive-swings floor of 100, the Savant PA floor of 100, the pair-set floor of 200 and
   the two folds are FIXED. A sweep over any of them is a new registration.
4. **MDE95 in run** (1.645 times the bootstrap sd of the gap), never a stored constant.
5. **The headline number on a served column is the served construction's number**
   (HEM_RIV_REGATE_GATE.md R1-6 standing consequence). The eval figure appears only as a
   labelled reproduction.
6. **A NULL is a complete result.** If the served construction fails, the column stays
   dark, and no third construction is tried afterwards.

---

## 2. The served construction S1, as code facts the builder must match

For a served season Y (`hitter_export._join_btblend_plus`, new):

1. **Inputs.** The Savant expected-statistics batter leaderboard (est_woba, pa); the
   unrounded HEM+ core `hem_plus_raw` of the scored board hitters (the same `_hem_raw` dict
   the xHEM+ Blend join reads); the Savant bat-tracking batter leaderboard for Y, the same
   endpoint and field map as `tools/bat_tracking_lab.py` (`BT_URL`, `BT_FIELD_MAP`).
2. **The BT composite's normalizer (the owner's first question).** Each component (bat speed
   `avg_sweetspot_speed_mph_qualified`, squared-up rate `squared_up_per_swing`, blast rate
   `squared_up_with_speed_per_swing`) is z-scored over the season's FULL bat-tracking
   leaderboard at `swings_qualified` (competitive swings) >= 100, with the population sd, and
   the composite is the mean of the three z. This is EXACTLY the eval's component normalizer
   (`bat_tracking_lab.zmap` over `load_bt`). The pool depends on the bat-tracking leaderboard
   alone, never on which hitters the board shows, so the composite carries no
   served-versus-eval difference at the component stage.
3. **The competitive-swings floor on the board (the owner's second question): 100**, the eval
   floor (`BT_MIN_SWINGS`). A board row is stamped only when it has Savant PA >= 100, a HEM
   core, AND a bat-tracking row at >= 100 competitive swings. Any missing leg leaves the field
   absent and the cell blank; nothing is imputed.
4. **The blend-leg normalizer.** The joined served pool J(Y) is every Savant batter at
   PA >= 100 with est_woba > 0 that also carries a HEM core and a bat-tracking row at the
   floor. Each of the three legs (est_woba, hem_plus_raw, composite) is z-scored over J(Y)
   with the sample sd (the `_mu_sd` convention of `_join_fwdhem_plus`); the blend is
   0.595 z(est_woba) + 0.255 z(hem_plus_raw) + 0.15 z(composite); the blend is
   re-standardized by its own sd over J(Y) and mapped affinely onto J(Y)'s HEM+ core location
   and spread; the served value is `int(round(...))`, on the HEM+ ruler beside xHEM+ and the
   xHEM+ Blend.
   Why J(Y) and not a PA >= 200 normalizer pool closer to the eval: the sibling column
   normalizes over its PA >= 100 served pool, a PA >= 200 pool is nearly empty for the first
   two months of a season, and choosing the pool that the fwdHEM+ ladder suggests would be a
   researcher choice informed by a read number. The PA >= 200 pool is computed as a labelled
   sensitivity (S2, section 7) with zero verdict weight.
5. **Fetch and cache.** The served path caches the bat-tracking leaderboard under
   `.cache/bat_tracking/served/`, closed seasons forever and the current season with the same
   live TTL as `mlb_player_export._savant`; a failed refresh falls back to the stale file, and
   no file means no column. The lab's frozen captures under `.cache/bat_tracking/` are never
   written by the served path.

## 3. The column and the flag (the owner's third question)

- **Recommended and built: a NEW column**, field `btblend_plus`, label "BT Blend", on the
  /mlbstats/ Hitter Leaderboards Skill view beside the xHEM+ Blend. Plan Part 8 class 2 (a new
  served number). The xHEM+ Blend column is untouched.
- The alternative, REPLACING the xHEM+ Blend column with this construction, moves an existing
  served number (class 3) and retires a provisional row's column; it is recorded as an owner
  question and is not built.
- **Flag:** `hitter_export.BTBLEND_SERVE`, a module constant, default **False**. Off, the join
  reads nothing, fetches nothing, and `data/hitter_leaderboards.json` is byte-identical to the
  flag-less exporter. A local preview (`EEPHUS_BTBLEND_PREVIEW=1`) computes the column and
  writes ONLY `.cache/bat_tracking/preview/btblend_preview_{Y}.json`; it never stamps a board
  row. The page column ships in the same flip commit; while the flag is off no page code reads
  the field.

## 4. Estimand of the one re-read

    delta = rho(BT_served(Y), wOBA(Y+1)) - rho(fwdHEM+_served(Y), wOBA(Y+1))

- **Pair set:** arm B's pair set exactly, unchanged: Savant PA >= 200 in Y AND Y+1, a HEM
  core in Y, a bat-tracking row at >= 100 competitive swings in Y; folds 2024 to 2025 and
  2025 to 2026, the 2026 outcome complete under the owner's logged season-complete override
  (EW3-6, `PLUS_LAB_SEASON_COMPLETE_ASOF 2026:2026-10-01`). Published n 528 (a PRIOR); the run
  publishes its own n and any deviation is a defect.
- **Target:** Savant wOBA in Y+1, as arm B scored it.
- **Candidate:** S1 at rung D4 (section 5), the integer column as it would be served,
  normalized over J(Y) built from the COMPLETE season Y pools.
- **Baseline:** the served xHEM+ Blend at D4, `_join_fwdhem_plus`'s recipe over ITS OWN served
  pool (Savant PA >= 100 with a HEM core), reconstructed by
  `xhem_served_regate_lab.served_fwdhem_pool` / `served_fwdhem_unrounded`, rounded. This is the
  column the new one would stand beside, and it is what arm B's bar named as the incumbent.
- **Normalizer pool versus evaluation pool:** normalizers are fitted on the full season pools;
  the statistic is read on the pair-set rows only.
- **Approximation disclosed in advance** (HEM_RIV_REGATE_GATE.md R1-2): the served normalizer
  is built at pipeline time from whatever rows exist then; the re-read builds it on complete
  season pools.

## 5. The ladder (candidate and baseline move together, rung by rung)

| rung | candidate | baseline | verdict weight |
|---|---|---|---|
| D0 | arm B eval construction (legs z within predictor season over the pair set) | fwdHEM+ eval construction | none: reproduction check, original seed 20260723 and the re-read seed |
| D1 | legs z over J(Y), plain 0.595/0.255/0.15 blend | legs z over the fwdHEM+ served pool, plain 0.7/0.3 blend | none |
| D2 | D1 plus the re-standardize and the affine HEM+ map | the same for fwdHEM+ | none |
| D3 | D2 unrounded (identical to D2 by construction; emitted so rounding is read off a stated rung) | same | none |
| D4 | **the served integers** | **the served integers** | **THE VERDICT** |

D0 must reproduce `data/bat_tracking_eval.json` arm B exactly under seed 20260723: n 528,
rho 0.4598 vs 0.4465, v1 gap lo95 +0.0015, v2 gap lo95 +0.0025. If it does not, the run
STOPS and the reproduction failure is the finding.

## 6. Decision rule, consequences fixed in advance

Seed 20261014, 2000 reps, one primary test (k = 1, Holm is the identity; declared so the
family cannot grow afterwards).

| outcome at D4 | consequence |
|---|---|
| gap lo95 > 0 under BOTH v1 and v2 | **PASS. The flag flips** in ONE commit carrying `BTBLEND_SERVE = True`, the regenerated `data/hitter_leaderboards.json`, the BT Blend column in `assets/mlbstats.js`, a glossary entry, and a NEW registry row `btblend_plus` (verdict **provisional**: two folds, small n, the lab's own honesty clause) whose headline is the D4 number |
| gap lo95 > 0 under one convention only | **FAIL. Stays dark.** Rule 2 requires both |
| the gap CI straddles 0 under both | **FAIL. Stays dark**, recorded as "not separable from the served xHEM+ Blend on the served construction at this n" |
| gap hi95 < 0 under either convention | **REFUTED on the served construction. Stays dark.** The bat-tracking row notes record that the eval-construction edge does not survive the served normalizer |

Whatever the outcome, `bat_tracking_hitters` records the re-read in its notes and keeps its
verdict for the EVAL construction (provisional): the lab result and the served result are
different objects, and both numbers are printed.

## 7. Disclosures, zero verdict weight

- the candidate at D4 against raw Savant xwOBA(Y) alone, on the same rows (the claim text of
  any flipped column must say whether it separates from xwOBA alone);
- the candidate at D4 against the served xHEM+ integer, on the same rows;
- per-fold rhos at D4;
- **S2**, the PA >= 200 normalizer-pool variant of S1 (J(Y) restricted to Savant PA >= 200
  for fitting the legs, applied to the same rows), D4 gap against the same baseline;
- coverage, never used to explain a gap: J(Y) size and the fwdHEM+ served pool size per
  season, the count of fwdHEM+-stamped rows that the bat-tracking floor leaves blank, and
  pair-set n per fold. The gate speaks only about the PA >= 200 subset while the board would
  stamp PA >= 100, and that sentence travels with the verdict.

## 8. Hard dates

- This document is committed 2026-10-14, alone, before any served-construction number.
- The re-read runs ONCE, 2026-10-14, as an OWNER-WAIVED EARLY READ (EW3-5; the 2026 outcome
  half rests on the EW3-6 season-complete override, which the artifact logs).
- No second read of this pair set. The next read needs the 2026 to 2027 fold (complete after
  2027-11-15) and its own document.
- The artifact, the registry note and the result section below move in the SAME commit.

## 9. Stop rule

- D0 does not reproduce: STOP, the reproduction failure is the finding.
- An exception after scoring began: STOP without rerunning, write the owner question.
- Nothing separates: a complete result; the column stays dark.

## 10. Results

**Read once, 2026-10-14, an OWNER-WAIVED EARLY READ** (EW3-5; the 2026 outcome half rests
on the EW3-6 season-complete override `PLUS_LAB_SEASON_COMPLETE_ASOF 2026:2026-10-01`, logged
in the artifact). Artifact `data/bat_tracking_served_eval.json` (generated 2026-10-14,
runtime 43.4 s); this section is transcribed from it and was not re-run.
Seed 20261014, 2000 reps, k = 1.

**Verdict: PASS.** The served construction clears the served xHEM+ Blend at D4 under BOTH conventions. The flag flips.

- Pair set: n 528 (published prior 528, no deviation); drops: partial outcome kept
  0, HEM missing 0, BT missing 0.
- Integrity: served composite minus eval composite max abs 2.2e-15;
  HEM core served minus eval max abs 0.0; D4 matches the production
  module (`bat_tracking_blend.served_values`): True.
- D0 reproduction (seed 20260723): n 528, rho 0.4598 vs 0.4465, v1 lo95
  +0.0015, v2 lo95 +0.0025; reproduces `data/bat_tracking_eval.json` arm B: True.

| rung | rho BT Blend (v1) | rho xHEM+ Blend (v1) | gap v1 | gap v2 | MDE95 v1 / v2 |
|---|---|---|---|---|---|
| D0 (seed 20260723) | 0.4598 | 0.4465 | mean +0.0133, lo95 +0.0015, hi95 +0.0256 | mean +0.0135, lo95 +0.0025, hi95 +0.0254 | 0.0101 / 0.0095 |
| D0 | 0.4598 | 0.4465 | mean +0.0134, lo95 +0.0017, hi95 +0.0253 | mean +0.0134, lo95 +0.0017, hi95 +0.0249 | 0.0098 / 0.0096 |
| D1 | 0.4601 | 0.4457 | mean +0.0145, lo95 +0.0031, hi95 +0.0258 | mean +0.0145, lo95 +0.0030, hi95 +0.0254 | 0.0095 / 0.0093 |
| D2 | 0.4598 | 0.4454 | mean +0.0146, lo95 +0.0029, hi95 +0.0264 | mean +0.0146, lo95 +0.0032, hi95 +0.0257 | 0.0097 / 0.0094 |
| D3 | 0.4598 | 0.4454 | mean +0.0146, lo95 +0.0029, hi95 +0.0264 | mean +0.0146, lo95 +0.0032, hi95 +0.0257 | 0.0097 / 0.0094 |
| D4 | 0.4595 | 0.4464 | mean +0.0132, lo95 +0.0019, hi95 +0.0242 | mean +0.0131, lo95 +0.0018, hi95 +0.0243 | 0.0095 / 0.0094 |

The headline is D4: rho 0.4595 against the served xHEM+ Blend 0.4464,
gap lo95 +0.0019 (v1) and +0.0018 (v2), both above zero. The served
normalizer cost the candidate almost nothing on this pair set (D0 v1 gap mean
+0.0134, D4 +0.0132).

Disclosures, zero verdict weight (section 7):

- D4 against raw Savant xwOBA(Y) alone: v1 mean +0.0121, lo95 -0.0044, hi95 +0.0277; v2 mean +0.0117, lo95 -0.0027, hi95 +0.0269.
  **The BT Blend does NOT separate from xwOBA alone**; any claim text on the column says so.
- D4 against the served xHEM+ integer: v1 mean +0.0115, lo95 -0.0048, hi95 +0.0269; v2 mean +0.0109, lo95 -0.0033, hi95 +0.0260.
- Per fold at D4: 2024 to 2025 n 265, rho 0.4611 vs 0.4523;
  2025 to 2026 n 263, rho 0.4547 vs 0.4401.
- S2 (PA >= 200 normalizer pool, n 365 in 2024 and 348 in 2025): v1 mean +0.0122, lo95 +0.0003, hi95 +0.0244;
  v2 mean +0.0125, lo95 +0.0005, hi95 +0.0247.
- Coverage: J(Y) 455 (2024) and 461 (2025); the xHEM+ Blend served pool
  455 and 461; xHEM+ Blend rows the bat-tracking floor leaves blank
  0 and 0; pair-set n 265 and 263.
  The gate speaks only about the PA >= 200 subset while the board stamps PA >= 100.

Consequence (section 6, fixed in advance): the flag flips in its own ONE commit with the
regenerated board, the page column, the glossary entry and the new registry row
`btblend_plus` (provisional). `bat_tracking_hitters` keeps its EVAL-construction verdict
(provisional) and carries this re-read in its notes. No second read of this pair set; the
next read needs the 2026 to 2027 fold (complete after 2027-11-15) and its own document.

# eFV eval basis ledger, 2026-08-07 (omnibus-3 lane A)

Everything the eFV eval published on the RETIRED basis, captured before the
regeneration that replaced it, plus every measurement lane A took. Written because
`data/source_backtest.json` is gitignored and rewritten nightly, and the pre-promotion
copy of it was already lost once. If you need to know which protocol produced a number
someone is quoting, this file is the answer.

Produced by: `tools/efv_mde_lab.py` (parity / mde / headtohead / sensitivity),
`tools/efv_scoreboard.py`. Ledger artifacts: `data/xfv_mde_floor.json`,
`data/xfv_headtohead_gap.json`.

---

## 0. The question the owner asked

> Why did Spearman fall .390 to .351, and AUC with it?

It is protocol arithmetic from the owner's own 2026-08-06 promotion, not a regression.
`efv_model.SCORED_YEARS` went from 4 folds (2020-2023) to 11 (2014-2024) at
`efv_model.py:81`, and the published headline became pair-weighted
(`prospect_path.py:366-396`, `_score` at `:417`). `oos_grades` trains each fold on all
rows with `decision_year < yr` (`efv_model.py:757-758`), so every pre-existing grade is
bit-identical; the pool simply grew from 2,200 to 3,210 rows by adding the thin
2014-2019 cohorts and the censored 2024 cohort, which are harder.

VERIFIED 2026-08-07 on fresh matrices, `tools/efv_mde_lab.py parity`:

| basis | hit cons | hit blend | pit cons | pit blend | n hit / pit |
|---|---|---|---|---|---|
| 4-fold 2020-2023, unweighted (retired) | 0.3521 | 0.3882 | 0.2673 | 0.3206 | 353 / 438 |
| 11-fold 2014-2024, unweighted | 0.3797 | 0.3910 | 0.2404 | 0.2512 | 755 / 890 |
| 11-fold 2014-2024, pair-weighted (SHIPPED) | 0.3919 | 0.3993 | 0.2495 | 0.2562 | 755 / 890 |

The retired numbers reproduce exactly, so nothing broke. Note the direction people
miss: the flagship hitter blend rho went UP under weighting (0.3910 to 0.3993). What
fell is the CONSENSUS-relative margin, and the pitcher side, whose 2014-2018 folds
train on almost nothing.

The .351 the owner is reading is a different statistic again: it is
`accuracy.pooled.xfv.spearman` in `data/source_backtest.json`, the common-set
head-to-head, not the model's own forward-chained eval. See section 6.

---

## 1. CAPTURE: the legacy-basis values, verbatim

### 1a. `data/source_backtest.json` as of 2026-08-07T03:35:55Z (pre-regeneration)

`accuracy.pooled`, each rater on the rows THAT rater graded:

| rater | n | spearman | auc |
|---|---|---|---|
| fangraphs | 4259 | 0.2502 | 0.7007 |
| mlb_pipeline | 4259 | 0.2823 | 0.7184 |
| prospx_consensus | 4259 | 0.2846 | 0.7301 |
| xfv | 3210 | 0.3511 | 0.7328 |

`accuracy.common_n` 4259. `xfv_vs_consensus`, protocol "forward-chained out-of-sample;
debuted cohort; first-6-season bWAR (KM-censored)":

| side | n | consensus | xfv | delta | mde95 (then) | resolvable |
|---|---|---|---|---|---|---|
| hitters | 755 | 0.3919 | 0.3993 | +0.0074 | 0.045 | false |
| pitchers | 890 | 0.2495 | 0.2562 | +0.0067 | 0.045 | false |

era_split (hitters): <=2018 n 129, 0.4897 vs 0.4915; 2019-2021 n 205, 0.3087 vs 0.3532;
2022-2023 n 220, 0.3981 vs 0.4300.
era_split (pitchers): <=2018 n 132, 0.3510 vs 0.3308; 2019-2021 n 286, 0.1755 vs 0.1815;
2022-2023 n 228, 0.3310 vs 0.4075.

`accuracy.xfv_vs_consensus_detail`: n 1263, n_disagreements 325,
xfv_right_share_on_disagreements 0.551. Per tier (consensus / xfv): 55 n 43
-0.0472 / 0.3142; 50 n 135 -0.0427 / -0.0179; 45 n 181 -0.1057 / 0.1740;
<45 n 882 0.0496 / 0.0973.

### 1b. `data/xfv_scoreboard_eval.json` as of 2026-07-30 (the frozen legacy basis)

This is the artifact `assets/diamond.js:32` was reading, which is why the Diamond hub
printed 0.384 while the glossary printed 0.351.

| cell | n | efv | consensus |
|---|---|---|---|
| hit pooled spearman | 353 | 0.3882 | 0.3522 |
| hit pooled auc_contributor | 353 | 0.7768 | 0.7556 |
| hit pooled auc_star | 353 | 0.8275 | 0.8087 |
| pit pooled spearman | 438 | 0.3060 | 0.2671 |
| pit pooled auc_contributor | 438 | 0.7187 | 0.7023 |
| pit pooled auc_star | 438 | 0.8552 | 0.8371 |
| head_to_head vs consensus, spearman | 2200 | 0.3840 | 0.2830 |
| head_to_head vs consensus, auc_contributor | 2200 | 0.7572 | 0.7316 |
| head_to_head vs fangraphs, spearman | 2200 | 0.3840 | 0.2483 |
| head_to_head vs mlb_pipeline, spearman | 2200 | 0.3840 | 0.2818 |
| top20 capture | 1632 | 0.6985 | 0.7039 |
| capture curve area | 1632 | 0.8243 | 0.8121 |

The same pairs are preserved inside the regenerated artifact at
`legacy_4fold_footnote` (owner decision 1: 11-fold is the headline, legacy 4-fold
survives as a labeled dated footnote).

---

## 2. XFV_VS_CONSENSUS_MDE95, re-derived on the shipped basis

Command: `python tools/efv_mde_lab.py mde 2000`. Seed 20260807, B = 2000, elapsed 50s
(cost was measured first at 22ms per replicate, so the registered B needed no
reduction). Ledger: `data/xfv_mde_floor.json`.

Protocol, per `docs/EFV_GATE_STANDARD.md` section 2: paired bootstrap over the WHOLE
pool, train AND test resampled together, consensus OLS and the weighted ridge refit on
every draw, blend and baseline scored on identical rows. The replica reproduces the
shipped artifact to four decimals on both sides before any resampling, which is the
parity check that licenses the rest.

### Result

| statistic | point delta | sd | MDE95 (1-sided) | MDE95 (2-sided) | resolvable |
|---|---|---|---|---|---|
| hit pooled rho, pair-weighted | +0.0074 | 0.02675 | **0.0440** | 0.0524 | NO (0.17x) |
| pit pooled rho, pair-weighted | +0.0067 | 0.02648 | **0.0436** | 0.0519 | NO (0.15x) |
| block-rho, pair-weighted | +0.0120 | 0.01975 | **0.0325** | 0.0387 | NO (0.37x) |
| hit pooled rho, unweighted | +0.0113 | 0.02283 | 0.0376 | 0.0447 | NO (0.30x) |
| pit pooled rho, unweighted | +0.0108 | 0.02285 | 0.0376 | 0.0448 | NO (0.29x) |
| block-rho, unweighted | +0.0142 | 0.01695 | 0.0279 | 0.0332 | NO (0.51x) |

Shipped constant: `source_backtest.XFV_VS_CONSENSUS_MDE95` 0.045 to **0.044**.

### THE PREMISE THAT DID NOT HOLD

`docs/master-plan-2026-08-05-omnibus2.md:427-429` estimated the new floor at ~0.012 on
the theory that n 353/438 to 755/890 buys power, and the omnibus-3 plan carried that
forward as "the unweighted deltas may genuinely resolve". **They do not, and the floor
did not move.** Three reasons, in order of size:

1. The bootstrap resamples the TRAIN frame, so the ridge's own refit variance is in
   the delta. That variance is a function of how well the feature block is identified,
   not of test n, and it does not shrink when you add test rows.
2. The rows the promotion added are the WORST rows for power: 2014-2016 folds train on
   almost nothing, and the 2024 fold is censored.
3. Pair-weighting the 2024 cohort at 0.333 hands back the effective n those rows
   bought. Weighted MDE95 0.0440 against unweighted 0.0376 on the identical row set.

### Convention, which was never written down

The retired 0.045 is a ONE-SIDED 95% figure (1.645 sd). The same lab on the legacy
4-fold pool measures 0.0376 hit / 0.0487 pit one-sided, which brackets it; two-sided it
would have been 0.0448 / 0.0580, and 0.045 would have been the hitter number only.
Reading the old constant as two-sided moves the bar by 18%. Section 1 of the gate
standard now states the convention.

### Re-adjudication of the published verdicts

| claim | delta | floor | verdict |
|---|---|---|---|
| hit blend beats consensus, weighted (SERVED) | +0.0074 | 0.044 | NOT RESOLVABLE |
| pit blend beats consensus, weighted (SERVED) | +0.0067 | 0.044 | NOT RESOLVABLE |
| hit blend beats consensus, unweighted | +0.0113 | 0.0376 | NOT RESOLVABLE |
| pit blend beats consensus, unweighted | +0.0108 | 0.0376 | NOT RESOLVABLE |
| block-rho, both sides pooled | +0.0120 | 0.0325 | NOT RESOLVABLE |
| head-to-head vs consensus, identical rows | +0.0297 | 0.0352 | NOT RESOLVABLE (0.84x) |

Nothing resolves. The published `resolvable: false` / `"not resolvable at this power"`
strings were already correct under the old floor and stay correct under the new one;
what changes is that they now sit on a floor measured under the protocol they gate.

---

## 3. block-rho, the second leg of the two-metric gate

Registered at `docs/EFV_GATE_STANDARD.md` section 3 and previously computed nowhere in
shipped code. Now emitted by `efv_model.block_rho_eval()` into both side artifacts, into
`source_backtest.xfv_vs_consensus.block_rho`, and into the scoreboard.

11-fold pair-weighted, n = 1,645 (755 hit + 890 pit): consensus 0.3107, blend 0.3228,
delta **+0.0121** against MDE95 0.0325. Not resolvable.

Two things a reader has to keep straight:

- The registered 0.0149 is the floor for an INCREMENTAL FEATURE ADD measured on
  block-rho (the class in the `docs/EFV_FRONTIER_AUDIT.md` table row "recommended
  evaluator, block-rho"), on the 2020-2024 both-sides pool of n 1,001. It is NOT the
  floor for a model-vs-consensus delta, which is the 0.0325 above. Two different
  statistic classes share the instrument. Lane C3 wants the feature-add floor
  RE-MEASURED on the 11-fold basis before it uses 0.0149; this lane did not do that,
  because a feature-add bootstrap needs the candidate column and lane C owns those.
- The carve-out at `EFV_GATE_STANDARD.md:55-78` still stands: full-pool debut AUC is
  INADMISSIBLE for any candidate that can sense a missing MiLB block. block-rho carries
  no such exclusion, which is what makes it the usable high-SNR instrument.

---

## 4. The hardcoded honest_note

`efv_model.py:2193-2198` shipped a paragraph asserting eFV "BEAT consensus FV on
out-of-sample rank for both cuts" while `verdict_vs_consensus` in the same artifact
recorded `rank_win: false` for every model, and while the hitter `full_pool_km` cut is
rank-NEGATIVE (-0.0215) on the 11-fold basis. It is now derived by `_honest_note` from
`verdict_vs_consensus`, the era split, the block-rho leg, and the MDE, so it cannot
contradict the numbers printed beside it. Sample output, hitters:

> eFV does not beat consensus FV on out-of-sample rank on every cut (debuted_km
> +0.0074, full_pool_km -0.0215), and no gap reaches the 0.044 this eval can resolve
> either way. The higher-SNR block-rho leg reads +0.0121 against 0.0325: not resolvable
> at this power. By era the edge concentrates in recent cohorts (+0.0319 on 2022-2023
> vs +0.0018 on <=2018), so what edge exists is not an artifact of older, less accurate
> scouting. eFV still trails on MAE (it predicts more spread; consensus regresses to
> the mean). That loss is committed.

---

## 5. Protocol sensitivity (REPORT ONLY, no served basis change)

`python tools/efv_mde_lab.py sensitivity`. Chain start 2014 vs 2017, crossed with the
censored 2024 fold in (its live 0.333 weight) or out of the chain. All pair-weighted.
"Weight 0" is implemented as EXCLUSION, because a zero-weight row still enters
`_rankdata` and would keep shifting every other row's rank while contributing nothing.

| chain start | 2024 fold | hit n | hit cons | hit blend | hit delta | pit n | pit cons | pit blend | pit delta | block delta |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014 | in, w 0.333 (SERVED) | 755 | 0.3919 | 0.3993 | +0.0074 | 890 | 0.2495 | 0.2562 | +0.0067 | +0.0120 |
| 2014 | excluded | 664 | 0.3994 | 0.4094 | +0.0100 | 771 | 0.2589 | 0.2689 | +0.0100 | +0.0137 |
| 2017 | in, w 0.333 | 606 | 0.3808 | 0.3922 | +0.0114 | 716 | 0.2336 | 0.2371 | +0.0035 | +0.0147 |
| 2017 | excluded | 515 | 0.3909 | 0.4048 | +0.0140 | 597 | 0.2452 | 0.2526 | +0.0073 | +0.0174 |

What each dial buys:

- **Dropping the censored 2024 fold** raises every level (both raters) and widens the
  margin by about +0.003 on both sides. That is the cleanest single dial, and it is
  exactly what you would expect if the 2024 labels are noise: two thirds of each 2024
  target is extrapolated.
- **Starting at 2017** raises the hitter margin (+0.0074 to +0.0114) and CUTS the
  pitcher margin (+0.0067 to +0.0035). The plan's premise that "2014-2016 folds train
  on almost nothing and pit blend is actively bad there" is HALF right: those folds do
  hurt hitters, but for pitchers they are carrying the margin, not dragging it. The
  pitcher blend's problem is the 2019-2021 era (delta +0.0060), not the 2014-2016 one.
- No cell in this table clears its floor. The largest margin in it, hit 2017-excluded
  at +0.0140, is 0.32x of the hitter MDE95. **Choosing among these dials is choosing
  among four unresolvable numbers**, which is the honest reason not to re-open the
  basis decision the owner just made.

---

## 6. The head-to-head number, and what the glossary claims from it

`assets/glossary.js:654-660` asserts that eFV "orders realized WAR better than every
grade on the board" from the bare inequality 0.3511 vs 0.2846.

**Those two numbers are not computed on the same rows.** `source_backtest._acc` scores
each rater on the rows THAT rater graded. eFV's OOS grade covers 3,210 of the 4,259
common rows; consensus is scored on all 4,259. Re-scoring every rater on the eFV-covered
rows (`accuracy.pooled_efv_common`, added 2026-08-07):

| rater | full common set (n 4259) | eFV-covered rows (n 3210) |
|---|---|---|
| eFV (OOS) | 0.3511 | 0.3511 |
| PROSPX consensus | 0.2846 | **0.3214** |
| MLB Pipeline | 0.2823 | **0.3233** |
| FanGraphs | 0.2502 | **0.2774** |

So the gap is +0.0297, not +0.0665. Slightly more than half the published margin was
the population, not the ordering: the 1,049 rows eFV cannot reach are rows consensus
orders BADLY, and excluding them flatters eFV. Note also that eFV is not ahead of MLB
Pipeline by much on this basis (+0.0278), which matters for a claim phrased as "better
than EVERY grade on the board".

### The same defect ran one level down, and it was worse there

`accuracy.by_archetype` had the identical problem, and the Diamond hub renders it as a
table that green-highlights "the higher of the two". On the honest basis
(`raters_efv_common`, added 2026-08-07) the table goes from six eFV wins to three.

| archetype | n (eFV rows) | eFV | consensus, mixed rows | consensus, IDENTICAL rows | verdict flip |
|---|---|---|---|---|---|
| HS bats | 168 | 0.4495 | 0.3758 | **0.4772** | WIN to LOSS |
| HS arms | 144 | 0.3617 | 0.3086 | **0.3800** | WIN to LOSS |
| College bats | 180 | 0.3414 | 0.3040 | 0.3159 | win holds |
| College arms | 244 | 0.2778 | 0.2755 | **0.2898** | WIN to LOSS |
| Int'l bats | 138 | 0.4178 | 0.3599 | 0.3907 | win holds |
| Int'l arms | 131 | 0.3259 | 0.1865 | 0.2215 | win holds |

Consensus rises in ALL SIX cells when the rows are made identical, which is the
signature of a coverage artifact rather than noise: the players eFV's matrix cannot
reach are systematically the ones the boards order worst. Against MLB Pipeline on the
same basis eFV is also 3-3 (it trails on HS bats 0.4774, HS arms 0.4475, and college
arms 0.3107). "Better than every grade on the board" is not a defensible sentence on
any cut of this table.

MDE for that gap: `python tools/efv_mde_lab.py headtohead 2000`, ledger
`data/xfv_headtohead_gap.json`. Cluster paired bootstrap resampling the eFV matrix pool
by player, refitting the forward chain, scoring both legs on the common-set rows the
resampled players own.

| quantity | value |
|---|---|
| eFV (raw OOS score) | 0.35416 |
| consensus, identical rows | 0.32143 |
| delta | +0.03273 |
| sd | 0.02139 |
| MDE95 (1-sided) | **0.0352** |
| CI95 | [-0.0141, +0.0692] |
| P(delta > 0) | 0.8965 |
| resolvable | **NO** (0.93x of floor) |

**The claim is NOT earned.** It fails three ways: the honest pooled gap is under half
the size the copy quotes; that gap sits below its own detection limit with the
bootstrap CI straddling zero; and on the per-archetype cut eFV is 3-3 against both the
consensus and MLB Pipeline, so "every grade on the board" is false even before power
enters the argument. The pooled gap is close (0.93x of floor) and would likely resolve
with another two graduating cohorts, which is worth saying rather than hiding.

### The exact change requested for `assets/glossary.js:652-657`

Another agent owns that file. There are TWO parts, and the first one is not copy.

**(a) The data source, `glossary.js:652`.** The whole chart, bars and star included,
reads `bt.accuracy.pooled`, while the chart title one block down promises "same
players, same outcome, same window". That promise is false for the eFV bar on that
basis. Change:

```js
const pld = bt.accuracy.pooled || {};
```
to
```js
// The chart title promises identical rows. accuracy.pooled scores each rater on
// the rows IT graded, and eFV covers 3,210 of 4,259, so on that basis the bars and
// the best-of star compare numbers built from different players.
const pld = bt.accuracy.pooled_efv_common || bt.accuracy.pooled || {};
```

That one line moves consensus from 0.2846 to 0.3214, MLB Pipeline to 0.3233 and
FanGraphs to 0.2774 in the bars, and it keeps the star meaningful.

**(b) The verdict paragraph.** Replace its claim with:

> On the 3,210 resolved players eFV and the boards both graded, eFV's out-of-sample
> ordering of realized WAR runs +0.030 Spearman ahead of the PROSPX consensus
> (0.3511 vs 0.3214) and +0.028 ahead of MLB Pipeline. Both gaps sit under the 0.0352
> this backtest can resolve at 95%, so read it as a tie that leans eFV's way, not a
> win. Broken out by prospect group it is three groups to three. The wider
> 0.3511-vs-0.2846 gap you may have seen compares eFV on its 3,210 rows against the
> boards on all 4,259, and about half of it is the row difference rather than the
> ordering.

Constraints for whoever applies it: no em-dash; eFV and +stat values round NEAREST;
the numbers should be read from `accuracy.pooled_efv_common` and
`accuracy.head_to_head_verdict` in `data/source_backtest.json` rather than hardcoded,
since both now exist and regenerate nightly.

If a shorter form is wanted, the minimum honest version is: drop "better than every
grade on the board" and put the MDE beside the number. Any sentence that keeps the
superlative is false on the archetype table regardless of what the pooled figure does.

---

## 7. What lane A changed in served output

- `source_backtest.XFV_VS_CONSENSUS_MDE95` 0.045 to 0.044 (both verdicts stay
  "not resolvable at this power"; no star turns on or off).
- `accuracy.pooled_efv_common`, `accuracy.common_n_efv`,
  `accuracy.head_to_head_verdict` added to `data/source_backtest.json`.
- `xfv_vs_consensus.block_rho` added to the same artifact.
- `block_rho` and a derived `honest_note` added to `data/xfv_eval.json` and
  `data/xfv_eval_pitcher.json` (lands on the next eval rebuild).
- `data/xfv_scoreboard_eval.json` regenerated onto the 11-fold pair-weighted basis,
  stamped with `basis` and carrying `legacy_4fold_footnote`. Its pooled cells now
  reproduce the published headline exactly (`artifact_crosscheck` drift 0.0000 on both
  sides, against 0.0083 / 0.0050 before), so the Diamond hub and the Methodology tab
  stop disagreeing.
- The scoreboard head-to-head moved onto the identical-rows basis, so the Diamond hub
  stops printing a margin that was part population.

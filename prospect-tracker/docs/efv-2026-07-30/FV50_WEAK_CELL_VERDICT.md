# Lane F: the FV50 weakness is gone, and the premise had expired

Owner ask 8: "Why is eFV so weak at the ~50 FV tier/cohort? Can we improve eFV so that it
wins across all cohorts/comparison lanes possible, without shipping losses to
Spearman/AUC? Can we improve AUC score further?"

Answered by regenerating `data/xfv_scoreboard_eval.json` on the current tree
(2026-07-30) rather than reasoning from the committed artifact, which was dated
2026-07-24 and predated the entire outcome-calibration program.

## 1. The FV50 cell is now a WIN on both sides

| tier | measured 2026-07-24 | measured 2026-07-30 | swing |
|---|---|---|---|
| **pit FV50** | eFV 0.1697 vs cons 0.3123, **margin -0.1426** (n=40) | eFV 0.2405 vs cons 0.0824, **margin +0.1581** (n=41) | **+0.30** |
| **hit FV50** | already a win (+0.4594) | eFV 0.2845 vs cons 0.1529, **margin +0.1316** (n=70) | still a win |

The single largest weak cell in the program's opening diagnosis no longer exists. It was
not repaired by a lane aimed at it; it was repaired by the pooled outcome refit, the age
dial, the usage-based roles and the fresh ingest all landing together, plus a tier
population that grew from 40 to 41 and shifted composition.

**This also corrects the plan I wrote and the report I gave.** Both said the FV50
weakness was pitcher-only and live. It was pitcher-only and live *on the July 24
measurement*. The correct current statement is that eFV wins the FV50 cell on both sides.

## 2. Full per-tier picture, fresh

| side | tier | n | eFV | consensus | margin |
|---|---|---|---|---|---|
| hit | 40 | 140 | 0.1262 | -0.0355 | +0.1617 |
| hit | **45** | 75 | 0.2792 | 0.3430 | **-0.0638** |
| hit | 50 | 70 | 0.2845 | 0.1529 | +0.1316 |
| hit | **55** | 22 | 0.3213 | 0.3906 | **-0.0693** |
| hit | 60 | 15 | 0.4000 | 0.2140 | +0.1860 |
| pit | 35 | 79 | 0.0214 | -0.1469 | +0.1683 |
| pit | 40 | 238 | 0.1541 | 0.0518 | +0.1023 |
| pit | **45** | 60 | 0.0683 | 0.0916 | **-0.0233** |
| pit | 50 | 41 | 0.2405 | 0.0824 | +0.1581 |
| pit | 55 | 17 | -0.1348 | -0.2653 | +0.1305 |

Three tier cells remain negative. Against their own registered floors (t45 MDE95 is
~0.055 hit / ~0.10 pit):

- **hit FV45, -0.0638 on n=75.** The only tier weakness that clears its own noise floor,
  and it clears it barely. This is the known t45 fringe cell and it is already a
  registered gate metric, so it has a harness and a floor and does not need a new one.
- **pit FV45, -0.0233 on n=60.** Well inside its floor. Not a finding.
- **hit FV55, -0.0693 on n=22.** Twenty-two players. Not a finding.

So the honest answer to "win across all cohorts and lanes" is that there is exactly ONE
tier cell worth spending on, hitters at FV45, and it is the cell the gate standard already
tracks as `t45`.

## 3. AUC is already winning on all four measures

| side | metric | eFV | consensus | margin |
|---|---|---|---|---|
| hit | Spearman | 0.3882 | 0.3522 | +0.0360 |
| hit | AUC contributor | 0.7768 | 0.7556 | +0.0212 |
| hit | AUC star | 0.8275 | 0.8087 | +0.0188 |
| pit | Spearman | 0.3060 | 0.2671 | +0.0389 |
| pit | AUC contributor | 0.7187 | 0.7023 | +0.0164 |
| pit | AUC star | 0.8552 | 0.8371 | +0.0181 |

Head-to-head on the common resolved set (n=2,200, every source graded the player
preseason, eFV entering with its forward-chained out-of-sample grade): eFV Spearman
**0.384** against PROSPX consensus 0.283 and FanGraphs 0.248, AUC contributor 0.7572
against 0.7316.

eFV wins every pooled lane and every AUC on both sides. "Improve AUC further" has no
identified defect to attack: the remaining 11 weak cells are slices, not lanes, and the
one that clears its floor is a Spearman cell, not an AUC cell.

## 4. What this means for the lane

**Lane F closes without a model change**, because the defect it was scoped against is
gone and the replacement candidates do not clear their floors. That is the correct
outcome, not a failure to find one: the alternative would have been to go hunting for a
lever against an eleven-cell list where ten of the eleven are inside their own noise, and
the gate standard exists to stop exactly that.

The one live thread out of this lane is the pitcher arm of E1
(`docs/efv-2026-07-30/E1_REPEAT_LEVEL_GATE.md`): +0.0127 pooled, both AUC labels up,
3 of 4 folds, beating every zero-information control, still 0.79x its floor. If any
accuracy work continues, that is the candidate with evidence behind it, and it is an
owner call rather than a measurement question.

Standing caveat that did not change: the scoreboard's per-tier cells have no registered
per-tier MDE. Margins in the +/-0.07 range on n of 15 to 75 should be read as texture,
not as findings, which is precisely how the -0.1426 that opened this program should have
been read at the time.

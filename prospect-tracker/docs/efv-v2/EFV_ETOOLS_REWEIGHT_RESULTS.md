# eFV tool inputs on eTools: results for the owner (2026-10-16)

Plain language. Every number is copied from `data/_labs/efv5/efv_etools_reweight_fit.json`; the
method, fixed and committed alone before any number (49ca37be), and the full tables are in
`docs/efv-v2/EFV_ETOOLS_REWEIGHT.md` (sections 12 and 13). Development frames only (list years
2017 to 2019, debut classes 2017 to 2023); nothing here is cut by consensus-FV level. No
em-dashes.

## The one-line answer

Putting the eTools into eFV in place of the consensus tool grades does not make eFV better, so
nothing changes on the site. The eTools are better at predicting what each tool measures (hit
tool: strikeout rate), but once consensus FV is known they add nothing to predicting later WAR,
and eHIT is a worse WAR signal than the consensus hit grade it replaces.

## What was asked (EW3-26)

"Recheck correlations for tool weights in eFV using eTools ... Make sure to re-weight as well."
Two parts: (1) how well each eTool, against the consensus grade it replaces, lines up with the
eFV outcome (later WAR), by position group and age band; (2) refit the served eFV skill head
with the eTools in the tool slots, every weight re-estimated, and keep it only if it beats the
served eFV (the re-fit RT) on the development frames.

## Part 1: does each eTool line up with later WAR better than the consensus grade?

Within-year rank correlation with later WAR (higher is better). "Gain over consensus FV" is
how much the tool adds to an order that already knows consensus FV.

| tool | list years: eTool / consensus grade | debut classes: eTool / consensus grade | gain over consensus FV, eTool minus grade (both frames) |
|---|---|---|---|
| Hit (eHIT) | 0.089 / 0.131 | 0.194 / 0.299 (worse, CI95 -0.165 to -0.048) | +0.002 and +0.000 |
| Game power (ePOW) | 0.075 / 0.075 | 0.122 / 0.123 | +0.000 and -0.006 |
| Fastball (eFB) | -0.013 / -0.038 | 0.127 / 0.095 | -0.001 and +0.006 |
| Command (eCMD) | 0.118 / 0.147 (worse) | 0.165 / 0.191 (worse) | -0.003 and -0.002 |
| Raw power (eRAW, not a passing eTool) | 0.045 / 0.041 | 0.055 / 0.049 | 0.000 and 0.000 |
| Speed (eSPD, not a passing eTool) | 0.018 / 0.010 | 0.114 / 0.097 | +0.007 and +0.001 |
| Pitch selection (eSEL), 73 rows of 2023 | | 0.149 / 0.120 | too few rows |
| Bat control (eBAT), 73 rows of 2023 | | -0.011 / -0.043 | too few rows |

No eTool adds more over consensus FV than its consensus grade does with an interval above zero,
overall or in any position group or age band; one adds less (ePOW on the debut classes, -0.006,
CI95 -0.012 to -0.000). eHIT trails the consensus hit grade in every hitter group with 100 or more rows except
list-year catchers. The reason, as far as these frames show it: eHIT is built to predict MLB
strikeout rate, and strikeout rate is not what separates later WAR once consensus FV is known.
eSEL and eBAT have consensus grades only from the 2021 boards, so they reach just one debut class
and cannot be judged here.

## Part 2: the re-weight

| version | what it is | list years | debut classes | pooled vs served |
|---|---|---|---|---|
| served (RT) | the re-fit serving today | 0.1683 | 0.3937 | |
| E | eTools in the four tool slots | 0.1632 | 0.3916 | -0.0045 |
| ED | E minus the raw strikeout and first-pitch strike rates the eTools already carry | 0.1635 | 0.3926 | -0.0040 |
| EC (null) | E's layout with the consensus grades | 0.1638 | 0.3915 | |
| EP (null) | E with each player's eTool shift shuffled | 0.1639 | 0.3946 | |
| consensus | PROSPX consensus | 0.1792 | 0.3814 | |

The rule fixed in advance needed a pooled gain over the served eFV and no frame behind by more
than 0.005. E is behind on both frames (-0.0052 on list years, interval -0.0100 to -0.0003); ED
is behind by -0.0049 and -0.0011. Neither passes. Against its own nulls E reads -0.0005 (same
layout, consensus grades) and -0.0013 (shuffled eTools): the eTools carry no signal for WAR that
the consensus grades did not. The small loss comes from the layout change on pitchers (the
fastball slot widened from the Triple-A cell to every pitcher), not from the eTools.

## Every tool's weight, old and new

Weights are in percentile points of the order per standard deviation of the tool, as the
production fit carries them.

| tool | served eFV (consensus grade) | re-weighted (eTool, version E) |
|---|---|---|
| Hit | 0.051 | 0 (eHIT fails the rule that a driver keep one sign year to year, in 6 of 7 debut-class folds) |
| Game power | 0 | 0.009 |
| Fastball | 0.017 (Triple-A pitchers only) | 0.066 (every pitcher with a grade) |
| Command | 0.055 | 0.056 |
| Head weight on the skill side | hitters 0.297, pitchers 1.0 | hitters 0.218, pitchers 0.884 |

## What happens now

- Nothing on the site moves. eFV keeps the consensus tool grades as inputs; the eTools stay the
  shown tool grades everywhere they already are (EW3-27 is untouched).
- The re-weighted tool arm (`efv_etools_reweight.etool_inputs`) is handed to EFV_X3_POOLED_MODEL
  as registered, with this read as its starting point.
- Two development rows (model `efv_etools_reweight`) are on the Source Comparison progress
  ledger, drawn hollow like every development row; they adjudicate nothing.

## Owner questions (defaults applied, nothing stopped)

1. **eTools inside eFV.** Default (a): leave eFV on consensus tool inputs; the eTools remain the
   shown grades and an input X3 may test under its own registration. (b) Register an eTool
   variant fitted to a WAR-relevant label (the current eTools are fitted to each tool's own
   stat, for example strikeout rate for hit), then re-run this comparison; this costs a new
   registration and a new read of the same development frames. (c) Drop the arm from X3
   entirely given this read.
2. **The weights the eTools composite (EW3-28, ETOOLS_PLUS) reads.** It was to weight eTools by
   "their re-weighted eFV weights". Default (a): ETOOLS_PLUS takes the weights above from
   version E (hit 0, game power 0.009, fastball 0.066, command 0.056) as its input and decides
   its own scaling under its own registration, saying that hit carries no eFV weight. (b) Use
   the served eFV's consensus-tool weights mapped onto the eTools (hit 0.051, fastball 0.017,
   command 0.055, game power 0). (c) Weight the eTools by their own tool-label accuracy instead
   of eFV weights.

# eTools: the flip question (ETOOLS_FLIP_PREP, 2026-10-15)

**Question ETOOLS-FLIP-1: show eTools on the PROSPX cards? (yes / no)**

Nothing is flipped. `ETOOLS_ON` (etools.py) and `ETOOLS_CARD_ON` (prospx/index.html) are both
False and a test pins them together. Flipping is: set both True, run `python etools.py --preview`
(it then writes `data/etools.json`), restamp, commit.

## What the card would show

On the Scouting / Tools tab, beside each consensus tool grade, a small chip (for example
"eHIT 45"), and under the grade grid one line per eTool: the eTool (rounded up to the next 5), its
80% band, the consensus grade, and each sub-driver's push in grade points (for example
"translated strikeout rate +3.4, pitches per batter faced +0.8"). Six tools: eHIT, ePOW, eSEL,
eBAT, eFB, eCMD. The other seven keep the consensus grade with no chip. eFV does not change
either way (EFV_X3 decides whether eFV reads eTools).

## The numbers (all from data/_labs/etools/, summarized in data/etools_eval.json)

Within-list rank correlation with the tool's outcome stat, consensus grade to eTool. MLB is among
players who debuted; minors is the translated Double-A and Triple-A line.

| eTool | outcome | MLB consensus to eTool (LB) | minors (LB) | never reached Double-A (d, LB) | re-weighted for promotion (d, LB) | 2026 shift |
|---|---|---|---|---|---|---|
| eHIT | MLB K% | 0.298 to 0.600 (+0.256) | 0.436 to 0.710 (+0.247) | +0.271 (+0.228) | +0.256 (+0.225) | +1.33, inside the development years |
| ePOW | ISO | 0.539 to 0.573 (+0.017) | 0.594 to 0.633 (+0.030) | +0.059 (+0.046) | +0.041 (+0.029) | +0.13 |
| eSEL | chase, 2026 | 0.496 to 0.585 (+0.045) | 0.556 to 0.628 (+0.048) | not measurable | +0.061 (+0.040) | -0.30 |
| eBAT | zone contact, 2026 | 0.383 to 0.474 (+0.059) | 0.477 to 0.556 (+0.062) | not measurable | +0.075 (+0.054) | +0.13 |
| eFB | pitcher K% | 0.293 to 0.362 (+0.036) | 0.294 to 0.471 (+0.153) | +0.145 (+0.107) | +0.165 (+0.142) | **+2.92, outside** (-2.02 to +1.49) |
| eCMD | pitcher BB% | 0.377 to 0.418 (+0.024) | 0.539 to 0.613 (+0.061) | +0.099 (+0.069) | +0.077 (+0.061) | +0.49 |

LB: one-sided 95% lower bound, with each bootstrap draw re-ranked (the fixed version of the look's
bootstrap; every pass held). The three review items are closed: (1) drift: only eFB is off the
development years, all six are served centred on the board they score, which costs at most 0.0017
of rank correlation out of fold; (2) promotion: all six PROMOTION-CLEAR (eSEL and eBAT on the
re-weighted read alone); (3) the BA weight and bootstrap fixes moved no verdict, and outlet
weighting is still null on 13 of 13 tools.

How much the cards would move (2026 boards, re-centred): eHIT standard deviation 6.3 grade points
from the consensus, 322 of 829 hitters by 5 or more; eFB 5.8, 320 of 803; eSEL 5.1, 203 of 611;
eBAT 5.4, 205 of 659; ePOW 2.7, 50 of 829; eCMD 3.0, 63 of 801. The bands are wide (eHIT about
+/- 12 grade points at 80%), and the chips round up to the next 5.

## Options

1. **No, keep dark (applied: the spec's default).** Nothing changes; the Library's eTools view
   shows the evidence.
2. **Yes, all six, re-centred (recommended on the numbers).** Every registered check passed.
3. **Yes, but hold eFB** until a second season shows whether its drift (2026 translated
   strikeout rates above what the fastball grades predict) persists. Five chips; eFB stays
   consensus.
4. **Yes, with the reduced sub-driver sets**: drop P/PA PAR from eHIT and swinging-strike rate
   from eFB (amendment 1 found they add nothing given the others; the reduced eTools beat
   consensus as well, eHIT +0.302 / +0.274, eFB +0.065 / +0.176). This changes the built eTool and
   needs its own short registration before it serves.

## Smaller questions, defaults applied

- **ETOOLS-FLIP-2, Baseball America's weight in the outlet-weighting arm.** Applied: derived by
  the same estimator over the three outlets (0.92 to 1.05). Alternatives: exclude BA (reported, also
  null), or a declared neutral 1.0 (what the look did implicitly). The arm serves nothing.
- **ETOOLS-FLIP-3, the drifted eTool.** Applied: the registered rule, re-centred on the scoring
  board. Alternative: show eFB uncentred with a drift note beside it (its shift would stay +2.9).

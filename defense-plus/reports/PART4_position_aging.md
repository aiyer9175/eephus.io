# Part 4 — General Position Defensive Aging (joint-dropout)
Date: 2026-06-16 · `pipeline/11_position_aging.py` · `~/mlb-aging-curves/fit_joint_dropout`, OAA 2016–2025 (DRS for C), Inn≥300

Dropout = not playing that position next year, so an aging SS forced to 3B counts as an SS exit — the model corrects the "surviving SS look young" bias. Strong `gamma`>0 everywhere confirms the correction matters (premium-position decliners are pushed off the position).

## Peak-age ladder (sorted)
| Pos | metric | peak age | decline peak→33 (runs) | 27→33 | gamma |
|---|---|--:|--:|--:|--:|
| LF | OAA | ~21* | 3.8 | 0.9 | 0.12 |
| RF | OAA | ~21* | 4.2 | 2.2 | 0.29 |
| CF | OAA | ~23 | **6.0** | 4.4 | 1.10 |
| 2B | OAA | 26 | 2.3 | 2.2 | 0.38 |
| 3B | OAA | 26 | 1.5 | 1.4 | 2.40 |
| SS | OAA | 27 | 3.7 | 3.7 | 0.79 |
| C | DRS | 28 | 5.0 | 4.8 | 0.71 |
| 1B | OAA | **31** | 0.2 | −0.4 | 1.60 |

\*LF/RF peaks sit at the young edge of the grid → read as "declines from the early 20s," not a precise peak.

## The pattern: peak age is inversely ordered with athletic demand
1. **Outfield range peaks earliest and declines steeply** — LF/RF from the early 20s, **CF the steepest of all (−6.0 runs peak→33)**. OF range is pure speed (sprint speed peaks ~22–23), so it ages exactly like the burst component from the jump analysis.
2. **Infield peaks mid-20s** — 2B/3B at 26, SS at 27. SS declines more (−3.7) than 3B (−1.4): SS is range-driven (ages), 3B is reactions/arm (ages well).
3. **Catcher peaks latest among skill positions (28) and declines moderately** (−4.8 by 33) — framing is a *learned* skill that takes time to peak, then workload (knees/back) erodes it.
4. **1B peaks at 31 and barely ages** (−0.4 by 33, essentially flat) — least athletic, most experience-based (footwork/scooping); also the noisiest, lowest-value range signal.

So the defensive spectrum is also an **aging spectrum**: the more a position leans on athleticism/range, the younger it peaks and the harder it falls. This pairs directly with the survivorship work — the positions that decline fastest (CF, SS) are exactly the ones from which aging players get displaced (high gamma).

## Use for Defense+ / Career+
- **Age the range estimate hardest at CF/SS**, gently at 3B/1B. A 30-yo CF projects down much more than a 30-yo 3B.
- Peak ages feed Part 5 (position viability): the window for holding a premium position is short (CF/SS peak 23–27), which is *why* migration down the spectrum is the norm — quantified here.
- Catcher's late peak + workload decline argues for separate framing/blocking/throwing aging (a follow-up; DRS-total here blends them).

## Caveats
- OAA for OF is **range only** (corner arm value not captured); within-position aging (how defense ages for those who stay, dropout-corrected).
- 1B OAA is a thin, noisy signal → its "no decline" is partly low range content.
- Catcher uses DRS (framing-dominated); component-level catcher aging deferred.

## Confirmation
Independently reproduced 2026-06-18 (re-fit from scratch): peak ages matched exactly, declines matched (e.g. CF −0.78 SD ≈ the −4.4 runs here; 1B flat). Result is stable.

## Files
- `pipeline/11_position_aging.py`, `reports/11_position_aging.csv`, `reports/11_position_aging_curves.csv`

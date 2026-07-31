# Lane A verdict: the arm gate is a NO-SHIP, and sprint speed is the indicator that works

Measured 2026-07-30/31 against `CONVERSION_ARM_GATE.md`, which pre-registered the design
and its no-ship conditions before any of this was run.

## VERDICT

| piece | verdict |
|---|---|
| `savant_arm_strength.py` ingest (795 players, 2020+) | **SHIP.** Real data, first arm measurement in the tree. |
| `savant_sprint.py` ingest (1,603 players, 2015+) | **SHIP.** |
| **arm GATE on position candidates** | **NO SHIP.** Triggers pre-registered no-ship condition 1: the derived floors do not separate positions once throw context is removed. |
| sprint speed as the range indicator | **PROCEED.** It separates positions four times better than adjusted arm does. |

## 1. What the raw numbers looked like, and why they were a trap

2025 incumbents, arm velocity by the position thrown from, at least 25 throws:

| pos | n | p10 | median | p90 |
|---|---|---|---|---|
| 1B | 54 | 68.7 | 75.0 | 81.1 |
| 2B | 78 | 74.9 | 78.2 | 83.2 |
| 3B | 49 | 79.9 | **83.3** | 88.6 |
| SS | 57 | 79.6 | 82.9 | 87.6 |
| LF | 70 | 82.6 | 86.2 | 90.9 |
| CF | 66 | 83.1 | 87.7 | 93.3 |
| RF | 76 | 85.2 | 89.1 | 95.0 |

Read cross-sectionally this is exactly the owner's hypothesis confirmed: third basemen
throw 5.1 mph harder than second basemen, so gate the move on arm. **That reading is
wrong**, and building the gate on it would have encoded where a player stands as though
it were how hard he throws.

## 2. The measurement that killed it

Take the SAME player in the SAME season who threw from two positions. His arm is held
constant by construction, so any difference is throw context.

| pair | n | mean delta (mph) |
|---|---|---|
| 3B minus 2B | 65 | **+3.69** |
| SS minus 2B | 91 | +3.71 |
| **3B minus SS** | 38 | **+0.50** |
| 3B minus 1B | 13 | +8.29 |
| 2B minus 1B | 20 | +2.67 |
| any OF minus any IF | 102 | **+7.46** (98% of pairs read higher in the OF) |

So of the 5.1 mph that appeared to separate third base from second base, **3.69 is the
same arm throwing from a different spot**. Longer throws are made harder; the radar is
reading the throw, not the thrower.

Applying those within-player offsets back to the cross-section and re-reading the
medians in a common (2B) frame:

| pos | raw median | context-adjusted median |
|---|---|---|
| 1B | 75.0 | 77.7 |
| 2B | 78.2 | 78.2 |
| LF | 86.2 | 78.7 |
| SS | 82.9 | 79.2 |
| 3B | 83.3 | 79.6 |
| CF | 87.7 | 79.8 |
| RF | 89.1 | 80.0 |

**The infield spread falls from 8.30 mph to 1.94 mph, against a within-position standard
deviation of 3.80 mph.** Every position from first base to right field lands inside a
2.3 mph band. The ordering is still the right one, so the selection is real, but it is
half the size of the noise inside any one position.

This is not circular: the offsets were estimated with talent held fixed (within player),
so if positions genuinely selected on arm, the adjusted medians would still separate.
They do not.

## 3. What this actually answers for the owner

The question was "does a struggling shortstop have the arm to move to third, or should he
go to second or first?" The measured answer is cleaner than a gate would have been:

**Arm is essentially never the binding constraint inside the infield.** A shortstop's arm
reads 0.50 mph off a third baseman's on the same scale, and a second baseman's arm sits
1.4 mph below a third baseman's after context, well inside one standard deviation. If a
shortstop cannot play third, it is not his arm. It is hands, actions or first-step
reaction, and those are already inside the OAA read the model transports today.

The intuition is real and widely held. It is also, on this evidence, mostly an artifact of
comparing throw distances.

## 4. Sprint speed is the indicator that survives

2025, by Savant's own position tag:

| pos | n | p10 | median | p90 |
|---|---|---|---|---|
| C | 83 | 24.4 | 26.1 | 27.6 |
| 1B | 58 | 25.0 | 26.4 | 28.0 |
| 3B | 72 | 25.8 | 27.0 | 28.8 |
| RF | 68 | 26.5 | 27.8 | 29.3 |
| 2B | 71 | 26.3 | 27.8 | 28.9 |
| LF | 62 | 27.0 | 27.8 | 28.9 |
| SS | 53 | 26.5 | 27.9 | 29.2 |
| CF | 64 | 27.7 | **28.9** | 29.6 |

Spread of position medians 2.75 ft/s against a pooled sd of 1.35, a **ratio of 2.03**,
against context-adjusted arm's 0.51. Four times the discrimination, a clean monotone
ladder in the expected order, and no throw-context confound, because a sprint is a sprint
wherever you stand.

So the outfield half of ask 1 is the half with a working instrument: centre field is
genuinely separated (28.9 against 27.8 for the corners and 26.4 for first base), which is
the discrimination the owner wanted for "who projects best to the outfield".

## 5. What ships now, and what is next

Shipping: both ingests, with tests and registry rows. The arm feed is worth having even
though its gate failed. It is the first arm measurement in the tree, it is what a scouted
throw grade can finally be audited against (`data/tool_grade_tables.json` has no
`throw` table because nothing measured arms), and a genuinely weak arm is still a real
signal even if position does not select on it.

Not shipping: the arm gate on `positional_fit` candidates.

Next, on the evidence: a sprint-speed range indicator for the outfield projection, gated
on its own terms. It should be built against the OF half of the ask, where the
measurement works, rather than the infield half, where it does not.

## 6. Caveat on the offsets

The within-player pairs are a selected population: players who log real innings at two
positions are utility types, and they may not throw the way regulars do. The offsets are
estimated on 13 to 114 pairs per comparison. They are strong enough to overturn a naive
gate, which is what they were used for; they are not proposed as a published correction
table without a wider fit.

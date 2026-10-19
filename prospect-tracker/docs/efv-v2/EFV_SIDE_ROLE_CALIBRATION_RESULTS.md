# eFV side and role calibration: results in plain language

Read 2026-10-19 under owner decision EW3-42 ("I feel like pitchers are inflated across the
board, especially relief pitchers"). Method and the full numbers:
`docs/efv-v2/EFV_SIDE_ROLE_CALIBRATION.md` (sections 11 and 12); artifact
`data/_labs/efv5/efv_side_role_calibration.json`. Development frames only (list vintages 2017 to
2019 and debut years 2017 to 2023, 3,692 rows); nothing here is a served claim.

## The short answer

Partly yes, but no fix passed, so nothing served changes.

- Across the whole board, pitchers do not clearly under-deliver: at the same implied value they
  realized 0.93 of what hitters realized (95 percent range 0.74 to 1.17).
- At the top they do. In the top tenth of each side's grades, pitchers realized 0.80 of the value
  their grade implies (0.64 to 0.997). On the list-vintage frame, where a prospect who never
  reaches the majors counts as zero, top pitchers realized 0.57 of what top hitters did (0.35 to
  0.88). Among players who did debut, the two sides matched (1.01). So the gap is mostly about
  pitchers failing to reach the majors, not about what they do once there.
- Relievers: on the list-vintage frame, pitchers used in relief realized 0.53 of what starters
  did (0.20 to 0.97). Among debuted pitchers the 73 relief rows point the other way, and pooled
  the figure is 0.84 (0.43 to 1.37), so the sign is not settled. Short starters (Brandon Clarke's
  usage) matched starters.

## What was tried

The value chain gives a pitcher and a hitter with the same eFV grade the same expected six-season
WAR. Two corrections were tested, each mapping a grade to the grade that the other side would
need to deliver the same value:

| candidate | what it does | squared error vs no correction (positive is better) |
|---|---|---|
| b | one map for hitters, one for pitchers | -0.0239 (95 percent range -0.0386 to -0.0097) |
| c | b plus separate maps for starters, short starters and relievers | -0.0231 (-0.0385 to -0.0087) |

Both made the predictions worse, not better. The maps are fitted from a few hundred rows per side,
and the top of each map rests on a handful of players, so they swing too far: b would lift Seth
Hernandez from 59.0 to 67.2 and Jesus Made from 61.5 to 67.5 while pulling most top pitchers
down. A simulation on the same rows also shows that this kind of test could not have detected a
15 percent side gap even if one existed (it caught it 2 times in 100).

## What would have changed if b had passed (it did not)

The joint top 100 by grade would have held 13 pitchers instead of 31; the top 50 hitters would
have risen about 1.8 grades and the top 50 pitchers fallen about 1.3. Under c, relievers would
have fallen about 0.9 grades on average.

## What a next step could be

A smaller correction (one discount per side and role, or a discount only on the top of the
pitcher board) was not tested here. It would need its own registration, and a check first that
the frames can detect a gap of the size reported above.

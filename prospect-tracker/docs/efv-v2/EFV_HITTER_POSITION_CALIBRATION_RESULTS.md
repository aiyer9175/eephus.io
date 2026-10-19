# eFV hitter position calibration: results in plain language

Read 2026-10-19 under owner decisions EW3-47 ("Should we also do EFV_SIDE_ROLE_CALIBRATION on
hitter positions/roles?") and EW3-48 ("Can we factor MiLB defensive runs for each prospect into
the role factor, as well as positional versa?"). Method and the full numbers:
`docs/efv-v2/EFV_HITTER_POSITION_CALIBRATION.md` (sections 12 and 13); artifact
`data/_labs/efv5/efv_hitter_position_calibration.json`. Development frames only (list vintages
2017 to 2019 and debut years 2017 to 2023, 1,871 hitter rows); nothing here is a served claim.

## The short answer

No position correction passed, so nothing served changes.

- Hitters were grouped by the position their graders listed when the grade was read (C, SS/CF,
  2B/3B, corner OF, 1B/DH; a multi-position listing counts at its most demanding position). At
  the same eFV grade, each group realized about what the grade implies: C 1.05, SS/CF 1.07, 2B/3B
  0.83, corner OF 1.01, 1B/DH 1.03 (each 95 percent range spans 1).
- The tested correction pools the five groups and lets each move only as far as the data show
  real differences between them. The groups differ less than their noise, so every correction
  factor came out at exactly 1: the correction equals no correction.
- These frames can only detect a gap of about 30 percent for SS/CF and 50 percent or more for
  the other groups. A planted 25 percent SS/CF effect was detected 2 times in 100.

## Shortstops and center fielders who move down the spectrum

Of the listed SS and CF who kept playing, 36 percent later played mainly at 2B, 3B, a corner
outfield spot or 1B. They realized 1.27 of their implied value, against 1.04 for those who
stayed (the difference is not resolved). A move is only seen for a player who kept playing, so
movers are hitters whose bat carried them to another position; this explains the past, it does
not predict who will move.

## MiLB fielding runs and versatility (EW3-48)

MiLB fielding runs exist from 2021, so these terms could only be read on the 2022 and 2023 debut
cohorts (175 hitters with a fielding history before their grade date). All three point the
expected way: better MiLB defenders, players who qualified at more positions, players with a
larger share of games at C, SS or CF, and better defenders listed at SS or CF realized more value
(+0.15 to +0.19 per standard deviation). None is distinguishable from zero, and the test could
have detected a planted effect of 0.30 per standard deviation at most 5 times in 100, so the
result is "underpowered", not "no effect".

## What would change the answer

More debut cohorts with 2021+ MiLB fielding history and a few seasons of MLB outcome. The 2024
cohort is outside the development frames and the 2025+ cohorts are reserved, so this read cannot
be repeated with more power on the current frames.

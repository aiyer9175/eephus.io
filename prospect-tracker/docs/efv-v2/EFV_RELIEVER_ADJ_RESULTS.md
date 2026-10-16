# eFV pitcher usage (reliever) adjustment: results in plain language

Read 2026-10-15 under owner decision EW3-31. Method and the full numbers:
`docs/efv-v2/EFV_RELIEVER_ADJ.md` (sections 11 and 12); artifact
`data/_labs/efv5/efv_reliever_adj_fit.json`. Development frames only (list vintages 2017 to
2019 and debut years 2017 to 2023, pitchers); nothing here is a served claim.

## The short answer

No reliever adjustment passed the rule fixed before the read, so the served eFV does not
change. The data are also too noisy to settle the question either way: a simulation on the
same rows shows that even if the model's calls on short-outing pitchers were only 40 percent
real, the rule would almost never pass. What the point estimates say is split:

- **Relievers** (under half their appearances are starts): yes, the model looks too
  enthusiastic. On the pitchers it moved up most, relievers realized none of the move on
  average, while starters realized about half of it. A relief-only weight would keep about
  30 percent of a reliever's skill shift.
- **Short starters** (mostly starts, under 3.5 innings per start, Brandon Clarke's class): no.
  Their up-calls came true about as often as starters' did.

## Brandon Clarke

His 2026 line reads 10 games, 10 starts, 29.2 innings: 3.0 innings per start, so the usage
rule calls him a short starter, not a reliever. The served grade is 49.8 (rank 13 of 941
pitchers) against a consensus of 45.9. The best-scoring adjustment (B, a separate weight on
the skill shift by role) leaves him at 49.8 because short starters' shifts held up on the
development frames. The adjustment that adds a role term inside the model (A) would raise him
to 52.3; the one that normalizes strikeout and CSW rates for outing length (C) leaves him at
49.8 and moves him to rank 15. None of these serves.

## What was tested

| candidate | what it does | pitcher ranking vs the current model, both frames pooled |
|---|---|---|
| A | a role term inside the skill head | +0.0009 (CI95 -0.0163 to +0.0180) |
| B | a separate DS-08 weight on the skill shift for short starters and relievers | +0.0035 (CI95 -0.0029 to +0.0098) |
| C | strikeout, CSW, K-beyond-whiff and population rates normalized by batters faced per outing | -0.0058 (CI95 -0.0150 to +0.0034) |

The rule needed the pooled interval to sit above zero and neither frame to drop by more than
0.005. B came closest (both frames up, interval still spanning zero); it beat 98.5 percent of
reshuffled-role versions of itself, so the role split is not pure noise, but it is not
resolved.

## How the usage label works

From the minor league lines through the season the read can see: Reliever when fewer than
half the appearances are starts; Short starts when most are starts but the innings per start
are under 3.5; Starter otherwise; nothing for pitchers with under 5 appearances or no line.
The PROSPX card now prints it for every board pitcher (for example "Usage: Short starts (2026
MiLB): 10 G, 10 GS, 29.2 IP, 3.0 IP per start"). It is a statement of usage and moves no
grade. On today's board: 390 starters, 83 short starters, 340 relievers, 35 with too few
appearances, 93 with no line.

## If B were served (descriptive only; it did not pass)

83 of 941 pitchers would move by a grade or more, at most 4.3. Relievers' average eFV minus
consensus would go from -0.33 to -0.12 and their average distance from consensus from 0.91 to
0.34. The 20 largest short-start and relief movers:

| pitcher | usage | consensus | eFV now (rank) | under B (rank) |
|---|---|---|---|---|
| micah_ashman | RELIEF | 40.0 | 45.2 (#64) | 40.9 (#165) |
| sandro_santana | RELIEF | 39.2 | 44.2 (#73) | 40.0 (#213) |
| matt_jachec | RELIEF | 40.0 | 44.2 (#79) | 40.9 (#180) |
| andrew_dunford | RELIEF | 35.0 | 31.8 (#941) | 35.0 (#909) |
| dylan_lesko | RELIEF | 42.5 | 36.6 (#602) | 39.4 (#285) |
| jordarlin_mendoza | RELIEF | 39.4 | 36.6 (#597) | 38.8 (#391) |
| ryan_forcucci | SHORT-START | 37.6 | 33.9 (#940) | 31.8 (#941) |
| josh_grosz | RELIEF | 40.0 | 42.2 (#127) | 40.1 (#210) |
| austin_vernon | RELIEF | 39.2 | 36.2 (#666) | 38.1 (#450) |
| carlson_reed | RELIEF | 39.2 | 36.2 (#660) | 38.1 (#448) |
| landon_sims | RELIEF | 40.2 | 37.5 (#539) | 39.2 (#323) |
| chase_mobley | RELIEF | 39.2 | 35.9 (#683) | 37.6 (#461) |
| maddux_bruns | RELIEF | 39.2 | 36.6 (#595) | 38.3 (#425) |
| ben_simon | RELIEF | 40.0 | 37.6 (#474) | 39.2 (#332) |
| junseok_shim | RELIEF | 40.2 | 37.6 (#500) | 39.2 (#306) |
| kamden_edge | RELIEF | 35.0 | 37.6 (#504) | 35.9 (#689) |
| quinton_low | RELIEF | 40.0 | 37.6 (#468) | 39.2 (#329) |
| tyler_hampu | RELIEF | 40.0 | 37.6 (#467) | 39.2 (#328) |
| zac_leigh | RELIEF | 40.0 | 37.6 (#488) | 39.2 (#338) |
| jose_paulino | RELIEF | 40.2 | 42.5 (#122) | 40.8 (#188) |

B pulls relievers toward consensus from both sides: the ones the model lifts come down, and
the ones it sinks come back up, because it shrinks the whole relief shift. The artifact lists
the same table for A and C.

# eFV v5 COMBINED re-fit: results for the owner (2026-10-15)

Plain language. Every number is copied from `data/_labs/efv5/efv5_refit_fit.json`; the method,
fixed before the read, and the full tables are in `docs/efv-v2/EFV_V5_REFIT.md` (sections 12 and
13). Development frames only; nothing here is cut by consensus-FV level. No em-dashes.

## The one-line answer

The registered re-fit beats the served eFV v5 COMBINED on the pooled development frames and
passes the owner's rule, and it closes the hitter gap to consensus (from about 0.03 to 0.05
behind to level). The flip is prepared dark; nothing on the board has moved. Against consensus
every reading is still a tie, so the claim stays "ties consensus", now re-derived from the
re-fit's own numbers.

## What the re-fit changed (the audit's fixes, each registered before the read)

- The population translation's league norms are repaired (each count once; the Mexican League
  out of the affiliated population).
- The columns that read nothing on the live board (the rater panel, the report fields, three
  High-A slider cells) are dropped from the fit, so they no longer bend the other weights.
- The arrival (timing) head is fitted on the list-vintage frame, where a row's read date does
  not line up with its outcome. There the level reached carries no weight at all.
- Training rows read on 15 October of each season, with the consensus that stood that day, are
  added (640 hitters, 676 pitchers), so the board's own timing is in the training data. No
  historical consensus was re-ranked in October, so the October 2026 Pipeline re-ranks on the
  live board remain a regime with no training row.
- The head weights are re-derived by the project's own rule (DS-08's ratio) on out-of-fold head
  terms of both development frames, forward chained.
- A registered variant (RT) also ranks the population translation inside each year instead of
  using it raw.

## The weights

| side | served today (V2's constants) | re-fit RT (prepared) | re-fit R |
|---|---|---|---|
| hitters skill | 0.909 | 0.297 (CI95 of the ratio 0.065 to 0.594) | 0.312 (0.089 to 0.595) |
| hitters arrival | 0.203 | 0 (ratio -0.242; -0.542 to +0.036) | 0 (ratio -0.257) |
| pitchers skill | 1.0 | 1.0 (ratio 1.053; 0.534 to 1.918) | 1.0 (ratio 1.105) |
| pitchers arrival | 0.020 | 0 (ratio -0.496; -0.834 to -0.199) | 0 (ratio -0.542) |

The audit asked for the arrival weight to be re-derived rather than set by fiat: re-derived, it
is zero on both sides. The hitter skill weight falls to about a third of the served value; the
leave-one-year-out sensitivity reads 0.43, still half the served value.

## The read (within (side, list year) Spearman)

| frame | n | served v5 | re-fit RT | re-fit R | consensus |
|---|---|---|---|---|---|
| list years 2017 to 2019 | 2,862 | 0.1685 | 0.1683 | 0.1696 | 0.1792 |
| debut cohorts 2017 to 2023 | 830 | 0.3611 | 0.3937 | 0.3869 | 0.3814 |

- Hitters: the re-fit gains +0.029 (list years) and +0.057 (debut cohorts, CI95 +0.008 to
  +0.102) over the served v5, and now sits level with consensus (-0.0035 and +0.0067, both
  intervals across zero) where the served v5 trailed by 0.032 and 0.051.
- Pitchers: level with the served v5 on the debut cohorts (+0.008) and, as read, behind it on
  the list years (-0.031, CI95 -0.053 to -0.008). Restated 2026-10-16 (EFV_PIT_AUDIT_FIXES,
  `data/_labs/efv5/efv5_refit_pit_reread.json`): that loss is a cross-fit effect of the read's
  harness, not of the served head. It sits in one fold (2017, -0.090), where the pool left
  after removing that fold lit the pitcher arrival term on 16 scored rows only (the 2017 debut
  cohort), so the fold's arrival weight came from those 16 rows (ratio 1.89, clipped to 1.0).
  The served pitcher arrival weight is 0. Read at the served weights (skill 1.0, arrival 0),
  the pitcher head is level with the served v5 on the list years (-0.0035, CI95 -0.0107 to
  +0.0037) and with consensus (+0.0085, CI95 -0.0187 to +0.0344); both frames pooled, -0.0009
  against v5 and +0.0107 against consensus (CI95 -0.0127 to +0.0345), a tie. The harness now
  holds such a thin term at 0 (`efv5_refit.CROSSFIT_MIN_NONZERO`, 100 rows); with that guard
  the read gives -0.0037 against v5 on the list years.
- The rule (pooled over both frames, and no frame behind by more than 0.005): RT +0.0072 pooled
  (list years -0.0002, debut cohorts +0.0326), R +0.0066 (+0.0011, +0.0258). Both pass; RT is
  prepared because its pooled gain is the larger, as registered. These figures are the read's
  as run; the pitcher fold 2017 effect above is inside the list-year figure, and they were not
  re-read.

At the board's own timing (each debut-cohort row read on 15 October of the season before, against
the consensus that stood then), the re-fit orders later WAR better than that consensus (+0.036,
CI95 +0.008 to +0.062). That is the advantage of reading a finished season before the lists
re-rank it; it is a development datum the site may not print.

## What the board would do on the flip

- Hitters: mean distance between eFV and consensus falls from 1.66 to 0.56 grades; 586 of 1,055
  move by a grade or more (131 by three or more); 30 of the served top 50 stay top 50.
- Pitchers: the distance rises from 0.89 to 1.26 grades (the pitcher skill head now carries the
  repaired population translation, command, called-plus-swinging strikes and popups at full
  weight); 175 of 941 move by a grade or more, 4 by three or more.
- Nelson Rada: 55.6 (rank 7) today; 46.9 (rank 81) under RT, where the hitter head reduces to the
  hit tool (the penalty search set every added hitter column to zero); 49.6 (rank 30) under R,
  which keeps the population translation (+11.4 percentile points) beside the hit tool.

## Ship or not

Both candidates pass. The flip is prepared dark (`efv5_refit.EFV_V5_REFIT_ON`, with
`efv_w2_popmle.POP_REPAIR_ON`); the owner decides. The claim that would print with it: "Ties
PROSPX consensus on the development frames: within Spearman difference +0.0123 (CI95 -0.012 to
+0.034) on the vintage-matched frame (n 830) and -0.0109 (CI95 -0.031 to +0.010) on list vintages
2017 to 2019 (n 2862); development reads (2026-10-15)."

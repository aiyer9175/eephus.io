# eFV X3, the pooled model: results in plain language

Read once on 2026-10-19. Method fixed in advance: `docs/efv-v2/EFV_X3_POOLED_MODEL.md`
(registered alone at 56d6879d; the numbers are its sections 13 and 14). Artifact:
`data/_labs/efv_x3/efv_x3_pooled.json`. Development frames only; nothing served moved.

## What was tried

You approved (EW3-12, EW3-42) replacing eFV's cell-by-cell drivers with one pooled model built
the way a statistician or economist would build it:

- It starts from consensus and asks only what consensus misses.
- It splits a career into three questions: will he reach the majors, how much will he play once
  there, and how good is he per season of play. The answers multiply into six-season WAR.
- It uses about 24 inputs per side, fixed in advance: the eTools, translated minor league rates,
  club decisions (options, trades, Rule 5), pitch counts per PA, per batter and per inning,
  age, level and draft route, and for pitchers how they are used (starts, innings per outing)
  and a fitted chance of ending in the bullpen.
- It added seven safeguards you asked for: recent call-ups count only the seasons they have
  played; a correction for only seeing the players who made it; consensus trusted less when the
  graders are few or disagree; training rows reweighted to look like today's board; the
  pitcher role path; honest uncertainty bands; and pitchers reported by role.
- Two model types (a shrunken linear model with position and role groups, and a boosted tree
  model held to sensible directions) competed inside every fold, and the better one was picked
  on earlier years only.

## What happened

**It does not beat consensus. It ties, with the point estimate below.**

- Pooled over every development frame (3,062 rows), X3 orders later WAR a little worse than
  PROSPX consensus: -0.020 in within-year rank correlation, with a range of -0.047 to +0.008.
  The read could detect an edge of about 0.023 or larger.
- It also trails the eFV you serve today by 0.023, which by itself fails the rule (the most it
  may trail is 0.005).
- When every input was scrambled at random, the same machinery scored -0.056 to -0.007 against
  consensus. X3's real inputs landed in the middle of that range (13 of the 20 scrambled
  runs did worse, 7 did better), so they added nothing scrambled inputs did not.
- The registered planted check failed: a made-up input correlated 0.20 with the outcome lifted
  X3 only to +0.007, not clear of consensus. So this pipeline, on this many players, cannot
  find an edge that size. The verdict is therefore "ties, unresolved", not "there is nothing
  to find".
- Hitters and pitchers both sit below consensus (hitters -0.018, pitchers -0.022). On the list
  years alone X3 is -0.018; on the debut cohorts alone -0.055.

## Your pitcher and reliever question

You said pitchers, especially relievers, look inflated. Reported by role at the time of the
read (never by grade level):

| Role | Rows | X3 against consensus | X3 against served eFV |
|---|---|---|---|
| Starters | 922 | -0.047 | -0.048 |
| Short starters | 106 | +0.073 | -0.033 |
| Relievers | 322 | +0.045 | +0.017 |

The relief and short-start rows lean X3's way, but every range spans zero and there are too
few of them to tell (an edge under about 0.11 cannot be seen). The role path itself did not
help: scrambling the fitted bullpen chance did slightly better (-0.010 against X3, a tie).

## The safeguards, one by one

Each was checked twice: on made-up data where the right answer is known (all six passed), and
by rerunning X3 with that safeguard switched off.

- Counting only played seasons: no difference (-0.0002).
- Correcting for who made it: the one that helped, +0.006 (range -0.001 to +0.013).
- Trusting consensus less when graders disagree: no difference (-0.001).
- Reweighting toward today's board: today's board looks very unlike the training years (a
  classifier can tell a live row from a training row almost every time, AUC 0.94 to 0.997,
  mostly through more college draftees and lower consensus grades), so the weights lean on a few rows; switching them off
  did slightly better (-0.010, a tie).
- Uncertainty bands: the 80 percent bands held about 80 percent of outcomes (77 percent for
  the rank band, 79 percent for the six-season WAR band). But the full spread is too narrow at
  the top: big careers land above the predicted range twice as often as they should.
- Full-distribution scores (bust, middle, star and reach): X3 is slightly worse than
  consensus on each, and these differences are clear of zero.

## Pitch counts (EW3-41)

The pitch rates entered as candidates with no separate gate and the model's own shrinkage
decided. None was removed outright, but none carried the model: their slopes are small and
change sign across folds and stages (the full table is section 13.6 of the method document).
This matches the earlier tests that refused them.

## What changes

Nothing served. No flag, no dark build, no flip question: under the registered rule a FAIL
stops here. Two development rows (model `efv_x3_pooled`) join the Source Comparison progress
ledger, drawn hollow like every development row.

## What it tells us

The label pool is the limit, not the model. A careful pooled model with every input the program
has built ties consensus on development, and the planted check shows the pool is too small for
this pipeline to see a modest edge even when one is planted. The forward read on the 2027
season (the registered confirmation clause) only matters for a model that passes here; X3 did
not.

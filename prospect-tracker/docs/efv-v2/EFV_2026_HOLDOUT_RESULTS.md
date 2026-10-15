# eFV on the 2026 season: results for the owner (2026-10-15)

Plain language. Every number is copied from `data/efv_2026_holdout.json`; the method, the
pass rule and the full tables are in `docs/efv-v2/EFV_2026_HOLDOUT.md` (registered and
committed before any number was read). No em-dashes. Nothing here is cut by consensus-FV
cell.

## The one-line answer

On the 2026 season, the served eFV ordered the preseason-2026 prospects' 2026 WAR a little
better than PROSPX consensus (Spearman +0.012), but the difference is inside the noise: the
registered rule needed the one-sided 95 percent lower bound above zero and it is -0.007
(player-clustered) and -0.007 (club-clustered). The verdict is **ties**. eFV does not beat
consensus on the 2026 holdout; nothing on the site moves and the copy keeps "ties consensus".

## What was scored

- **Who**: every prospect on a preseason 2026 list, with every list read as it stood on the
  2026 opening day (2026-03-25): 1,208 players (590 hitters, 618 pitchers). 167 of them
  (78 hitters, 89 pitchers) reached the majors in the 2026 regular season.
- **Against what**: 2026 regular-season fWAR from the frozen label (0 for anyone who did not
  reach the majors).
- **Who was graded**: the served eFV (v5 COMBINED), the earlier eFV V2 and eFV v1, PROSPX
  consensus, MLB Pipeline and FanGraphs. Each eFV version was rebuilt so that it knew nothing
  dated after opening day: its training labels stop at the 2025 season and its inputs (lists,
  minor league lines through 2025, injuries, scouting grades) are all dated on or before
  2026-03-25.

## The table (within-side Spearman with 2026 WAR, size-weighted over hitters and pitchers)

| grader | hitters | pitchers | both |
|---|---|---|---|
| eFV v5 COMBINED (served) | 0.180 | 0.085 | 0.131 |
| eFV V2 | 0.173 | 0.073 | 0.122 |
| eFV v1 | 0.168 | 0.078 | 0.122 |
| PROSPX consensus | 0.167 | 0.073 | 0.119 |
| MLB Pipeline (its own 585 players) | 0.236 | 0.057 | 0.156 |
| FanGraphs (its own 1,108 players) | 0.200 | 0.099 | 0.148 |

The served eFV minus consensus, same 1,208 players: +0.0121 (95 percent interval -0.011 to
+0.035). Every eFV version is a hair above consensus and none is clear of it.

## What the read says, in plain words

- **eFV's real edge on 2026 is arrival, not value.** On who reached the majors in 2026 the
  served eFV beats consensus clearly (AUC 0.726 against 0.677, +0.049, lower bounds +0.034
  and +0.033). That edge is almost all hitters (+0.095); eFV V2 shows the same hitter edge
  (+0.100), so it most likely comes from the hitter timing head (the level a player has
  reached). The registration called this read tilted toward a model with
  a timing head and never value, so it does not count toward the verdict.
- **Among the best-known prospects eFV trails.** On the 570 players both Pipeline and
  FanGraphs graded, the served eFV reads -0.013 against consensus (interval -0.047 to
  +0.020). Its small overall lead comes from the less-covered part of the lists.
- **v5 COMBINED improved on V2 here.** +0.0093 over V2 (lower bounds -0.0018 and -0.0007):
  close to resolvable, on both sides, which is the opposite of its hitter result on the
  development frames. One season; not a claim.
- **FanGraphs beat the consensus blend on its own players** (+0.028, lower bounds +0.005 and
  +0.011, both above zero). MLB Pipeline trailed it (-0.025, interval spans zero). This is a
  single season and a source comparison the registration did not make a rule for; it is a
  question below, not a change.
- **Among the players who did reach the majors, eFV ordered their WAR rate worse.** Per 600
  PA or 150 IP, on the debutants both sources graded (131), the served eFV reads -0.068
  against consensus (interval -0.138 to -0.003). Descriptive only, small sample.
- **The debut classes (secondary).** On the 2025 debut class's 2026 season and the 2026
  class's first season (363 players), the served eFV leads consensus by +0.032 (lower bounds
  +0.0003 and +0.0063). Most of it is the 2025 class (+0.069). This frame only includes players
  who reached the majors, so it is read beside the main result and adjudicates nothing.
- **MiLB2026 was not read.** The 2026 minor league production composite belongs to the
  surrogate gate, whose guard refuses a 2026 read until that gate is registered and its look
  is recorded. It was not read around the guard.

## What changes

- Nothing served: the board, grades, dollars, odds and the "ties consensus" claim are
  untouched.
- One row was added to the Source Comparison ledger (frame "2026 holdout", verdict "ties"),
  shown in the table and never on the chart.
- The 2026 frame is now spent: no later model will ever be claimed on it. The next task
  (EFV_2026_FOLD_TRAINING) folds the 2025 and 2026 classes into training, and any later
  "beats consensus" claim waits for the 2027 season.

## Questions recorded for the owner (defaults applied, nothing stopped)

1. **MiLB2026.** Default: not read (the surrogate guard refused). Alternatives: (b) record an
   owner waiver in `docs/efv-v2/SURROGATE_2026_GATE.md` and read the composite once as a
   descriptive column of this holdout; (c) leave it to the surrogate gate's own schedule.
2. **The arrival result in the copy.** Default: no copy change (the read is tilted and the
   pass rule is on value). Alternatives: (b) one arrival-only sentence on Source Comparison
   ("on the 2026 holdout eFV picked who reached the majors better than consensus; on 2026
   WAR it ties"), labelled tilted; (c) fold it into the EFV_BEAT_TILTED_LABELS registration
   (EW3-11 path 3), which already limits copy to arrival.
3. **FanGraphs beat the consensus blend on 2026.** Default: nothing (one season, no rule
   registered for a source comparison). Alternatives: (b) register a consensus source-weight
   test on the development frames; (c) add FanGraphs alone as a fourth comparison line in the
   next registered read.

# RC-6 output diff: per-season OPS+ / ERA- shrink (for owner sign-off)

**Change.** The per-season career rows (`current_season_statlines` in debuts.json / inactive.json) computed `ops_plus_level` / `era_minus_level` RAW, while the headline statline already shrinks them (empirical-Bayes toward the level mean, K_AB=170 AB / K_IP=50 IP). The per-season rows now apply the SAME shrink, so a small-sample line no longer reads an extreme and the two surfaces stop disagreeing.

**Method.** Numbers computed directly from the committed debuts.json + inactive.json payloads (level mean backed out of each row's raw stat and its old index), no pipeline run.

## ops_plus_level
- rows: 1053; changed: 1017; unchanged: 36
- median abs change: 10; 90th-pct abs change: 42; max abs change: 239
- **Qualified rows (AB >= 130, n=406): median abs change 5, max 29** - the shrink barely touches real samples; the big moves are all tiny-sample cameos.
- Worst small-sample blowups tamed (AB, old -> new):
  - Lars Nootbaar (AB=3): 343 -> 104
  - Josh Smith (AB=4): 280 -> 104
  - Joshua Kuroda-Grauer (AB=4): 264 -> 104
  - Denzel Clarke (AB=6): 261 -> 105
  - Wyatt Langford (AB=5): 232 -> 104

## era_minus_level
- rows: 1074; changed: 1061; unchanged: 13
- median abs change: 24; 90th-pct abs change: 102; max abs change: 1467
- **Qualified rows (IP >= 40, n=190): median abs change 10, max 43** - real samples move modestly; extremes are cameos.
- Worst small-sample blowups tamed (IP, old -> new):
  - Josh White (IP=0.2): 1573 -> 106
  - Jackson Rutledge (IP=1.1): 1101 -> 122
  - Quinn Priester (IP=1.1): 1101 -> 122
  - Ty Adcock (IP=0.1): 1095 -> 102
  - Jorge Gonzalez (IP=2.1): 984 -> 136

## Assessment
The change is a strict improvement in honesty and self-consistency: a 3-AB MLB cameo no longer posts OPS+ 343 on the per-season breakdown while the headline (correctly) reads ~104. Qualified full-workload rows move only slightly (medians 5 / 10), so leaderboard-relevant lines are effectively unchanged. The shrink constants are the already-shipped K_AB=170 / K_IP=50; this fix removes an inconsistency rather than introducing a new calibration. A lighter per-season display shrink, if ever wanted, is a separate calibration decision on both surfaces.

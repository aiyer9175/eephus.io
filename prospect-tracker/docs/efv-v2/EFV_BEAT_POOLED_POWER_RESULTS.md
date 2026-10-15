# eFV against consensus, pooled for power: results for the owner (2026-10-15)

Plain language. Every number is copied from `data/_labs/efv5/efv_beat_pooled_power.json`; the
method, fixed and committed alone before any number (commit 4eee1808), and the full tables are
in `docs/efv-v2/EFV_BEAT_POOLED_POWER.md`. No em-dashes. Nothing here is cut by consensus-FV
cell.

## The one-line answer

Pooling every development frame does not show eFV beating consensus. The served eFV (v5
COMBINED) reads -0.010 against PROSPX consensus with a one-sided 95 percent lower bound of
-0.034, and the pooled read is only sensitive enough to see an edge of about 0.023 or larger.
The verdict is **ties**. Nothing on the site moves and the copy keeps "ties consensus".

## What was asked

The single-frame reads were each about +/-0.02 wide, so a real edge of +0.005 to +0.01 would
look like a tie on any one frame. The idea was to pool the list years 2017 to 2019 and the
debut classes 2017 to 2023 into one test and narrow the interval.

## Why pooling did not help much

596 of the 830 players in the debut-class frame are already in the list-year frame. Counting a
player twice would overstate the evidence, so the registered rule kept his list-year rows and
dropped his debut-class row. That left 234 new rows, and only 200 of them sit in groups big
enough to score (the 2022 and 2023 classes). The pool grew from 2,862 to 3,062 scored rows and
the smallest detectable edge fell only from 0.025 to 0.023. Even pooled, an edge of +0.005 to
+0.01 is several times too small to resolve on these frames.

## The table (development frames pooled; within-year Spearman against later WAR)

| comparison | hitters | pitchers | both | lower bound (both) |
|---|---|---|---|---|
| eFV v5 COMBINED minus consensus | -0.033 | +0.013 | -0.010 | -0.034 |
| eFV V2 minus consensus | -0.022 | -0.002 | -0.012 | -0.029 |
| eFV v1 minus consensus | -0.002 | +0.004 | +0.001 | -0.018 |
| v5 COMBINED minus V2 | -0.011 | +0.015 | +0.002 | -0.013 |

Every pooled interval spans zero. The club-clustered check agrees (lower bound -0.031).

## The corroboration reads

- **The spent frames (list years 2020 and 2021, the 2025 debut class), read once more:**
  v5 COMBINED minus consensus +0.0001 (lower bound -0.024). A tie.
- **The 2026 holdout (quoted, not recomputed):** +0.012 (lower bound -0.007). A tie.

## What the read does show (development only, not a claim)

- Pitchers are where v5 COMBINED adds something over V2: +0.015 pooled on the development
  frames, with a lower bound just above zero (+0.001). That is the frame the penalty was chosen
  on, and on the spent frames the same comparison reads -0.008, so it is not a result.
- Hitters are where v5 COMBINED loses ground to consensus (-0.033), as the v5 COMBINED read
  already showed on each frame.

## What the site may print

Nothing changes. The copy keeps "ties consensus". If a sentence is wanted on Source
Comparison, the registered one is: "Pooled over every development frame (3,062 rows), eFV v5
COMBINED minus PROSPX consensus reads -0.010 (one-sided 95 percent lower bound -0.034); the
pooled read could detect an edge of 0.023 or larger, and it does not find one."

## Questions recorded for the owner (defaults applied, nothing stopped)

1. **The pooled path's next step.** Default: close the pooled-power path on the current frames
   (the development pool is spent for this question and cannot resolve the hoped-for edge).
   Alternatives: (b) register a pooled read that adds the next unread frames when their data
   exists (the 2027 list year's three-season label, the 2024 debut class once it resolves),
   which waits for data; (c) a pooled estimand over development and spent frames together,
   which would need a new registration and could never be a clean claim because the spent
   frames have been read many times.
2. **The pitcher edge over V2 (+0.015, lower bound +0.001 on the development frames, -0.008 on
   the spent frames).** Default: nothing. Alternative: (b) register a pitcher-only v5 COMBINED
   versus V2 confirmation on the next unread frame.
3. **The club-clustered check.** 1,328 of 3,096 rows have no club on a board point at or before
   the read (early list years), so they share one `UNK` cluster. Default: as registered (it did
   not decide anything). Alternative: (b) fill the club from the player's later org for the
   sensitivity only.

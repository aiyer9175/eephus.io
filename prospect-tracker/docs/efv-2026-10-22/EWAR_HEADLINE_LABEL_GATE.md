# eWAR headline label check: eFV's label from published fWAR to the headline eWAR (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EFV_LABEL_HEADLINE_EWAR_CHECK (owner answer EWLE-Q2
"Headline eWAR, after a check", 2026-10-22). This document is committed ALONE, before any number
of its estimands is computed: no headline label value has been frozen, no guard statistic, no twin
and no blast radius figure exists at this commit. Nothing in this commit changes a model, an
exporter, a flag or a served artifact. Part 9 is filled in afterwards and nothing above part 9 may
be edited once anything is written below it; a change is a dated amendment under part 9, committed
alone. Its pin test is `test_ewar_headline_label_registration.py`.

- The predecessor, whose guard this one re-reads: `docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md`
  (the core eWAR label epoch). Its guard did not hold on 2026-10-22 (part 11 there), and its owner
  question EWLE-Q2 was answered with this check.
- eWAR itself: `docs/ebr-2026-09-30/EBR_GATE.md` amendment 11.10 (`data/ewar_v3.json`, the frozen
  fWAR vintage plus named departures), the skill look of part 12.2 (no candidate part admitted,
  2026-10-19), and the eABS part by owner override EW3-32 (EBR_GATE.md 11.10.2,
  `docs/eabs-2026-10-15/EABS_GATE.md` 9.2).
- The fWAR label epoch, whose clauses (a) to (l) the core gate carries and this gate carries through
  it: `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`.

## 0. What kind of decision this is

**The label basis is an OWNER BASIS DECISION, and one registered condition stands in front of it:
the circularity guard of part 4, the core gate's guard re-read on the headline label.** Choosing
which WAR eFV trains on is not a claim that the new series makes eFV or any priced number more
accurate, and no clause here measures that claim. Clause (l) of the fWAR label epoch binds every
part of this document: copy may never claim an accuracy gain from a basis change. Movement is not
accuracy.

## 1. Decision record

1. **EW3-17 (owner, 2026-10-15):** "Yeah we can switch the eFV label." **EW3-20 (owner,
   2026-10-15):** eWAR is published as the headline (predictive) eWAR and eWAR realized; the label is
   the predictive series, with the realized series read as a registered sensitivity.
2. **The core label failed its guard** (core gate part 11, the 2026-10-22 entry): G-1 gap -0.0285,
   5th percentile -0.0386 against the -0.02 margin; G-2 runs allowed, run differential and wins not
   NON-INFERIOR. Nothing switched.
3. **EWLE-Q2 (owner, 2026-10-22), as recorded in DECISIONS_FOR_OWNER.md:** "'Headline eWAR, after a
   check': EFV_LABEL_HEADLINE_EWAR_CHECK registers and runs the check for fWAR + ABS as eFV's label;
   switch only on pass."
4. **The task specification:** register ALONE a check of the HEADLINE eWAR label (published fWAR
   plus the ABS part from 2026, as served by eWAR v3) as eFV's training label, on the same frames and
   legs as the core check (next-season published fWAR rank, the random-change comparator of the same
   size, the -0.02 limit); run once; switch eFV's label only if it passes, with the fingerprint's
   label= term and `BOARD_RANK_BASIS_EPOCH` bumped and restamped together and `data/xfv_history.json`
   regenerated; otherwise eFV keeps fWAR and the row records the failure.

## 2. The label

For season s and player p, with war the frozen fWAR vintage's value (`data/fwar_vintage.json`) and
dh the headline departure of `data/ewar_v3.json` on each side, as frozen by part 3:

```
label(p, s)    = war_hit(p, s) + dh_bat(p, s) + war_pit(p, s) + dh_pit(p, s)     (the headline eWAR)
realized(p, s) = war_hit(p, s) + dr_bat(p, s) + war_pit(p, s) + dr_pit(p, s)     (eWAR realized)
```

- **The label is the HEADLINE eWAR: published fWAR plus the eABS part from 2026.** It is the series
  the site displays as plain "eWAR" (`war_source.DISPLAY_PROVIDER` 'ewar_v3', headline series), frozen
  so that a later rebuild of `data/ewar_v3.json` cannot move a label value without a new vintage id
  (the EW3-19 precedent).
- **The realized sensitivity** adds the realized departures dr (R2, the realized pitching basis, from
  2016, plus the eABS part from 2026). It trains nothing and anchors nothing, and every report says so
  beside it.
- **The transform contract is the eWAR v3 transform's.** The label moves values, never the season set:
  a season the frozen fWAR vintage did not serve for a player (the row's fwar_coverage fallback years)
  keeps its stored value, exactly as `war_source.row_on_provider(row, 'ewar_v3')` treats it. Values
  are rounded to 2 decimals like the fwar series.
- **Where the label equals published fWAR (a structural fact, counted at registration without any
  statistic).** `data/ewar_v3.json` (sha256 `40ea0196102beb793e2aeae1d6503d160acbec92c6eebf6e583fae8bcc81fe69`,
  generated 2026-10-22T02:17:24+00:00, on fWAR vintage `2026-10-02-a020cf64844a`) lists headline
  departures on 1,470 player-seasons, every one of them in 2026 (662 hitting cells and 868 pitching
  cells), and none in 2000 to 2025: the eABS part's first season is 2026 and the skill look admitted no
  other part. So the label is published fWAR in every season before 2026.

## 3. The frozen label vintage and the switch

- **The file.** `data/ewar_headline_label.json`, written ONCE by
  `python tools/build_ewar_headline_label.py --write`. It stores, per season, the headline departures
  (`bat`, `pit`) and the realized departures (`real_bat`, `real_pit`) of `data/ewar_v3.json` (6
  decimals), with the fWAR vintage id, the sha256 of `data/ewar_v3.json` and a `content_sha256` over
  the departures. Its `vintage_id` is `ewar-headline-<fWAR vintage id>-<first 12 hex of content_sha256>`.
- **Frozen.** The builder refuses to overwrite a file whose content differs; a new label value needs a
  new vintage id through a dated amendment here.
- **Identities checked at build (any miss refuses and nothing is written).** (1) `data/ewar_v3.json`
  is built on the frozen fWAR vintage the site serves (same vintage id); (2) every stored departure
  equals `ewar_v3.departures` on its series within 1e-9 wins; (3) per season and side, the headline
  departures sum to zero within 1e-6 wins (eWAR v3's zero-sum rule); (4) no headline departure falls
  in a season before 2026.
- **Off the webroot.** The file is listed in `deploy/data_exclude.txt`, like the core label vintage.
- **The switch.** `war_source.EFV_LABEL_EWAR_HEADLINE` defaults to False, and
  `war_source.EFV_LABEL_PROVIDER` reads `"ewar_headline"` only when it is True (else
  `DEFAULT_PROVIDER`). It is the core gate's switch pattern (`LABEL_EWAR_CORE`), scoped to eFV.
- **Scope: eFV's label, and only eFV's label.** Under the switch, the series `efv_dataset` sums for the
  first-6-season label (the training target and the resolved label) and the series
  `efv_labels.war_seasons_table` serves to the development frames are each stored fwar row
  re-expressed through `ewar_headline_label.label_series`. The career_war table is NOT rebased and
  `war_source.DEFAULT_PROVIDER` stays `"fwar"`: every other label reader (the projections corpus, the
  FA corpus, the arbitration spine, WAG, the empirical anchors, star odds, the draft slot curve,
  surplus and the registered gate tools whose documents name fWAR) stays on published fWAR, and every
  display door prints what it prints today.
- **Registered reads that froze fWAR.** A registered eFV read whose tool refuses a label provider other
  than `"fwar"` keeps refusing under the switch: its look ran on fWAR, and re-running it on the new
  label is its own registration (core gate part 6, R5, carried).
- **The fingerprint and the epoch.** `storage.board_basis_fingerprint`'s label term reads
  `ewar_headline@<vintage id>` under the switch. The flip commit bumps `storage.BOARD_RANK_BASIS_EPOCH`
  and restamps `BOARD_BASIS_FINGERPRINT` together. Under the owner's flip rule (AG4-Q, 2026-10-22) the
  flip commit carries only the flag, the registry, the glossary, copy and tests; `data/xfv_history.json`
  (`efv_score.score_history`) and every other regeneration are run by the integrator on the main tree
  and named in the task's integration notes.
- **Registry.** A row `ewar_headline_label` (status provisional, `measurement_only`, eval artifact the
  guard record of part 4), claiming no accuracy.

## 4. The circularity guard

The core gate's part 4, read ONCE on the headline label after the vintage of part 3 is frozen, with
the same pairs, statistic, seeds, B, margin, comparator and rules. Only the series changes.

### 4.1 G-1, the player leg: next-season published fWAR

- **Pairs.** Hitting-group rows of the fWAR vintage with 300 or more plate appearances in Y and in Y + 1
  and a non-null war in both seasons, Y in 2011 to 2018 and 2021 to 2024 (every pair touching 2020 is
  excluded; 2025 is left out as the eWAR v3 holdout's).
- **Series.** a = the label's hitting value, war_i(Y) + dh_bat_i(Y); b = published fWAR war_i(Y).
  **Target:** published fWAR war_i(Y + 1), hitting group.
- **Statistic.** S(x) = the pair-count-weighted mean over predictor seasons of the within-season
  Spearman correlation of x with the target (average ranks for ties). **Gap = S(a) - S(b).**
- **Interval.** Player-clustered bootstrap, B 2,000, seed 20261022; lower = the 5th percentile of the
  drawn gaps, sd their standard deviation, MDE95 = 1.645 x sd.
- **Rule. NON-INFERIOR when lower > -0.02.**
- **The random-change comparator (the permuted twin).** Within each predictor season the label's
  hitting departures are permuted among that season's hitting rows (seasons ascending, rows in
  ascending mlbam, one `numpy.random.default_rng(20261022)`), twin = war + permuted departure, scored on
  the same draws. It decides nothing; when it is also NON-INFERIOR beside a NON-INFERIOR G-1, the record
  states that G-1 cannot separate the label's change from a random change of the same size.

### 4.2 G-2, the club leg: next-season runs and wins (the eBR gate's team guard 11.2.4, verbatim)

- `tools/swar_targets.team_guard` and `roster_matrix`, unchanged; frame = published fWAR on both sides;
  part = the label on the hitting side and on the pitching side (war + dh on each); ref = bWAR,
  reported beside. Outcomes of Y + 1: runs scored (hitting sum), runs allowed (hitting sum, sign
  reversed), run differential (total) and wins (total), StatsAPI standings.
- **Rule, as registered in 11.2.4.** dT = r(part sum, outcome) - r(frame sum, outcome); a player- and
  a franchise-clustered bootstrap, B 2,000 each, seed 20261024; **NON-INFERIOR when dT - 1.645 sd > -0.02
  under both bootstraps for every carried outcome**; a half-width above 0.02 is underpowered and not
  NON-INFERIOR.

### 4.3 Secondary legs (descriptive: each decides nothing)

1. G-1 on the rate (war per 600 PA). 2. G-1 at a 200 PA floor. 3. The realized sensitivity on
pitchers with 50 or more innings in Y and Y + 1, Y in 2016 to 2018 and 2021 to 2024 (war + dr_pit
against war). 4. G-1 on pairs whose Y row carries an absolute framing term above 0.05 runs.

### 4.4 The decision

- **THE GUARD HOLDS when G-1 and G-2 are both NON-INFERIOR.** The switch then flips in this task, in
  one flag commit (part 3), and `data/xfv_history.json` is regenerated by the integrator.
- **Otherwise the switch does not flip.** eFV keeps published fWAR, the registry row records the
  failure, and nothing served moves.
- **Before the look:** the reporting path is dry-run on fixtures with nulls (the identity series must
  read gap 0 and hold; a planted noise series must not hold), in `test_ewar_headline_label_guard.py`.
  The look's stdout and stderr are teed to the task's output directory before anything else runs. On
  any exception after scoring began: STOP, no re-run, `OWNER_QUESTION.md`.
- **The record.** `docs/efv-2026-10-22/ewar_headline_label_guard.json` (tracked, not served), produced by
  `python tools/ewar_headline_label_guard.py --look`, pinned by a result test.

### 4.5 What this guard can and cannot see (stated before the look)

- **It is an identity check, by construction.** Part 2 counts no headline departure in any predictor
  season (2011 to 2024) or target season (2012 to 2025). So on every G-1 pair a equals b, every drawn
  gap is 0 and the twin equals both; on G-2 the part equals the frame. The registered rule therefore
  reads NON-INFERIOR with gap 0 and sd 0, the identity reading the eWAR v3 build already records for
  its RPW form's team guard (`tools/build_ewar_v3.py`, 2026-10-21; `data/ewar_v3.json` meta
  `rpw.guard`: "identity: the headline series carries no departure on predictor seasons 2021 to
  2024").
- **What a pass establishes, and what it does not.** It establishes that the label is published fWAR
  wherever an outside next-season target exists. It says nothing about the eABS part, the one part of
  the label the site produces: no 2026 label value has a next-season target yet.
- **The structural check.** The record carries the count of predictor-season pairs with a departure
  (G-1 `n_pairs_departing`). If the look reads anything other than a G-1 gap of exactly 0, a twin gap
  of exactly 0, `n_pairs_departing` 0 and a G-2 dT of exactly 0 on every outcome, the structure stated
  here is wrong: STOP, nothing flips, `OWNER_QUESTION.md`.
- **The eABS part's own read, registered here and NOT run by this task (EWHL-R1).** The first pair
  that can see the eABS part is Y = 2026 against Y + 1 = 2027. When FanGraphs' final 2027 values and the
  2027 standings exist (not before the 2027 regular season ends), G-1 and G-2 of parts 4.1 and 4.2 are
  read once with Y = 2026 alone, against the same margin. If either leg is not NON-INFERIOR, the owner
  is asked whether eFV's label reverts to published fWAR; no default is taken. The data does not exist
  today, so this read cannot run now.

## 5. The label-only blast radius (descriptive, before any fit)

Measured once after the vintage is frozen, on labels alone, from the stored career_war table: the rows
and seasons whose eFV label value moves under the switch, by season, with the mean, standard deviation
and largest absolute change per moved season and per player's summed label seasons. No grade,
consensus FV, model output or FV cell is read, and no row is split by cohort or level. Recorded in part
9 beside the guard.

## 6. Owner questions

**EWHL-Q1 (recorded after the look, not blocking; the default is applied).** If the guard holds by
identity (part 4.5), is the switch made now? (a) Yes, now (the default: the specification's rule, the
owner's answer to EWLE-Q2), with EWHL-R1 able to revert it after 2027; (b) hold eFV on published fWAR
until EWHL-R1 reads the eABS part; (c) widen the switch to the site-wide label (projections, WAG,
surplus, anchors) at a main-tree epoch run.

## 7. What stays out

- No dark betting column is related to any outcome or price, and betting reads no WAR.
- No realized MLB statistic, bust, debut or graduation rate is computed by consensus-FV cell
  (`docs/PROSPECT_ANCHOR_GATE.md`); nothing here reads a grade.
- The reserved eFV frames R-LV and R-VM are never scored.
- `war_source.LABEL_EWAR_CORE` stays False; the core label vintage and its provider stay on record and
  dark.

## 8. Cross-references

- The core gate: `docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md` (parts 4, 6 R5, 7 and 11).
- The guard implementation it reuses: `tools/ewar_core_label_guard.py` (functions `g1`, `g2`,
  `twin_departures`, `gap_cell`).
- The standard: `docs/EFV_GATE_STANDARD.md` (the 0.02 margin).

## 9. Results

**EMPTY AT REGISTRATION.**

No label value, guard statistic, twin, secondary leg or blast-radius number has been computed at this
commit. The first entry here is dated, names the commit that produced it, and states what was met when
it ran. Clause (l) binds this part.

### Amendment 9.1 (2026-10-22, before the vintage is frozen and before any guard statistic): identity 3's tolerance

Part 3's identity 3 reads "per season and side, the headline departures sum to zero within 1e-6 wins".
`data/ewar_v3.json` stores each departure at 6 decimals, so the stored departures of a season carry
rounding residue: in 2026 they sum to -0.000001 wins on the hitting side (662 cells) and +0.000008 on
the pitching side (868 cells), while the artifact's own pre-rounding check
(`checks["2026"].sum_departure_wins`, `dh_bat` and `dh_pit`) reads under 1e-14. Read with the registered
1e-6, the builder would refuse a correct file on rounding alone. Identity 3 is therefore read as two
conditions, both required: (a) the artifact's own pre-rounding sum `checks[s].sum_departure_wins.dh_<side>`
is within 1e-9 wins of zero, and (b) the stored 6-decimal departures sum to zero within the rounding
bound n x 0.5e-6 wins, n the season's listed cells on that side (the convention of eWAR v3's own
`r2_rounding_bound`). Nothing else in parts 0 to 8 changes. This amendment is committed alone, found by
reading the input's sums before the build, with no label value frozen and no guard statistic computed.

### 2026-10-22: the guard HOLDS, by identity, as part 4.5 stated; the switch is cleared

This entry records the one read of part 4 and the label-only blast radius of part 5. Clause (l)
binds it: it reports what was measured and draws no conclusion about eFV's accuracy.

**What ran, and on what.** `python -u tools/ewar_headline_label_guard.py --look`, once, at HEAD
`2f6ce6c6` (2026-10-22 18:47:55 to 18:48:48 UTC), rc 0, after the fixture dry run passed
(`test_ewar_headline_label_guard.py`: the identity series held with gap 0 and matched the structure;
planted hitting noise failed G-1; planted pitching noise alone failed G-2). Inputs: the frozen label
vintage `ewar-headline-2026-10-02-a020cf64844a-8b30fccf933d` (frozen at `2f6ce6c6`, file sha256
`6b6f2a8f971fb505a033fd819d20bd39f91a4c520262786f2b9b0bd1a09fa9c4`, copied from `data/ewar_v3.json`
sha256 `40ea0196...`) on the frozen fWAR vintage `2026-10-02-a020cf64844a`; the Baseball-Reference stint
caches and StatsAPI standings the core guard read. The record is
`docs/efv-2026-10-22/ewar_headline_label_guard.json` (sha256
`5292ca859eda5ce69e9f0cef54a3a304ebcf4ed560d15ea38d1a999837bc5aae`, unedited since the look wrote it);
stdout and stderr were teed to the task's output directory before anything else ran.

**G-1, the player leg: NON-INFERIOR, by identity.** 2,416 hitter pairs (713 players, 12 predictor
seasons), 0 of them carrying a departure. Pair-weighted within-season Spearman with next-season
published fWAR: label 0.4788, published fWAR 0.4788. Gap 0, 5th percentile 0, sd 0 (B 2,000, seed
20261022). The permuted twin reads gap 0 as well, so G-1 cannot separate the label's change from a
random change of the same size: on these pairs both changes are zero.

**G-2, the club leg (11.2.4 verbatim, the label on both sides): NON-INFERIOR, by identity.** 360
club-seasons, 0 departing cells. Every outcome reads dT 0 with sd 0 under both bootstraps and no leg is
underpowered: runs scored r 0.4524, runs allowed 0.5250, run differential 0.7312, wins 0.7146, each
equal for the label and published fWAR (bWAR beside: 0.4395, 0.4540, 0.6774, 0.6592).

**Part 4.5's structure: as registered** (G-1 gap 0, twin gap 0, no departing pair, every G-2 dT 0). No
STOP.

**THE GUARD HOLDS (part 4.4). The switch is cleared** and flips in this task's flag commit. What the
pass establishes, as part 4.5 said before the look: the headline label is published fWAR wherever an
outside next-season target exists. It says nothing about the eABS part; EWHL-R1 is the first read that
can, once the 2027 season's data exists.

**Secondary legs (part 4.3; each decides nothing).**

| Leg | n | S label | S fWAR | gap | 5th pct |
| --- | --- | --- | --- | --- | --- |
| G-1 on the rate (per 600 PA) | 2,416 | 0.4460 | 0.4460 | 0 | 0 |
| G-1 at a 200 PA floor | 3,217 | 0.4650 | 0.4650 | 0 | 0 |
| realized sensitivity, pitchers 50+ IP (Y 2016 to 2018, 2021 to 2024) | 1,536 | 0.3430 | 0.4505 | -0.1075 | -0.1311 |
| G-1 on pairs with a framing term above 0.05 runs | 254 | 0.4853 | 0.4853 | 0 | 0 |

The realized row is the R2 departure alone in those seasons (eABS starts in 2026), so it reproduces the
core gate's realized-core pitcher leg exactly (-0.1075, n 1,536): the realized series is a sensitivity
and trains nothing. Its target is published fWAR, whose pitching is FIP-based; it is reported, not read.

**The label-only blast radius (part 5).** `python tools/ewar_headline_label_blast.py --write`, once,
record `docs/efv-2026-10-22/ewar_headline_label_blast.json` (sha256
`cc3ecb51f5e876dfdc9643ee9c2fa0781fa4ac7afaa4cf7c3840b5b83094b99c`), on the stored career_war table
(2,698 rows: 2,686 fwar, 6 ewar_v2, 6 bbref; the worktree's copy, whose career_war payloads hash equal
to the main tree's). Under the switch 1,029 rows move, every move in 2026: mean -0.0011 WAR, sd 0.0718,
largest 0.51; 112 rows move 0.1 WAR or more and 1 row 0.5 or more. No season before 2026 moves.

**Beside part 5 (descriptive, labels only, nothing persisted).** `efv_dataset.build_matrix` was run in
memory on both sides with the switch off and on, and only the label columns were compared: hitters,
245 of 2,012 rows move (`target_resolved` mean -0.0048, sd 0.0945, largest 0.51; `target_censored`,
the censoring-scaled label, mean -0.0124, sd 0.2048, largest 1.53); pitchers, 300 of 2,158 rows
(`target_resolved` mean +0.0004, sd 0.0586, largest 0.21; `target_censored` mean +0.0011, sd 0.1207,
largest 0.48). Every other column is identical. No grade or FV value was read, and no row was split by
cohort or level.

**Owner question EWHL-Q1 (part 6), the default applied:** (a) the switch is made now, with EWHL-R1 able
to revert it after 2027.

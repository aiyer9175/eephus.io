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

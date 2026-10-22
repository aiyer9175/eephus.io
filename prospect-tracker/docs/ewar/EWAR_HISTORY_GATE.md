# eWAR history: every season the data supports, stamped with its parts (ewar_history_v1)

Task EWAR_BACKGRADE_HISTORY (owner decision EW3-17, 2026-10-15, verbatim "We should be able to do
this by backgrading previous seasons (which we should show in the MLB Stats section, no reason to
not have stats going back as far as we can with our metrics)"; owner decision EW3-20, the two
numbers). This document is committed ALONE, before any number of its estimand is computed. It
fixes the seasons, the parts, the stamp rule, the core and full series, the agreement check, what
is served and what is never served. A change to any of them after the first number is a dated
amendment under part 9, never an edit. Its pin test is `test_ewar_history_registration.py`.

## 0. What it decides

- **The series is eWAR as registered, nothing new.** eWAR (`docs/ebr-2026-09-30/EBR_GATE.md`
  amendment 11.10) is the frozen published fWAR vintage (`data/fwar_vintage.json`) plus the named,
  zero-sum departures of `data/ewar_v3.json`: the ABS part in the headline eWAR from 2026, and the
  realized pitching basis R2 in eWAR realized from 2016. No look admitted any other part. This task
  admits no part, changes no part, refits nothing and moves no constant. It decides only HOW FAR
  BACK the displayed eWAR is shown, and WHAT each season is stamped as carrying.
- **Nothing that is served today moves.** Every eWAR number displayed on the commit date (the MLB
  Stats boards 2011 to 2026, the player pages' season lines from 2014) is the headline series, and
  it stays the headline series. The changes are additive: seasons 2000 to 2010 on the MLB Stats
  eWAR board's year selector, player pages' season lines from 2000, the league averages' eWAR rows
  from 2000, and a component stamp beside each.
- **Not a label decision.** Switching eFV's label to eWAR is task EFV_LABEL_EPOCH_EWAR, under its
  own registration. This document gives that task a per-season record of what eWAR carries; it
  computes no label, scores nothing on a label and relates no eWAR number to any later outcome.

## 1. The seasons, and where they stop

- **2000 to 2026**, every season of the frozen vintage whose two groups are frozen
  (`fwar_vintage.fwar_seasons`). `ewar_history.FIRST_SEASON` is `fwar_vintage.FIRST_ACCEPTED_SEASON`.
- **Why 2000.** The vintage's first accepted season is 2000 (owner answer O4 of the fWAR label
  epoch: "Cache 2000-2010"), and the vintage is never refetched (`fwar_vintage.py`; the epoch
  gate). A season before 2000 would need either a new vintage id that adds those seasons, which
  re-fingerprints every label that names the vintage, or a different frame (Baseball-Reference's),
  which would not be eWAR. Neither is done here; the question goes to the owner.
- **The live season.** 2026 is the last season and is complete (the regular season ended
  2026-09-27). A later season enters when the vintage freezes it.

## 2. The parts and the stamp rule

Each season is stamped with the parts its eWAR carries, each part MEASURED on that season's rows,
never typed:

| Part id | Label | Series | Present in season s when |
|---|---|---|---|
| `batting` | batting runs | both | always (a column of every hitting row) |
| `wsb` | steal runs (wSB) | both | always |
| `bsr_rest` | the rest of baserunning | both | some hitting row has abs(baseRunning - wSb) above 0.005 runs |
| `fielding` | fielding | both | always |
| `framing` | catcher framing | both | some hitting row has abs(F_i) above 0.05 runs, F_i defined below |
| `positional` | positional adjustment | both | always |
| `league_replacement` | league and replacement terms | both | always |
| `pitching` | pitching (FanGraphs' FIP-based) | both | always |
| `eabs` | eABS (ABS challenges) | both | `data/ewar_v3.json` checks[s] carries an ABS receipt |
| `r2` | realized pitching (runs allowed) | realized only | `data/ewar_v3.json` checks[s] counts R2 rows above 0 |

- `F_i = rar_i - (batting_i + baseRunning_i + fielding_i + positional_i + wLeague_i + replacement_i)`,
  the part of FanGraphs' RAR the feed does not list as a component: the catcher term (framing).
- **The label of `bsr_rest` is measured too.** Where baseRunning equals wSb + ubr + wGdp within 0.005
  runs on every hitting row of the season it reads "UBR and double plays (wGDP)"; otherwise
  "FanGraphs' other baserunning runs".
- **Groups.** A group is a maximal run of consecutive seasons with the same stamp (the same part set
  on both series and the same `bsr_rest` label). Each group carries one sentence naming what it
  carries and, against the newest season, what it does not. `eabs` is never listed as missing before
  its first season: challenges did not exist, so nothing is missing.

## 3. The core and the full series

For season s, every hitting-group row i and pitching-group row j of the vintage:

```
x_i       = (baseRunning_i - wSb_i) + F_i                       runs: the parts not in every season
X_i       = x_i - PA_i * (sum_k x_k) / (sum_k PA_k)             re-centred MLB-wide per PA
RPW_fg,s  = (sum rar) / (sum war) over hitting rows with abs(war) >= 0.5   FanGraphs' own conversion
core_i    = war_i - X_i / RPW_fg,s                              hitter, both series
core_j    = war_j                                               pitcher, both series
full_i    = war_i + dh_i      realized_i = war_i + dr_i         dh, dr: data/ewar_v3.json (0 when not listed)
```

- **CORE** is eWAR built only from the parts present in every season 2000 to 2026: batting, steal
  runs, fielding, the positional, league and replacement terms, and pitching. It is computed for
  every season so that the parts later seasons add can be measured against it.
- **FULL** is eWAR itself, the headline series as served, with every part its season carries; FULL
  realized is eWAR realized.
- **The gap per part** on season s, in wins, per side: `bsr_rest` and `framing` are their re-centred
  terms (B_i and Fr_i, the two halves of X_i / RPW_fg,s, each re-centred on its own, which sum to X_i
  / RPW_fg,s because re-centring is linear); `eabs` is the headline departure dh; `r2` is dr - dh on
  the pitching side.

## 4. The agreement check

**Identities (hard: any miss refuses the build and nothing is written).**

1. Per row, FULL - CORE = B + Fr + eABS within 1e-9 wins; FULL realized - CORE = B + Fr + eABS + R2
   within 1e-9 wins.
2. Per season and side, the sum of CORE equals the sum of published fWAR within 1e-6 wins, and so
   does the sum of FULL; FULL realized within the R2 rounding bound `data/ewar_v3.json` records.
3. In a season whose stamp carries none of `bsr_rest`, `framing`, `eabs` and `r2`, CORE equals FULL
   and FULL realized on every row exactly.

**The gap report (descriptive: it decides nothing, carries no threshold and moves nothing).** For
every season and every part present in it, on its side: rows with a nonzero term; the standard
deviation, mean absolute value and maximum absolute value of the term in wins; the cells whose CORE
and FULL differ at one decimal, as a count and a share of the side's rows; and the Spearman
correlation of CORE with FULL over hitters with 300 or more PA (headline parts) and over pitchers
with 50 or more IP (R2, on the realized series). The same block is reported for the total gap.

- No band is registered for the gap. CORE and FULL differ by exactly the measured parts, by design;
  a large framing term for a catcher is the part, not a defect. "Agree" means the identities hold:
  every difference between the two is a named part.

## 5. What is served and what is never served

- **Served: FULL, the headline eWAR, which is the displayed eWAR already.**
  - The MLB Stats eWAR board's year selector and range (`data/war_seasons.json`) cover 2000 to 2026.
    Every window states the stamp of each season group it spans; a single past season states its own.
    The clubs of production and names for seasons the eWAR v2 artifact never covered come from the
    same war_daily stint frame the board's Earned rollup reads.
  - Player pages' season lines start in 2000 (`mlb_player_export.CAREER_FROM`) and name the group
    stamps of their seasons where a part is missing. The eWAR v2 reference column is printed only on
    seasons the eWAR v2 artifact covers (2011 on): before that the eWAR v2 provider serves bWAR, and
    a bWAR value is never printed under the eWAR v2 label.
  - The league averages' eWAR rows (eWAR per 600 PA, per 200 IP) start in 2000.
- **Recorded, never displayed: CORE.** `data/ewar_history.json` carries the stamps, the groups, the
  identities' results and the gap report per season and part, and nothing per player. CORE is never
  a column, a sort key, a label, a driver or a model input.
- **Unchanged:** `data/ewar_v3.json`, `data/ewar.json`, `data/fwar_vintage.json`, `ewar_v3.py`,
  `tools/build_ewar_v3.py`, `war_source.DEFAULT_PROVIDER` (fWAR, the training label) and every
  fitted consumer. HoF stays on bWAR: its careers reach before 2000.

## 6. Registry and glossary

- Registry row `ewar_history`: provisional, `measurement_only`, eval artifact
  `data/ewar_history.json`; it claims no accuracy.
- The glossary entry `ewar` names the seasons (2000 to 2026) and the measured season stamps.

## 7. What was read before this registration

A census of the vintage, run to find which parts each season carries; none of it is a CORE, FULL or
gap statistic:

- `ubr` and `wGdp` are 0 on every hitting row in 2000, 2001, 2025 and 2026.
- baseRunning equals wSb + ubr + wGdp on every hitting row in 2002 to 2015 (largest residual 0.00
  runs); from 2016 it does not (largest residual 3.8 to 7.2 runs a season).
- rar equals the six listed components on every hitting row through 2007; from 2008 a residual sits
  on 86 to 108 rows a season, 84 to 103 of them catchers by StatsAPI's primary position and the rest
  players listed elsewhere (DH, first base, a multi-club row), summing to between -5.5 and +1.2 runs
  a season.
- rar / war is one constant per season to within 0.0003 (2008: 10.032; 2026: 9.822).
- `data/ewar_v3.json` lists no row before 2016; R2 rows 2016 to 2026; the ABS receipt in 2026 only.
- The player pages' board holds 83 players with a vintage season before 2014, the earliest in 2005.

## 8. Defaults

- Stop at 2000 (part 1); the owner may extend the vintage under its own amendment.
- R2 stays from 2016 (EBR_GATE.md 11.3.3): before 2016 eWAR realized equals eWAR on every row and the
  stamp says so. Extending R2 to 2011 to 2015 on the history runner record of task
  EBR_Q4B_HISTORY_BACKFILL would amend 11.3.3 and move served eWAR realized cells; it is put to the
  owner, not done.

## 9. Amendments

A dated amendment, committed alone, may only record an owner answer that arrived after this commit
or fix a definition defect an identity exposed, stating the defect and its evidence. The parts, the
stamp rule, the series and the report never change after the first build.

### 9.1 2026-10-22: a part's term enters x_i only in a season whose stamp carries it (definition defect, identity 3)

- **Defect.** Part 3 writes `x_i = (baseRunning_i - wSb_i) + F_i` in every season, while part 2
  stamps a part present only above its threshold. FanGraphs' components are published rounded, so
  F_i carries a rounding residual in every season: in 2000 and 2001, where no row reaches the 0.05
  run threshold and the stamp carries no framing, the largest abs(F_i) is 0.00027 and 0.00036 runs
  (read from the vintage before any CORE, FULL or gap number existed). Identity 3 ("CORE equals FULL
  on every row exactly" in a season with none of the four parts) could then never hold, and CORE
  would carry rounding noise as if it were a part.
- **Fix.** `x_i = [baseRunning_i - wSb_i if the season's stamp carries bsr_rest] + [F_i if it carries
  framing]`; B_i and Fr_i follow (0 in a season without the part). Nothing else changes: the stamp
  rule, the thresholds, the series, the identities and the report stand as registered.
- Committed alone with its pin, before any number of the estimand.

### 9.2 2026-10-22: FULL's side sum is checked within the artifact's storage rounding (definition defect, identity 2)

- **Defect.** Identity 2 checks the sum of FULL against published fWAR within 1e-6 wins, but
  `data/ewar_v3.json` stores each departure rounded to 6 decimals (its `write` of `dh` and `dr`), so
  the stored departures of a side sum to zero only within 5e-7 wins per listed row. The first build
  refused on exactly that: FULL's 2026 pitching sum sat +8e-6 wins off fWAR, over 868 listed
  pitching rows (a storage residual, not a part, read before any gap number existed). The artifact's
  own zero-sum checks run on its unrounded values and pass.
- **Fix.** FULL and FULL realized are checked per season and side within 1e-6 + 5e-7 x (rows of the
  side the artifact lists with a departure on that series) wins; FULL realized keeps the R2 rounding
  bound where that is larger. CORE keeps 1e-6. Identities 1 and 3 and everything else stand.
- Committed alone with its pin, before any gap number.

## 10. Results

**EMPTY AT REGISTRATION.**

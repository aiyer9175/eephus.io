# eWAR site-wide calibration: which WAR each consumer reads (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EWAR_SITEWIDE_CALIBRATION (owner decisions EW3-18 and
EW3-20). This document is committed ALONE, before any number of its estimands is computed: no
measurement band constant, no deserved ballot, no WAG figure on the new basis and no blast radius
exists at this commit. Nothing in this commit changes a model, an exporter, a flag or a served
artifact. Part 9 is filled in afterwards; nothing above part 9 may be edited once anything is
written below it, and a change is a dated amendment under part 9, committed alone. Its pin test is
`test_ewar_sitewide_calibration.py`.

- eWAR itself: `docs/ebr-2026-09-30/EBR_GATE.md` amendment 11.10 (`data/ewar_v3.json`): the headline
  eWAR is the frozen fWAR vintage plus the ABS part from 2026; eWAR realized adds the realized
  pitching basis R2 for pitchers from 2016 (11.10.3). Served as the displayed WAR since the flip
  aff642bd (2026-10-21, `war_source.EWAR_V3_LIVE`).
- eFV's label: `docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md` (switched 70c0c00d, 2026-10-22).
  This document does not touch it.

## 0. What kind of decision this is

**Each switch below is an owner basis decision (EW3-20) with a registered accounting check in front
of it.** Choosing which WAR series a consumer reads is not a claim that the consumer becomes more
accurate, and no clause here measures that claim; copy may never say a number improved because its
WAR basis changed. Movement is not accuracy. No clause relates any WAR series to a game outcome, a
price, a club outcome or an induction, groups a realized number by FV, eFV or consensus band
(`docs/PROSPECT_ANCHOR_GATE.md`), or reads a reserved eFV frame.

## 1. Decision record

1. **EW3-18 (owner, 2026-10-15):** "once eWAR is active, calibrate the site off it (Awards, eFV label
   per EW3-17, WAG, WARWAG)".
2. **EW3-20 (owner, 2026-10-15), with its amendment:** two numbers. The headline eWAR (predictive)
   is read by eFV, projections, trade and FA value, WAG and WARWAG; eWAR realized is read by Awards,
   the Hall of Fame and season recaps. "The Awards module shows who deserved each award on eWAR
   realized with its uncertainty band."
3. **EBR_GATE.md 11.10.5:** the Awards selection reads the displayed series under the module's own
   freeze rules, with eWAR realized printed beside each score. That stands: this document adds a
   separate deserved read and does not move the frozen selection or any closed season file.

## 2. The inventory: every consumer of a WAR series, today and after this task

| Consumer | Reads today | Reads after | Mechanism | Status at registration |
|---|---|---|---|---|
| Display doors (MLB Stats boards, player pages, Earned board, PAL, trade lookup, FA Archive, timeseries `career_war`) | headline eWAR | unchanged | `war_source.DISPLAY_PROVIDER` | done at aff642bd |
| eFV label | headline eWAR | unchanged | `war_source.EFV_LABEL_PROVIDER` | done at 70c0c00d |
| WAG (engine WAG on the debuted block, the boom/bust label, the farm WAG rollup, Talent Translation) | published fWAR (the stored `career_war` row) | headline eWAR | part 3, flag `storage.WAG_EWAR_HEADLINE` | this task |
| WARWAG (`WAR/season + WAG`, computed on the card) | WAR/season on headline eWAR, WAG on fWAR (a mixed basis) | both on headline eWAR | follows part 3 | this task |
| Awards selection (eephus 1st places, Now column) | displayed series under the freeze rules (2021 to 2026 records on eWAR v2) | unchanged | 11.10.5 | stands |
| Awards deserved read | none | eWAR realized with a measurement band | part 4, flag `awards_core.AWARDS_DESERVED_LIVE` | this task |
| Hall of Fame | bWAR (`hof_data.WAR_PROVIDER`, FROZEN by `docs/HOF_BAKEOFF_GATE.md`) | unchanged here | part 5.1 | deferred, owner question |
| Franchise Team eWAR and F-SCORE roster leg | the Earned board's provider (headline eWAR) | unchanged | 11.10.5 | done at aff642bd |
| Franchise club WAR history (1969 on) | bWAR | unchanged here | part 5.2 | deferred, owner question |
| Debuted value, surplus, trade value | fWAR (stored row) | unchanged here | part 5.3 | governed by EWV3_VALUATION_GATE_REGISTRATION |
| Projections, Team Outlook, FA projections, arbitration rungs, the Ledger and Franchise projected WAR tiles | fWAR-trained models | unchanged here | part 5.3 | fitted consumers; label is a retrain |
| Management | no WAR series | none | none | nothing to switch |

## 3. WAG and WARWAG on the headline eWAR

### 3.1 The estimand

For a debuted player with a stored `career_war` row R (series: published fWAR from the frozen
vintage, seasons the vintage did not reach kept on their incumbent), the observed leg of WAG is

```
observed_today(R) = R.career_war
observed_new(R)   = war_source.row_on_provider(R, "ewar_v3").career_war
                  = sum over seasons s of (R.seasons[s] + dh(p, s))     (2dp, the provider's own rounding)
```

with dh the headline departure of `data/ewar_v3.json` (both sides summed). The provider id is named
literally, `"ewar_v3"`, never `DISPLAY_PROVIDER`: with `EWAR_V3_LIVE` off the display falls back to
eWAR v2, a bWAR-based series, and WAG must not follow it. The expected leg (the FV-to-WAR survivor
curve, the exposure gate, the reliability weight) is not touched. The season count WAG is matched on
is the same row's season count in both cases. Debuted value, surplus and trade value keep reading
`R.career_war` (part 5.3).

### 3.2 The switch

`storage.WAG_EWAR_HEADLINE` (default False at the build commit). On, `_build_debuted_payload` passes
`observed_new` to the engine WAG and stamps `wag.war_basis = "ewar_v3"`; off, it passes
`observed_today` and stamps `"fwar"`. The PROSPX card's basis line reads `wag.war_basis` first.

### 3.3 The check (accounting only), and its pass rule

Computed once on the regenerated `data/timeseries` payloads against the same build with the flag off:

- C-1: no WAG-bearing player whose row has no 2026 season with a nonzero headline departure moves
  (`regressed_wag`, `counting_wag`, `regressed_lo`, `regressed_hi`, `boom_label` identical).
- C-2: for every player whose observed leg moves, `observed_new - observed_today` equals the sum of
  his headline departures within 0.01 wins (the 2dp rounding of the provider).
- C-3: the debuted value block (`trade_value_mm`, `total_value_mm`, `realized_mm`, `posterior`)
  is identical for every player.

PASS when C-1, C-2 and C-3 all hold. A failure leaves the flag off and is recorded in part 9. The
counts reported with the result: players whose WAG moves, the largest absolute move in
`regressed_wag`, boom/bust labels that change, and farm WAG rollups that move.

## 4. The Awards deserved read on eWAR realized

### 4.1 The ballot

For each season S in the Awards selector (2021 to the current season), each of MVP, Cy Young and
Rookie of the Year and each league: the module's own rule (`awards_core.mvp_ballot`,
`cy_young_ballot`, `rookie_ballot`: the same floors, the same rookie test, the same in-league split
and the same tiebreaks) applied to the same player rows with each side's WAR replaced by its eWAR
realized share (`WAR_realized` of the `ewar_v3` stint frame, summed as `league_split` sums `WAR`).
Manager of the Year carries no WAR and has no deserved read. The deserved ballot is the top
`DESERVED_N = 5` places.

### 4.2 The measurement band

The band says how far two honest published measurements of the same player-season disagree, not a
sampling interval and not a forecast. Per side x in {bat, pit}, with player-season sums over stints:

```
frame: player-seasons 2015 to 2025, 2020 excluded, that the frozen fWAR vintage carries on side x,
       with exposure e > 0 (PA for bat, IP = IPouts / 3 for pit)
d      = published fWAR (the vintage) - bWAR (war_daily, WAR_bwar of the stint frame)
k_x    = sum of d^2 / (2 * sum of e)          wins^2 per PA (bat) or per IP (pit)
sigma(p, S)^2 = k_bat * PA(p, S) + k_pit * IP(p, S)      (the in-league exposure the ballot reads)
band(p, S)    = realized(p, S) +/- 1.645 * sigma(p, S)
```

- The halving assumes the two systems' errors are independent with equal variance and that the
  variance grows in proportion to playing time. Both are assumptions, disclosed on the page in one
  plain sentence; neither is tested here. k is fixed per side from this frame (not per season) and
  written with its frame counts into `data/awards_eval.json`.
- Reported beside k, descriptive only: k by exposure tercile, so a reader can see how far the
  per-exposure line is from flat. No threshold is set on it.

### 4.3 The verdict

With L the deserved ballot's first place and i any other place:

```
i is within the band of L   when   realized(L) - realized(i) < 1.645 * sqrt(sigma(L)^2 + sigma(i)^2)
verdict = "clear"            when no other place is within the band of L
        = "too close to call" otherwise, naming every place within the band of L
```

Where the writers' result for S exists (the module's winners file), the read names the writers'
winner and whether he is L, within the band of L, or outside it. Descriptive only: no rate, count or
test over seasons is computed from these comparisons.

### 4.4 The switch and the check

`awards_core.AWARDS_DESERVED_LIVE` (default False at the build commit). Off, the block is built into
`data/awards_eval.json` only (the registry artifact, not read by the page); on, it is also written
into `data/awards.json` under `deserved`, keyed by season, so closed season files
(`awards_<S>.json`, write-once) and the frozen selection stay byte-identical. The check, an accounting
identity, PASS when every one holds:

- D-1: per season and side, the realized league total over the frame rows equals the headline total
  plus the summed realized-minus-headline departures of `data/ewar_v3.json` within 0.05 wins.
- D-2: every deserved ballot's eligible pool equals the selection rule's pool for the same award,
  league and season (same floors, same rookie test).
- D-3: k_bat and k_pit are finite and positive, each from at least 1,000 player-seasons.
- D-4: every closed `awards_<S>.json` and the 2026 frozen record are byte-identical before and after.

## 5. What this task does not switch, and why

### 5.1 The Hall of Fame

`hof_data.WAR_PROVIDER = "bwar"` is FROZEN by `docs/HOF_BAKEOFF_GATE.md` and pinned by
`test_epoch_display_doors.py`. The eWAR series begins in 2000 (the frozen fWAR vintage), so a switch
splices two definitions inside most careers on the current ballot and moves them against standards
read on bWAR careers. That is a change of the HoF rule's scale, which the HoF gate governs, not an
accounting switch. Owner question SWC-Q1 (part 8).

### 5.2 The Franchise club WAR history

One bWAR series per club from 1969. eWAR realized exists from 2000, so a switch would join two
definitions inside one chart. Owner question SWC-Q2 (part 8).

### 5.3 Fitted and priced consumers

Debuted value, surplus and trade value read fWAR until `EWV3_VALUATION_GATE_REGISTRATION` (owner
SWAR-Q4) reads. The projections and their consumers (Team Outlook, FA, arbitration, the Ledger and
Franchise projected WAR tiles) are trained on fWAR; switching their label is a retrain, which the
do-not-reopen list forbids here. Their copy keeps saying "fWAR basis", which is what they read.

## 6. What may and may not be claimed

- May: "WAG is measured on eWAR"; "deserved on eWAR realized"; "the band is the disagreement between
  two published WAR systems for a season of this playing time"; "too close to call".
- May not: that any number became more accurate because its WAR basis changed; that the band is a
  confidence interval or a probability; that a writers' vote was wrong; any rate of writers' winners
  inside or outside the band.

## 7. The order of commits

1. This document and its pin test, alone.
2. The build, both flags off: no served file moves (every regenerated served artifact byte-identical
   to the flag-off build apart from timestamps; the band and the deserved ballots land in
   `data/awards_eval.json`, the registry artifact).
3. The checks of 3.3 and 4.4 run once; part 9 records them.
4. A flip commit per passing part (flag, registry, glossary, copy and tests only, owner rule AG4-Q);
   the regenerations are listed for the integrator.

## 8. Owner questions recorded

- SWC-Q1 (Hall of Fame basis): (a) keep the HoF rule on bWAR and register a HoF re-check before any
  switch (default; nothing moves); (b) splice eWAR realized for seasons 2000 on into HoF careers with
  a disclosure, after a HoF gate amendment re-reads the standards; (c) show eWAR realized beside bWAR
  as a reference column for careers wholly inside 2000 to 2026, the rule unchanged.
- SWC-Q2 (Franchise club WAR history): (a) keep bWAR from 1969 (default; one definition per chart);
  (b) switch seasons 2000 on to eWAR realized with a marked seam; (c) add an eWAR realized line from
  2000 beside the bWAR line.

## 9. Results

### 9.1 2026-10-22: the checks of 3.3 and 4.4, run once (build a908f44c, both flags off)

**WAG (part 3.3): PASS.** Two timeseries exports from the same inputs rebuild_only loads, each in
its own process, storage.WAG_EWAR_HEADLINE off then on, compared player by player:

- 2,768 debuted players, 2,434 with a WAG block. C-1 held (no WAG moved for a player whose row
  carries no 2026 headline departure); C-2 held on every moved row (observed leg moved by the sum
  of the row's departures within 0.01 wins); C-3 held (debuted value, surplus, trade value and
  posterior identical for every player).
- Reported: 967 of 2,434 WAG rows move; the largest move in regressed_wag is 0.076 (Edgar Quero,
  -0.324 to -0.248); 7 boom/bust labels change (samuel_basallo, carlos_narvaez, endy_rodriguez,
  jake_irvin, ivan_herrera, yennier_cano, shane_baz).
- The farm grade follows the WAG it rolls up (talent translation, boom and bust rates, MLB
  production): all 30 org summaries move in some leaf; farm_rank swaps BAL (1 to 2) and LAD
  (2 to 1); the overall letter moves BAL A+ to A and LAD A to A+; farm_score moves on 4 clubs by at
  most 0.2 (BAL 112.8 to 112.6).

**Awards (part 4.4): PASS.** D-1 held (realized league totals reconcile with the artifact on every
season and side, largest gap 0.0); D-2 held (every pool equals the selection rule's); D-3 held
(k_bat 0.000525 wins^2 per PA from 8,592 player-seasons, k_pit 0.003787 wins^2 per IP from 8,221);
D-4 held (no closed season file and not the 2026 frozen record changed; the export with the flag
on succeeded, awards.json 133,665 to 186,454 bytes, under its 400,000 line).

- k by exposure tercile, descriptive: bat 0.000210 (1 to 40 PA), 0.000445 (40 to 285), 0.000555
  (285 to 753); pit 0.003329 (0.3 to 18.3 IP), 0.003640 (18.3 to 59.7), 0.003868 (59.7 to 232.7).
  The per-exposure line is not flat for hitters at low playing time. Most ballot rows sit in the
  top tercile (the floors are 252 PA or 81 IP for MVP, 100 PA or 30 IP for Rookie, 41 IP for Cy
  Young), where the tercile's k reads about 6 percent (bat) and 2 percent (pit) above the pooled k,
  so the served band is slightly narrow there.
- 36 ballots (MVP, Cy Young, Rookie, two leagues, 2021 to 2026): 4 read clear, 32 too close to call.
- Disclosure: while the result was written up, one tally of the writers' standing across the 30
  closed-season ballots was printed to the session's console, which 4.3 says is not computed. It is
  not recorded here, in the report or in any artifact, and nothing reads it.

### 9.2 2026-10-22: amendments made at the build, recorded here (above is not edited)

- 3.2: the block carries `war_basis` only while the flag is on, so a flag-off export is
  byte-identical to the export before this task (part 7 step 2); off reads the stored row.
- 4.4: with the flag off nothing is built or written, not even in `data/awards_eval.json`; the
  check builds the read in memory (part 7 step 2's "no served file moves" binds before 4.4's
  sentence). On, `data/awards_eval.json` carries the band under `realized_read_band`.
- 4.4 and 6: the payload key is `realized_read`, not `deserved`, and the page says "The rule on
  eWAR realized", "too close to call" and "within the band": the Awards module's copy rules ban
  the verdict words, keys included (`awards_core.VERDICT_WORDS`, `test_awards_copy.py`). Owner
  question SWC-Q3 records the choice. The registry row is `awards_realized_read`.

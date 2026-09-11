# Master plan 2026-09-09: the FanGraphs frame, eWAR v3, and the PROSPX + Sports Betting audit

Branch `efv-conviction-2026-08-08`. Written to the standard of
`docs/master-plan-2026-09-05-opus.md`: every number below comes from a committed artifact,
a reference sheet or a measurement whose command is recorded in the audit bundle; every
lane carries a pre-registered gate, a permanent-close pre-commitment and a blast-radius
clause per `docs/EFV_GATE_STANDARD.md`; every registry row gets an eval artifact before
anything ships. No em-dashes.

The owner's ask, 2026-09-09: holistically audit and improve PROSPX and Sports Betting and
every model and metric they depend on; check that we compute each metric correctly against
`library.fangraphs.com`; and use the seven WAR pages as the framework for our own WAR,
eWAR, seeking to IMPROVE on WAR and to use it for every WAR-dependent calculation on the
site. Owner direction the same day: **proceed with FanGraphs as the primary framework.**

The plan has six parts.

- Part 0: what the audit measured, and the five facts that change the program.
- Part 1: eWAR v3 on the FanGraphs frame. The owner's central ask.
- Part 2: the served-defect backlog (W0), ranked, with blast radius.
- Part 3: PROSPX, the valuation chain, and WAG.
- Part 4: Sports Betting and the module lanes.
- Part 5: sequencing, the owner decision queue, and the do-not-reopen additions.

The audit bundle lives at `C:/Users/noah/baseball-projects/_audit_2026-09-09/`:
`sheets/` (18 FanGraphs reference sheets), `findings/` (18 lanes, JSON + evidence),
`feasibility/` (7 fWAR components), `ideas/`, `journals/`, `scripts/`, and `PLAN_NOTES.md`.

---

## Part 0. What the audit measured

Eighteen lanes ran read-only against the tree and against 98 pages of the FanGraphs
library, fetched 2026-09-09 and 2026-09-10. Twelve metric-family lanes diffed our
implementations against the reference definitions; seven feasibility lanes established what
an fWAR-frame component would cost to build from data on disk; six standalone lanes audited
the served artifacts, the glossary, the registry and the betting engine.

**259 findings: 26 P0, 53 P1, 57 P2, 81 P3, 42 INFO.** A P0 is a served number or a served
claim that is wrong, with a verified row count. The findings were then put through an
adversarial refutation pass, one skeptic per lane, instructed to default to refuted; Part 2
carries only what survived.

### 0.1 Five facts that change the program

**1. Published fWAR is obtainable, and it is not a FanGraphs fetch.** MLB's own StatsAPI
`stats=sabermetrics` endpoint serves fWAR verbatim, MLBAM-keyed, back to 1950. It matches
the FanGraphs leaderboard to 0.0000 on both probed seasons (2011: 1,173 hitters + 662
pitchers; 2025: 765 + 873). `hitter_export.py:182` already fetches this host nightly and
`.cache/statsapi_saber_hitting_{2021..2026}.json` already holds six seasons of it. Hitters
carry `batting`, `baseRunning`, `fielding`, `positional`, `wLeague`, `replacement`, `rar`,
`war`, `ubr`, `wSb`, `wGdp`; pitchers carry `war`, `rar`, `ra9War`, `fip`, `xfip`, `pLI`,
`gmLI`. Consequences: the replica can be validated COMPONENT BY COMPONENT per season rather
than on the WAR total; the standing fact "fWAR is not obtainable programmatically" is
retired; and the 2026-08-03 ledger line banning re-probes of fangraphs.com is untouched,
because this is a different host.

**2. The library pages are stale about fielding, and our reference sheet inherited it.**
Served fWAR fielding has been Statcast-based since 2016 (the 2022 range update and the 2024
arm, blocking and throwing updates), and **catcher framing is INSIDE fWAR fielding in every
season probed** (2011: catcher Fielding equals rSB + CFraming to a max residual of 0.384).
UZR is the basis only before 2016. The library pages that say framing is excluded describe a
frame FanGraphs no longer serves. This flips a design conclusion: a framing-inclusive
catcher component is PARITY with fWAR, not an improvement claim, and the 2026-09-05
do-not-reopen entry banned only the year-blind Savant leaderboard, while two season-resolved
sources exist (the FanGraphs `CFraming` column, and the per-year Savant page JSON route
documented in `../defense-plus`).

**3. The eWAR artifact is never rebuilt.** `data/ewar.json` is stamped
`2026-09-03T12:35:09`. `tools/build_ewar.py` is hand-run only: nothing in `run_monthly.py`
calls it (the two mentions at :4716-4719 are comments), and nothing calls `ewar.build`.
So the served WAR is frozen mid-season on rows whose IP, ERA and bWAR refresh nightly, while
the served glossary claims it rebuilds. Verified independently. This is item 1 of W0.

**4. The pitcher replica already works.** A from-disk FG-frame pitcher WAR (plain FIP,
B-Ref PPF, B-Ref `GR_LI` as gmLI) reproduces published fWAR at r 0.9800 (2011, n 662) and
r 0.9873 (2025, n 873), MAE 0.158 and 0.094, with SP and RP season sums within 2 WAR.
Adding IFFB from the leaderboard pull closes 12 to 18 percent of the residual. The batting
replica matches published Batting Runs to 0.013 runs MAE when FanGraphs' own park factor is
used. The two hard gaps are fielding (no UZR, no Statcast component splits, no framing on
disk) and pre-2018 baserunning detail.

**5. Sports Betting has zero WAR readers.** Measured in lane F10. The eWAR epoch therefore
has no betting blast radius, and the two halves of this plan can proceed in parallel.

### 0.2 The shape of the defect list, and what it says about the platform

The dominant P0 class is not arithmetic. It is **a served claim contradicting served
behaviour**: a tooltip, glossary card, filter chip or accountability note describing a
threshold, formula, rate or input the code no longer uses. Roughly half the P0s are that,
and they cluster where a gate was re-run or a default was flipped without the copy moving
with it. The second class is **a served number that no invariant guards**, which is exactly
the failure mode the 2026-09-06 session named after four defects of the same shape.

The plan's W0 therefore has two halves that must ship together: repair the numbers, and
install the invariants and copy-derivation that stop the class recurring. A repair without
the invariant buys one cycle.

---

## Part 1. eWAR v3 on the FanGraphs frame

**The owner's decision, 2026-09-09: FanGraphs is the primary framework.** eWAR v2 (the
Baseball-Reference run frame with FIP pitching swapped in) becomes the incumbent to beat,
not the base to extend. Every departure from fWAR is an IMPROVEMENT CLAIM carrying its own
pre-registered gate; where no gate resolves, the component stays fWAR-faithful.

That rule is what makes this tractable. The 2026-09-04 epoch measured a NULL for the WAR
basis on eFV accuracy, and copy may still never claim an accuracy gain from a basis change.
What the fWAR frame buys is not accuracy, it is COHERENCE: the industry FV-to-WAR tables the
whole valuation chain rests on are denominated in fWAR, the readers comparing our number to
a public one are comparing to fWAR, and today the served hitter WAR differs from fWAR with
an sd of 0.55 and only 28.9 percent of rows inside 0.1 WAR.

### 1.1 The frame, component by component

Transcribed from the reference sheets. Position players:

```
WAR = (Batting + BaseRunning + Fielding + Positional + League + Replacement) / RPW
Batting     = wRAA + (lgR/PA - PF*lgR/PA)*PA + (lgR/PA - AL/NL non-pitcher wRC/PA)*PA
wRAA        = ((wOBA - lgwOBA) / wOBA scale) * PA
BaseRunning = UBR + wSB + wGDP
wSB         = SB*runSB + CS*runCS - lgwSB*(1B + BB + HBP - IBB)
Positional  = (Innings/9/162) * ladder, summed across positions
League      = ((-1) * (lgBat + lgBsR + lgFld + lgPos) / lgPA) * PA
Replacement = (570 * (MLB Games/2430)) * (RPW/lgPA) * PA
RPW         = 9 * (MLB R / MLB IP) * 1.5 + 3        [one MLB constant per season]
```

Pitchers:

```
ifFIP constant = lgERA - (((13*lgHR) + (3*(lgBB+lgHBP)) - (2*(lgK+lgIFFB))) / lgIP)
ifFIP   = ((13*HR) + (3*(BB+HBP)) - (2*(K+IFFB))) / IP + ifFIP constant
FIPR9   = ifFIP + (lgRA9 - lgERA)                    [ADDITIVE]
pFIPR9  = FIPR9 / (PF/100)                           [FIP-specific park factor]
RAAP9   = (AL or NL) FIPR9 - pFIPR9                  [own league, not MLB]
dRPW    = ((((18 - IP/G) * lgFIPR9) + ((IP/G) * pFIPR9)) / 18 + 2) * 1.5   [per pitcher]
WPGAA   = RAAP9 / dRPW
RepLvl  = 0.03*(1 - GS/G) + 0.12*(GS/G)              [continuous in GS/G]
WAR'    = (WPGAA + RepLvl) * (IP/9)
relief  = WAR' * (1 + gmLI)/2                        [levers the WHOLE quantity]
WAR     = WAR' + WARIP*IP                            [MLB-wide pin to 430]
```

Conventions: 1,000 WAR per season at a .294 replacement winning percentage, split 57/43
between position players and pitchers.

### 1.2 Where eWAR v2 sits against that frame, measured

| Component | eWAR v2 today | fWAR frame | Measured gap |
|---|---|---|---|
| Batting | B-Ref `runs_bat` verbatim | wRAA + park + league | replica matches FG to 0.013 runs MAE with FG's PF |
| Baserunning | B-Ref `runs_br` + `runs_dp` | UBR + wSB + wGDP | r 0.914, slope 1.069 vs FG BsR; zero points differ by 10-17 runs/season pre-2022 |
| Fielding | B-Ref DRS columns, ZERO framing | Statcast range + arm + catcher, framing INSIDE | r(DRS, UZR) 0.765; CFraming sd across catchers 5.1 to 9.1 runs |
| Positional | B-Ref `runs_position` | fixed FG ladder | B-Ref is era-indexed: SS +9.1 to +10.2, C +11.4 to +12.5 across the universal-DH boundary |
| League adj | none (B-Ref folds it in) | explicit per league | at most 2.6 to 4.5 runs per 600 PA pre-2022 |
| Replacement | B-Ref 59/41, total pinned to 999 | 57/43, total 1,000 | pitchers 410 to 430, +20 WAR/season |
| RPW | per-team least squares, one constant | 9*(R/IP)*1.5+3 per season | eWAR sits 0.13 to 0.25 BELOW FG in all 15 seasons |
| Pitching runs | FIP, MULTIPLICATIVE carry to RA9 | ifFIP, ADDITIVE carry | spread inflated 7.8 to 9.6 percent |
| Park (pitch) | B-Ref PPF on the solved CENTRE | FIP-specific PF divided into the rate | 10.4 percent of rows differ by 5+ PF points from `PPF_custom` |
| Runs to wins (pitch) | one constant per team-season | dynamic per pitcher | fitted on a pool 60 percent position players |
| Leverage | B-Ref `WAA_adj` chaining, above-average part only | (1+gmLI)/2 on the WHOLE quantity | replacement-term piece alone maxes at +0.366 WAR for a closer; the frequently quoted +0.5 is that piece PLUS the unlevered-delta piece and the two must be quoted as one sum or as two terms, never interchangeably |
| Role | knife-edge bucket | continuous in GS/G | 34 rows a season move up to 0.54 WAR on a classification |

Frame consequences of adopting fWAR wholesale, measured over 2011-2026: reliever WAR falls
22.6 percent (1,975 to 1,528), the SP/RP split moves from 68.5/31.5 to 76.7/23.3, and
pitchers gain 20 WAR a season from the 430 pin.

### 1.3 The build, in five gated waves

**W1.0 Plumbing, before any component (effort M, no served number moves).**

- `tools/build_ewar.py` enters `run_monthly` on the WAR-read cadence, with a freshness
  assertion that fails loudly when the artifact's `generated_at` predates the newest
  `war_daily` pull. This is P0 F10-02 and it ships first.
- One **league-constants table per season**, derived and validated: wOBA weights and scale,
  lgwOBA, lgR/PA, RPW, FIP and ifFIP constants, runSB and runCS, replacement runs. Today
  four modules carry four private copies with different weight sets and a wOBA scale
  (`fa_config.yaml` 1.15) outside every published season value. Validation: recomputed
  lgwOBA within 0.0005 of the Guts column every season 2011-2026 (already passing), and
  per-player wOBA within 0.0005 of the published feed.
- **The fWAR reference set**: cache StatsAPI sabermetrics for pitchers and for 2011-2020
  hitters under `.cache/statsapi_saber_*`. Owner scope call in 5.2, cost 0.2 to 0.9 s and
  0.4 to 0.9 MB per call, same host and fetcher the nightly already uses.
- **Identity repair** before any join is called clean: 16 `career_war` rows serve a
  same-name veteran's seasons under a prospect's slug, the Chadwick name path hands a
  never-debuted prospect any same-name MLB id, and 142 MLBAM ids are unresolved.

*Status 2026-09-11.* The league-constants table is built (`723848c6`): wOBA weights,
scale and lgwOBA solved exactly from the feed, RPW, the FIP constant (BB includes IBB),
runSB, runCS, lgwSB and R/PA, each matching the Guts table to its printed digit for
2011-2025. The reference set is cached. Not done: the `build_ewar` pipeline step (waits
on D11), the consumer half (fa_config, hem_plus and wrc_rates still carry the 2013
weights), and the identity repair.

**W1.1 The faithful replica (effort L). Build fWAR, do not improve it yet.**

*Status 2026-09-11 (`4242177b`).* Position players PASS every component in every
complete season 2011-2025 (at least 99.9 percent within 1.0 run, worst MAE 0.11 runs),
with UBR, wGDP, fielding and the batting park factor consumed and labelled. Pitchers
FAIL every season (RAR 66 to 96 percent within a run): FIP reproduces exactly, and the
gap is IFFB, FanGraphs' FIP park factor and per-stint pitcher counts, none on disk.
Component table: `data/fwar_replica_eval.json`; registry row `fwar_replica`.

Each component reproduced from inputs and gated at **1.0 run on at least 99 percent of rows
per season, 2011-2026**, against the published feed:

| Component | Status from feasibility | What W1.1 must add |
|---|---|---|
| Batting | matches to 0.013 runs MAE | FG park factor for 2011-2020 (10 Guts fetches or a leaderboard back-solve); per-stint apportionment by `war_daily` PA share |
| Positional | ladder inversion R2 0.993-0.996 | exact DH exposure from B-Ref `Inn` minus fielded innings |
| League + Replacement | arithmetic, inputs complete | pin the pool convention (5.2 decision) |
| RPW | inputs complete | adopt the FG closed form |
| Pitching | r 0.987, MAE 0.094 | IFFB from the leaderboard pull; additive carry; own-league baseline; FIP-specific PF; dynamic dRPW; continuous role; whole-quantity leverage; 430 pin |
| Baserunning | wSB exact; UBR/wGDP need PBP | 2018+ from `.cache/win_prob`; wSB-only before, labelled |
| Fielding | **blocked**, see W1.2 | consume the published `fielding` column while the component is unbuildable |

The acceptance test is not the WAR total. It is the component table, per season, with the
row counts that cleared 1.0 run published in the eval artifact.

**A hard prerequisite, from lane F02:** an in-house wSB built from the current corpus events
table would overstate lgwSB by 52 percent one-sidedly, because roughly 22 percent of steal
attempts happen on the plate-appearance-ending pitch and the events table cannot see them.
The corpus needs a runners table, and the census gate is that corpus attempts equal StatsAPI
league SB + CS within 1 percent, BEFORE any baserunning component is built.

**W1.2 Fielding, the one genuinely blocked component (effort L, owner decision in 5.2).**

Neither UZR nor the Statcast component splits nor framing are on disk. Three routes:
(a) consume the published `fielding` column from the feed, which is fWAR-exact and needs no
model; (b) build from Statcast components, which needs the split columns we do not have;
(c) wait for SDR. The plan's default is **(a) for the replica** and a registered arm for a
framing-inclusive catcher component, since framing is fWAR PARITY (fact 2) and the largest
catcher value term is currently at zero. The multi-indicator range idea (DRS plus Statcast)
is the banned blend class by name and may run ONLY under the frozen SDR gates G-A and G-B.

**W1.3 The improvement arms (effort M each, one family per Holm step).**

Each arm is a departure from fWAR and must beat the faithful replica on a pre-registered
forward gate, not on descriptive fidelity. The descriptive team-wins gate is lost by any FIP
WAR by construction and is reported, never used to decide.

1. **ifFIP vs plain FIP.** IFFB explains the largest residual against published fWAR
   (corr -0.42). Gate: `gate_pitcher_persistence` forecast leg on identical pairs, min 50
   IP, temporal split fit 2011-2018 and score 2019-2025, plus a row-permuted IFFB twin.
   **Source correction, from verification:** take IFFB from the FanGraphs leaderboard
   column already probed on 2026-09-09, NOT from a `.cache/win_prob` popup walker. StatsAPI
   `popup` trajectory is not the vendor IFFB (a 4-game sample puts popups at 19 of 207
   batted balls, far above any infield-fly rate) and that cache misses 2011-2017 and 2020
   while eWAR runs 2011-2026.
2. **League-baselined RAAP9 vs eWAR v2's per-role centring.** This is the fWAR-faithful
   default, so it is the arm that must LOSE for v2's role centring to survive. In-sample it
   already leads by +0.0040 to +0.0129 across four windows; the R2e.2 precedent (a +0.023
   in-sample gain that collapsed to +0.0017 on a temporal split) sets the transport bar.
3. **Park:** FG FIP factor vs B-Ref PPF vs `PPF_custom` (the venue-mix factor already on
   disk and unused). FG's own caveat says its factor assumes half home and half neutral;
   `PPF_custom` does not.
4. **Leverage on the above-average part only.** FanGraphs levers the whole quantity
   including replacement, so a replacement-level reliever gains value for usage alone.
   Gate: reliever season-WAR self-correlation and the forward team-runs leg, NOT the
   persistence runs leg, which excludes leverage by construction. Note the standing ban:
   crediting relievers with OUR OWN gmLI is a measured null (r 0.9947 with B-Ref's).
5. **Framing-inclusive catcher fielding** (see W1.2).
6. **Reliability-shrunk fielding.** FanGraphs serves a raw centred single-season read while
   its own Def page warns 20 to 30 games hold little predictive value. Ship only if the
   forward leg clears a player-clustered 95 percent lower bound and the current-season
   descriptive leg does not lose by more than the pre-registered margin.

**Negative list, recorded so the plan does not reopen measured nulls:** xwOBA-allowed or
contact-quality season estimators (X-S4, 0.377 vs 0.382), observed-K shrink (K-prior closed
permanently), a single global HR-shrink k (R2e.2 no-ship, did not transport), and the
OAA/rfield blend at any weight outside the SDR gates.

**W1.4 The label epoch and the re-anchor cascade (effort L, its own epoch).**

Precedent: `docs/efv-2026-09-03/WAR_BASIS_RUNBOOK.md`, whose step ordering is load-bearing
(floors before deltas, curve before anchors, retrain before rebuild, two rebuild passes,
margins last). The cascade is the five bWAR-pinned families plus the client `FV_WAR_ANCHORS`
mirror, the eFV matrices and floors, the fingerprint label term, `star_label_view`, the
projections retrain and the arbitration spine.

Two clauses specific to this epoch. First, **fWAR itself becomes a candidate eFV label**,
which is a separate question from the served WAR basis and needs its own registration; do
not let it ride the epoch silently. Second, `fv_to_6yr_avg_war` currently AVERAGES an eWAR
measurement with an fWAR reference at a flat 0.5 and changes denomination at FV 45 (L13-10);
under the fWAR frame both sides are finally in one currency, and that reconciliation must be
measured and published rather than assumed.

### 1.4 The positional ladder

Our fitted ladder (registry `positional_ladder`, validated 2026-07-25) beats the FanGraphs
table by 0.4819 runs per 650 PA held-out, on 4 of 4 era splits, against a zero-information
control at -5.02. The FanGraphs table is wrong by about 4 runs at first base and treats
second, third and centre as one rung where the current window measures 5.12, 3.62 and 4.14.
FanGraphs' own page says the ladder is from a number of years ago and could change.

**Decision: the eWAR positional component reads OUR ladder, by reference from the artifact,
so ladder upgrades never touch WAR code.** The FanGraphs table is a comparison row.

Three caveats ride it. The ladder is an INVERSION of B-Ref's `runs_position`, so under the
fWAR frame it imports B-Ref's positional pricing into a FanGraphs frame and that hybrid must
be disclosed. The zero-point convention differs (ours exposure-weighted, FanGraphs
fielder-centred with DH outside); gaps are identical and the league adjustment absorbs the
level, so WAR totals are unaffected, but per-position Off/Def splits are not, and the
convention is pinned once. And the era indexing is real: the ladder moves across the
universal-DH boundary by more than its own confidence intervals.

Three ladder lanes, none blocking eWAR:

1. **One ladder object, one DH specification (effort S).** Two live DH exposure specs
   disagree and every rung moves when the shares renormalise; the exact exposure (B-Ref
   `Inn` minus fielded innings) raises in-sample R2 from 0.986-0.992 to 0.993-0.996 in 15 of
   15 seasons and moves the DH rung from about -14.7 to -13.9. Re-route the hand-written
   RPS+ position multipliers in `prospx/index.html` to the artifact. Gate: the K5
   forward-chained harness, paired cluster bootstrap, permuted-label control.
2. **Per-season shrunk ladder as a challenger (effort S).** Measured drift at SS, 2B and CF
   is two to three CI half-widths, so a six-season window is an average of two tables.
   Same K5 harness. Modest expected gain; commit the null if it loses.
3. **Triangulation (effort M), the lane that makes "improve" mean something.** The ladder
   has three independent identifications and we use one. The defensive-transfer ladder D(p)
   is already fitted in `positional_fit` from 2,081 two-position pairs on Statcast, and an
   offensive-equivalence ladder (the batting-runs gap by position) has never been fitted
   though every input is on disk. Gate: the three agree within their joint CI at each rung;
   where they disagree the B-Ref inversion is the one carrying an assumption. Catcher stays
   on the inversion until framing or SDR lands, and the arm/DP rungs likewise.

A defect found while auditing this: Position Fit composes the Statcast-scale D(p) with the
B-Ref-scale ladder, so an average glove gains or loses runs on a move the ladder exists to
make value-neutral. 71 of 245 served best-position verdicts rest on D. FanGraphs solved the
same problem with no D term at all. Fix is disclosure plus a no-D arm in the existing
169-mover harness.

### 1.5 What eWAR v3 may and may not claim

May: that it is computed on the FanGraphs frame, component by component, validated against
published fWAR within a stated tolerance, with every departure named and gated. That it
carries a positional ladder measured on our own resolved data rather than a published table
from over a decade ago. That its inputs are reproducible and vintage-stamped, which
FanGraphs' own published Batting is not (it drifts up to 4.0 runs between fetch dates as the
park factor accrues).

May not: any accuracy claim from the basis change. The 2026-09-04 epoch measured a null and
nothing here re-opens it. The descriptive team-wins gate is lost by construction for any FIP
WAR and must be published as a loss.

### 1.6 Owner decisions this program needs, with defaults

Recorded here rather than in Part 5 because every one of them gates a W1 lane. Where the
answer is a convention rather than an outcome, the plan says RECORD, not FIT: fitting a
convention against outcomes is a fabricated gate.

**D1. The fWAR reference set (default: cache it).** Cache StatsAPI `stats=sabermetrics`
for pitchers and for 2011-2020 hitters under `.cache/statsapi_saber_*`. Same host and the
same fetcher the nightly already uses for 2021-2026 hitters, 0.2 to 0.9 s and 0.4 to 0.9 MB
per call, no fangraphs.com access, so the 2026-08-03 no-re-probe line is untouched. Without
it the replica has no component-level validation target before 2021.

**D2. Fielding for the replica (default: consume the published column).** UZR, the Statcast
component splits and framing are all absent from disk. Consuming the feed's `fielding`
column is fWAR-exact and needs no model; building from components is blocked; SDR is
data-blocked. The default is explicitly a HYBRID and must be disclosed as one.

**D3. Framing source (default: the FanGraphs `CFraming` column).** Framing is fWAR PARITY,
not an improvement, and it is the largest catcher value term sitting at zero in eWAR v2.
Two season-resolved sources exist. The 2026-09-05 ban covers only the year-blind Savant
leaderboard endpoint and is not touched.

*Erratum, 2026-09-11 (new evidence, changes this default's premise).* Framing is ON DISK
after all, inside MLB's sabermetrics feed: `rar - (batting + baseRunning + fielding +
positional + wLeague + replacement)` equals FanGraphs `CFraming` with max difference 0.0
on every catcher in five probed seasons (2011, 2016, 2023, 2024, 2025), and is zero on
every non-catcher. So a third source, needing no fangraphs.com fetch, is season-stamped
and already cached for 2011-2026. Recommended default becomes that residual, read through
`saber_feed.framing_residual` (the one loader the Defense board, the hitter board's wRC+
column and the replica share; eWAR v3 must read `saber_feed`, never `dem_plus`). Three
corrections to the C3 fielding record from the same lane: Savant `frp` in
`data/savant_oaa.json` is FanGraphs' RANGE-ONLY `rFRP`, not unified FRP; B-Ref
`runs_catcher` equals `rSB + rCERA` (no blocking piece; `rCERA` is staff run prevention);
B-Ref `runs_defense` equals SIS DRS minus `rSZ`.

**D4. Replacement split, 57/43 or 59/41 (default: 57/43, the FanGraphs convention).**
B-Ref measures 59/41 and eWAR v2 inherits it. Under the FanGraphs frame the split is 57/43
and pitchers gain about 20 WAR a season. RECORD as a decision in the runbook; there is no
outcome to fit it against.

**D5. League-adjustment pool (default: AL/NL, non-pitcher).** FanGraphs writes `lgPA`
without stating MLB-wide versus per league, or whether pitcher batting is in. The magnitude
differs by pool (2.6 versus 4.46 runs per 600 PA pre-2022). Pin it before the first build.

**D6. Runs per win (default: the FanGraphs closed form).** One MLB constant per season,
9*(R/IP)*1.5+3. eWAR's per-team least-squares estimator sits 0.13 to 0.25 runs below it in
all 15 seasons. A third arm exists: score both against actual team wins from run
differential over 450 team-seasons, as a correctness check on a constant, never as an
accuracy claim.

**D7. Does fWAR become a candidate eFV LABEL (default: register it separately, do not let
it ride the basis epoch).** The served WAR basis and the eFV training label are two
questions. The 2026-09-04 epoch measured a null for the label swap; a new label needs its
own registration and its own floors.

**D8. Ladder zero-point (default: exposure-weighted, ours).** Gaps are identical under
either convention and the league adjustment absorbs the level, so WAR totals do not move;
per-position Off and Def splits do. Pin once and state it on the surface.

**D9. Park-factor vintage (default: freeze at season close and stamp it).** FanGraphs' own
published Batting for a completed season drifts as the factor accrues, up to 4.0 runs in
2025 between two fetch dates. Our number should be reproducible even where theirs is not,
which is a genuine advantage and should be stated as one.

**D11. The eWAR rebuild cadence, and it is the whole cascade, not a cron line
(default: rebuild on the WAR-read cadence inside the runbook's ordering, NOT
nightly).** Shipped 2026-09-10: the false glossary claim is deleted and every board
now publishes its eWAR build stamp and drift. What is NOT shipped, because it is
the owner's call, is when the artifact is rebuilt. Runbook step B ends
"INVALIDATES: everything below", and below it sit the career_war rebase (which
refuses a plain re-run), the pooled outcome curve, the empirical anchors, the draft
slot curve, the war_rate vintages and the projections retrain. A nightly rebuild
would also re-solve the per-season per-role centring constant every night, so
completed-season WAR moves by rounding and the board-basis fingerprint churns
daily. The three options are: (i) rebuild with the full cascade on the monthly WAR
read, which keeps one named build behind every fitted artifact and leaves the
current season up to a month stale with the staleness disclosed; (ii) rebuild
nightly and accept fingerprint churn plus a re-anchor every night, which the plan
recommends against; (iii) leave it hand-run and rely on the new disclosure, which
is honest but means a reader sees a stale cell until someone remembers. Default is
(i).

**D10. The 2011-2020 park factors (default: ten Guts fetches).** Needed once, cached, then
the batting replica is exact. The alternative, the Savant runs index, costs 1.06 runs MAE
and has no 2011 coverage.

---

## Part 2. The served-defect backlog (W0)

Eighty P0 and P1 findings went through an adversarial refutation pass, one skeptic per
lane, instructed to default to REFUTED and to check first whether the auditor had measured a
retired field, a dead branch or a lab artifact rather than the served path.

**Result: 42 CONFIRMED, 38 PARTLY_CONFIRMED, 0 REFUTED, 31 severities corrected DOWNWARD.**
Nothing was refuted outright, which says the auditors read the code correctly. But roughly
two in five findings had an overstated blast radius, and that is the number the plan carries
rather than the auditor's. Nineteen P0s survive.

The corrections that matter most, as a standing lesson: one finding's radius fell from 6,433
served rows to **60**, because every prospect row is re-pointed onto the eFV surplus so the
Bayesian posterior it measured reaches almost nothing; another's fell from 2,600 rows to
**651**, because the renderer gates on a full season of playing time; a third's "184 served
pills" died entirely because the field **has no reader anywhere in the repo**. Two moved the
other way. Measure the SERVED path, not the compute path.

### 2.1 The nineteen confirmed P0s, ranked by what they break

**Tier 1, the WAR basis itself. These block Part 1.**

1. **F10-02 and F11-01, the eWAR artifact is never rebuilt.** Narrowed by verification, and
   the narrowing matters: the staleness is confined to the CURRENT-season cell, with 0 of
   855 2024 and 0 of 873 2025 pitcher-seasons drifting. Career totals, WAG inputs and eFV
   labels carry a stale 2026 cell, not a stale series. 422 of 773 pitcher cards, of which
   71 move a full display step. **The fix is NOT a drop-in pipeline phase**: runbook step B
   ends "INVALIDATES: everything below", and below it sits the career_war rebase, which
   refuses a plain re-run. This needs the runbook's ordering, not a cron line.
2. **F10-01, mixed basis on one board.** Evidence strengthened by direct replication: the
   served 3yr column reproduces on bWAR to a 0.36-point median and moves 4.02 (SP) and 5.09
   (RP) points on eWAR. 498 pitcher board rows plus 497 card blocks; 103 of 197 SP and 196
   of 301 RP move 3 or more points if re-pointed. Re-pointing MOVES SERVED NUMBERS and
   re-derives glossary rhos pinned by a freshness test, so it is an epoch, not a patch.

**Tier 2, a served accuracy claim that reverses under its own repair.**

3. **F07-02, the win-expectancy engine is fitted and queried on a post-play score against a
   pre-play base-out state.** Verification found this **UNDERSTATED**. The leakage is what
   manufactures the served edge: on the honest pre-play state the MLB feed reads 0.157516
   against this model's 0.157678, so **the served claim that the team-blind model is
   slightly better than the feed is FALSE once the leak is closed.** Touches all seven
   coefficients, the calibration block, the 213-cell table and 13,971 attempts.
4. **F07-05 and F07-01 ride with it**: three served tail numbers the shipped model does not
   produce plus two inverted narrative claims, and 18 blank win probabilities in the very
   table the copy says the boundary is priced from. Both must land WITH F07-02, because the
   numbers they would publish are the numbers F07-02 moves.

**Tier 3, wrong served numbers.**

5. **F01-03, the wOBA scale.** `woba_scale: 1.15` for every season against a measured 1.24.
   3,205 served rate rows, 748 off by 3 or more wRC+ points, worst 10.2. Two refinements:
   the scale that PAIRS with the engine's 2013 weights is **1.277**, and there is a
   **second hardcoded 1.15 at `positional_fit.py:135`** with no fitted coefficient to
   absorb it. **Do not ship it with F01-04**: F01-03 alone closes the entire measured width
   gap, and stacking the divisor change would overshoot by about 1.5 percent.
6. **F05-06, two numbers called ERA-** on the same pitcher card, 250 of 429 disagreeing by
   15 or more and 134 by 30 or more. Guard the DISPLAY only: the field feeds a trade-value
   disqualifier and RPS+.
7. **F05-02, a shrunk role-pool skill FIP served as "FIP"** on 505 bullpen and 229 starter
   rows, plus a third surface verification found (`mlb_current_lines.json`, 733 players).
   Do not rename the JSON key; relabel the header and retarget the glossary term.
8. **F02-01, the running-game census.** 40.56 percent of caught stealings invisible.
   Corrected: the exclusion row gains **2,455 not 2,470**, and it is **not a pure counting
   fix**, since 2 attempts enter the PRICED population and move the 3B success rate and the
   swing-weighted break-even.
9. **L15-F1, the provisional-pool dedupe.** 2,669 duplicate rows on the farm surfaces plus
   2,688 on the homepage rail. Corrected: there are **eight** concat sites, four routed and
   four bare, not "three of seven". The fix moves every farm header count by design.
10. **L14-01, the runline tie atom.** ALL SIX served runline rows, not the two filed: the
    +1.5 sides are overstated and the -1.5 sides understated by exactly the same amount.
11. **L14-02, DFS prices a live game off an in-game market.** 22 of 117 rows; 21 carry a bad
    implied team total and win probability. The deeper miss is that the builder applies **no
    status filter at all**, so a Final game is on the card too and escapes only because the
    provider drops settled events.

**Tier 4, served claims contradicting served behaviour.** F03-01 (the A-ball pill says the
signal is not an input while it leans 478 grades; the replacement copy must be CONDITIONAL,
since 218 other pill-rendering cards carry a note that is currently true), F06-01 (21 of 26
breakout rows show a threshold they did not clear), F12-01 and F12-02 (a 9 percent discount
rate over a table computed at 7 percent, and an Ohtani net present value wrong by $77.8M),
L17-F1 (128 priced against 109 served), L18-01 (a superseded report card still starring a
model on a leg its own metric string calls unresolvable).

### 2.2 The invariant layer, which ships WITH the repairs

Every Tier 3 and Tier 4 defect is a number or a string that no test compares against its own
source. Repairing them without this buys one cycle. The block asserts, at publish time: fan
order and bucket sums; one price per player; rank uniqueness and contiguity; served counts
equal to rendered counts; the client FV-to-WAR mirror equal to the engine; every served
threshold string derived from the constant it names; every plus metric's anchor at its
advertised value; and artifact freshness against its own inputs. The copy rule is the one
the accuracy page already follows: **a served number inside a string is interpolated from
the artifact, never typed.**

---

## Part 3. PROSPX, the valuation chain and WAG

### 3.1 WAG is the most concentrated damage on the platform

Seven findings, every mechanism reproduced, and the 2026-09-03 design audit's F25 confirmed
for the third time. What verification corrected is scale, not existence.

- **There are FOUR served implementations, not three.** The Time Machine renders
  `regressed_wag` ungated and is absent from the lane's own map.
- The JS pill reaches **651** rows, not 2,600, and on that population the legacy-versus-JS
  dispersion is **0.033**, not 0.711.
- The survivor curve is non-monotone over FV 20-35 and reaches **276** rows, on a DISPLAY
  leaf; the graded boom and bust leaves read consensus FV, where only 40 graduates sit in
  the inverted band.
- The "70 percent of the population fails the conditioning event" figure is a **category
  error**: it compares realized career WAR over a count of calendar seasons against a bucket
  edge defined as projected WAR per normalised 600-PA season. Directionally the survivor
  baseline is too high; the size is not established.

**The lane: one WAG definition, baked once.** Engine WAG on the at-debut grade, every
surface reading the baked block, the other three implementations deleted. Any
sustained-performance filter becomes a display filter rather than a second definition. Gate:
a realized-PIT artifact on held-out debuted cohorts, forward-chained by debut class, with a
zero-information control permuting observed WAR within (FV tier, exposure decile) cells.
Sequence AFTER the eWAR label epoch, because E[WAR | FV, debuted, exposure] must be fitted
on the final label.

### 3.2 The valuation chain under one currency

`fv_to_6yr_avg_war` averages an eWAR measurement with an fWAR reference at a flat 0.5 and
changes denomination at FV 45. Under Part 1 both sides land in one currency for the first
time, and that reconciliation is a measurement the plan owes rather than an assumption. Two
forward curves inverted at the same predicted WAR disagree by a mean 3.5 FV; the pooled
curve saturates above FV 70 and inverts there at 500 FV per WAR; star odds exceed the card's
own star-band mass on 100 percent of rows; and the model trains on a censored label while
inverting through a curve fitted on uncensored rows only. These are one family, one epoch,
sequenced behind the label.

### 3.3 The served-board lanes

The FV-0 sentinel reaches the survivor curve and extrapolates to 11.84 WAR per year, giving
136 graduate rows a wrong boom or bust label (verification: unrendered today, so P1). On
2,479 of 4,685 rows the bust probability, surplus, band and fan are all priced at the FV20
knot while the displayed grade is not. `FV_WAR_ANCHORS` is byte-exact against the engine
today and nothing keeps it that way, which is one line of the Part 2 invariant block.

---

## Part 4. Sports Betting and the module lanes

Sports Betting has **zero WAR readers**, so this part runs in parallel with Part 1.

### 4.1 Engineering repairs

Beyond the two P0s in Part 2: `_slate_is_open` counts a postponed game as started once its
scheduled first pitch passes, which its own comment says must not happen; `min_edge_gate`
sweeps a market-pooled sample the ledger that produces it calls a defect; the shared credit
ledger is written by the test suite, so 114 of 132 booked credits never reached the provider
(latent, because the props job is gated off); and the de-vig method, the book-selection rule
and the fitted extra-innings home rate are all served objects with no registry row.

### 4.2 The pre-registered clocks, and one that would have measured nothing

**`off_vs_lhp` and `off_vs_rhp` are arithmetically IDENTICAL on every team every night
across 480 stored rows.** The handedness gate opens around 2026-09-15 and would have
measured noise. Repairing the builder is a data-capture fix, not an early look, and it must
land before the date. The other two clocks (xwOBA form and availability around 09-17,
schema 4 around 10-06) stand as registered.

### 4.3 Improvement lanes, harvested from the ideas panel

Sixty-eight gated ideas across six angles survive in the audit bundle, each carrying a
mechanism, a pre-registrable gate and a ban-check. The ones that fit this program: a
results-and-starters state-space team strength with offseason carry, fitted 2018-2025 and
served as a stacked challenger; game-level starter form from pitch-level velocity against
the pitcher's own trailing baseline, which replaces a season-to-date feature in the one term
where the vintage model's skill actually lives; an empirical conditional run PMF fitted on
eight seasons, replacing the 305-game dispersion fit; home-field and tie-mass priors from
eight seasons; the run value of a called strike from count-state run expectancy, so framing
can enter run prevention in runs rather than as a rate; and a market-residual feature screen
that uses the open market as a diagnostic target for prioritisation and never as a price
input. On the operations side: an accessible-book ROI arm, a consensus-fair edge
denominator, a per-book hold table with a fair-book concentration tripwire, credit-ledger
test isolation, and closing-line value as a pre-registered secondary criterion of the
selection bake-off.

### 4.4 Fantasy, DFS and props

`_PA_PER_START = 4.15` is not the league anchor its comment and the page claim, so every
DraftKings and FanDuel hitter total is about 3.2 percent high; `SLOT_PA` over-allocates at
every slot and is the binomial trial count for the live 1-plus-hits and 1-plus-home-run
props. Both are prerequisites to any props sub-model. The DFS archive has a grader waiting
to run against cached box scores, start probability can be scored as a calibrated number,
and the four next prop markets can be dark-graded on the harness that already exists.

---

## Part 5. Sequencing

**W0, the truth layer.** The Tier 1 and Tier 2 P0s with the invariant block, plus the
handedness capture repair before its clock opens. Nothing in W0 waits on a model decision.
Order inside W0 is set by the runbook, not by severity: the eWAR rebuild carries an
INVALIDATES clause that reaches the career_war rebase.

**W1, the replica.** Part 1 waves 1.0 through 1.2. Ends with an eWAR v3 that reproduces
published fWAR component by component within a stated tolerance, with fielding consumed from
the feed and disclosed as a hybrid.

**W2, the improvement arms.** Part 1 wave 1.3, one family per Holm step, each against the
faithful replica on a forward gate. In parallel: the betting sub-models and the ladder
triangulation.

**W3, the label epoch.** Part 1 wave 1.4 with the full re-anchor cascade, then the WAG
unification and the valuation-chain reconciliation, both of which need the final label.

**W4, the reads.** The three betting clocks on their dates, and the 2027 `RESOLVED_THROUGH`
unlock.

### 5.1 Do-not-reopen additions from this program

- The library's fielding pages as a reference for what fWAR SERVES. Cite the 2022 and 2024
  update posts instead; the library describes a retired frame.
- "fWAR is not obtainable programmatically" and "no published fWAR exists on disk". Both are
  retired by the StatsAPI sabermetrics route.
- The `.cache/win_prob` popup walker as an IFFB source. StatsAPI popup trajectory is not
  vendor IFFB, and the cache misses 2011-2017 and 2020.
- Multi-indicator range (DRS plus Statcast) outside the frozen SDR gates. It is the banned
  blend class by name.
- Crediting relievers with our own gmLI. Measured null, r 0.9947 with B-Ref's.
- The four measured nulls on the pitching negative list in section 1.3.
- Re-fitting the 57/43 split, the league-adjustment pool or the runs-per-win form against
  outcomes. They are conventions; record them.

### 5.2 What this program does not attempt

It does not re-open the eFV feature frontier, which is closed on 39 arms with zero
survivors, and it does not claim the WAR basis change buys accuracy, which was measured as a
null on 2026-09-04. It does not build fielding from components, because the components are
not on disk. And it does not touch the betting model's served selection rule, which belongs
to the bake-off already registered on 2026-09-05.

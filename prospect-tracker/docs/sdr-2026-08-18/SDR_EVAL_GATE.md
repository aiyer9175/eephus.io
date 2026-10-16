# G-A: sdr_eval, the MLB SDR validation gate (pre-registered 2026-08-18)

STATUS: REGISTERED, DATA-BLOCKED. Clauses frozen before any SDR data exists in
this environment. Results are empty and stay empty until a defense-card drop
passes sdr_intake --validate and its census is committed. The census fixes the
frame BEFORE any clause is measured; nothing below is read early.

## The question

Is Will's SDR (the defense-plus skill composite: range, arm, framing,
blocking, DP pivot; catcher components per 25_catcher_components.py) a better
measurement of MLB defensive value than the incumbents (B-Ref rfield, Savant
OAA/FRP), on forward legs, at the coverage his drop declares?

## Frame (census-dependent, fixed at census commit, never after)

- Seasons and positions: exactly the drop's declared coverage. Expect a
  tracking-era cliff; a has-SDR indicator is an ERA INDICATOR and is
  inadmissible in any trainable use.
- Row unit: player-season-position per the declared defense contract
  (sdr_intake.DEFENSE_CARD_CONTRACT).
- Innings floor: the drop's own reliability convention if it ships one, else
  Inn >= 200 stated as policy.

## Clauses (frozen)

1. C1 SELF-PERSISTENCE (forward, gated): year-over-year Spearman of SDR runs
   per inning vs itself, players with qualifying innings both seasons,
   compared to the SAME statistic for rfield and OAA on the SAME player set.
   SDR must beat BOTH incumbents on the point estimate AND clear a
   player-clustered bootstrap 95% lower bound above the better incumbent, or
   the clause fails.
2. C2 TEAM FORWARD (gated): team-season SDR sum predicting next-season team
   runs allowed (defense leg: runs allowed residualized on team pitching FIP,
   the ewar.py convention), vs the same construction on rfield and OAA.
   Same beat-both + LB rule.
3. C3 AGREEMENT (descriptive, reported never gated): correlation with realized
   defensive value against the two named baselines from the record: FG fFld
   (Spearman 0.28 on the prospect frame) and prospect_def_value (0.68). These
   numbers belong to their own frames and are context, not the bar.
4. C4 FACE VALIDITY (reported): top/bottom 15 by position, eyeballed, named
   in Results with any absurdity called out.

Floors are derived on the census frame at measurement time (never reused from
another frame). Holm across C1/C2. A noise twin (permuted within
position-season) accompanies each gated clause; a clause is not creditable if
its twin also clears.

## What this gate does NOT decide

Display (W2 ships on validated-descriptive basis per the master plan), the
eWAR merge (G-B), and any eFV use (G-C then W4) have their own gates.

## Amendment 2026-10-15: the in-house drop, the frame operationalized, and the amended estimand (owner decisions EW3-18, EW3-23, EW3-5)

Committed alone, docs only, before the drop exists, before any census and before any
statistic below is computed. No SDR value, no year-to-year number and no club number
for SDR was read to write it. The clauses above stand as frozen; this part fixes what
the census left open and adds one owner-ordered leg.

### A1. What changed since registration

- **The data block is gone (EW3-18).** Will's method is in the repo (BaseballR/
  defense-plus); only its raw inputs were on his machine, and they are public. Task
  EWAR_SDR_INHOUSE fetches them into `.cache/sdr/` (FanGraphs fielding leaderboard
  JSON with OAA, DRS and its parts, FRP, UZR and CFraming; Savant OAA, catcher
  framing, blocking, pop time and arm) and runs his stages unedited through
  `tools/sdr_inhouse.py`, which only redirects his home-directory paths and sets the
  season window (A2). The OAA/DRS blend ban outside these gates does not apply: this
  is the SDR gate route the ban names.
- **Timing (EW3-5).** This read runs on 2026-10-15 and is recorded as an
  OWNER-WAIVED EARLY READ.

### A2. The drop and its coverage rule (fixed before the census)

- **SDR, per Will's card.** `sdr_runs` is `build_defense_card.py`'s `def_runs`, which
  is 06_total_defense_plus.py's `dplus_runs`: within (position, season) z-scores of
  OAA, DRS and FRP, weighted by each system's year-to-year reliability inside the
  window, scaled to runs by the position's DRS sd and shrunk by Inn / (Inn + 269).
  Row unit: player-season-position, positions C, 1B, 2B, 3B, SS, LF, CF, RF.
- **Window.** Will ships one season from a trailing five-season window (2021 to 2025,
  ship 2025). The adapter keeps it per season S: window max(2016, S - 4) to S, ship S.
  Statcast OAA and FRP begin in 2016, so the first season with a year-to-year pair in
  its own window is 2017: coverage is 2017 to 2026. No season's SDR reads a later
  season.
- **Innings floor.** 300 innings at the position, the drop's own convention
  (06's MIN_INN), in place of the registration's fallback 200.
- **Components** (`range_runs` DRS rPM, `arm_runs` DRS rARM, `dp_runs` DRS rGDP,
  `framing_runs` FanGraphs CFraming, `blocking_runs` Savant catcher blocking runs,
  2018 on) are the sources' own runs on the same row, carried for the census and the
  intake's non-range rule. They are not parts of `sdr_runs`.
- **Not run, named:** the stages that need Will's private files (deep_mlb.parquet,
  bayesian_curves, grades_long.parquet, body.parquet, the Savant jump and directional
  files) are inventoried in `docs/sdr-2026-08-18/SDR_INHOUSE_RUNBOOK.md` and not run.

### A3. Clause operationalization (C1 to C4)

- **Unit for C1 and C2: the player-season.** B-Ref `runs_field` exists only per
  player-season, so all three metrics are read per player-season over the player's
  frame rows (positions at 300+ innings):
  - SDR rate = sum of `sdr_runs` / sum of innings;
  - OAA rate = sum of FanGraphs-hosted OAA / sum of innings over the same rows where
    OAA is present (Savant's OAA as FanGraphs republishes it per position; Savant's
    own leaderboard aggregates by primary position and is not row-matched);
  - rfield rate = B-Ref `runs_field` / B-Ref `Inn`, summed over stints, from
    `.cache/war_daily/bat.parquet` as it stands at the read (its sha256 and modified
    time printed before any statistic).
- **Pairs.** Predictor seasons 2017 to 2025 (outcome seasons 2018 to 2026); a pair is
  a player in the frame in Y and Y+1. Pairs touching 2020 are included (per-inning
  rates); the pooled statistic without them is reported beside, deciding nothing.
- **C1 player set.** Pairs with all three rates defined in both seasons. OAA does not
  rate catchers, so catchers leave the pooled clause; they are reported per position
  (A5).
- **C1 statistic and rule.** Spearman of rate(Y) with rate(Y+1), pooled, per metric.
  d = rho(SDR) - max(rho(rfield), rho(OAA)), the better incumbent fixed at the point
  estimate. Player-clustered bootstrap (players drawn with replacement with all their
  pairs), B = 2,000, seed 20261015. LB95 = the 2.5th percentile of d; one-sided p =
  the share of draws with d <= 0. C1 passes when rho(SDR) beats both incumbents at
  the point, LB95 > 0, Holm (with C2, alpha 0.05) rejects, and its twin fails.
- **C2 club construction.** Each player-season's runs over its frame innings, rate x
  frame innings for every metric (for SDR and OAA that is their own sum), are
  allocated to clubs by the player's frame innings with each club (FanGraphs fielding
  leaderboard split by club). Club sum S_c(Y) per metric. Target: club runs allowed in
  Y+1 residualized on club FIP runs (FanGraphs club pitching totals: R on FIP x IP /
  9, ordinary least squares within the season across the 30 clubs), the residual
  standardized within its season and its sign reversed so that fewer runs than FIP
  implies ranks higher. Predictor sums standardized within season. Franchises are
  joined across seasons by FanGraphs teamid. Statistic: Spearman of S_c(Y) with the
  target, pooled over 270 club-season pairs. Rule and bootstrap as C1, the bootstrap
  player-clustered (players drawn with replacement, every club sum recomputed,
  outcomes fixed); a club-clustered bootstrap (franchises drawn) is reported beside.
- **Holm** across C1 and C2 at alpha 0.05 on the one-sided p. **The twin** for each
  clause: `sdr_runs` permuted within (position, season) among frame rows, seed
  20261016, one draw, scored by the same rule; a clause is not creditable if its twin
  passes.
- **Verdict.** G-A PASS when C1 and C2 both pass; PARTIAL when one passes; FAIL when
  neither does. A null is a complete result.
- **C3 (reported).** Same-season Spearman of SDR rate with rfield rate, with UZR rate
  (2017 to 2024) and with FanGraphs' Defense per inning, on the player-season frame.
  The registration's baselines FG fFld 0.28 and prospect_def_value 0.68 belong to the
  prospect frame; prospect_def_value has no MLB player-season value, so neither number
  is recomputed here and both stay context.
- **C4 (reported).** Top and bottom 15 by `sdr_runs` at each position in 2026, named,
  with any absurdity called out in Results.

### A4. The amended estimand (owner decision EW3-23, EBR_GATE.md part 11.2)

EW3-23 makes next-season realized runs from an independent source the deciding target
for fielding legs, and EBR_GATE.md 11.2.2 says how a blend is scored: leaving one
source out. Two cells, computed after C1 to C4, on the C1 pair frame and bootstrap:

- **C5, deciding for the EW3-23 read (Holm family k = 1).** The 11.2.2 blend rule. SDR
  reads two fielding systems: DRS, and Statcast (OAA and FRP are one system). For each
  system S, Will's 06 is re-run with S removed from its source list (the adapter's
  `no_drs` and `no_statcast` variants; nothing else changes) and that SDR is scored on
  S in Y+1 against the incumbent that does not read S:
  - S = DRS: SDR without DRS (OAA and FRP) against OAA, target FanGraphs DRS per
    inning in Y+1;
  - S = Statcast: SDR without Statcast (DRS) against B-Ref rfield, target FRP per
    inning in Y+1.
  The per-system gap is rho(SDR without S) - rho(incumbent), on the target; the cell's
  gap is the mean of the two, one cell inside the same player-clustered bootstrap
  (B = 2,000, seed 20261015). C5 is a WIN when the gap's LB95 > 0 and its twin (each
  SDR variant permuted within position and season) does not also clear; LOSS when the
  upper end of its 95% interval is below 0; otherwise UNRESOLVED.
- **C6, reported beside, deciding nothing.** The one fielding-runs series none of the
  three metrics reads: FanGraphs UZR per inning in Y+1 (published through 2024, so
  predictor seasons 2017 to 2023, non-catchers; UZR does not rate catchers). Full SDR,
  rfield and OAA are each scored on it, with C1's rule printed. Disclosed: UZR and DRS
  share their batted-ball data provider (Sports Info Solutions), so the target is
  independent of the method, not of the data.
- **Per position (A5)** each cell is also printed by position, deciding nothing.

### A5. Per-position results (reported, never gated)

For each position, on player-position rows at 300+ innings in both Y and Y+1:
self-persistence Spearman of SDR, rfield (player-season, disclosed as not
position-specific) and OAA (not for catchers), the SDR minus best-incumbent gap with
its player-clustered LB95, and C6's UZR cell. Catchers add the self-persistence of
the framing and blocking components. No Holm; no position is credited from these.

## Results

PENDING. Data-blocked at registration (2026-08-18): no SDR data exists in the
repo or the environment; defense-plus has no export adapter. See
docs/sdr-intake-request-2026-08-18.md for what was asked of Will.

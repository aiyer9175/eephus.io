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

At registration (2026-08-18): data-blocked; no SDR data existed in the repo or the
environment and defense-plus had no export adapter
(docs/sdr-intake-request-2026-08-18.md).

### 2026-10-15: G-A read once, OWNER-WAIVED EARLY READ (EW3-5). Verdict: FAIL

Artifact `data/sdr_eval.json` (tools/sdr_eval_gate.py, one run, stdout and stderr kept with
the task's report). Inputs: the accepted drop `sdr_defense_card__2026-10-15.csv` (sha256
8a41d1c2...358e, 3,466 rows, census committed first at 133b0566); `.cache/war_daily/bat.parquet`
sha256 e9571c42...fd55, modified 2026-10-16T02:02Z; fetch and run manifests under
`.cache/sdr/`. Amendment 2026-10-15 fixed every choice before the drop existed (0cffb4be); the
adapter and this tool were committed before the drop was built (a2200821).

Adapter receipt, read before any clause: Will's 06 run here for 2025 reproduces his PART2
report (system reliabilities FRP 0.515, OAA 0.469, DRS 0.400 against his .52, .47, .40; his
2025 board order Bailey, Witt, Kirk, Hayes, Rafaela, Crow-Armstrong, Winn, Hoerner).

| Clause | SDR | rfield | OAA | d vs better | LB95, UB95 | Holm p | Twin | Result |
|---|---|---|---|---|---|---|---|---|
| C1 self-persistence (1,644 player-season pairs, 527 players, 2017 to 2025) | 0.4031 | 0.3809 | 0.4696 | -0.0665 (OAA) | -0.1055, -0.0277 | 0.9995 | fails (SDR -0.0146) | FAIL: SDR beats rfield, loses to OAA |
| C2 club runs allowed beyond FIP, Y+1 (270 club-season pairs) | 0.1499 | 0.1808 | 0.1345 | -0.0308 (rfield) | -0.0792, +0.0615 | 0.6215 | fails (SDR 0.0018) | FAIL: SDR beats OAA, loses to rfield |

- Without pairs touching 2020: C1 SDR 0.4014, rfield 0.3894, OAA 0.4786 (1,423 pairs); C2 SDR
  0.1608, rfield 0.1716, OAA 0.0991. Same ordering on C1; C2's SDR-rfield gap narrows.
- C2's club-clustered interval, beside: -0.1230 to +0.0601.
- **C3 (reported).** Same-season Spearman of the SDR rate: with rfield 0.6419 (3,207
  player-seasons), with UZR 0.6149 (2,108, 2017 to 2024), with FanGraphs Defense 0.6967.
- **C4 (reported), 2026 boards.** Face-valid at the top of every position (Crow-Armstrong
  +19.7 and Rafaela +13.6 in CF; Witt +11.8 and Winn +11.1 at SS; Turang +13.3 at 2B; Olson
  +9.9 at 1B; Bregman +10.9 at 3B; Dingler +13.6 at C). No absurdity found; rows worth a
  look against the players' other seasons: the largest negatives at premium positions (Trea
  Turner -10.5 and Willy Adames -10.4 at SS, Julio Rodriguez -6.0 in CF), and at catcher Cal
  Raleigh -4.6 and Patrick Bailey only +5.5, because SDR for catchers
  rests on DRS and FRP alone (OAA does not rate catchers) and carries framing only as far as
  those two systems do. Full top and bottom 15 per position are in the artifact.
- **C5, the EW3-23 leg (EBR_GATE.md 11.2.2), deciding for that read: UNRESOLVED.** Gap +0.0044
  (LB95 -0.0146, UB95 +0.0223, 1,644 pairs): SDR without DRS 0.2925 against OAA 0.2891 on
  DRS(Y+1) (gap +0.0035); SDR without Statcast 0.3328 against rfield 0.3275 on FRP(Y+1) (gap
  +0.0053). Twin gap -0.3031, does not clear.
- **C6 (reported).** On UZR(Y+1), the series none of the three reads (1,247 pairs, predictor
  seasons 2017 to 2023): SDR 0.2787, OAA 0.2736, rfield 0.2233; SDR leads at the point,
  d +0.0050, LB95 -0.0248.

**Per position (A5, reported, never gated).** Self-persistence on player-position rows, SDR
against the better incumbent:

| Pos | Pairs | SDR | rfield | OAA | d (better) | LB95, UB95 | On UZR(Y+1): SDR, rfield, OAA |
|---|---|---|---|---|---|---|---|
| C | 321 | 0.6145 | 0.0248 | n/a | +0.5897 (rfield) | +0.4510, +0.7161 | n/a (UZR does not rate catchers) |
| 1B | 219 | 0.3501 | 0.2942 | 0.2999 | +0.0502 (OAA) | -0.0468, +0.1431 | 0.2329, 0.1612, 0.2222 |
| 2B | 192 | 0.3967 | 0.3712 | 0.3616 | +0.0256 (rfield) | -0.1313, +0.1928 | 0.2480, 0.1322, 0.2662 |
| 3B | 214 | 0.4684 | 0.3935 | 0.4154 | +0.0530 (OAA) | -0.0239, +0.1272 | 0.3737, 0.2698, 0.3926 |
| SS | 227 | 0.4435 | 0.4081 | 0.4388 | +0.0047 (OAA) | -0.0727, +0.0823 | 0.1134, 0.1578, 0.0840 |
| LF | 172 | 0.4210 | 0.3655 | 0.4316 | -0.0106 (OAA) | -0.1107, +0.0883 | 0.2345, 0.1974, 0.2972 |
| CF | 210 | 0.5525 | 0.4040 | 0.5290 | +0.0235 (OAA) | -0.0743, +0.1133 | 0.4175, 0.2768, 0.3739 |
| RF | 204 | 0.5069 | 0.3776 | 0.4579 | +0.0490 (OAA) | -0.0311, +0.1319 | 0.3339, 0.2351, 0.3049 |

Catchers also: framing component self-persistence 0.6139 (321 pairs), blocking 0.5248 (277).
The catcher cell is the one place SDR clears its better incumbent at LB95; it is reported, not
credited, and B-Ref's catcher rfield (rSB plus rCERA, no framing) is a weak incumbent there.

**Post-hoc observation, disclosed, deciding nothing.** Within position SDR leads OAA at the
point at six of seven non-catcher positions, yet loses the pooled C1. The pooled OAA rate
carries persistent differences in position means among 300-inning regulars (per 1,000
innings: CF +4.49, SS +1.37, LF -2.60, RF -1.42), which a player keeps when he keeps his
position; SDR is centred within position and season by construction. Centring each rate
within (primary position, season) after the fact gives SDR 0.3994, OAA 0.3823, rfield
0.3516 on the same pairs. This was computed after the read, by a one-off command recorded
in the task report, and changes no clause: C1 as registered is FAIL. Any position-centred
read would need its own registration and a frame it has not seen (the 2026 to 2027 pairs).

**What this licenses.** No claim that SDR is a better measure of MLB fielding value than
rfield or OAA. SDR is not served and does not enter eWAR on this gate; G-B (the merge gate)
is untouched by this read. The descriptive per-position and catcher cells may be quoted as
measurements with their frames, never as a validation.

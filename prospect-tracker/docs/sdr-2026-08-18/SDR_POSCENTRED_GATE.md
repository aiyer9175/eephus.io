# SDR_POSCENTRED_GATE: the position-centred G-A re-check on unseen pairs (registered 2026-10-16)

STATUS: REGISTERED 2026-10-16, NOT READ. Read once, not before 2027-11-01, by the queued task
SDR_POSCENTRED_READ. This document is committed ALONE, docs only, before the gate's tool exists
and before any number of its estimands exists: its outcome season (2027) has not been played. A
change before the read is a dated note in part 13, committed alone before the read; nothing above
part 13 is edited after this commit.

Owner decision EW3-33 (2026-10-16, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): SDR-GA-Q1 answered
"re-register + catcher now". Part 1 is `docs/sdr-2026-08-18/SDR_CATCHER_GATE.md` (read 2026-10-16,
PARTIAL). This is part 2 (task SDR_POSCENTRED_REGISTER): G-A's self-persistence clause re-asked with
every rate centred within (primary position, season), G-A's C2 and C5 legs unchanged, read only on
the 2026 to 2027 pairs after the 2027 season. The owner's waiver of look days (EW3-5, 2026-10-14)
does not move this read: it needs data that does not exist yet (the 2027 season), which is the one
reason EW3-5 keeps to wait.

## 0. What was read before this registration

- **G-A, read once 2026-10-15** (`SDR_EVAL_GATE.md`, Results; FAIL). C1 pooled self-persistence on
  1,644 player-season pairs, predictor seasons 2017 to 2025: SDR 0.4031, rfield 0.3809, OAA 0.4696;
  d vs OAA -0.0665 (LB95 -0.1055, UB95 -0.0277). C2 on 270 club-season pairs: SDR 0.1499, rfield
  0.1808, OAA 0.1345; d vs rfield -0.0308 (LB95 -0.0792, UB95 +0.0615). C5 gap +0.0044 (LB95
  -0.0146, UB95 +0.0223), UNRESOLVED. C6 on UZR(Y + 1): SDR 0.2787, OAA 0.2736, rfield 0.2233. A5 per
  position: SDR leads OAA at the point at 6 of 7 non-catcher positions, none at LB95.
- **G-A's post-hoc observation** (deciding nothing): the pooled OAA rate keeps persistent
  position-mean differences among 300-inning regulars (per 1,000 innings: CF +4.49, SS +1.37, LF
  -2.60, RF -1.42); centring each rate within (primary position, season) after the read gave SDR
  0.3994, OAA 0.3823, rfield 0.3516 on G-A's pairs. That one-off command was not kept verbatim in the
  repository; part 3 fixes this gate's own construction, so the post-hoc numbers are context and not
  a target this gate reproduces.
- **SDR_CATCHER_GATE, read 2026-10-16: PARTIAL** (E1 FAIL, E2 PASS); nothing served, nothing handed
  to eWAR.
- **The fielding triangulation** (`docs/ewar/FIELDING_TRIANGULATION_GATE.md`, read 2026-10-16: FAIL)
  centres every reading within (position, season) at row level, innings-weighted, on its own frame.
- **The 2026 season** was read as an outcome season: G-A's (2025, 2026) pairs (C1, C2, C5, A5), G-A's
  C4 2026 boards, the triangulation's read and the catcher gate. **Never computed on any frame:** a
  (2026, 2027) pair unit and every 2027 value; neither exists today.
- **Facts used here, no estimand:** the sha256 of the frozen predictor files (part 2); the census's
  371 drop rows in 2026 (`data/sdr_census.json`).

## 1. The question

Whether SDR persists from 2026 to 2027 better than OAA and B-Ref rfield, on player pairs no read
has seen, once each metric's rate is centred within (primary position, season), so that a
position's level in a source cannot pass for a player's skill. G-A's club leg (C2) and the
EW3-23 leg (C5) are asked again on the same unseen season, unchanged.

## 2. Frame (fixed here)

- **One pair season.** Predictor season Y = 2026, outcome season Y + 1 = 2027. No other season pair
  is scored by a deciding leg.
- **Rows, floor, unit and rates: G-A's, unchanged.** The drop's player-season-position rows at 300+
  innings (`SDR_EVAL_GATE.md` A2), read per player-season (A3): SDR rate = sum of `sdr_runs` / sum of
  innings; OAA rate = FanGraphs-hosted OAA over the rows where OAA is present / those rows' innings;
  rfield rate = B-Ref `runs_field` / `Inn`, summed over stints. Nothing in Will's method is edited
  or refitted.
- **Predictor values are frozen today.** Copies made 2026-10-16 in `.cache/sdr/frozen_predictor_2026/`
  (listed with their hashes in its `SHA256SUMS.txt`). Every 2026 value of every leg comes from these
  files; the read verifies each sha256 before any statistic, and a mismatch STOPS the read.

| File (frozen copy) | Source path at freeze | sha256 | Supplies (season 2026) |
|---|---|---|---|
| `sdr_defense_card__2026-10-15.csv` | `data/drops/wills/` | 8a41d1c20ce37a45fec3150fcf87ceae67f74a16d77cbdf53f44edc44691358e | SDR (`sdr_runs`), rows, innings |
| `06_defense_plus_2026__no_drs.csv` | `.cache/sdr/home/defense_plus/reports/` | bba48de839389910f2832ef285b464631816bdd503478ead6e8424853ae7762e | C5 variant without DRS |
| `06_defense_plus_2026__no_statcast.csv` | same | 39ff933faae677d6cf1318137e95012be2f9e273ce6c473504ce556ba67b77cd | C5 variant without Statcast |
| `06_defense_plus_2026.csv` | same | 86ffa794d39dce368185432d5cce91b104260d8b14cca73dbafe5626135c0822 | the full run behind the drop (check only) |
| `fg_field_full_2026.csv` | `.cache/sdr/home/defense_plus/data/raw/` | 58e53c3a5ca76befeae87a5d5d32035da9fb7073f88275c69914b3263fe671cc | OAA, DRS, FRP, Defense |
| `fg_field_split_2026.csv` | same | a6c4d620b5bf4f87d949d2226633f0d89d0491da452811e20d67fd7f62594713 | C2 club shares |
| `fg_team_pit_2026.csv` | same | aa00708026f99132db490403d9be6750028bb02a32bd7d0ab7584e5b949dc023 | (2026 club totals; not a C2 input, kept for R8) |
| `bat.parquet` | `.cache/war_daily/` | e9571c428cb4db444e4b8214bb9adc5834925529e7d10db4271993f79fc3fd55 | rfield 2026 (the file G-A read) |

- **Outcome values, built at the read.** 2027 SDR and its two variants: `tools/sdr_inhouse.py`
  extended to season 2027 (window 2023 to 2027, ship 2027, the same declared patches, Will's files
  byte for byte), fetching without `--force` so every 2016 to 2026 raw file keeps its hash; 2027
  OAA, DRS, FRP and club shares from the 2027 FanGraphs fielding fetch; 2027 rfield from
  `.cache/war_daily/bat.parquet` as it stands at the read (sha256 and modified time printed before
  any statistic); 2027 club runs and FIP from the FanGraphs club pitching totals for C2's target.
- **Data-exists precondition (checked first).** The 2027 regular season is over; the FanGraphs
  fielding leaderboard for 2027 carries OAA, DRS and FRP; B-Ref's war_daily carries 2027
  `runs_field`; FanGraphs club pitching totals for 2027 exist for 30 clubs. Otherwise the read stops
  with 'BLOCKER: date <the first date the missing data exists>'.
- **Never used:** any consensus FV, prospect grade or FV-level cell (no stratification by
  consensus-FV level anywhere); any betting column; the eFV reserved frames; `backtest.run_backtest`.

## 3. C1c: position-centred self-persistence (deciding)

```
P(i, Y)      = the position of player i's frame row with the most innings in season Y
               (tie: the earlier of C, 1B, 2B, 3B, SS, LF, CF, RF)
eligible     = SDR, OAA and rfield rates all defined (G-A A3) and P(i, Y) is not C
mu_m(p, Y)   = unweighted mean of rate_m over the season's eligible player-seasons with P = p
               (a cell with fewer than 8 eligible player-seasons is dropped; its members are counted
               and printed)
c_m(i, Y)    = rate_m(i, Y) - mu_m(P(i, Y), Y)                 m in {SDR, OAA, rfield}
pairs        = players eligible in 2026 and in 2027 (P may differ between the seasons)
rho_m        = Spearman( c_m(i, 2026), c_m(i, 2027) )
d            = rho_SDR - max(rho_OAA, rho_rfield)              better incumbent fixed at the point
rho_PT       = Spearman( c_Inn(i, 2026), c_SDR(i, 2027) )      innings centred in the same cells;
                                                               more innings ranks higher
d_PT         = rho_SDR - rho_PT
```

Catchers stay out (OAA does not rate them; their own gate is SDR_CATCHER_GATE). Each season's rate
is centred in that season's own cell, so a player who changes position is compared with his new
position's mean.

**Comparators (the null-comparator rule).** Z, the zero comparator: every player at the cell mean,
Spearman 0 by definition; C1c clears Z when LB95(rho_SDR) > 0. PT, the playing-time comparator: d_PT
as above; SDR is shrunk by Inn / (Inn + 269), so part of its rate can carry playing time.

**Bootstrap.** Players drawn with replacement with their pair (one pair per player here), B = 2,000,
seed 20271101; every statistic of the cell recomputed on each draw; the cell means mu are held at
their full-frame values (centring is a property of the frame, disclosed). LB95 = 2.5th percentile;
one-sided p = share of draws with d <= 0. The bootstrap sd of d and MDE95 = 1.96 x that sd are
printed before any point estimate.

**C1c passes** when all hold: rho_SDR beats both incumbents at the point; LB95(d) > 0; LB95(rho_SDR)
> 0 (clears Z); LB95(d_PT) > 0 (clears PT); Holm (part 6) rejects; its twin does not pass.

## 4. C2: club runs allowed beyond FIP (deciding, G-A's leg unchanged)

G-A A3's construction on the one pair season: each 2026 player-season's runs over its frame
innings (rate x frame innings) allocated to clubs by the frozen 2026 club split, club sums
standardized within 2026, against 2027 club runs allowed residualized on club FIP runs (ordinary
least squares across the 30 clubs, residual standardized, sign reversed); franchises joined by
FanGraphs teamid; 30 club pairs. Rates are G-A's uncentred rates (the leg is unchanged). Statistic,
beat-both rule and player-clustered bootstrap (players drawn, every club sum recomputed, outcomes
fixed) as G-A, B = 2,000, seed 20271101; the club-clustered interval is printed beside.

The one addition, under the null-comparator rule: C2 also needs LB95(rho_SDR) > 0 (clears Z).

## 5. C5: the EW3-23 leg (deciding for that read, Holm family k = 1, G-A's leg unchanged)

G-A A4 on G-A's C1 pair frame (uncentred, all three rates defined in both seasons) for predictor
season 2026: per system S in {DRS, Statcast}, rho(SDR without S (2026), T_S(2027)) minus
rho(incumbent_S (2026), T_S(2027)), with T_DRS = FanGraphs DRS per inning and the incumbent OAA, and
T_Statcast = FRP per inning and the incumbent rfield; gap = mean of the two. Same bootstrap (B =
2,000, seed 20271101). WIN when LB95(gap) > 0, LB95(g_Z) > 0 (g_Z = mean over S of rho(SDR without
S, T_S); the null-comparator addition) and its twin does not clear; LOSS when UB95(gap) < 0;
otherwise UNRESOLVED.

## 6. Holm, twins, verdict

- **Holm** across C1c and C2 at alpha 0.05 (k = 2) on the one-sided p. C5 is its own family.
- **The twin** of every deciding leg: `sdr_runs` and both variants' runs permuted within (position,
  season) among the frame rows of each season (G-A's `permute_sdr`), seed 20271102, one draw, scored
  by the same rules (rates recomputed, then centred for C1c). A leg whose twin passes is not credited.
- **Verdict.** PASS when C1c and C2 both pass; PARTIAL when one passes; FAIL when neither does. C5's
  disposition (WIN, LOSS, UNRESOLVED) is recorded beside. A null is a complete result.

## 7. Before the read: dry run and planted recovery

- **Dry run** on a synthetic fixture with nulls (a player without a B-Ref row, without OAA, without a
  2027 row, without a variant value, a cell under 8 members, a primary-position tie) through the
  whole reporting path; it writes nothing.
- **Worlds on the real 2026 to 2027 design.** The real frame's players, rows, positions, innings and
  club shares; every metric, variant and target value replaced by simulation (seed 20271103; no real
  metric value is read). A talent t ~ N(0, 1) per player and an offset o_p ~ N(0, 1) per position,
  both fixed across the two seasons. Each world is scored by parts 3 to 6 with B = 2,000.
  - **PLANTED.** SDR and both variants = t + noise sd 0.5; OAA = t + o_p + noise sd 1.2; rfield = t +
    noise sd 1.5; the C5 targets in 2027 = t + noise sd 1.0; the 2027 club target = the club's
    innings-share-weighted sum of t over its 2027 frame players, standardized, + noise sd 0.5. C1c
    must read PASS and C5 must read WIN. C2's planted result is printed; if C2 cannot pass even here,
    the record says so before the read: the leg cannot resolve on 30 club pairs.
  - **NULL.** Every value noise (t = 0, o_p = 0). Every leg must FAIL, and Z must not be cleared in
    C1c, C2 or C5.
  - **POSITION ONLY.** Every metric = o_p + noise sd 1.0, no talent. C1c must not read PASS; G-A's
    uncentred C1 rule is printed beside on the same world, to show the offset persistence the
    centring removes.
  - **PLAYING TIME ONLY.** Every rate = 0.5 x z(innings within its cell) + noise sd 1.0, no talent.
    PT must stop C1c (C1c must not read PASS).
  If PLANTED fails C1c or C5, or NULL, POSITION ONLY or PLAYING TIME ONLY reads PASS on any leg, the
  read does not run: the defect is fixed and recorded in part 13 before the read.

## 8. Reported beside, deciding nothing

- **R1** G-A's uncentred C1 on the 2026 to 2027 pairs.
- **R2** C1c on position-stable pairs only (the same P in both seasons).
- **R3** C1c with innings-weighted cell means.
- **R4** per position (centring within one position is a constant shift, so these are plain
  within-position cells): SDR, OAA and rfield persistence, d and its LB95.
- **R5** C5 with every rate and target centred as in part 3.
- **R6** C6 on UZR per inning in 2027, only if FanGraphs publishes 2027 UZR (it published none for
  2025 or 2026 at G-A's fetch); otherwise "not run".
- **R7** C3 same-season agreement in 2027 and C4's 2027 boards (top and bottom 15 per position).
- **R8** whether `tools/sdr_inhouse.py` run at the read rebuilds the 2026 rows byte for byte from the
  then cache (the frozen rows decide either way).

## 9. Power, for scale (no statistic computed)

Arithmetic on G-A's published intervals, scaled by the square root of the pair counts; no value of
this gate's frame was computed. The read prints its own bootstrap sd and MDE95 before any point
estimate, and where MDE95 exceeds a gap the record says the leg could not see it.

- C1: G-A's d interval on 1,644 pairs has half-width 0.039. G-A averaged 183 pairs per predictor
  season, so one season's pairs give a half-width near 0.12. The post-hoc centred gap SDR minus OAA
  was +0.017, about a seventh of that.
- C2: half-width 0.070 on 270 club pairs; on 30, near 0.21.
- C5: half-width 0.0185 on 1,644 pairs; on one season, near 0.055; G-A's gap was +0.0044.

## 10. What each result licenses

- **Until the read.** SDR stays out of eWAR. The one exception the owner named, a catcher part if
  SDR_CATCHER_GATE passed, does not apply: that gate read PARTIAL on 2026-10-16.
- **PASS.** G-A's question re-asked on the position-centred estimand passes on unseen pairs. SDR
  becomes eligible as a fielding reading for eWAR v3 only through G-B
  (`docs/sdr-2026-08-18/EWAR_V3_MERGE_GATE.md`) and a dated `docs/ebr-2026-09-30/EBR_GATE.md` part 11
  amendment, scored by the skill look then in force. The registry row `sdr_mlb` records the read.
  No served number moves by this read itself; any claim names this frame.
- **PARTIAL.** The passing leg may be quoted as a measurement with its frame; nothing is served and
  nothing enters eWAR.
- **FAIL.** G-A's FAIL stands with this re-check; SDR stays outside eWAR; this estimand is not
  re-registered without a new owner decision.
- G-A's 2026-10-15 verdict and record are never rewritten; this gate's result is a dated note there.

## 11. Registered expectations (predictions, not measurements)

- C1c: SDR ahead of OAA and rfield at the point by less than 0.05; LB95(d) does not clear 0, because
  one season's pairs cannot see a gap of that size (part 9).
- C2: FAIL (30 club pairs).
- C5: UNRESOLVED.
- Verdict: FAIL.

## 12. Tool, artifact, tests and the queued read

- **Queued task SDR_POSCENTRED_READ**, not before 2027-11-01, requiring this registration. It builds
  `tools/sdr_poscentred_gate.py` (reusing `tools/sdr_eval_gate.py`'s `player_seasons`, `pairs`,
  `club_target`, `club_contrib`, `c5_read`, `permute_sdr` and `holm` without editing them; `--dry-run`
  on the fixture, `--simulate` for part 7, then the read once with its stdout and stderr teed to the
  task's output directory before anything else runs) and `test_sdr_poscentred_gate.py`; artifact
  `data/_labs/sdr_poscentred/sdr_poscentred_eval.json` (tracked; `data/_labs` ships in neither deploy
  consumer). It records the result in part 13, a dated pointer note in `SDR_EVAL_GATE.md` and the
  `sdr_mlb` registry notes, in one commit.
- **Calendar.** The read does not run on a registered look day of another gate (2027-11-09 and
  2027-11-16 among them; check `docs/*GATE*.md` on the day). On an exception after scoring began, the
  read STOPS without rerunning and writes the owner question.
- Read once; never rerun on the same frame.

## 13. Results and dated notes

PENDING. Not read; the 2027 season does not exist at registration.

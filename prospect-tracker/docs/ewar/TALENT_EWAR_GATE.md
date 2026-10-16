# Talent eWAR: per-part reliability, a posterior band and a shrunk total (talent_ewar_v1)

Task EWAR_INNOVATE_LEDGER, item (d) (owner decisions EW3-20 and EW3-23, 2026-10-15; the ewar-map
plan's innovator item 4). This document is committed ALONE, with its pin test
`test_ewar_innovate_registration.py`, before the construct's code exists and before any number of
its estimands is computed. A change after the first number is a dated note in part 8, never an
edit above it.

STATUS: REGISTERED; READ 2026-10-16, NOT VALIDATED on both sides (part 8).

## 0. What it is

- **WAR is shown as a point, while its parts carry very different noise.** A season's batting runs
  repeat far better than its fielding or baserunning runs. Talent eWAR gives each measured part
  its own reliability, shrinks each part's rate toward the season's mean by that reliability, and
  sums the shrunk parts beside the realized total; a posterior band per player-season says how much
  of the season was signal.
- **Its place in the owner's two numbers (EW3-20).** The headline eWAR is the predictive,
  talent-true number; "eWAR realized" records actual runs. This construct is the uniform rule the
  headline can apply to the parts that carry no admitted skill arm. It is built here on FanGraphs'
  frame (the frozen fWAR vintage), the base eWAR v3 departs from, so it can be read now; it changes
  no served number and admits nothing.
- **The deciding target is next-season realized runs** (EW3-23, `docs/ebr-2026-09-30/EBR_GATE.md`
  part 11.2), not published fWAR(Y+1), which is reported as a secondary comparison that decides
  nothing. The spec's phrase "validated on ranking fWAR(Y+1)" is read through EW3-23, which the
  same spec makes binding on every registration and read; this default is recorded as an owner
  question in the task's report.
- **Development frames for selection.** Constants are fitted on predictor seasons 2010 to 2015;
  the read uses predictor seasons 2016, 2017 and 2018. The eWAR v3 skill look's frame (predictor
  seasons 2021 to 2024) and its holdout are never read here.

## 1. Data (read from caches; this task fetches nothing for this item)

- The frozen fWAR vintage `data/fwar_vintage.json` (vintage `2026-10-02-57bf90f7143e`): hitting
  `batting`, `baseRunning`, `fielding`, `positional`, `wLeague`, `replacement`, `war`,
  `plateAppearances`; pitching `war`, `ra9War`.
- StatsAPI season pitching lines `.cache/fa_statsapi_pitching_<Y>.json`: battersFaced, outs,
  strikeOuts, baseOnBalls, hitByPitch, homeRuns; a traded pitcher's row is his season total.
- Baseball-Reference `runs_field` per player-season (`.cache/war_daily/bat.parquet`, summed over
  stints, joined by `mlb_ID`), the independent fielding source of 11.2.2; its sha256 and modified
  time are printed before any statistic.
- Runs per win: `league_constants.league_totals(Y)["rpw"]`.
- 2020 is out on both sides of every pair. No 2021 or later season is read.

## 2. The construct

**2.1 Parts.** Hitters, on plate appearances n: BAT (FanGraphs batting runs), BR (baserunning
runs), FLD (fielding runs). Positional, league and replacement runs are conventions and are never
shrunk. Pitchers, on batters faced n: the strikeout rate K, the walk plus hit-by-pitch rate BH and
the home-run rate HR, each per batter faced.

**2.2 Reliability, frozen.** For each part c, on (Y, Y+1) pairs with Y in 2010 to 2015, hitters 200 PA and pitchers 200 batters faced in both seasons: e = rate minus the
season's exposure-weighted mean rate (over every row of the season with exposure 1 or more); r_c
the pooled Pearson of e(Y) with e(Y+1), clamped to 0.05 to 0.95 (`swar_lab.R_CLAMP`); hm the mean
harmonic mean of the pair's exposures; K_c = hm (1 - r_c) / r_c; tau2_c the exposure-weighted
covariance of e(Y) and e(Y+1); sigma2_c = K_c * tau2_c. Frozen in `talent_ewar.py` with their log
before any read of part 3.

**2.3 Shrink, re-centre, sum.** For a player-season with exposure n and part rate x_c, the
season's mean m_c and rel_c = n / (n + K_c):

```
hitters   g_c   = -(1 - rel_c) * n * (x_c - m_c)                  runs
          d_c   = g_c - n * (sum over the season's rows of g_c) / (sum of n)   zero-sum per season
          talent eWAR = fWAR + (d_BAT + d_BR + d_FLD) / RPW_s
pitchers  dq_c  = -(1 - rel_c) * (x_c - m_c)                      rate change, per batter faced
          druns = -n * (13 dq_HR + 3 dq_BH - 2 dq_K) / 9          FIP runs saved (13, 3, 2: FIP's)
          D     = druns / RPW_s - IP * (sum druns / RPW_s) / (sum IP)   zero-sum per season
          talent eWAR = fWAR + D
```

  Two-way players are on each side. A row whose exposure is 0 carries 0. The construct is linear,
  so the talent total minus fWAR is the sum of named part departures, each published per player.

**2.4 The posterior band.** Normal-normal per part: posterior variance of the part's rate (1 -
rel_c) * tau2_c, parts independent. Hitters: sd = n * sqrt(sum_c (1 - rel_c) tau2_c) / RPW_s;
pitchers: sd = (n / 9) * sqrt(169 v_HR + 9 v_BH + 4 v_K) / RPW_s, v_c = (1 - rel_c) tau2_c. The
band is talent eWAR plus or minus 1.2816 sd (80 percent).

## 3. The reads (development pairs: Y in 2016, 2017, 2018; floors 200 PA or 50 IP in both seasons)

**3.1 T1, ranking next-season realized runs (deciding).** Per side, two cells (rate and total),
Holm k = 2 per side:

| Side | Arm R (realized, the base) | Arm T (talent) | Target, Y+1: rate; total |
|---|---|---|---|
| Hitters | BAT + BR + FLD in Y | R + d_BAT + d_BR + d_FLD | FanGraphs BAT + BR (realized events) + Baseball-Reference runs_field: per PA; in runs |
| Pitchers | fWAR in Y (FIP-based) | fWAR + D | FanGraphs RA9-WAR (runs allowed, park-adjusted): per IP; in total |

- Statistic: Spearman gap T minus R; v2 primary (target z-scored within the outcome season;
  player-clustered, season-stratified bootstrap), v1 reported and required to agree in sign; B =
  2,000, seed 20261016; MDE95 and each cell's bootstrap sd printed before any gap.
- B1, the null shrink: R's rate shrunk uniformly, (x n + m k) / (n + k), one k per side by the
  `swar_lab.fit_b1` rule on the 2010 to 2015 pairs against the side's target. Twin: the summed
  departure permuted within (season, exposure decile) and added to R.
- Dispositions per cell in the order of `EBR_GATE.md` part 9.5 (WIN, SMALL WIN, LOSS,
  EQUIVALENT, UNRESOLVED), margin +0.02. **WIN (components)** needs lo95 above 0 against R and
  against B1 and the twin's lo95 at or below 0.
- Planted recovery and null comparator (fixture, before the run): a planted departure built from
  the target's own Y+1 deviation reads WIN on both cells; an all-zero departure never reads WIN.

**3.2 T2, the band's calibration (deciding for the band).** On the same pairs, per side: for each
part, the share of player-seasons whose Y+1 deviation from the season mean lies inside the
posterior mean's deviation plus or minus 1.2816 sqrt(predictive variance), predictive variance =
(1 - rel_c) tau2_c + sigma2_c / n(Y+1), on the frame's own part in Y+1 (FanGraphs BAT, BR, FLD;
the strikeout, walk plus hit-by-pitch and home-run rates). The band passes for a side when every
part's coverage lies between 0.75 and 0.85.

**3.3 Secondary, deciding nothing:** the same cells against published fWAR(Y+1) per PA or IP and
in total; T against bWAR(Y) as a reference arm.

**3.4 DEV PASS, per side:** T1's rate cell WIN (components), its total cell not LOSS, and T2's
band passes. Otherwise NOT VALIDATED for that side (a complete result).

## 4. Registered expectations (predictions, not measurements)

The hitter rate gap is positive (fielding and baserunning carry the least reliability and move
most), likely SMALL WIN or WIN (regression only) against R and smaller against B1; the pitcher
rate gap is positive and larger than the hitters'; every twin fails; the band under-covers a
little (talent drifts between seasons), so T2 is the likelier failure.

## 5. What a DEV PASS licenses

- A dated amendment to `docs/ebr-2026-09-30/EBR_GATE.md` part 11, committed alone before the skill
  look, registering the per-part reliability shrink as the headline eWAR's rule for the measured
  parts that carry no admitted skill arm (EW3-20's "shrunk skill rates"), with its own cells on
  11.2.1's component targets summed over the parts it touches, B1, the twin, the team guard and
  the secondary estimand, on the skill look's frame. The constants of part 2.2 stay frozen.
- The band may be shown beside the headline eWAR only after that look and only for a side whose T2
  passed; a display is a later registration with its own copy.

## 6. What is never done

- No served number, page, registry row or glossary entry reads talent eWAR under this document.
- No claim of "true talent" in copy; the number is a reliability-shrunk estimate on stated
  constants.
- No read on a predictor season 2021 to 2025.

## 7. Tool and tests

`talent_ewar.py` (pure: the fit, the shrink, the band, the frozen constants),
`tools/talent_ewar_lab.py` (with `--dry-run` on a synthetic fixture with nulls; stdout and stderr
teed to the output directory), `test_talent_ewar.py`. Output: `data/_labs/ewar_innovate/
talent_ewar_eval.json` (tracked, never shipped); per-player values only in
`.cache/ewar_innovate_ledger/talent_ewar/`.

## 8. Results and dated notes

EMPTY.

### 8.1 2026-10-16: the constants and the reads (tools/talent_ewar_lab.py), once

- **Constants (part 2.2), fitted once on 2010 to 2015 pairs and frozen in `talent_ewar.py`**
  (log `data/_labs/ewar_innovate/talent_ewar_fit.json`): hitters, 1,616 pairs: BAT r 0.445, K 585
  PA; BR r 0.555, K 375 PA; FLD r 0.369, K 802 PA. Pitchers, 1,423 pairs: K r 0.731, K 179
  batters faced; BH r 0.575, K 361; HR r 0.269, K 1,330. B1's k: hitters 748.8 PA, pitchers 230.7
  IP.
- **Dry run** on the fixture with nulls passed before the read (planted: WIN (components) on both
  cells; all-zero: EQUIVALENT).
- **T1 (part 3.1), predictor seasons 2016 to 2018** (war_daily sha256 e9571c42..., modified
  2026-10-16T03:48Z). Floors printed first: hitters rate MDE95 0.0082, total 0.0102; pitchers rate
  0.0376, total 0.0265.

| Side, cell | Pairs | rho R (base) | rho T (talent) | rho B1 | Gap T - R (95 percent) | T - B1 lo95 | Twin lo95 | Disposition |
|---|---|---|---|---|---|---|---|---|
| Hitters, rate | 800 | 0.3995 | 0.4099 | 0.4047 | +0.0105 (+0.0009 to +0.0205) | -0.0022 | -0.1378 | SMALL WIN |
| Hitters, total | 800 | 0.4176 | 0.4167 | 0.4155 | -0.0009 (-0.0130 to +0.0110) | -0.0126 | -0.1303 | EQUIVALENT |
| Pitchers, rate | 670 | 0.2519 | 0.2494 | 0.2639 | -0.0025 (-0.0485 to +0.0401) | -0.0594 | -0.0953 | UNRESOLVED |
| Pitchers, total | 670 | 0.3674 | 0.4005 | 0.3790 | +0.0331 (+0.0009 to +0.0639) | +0.0013 | -0.0557 | WIN (components) |

  v1 agrees in sign on every cell. Reference, no weight: bWAR(Y) per PA against the hitters'
  target, rho 0.3541.
- **T2 (part 3.2), the band's 80 percent coverage:** hitters BAT 0.805, BR 0.944, FLD 0.855;
  pitchers K 0.767, BH 0.803, HR 0.748. **Fails on both sides** (BR over-covers: its band is too
  wide; HR under-covers).
- **Secondary (part 3.3), deciding nothing:** against published fWAR(Y+1), hitters rate EQUIVALENT
  (+0.0038), total UNRESOLVED (-0.0112); pitchers rate UNRESOLVED (+0.0355), total WIN
  (components) (+0.0554, 95 percent +0.0260 to +0.0842).
- **Verdict (part 3.4): NOT VALIDATED on both sides.** Hitters: the rate cell is a SMALL WIN (it
  ranks next season's realized runs a little better than realized WAR, not better than a uniform
  shrink) and the band fails. Pitchers: the rate cell is UNRESOLVED; the total cell's WIN does
  not decide (part 3.4 reads the rate cell), and the band fails. Nothing is registered for the
  eWAR v3 skill look under part 5, and no band is shown.

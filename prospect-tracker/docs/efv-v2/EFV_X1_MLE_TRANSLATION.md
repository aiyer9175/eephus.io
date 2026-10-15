# EFV_X1: MLE translation and reliability layer (registration, fixed before any number)

Written 2026-10-15 under the owner's decision EW3-12 of 2026-10-15
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim "Let's do all of the above"), the first
step of the expert eFV program. This document is committed ALONE, before the module
`efv_x1_translate.py` computes any translated rate, any constant or any statistic. Sections 1
to 9 are written now; the build appends section 10 (the constants and the translation
diagnostics) and the development read appends section 11 (the incremental read). The
plain-language summary for the owner is `docs/efv-v2/EFV_X1_RESULTS.md`. No em-dashes.

## 1. What this is, and what it is not

The industry projects a minor leaguer by translating his line into a major league
equivalent (Davenport's MLEs, ZiPS, Steamer): the level, the league, the park and the
season's run environment are taken out of each rate, and the translated rate is then
shrunk toward a prior by how much of it is sample noise. eFV has never done this; its
MiLB drivers are rates relative to the line's own level and league. This task builds that
layer and reports how much each feature it produces adds to PROSPX consensus on the two
development frames.

It is DESCRIPTIVE. Its outputs are inputs for EFV_X3 (the pooled model). Nothing served
reads it, no flag reads it, no ledger row or progress-chart row is written, and no outcome
of this read ships or adjudicates anything. The served grade does not change.

## 2. Data

- Source: the public MLB StatsAPI season feed (`/api/v1/stats?stats=season`, one request per
  sport, season and group, plus `/api/v1/teams/stats` per sport, season and group),
  fetched once by `efv_x1_fetch.py` into `.cache/EFV_X1_MLE_TRANSLATION/` only, one request
  at a time 0.6 s apart. No paid or login-walled source.
- Sports 1 (MLB) and 11 to 16 (every affiliated level), seasons 2005 to 2026; 2020 is
  skipped (no minor league season). Levels follow `milb_history`: AAA, AA, A+, A (sport 15
  folds into A), CPX and DSL (sport 16 split by league name).
- The Mexican League is dropped: its lines sit under sport 11 (AAA) in the feed through
  2020, and it was never a development league. Any line whose league is `MEX` is removed
  before anything is fitted, in every season.
- The feed aggregates a player who played for two or more teams of one sport-season into
  one line (num_teams above 1, no team). Such a line keeps its league when the feed gives
  one and takes the neutral park factor 1.

## 3. The statistics translated

Per line, from counts (never from the feed's rounded rates):

| side | stat | numerator | denominator |
|---|---|---|---|
| hit | k (K%) | SO | PA |
| hit | bb (BB%) | BB | PA |
| hit | iso | 2B + 2 x 3B + 3 x HR | AB |
| hit | babip | H - HR | AB - SO - HR + SF |
| hit | obp | H + BB + HBP | AB + BB + HBP + SF |
| hit | woba | 0.69 uBB + 0.72 HBP + 0.89 1B + 1.27 2B + 1.62 3B + 2.10 HR | AB + BB - IBB + SF + HBP |
| pit | k (K%) | SO | BF |
| pit | bb (BB%) | BB | BF |
| pit | hr9 (HR/9) | HR | outs / 27 |
| pit | gb (GB%) | ground outs | ground outs + air outs (where present; a line with none has no GB%) |

The wOBA weights are fixed constants on the FanGraphs scale (declared, not season-fitted):
the translation works on ratios to the environment, so a constant set changes only the
scale. K-BB% (pitchers) is the shrunk K% minus the shrunk BB%, derived, not shrunk on its own.

## 4. The translation (part a)

For one side, one stat and one season s, every line i of the season (MLB and every
affiliated league, MEX removed) has a numerator n_i, a denominator d_i, a player p and a
league-season g (MLB is one league, AL and NL pooled). The expected numerator is

    E[n_i] = d_i * pi_i * theta_{p} * lambda_{g}

- theta_p is the player's season talent on the MLB scale (one per player and season);
- lambda_g is the league-season factor: the season's environment at that league times the
  league's difficulty relative to MLB, with lambda_MLB = 1;
- pi_i is the line's team (park) factor (below), 1 for a multi-team line.

The factors are fitted by Poisson fixed-effects iteration (alternating
theta_p = sum n / sum d pi lambda over the player's lines, lambda_g = sum n / sum d pi theta
over the league's lines, lambda_MLB held at 1) for 200 iterations or until the largest
relative change is below 1e-9. This is the chained same-player method: a league's factor is
identified only by players who also appear in another league the same season, so DSL is
chained to CPX, CPX to A, A to A+, A+ to AA, AA to AAA and AAA to MLB through the players
observed at consecutive levels and in MLB; a player seen in one league only informs nothing
about the factors. Same-season pairs are used so that a player's aging does not enter the
level gap. A league-season with fewer than MIN_LINK = 15 linking players (players with a
line there and a line in another league that season) is not identified on its own: its
difficulty (lambda over the league's pooled rate) is the denominator-weighted mean
difficulty of the identified leagues of the same level that season, times its own pooled
rate. A level with no identified league that season takes the mean difficulty of that
level over the earlier seasons where it was identified; with none, the level above's.

**Park.** The season feed has no home and road splits, and it merges a traded player's
teams, so a team's park cannot be identified by the same-player method from this feed (no
player is seen on two teams of one league in one season). The park leg uses the classic
two-sided team method instead: a team's factor in season s is the geometric mean of its
batters' rate and its pitchers' allowed rate, each over its league-season's pooled rate,
averaged over seasons s - 2 to s for the same team id and league (seasons at or before s
only), then regressed toward 1 by r, the year-over-year correlation of the single-season
two-sided factor of the same team id in consecutive seasons over every season at or before
s (floored at 0). A player on that team plays half his games at home, so the two-sided
factor estimates the effect on his line, which is what the translation removes. This is a
recorded deviation from the spec's "estimated by the chained same-player method" for the
park leg only; section 10 reports r per stat.

**The translated rate.** A line's MLB-equivalent rate in season s is
x_i = n_i / (d_i * pi_i * lambda_g), and a player-season's is theta_p (all his lines that
season pooled). To compare seasons, every rate is put in the MLB environment of the row's
reference season T (section 6): x * R_MLB(T) / R_MLB(s), with R_MLB the MLB pooled rate.

**As of.** Season s's league factors read season s only; the park factor reads seasons s - 2
to s; every season read by a row ended (1 October, the `efv_w2_milb.last_readable_season`
rule) at or before the row's as-of date. The module asserts it on every row.

## 5. The reliability layer (part b)

Each translated player-season rate x (season exposure n, the raw denominator: PA, AB, BIP,
BF, innings / 9 or ground plus air outs) is shrunk toward its level-and-age prior mu:

    shrunk = (n * x + k * mu) / (n + k)

- mu is the exposure-weighted mean translated rate of the player-seasons in the same cell
  (the level that holds most of the player's exposure that season, and the integer age
  clipped to 17 to 30), over the prior window; a cell with fewer than 30 player-seasons
  takes the level's mean.
- k is the stat's stabilization point (in its own denominator units), by empirical Bayes
  method of moments over the player-seasons of the prior window with at least 100 PA or
  100 BF: the true-talent variance tau^2 is the variance of x around mu minus the mean
  sampling variance, and k = mean per-unit sampling variance / tau^2. The per-unit
  sampling variance is p(1 - p) for a proportion, the rate itself for HR/9 (Poisson), and
  the line's own second moment minus its squared mean for ISO and wOBA, each on the
  translated scale. If tau^2 is not positive, k is recorded as undefined and the stat is
  not shrunk (k = 0) at that T.
- The prior window is the five played seasons ending at T (seasons at or before T only).
- The weight n / (n + k) rises with n for every k at or above 0, so the shrinkage is
  monotone in sample size (tested).

## 6. The trajectory features (part c)

A frame row read at year Y as of a cutoff reads the last season that ended by its read,
T = `efv_w2_milb.last_readable_season(Y, cutoff)` stepped back over 2020, and the two
played seasons before T: the window (T, T - 1, T - 2), skipping 2020. For each side the
features are:

- `<stat>_rw` for every stat of section 3 (hitters k, bb, iso, babip, obp, woba; pitchers
  k, bb, hr9, gb) and `kbb_rw` (pitchers): the reliability-weighted translated rate over the
  window. Season rates are pooled with Marcel recency weights 5, 4, 3 (newest first) on
  exposure, x_bar = sum m_s n_s x_s / sum m_s n_s, the effective exposure is
  sum (m_s / 5) n_s, and x_bar is shrunk (section 5) toward the prior of the newest season's
  cell with that effective exposure.
- `<stat>_yoy`: the shrunk rate of the newest season minus that of the season before it in
  the window, each shrunk on its own; missing unless both seasons have exposure.
- `age_rel_level`: the player's age in the newest season minus the exposure-weighted mean age
  of every line at the level holding most of his exposure that season.
A row with no affiliated line in the window has every feature missing. Only pre-debut
lines are read: the MLB lines enter the factor fits, never a row's features.

Feature count: hitters 6 rw + 6 yoy + age = 13; pitchers 4 rw + kbb_rw + 4 yoy + age = 10.

## 7. The development read (the only read)

- **Frames.** lv_dev: list vintages 2017, 2018 and 2019, label W3 (fWAR over the first three
  MLB seasons, 0 when no debut within three seasons of V), as
  `tools/efv_v2_model_class_screen.build_inputs` scores them (its scored rows: consensus
  present, label present). vm_dev: the DS-16 vintage-matched rows of debut years 2017 to
  2024 that the same builder scores (career WAR to date). Label provider fwar, resolved
  through 2026. No other frame is read: R-LV (list vintages 2020 and 2021) and R-VM (the
  2025 and later debut cohorts) are not opened (`efv_vintage_frame` guards; the builder
  stops before 2025). EW3-13's 2026 holdout belongs to EFV_2026_HOLDOUT_READ, not here.
- **As of.** A list-vintage row reads at its window start (V-01-01) through its outcome-blind
  `mlbam_id`; a vintage-matched row reads at its pinned preseason as-of
  (`efv_v2_model.pinned_inputs`) through the matrix `mlbam_id`.
- **Estimand.** For each frame, side and feature j: the within (side, vintage) Spearman of a
  consensus-plus-feature score against the label, minus that of consensus alone.
- **The score.** Inside each (side, year) group: u_c the consensus FV percentile (average
  ranks), u_y the label percentile, z_j the feature z-scored over the group's rows that have
  it, 0 where missing, and m_j the missing indicator. For each held-out year, a ridge
  (alpha 1.0, intercept free) of u_y on (u_c, z_j, m_j) is fitted on the rows of the other
  years of the same frame and side (leave one year out), and predicts the held-out year.
  The combination weight therefore uses labels of other development years, including
  later ones; it is two slopes, the inputs are as-of, and the read selects nothing.
- **Statistic.** `efv_v2_stat.paired_delta(statistic="within")`: the size-weighted mean over
  groups of at least 20 rows of the within-group Spearman, delta = score minus consensus,
  E_cond paired player-clustered bootstrap, B = 2000, seed 20261018.
- **Reference.** The feature's permuted twin (values shuffled across rows inside each
  (side, year), seed 20261019) through the same leave-one-year-out score, point estimate
  only: the gain a no-information tiebreaker earns on consensus's ties.
- **Also reported, descriptive:** each feature's coverage, its own within Spearman with the
  label and its within Spearman with consensus.

## 8. The rule (descriptive flag; it ships nothing)

A feature is FLAGGED for EFV_X3's candidate list when its delta is above 0 on both lv_dev and
vm_dev, the CI95 lower bound is above 0 on at least one of them, and the delta is above its
twin's on both. Every other feature is NOT FLAGGED (it stays available to EFV_X3, which
registers its own selection). Neither outcome moves anything served; a flip question would
need a registered ship rule this task does not have.

## 9. The tests (`test_efv_x1_translate.py`)

1. Translation recovers MLB rates on held-out consecutive-level pairs: with players split
   into five folds (seed 20261018), the factors fitted without a fold translate the fold's
   AAA lines of players who also batted or pitched in MLB that season, and the pooled
   translated rate sits closer to their pooled MLB rate than the untranslated AAA rate does;
   likewise AA to AAA. On a synthetic league with known factors the fit recovers them to
   within 2 percent.
2. Shrinkage is monotone: the weight n / (n + k) and the distance of the shrunk rate from its
   prior both behave monotonically in n.
3. No look-ahead: every season a row reads ended at or before its as-of; factors of season s
   are unchanged when every later season is removed; a row's features are unchanged when
   later seasons are removed.
4. The source scan: no grouping by consensus-FV level, no reserved vintage, no served module
   imports `efv_x1_translate`.

GATE COMPLIANCE (`docs/PROSPECT_ANCHOR_GATE.md`): the only strata are side, season, year,
league, level, team and integer age. Nothing groups, counts or averages anything by
consensus-FV level.

## 10. The build (appended 2026-10-15, after the registration commit ab1665e9)

Artifact: `data/_labs/efv_x1/efv_x1_translate.json` (`factors`), off the webroot.

- **Data.** 588 cache files, 304,077 rows (21 seasons x 7 sports x 2 groups x players and
  teams). MEX lines dropped: 288 to 411 a season per side, 2005 to 2019; none from 2021 (the
  league left sport 11).
- **Implementation details the registration did not fix.** The team feed carries no league,
  so a team's league is read off its single-team player lines, and the park factor is keyed
  by team id (a team id sits in one league in a season). For HR/9 the park leg reads home
  runs per batter on both sides (the team batting line has no outs). Neither touches an
  outcome.
- **Identification.** Every affiliated league is identified by same-season links in every
  season (14 to 17 of 15 to 19 league keys) except the DSL and VSL, which have 0 to 2
  linking players a season and are never identified; with no earlier identified season,
  they take the CPX difficulty of the same season (the registered fallback), times their
  own pooled rate. This is the weakest link of the ladder and is disclosed as such.
- **Park.** The year-over-year r of the single-season two-sided team factor is 0.33 (BB%) to
  0.54 (HR/9); GB% falls from 0.45 (T 2016) to 0.13 (T 2022) as the post-2021 ground and
  air out coding enters. So a team's three-year factor is regressed about half way to 1.
- **Stabilization points (k, in the stat's own denominator), T 2016 / 2018 / 2022.**
  Hitters: K% 41.8 / 40.6 / 38.7 PA, BB% 99.6 / 101.9 / 100.9 PA, ISO 120.8 / 124.2 / 138.7
  AB, BABIP 340.7 / 347.5 / 363.7 balls in play, OBP 208.9 / 226.7 / 217.9, wOBA 223.8 /
  241.5 / 242.6. Pitchers: K% 66.4 / 67.1 / 70.8 BF, BB% 65.5 / 65.2 / 58.9 BF, HR/9
  17.2 / 13.5 / 13.8 nine-inning units, GB% 39.4 / 40.3 / 16.2 batted outs. Every k is
  defined (tau squared positive) at every T read. They run below the published MLB points
  because the prior window mixes levels and ages, so true talent spreads wider than in MLB.
- **Recovery (held-out players, five folds, seasons 2005 to 2026 without 2020).** The mean
  absolute relative error of the pooled translated rate against the pooled actual rate at
  the higher level, translated versus untranslated:

  | pair | hitters K% | BB% | ISO | BABIP | OBP | wOBA | pitchers K% | BB% | HR/9 | GB% |
  |---|---|---|---|---|---|---|---|---|---|---|
  | AAA to MLB | 0.062 / 0.145 | 0.059 / 0.252 | 0.063 / 0.253 | 0.035 / 0.122 | 0.037 / 0.170 | 0.040 / 0.175 | 0.024 / 0.259 | 0.029 / 0.111 | 0.096 / 0.300 | 0.011 / 0.085 |
  | AA to AAA | 0.017 / 0.046 | 0.040 / 0.131 | 0.052 / 0.111 | 0.026 / 0.032 | 0.024 / 0.054 | 0.026 / 0.055 | 0.059 / 0.192 | 0.024 / 0.163 | 0.076 / 0.312 | 0.016 / 0.033 |
  | A+ to AA | 0.020 / 0.066 | 0.039 / 0.123 | 0.051 / 0.176 | 0.028 / 0.090 | 0.025 / 0.102 | 0.028 / 0.109 | 0.074 / 0.207 | 0.034 / 0.171 | 0.113 / 0.300 | 0.026 / 0.076 |

  The translation is closer in 14 to 21 of the 21 seasons for every stat and pair. HR/9 is
  the noisiest (about 10 percent).

## 11. The development read (appended 2026-10-15; descriptive, adjudicates nothing)

Artifact: `data/_labs/efv_x1/efv_x1_translate.json` (`reads`). Rows: lv_dev 1,465 hitter
rows (888 players) and 1,397 pitcher rows (865 players); vm_dev 406 hitters and 424
pitchers. Coverage of the window features 0.93 (lv_dev) and 0.99 (vm_dev); the
year-over-year features 0.68 to 0.76 (lv_dev) and 0.92 to 0.97 (vm_dev). Consensus's own
within Spearman: lv_dev 0.195 hitters, 0.163 pitchers; vm_dev 0.395 and 0.367.

Delta = within Spearman of the leave-one-year-out score minus consensus's (CI95, E_cond
B 2000 seed 20261018); twin = the permuted twin's delta.

| side | feature | lv_dev delta | CI95 | twin | vm_dev delta | CI95 | twin |
|---|---|---|---|---|---|---|---|
| hit | k_rw | -0.0001 | -0.0124, +0.0118 | +0.0012 | +0.0032 | -0.0163, +0.0220 | -0.0007 |
| hit | bb_rw | -0.0039 | -0.0126, +0.0051 | -0.0066 | -0.0036 | -0.0282, +0.0199 | -0.0041 |
| hit | iso_rw | -0.0053 | -0.0150, +0.0044 | -0.0151 | -0.0086 | -0.0264, +0.0069 | +0.0020 |
| hit | babip_rw | -0.0047 | -0.0157, +0.0065 | -0.0114 | -0.0109 | -0.0271, +0.0041 | -0.0014 |
| hit | obp_rw | -0.0027 | -0.0127, +0.0069 | -0.0110 | -0.0018 | -0.0264, +0.0206 | -0.0109 |
| hit | woba_rw | -0.0039 | -0.0144, +0.0064 | -0.0017 | -0.0066 | -0.0269, +0.0116 | +0.0037 |
| hit | k_yoy | -0.0147 | -0.0259, -0.0047 | -0.0114 | +0.0029 | -0.0246, +0.0247 | -0.0119 |
| hit | bb_yoy | -0.0116 | -0.0226, -0.0009 | -0.0062 | -0.0104 | -0.0386, +0.0138 | -0.0186 |
| hit | iso_yoy | -0.0113 | -0.0224, -0.0009 | -0.0035 | -0.0055 | -0.0360, +0.0222 | -0.0022 |
| hit | babip_yoy | -0.0288 | -0.0428, -0.0158 | -0.0077 | -0.0005 | -0.0281, +0.0224 | -0.0168 |
| hit | obp_yoy | -0.0139 | -0.0287, -0.0003 | -0.0007 | -0.0018 | -0.0283, +0.0211 | -0.0173 |
| hit | woba_yoy | -0.0159 | -0.0306, -0.0024 | -0.0065 | -0.0007 | -0.0297, +0.0253 | -0.0119 |
| hit | age_rel_level | -0.0103 | -0.0234, +0.0028 | -0.0092 | -0.0046 | -0.0201, +0.0091 | -0.0105 |
| pit | k_rw | -0.0086 | -0.0206, +0.0031 | +0.0056 | -0.0041 | -0.0313, +0.0229 | -0.0075 |
| pit | bb_rw | +0.0008 | -0.0120, +0.0142 | -0.0402 | +0.0061 | -0.0154, +0.0283 | +0.0132 |
| pit | hr9_rw | -0.0086 | -0.0217, +0.0038 | -0.0052 | +0.0009 | -0.0291, +0.0324 | -0.0139 |
| pit | gb_rw | +0.0008 | -0.0173, +0.0184 | -0.0117 | +0.0008 | -0.0288, +0.0321 | +0.0028 |
| pit | kbb_rw | -0.0040 | -0.0161, +0.0082 | -0.0040 | +0.0049 | -0.0205, +0.0309 | -0.0096 |
| pit | k_yoy | -0.0025 | -0.0187, +0.0131 | +0.0026 | -0.0248 | -0.0521, +0.0023 | -0.0070 |
| pit | bb_yoy | -0.0036 | -0.0185, +0.0110 | -0.0250 | -0.0090 | -0.0379, +0.0176 | -0.0012 |
| pit | hr9_yoy | -0.0003 | -0.0189, +0.0176 | -0.0008 | -0.0056 | -0.0348, +0.0204 | -0.0339 |
| pit | gb_yoy | -0.0103 | -0.0256, +0.0050 | -0.0014 | -0.0116 | -0.0401, +0.0154 | -0.0153 |
| pit | age_rel_level | -0.0026 | -0.0135, +0.0086 | -0.0064 | +0.0010 | -0.0236, +0.0241 | -0.0156 |

**Rule (s8): no feature is FLAGGED.** Two (pitcher bb_rw and gb_rw) are above zero on both
frames, but neither has a CI95 lower bound above zero on either, and bb_rw sits below its
twin on vm_dev. Six hitter year-over-year features read below zero on lv_dev with the CI95
upper bound below zero: one noisy change column, combined one at a time with consensus,
costs ranking on the list frame. The features' own within correlation with the label runs
the expected way (hitter wOBA_rw +0.078 / +0.134, ISO_rw +0.070 / +0.098, K%_rw -0.046 /
-0.096; pitcher K%_rw +0.034 / +0.141, HR/9_rw -0.000 / -0.148), but consensus already
carries it: the translated rates correlate with consensus inside the group (wOBA_rw
+0.251 / +0.191, ISO_rw +0.265 / +0.148, pitcher K%_rw +0.158 / +0.235).

Reading: the translated, reliability-weighted rates are better measurements of the same
performance (section 10), but one at a time they add nothing to consensus that this read
can see. They pass to EFV_X3 as inputs, unflagged; X3 registers its own selection. Nothing
served moved, no ledger row was written, and R-LV and R-VM were not opened.

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

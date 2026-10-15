# eFV v5 group drivers: results for the owner (2026-10-15)

Plain language. Every number is copied from `data/efv5_metric_atlas.json`,
`data/_labs/efv5/efv5_group_select.json` and `data/_labs/efv5/efv5_group_spent.json`; the rule
and the full tables are in `docs/efv-v2/EFV_V5_BACKTEST.md`. No em-dashes. Nothing here is cut
by consensus-FV cell.

## The one-line answer

Yes, we can build the chart's correlations into eFV, and we did: every group signal the atlas
found that also has a long track record became an eFV driver that switches on only for its own
group. It does not make eFV better yet. Two of them (Single-A hitters' wOBA and slugging) helped
on the development years and then hurt slightly on the 2020 and 2021 lists. eFV v5 does not
ship; the served eFV, the board and the dollars do not move; the honest claim is still "ties
consensus".

## What was built

The atlas scored every MiLB statistic in every level, age band and role group twice: raw, like
Robert Stock's chart, and on top of PROSPX consensus FV. Only the second score can help eFV,
because eFV starts from consensus. This task took every atlas cell that:

- beat consensus on the second score with a 95 percent interval above zero and a false
  discovery rate (q) of 0.10 or less, and
- comes from a family with a long history (season lines from 2005, pitch calls from 2007), so
  it can be tested against six-season fWAR, and
- does not lean on the 2025 debut cohort (those cells are spent).

That is 47 cells. A raw rate and its age-adjusted version measure the same thing, so they became
one driver each: 28 drivers. Each driver is "this statistic, in this group, compared with the
group's own average that year, and zero for everyone outside the group". Age drivers went to
eFV's arrival (timing) part; performance drivers went to its talent (skill) part.

| group | drivers |
|---|---|
| Single-A hitters, all | K%, BB minus K, AVG, OPS, wOBA, SLG, age |
| Single-A hitters, young for the level | K%, BB minus K, AVG, age |
| Complex-league hitters | AVG, OPS, wOBA |
| High-A hitters, all and young | pitch-call contact rate, whiff rate (young also two-strike contact) |
| Single-A pitchers, all | K%, K-BB%, age |
| Single-A pitchers, young for the level | K%, K-BB% |
| Single-A starters | K%, K-BB%, batters per game, age |

The chart's tracking statistics (Stuff+, velocity, ride, xwOBA against) start in 2021, so they
have no six-season record yet and stay with the tracking-era work (EW3-1).

## How each driver was judged

The same rule as eFV v4, fixed before anything was read: add one driver at a time, keep it only
if it lifts the 2017 to 2019 list years by at least +0.0020 and does not cost the 2017 to 2023
debut cohorts more than 0.0020, at most six drivers. Then read the chosen set once on the 2020
and 2021 lists and the 2025 debut cohort (already used once on 10-08, so labelled spent), and
ship only if it beats the served eFV on all four.

## The table (within (side, list year) Spearman, pooled over sides)

| frame | n | v5 | served eFV (V2) | consensus | v5 minus V2 | v5 minus consensus | role |
|---|---|---|---|---|---|---|---|
| list years 2017 to 2019 | 2,862 | 0.1709 | 0.1676 | 0.1792 | +0.0033 (-0.0007 to +0.0073) | -0.0083 (-0.0292 to +0.0120) | development, chosen on it |
| debut cohorts 2017 to 2023 | 830 | 0.3713 | 0.3713 | 0.3814 | 0 (identical rows) | -0.0101 (-0.0391 to +0.0160) | development, chosen on it |
| list years 2020 and 2021 | 2,349 | 0.1481 | 0.1511 | 0.1494 | -0.0030 (E_refit -0.0099 to +0.0001) | -0.0013 (E_refit -0.0246 to +0.0162) | spent |
| the 2025 debut cohort | 147 | 0.3739 | 0.3739 | 0.3333 | 0 (identical rows) | +0.0406 (E_refit -0.0830 to +0.1251) | spent |

## Ship or not

Not. The owner's rule (EW2-10) was: ship only if v5 beats served V2 on all four frames. It beats
V2 on the list years it was chosen on and on none of the other three. `EFV_V5_ON` stays False.
The two development rows now on the Source Comparison page are drawn hollow, as development
reads.

## Why it came out this way, in plain words

- The atlas asked "does this statistic tell you who reaches the majors, beyond consensus?" eFV
  asks "does it reorder players by the WAR they go on to produce, beyond consensus?" The first
  answer was yes for 47 cells; the second was no for 26 of the 28 drivers built from them.
- Single-A pitcher strikeout rate and K-BB%, the chart's strongest kind of signal, never
  cleared the first step: on the list years they moved the pitcher order by between 0 and
  +0.0004, far under the +0.0020 bar, and K-BB% cost the debut cohorts -0.0065.
- Single-A hitter wOBA and slugging did clear it, on 418 list-year hitters, worth +0.0064 on
  hitters. On the 2020 and 2021 lists the same two drivers cost -0.0058 on hitters, negative in
  both years: a development lift that reversed on the later lists, the same pattern v3 and v4
  showed.
- The debut-cohort frames cannot test these drivers: at the debut-year read almost nobody is
  still in Single-A or the complex leagues (2 of 82 hitters in the 2025 cohort).

## What this closes and what stays open

- Closed on the frames that exist: the atlas's 28 long-label group drivers, one by one and in
  combination, under the owner's rule.
- Open: the tracking-era head (EW3-1), where Stuff+, velocity and the other chart statistics
  live; it needs a short-horizon label and its own consensus comparison, and gains a six-season
  label only as the 2021 and later cohorts mature. And the consensus-method item (DS-Q4), the
  one lever with a known effect on the list years.

## Questions recorded for the owner (defaults applied, nothing stopped)

1. Where a reach signal enters eFV. Default taken: performance statistics to the skill head,
   age to the timing head (Driver System V2 principle 4). Alternatives: (B) offer every atlas
   driver to the timing head as well, since the atlas read them on reaching MLB (52 steps
   instead of 28; on pitchers the timing head carries weight 0.020, so it can barely move
   them); (C) let a reach-label driver re-weight the pitcher timing head, which reopens the P5
   weights the owner kept (EW2-9).
2. The 2021 list read. Default taken: a 2021 row reads its 2019 season (no MiLB season in 2020),
   so a player listed in both 2020 and 2021 carries the same Single-A line twice. Alternative:
   no group membership on 2021 rows (the drivers would be zero there).
3. Spent-read ledger rows. Default taken: none (as v4). Alternative: two rows with role reserved
   labelled spent, which would draw as a second look on the chart.

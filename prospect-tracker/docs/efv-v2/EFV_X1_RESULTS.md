# EFV_X1 results: what the MLE translation layer found (plain language)

Written 2026-10-15 for the owner. The method was fixed and committed before anything was
measured (`docs/efv-v2/EFV_X1_MLE_TRANSLATION.md`, sections 1 to 9); the numbers here come
from `data/_labs/efv_x1/efv_x1_translate.json` (sections 10 and 11 of that document carry
the full tables). Nothing on the site changed.

## What was built

The industry projects a minor leaguer by turning his stat line into a major league
equivalent: it takes out how hard the level is, how the league and the park play, and the
run environment of the season, then discounts the result by how small the sample is. eFV
had never done that. This task builds it, in `efv_x1_translate.py`:

1. **Translation.** Every affiliated season line from 2005 to 2026 (Mexican League dropped,
   no 2020) is put on the big league scale, stat by stat: hitters' strikeout and walk rates,
   ISO, BABIP, OBP and wOBA; pitchers' strikeout and walk rates, K-BB, HR/9 and ground ball
   rate. How hard each league is comes from the same players seen in two leagues in the same
   season, chained up the ladder to the majors. Park effects come from each team's hitters
   and pitchers together, regressed about half way to neutral.
2. **Reliability.** Each translated rate is pulled toward what a player of the same level and
   age usually does, by an amount set by how much of the rate is noise. A strikeout rate
   settles after about 40 plate appearances of translated minor league data, a walk rate
   after about 100, ISO after about 125, BABIP after about 350.
3. **Trajectory.** For each prospect at each read: a three-season weighted average of each
   translated rate, the change from the year before, and his age against his level.

## Does the translation work?

Yes, as a measurement. Hold out a set of players, fit the factors on everyone else, and
predict how the held-out players' minor league lines would look one level up. Against
their actual lines at the higher level, the translated prediction misses by about 1 to 7
percent on every stat but HR/9, against 3 to 26 percent for the raw minor league numbers,
and it is closer in nearly every season (14 to 21 of 21, by stat and level pair). Pitcher HR/9 is the noisiest
(about 10 percent off). One weak spot: the Dominican and Venezuelan summer leagues almost
never share players with another league in the same season, so their difficulty is borrowed
from the US complex leagues.

## Does it help eFV beat consensus?

Not by itself. Each of the 23 new features was added, one at a time, to PROSPX consensus on
the two development frames (the 2017 to 2019 lists, and the 2017 to 2024 debut classes), and
scored on how well the combination ranks players within each list year.

- No feature cleared the bar the registration set (better than consensus on both frames,
  clearly above zero on at least one, and better than a scrambled copy of itself). None is
  flagged.
- The full-window translated rates land within about plus or minus 0.01 of consensus, inside
  the noise. Two pitcher features (walk rate and ground ball rate) are slightly positive on
  both frames, by less than 0.007.
- The year-over-year change columns hurt hitters on the list frame (minus 0.011 to minus
  0.029): a single noisy change number, bolted onto consensus, makes the ranking worse.
- The new rates do point the right way on their own (better wOBA and ISO, more strikeouts by
  pitchers and fewer by hitters, all go with more WAR), but they correlate with consensus,
  so the scouts already have most of what they say.

## What this means

The translation layer is a better measuring stick for minor league performance, and it is
the input the pooled model needs. On its own it confirms what the earlier eFV work found:
consensus already absorbs what the box score says. The value, if any, will show up only
when these features enter one pooled model alongside the team-decision features (EFV_X2)
and the larger 2025 to 2026 training pool (EFV_X3, after EFV_2026_FOLD_TRAINING), which
registers its own test. Nothing here changes a grade, and there is no flip question.

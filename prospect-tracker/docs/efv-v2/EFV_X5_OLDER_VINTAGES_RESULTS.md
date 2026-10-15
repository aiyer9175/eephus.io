# eFV X5 results: older prospect lists added to the label pool

Written 2026-10-15 for the owner (decision EW3-12, item 5). The method was registered first,
alone, in `docs/efv-v2/EFV_X5_OLDER_VINTAGES.md` (commit d9413f3a); the numbers below are
its section 9. Nothing on the site changes.

## What was done

eFV is limited by how many graded prospects have a known outcome, not by features. Our list
history started in 2011. I went looking for public prospect lists from before 2011, kept the
ones that were free to read and carry a publication date inside the preseason (January 1 to
April 30), and matched every printed name to a player id the same outcome-blind way the
existing frame does (the name against players already in the minors before that season,
never using whether the player later reached the majors).

Four sources passed every rule:

- Baseball America Top 100, 2006 to 2013 and 2015 (900 rows), read from Internet Archive
  copies of Baseball America's own pages, dated by each year's article.
- Baseball America organization Top 10 lists, the 78 published in January to April of
  2007 to 2013 (779 rows). The other 125 came out in October to December, before the
  preseason window, so they do not count as preseason reads.
- Baseball Prospectus Top 100 and Top 101, 2007 to 2011 (502 rows), free articles.
- John Sickels's Minor League Ball organization Top 20 lists, the 23 posted in January of
  2009 to 2011 (465 rows, each with his letter grade), read from Internet Archive copies.

Two did not pass: MLB.com's Top 50 (the 2009 list came out in December 2008, and the 2010
list has no date I could confirm from MLB itself) and FanGraphs's older team lists (not
reached in the time I had).

Names matched to an id at 89% to 95% depending on the source. Six lists below 80% were
dropped by the rule written in advance.

## What it adds

- 995 new prospect-season rows for the development frame: 819 in the new seasons 2006 to
  2010 (439 hitters, 380 pitchers) and 176 in seasons we already had, mostly 2011, which
  more than doubles (122 rows today, 145 more).
- 612 of those players are in no current frame row at all.
- The smallest edge the development frame can detect (mde95 of the eFV versus consensus
  Spearman gap) falls from 0.0180 to 0.0166 on the registered reading (to 0.0155 if every
  new row ended up scored). That is a real but modest gain: about a 17% larger frame.

## What it does not do yet

These rows have not been scored, joined to outcomes or used to train anything. Before 2011
there is no PROSPX consensus, so a test on these seasons would compare eFV against the old
list's own ranking, and the earliest seasons have only one to five years of minor league
history behind them. Whoever uses them (the pooled model, EFV_X3, or the 2026 training fold)
registers that use first.

Terms: Baseball America, Baseball Prospectus and Minor League Ball all limit their content
to personal, non-commercial use. Only list facts (name, rank, team, position, grade, date)
are stored, nothing is published, and the raw pages stay in the local cache.

## Owner question X5-Q1: what to do with the 995 older-list rows

The older lists (Baseball America Top 100 and team Top 10s, Baseball Prospectus Top 100,
Minor League Ball Top 20s) add 995 resolved development rows (819 of them in 2006 to 2010)
and shrink the development frame's mde95 from 0.0180 to 0.0166. Nothing served moved.

Options (the default is applied now):

- (a) DEFAULT: keep them as a development lab artifact (`data/_labs/efv_x5/`). The next
  modelling task that wants them (EFV_X3_POOLED_MODEL or EFV_2026_FOLD_TRAINING) widens the
  development vintages to 2006 to 2010 and joins outcomes under its own registration.
  Changes nothing today.
- (b) Adopt them into the development frame now (widen `efv_vintage_frame.DEV_VINTAGES` to
  2006 and let the archived lists count as real graders in the frame). Every later
  development number moves, and pre-2011 rows are scored against the old list's rank
  because no PROSPX consensus exists before 2011.
- (c) Keep only the non-Baseball America sources (Baseball Prospectus and Minor League Ball),
  if you would rather not hold facts drawn from Baseball America's pages given its terms.
  The gain falls from 995 to 616 rows (379 rows rest on Baseball America alone) and the
  registered mde95 to about 0.0171 instead of 0.0166.
- (d) Source more before adopting: Baseball Prospectus team Top 11s (2008 to 2011),
  Sickels 2012 to 2016, FanGraphs team lists through WebFetch, and a date for Baseball
  America's 2014, 2016 and 2017 Top 100s.

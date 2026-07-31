# FanGraphs FV / 20-80 framework: source-faithful reference

Purpose: a single implementable record of what has actually been published about the 20-80
scouting scale, Future Value (FV), prospect dollar valuation, and prospect risk. Every table
below is transcribed from the named source. Every definitional claim is backed by a short
attributed quote so a later reader can separate our paraphrase from the outlet's actual words.

SCOPE: this file spans THREE outlets, not one. Parts 1 through 10 are FanGraphs, which is the
scale our own FV is defined against. Part 11 covers MLB Pipeline and Baseball America, the two
live consensus sources our `grade_normalization` module quantile-maps onto the FanGraphs scale,
and states precisely where the three outlets disagree about what the same number means. Part 12
covers Baseball America's explicit risk/variance dimension, which has no FanGraphs equivalent.
The filename is unchanged deliberately; FanGraphs remains the reference frame and the other two
outlets are documented as sources that must be translated INTO it.

House style note: this file contains no em-dashes and no en-dashes. Where a source
sentence used one, it has been rewritten as " - " inside the quote. Where a source TABLE
CELL held a dash placeholder (an em-dash or en-dash meaning "not applicable"), it is
transcribed here as `n/a`. No other edit has been made to quoted text. Typos in the
source are marked `[sic]`.

## Sources read

All fetched 2026-07-30, as raw HTML over `curl`, then parsed to text and tables. The
WebFetch summarizer refused verbatim reproduction of one article, so all extraction below
is from the raw HTML.

Primary (assigned):

| # | Title | Author | URL | Publication era |
|---|---|---|---|---|
| S1 | The Details of Our New Prospect Valuation Methodology | Ben Clemens | https://blogs.fangraphs.com/the-details-of-our-new-prospect-valuation-methodology/ | 2026 |
| S2 | The New FanGraphs Scouting Primer | Eric Longenhagen and Kiley McDaniel | https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/ | 2018 |
| S3 | Scouting Explained: The 20-80 Scouting Scale | Kiley McDaniel | https://blogs.fangraphs.com/scouting-explained-the-20-80-scouting-scale/ | 2014 |

The WAR-translation lineage (assigned mid-task):

| # | Title | Author | URL | Publication era |
|---|---|---|---|---|
| W1 | The 20-80 Scouting Scale, Translated to Wins | Carson Cistulli | https://blogs.fangraphs.com/the-20-80-scouting-scale-translated-to-wins/ | 2013 |
| W2 | The 20-80 Scale, SABR Style | Mark Smith | https://blogs.fangraphs.com/the-20-80-scale-sabr-style/ | Feb 2013 |
| W3 | The 20-80 Scale, Saber Style (Again Yet Different) | Mark Smith | https://blogs.fangraphs.com/the-20-80-scale-saber-style-again-yet-different/ | Feb 2013 |

Followed from the primary sources' own links:

| # | Title | Author | URL | Era |
|---|---|---|---|---|
| L1 | Introducing an Updated Method for Prospect Valuation | Ben Clemens | https://blogs.fangraphs.com/introducing-an-updated-method-for-prospect-valuation/ | 2026 |
| L2 | An Update to Prospect Valuation | Craig Edwards | https://blogs.fangraphs.com/an-update-to-prospect-valuation/ | 2019 |
| L3 | Putting a Dollar Value on Prospects Outside the Top 100 | Craig Edwards | https://blogs.fangraphs.com/putting-a-dollar-value-on-prospects-outside-the-top-100/ | 2019 |
| L4 | What Are Teams Paying For A Win In Free Agency? 2026 Edition | Ben Clemens | https://blogs.fangraphs.com/what-are-teams-paying-for-a-win-in-free-agency-2026-edition/ | 2026 |
| L5 | How Do Baseball Teams Discount the Future? | Matt Swartz | https://blogs.fangraphs.com/how-do-baseball-teams-discount-the-future/ | 2017 |
| L6 | How Do Prospect Grades Translate to Future Outcomes? | Ben Clemens | https://blogs.fangraphs.com/how-do-prospect-grades-translate-to-future-outcomes/ | 2025 |
| L7 | Prospect Week Primer | Eric Longenhagen | https://blogs.fangraphs.com/prospect-week-primer/ | 2022 |
| L8 | How To Use The Board: A Tutorial | Eric Longenhagen | https://blogs.fangraphs.com/how-to-use-the-board-a-tutorial/ | 2021 |
| L9 | Valuing Prospects: The Pros and Cons of a Single Number | Eric Longenhagen | https://blogs.fangraphs.com/valuing-prospects-the-pros-and-cons-of-a-single-number/ | 2017 |
| L10 | Top 200 Prospects: The Process and Introduction | Kiley McDaniel | https://blogs.fangraphs.com/top-200-prospects-the-process-and-introduction/ | 2015 |
| L11 | Scouting Explained: The Mysterious Hit Tool, Pt. 1 | Kiley McDaniel | https://blogs.fangraphs.com/scouting-the-hit-tool-pt-1/ | 2014 |
| L12 | Scouting Explained: The Mysterious Hit Tool, Pt. 2 | Kiley McDaniel | https://blogs.fangraphs.com/scouting-the-hit-tool-pt-2/ | 2014 |
| L13 | Scouting Explained: The Mysterious Hit Tool, Pt. 3 | Kiley McDaniel | https://blogs.fangraphs.com/scouting-the-hit-tool-pt-3/ | 2014 |
| L14 | Scouting Explained: The Mysterious Hit Tool, Pt. 4 | Kiley McDaniel | https://blogs.fangraphs.com/scouting-the-hit-tool-pt-4/ | 2014 |
| L15 | Scouting Explained: The Mysterious Hit Tool Mailbag (Pt. 5) | Kiley McDaniel | https://blogs.fangraphs.com/scouting-the-hit-tool-pt-5/ | 2014 |
| L16 | Scouting Explained: The Mysterious Hit Tool, Pt. 6 | Kiley McDaniel | https://blogs.fangraphs.com/scouting-the-hit-tool-pt-6/ | 2014 |

Other outlets (assigned mid-task):

| # | Title | Author | URL | Era | Retrieval |
|---|---|---|---|---|---|
| P1 | Scouting Grades (glossary entry) | MLB.com / MLB Pipeline, unsigned | https://www.mlb.com/glossary/miscellaneous/scouting-grades | undated, live | Direct, HTTP 200 |
| B1 | Explaining The 20-80 Baseball Scouting Scale | Kyle Glaser, Baseball America | https://www.baseballamerica.com/stories/explaining-the-20-80-baseball-scouting-scale/ | undated, live | Blocked direct; read via Wayback snapshot 2026-07-20 |
| B2 | Explaining Baseball America's Updated MLB Prospect Grades & Risk System | J.J. Cooper, Baseball America | https://www.baseballamerica.com/stories/explaining-baseball-americas-updated-mlb-prospect-grades-risk-system/ | 2026 | Blocked direct; read via Wayback snapshot 2026-03-04 |

Retrieval honesty note on Baseball America: both BA URLs returned HTTP 403 to direct fetch
and to WebFetch. The 403 body is a Cloudflare "managed challenge" interstitial ("Enable
JavaScript and cookies to continue"), which is a bot block, NOT a paywall and NOT a 404. Both
articles were then read IN FULL from Internet Archive snapshots (B1 captured 2026-07-20, B2
captured 2026-03-04). Everything attributed to B1 and B2 below is complete article text from
those snapshots, not reconstruction and not summary. The one caveat that follows from using
snapshots is currency: if BA has edited either page since its snapshot date, this file reflects
the snapshot. B2 is explicitly a 2026 revision of BA's own system, so its content is current as
of the 2026 cycle.

Of the 29 URLs in this document, 27 returned HTTP 200 on direct fetch and 2 (both BA) required
the Wayback route. Nothing 404'd and nothing was paywalled. See the closing appendix for the
full fetch log and for the linked-but-not-read list.

Series completeness note: the "Scouting Explained" series index, as printed at the head of
both S3 (2014) and L10 (2015), lists exactly eight entries: an Introduction (which IS S3)
plus Hit Tool Pt 1 through Pt 6. There is no published "Scouting Explained" instalment for
power, speed, fielding, arm, or any pitch type. The series stopped after the hit tool.

---

# Part 1. The 20-80 scale

## 1.1 The distributional definition

> "The invention of the scale is credited to Branch Rickey and whether he intended it or
> not, it mirrors various scientific scales. 50 is major league average, then each 10 point
> increment represents a standard deviation better or worse than average. In a normal
> distribution, three standard deviations in either direction should include 99.7% of your
> sample, so that's why the scale is 20 to 80 rather than 0 and 100."
> - Kiley McDaniel, S3 (2014)

McDaniel immediately qualifies the normality assumption:

> "That said, the distribution of tools isn't a normal curve for every tool, but is
> somewhere close to that for most."
> - Kiley McDaniel, S3 (2014)

The 2018 primer restates the same construction and adds why granularity varies along the
curve:

> "The center of the scale (50) represents major-league average with each whole grade away
> from 50 representing a standard deviation away from it. The industry also uses grades of
> 45 and 55 as a means of assessment because there are so many players, fastballs, throwing
> arms, etc. hovering right around average that it's necessary to be more granular at that
> point on the talent curve. It's rare for a scout to use grades like 65 or 35 because that
> level of visual precision on those parts of the curve isn't all that feasible. Analysts
> are more likely to use those grades since they're looking at a Trackman readout or some
> other form of objective measure and that is literally where someone's exit velos or
> curveball spin might be on the curve."
> - Longenhagen and McDaniel, S2 (2018)

The 2022 restatement is the most explicit about the population the curve is drawn over:

> "Baseball talent is normally distributed across the population, with Trout existing at
> the far right tail of the continuum, and you and I somewhere toward the far left. When we
> zoom in and focus solely on the big league portion of the population, the bell curve shape
> still holds, with Trout on the far right, low-impact players with long careers grouped
> toward the middle, and career 'cup of coffee' types on the far left."
> - Eric Longenhagen, L7 (2022)

That is a load-bearing detail for implementation: the scale is defined against the
MAJOR LEAGUE population, not the minor league or all-baseball population.

## 1.2 Percentile / rarity readings of the tails

Two published rarity statements, which differ slightly from each other:

> "An 80 is incredibly rare because one would have to be 3 standard deviations above the
> mean (or in the top 0.1-0.2 percent of players), and it's a representation of the truly,
> truly elite."
> - Mark Smith, W2 (2013)

> "Statistically, only 0.1 percent of the population, or 1 in 1000, people are 3 standard
> deviations above (or below) the mean. 750 players will start the season on an Opening Day
> roster, which means there might not be an 80 in the bunch"
> - Mark Smith, W3 (2013)

> "In a normal distribution, only about 2% of the population exists two or more standard
> deviations above the average, which means that in a big-league player population of about
> 800 guys, only about 10-15 would be '70s' or '80s.'"
> - Eric Longenhagen, L7 (2022)

Longenhagen also gives the reasoning for truncating at three SD rather than extending the
scale, using a non-baseball example:

> "The scale doesn't go from 0-to-100 because the overwhelming majority of data exists
> within three standard deviations on either side of average, with data existing outside
> those deviations considered noise. If I was going to graph the height of human men, Joel
> Embiid and Yao Ming would both be 80s even though Yao has five or six inches on Embiid;
> seven-footers are three standard deviations away from the 6-foot average, making Yao and
> others his height noise."
> - Eric Longenhagen, L7 (2022)

Implementation consequence: the scale is CENSORED at both ends. An 80 is not "exactly
+3 SD"; it is "+3 SD or anything beyond". Do not invert an 80 back into a point estimate.

## 1.3 The adjective ladder

Verbatim from the S3 objective-tool table's "Tool Is Called" column, which is the only
place FanGraphs prints the ladder as a table:

| Grade | Tool Is Called |
|---|---|
| 80 | 80 |
| 75 | (no term) |
| 70 | Plus Plus |
| 65 | (no term) |
| 60 | Plus |
| 55 | Above Avg |
| 50 | Avg |
| 45 | Below Avg |
| 40 | (no term) |
| 35 | (no term) |
| 30 | (no term) |

Quantity and units: none. This is a naming convention only. Blank rows are blank in the
source, not omitted here.

The same ladder in prose, with the reason 75 and 65 have no names:

> "An 80 tool is called 80. It's really rare, so why do we need another name for it? 75 is
> almost never used because scouts will yell at you to make a choice and many don't use 65,
> though it's much more accepted than 75. These half grades like 65 and 75 don't have
> separate terms because many teams use a 2-8 scale rather than 20-80 and 2-8 is the scale
> that was predominant when many of today's top scouts were starting out."
> - Kiley McDaniel, S3 (2014)

McDaniel's 2015 restatement adds an important qualitative anchor per grade:

> "Average is 50, above average is 55, below average is 45, plus is 60, plus-plus is 70 and
> 80 is just called 80 because it's so rare and special that it doesn't need another name;
> think Giancarlo Stanton's power, Billy Hamilton's speed, or Randy Johnson's fastball."
> - Kiley McDaniel, L10 (2015)

Note what is NOT in any FanGraphs source: the words "poor" and "elite" are not assigned to
specific grades anywhere in these articles. The ladder as FanGraphs publishes it runs
Below Avg (45) / Avg (50) / Above Avg (55) / Plus (60) / Plus Plus (70) / 80 (80). There is
no published adjective for 40, 35, 30, 25, or 20. "Elite" is used in prose (for example
"the truly, truly elite" for 80s, and "anything more than that means we think they're
elite" for relievers above 45 FV) but is never pinned to a numeric grade in a table.

## 1.4 Present / future notation and the 2-8 shorthand

> "Scouts also use present and future grades for each tool. Present grades often are 20's
> for high school players while, in the upper levels of the minors, the gap between present
> and future grades is very small. A present 20 and future 50 grade on a tool is noted as
> 20/50."
> - Kiley McDaniel, S3 (2014)

Worked example of the full report format, from the Joey Gallo report reproduced in L14:

> "Hit: 30/45, Game Power: 60/70, Raw Power: 80/80, Speed: 40/40, Field: 45/50, Throw:
> 70/70 Upside: .260/.350/.500 (30-35 HR), fringy 3B or solid RF FV/Risk: 60, High (4 on a
> 1-5 scale) Projected Path: 2014: AA, 2015: AAA/MLB, 2016: MLB"
> - Kiley McDaniel, L14 (2014)

For amateur present-hit grades specifically, McDaniel switched to a peer-relative grade:

> "The present hit grades for Rodgers and for all amateur players going forward is a peer
> grade...rather than just putting blanket 20s on everyone's present hit tool. A peer grade
> means how the player performs currently in games relative to his peers: players the same
> age and general draft status or skill level. Some teams started using this system to avoid
> over-projecting a raw hitter; some use the rule that you can't project over 10 points
> above the peer grade for the future grade."
> - Kiley McDaniel, L15 (2014), quoting his own draft rankings

That last clause is a hard constraint some organizations apply: future grade minus present
peer grade is capped at +10 points.

## 1.5 Which tools exist, and what is folded into each

> "The five tools for position players are 1) Hitting 2) Power 3) Running 4) Fielding and
> 5) Throwing."
> - Kiley McDaniel, S3 (2014)

> "Throwing accuracy is folded into the throwing tool grade (which is mostly arm strength
> since accuracy problems are often fixable) while fielding range, hands, instincts and all
> the components of defense are folded into the fielding grade. Base running skill and good
> jumps out of the batter's box are also folded into the run grade. Many organizations and I
> will split power into game power (predicting big league power stats) and raw power (how
> far he can hit the ball in batting practice) but they are often the same [...] The hit tool
> includes plate discipline (the most commonly asked-for sixth tool by the internet)"
> - Kiley McDaniel, S3 (2014)

The raw/game power split, restated with units:

> "I split power into raw (deepest shot in batting practice) and game (homers per full MLB
> season at maturity)"
> - Kiley McDaniel, L16 (2014)

For pitchers:

> "Scouts grade each of their pitches (fastball, curveball, slider, changeup, splitter,
> cutter being the most common) on the 20-80 scale, then either grade the command of each
> pitch separately or have one overall command grade. [...] That said, the three core pitches
> (fastball, changeup, best breaking ball) and command are the four core grades that scouts
> use to make decisions and that inform the overall grade."
> - Kiley McDaniel, S3 (2014)

Two published tool-to-role thresholds for pitchers:

> "A 60 or better off-speed pitch is the standard for being called a 'swing and miss' pitch;
> you need two 60 pitches and at least an average third pitch and command to be a #3
> starter, for example."
> - Kiley McDaniel, L10 (2015)

The hit tool is decomposed by McDaniel into three graded components (L12): (1) "The Tools"
(bat speed, raw strength, swing structure and path), (2) "Bat Control" (also called "feel
for the bat head", the ability to adjust mid-swing to the pitch; Ichiro and Vladimir
Guerrero named as 80s), and (3) a third grouping covering approach and performance context.
Each is graded 20-80 and then combined into the single hit grade. This is McDaniel's
personal method, explicitly not an industry standard:

> "Scouts all have different ways that they do it and I've tinkered with different methods,
> but this one works for me"
> - Kiley McDaniel, L12 (2014)

---

# Part 2. Per-tool grade tables mapped to measured units

## 2.1 The industry-consensus objective table (S3, 2014)

This is the single most reproduced table in the FanGraphs corpus. It appears identically in
S3 (2014), L10 (2015), and L14 (2014).

| Grade | Tool Is Called | Fastball Velo | Batting Avg | Homers | RHH to 1B | LHH to 1B | 60 Yd Run |
|---|---|---|---|---|---|---|---|
| 80 | 80 | 97 | .320 | 40+ | 4.00 | 3.90 | 6.3 |
| 75 | | 96 | .310 | 35-40 | 4.05 | 3.95 | 6.4 |
| 70 | Plus Plus | 95 | .300 | 30-35 | 4.10 | 4.00 | 6.5 |
| 65 | | 94 | .290 | 27-30 | 4.15 | 4.05 | 6.6 |
| 60 | Plus | 93 | .280 | 23-27 | 4.20 | 4.10 | 6.7 |
| 55 | Above Avg | 92 | .270 | 19-22 | 4.25 | 4.15 | 6.8 |
| 50 | Avg | 90-91 | .260 | 15-18 | 4.30 | 4.20 | 6.9-7.0 |
| 45 | Below Avg | 89 | .250 | 12-15 | 4.35 | 4.25 | 7.1 |
| 40 | | 88 | .240 | 8-12 | 4.40 | 4.30 | 7.2 |
| 35 | | 87 | .230 | 5-8 | 4.45 | 4.35 | 7.3 |
| 30 | | 86 | .220 | 3-5 | 4.50 | 4.40 | 7.4 |

Quantity and units, column by column:

- Fastball Velo: miles per hour, average fastball velocity. PITCHERS only.
- Batting Avg: major league batting average at maturity. This is the HIT tool, HITTERS only.
- Homers: home runs per full major league season at maturity. This is the GAME POWER tool
  (per L16: "game (homers per full MLB season at maturity)"), HITTERS only. Note 80 is an
  open interval ("40+") and every other row is a closed range, so this column is a band
  scale, not a point scale.
- RHH to 1B and LHH to 1B: seconds, home plate to first base, from the right-handed and
  left-handed batter's box respectively. This is the RUN tool, HITTERS only. Lower is
  better. The handedness adjustment is a flat 0.10 seconds at every grade.
- 60 Yd Run: seconds, 60-yard dash. Also the RUN tool. Lower is better.

There is no exit velocity, spin rate, or arm-strength column in this or any other FanGraphs
table located. See Open Questions.

McDaniel's own caveats on this table:

> "This is a table showing the tool grades (fastball for pitchers, hit, power and speed for
> hitters) that have objective scales that every scout uses to grade. These scales will vary
> team to team, possibly shifted one notch in either direction, or maybe separate grades for
> fastball velocity for righties/lefties or starter/reliever but these are essentially
> industry consensus scales."
> - Kiley McDaniel, S3 (2014)

On the fastball column being a starting point rather than an answer:

> "Fastball velocity is pretty self-explanatory and this is used as a starting point, with
> many other pieces of information leading to 1-2 notch moves up or down. As mentioned above,
> lefty/righty and starter/reliever can be taken into account (though I and many teams don't
> do that, instead considering those factors in the overall grade at the end) while command,
> movement and deception are common other components to move up/down from the starting
> velocity grade."
> - Kiley McDaniel, S3 (2014)

On the two speed columns measuring different things:

> "For the two different run grade scale, we have the 60-yard dash, which is a combine-style
> showcase measure of straight-line speed akin to the 40 from the football combine while the
> home to first base times from either batter's box are functional game speed. Often scouts
> use the raw times (comparing them with scouts nearby to verify accuracy) then round up/down
> based on wind/grass conditions for the 60 or how good of a jump out of the box and effort
> level on times to first base."
> - Kiley McDaniel, S3 (2014)

On the hit and homer columns being approximations he is not fully happy with:

> "I'll go more into the batting average/on base/hit tool thing in the hit tool article but
> it seems like even the most statistically-inclined people agree this scale is kind of
> agreeable for what it's trying to do. For homers, it's a similar situation that I'll get
> into later; ideally you'd like isolated power for projection purposes, but this scale works
> for what it's trying to do."
> - Kiley McDaniel, S3 (2014)

And the explicit warning that the hit grade is batting average only, which makes
high-walk hitters rank above their hit grade:

> "Notice that the hitting tool grade only refers to batting average, so some prospects with
> strong plate discipline - Jesse Winker and Michael Conforto, for example - are rated higher
> than you'd expect given their pure hit tool grade. The hit tool is just meant to grade the
> ability to make contact and the raw tools (bat speed, eye-hand coordination, etc)."
> - Kiley McDaniel, L10 (2015)

Note this sits in direct tension with S3's own claim that "The hit tool includes plate
discipline". See Open Questions.

## 2.2 Mark Smith's z-score tables (W2, 2013)

W2's method, in his words:

> "I used statistics from 2010-2012 because the timeframe is large enough to get a sample and
> small enough to stay within the recent run environment, and I used Russell Carleton's
> measurements for each statistic to get a sample at least indicative of skill."
> - Mark Smith, W2 (2013)

All W2 tables below: grade rows carry an explicit z column (standard deviations from the
major league mean), and the statistic columns are three-year (2010-2012) player values.
The "Player" columns are the exemplar player Smith found sitting at that value; they are
transcribed for fidelity but carry no numeric meaning.

### Hit tool

| Hit Tool | z | BA | Player | BABiP | Player |
|---|---|---|---|---|---|
| 80 | 3 | .336 | Miguel Cabrera | .383 | n/a |
| 70 | 2 | .313 | Josh Hamilton | .357 | Dexter Fowler |
| 60 | 1 | .290 | Martin Prado | .332 | David Wright |
| 50 | 0 | .267 | Rafael Furcal | .306 | Asdrubal Cabrera |
| 40 | -1 | .244 | Vernon Wells | .280 | Shane Victorino |
| 30 | -2 | .221 | Brendan Ryan | .254 | Mark Teixeira |
| 20 | -3 | .199 | n/a | .228 | n/a |

Quantity and units: three-year (2010-2012) batting average and BABIP, HITTERS. Qualifier
1000 PA for BA, 1500 PA for BABIP. Implied SD: 0.0228 BA, 0.0258 BABIP.

### Power tool

| Power Tool | z | ISO | Player | HR/PA | Player |
|---|---|---|---|---|---|
| 80 | 3 | .294 | Jose Bautista | 6.6% | Jose Bautista |
| 70 | 2 | .242 | Joey Votto | 5.2% | Edwin Encarnacion |
| 60 | 1 | .191 | Buster Posey | 3.8% | Kevin Youkilis |
| 50 | (blank) | .140 | Nick Markakis | 2.4% | Shane Victorino |
| 40 | -1 | .089 | Ryan Hanigan | 1.0% | Jose Altuve |
| 30 | -2 | .038 | Ramiro Pena | -0.4% | n/a |
| 20 | -3 | -.013 | n/a | -1.8% | n/a |

Quantity and units: three-year ISO and home runs per plate appearance, HITTERS, 180 PA
minimum, pitchers excluded. Implied SD: 0.051 ISO, 1.4% HR/PA. Smith flags that the bottom
rows go impossible:

> "As for the negative numbers, it's mainly just a glitch in the numbers (those negatives
> obviously aren't possible)."
> - Mark Smith, W2 (2013)

### Speed tool

| Speed Tool | z | SB/3 | Player | BsR/3 | Player |
|---|---|---|---|---|---|
| 80 | 3 | 38 | Ichiro Suzuki | 9 | Michael Bourn |
| 70 | 2 | 29 | Elvis Andrus | 6 | Rajai Davis |
| 60 | 1 | 19 | Chris Young | 3 | Andrew McCutchen |
| 50 | (blank) | 9 | Jon Jay | (blank) | Yunel Escobar |
| 40 | -1 | (blank) | n/a | -3 | Jason Kubel |
| 30 | -2 | -10 | n/a | -5 | Adrian Gonzalez |
| 20 | -3 | -20 | n/a | -8 | Ryan Howard |

Quantity and units: stolen bases per season (three-year total divided by 3) and BsR per
season (three-year total divided by 3, in runs). HITTERS. Implied SD: about 9.6 SB/yr and
about 2.9 BsR runs/yr. Blank cells are blank in the source. This table is internally rough:
the SB column runs negative, which is impossible, and the 50 row for BsR is blank rather
than the 0 that BsR's definition requires.

### Defense tool

| Defense | z-Score | UZR/150 | Player | Fld/3 | Player |
|---|---|---|---|---|---|
| 80 | 3 | 22.8 | n/a | 17.9 | Brett Gardner |
| 70 | 2 | 15.7 | Adrian Beltre | 12.4 | Michael Bourn |
| 60 | 1 | 8.7 | Giancarlo Stanton | 6.9 | Carlos Gomez |
| 50 | (blank) | 1.6 | Casey McGehee | 1.5 | Drew Stubbs |
| 40 | -1 | -5.4 | Dan Uggla | -4.0 | Rickie Weeks |
| 30 | -2 | -12.5 | Asdrubal Cabrera | -9.5 | Michael Morse |
| 20 | -3 | -19.6 | n/a | -14.9 | n/a |

Quantity and units: UZR per 150 games (runs) and Fld per season (three-year total divided
by 3, runs). HITTERS, 2500 innings minimum. Implied SD: about 7.1 UZR/150 runs, about 5.5
Fld runs. Note the 50 row is +1.6 and +1.5, not 0, so this table's centre is the qualified
population mean and not the league mean. That is a real, non-obvious calibration wrinkle.
Smith adds that pooling positions was forced:

> "Defense might be the hardest tool to look at in this situation, and while it might have
> been better to look at this position-by-position, the sample (needing 2500 innings) was
> already pretty small."
> - Mark Smith, W2 (2013)

### Arm tool

| Arm Tool | z | rARM/3 | Player | ARM/3 | Player |
|---|---|---|---|---|---|
| 80 | 3 | 8.8 | Alex Gordon | 8.5 | Jeff Francoeur |
| 70 | 2 | 5.9 | Jose Bautista | 5.7 | Alex Gordon |
| 60 | 1 | 3.0 | Jayson Werth | 3.0 | Jayson Werth |
| 50 | (blank) | 0.2 | Austin Jackson | 0.2 | Matt Kemp |
| 40 | -1 | -2.7 | Ichiro Suzuki | -2.5 | Matt Holliday |
| 30 | -2 | -5.6 | n/a | -5.3 | Ryan Braun |
| 20 | -3 | -8.4 | n/a | -8.1 | n/a |

Quantity and units: outfield arm runs per season (three-year total divided by 3). Implied
SD about 2.9 runs. This is the only arm-strength grade table published, and Smith disclaims
it as a proxy that measures the wrong thing:

> "I used these arm ratings, but they only exist for outfielders and include accuracy as
> well as arm strength. Radar gun measurements and/or FIELD f/x velocity measurements would
> probably be more helpful for objectively measuring this tool."
> - Mark Smith, W2 (2013)

This is the closest FanGraphs comes to a published arm-strength unit scale, and it is in
defensive runs, NOT in miles per hour or feet. There is no published grade-to-mph
arm-strength table.

### Fastball velocity, split by role

| FB Velo | z | SP Velo | Player | RP Velo | Player |
|---|---|---|---|---|---|
| 80 | 3 | 97 | n/a | 100 | n/a |
| 70 | 2 | 95 | Stephen Strasburg | 97 | Daniel Bard |
| 60 | 1 | 93 | Mat Latos | 95 | Drew Storen |
| 50 | (blank) | 91 | Adam Wainwright | 92 | Ramon Ramirez |
| 40 | -1 | 88 | Mike Fiers | 89 | Michael Wuertz |
| 30 | -2 | 86 | Mark Buerhle [sic] | 86 | Pat Neshek |
| 20 | -3 | 84 | Jamie Moyer | 84 | Livan Hernandez |

Quantity and units: miles per hour, average fastball velocity, PITCHERS, split starter vs
reliever. Implied SD about 2.2 mph (SP) and 2.7 mph (RP). Relievers are held to a higher bar
by 1 to 3 mph at every grade. On handedness:

> "The mean for the two were 91.2 (RHP) and 90.5 (LHP), which was expected, but when I
> applied standard deviations, the SD for LHP was larger (probably due to the much smaller
> sample). A 60-80 necessitated a higher velocity from a LHP than a RHP, which didn't seem to
> make sense. Using the mean velocity difference of about 1 mph, you can dock the grades
> shown above by 1 mph and use that for lefties if you so choose."
> - Mark Smith, W2 (2013)

So the published handedness adjustment for fastball velocity is: subtract 1 mph from each
threshold for left-handed pitchers. Smith presents it as optional.

### Control

| Control | z | SP BB% | Player | RP BB% | Player |
|---|---|---|---|---|---|
| 80 | -3 | 1.7% | n/a | 2.0% | n/a |
| 70 | -2 | 3.7% | Roy Halladay | 4.4% | Sergio Romo |
| 60 | -1 | 5.7% | Rick Porcello | 6.8% | Jason Motte |
| 50 | (blank) | 7.8% | Derek Holland | 9.2% | Guillermo Mota |
| 40 | 1 | 9.8% | C.J. Wilson | 11.6% | Manny Parra |
| 30 | 2 | 11.8% | Danny Duffy | 13.9% | Tim Collins |
| 20 | 3 | 13.9% | Jonathan Sanchez | 16.3% | Carlos Marmol |

Quantity and units: walk rate, PITCHERS, split starter vs reliever. Implied SD about 2.0
percentage points (SP) and 2.4 (RP). NOTE THE SIGN INVERSION: the z column runs -3 at the
80 row and +3 at the 20 row, because a lower walk rate is better. Any implementation reading
these tables generically must special-case the sign on control.

Smith's own note on the top of this scale being unreachable:

> "You'll note that there are no 80 control guys, and no one was even within 1% of reaching
> that grade. Perhaps 80 control (in its literal definition) is too high of a standard here,
> but there's also the possibility that there is such a thing as 'throwing too many strikes'"
> - Mark Smith, W2 (2013)

W2's overall framing of what these tables are for:

> "The point of all of this was simply to give us all an idea of what it would actually take
> to reach a certain scouting grade."
> - Mark Smith, W2 (2013)

W2 contains NO WAR mapping and NO overall-FV mapping. It is per-tool only.

---

# Part 3. FV mapped to role and to WAR

## 3.1 McDaniel's combined overall-grade table (S3, 2014)

This is the table the owner's summary is quoting. It appears identically in S3 (2014) and
L10 (2015).

| Grade | Hitter | Starting Pitcher | Relief Pitcher | WAR |
|---|---|---|---|---|
| 80 | Top 1-2 | #1 Starter | n/a | 7.0 |
| 75 | Top 2-3 | #1 | n/a | 6.0 |
| 70 | Top 5 | #1/2 | n/a | 5.0 |
| 65 | All-Star | #2/3 | n/a | 4.0 |
| 60 | Plus | #3 | High Closer | 3.0 |
| 55 | Above Avg | #3/4 | Mid Closer | 2.5 |
| 50 | Avg Regular | #4 | Low CL/High SU | 2.0 |
| 45 | Platoon/Util | #5 | Low Setup | 1.5 |
| 40 | Bench | Swing/Spot SP | Middle RP | 1.0 |
| 35 | Emergency Call-Up | Emergency Call-Up | Emergency Call-Up | 0.0 |
| 30 | *Organizational | *Organizational | *Organizational | -1.0 |

Quantity and units of the WAR column: WAR per SEASON, framed as TRUE TALENT LEVEL, not a
career total and not an observed single season. McDaniel is explicit:

> "The WAR grade here is meant as a true talent level, so crazy BABIP and UZR swings or
> playing time varying year-to-year doesn't confuse us."
> - Kiley McDaniel, S3 (2014)

The `n/a` cells for relievers at 65 through 80 are dash placeholders in the source, meaning
relievers do not reach those grades. That is the documented reliever FV ceiling in this
table: 60 (High Closer). See Part 5.

The two footnotes travel with the table:

> "* 'Organizational' is the term scouts use to describe a player that has no major league
> value; he's just there to fill out a minor league roster and be a good influence on the
> prospects, though sometimes org players can outplay that projection.
> ** I didn't continue down to 20 on either scale since it's almost never relevant for
> players that I'll be writing about or any of their tools, other than speed for big fat
> sluggers."
> - Kiley McDaniel, S3 (2014)

So there is NO published FV row for 20 or 25 in the overall-grade table. Anyone
implementing 20 and 25 FV rows is extrapolating.

McDaniel also disclaims the "Top 1-2" style role labels as conventional rather than literal:

> "The concept that an 80 is just one or two big leaguers at each position is a traditional
> one while technically there could be a bunch of 7-win guys at any position. The 'Top 1-2'
> notation for hitters is just to give an idea of typically how exclusive each group should
> be, realizing it isn't always true."
> - Kiley McDaniel, S3 (2014)

And explains the starter-number tiers, which are tiers and not depth-chart slots:

> "Most scouts agree there are only ever 8-12 pitchers that could be called #1s or aces at
> any given time, but then there's like 20 #2s and like 75 #3s. Many fans get tripped up by
> this term, thinking there are 30 of each type or that every team has exactly one version of
> each; that's an understandable misunderstanding."
> - Kiley McDaniel, S3 (2014)

### The 2015 restatement says PEAK, and this matters

In L10, McDaniel attaches a different quantity to the same table:

> "for a big league ready player with relatively little risk that I peg as a 55 FV - Rays RF
> Steven Souza, for example - this means I think his most likely peak season(s) in the big
> leagues will be +2.5 to + 2.9 wins, with a relatively equal chance of his peak being a
> notch higher or lower than that."
> - Kiley McDaniel, L10 (2015)

That is PEAK-season WAR. The 2018 and 2022 primers explicitly reject that reading. See
Part 6.3 and Part 7.1. This is the single most consequential inconsistency in the corpus.

## 3.2 The 2018 primer: hitters (S2)

FV definition, first:

> "FV stands for Future Value, and it's the way we distill each player's scouting evaluation
> into a single expression. Broadly stated, Future Value is a grade on the 20-80 scale that
> maps to anticipated annual WAR production during the player's first six years of service."
> - Longenhagen and McDaniel, S2 (2018)

Construction of the table:

> "Here is fresh math from the 2018 season regarding WAR distribution of hitters mapped to
> the 20-80 scale. Eric calculated it twice, first by using all hitters with 200 plate
> appearances (which produced a sample of 355 players, or approximately every team's starting
> lineup and its three most used bench players) and then the best 255 players from that sample
> (effectively, the starters). The WAR bands created by these two samples are very similar to
> the ones you've seen on this site before."
> - Longenhagen and McDaniel, S2 (2018)

| Scouting Scale | Role | WAR |
|---|---|---|
| 20 | Org guy | n/a |
| 30 | Up & Down | <-0.1 |
| 40 | Bench Player | 0.0 to 0.7 |
| 45 | Low End Reg/Platoon | 0.8 to 1.5 |
| 50 | Avg Everyday Player | 1.6 to 2.4 |
| 55 | Above Avg Reg | 2.5 to 3.3 |
| 60 | All Star | 3.4 to 4.9 |
| 70 | Top 10 overall | 5.0 to 7.0 |
| 80 | Top 5 overall | > 7.0 |

Quantity and units: WAR per SEASON, specifically the AVERAGE ANNUAL WAR over the player's
first six years of major league service. HITTERS. Bands, not points. Note there are NO rows
for 25, 35, 65, or 75 in this table. 60 spans 1.5 WAR of width while 45, 50 and 55 span
about 0.8 each, so the band widths are not uniform.

## 3.3 The 2018 primer: starting pitchers (S2)

> "Pitching is a little more complicated because pitching standards and roles are changing.
> Velocity and strikeout rates are higher than ever. Starting-pitcher innings are lower than
> ever. Whatever the case, here's how 2018's starters shake out based on WAR distribution.
> For this, Eric's first pass included all starters who threw at least 50 innings (which
> ended up being 180 pitchers, essentially starters No. 1 through 6 on each team) then the
> top 150 pitchers from that sample (all 30 teams' starting rotations)."
> - Longenhagen and McDaniel, S2 (2018)

| Scouting Scale | Role | WAR |
|---|---|---|
| 20 | Org Guy | n/a |
| 30 | Up & Down | < -0.1 |
| 40 | Backend starters, FIP typically close to 5.00 | 0.0 to 0.9 |
| 45 | #4/5 starters, FIP approx 4.20 | 1.0 to 1.7 |
| 50 | #4 starters. Approx 4.00 FIP, at times worse but then with lots of innings | 1.8 to 2.5 |
| 55 | #3/4 starters. Approx 3.70 FIP along with about 160 IP | 2.6 to 3.4 |
| 60 | #3 starters, 3.30 FIP, volume approaching 200 innings | 3.5 to 4.9 |
| 70 | #2 starters, FIP under 3, about 200 IP | 5.0 to 7.0 |
| 80 | #1s. Top 1-3 arms in baseball. 'Ace' if they do it several years in a row. | >7.0 |

Quantity and units: WAR per SEASON, average annual over the first six years of service.
STARTING PITCHERS. The FIP and IP figures inside the Role column are FanGraphs' own
role anchors, in FIP runs and innings pitched respectively.

FanGraphs then explicitly endorses collapsing the hitter and pitcher tables back onto
McDaniel's 2014 combined table:

> "The pitcher and position-player WAR curves are similar enough that, especially when we
> consider WAR's margin for error, it's reasonable to round and combine these two tables
> pretty much exactly the way Kiley did back in 2014."
> - Longenhagen and McDaniel, S2 (2018)

## 3.4 The 2022 restatement (L7)

L7 reprints the hitter table with only cosmetic label changes (30 becomes "Fringe
MLB/Triple-A depth" rather than "Up & Down"; capitalisation differs). The WAR bands are
IDENTICAL to 2018. It attaches this caveat, which 2018 did not:

> "Don't let the decimals fool you into thinking this is perfectly exact. These WAR bands
> are based on actual big league standard deviations, but the lines between the buckets
> aren't as stark as the chart makes it seem."
> - Eric Longenhagen, L7 (2022)

L7's pitcher table changes the bottom row from "30" to "35/35+" and rewrites the role text:

| Scouting Scale | Role | WAR |
|---|---|---|
| 20 | Org guy | n/a |
| 35/35+ | Depth/spot starters, typically SP6 through SP8-10 in a given org | < -0.1 |
| 40 | Fifth starters who eat innings, FIP typically close to 5.00 | 0.0 to 0.9 |
| 45 | No. 4/5 starters, approx 4.20 FIP, on the fringe of playoff rotation | 1.0 to 1.7 |
| 50 | No. 4 starters, approx 4.00 FIP, sometimes worse w/lots of IP | 1.8 to 2.5 |
| 55 | "Mid-rotation" starters, lock for playoff rotation. Approx 3.70 FIP along w/about 160 IP | 2.6 to 3.4 |
| 60 | All-Star candidates, 3.30 FIP, volume approaching 200 innings | 3.5 to 4.9 |
| 70 | Top-of-the-rotation types, FIP under 3.00, about 200 IP | 5.0 to 7.0 |
| 80 | No. 1s. Top 1-3 arms in baseball. 'Ace' if they do it several years in a row. | >7.0 |

Quantity and units: identical to 3.3. Average annual WAR, first six years of service,
STARTING PITCHERS.

## 3.5 The 2022 hitter role table, with the "+" tiers (L7)

This is the only published FanGraphs table that gives role text for 35+ and 40+ on the
hitter side.

| FV | Role | Recent/Current Example |
|---|---|---|
| 30 | Org guy | Darick Hall |
| 35+ | One-tool bench guy, limited utility | Terrance Gore |
| 40 | RHH corner role, 5th OF, light-hitting utility, low-end 1B regular, backup C | Jordan Luplow, Guillermo Heredia, Sergio Alcantara, Christian Walker |
| 40+ | 40 role w/ premium tool or two | Adam Duvall, Edwin Rios, Adam Engel, Yandy Diaz |
| 45 | LHH platoon, luxury utility types, low-end MIF/CF regulars | Freddy Galvis, Seth Smith, Matt Joyce, Jackie Bradley Jr. |

Quantity and units: role labels only, no WAR. HITTERS. Note that the table STOPS at 45; L7
does not extend role text above 45 on the hitter side.

Note the handedness asymmetry baked into the role text: a right-handed-hitting corner or
platoon bat is a 40, while a LEFT-handed platoon bat is a 45. That is a published,
one-tier handedness adjustment for platoon bats.

## 3.6 The 2022 reliever role table (L7)

| FV | Role | Recent/Current Example |
|---|---|---|
| 30 | Org guy | C.J. Carter |
| 35+ | Up/down RP, optioned often | Cole Uvila |
| 40 | Single-inning middle reliever | Caleb Thielbar |
| 40+ | Multi-inning reliever, once-through-the-order types | Ryan Yarbrough |
| 45 | Traditional set-up type, high-leverage guys start here | Alex Colome |
| 45+ | Likely late-inning RPs with a shot to start | Ryne Nelson |
| 50 | No-doubt closers | James Karinchak |

Quantity and units: role labels only, no WAR. RELIEVERS. The table STOPS at 50. This is the
modern documented reliever FV ceiling in role terms, and it is TEN POINTS LOWER than the
2014 table's reliever ceiling of 60 (High Closer). See Part 5.3.

---

# Part 4. The "+" grades

There are TWO distinct and incompatible published meanings for "+", separated by about
seven years. Implementations must not conflate them.

## 4.1 Meaning A (2014-2015): a half-grade on a TOOL, worth 2.5 points

> "One more important addition to the scale that isn't shown here is solid average (52.5)
> and fringe-average or fringy (47.5). Since so many tools fall close to 50 but you may
> clearly prefer one 50 to the other, many scouts will use these terms to differentiate.
> Again, given the thousands of players I'll be grading, it makes sense to use this and it
> will show up as 45+ or 50+, since no scout has or ever will write 52.5 or 47.5 (they just
> put 50 then say fringy or solid average in the comments)."
> - Kiley McDaniel, S3 (2014)

Restated in L10:

> "Since there are so many players that have tools that are 45 or 50, I use a + to denote
> 47.5 (fringe-average or fringy) and 52.5 (solid-average), or the half-grades between these
> most common grades, 45, 50 and 55."
> - Kiley McDaniel, L10 (2015)

So under Meaning A: `45+` = 47.5 and `50+` = 52.5. The "+" adds 2.5 points and applies to
TOOL grades. Note that Meaning A produces a `50+` grade, which does NOT appear anywhere in
the modern FV ladder.

## 4.2 Meaning B (2021-2026): a break-out flag on an FV, sitting between the 5-point steps

> "What's with the pluses? For near-ready players, they correspond to the role the chart
> denotes. For younger players, they're a way of indicating we think a prospect has a chance
> to break out and move way up the scale. [...] Especially as it concerns younger players, the
> '+' tends to indicate that we think the player will have a higher FV in the future, meaning
> there's something about them indicative of continued development."
> - Eric Longenhagen, L7 (2022)

The fuller version from the Board tutorial:

> "For hitters, I tend to use this for a player who I think has a chance to break out.
> They're often the higher-upside players who are farther away from the big leagues. As they
> get closer to the big leagues, I try to just pick a plain FV grade to describe their role,
> though some players will retain a '+' designation either because of persistent perceived
> variance (Franchy Cordero would still be a 45+ FV for me, for example, as would Monte
> Harrison and maybe Tyler O'Neill) or because of how good they are in their role. For
> example, J.D. Davis is basically a four-corners bench player, which is a 40, but he has so
> much power that he's become a very good version of a player in that role. So if I knew a
> prospect was going to become J.D. Davis, they'd be a 40+ FV even if they're big league
> ready."
> - Eric Longenhagen, L8 (2021)

So under Meaning B, "+" carries THREE different jobs:

1. Break-out potential, for young / distant players. This is the dominant use.
2. Persistent variance, retained even for near-ready players.
3. "Very good version of" a sub-50 role, for near-ready players with a standout tool.

Meaning B's grade set, as it actually appears in published FanGraphs data, is
`35+, 40+, 45+`. There is NO `50+` and no `55+` in the modern FV ladder. The valuation
tables in Part 7 confirm this: they list 35+, 40, 40+, 45, 45+, 50, 55, 60, 65, 70 and
nothing else.

The break-out reasoning gets a worked example in L8, and it is the cleanest published
statement of how "+" is decided:

> "Margot has generated about 1.5 WAR annually throughout his career to this point
> (prorating the 2020 season due to the pandemic), which is a 45, so I should start with
> Swaggerty in the 45 FV bucket. But when I consider Swaggerty's handedness relative to
> Margot's (Swaggerty's going to have more of a platoon advantage than Manny does) and the
> fact that he still has an opportunity to make a swing change to tap into that
> aforementioned power (while for Margot that time has come and gone), I should at least
> consider making Swaggerty a 45+ FV based on the chance that he might be more than Margot
> ended up being"
> - Eric Longenhagen, L8 (2021)

## 4.3 Where "+" sits numerically for valuation

The 2026 valuation table treats the "+" tiers as genuine intermediate tiers with their own
values, strictly between the adjacent whole grades. From L1:

- 45 hitter: $14.5M. 45+ hitter: $18.5M. 50 hitter: $45.0M.
- 40 hitter: $5.5M. 40+ hitter: $8.0M. 45 hitter: $14.5M.

So `+` is worth much less than half a tier in dollar terms at the low end. From 45 to 45+ is
$4.0M, while 45+ to 50 is $26.5M. The tiers are NOT evenly spaced and interpolation between
whole grades would badly misprice 45+.

---

# Part 5. Position adjustments, handedness, role scarcity, reliever ceiling

## 5.1 Position

The most direct published statement:

> "A 50 FV indicates that we think a player will be an average everyday big leaguer at their
> given position."
> - Eric Longenhagen, L7 (2022)

"At their given position" is the whole position adjustment: FV is already position-relative.
The worked example:

> "It is very hard to be a 50 at first base, since there are so many sluggers at that
> position. Take Jesus Aguilar, for example. He has made an All-Star team and had one 3-WAR
> season, but the offensive bar at first base is so high that he's more often hovered around
> the 1-WAR mark and has accumulated 5.2 WAR since debuting in 2014. That's a 40. It is not
> disrespectful to call Aguilar (or any prospect) a 40, it's just a contextualization of
> their place on the baseball talent continuum."
> - Eric Longenhagen, L7 (2022)

Because FV routes through WAR, and WAR already carries a positional adjustment, the position
effect enters FV through WAR rather than as a separate additive term. There is no published
table of FV position adjustments.

On the fielding TOOL specifically, position makes the 20-80 scale awkward, and Longenhagen
says so:

> "This is the position player tool grade area that has the most room for improvement.
> Evaluating defense (mostly range for outfielders and a combination of range/footwork/actions
> for infielders) in a traditional sense is fine, but the entire 20-80 scale is not often used
> here, and it's hard to know if it should be. After all, wouldn't an 80-grade second baseman
> just be able to play SS?"
> - Eric Longenhagen, L8 (2021)

That is an explicit admission that the fielding grade is NOT a position-neutral z-score.

Position also drives the specificity requirement on defensive projection:

> "A finite scope also forces us to be more specific about defensive projections. It's easy
> to look at Vladimir Guerrero Jr. and say that he'll eventually outgrow third base and move
> to first, but it's more useful to be reasonably specific about when."
> - Longenhagen and McDaniel, S2 (2018)

## 5.2 Handedness

Three published handedness adjustments, all small and all in different units:

1. Run tool: left-handed hitters get 0.10 seconds knocked off every home-to-first threshold
   (S3 table, Part 2.1). A 4.20 from the left side and a 4.30 from the right side are both
   50-grade speed.
2. Fastball velocity: subtract 1 mph from each threshold for left-handed pitchers, per W2,
   presented as optional. S3 notes some teams keep separate lefty/righty velocity scales and
   others fold handedness into the overall grade instead.
3. FV role: a left-handed platoon bat is a 45 while a right-handed corner/platoon bat is a
   40 (L7 table, Part 3.5). Longenhagen also cites handedness as a reason to add a "+"
   (the Swaggerty example, Part 4.2).

## 5.3 Relievers

The 2014 position:

> "Relievers are hard to value in this sense, as many people and scouts would say you're
> crazy to not call Mariano Rivera an 80 since he's the best ever. The problem is that assumes
> he's as valuable as Mike Trout, which significantly fewer people believe [...] The WAR
> framework gives us a way to figure out where most players can be described and most elite
> relievers max out at around 3 wins, with very few racking up multiple seasons that good.
> You'd take a 60 position player over a 60 starting pitcher and either over a 60 reliever
> (all things being equal) due to attrition and these overall grades do their best to make the
> comparisons simpler."
> - Kiley McDaniel, S3 (2014)

Two separate claims there, both implementable: (a) the reliever FV ceiling in the 2014 table
is 60, because elite relievers max out near 3 WAR; (b) FV is NOT fungible across player type
even at equal grade, and the preference order at equal FV is position player > starter >
reliever, on attrition grounds.

The 2018 position, which lowers the ceiling substantially:

> "Relievers are punished in any WAR-based measure because they throw fewer innings. The best
> relievers on the planet typically yield about 3 WAR, while really excellent relievers are
> 1.5-2.0 WAR players. Some clubs do consider elite relievers to be 80s and think WAR-only
> analysis of relievers ignores too much of the leverage component of their jobs. This is
> probably true, but we also think relief usage is about to change in a way that both
> accentuates that component but also changes the volume of innings they throw. For now,
> single-inning middle-relief types get a 40 FV from us, we slap 45 FVs on arms we think will
> be dominant bullpen pieces (Seranthony Dominguez and A.J. Minter are two examples from
> recent years), and anything more than that means we think they're elite, but most elite
> relievers were starters as prospects."
> - Longenhagen and McDaniel, S2 (2018)

So the 2018 reliever ladder is: 40 = single-inning middle relief, 45 = dominant bullpen
piece, above 45 = elite and rare. The 2022 table (Part 3.6) extends this to 50 = no-doubt
closer and stops there.

The 2022 statement that reliever FV is deliberately NOT a WAR mapping:

> "Meanwhile, relievers (who have become more important) are punished by any WAR-based
> evaluation since they tend to throw fewer innings. We've made adjustments to the way we FV
> relievers to be a little more subjective than just mapping to WAR output. This is one of
> the benefits of filtering WAR for starters and relievers through FV rather than using WAR
> itself, as it allows us to make manual adjustments like this."
> - Eric Longenhagen, L7 (2022)

This is a hard warning for any lab that wants to invert reliever FV into WAR: FanGraphs
says the reliever mapping is deliberately broken relative to WAR.

L8 adds that FanGraphs now labels reliever type explicitly and lets FV describe quality
within that type:

> "I'm now designating pitchers as 'Starting Pitchers,' 'Multi-Inning Relievers,' and
> 'Single-Inning Relievers' rather than as just left- or right-handed pitchers to help
> illustrate projected roles, and then letting the FV show you how good I expect they'll be
> in that role."
> - Eric Longenhagen, L8 (2021)

And the 2025 outcomes study concedes it has no principled reliever handling at all:

> "There's one other limitation of measuring pitchers this way: I don't have a good method
> for dealing with the differential between reliever and starter valuation. Normalizing
> relievers to 200 innings pitched doesn't make a ton of sense, but handling them on their own
> also feels strange, and I don't have a good way of converting reliever WAR to the
> backup/regular/star scale that I'm using here. A 3-WAR reliever wouldn't be an above-average
> player, they'd be the best reliever in baseball."
> - Ben Clemens, L6 (2025)

## 5.4 Pitchers generally

A blanket pitcher penalty is published:

> "Because of injuries and general attrition, I tend to knock pitchers down one notch FV-wise
> from where their report would suggest, which scouts also do."
> - Kiley McDaniel, L10 (2015)

"One notch" means one 5-point step. The 2022 restatement gives the reason and the observed
consequence on list shape:

> "This is especially true for young pitchers, whose elbows play Russian Roulette once a week
> for about four or five years between when they're drafted and when they typically establish
> themselves in a big league role. [...] Because of injury and attrition, teams tend to need
> many more pitchers than appear on their Opening Day roster to get through a season, so we
> tend to have lots of pitchers occupying the bottom range of our prospect lists because the
> industry need for spot starters and up/down relief types is so significant. [...] On the flip
> side, the very top of our prospect lists, including our overall Top 100, tends to be dense
> with hitters. Alex Reyes, A.J. Puk, Forrest Whitley, Yadier Alvarez, MacKenzie Gore - we've
> put our hand on the stove too many times not to make an adjustment in this area."
> - Eric Longenhagen, L7 (2022)

The 2026 valuation confirms the practice has become extreme at the top:

> "We haven't given out a 70 FV to a pitcher since 2020 (MacKenzie Gore), and our grading has
> changed meaningfully since then, to the point where I'm confident that the same evaluation
> wouldn't produce a 70-FV grade today."
> - Ben Clemens, L1 (2026)

## 5.5 Proximity and ETA are inside FV

> "Do you treat upper-level minor leaguers and low-level teenagers the same way as far as FV
> is concerned? No. For many reasons, we value proximity to the big leagues and attempt to
> bake it in to FV. If there are two minor leaguers who are exactly the same in every way, and
> one is in Double-A and the other is in the GCL, it makes sense that the player closer to the
> big leagues would rank higher than the Rookie-level ball. There are some 50 FV players in
> our rankings who we think have a chance to be 60s or better in the big leagues, but the
> risk/proximity aspect of their profile needs to be captured in FV somewhere. The amount we
> deduct for things like risk due to injury or player demographics is subjective, and we don't
> have a guideline to share for deducting FV when someone has a surgery or gets busted for
> PEDs, but we're okay with that because so much of this process is already subjective."
> - Longenhagen and McDaniel, S2 (2018)

Longenhagen calls this out as the system's main cost:

> "My own issue with FV is that it can hamstring the evaluator's conviction about low-level
> prospects. Because risk and proximity to the majors have to factor into FV's abstract
> composition for the system of measure to work, players at the lowest levels of the minor
> leagues are penalized for being there. I might think a player in the GCL is going to be a
> Role 6 player (aka a 60, first-division regular, No. 3 starter, someone worth 3 WAR
> annually, etc.) but will only assign a 50 FV or so, because proximity to the majors factors
> into the FV grade and the prospect in question is likely a riskier one than a player with
> the same amount of potential who is playing at Triple-A and has experienced success there."
> - Eric Longenhagen, L9 (2017)

That quote also fixes the legacy "Role" nomenclature: Role 6 = 60 FV.

And a note that the six-year window can itself bite older prospects:

> "Keep in mind that, for some older prospects, the six-year window will encompass the start
> of their decline phase, which is part of why our rankings skew young."
> - Longenhagen and McDaniel, S2 (2018)

---

# Part 6. The WAR-translation lineage: three mappings compared

The three lineage articles (W1, W2, W3) all predate FV as a FanGraphs product. W2 has no
WAR mapping at all. W1 maps individual TOOLS to WAR. W3 maps whole-player PERFORMANCE
metrics to WAR. None of the three is an FV mapping in the modern sense, because none of them
carries risk, proximity, or bust probability. They are all descriptive translations of a
CURRENT major league population.

## 6.1 W1 (Cistulli 2013): per-tool WAR, single season, 550 PA baseline

Method and baseline, in his words:

> "Note, finally, that I've used 550 plate appearances as the baseline for an offensive
> player, for this reason: a batter with league-average rates in everything and 550 plate
> appearances produces a 2.0 WAR - i.e. the sort of WAR generally associated with a league
> average player."
> - Carson Cistulli, W1 (2013)

Baseline average player used throughout:

| PA | BB% | K% | HRC% | BABIP | BsR | Fld+Pos | HR | H | AVG | OBP | SLG | ISO | wOBA | Off | Def | Rep | WAR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 550 | 8.0% | 19.5% | 3.5% | .300 | 0.0 | 0.0 | 14 | 129 | .257 | .321 | .403 | .146 | .319 | 0 | 0 | 18 | 2.0 |

Quantity and units: the 2013 league-average hitter in a single season of 550 PA. HRC% is
home-run rate on contact. WAR is single-season WAR.

### W1 hit tool

Distribution assumptions stated:

> "The league-average batting average in 2013 was .257; a standard deviation, about 25 points.
> Using those figures as benchmarks, below is an estimate of the value for each grade along
> the scouting scale, assuming a league-average walk rate (ca. 8%), home-run rate on contact
> (ca. 3.5%), and also league-average baserunning and defense. Note that I've also attempted
> to distribute changes in strikeout rate (19.5% average, 6.0% standard deviation) and BABIP
> (.300 average, .025 standard deviation) evenly."
> - Carson Cistulli, W1 (2013)

| Grade | PA | K% | BABIP | AVG | OBP | SLG | ISO | wOBA | Off | WAR |
|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 550 | 31.5% | .250 | .182 | .253 | .313 | .131 | .246 | -31 | -1.4 |
| 30 | 550 | 27.5% | .268 | .207 | .276 | .343 | .136 | .271 | -20 | -0.2 |
| 40 | 550 | 23.5% | .285 | .232 | .298 | .373 | .141 | .296 | -10 | 0.9 |
| 50 | 550 | 19.5% | .300 | .257 | .321 | .403 | .146 | .319 | 0 | 2.0 |
| 60 | 550 | 16.0% | .316 | .282 | .344 | .432 | .150 | .341 | 10 | 3.0 |
| 70 | 550 | 12.5% | .330 | .307 | .367 | .461 | .154 | .362 | 19 | 4.0 |
| 80 | 550 | 9.5% | .345 | .332 | .389 | .490 | .158 | .381 | 27 | 4.9 |
| Avg per 10 pts | | | | | | | | | | 1.0 |

Quantity and units: WAR is FULL-PLAYER single-season WAR at 550 PA, varying the HIT tool
only and holding every other tool at league average. So the WAR column is "what a player
with this hit grade and average everything else is worth in one season". Value per 10 points
of hit grade: about 1.0 WAR.

### W1 power tool, version 1 (BABIP held constant)

> "As Mark Smith found in February, the league average home-run rate is approximately 2.5%
> (or 14 home runs per 550 PA). As Smith also found, a standard deviation is of such a size
> (about 1.5%) that it prevents any player from recording a home-run rate any lower than about
> 1.5 standard deviations below the league average (or, about a grade of 35 on power). To
> address that, I've halved the standard deviation for the three grades below 50, so that a 20
> and 30 power grade actually mean something."
> - Carson Cistulli, W1 (2013)

| Grade | PA | HRC% | HR | AVG | OBP | SLG | ISO | wOBA | Off | WAR |
|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 550 | 0.5% | 2 | .240 | .306 | .310 | .070 | .281 | -16 | 0.2 |
| 30 | 550 | 1.5% | 6 | .246 | .311 | .341 | .095 | .293 | -11 | 0.8 |
| 40 | 550 | 2.5% | 10 | .251 | .316 | .372 | .120 | .306 | -5 | 1.4 |
| 50 | 550 | 3.5% | 14 | .257 | .321 | .403 | .146 | .319 | 0 | 2.0 |
| 60 | 550 | 5.5% | 22 | .268 | .331 | .465 | .197 | .344 | 11 | 3.2 |
| 70 | 550 | 7.5% | 30 | .279 | .342 | .527 | .247 | .369 | 22 | 4.4 |
| 80 | 550 | 9.5% | 38 | .290 | .352 | .588 | .298 | .394 | 33 | 5.5 |
| Avg per 10 pts | | | | | | | | | | 0.9 |

Quantity and units: as above, varying only home-run rate on contact. Note the SD is HALVED
below 50 (so the sub-50 rows are not on the same SD scale as the above-50 rows). Cistulli
flags the side effect:

> "What one finds is that batting average increases a full 50 points between a player with 20
> power and one with 80 power without altering strikeout rate or BABIP, at all. This is a
> reality of the hit and power tools, if one defines them in a particular way: they interact."
> - Carson Cistulli, W1 (2013)

### W1 power tool, version 2 (BABIP falls as power rises)

| Grade | PA | HRC% | BABIP | HR | AVG | OBP | SLG | ISO | wOBA | Off | WAR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 550 | 0.5% | .321 | 2 | .257 | .321 | .326 | .070 | .295 | -10 | 0.9 |
| 30 | 550 | 1.5% | .314 | 6 | .257 | .321 | .352 | .095 | .303 | -6 | 1.3 |
| 40 | 550 | 2.5% | .307 | 10 | .257 | .321 | .377 | .120 | .311 | -3 | 1.6 |
| 50 | 550 | 3.5% | .300 | 14 | .257 | .321 | .403 | .146 | .319 | 0 | 2.0 |
| 60 | 550 | 5.5% | .285 | 22 | .257 | .321 | .453 | .197 | .334 | 7 | 2.7 |
| 70 | 550 | 7.5% | .269 | 30 | .257 | .321 | .504 | .247 | .348 | 13 | 3.4 |
| 80 | 550 | 9.5% | .253 | 38 | .257 | .321 | .555 | .298 | .362 | 19 | 4.0 |
| Avg per 10 pts | | | | | | | | | | | 0.5 |

Quantity and units: as above, but batting average is HELD CONSTANT at .257 by lowering
BABIP as power rises, which isolates power from the hit tool. Value per 10 points: 0.5 WAR.
Cistulli offers both and picks neither, so the published power translation is a RANGE:

> "Value of Every 10 Scouting Points (From 50): Either about 0.9 WAR or 0.5 WAR."
> - Carson Cistulli, W1 (2013)

### W1 run tool

> "League average by that metric is zero by definition; a standard deviation, about 3 runs."
> - Carson Cistulli, W1 (2013)

| Grade | PA | BsR | Off | WAR |
|---|---|---|---|---|
| 20 | 550 | -9.0 | -9 | 1.0 |
| 30 | 550 | -6.0 | -6 | 1.4 |
| 40 | 550 | -3.0 | -3 | 1.7 |
| 50 | 550 | 0.0 | 0 | 2.0 |
| 60 | 550 | 3.0 | 3 | 2.3 |
| 70 | 550 | 6.0 | 6 | 2.7 |
| 80 | 550 | 9.0 | 9 | 3.0 |
| Avg per 10 pts | | | | 0.3 |

Quantity and units: BsR in runs per 550 PA season; WAR is full-player single-season WAR.
Value per 10 points: 0.3 WAR. Cistulli warns this is baserunning only and NOT the run tool:

> "we'll use BsR as a proxy for speed. [...] Is there a perfect correlation between those
> figures and raw speed? Likely not. Baserunning production is likely a combination of raw
> speed and 'instincts' and, finally, opportunities."
> - Carson Cistulli, W1 (2013)

It also excludes speed's effects on defence and BABIP, which he states in the table lead-in
("as they relate to baserunning exclusively and not, for example, defensive range or BABIP").

### W1 fielding and arm, combined

> "By definition, the league average fielder records a defensive value (again, fielding plus
> positional adjustment) of zero. The standard deviation is about 10 runs per annum."
> - Carson Cistulli, W1 (2013)

| Grade | PA | Fld+Pos | Def | WAR |
|---|---|---|---|---|
| 20 | 550 | -30.0 | -30 | -1.2 |
| 30 | 550 | -20.0 | -20 | -0.1 |
| 40 | 550 | -10.0 | -10 | 0.9 |
| 50 | 550 | 0.0 | 0 | 2.0 |
| 60 | 550 | 10.0 | 10 | 3.1 |
| 70 | 550 | 20.0 | 20 | 4.2 |
| 80 | 550 | 30.0 | 30 | 5.2 |
| Avg per 10 pts | | | | 1.1 |

Quantity and units: Def (fielding runs PLUS positional adjustment) in runs per season; WAR
is full-player single-season WAR. Value per 10 points: 1.1 WAR. Fielding and arm are
deliberately NOT separated:

> "Just as with baserunning, there's a disconnect between the actual physical skills of
> fielding and the precise value, in runs or wins, which those skills are likely to produce.
> For that reason, I've made no attempt to separate the differences between the fielding and
> arm tools. Also for that reason, I must concede that what we're considering here are
> proxies for the tools, and not any sort of objective expression of the tools themselves."
> - Carson Cistulli, W1 (2013)

Because this column bundles the positional adjustment into the fielding grade, it double
counts position if combined with a position-relative FV. Flag for any implementation.

### W1 summary table

| Tool | WAR Every 10 Pts* |
|---|---|
| Hit | 1.0 |
| Power | 0.9 or 0.5 |
| Run | 0.3 |
| Fld/Arm | 1.1 |

> "*Above or below major-league average, that is, meaning the ceiling for a player with 550
> PAs is ca. 10-12 wins."
> - Carson Cistulli, W1 (2013)

Quantity and units: marginal single-season WAR per 10 points of a single tool, holding all
other tools at average. Summing across tools is what produces the 10 to 12 win ceiling. Note
that summing all four at their 80-grade values would DOUBLE COUNT, since the hit and power
tables both move batting average and the fielding table contains the positional adjustment.

W1's own framing, which should govern any use of it:

> "this is not intended to be a definitive work, but rather a rough attempt to provide some
> clarity on the actual significance, in terms of wins, of the various scouting grades for
> each tool."
> - Carson Cistulli, W1 (2013)

W1 offers exactly one whole-player example: "for Garin Cecchini, who, as a 70 hitter and
average everything-else, would likely produce about a 4.0 WAR."

## 6.2 W3 (Smith 2013): whole-player WAR, single season, by role

W3 is the only lineage article that produces a whole-player FV-to-WAR mapping.

### Hitters: wRC+ and WAR/600

| Grade | wRC+ | Player | WAR/600 | Player |
|---|---|---|---|---|
| 80 | 165 | Jose Bautista | 7.5 | Mike Trout |
| 70 | 141 | Giancarlo Stanton | 5.6 | Jacoby Ellsbury |
| 60 | 117 | Yadier Molina | 3.7 | Carlos Beltran |
| 50 | 94 | James Loney | 1.8 | Reed Johnson |
| 40 | 70 | Gerald Laird | -0.1 | Justin Smoak |
| 30 | 46 | Wil Nieves | -2.0 | Emmanuel Burriss |
| 20 | 22 | Ramiro Pena | -3.9 | Joe Mather |

Quantity and units: wRC+ (100 = league average) and WAR per 600 plate appearances, HITTERS,
2010-2012 three-year averages, 200 PA qualifier. Implied SD: 23.8 wRC+ points and 1.90
WAR/600. This is SINGLE-SEASON RATE WAR of a CURRENT major league population, not a
projection and not bust-inclusive.

Note the 50 row is 94 wRC+ and 1.8 WAR/600, both slightly BELOW league average, because the
population is all hitters with 200-plus PA rather than starters only. That is the key
calibration difference against the 2018 primer, which computed bands twice (all 200-PA
hitters, and starters only) and published the rounded consensus.

Smith's own role reading of the WAR column:

> "The rest of the breakdown is as expected - 0-2 wins is generally a bench player, 2-4 is a
> regular, 4-6 is an All-Star-caliber player, and a 6+ win player is an MVP candidate, with
> the 7-and-above players as your real contenders."
> - Mark Smith, W3 (2013)

### Hitters: OBP and wOBA

| Grade | OBP | Player | wOBA | Player |
|---|---|---|---|---|
| 80 | .413 | Prince Fielder | .421 | Joey Votto |
| 70 | .384 | Ryan Braun | .385 | Buster Posey |
| 60 | .355 | Norichika Aoki | .349 | Matt Joyce |
| 50 | .327 | Kendrys Morales | .312 | Tyler Flowers |
| 40 | .298 | Tyler Colvin | .276 | Everth Cabrera |
| 30 | .269 | Cesar Izturis | .240 | Jack Wilson |
| 20 | .240 | Drew Butera | .204 | Ramiro Pena |

Quantity and units: three-year OBP and wOBA, HITTERS. Implied SD: .0288 OBP, .0362 wOBA.

### Pitchers: WAR by role

| WAR | SP/200 | Player | RP/60 | Player |
|---|---|---|---|---|
| 80 | 6.8 | n/a | 2.33 | Craig Kimbrel |
| 70 | 5.4 | Josh Johnson | 1.64 | David Robertson |
| 60 | 3.9 | Madison Bumgarner | 0.94 | Wade Davis |
| 50 | 2.4 | Joe Blanton | 0.25 | Jon Rauch |
| 40 | 1.0 | Bronson Arroyo | -0.45 | Kyle McClellan |
| 30 | -0.5 | Jeff Suppan | -1.14 | Chuckie Fick |
| 20 | -2.0 | Ryan Rowland-Smith | -1.83 | Brian Tallet |

Quantity and units: WAR per 200 innings pitched (starters) and WAR per 60 innings pitched
(relievers). Single-season rate, 2010-2012. Implied SD: 1.47 WAR/200 for starters and 0.693
WAR/60 for relievers. The leftmost header is labelled "WAR" in the source but is the GRADE
column; that is a source labelling error, kept as-is.

This is the ONLY published table in the whole corpus that puts relievers on all seven grade
rows including 70 and 80. It does so by rating relievers against OTHER RELIEVERS, at 60 IP.
It is therefore NOT commensurable with the 2014 or 2022 FV reliever ladders, which rate
relievers against the whole player population.

### Pitchers: FIP by league and role

| FIP | AL SP | Player | NL SP | Player |
|---|---|---|---|---|
| 80 | 2.32 | n/a | 2.24 | n/a |
| 70 | 2.93 | Justin Verlander | 2.80 | Clayton Kershaw |
| 60 | 3.54 | Dan Haren | 3.36 | Mat Latos |
| 50 | 4.15 | Kevin Slowey | 3.91 | Tim Stauffer |
| 40 | 4.77 | Jeanmar Gomez | 4.47 | Randy Wolf |
| 30 | 5.38 | Javier Vazquez | 5.03 | Ross Ohlendorf |
| 20 | 5.99 | Ryan Rowland-Smith | 5.58 | n/a |

| FIP | AL RP | Player | NL RP | Player |
|---|---|---|---|---|
| 80 | 1.48 | n/a | 1.34 | Craig Kimbrel |
| 70 | 2.30 | Junichi Tazawa | 2.15 | Aroldis Chapman |
| 60 | 3.13 | Esmil Rogers | 2.95 | Jason Motte |
| 50 | 3.96 | Tim Collins | 3.76 | Wesley Wright |
| 40 | 4.79 | Aaron Laffey | 4.57 | Josh Roenicke |
| 30 | 5.62 | Manny Delcarmen | 5.37 | Livan Hernandez |
| 20 | 6.45 | Brian Tallet | 6.18 | n/a |

Quantity and units: FIP (runs per nine innings), split by league AND role. Lower is better,
so the sign runs backwards relative to the WAR tables. Implied SD: about 0.61 (AL SP), 0.56
(NL SP), 0.83 (AL RP), 0.81 (NL RP). The league split exists because:

> "I split the pitching groups a bit further into AL and NL because the run environments are
> a bit different for each league."
> - Mark Smith, W3 (2013)

This is a run-environment adjustment, and it is the only one published anywhere in the
corpus. It is now obsolete as stated (the DH is universal), but the PRINCIPLE that the
grade-to-FIP map must be re-centred on the run environment is live and is not honoured by
the 2018 or 2022 primer FIP anchors.

## 6.3 Side-by-side: FV to WAR under every published method

Every column is a DIFFERENT quantity. Read the units row before using any of them.

| Grade | W3 hitter WAR/600 | W3 SP WAR/200 | W3 RP WAR/60 | W1 hit-tool-only WAR | McD 2014 combined WAR | Primer hitter band | Primer SP band | Clemens 2026 hitter | Clemens 2026 pitcher |
|---|---|---|---|---|---|---|---|---|---|
| 20 | -3.9 | -2.0 | -1.83 | -1.4 | (not published) | (not published) | (not published) | (not published) | (not published) |
| 25 | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) |
| 30 | -2.0 | -0.5 | -1.14 | -0.2 | -1.0 | <-0.1 | <-0.1 | (not published) | (not published) |
| 35 | (not published) | (not published) | (not published) | (not published) | 0.0 | (not published) | <-0.1 (as 35/35+) | (not published) | (not published) |
| 35+ | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | <-0.1 | 0.3 | 0.25 |
| 40 | -0.1 | 1.0 | -0.45 | 0.9 | 1.0 | 0.0 to 0.7 | 0.0 to 0.9 | 0.75 | 0.55 |
| 40+ | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | 1.2 | 1.0 |
| 45 | (not published) | (not published) | (not published) | (not published) | 1.5 | 0.8 to 1.5 | 1.0 to 1.7 | 2.5 | 1.6 |
| 45+ | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | (not published) | 3.2 | 2.6 |
| 50 | 1.8 | 2.4 | 0.25 | 2.0 | 2.0 | 1.6 to 2.4 | 1.8 to 2.5 | 7 | 5 |
| 55 | (not published) | (not published) | (not published) | (not published) | 2.5 | 2.5 to 3.3 | 2.6 to 3.4 | 8 | 7 |
| 60 | 3.7 | 3.9 | 0.94 | 3.0 | 3.0 | 3.4 to 4.9 | 3.5 to 4.9 | 12.5 | 11 |
| 65 | (not published) | (not published) | (not published) | (not published) | 4.0 | (not published) | (not published) | 13.5 | 13.5 |
| 70 | 5.6 | 5.4 | 1.64 | 4.0 | 5.0 | 5.0 to 7.0 | 5.0 to 7.0 | 27.5 | 27 |
| 75 | (not published) | (not published) | (not published) | (not published) | 6.0 | (not published) | (not published) | (not published) | (not published) |
| 80 | 7.5 | 6.8 | 2.33 | 4.9 | 7.0 | > 7.0 | >7.0 | (not published) | (not published) |

Units and framing, per column:

1. W3 hitter WAR/600: single-season WAR per 600 PA. Descriptive of the 2010-2012 major
   league population (200-PA qualifier). NOT bust-inclusive, NOT a projection.
2. W3 SP WAR/200: single-season WAR per 200 IP, starters only. Same framing.
3. W3 RP WAR/60: single-season WAR per 60 IP, relievers rated AGAINST OTHER RELIEVERS.
   Same framing. Not commensurable with the other columns.
4. W1 hit-tool-only WAR: single-season full-player WAR at 550 PA, varying ONLY the hit
   tool, everything else average. Not an overall-FV mapping at all.
5. McD 2014 combined WAR: WAR per season, framed as TRUE TALENT. In S3 (2014) it is
   unqualified true talent; in L10 (2015) the same numbers are described as the player's
   most likely PEAK season. Not bust-inclusive.
6. Primer hitter band: AVERAGE ANNUAL WAR over the first six years of service. Talent plus
   durability plus consistency. Explicitly NOT peak. Not bust-inclusive.
7. Primer SP band: same, starting pitchers.
8. Clemens 2026 hitter: TOTAL UNDISCOUNTED WAR over the entire team control span, averaged
   over ALL historical prospects who carried that grade INCLUDING those who never reached
   the majors. BUST-INCLUSIVE. This is a completely different quantity from columns 1-7.
9. Clemens 2026 pitcher: same, pitchers.

Rough commensurability note (this is OUR arithmetic, not FanGraphs'): to compare column 8
against column 6, divide column 8 by about 6 years. A 50 FV hitter is 7.0 total, or about
1.17 WAR per year bust-inclusive, against a primer talent band of 1.6 to 2.4 (midpoint 2.0).
The ratio, about 58%, is the bust-and-attrition discount at 50 FV. The same arithmetic gives
roughly 36% at 40 and 45 FV, about 46% at 55, about 50% at 60, and about 76% at 70. Do not
attribute these ratios to FanGraphs; they are derived and they inherit the primer's band
midpoint choice and a flat 6-year assumption that S1 says is often exceeded.

## 6.4 Where the lineage articles disagree

### D1. Whether 10 points is one SD of WAR

W3 makes 10 points exactly one SD of observed WAR: for hitters the steps from 20 up are
uniformly 1.9 WAR/600. McDaniel's 2014 table does NOT: its steps per 5 points run 1.0, 1.0,
0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0 going up from 30. It is COMPRESSED between 40 and 60
and expanded outside that range. Consequence: at 40 FV the two disagree by 1.1 WAR
(W3 -0.1 vs McDaniel 1.0), and at 60 by 0.7 WAR (W3 3.7 vs McDaniel 3.0). McDaniel's table
is role-anchored, not SD-anchored, despite the article that houses it defining the scale in
SD terms. This is an internal inconsistency in S3 itself.

### D2. Where 50 sits

W3 puts 50 slightly BELOW league average (94 wRC+, 1.8 WAR/600) because his population is
everyone with 200-plus PA. W1 puts 50 exactly AT league average by construction (2.0 WAR at
550 PA with average rates). McDaniel 2014 puts 50 at 2.0 and calls it "Avg Regular". The
2018 primer band for 50 is 1.6 to 2.4, which straddles both. The population definition is
the whole disagreement: "all players who got 200 PA" versus "starters" versus "the league
mean rate".

### D3. Relievers

W3 grades relievers on a reliever-only scale and cheerfully awards an 80 (Kimbrel). S3
(2014) refuses to let relievers past 60 and argues explicitly against calling Rivera an 80.
S2 (2018) puts dominant bullpen pieces at 45 and calls anything above that elite. L7 (2022)
caps the reliever role table at 50. So the published reliever ceiling has moved 80 (W3,
reliever-relative) to 60 (2014) to roughly 45-50 (2018-2022), while the underlying claim
about reliever WAR ("most elite relievers max out at around 3 wins") has not changed at all.
The movement is a change in the SCALE CONVENTION, not in the estimate of reliever value.

### D4. Peak versus average

L10 (2015) says the 2014 WAR column is the player's most likely PEAK season. S2 (2018) and
L7 (2022) say FV is the AVERAGE ANNUAL over six years and explicitly disown peak. S2 names
two players to make the point:

> "Sonny Gray peaked at 3.8 WAR in 2015 (a strong 60) but averaged 2.2 annual WAR (50) over
> his first six years, and we think the latter is a better representation of his profile
> because it accounts not only for talent but also the ability to stay healthy and perform
> consistently. Matt Duffy posted a 4.4 WAR campaign in 2015 but has averaged just shy of two
> wins per season, and again we think that's more representative of his true talent."
> - Longenhagen and McDaniel, S2 (2018)

L7 makes the same argument with Baez and Gomez:

> "Baez's peak year (5.4 WAR in 2018) is a 70 on the scale, but he hasn't been that type of
> player every year, with many seasons in the 2.5-3.0 WAR range. It would be incorrect to call
> Baez or someone like Carlos Gomez a '70' since there are players who produce 5-ish WAR every
> year, while Baez and Gomez merely peaked there for a little while."
> - Eric Longenhagen, L7 (2022)

For the same player, the peak reading and the average reading differ by one to two full
grades. This is the largest single disagreement in the corpus and it is a disagreement
between FanGraphs and its own earlier self, not between authors of different sites.

### D5. Whether the mapping is descriptive or predictive

W1, W2 and W3 are all DESCRIPTIVE: they take a current major league population and ask what
statistic corresponds to each grade. FV is PREDICTIVE and carries risk, proximity and
subjective bust discounts inside the grade. S1/L1 (2026) is neither: it is an EMPIRICAL
BUST-INCLUSIVE EXPECTATION measured over resolved historical cohorts. A lab testing these
against resolved cohorts must not score the descriptive mappings on bust-inclusive targets,
or the descriptive mappings will look catastrophically over-optimistic purely by
construction.

### D6. Linearity of the cost of a win

L5 (Swartz 2017) concludes "the cost per WAR remaining linear across all average annual
values". L4 (Clemens 2026) concludes the opposite and quantifies it: about $7M/win for 0-1
WAR players, $8.5M for 1-2, and $13M for 2-plus. Both are FanGraphs house positions nine
years apart. The 2026 valuation uses the non-linear version, and says the flat alternative
lowers the total value of the minors from $12B to $10.5B.

### D7. Position and defence handling

W1 folds the positional adjustment INTO the fielding grade (its Def column is Fld+Pos). W2
pools all positions into one defensive z-score and admits it should not have. Modern FV puts
position inside the grade by defining 50 as "average everyday big leaguer at their given
position". These three are mutually incompatible, and any combination of a W1 fielding grade
with a modern position-relative FV double counts position.

---

# Part 7. The valuation methodology

## 7.1 THE CENTRAL DISTINCTION: projected peak role versus bust-inclusive expected value

These are two different numbers and FanGraphs publishes both, in different articles, without
ever putting them side by side.

**Quantity A, the talent / role projection.** This is what the FV GRADE means. It is the
average annual WAR FanGraphs expects the player to produce over his first six years of
service IF he becomes the player they project. Risk, injury and proximity are already netted
out of the GRADE (a risky GCL teenager gets a lower grade than an identical Triple-A player),
but the WAR number attached to the grade is a talent statement about a realised big leaguer.
The 2018 and 2022 primer tables (Parts 3.2, 3.3, 3.4) publish Quantity A. McDaniel's 2014
table (Part 3.1) publishes Quantity A too, read as true talent; L10 (2015) reads the same
numbers as peak-season talent, which is a THIRD variant, Quantity A-prime.

**Quantity B, the bust-inclusive empirical expectation.** This is what the VALUATION tables
mean. It is the arithmetic mean, over all historical prospects who carried that grade, of
total team-control WAR (or surplus dollars), with zeros left in for every prospect who never
reached the majors. The 2026 tables (Part 7.2) and Edwards' 2019 tables (Part 7.5) publish
Quantity B.

The definitive statement that Quantity A is not peak:

> "Please note we are not projecting peak seasons here but rather the average annual WAR over
> the player's first six years of big league employment."
> - Longenhagen and McDaniel, S2 (2018)

The definitive statement that Quantity B leaves the zeros in:

> "We didn't discard anyone; if a prospect never reached the majors, their ledger shows no
> surplus value and no WAR."
> - Ben Clemens, S1 (2026)

> "We didn't ignore any prospect rankings in doing so, and didn't remove nulls - if a 50-FV
> player didn't make the majors, for example, we left in a row of zero WAR and zero surplus
> value."
> - Ben Clemens, L1 (2026)

And the statement that Quantity B is a mean over a distribution, not a prediction about an
individual:

> "That number is an average of all the hits, semi-hits, semi-misses, and outright busts that
> carried a similar evaluation in each prospect tier in the past."
> - Ben Clemens, L1 (2026)

The 2025 outcomes study says the same thing about the grade itself:

> "Being a 60 FV prospect doesn't make you 17% likely to turn into a star; rather, our team
> is trying to identify players with s [sic] relatively good chance of stardom by throwing a
> big FV on them."
> - Ben Clemens, L6 (2025)

**Numerical proof that A and B are different quantities.** A 50 FV hitter is 1.6 to 2.4 WAR
per year under Quantity A. Over six years that is 9.6 to 14.4 WAR. Quantity B for the same
grade is 7.0 total WAR. The gap is the bust rate: L6 reports 23% of 50 FV hitters washed out
entirely. Any model that feeds a Quantity A band into a Quantity B slot will overprice
prospects by roughly a factor of two at 50 FV and by roughly a factor of three at 40 to 45
FV.

## 7.2 The 2026 headline table (L1)

| FV | Type | Expected Surplus Value | Expected WAR | Star Odds |
|---|---|---|---|---|
| 70 | Hitter | $195,000,000 | 27.5 | 87.5% |
| 70 | Pitcher | $195,000,000 | 27 | 87.5% |
| 65 | Hitter | $95,000,000 | 13.5 | 40.0% |
| 65 | Pitcher | $95,000,000 | 13.5 | 40.0% |
| 60 | Hitter | $82,000,000 | 12.5 | 33.0% |
| 60 | Pitcher | $70,000,000 | 11 | 21.0% |
| 55 | Hitter | $55,000,000 | 8 | 17.5% |
| 55 | Pitcher | $45,000,000 | 7 | 7.0% |
| 50 | Hitter | $45,000,000 | 7 | 13.5% |
| 50 | Pitcher | $33,500,000 | 5 | 7.0% |
| 45+ | Hitter | $18,500,000 | 3.2 | 6.0% |
| 45+ | Pitcher | $15,000,000 | 2.6 | 3.0% |
| 45 | Hitter | $14,500,000 | 2.5 | 3.5% |
| 45 | Pitcher | $9,500,000 | 1.6 | 1.5% |
| 40+ | Hitter | $8,000,000 | 1.2 | 1.8% |
| 40+ | Pitcher | $7,000,000 | 1 | 1.0% |
| 40 | Hitter | $5,500,000 | 0.75 | 0.8% |
| 40 | Pitcher | $4,000,000 | 0.55 | 0.4% |
| 35+ | Hitter | $2,000,000 | 0.3 | 0.4% |
| 35+ | Pitcher | $1,500,000 | 0.25 | 0.4% |

Quantity and units, column by column:

- Expected Surplus Value: 2026 US dollars, DISCOUNTED to present value at a net 7% rate,
  per prospect, BUST-INCLUSIVE mean over the historical cohort. Free-agency-equivalent value
  of team-control production minus estimated team-control salary cost.
- Expected WAR: TOTAL, UNDISCOUNTED WAR accumulated over the entire team control span (not
  per year, not peak, not six-year-average). BUST-INCLUSIVE mean, zeros retained.
- Star Odds: probability, defined precisely as below.

> "First, we calculated the un-discounted WAR that each tier of prospect projects to
> accumulate during their team control years."
> - Ben Clemens, L1 (2026)

> "we also calculated the odds that a prospect will turn out to be a star. For this study,
> we've defined a star as a player who posts two or more seasons of 4 or more WAR during their
> team control years."
> - Ben Clemens, L1 (2026)

Note the two anomalies in the table, both of which FanGraphs explains: 70 FV hitters and
pitchers get the SAME value, and 65 FV hitters and pitchers get the same value, breaking the
otherwise universal hitter-over-pitcher pattern.

> "That's something that arises from how rarely we hand out 65- and 70-FV grades to pitchers
> these days. [...] Pitching prospects this elite are less common than hitting prospects of the
> same caliber, but the few who do exist perform just as well on a per-player basis."
> - Ben Clemens, L1 (2026)

> "By the time we get to more 'normal' top prospects, the standard split, with hitting
> prospects being more valuable than pitching prospects with the same grade, is still borne
> out by the data. That pattern continues even outside the prospects who populate the Top 100;
> for every Future Value below 65, pitchers deliver less WAR on average and are less likely to
> turn into stars than hitters with the same grade."
> - Ben Clemens, L1 (2026)

There is no 75 or 80 row. FanGraphs has never handed out an 80 FV to a prospect in this
dataset, and Ohtani's 70 was a two-way grade.

## 7.3 The 2026 comparison against Edwards, with counts (L1)

| FV | Type | Edwards (2019 $) | Edwards (With Inflation) | New Method | Number of Prospects | Total Value (Edwards) | Total Value (Edwards, w/Infl) | Total Value (New) |
|---|---|---|---|---|---|---|---|---|
| 70 | Hitter | $112M | $146.2M | $195M | 1 | $112M | $146M | $195M |
| 70 | Pitcher | $85M | $111M | $195M | 0 | $0 | $0 | $0 |
| 65 | Hitter | $62M | $81M | $95M | 2 | $124M | $162M | $190M |
| 65 | Pitcher | $64M | $84M | $95M | 1 | $64M | $83M | $95M |
| 60 | Hitter | $55M | $72M | $82M | 4 | $220M | $287M | $328M |
| 60 | Pitcher | $60M | $78M | $70M | 4 | $240M | $313M | $280M |
| 55 | Hitter | $46M | $60M | $55M | 13 | $598M | $780M | $715M |
| 55 | Pitcher | $34M | $44M | $45M | 7 | $238M | $311M | $315M |
| 50 | Hitter | $28M | $36.5M | $45M | 52 | $1,450M | $1,900M | $2,340M |
| 50 | Pitcher | $21M | $27.5M | $33.5M | 39 | $819M | $1,070M | $1,306M |
| 45+ | Hitter | $8M | $10.5M | $18.5M | 33 | $264M | $345M | $610M |
| 45+ | Pitcher | $6M | $7.8M | $15M | 20 | $120M | $157M | $300M |
| 45 | Hitter | $6M | $7.8M | $14.5M | 59 | $354M | $462M | $855M |
| 45 | Pitcher | $4M | $5.2M | $9.5M | 62 | $248M | $324M | $589M |
| 40+ | Hitter | $4M | $5.2M | $8M | 102 | $408M | $533M | $816M |
| 40+ | Pitcher | $3M | $4M | $7M | 94 | $282M | $368M | $658M |
| 40 | Hitter | $2M | $2.5M | $5.5M | 168 | $336M | $439M | $924M |
| 40 | Pitcher | $1M | $1.5M | $4M | 208 | $208M | $272M | $832M |
| 35+ | Hitter | $.5M | $.65M | $2M | 182 | $91M | $119M | $364M |
| 35+ | Pitcher | $.5M | $.65M | $1.5M | 239 | $119.5M | $156M | $358M |
| Total | n/a | n/a | n/a | n/a | n/a | $6,305M | $8,227M | $12,072M |

Quantity and units: per-prospect surplus value in millions of dollars under three methods,
then the live 2026 population count per tier, then the tier aggregates. The "Number of
Prospects" column is a snapshot of the actual FanGraphs board and is directly usable as a
grade-distribution prior: 1 70-FV hitter, 0 70-FV pitchers, and 421 prospects at 35+.

## 7.4 The 2026 method, assumption by assumption (S1 and L1)

**Prospect cohort.** Baseball America Top 100 for 2005-2016, FanGraphs lists for 2017-2018.
Ordinal ranks converted to FV grades separately for hitters and pitchers, then adjusted
between years by a regressed factor based on that class' major league production, then forced
to match the modern FV distribution.

> "With those adjusted ordinal rankings in hand, we assigned grades to each prospect with the
> constraint that the overall population of prospects matched the distribution of grades that
> we hand out today. In other words, we enforced the prospect team's modern preferences on our
> old rankings, such that a 70 FV 'means' the same thing in every year."
> - Ben Clemens, S1 (2026)

FanGraphs flags the resulting leakage itself:

> "This method introduces some potential bias. Judging prospects based on how they turned out
> inherently brings some information from the future into the mix."
> - Ben Clemens, S1 (2026)

**Team control definition.**

> "We defined team control years based solely on days on the major league roster, ignoring
> actual non-tender and contract extension decisions. This results in some players having team
> control spans of more than seven years thanks to partial seasons, but no player had a span
> shorter than six seasons; if they retired before reaching free agency, zeroes were recorded
> for all the remaining years."
> - Ben Clemens, S1 (2026)

So the control span is 6 to 7-plus years, NOT a flat 6. That matters for anyone dividing the
total-WAR column by a fixed year count.

**Cost of a win.** Graduated, from L4, using the 2024-2026 average:

> "That works out to roughly $7 million per win for 0-1 WAR players, $8.5 million per win for
> 1-2 WAR players, and $13 million per win for players who rack up more than 2 WAR. Teams will
> pay up for stars, and as a result, prospects more likely to turn into stars command extra
> surplus value."
> - Ben Clemens, L1 (2026)

L4's underlying seven-year table:

| Year | Overall $/WAR | 0-1 $/WAR | 1-2 $/WAR | 2+ $/WAR |
|---|---|---|---|---|
| 2020 | 10.85M | 10.93M | 8.52M | 11.99M |
| 2021 | 6.70M | 4.09M | 6.31M | 7.22M |
| 2022 | 11.24M | 9.46M | 8.77M | 12.15M |
| 2023 | 10.34M | 6.87M | 9.77M | 10.81M |
| 2024 | 12.08M | 8.22M | 8.83M | 14.13M |
| 2025 | 11.92M | 5.96M | 8.95M | 13.91M |
| 2026 | 11.23M | 6.74M | 8.51M | 12.84M |
| Average | 10.62M | 7.37M | 8.60M | 11.76M |

Quantity and units: millions of dollars of guaranteed contract value per projected WAR in
the first year of the deal, inflation-adjusted to 2025 dollars, aging-adjusted at 0.4 WAR
per year of decline, 5% annual salary inflation on future guarantees, league minimum salary
subtracted. Free agent STARTING PITCHERS and POSITION PLAYERS only. Relievers are excluded:

> "I took every starting pitcher and position player (relievers are weird and should be
> modeled differently due to leverage concerns)"
> - Ben Clemens, L4 (2026)

Confidence intervals per tier: $6.3M to $8.6M for 0-1 WAR, $7.8M to $9.4M for 1-2 WAR,
$10.6M to $12.9M for 2-plus WAR.

**Salary cost model.**

> "For pre-arbitration years, we assigned the league minimum salary. For arbitration years,
> we assigned salaries based on a percentage of the previous season's WAR value in free
> agency: 15% for Arb 1, 35% for Arb 2, 50% for Arb 3, and 75% for Arb 4. We tested multiple
> arbitration structures, and while none were perfect, this formulation produced the lowest
> mean squared error when compared to actual arbitration payouts under the new CBA."
> - Ben Clemens, S1 (2026)

**Discount rate.**

> "We applied a net 7% discount rate - a 10% discount rate, in line with past research, minus
> an estimated 3% annual increase in the cost of a win in free agency."
> - Ben Clemens, S1 (2026)

The 10% traces to L5, which tested 5%, 10% and 15% against free agent contracts with and
without draft pick compensation attached and settled on 10%:

> "I decided to continue using a 10% discount rate (meaning that teams currently value the
> ability to obtain future WAR 10% less each year into the future). This is still my best
> guess about how teams are valuing draft picks."
> - Matt Swartz, L5 (2017)

Swartz also notes 10% is not necessarily irrational impatience, because franchise values
compound and winning sooner monetises sooner.

**Sub-50 grades use a top-down allocation, not per-prospect measurement.**

> "Given the challenges of collecting and aggregating historical prospect grades, particularly
> outside the Top 100, we couldn't do a per-prospect look at the entire minors. For
> lower-graded prospects, we used a top-down method. We estimated the total pool of value
> produced by prospects outside the Top 100, then divided that pool among the grades. The
> logic here is that a total is far more stable than any of its constituent parts [...] We can't
> say with great confidence what a single 40-FV pitcher is worth, but we can say with
> confidence what the entire outside-the-Top-100 group has been worth."
> - Ben Clemens, S1 (2026)

**Residence time.** Sub-50 prospect value is scaled from a per-debut-class figure to a
whole-minors figure using average time spent in the minors:

> "We approximated average residence time as between 1.9 and 2.5 years, with our best guess
> at two years even. We anchored near the low end of the range thanks to the effects of minor
> league contraction"
> - Ben Clemens, S1 (2026)

**The upgrade-option term, which dominates sub-50 value.** This is the most important
mechanical detail in the whole valuation and it is easy to miss.

> "In addition to debuting in the majors and then accruing value, lower-graded prospects can
> also improve while in the minors and receive a 50 FV or higher grade in a future season. For
> much of the player population, the odds of developing into a top prospect while still in the
> minors outstrip the likelihood of graduating to the majors and contributing immediately."
> - Ben Clemens, S1 (2026)

> "Each prospect was valued as the odds of an upgrade multiplied by our estimate of the value
> of that upgrade (taken from the 50 FV and above valuation method above), plus the odds of not
> being upgraded (one minus upgrade odds) multiplied by the expected value of that prospect
> contingent on not being upgraded"
> - Ben Clemens, S1 (2026)

The worked example, with the punchline:

> "We value a 45-FV position player at roughly $16 million in surplus value. That's about a
> one-in-five chance of an upgrade - in which case he's worth roughly what a 50 FV is - plus
> the four-in-five chance he isn't, where his expected contribution is closer to $7 million.
> The biggest driver of a lower-graded prospect's value isn't their likeliest outcome - it's
> the chance that they develop into a meaningfully better prospect."
> - Ben Clemens, S1 (2026)

Note the $16M in this example does not match the $14.5M for a 45 FV hitter in the published
table. See Open Questions.

Upgrade odds were estimated on 2019-2023 data "(to exclude right-bounded issues)".

**Confidence.**

> "We're most confident in the total, not the exact breakdown between tiers, but we believe
> they're sensible."
> - Ben Clemens, S1 (2026)

**Sensitivity analysis.** Baseline total minor league surplus value is roughly $12 billion
(L1 gives the range as $10.5B to $13.75B; S1's sensitivity text gives $10.5B to $12.7B).

| Assumption varied | Effect on total minor league surplus value |
|---|---|
| Cost of a win +10% | $12.7B (from $12B baseline) |
| Cost of a win -10% | $11.3B |
| Flatten cost of a win linearly | $10.5B, decrease concentrated in Top 100 |
| Discount rate +/- 3% | +/- $700M |
| Arbitration percentages +/- ~30% | +/- $400M |
| Minor league residence time +/- 0.5 years | +/- $600M |
| Contingent (upgrade) value assumptions | up to $500M, split between 40 and 45 FV |
| Which historical years used as inputs | +/- $200M |
| Other minor changes combined | under $200M |

Quantity and units: billions or millions of 2026 dollars, total present-value surplus across
all graded affiliated minor leaguers.

Per-grade ranges under reasonable alternative calibrations:

| Grade and type | Published value | Range under alternative calibrations |
|---|---|---|
| 70 (either) | $195M | $150M to $200M |
| 65 Hitter | $95M | $75M to $105M |
| 60 Pitcher | $70M | $60M to $78M |
| 50 (either) | $45M / $33.5M | "largely unaffected by calibration" |
| 40 (either) | $5.5M / $4M | $3M to $7M total surplus per prospect |

Aggregate split above and below 50 FV:

> "Across the entire population of ranked minor leaguers, we project prospects with a grade of
> 50 FV or higher to accumulate $5.7 billion in surplus value during their team control years,
> while prospects graded below a 50 FV project to accrue an aggregate $6.3 billion in their
> team control years."
> - Ben Clemens, L1 (2026)

## 7.5 Edwards 2019: the bust-rate table (L2)

This is the ONLY published FanGraphs table that gives an explicit bust rate and star rate
per FV tier alongside a mean and a dispersion.

| Prospect Type | 2018 $ Value* | Players | AVG WAR** | MEDIAN WAR | Standard Deviation | Bust Rate (<1 Present Day WAR) | Star Rate (>10 Present Day WAR) |
|---|---|---|---|---|---|---|---|
| 70 POS | $112 M | 21 | 12.5 | 11.3 | 7.6 | 4.8% | 57.1% |
| 70 P | $85 M | 9 | 9.5 | 7.8 | 7.2 | 0.0% | 44.4% |
| 65 POS | $62 M | 47 | 6.9 | 5.5 | 6.4 | 18.8% | 29.8% |
| 65 P | $64 M | 28 | 7.1 | 6.7 | 6.1 | 14.3% | 17.9% |
| 60 POS | $55 M | 154 | 6.1 | 3.9 | 6.6 | 31.8% | 27.3% |
| 60 P | $60 M | 86 | 6.7 | 6.6 | 5.6 | 22.1% | 25.6% |
| 55 POS | $46 M | 178 | 5.1 | 2.9 | 6.5 | 36.5% | 21.9% |
| 55 P | $34 M | 122 | 3.7 | 2.2 | 4.6 | 39.3% | 9.8% |
| 50 POS | $28 M | 433 | 3.1 | 0.8 | 4.7 | 51.5% | 9.9% |
| 50 P | $21 M | 422 | 2.3 | 0.4 | 3.7 | 58.1% | 5.7% |

Quantity and units. This is the fiddliest set of units in the corpus, so precisely:

- AVG WAR and MEDIAN WAR: "PRESENT DAY WAR", meaning WAR produced over the first NINE
  seasons of a career (including the season in which the prospect was ranked), first
  redistributed across the final seven of those nine seasons on a synthetic development
  curve, then reduced by an arbitration discount, then discounted for present value at 8%
  per year. It is NOT raw career WAR and NOT annual WAR. BUST-INCLUSIVE.
- Standard Deviation: SD of that same present-day WAR quantity, across prospects in the tier.
- Bust Rate: share of prospects in the tier producing under 1.0 present-day WAR.
- Star Rate: share producing over 10.0 present-day WAR.
- 2018 $ Value: millions of dollars at $9M per win.
- Players: cohort count from Baseball America Top 100 lists, 1996-2010, all rankings kept
  including repeat appearances of the same player in multiple years.

The nine-year window and the redistribution, in Edwards' words:

> "To determine surplus value for players, I used WAR produced over the first nine seasons of
> a career, including the season in which a prospect was ranked. Why nine years? In today's
> game, most players don't hit free agency until after their seventh major-league season. By
> examining nine seasons, it's possible to account for prospects who were still a couple years
> away from the majors when they appeared on a top-100 list"
> - Craig Edwards, L2 (2019)

> "I've spread out a player's WAR over the final seven seasons of the period in question,
> distributing 10% of it to years three and four before slightly gradually increasing that
> figure up to 20% by year nine. To calculate surplus value, I've discounted WAR by 3% in years
> No. 3 through 5 (to approximate the impact of the league-minimum salary) and then 15% in year
> six, 32% in year seven, 48% in year eight, and 72% in year nine."
> - Craig Edwards, L2 (2019)

> "After that, I applied an 8% discount rate for present value."
> - Craig Edwards, L2 (2019)

And the caution about what the dollar figure is:

> "Keep in mind that the dollar figure isn't a direct value, but rather equivalent value of a
> prospect relative to the free-agent market. [...] These values likely roughly approximate what
> an individual player might get as a signing bonus if he were declared a free agent and teams
> could only provide a signing bonus instead of a long-term contract."
> - Craig Edwards, L2 (2019)

Note the MEDIAN is far below the MEAN at every tier, and dramatically so at 50 FV (POS mean
3.1, median 0.8; P mean 2.3, median 0.4). The distribution is heavily right-skewed. A model
calibrated on the mean will mis-serve any question about the typical prospect.

Edwards' grade-population prior, negotiated with Longenhagen and McDaniel:

| Numerical Value | Players |
|---|---|
| 70 | 2 |
| 65 | 5 |
| 60 | 16 |
| 55 | 20 |
| 50 | 57 |

Quantity and units: the number of prospects FanGraphs expects to be carrying each grade in
the minors at a typical moment. This is an assumed distribution, not a measurement. Compare
against the live 2026 counts in Part 7.3, which are much larger at 50 (91 across both types).

## 7.6 Edwards 2019: below 50 FV (L3)

| Grade | Number of Players | AVG WAR* | 2018 $ Value** |
|---|---|---|---|
| 45+ POS | 18 | 0.9 | $8 M |
| 45+ P | 18 | 0.7 | $6 M |
| 45 POS | 76 | 0.7 | $6 M |
| 45 P | 76 | 0.4 | $4 M |
| 40+ POS | 38 | 0.4 | $4 M |
| 40+ P | 38 | 0.3 | $3 M |
| 40 POS | 211 | 0.2 | $2 M |
| 40 P | 211 | 0.1 | $1 M |

Quantity and units: same present-day-WAR definition as 7.5, at $9M per win. Edwards
restates it:

> "if I say a prospect is worth 2 WAR, that indicates his value over the course of the next
> nine seasons put into present day (ie 2019) WAR - which accounts for his final prospect
> years and cost-controlled seasons, as well."
> - Craig Edwards, L3 (2019)

Note the four sub-50 tiers Edwards uses are 45+, 45, 40+, 40. There is no 35+ tier in 2019;
35+ first appears in the 2026 table.

## 7.7 The 2025 outcome-distribution tables (L6)

These are the most directly implementable bust tables, because they are stated as full
outcome distributions rather than a single mean.

Method: FanGraphs prospect lists 2019-2022, 45 FV and above, paired with projections three
years later. Hitters normalised to 600 PA, pitchers to 200 IP. Outcome bins:

> "I counted everything below 0.5 WAR per season as a 'washout,' including those players who
> didn't have major league projections three years later. [...] I graded results between 0.5 and
> 1.5 WAR as 'backup.' I classified seasons between 1.5 and 2.5 WAR as 'regular,' as in a major
> league regular. Finally, 2.5-4 WAR merited an 'above average' mark, while 4-plus WAR got a
> grade of 'star.'"
> - Ben Clemens, L6 (2025)

### Hitters

| FV | Washed Out | Backup | Regular | Above Average | Star | Count |
|---|---|---|---|---|---|---|
| 45 | 51% | 25% | 17% | 6% | 1% | 295 |
| 45+ | 52% | 18% | 19% | 11% | 1% | 91 |
| 50 | 23% | 24% | 30% | 21% | 2% | 197 |
| 55 | 17% | 17% | 30% | 31% | 6% | 54 |
| 60 | 14% | 12% | 19% | 38% | 17% | 42 |
| 65 | 0% | 33% | 33% | 0% | 33% | 3 |
| 70 | 0% | 0% | 0% | 0% | 100% | 2 |
| 80 | 0% | 0% | 0% | 0% | 100% | 1 |

### Pitchers

| FV | Washed Out | Backup | Regular | Above Average | Star | Count |
|---|---|---|---|---|---|---|
| 45 | 53% | 26% | 16% | 5% | 0% | 230 |
| 45+ | 38% | 24% | 25% | 13% | 0% | 68 |
| 50 | 27% | 27% | 24% | 20% | 2% | 96 |
| 55 | 17% | 20% | 37% | 27% | 0% | 30 |
| 60 | 17% | 33% | 25% | 25% | 0% | 12 |
| 65 | 0% | 0% | 0% | 100% | 0% | 1 |
| 70 | 0% | 0% | 100% | 0% | 0% | 1 |

Quantity and units for both: row-wise probability distribution over five outcome bins, where
the bins are PROJECTED WAR per normalised season three years after the prospect was graded
(600 PA for hitters, 200 IP for pitchers). BUST-INCLUSIVE: "washed out" includes players
with no major league projection at all. Rows sum to 100% up to rounding. Counts are the
number of graded prospect-seasons in each tier.

Do NOT read these as six-year or career outcomes. They are a single projected season at a
fixed three-year horizon, which is why the 65 and 70 rows are unusable (counts of 1 to 3).
FanGraphs says so: "there are only six data points above 60 FV, so that's mostly a stab in
the dark."

Note the 45 and 45+ hitter rows have essentially the SAME washout rate (51% and 52%); the
"+" buys upside, not safety. FanGraphs states this:

> "The 45+ FVs look like the 45 FVs, only with a better top end; their chances of ending up
> above average are meaningfully better."
> - Ben Clemens, L6 (2025)

For pitchers the pattern is different: the 45+ washout rate (38%) is much better than 45
(53%). The two sides disagree about what "+" buys.

L6's non-additivity warning, with a worked example:

| Group | Washed Out | Backup | Regular | Above Average | Star |
|---|---|---|---|---|---|
| Two 50 FVs | 46% | 49% | 60% | 42% | 4% |
| One 55, One 45 | 68% | 42% | 47% | 37% | 6% |

Quantity and units: SUMMED (not averaged, not compounded) probabilities across two
prospects, so rows sum to 200%. This is explicitly a shorthand: "Adding isn't exactly the
right way to handle this, but it's a good shorthand for quick comparisons." The correct
figures FanGraphs gives from its own calculator are: odds of at least one above-average or
better, 40.7% for two 50s versus 41.4% for the 45/55 split; odds of two players who are at
least regulars, 28.1% versus 16.1%; odds of at least one star, 4% versus 6%.

## 7.8 ETA and cohort handling

Two distinct treatments, and they are not the same:

1. **In the FV grade itself**, ETA is priced by DEDUCTION. A distant prospect gets a lower
   FV than an identical near-ready prospect (Part 5.5). So a 50 FV given to a GCL teenager
   already embeds a proximity penalty, and the valuation tables can be applied to it
   directly without a further ETA adjustment.
2. **In the 2026 valuation**, ETA enters twice: through the residence-time scale-up (about
   2 years in the minors for sub-50 prospects, used to convert a per-debut-class value into
   a whole-minors value) and through the net 7% discount applied per year of team control.
   There is no per-prospect ETA discount in the published tables.

There is no published table of FV values by ETA. A 50 FV in Rookie ball and a 50 FV in
Triple-A carry the SAME published surplus value, on the argument that the difference is
already inside the grade.

---

# Part 8. What FV is NOT

Every item here is a direct disclaimer from a FanGraphs author.

**Not a prediction of a specific WAR total.**

> "The WAR-to-overall-player-grade conversion also isn't perfect, so don't assume someone is
> an 80 for the rest of time after one 7-win season by one of the WAR metrics. It's a guide to
> convert a scouting grade convention for minor leaguers and amateur players to a scale that
> can be understood for purposes like valuing players in trades."
> - Kiley McDaniel, S3 (2014)

**Not an average of the tool grades.**

> "The scout isn't just averaging the core future tool grades; he's trying to use one number
> to describe how valuable this player is on the overall player market, taking into account
> risk, distance to ceiling and other factors."
> - Kiley McDaniel, S3 (2014)

**Not a single-season observation, and not confused by variance in playing time.**

> "The WAR grade here is meant as a true talent level, so crazy BABIP and UZR swings or
> playing time varying year-to-year doesn't confuse us. I also may project a player's upside or
> future tool grades to be a 3-win player, but the overall grade is subjective and includes
> various types of risk in the determination."
> - Kiley McDaniel, S3 (2014)

**Not exact at the band boundaries.**

> "Don't let the decimals fool you into thinking this is perfectly exact. These WAR bands are
> based on actual big league standard deviations, but the lines between the buckets aren't as
> stark as the chart makes it seem."
> - Eric Longenhagen, L7 (2022)

**Not as scientific as it looks.**

> "I think the Future Value system and the 20-80 scouting scale itself are often regarded as
> more scientific than they actually are. They primarily function as a means of communicating
> information about players with others who already know the language."
> - Eric Longenhagen, L9 (2017)

**Not a total order within a tier.**

> "We think you can make strong arguments to rank players within the same FV tier in a lot of
> different ways, especially as we move down the scale. Lots of the 40 FV prospects on our
> lists are risky young players who might be really good one day but might also be nothing, and
> several of our 40 FV players are near-ready back-end starters. Some teams would, if given the
> chance, take the lottery ticket instead of the low-ceiling starter. [...] In short, teams behave
> logically, but we don't think that logic is uniform across baseball"
> - Longenhagen and McDaniel, S2 (2018)

The practical version of that: the SAME FV can mean two very different distributions.

**Not comparable across publications.**

> "I'll also note that the other prospect publications do not go about prospecting in exactly
> the same way we do, even though they often also make use of the 20-80 scale. You should be
> sure to refer to the explanations they provide for their methodology when you engage with
> them around their work rather than assuming it mimics ours."
> - Eric Longenhagen, L7 (2022)

L9 gives the specific contrast: Baseball America pairs a 20-80 ceiling grade with a risk word
("60 Extreme" or "45 Safe"), while Baseball Prospectus and many clubs publish BOTH a ceiling
grade and a most-likely-role grade ("50, #4 starter" plus "40, Middle Relief"). FanGraphs
collapses all of that into one number.

**Not stable across eras of its own definition.** The FV grade set, the reliever ceiling, the
peak-versus-average framing, and the meaning of "+" have all changed between 2014, 2018,
2022 and 2026. See Part 6.4 and the Open Questions.

**Not a claim about an individual's probability.**

> "Grades aren't innate things, they're just our team's best attempt at capturing the relative
> upside and risk of yet-to-debut players."
> - Ben Clemens, L6 (2025)

**Not durable against CBA change, on the dollar side.**

> "Importantly, these estimates reflect the current structure of the minor leagues and player
> compensation; should the next collective bargaining agreement change the rules of early-career
> compensation, or even change free agency such that the cost of a win moves meaningfully, these
> surplus values will move as well. The WAR estimates and the odds of a player being a star are
> more robust [sic] to changes in compensation structure, but if the length of team control
> changes, those will need recalibration too."
> - Ben Clemens, L1 (2026)

---

# Part 9. Checking the owner's summary against the sources

Owner's stated understanding: "80 FV = ~7.0 WAR, a #1 starter or a top 1-2 player; 45 =
platoon/util bat, #5 starter, low setup man".

**Verdict: exactly correct, and it is quoting McDaniel's 2014 combined table (Part 3.1),
verbatim in its role labels.** That table's 80 row reads Hitter "Top 1-2", Starting Pitcher
"#1 Starter", WAR 7.0. Its 45 row reads Hitter "Platoon/Util", Starting Pitcher "#5", Relief
Pitcher "Low Setup", WAR 1.5. The owner's summary is a faithful reading of S3.

Three corrections to attach to it, none of which contradict the summary itself:

1. **The units are contested even within FanGraphs.** S3 (2014) calls the 7.0 a true-talent
   WAR level. L10 (2015) calls the same number the most likely PEAK season. S2 (2018) and L7
   (2022) explicitly reject peak and define it as average annual WAR over the first six
   service years. Pick one deliberately; they are one to two grades apart for a variable
   player.

2. **The 2014 table is not the current FanGraphs table.** The modern primer tables (Parts
   3.2 to 3.4) drop the 65 and 75 rows entirely, replace point values with bands, split
   hitters and pitchers, and route relievers through a separate subjective role ladder that
   tops out at 50 rather than 60. The owner's summary is correct about 2014 and incomplete
   about 2026.

3. **Neither the 7.0 nor the 1.5 is a valuation input.** The 2026 valuation table has no 80
   row at all, and its 45 FV hitter figure is 2.5 TOTAL team-control WAR, bust-inclusive.
   That is not 1.5 per year and it is not comparable to it. Confusing these two is the single
   biggest available error in this domain.

---

# Part 10. Quantity register for implementers

Every WAR-like number in this document, with its exact meaning. If a model consumes any of
these, it must record which row it used.

| Label | Source | Population | Time base | Bust-inclusive? | Units |
|---|---|---|---|---|---|
| Tool grade to mph / sec / AVG / HR | S3 2014 | Industry consensus, MLB at maturity | Mature season | No | mph, seconds, AVG, HR per season |
| Tool grade to z and stat | W2 2013 | MLB 2010-2012, qualified | 3-year average | No | varies per tool |
| Per-tool WAR | W1 2013 | Constructed 2013 league-average hitter | Single season, 550 PA | No | WAR, all other tools held average |
| Whole-player WAR/600, /200, /60 | W3 2013 | MLB 2010-2012 | Single season rate | No | WAR per 600 PA, 200 IP, 60 IP |
| Combined overall-grade WAR | S3 2014 | MLB | Per season, true talent | No | WAR per season |
| Combined overall-grade WAR, peak reading | L10 2015 | MLB | Most likely PEAK season | No | WAR per season |
| Primer WAR bands, hitters | S2 2018, L7 2022 | MLB, 200 PA and starters-only passes | Average annual, first 6 service years | No | WAR per season, band |
| Primer WAR bands, starters | S2 2018, L7 2022 | MLB, 50 IP and rotation-only passes | Average annual, first 6 service years | No | WAR per season, band |
| Edwards present-day WAR | L2, L3 2019 | BA Top 100 1996-2010, all rankings | First 9 seasons, redistributed, arb-discounted, 8% PV | YES | discounted WAR |
| Edwards bust rate | L2 2019 | same | same | YES | share under 1.0 present-day WAR |
| Edwards star rate | L2 2019 | same | same | YES | share over 10.0 present-day WAR |
| Clemens expected WAR | L1 2026 | BA Top 100 2005-2016 plus FG 2017-2018 | TOTAL team control span (6 to 7-plus yrs), undiscounted | YES | total WAR |
| Clemens expected surplus | L1 2026 | same | Team control span, 7% net discount | YES | 2026 dollars, present value |
| Clemens star odds | L1 2026 | same | Team control span | YES | probability of 2-plus seasons of 4-plus WAR |
| Clemens outcome bins | L6 2025 | FG lists 2019-2022, 45 FV plus | Single projected season, 3-year horizon | YES | probability over 5 bins |

---

# Part 11. Cross-outlet scale semantics: MLB Pipeline and Baseball America

This part exists because our `grade_normalization` module maps Pipeline and BA grades onto the
FanGraphs scale. Everything below is about whether the same NUMBER means the same THING at each
outlet. The short answer is that it does not, and the mismatches are structural rather than
noise.

## 11.1 MLB Pipeline's published definition, in full

P1 is a glossary entry, not an essay. It is short enough to quote almost completely, and doing
so is the honest way to show how little Pipeline publishes.

> "Scouting grades have been a staple of MLB.com's prospect coverage for years, and they
> generally match how clubs grade players as well."
> - MLB.com glossary, P1

> "Players are graded on a 20-80 scale: 20-30 is well below average, 40 is below average, 50 is
> average, 60 is above average and 70-80 is well above average. When discussing prospects, the
> most important number is the future overall grade, an all-encompassing number on the 20-80
> scale that signifies what each player is projected to ultimately be in the big leagues."
> - MLB.com glossary, P1

> "A future overall grade of 65 or better is for a player who could develop into a future impact
> Major Leaguer, perhaps an All-Star-caliber standout. (Note: Some clubs use a 2-8 scale -- as
> opposed to 20-80 -- which is basically the same thing but without half-grades.)"
> - MLB.com glossary, P1

That is the entire definitional content of the page.

Pipeline's adjective ladder, transcribed as a table:

| Grade | Pipeline's term |
|---|---|
| 20-30 | well below average |
| 40 | below average |
| 50 | average |
| 60 | above average |
| 70-80 | well above average |

Quantity and units: none, naming convention only. Note that Pipeline BANDS the extremes
(20-30 share one label, 70-80 share one label) and publishes no label at all for 45, 55, 65 or
75, even though its own grades use 45 and 55 routinely.

**Correction to the brief for this task.** The brief stated that Pipeline's glossary contains
explicit velocity and run-time grade bands. It does not. The page contains zero HTML tables,
zero occurrences of "60-yard", "home to first" or "pop time", and zero real occurrences of
"mph" (all 186 raw-HTML matches for the string "mph" are CSS substrings inside "emphasis" and
inside MLB design-token variable names). A follow-up search of mlb.com found no other Pipeline
page publishing a grade-to-measurement band table either. Pipeline appears to publish per-tool
20-80 grades on player pages WITHOUT ever publishing the measurement thresholds behind them.
For implementation this means Pipeline's tool grades cannot be re-derived from measurements or
audited against a published scale. They can only be consumed as given.

Three further things P1 does NOT contain, all of which matter:

- No role ladder. Pipeline never says what a 50 overall grade means in terms of playing role
  (regular, platoon, bench, number four starter), and never maps a grade to WAR.
- No risk or variance dimension.
- No statement that 10 points equals one standard deviation. Pipeline's ladder is purely
  ordinal adjectives. This is the only one of the three outlets that does NOT invoke the normal
  distribution.

## 11.2 Baseball America's published definition

B1 states the purpose and the sourcing:

> "For the Baseball America Prospect Handbook, BA authors speak to hundreds of scouts over the
> course of the year to report on prospects and write the scouting reports enclosed. While none
> of the authors is a scout, we use scouts' terminology to accurately report how the industry
> views and projects players. This includes the 20-80 scouting scale, the industry standard for
> grading players and their tools."
> - Kyle Glaser, B1

BA flags up front that the vocabulary is not universal:

> "Not every team uses the wording below. Some use a 2-to-8 scale without half-grades, and
> others use above-average and plus synonymously."
> - Kyle Glaser, B1

That last clause is important for normalization: BA is telling us that some evaluators do not
distinguish 55 from 60 at all.

### BA's adjective ladder, with its own named examples

| Grade | BA's term | BA's named examples |
|---|---|---|
| 20 | As bad as it gets for a big leaguer | Myles Straw's power, Daniel Vogelbach's speed |
| 30 | Well below-average, but not unplayable | Kyle Hendricks' fastball |
| 40 | Below-average | Rafael Devers' defense, Dylan Cease's control |
| 45 | Fringe-average | Matt Chapman's hitting ability, Mike Zunino's arm |
| 50 | Major league average | Jeff McNeil's speed |
| 55 | Above-average | Randy Arozarena's power |
| 60 | Plus | Marcus Semien's defense, Zac Gallen's control |
| 70 | Plus-Plus. Among the best tools in the game | Freddie Freeman's hitting ability, Blake Snell's curveball, Ronald Acuna Jr.'s arm |
| 80 | Top of the scale | Shohei Ohtani's power, Corbin Carroll's speed, Devin Williams' changeup |

Quantity and units: none, naming convention with exemplars. Player names transcribed as
printed, including BA's own spellings.

BA's own note on how exclusive an 80 is:

> "Some scouts consider only one player's tool in all of the major leagues to be an 80."
> - Kyle Glaser, B1

Note that BA's ladder omits 65 and 75, yet BA's own SPEED and FASTBALL measurement tables below
DO carry a 65 row. So BA uses 65 as a measurement grade without giving it an adjective, which is
the same pattern FanGraphs has.

### BA's per-tool measurement tables

BA prints these as text blocks with dot leaders rather than as HTML tables. They are transcribed
here as tables with no value changes. BA's own preamble:

> "(Note: The following scales were created in conjunction with major league teams to best
> reflect overall industry standards. Individual teams' scales may differ.)"
> - Kyle Glaser, B1

**HIT**

| Grade | Batting Avg |
|---|---|
| 80 | .315+ |
| 70 | .295-.314 |
| 60 | .275-.294 |
| 55 | .265-.274 |
| 50 | .255-.264 |
| 45 | .245-.254 |
| 40 | .235-.244 |
| 30 | .215-.234 |
| 20 | <.215 |

Quantity and units: major league batting average, projected, HITTERS. Bands, not points. No 65
or 75 row. Note the bands are 10 points of AVG wide at 55/50/45/40 and 20 points wide at 70/60.

**POWER**

| Grade | Home Runs |
|---|---|
| 80 | 40+ |
| 70 | 34-39 |
| 60 | 28-33 |
| 55 | 23-27 |
| 50 | 19-22 |
| 45 | 14-18 |
| 40 | 10-13 |
| 30 | 5-9 |
| 20 | 0-4 |

Quantity and units: home runs per major league season, GAME power, HITTERS. BA states this is
career-average framed, not peak: "game power is graded by how many home runs the hitter projects
to hit in the majors, preferably an average over the course of a career." BA also states the
scale has been moved: "We have tweaked our power grades based on the recent rise in home run
rates to reflect changing industry standards."

**SPEED**

| Grade | Home-First RHH (secs) | Home-First LHH (secs) |
|---|---|---|
| 80 | 4.00 | 3.90 |
| 70 | 4.10 | 4.00 |
| 65 | 4.15 | 4.05 |
| 60 | 4.20 | 4.10 |
| 55 | 4.25 | 4.15 |
| 50 | 4.30 | 4.20 |
| 45 | 4.35 | 4.25 |
| 40 | 4.40 | 4.30 |
| 30 | 4.50 | 4.40 |
| 20 | 4.60 | 4.50 |

Quantity and units: seconds, home plate to first base, by batter handedness. Lower is better.
Handedness adjustment is a flat 0.10 seconds, identical to FanGraphs.

**FASTBALL**

| Grade | Velocity (Starters) |
|---|---|
| 80 | 98+ mph |
| 70 | 97 |
| 65 | 96 |
| 60 | 95 |
| 55 | 94 |
| 50 | 93 |
| 45 | 92 |
| 40 | 90-91 |
| 30 | 88-89 |
| 20 | 87 or less |

Quantity and units: miles per hour, average fastball velocity over a typical outing, STARTING
PITCHERS. BA is explicit that this is an average and not a peak: "Fastballs earn their grades
based on the average range of the pitch over the course of a typical outing, not their peak
velocity."

BA's two published adjustments to this table:

> "You can reduce the scale by 1 mph for lefthanders, whose velocities are usually slightly
> lower."
> - Kyle Glaser, B1

> "A move to the bullpen complicates in another direction. Pitchers airing it out for one inning
> should throw harder than someone trying to last six or seven innings, so add 1-2 mph for
> relievers."
> - Kyle Glaser, B1

So BA's full velocity model is: starter table, minus 1 mph for left-handers, plus 1 to 2 mph for
relievers. The lefty adjustment matches Mark Smith's W2 exactly.

BA also warns the velocity grade is not the fastball grade:

> "A fastball grade doesn't stem solely from its velocity - command and life are crucial
> elements as well. A 100 mph fastball with poor movement characteristics may grade below a 97
> mph fastball with elite movement."
> - Kyle Glaser, B1

**ARM STRENGTH (catchers)**

| Grade | Pop Times To Second Base (secs) |
|---|---|
| 80 | < 1.90 |
| 70 | 1.90-1.94 |
| 60 | 1.95-1.99 |
| 50 | 2.00-2.04 |
| 40 | 2.05-2.09 |
| 30 | 2.10-2.14 |
| 20 | > 2.15 |

Quantity and units: seconds, catcher pop time, defined by BA as "the time it takes from the pop
of the ball in the catcher's mitt to the pop of the ball in the fielder's glove at second base".
Lower is better. CATCHERS only.

This is the ONLY published grade-to-measurement arm-strength table found at any of the three
outlets. It closes part of open question Q3, but only for catchers, and only in pop-time seconds
rather than throw velocity. There is still no published grade-to-mph arm table for outfielders or
infielders anywhere. BA describes the non-catcher method qualitatively only: "Arm strength can be
evaluated by observing the velocity and carry of throws, measured in workouts with radar guns".

BA on defense, also qualitative only and explicitly position-dependent:

> "Defense takes different factors into account by position but starts with proper footwork and
> technique, incorporates physical attributes such as hands, short-area quickness and fluid
> actions, then adds subtle skills such as instincts and anticipation."
> - Kyle Glaser, B1

## 11.3 BA's overall grade: an UPSIDE grade, not an FV

This is the single most consequential cross-outlet difference and it is stated plainly in B2.

> "We casually refer to them as 'BA Grades,' but in reality, our grades have always had two
> vital components: a future role grade and the likelihood of achieving that grade."
> - J.J. Cooper, B2

> "The number component is an attempt to summarize the likely projected role of a prospect on
> the familiar 20-80 scouting scale"
> - J.J. Cooper, B2

BA's role ladder, verbatim:

| BA Grade | Role definition |
|---|---|
| 80 | A player we expect to see in Cooperstown one day. |
| 70 | One of the best players in the game and someone who may reach the Hall of Fame. |
| 60 | A top-tier regular who likely makes All-Star Game appearances. |
| 50 | A solid regular for a competitive team and someone who would not look out of place in a postseason lineup. |
| 45 | A regular for a second-division team or a player with a smaller role on a competitor. |
| 40 | An MLB role player. |

Quantity and units: role labels only. No WAR anywhere. HITTERS and PITCHERS are not separated.
No rows for 20, 30, 35, 55, 65, or 75, although 55 is used in B2's own worked examples.

The decisive sentence, which says the role grade does NOT include the probability:

> "While these role grades paint a picture of a player's upside, they don't account for the
> likelihood of that upside being achieved."
> - J.J. Cooper, B2

So a BA 50 is an UPSIDE statement. A FanGraphs 50 FV is not; FanGraphs bakes risk and proximity
INTO the number (Part 5.5). These are different quantities wearing the same digits.

## 11.4 Where the three outlets disagree

### X1. Whether the scale is a standard-deviation scale

FanGraphs asserts it explicitly and repeatedly (10 points equals one SD, three SD covers 99.7%).
BA never mentions standard deviations, normal distributions, or percentiles anywhere in B1 or B2;
its ladder is adjectives plus measurement bands. Pipeline likewise never mentions them. So of the
three, only FanGraphs claims a distributional interpretation. Any normalization that assumes all
three outlets are emitting z-scores is importing an assumption that two of the three never made.

### X2. Fastball velocity: BA's scale sits about 2 mph above FanGraphs'

| Grade | FanGraphs S3 (2014) | BA B1 (current) | Smith W2 SP (2013) | Gap, BA minus FG |
|---|---|---|---|---|
| 80 | 97 | 98+ | 97 | +1 or more |
| 75 | 96 | (no row) | n/a | n/a |
| 70 | 95 | 97 | 95 | +2 |
| 65 | 94 | 96 | n/a | +2 |
| 60 | 93 | 95 | 93 | +2 |
| 55 | 92 | 94 | n/a | +2 |
| 50 | 90-91 | 93 | 91 | +2 to +3 |
| 45 | 89 | 92 | n/a | +3 |
| 40 | 88 | 90-91 | 88 | +2 to +3 |
| 35 | 87 | (no row) | n/a | n/a |
| 30 | 86 | 88-89 | 86 | +2 to +3 |
| 20 | (no row) | 87 or less | 84 | n/a |

Units: miles per hour, average fastball velocity, starting pitchers. This is a genuine and
LARGE scale offset: a 93 mph starter is a 60 on the 2014 FanGraphs scale and a 50 on BA's current
scale. BA says why, and it is era drift rather than disagreement:

> "Velocity steadily has increased over the past two decades. Not long ago, an 88-91 mph fastball
> was considered major league average. Now, major league starting pitchers sit 93 mph on
> average."
> - Kyle Glaser, B1

Note BA's "not long ago, an 88-91 mph fastball was considered major league average" is a direct
description of the FanGraphs 2014 table's 50 row (90-91) and 40 row (88). BA is not contradicting
FanGraphs; BA has re-centred and FanGraphs' published table has not. The FanGraphs 2014 velocity
column should be treated as STALE, not as a competing convention. Smith's 2013 numbers agree with
FanGraphs 2014, which confirms the 2014 table was correct for its era.

### X3. Game power: BA's scale also sits above FanGraphs'

| Grade | FanGraphs S3 (2014) HR | BA B1 (current) HR | Gap |
|---|---|---|---|
| 80 | 40+ | 40+ | same |
| 75 | 35-40 | (no row) | n/a |
| 70 | 30-35 | 34-39 | +4 |
| 65 | 27-30 | (no row) | n/a |
| 60 | 23-27 | 28-33 | +5 to +6 |
| 55 | 19-22 | 23-27 | +4 to +5 |
| 50 | 15-18 | 19-22 | +4 |
| 45 | 12-15 | 14-18 | +2 to +3 |
| 40 | 8-12 | 10-13 | +1 to +2 |
| 35 | 5-8 | (no row) | n/a |
| 30 | 3-5 | 5-9 | +2 to +4 |
| 20 | (no row) | 0-4 | n/a |

Units: home runs per full major league season at maturity, hitters. BA again states the reason
is deliberate recalibration: "We have tweaked our power grades based on the recent rise in home
run rates to reflect changing industry standards." Note the offset is NOT uniform: it is about +4
to +6 HR in the 50 to 70 range and only +1 to +3 at 40 and 45. A linear shift will not reconcile
these two scales.

### X4. Hit tool: the two outlets agree

FanGraphs prints points (50 = .260) and BA prints bands (50 = .255-.264). The FanGraphs point
value falls inside the BA band at every shared grade: FG .260 inside BA .255-.264 at 50; FG .250
inside BA .245-.254 at 45; FG .240 inside BA .235-.244 at 40; FG .270 inside BA .265-.274 at 55;
FG .280 inside BA .275-.294 at 60. The hit scale has NOT drifted, unlike velocity and power. This
is a useful control: it shows the velocity and power gaps are real recalibration and not a
general BA-versus-FanGraphs offset.

### X5. Speed: the two outlets agree exactly

The home-to-first tables are identical at every shared grade and both use a flat 0.10 second
handedness adjustment. BA additionally publishes 20 and 30 rows (4.60/4.50 and 4.50/4.40) where
FanGraphs stops at 30 (4.50/4.40, which matches BA's 30 row exactly). FanGraphs publishes a
60-yard-dash column that BA does not.

### X6. What the overall number means: three different quantities

| Outlet | Overall grade name | What it measures | Risk included in the number? | Mapped to WAR? |
|---|---|---|---|---|
| FanGraphs | FV (Future Value) | Average annual WAR over the first six service years | YES, deducted from the grade | YES, banded |
| MLB Pipeline | Future overall grade | "what each player is projected to ultimately be in the big leagues" | Not stated | No |
| Baseball America | BA Grade (role grade) | Projected future ROLE if achieved, i.e. upside | NO, carried separately as a risk tier | No |

This is the core normalization problem, and it is a three-way mismatch rather than a two-way one:

- **BA versus FanGraphs.** BA's headline number is upside-only; FanGraphs' is risk-discounted.
  BA quantifies its own gap: the median prospect carries an "average" risk tier worth minus 10
  points (Part 12). So a BA 50 with median risk is BA-internally equivalent to an adjusted 40.
  Mapping BA's HEADLINE number onto FV without applying BA's own risk penalty will systematically
  overrate BA-sourced prospects, by roughly one full tier at the median and by up to four tiers
  at the extremes (a 60/Extreme is a BA-adjusted 40). The correct FanGraphs-comparable BA field is
  the ADJUSTED grade, which BA began printing in 2026 (Part 12.3), not the headline grade.
- **Pipeline versus FanGraphs.** Pipeline's word "ultimately" reads as an upside or ceiling
  framing closer to BA's than to FanGraphs'. But Pipeline never says whether risk is inside the
  number, so this cannot be resolved from the published text. It is an unquantified mismatch of
  unknown sign, which is worse for calibration than a known one. See Q23.
- **Pipeline's one published anchor.** "A future overall grade of 65 or better is for a player who
  could develop into a future impact Major Leaguer, perhaps an All-Star-caliber standout." The
  All-Star anchor is the one role label all three outlets happen to name, so it is the only
  directly comparable point available. BA puts All-Star appearances at 60. FanGraphs puts All-Star
  at 60 in the 2018 and 2022 primer tables, but at 65 in the 2014 combined table (whose 60 row
  reads "Plus" and whose 65 row reads "All-Star"), so FanGraphs itself is split across eras.
  Pipeline puts All-Star-caliber at 65 or better. Taking the modern FanGraphs and BA position of
  60, Pipeline's All-Star anchor sits ONE TIER HIGHER. That is the single quantifiable
  Pipeline-versus-others offset available from the published text, and its direction matches the
  BA-versus-FanGraphs direction: Pipeline's numbers, like BA's, appear to need discounting rather
  than inflating to reach FV. One anchor is thin evidence, so treat the magnitude as unresolved
  and the sign as weakly indicated.

### X7. Granularity and which grades legally exist

| Outlet | Grades with published adjectives | Grades appearing in measurement or role tables | Half-grade / plus convention |
|---|---|---|---|
| FanGraphs | 45, 50, 55, 60, 70, 80 | 30 to 80 by 5s (tools); 20/30/40/45/50/55/60/70/80 (FV bands) | "+" tiers 35+, 40+, 45+ below 50 only |
| MLB Pipeline | 20-30, 40, 50, 60, 70-80 (banded) | none published | none published |
| Baseball America | 20, 30, 40, 45, 50, 55, 60, 70, 80 | 20/30/40/45/50/55/60/65/70/80 (varies by tool) | none; risk tier carried separately |

Consequences for normalization: FanGraphs is the only outlet with sub-5-point tiers ("+"), and it
uses them only below 50. BA has no "+" at all and instead splits the same information into a
separate risk axis. Pipeline publishes neither. So FanGraphs' 45+ has no BA or Pipeline
counterpart, and BA's 50/High has no FanGraphs counterpart. A quantile map can align the
marginal distributions but cannot recover either outlet's missing axis.

### X8. All three agree on one thing

All three outlets independently state that the 2-8 scale is an equivalent convention used by some
clubs, and that it lacks half-grades. FanGraphs S3: "many teams use a 2-8 scale rather than
20-80". Pipeline P1: "Some clubs use a 2-8 scale ... which is basically the same thing but without
half-grades." BA B1: "Some use a 2-to-8 scale without half-grades". Any ingestion of club-sourced
grades should expect integers 2 through 8 mapping to 20 through 80 with no 45, 55, 65 or 75
available.

---

# Part 12. Baseball America's risk system

FanGraphs has no equivalent to this. It is the second axis BA carries that FanGraphs collapses
into its single FV number.

## 12.1 Why BA carries a second axis

> "Risk assessment, then, is [essential] when comparing, for example, a tooled-up Dominican
> Summer League star to a Triple-A player ready to contribute now. Or when comparing a position
> player to a pitcher. Or when comparing a player who missed a year to injury with one who has a
> long track record of good health."
> - J.J. Cooper, B2 (one word replaced, see the copy-gate note at the end of this file)

The three comparisons BA names as needing a risk axis (level/proximity, hitter versus pitcher, and
injury history) are exactly the three things FanGraphs says it handles by DEDUCTING from FV
(Parts 5.4 and 5.5). Same problem, opposite architecture.

## 12.2 The 2026 baseline reset

This is an era break in BA's own data and it must be handled by anyone using BA grades across
years.

> "When BA Grades were introduced in 2012, we settled on 'high' as the baseline risk for all
> players, because prospects carry high risk when compared with major leaguers."
> - J.J. Cooper, B2

> "But it also wasn't what we wanted to fully convey. Those prospects deemed high risk weren't
> riskier than the average prospect. They were just risky, like all prospects."
> - J.J. Cooper, B2

> "In the past, we have used 50/High - which represents a 50 role grade and high risk - as a
> baseline for the run-of-the-mill, solid prospects we rank. This year, those will be 50/Average
> prospects."
> - J.J. Cooper, B2

> "By changing our baseline risk grade from high to average, we hope to better convey how a
> prospect compares to other top prospects. All prospects are risky, but a prospect with average
> risk is a player who is not particularly risky when compared to other prospects."
> - J.J. Cooper, B2

So the SAME player who was a 50/High in 2025 is a 50/Average in 2026. The role grade did not move;
the risk LABEL did. Under BA's own penalty table that is a 5-point change in adjusted grade for an
unchanged player. Any longitudinal use of BA risk tiers across the 2025/2026 boundary must
re-baseline or it will read a labelling change as a real improvement in risk.

BA dates the change and its own unease about it:

> "This year, we're making the biggest tweak to the process since BA Grades debuted nearly 15
> years ago."
> - J.J. Cooper, B2

> "This is a big adjustment for BA, and it doesn't come without some concern about changing a
> system that we have maintained for more than a decade."
> - J.J. Cooper, B2

## 12.3 The risk ladder and the penalty table

BA's 2026 risk tiers, verbatim:

| Risk tier | BA's definition |
|---|---|
| Low risk | A player who is close to the majors, typically with little or no projection remaining and no pressing injury questions, with a high probability of having a major league career in some capacity. |
| Mild risk | Some work left to refine their skills, but a proven player who typically comes with upper minors performance. |
| Average risk | The most common or median risk level for players ranked among a team's Top 30 prospects. The average prospect has significant risk or weaknesses in some areas of their game, typical of most prospects. |
| High risk | Players with injury questions, players who struggle with a key skill (especially control for pitchers or contact for hitters) and many teenagers in the low minors with significant projection remaining. |
| Extreme risk | Players who have well above-average durability issues, multiple skills/tools issues to resolve and inexperienced teenage prospects who are years from the majors. |

Quantity and units: ordered categorical, five levels, Low being least risky. "Average" is defined
DISTRIBUTIONALLY as the median of a team's Top 30, which makes it the only anchored tier.

The penalty table, which converts the two axes into one number:

| Risk tier | Penalty to BA Grade |
|---|---|
| Low | No penalty |
| Mild | -5 points |
| Average | -10 points |
| High | -15 points |
| Extreme | -20 points |

Quantity and units: points on the 20-80 scale, SUBTRACTED from the role grade to produce the
adjusted grade. Note the source prints these with a Unicode minus-like glyph; they are
transcribed here as plain hyphens with no value change.

> "Internally, we have always fused the BA Grade and risk together into what we call an adjusted
> grade. For the first time, we are printing those adjusted BA Grades to provide maximum
> transparency."
> - J.J. Cooper, B2

So: **adjusted grade = role grade minus risk penalty**, and the penalty is a clean linear 5 points
per tier. The equivalence classes this creates are stated explicitly:

> "Adjusted grades are designed to capture how different player types with varying levels of
> experience can line up on an ordinal ranking. A 40/Low, for example, carries the same adjusted
> grade of 40 as a 45/Mild or a 50/Average or a 55/High or a 60/Extreme."
> - J.J. Cooper, B2

Worked out as a grid, adjusted grade by role grade and risk tier (our arithmetic from BA's rule,
with BA's own stated diagonal shown to verify it):

| Role grade | Low (0) | Mild (-5) | Average (-10) | High (-15) | Extreme (-20) |
|---|---|---|---|---|---|
| 60 | 60 | 55 | 50 | 45 | **40** |
| 55 | 55 | 50 | 45 | **40** | 35 |
| 50 | 50 | 45 | **40** | 35 | 30 |
| 45 | 45 | **40** | 35 | 30 | 25 |
| 40 | **40** | 35 | 30 | 25 | 20 |

The bolded diagonal is exactly the equivalence class BA names. Derived by us from BA's stated
rule; only the diagonal is published.

Two published calibration anchors on the adjusted scale:

> "Top 100 Prospects can be counted on to carry an adjusted BA Grade of 45 or better (e.g.
> 50/Mild, 55/Average or 60/High)."
> - J.J. Cooper, B2

> "Conversely, a farm system full of players with an adjusted grade of 35 or lower is either full
> of unproven, faraway prospects or low-ceiling role players - or some mixture of the two."
> - J.J. Cooper, B2

Those two sentences make the adjusted grade the directly usable field: adjusted 45 or better is
BA's Top 100 threshold, and adjusted 35 or lower is BA's marker for a weak system. Compare with
FanGraphs, whose Top 100 threshold is a 50 FV or better (Part 7.2's cohort note: "the number of
50-FV and above players growing to 123 over the course of this list cycle"). So BA adjusted 45
lines up roughly with FanGraphs FV 50 as a Top-100 cut, which is a concrete, testable
cross-outlet anchor.

BA also notes the two axes support genuinely different team preferences rather than one being
correct:

> "For those teams that chase upside and are tolerant of risk, a 60/Extreme prospect ranked four
> spots behind a 50/Average player may be preferable. For those who don't want to be burned by the
> siren song of potential, the 45/Mild prospect may appear to be the better bet."
> - J.J. Cooper, B2

## 12.4 Two-dimensional grade versus one-number bust-inclusive FV (conceptual only)

No implementation here, per the brief. The conceptual mapping is this.

BA emits an ordered pair: a CENTRAL grade that is an upside/role statement, plus a RISK tier that
is a coarse, five-level statement about the probability of reaching it. It then collapses the pair
by a fixed linear rule (5 points per tier) into an adjusted grade used for ordinal ranking.
FanGraphs emits ONE number that has already had risk subtracted, by a subjective and explicitly
unpublished amount ("The amount we deduct for things like risk due to injury or player
demographics is subjective, and we don't have a guideline to share", S2).

Three things follow.

First, BA's architecture is RECOVERABLE and FanGraphs' is not. Because BA publishes both the role
grade and the penalty, a consumer can undo the risk discount and get back to a pure upside
statement, or re-apply a different discount. A FanGraphs FV cannot be decomposed back into upside
and risk, because the deduction was never published per player. For our purposes, BA's pair is
strictly more informative even though its risk axis is coarser.

Second, BA's collapse rule is LINEAR and RISK-INDEPENDENT OF GRADE, which cannot be right in
expectation. A flat minus 10 for average risk applies the same absolute penalty to a 60 as to a
40, whereas the FanGraphs outcome tables (Part 7.7) show washout rates falling steeply with grade
(51% at 45 FV versus 14% at 60 FV for hitters). A constant additive penalty on an ordinal scale
whose WAR spacing is itself non-uniform (Part 6.4 D1) cannot represent a constant probability
discount. BA's adjusted grade is therefore best read as a RANKING DEVICE, which is exactly what BA
calls it ("designed to capture how different player types ... can line up on an ordinal ranking"),
and not as an expected-value estimate.

Third, and this is the connection to machinery we already have: BA's risk ladder is a
CENTRAL-GRADE-PLUS-DISPERSION representation, and our platform already carries the dispersion
directly, per prospect, as `p_bust` and as outcome-bucket distributions. Those are strictly finer
than a five-level categorical. So BA's risk vocabulary is not something we need to acquire; it is
a candidate DISPLAY LABEL for a quantity we already compute more precisely. The natural reading is
that BA's five tiers are bins of a bust probability, and BA's own definitions supply the anchor
(Average risk is defined as the median of a team's Top 30). Whether our `p_bust` distribution
actually bins onto BA's five tiers in a way that reproduces BA's stated equivalence diagonal is an
empirical question, not a documentation question, and it is logged as Q26.

The clean statement of the difference, for anyone reasoning about it later: FanGraphs' FV is
approximately a MEAN over the outcome distribution (risk already netted in, and the 2026 valuation
tables make the bust-inclusive mean explicit). BA's pair is approximately a MODE plus a SPREAD
(the role grade is the outcome if things go right, the risk tier is how wide the distribution is).
Those are different summary statistics of the same underlying distribution, and for a right-skewed
prospect distribution (Part 7.5: median far below mean at every tier) they are NOT
interconvertible without knowing the shape.

---

# Open questions / ambiguities in the source

Numbered so they can be cited in follow-up work.

**Q1. Peak versus average annual is never reconciled.** L10 (2015) attaches the 2014 WAR
column to "most likely peak season(s)". S2 (2018) says "we are not projecting peak seasons
here". Both refer to the same table of numbers, and S2 explicitly endorses combining its own
bands "pretty much exactly the way Kiley did back in 2014". Either the 2014 numbers changed
meaning silently, or one of the two articles is wrong about its own table. FanGraphs never
addresses this.

**Q2. The 2014 combined table is not an SD scale, despite living in the article that defines
the scale as an SD scale.** S3 asserts 10 points equals one standard deviation, then prints a
WAR column whose steps are 0.5 per 5 points between 40 and 60 and 1.0 per 5 points outside
that range. W3, computing actual SDs on real data, gets uniform 1.9 WAR per 10 points for
hitters. Both cannot be right. Which one a lab should treat as the FanGraphs position is
undetermined by the text.

**Q3. There is no published exit velocity, spin rate, or arm-strength-in-mph table.** S2
(2018) explicitly names "exit velos or curveball spin" as the things analysts grade on the
20-80 scale, and says analysts are the reason 65 and 35 grades get used at all. But no
FanGraphs article located publishes the grade-to-exit-velocity or grade-to-spin scale. The
only arm table (W2) is in outfield defensive runs and Smith himself calls it the wrong unit.
Anyone implementing exit velocity or spin grades is working outside the published corpus.

**Q4. Does the hit tool include plate discipline?** S3 says "The hit tool includes plate
discipline (the most commonly asked-for sixth tool by the internet)". L10 says "the hitting
tool grade only refers to batting average" and that high-discipline hitters "are rated higher
than you'd expect given their pure hit tool grade", implying discipline is handled OUTSIDE
the hit grade. These are the same author one year apart, and they contradict.

**Q5. The "+" has two incompatible published definitions and no announced transition.** In
2014-2015 "+" means plus 2.5 points on a TOOL (45+ = 47.5, 50+ = 52.5). From 2021 it means a
break-out / variance flag on an FV, with the grade set 35+, 40+, 45+ and no 50+. No article
announces the change. Worse, the modern FV data uses "+" only below 50 while the old tool
convention centred it ON 50, so a naive reader of the 2014 article would expect 50+ to be the
most common plus grade of all, when in fact it does not exist.

**Q6. What "+" buys is inconsistent between hitters and pitchers.** L6's washout rates say
45 and 45+ hitters bust at the same rate (51% vs 52%) while 45+ pitchers bust far less than
45 pitchers (38% vs 53%). L7 and L8 describe "+" as purely an upside flag, which fits the
hitter data and not the pitcher data. Unexplained.

**Q7. The reliever ceiling is stated three different ways and never reconciled.** W3 gives
relievers a full 20-80 range up to 80 by grading them against relievers. S3 caps them at 60
and argues against 80. S2 puts dominant bullpen arms at 45. L7's role table stops at 50. And
S2 concedes clubs who call elite relievers 80s are "probably" right about leverage. There is
no single answer in the corpus to "what is the maximum reliever FV".

**Q8. The 45 FV hitter surplus value is stated twice with different numbers.** S1's worked
example says "We value a 45-FV position player at roughly $16 million in surplus value". L1's
published table says $14,500,000. The $16M example also does not decompose to the table's
numbers cleanly (0.2 x $45M + 0.8 x $7M = $14.6M, which matches the TABLE, not the $16M in
the prose). The prose figure appears to be a rounding or a stale draft value.

**Q9. The total value of the minors is stated as two different ranges.** L1 says "between
$10.5 billion and $13.75 billion" with a best guess of $12B. S1's sensitivity section walks
through the same perturbations and produces $10.5B to $12.7B. The $13.75B upper bound in L1
is not reachable from any single perturbation S1 describes.

**Q10. Team control span is "6 to 7-plus years" but every per-year conversion assumes 6.**
S1 says spans exceed seven years for some players and are never under six. The FV definition
is pinned to exactly six. So converting the 2026 total-WAR column into an annual figure has
no correct divisor, and the resulting bust-discount ratio inherits that ambiguity.

**Q11. Cost of a win: linear or not?** L5 (2017) concludes cost per WAR is linear across
average annual values. L4 (2026) concludes it is materially non-linear and quantifies a near
2x ratio between the top and bottom tiers. Both are house positions and the 2026 valuation
depends on the non-linear one to the tune of $1.5B of total minor league value. Whether the
market changed or the earlier method was wrong is not addressed.

**Q12. No published FV rows for 20, 25, or 30 in the valuation lineage.** S3 declines to go
below 30 on the overall scale. The valuation tables stop at 35+. So there is no published
value, WAR, or bust rate for a 20, 25, 30 or plain 35 FV prospect. The 2026 method also
explicitly removes the value generated by prospects who "never received a grade from the
FanGraphs prospect team" before allocating anything, so unranked players are outside the
system entirely rather than being the bottom of it.

**Q13. The sub-50 tier values are an allocation, not a measurement, and FanGraphs says so.**
"We're most confident in the total, not the exact breakdown between tiers." Combined with
"We applied some curve-smoothing to ensure that value climbs sensibly from one grade to the
next rather than bouncing around on small samples", this means the monotonic shape of the
sub-50 tiers is partly IMPOSED and cannot be used as evidence that the ordering is real.

**Q14. The 2026 grade assignment uses future information.** Historical ordinal ranks were
converted to FV grades using "a regressed factor based on that class' major league
production". FanGraphs flags this as a bias but does not bound it. Any lab benchmarking
against these numbers on resolved cohorts is partly benchmarking against a target that saw
the answer.

**Q15. Which W1 power translation is correct?** W1 publishes two power tables and two answers
(0.9 WAR or 0.5 WAR per 10 points) and does not choose. It also halves the standard deviation
below 50 in the first table so the sub-50 rows are on a different scale from the above-50
rows in the same table.

**Q16. W2's tables are not internally consistent at the tails.** The power table produces
negative ISO and negative HR/PA at 20 and 30. The speed table produces negative stolen base
totals. The defence table centres 50 at +1.6 runs rather than 0. Smith acknowledges the first
as "a glitch in the numbers" and does not address the others. Any lab fitting to W2 must
decide whether to truncate or to re-centre.

**Q17. W3's pitcher table header is mislabelled.** The grade column is headed "WAR" and the
value columns are headed "SP/200" and "RP/60". Read literally the header says the grades are
WAR values. This is a source typo, but it means the table cannot be machine-parsed on its
headers alone.

**Q18. Position adjustment has no published magnitude.** FanGraphs says FV is
position-relative ("average everyday big leaguer at their given position") and gives the
first-base example qualitatively, but publishes no per-position offset. Meanwhile W1 folds the
positional adjustment into its fielding grade and W2 pools positions together. There is no way
to reconcile these into a single position term from the published text alone.

**Q19. The 2018 primer promises an updating document that the 2022 and 2026 pieces do not
supersede cleanly.** S2 says "As we continue to augment our thinking and methodology, so too
will we update this document". L7 (2022) says "There have been no significant changes to our
process". Yet the pitcher table's bottom row changed from 30 to 35/35+, a reliever role table
appeared, and the "+" definition shifted. Whether those count as "no significant changes" is
a judgement FanGraphs makes and a lab may not want to accept.

**Q20. Fielding grades may not span the full scale, by FanGraphs' own admission.**
"the entire 20-80 scale is not often used here, and it's hard to know if it should be. After
all, wouldn't an 80-grade second baseman just be able to play SS?" So the fielding tool's
effective range, and whether it is censored by position eligibility, is open.

## Added by the cross-outlet sources (Parts 11 and 12)

**Q21. MLB Pipeline publishes no measurement thresholds at all.** P1 is the whole of Pipeline's
published definition, and it contains no grade-to-mph, grade-to-seconds, or grade-to-anything
table; a follow-up search of mlb.com found none elsewhere. Pipeline nonetheless emits per-tool
20-80 grades on every player page. So Pipeline's tool grades are unauditable against any published
scale and cannot be re-derived from measurements. Whether Pipeline uses the FanGraphs-era
thresholds, BA's re-centred ones, or something private is unknowable from public text.

**Q22. Pipeline never states whether risk is inside its overall grade.** BA says explicitly that
risk is OUTSIDE its role grade; FanGraphs says explicitly that risk is INSIDE its FV. Pipeline says
only that the future overall grade "signifies what each player is projected to ultimately be in
the big leagues". The word "ultimately" hints at a ceiling framing, but this is not a statement
about risk. This is the largest unquantified normalization gap of the three outlets, and unlike the
BA gap it has no published penalty to undo.

**Q23. Pipeline's All-Star anchor is one tier above BA's and above modern FanGraphs'.** Pipeline
places All-Star-caliber at 65-plus; BA and the modern FanGraphs primer place All-Star at 60. A
single anchor cannot establish an offset curve, and FanGraphs' own 2014 table puts All-Star at 65,
matching Pipeline. So whether Pipeline is offset from the modern consensus, or merely frozen at the
older convention, is undetermined.

**Q24. Neither Pipeline nor BA claims a standard-deviation interpretation.** Only FanGraphs does.
If our normalization assumes all three outlets emit comparable z-scores, that assumption is
supported by exactly one of the three sources. BA's scale is adjectives plus measurement bands with
no distributional claim anywhere; Pipeline's is banded adjectives only.

**Q25. BA's velocity and power scales have drifted from FanGraphs' published ones but its hit and
speed scales have not.** BA is about +2 mph on fastball and about +4 to +6 HR on game power at the
50-to-70 range, while the hit and home-to-first scales match FanGraphs exactly. BA attributes both
gaps to deliberate recalibration for era. The FanGraphs 2014 velocity and power columns are
therefore best treated as stale rather than as a competing convention, but FanGraphs has never
published a replacement, so there is no current FanGraphs velocity or power scale to normalize
against. The power offset is also non-uniform (+1 to +3 at 40 and 45, +4 to +6 at 50 to 70), so no
single shift reconciles them.

**Q26. Does our p_bust actually bin onto BA's five risk tiers?** BA's risk ladder is a
central-grade-plus-dispersion representation, and we already carry the dispersion per prospect as
`p_bust` and as outcome-bucket distributions, which are strictly finer than five ordered
categories. That makes BA's tier NAMES (Low / Mild / Average / High / Extreme) a candidate DISPLAY
VOCABULARY for machinery we already have, with the advantage that BA supplies a distributional
anchor for one tier ("Average risk" is defined as the median of a team's Top 30). Two things are
unresolved and are empirical, not documentary. First, whether binning our `p_bust` into five bins
reproduces BA's stated equivalence diagonal (40/Low = 45/Mild = 50/Average = 55/High =
60/Extreme). Second, whether a flat 5-points-per-tier penalty is even representable in our
framework, given that FanGraphs' own outcome tables show washout rates falling steeply and
non-linearly with grade (51% at 45 FV against 14% at 60 FV for hitters), which a
grade-independent additive penalty cannot express. Adopting BA's labels is cheap; adopting BA's
arithmetic would be a step backwards from what we already compute.

**Q27. BA's 2026 risk re-baseline is an undocumented era break in BA's own historical data.** The
same unchanged player who was a 50/High in 2025 is a 50/Average in 2026, which is a 5-point change
in BA adjusted grade for no change in the player. BA states the reset clearly but publishes no
crosswalk and no restated history. Any longitudinal use of BA risk tiers across the 2025/2026
boundary will read a labelling change as a real risk improvement unless it re-baselines. It is also
unstated whether BA's OLD tier set was the same five names (the 2012 scheme is described using
"high", "extreme" and "medium", and "medium" is not one of the 2026 five), so the old and new
ladders may not even have the same cardinality.

**Q28. BA's risk penalty is linear and grade-independent, which cannot be right in expectation.**
Minus 10 points for average risk is applied identically to a 60 and to a 40. Since the WAR spacing
of the 20-80 scale is itself non-uniform (Q2) and bust rates fall steeply with grade (Part 7.7),
a constant additive penalty cannot represent a constant probability discount. BA calls the adjusted
grade an ordinal ranking device, which is consistent, but it means the adjusted grade must not be
read as an expected-value estimate.

**Q29. BA's role ladder omits half the scale.** B2 publishes role definitions for 80, 70, 60, 50,
45 and 40 only, yet B2's own worked examples use 55 ("55/Average", "55/High") and BA's measurement
tables use 65. So BA assigns grades it has not defined a role for. There is also no BA role
definition below 40, so BA's equivalent of an organizational player is undefined even though its
adjusted-grade arithmetic produces values as low as 20.

**Q30. BA's arm table is catchers-only and in the wrong unit for everyone else.** B1 supplies the
only published grade-to-measurement arm scale at any outlet, in catcher pop-time seconds. It
partially closes Q3, but there is still no published grade-to-mph arm scale for outfielders or
infielders anywhere across the three outlets, and pop time bundles footwork, transfer and
release with arm strength, so it is not a pure arm measurement even for catchers.

---

# Copy-gate conflicts with quoted source text

Recorded per the house rule: where a direct quote from a source contains a word on the
`copy_lint` ban list, the quote was kept accurate and the conflict is reported here rather than
the quote being silently altered. There is one exception, marked below, where the quote was
altered and the alteration was disclosed inline.

| Source | Quoted phrase | Banned term | Resolution |
|---|---|---|---|
| S3 (FanGraphs 2014) | "a combine-style showcase measure of straight-line speed" | showcase | Quote kept verbatim. It is the definitional sentence distinguishing the 60-yard-dash column from the home-to-first columns, so it could not be dropped without losing the distinction. |
| B1 (Baseball America) | "command and life are crucial elements as well" | crucial | Quote kept verbatim. It is the definitional caveat that a fastball grade is not a velocity grade. |
| B2 (Baseball America) | "Risk assessment, then, is crucial when comparing..." | crucial | ALTERED. Rendered as "is [essential]" with the substitution flagged in a parenthetical immediately after the quote, because this one is not a definitional term and the bracket convention makes the edit visible. The original word is "crucial". |
| L1 (FanGraphs 2026) | "The WAR estimates and the odds of a player being a star are more robust to changes in compensation structure" | robust | Quote kept verbatim and marked `[sic]` inline, since "robust" here is the author's own technical usage. |

Note on gate scope: `docs/reference/*.md` is not in `tools/strip_emdashes.py`'s `TARGETS` list, so
neither gate scans this path today and both pass trivially. The file was nonetheless written to
satisfy both rule sets independently: it contains zero em-dashes and zero en-dashes, and the only
ban-list hits are the four quoted phrases above. `copy_lint` treats ban-list hits as hard failures
only in `PURE_COPY` files (README.md, data/glossary.json, content/team.json,
assets/team/README.md), and advisory elsewhere, so even if this path were added to `TARGETS` the
four quotes would be advisory rather than blocking.

---

# Appendix: fetch log

All fetches performed 2026-07-30. Nothing 404'd, nothing was paywalled, nothing required a login.
The "Click Here To Become a Member" string appears mid-body in every FanGraphs article fetched; it
is an inline advertisement, not a paywall boundary, and full article text follows it in every case.

Summary: 27 of 29 URLs returned HTTP 200 on direct fetch. The 2 Baseball America URLs returned
HTTP 403 to both `curl` and WebFetch and were read in full from Internet Archive snapshots.

Succeeded on direct fetch (HTTP 200):

1. https://blogs.fangraphs.com/the-details-of-our-new-prospect-valuation-methodology/
2. https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/
3. https://blogs.fangraphs.com/scouting-explained-the-20-80-scouting-scale/
4. https://blogs.fangraphs.com/the-20-80-scouting-scale-translated-to-wins/
5. https://blogs.fangraphs.com/the-20-80-scale-sabr-style/
6. https://blogs.fangraphs.com/the-20-80-scale-saber-style-again-yet-different/
7. https://blogs.fangraphs.com/introducing-an-updated-method-for-prospect-valuation/
8. https://blogs.fangraphs.com/an-update-to-prospect-valuation/
9. https://blogs.fangraphs.com/putting-a-dollar-value-on-prospects-outside-the-top-100/
10. https://blogs.fangraphs.com/what-are-teams-paying-for-a-win-in-free-agency-2026-edition/
11. https://blogs.fangraphs.com/how-do-baseball-teams-discount-the-future/
12. https://blogs.fangraphs.com/how-do-prospect-grades-translate-to-future-outcomes/
13. https://blogs.fangraphs.com/prospect-week-primer/
14. https://blogs.fangraphs.com/how-to-use-the-board-a-tutorial/
15. https://blogs.fangraphs.com/valuing-prospects-the-pros-and-cons-of-a-single-number/
16. https://blogs.fangraphs.com/top-200-prospects-the-process-and-introduction/
17. https://blogs.fangraphs.com/scouting-the-hit-tool-pt-1/
18. https://blogs.fangraphs.com/scouting-the-hit-tool-pt-2/
19. https://blogs.fangraphs.com/scouting-the-hit-tool-pt-3/
20. https://blogs.fangraphs.com/scouting-the-hit-tool-pt-4/
21. https://blogs.fangraphs.com/scouting-the-hit-tool-pt-5/
22. https://blogs.fangraphs.com/scouting-the-hit-tool-pt-6/
23. https://blogs.fangraphs.com/valuing-the-2017-top-100-prospects/
24. https://blogs.fangraphs.com/updating-prospect-valuations/
25. https://blogs.fangraphs.com/saying-hello/
26. https://blogs.fangraphs.com/2026-top-100-prospects/ (reached via search result listing only, not parsed for tables)
27. https://www.mlb.com/glossary/miscellaneous/scouting-grades

Blocked on direct fetch, read in full via Internet Archive:

28. https://www.baseballamerica.com/stories/explaining-the-20-80-baseball-scouting-scale/
    - Direct fetch: HTTP 403. WebFetch: HTTP 403. Body is a Cloudflare managed-challenge
      interstitial ("Just a moment... Enable JavaScript and cookies to continue"), i.e. a bot
      block, not a paywall and not a 404.
    - Read via https://web.archive.org/web/20260720150852/https://www.baseballamerica.com/stories/explaining-the-20-80-baseball-scouting-scale/
      (snapshot 2026-07-20), HTTP 200, full article body including all five measurement tables.
29. https://www.baseballamerica.com/stories/explaining-baseball-americas-updated-mlb-prospect-grades-risk-system/
    - Direct fetch: HTTP 403, same Cloudflare interstitial.
    - Read via https://web.archive.org/web/20260304055525/https://www.baseballamerica.com/stories/explaining-baseball-americas-updated-mlb-prospect-grades-risk-system/
      (snapshot 2026-03-04), HTTP 200, full article body including the role ladder, the five-tier
      risk ladder, and the penalty table.

Failed outright: none. Both blocked URLs were recovered in full; nothing in this document is
reconstructed from memory or from search-result snippets.

Partial-read markers: none. Every article credited above was read as complete body text. The one
item read only as a search-result listing is item 26, the 2026 Top 100 list, which was not used
for any table or quote in this document.

Extraction method, for reproducibility: `curl` with a desktop browser user-agent to raw HTML, then
BeautifulSoup to walk the article body in document order, converting `<table>` elements to markdown
and preserving heading and paragraph order. BA's measurement scales are NOT HTML tables in the
source; they are pre-formatted text blocks with dot leaders, and were transcribed to markdown
tables by hand with no value changes. The WebFetch tool's summarizer declined to reproduce article
content verbatim on copyright grounds, which is why raw HTML was used throughout.

Linked from the sources but NOT read, and why:

- The off-site prior art in the valuation lineage (Victor Wang at Hardball Times, Scott
  McKinney at Royals Review, Kevin Creagh at Pirates Prospects, Steve DiMiceli at The Point
  of Pittsburgh, Jeff Zimmerman's 2016 Hardball Times Annual chapter, Driveline Baseball's
  2019 study, Sean Smith's Substack piece on the cost of free agents, Sky Andrecheck's Draft
  Pick WAR Calculator). These are not FanGraphs and were out of scope for this extraction.
  They are the upstream sources for the surplus-value method and would be the next read if
  the lab wants to test alternative team-control valuations.
- The Board itself (https://www.fangraphs.com/prospects/the-board and
  /prospects/farm-system-rankings). These are interactive data surfaces, not articles.
- Kiley McDaniel and Eric Longenhagen's book "Future Value", cited in L7 and L8 as holding
  the fullest version of the methodology. Not available online.
- Individual player pages, the 2026 Top 100 list body, and FanGraphs Weekly Mailbag entries.
  No framework tables in them.

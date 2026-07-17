# PLAYING TIME MODEL FRAMEWORK

# ROLE • OPPORTUNITY • POSITION MOBILITY • ORGANIZATIONAL INCENTIVES

## IMPORTANT

This model excludes injuries for now. Medical availability will be built later as a separate model.

This model estimates role-based playing time:

Projected PA =
Talent Claim
+ Roster Opportunity
+ Replacement Pressure
+ Defensive Utility
+ Position Lifecycle
+ Position Mobility
+ Prospect Pedigree
+ Contract / Service-Time Incentives
+ Organizational Behavior

Playing time is a resource-allocation problem, not a pure player-skill problem.

---

# CORE TARGETS

* PA
* Games
* Starts
* MLB roster days
* Opening Day roster probability
* Call-up probability
* Call-up timing
* Full-time role probability
* Platoon share
* Bench-role probability
* Demotion probability

---

# DATA PULL REQUIREMENTS

Pull from existing project/GitHub/prospect tracker infrastructure where available:
prospect grades, FV, tool grades, defensive/run/arm grades, position, defensive home,
org rank, top-100 status, MLBAM IDs, team/org, level, 40-man status, option status,
contract data, historical PA/G/starts, defensive metrics, position history.

Required ID checks: MLBAM ID, player name, season, organization, level, position.
Flag: duplicate players, missing IDs, mismatched orgs, stale grades, conflicting
positions, duplicate seasonal rows. No data source accepted unless it passes join
validation.

---

# MODEL STRATEGY RACE

* Model A — Conventional PA model (historical PA + talent + age + position + prospect status)
* Model B — Opportunity cost model (player value minus best alternative / position-group competition)
* Model C — Depth chart / discrete choice (team-position-date start probabilities)
* Model D — Hazard / survival (time to debut, call-up, demotion, role gain/loss)
* Model E — Competing risks (AAA / bench / platoon / regular / demotion / trade)
* Model F — Hierarchical organization model (org-specific promotion/veteran/platoon behavior)
* Model G — Portfolio allocation (PA as scarce team resource)

Every model tested against conventional baselines.

---

# CORE FEATURE FAMILIES

1. Talent / Role Claim — projected wRC+/WAR/off/def value, age, prior MLB, prospect status
2. Historical Usage — prior 1/2/3-yr PA, G, starts, roster days, service days (strongest baseline)
3. Replacement Pressure+ — competitor quality, depth-chart rank, viable alternatives
4. Defensive Floor+ — OAA/FRV/DRS/UZR/scouting grades; audit EVERY source separately;
   weight by out-of-sample value only
5. Defensive Flexibility+ — number of playable positions, premium-position ability, DH-only risk
6. Position Lifecycle+ — position-specific PA aging curves (catcher trust effect);
   C/SS/CF/2B/3B/LF-RF/1B/DH separately; scarcity + role-security multipliers
7. Position Mobility+ — transition matrix (3B→1B easy; 1B→3B hard; DH→SS very hard);
   future position distribution, transition cost, lineup pathway count
8. Prospect Pedigree+ — FV, top-100/50/10, draft position, bonus, org rank; candidate
   signals, not truth
9. Organizational Investment+ — pre-arb extensions, guaranteed dollars, acquisition cost
10. Transaction Cost+ — 40-man, options, Rule 5, waiver risk, arb status, walk year
11. Service-Time / Prospect Incentives+ — threshold proximity, Super Two, manipulation risk
12. Organizational Aggression+ — org promotion history, debut ages, option churn;
    hierarchical League → Org → Position → Player
13. Platoon Risk+ — handedness, projected splits, alternatives by hand, platoon share

---

# SCOUTING / GRADE EVALUATION FRAMEWORK

Audit every grade source (BA, Pipeline, FanGraphs, ESPN, internal) separately:
hit/power/run/field/arm/FV. For playing time prioritize field, arm, run, FV, position
projection, defensive home, org rank. Report reliability, incremental PA prediction,
position-retention/migration prediction, call-up prediction, role-security prediction.
Downweight/shrink/exclude poor sources. Build source weights from out-of-sample
performance only — never average blindly.

---

# TARGET DECOMPOSITION

PA = roster probability × active roster days × start probability × PA per start + bench PA

Separate targets: Opening Day roster prob, call-up prob/date, roster days, GS, G,
PA/start, bench PA, platoon share, full-time role prob.

---

# VALIDATION LADDER

A: historical PA only → B: + talent → C: + replacement pressure → D: + defensive
flexibility → E: + prospect pedigree → F: + contract/service/transaction cost →
G: + org effects → H: + position lifecycle/mobility.

Report ΔR², ΔRMSE, ΔMAE, calibration error, Brier, log loss, rank correlation.

---

# LEAKAGE AUDIT

No current-year PA predicting itself; no post-call-up performance in preseason
projections; no post-promotion rankings; no post-trade depth charts; no post-date
option/contract status; every feature timestamped; only information available at
prediction time.

---

# STRESS TESTING

Slice by: prospects/rookies/veterans, top-100 vs not, C, SS, DH-only, multi-position,
rebuilding vs contending, payroll tier, options vs out-of-options.
Report best/median/worst case + failure modes.

---

# CHAMPION / CHALLENGER

Champion = best conventional baseline. Challengers = models B–G. Promote only if
future PA prediction, role classification, and calibration improve with justified
complexity.

---

# OUTPUT FORMAT (per player)

Projected PA, 80% interval, roster prob, call-up prob, expected call-up date,
full-time role prob, platoon risk, role-security score, replacement-pressure score,
defensive-flexibility score, position-lifecycle adjustment, position-mobility score,
service-time risk, org-investment score, primary PA drivers, main uncertainty source.

---

# FINAL GOVERNING RULE

A feature ships only if it: improves future PA prediction, improves role
classification, survives leakage audit, survives stress testing, is timestamp-valid,
interpretable, reproducible, adds value beyond historical PA + talent, and justifies
its complexity. Every source earns inclusion through out-of-sample value.

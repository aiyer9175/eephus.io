# Defensive-metric source probe for the position-conversion lane

Lane A2 of `docs/master-plan-2026-07-30-nine-asks.md`. Run before scoping any conversion
work, because the owner named three inputs (arm strength, range/OAA, DRS) and only two of
them are obtainable from this machine.

## DRS: OUT OF SCOPE. Measured, not assumed.

Probed 2026-07-30 from this box, browser User-Agent, the modern JSON endpoint that
`defense-plus` recorded as working from Will's machine on 2026-06-16:

```
GET https://www.fangraphs.com/api/leaders/major-league/data
      ?stats=fld&type=8&season=2025&season1=2025&pos=all&lg=all&qual=0
UA: Mozilla/5.0 ... Chrome/126.0

-> HTTP 403 in 0.05s, 6,227 bytes of "Just a moment..." Cloudflare interstitial
```

The 403 arrives in 50ms with a challenge page, which is an edge block on the client, not
a rate limit or a bad query. This matches every prior FanGraphs result from this IP
(`pal_export.py` docstring; the pitcher-alchemy probe). A browser-UA header does not
defeat it. **Do not build a DRS ingest, and do not retry-loop the host.**

DRS is also proprietary to Sports Info Solutions, and Baseball-Reference's terms bar
scripted clients, so there is no second route from here.

### What satisfies the owner's ask instead

The ask was "DRS would be relevant for seeing which players project best to the infield"
and "check their OAA/DRS at specific positions they have played". Both halves are
already answerable from data on disk, without DRS:

| need | substrate on disk | shape |
|---|---|---|
| per-position defensive read, by season | `data/savant_oaa.json` (`savant_oaa.py`) | OAA **and FRP** per (player, position, season), 2016-2026, 13,001 rows, incl. directional splits |
| defensive runs history | `data/mlb_def_history.json` (`tools/build_def_history.py`) | bWAR `war_def` + `runs_position` per (player, season), 2000-2026, 17,016 rows |
| innings denominator for sample-size calibration | `data/fielding_innings.json` | league-wide StatsAPI fielding, 2000-2026 |

FRP (Fielding Run Prevention) is the Savant runs-denominated companion to OAA and is the
closest public analogue to DRS. Note the `defense-plus` reliability finding: **OAA and
FRP are redundant and must never both enter a model as separate indicators.**

Reliability priors to use as constants (measured, `defense-plus/reports/00_DATA_AND_RELIABILITY.md`):
OAA rho_true 0.60 with n0 = 269 innings (fast-stabilizing), DRS rho 0.76 with n0 = 527
(slower, stickier). Since DRS is unavailable, the conversion lane inherits OAA's faster,
noisier stabilization and must lean on the per-position `k_inn` shrinkage already fitted
in `data/positional_fit.json` `fit.signal` (CF 632 innings through 1B 2,539).

## Arm strength and sprint speed: IN SCOPE, not yet ingested

Neither exists anywhere in `prospect-tracker` (repo-wide grep finds only a `defense-plus`
probe script). Both are fetchable:

```
arm:    https://baseballsavant.mlb.com/leaderboard/arm-strength?type=player&year={Y}&minThrows=q&csv=true
sprint: https://baseballsavant.mlb.com/leaderboard/sprint_speed?year={Y}&min=10&csv=true
```

**Measured trap to carry into the ingest:** the parameter is `year`. Passing `season`
is accepted and silently ignored, returning the default year, so a loop written with
`season=` produces one year of data stamped as many. Clone the `savant_oaa.py` pattern
(1.05s throttle, `.cache/` CSVs, fail-soft, compact JSON output).

Arm strength is also the single most reliable defensive signal measured anywhere in this
codebase (year-over-year r .72 to .86, versus OAA's .32 to .57), which is why it is the
right instrument for the owner's specific rules about who can hold 3B or right field.

## Catchers stay out of the first cut

Savant's OAA leaderboard returns **zero catcher rows in every season** (verified in the
existing ingest). Framing and pop time are fetchable on separate endpoints but need their
own ingest and their own stabilization constants. The conversion lane ships non-catchers
first, as `positional_fit.py` already does.

## Prospect side has no tracking data at all

There is no public MiLB Statcast defense. A prospect conversion read can only ride: the
MiLB games-and-innings census by position, counting proxies (putouts, assists, errors,
double plays) that the StatsAPI fielding endpoint already returns but the current lean
schema discards, scout `tool_throw` grades (2017-2020 coverage only), and the
`prospect_def_value` migration matrix. Say so on the surface rather than implying a
measured range number exists for a prospect.

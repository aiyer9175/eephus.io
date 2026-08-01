# Trade board coverage: why Aaron Judge was missing

Opened by a user question: "Why isn't A.J. Minter showing up in the trade
calculator?" The answer for Minter turned out to be correct behaviour. The
answer for everyone else did not.

## The defect

The board population is assembled in `run_monthly.py` from three files:

```
tv_players = timeseries.json (active prospects)
           + debuts.json     (prospects we tracked who reached MLB)
           + graduates.json
```

**All three are prospect-derived.** A player is in them only if this platform
once tracked him as a prospect. An established veteran who was never in our
ranking coverage - debuted before it, arrived from NPB/KBO, or was simply never
ranked - never reached the trade board at all, however completely
`/projections/` modelled him.

Measured 2026-08-01, before the fix:

| | |
|---|---|
| projected vets | 1,319 |
| absent from the trade board | **325 (24.6%)** |
| ...of those, carrying a real contract | 158 |
| ...total 5y WAR absent from the board | 145.3 |

Absent included **Aaron Judge** ($24.6M surplus through 2031), Garrett Crochet,
Matt Chapman, Tyler Glasnow, Framber Valdez and Brandon Nimmo.

**Why no amount of work inside `apply_platform_surplus` could have fixed it:**
that function RE-PRICES records that already exist. It has no path to ADD one.
The population had to grow.

## The fix

`_append_projection_only_rows` seeds the board with priced vets the prospect
pool never contained. They are built on **exactly** the basis an MLB row already
on the board gets:

- value = `surNpv` (contract-surplus NPV), `surplus_source = "projection"`,
- eFV credible bands left null (a prospect-era band does not describe a
  contract-surplus NPV - the same deliberate null the existing branch uses),
- `board_entry = "projection_only"` so the row can say why it exists.

**No FV is invented.** The prospect Bayesian model is not run on them. Fabricating
a grade to get a player onto a board is the defect class this codebase has
removed twice already: the BA-statcast flat FV-40 and the `performance_ingest`
flat FV-35.

Result: 87 rows added, coverage **740 of 740 priced vets**, Judge on the board at
$24.6M / grade B.

## Why Minter is STILL not on the valued board, and why that is right

`surNpv` exists only when a contract has at least one salary-known season inside
the projection horizon (`FIRST_SEASON = 2027`, 5 seasons). 579 vets have none:

| reason | n | meaning |
|---|---|---|
| `expiring` | 218 | contract ends 2026, so there is no team-controlled season left to trade. A pending free agent is not a trade asset; the FA module prices him. |
| `no_contract` | 361 | nothing on file (pre-arb / optioned players Spotrac does not list), so there is no salary to subtract from projected value. |

**A.J. Minter is `expiring`** (NYM, RP, contract through 2026). His absence from a
board denominated in future control is correct.

But absence with no explanation is what sent someone into the source. So the
unpriceable vets now ship in `trade_values.json` under `unpriced`, with their
reason, and the Trade Machine search surfaces them as dimmed, inert rows reading
"contract ends 2026 - no controlled season to trade". They are deliberately kept
OUT of `players[]` so they never pollute a value ranking.

## OPEN, REGISTERED, NOT FIXED: the 361 pre-arb players

This is the larger remaining hole and it is a modelling decision, not plumbing.
Players with no contract on file are mostly **pre-arbitration**, which means they
have up to six controlled years at close to the league minimum - the single most
valuable asset class in a trade. We currently price them at nothing.

Pricing them requires deciding what salary to assume (league minimum, then an
arbitration ramp) and where service time comes from. That is a real model with a
real gate, not a default to be smuggled in beside a chart page. Until it exists
they are published as `no_contract` rather than silently dropped.

Jazz Chisholm Jr. appears in this group with 6.6 projected 5y WAR, which is a
good illustration of the size of what is being left on the table.

## What stops it recurring

1. `_projection_coverage` stamps `coverage` into `trade_values.json` every run:
   vets, priced vets, priced-on-board, missing, and the unpriceable split. **The
   number rides in the data**, not in a log line nobody reads.
2. `test_trade_board_coverage.py` fails when any priced vet is off the board, and
   separately pins that unpriceable vets are published with a reason and never
   leak into the valued rankings.
3. `test_calibration_vintage.py` now asserts the same player is worth the same on
   the trade board and `/projections/`, per player - not merely that the two
   share a calibration version.
4. The export logs a `COVERAGE` warning naming the top missing players.

## A third finding, fixed in passing

**Nothing in this repo writes `graduates.json`.** It is read by
`bayes_trade_value`, `efv_score` and `grpo_prospect`, and the loader guarded it
with `if exists()`, which makes a file that has never existed indistinguishable
from an empty one. It now logs a warning naming the absence. Same failure shape
as the FA parser that returned `[]` for a full day without anyone noticing.

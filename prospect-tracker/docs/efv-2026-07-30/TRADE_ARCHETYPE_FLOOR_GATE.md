# Gate: the trade machine's archetype floors, after the EV re-price

Pre-registered 2026-07-31, immediately after the v6 EV calibration shipped
(`SURPLUS_EV_OBJECTIVE.md`). Two findings, both surfaced by that change, neither caused
by it in the same way. Written before either is repaired so the repair cannot be scored
against a moving target.

## Finding 1: the projection anchor is announced and then overridden

`bayes_trade_value.py:3281-3284` applies the MLB projection surplus anchor:

```python
if _projection_anchor:
    posterior_surplus_mm = _proj_surplus_mm
    gross_floor_mm = max(gross_floor_mm, _proj_surplus_mm)
    inputs_available.append("mlb_projection_surplus_anchor")
```

`bayes_trade_value.py:3493-3495`, several hundred lines later, overrides it:

```python
if archetype_policy["posterior_floor_mm"] > posterior_surplus_mm:
    posterior_surplus_mm = archetype_policy["posterior_floor_mm"]
    inputs_available.append("archetype_posterior_floor")
```

The anchor flag is still on the record. So the output announces an anchor that did not
survive to the price. On the FV60 RF fixture in
`test_mlb_hitter_500_pa_projection_anchor_grounds_middling_bat`, anchoring at $35.0M and
not anchoring at all both yield **$51.6M** - the anchor changes nothing.

**This is PRE-EXISTING.** Verified by restoring the committed `value_framework_config.yaml`
and `prospx_current.yaml` and re-running: red at HEAD too. The EV re-price did not create
it, it only pushed the fixture's bound past the point where the test noticed.

### Measured blast radius (live board, 6,414 priced rows)

| | count |
|---|---|
| projection anchor applies | 276 |
| ...and archetype floor overrides it | **77** |
| trade value carried by those 77 rows | **$1,365M** |

Affected rows are established MLB arms and bats, not filler: Francisco Alvarez ($87.2M),
Yamamoto, Bryce Miller, Taj Bradley, Hunter Brown, Hunter Greene, Luzardo, Max Fried,
Ranger Suarez, Drew Rasmussen.

### Why it is NOT repaired in the EV change

The precedence is a judgement call, not a mechanical bug, and the two readings are both
defensible:

- **The floor should yield.** Its own docstring scopes it to *"do not let noisy early MLB
  evidence erase a group whose prior should remain informative."* The anchor gate requires
  `career_pa >= 500` (hitters), `>= 1000`, or `>= 300 IP`. That is the substantial-sample
  regime, the opposite of what the floor was written for. On its stated purpose the floor
  does not apply here at all.
- **The floor should win.** These are hand-set guardrails. Read as "this archetype does
  not trade below $X regardless of what the projection says this month", overriding a
  single-season projection is the intended behaviour, and the docstring is just narrower
  than the practice.

Repairing it moves 77 served rows and $1.37B of board value, so it needs an owner call
and its own before/after, not a silent tack-on to a pricing ship.

### Ship gate for the eventual repair

1. Pick ONE precedence and make the output honest about it. If the floor wins, the anchor
   must stop emitting `mlb_projection_surplus_anchor` when it was overridden; if the
   anchor wins, gate the floor on the anchor being absent. Either way, no record may
   carry a flag for an input that did not reach the price.
2. Report the full 77-row before/after, not a summary statistic.
3. `test_mlb_hitter_500_pa_projection_anchor_grounds_middling_bat` is `xfail(strict=True)`.
   It must flip to a plain pass (anchor wins) or be rewritten to assert the floor's
   precedence explicitly (floor wins). Deleting it is not an option.

## Finding 2: absolute archetype floors did NOT re-scale with the re-price

This one IS a direct consequence of the EV change and is recorded here rather than
repaired, for the same reason.

The archetype floors come in two kinds. `_floor_from_prior(name, pct)` is **relative**
(`prior_surplus_mm * pct`) and re-scaled automatically with the board. But
`bayes_trade_value.py:2398/2431/2456/2481` set **absolute dollar** floors - 65.0, 62.0,
58.0, 65.0 - and those did not move at all while the surplus board rose 74%.

Measured effect on where the floor binds:

| | v5 (median objective) | v6 (EV objective) |
|---|---|---|
| rows where `archetype_posterior_floor` binds | 427 | **378** |
| stopped binding (price rose past the floor) | | 56 |
| newly binds | | 7 |

Board totals for the trade machine: **$46,070M -> $54,497M (+18.3%)**, against +74.4% on
the raw surplus board. The gap is the damping from these absolute floors and from the
relative caps. 5,107 of 6,414 rows (79.6%) changed trade value; the median move is
+$0.7M, p90 +$2.9M, max +$21.6M, and a minority FALL (min -$3.9M) where a widened
relative cap stopped binding.

Nothing here is wrong in the sense of being incorrect arithmetic. But a guardrail
denominated in absolute dollars silently loosens every time the currency it guards is
re-scaled, and four of them just did. Whether they should be re-anchored (and to what)
is a calibration decision on the trade machine, which is a different model from the
surplus layer this change touched.

### Ship gate for the eventual repair

1. Decide whether these four floors are absolute-by-intent or were absolute-by-accident.
   If the latter, express them as `_floor_from_prior` percentages so they track the board.
2. Whichever way, the 378 currently-floored rows get a published before/after.
3. No change to the surplus layer. If a trade-machine recalibration needs the surplus map
   to move, that is the wrong fix.

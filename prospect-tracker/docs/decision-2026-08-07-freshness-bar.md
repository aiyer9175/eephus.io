# Decision 2026-08-07: what the registry reports about freshness

Status: DECIDED and implemented. One freshness concept, not three.

## The question that was re-opened

`model_registry.STALE_DAYS` was lowered from 240 to 90 on 2026-08-03 with the
reason written into the constant: at 240 the bar sat 4.5x above the oldest
artifact in the tree, so `stale` was structurally incapable of firing and the
freshness map reported "nothing is stale" as a tautology rather than a finding.

On 2026-08-07 the same complaint came back. At 90 the bar still fires on
nothing. The lane was asked to pick exactly one of three fixes and write down
why: lower the bar again, state freshness as a distribution instead of a
boolean, or make the undated artifacts the reported thing.

## What was measured first (2026-08-07, this tree)

| quantity | measured |
|---|---|
| registry rows | 217 |
| rows with an eval artifact that exists | 180 |
| distinct artifact files behind them | 170 |
| files carrying a production date of their own | 142 |
| files carrying NO date of their own | 28 |
| freshness rows aged by the artifact's own stamp | 147 |
| freshness rows aged by file mtime (the fallback) | 33 |
| oldest DATED artifact | 58 days |
| median artifact age | 15 days |
| 90th percentile artifact age | 36 days |
| rows `stale` at STALE_DAYS = 90 | 0 |

## The decision

**Option chosen: make the undated artifacts the thing that is reported.**

Implemented as `test_no_new_undated_eval_artifact` in `test_model_registry.py`,
a ratchet over the 28 paths measured above.

### Why not "lower the bar again"

Because the guard that exists forbids it, and the guard is right.
`test_stale_threshold_is_reachable` asserts `STALE_DAYS > oldest`, and the
oldest dated artifact today is 58 days. Any value that fires on something today
is therefore inadmissible, so "lower it until something trips" is not a move
that test permits. That is not an accident of the test: a bar tuned until it
alarms on a healthy tree is a false alarm, and a third re-tuning would be the
second time this program mistook a quiet instrument for a broken one.

`stale` fires on nothing because nothing is neglected. The median eval on this
platform is 15 days old and the 90th percentile is 36. The bar's VALUE is not
the defect and there is nothing to fix in it.

### Why not "state freshness as a distribution"

Because it is already stated as one, and adding a second place would be the
third concept this decision is supposed to prevent. `/models/` (shipped
2026-08-07, `build_site.build_models`) renders the whole distribution in its
Freshness block: how many rows name an artifact, how many of those files date
themselves, the oldest dated artifact, how many are past the bar, and how many
files do not date themselves at all. Duplicating that inside
`model_registry.freshness()` would give the platform two freshness summaries
that can disagree.

### Why the undated artifacts are the real finding

They are the one part of the freshness story that is a DEFECT rather than a
policy dial, and the only part somebody can fix.

`freshness()` falls back to the file mtime when an artifact declares no date.
The deploy box runs `git checkout -- .` every night, which rewrites every
tracked mtime to the moment of checkout. So on the machine that actually serves
the site, those 33 rows report an age of roughly zero regardless of when the
measurement was really taken, and they report it exactly where a stale eval
would matter most. A boolean that reads "not stale" off a checkout timestamp is
worse than no reading at all, because it looks like evidence.

That failure mode is invisible today: the map returns `age_source: "mtime"` and
nothing was enforcing how many rows were allowed to sit on that branch.
`test_freshness_prefers_the_artifacts_own_stamp_over_mtime` only required that
stamped rows outnumber mtime rows, which passes at 147 vs 33 and would still
pass at 91 vs 89.

## What was implemented

- `test_model_registry.UNDATED_EVAL_ARTIFACTS`: the 28 paths, frozen.
- `test_model_registry.test_no_new_undated_eval_artifact`: any registry
  eval_artifact that exists and declares no top-level date, and is not already
  in the frozen set, fails the suite and is named in the message. The message
  says to stamp the artifact, not to extend the set.
- `test_stale_threshold_is_reachable`: docstring rewritten to record this
  decision, so the next session does not spend a fourth pass lowering a bar
  that its own first clause forbids lowering.

The set is monotone decreasing by design. Stamping an artifact makes the set
shrink and the test stays green; the pinned line should then be deleted.

## Follow-ups this decision deliberately did not take

1. `/models/` COUNTS the undated files but does not NAME them. Naming them is a
   small change in `build_site.build_models` (the `fresh_bits` block), owned by
   another lane this program.
2. Twenty-five of the 28 are `data/*.json` written by generators in this repo.
   Each is a one-key fix at the point of write (`generated_at`). None was taken
   here because those generators are other lanes' files and running them is
   forbidden mid-program.
3. `docs/efv-2026-07-30/EFV_LANE_GATES.md` can never be dated by
   `_artifact_date`, which parses JSON only. It is pinned as undated rather
   than special-cased, because a markdown gate record used as an eval artifact
   is a separate question from freshness.

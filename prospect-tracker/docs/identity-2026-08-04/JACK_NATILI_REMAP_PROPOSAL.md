# jack_natili / jackson_natili: a key-remap PROPOSAL. Not executed.

Owner decision requested 2026-08-04. This document proposes; it writes nothing.
The identity-repair path used on the other four collisions NEVER renames a key,
by design, so this case sits outside what that tooling is authorised to do.

## They are the same human, and the evidence is not circumstantial

| field | `jack_natili` | `jackson_natili` |
|---|---|---|
| birth_date | 2005-03-10 | 2005-03-10 |
| position | C | C |
| org | COL | COL |
| age | 21.4 | 21.4 |
| transaction | "Colorado Rockies signed C Jack Natili", 2026-07-20 | same row, same date |
| draft | 2026, round_label 3, pick_overall 76 | 2026, round_label 3, pick_overall 76 |
| school | Cincinnati | Cincinnati (OH) |

Same birth date, same club, same position, same draft pick number, same signing
transaction. This is one player, entered twice under a short-form and a
long-form of his first name.

## This one IS user-visible, unlike the other four

The other four collisions were two humans fused onto one key. This is the
inverse, and it reaches the published board: he occupies TWO ROWS at TWO RANKS
with TWO DIFFERENT GRADES.

| field | `jack_natili` | `jackson_natili` |
|---|---|---|
| overall_rank | **320** | **154** |
| fv_label / fv_raw | 42 / 41.7 | 45 / 45.0 |
| xfv_grade | 44.3 | 47.6 |
| consensus_live_rank | 315 | 173 |
| dollar_dvm_plus | 95.5 | 93.7 |

Both rows carry independent consensus scores, so two source rows are feeding
them separately and each is being graded on its own partial evidence. Whichever
key survives, the merged player's grade should be RE-DERIVED from the union of
sources, not inherited from either row, because both are currently scored on a
fraction of what is known about him.

## Which key is canonical: `jackson_natili`

The deciding fact is in `data/player_links.json`:

    byKey.jackson_natili: {"mlbam": 814385, "name": "Jackson Natili", ...}
    byKey.jack_natili:    {"mlbam": null,   "name": "Jack Natili",    ...}

`jackson_natili` carries the resolved MLBAM id. `jack_natili` has `mlbam: null`
and therefore cannot join to StatsAPI, Savant, or anything else keyed on MLBAM.
Keeping the un-resolvable key as canonical would mean deliberately choosing the
row that cannot be joined to any external source.

## What `jack_natili` holds that must NOT be lost

The canonical key is not the complete one, which is exactly why this is a merge
and not a delete:

  * `bonus_usd`: **1097500** on `jack_natili`, **null** on `jackson_natili`.
    This is real signing money and it exists on the losing key only.
  * `current_level`: **CPX** on `jack_natili`, **null** on `jackson_natili`.
  * `team_name`: "COL" vs "Colorado Rockies"; `school`: "Cincinnati" vs
    "Cincinnati (OH)". Cosmetic, but pick the normalised form deliberately.

One field is outright WRONG on `jack_natili` and should not be carried over:
`acquisition.pick_round` is **1**, which contradicts its own `round_label` "3"
and `pick_overall` 76. `jackson_natili` has `pick_round` 3, which is consistent.
Take the pick fields from `jackson_natili`.

## Artifact footprint: 17 files, and the split is not clean

    artifact                            jack_natili   jackson_natili
    grpo_scores.json                        13              7
    player_links.json                        3              5
    _gn_lab/consensus_modes.json             2              2
    xfv.json                                 1              1
    xfv_backgrade.json                       1              1
    xfv_live_hitter_matrix.json              1              1
    trade_values.json                        1              1
    xfv_proxy_eval.json                      1              1
    rosters_by_org.json                      1              0
    grpo_public.json                         0              1
    mlb_projections.json                     0              1
    scout_reports.json / _1.json             0              1 each
    xfv_history.json                         0              1
    timeseries.json                          1              1

Note `grpo_scores.json` carries 13 references to the losing key against 7 to the
canonical one, so a naive delete would destroy the majority of his GRPO history.

## Proposed sequence, if approved

1. Back up the DB, as the 2026-08-04 repair pass did.
2. Merge FIELD-WISE onto `jackson_natili`, taking `bonus_usd` and
   `current_level` from `jack_natili` and the pick fields from
   `jackson_natili`. Value-guarded writes only, idempotent, so a re-run is a
   no-op.
3. Repoint `jack_natili` references in the DB to `jackson_natili`, including
   the GRPO history where the losing key holds the larger share.
4. Add `jack_natili` to the slug-alias table so any future source using the
   short form resolves to the canonical key instead of re-creating the split.
   WITHOUT THIS STEP THE SPLIT REGENERATES on the next ingest that spells him
   "Jack", which is how the transaction feed spells him.
5. Rebuild: `run_monthly --rebuild-only`, then regenerate `identity_audit`, then
   proj_export and trade_values in that order (test_calibration_vintage requires
   they agree).
6. Expect the board to lose one row and the surviving row's rank to move: he is
   currently 154 and 320, and the merged row should land on a grade re-derived
   from the union of both source sets, not on either existing grade.
7. Remove the `jack_natili` allowlist entry; `critical_active_player_keys`
   should go empty.

## The risk, stated plainly

A key remap is the one identity operation that CANNOT be cleanly undone by
re-running the repair, which is why the 2026-08-04 tooling refuses to do it. The
DB backup is the rollback, not the tool. Step 4 is the step most likely to be
skipped and is the one that determines whether the split comes back next month.

## Recommendation

Approve, but as its own pass, not bundled with the dpw re-anchor. Both rewrite
the board, and running them together would make it impossible to attribute a
rank change to one or the other.

# Consensus-side patch (lane `anchor`, NOT applied)

`consensus.py` is owned by a concurrent workflow. This is the exact patch to apply
there, plus one escalation option that is deliberately NOT written as a patch
because it changes served numbers and needs the full gate.

## The defect

`storage.upsert_unranked_active_player` claims, in a code comment:

> This never displaces a real FV from a scouting source because
> `source='performance_ingest'` is excluded from the consensus weights.

**That is false.** `consensus.load_source_weights()` reads `data/source_weights.json`,
whose `weights` object is `{}` (reverted to equal on 2026-07-25). Sources absent from
that file vote at 1.0. `performance_ingest` is absent, so it votes at 1.0 like
FanGraphs.

Measured on the live DB / `data/xfv.json`, 2026-07-25:

| quantity | value |
|---|---|
| active board players | 4,477 |
| whose only explicit-FV source is `performance_ingest` | **2,575** |
| of those, serving `consensus_fv` == 35.0 exactly | 2,575 |
| active players pinned at the served eFV floor (q = 35.0) | 2,879 |
| floor players whose anchor is the synthetic constant | 2,214 (77%) |

The number is not a weak grade. It is a constant, identical for every player it
touches, and it is indistinguishable downstream from a real single-source grade:

* `compute_consensus_point` puts `35.0` into `explicit_fvs`, so `avg_fv_n = 1` and
  `sources_contributing = ["performance_ingest"]`.
* The single-instance shrinkage then pulls toward `SINGLE_SOURCE_PRIOR = 35`, which
  is a **no-op on 35.0**. So `consensus_fv_raw = 35.00` is 100% the constant, with
  zero information content, and nothing on the point says so.
* `efv_dataset` reads `n_sources = 1.0` for these players: the model is told one
  outlet graded them.

## Patch 1 (recommended, output-neutral): flag the point

Adds a boolean to `ConsensusPoint`. **No numeric field changes**, so no served grade
moves and no eFV re-gate is required. It makes the placeholder legible to every
consumer (site copy, eFV feature builders, the identity audit) instead of leaving
them to re-derive it from the source list.

```python
# --- consensus.py, near _SOURCE_WEIGHTS (line ~453) ---------------------------

# Sources whose "grade" carries no published information: a single constant
# stamped on every player they touch. `performance_ingest` hands out FV 35.0
# flat (storage.upsert_unranked_active_player); `auto_detect` is a debut/roster
# tracker. Mirrors grade_normalization._SYNTHETIC_SOURCES, MINUS draft_signing:
# that source is flagged synthetic only so the quantile map passes its scale
# through raw -- its VALUE is a real published draft-board FV.
CONSTANT_ANCHOR_SOURCES = frozenset({"performance_ingest", "auto_detect"})
```

```python
# --- consensus.py, ConsensusPoint dataclass (after `consensus_fv_plus`) -------

    # True when EVERY source contributing an explicit FV to this point is a
    # constant-anchor source, i.e. the consensus number is a placeholder
    # (FV 35.0 for all 2,575 such active players on 2026-07-25) and not a
    # scouting opinion. Consumers must not read it as "one outlet graded him".
    synthetic_anchor: bool = False
```

```python
# --- consensus.py, compute_consensus_point return (line ~746) -----------------

        consensus_fv_plus=consensus_fv_plus,
+       synthetic_anchor=bool(contributing_sources)
+                        and contributing_sources <= CONSTANT_ANCHOR_SOURCES,
        org=_pit_org(day_snaps, event_date),
```

`build_timeseries` should propagate the flag onto the serialized point the same way
it propagates `consensus_fv_plus`.

## Patch 2 (escalation, NOT written as a diff): stop the constant voting

The information-correct treatment is that a constant is not a vote: exclude
`performance_ingest` from `explicit_fvs` and let these players fall through to the
`rank_implied_fv` path, or carry no consensus FV at all.

**Do not apply this without the full gate.** Measured blast radius:

* `compute_consensus_point` returns `None` when `not explicit_fvs and not
  rank_implied_fvs`. `performance_ingest` rows are written with `rank = NULL`, so
  there is no rank fallback: all **2,575** players would lose their ConsensusPoint,
  drop out of `timeseries.json`, and disappear from the board entirely.
* It also changes `n_sources` (1.0 -> 0.0) and `consensus_fv_raw` for those rows,
  both of which are live eFV model inputs. Against
  `docs/EFV_GATE_STANDARD.md` this needs the paired bootstrap, the row-permuted
  zero-information control, the permutation null band, and >= 4 time splits, on a
  cohort that is 58.6% of the active board.

This is a product decision (does an ungraded auto-tracked player belong on the
board at all?) before it is a modelling one, so it is escalated rather than patched.

## Related fix already applied in this lane's own files

`storage.upsert_unranked_active_player`'s comment asserting the exclusion is false
and has been corrected in place, alongside the frozen-date fix.

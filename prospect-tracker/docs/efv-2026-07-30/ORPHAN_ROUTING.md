# The seven orphans: where they go, and why the seam did not need a new rule

Lane: LANE-ORPHAN. Owner decision 2026-07-30: **route them to the provisional / ungraded
path (`efv_ungraded.py`). Do NOT re-invent a consensus FV for them. Fix at the seam so this
is a general rule, not seven special cases.**

Predecessor: `docs/efv-2026-07-30/POSITION_ROLE_GATE.md` 3.2, which removed
`baseballamerica_statcast_by_age`'s fabricated FV 40 and found, unpredicted by the audit,
that seven players leave the board because that snapshot was their ONLY row in the
database: `braylon_whitaker`, `easton_shelton`, `jacob_friend`, `jake_cunningham`,
`jose_meza`, `mason_guerra`, `michael_martinez` (ranks 373 / 458 / 473 / 483 / 638 / 759 /
1,383, none inside the top 300).

---

## 1. WHY they fall off, traced to the predicate

Board membership is not gated on a non-null consensus FV, and it is not gated on snapshot
existence. It is gated on **a consensus POINT existing**, and the chain is four links:

1. `consensus.compute_consensus_point` returns `None` unless the player has at least one
   explicit FV or at least one non-org-list rank (`consensus.py:641`,
   `if not explicit_fvs and not rank_implied_fvs: return None`). Tool grades contribute to
   `contributing_sources` but are NOT sufficient, and all seven carry `tools_json` NULL
   anyway.
2. `consensus.build_timeseries` drops the `None` but STILL EMITS the player, with
   `points=[]` and `fv_high/low/open/close = 0.0` (`consensus.py:1202-1242`). Consensus
   does not delete anybody.
3. `storage.export_timeseries_json:10016` is the actual board gate:
   `if not p.points: inactives.append(p); continue`. It fires before every other active
   gate (MLB-30 org, `MIN_PROSPECT_FV`, the age cap, the stale gates).
4. Downstream, `efv_dataset.build_live_matrix:911` and `efv_score.run_live:1594` both
   independently require `consensus_fv_raw`, so even a player who survived step 3 would
   carry no eFV row.

So: **no scout grade -> no consensus point -> off the flagship board.** That is correct
behaviour and not a bug. What made the seven surprising is that a fabricated grade had been
holding them on the graded side of a line they never belonged on.

## 2. The provisional path already covers exactly this case

`efv_ungraded.build` enumerates `data/rosters_by_org.json`, skips `level == "MLB"`, and its
entry predicate is one line, now named `efv_ungraded.flagship_owns`:

    if flagship_owns(p): continue          # fv_raw is not None -> flagship owns it

`fv_raw` on a roster row is stamped by `run_monthly.py:2008-2018` from the timeseries:
`latest.consensus_fv_raw if latest else None`. **It is None exactly when the player has no
consensus point.** So `flagship_owns` and `compute_consensus_point` are complements, and
every rostered non-MLB player with usable MiLB production lands in exactly one pool:

| | consensus point | `fv_raw` | pool |
|---|---|---|---|
| has a scout grade or a rank | yes | set | flagship eFV board |
| has neither | no | None | provisional (`xfv_ungraded.json`, 3,404 rows today) |

There is no third state and no gap. The rule is general, it predates this decision, and it
serves 3,404 players.

**THE SEAM THEREFORE NEEDED NO BEHAVIOUR CHANGE.** What it needed was a name and a test,
because a rule that only exists as an inline `continue` with a six-word comment is a rule
that can be broken by accident. `efv_ungraded.flagship_owns` is that name; the partition,
its provenance and the orphan story are in its docstring; and
`test_ungraded_orphan_routing.py` pins BOTH halves (an identity-only snapshot produces no
consensus point; a row with no `fv_raw` is a provisional candidate) so a future change that
makes a player fail both predicates fails a test instead of silently deleting them.

Two notes on the predicate that the test also pins:

* `fv_raw is not None`, never truthiness. A legitimate grade of 0.0 is a grade.
* The seven are picked up on the SAME production run that drops them, not the next one:
  `rosters_by_org.json` is rebuilt at `run_monthly.py:2039` from the timeseries built at
  `:1723`, and `efv_ungraded.build` runs later inside `efv_export.regen_all`.

## 3. Verified: all seven land in provisional, with grades

Replayed `efv_ungraded.build`'s per-player body for the seven with `fv_raw` treated as None,
using the module's own `fit_nofv`, `_milb_features`, `_vec`, `_war`, `_grade` and
`_display_statline`. **7 of 7 are present in `rosters_by_org.json`, 7 of 7 clear the
production gate (`_milb_features` returns a `k_rel`), 0 of 7 are dropped as
`no_production`, and 0 of 7 trip the `_SUBFLOOR_GRADE` cameo cap.**

| player | org | level | pos | age | PA (primary level) | provisional WAR | **provisional grade** | flagship grade it replaces | p_bust (thin-sample) |
|---|---|---|---|---|---|---|---|---|---|
| `easton_shelton` | LAD | A | 1B | 20.9 | 398 | 3.505 | **40.3** | 40.8 | 0.823 |
| `braylon_whitaker` | BAL | A | OF | 20.4 | 330 | 2.161 | **35.2** | 35.0 | 0.908 |
| `jacob_friend` | CIN | A+ | C | 23.4 | 186 | 2.144 | **35.1** | 43.5 | 0.862 |
| `michael_martinez` | ATL | A | OF | 19.5 | 140 | 2.099 | **35.0** | 40.6 | 0.911 |
| `jake_cunningham` | SDP | AA | OF | 24.1 | 119 | 1.715 | **33.5** | 41.2 | 0.903 |
| `mason_guerra` | ATL | A+ | 1B | 23.9 | 283 | -0.200 | **26.2** | 37.5 | 0.959 |
| `jose_meza` | LAD | A+ | OF | 23.3 | 339 | -1.464 | **21.4** | 21.6 | 0.980 |

Against the current 3,404-row provisional pool (grades 20.0 / 25.7 / 46.6 at min / median /
max), four of the seven land in the top 3% and `easton_shelton` at the 99.8th percentile.
They are not org filler and the provisional path prices them accordingly.

## 4. What they lose, stated plainly

Provisional rows are first-class on the CLIENT board (`prospx` fetches
`/data/xfv_ungraded.json`, `_buildProvPlayers` synthesizes player objects, and
`getFilteredActives` concatenates them into the same pool that `buildEfvRankMap` ranks), and
they enter the farm rank-and-tier pool server side (`storage._load_ungraded_by_org`). They
do NOT get a server-baked `overall_rank`, `metric_snapshots` rank history, a per-source
snapshot panel, spotlights, movement, or DvM+ / surplus accumulation.

That is a demotion, not a deletion, and it is the correct one: those surfaces all describe
what the industry said about a player, and nobody ever said anything about these seven.

## 5. The finding that is worth more than the seven players

`jacob_friend` drops 43.5 -> 35.1, and the owner's brief flagged him as the one worth a
second look. The drop is real, and **it is NOT caused by losing the fabricated grade.** It
has two separable causes, and only the second is a defect.

**(a) A different model, legitimately.** The flagship ridge carries `fv` as a feature
(`efv_model._feature_spec`: 14 hitter features, one of them the consensus grade), so the
seven were scored with the fabricated 38.33 as a model input AND as the `rank_war` blend
anchor. The provisional path uses `fit_nofv`, a production-only ridge with no FV feature,
and substitutes `_GRADE_MAP[side]["BASE"]`. Predicted WAR moves in both directions
(`jacob_friend` 1.67 -> 2.14 UP, `mason_guerra` 0.88 -> -0.20 DOWN). That is what removing a
fabricated input is supposed to look like.

**(b) A different GRADE MAP, which is a defect nobody registered.** LANE-P2 re-pointed the
flagship grade onto `vf.outcome_implied_fv` on 2026-07-30. It did NOT re-point
`efv_ungraded._grade`, which is still a bespoke linear map (`27.0 + 3.8*war` for hitters,
soft-ceilinged at KNEE 43 / CEIL 49). At the SAME predicted WAR the two now disagree badly:

| predicted WAR | `vf.outcome_implied_fv` (flagship) | `efv_ungraded._grade` (provisional) | gap |
|---|---|---|---|
| -1.46 | 20.0 | 21.4 | +1.4 |
| -0.20 | 20.0 | 26.2 | +6.2 |
| 1.67 | 44.0 | 33.3 | **-10.7** |
| 2.14 | 44.8 | 35.1 | **-9.7** |
| 3.51 | 47.6 | 40.3 | **-7.3** |

The provisional map is more generous below roughly 0.4 WAR and about ten FV stingier
through the 1.5 to 3.5 band where real prospects live. So routing a player to provisional
today costs them close to ten grade points of pure map difference, on top of any honest
model difference. That is the same "two maps in one product" shape the odds-basis gate was
written to adjudicate, and it has not been measured on this side.

**GATED, NOT FIXED.** Re-pointing `efv_ungraded._grade` would move all 3,404 served
provisional grades at once, it interacts with the deliberately restored 2026-07-25
provisional cap (owner call, `docs/EFV_FRONTIER_AUDIT.md` follow-up) whose whole argument is
that an ungraded low-minors bat must NOT reach a graded-path asymptote, and the module's own
OOS harness scores `_war()` rather than `_grade()` so it cannot adjudicate a map change at
all. It is out of scope for a routing decision and it needs its own pre-registered gate.
Recorded here as the highest-value follow-up this lane found.

## 6. What shipped

`efv_ungraded.flagship_owns` (a named predicate and a docstring, exact no-op),
`test_ungraded_orphan_routing.py`, and this document. No production behaviour changed, and
nothing had to: the seven route to provisional on the next production ingest because the
partition already works. `POSITION_ROLE_GATE.md` 3.5 follow-up 7 is closed by this.

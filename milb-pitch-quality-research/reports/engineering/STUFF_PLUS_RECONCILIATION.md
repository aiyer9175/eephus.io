# Stuff+ Reconciliation

Phase 2 — the largest remaining architectural question, per this charter's own framing. Resolved here with a definitive recommendation, grounded in a precise (not approximate) feature-level comparison verified directly against `prospect-tracker/stuff_plus_aaa.py`'s source and `data/stuff_plus_aaa_eval.json`'s real numbers.

## Do they estimate the same construct?

**No.** `stuff_plus_aaa` is a supervised model: LightGBM regressed against `delta_run_exp` (a per-pitch run-value label), producing a single scaled score (100+10z) meant to answer "how much run value does this pitcher's stuff generate." Module 1 (Physical Stuff) has **no label, no model, no target** — it is a direct descriptive measurement of physical traits (velocity/movement/spin averages), answering a categorically different question: "what are this pitcher's physical characteristics." Module 1 sits **upstream** of what `stuff_plus_aaa` does; it is not a competing answer to the same question.

## Which features overlap?

Verified directly against `stuff_plus_aaa.py`'s documented feature list (`release_speed, spin, extension, pfx_x, pfx_z, release_pos_x, release_pos_z, arm_angle, velo_delta_vs_primary`) and Module 1's data pipeline (`scripts/phase1b/build_pitch_dataset.py`, `scripts/phase1c/build_pitch_dataset_v2.py`):

| Field concept | `stuff_plus_aaa` field | Module 1 field | Overlap status |
|---|---|---|---|
| Velocity | `release_speed` | `start_speed` | **Overlaps**, reliability-tested (r=0.98-0.99) |
| Horizontal/vertical movement | `pfx_x`, `pfx_z` | `pfx_x`, `pfx_z` | **Overlaps**, reliability-tested (r=0.91-0.98) |
| Spin rate | `spin` | `spin_rate` | **Overlaps**, reliability-tested (r=0.98) |
| Extension | `extension` | `extension` | **Overlaps in presence, not in evidence** — captured by Module 1's pipeline but never reliability-tested (confirmed by grep against `RELIABILITY_STATS.json`: no match) |
| Release position | `release_pos_x`, `release_pos_z` | `release_x0`/`release_z0` (from `x0`/`y0`/`z0`) | **Overlaps in presence, not in evidence** — same caveat as extension |
| Arm angle | `arm_angle` | *(none)* | **No overlap — genuinely uncomputable.** Confirmed: the MLB Stats API live-feed (Module 1's data source) has no `arm_angle`-equivalent field anywhere in `pitchData`; this is exclusive to Baseball Savant's `statcast-search-minors` endpoint. |
| Velocity separation | `velo_delta_vs_primary` | *(none, but derivable)* | **No overlap today** — neither system currently computes this; Module 1 + Module 2 (Arsenal) combined have the raw ingredients (per-pitch-type velocity) to derive it, but it isn't implemented. |

## Which outputs overlap?

**None, directly.** `stuff_plus_aaa` outputs one composite score per pitcher-season. Module 1 outputs multiple raw trait averages, by design (a universal composite was rejected architecturally, `reports/phase1c/ARCHITECTURE_COMPARISON.md`). The overlap is entirely in *input* space, not *output* space — there is no risk of two conflicting numbers being shown for "the same thing" on a player page, because Module 1 doesn't produce a thing of the same shape.

## Which consumers overlap?

`stuff_plus_aaa` has one confirmed live consumer: PROSPX pitcher cards (`CURRENT_ECOSYSTEM_MAP.md`). Module 1 has zero confirmed consumers (`reports/architecture/CONSUMER_AUDIT.md`). No overlap exists today because Module 1 isn't wired anywhere yet.

## Which validation targets overlap?

**None.** `stuff_plus_aaa` validates against `delta_run_exp` (pitch-level) and, at the forward-gate stage, MLB ERA/K% for graduates (`stuff_plus_aaa_eval.json`: pitcher-level season-out r=0.28, forward r=0.047 vs. ERA⁻¹, r=0.505 vs. K%). Module 1 has no predictive-validity target at all — its evidence is reliability (split-half/month-to-month consistency), a fundamentally different kind of claim ("this measurement is stable," not "this measurement predicts an outcome").

## The evidence that actually resolves A-E

**The reliability contrast is the deciding evidence**: Module 1's raw physical-trait measurements (r=0.91-0.99) are dramatically more stable than `stuff_plus_aaa`'s derived run-value score built from similar inputs (pitcher-level r=0.28). This is exactly what should be expected — averaging raw physical measurements is inherently less noisy than regressing them against a noisy per-pitch outcome — but it means Module 1's outputs are a plausible, evidence-supported **feature-quality upgrade** for `stuff_plus_aaa`'s own model, not a competing end-user score.

## Verdict: **(E) Hybrid, precisely defined — not (C) alone, not left vague**

- **Where `stuff_plus_aaa` already operates (AAA)**: **(C) Module 1 augments Stuff+.** Concretely, Module 1's velocity/movement/spin averages are candidate replacement or supplementary features for `stuff_plus_aaa`'s LightGBM input layer, motivated directly by the reliability contrast above. This is an implementation experiment (does swapping in Module 1's more-reliable features improve `stuff_plus_aaa`'s pitcher-level stability or forward-gate performance?), not something this charter can claim already works.
- **Where `stuff_plus_aaa` does not operate (tracked Low-A)**: **independent extension**, not augmentation — there is nothing to augment, since `stuff_plus_aaa` is AAA-only by design. Module 1 stands alone here.
- **(A) is rejected**: the two systems don't estimate the same construct (no label vs. a real supervised target); collapsing them would erase `stuff_plus_aaa`'s own validation lineage for no evidentiary gain.
- **(B) is rejected**: `stuff_plus_aaa` has a live consumer and real (if weak) forward-validation evidence; Module 1 has neither. Replacing it is unsupported by any evidence produced across four charters of research.
- **(D), as "nothing should ever connect them," is rejected** — the reliability contrast is too suggestive of real value to leave unexplored — but **(D) in the narrower sense of "do not modify `stuff_plus_aaa`'s code during this charter" is correctly binding**, per the standing governance rule (no production systems modified during this charter, inherited from the original Phase I charter).

## The concrete blocker to implementing this verdict

**The two systems use different public data endpoints** (`DEPENDENCY_GRAPH.md`, prior charter) — `stuff_plus_aaa` reads Baseball Savant's `statcast-search-minors`; Module 1 reads the MLB Stats API live-feed. Before any augmentation experiment can run, one of two things must happen: (a) Module 1's pipeline is extended or replaced to pull from Savant's minors search (gaining `arm_angle`, losing nothing essential since the overlapping fields are present on both), or (b) a per-pitch join/reconciliation layer is built between the two sources. **This is a real, named engineering blocker, not a documentation gap** — it directly affects `MODULE1_READINESS.md`'s readiness verdict.

## Observed evidence / Inference / Speculation

The feature-overlap table and reliability numbers are Observed evidence, each independently verifiable against the cited file. The verdict (hybrid, precisely bounded by AAA/Low-A) is Inference built on that evidence. Whether the augmentation experiment would actually improve `stuff_plus_aaa`'s performance is explicitly Speculation — plausible, motivated, and not yet tested.

## Future work

The augmentation experiment itself (feed Module 1's features into `stuff_plus_aaa`'s LightGBM training, measure the stability/forward-gate delta) is the single most concrete, valuable next research step this entire four-charter research program has surfaced — named here, not attempted, since it requires touching `stuff_plus_aaa`'s actual training code, which is out of this charter's scope.

# Lane E3 closure: RP to SP is sign-wrong, not underpowered

Written 2026-08-06. No new run was performed. Everything below cites artifacts
already on disk, chiefly `data/pal_gamelog_eval.json` (generated 2026-07-15) and
`.cache/pal_xrv/w3_detail.json`.

## The finding

The master plan's premise for this lane was that "the binding constraint is n,
not features", and the instruction was to expand the closed-event set and
re-gate. **That expansion has already been run, and the premise is wrong.**

From `data/pal_gamelog_eval.json`, `verdicts.lane_a.rp_sp_stays_sign_wrong`:

| set | n | Spearman rho | passes gate |
|---|---|---|---|
| legacy | 25 | -0.2062 | no |
| expanded | 35 | -0.1736 | no, and no under v2 |

The gate requires the model's rank correlation with `war_delta` to beat the best
baseline, with the gap's lower 95% bound above -0.01. The observed correlation is
**negative**. The fit ranks RP-to-SP candidates in close to the opposite of the
order their outcomes take.

## Why more data cannot fix it

A sample-size argument applies to an effect that is real but not yet resolvable.
This effect is resolvable and points the wrong way.

Bootstrap spread on Spearman rho at this size is approximately
`sd(n) = 1.106 / sqrt(n)`, so the gate's minimum detectable effect is about
**+0.356 at n = 35** and about **+0.207 at n = 100**. The observed gap against
the best baseline is **-0.198**. No n closes a gap that is on the wrong side of
zero; collecting more events makes the failure more certain, not less.

The arrival rate settles it as a practical matter too. The expansion recovered 89
conversion events in total, of which the RP-to-SP gate set gained **10** (25 to
35), not the roughly 100 that decision #8 assumed. That estimate was reading the
SP-to-RP figure. At the observed rate of about 5.8 new RP-to-SP gate rows per
season, n = 100 arrives around **2037**.

## What the same expansion did prove

`verdicts.lane_a.sp_rp_pass_strengthens`, the other direction, **passed and got
stronger**:

| set | n | rho | gap lo95 | passes |
|---|---|---|---|---|
| legacy | 61 | 0.2916 | +0.0745 | yes |
| expanded | 100 | 0.3607 | +0.4647 | yes, under v1 and v2 |

So the owner's "run both, report both" decision is discharged. One direction
works and is now better evidenced than it was; the other does not work and cannot
be rescued by volume.

This asymmetry is itself informative. The event detector, the labeling, and the
gate machinery are all shared between the two directions, so SP-to-RP passing on
the same pipeline rules out a harness defect as the explanation for RP-to-SP
failing. What is left is the model.

**Caveat added 2026-09-25 (final pass M07-01).** The SP-to-RP pass above is
weaker evidence than this section reads. Every registered baseline (K-BB%,
negated ERA, SEM+) is signed so a better pre-season predicts a bigger gain,
while war_delta pays out on a bad pre-season. Read the other way, the negated
ERA baseline ranks the legacy 61 events at +0.62 (data/pal_eval.json -0.62)
and the expanded 100 at +0.6828 (data/pal_gamelog_eval.json -0.6828), above
FIT both times, and FIT scales with starter ERA through its conversion-need
term. So "one direction works" holds against quality reads, not against
regression to the mean, and the harness-defect argument rests on the same
pass. Nothing here was re-gated; a need-direction re-gate is a new
pre-registration (owner sign-off, after the fWAR season-close epoch), and the
RP-to-SP closed-event set stays closed.

## Status

**Lane E3 is closed as a NO-SHIP for RP to SP.** Nothing was shipped, and the
`pal_conversion` registry verdict stays `provisional`.

Added to the banned-experiment ledger: do not propose expanding the RP-to-SP
closed-event set again as a route to passing this gate. The expansion has been
run, the direction of the effect is the problem, and the power arithmetic above
is the reason.

## What would legitimately reopen it

Not more rows. A different model or a different target, pre-registered as such:

1. **A different target.** `war_delta` may be the wrong outcome for this
   question. A held-the-role label, or an innings-weighted quality measure,
   changes what is being predicted rather than how much of it there is.
2. **A different feature basis.** The current fit is an arsenal-depth-anchored
   weighted blend with frozen literature weights. The negative correlation is
   consistent with the blend being anti-informative for this direction, which is
   a model claim and is testable directly.
3. **The W3 ARM-1 aStuff plus blend gate**, pre-registered in
   `tools/pal_xrv_lab.py` and never run. It is a separate question from the
   event count and remains open.

Any of those is a new pre-registration with its own gate, not a continuation of
this one.

## 2026-10-08: SP to RP re-gate, pre-registered (owner answer M22-3)

Registered 2026-10-08, before any 2026 SP-to-RP outcome was computed for this purpose.
Owner answers 2026-09-25, final-pass 'more' batch 22: M22-3 (pre-register an SP-to-RP
re-gate for the fWAR season-close epoch) and M22-2 (the served verdict word stays
'validated', with the mean-reversion caveat beside it, until this re-gate is graded).
Census finding M07-01. This section scores nothing. Git timestamps it; the result is
appended below it as its own dated entry, and nothing in this section may be edited once
a result exists.

### Why a re-gate

The 2026-07-15 SP-to-RP pass (rho +0.2916, n 61, gap lo95 +0.0745, `data/pal_eval.json`)
beat three quality baselines that are all signed so a better pre-season predicts a bigger
gain, while `war_delta` pays out on a bad pre-season. FIT scales with starter ERA through
its conversion-need term, so the pass may be regression to the mean. The census (M07-01,
live eWAR v2 series, the same 61 events) read the need direction at +ERA_pre 0.521 and
-WAR_pre 0.728 against FIT 0.271, with a partial rho of FIT given ERA_pre of -0.081. Those
figures were read on the original frame and are why this re-gate exists; they are not
part of it.

### The frame: unseen 2026 events only

- **Graded events.** SP-to-RP conversions whose post (new-role) season is 2026, found by
  `pal_conversion.detect_conversions` on the closed 2026 season (both seasons at least
  `CONV_MIN_IP` 20 IP, the original gate's detector). None of these is among the 61 gate
  events, whose post seasons all close by 2025. An event enters the graded set only when
  FIT and all six baselines below are non-null and WAR exists for both its pre and post
  season on the primary series.
- **Fallback, fixed now.** If that set has fewer than the minimum n below, the graded set
  becomes that set plus the 2026 SP-to-RP events recovered by
  `pal_gamelogs.recover_events` (the Lane A mid-year-switch detector, as tagged in
  `data/pal_gamelog_eval.json`), deduplicated by (mlbam, post season). The fallback is
  decided here, before any count is taken.
- **RP to SP.** The 7 RP-to-SP 2026 events in the served History are a reported
  sensitivity only: their rho and baseline rhos are printed and nothing follows from them.
  RP to SP stays a structural screen, and its closed-event set stays closed per the
  sections above.
- **Pinned code.** FIT is scored with the frozen weights at this registration's parent
  commit `0f9fb164`: `pal_conversion.py` blob `b19396dd`, `pal_export.py` blob `90de8170`,
  `pal_gamelogs.py` blob `4500fcc0`, `tools/pal_backtest_lab.py` blob `f24a8c13`,
  `rate_stabilization.py` blob `a25e121f`. Each event is scored on its TRUE pre-season row
  (repair 1 of the T1-6 harness), with pedigree and throwing hand set (repair 2). If any of
  those files changes before the look, the look scores with these blobs, not the newer ones.

### What the frame has already exposed, and whether that changes it

1. The 2026-07-15 lab's `rho_fit_war_delta_incl_partial_2026` sensitivity (0.2733, n 67)
   pooled the partial-season outcomes of 6 SP-to-RP 2026 events with the 61. No
   2026-only figure was reported.
2. The /pal/ History tab serves pre-season WAR, post-season WAR and `war_delta` for every
   2026 event, so their realized outcomes are on the site before the look.
3. Once TR_5_FLIP lands (not before 2026-10-11), the /mlbstats/ Trends tab displays, for
   display only, realized 2026 fastball velocity changes against each pitcher's own earlier
   games, including pitchers who moved from the rotation to the bullpen: the quantity
   PAL's `velo_delta` projects. League Trends relates none of it to an outcome.

None of this changes the frame. The protection an unseen frame gives is that no choice can
be tuned to the outcomes, and every choice is fixed above and below: the detector, the
fallback, the FIT code and its weights, the six baselines, the outcome series, the rule,
the seed, the minimum n and the look date. Realized velocity is not an input to FIT (FIT
reads the pre-season fastball) and is not the outcome. What remains banned until the look
is computing any 2026-only SP-to-RP rho, gap or other outcome read against FIT or a
baseline; doing so voids this registration (see "Looking early").

### Outcome series

- **Primary:** `war_delta` = post-season WAR minus pre-season WAR on published fWAR,
  `war_source.stint_frame('pit', provider='fwar')`, the fWAR label epoch's label, as
  served on the look date. The look records the vintage it read.
- **Reported, never the verdict:** the same `war_delta` on eWAR v2 (the displayed basis)
  and on bWAR (the original gate's basis); post-role WAR level (post-season WAR alone,
  with the same baselines); the partial Spearman rho of FIT on `war_delta` given ERA_pre
  and given WAR_pre, each with a bootstrap CI95.

fWAR and bWAR both scale a reliever's value by his Leverage Index and eWAR v2 centres FIP
within role, so a cross-role `war_delta` mixes two role frames on every series. That is
true of the 61 as well, and the re-gate reads it as given.

### Baselines

All six are computed on the same events, from the pre-season row:

| key | definition | direction |
|---|---|---|
| `kbb_pre` | pre-season K% minus BB% | quality, as registered 2026-07-15 |
| `neg_era_pre` | minus pre-season ERA | quality, as registered 2026-07-15 |
| `index_pre` | pre-season SEM+ (`season_sem_raw`) | quality, as registered 2026-07-15 |
| `era_pre` | plus pre-season ERA | need |
| `need_shrunk` | `pal_conversion.starter_need_score(era_pre, ip_pre)`: ERA shrunk toward 4.20 by 45 IP, mapped to 0 to 100 | need |
| `neg_war_pre` | minus pre-season WAR on the primary series | need |

### Metric and pass rule

- **Metric:** Spearman rho of pre-conversion FIT against `war_delta`, and the same for
  each baseline.
- **Pass rule (the original gate's form, unchanged):** PASS iff n_graded >= 15 AND
  rho(FIT, war_delta) >= rho(B*) AND the bootstrap gap rho(FIT) - rho(B*) has lo95 > -0.01,
  where B* is the baseline with the highest rho of the six. Event bootstrap, seed 20260714,
  2000 reps, the v1 convention of `data/pal_gamelog_eval.json`.
- **Minimum n:** 15 graded events. Under 15 after the fallback, the result is INSUFFICIENT.
- **Power, stated before the look.** At the closure section's spread, sd(n) = 1.106 /
  sqrt(n), the one-sided detectable gap is about +0.47 at n 15 and +0.36 at n 25. On the
  original 61 (census, eWAR v2) the best need baseline led FIT by 0.457. A pass needs FIT to beat the need
  read outright on new events; the likeliest result is a fail, and this section says so in
  advance.

Why this bar and not a partial-rho floor alone: the served copy says pre-conversion FIT
"out-ranked every registered same-event baseline". A pass that kept that sentence true
has to beat the need reads, not only carry information beyond them. The partial rho is
printed beside the verdict so a reader can see how much FIT adds when it does not win.

### What each result does

- **PASS:** the SP-to-RP verdict word stays 'validated'; the mean-reversion caveat is
  replaced by a citation of this re-gate's result entry.
- **FAIL or INSUFFICIENT:** the SP-to-RP verdict word drops to 'structural screen', the
  word RP to SP already carries: the /pal/ masthead clause, the meta description, the
  SP-to-RP caption, the History scorecard, the share captions, the glossary entries
  `sp_rp_fit` and `pal_conversion`, and the `pal_conversion` registry note. The registry
  verdict stays `provisional` in every case (RP to SP still fails). A later re-gate on
  2027 events is a new registration.
- **The look task** writes its own eval artifact, appends the dated result entry below this
  section, and makes `pal_export.py` carry the re-gate's per-direction pass into
  `backtest.gate` so every verdict word above is derived from the artifact, never typed.

### Look date

**Look date: 2026-11-03.** ONE look, on 2026-11-03 or, if that day is a registered look day
of another gate or a pipeline hold, the first later day that is not. Never before
2026-11-03, and never before the fWAR label epoch's step Z entry
(`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9, recorded 2026-10-03). The month
after the regular season lets the published 2026 fWAR settle and puts this registration's
commit weeks ahead of the read.

### Looking early

Computing any 2026-only SP-to-RP rho, gap or other outcome read against FIT or a baseline before
the look date disqualifies this registration. The verdict word then drops to 'structural
screen' as on a fail, because no clean frame remains until 2027 events exist under a new
registration.

# G-B: eWAR v3, the SDR merge gate (pre-registered 2026-08-18)

STATUS: REGISTERED, DATA-BLOCKED. This is the re-run the kept w-grid at
ewar.py:806-812 was written for. Clauses frozen before any SDR data exists.

## What is NEW (the re-open burden, stated up front)

The standing ban: an OAA/rfield blend at ANY w is a settled loss (measured on
the v2 grid, monotone, fielding_blend_w = 0.0). SDR qualifies to re-open the
grid because it is NOT that class: defense-plus carries components beyond
range (arm, framing, blocking, the DP pivot; 05_skill_composites.py) and
catcher coverage (25_catcher_components.py), which no incumbent blend had.
sdr_intake REFUSES a defense drop whose only live signal is range-class, so a
drop that reaches this gate is structurally new. If the drop's census shows
the non-range components carry data on fewer than 20% of rows, this gate is
NOT run and the refusal is recorded here instead.

## The merge under test

ewar_merged = Will's pitcher eWAR (his contract, his uncertainty fields)
+ SDR-bearing fielding (the w-grid over rfield vs SDR runs)
+ B-Ref offense / baserunning / positional adjustment
on the ewar.py frame, replacement re-derived so league sums match (existing
accounting machinery; max deviation must stay 0.0).

## Clauses (frozen)

1. C1 GRID SELECTION RULE (pre-committed): w* is chosen on the SAME two
   forward legs the v2 grid used (pitching-era self-persistence is not
   touched by fielding; the fielding legs are: fielding self-persistence and
   next-season team runs allowed), maximizing the average rank across both,
   ties to the LOWER w. No other statistic may pick w.
2. C2 SHIP RULE: ewar_merged ships as a provider only if w* > 0 AND the
   w* column beats w=0 on both legs' point estimates with at least one leg
   clearing a player-clustered 95% lower bound. Otherwise fielding stays
   rfield and ewar_merged is pitcher-swap-only, stated on the row.
3. C3 ACCOUNTING GATE (blocking): league-sum deviation 0.0 to machine
   precision, per season, both leagues, or the provider does not wire.
4. C4 COVERAGE GATE (blocking): the provider serves only seasons the drop
   covers; per-row basis flags (which ewar.json already carries for v2)
   extend to the fielding leg; no silent fallback inside a served row.
5. C5 ATTRIBUTION ARMS (reported): pitcher-swap-only vs fielding-swap-only
   vs both, so the merged gain decomposes and nobody quotes the sum as one
   mechanism.
6. C6 CATCHERS EXPLICIT: catcher rows ship only if the drop covers catchers;
   otherwise the out-of-scope note stays (the refused-framing hole remains
   named, not papered).

war_source.ewar_merged stops raising ONLY when C2-C4 pass. The ewar registry
row gains the dated merge verdict either way. tools/gen_audit_docs.py runs
after the registry edit.

## Results

PENDING. Data-blocked at registration (2026-08-18).

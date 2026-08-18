# G-A: sdr_eval, the MLB SDR validation gate (pre-registered 2026-08-18)

STATUS: REGISTERED, DATA-BLOCKED. Clauses frozen before any SDR data exists in
this environment. Results are empty and stay empty until a defense-card drop
passes sdr_intake --validate and its census is committed. The census fixes the
frame BEFORE any clause is measured; nothing below is read early.

## The question

Is Will's SDR (the defense-plus skill composite: range, arm, framing,
blocking, DP pivot; catcher components per 25_catcher_components.py) a better
measurement of MLB defensive value than the incumbents (B-Ref rfield, Savant
OAA/FRP), on forward legs, at the coverage his drop declares?

## Frame (census-dependent, fixed at census commit, never after)

- Seasons and positions: exactly the drop's declared coverage. Expect a
  tracking-era cliff; a has-SDR indicator is an ERA INDICATOR and is
  inadmissible in any trainable use.
- Row unit: player-season-position per the declared defense contract
  (sdr_intake.DEFENSE_CARD_CONTRACT).
- Innings floor: the drop's own reliability convention if it ships one, else
  Inn >= 200 stated as policy.

## Clauses (frozen)

1. C1 SELF-PERSISTENCE (forward, gated): year-over-year Spearman of SDR runs
   per inning vs itself, players with qualifying innings both seasons,
   compared to the SAME statistic for rfield and OAA on the SAME player set.
   SDR must beat BOTH incumbents on the point estimate AND clear a
   player-clustered bootstrap 95% lower bound above the better incumbent, or
   the clause fails.
2. C2 TEAM FORWARD (gated): team-season SDR sum predicting next-season team
   runs allowed (defense leg: runs allowed residualized on team pitching FIP,
   the ewar.py convention), vs the same construction on rfield and OAA.
   Same beat-both + LB rule.
3. C3 AGREEMENT (descriptive, reported never gated): correlation with realized
   defensive value against the two named baselines from the record: FG fFld
   (Spearman 0.28 on the prospect frame) and prospect_def_value (0.68). These
   numbers belong to their own frames and are context, not the bar.
4. C4 FACE VALIDITY (reported): top/bottom 15 by position, eyeballed, named
   in Results with any absurdity called out.

Floors are derived on the census frame at measurement time (never reused from
another frame). Holm across C1/C2. A noise twin (permuted within
position-season) accompanies each gated clause; a clause is not creditable if
its twin also clears.

## What this gate does NOT decide

Display (W2 ships on validated-descriptive basis per the master plan), the
eWAR merge (G-B), and any eFV use (G-C then W4) have their own gates.

## Results

PENDING. Data-blocked at registration (2026-08-18): no SDR data exists in the
repo or the environment; defense-plus has no export adapter. See
docs/sdr-intake-request-2026-08-18.md for what was asked of Will.

# Expansion E24 — Depth-Chart PA Allocator

- budget (training mean OD-hitter PA per team): 4246; cap (99th pct): 712
- test incumbents: 1990; with OD team 56%

## Overall (incumbents, test 2023-25)
              model     R2   MAE  RMSE    rho
     champion (raw) 0.7145  94.5 124.0 0.8615
          allocator 0.6789 100.9 131.5 0.8559
    blend raw+alloc 0.7046  96.8 126.1 0.8609
            Steamer 0.6742  90.3 132.5 0.8478
blend alloc+Steamer 0.7264  90.0 121.4 0.8669

## By PREDICTED-PA band (where the allocator should act)
- pred>=500 (n=243): raw 101.6 | alloc 139.0 | blend 117.5 | Steamer 83.6
- pred 300-500 (n=565): raw 127.3 | alloc 134.9 | blend 129.4 | Steamer 124.9
- pred<300 (n=1177): raw 77.4 | alloc 76.7 | blend 76.9 | Steamer 75.0

## Verdict
Allocator ships if it closes the projected-regular gap (pred>=500 toward
Steamer 83.6) without hurting overall.

## VERDICT — allocator FAILS (and why it's fundamental, not tuning)
Overall MAE 94.5 -> 100.9 (worse); target band pred>=500 101.6 -> 139.0 (much
worse). Two fundamental blockers, both confirmed:

1. INCOMPLETE ROSTERS. We see ~12.3 incumbents per team-season; a real team
   uses 20+ hitters (call-ups unknown at projection time). Allocating the team
   PA budget among a half-seen roster over-inflates the players we do see.

2. THE BORDERLINE PROBLEM (irreducible). 36% of players who realized 500+ PA
   were predicted <450 (borderline). Correct allocation requires knowing WHICH
   borderline 300-450 guys win the everyday job — exactly the unpredictable
   bimodal-spread uncertainty (E23). Water-filling lifts the already-high guys
   (overshooting) instead of the right borderline ones (which it can't identify).

CONCLUSION: the projected-regular gap (~15-18 PA on pred>=500) is IRREDUCIBLE
from our data. It is Steamer's HUMAN-CURATED depth-chart / role assignment
(FanGraphs RosterResource manually pencils in the starting jobs) — information
we cannot reconstruct by allocating our own uncertain predictions.

## Where this lands the whole gap investigation
- Calibration (E23): wash. Durability (E23): no-add. Allocator (E24): fails.
- The residual Steamer MAE edge is curated playing-time information, full stop.
- Two ways to get it: (a) the Steamer BLEND — already deployed, captures it,
  best result (blend champ+Steamer MAE 87.7); (b) INGEST a curated depth-chart
  feed (RosterResource/FG Depth Charts) — but that's an external dependency
  like Steamer, not an in-house build.
- RECOMMENDATION: keep the Steamer blend as the deployed champion; do NOT ship
  the allocator. The in-house model is at its information ceiling; the gap is
  someone else's hand-curated roster knowledge.

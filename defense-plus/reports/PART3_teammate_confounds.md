# Part 3 — Teammate / Positioning Confounds
Date: 2026-06-16 · `pipeline/07_teammate_confounds.py` · all tests vs permutation/placebo floor

## Question
Part 2 removed metric-specific noise but not variance SHARED across metrics (positioning,
park, opportunity, scorer). How big is that shared confound, and must Defense+ adjust for
teammate effects? Tested on OAA (our primary range indicator), 2021–2025, Inn≥400.

## Results — the feared confounds are small-to-absent

| Test | Statistic | vs chance | Verdict |
|---|---|---|---|
| **A. Shared team-season component (ICC)** — do teammates' OAA cluster? | OF ICC **+0.012** (p=0.73); IF ICC **+0.057** (p=0.11) | within permutation noise (null sd 0.036) | **No significant team confound.** OAA is team-isolated. IF hint not significant. |
| **B. Does talent travel?** — OAA persistence movers vs stayers | stayers r **0.477**, movers r **0.504** | movers ≈ stayers (slightly higher) | **OAA travels with the player.** Context change doesn't erode it → it's talent. |
| **C. OF cannibalization** — corner opportunity rate vs CF range | r **+0.057** (p=0.36) | within placebo noise (sd 0.062), wrong sign | **No CF→corner opportunity cannibalization** detected. |

## Read
**OAA is already well-isolated from teammate, positioning, and park effects** — because it's built to be opportunity-adjusted (every ball weighted by its catch probability given the fielder's start position), it sidesteps the confounds that the prompt (rightly) worried about for zone-based metrics.

1. **Defense+ needs NO teammate/team adjustment for OAA.** Team de-meaning would add noise, not remove bias — and it's exactly the season-grain confound-factory move to avoid. The placebo floors are why we can say this: the raw IF ICC (+0.057) and cannibalization (+0.057) *look* like effects until you see the permutation null sits at the same magnitude.
2. **The famous "elite CF cannibalizes the corners" intuition doesn't survive contact with the data** (on opportunity rate). If it operates at all, it's below the noise floor at season grain.
3. **Updates Part 2's caveat:** I'd warned the 0.61 shared communality might contain shared positioning/park confound. Test A says the *team-level* shared component of OAA is ≤6% and not significant → the Part-2 latent range talent is **largely true talent, not shared confound**. The variance-decomposition question that was "gated by Part 3" is answered for OAA: team/positioning/park ≈ negligible.

## Caveats / scope
- Validated for **OAA** specifically. **DRS/UZR are zone-based and more plausibly team/positioning-sensitive** — since Defense+ leans on OAA for range and uses DRS only for the sticky backbone, flag DRS's potential team-sensitivity but don't rely on it for the confound-clean signal.
- The IF shared hint (ICC .057, p=.11) — possible positioning-system / GB-staff / scorer effect — worth monitoring with more seasons; not adjustable yet.
- Season-grain analysis; a within-season positioning study would need play-level data.

## Recommendation for Defense+
Do **not** build a teammate-adjustment layer. Anchor range talent on OAA (confound-clean per Tests A–C), keep DRS components for stickiness with a team-sensitivity caveat, and spend modeling effort on aging/viability/translation instead. This is a "the simple thing is correct" result, validated by placebo.

## Files
- `pipeline/07_teammate_confounds.py`

# Infield component aging (IF analog of OF jump components)
Date: 2026-06-18 · `pipeline/19_infield_component_aging.py` · joint-dropout, SS/2B/3B 2016–2025, Inn≥300

Infield OAA decomposes **directionally**: `infront` (charging slow rollers = hands/transfer/reactions), `lateral` (side-to-side RANGE = athleticism), `behind`. Plus arm strength (mph) as a separate tool. How each ages (27→33, SD vs peers):

| component | 27→33 | role |
|---|--:|---|
| **infront** (hands/charge) | **−0.13** | most durable — IF "instincts/hands" |
| lateral (range) | −0.18 | athletic range — ages faster |
| arm strength (mph) | −0.25 | velocity erodes — **not a durable anchor** |
| behind | −0.28 | small, noisy |
| OAA total | −0.26 | |

## Reads
- **Durable infield skill = hands/charging (`infront`), not range or arm** — the IF parallel to OF reaction/route. A slick-fielding charger ages best.
- **Arm ages too** (−0.25) — throwing velocity declines with age like pitch velo; a cannon-arm IF gets no aging pass (corrects the "arm holds" guess).
- **Narrower spread than OF** (−0.13 to −0.28 vs OF's −0.06 to −0.62): infield range is quicker-twitch + positioning, not the pure speed that collapses in CF. So the IF aging *multiplier* moves the needle less than the OF one — but a hands-first vs range-first SS still age measurably differently.

## Use (Career+ IF aging multiplier)
Scale an infielder's aging slope by their directional value profile: high-`infront` share → slower aging (mult <1); range/`behind`-driven → at/above average. Range ~0.6–1.2 (vs OF 0.2–1.6). Mirrors the OF component-profile aging in `18_career_plus_v11.py`.

## Files
- `pipeline/19_infield_component_aging.py` → `reports/19_infield_component_aging.csv`

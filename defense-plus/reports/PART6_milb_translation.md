# Part 6 — MiLB → MLB Defensive Translation
Date: 2026-06-18 · `pipeline/15_milb_translation.py` · AAA fielding from statsapi (sportId 11; AA fallback)

## Setup
MiLB has no tracking metrics, so **position history is the signal**. Cohort = 462 MLB position
players (debut ≥2015, ≥100 career MLB GS at primary). For each: primary AAA position (most
games-started) → primary MLB position. Tests the prompt's hypothesis: does holding a position
at AAA predict holding it in MLB, and does debuting young matter?

## 1. AAA → MLB transition matrix  P(MLB pos | AAA pos), %
| AAA↓ \ MLB→ | C | SS | CF | 2B | 3B | RF | LF | 1B | DH |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **C** | **95** | 1 | | | | | 2 | | 1 |
| **SS** | | **56** | 3 | 23 | 12 | | 4 | 1 | |
| **CF** | | 1 | **70** | | | 13 | 14 | | 1 |
| **2B** | | 7 | 5 | **56** | 19 | | 5 | 9 | |
| **3B** | | | 2 | 13 | **67** | | 4 | 13 | 2 |
| **RF** | | | 5 | | | **70** | 20 | 2 | 2 |
| **LF** | | | 10 | 5 | 2 | 22 | **45** | 5 | 10 |
| **1B** | | | 2 | 2 | 5 | 7 | | **75** | 9 |

## 2. Position-hold rate (AAA → same MLB position) — assignment IS predictive, position-dependently
| AAA pos | holds in MLB | n |
|---|--:|--:|
| **C** | **95%** | 82 |
| CF | 70% | 83 |
| 3B | 67% | 54 |
| SS | 57% | 73 |
| 2B | 56% | 43 |

- **Catcher: position is destiny** (95%). If you catch at AAA, you catch in MLB — the single strongest translation signal.
- **SS holds only 57%** — meaningfully predictive but far from certain; 44% slide to 2B (23%) / 3B (12%), the classic infield cascade. The MLB SS bar is the hardest jump to clear.
- The down-spectrum cascade mirrors the MLB migration matrix (Part 5): SS→2B/3B, CF→corners, 3B→1B.

## 3. "Debuts young" — confirmed for SS, irrelevant for CF
P(AAA-SS holds MLB SS) by debut age:

| debut age | hold SS | n |
|---|--:|--:|
| **≤22 (young)** | **69%** | 39 |
| 23–24 | 47% | 30 |
| **≥25 (old)** | **40%** | 10 |

A young AAA shortstop is a *real* shortstop (69%); an old one is usually org filler sliding to 2B/3B (40%). **But CF is age-independent** (≤23: 68%, ≥24: 69%) — center field is a pure speed/tool that shows up early, so age adds nothing. So debut age is a strong modifier *only for the skill-and-instinct positions* (SS), not the pure-tool ones (CF).

## Translation priors (the Part-6 deliverable)
- **C:** ~95% hold — assignment near-deterministic.
- **CF:** ~70% hold, **age-independent** — trust the AAA CF label regardless of age.
- **SS:** 57% base, but **69% if debut ≤22 / 40% if ≥25** — condition on age.
- **2B/3B/corner:** moderate, mostly stable or down-spectrum; 1B/DH are sinks (75% / absorbing).
- When a position isn't held, the destination is **down the defensive spectrum**, predictably (use the matrix rows as priors).

## Limits & next
- AAA innings-by-position only (no tracking) → this captures *position viability*, not defensive *quality*. Quality translation would need scouting grades (`grades_long.parquet`: field/throw/speed) — the natural next module (also Part 7).
- Counting proxies (assists/errors/range) untested as quality signals yet.
- Next: a predictive model P(MLB pos | AAA pos + age + scouting field/arm/speed grade), and whether grades add over position+age.

## Files
- `pipeline/15_milb_translation.py` → `reports/15_milb_transition.csv`, cache `data/raw/milb_fielding.parquet`

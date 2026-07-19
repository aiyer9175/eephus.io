# Catcher Component Model (completed)
Date: 2026-06-18 · `pipeline/25_catcher_components.py` (+ framing/throwing aging from earlier)

Catchers were treated as a DRS monolith; this decomposes the value into framing + throwing + blocking and checks reliability + aging.

## Value composition — framing dominates
| component | value spread (run SD) | reliability (y2y) | aging 27→33 (SD) |
|---|--:|--:|--:|
| **Framing** (rv_tot) | **6.27** (dominant) | 0.53 | **−0.41** (fastest) |
| Throwing (pop time / arm) | secondary | **0.76** (most reliable) | −0.32 |
| Blocking (blocking runs) | **1.76** (minor, range −7..+6) | 0.46 | **−0.22** (most durable) |
| Game-calling | unmeasurable | — | — |

Framing differentiates catcher value **~3.5× more than blocking** — matches the known sabermetric picture. Throwing is the most *reliable* (the pop-time/arm tool), framing the most *valuable*.

## Key result — no MEANINGFUL durable catcher component
Blocking is actually the most age-resistant skill (−0.22), but it's **too minor (SD 1.76, ~28% of framing's spread) to provide real aging insurance** — and the *dominant* skill, framing, ages fastest (−0.41). So unlike OF (reads durable + valuable) and IF (hands durable + valuable), **catchers have no age-resistant skill that's also a big share of value** — the physical toll erodes the part that matters most. This is *why* catcher DRS ages the steepest after CF (−0.63, Part 4), and it confirms that **Career+'s monolithic, no-aging-bonus treatment of catchers is correct.**

## Data note
Per-year blocking IS pullable — the param is **`season_start`/`season_end`**, not `year`/`startYear`/`season` (those are silently ignored and return a fixed multi-year aggregate). Endpoint logged in [[reference-baseball-data]].

## Files
- `pipeline/25_catcher_components.py`, blocking cache `data/raw/blocking_*.csv` (aggregate)

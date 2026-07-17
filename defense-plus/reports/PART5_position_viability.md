# Part 5 — Position Viability / Retention
Date: 2026-06-18 · `pipeline/12_position_migration.py`, `pipeline/13_retention_model.py`

## Question
Can a player stay at his position, where does he migrate, and what predicts it? Backbone =
27 years of usage (primary position from games-started, usage_spine 2000-2026, 10,335
transitions); retention model adds defensive quality (OAA) + age (2016-2024, Inn≥300).

## 1. Migration matrix — P(pos_t+1 | pos_t)
Retention (stay same position) and the dominant moves:

| from | stay | exit | top destinations |
|---|--:|--:|---|
| **C** | **75%** | 23% | almost none (1% 1B/DH) — catchers stay or retire |
| **SS** | 65% | 18% | →2B 10%, →3B 5% |
| **CF** | 58% | 21% | →RF 9%, →LF 9% |
| **2B** | 57% | 24% | →3B 7%, →SS 6% |
| **3B** | 59% | 22% | →2B 5%, →1B 5%, →SS 4% |
| **RF** | 54% | 20% | →LF 11%, →CF 7% |
| **LF** | 47% | 27% | →RF 9%, →CF 7% |
| **1B** | 63% | 23% | →DH 5% |
| **DH** | 45% | 30% | →1B 9%, →LF 6% |

- **Catcher and SS are the stickiest** premium spots; **LF/DH the most transient**.
- Classic paths confirmed: **SS→2B/3B (15%), CF→corners (18%), 3B/1B→DH**.
- **Migration is only mildly down-spectrum (58% down / 42% up)** — lots of lateral/up movement (young players finding a position, utility versatility). NOT a pure "everyone slides down" story.

## 2. Migration accelerates with age — at the early-peaking positions
Move-off-position rate by age band (premium positions):

| pos | ≤25 | 26–28 | 29–31 | 32+ | Part-4 peak |
|---|--:|--:|--:|--:|--:|
| **C** | 3 | 2 | 3 | 2 | 28 — *flat: catchers don't migrate, they retire* |
| **SS** | 17 | 19 | 24 | **30** | 27 |
| **CF** | 23 | 24 | 28 | **37** | 23 |
| **2B** | 27 | 26 | 24 | 24 | 26 — *flat: a destination, not an origin* |

SS and CF (early peaks, steep Part-4 decline) shed players with age; 2B is where ex-SS *land* (flat); catchers are a closed system (stay/retire).

## 3. Retention model — does being a good defender keep you at the position?
P(stay) ~ age + OAA (logistic, Inn≥300). Holding the other fixed:

| pos | bad glove (−1SD) → good glove (+1SD) | age 24 → age 32 |
|---|---|---|
| **CF** | 38% → **77%** (+39 pt) | 64% → 53% |
| **3B** | 50% → **78%** (+28 pt) | 69% → 62% |
| **SS** | 58% → **77%** (+19 pt) | **77% → 57%** |
| **2B** | 59% → 65% (+6 pt) | 65% → 59% |

- **Defensive quality strongly buys position retention** at the skill positions — most at **CF** (a poor-fielding CF is moved off almost regardless: you must cover ground), then 3B and SS. 
- **2B is the exception (+6 pt)** — retention barely depends on the glove, because 2B is a *landing spot* (nowhere more-premium to fall to). Confirms the migration matrix.
- **Age drives players off SS hardest** (77%→57%, 24→32) — the aging SS slides to 2B/3B even while still competent.

## Synthesis (ties Parts 4, 5, 11-A together)
Defense is career insurance at three levels: it keeps you **in MLB** (M11-A: ~13 wOBA+ discount), it keeps you **at your premium position** (this model: +19–39 pt retention), and the premium position is exactly where the offensive bar is lowest. The mechanism is age → defensive decline (Part 4) → migration down/off the position (Parts 5.1–5.2) → higher offensive bar to survive (M11-A). A good glove slows every step.

## For Career+ / next
- The retention model is the population layer of a **per-player P(can-play-position)** viability score — the natural Career+ build (add arm strength, sprint speed, body type as inputs).
- MiLB→MLB position-transition matrices = **Part 6** (does a prospect who stays at SS through AA/AAA hold SS in MLB?).

## Files
- `pipeline/12_position_migration.py` → `reports/12_transition_matrix.csv`, `12_retention.csv`
- `pipeline/13_retention_model.py` → `reports/13_retention_model.csv`

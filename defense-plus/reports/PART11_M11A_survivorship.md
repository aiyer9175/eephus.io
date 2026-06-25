# Part 11 / M11-A — Career Survivorship by Position
Date: 2026-06-16 · `pipeline/11a_survivorship_by_position.py`

## Question
What offensive level keeps a player in MLB, and does it differ by position? — the
**position-specific offensive replacement level**. Descriptive, no identification problem.
Hypothesis: SS/CF/C survive on less offense than 1B/LF/RF (defense = career insurance).

## Data
- Spine: `usage_spine` (primary position via games-started, PA, survival), 2000–2024 (t+1 observed).
- Offense: `deep_mlb` wOBA → era-adjusted **wOBA+** = 100·wOBA / PA-weighted league wOBA.
- Sample: 8,524 player-seasons, PA≥200. Survival = ≥50 PA in MLB next season (base rate 88.2%).

## Result 1 — model-free (no assumptions): survival rate by position × wOBA+ band

| Pos | <85 | 85–95 | 95–105 | 105–115 | 115+ |
|---|--:|--:|--:|--:|--:|
| C  | **79** | 87 | 96 | 99 | 96 |
| SS | **72** | 90 | 96 | 99 | 97 |
| CF | **66** | 82 | 94 | 99 | 98 |
| 2B | 57 | 80 | 95 | 96 | 100 |
| 3B | 52 | 79 | 90 | 96 | 99 |
| RF | 57 | 69 | 88 | 97 | 98 |
| LF | 51 | 66 | 87 | 94 | 96 |
| 1B | **35** | 67 | 84 | 93 | 98 |
| DH | **33** | 57 | 73 | 94 | 94 |

The defensive-spectrum ordering is **perfectly monotonic**, and the gap is **concentrated among weak hitters**: a below-average-hitting catcher survives 79% of the time, an identical-hitting 1B only 35%. By the 115+ band offense erases the position effect (all ~96–100%). That is exactly the signature of "career insurance" — defense protects you precisely when your bat doesn't.

## Result 2 — threshold model (logistic, age + log(PA) controlled)
wOBA+ needed for an **80% chance to stick** (age 28, ~450 PA), bootstrap 68% CIs:

| Pos | threshold wOBA+ | CI |
|---|--:|---|
| C  | **64** | [62,67] |
| SS | **73** | [71,76] |
| CF | 79 | [77,81] |
| 2B | 79 | [78,81] |
| 3B | 81 | [79,83] |
| RF | 84 | [82,85] |
| LF | 85 | [83,87] |
| 1B | **87** | [85,89] |
| DH | **90** | [88,92] |

- Premium defense (C/SS/CF/2B) mean **74** vs bat-first (1B/LF/RF/DH) mean **86** → **13 wOBA+ point defensive discount**.
- **Catcher gets the biggest break** (64) and DH the smallest (90): a **26-point** spread end-to-end. A catcher can stick on offense a 1B never could.
- Monotonic along the spectrum; premium vs bat-first CIs do not overlap.
- **OOS AUC 0.818** (train ≤2016, test ≥2017) — generalizes.

## Reads / use for Career+
- **Defense as career insurance is real and large** — a premium defender needs ~13 wOBA+ points less offense to stick, and the protection is concentrated exactly where bats fail. This is a position-specific replacement level that belongs directly in Career+ survival/playing-time priors: the same projected bat implies very different career length at SS vs 1B.
- A bat-first prospect carries a **higher offensive bar to clear** — 1B/DH profiles are fragile because there's no defensive floor.

## Caveats
- **Defense not controlled** → the threshold is the *population-average* offensive bar given *typical* defense at that position. A SS who survives on 73 wOBA+ is implicitly an adequate-or-better glove; the 13-point discount blends defensive value + positional scarcity, not "insurance for a fixed-quality defender." Adding Defense+ as a covariate (once built) would split those.
- Survival bar is "≥50 PA next year" (still in MLB). A "remain a regular" (≥400 PA) variant would likely widen the gaps — worth a follow-up.
- wOBA+ is offense-only (era-adjusted, not park/positionally adjusted). Absolute thresholds shift with the PA/age reference; the **ordering and gaps** are the robust takeaways.

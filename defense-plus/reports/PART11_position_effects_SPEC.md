# PART 11 — Position Effects Research Program (SPEC)
Added 2026-06-16. Research module to run **before** Defense+ / Career+ model-building.

## Central question
Does defensive position merely *describe* player archetypes, or does it *actively shape*
development and career outcomes? Two very different hypotheses:

- **Selection:** `Position ← Athleticism → Offense`. Position has no causal effect; SS/CF/C
  already differ physically before they ever play the position.
- **Causation:** `Athleticism → Position → Offense`. Playing the position changes training,
  fatigue, injury exposure, cognitive load, offensive tradeoffs.

Goal: `Observed Position Effect = Selection Effect + True Position Effect`, and estimate the split.

---

## THE LOAD-BEARING ISSUE: identification, not measurement
The sub-parts as literally worded (A "do SS develop power slower?", B "are SS better contact
hitters?", C "do catchers have better swing decisions?") are **cross-sectional position
comparisons**. Run as written they measure **selection almost entirely** — who *becomes* a SS,
not what SS *does* to a player. Controlling for age/size/sprint-speed/prior-offense helps but
**cannot** remove selection on unobserved athleticism (the omitted variable is exactly the thing
that sorted players to positions). So a "residual position effect" from a controlled regression
is an **upper bound on causation, contaminated by residual selection** — not a causal estimate.

This is the same trap as the [[feedback-career-mean-leakage]] / season-grain confound-factory
lessons. We will not report controlled cross-sectional residuals as causal effects.

### Designs ranked by what they can actually identify

| Design | Identifies | Strength | Notes |
|---|---|---|---|
| **Survival threshold by position** (the addition) | Position-specific offensive replacement level | **Strong — no identification needed** | Descriptive & directly actionable; the recommended starting module |
| **Within-player position change** (Part H) | True position effect on offense/injury | **Strong** | Differences out fixed player endowment; but moves are non-random (better hitters slid off premium D earlier) → must model the move's cause / use timing controls |
| **Injury exposure → offense** (Part E, via [[project-injury-model]]) | Position→injury (plausibly causal) → offense mediation | **Medium-strong** | Catching IS physically different; injury is a credible causal channel |
| **Matched-athleticism comparison** (sprint speed + size + age + prior offense + level) | Selection-adjusted association | Medium | Quasi-control; residual selection remains |
| **Raw cross-sectional A/B/C/F** | Selection + archetype description | **Weak for causation** | Useful only as *description* of archetypes, labelled as such |

**Verdict:** Part 11's value lives in **survival-threshold** + **within-player transitions** +
**injury mediation**. Parts A/B/C/F should be reframed as *archetype description* (selection
maps), not causal tests — still worth producing, but honestly labelled.

---

## DATA REALITY (what's buildable from this machine)
- **Position + survival + PA, 2000–2026, ~9k PA≥200 seasons** — FREE from
  `playing_time_model/usage_spine.parquet` (games-started by every position) +
  `replacement_features.parquet` (primary_pos precomputed). ✓
- **Offense (season wOBA/wRC+/OBP/SLG)** — needs a join: statsapi hitting lines (reachable) or
  BRef, era/league-adjusted. The one outstanding pull for survival + aging + transitions.
- **Bat-tracking offense (Swing+, bat speed, EV90, attack angle)** — **only 2023+** (Statcast
  bat tracking). So Parts A & F that hinge on bat speed/Swing+ are limited to a ~3-yr window and
  cannot support aging/development claims yet. Their non-bat-speed offense (K%/BB%/ISO/contact)
  goes back to 2000+.
- **Reuse completed projects:** [[project-aging-curves]] (Part D), [[project-injury-model]]
  (Part E — Skill Impact Matrix, group-level only), [[project-variance-plus]] (Part G —
  collapse/reinvention rates), Decision+/Bat-to-Ball+/Contact+ (Parts B/C, 2023+).
- **Org effects (Part I):** [[project-pt-plus-expansion]] already found org promotion tendency
  **fully mediated by 40-man selection** → expect org "development" effects to be largely
  selection/mediated. Test on premium-position *retention* specifically, with low priors.

---

## Sub-parts (user spec) — retained, reframed by identifiability
- **A. Position × Swing+/power/bat speed** — *archetype description* (2023+ for bat speed); causal only via transitions/matching.
- **B. Position × Bat-to-Ball** — archetype description; reuse Bat-to-Ball+ (2023+).
- **C. Position × Swing decisions (Decision+)** — archetype description; reuse Decision+.
- **D. Position × offensive aging** — group by season-age NOT career-mean ([[feedback-career-mean-leakage]]); survivorship-corrected (aging curves are biased by who stays).
- **E. Position × injury risk** — plausibly causal; quantify "aging vs accumulated injury" via injury_model mediation.
- **F. Position × physical development (weight/BMI/speed)** — body-type ↔ position is bidirectional; matched design.
- **G. Position × career variance (Variance+)** — collapse/stable/reinvention/superstar rates by position; "is defensive value career insurance?"
- **H. Position transitions (SS→3B, C→1B, CF→corner, …)** — the cleanest causal lever; before/after offense Δ, with move-timing controls.
- **I. Organizational effects** — low prior (selection-mediated); retention focus.

## RECOMMENDED FIRST MODULE — Career survivorship by position (M11-A)
Why first: descriptive (no identification problem), directly actionable for Career+, and the user
flagged it as potentially the single most valuable input.

**Question:** What offensive level keeps a player in MLB, and does it differ by position? I.e. the
**position-specific offensive replacement level** — the wRC+/wOBA below which players at each
position exit, separately for SS/CF/C vs 1B/LF/RF.

**Build:**
1. Per player-season (2000–2026, PA≥200): primary position (from gs_*), age, PA, offense
   (era/league-adjusted wRC+ or OPS+; join from statsapi/BRef).
2. Survival = meaningful MLB PA in t+1 (and a 2-yr variant).
3. Model P(exit | offense, age, position) — logistic with position×offense interaction, or
   estimate the offense level where P(survive next yr)=0.5 per position.
4. **Output:** position-specific survival threshold curve + the offensive "discount" premium-
   defense positions get. Hypothesis: SS/CF/C survive at materially lower offensive thresholds
   (defense = career insurance); 1B/LF/RF need to hit. Validate OOS (predict actual exits).

Standards (all sub-parts): selection effect vs residual reported separately; effect sizes + CIs +
reliability + OOS + ablations + explicit causal-limitation statement.

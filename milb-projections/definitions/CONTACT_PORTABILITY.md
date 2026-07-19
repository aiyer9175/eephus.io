# Contact Portability

## What this document is actually about

The charter that produced this package assumed a dedicated "contact portability" asset — a model translating Statcast-grade contact/collision quality (exit velocity, barrel rate, damage) across MiLB levels and into MLB terms. **That asset does not exist in Eephus.** This is confirmed by reconnaissance across every hitter-contact-adjacent directory (`bat_to_ball_plus`, `contact_plus`, `damage_conversion_plus`, `translation_layer`, `variance_plus`, `identity_plus`) — all are MLB-only, with zero MiLB dimension.

What exists instead, and is exported here as the closest available substitute, is a **MiLB→MLB rate-skill persistence and translation layer** that operates on aggregate outcome rates (K%, BB%, ISO, wOBA-derived offense/power/contact/defense components), not on batted-ball physics. Its own documentation explicitly states why: Statcast bat-tracking coverage is MLB + AAA (2023+) only, so EV/barrel-based contact quality is **not translatable below AAA** — there is no data to translate.

## Why this exists

`career_outcome_plus/milb/block2_translations.py` and `block5_recommended_architecture.md` study how well level-t skill rates predict early-MLB skill rates, per component, with level-conditioned reliability weights. The production consumer of this research is the rate-talent estimation step (`career_outcome_plus/model/step2b_rate_talent.py`) and the downstream career/xWAR projection (`m3_calibrate.py`).

## Source, output, and unit

- Code (not published — see `PUBLICATION_POLICY.md`): `career_outcome_plus/model/step2b_rate_talent.py`, config `career_outcome_plus/model/evidence_weighting_config.yaml`.
- Output 1 — `latent_rate_talent.parquet` (77,524 rows). Grain: **batter × season**, using a `top_level` field (the highest level a player's evidence draws from that season) rather than a separate level dimension per row.
  - Columns: `batter, season, eff_n, def_n, top_level, off, pow, con, def, up_mid_share, premium, weight, off_z, pow_z, con_z, def_z, theta, season_state`.
  - `con` here is **defined as −K% (strikeout avoidance)**, not contact-quality-on-contact (EV/barrel). This is a name collision worth flagging explicitly: "contact" in this system means plate-discipline-adjusted whiff avoidance, not batted-ball damage.
  - `eff_n` (effective sample size) is the closest thing to an uncertainty/reliability field; there is no explicit standard-error or confidence-interval column.
- Output 2 — `milb_xwar_projection.parquet` (4,721 rows). Grain: **batter × season × level**.
  - Columns: `batter, season, level, age, p_reach_100_pa, e_war, xWAR, p_coffee, p_regular, p_role, p_star, p_super, has_mlb_appearance, mlb_debut_season, has_reached_100_pa, career_mlb_pa, reach100_season, already_debuted, debut_season, season_state, status_as_of_date, status_source, model_version`.
  - This is a downstream career-outcome projection, not a contact-quality metric — included here only because it's the nearest thing to a "translated MiLB skill estimate with an MLB-comparable target" that exists.

## Target definition

`off`/`pow`/`con`/`def` are level-and-competition-adjusted z-scored component skills, shrunk toward level-conditioned reliability (`level_reliability` in `evidence_weighting_config.yaml`: MLB 1.00, AAA 0.43, AA 0.46, A+ 0.28, A 0.21, Rk 0.25, DSL 0.12 — a documented reliability cliff at AA and below). `theta` is the composite latent skill estimate feeding career projection. None of these targets are contact-quality-on-contact in the batted-ball-physics sense.

## Training cutoff / prediction timestamp

`status_as_of_date` and `season_state` in `milb_xwar_projection.parquet` are the closest fields to a governing timestamp. Neither output carries a documented training-data cutoff date separate from the season itself — treat `season` as the latest season of evidence unless `status_as_of_date` says otherwise for a given row.

## Level adjustment

Handled via `evidence_weighting_config.yaml`'s `level_reliability` table (shrinkage weights, not a physical unit conversion). There is no per-pitch-type or per-batted-ball-type level translation of any kind.

## Uncertainty

`eff_n` (effective sample size) in `latent_rate_talent.parquet`; outcome-band probabilities (`p_coffee`...`p_super`) in `milb_xwar_projection.parquet` express uncertainty over career outcome tiers, not over the point estimate itself. No credible interval column exists in either file.

## Valid interpretation

- May be used as **context** (to understand a batter's general offensive-skill level when interpreting a pitcher's results against him) — e.g., "this pitcher's opponents skew below-average contact-skill hitters."
- May be used as a worked example of how Eephus handles level-conditioned reliability collapse, informing how a future pitch-quality model should shrink its own level-crossing estimates.

## Invalid interpretation

- **Must not** be used as, or represented as, a batted-ball contact-quality (EV/barrel/damage) portability metric. It measures outcome-rate persistence, not physical contact quality.
- **Must not** be treated as validated below AAA for anything Statcast-adjacent — the source documentation is explicit that this gap is unresolved, not merely unaddressed by this package.
- **Must not** be joined to pitcher-level data as if it were a pitch-level or plate-appearance-level batter-quality control without accounting for its batter×season (or batter×season×level) grain — it is not a per-pitch signal.

## Known limitations

- No Statcast-based contact-quality translation exists below AAA (2023+).
- `con` field name collision with batted-ball "contact quality" is a real risk for misuse; always read it as "contact rate (1 − K%)," never as damage/EV-based quality.
- No explicit confidence interval; `eff_n` and the outcome-tier probabilities are the only uncertainty signal.
- Underlying source code is proprietary (`Copyright (C) 2026 Will Cahoon — All Rights Reserved`); only the derived output (via a private export) and this methodology description are shared, per `PUBLICATION_POLICY.md`.

## Feature / benchmark / label / context classification

`off`/`pow`/`con`/`def`/`theta`: usable as **context**, not as a feature for the future pitch-quality model (they describe hitters, not pitchers, and are not physical contact quality). `e_war`/`xWAR`/outcome-tier probabilities in `milb_xwar_projection.parquet`: **context only** — they are a different model's target, not a benchmark for pitch quality.

# Pitch-Quality Research Contract

## Why this document exists

The future MiLB pitch-quality/arsenal model starts from noisy pitch-by-pitch outcomes (swings, whiffs, called strikes, contact quality, damage). Every one of those outcomes is a joint product of what the pitcher did, who the batter was, the count, the park, the catcher, and chance. Treating raw outcome rates as if they were a clean measurement of "pitch quality" is the single most common failure mode in this kind of research, and it is exactly what Eephus's own pitcher-eWAR stacks were built to avoid at the run-value level (see `definitions/PITCHER_EWAR.md`, `definitions/MILB_PITCHER_PROJECTION.md`). This contract exists so the same discipline carries into pitch-level work.

## Four levels that must be kept distinct

**A. Observed pitch effectiveness** — what actually happened on pitches thrown: swing rate, whiff-given-swing, called-strike-given-take, chase, contact quality given contact, ground-ball tendency, damage given contact, count progression, total run value. This is raw signal, unadjusted for context.

**B. Context-adjusted effectiveness** — (A) after adjusting for legitimate context: level, league, season, pitch type, batter handedness, pitcher handedness, count, batter quality, location, velocity, park (use `definitions/MILB_PARK_FACTORS.md` — do not re-derive park factors, reuse the authoritative export), catcher where identifiable, previous-pitch context, organization, tracking source. Adjusting for context is not optional — a pitcher who happens to face weaker MiLB competition or pitch in a bandbox park will look artificially better or worse in (A) alone.

**C. Stable pitcher-by-pitch-type signal** — the component of (B) that survives split-half reliability, month-to-month reliability, year-to-year reliability, same-level forward prediction, promotion-seam validation, and future-MLB validation, with uncertainty-aware shrinkage applied throughout. Most of the variance in (A) and even (B) is noise; only the part that is demonstrably repeatable belongs in (C).

**D. Latent arsenal quality** — a research construct built on top of (C), justified by stable signal, whatever limited physical information is actually available (velocity, sparse location data — not invented movement data), interaction effects between pitch types, and evidence of future portability (does it predict outcomes at a higher level, or after a promotion, better than raw stats alone?).

Collapsing any of these into an earlier one — calling (A) "pitch quality," or calling all of (B)'s residual "stuff" — is the failure this contract exists to prevent.

## Explicit prohibitions

The future builder must not:

- Label raw run value (A) as pitch quality.
- Label all residual performance after context adjustment (B) as "pitch shape" without demonstrating it survives (C)'s reliability program.
- Interpret a velocity residual as evidence of movement without independent movement data — Eephus has no MiLB movement feed (see `[[project_platoon_rebuild]]`-adjacent finding: "pitch-environment mechanism real but undeployable — no MiLB movement feed" is a documented Eephus-wide limitation, not specific to this charter).
- Hide command (location precision) inside a single "Stuff+"-like score such that it can't be separately audited.
- Ignore sequencing (treating a pitcher's pitch mix as if each pitch were thrown in isolation, when count state and prior-pitch context measurably affect outcomes).
- Treat millions of individual pitches as independent observations when computing significance or reliability — they are clustered by pitcher, by game, by season, and pretending otherwise inflates apparent confidence.
- Use arbitrary sample-size cutoffs (e.g. "100 pitches minimum") without empirically testing where reliability actually stabilizes for each channel.
- Issue a production recommendation ("this challenger should replace/augment the champion") from retrospective in-sample fit alone — see `BENCHMARK_REQUIREMENTS.md` for the required out-of-sample comparison ladder.

## Required comparisons

See `BENCHMARK_REQUIREMENTS.md` for the full ladder (A. velocity only → I. Eephus stack + raw new-model features) and the five required interpretive comparisons (value of shrinkage, value of context adjustment, value of the latent architecture, incremental value to Eephus, and whether the constructed metric beats the raw feature bundle it's built from).

## Required reliability program

Before any latent pitch-quality construct (D) is taken seriously, the builder must produce:

- Empirical stabilization curves (reliability vs. sample size, measured directly — not assumed from a rule of thumb).
- Pitcher-clustered uncertainty (standard errors that account for repeated observations per pitcher, not naive per-pitch SEs).
- Effective sample size per pitcher-pitch-type-level cell.
- The actual amount of shrinkage applied, and why.
- Reliability broken out by level (MLB vs. AAA vs. AA/High-A/Low-A — Eephus's own pitcher-eWAR stacks already show contact-signal reliability collapses below AAA; a pitch-quality model should expect the same and measure it, not assume it away).
- Reliability broken out by pitch family.
- Reliability before vs. after a level promotion — this is the single most decision-relevant reliability check, since the whole point of a portable pitch-quality metric is that it should still mean something across a promotion seam.

## Required negative controls

To distinguish real signal from artifacts of the modeling process, the builder must run and report:

- Randomized pitcher identity (does the model still "find" structure with shuffled pitcher labels?).
- Randomized pitch type within valid strata.
- Shuffled season ordering.
- A level-only model (no pitcher information at all — how much of the apparent signal is just level effects?).
- An organization-only model (how much is just which org's development system a pitcher came from?).
- A tracking-source-only model (does data-collection-system identity alone predict the outcome — a red flag for measurement artifact, not pitcher skill).
- A park-only model (how much of the apparent "pitch quality" is actually just park factor leaking through — reuse `definitions/MILB_PARK_FACTORS.md`'s export to check this directly rather than re-deriving park effects).
- A sample-size-only model (does raw pitch count alone predict the metric — a sign of survivorship/opportunity bias rather than skill).
- League-average velocity replacement (substitute every pitcher's velocity with the league mean — how much apparent signal disappears?).
- Feature-family ablations (remove each input family — velocity, location, count context, sequencing — one at a time and measure the drop).

Any negative control that "passes" (i.e., a control built from information the model wasn't supposed to be capturing meaningfully still predicts the outcome nearly as well as the real model) is a signal that the real model's apparent skill is at least partly artifact, not signal, and must be reported as such — not quietly dropped from the writeup.

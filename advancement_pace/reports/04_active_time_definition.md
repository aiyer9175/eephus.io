# 04 — Active Development Time

**Core (published) definition: active professional seasons = count of seasons with at
least one meaningful assignment (PA ≥ 30 at some level), as of the scoring season.**

This is the observed-play definition. It automatically excludes, with no auxiliary
injury feed and no over-engineering:
- the cancelled 2020 MiLB season (zero rows exist; asserted in tests),
- full-season injuries, restricted-list years, visa-delay years, any season without
  meaningful play — none of them count as development time.

## Research (comparison) version — calendar time
`calendar_years = season − first_meaningful_season + 1 − (1 if the span crosses 2020)`.

Comparison on the scored population: spearman(active, calendar) = **0.992**; the two are
equal on 92.9% of rows. The definitions diverge only for injury/inactivity-interrupted
careers — exactly where the core definition is the fairer description (a player who
missed 2023 entirely did not have advancement opportunity in 2023). The core version is
also the more reproducible one (no IL feed dependency), so it is the published basis.

## Known, bounded trade-off: the 2020 cohort
Players active in both 2019 and 2021 average AP+ **101.65** on their 2021+ rows vs
**100.32** for others — a ~1.3-point artifact: development that happened during the
lost year (age growth at alternate sites/instructs) shows up as pace per *active*
season. The calendar version would instead *penalize* the same players for a year no
one could advance in. The artifact is small (≈0.13 SD), one-directional, and documented;
2020-straddling careers get a display note in the card spec (13).

Per-season availability weighting (partial-season IL) was **not** built: MiLB IL data
at season-line grain is unreliable, and the charter explicitly warns against
over-engineering unavailable injury data.

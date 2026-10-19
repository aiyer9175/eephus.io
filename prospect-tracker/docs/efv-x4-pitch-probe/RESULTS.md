# StatsAPI pitch tracking below Triple-A: results in plain language

Generated 2026-10-15T19:09:09Z by `tools/efv_x4_pitch_probe.py`. Registration `docs/efv-x4-pitch-probe/REGISTRATION.md`, read the same day as an owner-waived early read (EW3-5). Tables: `docs/efv-x4-pitch-probe/COVERAGE.md`. Nothing served moves.

## What was asked

Savant's public minor-league data covers only Triple-A (from 2022) and the Florida State League (from 2021). The question was whether MLB's free game feeds (StatsAPI) carry pitch tracking (velocity, spin, movement, extension, location, exit velocity and launch angle) for Double-A, High-A and Single-A games, in which seasons and parks, and if so whether that data tells us anything about prospects that consensus does not.

## What we found

- AA: share of sampled games with release speed on 80 percent or more of pitches: 2021 0%, 2022 0%, 2023 0%, 2024 0%, 2025 0%, 2026 0%.
- A+: share of sampled games with release speed on 80 percent or more of pitches: 2021 0%, 2022 0%, 2023 0%, 2024 0%, 2025 0%, 2026 0%.
- A: share of sampled games with release speed on 80 percent or more of pitches: 2021 30%, 2022 30%, 2023 27%, 2024 30%, 2025 30%, 2026 30%.
- Triple-A (the control): 2021 0%, 2022 37%, 2023 100%, 2024 100%, 2025 100%, 2026 100%.
- Double-A and High-A: no sampled game in any season 2021 to 2026 carries release speed, spin, movement, extension, plate location or exit velocity (720 games, 360 venue-seasons). The feeds hold only the pitch call, the count, the batted-ball type and the stringer's pixel click.
- Single-A: the tracked games are all in the Florida State League (named Low-A Southeast in 2021; 106 of its 120 sampled games tracked); the other Single-A leagues (California League, Carolina League, Low-A East, Low-A West) carry none. So Single-A cells sit near the Florida State League's share of Single-A games and never reach the 50 percent bar.
- Florida State League venues with an untracked sampled game: Jackie Robinson Ballpark, The Ballpark of the Palm Beaches.
- Of the 974 untracked sub-AAA games, the largest share of pitches with a release speed is 0%: tracking is all or nothing by park.
- The Triple-A control: tracking in 0 parks in 2021, 11 of 30 sampled parks in 2022, and every sampled park from 2023. Savant's one probe day of 2022 (2022-06-15) served 19 home parks across Triple-A and the Florida State League, so in 2022 StatsAPI is, if anything, thinner than Savant, not richer.
- Savant's census of 2026-10-14 reads: "2019: nothing served (probe 2019-06-12); 2021: A; 2022: AAA, A; 2023: AAA, A; 2024: AAA, A; 2025: AAA, A; 2026: AAA, A; never served: AA, A+; 2020 had no MiLB season". StatsAPI tracks the same levels and the same Single-A league, so it adds no tracked level or league over Savant's public minors data (the tracking-era head already reads the Florida State League and Triple-A from Savant).

## The descriptive signal read

Not run: coverage below AAA is not REAL by the section 3 rule. The registration stops the probe here: no aggregate is built and no outcome is read, because the data does not exist below Triple-A on this source.

## What happens next

- Nothing ships and nothing served moves. The registration's rule stops the probe at the coverage tables: no aggregate is built and no outcome is read, because the data does not exist below Triple-A outside the Florida State League, which the tracking-era head already reads from Savant.
- EFV_X3_POOLED_MODEL should take Double-A and High-A as box-score and pitch-call levels only (chase and zone contact need a measured location, which does not exist there; whiff, called-strike and contact rates need only the pitch call, and the eFV v4 playByPlay cache already holds the calls of the 2021 to 2025 games).
- A new tracked level would show up in this same sample at no cost: rerun `python tools/efv_x4_pitch_probe.py --probe` after a future season (the cache keeps every sampled feed), and a level that turns VELO-COVERED re-registers before any read.

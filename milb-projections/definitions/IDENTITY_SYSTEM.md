# Identity System

## What it is

The single authoritative player-identity mapping in Eephus: `eephus_identity.parquet`, built by `career_outcome_plus/build_eephus_identity.py`. 10,679 rows, one row per player, current-state only.

## Fields (real columns, confirmed against the live parquet)

`eephus_pid, mlbam_id, statcast_id, milb_id, fangraphs_id, bbref_id, retro_id, name, organization, current_level, bats, throws, dob, primary_position, secondary_positions, is_predebut`, plus a parallel set of `*_coverage` boolean flags (`fangraphs_coverage, bbref_coverage, retro_coverage, dob_coverage, org_coverage, primary_position_coverage, bats_coverage, name_coverage, throws_coverage, secondary_positions_coverage, bio_coverage`).

- `eephus_pid` (format `E%07d`) is **minted by ascending-mlbam_id sort at build time, not a stable long-lived external identifier** — it can shift if the build re-runs over a different player universe. Join on `mlbam_id` (or `statcast_id`/`milb_id`, both aliases of it in this file) for anything that needs to survive a rebuild.
- `throws` and `secondary_positions` are placeholder columns, always null — "not on disk" per the source, not a data-quality defect specific to any player.
- `organization` is a single free-text field (current team name), not a structured team/affiliate/league/park join.

## What this system does NOT provide (documented, not fabricated)

- **No team_id, affiliate_id, parent_org_id, league_id, or venue/park_id.** Team/park/league mapping is a separate, disjoint system (`milb_pitcher_ewar/pipeline/build_infrastructure.py` → `milb_affiliate_mapping.parquet` etc.) that is never joined to player identity anywhere in the codebase, and which is classified `NOT_NEEDED` for this handoff because it's directly reconstructable from the public MLB Stats API (season/team/affiliate/league/venue reference data).
- **No effective-dating.** No `effective_start`/`effective_end`/`as_of` field exists anywhere. This file cannot answer "what team/level was this player on as of date X" — it can only answer "what is this player's current organization/level as of the last build."
- **No mixed-season flag, no name-correction/alias-history audit trail.**

## Historical / point-in-time joins

**Not supported.** This is a hard limitation, documented here rather than worked around. Any consumer that needs "player's team/level as of a specific date" cannot get it from this file or from the team/affiliate mapping (which is season-grain, not date-grain, and isn't linked to player identity at all). See `TEMPORAL_INTEGRITY.md`.

## Collision / ambiguity handling

The builder resolves duplicate/many-to-one keys via `sort_values(...).drop_duplicates(key, keep="last")` in four places (Chadwick register, career panel, batter leaderboards, MiLB xWAR projection), **with no logged count of how many rows were collapsed and no warning emitted.** This is a documented gap: silent "last wins" resolution, not flagged collisions. A future consumer relying on this file for a critical join should independently check `df.duplicated(subset=["mlbam_id"]).sum()` rather than assume zero collisions were silently dropped upstream (at the time of this export, 0 duplicate `mlbam_id` rows were observed in the output file itself — but the upstream collapse logic that produced that zero is not observable from the output alone).

## Redaction applied by this package's export

`dob` (full year-month-day birthdate) is **truncated to birth-year only** before export — see `adapters/export_identity.py`. Full birthdate precision is more granular than what's typically published for public athletes and is not needed for age-on-date calculations at year granularity; this redaction is applied unconditionally, not configurable, per `PUBLICATION_POLICY.md`.

## Feature / label / benchmark classification

The entire file is **context/join-key material** — an identity mapping is never a feature or a label for a pitch-quality model. `is_predebut`, `current_level` are useful conditioning context (e.g., excluding predebut players from an MLB-only comparison).

## Known limitations

No historical joins. Silent collision handling. No team/park/league join. `eephus_pid` is not stable across rebuilds — always join on `mlbam_id`.

# Phase 1 Pilot Scope

## Why a pilot, and why venue-stratified

A full-scope data audit (every level, every season, every game) is a large undertaking whose value depends entirely on whether the audit methodology is sound. Before committing to that scale, a bounded pilot validates the approach and — critically — surfaces the actual shape of the coverage problem, which turned out to be different from what was assumed going in.

Before writing any pull code, a single live game was checked per level (2025-06-15) as a sanity probe:

| Level | Venue | Pitch type | Velocity | Movement (pfx/spin/break) | Zone/location | Hit data (EV/LA) |
|---|---|---|---|---|---|---|
| AAA | Coolray Field | 294/294 | 294/294 | 294/294 | 294/294 | 59/59 |
| AA | Prince George's Stadium | 0/308 | 0/308 | 0/308 | 0/308 | 0/58 |
| High-A | AdventHealth Stadium | 0/280 | 0/280 | 0/280 | 0/280 | 0/62 |
| Low-A | TD Ballpark | 167/167 | 167/167 | 167/167 | 167/167 | 29/29 |

Two things fall out of this single-game probe:

1. **The public MLB Stats API carries full Statcast/Trackman-grade pitch data where it's present** — pitch type, velocity, `pfxX`/`pfxZ` movement, spin rate/direction, release extension, plate location, and batted-ball exit velocity/launch angle. This is richer than `milb-projections/PITCH_QUALITY_RESEARCH_CONTRACT.md`'s working assumption ("Eephus has no MiLB movement feed" — true for Eephus's own internal systems, not true of the public feed this research pulls from directly).
2. **Coverage looks like an all-or-nothing, venue-level property, not a level-level one.** AAA and Low-A were both 100% covered; AA and High-A were both 0% covered, in this single-game sample. A level-only audit (typical of Statcast-era research assumptions — "AAA has it, lower levels don't") would completely miss this pattern. A pilot stratified only by level would silently average venues with full tracking installs together with venues that have none, and report a misleading fractional coverage number for the level as a whole.

This is exactly the "do not assume every MiLB level supports the same architecture" instruction in the governing charter — evidence over assumption. The pilot is designed to test the venue-vs-level hypothesis properly, not just confirm the one-game probe.

## Sampling design

- **Season**: 2025 — the most recent fully completed MiLB season as of this research (2026-07-19; the 2026 season is in progress).
- **Levels**: AAA (`sportId=11`), AA (`sportId=12`), High-A (`sportId=13`), Low-A (`sportId=14`) — the four levels with a public Eephus pitcher-eWAR champion counterpart (CPX/DSL excluded, matching `milb-projections/manifests/BENCHMARK_MANIFEST.yaml`'s own scope).
- **Venue enumeration**: per level, pull the full 2025 season schedule (one lightweight API call per level) and extract the distinct set of venues that hosted games — roughly 30 per level, ~120 total across all four.
- **Games per venue**: 3 games per venue, spread across early (April/May), mid (June/July), and late (August/September) season, to catch mid-season tracking installs or outages rather than assuming a venue's coverage is constant all year.
- **Total pilot size**: roughly 300–360 game-feed pulls.

## Pull mechanics

- Endpoint: `GET https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live` (public, no auth required — confirmed reachable from this environment).
- Rate limit: ~0.3–0.5s between calls. At this pace the full pilot completes in well under an hour of wall-clock API time.
- Caching: every raw response is saved to `data_cache/{level}/{gamePk}.json` and never re-fetched if already present — the pull is resumable and idempotent.
- Nothing under `data_cache/` is committed (see `.gitignore`); it's regenerable from the scripts at any time and would otherwise bloat git history with public, non-authoritative data.

## Fields extracted per pitch

From each `playEvents` entry where `isPitch: true`:

- **Identity**: `details.type.code`/`description`, `details.typeConfidence`
- **Velocity**: `pitchData.startSpeed`, `pitchData.endSpeed`
- **Movement**: `pitchData.coordinates.pfxX`/`pfxZ`, `pitchData.breaks.breakVertical`/`breakVerticalInduced`/`breakHorizontal`/`breakAngle`/`breakLength`
- **Spin**: `pitchData.breaks.spinRate`/`spinDirection`
- **Release**: `pitchData.extension`, `pitchData.coordinates.x0`/`y0`/`z0`/`vX0`/`vY0`/`vZ0`/`aX`/`aY`/`aZ`
- **Location**: `pitchData.coordinates.pX`/`pZ`, `pitchData.zone`, `pitchData.strikeZoneTop`/`strikeZoneBottom`
- **Timing**: `pitchData.plateTime`
- **Count/sequence**: `count.balls`/`strikes`/`outs`, `pitchNumber`
- **Outcome**: `details.call.code`/`description`, `details.isStrike`/`isBall`/`isInPlay`

From each play event's `hitData` (batted balls):

- `launchSpeed`, `launchAngle`, `totalDistance`, `trajectory`, `hardness`, `location`, `coordinates`

Plus game-level context carried on every row: `gamePk`, `level`, `venue.id`/`name`, `officialDate`, batter/pitcher `id` and handedness from the play's `matchup`.

## What this pilot does not attempt

- No real Eephus champion-benchmark values (park factors, pitcher eWAR) — schema-only, per `DECISION_LEDGER.md` #1.
- No reliability/stabilization curves, no negative controls, no promotion-seam validation — meaningful only once the coverage findings are in.
- No pitch-quality modeling of any kind. This is a data audit, not a model build.

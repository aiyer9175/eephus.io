# Module 0 — Data Pull / Join Validation Report

## A. Prospect tracker DB
- players: 2769 rows, 2769 unique keys
- missing fields: {'position': 12, 'org': 0, 'birth_date': 83}
- **FLAG** 6 mlbam_ids map to >1 player_key (tracker name-collision bug, e.g. brennen_davis/brendon_davis) — dropping 12 ambiguous bridge rows: [679883, 680695, 687069, 699024, 806985, 829038]
- mlbam bridge: 2576/2769 tracker players have an mlbam_id (93% coverage)
- 193 tracker players lack mlbam_id (mostly never-rostered/intl)

- snapshots: 7588 rows, sources: {'auto_detect': 915, 'espn': 250, 'just_baseball': 100, 'mlb_pipeline': 5996, 'mlb_pipeline_international': 27, 'tjstats': 300}
- snapshot date ranges:
                                   min         max
source                                            
auto_detect                 2018-08-21  2026-05-26
espn                        2025-08-20  2026-05-22
just_baseball               2026-03-04  2026-03-04
mlb_pipeline                2021-01-22  2026-01-22
mlb_pipeline_international  2026-05-26  2026-05-26
tjstats                     2026-01-22  2026-05-17
- snapshot scopes: {'org': 5397, 'debut': 915, 'list': 650, 'top100': 599, 'international': 27}
- tool grade fields present: ['cb', 'ch', 'cmd', 'ct', 'fb', 'field', 'game_pwr', 'hit', 'pitch_sel', 'raw_pwr', 'sl', 'speed', 'throw']
- grades_long saved: (7588, 24), 96% rows mlbam-linked
- org mismatch (players vs latest snapshot): 0/2769 (expected: trades since last snapshot)

- roster_status parsed: (2769, 11); on_40_man coverage 100%, options_remaining coverage 100%
- NOTE roster_status is a current snapshot (fetched_at 2026-05-27); historical option/40-man state must come from transactions — timestamp-validity flagged for leakage audit

## B. Deep history (projection_engine)
- deep_mlb: (24057, 26), seasons 2000-2026, 5465 players, dup (batter,season,sport) rows: 0
- deep_minors: (38416, 26), seasons 2008-2026, 10677 players, dup (batter,season,sport) rows: 0

## C. Talent layer (swing_plus stat_projections)
- stat_projections: (1827, 10), seasons 2023-2026, dup rows: 0

## D. Cross-source joins
- tracker∩deep_mlb: 544 players
- tracker∩deep_minors: 1043 players
- stat_projections∩deep_mlb(2024+): 675/700 projection players matched

## Verdict
1 flags raised (see above). Sources usable with noted caveats.

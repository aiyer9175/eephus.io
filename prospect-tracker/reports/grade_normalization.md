# Cross-source grade normalization (Phase 8, Tier 2)

_Generated 2026-07-04 for cycle 2026. Analytical layer: the live consensus is unchanged; this is reproducible and diff-able._

Each source's grade distribution is quantile-mapped onto FanGraphs FV on the OVERLAP (players graded by both source and FanGraphs), per role per cycle. Mapping on the shared players separates a genuine scale bias from a coverage difference, so a top-only outlet is not called hot just for skipping the low tiers. No scale equivalences are assumed; the mappings are data-derived.

## Source drift vs FanGraphs (overlap, cycle 2026)

median shift = FanGraphs median minus the source median on the shared players (negative = the source grades higher than FanGraphs).

### Hitter

| source | overlap n | source median | FG median | shift | pooled | flag |
| --- | --- | --- | --- | --- | --- | --- |
| baseballamerica_statcast_by_age | 29 | 40.0 | 40.0 | 0.0 |  |  |
| espn | 61 | 55.0 | 50.0 | -5.0 |  | MATERIAL |
| fangraphs | 665 | 40.0 | 40.0 | 0.0 |  |  |
| just_baseball | 83 | 50.0 | 50.0 | 0.0 |  |  |
| mlb_pipeline | 411 | 45.0 | 40.0 | -5.0 |  | MATERIAL |
| mlb_pipeline_international | 37 | 50.0 | 40.0 | -10.0 |  | MATERIAL |
| performance_ingest | 2 | 35.0 | 35.0 | 0.0 |  |  |
| tjstats | 82 | 50.0 | 50.0 | 0.0 |  |  |

### Pitcher

| source | overlap n | source median | FG median | shift | pooled | flag |
| --- | --- | --- | --- | --- | --- | --- |
| espn | 42 | 50.0 | 50.0 | 0.0 |  |  |
| fangraphs | 720 | 40.0 | 40.0 | 0.0 |  |  |
| just_baseball | 42 | 50.0 | 50.0 | 0.0 |  |  |
| mlb_pipeline | 347 | 45.0 | 40.0 | -5.0 |  | MATERIAL |
| mlb_pipeline_international | 1 | 45.0 | 35.0 | -10.0 |  | MATERIAL |
| performance_ingest | 6 | 35.0 | 40.0 | 5.0 |  | MATERIAL |
| tjstats | 54 | 50.0 | 50.0 | 0.0 |  |  |

## Consensus: before vs after normalization

Over 824 players graded by 2+ sources in 2026, the normalized consensus moves by mean -0.219, median 0.0 FV (p10 -2.5, p90 0.0, max abs 7.5). Most players are unchanged; the moves concentrate on players graded by a materially hot or cold source.

### Top 20 consensus movers

| player | role | raw consensus | normalized | diff | sources |
| --- | --- | --- | --- | --- | --- |
| andri_hidalgo | pitcher | 45.0 | 37.5 | -7.5 | 2 |
| francisco_renteria | hitter | 53.33 | 46.67 | -6.67 | 3 |
| angeibel_gomez | hitter | 51.67 | 45.0 | -6.67 | 3 |
| johenssy_colome | hitter | 51.67 | 45.0 | -6.67 | 3 |
| wandy_asigen | hitter | 51.67 | 46.67 | -5.0 | 3 |
| ronny_munoz | hitter | 45.0 | 40.0 | -5.0 | 2 |
| dawvris_brito | hitter | 42.5 | 37.5 | -5.0 | 2 |
| svert_reinoso | hitter | 42.5 | 37.5 | -5.0 | 2 |
| juan_parra | hitter | 42.5 | 37.5 | -5.0 | 2 |
| luke_hill | hitter | 40.0 | 45.0 | 5.0 | 2 |
| quentin_young | hitter | 42.5 | 47.5 | 5.0 | 2 |
| isaias_suarez | hitter | 42.5 | 37.5 | -5.0 | 2 |
| ariel_roque | hitter | 45.0 | 40.0 | -5.0 | 2 |
| gregory_pio | hitter | 40.0 | 35.0 | -5.0 | 2 |
| richard_matic | hitter | 37.5 | 42.5 | 5.0 | 2 |
| randy_arias | hitter | 40.0 | 35.0 | -5.0 | 2 |
| jaiden_lo_re | hitter | 40.0 | 45.0 | 5.0 | 2 |
| ricky_duran | hitter | 40.0 | 35.0 | -5.0 | 2 |
| kendri_fana | pitcher | 40.0 | 35.0 | -5.0 | 2 |
| pedro_gomez | hitter | 42.5 | 37.5 | -5.0 | 2 |

## Reproducibility + identity

- Recomputation is deterministic: True.
- FanGraphs maps to itself (identity): True.
- Material-drift sources flagged: espn, mlb_pipeline, mlb_pipeline_international, performance_ingest.


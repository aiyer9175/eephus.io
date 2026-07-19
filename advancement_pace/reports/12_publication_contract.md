# 12 — Publication Contract

**Artifact:** `data/advancement_pace_public.parquet` — 45,627 rows, 14,748 players,
grain player_id × season (as-of end of season), 2009–2026 entries, 2,478 rows at the
2026 as-of. Staged only; **not wired into the live site** (a later frontend charter owns
that step — the existing publish architecture required no staging output here).

## Schema (charter schema, complete)
`player_id, season, as_of_date, advancement_pace_plus, advancement_percentile,
raw_advancement_pace, expected_peer_pace, advancement_residual, sample_quality,
active_pro_seasons, meaningful_assignments, meaningful_promotions, starting_level,
current_level, position_group, entry_pathway, reference_population,
methodology_version, data_version, generated_at, stat_type, model_eligible`
plus internal companions `advancement_pace_plus_internal` (uncapped stabilized),
`advancement_pace_plus_raw_internal` (unshrunk), and `name` for QC.

Required constants on every row: `stat_type="descriptive"`, `model_eligible=False`.

## Contracts (`contracts.py`, enforced fail-closed in `publication.py` + pytest)
- full schema present; no forbidden ambiguous column names;
- player_id × season unique, non-null; methodology_version semver;
- public score inside display cap 70–130; percentile in 0–100;
- tier vocabulary closed; level vocabulary closed;
- Insufficient rows carry no score; zero 2020 rows; left-censored 2008 entries absent.

## Provenance
`data/provenance_manifest.json`: artifact SHA, row/player counts, methodology +
level-map versions, generation timestamp, all six input files with SHA-256 prefixes,
permitted and forbidden consumer lists. `data/schema.json` carries dtypes, cap, scale
copy, and the meaningful-PA threshold. `data/lineage.json` regenerates each build.

## Versioning
- `methodology_version` (1.0.0): any change to threshold, ladder, baseline, scale.
- `LEVEL_MAP_VERSION` (1.0.0): ladder/mapping changes.
- `data_version`: derived from input SHAs each refresh.

Rebuild: `python build_all.py` (venv `~/swing_plus/.venv`) — exits 2 on any contract
failure, publishing nothing partial.

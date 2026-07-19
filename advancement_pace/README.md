# Advancement Pace+ (descriptive)

**How quickly has this player advanced through the affiliated minor-league ladder,
relative to comparable players?** 100 = typical peer-adjusted pace; 110 ≈ one standard
unit faster; 90 ≈ one slower. Percentile published alongside.

**This is a descriptive statistic, not a projection.** It describes the path a player
has already taken. It does not claim that advancing quickly causes future success and
it must never feed Career Outcome+, p_reach, xWAR, xFV, eFV, eWAR, eoWAR, readiness,
opportunity, routing, or any predictive/valuation head. Every artifact row carries
`stat_type="descriptive"`, `model_eligible=false`; `tests/test_isolation.py` enforces
the boundary fail-closed in every build.

## Method (methodology 1.0.0 — reports/ for full detail)
- Level ladder: Rk(1) A(2) A+(3) AA(4) AAA(5); MLB is a terminal event, not a rung.
- Meaningful assignment: ≥30 PA at a level-season. Active time: seasons with meaningful
  play (2020 cancelled season can never count).
- Raw measure: **area pace** — mean PA-weighted ladder height per active season.
- Peer baseline: joint fixed effects — starting_level × experience cells + additive
  entry-age / era / position-group / entry-pathway dummies. All margins flat.
- Score: 100 + 10 × standardized residual, shrunk toward 100 for thin samples
  (k=1 on meaningful assignments), displayed capped 70–130, tiered
  Insufficient/Early/Developing/Established.

## Build
```
~/swing_plus/.venv/bin/python build_all.py    # exit 2 = contract failure, nothing publishes
```
Pipeline: `build_history.py` → `publication.py` (scores + artifact + contract) → pytest.
Output: `data/advancement_pace_public.parquet` + `schema.json` + `provenance_manifest.json`
+ `example_players.json`.

## Files
`level_map.py` ladder (versioned) · `build_history.py` Phase 1–2 · `raw_pace.py`
Phase 3–5 · `peer_baseline.py` Phase 6–7 · `score.py` Phase 8–9 · `publication.py`
Phase 12 · `contracts.py` schema contracts · `tests/` contract + isolation ·
`reports/01…14 + FINAL_ADVANCEMENT_PACE_RULING.md`.

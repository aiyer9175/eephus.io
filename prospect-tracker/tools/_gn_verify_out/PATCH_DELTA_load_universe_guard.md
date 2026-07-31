# Required delta to the survivorship lane's `_load_universe` patch

The lane's patch extends the universe from `debuts.json` AND `inactive.json`.
That is correct and necessary, but it must NOT admit `inactive.json` rows raw.
Every record in `inactive.json` has `status="active"`, `debut_date=None` and no
`career_war` block (verified: 2,409 of 2,409 on all three), so
`source_backtest._outcome()` scores every restored row as
`debuted=False, war=0.0`. Some of those rows are real MLB players.

Measured on the current tree (base years 2017-2023, any rater grade):
  restored player-years            3,200
  MLB-exposed (StatsAPI sport-1)      58  (1.81%; 3.1% in 2021)
  distinct players                    23  (adolis_garcia, kodai_senga,
                                           masataka_yoshida, ronel_blanco,
                                           justin_topa, jose_de_leon, ...)
  cross-slice mlbam collisions        11  (9 inactive-vs-timeseries,
                                           2 inactive-vs-debuts)
LOWER BOUND: only 726 of 2,409 inactive records carry an mlbam_id at all, so
70% of the restored pool cannot be screened by this route.

`efv_dataset.build_matrix` already guards this exact pool (`_mlb_exposed_ids`,
the F1 bust-loop guard, efv_dataset.py:691-703). Carry the same guard.

## Delta (apply on top of the lane's `_load_universe` rewrite)

```python
def _load_universe(data_dir: Path = DATA_DIR) -> list[dict]:
    players: list[dict] = []
    ts_path = data_dir / "timeseries.json"
    if ts_path.exists():
        ts = json.loads(ts_path.read_text(encoding="utf-8"))
        players.extend(ts.get("players") or [])
    deb_path = data_dir / "debuts.json"
    if deb_path.exists():
        d = json.loads(deb_path.read_text(encoding="utf-8"))
        players.extend(d if isinstance(d, list) else (d.get("players") or []))
    # SURVIVORSHIP REPAIR (2026-07-25). Players released or aged out WITHOUT
    # debuting live in inactive.json and were silently absent, so every cohort
    # read 98-100% debut back to 2013. Restoring them moves the 2017 Pipeline
    # cohort from n=427 debut 0.995 to n=940 debut 0.452.
    #
    # F1 GUARD, mirrored from efv_dataset.build_matrix: an inactive.json record
    # has debut_date=None and no career_war by construction, so _outcome()
    # would score it 0 WAR / never-debuted. 23 of these are real MLB players
    # (adolis_garcia, kodai_senga, masataka_yoshida, ronel_blanco, ...) whose
    # debut the upstream detector missed, and 11 more collide on mlbam_id with
    # a record already in timeseries.json or debuts.json. Admitting them raw
    # trades one survivorship defect for a smaller label-corruption defect of
    # the same family. Drop them; do not relabel them here.
    ina_path = data_dir / "inactive.json"
    if ina_path.exists():
        ina = json.loads(ina_path.read_text(encoding="utf-8"))
        ina = ina if isinstance(ina, list) else (ina.get("players") or [])
        seen_ids = {str(p["mlbam_id"]) for p in players
                    if p.get("mlbam_id") is not None}
        try:
            from efv_dataset import _mlb_exposed_ids
            exposed = _mlb_exposed_ids()
        except Exception:                      # caches cold: fall back to the
            exposed = set()                    # cross-slice check alone
        for rec in ina:
            mid = rec.get("mlbam_id")
            if mid is not None:
                if str(mid) in seen_ids:
                    continue                   # identity collision, not a bust
                try:
                    if int(mid) in exposed:
                        continue               # real MLB exposure, not a bust
                except (TypeError, ValueError):
                    pass
            players.append(rec)
    return players
```

## Also correct in the lane's writeup

- Null #6 ("double-counting risk nil, the three slices are pairwise disjoint")
  was measured on `player_key`. On `mlbam_id` there are 11 cross-slice
  collisions, 9 of which the patch would duplicate into the cohort.
- "The 7 absent [from the eFV matrices] are excluded by the F1 guard" is a
  count on their narrower common-set denominator. The MLB-exposed population
  inside `inactive.json` is 46 overall, 23 in resolved base years.

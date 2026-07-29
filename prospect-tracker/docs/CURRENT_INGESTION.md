# Current Ingestion + eFV Provenance (Phase 0)

Written 2026-07-24 as the baseline for the data-sourcing program. Establishes what
eFV already consumes so orthogonality of any new source can be judged against a
known baseline, and locates the residual/coverage holes that set the search prior.

## 1. External sources currently ingested

| source | host | auth | cadence | grain | role |
|---|---|---|---|---|---|
| MLB StatsAPI (load-bearing) | statsapi.mlb.com | none | daily + monthly | player-season / transaction / roster / pitch | ids, transactions, IL, rosters, season stats per level, fielding, self-computed leverage |
| MiLB season stats | statsapi.mlb.com `/stats?...&sportIds=` | none | monthly (cached forever past-season) | player-season | `milb_history.py`; level+season league norms for rate translation |
| Baseball Savant | baseballsavant.mlb.com | none | daily incremental, disk-cached | pitch / player-season | MLB Statcast + minors Statcast (**AAA Hawk-Eye 2023+ only**) |
| FanGraphs board | fangraphs.com | none (but Cloudflare-blocks scripted fetch) | manual CSV drops (step 0b) | player | consensus FV + tool grades + TrackMan-derived board fields |
| TJStats top-100 | tjstats (Thomas Nestico) | none | daily point-in-time | player | one consensus-component board; append-only history |
| MLB Pipeline | mlb.com/prospects | none | daily boards + per-team Top 30 | player | consensus-component FV + org lists; draft + international lists |
| Spotrac | spotrac.com | none | monthly best-effort | player | IFA signing bonuses + contracts |
| NCAA D1 | stats.ncaa.org | none | monthly (draft window) | player-season / box | college box scores for draft prospects (`college_stats.py`) |

Join spine: **MLBAM player id is primary**, with FanGraphs id / slug (`player_key`) as
satellites. Amateur + international players enter scouting sources before they exist in
MLBAM (the hard case).

## 2. eFV feature matrix + provenance

eFV trains on **realized first-6-MLB-season summed bWAR** (KM-censored for unresolved
cohorts). Two matrices: `data/xfv_hitter_matrix.json` (1,933 rows: 845 debuted + 1,088
busts) and `data/xfv_pitcher_matrix.json`. The hitter model feature set
(`efv_model._FEATURES_HIT`) and each feature's source:

| feature | provenance | matrix coverage |
|---|---|---|
| `fv` (consensus_fv_raw) | FG + MLB Pipeline + TJStats consensus, strictly pre-outcome vintage | 1933/1933 (100%) |
| `fv_fangraphs`, `fv_mlb_pipeline` | per-source board FV | 1287 / 1586 (67% / 82%) |
| tool vector (hit/pwr/field/speed/throw) | board tool grades | 1713/1933 (89%) |
| `obp_rel`, `k_rel`, `iso_rel`, `ops_rel` (+peak) | `milb_history` translated rates vs contemporaneous league norms | **904/1933 (47%)** |
| `age_rel_level`, `level_rank`, `n_milb_seasons`, `stale` | `milb_history` final pre-decision season | 904/1933 (47%) |
| `pick_overall`, `bonus_usd` | draft (Pipeline / Spotrac) | **771 / 549 (40% / 28%)** |
| `is_ifa`, `is_college` | acquisition classification | derived |
| `il_stints_pre`, `il_any_pre` | StatsAPI IL / transactions | derived |
| `milb_missing` / `milb_unavailable` | indicator: imputed-zero vs data-cannot-exist | derived |

Baseline bar (consensus_fv_raw Spearman vs realized first-6yr bWAR): debuted-only resolved
**0.3798** (n=463), full-pool resolved 0.2586 (n=1500), KM-censored full pool 0.27.

## 3. The binding coverage hole: identity, not data

MiLB-production coverage is only 47%, and it collapses on the exact cohorts whose labels
are fully resolved:

```
debut 2011-2014:  0%      debut 2019: 83%
debut 2015:       3%      debut 2022: 97%
debut 2017:      52%      debut 2024: 100%
```

Diagnosis (measured, not assumed): the milb-coverage ceiling **exactly equals the mlbam-id
coverage** on every cohort. Every row that has an mlbam id already has its MiLB features;
the 2011-2016 rows are missing features because the debuts.json backfill dropped their
mlbam ids (they are famous MLB players: kris_bryant, byron_buxton, noah_syndergaard...).
StatsAPI *does* serve pre-2014 MiLB season stats (AA hitting returns ~1000+ player-seasons
for every year 2005-2013 - verified live); the local `milb_history` cache simply stopped at
2014 by config, and `efv_dataset._milb_features` hard-stopped its season loop at 2013.

**So the binding constraint is join-key resolution, exactly as runbook section 5 predicts
("ingestion fails at the join, not the fetch"). Identity resolution is the master key: it
unlocks MiLB history + official draft bonus/slot + winter-league + TJ-surgery joins for the
resolved-label cohorts at once.** Data availability was never the blocker.

## 4. Known coverage holes ranked (the search prior)

1. **mlbam ids on 2011-2016 debuted + old bust rows** - unlocks features already in hand.
   Highest information-gain-per-hour because the data is verified and free; only the join
   was missing. (Primary lever of this program.)
2. **Deep pitcher-injury history** - StatsAPI IL is current-status only; no surgery /
   recovery / TJ history. Deep history (1974+) dodges the label-horizon trap. (TJ list.)
3. **MiLB pitch-quality / stuff with low-minors reach** - orthogonal by construction; but
   current-season-only sources are label-horizon-trapped for training.
4. **Amateur / international pre-professional coverage** - thin, and pre-MLBAM identity.
5. **Environment normalization below AAA** - park/league context correlated with org.

## 5. Label-horizon trap (structural, restated)

Newest measurement data (MiLB Statcast 2023+) covers the cohorts whose outcomes are not yet
resolved; the cohorts with resolved 6-year labels (2011-2018) predate that tracking. No
scrape fixes this directly. What helps: filling *ordinary* deep-history features on the
resolved cohorts (lever 1), deep-history risk features (lever 2), and short-horizon
surrogate labels. Sources are therefore weighted by History and Vintage, not Freshness.

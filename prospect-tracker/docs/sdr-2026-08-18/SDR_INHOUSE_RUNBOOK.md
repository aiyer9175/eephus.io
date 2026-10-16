# SDR in-house runbook (task EWAR_SDR_INHOUSE, owner decision EW3-18, 2026-10-15)

Will Cahoon's Defense+ method is in the repo at `BaseballR/defense-plus`. Its raw inputs
lived on his machine. `tools/sdr_inhouse.py` fetches the public ones into `.cache/sdr/`
and runs his stages unedited (a copy of each file, a declared config patch for the season
window and output names only, and his home-directory paths redirected to
`.cache/sdr/home/` through USERPROFILE and HOME). Nothing under `defense-plus/` is written.

## Commands, in order

```
python tools/sdr_inhouse.py fetch    # public inputs -> .cache/sdr/home/defense_plus/data/raw/
python tools/sdr_inhouse.py stages   # 06 per season 2017-2026 (full, no_drs, no_statcast), card per season
python tools/sdr_inhouse.py milb     # 15_milb_translation on cached StatsAPI fielding lines
python tools/sdr_inhouse.py drop     # data/drops/wills/sdr_defense_card__<date>.csv (gitignored)
python sdr_intake.py --stream sdr_defense_card --accept data/drops/wills/sdr_defense_card__<date>.csv
python tools/sdr_eval_gate.py --dry-run   # fixtures with nulls
python tools/sdr_eval_gate.py             # data/sdr_eval.json, data/milb_sdr_eval.json
```

`.cache/sdr/fetch_manifest.json` records url, sha256 of the raw body, rows and fetch time
per file; `.cache/sdr/run_manifest.json` records, per run, Will's file, its sha256, the
patch list, the exit code and the log path. `fetch` never refetches a file it holds
unless `--force`; `drop` rebuilds the same bytes from the same cache.

## Public sources

| File (Will's name) | Source | Seasons | Notes |
|---|---|---|---|
| fg_field_full_<y>.csv | FanGraphs leaderboard JSON, stats=fld, team=0 (one row per player-position) | 2016-2026 | OAA, DRS and parts (rPM, rARM, rGDP, rGFP, rSB, rCERA, rSZ), FRP and parts, UZR (unpublished for 2025 and 2026 at fetch), CFraming, Inn. The library's default User-Agent: a spoofed browser one draws FanGraphs' challenge (fg_leaderboards.py). |
| fg_field_split_<y>.csv | same, team=0,to (split by club) | 2016-2026 | club attribution for the gate's C2 |
| fg_team_pit_<y>.csv | FanGraphs leaderboard JSON, stats=pit, team=0,ts (club totals) | 2016-2026 | R, FIP, IP for the gate's C2 |
| oaa_if_<y>.csv, oaa_of_<y>.csv | Savant outs_above_average CSV | 2016-2026 | Will's 01 URL |
| framing_<y>.csv | Savant catcher_framing page (embedded grid) | 2016-2026 | Will's 01 parser |
| poptime_<y>.csv | Savant poptime CSV | 2016-2026 | |
| arm_<y>.csv | Savant arm-strength CSV | 2020-2026 | Savant publishes from 2020 |
| blocking_<y>.csv | Savant catcher-blocking CSV | 2018-2026 | Will's 25 URL (`?year=`) returns the current season for every year; the adapter uses the season_start/season_end form and refuses a file whose start_year is wrong |
| usage_spine.parquet (his playing_time_model) | built from `.cache/statsapi_field/fld_<y>.json` (StatsAPI MLB season fielding) | 2000-2026 | no DH starts (fielding lines carry none) |
| milb_fielding.parquet | built from `.cache/statsapi_field_season/fld_v2_{11,12}_<y>.json` | 2005-2026 | Will's per-player yearByYear pull, summed the same way; every id pre-cached so his stage makes no request |

## Stage inventory (what each reads; what runs here)

| Stage | Reads | Runs here |
|---|---|---|
| 00 reachability probe | live network probes | no (a probe, superseded by the fetch manifest) |
| 01 reliability | Savant OAA, framing, poptime, arm | inputs fetched; not part of the card |
| 02 FG fielding reliability | fg_field_<y>.csv (his column subset of the same FanGraphs call) | not part of the card |
| 03 reliability vs stability | fg_field_<y>.csv | not part of the card |
| 04 latent range talent | fg_field_full | not part of the card |
| 05 skill composites | fg_field_full, arm, poptime, framing | not part of the card |
| **06 total Defense+** | fg_field_full | **yes, per season 2017-2026, plus the no_drs and no_statcast source-list variants the gate's C5 reads** |
| 07 teammate confounds | fg_field_full, usage_spine | no (not part of the card) |
| 08, 09, 10 jump aging | ofjump_<y>.csv, deep_mlb.parquet, bayesian_curves | no: deep_mlb.parquet and bayesian_curves are his private files |
| 11, 11a, 11a2, 12, 13 position aging, survivorship, migration, retention | fg_field_full, usage_spine, deep_mlb.parquet, bayesian_curves | no: deep_mlb.parquet, bayesian_curves |
| **15 MiLB translation** | usage_spine, StatsAPI MiLB fielding | **yes, on the cached StatsAPI lines** |
| 16 scouting quality | grades_long.parquet, usage_spine, deep_mlb.parquet | no: grades_long.parquet, deep_mlb.parquet |
| 17, 18, 21, 22 career Defense+ | 06 board, deep_mlb.parquet, ofjump, if_oaa_dir, usage_spine | no: deep_mlb.parquet and the Savant jump and directional files |
| 19 infield component aging | arm, if_oaa_dir, deep_mlb.parquet, bayesian_curves | no |
| 20 team needs | sprint speed (his contact_plus), usage_spine, deep_mlb.parquet | no |
| 23 backtest | fg_field_full, deep_mlb.parquet | no |
| 24 frame and body | body.parquet, usage_spine, deep_mlb.parquet | no: body.parquet |
| 25 catcher components | framing, blocking, poptime, deep_mlb.parquet, bayesian_curves | no (aging fit needs his private files); its blocking input is fetched and carried on the card as blocking_runs |
| 26 prospect prior | grades_long.parquet, body.parquet, usage_spine, fg_field_full | no: grades_long.parquet, body.parquet |
| 27 FG grade eval | FanGraphs board pages, fg_field_full, arm | no |
| **build_defense_card** | 06 board, fg_field_full | **yes, per season** |
| build_defense_projection, backtest_projection | 11 aging curves, deep_mlb.parquet, his swing_plus panels | no |

## The drop (contract `sdr_intake.DEFENSE_CARD_CONTRACT`)

One row per player, season and position that 06 ships (300+ innings at the position).
`sdr_runs` is the card's `def_runs` (06 `dplus_runs`), `sdr_runs_sd` its `def_sd`,
`reliability` Inn / (Inn + 269) (06's shrink). Components on the same row, from the
sources, never summed into SDR: `range_runs` DRS rPM, `arm_runs` DRS rARM, `dp_runs` DRS
rGDP, `framing_runs` FanGraphs CFraming, `blocking_runs` Savant catcher blocking runs.
Will's own card columns ride along (`dplus_total`, `d_oaa`, `d_drs`, `d_frp`, `d_framing`,
`def_source`). The drop is gitignored, like every drop; the census
(`data/sdr_census.json`) and the intake ledger (`data/sdr_intake_manifest.json`) record its
sha256.

## What the read decides

The gates `SDR_EVAL_GATE.md` (G-A) and `MILB_SDR_EVAL_GATE.md` (G-C), with their
Amendment 2026-10-15, own every clause. This runbook states inputs and commands only.

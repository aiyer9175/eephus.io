# eWAR v3 inputs and the nightly eWAR cadence (2026-09-11)

Owner decisions answered 2026-09-11 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, ANSWERED):
13 (framing source: pull FanGraphs CFraming), 14a (pitcher replica inputs: pull IFFB and the
FIP park factor from FanGraphs), 10 / D11 (eWAR cadence: NIGHTLY). This note records what
was built, the numbers it was measured on, and exactly what the nightly moves. Nothing in the
FanGraphs half is served, and nothing of FanGraphs' is republished.

## 1. The fetcher: `fg_leaderboards.py`

Three kinds, one request per (kind, season), cached under `.cache/fangraphs/`:

| kind | endpoint | kept |
|---|---|---|
| pitching | `https://www.fangraphs.com/api/leaders/major-league/data` (stats=pit, qual=0, type=8) | IFFB, CFraming, Start-IP, published FIP / WAR / RAR, identity |
| fielding | same endpoint, stats=fld | CFraming, Pos, Inn, identity |
| park_factors | `https://www.fangraphs.com/api/tools/guts/data?type=pf&teamid=0` | the Guts table per club, FIP and Basic (5yr) columns |

- Transport: the library's default User-Agent (a spoofed browser UA is what draws the
  Cloudflare challenge), at most one request per second. The Guts JSON endpoint was found
  2026-09-11 behind the `/tools/guts` page (the old `guts.aspx` redirects there).
- Season-stamped: each file records the season, URL, fetch time, raw-body sha256 and whether
  the season was complete (from November 1 of its year). Complete seasons are never refetched
  without `--force`; the live season expires after 20 hours.
- Refuse on shape change: missing column, wrong season, a page that does not hold the whole
  season, duplicate ids, IFFB above batters faced, a league IFFB rate out of band, framing
  null on every row, an unmapped club, or a park factor outside 75 to 130 raises
  `ShapeChanged` and leaves the previous file alone. The first live pull proved it: 2021's
  Guts table names Cleveland "Cleveland" (between "Indians" and "Guardians"), the fetch
  refused, and the map gained the name.
- Readers (`pitcher_iffb`, `pitcher_framing`, `catcher_framing`, `fip_park_factors`) read the
  cache only and raise `NotCached`. `test_fg_leaderboards.py` fails if any module other than
  the replica eval imports the fetcher.

## 2. The pitcher replica on FanGraphs' inputs (`tools/fwar_replica_eval.py`)

### The finding: FanGraphs charges catcher framing back to the pitcher

IFFB and FanGraphs' own FIP park factor were not enough. Back-solving a park factor per team
from published pitcher WAR gave team values off the Guts FIP factor by 1.0 to 2.6 points on
average (up to 8), with small spread inside a team (median 0.5 to 1.2 points), which is not
what a park factor looks like. 2011 Brewers: implied 95, Guts 103, with Lucroy catching. The
pitcher RAR residual correlated -0.988 (2011) and -0.807 (2025) with the pitching
leaderboard's `CFraming` column: the framing runs earned on the pitcher's own pitches, which
FanGraphs credits to the catcher inside Fielding and takes back from the pitcher so the
league's runs count once. No library page states it. It is coded as `fwar_frame` convention 9
and `framing_charge_per9`: 9 x CFraming / IP added to pFIPR9 after the park factor. Four
placements were measured (after RAR, levered with relief, before the park factor, after it);
the last three tie within 0.01 runs of MAE.

### The component table (gate: 99 percent of rows within 1.0 run, per season)

Default line = IFFB + FanGraphs Guts FIP park factor + pitcher framing charge + FanGraphs
Start-IP role split (arm `iffb_fg_pf_framing_fg_role`). "was" is the committed W1.1 artifact
(plain FIP, leave-one-out FIP- factor). The LOO-factor arm is the same line with the
leave-one-out FIP- back-solve in place of the Guts factor (`iffb_loo_pf_framing_fg_role`).
`fip_runs` (plain FIP against the published FIP) passes every completed season as before.

| season | n | RAR within 1.0 (was) | RAR MAE | WAR-runs within 1.0 (was) | verdict RAR / WAR | LOO-factor arm RAR / WAR | LOO verdict RAR / WAR | single-team RAR | traded RAR |
|---|---|---|---|---|---|---|---|---|---|
| 2011 | 662 | 0.9970 (0.6571) | 0.075 | 0.9955 (0.6435) | PASS / PASS | 0.9970 / 0.9970 | PASS / PASS | 0.9984 (619) | 0.9767 (43) |
| 2012 | 661 | 0.9909 (0.6793) | 0.159 | 0.9894 (0.6732) | PASS / FAIL | 0.9924 / 0.9909 | PASS / PASS | 0.9950 (602) | 0.9492 (59) |
| 2013 | 678 | 0.9867 (0.7242) | 0.190 | 0.9838 (0.7198) | FAIL / FAIL | 0.9912 / 0.9867 | PASS / FAIL | 0.9905 (632) | 0.9348 (46) |
| 2014 | 691 | 0.9884 (0.6975) | 0.257 | 0.9855 (0.6932) | FAIL / FAIL | 0.9884 / 0.9884 | FAIL / FAIL | 0.9922 (641) | 0.9400 (50) |
| 2015 | 734 | 0.9864 (0.7561) | 0.262 | 0.9837 (0.7520) | FAIL / FAIL | 0.9918 / 0.9918 | PASS / PASS | 0.9894 (661) | 0.9589 (73) |
| 2016 | 742 | 0.9933 (0.7574) | 0.093 | 0.9933 (0.7372) | PASS / PASS | 0.9919 / 0.9933 | PASS / PASS | 0.9939 (661) | 0.9877 (81) |
| 2017 | 753 | 0.9880 (0.7795) | 0.203 | 0.9814 (0.7689) | FAIL / FAIL | 0.9894 / 0.9841 | FAIL / FAIL | 0.9941 (673) | 0.9375 (80) |
| 2018 | 797 | 0.9837 (0.7541) | 0.169 | 0.9849 (0.7491) | FAIL / FAIL | 0.9824 / 0.9862 | FAIL / FAIL | 0.9873 (711) | 0.9535 (86) |
| 2019 | 829 | 0.9855 (0.7925) | 0.121 | 0.9855 (0.7925) | FAIL / FAIL | 0.9879 / 0.9879 | FAIL / FAIL | 0.9918 (736) | 0.9355 (93) |
| 2020 | 735 | 0.9905 (0.9551) | 0.128 | 0.9891 (0.9456) | PASS / FAIL | 0.9932 / 0.9891 | PASS / FAIL | 0.9943 (700) | 0.9143 (35) |
| 2021 | 906 | 0.9790 (0.8234) | 0.146 | 0.9779 (0.8190) | FAIL / FAIL | 0.9779 / 0.9779 | FAIL / FAIL | 0.9899 (795) | 0.9009 (111) |
| 2022 | 871 | 0.9897 (0.8163) | 0.086 | 0.9908 (0.8060) | FAIL / PASS | 0.9908 / 0.9908 | PASS / PASS | 0.9897 (780) | 0.9890 (91) |
| 2023 | 863 | 0.9942 (0.7694) | 0.106 | 0.9930 (0.7648) | PASS / PASS | 0.9930 / 0.9919 | PASS / PASS | 0.9987 (771) | 0.9565 (92) |
| 2024 | 853 | 0.9894 (0.8042) | 0.111 | 0.9871 (0.8066) | FAIL / FAIL | 0.9894 / 0.9871 | FAIL / FAIL | 0.9960 (747) | 0.9434 (106) |
| 2025 | 873 | 0.9908 (0.8144) | 0.178 | 0.9897 (0.8007) | PASS / FAIL | 0.9943 / 0.9908 | PASS / PASS | 0.9947 (753) | 0.9667 (120) |
| 2026 (live) | 852 | 0.9718 (0.8474) | 0.246 | 0.9648 (0.8474) | FAIL / FAIL | 0.9765 / 0.9730 | FAIL / FAIL | 0.9756 (739) | 0.9469 (113) |

Completed seasons clearing the gate (15 in all, 2011 to 2025):

| arm | RAR | WAR-runs | single-team RAR |
|---|---|---|---|
| W1.1 (plain FIP, LOO factor, B-Ref role innings) | 0 | 0 | 0 |
| default: Guts FIP factor | 6 (2011, 2012, 2016, 2020, 2023, 2025) | 4 (2011, 2016, 2022, 2023) | 11 |
| same line on the LOO FIP- factor | 9 (adds 2013, 2015, 2022) | 7 (2011, 2012, 2015, 2016, 2022, 2023, 2025) | 14 |

The leave-one-out factor clears three more seasons than the Guts factor. The Guts FIP column
as served today sits 0.13 to 0.92 points (per-season MAE) from the factor inside the
published FIP-, so the published WAR was priced on a factor close to, but not the same as,
the one the Guts page shows now. The default stays on the Guts factor because that is the
INPUT decision 14a asked for (the LOO arm consumes teammates' published FIP-); switching the
default is an owner question, and both arms are in the artifact (`pitcher_arms_summary`).

Where the default misses, it sits at 97.9 to 98.97 percent. What is left is mostly traded
pitchers (0.90 to 0.99): FanGraphs prices each stint on its own counts, and the replica
prices the season total with IP-weighted park and league. Per-stint counting stats are the
one input from decision 14a's list still not on disk. 2026 is scored against a StatsAPI feed
cached at a different time than the FanGraphs pull (the two published copies of pitcher WAR
differ on 40 of 852 rows, max 0.47 WAR; in every completed season they agree on every row to
0.0), so its row reads the vintage gap as much as the replica.

What each input buys (RAR share within 1.0 run, arms one input apart, every season in the
artifact under `pitchers_arms`): IFFB +0.04 (2020) to +0.13; the Guts FIP factor in place of
the leave-one-out back-solve -0.02 to +0.02 on the IFFB-only line; the framing charge +0.04 to
+0.26 in every season but 2020 (-0.003; largest 2011 to 2014, when framing values were
largest); FanGraphs Start-IP +0.001 to +0.03.

### Framing cross-check (decision 13)

FanGraphs CFraming (fielding leaderboard, catcher rows) against the feed's framing residual
(`rar` minus the six published parts, what the replica and DEM+ price): every catcher in
every season 2011 to 2026 agrees within 0.01 runs, one 2021 catcher at 0.03. 0 to 2 catchers
a season sit in one source only, none carrying more than 0.01 runs. The residual stays the
priced input; CFraming confirms it rather than replacing it.

### What the public artifact carries

`data/fwar_replica_eval.json` ships with the site's eval artifacts. It carries what the
replica made of FanGraphs' numbers (shares, MAE, row counts, the LOO-minus-Guts gap) and the
sha256 of every cached response. It does not carry the Guts park-factor table, the factor
applied to a pitcher when it is FanGraphs', or any catcher's CFraming (the cross-check's worst
rows give the gap only). Every replica number is identical to the build that did.

## 3. The nightly eWAR (`tools/build_ewar.py --nightly`)

### Where it runs

- Daily: `run_daily` step d8b, before d9 (the timeseries rebuild, the projections export and
  the eFV regen inside it), d9b2 (player cards), 9e-pre0 (the three boards) and d10b (the FA
  re-export). That is WAR_BASIS_RUNBOOK step B's place: ahead of every WAR reader.
- Monthly: `main` step 3-pre, before 3d-bis (career WAR through war_source), the monthly's
  first WAR reader; steps 4, 6 and 6b to 6b7b all read WAR before `main` chains the daily. The
  chained daily skips d8b when 3-pre priced the live season that day.
- Both call `run_monthly._ewar_nightly_step`: it catches `Exception` and `SystemExit` (ewar's
  input loaders raise SystemExit on an unreadable data file), logs the freshness assertion
  and records the `ewar_nightly` heartbeat. It never stops the night.

### The design

- It is not the whole of step B. Only the live season is re-priced; every completed season is
  carried byte for byte.
- A season is complete from November 1 of its own year (`war_source.EWAR_FREEZE_MONTH_DAY`, the
  same rule as the FanGraphs cache). The first nightly on or after that date prices it one
  last time and freezes it. A frozen season's blocks are copied, never rebuilt; each carries a
  sha256 (`war_source.ewar_season_digest`) in `meta.cadence.frozen_digests`, and the nightly
  refuses to write if a frozen season would change or if `generated_at` would move.
- A hand build has no cadence block. The seasons it froze are the ones complete on the day it
  was BUILT (`war_source.ewar_complete_at_build`), never the ones complete today, so a season
  it priced in progress is re-priced by the next nightly however late the file is read.
- The box restores the committed `data/ewar.json` before every run (`git checkout -- .` in
  deploy/nightly-build.sh). Each write is therefore also copied to `.cache/ewar/nightly.json`
  (`build_ewar.CARRY_PATH`, untracked), and the next night starts from that copy when it
  descends from the committed build: the same `generated_at`, every frozen season on its
  digest, agreeing with the committed file on every season both froze, and a later live build.
  A new hand build committed to the repo ends the lineage. The copy is put back on disk before
  anything is priced, so a night that fails serves the last good nightly.
- The live season is priced on that night's inputs or not at all:
  - war_daily: the frames the rest of the night serves (`war_source.stint_frame`, provider
    bwar, one read per side). A last-good-cache fallback (`served_stale()`) refuses.
  - FIP: ewar reads FIP from `fa_corpus.pkl`, which is up to three days old in season and is
    rebuilt only after this step. The nightly re-reads the rebuilt seasons' StatsAPI pitching
    lines on its own scraper-cache key (`ewar_nightly_statsapi_pitching_<season>`, 24-hour
    TTL) and prices them through `fa_projection.build_corpus` itself, in memory. The shared
    pickle and the `fa_statsapi_*` files are not touched, so the FA corpus keeps its own
    cadence. A re-read shorter than 90 percent of the pickle's rows keeps the pickle and says so.
  - standings: warmed through the shared scraper cache before the build.
  - An input older than the one the carried live season was priced on refuses, so the live
    season never moves backwards.
- `generated_at` stays the build of the frozen series. `storage.board_basis_fingerprint`'s
  `label=` term reads it, so the board basis does not churn nightly. `live_built_at` stamps the
  live season; `war_source.ewar_vintage` reports it as `artifact_generated_at` (from the frame
  receipt of the artifact the served frames were transformed with) and the frozen build as
  `label_build_at`.
- A hand full build (`python tools/build_ewar.py --first 2011 --last 2026 --write`) is still
  the only way to re-price a completed season, and it is the runbook cascade.
- Freshness assertion: `war_source.ewar_cadence_status()`. It fails when the live season was
  not built today, when it was priced on the last-good war_daily cache, when the StatsAPI
  stats or the standings were more than 36 hours old at the build
  (`EWAR_LIVE_INPUT_MAX_AGE_HOURS`), when a frozen season is off its digest, or when a complete
  season is not frozen.

### What changes nightly

- `data/ewar.json`: the live season's blocks, `meta.by_season`, `meta.pitching.by_season`
  and `meta.rpw_by_season` for that season, `meta.cadence`, `live_built_at`, `n_player_seasons`.
- `.cache/ewar/nightly.json` (the carried copy) and `.cache/ewar_nightly_statsapi_pitching_<season>.json`.
- Every served live-season eWAR that reads it through `war_source`: MLB player cards
  (`mlb_player_detail.json`, d9b2), the bullpen, starter and hitter boards (9e-pre0), the
  projections export and the FA re-export where they read the live season.
- `ewar_vintage` on the three boards: `stale` false and live drift 0 after the step.

### What does not change nightly

- Every completed season's blocks (byte for byte, digest-checked), `generated_at`, the board
  fingerprint's label term.
- `data/ewar_eval.json` (its gates score 2016 to the last completed season).
- `.cache/fa_corpus.pkl` and the `fa_statsapi_*` sources (the FA corpus keeps its three-day rule;
  its live-season WAR labels now read the nightly artifact whenever it rebuilds).
- The `career_war` table (monthly step 3d; it stores the live season's cell as of that run).
- The fitted artifacts downstream of step B, because they read completed seasons only: the
  pooled FV outcome curve, the empirical anchors and survivor curve, the draft slot curve, the
  war_rate_plus vintages, the eFV matrices, evals and floors, the projections bundle.

### Measured on 2026-09-11 (repo frames and caches, copies of the artifact, network blocked)

- A one-season build equals that season's slice of the full build exactly (2025 and 2026);
  a fresh full rebuild reproduces every 2011 to 2025 block of the 2026-09-03 artifact byte for
  byte. Freezing changes no completed-season number; it makes that structural.
- The first nightly moves 2026 only: 1,436 to 1,448 player-seasons (+12). 1,151 existing
  blocks change eWAR (747 by at least one 0.1 display step, 532 by 0.1 WAR or more, max
  0.88); 640 existing pitcher sides change (363 display steps). League sum 862.92 to 902.80 on
  4,198 to 4,392 team-games, replacement scale 0.99968 to 0.99783. The in-memory FIP re-read
  gave 852 rows against the pickle's 852 and the same 2026 blocks as the pickle build (the
  pickle was built after the current source).
- Frame drift against the artifact: 527 batting and 631 pitching player-seasons (all 2026)
  before, 0 and 0 after.
- The box, simulated (the committed file restored before every night): the second night starts
  from the carried copy and writes the same 2026 blocks on the same frames; the 2026-11-01
  freeze pass adds 2026 to the frozen list without moving `generated_at`; the night after is a
  no-op that leaves the file byte for byte; with the carried copy deleted, the restored
  2026-09-03 hand build is re-priced and frozen on that night's numbers, the same 2026 digest
  as the freeze pass, never frozen at its September numbers.

### Moves in files this change does not own (`handoff_not_owned.diff`, same commit)

- `test_war_source_ewar.py`: `rebuilds_on_a_schedule` is pinned to the artifact's cadence
  instead of False (the test said the flag and the glossary sentence move together), and the
  glossary pin reads the new sentence. The stale-threshold test passes unchanged: the stamp
  comes from the frame receipt.
- `data/glossary.json` (ewar methodology: "THE LIVE SEASON REBUILDS NIGHTLY" replaces "IT DOES
  NOT REBUILD WITH THE SEASON").
- `assets/mlbstats.js` `ewarTitle` reads `rebuilds_on_a_schedule` from the payload.
- `data/model_registry.json` row `fwar_replica` (the pitcher sentence, from the table above).
- `DATA_SOURCES.md` and `MODEL_REGISTRY.md` regenerate (`python tools/gen_audit_docs.py`).

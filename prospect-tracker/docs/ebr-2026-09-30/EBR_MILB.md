# Level-relative eBR for the minor leagues (task EBR_Q6B_MILB_CARDS)

Owner answer EBR-Q6 (b), 2026-10-01 (`DECISIONS_FOR_OWNER.md`, eWAR v3 batch 2): show eBR on prospect
cards, per level and season at 150 or more plate appearances, display only, never an eFV input, never
summarised by FV grade. This note records what was built, the defaults applied, and the receipts. The
definition is `EBR_GATE.md` part 2; where this note differs for the minor leagues, this note governs the
minor-league build only. Nothing here changes `ebr_v1`, the MLB record, or any MLB number.

## What it is

Runs above an average runner at the same level in the same season, counted from the minor-league
partition of the runner record (`.cache/pbp_runners/milb`): `ebr.py`'s five parts (eSB, ePK, eXB advancement,
eXB outs, eGDP) with their formulas untouched and `s = (level, season)`. Pure core `ebr_milb.py`, builder
`tools/build_ebr_milb.py`, previews under `.cache/ebr/milb_preview/`, served files `data/ebr_milb.json`
(card payload) and `data/ebr_milb_eval.json` (aggregates), flag `ebr_milb.MILB_EBR_LIVE`, card constant
`MILB_EBR_CARD_ON` in `prospx/index.html`. Registry row `ebr_milb` (provisional, measurement only), glossary
entry `ebr_milb`.

## The run basis, per level-season

- RE24 on the level-season's own fit set (the part 2.3 recipe), shrunk toward the level's pooled table
  over its seasons on disk (Single-A and Rookie, 2023 to 2026), or toward that season's all-MiLB table
  where a level has one season (AAA, AA, High-A, 2026).
- K by the method of moments (`ebr.shrink_constant`) over the level's seasons, or, for a one-season level,
  over every level-season on disk (the all-MiLB constant), clipped to [500, 5000]. Single-A 1929.2, Rookie
  2609.0, one-season levels 1342.7.
- The outcome distribution backs off from the level-season to the level's pooled counts (a level with two
  or more seasons) and then to all MiLB counts. Centring per level-season, which absorbs the minors' rule
  experiments by construction. Same classes and coordinate buckets as MLB.
- Advances on wild pitches and passed balls: the W sub-total (a count and uncentred runs, each group's run
  value split equally among its advancing runners), reported and never in the number.
- Units: every level-season with at least 100 final games (AA 2024 holds one game of a probe and is not a
  unit). Eleven units.

## Identity receipts

Official lines: StatsAPI season hitting lines, `sportIds` of the level, `playerPool=ALL`, fetched once per
level-season with `caughtStealing` and `groundIntoDoublePlay` kept, cached at `.cache/ebr/milb_lines/`.
`milb_history`'s lean rows are not changed.

| level-season | games | PA | SB record / official | CS record / official | SB and CS players off | exact share | GIDP exact share | PA coverage | games re-fetched or filled | steals typed by event | split-half r (Spearman-Brown, n) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AAA 2026 | 2,223 | 171,799 | 5,091 / 5,091 | 1,343 / 1,343 | 0 of 665 | 1.0000 | 0.9848 | 1.0000 | 11 | 1 | 0.28 (0.44, 465) |
| AA 2026 | 2,048 | 156,270 | 6,134 / 6,136 | 1,575 / 1,575 | 2 of 669 | 0.9970 | 0.9935 | 1.0000 | 12 | 1 | 0.29 (0.45, 426) |
| High-A 2026 | 1,952 | 151,430 | 6,248 / 6,249 | 1,683 / 1,683 | 1 of 665 | 0.9985 | 0.9902 | 1.0000 | 16 | 2 | 0.23 (0.38, 413) |
| Single-A 2023 | 1,952 | 148,834 | 5,588 / 5,589 | 1,674 / 1,674 | 1 of 709 | 0.9986 | 0.9953 | 1.0000 | 3 | 2 | 0.19 (0.32, 395) |
| Single-A 2024 | 1,945 | 148,375 | 5,727 / 5,727 | 1,586 / 1,586 | 0 of 718 | 1.0000 | 0.9937 | 1.0000 | 1 | 1 | 0.33 (0.50, 389) |
| Single-A 2025 | 1,948 | 149,078 | 6,708 / 6,708 | 1,894 / 1,894 | 0 of 727 | 1.0000 | 0.9922 | 1.0000 | 0 | 0 | 0.29 (0.45, 386) |
| Single-A 2026 | 1,955 | 151,721 | 6,671 / 6,671 | 2,009 / 2,009 | 4 of 764 | 0.9948 | 0.9897 | 1.0001 | 15 | 1 | 0.23 (0.38, 392) |
| Rookie 2023 | 2,210 | 164,294 | 7,034 / 7,035 | 2,500 / 2,500 | 3 of 1,442 | 0.9979 | 0.9982 | 1.0000 | 1,344 | 2 | 0.23 (0.37, 395) |
| Rookie 2024 | 2,268 | 163,573 | 8,282 / 8,282 | 2,639 / 2,639 | 2 of 1,270 | 0.9984 | 0.9950 | 1.0000 | 1,394 | 2 | 0.10 (0.19, 451) |
| Rookie 2025 | 2,314 | 167,445 | 8,498 / 8,497 | 2,737 / 2,737 | 1 of 1,274 | 0.9992 | 0.9952 | 1.0000 | 1,436 | 0 | 0.07 (0.14, 474) |
| Rookie 2026 | 2,267 | 163,737 | 9,620 / 9,622 | 2,717 / 2,717 | 2 of 1,279 | 0.9984 | 1.0000 | 1.0000 | 326 | 0 | 0.11 (0.21, 479) |

Split-half: runs earned in odd-numbered against even-numbered games (game_pk parity), players at 150 or more
plate appearances in the unit, stepped up with Spearman-Brown. A reliability, not a forecast. Cross-level
continuity for the 177 player-seasons with 150 or more plate appearances at two levels in one season: r 0.15
overall (AAA and AA r 0.35 on 49, AA and High-A r 0.26 on 69, High-A and Single-A r 0.14 on 42, Single-A and
Rookie r -0.24 on 15). Reported only; the pairs are selected players and the level-relative rates are not on
one scale.

### What was done to the record to get here

1. **Completeness (I3).** Rookie 2023 to 2026 held 38 to 87 percent of the official plate appearances (the
   feed cache's gaps). The final regular-season games the league schedule lists and the record lacked were
   fetched into `.cache/pbp_runners/refetch/milb/` (1,415, 1,438, 1,463 and 359 games), walked by
   `build_runner_moves._milb_job`, and overlaid in memory. The frozen parquet files are untouched.
2. **The one re-fetch (part 3).** For each player whose SB or CS differed from the official line, the
   official game log located the differing game and it was re-fetched once. A miss that survives is reported
   (the table), not hidden.
3. **Steals typed by event.** The feed has a few entries (0 to 2 per level-season) whose event is the
   runner's own stolen base (`stolen_base_2b` first to second, `_3b` second to third, `_home` third to home)
   with an ordinary advance as the movement reason; the official lines count them. A safe entry that moves
   the runner exactly from the event's origin to its target is put on the steal reason
   (`ebr_milb.normalise_runners`). The second runner of a double steal and the duplicate entry with no start
   base are untouched. `EBR_GATE.md` 2.2 keys steals on the movement reason because on the MLB feed the event
   type misfires on caught stealing; the minor-league rule is the narrower one above.

### The default applied: minor-league identity bounds

`EBR_GATE.md` part 3 requires exact SB and CS for every player. After the re-fetch and the steal typing, 5
of 11 level-seasons are exact on league SB and CS (AAA, Single-A 2024 to 2026 and Rookie 2024; per player,
AAA, Single-A 2024 and Single-A 2025 are exact too) and the rest differ by at most 2 steals in a league
(0.033 percent): a
few official steals are scorer decisions the feed's runner entries do not carry (for example a runner
credited a stolen base on another runner's steal, with an error-advance reason). The minor-league gate is
therefore: league SB and CS within 0.1 percent of the official lines, SB and CS exact for 99 percent of the
players who have any, GIDP within 0.5 percent at league level and exact for 97 percent of players (MLB's own
GIDP bounds), PA coverage at 99 percent or more, and I4 to I7 and I9 as in part 3. Every level-season passes.
Exact match is kept as a reported flag per level-season. A stricter reading (exact for every player or withheld) would serve
AAA 2026, Single-A 2024 and Single-A 2025 only.

## What the card shows and does not

PROSPX prospect pages, Overview, Signals section (position players): "Baserunning, level-relative", one row
per level and season at 150 or more plate appearances with the runs, a rate per 600 plate appearances, steals,
extra bases and double plays, and a tooltip saying it is level-relative, not comparable across levels or with
the majors, with the unit's split-half reliability and the W sub-total. 4,665 player-seasons at 150 or more
plate appearances across 2,923 players are served.

It is never an eFV input (no `efv_*` module reads it; `test_ebr_milb.py` pins it), never a reserved eFV frame,
never summarised, validated or stratified by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`), and carries
no forecast. A driver test belongs to a separate registration under `docs/efv-v2/DRIVER_SYSTEM_V2.md` and not
before `EFV_V2_GATE.md` is final and 2026-12-01.

## Rebuild

```
python tools/build_ebr_milb.py --reconcile      # the one re-fetch, then exit (network)
python tools/build_ebr_milb.py --fill "rookie|2026"   # games the record lacks (network)
python tools/build_ebr_milb.py --serve          # build, write previews; with MILB_EBR_LIVE also data/ebr_milb*.json
python tools/ebr_milb_flip_registry.py          # glossary entry, registry row, MODEL_GLOSSARY (idempotent)
```

A rebuild is byte-identical on the same record and the same re-fetched games (the I8 digests of two
consecutive builds matched on all 11 level-seasons). `.cache/game_feeds` is pruned at 400 days (2027-07-22
for the oldest 2026 feeds); `.cache/pbp_runners/milb` and `.cache/pbp_runners/refetch/milb` are the permanent
store and are listed in `tools/prune_cache.EXCLUDED` through `pbp_runners`.

## 2026-10-22: the history units, 2021 to 2023 (task ETOOLS_SPD_MILB_EBR_BACKFILL)

Owner answer ETOOLS-SPD-EBR (2026-10-21, "Backfill 2021-2023"): the record gains 2021 and 2022 at every level
and 2023 at High-A, Double-A and Triple-A, so the cards gain those seasons and eTools amendment 5 can run. The
counts above (eleven units, 4,665 rows) describe the build before this note; from this note on, the served
file holds 23 level-seasons and 9,482 rows at 150 or more plate appearances for 4,751 hitters.

**The feeds.** `tools/fetch_milb_feeds_hist.py` fetched the /feed/live payload of every final regular-season
game the league schedule lists for the 13 units into `.cache/milb_feeds_hist/feeds/` (never `.cache/game_feeds`,
the record, or the winProbability caches; the directory is in `tools/prune_cache.EXCLUDED`): the pattern of the
eBR history fetcher (receipts with sha256 per request, a healed receipts file after an unclean shutdown, atomic
writes, resumable, paced at most two requests a second, the house User-Agent, a stop inside the 06:00 to 11:00
UTC nightly window). 26,783 games listed; 26,290 payloads (16.1 GB); 493 answered as never played (a 404, or a
game the schedule lists as final with no plays, such as "Cancelled: Rain"). A game called early ends on an open
"Game Advisory" play and is kept as final.

**The record.** `python tools/build_runner_moves.py --milb-hist` copied them into `milb/<level>/<season>/` one
unit at a time, frozen on first build, and refuses while the receipts show a unit incomplete. The eleven
existing units' blocks, the MLB seasons and the existing parquet files are byte-identical (manifest blocks
compared before and after). The one re-fetch (part 3) located and re-fetched 17 games of mismatched players in
the new units.

| level-season | games | PA | SB record / official | CS record / official | SB and CS players off | GIDP league diff | PA coverage | re-fetched | split-half r (Spearman-Brown, n) | served |
|---|---|---|---|---|---|---|---|---|---|---|
| AAA 2021 | 1,925 | 145,997 | 2,752 / 2,752 | 887 / 887 | 0 of 567 | 0.35% | 1.0000 | 0 | 0.33 (0.50, 412) | yes |
| AA 2021 | 1,741 | 129,504 | 2,758 / 2,760 | 1,135 / 1,135 | 2 of 547 | 0.54% | 1.0000 | 2 | 0.16 (0.28, 370) | **no** |
| High-A 2021 | 1,772 | 133,871 | 3,820 / 3,821 | 1,219 / 1,219 | 1 of 609 | 0.11% | 1.0000 | 1 | 0.17 (0.28, 377) | yes |
| Single-A 2021 | 1,777 | 135,846 | 4,356 / 4,357 | 1,300 / 1,300 | 1 of 670 | 0.16% | 1.0000 | 1 | 0.21 (0.34, 358) | yes |
| Rookie 2021 | 2,284 | 159,153 | 6,442 / 6,443 | 2,575 / 2,575 | 3 of 1,456 | 0.23% | 1.0001 | 3 | 0.15 (0.26, 301) | yes |
| AAA 2022 | 2,237 | 171,720 | 4,160 / 4,161 | 1,142 / 1,142 | 1 of 634 | 0.45% | 1.0000 | 1 | 0.20 (0.34, 465) | yes |
| AA 2022 | 2,050 | 156,510 | 4,306 / 4,307 | 1,259 / 1,259 | 1 of 577 | 0.46% | 1.0000 | 1 | 0.17 (0.29, 419) | yes |
| High-A 2022 | 1,954 | 146,833 | 4,364 / 4,367 | 1,264 / 1,264 | 3 of 597 | 0.17% | 1.0000 | 3 | 0.24 (0.39, 399) | yes |
| Single-A 2022 | 1,956 | 149,397 | 5,113 / 5,113 | 1,523 / 1,523 | 0 of 689 | 0.31% | 1.0000 | 0 | 0.29 (0.45, 375) | yes |
| Rookie 2022 | 2,361 | 167,907 | 6,980 / 6,981 | 2,773 / 2,773 | 3 of 1,421 | 0.35% | 1.0001 | 3 | 0.03 (0.06, 415) | yes |
| AAA 2023 | 2,224 | 174,963 | 4,391 / 4,391 | 1,247 / 1,247 | 0 of 618 | 0.21% | 1.0000 | 0 | 0.30 (0.46, 470) | yes |
| AA 2023 | 2,054 | 156,701 | 4,806 / 4,807 | 1,384 / 1,384 | 1 of 583 | 0.28% | 1.0000 | 1 | 0.27 (0.43, 422) | yes |
| High-A 2023 | 1,955 | 147,812 | 4,738 / 4,739 | 1,457 / 1,457 | 1 of 608 | 0.18% | 1.0000 | 1 | 0.16 (0.27, 404) | yes |

**Withheld: AA 2021.** League GIDP is 2,042 in the record against 2,053 on the official line, 0.54 percent
against the 0.5 percent bound (I1), so its 370 rows are not on the cards; the unit stays in the eval artifact
with its receipts. The gap is scorer coding: the official line counts a few double plays the feed types as
`double_play` rather than `grounded_into_double_play`. The one re-fetch is defined for steals and caught
stealing only and does not apply.

**What moved on the cards.** Every existing row is re-priced because the run basis pools over the seasons on
disk: AAA, AA and High-A now have a level pool (K 3,986.6, 2,598.6 and 5,000.0, the clip, against the all-MiLB
1,342.7 before), Single-A K 1,929.2 to 3,499.5, Rookie K 2,609.0 to 3,248.4. Of the 4,665 rows served before,
4,550 change a printed digit and 1,831 change the runs shown; the largest move in runs is 0.6 (AA 2026), in
runs per 600 1.1. Split-half reliability of the existing units moves by at most 0.009 (AA 2026 0.453 to 0.461).
4,817 rows are new (1,828 hitters new to the payload, 846 existing hitters gain seasons). Cross-level
continuity: r 0.29 on 559 pairs (was 0.15 on 177). League SB and CS are exact in 8 of 23 served level-seasons;
the worst league SB or CS difference is 0.069 percent (High-A 2022, 4,364 against 4,367).

**Rebuild**

```
python tools/fetch_milb_feeds_hist.py           # the history feeds (network, about four hours; resumable)
python tools/fetch_milb_feeds_hist.py --status  # every unit complete before the copy
python tools/build_runner_moves.py --milb-hist  # into the record, frozen
python tools/build_ebr_milb.py --reconcile      # the one re-fetch for the new units (network)
python tools/build_ebr_milb.py --serve
python tools/ebr_milb_flip_registry.py          # registry and glossary figures from the eval
```

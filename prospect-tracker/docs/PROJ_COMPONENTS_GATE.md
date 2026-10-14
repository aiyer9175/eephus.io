# MLB Projections component gate (pre-registered 2026-10-08)

Covers the component projections the owner asked for on 2026-10-01 (message 1, verbatim): "Can
we also flesh out the MLB Projections module further, projecting not just WAR but specific
components of WAR (which should allow for more specificity for projections, as well as more
accurate projections by feeding more data into it)".

Two gates, both registered here before any component number exists:

- **PJ-C, the component gate** (section 4). Per veteran and season, FanGraphs-frame WAR
  components as means, scored on component labels from the frozen fWAR vintage, one look on
  the HOLDOUT frame (section 5).
- **PJ-W, the WAR arms** (section 6). W1 (component-built WAR against the served `war`) and
  W2 (a dark twin of the serving `proj_lgbm` bundle with component stack features), scored on
  label season 2027 only.

Plan: Part 9 section 9.2 'Component projections' ('Part 9 (proposed): Projections, aging, tools
and team program', durable bundle `_finalpass_2026-09-24/part9/PLAN.md`) and Lane A sections 3.1
'PJ-C, the component gate' and 3.2 'PJ-W, the WAR arms' (`_finalpass_2026-09-24/part9/LANE_A.md`,
cited as LANE_A). Owner answers PJ-Q1 to PJ-Q4, including the PJ-Q4 OVERRIDE, are in
DECISIONS_FOR_OWNER.md under 'the projections, aging, tools and team program (Part 9)'.
Citations are pinned at `@0d4892bb` with an anchor; where the anchor and the number disagree at
HEAD, the anchor wins.

Producers, none of which exist at registration: `proj_components.py` (PJ_2_COMPONENT_FRAME),
`proj_eval.run_components` (PJ_3_COMPONENT_SCORER), the heads and the DEV selection (PJ_4),
the look (PJ_5), `tools/proj_component_stack.py` and `model/proj_lgbm_components/` (PJ_9),
the 2027 read (PJ_11). Artifact: `data/proj_components_eval.json` (failed heads and failed arms
are blocks inside it, never a standalone eval file). Registry rows: `proj_components` and
`proj_component_stack`, defined in section 8.2 and written by PJ_3_COMPONENT_SCORER.

This document is committed alone. It writes nothing under data/, runs no exporter, lab, fetch
or pytest, and moves no served number.

---

## 0. Honesty clause, and the verification run before registration

**Nothing has been fitted or scored under this gate.** No component head exists, no frame has
been built, no component label has been read against a projection, no DEV selection has been
made and no holdout cell has been opened. Every threshold, grid, seed, frame and comparator in
this document is fixed before any of that happens.

The first checks, run 2026-10-08 in the lane-200 worktree on branch
`wt-PJ_1_COMPONENTS_GATE_REGISTRATION` (base `0f9fb164`):

- No `run_monthly.py`, nightly job or other writer in this worktree. (Other lanes' pytest
  sessions ran in their own worktrees; this task runs none.)
- `_pre_epoch_fwar_2026-10/` exists, and FWAR_LABEL_EPOCH_GATE.md part 9 carries the entry
  '### 2026-10-03: step Z, the fWAR label epoch's results' (step A 2026-10-03 11:47 local, step Z
  the same day 21:11). The epoch is not running.
- `docs/PROJ_COMPONENTS_GATE.md` did not exist at HEAD.
- None of `proj_components.py`, `tools/proj_component_stack.py`, `model/proj_components/`,
  `model/proj_lgbm_components/`, `data/proj_components_eval.json` exists.

### 0.1 (a) No committed artifact has scored a projected component label

Commands and output, verbatim:

```
$ for t in baseRunning bsr fielding positional ra9War gmli; do grep -l -i "$t" data/*_eval.json data/*eval*.json | sort -u | sed "s/^/$t  /"; done
baseRunning  data/fwar_replica_eval.json
baseRunning  data/hem_plus_eval.json
baseRunning  data/war_rate_plus_multiyear_eval.json
bsr  data/fa_gate1_eval.json
bsr  data/fwar_replica_eval.json
fielding  data/ba_tool_grade_eval.json
fielding  data/dem_plus_eval.json
fielding  data/dem_plus_multiyear_eval.json
fielding  data/ewar_eval.json
fielding  data/fwar_replica_eval.json
fielding  data/positional_ladder_eval.json
fielding  data/positional_ladder_recency_eval.json
fielding  data/war_rate_plus_multiyear_eval.json
fielding  data/xfv_role_arg_eval.json
positional  data/anthro_position_eval.json
positional  data/dem_plus_eval.json
positional  data/fwar_replica_eval.json
positional  data/positional_ladder_eval.json
positional  data/positional_ladder_recency_eval.json
positional  data/prospect_def_value_eval.json
positional  data/sprint_range_eval.json
gmli  data/fwar_replica_eval.json
gmli  data/leverage_consistency_eval.json
gmli  data/park_shrink_eval.json
gmli  data/rem_plus_eval.json
gmli  data/riv_plus_eval.json

$ grep -rli "baseRunning\|bsr\|fielding\|positional\|ra9War\|gmli" docs/ | wc -l
73
$ grep -rn -i "baseRunning\|bsr\|fielding\|positional\|ra9War\|gmli" docs/ | wc -l
613
$ grep -rn -i "baseRunning\|bsr\|fielding\|positional\|ra9War\|gmli" docs/ \
    | grep -i "project\|MAE\|Y+1\|next.year\|next.season\|forecast\|predict" | cut -d: -f1 | sort | uniq -c
      2 docs/PROJ_PATH_SHAPE_GATE.md
      1 docs/audit-2026-07/AUDIT_FINDINGS.md
      2 docs/audit/current_state_map.md
      2 docs/beta-recovery-record-2026-08-01.md
      3 docs/computed-stats-handoff-2026-08-01.md
      3 docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md
      1 docs/efv-2026-07-30/POSITION_CENSUS_ASOF.md
      2 docs/efv-2026-07-30/POSITION_ROLE_GATE.md
      2 docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md
      1 docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md
      1 docs/gate-2026-08-07-positional-shape-transfer.md
      1 docs/master-plan-2026-07-29-efv-fa.md
      1 docs/master-plan-2026-08-04-repairs-ewar2.md
      2 docs/master-plan-2026-09-05-opus.md
      2 docs/master-plan-2026-09-11-war-epoch-drivers-betting.md
     12 docs/master-plan-2026-09-24-final-pass.md
      1 docs/prereg-e4-anthro-position.md
$ grep -rn -i "ra9War" docs/ data/*eval*.json
docs/master-plan-2026-09-09-fangraphs-ewar-betting.md:52:`war`, `ubr`, `wSb`, `wGdp`; pitchers carry `war`, `rar`, `ra9War`, `fip`, `xfip`, `pLI`,
```

Every eval hit was opened and walked key by key (a JSON walk printing each key or string that
contains a term). Classification:

| hit | what it is | class |
|---|---|---|
| `fwar_replica_eval.json` | the W1.1 replica of FanGraphs WAR on realized inputs (`consumed`: UBR + wGDP, fielding, gmLI from the feed; `built`: positional) | replica of realized inputs, not a projection score |
| `ewar_eval.json` | `gate_3_coverage_identity.fielding`, fielding-innings coverage by season; face-validity lists | realized coverage, not a projection score |
| `fa_gate1_eval.json` | `notes`: defense and BsR are "not separately projected in v1" and are "absorbed by WAR map + bands" | states that no component is projected |
| `hem_plus_eval.json`, `war_rate_plus_multiyear_eval.json` | definitions and summaries naming baserunning and fielding as parts of WAR | realized descriptive, WAR or wOBA labels |
| `riv_plus_eval.json`, `rem_plus_eval.json`, `park_shrink_eval.json` | realized gmLI values on display rows; the self-computed gmLI convention | realized, not a projection score |
| `ba_tool_grade_eval.json`, `xfv_role_arg_eval.json`, `anthro_position_eval.json`, `sprint_range_eval.json` | prospect tool-label counts, a fielding-positions sidecar, caveats and the Position Fit board receipt | prospect or realized, no vintage label |
| `positional_ladder_eval.json`, `positional_ladder_recency_eval.json` | recovery of Baseball-Reference `runs_position` per 650 PA from same-season innings shares (B-Ref frame) | same-season reconstruction of realized inputs, not a projection score |
| `prospect_def_value_eval.json` | `proj_lgbm_swap_gate`: a defensive FEATURE arm scored on the WAR label (REJECTED) | WAR label (already in PROJ_PATH_SHAPE_GATE.md G-0.1's domain), not a component label |
| `dem_plus_eval.json`, `dem_plus_multiyear_eval.json` | DEM+ predictive validity: Spearman rho of season-Y DEM+ against the published fielding rate ((fielding + framing) per 1,000 innings) in Y+1, predictor seasons 2021 to 2024, 1,255 pairs; DEM+ 0.4597, raw rate 0.4531 | a RANK persistence read of a descriptive rating; no projected value and no MAE. PRIOR, disclosed in 0.2 |
| `leverage_consistency_eval.json` | Y to Y+1 autocorrelation of self-computed gmLI (StatsAPI winProbability, not the vintage `gmli`), pairs 2018 to 2025 ex 2020, pooled rho 0.4683, n 878 | a persistence read on a different gmLI series; no projected value. PRIOR, disclosed in 0.2 |

Docs: the 73 files are plans, gate documents, designs, handoffs and records. The 39 lines that
pair a term with a projection word were each read. They are: plans and descriptions of the
above artifacts (DEM+, Position Fit, REM+ and gmLI consistency, the positional ladder); the
fWAR epoch's F-DEF arm (the feed's fielding and positional runs as a FEATURE of the projections
bundle, scored on the WAR label); POSITION_ROLE_GATE's table of position-dependent prices; the
ETA lane; and one artifact found through the master plan rather than the eval glob, which is
the nearest prior and is classified separately:

- `data/positional_fit.json` `conversion_accuracy` (Position Fit, `positional_fit.conversion_accuracy`;
  quoted in master-plan-2026-09-24-final-pass.md as "Move-size MAE 5.682 vs carry-over 6.733 on 169
  moves"). It predicts, for a player who was a regular at position a in season t and a regular at
  a different position b in t+1, his Savant fielding-run-value rate per 1,000 innings at b in t+1.
  It is a scored projection of a fielding RATE, but of a different label (Savant FRV from
  `data/savant_oaa.json`, not the vintage `fielding` field), at one destination position, on a
  conditional population (169 position movers, 74 of them with label season 2022 to 2025). The
  two series agree closely on realized seasons (same-season Pearson r between the vintage
  `fielding` and the summed Savant FRV: 0.939 in 2018, n 537; 0.904 in 2023, n 558; 0.922 in
  2025, n 567), so this registration does not call the overlap nothing.

**Verdict of the search: no committed artifact has scored a projection of the vintage
`baseRunning`, `fielding`, `positional`, `gmli` or `ra9War` minus `war` on the veteran
population.** The registration proceeds. The Position Fit conversion test is the closest
prior; it is not a STOP under the rule as written (a different label, a different population
and a different quantity), and section 4.7 registers a disclosure split for it. The owner may
rule otherwise (FIX_REPORT owner question PJ1-Q2).

### 0.2 Priors read during design, recorded so a run cannot quietly beat them

| prior | source | figure |
|---|---|---|
| fielding rate persists about as well as DEM+ predicts it | `dem_plus_eval.json` verdict | rank rho Y to Y+1: raw rate 0.4531, DEM+ 0.4597 (gap lo95 -0.0039), 1,255 pairs, label seasons 2022 to 2025 |
| reliever deployment persists | `leverage_consistency_eval.json` gate | self-computed gmLI rho Y to Y+1 0.4683 (lo95 0.412), n 878 |
| a position move is partly predictable | `positional_fit.json` `conversion_accuracy` | MAE 5.682 against carry-over 6.733 runs per 1,000 innings, 169 moves |
| defense and position are where WAR-level gains came from | LANE_A finding A7; registry `proj_def_prior` | `pos_adj_prior` holdout pooled MAE -0.0027, star -0.0285 (WAR label) |
| baserunning is speed-driven | LANE_A 2.4 | untested here |
| RA9 minus FIP persists weakly | LANE_A 2.4 | low persistence expected; the P5 grid can shrink it to 0 |

None of these is a PJ-C result and none may be cited for a pass.

### 0.3 (b) Why this gate reads no WAR label season before 2027

PROJ_PATH_SHAPE_GATE.md G-0.1, 'The READ LEDGER, complete, and the burn standard applied evenly',
verbatim:

> **Every label season from 2015 through 2025 has already been scored on the
> shipped challenger, on exactly the statistics S1 through S6 use.** The block that
> does most of it, `gate1_targets`, is the one `proj_eval.run_rowmatch`'s own
> docstring flags as the block that "invites a false win claim". The label seasons
> with no prior challenger read are **2008 through 2014** and, once the season
> completes, **2026**.

PROJ_PATH_SHAPE_GATE.md 4.6, 'The frames, and how they are kept disjoint', verbatim (the frame
rows):

> | **DEV** | 2008, 2009, 2010, 2011 | (2008, h1-h4), (2009, h1-h3), (2010, h1-h2), (2011, h1) = 10 | h1-h4 | lambda selection (4.4), the frontier table, the A0 tolerance check (4.3), the MDE lab (3.1), every ARM B lever FIT | **no** |
> | **GATE** | 2012, 2013, 2014 | (2008, h5), (2009, h4-h5), (2010, h3-h5), (2011, h2-h4), (2012, h1-h3), (2013, h1-h2), (2014, h1) = 15 | h1-h5 | the primary and every secondary in 4.8-4.9; every ARM B adjudication in 5.5 | **yes** |
> | **CONFIRM** | 2026 | (2022, h5), (2023, h4), (2024, h3), (2025, h2), (2026, h1) | h1-h5 | the touched-once confirmation, opened exactly once at the ARM A look | **yes, once, and only under 4.6b** |

PROJ_PATH_SHAPE_GATE.md section 16, 'Underpowered is a verdict, and it is not a pass', item 1,
verbatim:

> 1. **ARM A, `MDE95(delta pooled MAE) >= 0.0065`** after the VIF: `UNDERPOWERED_NO_MARGIN`.
>    The arm does not ship, no number from the run is cited as evidence of preserved
>    accuracy, and the re-read is 2027-02-15.

So the WAR label seasons 2015 to 2025 are READ, 2008 to 2014 belong to the path-shape DEV and
GATE frames, and 2026 is its CONFIRM frame (opened at the ARM A look or the 2027-02-15
re-read). No WAR label season before 2027 is free for a verdict in this program. PJ-C therefore
scores component labels only and computes no WAR residual; PJ-W takes its verdict on label
season 2027.

### 0.4 (c) The frozen fWAR vintage and its reader

The vintage is built by queue tasks EPOCH_E3 (the builder and reader, `4f434602`, 2026-10-02,
`fwar_vintage.py`, `tools/build_fwar_vintage.py`) and EPOCH_D9_FREEZE (the freeze, `7e34799f`,
2026-10-02). It exists: `data/fwar_vintage.json`, vintage id `2026-10-02-0341299c20ec`, 27
seasons 2000 to 2026, every hitting and pitching group `frozen`.

```
$ grep -n "vintage" war_source.py   (excerpt)
70:             vintage data/fwar_vintage.json (fwar_vintage.py; written once by
71:             tools/build_fwar_vintage.py at EPOCH_D9_FREEZE), never the live
189:FWAR_BUILD_CMD: str = "python tools/build_fwar_vintage.py --freeze 2000-2026 --write"
256:    import fwar_vintage
257:    return fwar_vintage.available()
419:def fwar_index(vintage: dict | None = None) -> dict:
424:    blob = fwar_vintage.load() if vintage is None else vintage
```

**The reader is `fwar_vintage.load()`** (with `fwar_vintage.available()`,
`fwar_vintage.war_by_group(blob, season, group)` and `fwar_vintage.field_presence(blob)`);
`war_source.fwar_index()` is the WAR-label consumer that calls it. PJ_2 reads component labels
through `fwar_vintage.load()` only, never through `.cache/statsapi_saber_*`.

**Schema receipt, read with `fwar_vintage.field_presence` (row presence only, no value read
against anything).** On every season 2000 to 2026 the hitting group carries `baseRunning`,
`fielding`, `positional` on 100% of rows, and the pitching group `war` and `ra9War` on 100% and
`gmli` on 99.67% to 100%. **The hitting group carries `plateAppearances` on 0% of rows in every
season** (the module docstring says so: "that column is null until the feed publishes it"),
and `xfip` is 0% on the seasons checked. Hitting rows fall from 1,374 (2021) to 794 (2022) and
765 (2025) while pitching rows do not; joined to the raw StatsAPI hitting season cache, the
rows with at least 50 PA are steady (about 550 a season), so the drop is pitchers no longer
batting under the universal DH, not lost hitters. Section 3 takes PA from the raw cache because
of the first fact (default D1).

---

## 1. The component set

LANE_A section 2.1's table, verbatim:

| # | component | form | inputs | label (frozen fWAR vintage field) | incumbent today |
|---|---|---|---|---|---|
| H0 | PA | the champion's exposure walk: year 1 `pt_proj` (F-PTFIT hit), then the `pt` curve deltas `fa_market._decay_path` already applies | corpus | `plateAppearances` | computed, never shown |
| H1 | K%, BB%, ISO, BABIP, HR/PA | `project_player` then the `rate_path` walk | corpus, xISO blend | corpus rates | served inside wOBA/wRC+ |
| H2 | Batting runs | `fwar_frame.wraa` and the league batting term on projected wOBA x PA, park-neutral (PF 1.0), constants held at the last completed season of data/league_constants.json | H0, H1 | `batting` | none (wRC+ only) |
| H3 | Baserunning runs (BsR) | rate per 600 PA: Marcel 5/3/2 of `baseRunning`/PA shrunk toward 0 by PA (K from a fixed grid), plus a sprint-speed term when it earns its place on DEV, plus a linear age term fitted on DEV; times H0 | vintage `baseRunning, wSb, ubr, wGdp`; Savant sprint speed (.cache/savant_sprint, 2015+) | `baseRunning` | zero (the WAR map has no baserunning term; F-REALWAR carries it implicitly) |
| H4 | Fielding runs (Fld, catcher framing inside) | rate per 1,000 innings at the position mix of H5: Marcel of `fielding`/inning, shrunk by innings (grid), with an OAA term (.cache/savant_oaa, 2016+) and an arm term (.cache/savant_arm, 2020+) only if each earns its place on DEV; linear age term | vintage `fielding`; FG fielding cache `Inn, Pos, CFraming` 2011+ | `fielding` | `def_rate` (bWAR war_def + runs_position, F-DEF) |
| H5 | Positional runs (Pos) | `fwar_frame.positional` on projected innings by position: Marcel-weighted share of the last three seasons' innings by position (FG fielding `Inn`, StatsAPI fielding .cache/statsapi_field 2000+), held across the horizon, DH for the uncovered PA | fielding innings | `positional` | inside `def_rate` and `pos_adj_prior` |
| H6 | League runs (Lg) | `league_adjustment_rate` x H0, held at the last completed season | league constants | `wLeague` | none |
| H7 | Replacement runs (Rep) | `replacement_per_pa(2430, rpw, lg_pa)` x H0 | league constants | `replacement` | none |
| H8 | WAR from components | (H2 + H3 + H4 + H5 + H6 + H7) / rpw | | `war` | the served `war` (section 2.2) |
| P0 | IP, role | champion `ip_proj = pt_proj / 4.3` walk (P-IPAGE), GS share Marcel | corpus | `inningsPitched` | computed, never shown |
| P1 | K%, BB%, HR/BF | `project_player` then the walk | corpus | corpus | inside FIP |
| P2 | FIP | `rate_path` FIP path | P1 | `fip` | served |
| P3 | FIP-based WAR (FanGraphs' pitcher WAR) | `fwar_frame` pitcher chain on P0-P2: `fipr9`, `pfipr9` at PF 1.0 with no framing charge, `raap9`, `dynamic_rpw`, `replacement_level(gs, g)`, the relief multiplier on relief innings with P4, `warip` held at the last season | P0-P2, P4 | `war` (pitching) | the served `war` |
| P4 | gmLI (relievers) | Marcel of `gmli` shrunk toward 1.0 by games (grid) | vintage `gmli` | `gmli` | none (the WAR map has no gmLI term) |
| P5 | RA9-based WAR | P3 plus a shrunk gap: Marcel of (`ra9War` - `war`) per 100 IP shrunk toward 0 by IP (grid) | vintage `ra9War` | `ra9War` | none |

Two amendments to the table, recorded rather than edited into it:

- **The H3 and H4 age terms (unifier amendment U6, PLAN 9.7 'One aging service').** The "linear
  age term fitted on DEV" in H3 and H4 is not fitted inside `proj_components.py`. It is
  `aging_v3.AgingModel.component_curve(side, 'bsr')` and `component_curve(side, 'fld')`, fitted
  point-in-time per base B by `aging_v3.fit(corpus, B-1, ...)` with the incumbent delta-method
  estimator (the `aging='v2'` settings) on the frozen-vintage run parts. PJ-C judges each head
  including its age term; docs/AGING_V3_GATE.md does not adjudicate these two curves.
- **The H0 and P0 label sources** are in section 3 (PA from the raw StatsAPI hitting cache,
  default D1; IP, GS and G from the raw StatsAPI pitching cache, ruling R6).

**Choices fixed now, never tuned after a holdout read** (LANE_A 2.1, verbatim):

Shrink constants from fixed four-point grids chosen by DEV MAE alone (H3 {300, 600, 1200, 2400}
PA; H4 {1000, 2000, 4000, 8000} innings; P4 {20, 40, 80, 160} games; P5 {200, 400, 800, 1600}
IP); a Statcast term enters a head only if its DEV paired delta is below zero, and the DEV
decision is recorded before the holdout opens; position mix is held across the horizon (a drift
model belongs to lane AG's position-bucketed aging and enters only through its own gate); every
out-year league constant is held at the last completed season, exactly as `rate_path` holds its
run environment. Two-way players carry both sides' components; the components are means, so no
workload discount applies to them (`TWO_WAY_PIT_PTH_FACTOR` stays a PTH-only display factor).

Player lines are park-neutral (PF 1.0) on every head; the out-year league constants are those of
the last completed season in data/league_constants.json. Veterans only: the /projections/ vet
universe, `MIN_PA, MIN_IP = 100, 30` (proj_export.py@0d4892bb:166). Horizons 1 to 5, each a
MEAN.

**The DEV Statcast admission rule, stated as the decision record.** For each Savant term
(sprint speed in H3; OAA and arm in H4), PJ_4 scores the head with and without the term on DEV
with the section 4 bootstrap and writes `dev.statcast_decisions` into
`data/proj_components_eval.json`: the term, its paired DEV delta (with minus without), its
one-sided upper bound and IN or OUT. A term is IN only if its DEV paired delta is below zero.
The record is written and committed before the HOLDOUT is opened; no term is added, dropped or
reshaped after it. The arm term (2020+) is DEV-only by construction and never enters a verdict
head (LANE_A 2.4).

---

## 2. Coherence: components and the WAR head

- **Components are means.** Each is an expected value, so they add: H8 = sum / rpw is a sum of
  means. The served `war` (the ML q50 with the lift-only mean blend) and `warChamp` (the
  champion mean the team roll-up sums) are unchanged by anything in this document.
- **The gap line.** Every season the card prints the components, the WAR they imply (H8 or P3)
  and one labelled line, "rest of the served projection" = served `war` minus component WAR, so
  components plus gap equals the served `war` on every row by construction (owner answer PJ-Q1).
  The eval artifact publishes the gap's distribution by side, horizon and age band.
- **The tripwire.** A pooled mean gap beyond 0.30 WAR (either sign) at h1 on the HOLDOUT rows
  blocks any flip, whatever the per-head verdicts say. The gap is computed with the served
  engine's point-in-time path for each HOLDOUT base, never with a realized WAR.
- **Ranges, never summed.** Each component's 80% range comes from its own DEV residual
  quantiles by horizon and exposure tier, the construction of Gate 1's `band_quantiles` in
  data/fa_gate1_eval.json (keys such as `hit:lo`, `hit:hi`, `pit:hi`, each with `q10`, `q90`,
  `n`). Coverage is measured on the HOLDOUT, pooled and survived-only. No range is summed across
  components, no WAR range is built from component ranges (the WAR range stays the WAR head's
  own `warP10` / `warP90`), and a test asserts that no served key equals a sum of component P10
  or P90 values.
- **No WAR-label mean head.** Component WAR is never fed to `proj_ml.predict_path`, never a
  recenter target and never a head trained on the WAR label (PROJ_PATH_SHAPE_GATE.md section 15
  bans the mean-head arms).

---

## 3. Labels and frames

**Labels.** Every label is a field of the frozen fWAR vintage read through `fwar_vintage.load()`
(section 0.4), except the three pitching exposure fields and PA, which the vintage does not
carry:

- Hitting, from the vintage: `batting`, `baseRunning`, `fielding`, `positional`, `wLeague`,
  `replacement`, `war`, `wSb`, `ubr`, `wGdp`.
- Hitting PA (`plateAppearances`): the vintage field is null on every row of every season
  (section 0.4), so **PA comes from the raw StatsAPI hitting season cache
  `.cache/fa_statsapi_hitting_<season>.json`, read through `fa_sources.fetch_statsapi_season_stats(season, "hitting")`,
  summed over a traded player's team rows, joined on mlbam and season** (default D1, the same
  treatment ruling R6 gives IP). This is the H0 label and every per-PA denominator (H3's rate per
  600 PA, the exposure weights). If a later vintage season ever carries `plateAppearances`, the
  raw cache stays the source for this gate; the two are not mixed.
- Pitching, from the vintage: `war`, `rar`, `fip`, `xfip`, `ra9War`, `gmli`, `exli`, `pli`.
- Pitching `inningsPitched`, `gamesStarted`, `gamesPlayed`: not in the saber feed; from the raw
  StatsAPI season cache `.cache/fa_statsapi_pitching_<season>.json` read through `fa_sources`,
  never from the vintage (round 4, ruling R6).
- The live `.cache/statsapi_saber_*` files are never a label. A house eWAR v3 part is never a
  label (unifier U2; eBR plan section 5).

**Frames.** Forward-chained by base B; a cell (B, h) has label season B + h - 1; label season
2020 is excluded as Gate 1 excludes it; every lag reads seasons <= B - 1 only.

| frame | bases | cells | label seasons | use | verdict |
|---|---|---|---|---|---|
| DEV | 2014 to 2021 | every (B, h) with label season <= 2021, 2020 excluded | 2014 to 2021 ex 2020 | grids, Statcast admission, residual quantiles, MDE95 | no |
| HOLDOUT | 2022 to 2024 | (2022, h1-h4), (2023, h1-h3), (2024, h1-h2) | 2022 to 2025 | the one look (section 5) | yes, once |

Label season 2026 is never read by this gate. No WAR residual is computed on either frame. The
realized `war` field enters only as P5's subtrahend, inside the RA9 gap label (`ra9War` - `war`),
which is a component label. The gap line of section 2 is served `war` minus component WAR, two
projections, so it reads no realized WAR at all.

---

## 4. PJ-C, the component gate

### 4.1 Heads under verdict

- **H3**, baserunning runs (BsR).
- **H4 + H5 together**, Fld + Pos, the quantity `fa_projection.def_rate` estimates.
- **P4**, gmLI, judged through the relief WAR it multiplies (the P3 relief term with the
  projected gmLI against the same term with each comparator's gmLI).
- **P5**, the RA9 gap (`ra9War` - `war`).

### 4.2 Deterministic heads: receipts, not verdicts

H0 to H2, H6 to H8 and P0 to P3 are deterministic transforms of the Gate 1 engine. Each gets:

- the replica identity on realized inputs: `fwar_frame` on realized inputs reproduces the
  vintage within data/fwar_replica_eval.json's tolerance;
- DEV and HOLDOUT MAE published beside Gate 1's wRC+ and FIP figures.

No receipt is a verdict and none gates a flip, except the exposure test below.

### 4.3 The H0 and P0 exposure test (round 4, completeness 7)

- Statistic: exposure MAE (PA for H0, IP for P0) on HOLDOUT, h1, survived rows.
- Comparators, both required, on identical rows: the prior-season exposure, and the 5/4/3
  weighted three-season exposure. They are comparators only, never candidates.
- Bootstrap, seed and VIF as 4.5.
- PASS iff the one-sided 95% upper bound of the paired delta (candidate minus comparator) is
  below 0 against both.
- PJ_5 reads it at the look; PJ_8 serves the PA and IP lines only on a PASS, and otherwise they
  print 'not projected'.

### 4.4 The primary statistic and the comparators

- **Primary:** exposure-weighted rate MAE on survived rows, h1, HOLDOUT. Hitters (H3, H4 + H5)
  in runs per 600 PA, weighted by actual PA. P5 in runs per 100 IP (the WAR gap converted at the
  label season's runs per win in data/league_constants.json), weighted by actual IP.
- **P4 through the relief WAR it multiplies.** Per reliever row the error is
  |m(projected gmLI) - m(vintage `gmli`)| x R per 100 relief IP, where m(x) = (1 + x) / 2 is
  FanGraphs' relief multiplier and R is one constant, the DEV mean of relievers' runs above
  replacement per 100 IP before the multiplier, frozen in PJ_4's `dev` block. Weighted by actual
  relief IP. Because R is a constant, the verdict is the same as for relief-IP-weighted gmLI MAE;
  R only puts the figure in runs.
- **Secondary, reported, not gating:** runs MAE at projected playing time; 80% range coverage
  pooled and survived-only; the gap distribution.
- **Comparators, both required:**
  - NAIVE: the player's PA-weighted (IP-weighted for pitchers) three-season raw rate, weights
    5/4/3, the Gate 1 naive form.
  - IMPLICIT: what the served engine assumes today. 0 for BsR and for the RA9 gap; 1.0 for
    gmLI; `fa_projection.def_rate` translated to runs per 600 PA for Fld + Pos.

### 4.5 The bootstrap and power

- Paired bootstrap clustered on player, B 1000, seed 20261124, VIF 1.8 applied to every sd
  (the path-shape convention, PROJ_PATH_SHAPE_GATE.md 3.2).
- MDE95 one-sided (1.645 sd after the VIF) per head and per comparator, computed on DEV and
  published in `data/proj_components_eval.json` `dev.mde95` before the look.
- **UNDERPOWERED** when a head's DEV MDE95 exceeds 10% of its NAIVE MAE: the head does not ship,
  whatever the HOLDOUT says.

### 4.6 Pass per head

All of:

1. h1 HOLDOUT: one-sided 95% upper bound of the paired delta (head minus comparator) below 0
   against NAIVE and against IMPLICIT.
2. h2 and h3 HOLDOUT: upper bound below +10% of the comparator's MAE, against both.
3. Star slice (>= 500 PA or >= 120 IP in base - 1), h1 HOLDOUT: upper bound below +10% of the
   comparator's MAE, against both.

A failed or UNDERPOWERED head is not served; its runs ride in the gap line and the card says
'not projected'. A pass makes a head eligible for PJ_8's flip; the flip still needs the gap
tripwire (section 2) clear.

### 4.7 The Position Fit disclosure split (default D3)

Because Position Fit's conversion test (section 0.1) scored a projection of a closely related
fielding rate on 74 position-mover rows with label seasons 2022 to 2025, PJ_5 also publishes the
H4 + H5 h1 HOLDOUT statistics with those player-seasons removed (the movers in
`data/positional_fit.json` `conversion_accuracy` as of this registration, matched on mlbam and
label season), labelled READ-EXCLUDED. It carries no verdict and cannot rescue or sink the head;
it shows whether the verdict depends on rows a prior read touched.

---

## 5. The look

**When.** Once, on the first day after PJ_4_COMPONENT_HEADS_DEV lands with its DEV selection,
DEV MDE95 and Statcast decisions committed in `data/proj_components_eval.json` `dev`, on which
the HOLDOUT frame of section 3 is complete in the frozen vintage (it is: label seasons 2022 to
2025 are frozen in vintage `2026-10-02-0341299c20ec`) and no other registered look is recorded
or defined for that day (docs/*GATE*.md and docs/**/*GATE*.md, the Part 9 floor list, the
Prospect Anchor day of PROSPECT_ANCHOR_GATE.md section 14, the eFV reserved read). That day,
and the reason for any slip, are written in section 9 before scoring. This replaces the plan's
fixed 2026-11-25 (owner decision EPOCH-NOW, 2026-10-02: the Part 9 looks are registered as the
earliest day their build and frame are complete; default D2). The seed 20261124 is a constant
and does not move with the day.

**How.**

1. The whole reporting path is dry-run on fixtures with nulls first (PJ_3's fixtures).
2. stdout and stderr are teed to the task's output directory before anything else runs.
3. An exception after scoring began STOPs without a rerun and writes OWNER_QUESTION.md.
4. A null is a finding; nothing ships on it.

**What it writes.** Whatever the outcome, `data/proj_components_eval.json` gains the `holdout`
block, the registry row `proj_components` moves to `provisional` with
`data/proj_components_eval.json` as its eval artifact, and section 9 gains one row per head.

---

## 6. PJ-W, the WAR arms

- **W1**: component WAR (H8 hitters, P3 pitchers) against the served `war`, h1. A Marcel-family
  estimator; the served head beat the Marcel champion at h1 (LANE_A A6), so the registered prior
  is that W1 loses or ties. It decides one thing: whether a component WAR could ever be the
  served WAR (never before this read, and then only on the owner's word).
- **W2**: a dark twin of the serving `proj_lgbm` bundle with added features: projected BsR, Fld
  and Pos runs per 600 PA; last-season sprint speed with a missing flag; projected gmLI for
  pitchers; the RA9 gap. Same hyperparameters as the serving bundle (whatever the path-shape
  battery leaves serving). Trained point-in-time under `proj_ml.train_cached` rules into
  `model/proj_lgbm_components/`, never loaded by the served path.

**Both arms.**

- Label: the 2027 fWAR season total from the frozen vintage (frozen by FWAR_VINTAGE_FREEZE_2027).
- Rows: the veterans in the Opening Day 2027 frozen vintage (docs/PROJ_FORWARD_VINTAGE_GATE.md,
  task M15, as amended by task PJ_10 to carry the component lines, H8/P3 and W2's paths; that
  document does not exist at this registration), identical for both models, row-matched like
  `proj_eval.run_rowmatch`.
- h1; an absent season counts as 0 WAR (pooled, primary); survived-only is secondary.
- Star slice: base WAR >= 4. Tail ratio at 3 WAR, reported.
- Paired bootstrap clustered on player, B 1000, seed 20271109, VIF 1.8.
- **Pass:** one-sided 95% upper bound of the delta pooled MAE below 0 AND star-slice upper
  bound below +0.0065.
- **UNDERPOWERED:** MDE95 >= 0.0065 after the VIF. Nothing ships, and the record registers one
  accumulation read (label seasons 2027 and 2028, h1 and h2) for November 2028.

**The expected outcome, stated now.** About 0.010 WAR of MAE is resolvable on one season:
0.0027 x sqrt(20,721 / 1,400) = 0.0104, from Gate 1's F-REALWAR MDE95 0.00270 at n 20,721
(fa_projection.py@0d4892bb, at 'SHIPPED 2026-07-30, DEFAULT ON'). Past WAR-level data arms
moved MAE by 0.0027 to 0.0189, and a component arm aimed at baserunning and fielding sits at the
low end. **UNDERPOWERED is the likely verdict.**

**The W2 veto read (round 4, leakage 9).** Forward-chained point-in-time W2 bundles (labels <=
B - 1) scored on bases 2022 to 2025 at h1 against the same-base incumbent bundles, labelled READ.
Bases 2015 to 2021 are not point-in-time, because `model/proj_components/params.json` is frozen
on DEV labels up to 2021, so they are not read. A pooled one-sided upper bound at or above
+0.0065 vetoes W2 whatever 2027 says; no number from this read may be cited for a pass. PJ_9
runs it after the path-shape ARM B verdict.

**When.** Once, on the first day after PJ_9_STACK_ARM_DARK, PJ_10_FORWARD_FREEZE_AMENDMENT and
PJ_8_COMPONENT_FLIP (or PJ_8's recorded no-flip) have landed on which the 2027 season is frozen
in the vintage (FWAR_VINTAGE_FREEZE_2027) and the Opening Day 2027 forward vintage exists, and no
other registered look is recorded or defined for that day. This replaces the plan's "later of
2027-11-09 and seven days after the 2027 season exists in the frozen vintage" (owner decision
EPOCH-NOW; default D2). The seed 20271109 is a constant.

---

## 7. Bans

LANE_A section 7, verbatim:

- No Statcast contact-quality input to the WAR head or the batting component (A7: rejected
  2026-06-23 and four pWOBA arms); the xwOBA batting arm is NOV15's re-gate, not duplicated here.
- No mean head on the WAR label in any form, no pooled age recentering, no catcher or age lever
  (PROJ_PATH_SHAPE_GATE.md section 15; ARM B owns the levers).
- No WAR verdict on label seasons 2008-2026 (A8); no re-test of a WAR arm on the read 2015-2025 frame
  except W2's veto-only read.
- No hitter ISO cohorts, no Marcel 5/4/3, no pitcher PTFIT, no IL-history playing-time features (all
  measured losses, A7).
- No ML path into FA market pricing (do-not-reopen 10; `FA_PRICING_USE_DEF` and `use_ml=False`
  stay); W2 never reaches /fa/.
- No summing of quantile points, no WAR range from component ranges.
- No cohort intercepts or team-level recalibration (three consecutive losses).
- No house eWAR v3 part as a training label (EBR plan section 5).
- No scripted FanGraphs pull (docs/SOURCE_AUDIT.md); the benchmark uses only files the owner saves.
- No licensed playing-time model (not on disk).
- No prospect component lines (lane TL) and no aging-curve refit (lane AG).
- No change to bracket_v1, to the futures ledger's scorer (M12-20) or to `fa_fit` inputs.

Plus:

- No Savant term is added after DEV records its decision (section 1).
- No grid is extended or re-chosen after the look.
- No WAR label season 2008 to 2026 is read, except W2's veto read (bases 2022 to 2025, section 6)
  and PJ_12_PUBLIC_BENCHMARK's industry READ (the incumbent engines only, h1, labelled READ, never
  label season 2026 or 2008 to 2014; round 4, leakage 7). Owner answer PJ-Q4 (OVERRIDE) closed
  PJ_12 as NOT NEEDED, so that second exception has no user; it is kept here as registered and
  admits nothing else.
- No PJ task edits `proj_ml.py`, `fa_market.py` or `fa_projection.py` before
  data/proj_shape_gate.json carries the path-shape ARM B verdict, or PROJ_PATH_SHAPE_GATE.md
  section 19 records the battery closed.
- The 5/4/3 weighting appears only as a comparator (NAIVE, and the exposure comparator of 4.3),
  never as a candidate (PLAN 9.10).
- Copy never claims the WAR got more accurate (owner answer PJ-Q2); PJ_7 and PJ_8 carry the ban.

---

## 8. Served flags, blast radius and registry rows

### 8.1 Flags (LANE_A section 2.8, verbatim, for PROJ_COMPONENTS_LIVE and W2)

| flag | moves | never moves |
|---|---|---|
| `PROJ_COMPONENTS_LIVE` | adds keys only: `vets[].pa/ip`, `comp` block per vet in data/mlb_player_detail.json, board scalar `pa[0]`/`ip[0]` | every existing key of every vet row (`war`, `warChamp`, `warY1Champ`, `woba`, `wrc`, `fip`, surplus), trade values, FA, arbitration, Ledger, Franchise, betting inputs (`woba[0]`, `warY1Champ`) |
| W2 (never served by this lane) | nothing | everything |

`PROJ_COMPONENTS_LIVE` is a module flag in proj_export, default off, read by
assets/projections.js from the payload's `components_live`. While it is off the exporter writes
component lines only under a preview path in `.cache`. A test pins `war`, `warChamp`,
`warY1Champ`, `woba`, `wrc` and `fip` byte-identical with the flag on and off. The player detail
may grow by at most 15%; the export task measures the growth and stops above it.

### 8.2 Registry rows, defined here, written by PJ_3_COMPONENT_SCORER after step Z

data/model_registry.json is served and carries uncommitted pipeline churn, so this registration
does not write it (round 4, mechanics 3). PJ_3 writes both rows against `git show HEAD:`,
staging only the new rows' hunks, runs tools/gen_audit_docs.py and the registry tests, and marks
both rows internal if test_methodology_freshness.py needs it.

```
proj_components:
  surface: none yet (registered, not served); on a pass, the component lines of the /projections/ player Projection tab
  predicts: per veteran and season, FanGraphs-frame WAR components (batting, baserunning, fielding, positional, league, replacement runs; pitcher FIP-based and RA9-based WAR) as means, and playing time
  champion: none
  baseline: a naive three-season rate and the served engine implicit value per component
  metric: PJ-C, docs/PROJ_COMPONENTS_GATE.md section 4
  eval_artifact: null
  verdict: unvalidated
  registration_status: registered, not read
  depends_on: [fa_projection_marcel, fa_war_paths_decay]

proj_component_stack:
  surface: none (dark twin bundle, never served under this registration)
  predicts: veteran WAR paths with component stack features
  champion: none
  baseline: the serving proj_lgbm bundle
  metric: PJ-W, docs/PROJ_COMPONENTS_GATE.md section 6
  eval_artifact: null
  verdict: unvalidated
  registration_status: registered, not read
```

### 8.3 Defaults taken at registration

- **D1.** PA (the H0 label and every per-PA denominator) from the raw StatsAPI hitting season
  cache through `fa_sources`, because the vintage's `plateAppearances` is null on every row of
  every season (section 0.4).
- **D2.** Both looks registered as conditions (the earliest day the build and the frame are
  complete, off every other look day), replacing 2026-11-25 and "later of 2027-11-09 and seven
  days after", under owner decision EPOCH-NOW. Seeds unchanged.
- **D3.** The Position Fit conversion test is a disclosed prior, not a STOP, with the
  READ-EXCLUDED split of 4.7.

An amendment to this document is admissible only before the PJ-C look (for sections 1 to 5) or
the PJ-W look (for section 6), on an established fact about the data, filed with what moved on
disk since this document was committed, and it may not loosen any threshold.

---

## 9. The append-only record

Empty at registration. Every look, VOID, amendment or slip this gate authorises appends a row
here with its date, gate (PJ-C or PJ-W), verdict, artifact hash and notes. A row is never
deleted or edited; a correction is a new row. Nothing above this section changes once anything
is written in it.

| date | gate | verdict | artifact | notes |
|---|---|---|---|---|
| 2026-10-09 | PJ-C | DEV frozen (no verdict; nothing served moves) | model/proj_components/params.json, params sha256 da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6 | DEV frozen 2026-10-09 at fa4873a7, params sha256 da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6. Task PJ_4_COMPONENT_HEADS_DEV: bases 2014 to 2021, label seasons 2014 to 2019 and 2021 (25 cells, 32,123 scorer rows), seed 20261124, B 1000, VIF 1.8. Shrink constants by h1 DEV rate MAE: bsr_pa 300, fld_inn 1000, gmli_g 20, ra9gap_ip 1600. Statcast decisions (section 1, the DEV admission rule): sprint speed IN (h1 paired delta with minus without -0.0268 runs per 600 PA, ub95 +0.0064), OAA OUT (+0.0036, ub95 +0.0346), arm OUT (delta 0; no DEV row precedes a base that carries it, DEV-only by construction). R 3.8183 runs per 100 IP (section 4.4). DEV MDE95 (one-sided, after the VIF) at h1 vs NAIVE and vs IMPLICIT: bsr 0.063 / 0.176; fld_pos 0.206 / 0.472; gmli_relief 0.012 / 0.050; ra9_gap 0.296 / 0.044; none above 10% of its NAIVE MAE. The DEV tables, the Statcast decisions and the receipts (fwar_frame on realized inputs reproduces the frozen vintage on 2011 to 2021 for batting, wSB, BsR, positional, league, replacement and pitcher FIP runs, share within 1.0 run = 1.000 each season; the vintage differs from the live feed on 5,455 of 21,253 rows, max 0.898 runs) are in model/proj_components/dev_receipt.json; PJ_5 carries the dev block into data/proj_components_eval.json. Nothing under data/ was written; the registry row proj_components stays unvalidated. Defaults D1 to D11 are named in commit fa4873a7. The age terms of H3 and H4 are aging_v3 component_curve('hit', 'bsr' | 'fld') fitted at B - 1 (U5); the framing residual inside H4 carries no age term. |
| 2026-10-14 | PJ-C | look day set (no verdict; nothing served moves) | none yet | The PJ-C look of section 5 runs today, 2026-10-14 (task PJ_5_COMPONENT_LOOK, worktree lane 203, branch wt-PJ_5_COMPONENT_LOOK). The registered rule gives the first day after PJ_4_COMPONENT_HEADS_DEV landed (fa4873a7 and 14f9c5a5 on 2026-10-09, integrated at 1444d9f9) on which the HOLDOUT frame is complete in vintage 2026-10-02-0341299c20ec (it is: label seasons 2022 to 2025 are frozen) and no other registered look is recorded or defined for the day; that day was 2026-10-10. Slip of four days, reason: the task was dispatched on 2026-10-14 (an earlier dispatch of this lane never reported and left no commit and no working-tree change). Checked today: no look record in docs/*GATE*.md or docs/**/*GATE*.md is dated 2026-10-14; the nearest registered days are 2026-10-17 and 2026-10-18 (PROVISIONAL_ODDS_GATE.md, SURPLUS_ODDS_GATE_2.md, FANTASY_PROSPECT_LEG_GATE.md, GRPO_FORWARD_GATE.md) and 2026-10-20 (the W11_3 read); the Prospect Anchor day is 2026-11-20 (step Z 2026-10-03 plus 14 days is 2026-10-17, the later of the two is 2026-11-20); the eFV reserved read is cancelled (owner 2026-10-08). Also verified before this row: model/proj_components/params.json hashes to the recorded da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6, data/proj_components_eval.json does not exist, no run_monthly.py and no pytest process. Filed as the docs-only late-look amendment (Part 9 ruling R8) and committed alone before any scoring; the seed 20261124 and every threshold are unchanged; this row loosens nothing. |
| 2026-10-14 | PJ-C | PASS (H3 BsR) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | H3 BsR: h1 HOLDOUT survived n 1359, star n 399, rate MAE 1.8547. vs NAIVE (MAE 2.0548): h1 delta -0.2000 ub95 -0.1194; star delta -0.0913 ub95 -0.0247 (bar 0.1771); h2 ub95 -0.1689 (bar 0.2137); h3 ub95 -0.0591 (bar 0.2166); DEV MDE95 0.0627 against the 10% NAIVE bar 0.2351. vs IMPLICIT (MAE 2.6038): h1 delta -0.7490 ub95 -0.5446; star delta -0.7489 ub95 -0.4424 (bar 0.2429); h2 ub95 -0.5079 (bar 0.2597); h3 ub95 -0.4257 (bar 0.2621); DEV MDE95 0.1755 against the 10% NAIVE bar 0.2351. |
| 2026-10-14 | PJ-C | PASS (H4 + H5 Fld + Pos) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | H4 + H5 Fld + Pos: h1 HOLDOUT survived n 1359, star n 399, rate MAE 5.4415. vs NAIVE (MAE 5.9836): h1 delta -0.5421 ub95 -0.2206; star delta -0.2547 ub95 0.1320 (bar 0.4609); h2 ub95 -0.3363 (bar 0.6505); h3 ub95 -0.5440 (bar 0.7218); DEV MDE95 0.2055 against the 10% NAIVE bar 0.6240. vs IMPLICIT (MAE 7.9288): h1 delta -2.4873 ub95 -1.9044; star delta -2.1620 ub95 -1.3264 (bar 0.6516); h2 ub95 -1.4973 (bar 0.7909); h3 ub95 -1.3068 (bar 0.8192); DEV MDE95 0.4721 against the 10% NAIVE bar 0.6240. READ-EXCLUDED (Position Fit movers removed, 46 rows): MAE 5.4644, vs NAIVE delta -0.5405 ub95 -0.2253, vs IMPLICIT delta -2.5128 ub95 -1.9453; no verdict. |
| 2026-10-14 | PJ-C | UNDERPOWERED (P4 gmLI (through the relief runs it multiplies)) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | P4 gmLI (through the relief runs it multiplies): h1 HOLDOUT survived n 831, star n 1, rate MAE 0.5008. vs NAIVE (MAE 0.5255): h1 delta -0.0248 ub95 -0.0059; star delta -0.0088 ub95 n/a (bar 0.0234); h2 ub95 -0.0117 (bar 0.0603); h3 ub95 -0.0014 (bar 0.0633); DEV MDE95 0.0115 against the 10% NAIVE bar 0.0499. vs IMPLICIT (MAE 0.6450): h1 delta -0.1442 ub95 -0.0792; star delta 0.0121 ub95 n/a (bar 0.0213); h2 ub95 -0.0169 (bar 0.0664); h3 ub95 0.0211 (bar 0.0688); DEV MDE95 0.0501 against the 10% NAIVE bar 0.0499 EXCEEDS. reasons: DEV MDE95 exceeds 10% of the DEV NAIVE MAE against: implicit (gate 4.5); the head does not ship whatever the HOLDOUT says; star h1 ub95 vs naive not below +10% of its star MAE (None vs 0.02338); star h1 ub95 vs implicit not below +10% of its star MAE (None vs 0.02128). |
| 2026-10-14 | PJ-C | FAIL (P5 RA9 gap) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | P5 RA9 gap: h1 HOLDOUT survived n 1458, star n 288, rate MAE 7.2995. vs NAIVE (MAE 8.7887): h1 delta -1.4892 ub95 -1.0476; star delta -0.8292 ub95 -0.3072 (bar 0.6480); h2 ub95 -1.2958 (bar 0.9310); h3 ub95 -1.5388 (bar 0.9738); DEV MDE95 0.2959 against the 10% NAIVE bar 0.8653. vs IMPLICIT (MAE 7.3286): h1 delta -0.0291 ub95 0.0191; star delta -0.0421 ub95 0.0617 (bar 0.5693); h2 ub95 0.0416 (bar 0.7462); h3 ub95 0.0985 (bar 0.7479); DEV MDE95 0.0443 against the 10% NAIVE bar 0.8653. reasons: h1 ub95 vs implicit not below 0 (0.0191). |
| 2026-10-14 | PJ-C | FAIL (H0 PA (exposure test)) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | H0 PA (exposure test): h1 HOLDOUT survived n 1359, exposure MAE 128.05. vs prior_season (MAE 131.98): delta -3.93 ub95 2.04 MDE95 5.96. vs w543 (MAE 137.11): delta -9.06 ub95 -2.89 MDE95 6.17. reasons: h1 ub95 vs prior_season not below 0 (2.0385). PJ_8 serves the line only on a PASS; otherwise it prints 'not projected'. |
| 2026-10-14 | PJ-C | FAIL (P0 IP (exposure test)) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | P0 IP (exposure test): h1 HOLDOUT survived n 1458, exposure MAE 32.14. vs prior_season (MAE 33.03): delta -0.89 ub95 0.48 MDE95 1.38. vs w543 (MAE 32.67): delta -0.54 ub95 0.94 MDE95 1.48. reasons: h1 ub95 vs prior_season not below 0 (0.483); h1 ub95 vs w543 not below 0 (0.9414). PJ_8 serves the line only on a PASS; otherwise it prints 'not projected'. |
| 2026-10-14 | PJ-C | gap tripwire clear | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | Pooled mean (served war minus component WAR) at h1 on the HOLDOUT rows 0.0304 WAR (threshold 0.30 either sign; n 3944, sd 0.2848, p10 -0.2891, p50 0.0338, p90 0.3413); hitters 0.0708 (n 1869), pitchers -0.0061 (n 2075); by age band <=26 0.0190 (n 725), 27-30 0.0569 (n 1609), 31-34 0.0104 (n 1066), 35+ 0.0060 (n 544). Served = point-in-time proj_lgbm_v1 bundles (labels <= B - 1) with the served lift lambdas, champion fallback; never a label. |
| 2026-10-14 | PJ-C | flip (class 2; no verdict, nothing scored) | data/proj_components_eval.json sha256 b49295af34efa6c8b521f4a04304c8765c4df1ebc007bff43f8e22f5ccf6c0db | PJ_8_COMPONENT_FLIP sets proj_export.PROJ_COMPONENTS_LIVE True on the verdicts above, read at export time from the artifact (fail closed): H3 BsR and H4 + H5 Fld + Pos are served; P4 gmLI, P5 RA9 gap (and the RA9-based WAR line), H0 PA and P0 IP are null in every block and print 'not projected', their runs in the gap line (the relief share priced at gmLI 1.0). Owner answers PJ-Q1 (a), PJ-Q2 (a), PJ-Q3 (a). Taken ahead of the queue's not-before of 2026-11-26 under the owner's waiver of registered dates (EW3-5, 2026-10-14). |
| 2026-10-14 | PJ-W | W2 veto read: not vetoed (READ; no verdict, no pass cited) | data/proj_horizon_eval.json challenger_blocks.component_stack_tier2_veto, artifact sha256 3fe1ae672efaa95b947bb80982ea40305dcfc13f0e8fd9a1abe213d8528c9d7b | Task PJ_9_STACK_ARM_DARK (worktree lane 208, branch wt-PJ_9_STACK_ARM_DARK). The W2 Tier-2 veto read of section 6 (round 4, leakage 9): bases [2022, 2023, 2024, 2025], h1, forward-chained point-in-time twin (proj_lgbm_components_v1) and incumbent (proj_lgbm_v1, proj_ml.train_cached) bundles with labels at most B - 1, full quantiles, no blend lambdas, the raw monotone q50 as the point, identical rows, an absent season 0 WAR; twin minus incumbent MAE; paired bootstrap clustered on player B 1000, seed 20261119, VIF 1.8 on the sd; one-sided 95% upper bound. Pooled: n 8866 rows, 2824 players, MAE twin 0.4390, incumbent 0.4393, delta -0.0003, ub95 +0.0027, MDE95 +0.0031, bar +0.0065. Survived only: n 5021, delta -0.0015, ub95 +0.0039. Star slice (base WAR at least 4): n 227, delta +0.0064, ub95 +0.0544. Per base: 2022 n 2103 MAE twin 0.4795 incumbent 0.4728 delta +0.0067; 2023 n 2182 MAE twin 0.4313 incumbent 0.4361 delta -0.0048; 2024 n 2326 MAE twin 0.4253 incumbent 0.4285 delta -0.0032; 2025 n 2255 MAE twin 0.4227 incumbent 0.4223 delta +0.0004. Per side: hit n 3624 delta -0.0006; pit n 5242 delta -0.0001. Stack schema 6fe8bc02: proj_ml.feature_names plus bsr_rate_proj, fld_rate_proj, pos_rate_proj, sprint_l1, sprint_missing (hitters) and gmli_proj, ra9_gap_proj (pitchers), from the DEV-frozen heads at h1 (params sha256 da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6, vintage 2026-10-02-0341299c20ec); a column the heads cannot project is NaN (LightGBM missing). Twin of the incumbent serving bundle (train_hash 248baa38d8b7144a, max_label_season 2025, war_provider fwar; proj_ml.LGBM_PARAMS and _params_for per horizon, checked against its meta). Label READ; no number here is cited for a pass; the 2027 look (PJ_11) stays the verdict. The twin for the Opening Day freeze is trained by tools/proj_component_stack.py --final into model/proj_lgbm_components/ and is never loaded by the served path. Wall 884.0 s. |

**2026-10-14, owner-waived early read (EW3-5; task PJ_9_STACK_ARM_DARK).** Section 6 registered the W2 veto read to run after the path-shape ARM B verdict (ARM B look 2026-11-13; PLAN 9.7 'W2 waits for ARM B', PJ_9 queued 2026-11-19). The owner's waiver of 2026-10-14 (EW3-5: no registered dates, no look days; wait only for data that does not exist) was applied to that wait: the ARM B verdict is another lane's registered look, not data, and everything the read needs exists (the fWAR corpus with label seasons through 2025, the incumbent serving bundle on fwar, the DEV-frozen component params, the frozen vintage). The read is therefore recorded as an OWNER-WAIVED EARLY READ, and the twin is a twin of the INCUMBENT serving bundle (proj_lgbm_v1, train_hash 248baa38d8b7144a). If ARM A or ARM B later changes the serving bundle, the twin's caches miss by construction (keyed by the extended schema hash, the params hash and max_label_season) and PJ_10 rebuilds it with --final before the Opening Day freeze; the veto verdict above is read once and is not rerun. The PJ-C look record of the same day (lane 203) was not a same-day stop under the waiver. No threshold, seed or frame of section 6 moved.

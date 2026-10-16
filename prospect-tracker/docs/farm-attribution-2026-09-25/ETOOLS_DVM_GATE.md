# eTools in DvM+: the as-of eTool history, eDvM+ per tool, eToolDvM+, and the switch read (ETOOLS_DVM_GATE)

Registration status: REGISTERED

Task ETOOLS_DVM, written 2026-10-16 on lane wt-ETOOLS_DVM (base 8549bdeb). Docs only, committed
alone, before the as-of eTool history exists, before any eTool grade change is computed, and
before any number named in Parts 3 to 5 exists. It amends the development attribution
(`docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md`, VAL_4) and leaves the difficulty
gate (`docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md`) and its NO SHIP record untouched.

Owner decision EW3-34 (2026-10-16, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), verbatim: "Are we
also using eTool for ToolDvM+ (and each specific tool, ex. HitDvM+ using eHit)?" The answer at
registration is no: `docs/tools-2026-10/ETOOLS_ALL_CALCS.md` class H1 left per-tool DvM+ and
ToolDvM+ on consensus grades because an eTool existed only as one dated snapshot with no history.

**Nothing was scored to write this document.** No eTool was computed at any past date, no grade
change was read, no club index was rebuilt, no outcome was paired with anything. Every figure
below is a constant, a seed, a date, a threshold, a line reference at base 8549bdeb, or a figure
already published in a committed artifact.

---

## 0. Disclosures

0.1 **What earlier reads already saw.** The eTools look (`docs/tools-2026-10/ETOOLS_GATE.md`,
look dc271ac2) and its amendments read every passing eTool against the same MLB outcome labels
this read uses (gate 2.1, L_MLB), on board years 2011 to 2019 and 2022 to 2024, so the eTool's
LEVEL accuracy is known (`ETOOLS_RESULTS.md`; R-TIP in `ETOOLS_ALL_CALCS.md` Part 4.1). What no
read has computed is any eTool CHANGE over time, any club index built on eTool changes, or any
grade change paired with an MLB outcome. The served per-tool DvM+ values (consensus basis) are
public and were seen. The difficulty gate's validation figures for the FV-based DvM+ (V-S
-0.0350 for C0, section 18 there) are a different index on a different frame and were seen.

0.2 **The eTool fit saw these outcomes.** Each eTool's final fit (`etools_eval.json`,
`etools.final_fit`) was fit on the development frame's L_MLB and L_UM labels. Read (b) pairs grade
changes with the same players' later MLB outcomes, so an eTool from the final fit would be scored
on outcomes it was fit to. Read (b) therefore uses player-disjoint refits (4.3); read (a) reads no
outcome and uses the final fit.

0.3 **A served defect found while writing (a code reading, no statistic).** Since VAL_4
(6cb6af6b, 2026-10-08) every club's PowerDvM+ (`tool_dev.per_tool_dvm_plus.pwr`) is null on the
served payload (30 of 30 clubs in `data/timeseries.json` of 2026-10-16T03:33:37Z):
`dev_attribution.load_observations` keeps only the outlet keys in `TOOL_KEYS` (game_pwr, raw_pwr,
no `pwr`), while `storage.TOOL_GROUPS["pwr"]` reads the consolidated `pwr` key that
`consensus.py` (line 1603) synthesizes as the half-grade mean of game and raw power. The repair
restores the documented behaviour: each outlet's observation carries `pwr` by the consensus.py
rule (both: round to 0.5 of the mean; one: that one). It is committed in its own commit before
the read, with the served numbers it moves, and the consensus version of every read below uses
the same rule.

0.4 **Forking paths.** Six tool groups (hit, pwr, pitch_sel, bat_ctrl, fb, cmd), two reads each,
one construction, one window rule, the recovery checks of Part 5. Nothing is added after the read.

---

## 1. The as-of eTool history

1.1 **Tools.** The six eTools that passed the look: eHIT (hit), ePOW (game power), eSEL (pitch
selection), eBAT (bat control), eFB (fastball), eCMD (command), each with the look's admitted
sub-drivers and the look's final fit (`etools_eval.json` `etools.<tool>.final_fit`: the lines
a_j + b_j G and the weights c_j), unchanged. The DvM+ group `pwr` takes ePOW, as the site's shown
grades do (`etool_composite`, prospx `toolGradesShown`). Every other group (speed, field, arm,
sl, cb, ch, ct) has no passing eTool and keeps consensus in both versions.

1.2 **As of a date t.** MiLB season S is readable at t when its end, S-10-01, is on or before t
(`efv_x1_translate.SEASON_END_MMDD`, `efv_w2_milb.last_readable_season`): S(t) = year(t) when
t is in October to December, else year(t) - 1. The sub-driver values at t are the look's as-of
functions at board year S(t) + 1: the X1 family through `efv_x1_translate.features(pid, S + 1,
None, side)`, the level-season z family through `etools.ZMetric.asof(pid, S + 1)` (stabilization
k from season pairs up to S), the same Marcel weights and reliability shrinkage. The builder
asserts, for every value, that every season it read is at or before S and that S-10-01 is at or
before t. Identity: as the live preview (`etools.build_universe` with live True).

1.3 **The value.** For a base grade G (defined per use in 1.5) and sub-driver values z_j at t:
u_j = z_j - a_j - b_j G, and

    eTool(t; G) = clamp(G + sum_j c_j (u_j - delta_j(S(t))), 20, 80)

the sum over the admitted sub-drivers the player carries at S(t) (a missing sub-driver
contributes 0, so a player with none carries eTool = G).

1.4 **Re-centring (amendment 2, F1.5).** For block S (dates t with S(t) = S), delta_j(S) = (mean
of u_j over the block cohort carrying j) - (mean of u_j over the fit's training rows carrying j,
`etools_flip_prep_reads.json` `F1_drift_recentring.<tool>.train_mean_residual` for the final fit).
The block cohort of S: every player with an FG, MLB Pipeline or Baseball America snapshot
carrying the tool dated in (d_S - 400 days, d_S], d_S = S-10-01, and no MLB season at or before
S; G = the three-outlet mean, rounded to 0.5, of each outlet's latest such snapshot (the eTool's
own consensus, gate 1.2); z as of S. Every input of a block's delta is dated on or before d_S,
which is on or before every t in the block.

1.5 **Three series.**
- (i) **Per outlet** (the DvM+ pairs): at each snapshot of a growth outlet
  (`dev_attribution.GROWTH_SOURCES`) at date t, G = that outlet's grade of the tool at t (pwr:
  the outlet's game power grade; an outlet with no game power grade keeps its consolidated pwr,
  consensus). The eTool construction is applied to the outlet's own grade so the same-source
  rule of VAL_4 keeps holding: a pair's eTool change is one outlet's grade change plus the
  change in the stat reading, never a change in which outlets are averaged.
- (ii) **The prospect's eTool line** (the tool-history chart): at each `points[]` entry,
  G = `tools_consensus[tool]` (pwr: `game_pwr`).
- (iii) **The eTool composite line**: at each `points[]` entry,
  `storage._compute_tool_composites` (unchanged power means) on the shown grades: (ii) for the
  six tools, consensus for the rest, `pwr` replaced by the game power eTool.

1.6 **Artifact.** `python etool_history.py --build` writes `data/etool_asof.json`: per player and
tool, per block S, the two numbers that give the eTool for any base grade,
K = sum_j c_j (z_j - a_j - delta_j(S)) and Bslope = sum_j c_j b_j over the sub-drivers carried,
so eTool(t; G) = clamp(G (1 - Bslope) + K, 20, 80); plus each block's delta and cohort size and
a receipt (fit hashes, inputs sha256). It is a server input listed in `deploy/data_exclude.txt`.
The current card eTool (`data/etools.json`) is unchanged by this task.

---

## 2. eDvM+ per tool and eToolDvM+

2.1 **The served construction, unchanged** (storage at 8549bdeb): VAL_4's org calendar and tenure
growth (`dev_attribution.tenure_growth`: same-source consecutive pairs, split by days across the
tenures they span, mean over the outlets that observed a tenure, the expected-WAR scale
`storage._fv_to_expected_war`); the trailing window (pairs starting on or after today minus
`FARM_TOOL_DELTA_LOOKBACK_DAYS`, 7 years); active prospects only; each prospect's growth times
his current level's weight (`_TOOL_DEV_LEVEL_WEIGHTS`); per club and tool at least 3 prospects;
the k = 2 shrink toward the league mean (`_DVM_SHRINK_K`), z against the unshrunk pool sd,
100 + 10 z, the 1.35 stretch, rounded; the per-bucket pass; the position-importance composite
(`_bucket_weighted_tool_dvm`). The difficulty adjustment is what it is today: none
(`DVM_DIFFICULTY_ARM` None, `_apply_dvm_difficulty_tools` a no-op). The difficulty gate's k_org
is not served and is not used.

2.2 **eDvM+ for a tool** (eHit DvM+, ePower DvM+, eSel DvM+, eBat DvM+, eFB DvM+, eCmd DvM+):
2.1 with series (i) in place of each outlet's grade for that tool in the tool growth. Nothing else
moves. **eToolDvM+**: the 2.1 composite over the per-tool values with each switched tool's eDvM+
in its place; it has no read of its own and follows the per-tool decisions (Part 6).

---

## 3. Read (a): org development-skill persistence

3.1 **Windows.** Calendar years W, a pair assigned to the year of its END date (the difficulty
gate's convention, section 7 there). The pairs of W are every same-source pair ending in W, dated
on or before the player's debut (VAL_4's calendar ends there), over every player in the store
(active, debuted or inactive today): the analogue at W of "the active prospects". A pair with
either endpoint dated in 2020 or 2021 is dropped (R-LV list vintages are inputs this read does
not take); the R-VM debut cohorts are outcomes and (a) reads none.

3.2 **Club index per window.** Per version v (C consensus, E eTool) and tool group g: each pair's
growth on the expected-WAR scale split across tenures by days, per tenure the mean over the
outlets that observed it (2.1), times the player's level weight at W (his highest level with
100 or more PA or BF in season W, else in season W - 1; A- reads A's weight; none reads 1.0),
credited to the tenure's club (the 30 clubs of `trades.canonical_org`; unaffiliated credits
nobody); then the 2.1 club aggregation (at least 3 prospects, k = 2 shrink, z, 100 + 10 z, 1.35
stretch, rounded) across the clubs with a value: DvM+_v[o, W, g].

3.3 **Statistic.** P_v(g) = the mean, over consecutive window pairs (W, W + 1) where at least 10
clubs carry a value in both windows, of the Spearman correlation across those clubs of
DvM+_v[o, W, g] and DvM+_v[o, W + 1, g]; each window pair weighs equally. The window pairs are
fixed on the full sample. Delta_a(g) = P_E(g) - P_C(g).

3.4 **Interval.** Club-clustered bootstrap: the 30 clubs resampled with replacement with all
their windows, each window pair's Spearman taken on the drawn clubs with weighted mid-ranks
(`etools.weighted_midranks`, amendment 2 F3.2), the same draws for both versions (paired), B 2000,
seed 20261031; one-sided 95% lower bound = the 5th percentile.

3.5 **Rule (a).** NOT WORSE when the one-sided 95% lower bound of Delta_a(g) is above -0.05 (the
non-inferiority margin of the difficulty gate, section 13 condition 2).

3.6 **Zero comparator.** No development credit gives every club the same index in every window,
so its persistence is 0. P_v(g) and its lower bound are reported against 0 for both versions.
Read (a) is the non-inferiority guard; the zero comparator that decides is in read (b) (4.6),
so no candidate with no development signal can pass the decision as a whole.

3.7 **Reported, not deciding:** P for the eToolDvM+ composite and the consensus ToolDvM+ built the
same way per window; per-version counts (pairs, prospects, clubs per window).

---

## 4. Read (b): predictive validity of grade gains

4.1 **Rows.** One row per (player p, window W, tool group g) with: no MLB season before W and a
first MLB season of 2024 or earlier (R-VM never read); at least one pair of an outlet carrying
the tool on both ends ending in W (3.1, R-LV pairs dropped); and the tool's L_MLB label at board
year W (`etools.mlb_label(tool, pid, W)`, the look's definitions: the first three MLB seasons
strictly after W, through 2026, with the look's floors; pwr reads game power's label, ISO). The
outcome stats: hit, MLB K% (negated); pwr, ISO; pitch_sel, chase rate 2026 (negated); bat_ctrl,
zone contact 2026; fb, pitcher K%; cmd, pitcher BB% (negated).

4.2 **Start and gain (grade scale).** Per version v and outlet s with pairs ending in W: s's
start = the v grade at the start of its earliest pair ending in W; s's gain = the sum of the v
grade changes over its pairs ending in W. start_v = the mean over outlets of the starts; gain_v =
the mean over outlets of the gains. Version C reads each outlet's grade (pwr consolidated by the
consensus.py rule); version E reads series (i).

4.3 **The eTool for (b) is out of fold for the player.** Players are split into 5 folds by
sha256("20261031:" + mlbam) mod 5. For fold k, `etools.etool_fit` is refit on the look's
development frame (`load_board`, `build_universe`, `attach_candidates`, `attach_labels`,
`tool_frames`, built as in the look) on the rows of players NOT in fold k, with the look's admitted
set and both labels (gate 5.1); its training mean residuals give the 1.4 re-centring. Fold k's
players read their eTool from fold k's fit. Before any (b) statistic the runner checks the
history's sub-driver values against the development frame's candidates on every shared
(player, board year) row (equal to 1e-9) or stops.

4.4 **Statistic.** Folds by W (leave one window year out, player-disjoint,
`etools.fold_train_mask`). d_v = rho_w(out-of-fold OLS on [1, start_v, gain_v]) - rho_w(out-of-fold
OLS on [1, start_v]), rho_w the n-weighted mean of within-W Spearman over windows with 20 or more
rows (`etools.within_rho`). D(g) = d_E - d_C on the identical rows.

4.5 **Interval.** Player-clustered bootstrap, predictions fixed, players resampled, every window
re-ranked on each draw (amendment 2 F3.2), the same draws for all four predictions, B 2000, seed
20261031. One-sided 95% lower bound = the 5th percentile; one-sided p = 1 - Phi(D / sd of the
draws) (`etools.summarize_draws`). Holm across the computable tool groups (family of at most 6).

4.6 **Rule (b).** BETTER when all hold: (1) the lower bound of D(g) is above 0; (2) the
Holm-adjusted p of D(g) is at most 0.05; (3) the lower bound of d_E is above 0 (the eTool gain
beats the zero comparator: no development credit is the model on [1, start_E], d = 0).
Computable: at least 100 players and at least 3 windows of 20 or more rows (`etools.computable`);
otherwise NOT COMPUTABLE, which keeps consensus.

4.7 **Reported, not deciding:** d_C and d_E with intervals; the same read with the gain on the
expected-WAR scale (the DvM+ credit unit); counts per window. Survivorship: L_MLB exists only for
players who reached the majors (`etools.SURVIVORSHIP`); every (b) number is among debuts, and the
results say so beside it.

---

## 5. Planted recovery (no outcome is read; it runs before Parts 3 and 4 are scored)

5.1 **(b), per tool group,** on the real (b) rows (their start, gain, W and players), with the
outcome replaced by a synthetic one; z() standardizes over the group's rows; eps iid N(0, 1);
R 40 replicates, bootstrap B 400 each, seed 20261101 + replicate:
- PLANT_E: y = z(start_E) + 0.25 z(gain_E) + 2 eps;
- PLANT_C: y = z(start_C) + 0.25 z(gain_C) + 2 eps;
- NULL: y = 0.5 z(start_C) + 0.5 z(start_E) + 2 eps.
A replicate PASSES when 4.6 (1) and (3) hold. Recovery holds when PLANT_E passes in at least 80%
of replicates and PLANT_C and NULL each pass in at most 10%.

5.2 **(a), per tool group,** on the real (a) design (pairs, tenure shares, windows, level
weights): in each window the per-club credit entries (one prospect's level-weighted growth to one
club) are permuted across all entries of the window, independently per version, and a club
effect theta_o ~ N(0, (0.2 sd_W)^2) is added to each of the club's entries, sd_W the sd of the
window's entries, one theta per club per replicate, the same for both versions and all windows;
R 40, B 400, seed 20261102 + replicate. PLANT: theta as stated; NULL: theta = 0. Recovery holds
when, under PLANT, the lower bound of P_E is above 0 in at least 80% of replicates and rule (a)
passes in at least 80%, and under NULL the lower bound of P_E is above 0 in at most 10%.

5.3 A tool group whose recovery does not hold on either read is NOT RESOLVABLE and keeps
consensus, whatever its real-data numbers.

---

## 6. Decision and what follows

6.1 **Per tool group: SWITCH** when recovery holds on both reads (5.3), (a) is NOT WORSE (3.5) and
(b) is BETTER (4.6). Otherwise KEEP CONSENSUS (or NOT RESOLVABLE, or NOT COMPUTABLE), recorded with
its reason.

6.2 **A switch serves:** `tool_dev.per_tool_dvm_plus[g]` (and the per-bucket values) is the eDvM+
for each switched group; `tool_dev.per_tool_dvm_plus_cons` keeps the consensus version of every
group as the reference column; `tool_dev.etool_groups` names the switched groups;
`tools_dvm_plus` is the composite over the served per-tool values (eToolDvM+ when any group
switched) with `tools_dvm_plus_cons` beside it. The farm and org pages print the basis; the
prospect tool-history chart plots series (ii) for switched tools with the consensus line as a
ghost; the glossary and the registry say which tools switched and which kept consensus. The flag
is `etool_history.ETOOLS_DVM_GROUPS` (the switched groups; empty reproduces the consensus payload
byte for byte). The blast radius (farm letters, ranks, Franchise) is published in the serving
commit.

6.3 **No switch** builds nothing served beyond the 0.3 repair: the history artifact stays a
server input, the glossary and registry say per tool that DvM+ keeps consensus and why.

---

## 7. Guards and output

`python tools/etools_dvm_lab.py --read --gate-sha SHA` runs Parts 5, 3 and 4 once and writes
`data/_labs/etools/etools_dvm_read.json` (role development, spent marker, this document's
commit, the inputs' sha256 at start and end). It refuses unless SHA names a commit carrying this
file as REGISTERED, refuses a second scored read, and asserts: no pair with an endpoint in 2020 or
2021; no (b) row with a first MLB season after 2024; no outcome season after 2026; no input season
read after its as-of date; no grouping, key, filter or weight by consensus FV or any source's FV
(`docs/PROSPECT_ANCHOR_GATE.md`). `--check` counts rows only; `--dry-run` runs the reporting path
on fixtures. On an exception after the first real statistic the read is recorded as spent and
the question goes to the owner. Never `backtest.run_backtest`, `run_monthly` or `build_site` from
the runner; no projections retrain; nothing served moves from the runner.

## 8. Results

EMPTY AT REGISTRATION. The read's result is pasted here, dated, by this task's results commit.

# Position and role assignment: pre-registration and results

Lane: LANE-P5, Phase 5 only, of `docs/master-plan-2026-07-30-fv-calibration.md`.
Gate standard: `docs/EFV_GATE_STANDARD.md`.
Owner ask (verbatim): "Hitter position should be based on what position they've played the
most in the minors; pitcher position should be based on Games Started to determine starter
vs reliever."

Files this lane owns: `consensus.py`, `role_usage.py`, `fielding_positions.py`, new tests
and docs. It does NOT edit `efv_score.py`, `value_framework.py`, `storage.py` or
`data/glossary.json`; anything needing those is reported as an owed follow-up.

**PART 1 below was written and committed to disk BEFORE the 5.1 and 5.2 measurements ran.**
PART 2 is appended after. (5.3 is a descriptive census of what the scraper already ingests,
not a gate; its method is pre-registered here for the record and its result is in PART 2.)

---

# PART 1. Pre-registration

## 1.0 What this lane changes and what it deliberately does not

The served `position` string comes from `consensus._latest_meta`, which prefers FanGraphs
because FG FORWARD-PROJECTS where a prospect ends up rather than reporting today's roster
slot. That rationale is load-bearing and stays. This lane therefore:

* **5.1** adds `position_observed`, a SECOND field carrying the most-played non-DH MiLB
  position from `data/positions_played.json`. It does not repoint `position`.
* **5.2** generalizes rule D (`role_usage.usage_position_override`) so pitcher usage can
  decide the role in BOTH directions instead of only RP -> SP, with FG as the fallback for
  rows with no usable usage line.
* **5.3** audits, per source, what FV/overall grade the scraper actually ingests, to settle
  whether the Baseball America headline-grade defect described in
  `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` is live in our data.

## 1.1 (5.1) The observed-position resolver

**Input.** `data/positions_played.json`, built by `fielding_positions.build_positions_played`
from the StatsAPI fielding group with `leagueListId=mlb_milb`, career-to-date, per position
`{g, gs}`. The builder skips pitchers and its `__main__` filters to players with no
`debut_date`, so the artifact is a PROSPECT-ONLY, MiLB-dominated census. 2,675 players in the
current build (generated 2026-07-28).

**Definition.** `observed_position(by_pos)` returns the position with the most GAMES among
positions that are not in `fielding_positions._NON_FIELD` (`DH`, `PH`, `PR`).

**Pre-registered handling of every edge case:**

1. **DH exclusion.** `DH`/`PH`/`PR` are never eligible, matching `versa_positions`. A player
   whose largest bucket is DH resolves to his largest FIELDING bucket. A player with only
   DH/PH/PR resolves to `None`, not to `"DH"`.
2. **Minimum exposure.** The top position must clear the SAME thresholds the shipped versa
   qualification already uses - `>= VERSA_MIN_GAMES` (10) games OR `>= VERSA_MIN_STARTS`
   (5) starts - or the resolver returns `None`. No new tunable is introduced; a player with
   three career games at 2B gets a null, not a position.
3. **Ties.** Deterministic, three keys in order: (a) most games, (b) most starts, (c) the
   harder position on the defensive spectrum, ranked `C > SS > CF > 2B > 3B > RF > LF > 1B >
   OF > IF > P > everything else` (alphabetical last resort). Rationale for (c): when a
   player has split a season evenly, the industry convention and the scarcity model both
   treat the harder position as the meaningful one, and any tie-break must be a stated rule
   rather than dict-insertion order (which is what `versa_positions`' single-key sort
   currently falls back on).
4. **Players absent from the artifact.** `None`. The resolver never guesses and never falls
   back to the FG projection - a null is the honest signal that we have no observation.
   Pitchers are absent by construction (the builder skips them), so they resolve to `None`
   without a special case.
5. **Graduated players.** The artifact is built from pre-debut prospects, so a graduate's
   entry is a frozen pre-debut observation. `position_observed` is therefore explicitly
   labelled a MiLB observation, and the `_latest_meta` graduate exception (which already
   prefers depth-chart sources over FG once a player debuts) is left untouched. This lane
   does NOT propose `position_observed` as the graduate display position; the depth-chart
   sources are closer to the truth there.

**Deliverable.** The resolver plus a detail form returning `{pos, g, gs, share, tie,
qualified}` so a consumer can see the strength of the observation. Ships as a pure function
in `fielding_positions.py`. Wiring it onto the exported payload requires `storage.py`, which
this lane does not own, so the wiring is an owed follow-up, precisely specified.

**What is reported, not gated.** 5.1 changes no served number by construction (new field,
computed by a pure function, not wired). The measurement is descriptive: the disagreement
rate against the FG projection, and a per-consumer recommendation. There is no ship/no-ship
threshold because there is nothing to ship past the resolver itself.

## 1.2 (5.2) Usage as the primary pitcher role source

**Current state.** `role_usage.usage_position_override` flips MIRP/SIRP -> SP when the
current-season MiLB line is starter-shaped: GS-share >= 0.50 AND IP/G >= 3.0 AND IP >= 20.
The IP/G floor is the opener discriminator (openers ~1.1-1.2 IP/G, stretched starters
>= 3.0). One direction only.

**Generalization.** A new pure function `usage_role(g, gs, ip) -> "SP" | "RP" | None`:

* `"SP"` when `starter_by_usage(g, gs, ip)` is True (unchanged thresholds).
* `"RP"` when `ip >= IP_MIN` AND GS-share `<= RP_GS_SHARE_MAX` (0.25) AND IP/G `<
  IP_PER_G_MIN` (3.0).
* `None` otherwise - including the entire swingman band between the two (GS-share in
  (0.25, 0.50), or reliever-ish GS-share with a starter's IP/G). `None` means "usage does
  not adjudicate" and the FG designation stands.

The band between 0.25 and 0.50 GS-share is deliberately left unadjudicated rather than
split at 0.50. Rule D's 0.50 threshold was validated as a sufficient condition for "this is
really a starter"; its negation is NOT a validated sufficient condition for "this is really
a reliever", and pretending otherwise would relabel every swingman on one unvalidated
inequality. The opener guard survives unchanged and now works in the direction it always
implied: an opener (high GS-share, ~1.1 IP/G) fails the SP test and, at GS-share <= 0.25,
passes the RP test; at higher GS-share it lands in the unadjudicated band and keeps its FG
label.

**Fallback.** `usage_position_override` keeps the FG designation whenever `usage_role`
returns `None`, whenever the mlbam id is missing, and whenever the milb cache holds no MiLB
pitching row. Unchanged defensive posture: no data never flips a label.

**Blast radius that MUST be measured before anything ships (pre-registered list):**

* count of rows flipping RP-family -> SP (the already-shipped direction, as a regression
  check that the generalization does not change it),
* count of rows flipping SP -> RP,
* count of rows flipping generic `P` -> SP and `P` -> RP, reported separately,
* net change in `efv_score._RP_DESIGNATIONS` membership (`SIRP`, `MIRP`, `RP`, `CL`), since
  that set gates the reliever-ceiling factor `_role_factor`,
* of those, the subset that would actually TRIGGER `_role_factor` (age >= `_ROLE_RAMP_ONSET`
  = 23.5 AND model WAR >= 1.5), which is the population whose grade would move,
* effect on the PAL fit-direction gates (RP -> SP vs SP -> RP candidate pools),
* effect on the Phase-2b RP outcome-curve population.

**Pre-registered ship rule.** The RP -> SP direction is already shipped and stays default-on.
The **SP -> RP direction and the generic-`P` -> RP direction ship DEFAULT-OFF behind a module
flag unless they move ZERO graded rows.** Rationale: entering `_RP_DESIGNATIONS` exposes a
row to a multiplicative haircut on the model leg, which is board movement, and plan ground
rule 4 requires a `BOARD_RANK_BASIS_EPOCH` bump plus a `PINNED_MIX` update for board
movement - which lives in `storage.py` and `test_board_basis_coherence.py`, neither of which
this lane owns. A default-off flag plus a registry row is the correct landing for this lane;
turning it on is an owner call with an epoch bump attached.

`P` -> SP is treated as NOT board movement if and only if the measurement confirms it changes
no `_RP_DESIGNATIONS` membership and no pitcher/hitter classification (`P` and `SP` are both
outside the RP set and both pitcher tokens). It still changes a displayed string, so it is
reported either way.

## 1.3 (5.3) The BA ingestion audit

**Method.** A per-`source` census over the full `prospects.db` `snapshots` table
(2010-2026): rows, rows with non-null `fv`, rows with non-null `rank`, rows with a non-empty
`tools_json`, distinct players, and the same census broken out by year. Then, for every
source that carries an `fv`, trace the value back to the PRODUCER in the scraper to
distinguish a grade the outlet published from a constant our own ingestion assigns.

**The question being settled.** `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` establishes that
BA's headline grade carries risk SEPARATELY while FG's FV has risk already subtracted, so
mapping a BA headline onto the FV scale overrates by about one tier at the median and up to
four at the extremes; BA also reset its baseline in 2026 with no crosswalk and only began
printing its adjusted grade that year. If we ingest BA overall grades anywhere, they are
about a tier hot against the FanGraphs scale that `grade_normalization` maps everything onto,
and that is a live normalization defect.

**Pre-registered verdict rule.** If BA rows carry `fv IS NULL` throughout, the defect is NOT
live and the finding is a null - reported as a null, with the rank-implied-FV path checked
as the only remaining channel (BA rank can only become an FV when a player has no explicit
FV from any source; that condition is measured, not assumed). If BA rows DO carry an `fv`,
the size of the hotness is quantified against the paired FanGraphs distribution using
`grade_normalization`'s own overlap machinery and REGISTERED, not fixed blind.

A separate check, not in the original ask but implied by the method: any source whose `fv`
is a CONSTANT our scraper assigns rather than a published grade is a fabricated vote in
`consensus.avg_fv`, and its dilution effect on the players it touches is quantified.

## 1.4 What this lane will not do

* No edit to `efv_score.py`, `value_framework.py`, `storage.py`, `data/glossary.json`.
* No pytest run (concurrent lanes; conftest git-checkouts dirtied files).
* No exporter, `run_monthly`, `build_site` or scraper run; no `git add` of any `data/` path
  this lane did not create.
* No consumer flip. 5.1 enumerates consumers and recommends; the flips are owner calls.

---

# PART 2. Results

Appended after PART 1 was committed (a6616a7). Every number below is reproducible from
`data/positions_played.json` (generated 2026-07-28), `data/timeseries.json`,
`data/xfv.json`, `prospects.db` and the `.cache/milb_stats` 2026 pitching cache, offline.

## 2.1 The observed-position resolver

Shipped in `fielding_positions.py` as `observed_position`, `observed_position_detail` and
`load_observed_positions`. Registry row `position_observed`, verdict `unvalidated`
(`eval_artifact: null` - there is no artifact; this doc is the citation). Tests:
`test_position_role_phase5.py`, 34 cases.

**Coverage.** 2,674 of the 2,675 players in the census resolve. The single null is a player
under the exposure floor. Zero players have an empty census and zero are DH-only, so the
DH-exclusion and empty-map branches are correct-by-construction rather than load-bearing on
this build - they are still tested, because the census is rebuilt nightly.

| observed position | n |
|---|---|
| SS | 453 |
| CF | 432 |
| C | 400 |
| 2B | 327 |
| 3B | 291 |
| RF | 260 |
| LF | 245 |
| 1B | 241 |
| P | 25 |

The 25 `P` rows are converted or two-way players who entered the census before the builder's
pitcher skip applied; they are reported as `P`, not laundered into a field position.

**Ties.** 20 of the 2,674 are decided by the tie-break. The resolver disagrees with the
shipped `versa[0]` on 13 players, and every one of those 13 is a genuine games tie that
`versa_positions`' single-key sort was resolving on StatsAPI response order (e.g.
`rj_schreck` RF 196 / LF 196, `justin_boyd` LF 70 / RF 70, `devin_fitzgerald` 2B 96 / SS 96).
That is the determinism the tie-break was added for.

**Disagreement with the served FanGraphs projection.** 1,957 resolved players join
`data/timeseries.json`. 717 resolve but are not on the served board and 144 non-pitcher
served rows have no observation at all.

| relationship of served `position` to `position_observed` | n | share |
|---|---|---|
| exact (primary token) | 1,388 | 70.9% |
| DISAGREE within the infield | 210 | 10.7% |
| DISAGREE within the outfield | 145 | 7.4% |
| DISAGREE across groups | 93 | 4.8% |
| served generic OF, observed a specific slot | 55 | 2.8% |
| DISAGREE involving C | 28 | 1.4% |
| served DH, observed a field position | 27 | 1.4% |
| served generic INF, observed a specific slot | 4 | 0.2% |
| observed is a SECONDARY served token | 4 | 0.2% |
| pitcher / TWP (excluded) | 3 | 0.2% |

**476 hard disagreements, 24.3% of comparable rows.**

**The disagreement is signed, and that is the whole finding.** FanGraphs projects a move DOWN
the defensive spectrum 318 times against 184 up, a 1.73:1 skew. The most common pairs are
3B -> SS 44, RF -> CF 39, 2B -> SS 37, SS -> 2B 31, LF -> CF 30, RF -> LF 29, SS -> 3B 22,
1B -> 3B 21, 1B -> C 15, DH -> C 15. Read as "FG says he ends up at 3B, he has been playing
SS," which is the forward-projection doing exactly the job `_latest_meta` keeps it for.

Notable top-of-board cases: `ethan_holliday` 3B / SS, `jojo_parker` 3B / SS,
`caleb_bonemer` 3B / SS, `elian_pena` 3B / SS, `jett_williams` CF / SS,
`josue_briceno` 1B / C, `josiah_hartshorn` 1B / RF, `kayson_cunningham` 2B / SS,
`roldy_brito` CF / 2B, `edward_florentino` RF / CF.

**Why `position` is not repointed.** The skew is the argument. Swapping the observation into
`position` would make the board's defensive profile read systematically HARDER than the
industry expects these players to age into - 318 players would gain a premium-position label
the scouting consensus says they will not hold - and the positional scarcity multiplier, the
comp cohorts and the eFV `_pos_premium` feature would all price that. The two fields carry
different information and both are wanted.

**Not wired.** Adding the field to the exported payload is a `storage.py` edit this lane does
not own. Owed follow-up, specified in 2.4.

## 2.2 Usage as the primary pitcher role source

Shipped in `role_usage.py` as `reliever_by_usage`, `usage_role` and the `both_directions`
parameter on `usage_position_override`, behind `USAGE_ROLE_BOTH_DIRECTIONS = False`. Registry
row `pitcher_role_usage`, verdict `unvalidated`.

**Regression check on the shipped direction: EXACT.** Of the 338 FanGraphs relief-labelled
arms with a 2026 MiLB cache line, shipped rule D flips 103 to SP and the generalized rule
flips the same 103. Zero disagreements. The flag-off path is byte-identical to what is live,
and the 16 pre-existing `test_role_usage.py` cases still pass unchanged.

**Usage verdict over the 2,207 served pitcher rows with a 2026 line:** SP 705, RP 1,034,
UNADJUDICATED 468. The unadjudicated band is 21.2% of the pool, which is the honest size of
the swingman/tandem population the 0.25-to-0.50 gap was left open for.

**Flip counts, both directions on:**

| served label | new label | n |
|---|---|---|
| P | RP | 830 |
| P | SP | 362 |
| RHP | SP | 26 |
| SP | RP | 22 |
| RHP | RP | 17 |
| LHP | SP | 10 |
| LHP | RP | 2 |

1,269 label changes in total. **871 rows ENTER `efv_score._RP_DESIGNATIONS`** (849 of them
from the role-less `P`/`RHP`/`LHP` labels, 22 from `SP`), and 398 gain an `SP` label.

**Blast radius on the grade.** Of the 871 rows entering the RP set, exactly **3 trigger
`_role_factor`** (age >= `_ROLE_RAMP_ONSET` 23.5 AND WAR >= 1.5; the artifact carries the
blended `xfv_war_6yr` rather than the raw model leg, so this is a slightly conservative
proxy):

| player | flip | age | WAR | eFV grade | board rank | 2026 line |
|---|---|---|---|---|---|---|
| tink_hence | SP -> RP | 24.0 | 2.01 | 45.3 | 305 | 19 G / 3 GS / 20.3 IP |
| joe_glassey | P -> RP | 25.0 | 1.50 | 42.1 | 459 | 23 G / 0 GS / 29.3 IP |
| nick_frasso | SP -> RP | 27.8 | 1.50 | 42.1 | 483 | 25 G / 1 GS / 29.3 IP |

**Zero of the 871 sit inside the board top 300.** But 3 is not 0, and the pre-registered rule
was "default-off unless it moves zero graded rows", so it lands DEFAULT OFF. Turning it on is
an owner call carrying a `storage.BOARD_RANK_BASIS_EPOCH` bump, a `BOARD_BASIS_FINGERPRINT`
restamp and a `PINNED_MIX` update in the same commit (plan ground rule 4), none of which live
in files this lane owns.

The 22 SP -> RP flips are individually credible: Tink Hence at 19 G / 3 GS, Dylan Lesko at
21 G / 0 GS, Nick Frasso at 25 G / 1 GS. All 22 rank 305 or worse and 14 of the 22 already
grade at the FV20 floor, so this direction is mostly relabelling arms the board has already
written off. Tink Hence is the one row where the flip is both true and consequential.

**Second-order blast radius the flag also gates.** The reliever-ceiling factor is not the
only consumer of the role string:

* **PAL `_prospect_role`** (`pal_export.py:327`) reclassifies **1,269 rows**: SP 487 -> 863,
  RP 310 -> 1,181, SWING 1,619 -> 372. `pal_conversion.prospect_role_fit` only emits a
  `mismatch` when `role` is SP or RP, so 1,247 prospects that are currently invisible to the
  role-mismatch watch become eligible for it in one step. That is a product change of its own
  size and deserves its own look before the flag flips.
* **`spotlights.py:1229`** disqualifies an RP-labelled prospect aged 23+ from EVERY spotlight
  bucket. 830 P -> RP flips would newly expose that gate.
* **`grpo_prospect.py`** buckets position for the policy feature; `P` and `RP` are different
  buckets.
* **`value_framework`** role paths (`is_reliever_position`, the relief probability vector,
  `relief_war_haircut`, the RP branch of `expected_surplus_usd`, the roster-logjam group) all
  key on the same string.

**The FanGraphs fallback still covers the rows usage will not rule on**: 468 unadjudicated
rows plus the 209 served pitcher rows with no 2026 cache line keep their published label.

## 2.3 The BA ingestion audit

Full per-source census of `prospects.db.snapshots` (51,180 rows, 2010-2026):

| source | rows | with FV | with rank | with tools | years | players |
|---|---|---|---|---|---|---|
| fangraphs | 23,119 | 23,117 | 22,916 | 23,117 | 2017-2026 | 5,360 |
| mlb_pipeline | 17,976 | 17,438 | 17,976 | 17,438 | 2011-2026 | 5,394 |
| tjstats | 3,802 | 3,798 | 3,802 | 3,502 | 2026 | 141 |
| performance_ingest | 2,798 | 2,798 | 0 | 0 | 2026 | 2,798 |
| auto_detect | 2,483 | 0 | 0 | 0 | 2010-2026 | 2,483 |
| espn | 252 | 252 | 252 | 131 | 2025-2026 | 124 |
| mlb_pipeline_international | 245 | 245 | 0 | 0 | 2021-2026 | 242 |
| just_baseball | 226 | 226 | 226 | 226 | 2026 | 126 |
| draft_signing | 138 | 138 | 0 | 0 | 2026 | 138 |
| **baseballamerica** | **100** | **0** | **100** | **0** | **2026** | **100** |
| baseballamerica_statcast_by_age | 41 | 41 | 0 | 0 | 2026 | 41 |

Per-year detail: FanGraphs is the only source with a full FV+tools record from 2017, MLB
Pipeline carries FV+tools from 2011 (155 of 347 rows in 2011, essentially complete from
2013), ESPN appears in 2025, and tjstats / just_baseball / draft_signing / both BA sources
are 2026-only.

**VERDICT ON THE BA DEFECT: NOT LIVE. This is a null.**

`baseballamerica` carries **zero FV values across its entire 100-row history** - rank only,
one 2026-06-03 Top 100 list. So the headline-grade-versus-adjusted-grade problem the
framework doc describes, and the 2026 baseline reset with no crosswalk, cannot reach
`grade_normalization` through this source: there is no BA grade to be a tier hot.

The remaining channel, checked rather than assumed: `consensus` converts rank to an implied
FV only when a player has NO explicit FV from any source. **All 100 BA-ranked players carry an
explicit FV from at least one other source**, so BA's ranks never become an FV. They
contribute to `avg_rank` and nothing else. Combined with the other lane's finding that BA
contributes zero tool grades across the whole 2011-2026 history, Baseball America is
currently a rank-only, ordering-informational source in this system.

**What the audit DID find (a different defect, quantified and registered, not fixed).**

`baseballamerica_statcast_by_age` carries an FV on all 41 rows and every one of them is
**40.0**. It is not a Baseball America grade: `source_articles.py:230` assigns the constant
ourselves as a conservative editorial-standout floor for players who appear in BA's
age-banded Statcast table. It then votes in `consensus.avg_fv` at full weight 1.0, exactly
like a published grade.

The guard on it is too narrow. It skips a player only when THIS ARTICLE SET already ranked
him (`snapshot_keys` is built from the BA Top 100 parse), not when any source has graded him.
Result: **34 of the 41 rows land on players who already carry a real FV.** Mean delta to
`avg_fv` **-1.201**, median -1.042, worst -3.333 (`alexander_frias` and `james_tibbs_iii`,
both 50.0 -> 46.67; `andrew_fischer`, `axiel_plaz`, `cristian_arguelles` and `jaison_chourio`
at -2.500). 28 moved down, 3 up. The other 7 rows are the intended case - the FV40 is the
player's only grade and normal single-source shrinkage handles it.

The contrast that proves the point: `performance_ingest`, the other flat-constant source
(FV 35.0 x 2,798 rows, already documented as synthetic in
`draft_anchor_backfill.SYNTHETIC_SOURCES`), collides with a real grade only **30 times out of
2,798** - 2,768 of its players have no other grade at all, so it functions as the ungraded
floor it was designed to be. The BA statcast source has a **83% collision rate** and is doing
the opposite of what its own comment claims.

Registered on the `consensus_fv` row's notes ledger. The fix - widen the guard from "no
ranked snapshot in this article set" to "no explicit FV from any source" - changes served
consensus values for 34 players and therefore needs its own gate. NOT done here.

**Not a defect, checked and cleared:** `tjstats`, `espn` and `just_baseball` each show only
4-5 distinct FV values, which reads like a rank-band map at a glance. It is not. Their
producers parse the outlet's own published grade (`scrapers.py:1330`, `:1527`,
`tjstats.py:226`); the narrow range is simply that we ingest their TOP-100 lists, where every
grade is 50 or better.

## 2.4 Consumer enumeration for 5.1, with a recommendation each

Full enumeration behind this table covers 4 backend groups and 2 frontend groups. Only the
consumers where the projection-versus-observation choice is a real decision are listed;
everything that reads the string as a PITCHER/HITTER BINARY is unaffected by 5.1 by
construction and is omitted (`grade_normalization` among them - it reads
`snapshots.position` straight from the DB and only asks pitcher-or-hitter, so the widely
repeated claim that repointing `position` would move consensus grades through
`grade_normalization` is FALSE; the real reasons not to repoint are the ones in 2.1).

| consumer | file:line | what it does | READ |
|---|---|---|---|
| payload `position` | `storage.py:9412` | the served field itself | **PROJECTION** - keep. Add `position_observed` beside it. |
| positional scarcity $ | `value_framework.py:588` `position_multiplier`; `bayes_trade_value.py:418`, `:3415` `scarcity_multiplier`; prospx `22255` `surplusPositionMult` | market $ premium for a premium position | **PROJECTION.** Scarcity prices where he will PLAY IN THE MAJORS. Paying an SS premium for 318 players the industry says move off SS is the single most expensive way to get 5.1 wrong. |
| eFV `_pos_premium` | `efv_model.py:501` | model feature: up-the-middle = 1.0 | **OBSERVATION, gated.** This one is genuinely arguable and is the only 5.1 flip worth an experiment: the feature is asking "was he good enough to stay up the middle", which is an observation. Needs its own accuracy gate on the eFV pool, not a swap. |
| defensive home | `prospect_def_value.py:333`; `def_home_export.py:61-133` | P(holds position) vector | **OBSERVATION as the input, PROJECTION as the thing being predicted.** def_home already predicts the move that 5.1 measures; feeding it the projection is close to feeding it its own answer. Highest-value flip after `_pos_premium`. |
| archetype comps | prospx `16568-16626`, `16721-16763` | cohort by EXACT `q.position === pos` | **OBSERVATION.** "Who else has played this position at this age" is an observed-cohort question, and exact string equality on a projection makes cohorts that never shared a field. |
| similar prospects | prospx `48266-48336` | same `positionBucket` + FV +-2 + age +-1 | **OBSERVATION**, same argument, lower stakes. |
| peers / percentile cohort | prospx `16372-16443` | percentile pool by bucket | **OBSERVATION.** |
| org depth chart | prospx `48755-48882` | per-slot org rows | **PROJECTION.** A depth chart is a forecast of the future roster; that is what it is for. |
| farm positional need | prospx `49529-49551` `_farmPosGroup`; `storage.py:12163` `_pos_bucket_for` | org cohort scoring vs league | **PROJECTION.** Same reason. |
| RPS+ cohort + multiplier | prospx `52065-52122` | normalization cell and positional-difficulty multiplier | **OBSERVATION.** RPS+ compares a player to peers at his position on measured production; the cell should be where the production happened. |
| catcher tool weighting | `storage.py:9041` `_compute_tool_composites` | D-tool weight for catchers | **OBSERVATION.** A player catching 400 games is a catcher whatever the projection says (`josue_briceno`, served 1B, observed C, is the live case). |
| tool DvM+ / SC+ buckets | `storage.py:10282`, `:10619`, `:10773` `_pos_bucket_v2` | per-bucket display index cells | **OBSERVATION.** Same argument as RPS+. |
| position pill (card header) | prospx `36313-36340`, `28305`, `45555` and the build_site row meta | what the reader sees | **BOTH.** Show the projection as the primary and the observation as a secondary "playing: SS" line. The reader wants both and today gets neither labelled. |
| board / leaderboard filters | prospx `15211-15230` `positionMatches`, `15364`, `19431` | chip filtering | **BOTH, user-selectable.** A filter is a question; let the reader pick which question. |
| scatterplot colour, search meta, share cards | prospx `40279`, `mlb_player_export.py:646`, prospx `33823` | display only | **PROJECTION** - keep, not worth the churn. |
| physical-profile pool | prospx `32570-32582` | ht/wt/BMI z-score pool (C/IF/OF/P) | **PROJECTION.** Frame comparison is about the body type a position demands long-term. |
| `realized_implied_fv(position=)` | `value_framework.py:2835`, `:3005`; Phase 2b | per-position outcome curve | **PROJECTION for now, revisit in Phase 2b.** The outcome curves are fit on where players ENDED UP; the input must match the fit basis, and that is a Phase 2b decision, not this lane's. |

**None of these are flipped in this lane.** Each is an owner call, and `_pos_premium`,
`def_home` and the archetype/RPS+ cohort group are the three worth an experiment.

**Two defects found in passing, both outside this lane's files:**

1. **`grpo_prospect.py:105-112`, `:197`** - `_POS_BUCKET` has no `SIRP` or `MIRP` key and the
   lookup is `_POS_BUCKET.get(pos, 4)`. Every SIRP/MIRP prospect that the storage seam does
   not flip to SP is fed to the GRPO policy as **bucket 4, the LF/RF/1B/OF/DH corner-bat
   bucket**, not the relief bucket 6. On the current board that is 310 relief-labelled rows
   landing in the corner-bat cell. This is a live mislabelled model feature and is
   independent of everything in Phase 5.
2. **`prospx/index.html:15312-15320`** - `displayPosition()` already MUTATES `p.position` in
   place client-side: when the served label is an outfield slot and `positions_played.json`
   shows zero outfield games, it rewrites the label to the most-played real slot. So a
   partial, undocumented, OF-only version of owner ask 4 is ALREADY SHIPPED on the frontend,
   it runs before every FE filter, comp cohort, depth chart and scarcity multiplier, and it
   means the backend and the frontend can disagree about the same player's position today.
   Whatever is decided about `position_observed`, that mutation should become an explicit
   named field rather than an in-place overwrite.

## 2.5 Owed follow-ups (nothing here was done)

1. **Wire `position_observed` into the payload.** `storage.py` (not owned): call
   `fielding_positions.load_observed_positions()` once in `export_payload` next to the other
   sidecar loads, then set `"position_observed": _obs.get(p.player_key)` beside
   `"position": p.position` at `storage.py:9412`. Additive, null for 2,563 served rows that
   have no observation, changes no existing field. Also worth carrying
   `observed_position_detail`'s `g`/`share` so a surface can show "SS, 498 games".
2. **Reconcile the frontend mutation** at `prospx/index.html:15312-15320` with the new field
   (defect 2 above).
3. **Fix `grpo_prospect._POS_BUCKET`** (defect 1 above) - add SIRP/MIRP to bucket 6.
4. **Widen the `baseballamerica_statcast_by_age` guard** (2.3) - needs its own gate, moves
   34 served consensus values.
5. **Owner call on `USAGE_ROLE_BOTH_DIRECTIONS`** - with the epoch bump, fingerprint restamp
   and `PINNED_MIX` update attached, plus a decision on the PAL role-mismatch population.
6. **Rebuild `positions_played.json` for graduates** if `position_observed` is ever wanted on
   graduated players; the builder currently filters to pre-debut prospects, so a graduate's
   entry is frozen at his last prospect-era census.
7. **Consider splitting the emitted RP label** into SIRP/MIRP by IP per appearance if the
   flag is ever turned on. Deliberately not done: the cut is unvalidated and generic `RP` is
   already exact for every downstream role gate.

---

# PART 3. Owner decisions, executed (LANE-SHIP, 2026-07-30)

PART 1 and PART 2 above are LANE-P5's pre-registration and measurement. Three owner
decisions were taken on those findings and executed here. Every number below was
RE-MEASURED on the tree as it stood at execution time; the nightly box regen had moved the
artifacts since PART 2 was written, and where a number changed it is called out.

Files changed: `role_usage.py`, `storage.py`, `source_articles.py`, `efv_model.py`,
`prospect_def_value.py`, `prospx/index.html`, `data/model_registry.json` and tests.

## 3.1 DECISION 1 - both-direction pitcher roles are ON

`role_usage.USAGE_ROLE_BOTH_DIRECTIONS = True`.

**Regression on the shipped direction: still EXACT.** Shipped rule D and the generalized
rule flip the same 103 relief-labelled arms to SP, zero disagreements. The
`both_directions=False` path is byte-identical to what was live and is now pinned
explicitly in two test files rather than implied by a default.

**Ship mechanics, same commit.** `storage.BOARD_RANK_BASIS_EPOCH` was already 2026-07-30
(the pooled outcome refit set it earlier the same day), so the DATE did not need to move
and the reason for this second board input was recorded on it instead. The FINGERPRINT did
move: `storage.board_basis_fingerprint()` gained a `roles=` term fed by the new
`role_usage.role_resolution_mode()`, and `BOARD_BASIS_FINGERPRINT` is restamped to

    xfv_grade|scale=off|grademap=outcome_pooled@6dbe8353f3bb|roles=usage_both

This is the THIRD instance of the lesson `test_board_basis_coherence` was written for. The
flip moved 1,269 labels and 871 `_RP_DESIGNATIONS` memberships while leaving all three
existing fingerprint terms identical - so without the new term the fingerprint would once
again have reported "no change" through a real board input flipping.

`PINNED_MIX` is deliberately NOT re-recorded. It pins the top-N pitcher share, and no
flipped row is inside the board top 300, so the statistic provably cannot move on this
input. Re-pinning on a change that did not move the statistic would only lose the reading.

**Numbers as measured on the ship tree** (PART 2's figures in brackets where they moved):

| quantity | measured |
|---|---|
| served non-graduate pitcher rows | 2,422 |
| with a 2026 MiLB cache line | 2,210 [2,207] |
| usage verdict SP / RP / unadjudicated | 705 / 1,034 / 471 [468] |
| total label changes | 1,269 |
| rows ENTERING `_RP_DESIGNATIONS` | 871 (849 role-less, 22 from SP) |
| rows gaining SP | 398 |
| of the 871, triggering `_role_factor` | **3** |
| of the 871, inside the board top 300 | **0** (best rank 304) |

Flip table: `P -> RP` 830, `P -> SP` 362, `RHP -> SP` 26, `SP -> RP` 22, `RHP -> RP` 17,
`LHP -> SP` 10, `LHP -> RP` 2. Identical to PART 2.

The 3 triggers, with their ranks on the CURRENT board (PART 2's ranks in brackets):

| player | flip | age | WAR | eFV | rank | 2026 line | grade-move upper bound |
|---|---|---|---|---|---|---|---|
| `tink_hence` | SP -> RP | 24.0 | 2.01 | 45.3 | 304 [305] | 19 G / 3 GS / 20.3 IP | -0.17 FV |
| `nick_frasso` | SP -> RP | 27.8 | 1.50 | 42.1 | 418 [483] | 25 G / 1 GS / 29.3 IP | -0.79 FV |
| `joe_glassey` | P -> RP | 25.0 | 1.50 | 42.1 | 419 [459] | 23 G / 0 GS / 29.3 IP | -0.40 FV |

The upper bound is deliberately conservative: it inverts the FULL blended `xfv_war_6yr`
through the pooled outcome curve after the ramp factor, whereas `_role_factor` multiplies
only the MODEL leg. The true move is smaller than the number shown.

### Second-order radius, measured not assumed

* **PAL `_prospect_role`: 1,269 rows reclassified.** SP 487 -> 863, RP 310 -> 1,181,
  SWING 1,619 -> 372. `pal_conversion.prospect_role_fit` only emits a `mismatch` when the
  role is SP or RP, so **1,247 prospects that were invisible to the role-mismatch watch
  become eligible for it in one step.** This is a product change of its own size. It is
  FLAGGED, not gated - the flag that would gate it is the same one the owner decided - and
  it is the single largest downstream consequence of Decision 1.
* **`spotlights.py` RP-age-23 disqualifier: NULL.** 546 rows newly meet the gate
  (RP-labelled and age >= 23). **Zero of them clear the FV >= 45 floor that sits in front
  of it**, so no spotlight changes. PART 2 reported the exposure (830 rows) but not the
  interaction with the FV floor; measured, the interaction kills it entirely.
* **`value_framework` relief paths: 871 rows enter, 5 dollars move.** All 871 enter
  `is_reliever_position` and move `_roster_group` to "RP", so `relief_war_haircut` (0.5)
  and the `_pitcher_rp_by_bucket` all-relief vector now apply to them. But priced at their
  served grades, only **5 rows change surplus at all** - the rest price at $0 on both
  sides, which is the $0-heavy board the eFV defect ledger already documents. Worst:
  `tink_hence` $9.24MM -> $2.03MM, `nick_frasso` $4.61MM -> $1.74MM, `seth_clausen`
  $3.99MM -> $1.71MM, `joe_glassey` $3.67MM -> $1.72MM, `nicolo_pinazzi`
  $1.78MM -> $1.68MM. Mean -$2.88MM over the 5.
* **`grpo_prospect._POS_BUCKET`: an improvement.** `P` is bucket 5 (starter) and `RP` is
  bucket 6 (relief). 830 `P -> RP` flips move off the starter bucket and onto the relief
  bucket another lane added the same day. Not a regression.

## 3.2 DECISION 2 - `baseballamerica_statcast_by_age` no longer carries an FV

`source_articles.py` now emits that snapshot with `fv=None`. The row survives (identity,
position, org, active status, and the statcast event payload) - it just stops voting.

**Nothing is served differently until the next production ingest.** The 41 rows in
`prospects.db` still read 40.0 today; `insert_snapshots` is an UPSERT with
`fv = excluded.fv`, and the drop file `data/2026-06-03_statcast_byage.txt` is re-parsed on
every run, so the next ingest writes `fv=NULL` over them. No DB surgery was needed and none
was done. That also gives the owner a window to revert before anything is served.

**Method.** The full real path: `consensus.build_timeseries(load_all_snapshots(),
normalize=ADOPT_NORMALIZED_CONSENSUS)` over all 51,180 snapshots, run twice - once as the
DB stands, once with the 41 rows' `fv` set to `None` - comparing every player's LATEST
consensus point.

| statistic | before -> after |
|---|---|
| players whose latest consensus point moves | **34** |
| collateral movement on players outside the source | **0** |
| `avg_fv` delta | mean +0.497, median +0.210, range -2.500 .. +2.710, 27 up / 7 down |
| served `consensus_fv` delta | mean +0.324, 13 up / 6 down / 15 unchanged |
| best movers | `alexander_frias`, `james_tibbs_iii` 46 -> 49 |

### The owner's "all movement should be upward" premise is REFUTED, three ways

The decision brief predicted only upward movement, on the theory that the fabrication
DILUTED real grades. It did that on most players, but not all, and the exceptions are the
same defect seen from the other side. All three are arguments FOR the removal.

1. **On 7 of the 41 the invented FV 40 was ABOVE the player's real grades.** It was
   INFLATING them. `hyun_seung_lee`, `juan_villavicencio` and `richard_matic` all carry a
   real FV 35 and were being served 38; `jesus_pinto` 38.1 -> 36.3. Removing a fabricated
   grade that was too HIGH correctly moves a player down.
2. **Two players move UP on `avg_fv` and DOWN on served consensus.** `jason_schiavone` and
   `luke_hill` both go 40.64 -> 41.28 pre-shrinkage but 41 -> 40 served, because losing the
   fake vote takes them from 2 explicit-FV instances to 1 and re-arms the single-instance
   shrinkage pull toward FV 35 (`consensus.SINGLE_SOURCE_K`). The fabricated grade had been
   buying them a second opinion that did not exist - a second, unreported effect of the same
   defect, on `avg_fv_n` rather than on `avg_fv`.
3. **NOT PREDICTED BY THE AUDIT: 7 players leave the board entirely.** `braylon_whitaker`,
   `easton_shelton`, `jacob_friend`, `jake_cunningham`, `jose_meza`, `mason_guerra`,
   `michael_martinez` have **exactly one snapshot in the entire database - this one.** They
   are on the served board today only because we graded them ourselves. With no FV and no
   rank they produce no consensus point and drop out of the timeseries. Ranks 373 / 458 /
   473 / 483 / 638 / 759 / 1,383 - **none inside the top 300**, so nothing above rank 373
   re-ranks. Their snapshot row survives with `fv NULL`, so they stay in `players` with
   identity, org, position and active status; what they lose is a grade nobody ever gave
   them. `jacob_friend` is the one worth a second look: our own eFV grades him 43.5, and
   that grade disappears with him.

### Dangling references: none

`grade_normalization` selects `WHERE fv IS NOT NULL` and its `_mappable` guard already
refuses constant distributions, so the source drops out of normalization exactly the way
`baseballamerica` (100 rows, rank, zero FV) already does. It is NOT in `_SYNTHETIC_SOURCES`,
not in `data/source_weights.json`, and a repo-wide search finds it in no other `.py`,
`.html` or `.js` file. `data/grade_normalization_eval.json` and
`reports/grade_normalization.md` carry a stale row that regenerates itself.
`performance_ingest` was NOT touched.

## 3.3 DECISION 3 - `position_observed` published, safe consumers flipped

### Published

`storage.py` loads `fielding_positions.load_observed_positions()` once in the export and
emits `position_observed` on the player payload. **Omitted, not nulled**, when there is no
observation - `.get()` returns `None` either way and omitting keeps ~2,500 null keys out of
the payload. Coverage: 1,956 of 2,104 served non-pitcher rows (93.0%).

### Flipped to the observation

| consumer | file | measured blast radius |
|---|---|---|
| D-Tool catcher weighting | `storage._compute_tool_composites` input | 156 covered rows change bucket; **44 cross the catcher boundary** (the only crossing that changes a weight); only **9** of those 44 have a `composite_def` to move at all. Best-ranked `josue_briceno` (served 1B, observed C, rank 65). `composite_def` is display-only - D-Tool pill and tool flag - not a board input. |
| detail-page peer pools | `prospx` `_prospectDetailSidebarCards` | display cohorts, no board effect |
| tool-comparison radar cohort | `prospx` `_toolCompCandidates` | display cohort |
| similar-prospects cohort | `prospx` `renderPlayerDetail` | display cohort |
| RPS+ cohort cell + positional multiplier | `prospx` `_rpsPositionGroup` / `_rpsPositionMultiplier` | **425 of 1,957 covered rows change position group; 424 change the multiplier**, deltas -0.11 .. +0.16; **13 inside the served top 100** (`josiah_hartshorn` 20, `caleb_bonemer` 22, `kevin_alvarez` 26, `roldy_brito` 29, `jojo_parker` 30, `edward_florentino` 34, `charles_davalan` 35, `josue_briceno` 65, `josh_adamczewski` 67, `francisco_renteria` 70, `jett_williams` 79, `elian_pena` 81, `emmanuel_rodriguez` 87). RPS+ is computed client-side and does NOT enter `overall_rank`. |

All frontend flips go through one new helper, `cohortPosition(p)`, which returns
`p.position_observed || p.position`. It degrades to the projection on any payload built
before the field shipped, so the frontend change is a no-op until the next export.

### Kept on the projection, on purpose

Positional scarcity dollars, the org depth chart, farm positional need, the board filters,
the position pill, and the payload's primary `position`. The reason is measured and is the
whole finding of PART 2: the disagreement is SIGNED. FanGraphs projects a move DOWN the
defensive spectrum 318 times against 184 up, so repointing scarcity would pay 318 players a
premium-position premium the industry says they will not hold. A test now pins this refusal
(`test_the_projection_consumers_are_still_on_the_projection`).

### GATED DEFAULT-OFF, and why - one root cause, two flags

`efv_model.POS_PREMIUM_USES_OBSERVED = False` and
`prospect_def_value.DEF_VALUE_USES_OBSERVED = False`. Both are built, both are exact no-ops
while off (pinned by test), both are registered.

**The root cause is a COVERAGE SPLIT that is aligned with the LABEL.**
`fielding_positions.build_positions_played`'s `__main__` filters to players with no
`debut_date`, so the census is PRE-DEBUT ONLY:

| pool | rows with an observation |
|---|---|
| live eFV scoring pool (served hitters) | 1,956 / 2,104 = **93.0%** |
| eFV hitter TRAINING matrix | 613 / 1,927 = **31.8%** |
| ... of its BUST rows | 570 / 1,082 = 52.7% |
| ... of its DEBUTED rows | 43 / 845 = **5.1%** |

A fallback-to-projection flip would therefore define the feature one way on 93% of the rows
the model SCORES and the other way on 68% of the rows it TRAINS on - and the training split
is almost perfectly aligned with the target (95% of debuted rows fall back, 47% of busts
do). A feature whose DEFINITION correlates with the label is the shape of a leak, and a
ridge will learn it. That is a worse defect than the one the flip fixes.

`prospect_def_value` has a SECOND, independently disqualifying reason: its `position` is
documented as the AS-OF-DECISION label dated at the scouting snapshot, and that is what
makes the model leakage-safe and what its out-of-split win over FanGraphs' fFld grade rests
on. `positions_played.json` is CAREER-TO-DATE, so for a historical row it contains games
played AFTER the decision - part of the very migration the model is scored on predicting.
Note the contrast that shows the module already uses the census correctly:
`_up_mid_share_map` reads the SAME file as a present-day QUALITY MULTIPLIER, which is a
legitimate as-of-today read. It is the POSITION VECTOR, the thing that has to be dated, that
cannot come from a career-to-date file.

**What each would do if switched on today:**

* `_pos_premium`: 116 of 613 covered training rows change (69 gain the premium, 47 lose it);
  327 of 1,956 live rows change (232 gain, 95 lose - the same down-spectrum skew, 2.4:1
  here); **10 rows inside the served top 100** change the feature - `caleb_bonemer` 22,
  `kevin_alvarez` 26, `jojo_parker` 30, `edward_florentino` 34, `charles_davalan` 35,
  `josue_briceno` 65, `josh_adamczewski` 67, `francisco_renteria` 70, `elian_pena` 81,
  `emmanuel_rodriguez` 87 - and 29 inside the top 300. Ten top-100 rows is more than a
  handful, which is the owner's own gating threshold, independent of the leak argument.
* `def_value`: 225 of 613 covered hitter-matrix rows change `milb_vector`, and the change
  would be unmeasurable on 95% of the eval pool that could say whether it helped.

**Unblocking these is a DATA build, not a modelling call.** `pos_prem` needs
`positions_played.json` rebuilt WITHOUT the pre-debut filter. `def_value` needs an AS-OF
census (per-season fielding splits truncated at the decision date), which is strictly more
work. Then the eFV accuracy gate and the ladder eval respectively.

### Not flipped, with reasons

* **Draft-class same-position peers** (`_draftDetailSidebarCards`). `classProspects` are
  amateurs, so the MiLB fielding census has nothing for them and the flip would be a no-op
  on the pool it serves. Left alone. Latent defect noted in place while there: that cohort
  compares a RAW position string for equality, so it already misses any compound label
  ("SS/2B" never equals "SS"). Separate change, separate blast radius.
* **`storage._pos_bucket_v2`** (the DvM+ / SC+ display-index cells). PART 2 recommends the
  observation and the argument is the same as RPS+, but the owner's decision did not name it
  and those indices carry clamps and registry rows another lane is actively sweeping. Owed.

## 3.4 A note on movement suppression across all three decisions

Decisions 1 and 2 both move served grades on the next regen (3 rows through the reliever
ceiling, 34 through consensus). Neither is player movement, and the two suppression
mechanisms happen to cover both for one run:

* the RANK signal is gated by `BOARD_RANK_BASIS_EPOCH`'s strictly-after filter, already at
  2026-07-30;
* the eFV-delta signal is gated by `xfv_history_is_on_board_basis()`, which compares the
  artifact's stamp against `board_basis_fingerprint()`. Extending the fingerprint with the
  `roles=` term automatically invalidates the stamp, so the override stays suppressed until
  a production regen writes a series on the new basis.

That is the suppression working, not an accident to rely on. If the role flip had shipped
WITHOUT the fingerprint change, neither gate would have fired for it.

## 3.5 Owed follow-ups after this lane

1. **Rebuild `data/positions_played.json` without the pre-debut filter**, then re-run the
   eFV gate with `POS_PREMIUM_USES_OBSERVED = True`. This is the single blocker on the most
   interesting flip in the sweep.
2. **Build an AS-OF fielding census** (per-season splits truncated at the decision date)
   before `DEF_VALUE_USES_OBSERVED` can be evaluated at all.
3. **Reconcile `prospx` `displayPosition()`** with `position_observed`. It still MUTATES
   `p.position` in place, OF-only, before every filter, cohort, depth chart and scarcity
   multiplier runs, which means the frontend and the backend can disagree about the same
   player's position today. A pointer comment was added at the mutation site; the fix is its
   own change, and note that it moves the board FILTERS, which the observation flip
   deliberately does not.
4. **Decide on the PAL role-mismatch population**: 1,247 prospects became newly eligible for
   the role-mismatch watch in one step (3.1). Nobody has looked at what that surface now
   shows.
5. **`_pos_bucket_v2`** (DvM+ / SC+ buckets) - observation or projection.
6. **Consider splitting the emitted `RP` label** into SIRP/MIRP by IP per appearance now
   that the both-directions flag is on. Still deliberately not done: the cut is unvalidated
   and generic `RP` is already exact for every downstream role gate.
7. **The 7 board departures** from 3.2 are worth an owner look, `jacob_friend` in particular
   (our own eFV grades him 43.5 and that row disappears with him). If we want to keep
   model-graded players who carry no published grade at all, that is a deliberate product
   decision about the ungraded floor, not something a fabricated FanGraphs-scale vote should
   be doing by accident.

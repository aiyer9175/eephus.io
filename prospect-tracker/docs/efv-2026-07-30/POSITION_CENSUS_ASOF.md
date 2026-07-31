# The full-career, as-of-aware position census

Owner decision taken 2026-07-30: **build the full-career position census.** This answers
follow-ups 1 and 2 of `docs/efv-2026-07-30/POSITION_ROLE_GATE.md` section 3.5.

Files this lane owns: `fielding_positions.py`, the artifacts it writes, and its own tests
and docs. It does NOT edit `efv_model.py`, `efv_ungraded.py`, `value_framework.py`,
`efv_score.py`, `bullpen_export.py`, `proj_export.py` or `prospect_def_value.py`.
**`POS_PREMIUM_USES_OBSERVED` and `DEF_VALUE_USES_OBSERVED` are NOT flipped here.** They
are model changes and they belong to the eFV lane with their own gates. This lane's job
ends at the data being trustworthy.

---

## 1. Why the census stopped pre-debut

The gate doc records the bound as `build_positions_played`'s `__main__` filtering on
`debut_date`. That is real but it is not the production path. The pipeline calls the
builder at `run_monthly.py:2164-2171` and filters there:

```python
versa_input = [... for p in timeseries
               if p.status != "debuted" and ids_by_key.get(p.player_key)]
```

Two independent filters, same effect, and the provenance says the same thing about both.

**It is a SCOPE bound inherited from the artifact's original job, hardened by a COST
bound. It is not a leakage guard.** Three pieces of evidence, all contemporaneous:

1. **The commit that created it** (`c78a5a1`, 2026-06-24) describes the artifact as a
   frontend chip: *"'Versa' was a FanGraphs scout-reported multi-position string. It's now
   derived from ACTUAL GAME DATA... Ran it for all active position prospects: 868
   players."* The consumer was `prospx`'s versa flag. "Active position prospects" is the
   population a prospect board displays; a graduate has left the board, so he leaves the
   artifact. No temporal claim is made anywhere in the commit, the module docstring, or
   the `run_monthly` step comment.

2. **The cost bound is documented in the pipeline, in the builder's own step comment**
   (`run_monthly.py:2144-2152`): the step is *"measured 437s, the single slowest step in
   the pipeline"*, because `fetch_player_fielding` fires **one StatsAPI request per
   player**. That is also why the whole artifact sits behind a freshness gate
   (`VERSA_FRESH_DAYS`). A per-player loop over every player who ever appeared in the
   system is not affordable, so the loop was pointed at the board. The scope bound is
   what the cost bound could pay for.

3. **There is no as-of truncation anywhere in the module.** `fetch_player_fielding` asks
   for `stats=career`, so every value is summed to the BUILD DATE. If the pre-debut filter
   were a lookahead guard it would be a strange one: it would leave career-to-date totals
   in place for everyone it kept. The filter decides *whose* career total is fetched, not
   *how far* the total runs.

**Conclusion: the bound is not a deliberate leakage guard, so removing it is not removing
a protection.** But that finding does not by itself make a full-career census safe, and
the rest of this doc is about the two ways it could still go wrong.

---

## 2. Is extending it SAFE, or does it introduce lookahead?

A naive extension - "drop the debut filter, keep `stats=career`" - **would introduce a
worse leak than the one it fixes**, for exactly the reason `prospect_def_value.py:317-323`
already states: a career-to-date census asked about a 2015 training row returns games
played through 2026, including the positional migration the model is scored on predicting.

So this lane does not do that. The census is rebuilt on a different substrate:

| | shipped census | this census |
|---|---|---|
| endpoint | `/people/{id}/stats?stats=career&group=fielding&leagueListId=mlb_milb` | `/stats?stats=season&group=fielding&sportIds={1,11..16}&playerPool=ALL` |
| requests | **one per player** (437s for ~2,700) | **one per league-season** |
| grain | career total to build date | **per season** |
| population | board members who have not debuted | **everyone who appeared in affiliated ball, including retired players** |
| key | `player_key` | MLBAM id |
| as-of | none possible | `season_visible_through(as_of)` |

Per-season grain is what makes it safe. `as_of_by_pos(seasons_map, as_of)` sums only
seasons that were COMPLETE at the as-of date, so a historical row's vector contains
nothing that postdates its own decision.

### The as-of rule, pre-registered

`season_visible_through(as_of)` returns the last season complete at `as_of`, using a fixed
Oct 1 boundary (`SEASON_END_MONTH` / `SEASON_END_DAY`):

* a 2024-01-22 scouting snapshot sees **2023 and earlier**;
* a 2024-08-15 snapshot **also sees only 2023**.

Dropping the partial current season is deliberate. The endpoint returns a season TOTAL, so
crediting 2024 at an August 2024 decision would import games played after the call. Only
game-level truncation could recover that partial year and this feed cannot give it, so the
honest bound is whole completed seasons. It costs recency and buys the property the
`prospect_def_value` ladder eval needs: nothing in the vector postdates the decision it is
scored against.

`as_of_by_pos` returns `{}` - never a career total - when the as-of date is missing or
unparseable, so a caller asking for a dated read can never silently receive an undated one.
That is pinned by test.

**The eFV matrix anchors on `asof_date`, not `cutoff`.** All 1,927 rows carry `asof_date`
(the scouting-snapshot date). For debuted rows `cutoff` is the DEBUT date, which is always
later; anchoring on `cutoff` would have let the debut season itself into the window. The
two fields are 4 to 6 months apart on the debuted side and identical on the bust side.

### The definition is coherent across train and score

Training rows are read at their own `asof_date`; live rows are read at today. Both are
"the census as of the moment this row's grade is formed", so the feature has ONE
definition on both sides of the model. That was the property the gate doc found missing.

---

## 3. What actually binds coverage - and it is not the debut filter

This is the finding that matters most, and it was not visible before the census was built.

The census is keyed by MLBAM id, so coverage is capped by how many of our `player_key`s
can be bound to one. **That cap is itself aligned with the label, in the opposite
direction from the debut filter.** Measured on the eFV hitter matrix with the platform's
existing identity sources (`.cache/mlbam_ids.json`, `player_photos`,
`data/sources/mlbam_id_overrides.json`, the matrix's own `mlbam_id`):

| | id-resolved |
|---|---|
| DEBUTED rows | 836 / 845 = **98.9%** |
| BUST rows | 579 / 1,082 = **53.5%** |

A player who reached MLB is in every roster index we build from; an org-filler minor
leaguer who washed out in 2016 is not. So **simply dropping the debut filter would not
close the coverage gap - it would INVERT it**, from 47.6pp favouring busts to 45.4pp
favouring debuted rows. Same leak shape, mirror image. That is the trap in this task and
it is worth stating plainly: the pre-debut filter is the SECOND of two label-correlated
bounds, and it is the smaller one.

Note also that bust id-resolution (53.5%) almost exactly equals the shipped census's bust
coverage (52.7%). The old builder was already fetching every bust it could identify. The
debut filter was never what starved the bust side; identity was.

### Closing the identity gap, for free

The league-wide fielding feed carries `player.fullName` beside `player.id` for every
player in affiliated ball, which makes the census its own identity surface - and a far
wider one than an MLB roster index. `resolve_census_ids` binds an unresolved key to a
census id only when the normalized-name match is **unique after a guard**: the candidate
must already be playing by the row's decision year, so an id whose first season postdates
the decision is rejected as a different player. Ambiguous names are dropped, never guessed.

This is a **census-scoped** binding for coverage. It deliberately does NOT write to
`.cache/mlbam_ids.json` or `data/sources/mlbam_id_overrides.json`; the identity pipeline
owns those, and the 2026-07-24 program already recorded that pushing resolved old-cohort
ids into the model REGRESSED it. The bindings land in `data/fielding_census_ids.json` with
per-key provenance (`known` / `name`), so every one of them is auditable and reversible.

---

## 4. Coverage

Measured against the same three populations the gate doc used. The OLD column
reproduces the gate doc's published figures EXACTLY (93.0% / 31.8% / 52.7% / 5.1%), which
is the check that the populations are defined the same way.

| population | OLD pre-debut | NEW as-of season |
|---|---|---|
| live eFV scoring pool (served hitters) | 1,956 / 2,104 = **93.0%** | 1,985 / 2,104 = **94.3%** |
| eFV hitter TRAINING matrix | 613 / 1,927 = **31.8%** | 1,766 / 1,927 = **91.6%** |
| ... of its BUST rows | 570 / 1,082 = 52.7% | 927 / 1,082 = **85.7%** |
| ... of its DEBUTED rows | 43 / 845 = **5.1%** | 839 / 845 = **99.3%** |

**Debuted-minus-bust coverage gap: -47.6pp -> +13.6pp.** The absolute separation falls by
**3.5x** and changes sign.

### The gap NARROWS but does NOT close, and the residual is decomposed

| cause of a missing observation | bust | debuted | contribution to the gap |
|---|---|---|---|
| covered | 85.7% | 99.3% | - |
| no MLBAM id | 8.1% | 0.0% | 8.1pp |
| no completed season before the as-of date | 5.2% | 0.7% | 4.5pp |
| below the exposure floor / DH-only in window | 1.1% | 0.0% | 1.1pp |

**By the pre-registered success criterion - "coverage no longer separates debuted rows from
busts" - this lane does NOT clear it, and the two consumers must stay gated.** 13.6pp is a
much smaller lever than 47.6pp, but a ridge can still learn it. What follows is what each
residual term actually is, because two of the three are irreducible and one is not really
an identity failure at all.

**(a) The 87 unresolved rows are overwhelmingly NOT identity failures.** All 87 are bust
rows and 51 of them carry a name that appears NOWHERE in the affiliated fielding feed
2005-2026. Inspected, they are dominated by NPB and KBO players - `do_yeong_kim`,
`tatsuki_mizuno`, `chusei_mannami`, `shugo_maki`, `rui_muneyama`, `shion_matsuo`,
`baekho_kang`, `ju_won_kim`, `ryusei_terachi`, `seiya_yokoyama` - international
professionals who entered the matrix as posting/IFA candidates and **never played
affiliated ball at all**. `amateur_leagues.EMPTY_SPORTS` already records sportIds 31 (NPB)
and 32 (KBO) as verified empty in StatsAPI, so there is no feed that could cover them. A
fielding census cannot observe a player who has no affiliated fielding record; the honest
value for these rows is null and always will be.

The other 38 are ambiguous names. 34 of those have **no birth date anywhere in the
platform** (not in the matrix, not in `players`), so the birth-year guard has no input and
`resolve_census_ids` correctly refuses to guess. Resolving them needs a birth-date backfill,
not a census change.

**(b) The 62 "no completed season before the as-of date" rows are a CORRECT null.** 38 of
62 are IFA signings graded at signing, before they had played a professional game. At that
decision date there is genuinely nothing to observe, and any value other than null would be
lookahead. This term is a property of the as-of definition, not a defect in it - it is the
price of the leakage-safety the whole build exists to buy.

**(c) Conditional on identity, the gap is 6.1pp.** Restricted to the 1,840 rows that carry
an MLBAM id, coverage is bust 927/995 = **93.2%** and debuted 839/845 = **99.3%**. If the
eFV lane drops the 87 unresolvable rows from the training pool (4.5% of the matrix, all
bust, and all with a documented reason), the residual separation is 6.1pp, of which 4.5pp
is the irreducible (b). That is the number the eFV lane should be gating against, and it is
a modelling decision this lane does not take.

### Sanity check: the two censuses agree where both can see

On the 2,567 players covered by both artifacts, the season census and the shipped
career census resolve **the same position 2,556 times, 99.6%**. The 11 disagreements are
not noise - see section 7, they are a bug in the shipped one.

---

## 5. What this cost

| | |
|---|---|
| network | **154 league-season requests, 311s** (fetched twice: once before `age` was retained, once after - 685s total) |
| free reuse | MLB sportId 1, 22 seasons, came from `fielding_innings.py`'s existing `.cache/statsapi_field` at **zero requests** |
| cache written | `.cache/statsapi_field_season/fld_v2_{sport}_{season}.json`, 154 files, 48 MB, 490,091 rows |
| artifacts | `data/positions_played_seasons.json` 1.05 MB (3,827 players), `data/fielding_census_ids.json` 0.19 MB |
| deploy | both added to `deploy/data_exclude.txt` - model-side inputs, no page fetches them |

For contrast, the shipped per-player builder takes **437s to cover 2,675 CURRENT board
members** and structurally cannot reach a retired player. This one covers every player in
affiliated ball 2005-2026 for less time than that, and closed seasons never need refetching.

Nothing else was run: no `run_monthly`, no `build_site`, no exporter, no pytest.
`data/positions_played.json` was **not** regenerated.

---

## 6. What remains before the two gated consumers could be measured

Neither flag is flipped here. Both remain `False`.

**`efv_model.POS_PREMIUM_USES_OBSERVED`** - the blocker its own comment names ("rebuild
positions_played.json WITHOUT the pre-debut filter") is now cleared: the training pool goes
from 31.8% to 91.6% covered and the definition is the same on both sides of the model. What
is still owed before it can be measured:

1. An eFV-lane decision on the 87 unresolvable rows - drop them from the pool, or carry an
   explicit `has_observation` indicator so the ridge cannot confound coverage with the
   label. Doing neither leaves a 13.6pp separation in place.
2. `efv_model._observed_pos_map` currently reads `load_observed_positions`, which is the
   career-to-date, player_key-keyed artifact. It needs repointing at
   `observed_positions_as_of(census, {key: asof_date}, ids)`. That is an `efv_model.py`
   edit and belongs to the eFV lane.
3. Then the accuracy gate in `docs/EFV_GATE_STANDARD.md` on the refit. The gate doc already
   measured that 10 top-100 rows change the feature, so this moves the board and carries a
   `BOARD_RANK_BASIS_EPOCH` bump plus a `BOARD_BASIS_FINGERPRINT` restamp.

**`prospect_def_value.DEF_VALUE_USES_OBSERVED`** - its FIRST and disqualifying reason was
that the census is career-to-date while its `position` is documented as the as-of-decision
label. `as_of_by_pos` removes exactly that objection: the vector can now be dated at the
scouting snapshot, so the out-of-split ladder eval stays valid. What is still owed:

1. Repoint `_observed_pos_map` at the as-of resolver keyed on each matrix row's own
   `asof_date` (a `prospect_def_value.py` edit, not this lane's).
2. Re-run `data/positional_ladder_eval.json` out-of-split. Its ground-truth pool is the
   DEBUTED rows, which went from 5.1% to 99.3% covered - the eval was previously blind on
   95% of the population that could say whether the flip helped, and is not any more.
3. Note that `_up_mid_share_map` is a legitimate PRESENT-DAY read and should keep using
   `career_by_pos`; only the position VECTOR needs dating.

**Also owed, outside both flags:** wire the season census into `run_monthly` so it refreshes
(closed seasons are final; only the current season needs a refetch), and decide whether
`data/positions_played.json` should be rebuilt FROM the season census rather than from 2,675
per-player requests. The latter would retire the 437s step, the pre-debut filter and the
double-count in one move, but it changes a served artifact and needs its own gate.

---

## 7. A defect found in passing: the shipped census double-counts every MiLB game

Not part of the brief, found while checking the two censuses against each other, and it is
in a file this lane owns.

`fetch_player_fielding` sums EVERY split the career endpoint returns. That endpoint returns
per-LEVEL splits (`A`, `A(Short)`, `A+`, `AA`, `AAA`, `ROK`, `MLB`) **and a `Minors` ROLLUP
split that restates the sum of all the non-MLB ones**. Verified exactly, position by
position, on `jesus_made`, `leo_de_vries`, `bobby_witt_jr`, `dawel_lugo` and `jose_ramirez`
across every level mix: `rollup == sum(non-MLB per-level rows)`, no exceptions.

So **every minor-league game is counted twice and every major-league game once.** That is
not a uniform scale error, it is a WEIGHTING error between levels, and it biases the
resolved position toward wherever a player logged his MINOR-league time.

`dawel_lugo` is the clean case:

| | SS | 3B | resolves to |
|---|---|---|---|
| shipped (MiLB doubled) | 736 | 702 | **SS** |
| true | 368 | 390 (312 MiLB + 78 MLB) | **3B** |

**Blast radius: 11 of 2,567 comparable players (0.43%) change `observed_position`** -
`johan_de_los_santos`, `abiezel_ramirez`, `adolfo_sanchez`, `quin_cotton`, `dawel_lugo`,
`cody_miller`, `anderdson_rojas`, `jose_astudillo`, `ariel_reynoso`, `abel_sosa`,
`alex_linares`. All are adjacent-position flips (2B/SS, RF/CF, 3B/2B, LF/RF), which is what
a level-weighting bug produces. The other effect is that the versa exposure floor (10 G / 5
GS) has been operating at roughly HALF its stated value for minor-league play.

**Fixed in the builder; the artifact was NOT regenerated.** `aggregate_career_splits`
discards the rollup when per-level minor-league rows are present, and keeps it when a player
carries only the rollup (dropping it would lose him). Pinned by five tests.

`data/positions_played.json` on disk still holds the doubled counts, so nothing served moves
today. **The next monthly `run_monthly` step 3a-ii will pick the fix up and move those 11
players**, which reaches `position_observed`, the RPS+ cohort cell and the catcher D-tool
weighting that `POSITION_ROLE_GATE.md` section 3.3 flipped to the observation. None of those
is an `overall_rank` input, so this is display movement rather than board movement - but it
is movement, it is now predicted rather than discovered, and it is an owner call whether to
regenerate deliberately or let the monthly take it.

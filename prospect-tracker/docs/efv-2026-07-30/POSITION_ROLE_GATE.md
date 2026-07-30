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

Appended after PART 1 was on disk. See below.

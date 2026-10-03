# Staff Gems: the persistence gate (registration, 2026-10-03)

Registered 2026-10-03 on branch `efv-conviction-2026-08-08` (writer lane worktree), committed ALONE,
before any staff spell has met a grade pair and before the stage 0 staff fetch has run. Model id
`staff_gems`. Design: `docs/staff-gems/DESIGN.md` (where the two differ, this document wins). Owner
answers: SG-Q1 to SG-Q4 (2026-09-30) and Q-DVM-1 (2026-10-01), `DECISIONS_FOR_OWNER.md`. Plan: Part 8
P8.8 'Staff Gems' and 8.D 'Conflicts between lanes, resolved' rows 6 and 7.

Nothing below may be edited once any number in section 6 has been computed. Later text is appended
in section 13 with its date, never written over this text.

## 1. The question

Per role, one question: does a staff member's deviation from his own organization's mean, in the
traits his job covers, REPEAT in a second, disjoint group of the players he coached? A number that
does not repeat, printed beside a person's name, is a ranking of noise. The gate decides, per role,
whether any person may be named for that role (SG-Q1, SG-Q3). It does not decide anything else.

| Role | Staff (StatsAPI jobId) | Traits, same-source grade pairs | Players |
|---|---|---|---|
| hitting | COAT, COAH; assistant COAA | hit, game power, raw power, pitch selection, bat control | position players |
| pitching | COAP; assistant COPA; bullpen COAU | fastball, slider, curveball, changeup, cutter, command | pitchers |
| defense | DEFC; infield and catching titles mapped by hand in `config/staff_roles.yaml` (stage 1) | field, arm | position players |
| manager | MNGR and interim managers | overall FV, same-source grade pairs | all |

The manager leg reads same-source FV grade pairs, list to list, NEVER the per-snapshot eFV series
(plan 8.D row 6: the eFV retrospective series is today's model re-scoring old lists, the wrong
object for crediting past staff). No role reads eFV. Speed stays with the organization. A title
that maps to no role goes to the review queue and is never given a guessed role.

## 2. Preconditions for the look

1. Stage 1 (SG-1) landed: persons, spells and units parsed from `.cache/staff/`, the role map with
   its review queue, the identity rule (a person is the MLBAM id; a name never creates a person).
2. Stage 2 code (SG-2) landed: the exposure splitter, the estimator of section 5, and
   `tools/staff_gems_gate.py`, with `test_staff_gems_gate.py` passing.
3. The dry run of section 10 passed on fixtures with nulls.
4. The frame timing of section 3.3 holds on the day of the look.
5. The day is not a registered look date of any other gate (`docs/*GATE*.md`,
   `docs/diamond-betting.md`, plan Part 8 section 8.B) and not 2026-10-23, 2026-11-06,
   2026-11-13 or 2026-11-20, nor the eFV reserved-read day, nor a Part 9 look day.

VAL_4 is NOT a precondition: graduate WAR is not an input to this gate.

## 3. The frame

### 3.1 Grade pairs

The org Tendencies `toolDev` unit: consecutive snapshots of one player from one source, at least
60 days apart, the same organization at both ends; a pair that crosses an organization change is
split at the change date by the shared splitter (never dropped silently, never credited across the
change). Pairs from 2017-01-01 (the `gradeHistory` window) whose LATER snapshot is dated on or
before 2026-09-30; rows inserted before the freeze stamp the look writes first; a sha256 manifest
of the frame rows in the artifact.

### 3.2 Staff spells

Spells 2008 to 2026 from the StatsAPI coaches endpoint as fetched into `.cache/staff/` by
`staff_ingest.py --fetch` (stage 0), parsed in stage 1. Season-resolution spells (no date
bisection) are credited by days in the unit's season; day-resolution spells by days held.

### 3.3 The reserved 2020-2021 list vintages, and the timing (owner answer Q-DVM-1)

Q-DVM-1 is answered ("Exclude until then", 2026-10-01), and the same rule binds this gate (plan
8.D row 6). Grade pairs with an endpoint (either snapshot) in list vintage 2020 or 2021, the eFV
reserved frame R-LV, enter the look ONLY IF the R-LV look record exists when the look runs. The look
waits for that record. If no R-LV look record exists by 2027-01-31, the look runs on or after
2027-01-31 on the COMPLEMENT frame (no pair with a 2020 or 2021 endpoint) and the artifact says so
in its `frame.reserved_vintages` field. Nothing in this gate reads an eFV score, a realized MLB
statistic, a debut, WAR or a bust; no row of R-VM (the 2025+ debut cohorts) is scored; no
statistic is grouped by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`).

The fWAR label epoch's step Z is not a precondition (the manager leg reads no eFV), but the look
never runs between the epoch's step A and its step Z entry.

## 4. Exposure

For pair i and unit u (an affiliate-season, or the org-offseason unit), `e_iu` is the player's
active days at u inside the pair's interval, divided by 365.25; IL, rehab and MLB days are removed;
offseason days go to the org-offseason unit and to nobody by name. For staff member c in role r,
`e_ic` sums, over days, [player active at u] x [c holds r at u that day] / [holders of r at u that
day]. Days with no holder go to "vacant". Several sources grading the same months are weighted
1 / (number of that player's source pairs overlapping the pair).

## 5. The estimator

Per role, for every trait in the role's family: the league baseline by weighted least squares
(level, trait, source and season development rates per exposure-year; age at the first snapshot as
a spline; exposure-weighted park factor and league; an IL-days indicator; the publication gap). The
residual development, per pair-trait, is apportioned by exposure; the organization's role effect
`a(org, r)` is its exposure-weighted mean residual; a staff member's raw within-org deviation `b_c`
is his exposure-weighted mean residual minus his organization's mean, with its standard error. A
staff member who worked in more than one organization pools his deviations from each
organization's mean. Every statistic in section 6 is computed on RAW `b_c` (no shrinkage), so the
gate does not depend on the prior variance it is testing.

Units: grade points per player-year of exposure on the 20-80 scale. No 100 + 10z index for any
person.

## 6. The legs

### 6.1 Leg 1, split-half persistence, per role

Split each role's players into halves A and B by
`int(sha256(("staff_gems|" + player_key).encode()).hexdigest(), 16) % 2` (0 is A), so a player
informs one half only. Estimate `b_c` in each half. A staff member enters the correlation when he
clears the full floors of section 8.1 on all his players AND the half-floors in each half: at least
6 distinct players with 30 or more active days with him, at least 1.5 player-years of exposure and
at least 15 effective pair-trait observations. Statistic: the Pearson correlation of `b_c(A)` and
`b_c(B)` across those staff.

Null: permute staff labels within (org, level, season) cells, holding each cell's exposure fixed
(each spell keeps its players, days and exposure; only which person's record it belongs to
changes), recompute both halves and the correlation, 2,000 permutations, seed 20261003, the
construction of the management gate (`data/management_gate_eval.json`, `gate_1_split_half.null`).
One-sided p = (1 + number of permuted r at or above the observed r) / (1 + 2,000). Fewer than 20
staff entering the correlation: the role is UNPOWERED for leg 1 and cannot pass.

### 6.2 Leg 2, the pre-tenure placebo

Give each staff member the exposure of the same unit (affiliate and role) in the season BEFORE his
first season there: the players he never coached. Estimate his placebo deviation `b_c(pre)` with the
same estimator and floors halved as in 6.1. Statistic: the Pearson correlation of `b_c(pre)` and his
full-sample `b_c` across staff with both. Null: the same within-cell permutation, 2,000 draws, seed
20261004. The placebo CLEARS its null when its one-sided p is at or below 0.05 (unadjusted, which
makes a pass harder). A coach cannot develop players he never coached: a placebo that clears says
the signal is the affiliate, the level or the assignment of players. Fewer than 20 staff with a
placebo: leg 2 is UNPOWERED and the role cannot pass.

### 6.3 Leg 3, movers (wording only)

Staff past the floors in two organizations: the Pearson correlation of the deviation in the earlier
organization with the deviation in the later one, with its permutation p (2,000 draws, seed
20261005). Fewer than 30 movers: UNPOWERED. Leg 3 never decides PASS. When it is UNPOWERED or does
not clear p at or below 0.05, a named person's card says "above his organization's mean" and never
that he beats another organization's staff.

### 6.4 The detection floor, by injection

For each role, inject staff effects drawn from a normal distribution with SD s into the real
exposure design, with residuals permuted within (org, level, season) cells, for s in 0.10, 0.20,
0.30, 0.40, 0.60, 0.80, 1.00 and 1.50 grade points per player-year, 200 replicates each, seed
20261006. Power at s is the share of replicates whose leg 1 correlation exceeds the 98.75th
percentile of the role's own permutation null (the strictest Holm step, 0.0125). The detection floor
is the smallest s with power at or above 0.80, or "above 1.50". A null without its floor says
nothing; the artifact carries both.

## 7. The decision

- **Family:** the four roles, Holm-corrected at family alpha 0.05 on the leg 1 p-values (the
  smallest p is tested at 0.0125, then 0.0167, 0.025, 0.05; the owner's FP3-3 precedent).
- **PASS for a role** = leg 1 clears its Holm threshold AND leg 2 is powered and does NOT clear its
  own null. Leg 3 decides only the wording (6.3). Anything else is NULL for that role.
- **What a PASS allows:** gems in that role, under the floors (8.1), the gem rule (8.2) and the
  publication rule (9), in stage 3, behind `STAFF_GEMS_LIVE` default False.
- **What a NULL decides (owner answer SG-Q3, "Org view only"):** no person is named for that role;
  the role ships as org-by-role development with the gate sentence and its detection floor, each
  cell under the floors of 9 (ii) or unsigned; the question returns only as a new registration on a
  new frame after the 2027 season, disclosing its overlap with this frame.

## 8. Floors and the gem rule (DESIGN.md 4.5 and 4.6), fixed here

### 8.1 Floors per staff member and role

At least 12 distinct players with 30 or more active days with him inside qualifying pairs; at least
3.0 player-years of exposure; at least 2 seasons in the role; at least 30 effective pair-trait
observations after source down-weighting. Below any floor NO estimate is computed, internal or
served. An org-by-role cell needs 20 players and the person floor of 9 (ii). The floors are never
tuned on outcomes.

### 8.2 The gem rule

A gem in role r must: (1) pass the floors; (2) sit in a role that PASSED (section 7); (3) have the
lower end of the 90 percent band above zero for both the total effect `T_c = a(org, r) + b_c` and
the within-org effect `B_c = b_c` (bands from a player-clustered bootstrap of the whole pipeline,
B = 2,000, fixed seed, posteriors shrunk toward the org mean with the prior variance estimated from
the data); (4) survive Benjamini-Hochberg at q = 0.10 across every staff member in the role past the
floors; (5) remain a gem when any single player is removed. The label is re-decided twice a year and
needs two consecutive checkpoints to change.

## 9. The publication rule (owner answer SG-Q1, "Gems only"), with three additions

1. Name gems only, each with players, player-years, seasons, the 90 percent band and the
   attribution caveat.
2. Never rank, list, sort, colour, export or describe anyone below the mean, by name or by any
   identifying combination (club, level, season and role together identify a person).
3. One state for everyone else: "not measured", "not above the mean" and "below" render
   identically, and so do an unknown person id and a known non-gem id; no view counts staff
   measured.
4. Say who else developed the player (coordinators, rovers, analysts, strength and medical staff,
   the offseason, the player).
5. Removal and corrections on request through /report/, applied through the opt-out list of
   addition (iii) before any payload is written.
6. Data minimization: name, role, club and seasons from MLB's own listing; no photo, age, personal
   links or contract detail. No /news/ rows. Per-person estimates for non-gems live only in the
   gitignored `.cache/staff/` and are never committed.

The three additions, each keeping rule 2:

- **(i) Style fields only beside a name (owner answer SG-Q4).** A named manager or base-coach row
  carries style fields only: attempts, the share of steals of second and third, and the break-even
  faced. No success rate, realized value, mWPA or letter sits in the same row or leaf. The Franchise
  DUGOUT names move to a leaf with no realized figures: today's DUGOUT branch prints realized mWPA
  per decision family (`franchise_export.py@64bf1bb3:757-763`, at 'success_rate'), beside the
  `manager_skill` and `decision_quality` keys its NEVER list bans (`franchise_export.py@64bf1bb3:105-106`,
  FORBIDDEN_KEYS).
- **(ii) A person floor on every org-by-role cell.** Besides the 20-player floor, a cell needs at
  least 4 distinct persons with no person over half of the cell's exposure, or it is shown unsigned
  (a magnitude with no direction).
- **(iii) The opt-out list lives outside the webroot**, in `config/staff_optout.json` or
  `.cache/staff/optout.json`, never under `data/`: every top-level `data/*.json` ships
  (`deploy/publish_paths.txt`; census X03-15).

The two 2027 base-coach tests of SG-Q4 (a first-base-coach movers test on the steal execution
residual; a priced third-base send-or-hold family) are named here and NOT run; each needs its own
registration document, committed before the 2027 season and before any number exists. Until a test
passes, no base-coach number is computed for any person.

## 10. The look: one run, and its crash protocol

The look runs ONCE, at the timing of 3.3. Before it, `tools/staff_gems_gate.py` runs the whole
reporting path on fixtures with nulls (a role with no staff past the floors, an empty placebo, zero
movers). At the look, stdout and stderr are teed to the task's output directory before anything
else runs. On any exception after scoring began: STOP, do not rerun, and write the owner question.
Looking early, or a second look, disqualifies the role results and voids the look.

## 11. The artifact: `data/staff_gems_gate.json`, aggregate statistics only, NO person id

Keys: `model_id`, `registered` (this document's path and commit), `frame` (pair counts, date span,
`reserved_vintages` = "included (R-LV record <ref>)" or "complement frame", the sha256 manifest),
`roles` (per role: staff entering leg 1, the r, the null band and p, the Holm threshold, leg 2's r,
p and verdict, leg 3's movers count, r, p or UNPOWERED, the detection floor, the PASS or NULL
verdict), `family_alpha`, `seeds`, `ran_at`. No key or value carries a person id, a name, or a
row below the role level that identifies a person (no per-org, per-season or per-unit row). The
test `test_staff_gems_gate.py` asserts it. The file is aggregate and ships as the registry's eval
artifact for `staff_gems`.

## 12. Honesty clause: what was known on the design day (2026-09-30)

The lane read structure only: an ARCHIVED backup outside the repo, read-only and immutable, counted
rows, pairs and dates; no grade was differenced, no development rate was computed for any coach,
affiliate or organization, no outcome and no eFV value was read (DESIGN.md section 3).

- Snapshot rows / active with tools and org: 62,839 / 55,521. Same-source, same-org pairs at least
  60 days apart: 25,802 on 5,375 players; 1,341 consecutive same-source rows cross an org change.
  Pair span p10 / p50 / p90: 159 / 197 / 366 days; 64.2 percent touch an October to March window;
  0.6 percent sit inside one April to September window. Pairs by end year: 2012 129; 2015 465; 2017 559; 2018 1,471;
  2019 2,115; 2020 2,611; 2021 2,825; 2022 2,601; 2023 2,490; 2024 2,783; 2025 2,976; 2026 (to
  09-04) 3,559. Pair players with dated affiliate moves: 4,108 of 5,375 (76.4 percent).
- The spread coach effects must show against (committed `data/org_tendencies.json`, cross-org SD of
  tool development, noise included): 0.23 to 0.64 grade points per prospect-year by tool.
- Yankees affiliates, 9 sampled seasons 2008 to 2026: 146 distinct minor-league staff, 89 in more
  than one sampled season, 69 at more than one affiliate (within-org movement is plentiful,
  cross-org movement is the thin part, so leg 3 may be UNPOWERED).
- Arithmetic on stated assumptions (to be replaced by section 6.4): at a per-coach standard error
  near 1 point per player-year and about 300 coaches past the floors, a split-half correlation would
  be about 0.04 at a true coach SD of 0.3 and about 0.24 at 0.8, against a null SD near 0.058. The
  gate can see coach effects about as large as today's whole organization spread, not smaller ones.
  **A null is the likely result**, and the module is designed to ship under one (the In-Game
  Management running game read null on 13,973 attempts and withheld its plus metric).

Stage 1 may count exposure (staff spells against player locations, no grade deltas) to set power;
those counts are appended to section 13 before the look.

## 13. Record (append-only)

Nothing recorded yet.

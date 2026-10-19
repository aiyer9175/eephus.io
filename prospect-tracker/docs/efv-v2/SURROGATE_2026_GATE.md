# Surrogate outcomes of the 2026 MiLB season: SURROGATE_2026_GATE

Registration status: REGISTERED

Owner answer at draft commit (efv2026 OQ1): A (own gate; every section below applies).

Owner answer at registration (efv2026 OQ1): A. Own gate, no ship weight (recorded 2026-10-01 in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, as are the five below).

Owner answer at registration (efv2026 OQ2): A. Freeze; long horizons only: W3 at RT 2031 the single long-run primary, R3 at RT 2029 descriptive, no one-season surrogate read (S4 of s6.2 never runs, and the guard's `lv2026_surrogate` purpose stays closed).

Owner answer at registration (efv2026 OQ3): A. Wait for R-VM look 2.

Owner answer at registration (efv2026 OQ4): A. Leave the level-norm blend's New-Year flip; pin pure norms; disclose; the 12-20 fallback (moot since the step Z entry of 2026-10-03, s8.12).

Owner answer at registration (efv2026 OQ5): A. Defer the hitter-lean test until after this REGISTERED commit, every 2026-list player excluded and counted; read-only, descriptive, read once.

Owner answer at registration (efv2026 OQ6): A. Release the 2028 and 2029 cohorts at R-VM look 3's record, by the dated B9b amendment to `EFV_V2_GATE.md` (b2ed1107, Q10); label reads of registered long-run frames only.

REGISTERED 2026-10-15 (task SG_7, on HEAD e9fc3a3c of `efv-conviction-2026-08-08`). The
status line above reads REGISTERED; every item marked PENDING at the draft is filled (Q1,
Q9, s5.1, s8.11, s8.13, s11); the precondition states of s1 are re-taken against that HEAD,
and all ten hold; section 12 is empty. This commit carries this file alone. Its sha is the
one `tools/efv_surrogate_look.py` finds at run time (`registered_sha`) and hands to
`efv_surrogate_guard`. Registering measures nothing and moves no served number. No calendar
date gated it (owner decision EW3-5, 2026-10-14). The draft paragraph below is kept as the
record of the draft.

THIS IS A DRAFT. It is committed so its text is dated before any association, tabulation or
model fit between a surrogate outcome of the 2026 MiLB season and any rater score, label,
feature or stratum is computed on any list-vintage row (kill rule 3, s7, admits the counts of
s8.9 by name), not as the registration. A draft cannot open a guard:
`efv_vintage_frame.gate_doc_registered` accepts a gate text only when it carries a status
line reading exactly REGISTERED, alone on its line, and no other status line; the surrogate
guard (`efv_surrogate_guard`, task SG_2) applies that test to THIS file at a named commit
through a pure predicate that never touches the R-LV guard. The final commit changes that
one status line, fills every item marked PENDING, and is committed ALONE with section 12
empty.

Drafted 2026-09-30 on branch `efv-conviction-2026-08-08` from the lane `efv2026`
(`inventory.md`, `governance.md`, `surrogates.md`, `PLAN.md`, `REVIEWS.json`), revised
2026-10-01 (round 3) before any commit; the lane's base is 64bf1bb3 and the round-3 HEAD is
26b446d9 (PLAN.md header names which cited files are byte-identical between them). The
round-5 text is annex 8.N of `docs/master-plan-2026-09-24-final-pass.md` (its s5).

Revised a last time on 2026-10-14, before its first commit (task SG_0, re-armed), against
three events that came after round 5. `EFV_V2_GATE.md` reads REGISTERED since e7931ce4
(2026-10-08, owner decision EW2-6), and the one reserved read taken that day
(`tools/efv_v3_backtest.py --confirm`, `data/_labs/efv_v3/efv_v3_confirm.json`) is the
record of R-VM look 1 (that document's s11.1), so the 2026-12-01 date this text waited on
is gone. Owner decision EW3-5 (2026-10-14) waived every look day and registered date: no
calendar day blocks a read here, and a read waits only for data that does not exist yet.
The fWAR label epoch reached its step Z entry on 2026-10-03. The revision drops every
dependency on the cancelled 2026-12-01 read and on the blocked days, names look 1's record
file (Q8, s2.3), re-takes the precondition states (s1), the epoch facts step Z settled (Q3,
Q5, s8.12, s8.13, s10) and the citations into `EFV_V2_GATE.md` at this commit, and drops
Q3's floor requirement (s1 says why). Every frame, outcome, statistic, clause and decision rule is otherwise
unchanged. Citations into code and into other documents stay at 26b446d9 unless the
citation names another commit. Owner answers OQ1 to OQ6 (PLAN.md s7) were recorded on
2026-10-01 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, as "efv2026 OQn"; option A to all
six) and bind this document. No
em-dashes. No statistic in this document, its code or its planned artifacts is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`).

---

## 0. What this gate registers, and what it does not

It registers a frozen frame, one transfer read and, conditionally, one surrogate read:

- **The frozen V 2026 frame** (s2.2), whose ONE long-run primary is W3 at RT 2031 (s6.3),
  with R3 at RT 2029 as a tilted arrival read (no alpha).
- **T, the transfer read** (s6.1), on OLD, SPENT, NON-RESERVED cohorts only: T1 asks whether
  an innovation-based composite of 2026-type MiLB outcomes is faithful to six-season value;
  T2 to T4 ask whether the S-only timing label g_S is channel-consistent, comparable across
  the 2021 ladder break and harmless as a TIMING-head auxiliary.
- **S4, the one read of lv_2026 against the composite** (s6.2), which exists only under
  owner answer OQ2 = B, runs only if T1 and T3 pass, never before R-VM look 2's record
  (OQ3 = A), and is read against its own tilt.

It does not register a claim frame for the Source Comparison headline. Nothing here moves a
served driver, a served weight or an admission decision. A T2 to T4 pass admits g_S only
as an auxiliary label for the timing head of a candidate in the 2027 label-epoch
registration; the flip is the owner's call there. Arrival outcomes never train
a skill slope (`DRIVER_SYSTEM_V2.md` principle 4). The copy is whatever the reserved read
of `EFV_V2_GATE.md` (2026-10-08, decision EW2-6, with the ship and copy rule of EW2-7; that
document's s11) and its successors leave it; nothing here changes it.

**Honest prior, recorded so this gate cannot be read as promising anything.** Level and
arrival rungs read rho 0.187 / 0.150 (AA2) and 0.305 / 0.404 (R3) against L6 on
V 2011-2016 (`_finalpass_2026-09-24/efv2/E2_data_labels/DATA_LABELS.md:109-125`); T1 needs
0.50, and the innovation-based composite removes the pre-V rung that carries most of what
those rungs know, so its faithfulness is expected BELOW the absolute rungs'. Under full
surrogacy lv_2026 would be well powered (a floor-size surrogate lead maps to 0.003 to 0.010
long-run, finer than the R-LV floor); full surrogacy fails on the record (bypass share 57
to 92 percent; impossible for AA2, since consensus predicts L6 better than AA2 does), so no
surrogate-scale lead translates. If T1 passed, the multiplier would be at least 0.5. The
modal outcome of T1 is a fail; of T3, a STOP under its conservative CI rule; of T4,
"not shown harmful, unpowered". If S4 ever runs, a V2 lead is EXPECTED BY CONSTRUCTION and
uninformative; only a loss is informative. On T2(b), which tests signs on the TIMING target:
`level_rank` is expected to PASS (its slope on R3 given consensus is positive in 7 of 7
vintages, mean |t| 9.886, admitted) and `age_rel_level` is expected to FAIL, because its own
sign on R3 is unstable (-1 in 2018-2021, +1 in 2022-2024, mean |t| 2.34, not admitted), so
no split-wise sign agreement can hold for it. Since ANY (b) failure fails T for the
auxiliary route (s5 T2), this prior implies that T2 fails and the auxiliary route closes,
whatever T3 and T4 show. The round-2 prior cited the SKILL-target sign
(`level_rank` negative in 5 of 7 vintages), which T2 does not test (`data/xfv.json` meta
receipt `served_model.receipt.hit.timing.admission` at 64bf1bb3, lane copy
`snap/xfv_HEAD.json`; `data/xfv.json` changed since, s8.13).

---

## 1. Preconditions (all must hold before the status line changes)

| id | precondition | state at registration (2026-10-15, re-checked against HEAD e9fc3a3c) |
|---|---|---|
| Q1 | The ETA FanGraphs-blend look is recorded: `data/eta_eval.json` carries block `fg_blend_gate_2026_09_25` (`docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md` s6), recorded at be53132d (2026-09-30 19:22); and this lane's pre-look counts of that look's own outcome (V 2024 frame players who debuted in 2026, 63 / 72, and in 2025-26, 136 / 153, counted 2026-09-30 13:01 with no score joined) and the lv_2026 overlap (212 / 207) are disclosed in a dated addendum under ETA s8 (task SG_A, commit b912d0f243c2fe3ec80504ee534b0409264b4017) and in s8.11 | MET: record be53132d (block `fg_blend_gate_2026_09_25` with its decision; `efv_surrogate_guard.eta_look_recorded()` True at HEAD); addendum b912d0f2 (SG_A, 2026-10-08), an ancestor of HEAD |
| Q2 | The ten 2026 season files are frozen as a TRACKED copy `data/milb_season_frozen/2026/` equal row for row to the 2026-09-30 refetch, sha256-pinned in `data/efv_surrogate_pins_2026.json` with each level's last scheduled regular-season date; the 2026 sport-1 files reduced to their person-id sets (`mlb_event_ids_{hitting,pitching}.json`, no stat column) and pinned; the transfer seasons (2010 to 2019, 2021 to 2025; sport 1 as ids only) pinned by canonical content hash; pure-2026 level norms derived from the frozen copy in `data/milb_norms_2026_pure.json`; `.gitattributes` `-text` lines for every file this gate writes (s11) | MET (SG_1, a946cc73, 2026-10-09). Re-taken at registration: the ten frozen season files, the two event-id sets and the pure norms hash to their SG_1 pins on the working tree and on the git blob alike; the 200 transfer-season cells re-hash to their pins with 0 mismatches; the three `-text` lines are in `.gitattributes`; s11 carries the pins |
| Q3 | fWAR label freeze receipt with per-side coverage (`FWAR_LABEL_EPOCH_GATE.md` P1). The round-5 text also required the F-LV floors (EV-05, `data/efv_lv_floor.json`); they were never built, `EFV_V2_GATE.md` registered without them (s11.2 P2, waived by EW2-6), and no clause of this gate reads them (s4: measured floors are not a precondition of the status line; s9's draft-time floors scale the lv_dev E_cond floor), so this revision drops them | MET (the epoch's step Z entry, 2026-10-03, label `fwar@2026-10-02-0341299c20ec`; `FWAR_LABEL_EPOCH_GATE.md` part 9, commit 73850ecc; `EFV_V2_GATE.md` s11.2 P1) |
| Q4 | The surrogate guard exists and is tested: refuses R-LV for every sha before any sha check; refuses every read before this file is REGISTERED; enforces the frame schedule by purpose (s2.3); REFUSES, never drops, while any in-window 2025-or-later debutant lacks its owning look's record (s8.1); refuses any 2026 outcome before Q1's record; this gate's code never calls `guard_score_request`; look records read only from the files s2.3 names; no calendar day refused (Q7); `efv_vintage_frame.py` at the git blob s11 pins (09430d3b211c67a480b51aff0dbfb27d8f4ca669 at this commit, the blob SG_2's test pins; c9d5a29d4dfda710792b854b61983625e9c1367e at 64bf1bb3 and 26b446d9, before 6fd30aee and fc5b9cc0); the identity path imports no debut or MLB column (AST test) | MET. The guard (SG_2, 0d6e20a7) was amended to this revision at 88e81ff2 (2026-10-15): look 1 is read from `data/_labs/efv_v3/efv_v3_confirm.json` (`look_1_recorded`), looks 2 and 3 and the OQ6 release only from `data/efv_v2_gate.json`; `LOOK_DAYS` is empty and the reserved-read-day block is gone, so no calendar day is refused; the session-marker refusal stays. The builder is SG_3's (33db18fd). `efv_vintage_frame.py` reads blob 09430d3b at HEAD; `look_records()` at HEAD reads [rvm_look_1] |
| Q5 | The V 2026 rater freeze `data/efv_surrogate_frame_2026.json` exists, taken after Q1's record from the pre-epoch universe: SG_4 (before epoch step C) did not run, so the step A snapshot (`../_pre_epoch_fwar_2026-10/`, 3ae607a2) stands in, with the efv2026 lane's pre-step-A universe bundle for the inputs that snapshot lacks (orchestrator answer SG4B-Q1, 2026-10-14), and the freeze is taken from it after step Z (task SG_4B), with the provider `ewar_v2` and RESOLVED_THROUGH 2025 asserted for every label and `career_war` read it makes (HEAD's defaults have read `"fwar"`, `war_source.py:182`, and 2026, `efv_dataset.py:274`, since the epoch's steps D+U and F of 2026-10-03); recording the provider and the `career_war` basis it read; sha-pinned; re-freeze refused; the scored V2 object named exactly as s2.2; the zero-information twin's scores and the per-row head indices e_time and e_skill frozen beside it (s4); row and identity counts re-taken (s8.13) | MET (SG_4B, 27b53534; `frozen_by` SG_4B, frozen_at 2026-10-15T11:48:10Z): sha256 1c7823316b697dbbf107416379e54711bd1e10dc270a7db6c998ed268b9cf9b8; rows 590 / 617 and person ids 522 / 570 re-taken equal (s8.13, s11.1); the V2 fold object named as s2.2, sha256 5ebddd8d; the twin (seed 20260931) and e_time, e_skill frozen beside it; provider `ewar_v2` and RESOLVED_THROUGH 2025 asserted; `career_war` 2,698 rows (ewar_v2 2,563, bbref 135); re-freeze refused by the tool |
| Q6 | Owner answers OQ1 to OQ6 (PLAN.md s7) | MET (2026-10-01; option A to all six, `DECISIONS_FOR_OWNER.md` rows efv2026 OQ1 to OQ6), written into the header above, which `gate_header_records` reads |
| Q7 | The look runner (`tools/efv_surrogate_look.py`) refuses without this file's REGISTERED commit sha, pins inputs at start and end with the nightly idle, refuses a spent look, refuses in any session that runs another gate's look (a session rule, not a calendar day: owner decision EW3-5 of 2026-10-14 waived every look day and registered date, so the runner refuses no calendar date, and the eFV reserved-read day no longer exists, EW2-6 having taken that read on 2026-10-08), and writes the bootstrap SDs of every cell BEFORE it prints any point delta; its reporting path is tested on fixtures carrying None and NaN in every printed cell, and every look runs under the one-look crash protocol (tee first; on an exception after scoring began, STOP without rerunning, the look spent if marked, an owner question written; tasks SG_8, SG_9) | MET (c2e158b7, 2026-10-15): `tools/efv_surrogate_look.py` is built and has never run. It refuses without this file's REGISTERED commit sha (found at run time), a spent look (artifact key or crash marker), another gate's look session, a busy pipeline, a missing ETA record or a missing look-1 record; it refuses no calendar day; it prints every bootstrap SD before any point; its reporting path is tested on fixtures (`test_efv_surrogate_look.py`) |
| Q8 | R-VM look 1's record exists before S3, because T3's V 2022 rows include 2025 debutants inside the window and the guard refuses the read without it (s8.1); the record is `data/_labs/efv_v3/efv_v3_confirm.json`, which `EFV_V2_GATE.md` s11.1 names the look record for R-VM look 1 | MET (2026-10-08): `efv_v3_confirm.json` item EFV3_W3_SELECT_CONFIRM, role reserved, one_read, gate.sha e7931ce4, `gate.guards.r_vm_cohort_read` [2025] |
| Q9 | Input pins (s11) re-taken at registration; the fold scheme, the first scored vintage and the n each clause is read on written into s5, including whether the V-1 rung derivation of s3 passed its reproduction test or the registered fallback of s2.1 applies | MET at this commit: pins re-taken (s11); s5.1 written. The s3 derivation PASSED its reproduction test (SG_3, 33db18fd: `level_rank` reproduced on 2,122 of 2,122 hitter and 2,056 of 2,056 pitcher V 2015-2019 rows read inside the pinned store), so the s2.1 fallback does not apply |
| Q10 | Under OQ6 = A, the dated one-sentence amendment to `EFV_V2_GATE.md` s5 B9b (R-VM look 3's record releases, for the label reads of registered long-run frames only, the in-window debut cohorts no R-VM look owns) is committed by that document's own rules before this status line changes; under OQ6 = B nothing is owed here and both long-run reads stay deferred whole | MET (b2ed1107, 2026-10-15): the dated one-sentence B9b amendment in `EFV_V2_GATE.md`, committed alone while that file reads REGISTERED |

---

## 2. Frames

### 2.1 Transfer frames (spent; non-reserved; read only by T)

- **lv_dev_all.** F-LV (`efv_vintage_frame.build_frame`) on list vintages 2011 to 2019
  (`DEV_VINTAGES`): 5,962 rows, 2,720 players (1,363 hit / 1,357 pit; lane count
  `surr_work/surr_player_counts.json`). Label W3 and R3 on the frozen fWAR label (Q3). Rows
  at V 2011 to 2014 (786 hit / 719 pit, 1,505 of the 3,100 lv_L6 rows) carry NO MiLB block
  from `efv_dataset` (the season loop stops at 2014, `efv_dataset.py:971`; `:1057-1058`
  return None; `efv_v2_model.py:565-566` marks them `milb_unavailable`), so `level_rank`
  (V-1) and `age_rel_level` do not exist on them there. This gate does NOT read those two
  features from the frame for any vintage. It derives the V-1 rung and age-for-level itself
  (`rung_pre`, `age_pre`, s3) for EVERY frame vintage from the pinned season store on the
  outcome-blind id (seasons 2010 to 2025; the cache holds every sport and group from 2005,
  so 2010 is pinned for V 2011), with a test that reproduces `efv_dataset`'s primary-level
  rule (`:976-1013`: the highest rung at the 50 PA / 60 BF floor, else the most-exposed rung)
  on every V 2015-2019 row where the frame carries a `level_rank`. If that test fails on any
  row, the registered FALLBACK applies and is written into s5 at registration (Q9): T1 on
  V 2015-2016 only with a player-grouped 5-fold scheme (seed 20260930) and an inner
  player-grouped 5-fold for the penalty; T2's non-MiLB splits reduced to 2015-16 and
  2017-19; T3's old era V 2015-2019; T4's evaluation vintage V 2019 only (training up to
  V 2015). The fallback halves T1's player count and widens its half-width to about 0.06.
- **lv_L6.** Its subset V 2011 to 2016: 3,100 rows, 1,585 players (781 hitters, 804
  pitchers). Label L6, the six-season target percentile within (side, V). Late debuters whose
  L6 is censored at RT 2025 are KEPT at `efv_labels` `l6_censored_target` with weight
  `l6_weight` (the v1 training convention) WHEN THEY CARRY ONE, which `efv_labels` gives only
  to debuts in `DEBUT_YEARS` = 2011 to 2024 (`efv_dataset.py:315`,
  `range(2011, RESOLVED_THROUGH)`; `efv_labels.py:247-250`). Three groups carry NO L6 and
  leave T1: rows with status `reserved_vm` (a 2025-or-later debut: `efv_labels.py:228`,
  `:245-246`, which fire before the `DEBUT_YEARS` branch, so the F2 advance to RT 2026
  changes nothing here), `censored_never` rows (`efv_labels.py:161`, excluded from fit and
  score by the label module's own rule) and `identity_conflict` rows (`:219-220`). They are
  the latest arrivers and the still-active non-arrivers, so their exit is a SELECTION THAT
  TRUNCATES ARRIVAL: it is disclosed with counts per side and vintage on the T1 printout, and
  the rho on resolved (uncensored) rows alone is printed beside the primary. This gate never
  computes an L6 for a 2025-or-later debutant, not even after look 1 releases the debut
  event (T5 asserts it; B9b rule 2 and T5 forbid the MLB stat an L6 would need).
- **comparability.** V 2022 (652 hit / 615 pit rows) with R3 at RT 2025 on debut EVENTS
  through 2025 only; it reads S(2022) and R3 and nothing else. Its 73 / 76 rows of 2025-or-
  later debutants: a 2026 debut is outside the window (R3 = 0, a fact fixed by the end of
  2025, kept per B9b rule 1); a 2025 debut is inside the window and belongs to R-VM look 1,
  and the guard REFUSES the V 2022 read while look 1's record is absent (B9b rule 2,
  `EFV_V2_GATE.md:298-300`; s8.1), so T3 runs after Q8 (met 2026-10-08) and never with rows
  dropped. V 2023
  (630 / 643 rows; 105 / 120 R-VM-owned, 45 / 61 of them 2026 debuts inside the window) is
  read by NOTHING in this gate: its R3 at RT 2026 reads 2026 debut events that belong to
  R-VM look 2, and the round-2 "V 2023 joins T3 after S4" was a second T3 read with no
  decision rule (T3 has already gated S4 by then), a forking path, so it is dropped.
- Surrogate outcomes on these frames are season V outcomes of their own year (the S(V)
  analog of S(2026)), built from the pinned season store on the outcome-blind id.
  Seasons before 2021 keep short-season A (sportId 15) as its own rung between CPX and A,
  and EVERY component and norm that reads sportId 11 before 2021 drops the Mexican League
  first, by league name (`league == "MEX"`: 349 of the 1,627 hitter rows in the 2016 file,
  336 of 1,665 in 2019; `milb_history.league_norms` has no league filter, `:239-283`, so a
  MEX line would otherwise read as AAA in S1, S2, S3's norms and S4).

### 2.2 The prospective frame (fresh; long-run reads by s6.3; one surrogate read by s6.2 only under OQ2 = B)

- **lv_2026.** `build_frame(side, 2026)`: 590 hitter and 617 pitcher rows, one per player
  (counts from the universe snapshot of 2026-09-30 12:45; the identity split 1987b1b2 of
  2026-10-01 may move them by a handful of rows, s8.13, and SG_4 or SG_4B re-takes them). Window
  2026-01-01 to 2026-05-01, cut at an April debut; MiLB inputs through 2025; the
  outcome-blind person id (`efv_identity`, through 2025) exists for 453 and 454 rows; the
  record id stays on the row for audit only (`efv_vintage_frame.py:8-29`, `:217-223`,
  `:246-256`). Rows without a person id (137 / 163, 23.2 / 26.4 percent) take the
  ABSENT_IDENTITY code, are never dropped from the frame, and are EXCLUDED from the S_idx
  primary until a pre-V identity route exists (s3, s8.10). The 2026 coverage count on those
  rows that the round-2 draft printed here is a tabulation of a 2026 outcome by identity
  route; it lives in s8.9 with its provenance and is admitted under kill rule 3(i).
- **Raters, frozen at Q5 and never extended.** Each named exactly:
  - **V2 list-vintage fold V = 2026, eWAR v2 label, RT 2025, DS-08 draft weights
    (`data/efv_v2_assembly.json` at git blob 91b04fa861ec64e9c1978d4fad727fbc00a45fd9, its
    content at 64bf1bb3, 26b446d9 and the step A head 3ae607a2), heads refit per
    `EFV_V2_GATE.md` s4.5 on labelled F-LV vintages 2011-2019 with the 6 lv_2026 players on
    2017-2019 frames left out.** This is NOT the served V2 (the vm fit: hitter skill
    `tool_hit` only, pitchers consensus-only per the `data/xfv.json` receipt) and NOT the
    registered candidate P5 (weights re-derived once on the frozen fWAR label, c40c0dd0,
    2026-10-04; the file has carried them since, sha256
    35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823, the
    `EFV_V2_GATE.md` s11.2 P4 pin); the fWAR re-derivation is not applied to it. No lv_2026 read
    is therefore a result about the served or the registered eFV; it is a result about this
    named object. Its own sha and fold receipt are written into the freeze file.
  - eFV v1 forward-chained at decision years up to 2025.
  - In-window PROSPX consensus, MLB Pipeline and FanGraphs.
  - For arrival components only, descriptive, NOT prospective with respect to the ETA look
    (which scored the same forms against 2026 debut events of V 2024 rows, 212 / 207 of
    whose players sit here; recorded at be53132d, admitted under kill rule 3(ii)): the ETA
    shadow's CH40, arm A and arm B predictions and FanGraphs `eta_year` from the
    `fg_blend_gate_2026_09_25.live_shadow_2026` block (4,486 rows, one per player key,
    built "with inputs as of each listing date" and storing `level`, `on40`, `fg_eta_year`
    and `listing_date`; ETA s5). Its listing dates run 2026-01-01 to 2026-09-30 (by month:
    Jan 338, Feb 1,065, May 19, Jun 107, Jul 204, Aug 403, Sep 2,350; 1,403 rows before
    2026-05-01), so a row listed from May on carries an in-season 2026 level, 40-man status
    and FanGraphs ETA. A shadow row is JOINED only when its `listing_date` is before the
    frame row's own window end (`efv_vintage_frame.window_bounds`: before 2026-05-01 and
    before any April debut); otherwise the four ETA raters are None on that row and the row
    is counted. SG_4's tests and T5 assert it.
  - The served board is not point-in-time (v1 grades carry in-season 2026 stats; the served
    ETA is the FanGraphs-blend arm B on current inputs since 6c614289, with the org
    multipliers removed at c3916597), so only these reconstructed objects qualify.
- **Overlap, reported as counts only:** 754 of the 1,207 players also sit on a 2022-2025
  frame (V 2022: 52 / 53; V 2023: 117 / 121; V 2024: 212 / 207; V 2025: 354 / 367; key
  intersections of the lane's per-row file, s8.9); 6 on a 2017-2019 frame
  (`surr_work/surr_player_counts.json`); 79 / 94 rows are 2026 debutants (R-VM cohort 2026).

### 2.3 Reserved and excluded

- **R-LV** (V 2020, 2021; `efv_vintage_frame.RESERVED_LV`): never built by this gate, for
  any purpose, including overlap counts. The surrogate guard refuses R-LV for EVERY sha
  before it looks at any sha, and this gate's code never calls `guard_score_request`.
  (`EFV_V2_GATE.md` reads REGISTERED since e7931ce4, 2026-10-08, so `gate_sha_committed`
  accepts any 40-hex ancestor of HEAD whose tree carries that file marked REGISTERED,
  `efv_vintage_frame.py:156-172` at this commit, this gate's own commits included, and any
  of their shas would open `guard_score_request` if something handed it over; nothing here
  does. R-LV's one reserved read was taken that day by its own tool, and R-LV is spent
  (`EFV_V2_GATE.md` s11.1); SG_2 tests both fixture trees.)
- **Two kinds of read, kept apart.** SURROGATE reads (S3, S4) take season-V MiLB outcomes
  and, for a 2025-or-later debutant, the debut EVENT only, never an MLB stat. LONG-RUN LABEL
  reads (R3 at RT 2029 and W3 at RT 2031 on lv_2026, s6.3) read the debut event and MLB WAR
  through `efv_labels`, which today withholds every in-window 2025-or-later debut
  (`reserved_vm`, W3 None, `efv_labels.py:228-246`) and has no release keyed to a look
  record; SG_10 adds that release path by dated amendment before RT 2029. Both kinds
  REFUSE, never drop, while a row's owning look lacks its record (s8.1).
- **R-VM** (debut cohorts 2025 and later, `EFV_V2_GATE.md:61`), policy per B9b rule 2 and
  s8.1: a row whose 2025-or-later debut falls inside its frame's window leaves every read of
  this gate until the R-VM look that owns its cohort has its record; the guard refuses the
  read (`ReservedFrameError` with the count per cohort) while any such row lacks it. R-VM
  looks exist for the 2025, 2026 and 2027 cohorts only (RT 2026, 2027, 2028; PROG:142,
  :163, :355 "final boundary"; GATE:61-62), so the 2028 and 2029 cohorts, which R3 at RT
  2029 and W3 at RT 2031 contain, have no owning look. Look 1 was read on 2026-10-08
  (Q8; its `gate.guards.r_vm_cohort_read` is [2025]); looks 2 and 3 read career WAR at RT
  2027 and RT 2028, seasons not yet played, so they wait for data, the one wait decision
  EW3-5 keeps. Their release is owner question OQ6
  (A: at look 3's record, by the GATE amendment of Q10; B: a named successor registration,
  both long-run reads deferred whole and possibly never). This gate reads
  `EFV_V2_GATE.md:61` ("the 2025 debut cohort and later") as the reservation and PROG:142
  as the look schedule; OQ6 settles the gap between them for this gate's reads only.
- **The schedule the guard enforces** (`guard_surrogate_read(V, *, gate_sha, look_records,
  purpose)`, SG_2; a STOP line in a task spec is no longer the only thing between a read and
  a frame the plan says it never touches): purpose `transfer` opens V 2011-2019 at
  REGISTERED and V 2022 only with look 1's record, and refuses V 2023, 2024 and 2025 always
  (their arrival outcomes belong to the ETA gate and to R-VM) and V 2026 always; purpose
  `lv2026_surrogate` opens V 2026 only with look 2's record and only when this file's
  header records OQ2 = B; purpose `lv2026_long_run` opens V 2026 only with the records of
  looks 1, 2 and 3 and the OQ6 release; everything else refuses. `look_records` is read
  only from the record files `EFV_V2_GATE.md` names: for look 1,
  `data/_labs/efv_v3/efv_v3_confirm.json` (its s11.1; the file's `gate.sha` is e7931ce4 and
  its `gate.guards.r_vm_cohort_read` is [2025]); for looks 2 and 3 and the OQ6 release,
  `data/efv_v2_gate.json` (EV-13's record, absent today) unless that document names another
  file by then. Nothing else may claim a record. After
  a release the row returns with the debut EVENT as the top code and no MLB stat in the
  surrogate reads, and with its label in the long-run reads. What this gate reads on each
  frame: V 2022, S(2022) and R3 (RT 2025) after look 1; V 2023, V 2024 and V 2025, nothing
  at all; lv_2026, no outcome before look 2.
- **No FV-cell stratum anywhere.** Descriptive strata only: side, age, last level, draft or
  IFA, bonus band, parent club, source disagreement.

---

## 3. The outcomes (fixed here; season V of each frame, regular season only)

Rungs are `efv_dataset._LEVEL_RANK` (DSL 0, CPX 1, A 2, A+ 3, AA 4, AAA 5; `:317`), MLB 6,
never AP+'s `ap_level_rank`; seasons before 2021 keep short-season A (sportId 15) as its own
rung between CPX and A. Exposure floor 50 PA / 60 BF, else the most-exposed level
(`efv_dataset.py:976-1013`). MLB is the debut EVENT only: the builder reads sport-1 season
files through one function, `mlb_event_ids(season, group)`, which returns the set of person
ids with a regular-season sport-1 line in that season and nothing else; no sport-1 stat
column is ever read (T5), and for 2026 the id sets are the frozen `mlb_event_ids_*.json` of
Q2. A season with no affiliated or MLB line on the pre-V id codes ABSENT_KNOWN (a TJ record
in `data/tj_surgery.json`, person-keyed), ABSENT_IDENTITY (no pre-V id) or ABSENT_UNKNOWN;
ABSENT is never coded as the worst outcome without its sub-code. No store holds MiLB
postseason games, and none is read. Level-relative rates use PURE season norms from the
pinned files (Q2), never the current-year blend of `milb_history.league_norms` (`:285-306`),
and every norm and component that reads sportId 11 before 2021 drops `league == "MEX"`
rows first (s2.1).

**The V-1 state this gate derives itself (never read from the frame's MiLB block).** For
every frame row: `rung_pre` = the primary rung of season V-1 on the outcome-blind id from
the pinned store (the `efv_dataset` rule above); a first-year pro with no V-1 line takes his
entry rung from his first in-store season at or before V-1 (the `_pace_from_entry` lineage,
`efv_dataset.py:899-930`); a row with no in-store line at all is ABSENT-pre and takes the
within-(side, V) median rung with a flag that is NOT an S_idx input and is counted. `age_pre`
= age at season V-1 minus the median age of exposure-floor qualifiers at (season V-1,
rung_pre) in the pinned store, a within-store construct. A test reproduces `efv_dataset`'s
`level_rank` on every V 2015-2019 row where the frame carries one; the fallback of s2.1
applies if it fails.

| id | outcome | definition | in S_idx? |
|---|---|---|---|
| S1 | LEVEL_END | highest rung with exposure at the floor in season V, else the most-exposed rung; the MLB top code from `mlb_event_ids`; ABSENT codes | no (absolute rung; descriptive) |
| S2 | CLIMB | LEVEL_END(V) minus rung_pre, then RESIDUALIZED on rung_pre and age_pre with maps fixed on lv_L6 id-resolved rows (CLIMB is capped at 6 minus rung_pre, so an AAA row can climb at most 1 and raw CLIMB falls with the rung, the ceiling `DATA_LABELS.md:122-123` notes for AA2; e_time rises with the rung, so on raw CLIMB the ceiling alone would push e_time toward a LOSS by construction), then club-demeaned: minus a shrunken parent-club intercept fitted on lv_L6 by a function that takes the fitted club table as an argument; the club is the as-of org of s4, with unknown-org rows on the pooled intercept. eFV-native; AP+ is never read | yes (the innovation) |
| S3 | PERF | season-V rates at the primary rung against pure level norms, exposure-shrunk: hitters obp_rel, contact (minus k_rel), iso_rel; pitchers k_rel minus bb_rel; residualized on age_pre AND on rung_pre with maps fixed on lv_L6; the hitter scalar that e_skill (s7) and the S_idx ridge read is the equal-weight mean of the three columns after standardization within (side, V) on lv_L6; undefined for ABSENT and MLB-event rows, which take the within-(side, V) id-resolved mean (0 after standardization) with NO missing indicator (the ABSENT code and the MLB top code already enter through S5 and S2) | yes (residualized) |
| S4 | PT | PA (BF) over affiliated levels in season V over THAT season's own per-level full-season exposure among affiliated-league qualifiers (MEX excluded by league name before 2021), capped at 1, residualized on rung_pre and age_pre; pitchers also GS share; ABSENT gives 0 with its sub-code | yes (residualized) |
| S5 | STATUS | ACTIVE, ABSENT_KNOWN, ABSENT_IDENTITY, ABSENT_UNKNOWN. "Released" is not identifiable from one season (the BUST2 two-season rule) and is not coded | one ABSENT code among id-resolved rows; sub-codes descriptive |
| S_idx | the composite (T1's object; S4's primary) | per side, E[L6 percentile within (side, V) given S2, S3, S4 and the one ABSENT code], a ridge fitted on lv_L6 id-resolved rows, leave-one-vintage-out over V 2011-2016 for the faithfulness read (each fold's penalty by inner leave-one-vintage-out CV on its five training vintages, grid {1, 3, 10, 30, 100, 300, 1000}); the full six-vintage fit is the index applied to lv_2026. Under the s2.1 fallback: V 2015-2016 only, player-grouped 5-fold (seed 20260930) with an inner player-grouped 5-fold for the penalty, and the n written into s5 at registration. It contains NO rater input and NO pre-V state: no FV, tool grade, pick, bonus, age, protection status, absolute rung, rung_pre, age_pre or ABSENT_IDENTITY (rung_pre and age_pre enter only through the residualization of S2 to S4) | is the composite |
| g_S | the S-only timing label (T2 to T4's object). The round-2 draft called it g_time and gave it `level_rank`(V-1) and `age_rel_level` as inputs, which made T2(b) pass by construction for exactly the two drivers it tests | per side, E[R3 given S2, S3, S4, ABSENT], a penalized logistic fitted on lv_dev_all vintages with resolved R3, forward-chained, with NO pre-V input (rung_pre and age_pre enter only through the residualization of its inputs); the stage-B map of `surrogates.md` s3.2 for the TIMING head only. Its increment over E[R3 given rung_pre, age_pre] (a partial rho) is printed descriptively | separate object |

Set aside, not outcomes of this gate: November 40-man adds (already a V2 timing input,
DS-09); next-year consensus revision (agreement, not value); AFL and Futures Game
selection; "released" from one season.

---

## 4. The statistic and its intervals

- **Primary:** size-weighted within-(side, vintage) Spearman (`efv_v2_stat`, groups of at
  least 20 rows), each rater's OWN score against the outcome; on lv_2026 there is one
  vintage, so it is within side. Delta = within(rater) minus within(PROSPX consensus) on
  identical rows. V2 minus MLB Pipeline and V2 minus FanGraphs are reported beside it with
  the same machinery, descriptive.
- **Secondary:** pooled Spearman after the identical output map (`efv_v2_model.output_map`,
  as `EFV_V2_GATE.md` s3.3), reported beside the primary, never the claim alone.
- **Intervals:** paired bootstrap, B 2000, seed 20260930; resampled by player (the
  `source_backtest` resampler) and, as the binding sensitivity, by parent club at the
  listing date (about 40 rows per club). **The as-of org**, registered here because F-LV
  rows carry no org field (`efv_vintage_frame.py` has no `org` key) and
  `trades.canonical_org` (`trades.py:375`) only normalizes a team name: the `org` on the
  row's latest in-window board point (`points[].org`, the field
  `identity_audit.load_snapshot_orgs` reads, with the placeholder "Office of the
  Commissioner" treated as unknown), normalized by `canonical_org`; otherwise the last club
  in the MLB transaction feed dated before V-01-01 on the outcome-blind id; otherwise
  `org_unknown`, counted (the `eta_backtest.build_cohort` `org_unknown_at_V` pattern) and
  pooled into ONE pooled intercept for the S2 club term and one pseudo-club for the
  clustered bootstrap. No org dated at or after the row's window end is read (asserted), so
  a 2026 trade never enters lv_2026 and no 2026 org lands on a V 2011-2016 row. The claim
  on any cell is the one-sided 95 percent lower bound, printed beside the point; mde95 =
  1.645 x SD of the drawn deltas. Draft-time floors are sqrt(n) arithmetic (s9). Measured
  floors are NOT a precondition of the status line: the runner writes every cell's
  bootstrap SD before it prints any point delta (Q7), and the old-cohort analog floor for S4
  (the SD of rater-minus-consensus deltas against S_idx on lv_dev V 2017-2019, taken at S3)
  is filed as a dated amendment before S4.
- **Controls on every cell:** a zero-information V2 twin (driver columns permuted within
  vintage, permutation seed 20260931, its scores FROZEN at Q5 beside the V2 object so no
  refit of a 2026 object is needed in 2029 or 2031) and a 500-draw permutation null. The
  per-row head indices e_time and e_skill of the V2 fold object (its timing-head and
  skill-head scores, s7) are frozen at Q5 as well.

---

## 5. Clauses (frozen at this commit)

| clause | test | pass rule | governs |
|---|---|---|---|
| T1 faithfulness | rho(S_idx, L6 percentile) on lv_L6, per side, leave-one-vintage-out out-of-sample over V 2011-2016 (n 781 / 804 players when the s3 derivation of rung_pre and age_pre passes its reproduction test; under the s2.1 fallback V 2015-2016 only, player-grouped 5-fold; the derivation passed, so the fallback does not apply and the n is written in s5.1); rows with status reserved_vm, censored_never or identity_conflict carry no L6 and leave with counts per side and vintage (s2.1, a selection that truncates arrival, disclosed); the rho on resolved (uncensored) rows alone printed beside; W3 on lv_dev_all secondary | one-sided 95 percent lower bound at least 0.50 on L6, on BOTH sides | S4 only. A fail closes level and arrival surrogates as value proxies for eFV permanently (kill rule 7) |
| T2 channel | on g_S against Y = R3 for every timing-head candidate (`efv_v2_model.V2_TIMING_KEYS`, `V2_ABSENCE_KEY`, on_40man, nov_add): (a) partial rho(g_S, R3 given u_c) with lower bound above 0; (b) the sign of each driver's slope given u_c on g_S equals its sign on R3, pooled and in each split where the driver exists (MiLB drivers: 2015-16 and 2017-19; others: 2011-13, 2014-16, 2017-19; under the s2.1 fallback 2015-16 and 2017-19 for every driver). `V2_ABSENCE_KEY` (`milb_absent`, `efv_v2_model.py:659`) is a MiLB driver here: `efv_v2_model.v2_row` sets it to 1.0 on every row with no MiLB block (`:721-733`), so it is the CONSTANT 1.0 on every V 2011-2014 row and carries no variation there. Handling, registered now: for every MiLB driver, `V2_ABSENCE_KEY` included, (a), (b) and (c) are scored ONLY on V 2015-2019 rows, so its pooled (b) is the V 2015-2019 pool and its splits are 2015-16 and 2017-19; its slope is never estimated on, and its (b) is never failed by, the V 2011-2014 rows, which stay in g_S's own fit and in the non-MiLB drivers' reads. A driver constant within a scored split is a registration error: the runner checks every driver's variance per scored split BEFORE it reads any outcome and STOPs there (no look is spent), and the handling of that driver goes to a dated amendment written from the variance check alone; (c) the ratio of the driver's UNSTANDARDIZED slope given u_c on g_S (a probability, calibrated on its training vintages) to its slope on R3 (0/1, a linear-probability fit), both on the probability scale, lies in [0.5, 2.0]: the band is centred at 1 for a channel-consistent driver, because R3 minus g_S is then uncorrelated with the driver given u_c (the round-2 band on standardized slopes of within-(side, V) percentiles was centred near 1/rho(g, R3), about 1.8 to 2.2 with a binary R3, and would have failed a valid g); (d) the bypass share 1 - rho(u_c, g_S) rho(g_S, Y) / rho(u_c, Y) is printed per side. The skill-head version (g_skill against W3) is printed descriptively only; S_idx and g_S never enter a skill head. Prior (s0): `level_rank` expected to pass (b), `age_rel_level` expected to fail (b) | (a), (b) and (c) hold for every driver. ANY (b) or (c) failure fails T for the auxiliary route and bars that driver from any head that reads g_S in 2027 | the 2027 timing auxiliary |
| T3 comparability | rho(g_S, R3) on V 2011-2019 (fallback: V 2015-2019) against V 2022 (R3 at RT 2025, after Q8; one row per player, sides pooled); no later vintage is added (V 2023 is not read, s2.1) | PASS iff the CI95 of the Fisher-z difference lies entirely inside (-0.10, +0.10); anything else is a STOP: S4 never runs, the auxiliary route closes, and the lane may return only as a new registration disclosing this read. No re-basing after the read. S -> L6 comparability is ASSUMED and untestable until about RT 2031 | S4 and the auxiliary |
| T4 do no harm | the S-only regime emulated: for each evaluation vintage V in 2017-2019 (fallback: V 2019 only), R3 is masked on training vintages V-3 to V-1 (unresolved at RT V-1) and imputed by g_S fitted on vintages up to V-4 (2011-2013 for V 2017, 2011-2014 for V 2018, 2011-2015 for V 2019; usable because s3 derives rung_pre and age_pre on those vintages); the timing head trained on resolved plus imputed rows against the incumbent (resolved rows only, `lv_training_rows`); within statistic, E_cond; plus a permuted-S twin | HARM iff the one-sided 95 percent upper bound of (augmented minus incumbent) is below 0 or the point is below -0.005; otherwise "not shown harmful, unpowered" (mde95 0.0155 on lv_dev is three times the effects in play, so T4 can fail but cannot certify). The real S beats its twin iff the one-sided 95 percent lower bound of (real minus twin) is above 0; otherwise g_S is regularisation only and is not admitted | the 2027 timing auxiliary |
| T5 hygiene | test-enforced, asserted in the runner before any score | no V 2020 or 2021 row built; in a SURROGATE read (S3, S4) no MLB stat of any row and no debut event of a 2025-or-later debutant before the owning look's record; in a LONG-RUN read (R3 at RT 2029, W3 at RT 2031) no label of a 2025-or-later debutant except through the release path of s6.3 with its record present; no L6 ever computed for a 2025-or-later debutant; no read before Q1's record; the identity module imports no debut or MLB column; ABSENT sub-codes present; ABSENT_IDENTITY out of the primary with its count; exposure floors applied; the frozen 2026 copy's sha256 equals the pin; sport-1 files read only through `mlb_event_ids` (no stat column); MEX rows dropped wherever sportId 11 before 2021 is read; no ETA shadow row joined with a listing date at or after the frame row's window end; no org dated at or after the window end; no FV-cell grouping (the `test_efv_vintage_frame.py` scan extended); AP+ never imported; `efv_vintage_frame.py` at the git blob s11 pins (`git rev-parse HEAD:./efv_vintage_frame.py`; never a working-tree sha256, which drifts with CRLF, s11) | every read |
| T6 multiplicity and transfer | surrogate-scale family: Holm m = 1 (S_idx); head-falsification family at S4: Holm m = 4 (e_time on residualized, club-demeaned CLIMB; e_skill on residualized PERF, the hitter scalar of s3; per side), one-sided in the direction of a LOSS, the e_time cell also printed within (side, rung_pre) strata as its sensitivity; long-run family: W3 at RT 2031 alone (m = 1), Bonferroni 0.025 each if a second endpoint is ever added by amendment; player- and club-clustered bootstrap, B 2000; the surrogate threshold effect (STE, Burzykowski and Buyse 2006) of the rater-level line, estimated on a registered family of large deliberate perturbations (plus or minus 0.03 and beyond), DESCRIPTIVE ONLY | no surrogate-scale result, whatever its size against the STE, permits any statement about long-run direction or value (s0.3, s6.2, H_S); the STE is printed as a description of the rater-level line and permits nothing | every read |

### 5.1 Registered at the REGISTERED commit (Q9): fold schemes, first scored vintage, n

- **The s3 derivation PASSED; the s2.1 fallback does not apply.** SG_3's test (33db18fd)
  reproduced `efv_dataset`'s `level_rank` on 2,122 of 2,122 hitter and 2,056 of 2,056
  pitcher V 2015-2019 rows read inside the pinned store. One V 2018 hitter row
  (adrian_hernandez), whose frame `level_rank` was read off a 2005 AAA line below the pinned
  store's 2010 floor, is ABSENT-pre here and is not counted as a reproduction failure (SG_3
  owner question OQ-SG3-2, default A applied). A row with no V-1 line takes the latest
  earlier in-store season as `rung_pre`, which is what the frame's `level_rank` reads (SG_3
  OQ-SG3-1, default A applied; option B, the first in-store season, would fail the
  reproduction and bring in the fallback). Every clause reads its primary scheme.
- **n, re-taken at registration as frame membership only** (`efv_vintage_frame.build_frame`
  rows and player keys per side on HEAD e9fc3a3c's universe; no grade, label or outcome read).
  The runner prints the n each statistic is read on, and the no-L6 exits, at the read.

| clause | fold scheme | first scored vintage | n (hit / pit) |
|---|---|---|---|
| T1 | leave-one-vintage-out over V 2011-2016, six outer folds; each fold's ridge penalty by inner leave-one-vintage-out on its five training vintages over the grid {1, 3, 10, 30, 100, 300, 1000} | V 2011 | lv_L6 3,100 rows (1,588 / 1,512), 781 / 804 players, before the exits of rows with no L6 (reserved_vm, censored_never, identity_conflict), counted per side and vintage at the read; W3 secondary on lv_dev_all 5,962 rows (3,053 / 2,909), 1,364 / 1,356 players (the draft's 1,363 / 1,357; 2,720 pooled either way) |
| T2 | g_S forward-chained over lv_dev_all V 2011-2019 rows with resolved R3, each vintage predicted by a fit on the earlier ones, its penalty by an inner forward-chained split on the same grid; V 2011 and 2012 carry no forward value (D10) | V 2013 for g_S; MiLB drivers, `V2_ABSENCE_KEY` included, V 2015 | MiLB drivers on V 2015-2019: 4,457 rows (2,267 / 2,190), 1,156 / 1,140 players; splits 2015-16 802 / 793 rows and 2017-19 1,465 / 1,397. Other drivers: splits 2011-13 526 / 474, 2014-16 1,062 / 1,038, 2017-19 1,465 / 1,397 rows |
| T3 | rho(g_S, R3) on V 2011-2019 (the forward g_S of T2) against V 2022 (the full g_S fit), one row per player, sides pooled; Fisher-z difference CI95 | V 2013 for the old era (V 2011 and 2012 carry no forward g_S, D10); V 2022 | V 2011-2019 frames 2,720 players before the forward-value and resolved-R3 restrictions, which the runner counts; V 2022 1,268 rows (655 / 613; the draft's 652 / 615 at the 2026-09-30 snapshot) |
| T4 | evaluation vintages V 2017, 2018 and 2019; R3 masked on V-3 to V-1 and imputed by g_S fitted on V 2011 to V-4 (2011-2013, 2011-2014, 2011-2015); incumbent on resolved rows only | V 2017 | evaluation rows 1,465 / 1,397 (V 2017 472 / 469, V 2018 450 / 439, V 2019 543 / 489) |
| T5 | asserted before any score | every read | every row the read builds |
| T6 | paired bootstrap B 2000, seed 20260930, by player and by as-of parent club; Holm m = 1 for S_idx; the head family (m = 4) belongs to S4, which does not run under the recorded OQ2 = A | as the clause read | as the clause read |

- **The builder's defaults, registered as part of the frozen specification** (SG_3,
  `efv_surrogate.py` blob 2853ba7c): D1 `rung_pre` for a row with no V-1 line is the latest
  earlier in-store season; D2 ABSENT-pre rows take the within-(side, V) median `rung_pre` and
  `age_pre` (flagged), and a missing store age takes the median `age_pre` (flagged); D3
  short-season A is rung 1.5; D4 S4's full-season exposure is the 0.9 quantile of the
  level's floor qualifiers' summed exposure in that season; D5 ABSENT_KNOWN when a
  `data/tj_surgery.json` record is dated V-1-01-01 to V-09-30; D6 a missing S2 or S4 takes
  the id-resolved (side, V) mean, as S3; D7 club intercepts shrink by n / (n + k),
  k = sigma2 / tau2 (method of moments); D8 residual maps carry one intercept per `rung_pre`
  value plus a common `age_pre` slope (OLS); D9 the transaction fallback for the as-of org is
  the last event before V-01-01 whose destination resolves to a parent club, and the board
  route reads the latest in-window point only; D10 the g_S penalty by an inner
  forward-chained split, V 2011 and 2012 getting no forward value; D11 the PERF norm falls
  back to the prior season's pure norm, else missing, with no static prior; D12 `age_pre`
  uses StatsAPI store ages on both sides (a within-store construct).

---

## 6. The reads

### 6.1 S3, the transfer read (T1 to T6)

Once, after this file is REGISTERED. Its other inputs exist: epoch step Z and the P1 freeze
receipt (Q3, 2026-10-03) and R-VM look 1's record (Q8, 2026-10-08). No calendar day blocks
it (decision EW3-5); it never runs in a session that runs another gate's look (Q7); nightly
idle, one process. Output
`data/efv_surrogate_gate.json` key `transfer`, with verbatim runner output copied into s12.
Reads old spent cohorts and V 2022 only (purpose `transfer`); computes no 2026 outcome of any
row; the guard refuses it, rather than dropping rows, while any V 2022 row with a 2025 debut
inside the window lacks look 1's record. If S_idx fails T1 on either side, level and arrival
surrogates are closed as value proxies for eFV permanently (kill rule 7) and S4 never runs.
If T3 is a STOP, S4 never runs and the auxiliary route closes. The old-cohort analog floor
for S4 is measured here and filed as a dated amendment (s4).

### 6.2 S4, the one read of lv_2026 (only under OQ2 = B)

Once, only if S3 passed T1 and T3 on both sides, only after Q1 (the ETA record), and not
before R-VM look 2 has its record (about 2027-10; OQ3 = A, B9b rule 2); purpose
`lv2026_surrogate`, which the guard opens only with that record and only when this file's
header records OQ2 = B. Outcomes S1..S5 and S_idx computed from the frozen 2026 files for
every lv_2026 row; every rater of s2.2 scored by s4 (the ETA raters only on rows whose
shadow row qualifies, s2.2); ABSENT_IDENTITY rows excluded from the primary with their count
and a worst-code / best-code bounds sensitivity; a sensitivity on the residual of S_idx after
regressing on rung_pre, age_pre and parent club; the e_time cell also within (side, rung_pre)
strata; the number of formerly withheld R-VM rows now carrying an event-only top code
reported. Output key `lv_2026`; one row appended to `data/efv_progress.json` for frame
`lv_2026_surrogate` with role `tilted`, the expected direction printed on the row (never
charted, never the headline; task SG_5). What it may say: "scored point-in-time with models
that never saw a 2026 outcome, the V2 fold object of s2.2 [led / tied / trailed] consensus at
anticipating S_idx by X (95 percent lower bound); a lead was expected by construction".
What it may not say: anything about long-run value or direction, about beating consensus or
the industry, about the served or registered eFV, or about the Source Comparison headline.
Nothing else is read after S4 (the round-2 "V 2023 joins T3" is dropped, s2.1).

### 6.3 Long-run reads of the frozen frame (label reads; each deferred whole until every release exists)

- **W3 at RT 2031, the single long-run primary.** On `data/efv_surrogate_frame_2026.json`,
  the raters, the twin and the head indices as frozen; W3 from `efv_labels` on the label
  series then in force (a label change under FWAR clause (l), disclosed, never claimed as
  accuracy). One-sided alpha 0.05, m = 1; the claim is the 95 percent lower bound; controls
  as `EFV_V2_GATE.md` s8. **H_W3, registered now:** within-side W3 Spearman of the s2.2 V2
  fold object minus PROSPX consensus on identical rows, one-sided 0.05, m = 1; V2 minus
  Pipeline and V2 minus FanGraphs reported beside, descriptive. W3 at RT 2031 is WAR over
  dy..dy+2 for debuts 2026 to 2029 (`efv_labels.py:15-17`), so it consists of MLB stats of
  R-VM-coded debutants, and it is read ONLY through a label path that releases a
  `reserved_vm` row on its cohort's look record: SG_10, a dated amendment to
  `efv_labels.labels_for` (a `release_records` argument that a row's cohort record must
  appear in, with its own test), filed before RT 2029, absent today (`efv_labels.py:236-238`,
  `:245-246`); released labels are read only by the registered runner with purpose
  `lv2026_long_run`, never by a served path (`efv_v2_model._check_years` stays). Release
  rule: every row is KEPT (B9b rule 1: dropping selects on the outcome); the WHOLE read is
  deferred until the 2026 cohort (look 2), the 2027 cohort (look 3) and the 2028 and 2029
  cohorts (OQ6: A, look 3's record under the Q10 amendment; B, a named successor
  registration, so the read may never run) all have their release; the deferral is disclosed
  with the count per cohort, and no row is read early. `withhold_reserved_vm` REFUSES inside
  this read; it never drops.
- **R3 at RT 2029, a tilted arrival read.** Role `tilted`, no alpha, descriptive: R3 is the
  timing head's own target and the label on which consensus plus age plus level beat
  consensus by +0.047 (I2 idea 3), so a V2 lead there is tilt, not value. R3 at RT 2029
  covers debuts 2026 to 2029 (`efv_labels.py:20`, `:229-231`) and takes the SAME whole-read
  deferral and release path as W3; `withhold_reserved_vm` refuses, never drops (a drop would
  be the selection B9b rule 1 names).
- No O'Brien-Fleming spending across horizons: the three reads are three families (s5 T6),
  not one comparison accruing information.

---

## 7. Hypotheses and decision rules

- **H_T1:** S_idx is faithful (T1). If it fails, level and arrival surrogates are closed as
  value proxies for eFV; the pins, the snapshot and the frozen frame stay.
- **H_T2-4:** g_S is channel-consistent, comparable and not shown harmful (T2 to T4). If it
  holds, g_S is admitted as an auxiliary label for the TIMING head only, as a candidate in
  the 2027 registration; if any of T2 to T4 fails, the auxiliary route closes.
- **H_S (only under OQ2 = B, only if H_T1 holds and T3 passed):** on lv_2026 the V2 fold
  object is not worse than PROSPX consensus at anticipating S_idx. Interpretation fixed
  here: a V2 lead is expected by construction and says nothing about value; the informative
  reads are the head-falsification family (s5 T6): a resolved e_time LOSS against consensus
  on residualized, club-demeaned CLIMB falsifies the timing head's carry-over to the
  post-2021 ladder; a resolved e_skill LOSS on residualized PERF (the hitter scalar of s3)
  falsifies the skill head's; the Prospect Promotion Incentive (2022 CBA) weakens the MLB
  top code as evidence either way. **Expected signs under NO carry-over failure, written
  before the family is frozen:** e_time (V2's timing-head index minus consensus, within
  side, on residualized CLIMB) about 0 to +0.02, because the residualization removes the
  rung and age content the timing head reads, leaving its reading of the V-1 state, expected
  weakly positive; e_skill (the skill-head index minus consensus on residualized PERF) about
  0 to +0.03, because the skill head reads stat readers that track production. A LOSS is a
  one-sided 95 percent upper bound of the delta below 0; on raw CLIMB the AAA ceiling alone
  would have produced one by construction (s3 S2), which is why CLIMB is residualized.
  Pre-committed consequence: a head with a resolved loss may not enter the 2027 registration
  unchanged; it is re-specified there with the change disclosed.
- **H_W3:** registered in s6.3 (the single long-run primary).
- **Holm:** m = 1 for S_idx; m = 4 for the head family; m = 1 for W3 at RT 2031.
- **What ships:** nothing. Neither pass nor fail changes `w_skill`, `w_time`, any admission
  decision, the served grade or the copy.
- **Kill rules.** (1) Frozen list: nothing added after commit. (2) One read per frame per
  look; no friendlier frame, estimator, seed or norm. (3) Early association: any
  association, tabulation or model fit between a 2026 season outcome of an lv_2026 row and
  any rater score (an s2.2 rater's or any other), a label, a model feature or a stratum (any
  descriptive cut of the rows, such as parent club, bonus band, draft or IFA route, last
  level, age band or source disagreement), computed by or for eFV before this file is
  REGISTERED, turns lv_2026 into development permanently and voids s6.2 and s6.3 as claims.
  Admitted BY NAME, and nothing else: (i) this lane's s8.9 counters, which are counts of
  2026 outcomes within (vintage, side) and within identity route (person id present or
  absent; record id present or absent), including the 123 / 121 conditional count and the
  overlap key intersections, with no score, label or model feature joined; vintage, side and
  identity route are the only strata admitted, and only for those counts; (ii) the ETA FanGraphs-blend
  look recorded at be53132d, which scored CH40, arm A and arm B against debut years through
  2026-09-27 of V 2024 rows, 212 / 207 of whose players sit on lv_2026, with the
  consequence s2.2 and s8.11 state (those raters' arrival components here are descriptive
  only; the V2, v1, consensus, Pipeline and FanGraphs raters were not scored by it). (4)
  Twin at or above V2: no result. (5) Stale or unpinned inputs void the run. (6) Any
  FV-cell stratum voids the run. (7) T1 fail closes level and arrival surrogates as value
  proxies for eFV permanently; they remain the ETA program's outcomes. (8) Identity: any
  post-V or MLB column in the identity path voids the read (bug B4). (9) T3 STOP: no
  re-basing, no second specification; a new registration only. (10) R-VM: any READ OF THIS
  GATE (an S3, S4, R3 or W3 read, s6) that scores a withheld row before its owning look's
  record turns lv_2026 into development permanently; the per-row flags of s8.9 are not a
  read of this gate and are admitted under rule 3(i).

---

## 8. Disclosures

1. **R-VM debut events on lv_2026 (OQ3 = A, recorded 2026-10-01: wait).** 2026 debuts of
   frame players (79 / 94 rows) are 2026-cohort members. Under B9b rule 2
   (`EFV_V2_GATE.md:298-300`) their
   rows leave every read of this gate until R-VM look 2's record; no one-season read runs
   before that, and the guard refuses a read that would need them rather than dropping them.
   After the record, the surrogate read takes their debut EVENT as the top code and no MLB
   stat; the long-run reads take their labels through the release path (s6.3). The label
   module is NO backstop: `efv_labels.py:230-231` FILLS R3 = 1.0 for an in-window reserved
   debut once V + 3 <= RT; status becomes `reserved_vm` only in the W3/W2 loop (`:236-238`)
   and the L6 branch (`:245-246`), so every R3 consumer depends on the guard (the round-2
   sentence "only sets status" misdescribed the code). Until 2026-10-08 no scored frame
   contained a 2025-or-later debut event; the R-VM look 1 read of that day scored the 2025
   cohort (`EFV_V2_GATE.md` s11.1), and every reserved-read artifact to this commit records
   `r_vm_cohort_read` [2025], so no read has scored a 2026-or-later debut. Had the owner
   chosen OQ3 = B, that would have been a dated
   amendment to `EFV_V2_GATE.md` B9b rule 2 and to `PROGRAM.md` s2.4's R-VM definition,
   committed BEFORE this draft, not a disclosure. Rows of 2025 and 2026 debutants on V 2022
   and 2023 frames follow s2.3.
2. **Partly spent outcomes.** The 2026-09-25 owner-asked lanes read forward MiLB ISO and
   promotion speed on the 2022-2023 lists with no reserved vintage (DECISIONS:298-306), so
   V 2022-2023 promotion outcomes are partly spent; T3 discloses it. The fresh hitter-lean
   test (2025 FanGraphs list vs 2025-26 ISO) is owner question OQ5: 354 of the 590 lv_2026
   hitters sit on the V 2025 frame, so run before REGISTERED it would associate S3's exact
   production outcome with a rater on most of lv_2026 and spend S4's production component;
   it excludes and counts every lv_2026 player in every mode except OQ5 = A with OQ2 = B
   after S4 or the lane's close (so under OQ2 = A, never included, even after REGISTERED),
   and s9 records it.
3. **F-WATCH.** `tools/xfv_promo_watch.py` froze a pitcher cohort in July with a 2028
   debut outcome; a 2026 debut read is a partial look at that frozen cohort, and it is
   disclosed as such.
4. **The AA2 read on record** used record ids (bug B4, an outcome proxy) and a subset
   (n 876 / 727); T re-measures it on outcome-blind ids.
5. **Design exposure.** V2 was specified in September 2026 by people who watched the 2026
   season; lv_2026 is prospective in data, not in design. V 2027, frozen at 2027-05-01, is
   the first fully prospective vintage.
6. **The statistic** is the one `EFV_V2_GATE.md` s3.4 discloses as chosen after two spent
   reads that showed it favours eFV. The same disclosure applies here.
7. **Norms.** The served 2026 rel-rates read against a half-2025 norm until 2027-01-01;
   every read of this gate uses the pinned pure-2026 norms, so it does not reproduce the
   served values and does not try to.
8. **Postseason.** No store holds MiLB postseason games; outcomes are regular season by
   construction.
9. **This lane's own outcome flags and tabulations (counts only, sealed; admitted under
   kill rule 3(i)).** Before this draft, the lane's `facts2026.py` (sha256
   bfd644dcca2f9b102248af6048277f8cf676a14870ce233e593a43bba82b6447) wrote, on 2026-09-30
   at 13:01 (before the ETA look's first run at 17:59), `frame_rows_2022_2026.json` (sha256
   07f763170a0734699177edfdeba8118092b3753af868ec8ce3077eb0d0f8e028; 6,312 rows, one per
   (player, V) on V 2022-2026 frames, keyed by player_key, person id and record id, with
   boolean 2026 flags p_line, r_line, gl, prom_milb, il, rel, fortyman, debut26 and NO grade,
   score, label or feature) and `facts2026.json` (sha256
   fe6c264dd249bcd7081a19e49d6c4a5782014f161d1b14563fca73bc07ff76ac) with the counts
   tabulated in `facts_table.md` (sha256
   b1307246a9e08a5c3e118a5ca81d033f28f98c09a79ebfe7ca2a1610d7f63003, 13:06), reproduced in
   full below. Two further tabulations were computed FROM THE PER-ROW FILE on 2026-09-30
   during the round-2 revision (PLAN.md written 14:19) and were in view when ABSENT_IDENTITY
   was taken out of the S_idx primary (s3, s8.10): (a) among lv_2026 rows with no
   outcome-blind person id (137 hit / 163 pit), the number whose RECORD id carries a 2026
   MiLB line, 123 / 121 (filter V = 2026, pid absent, r_line true; recomputed identically on
   2026-10-01 by the lane's round-3 revision, the second and last load of the per-row file,
   whose provenance the SEAL paragraph below states), a coverage count by identity route that is also a tabulation of a 2026
   outcome on rows where V2's timing candidate `milb_absent` (`efv_v2_model.py:659`, `:731`)
   reads 1.0, which is why it is named here and not in s2.2; (b) the overlap of lv_2026
   player keys with the V 2022-2025 frames by vintage (52 / 53, 117 / 121, 212 / 207,
   354 / 367; 754 players in all), key intersections with no flag joined. No association
   with any score was computed. LOADS ON RECORD: the per-row file was loaded twice, both
   times by this lane and both read-only: on 2026-09-30 (round 2) for (a) and (b), and on
   2026-10-01 by the round-3 revision, which recomputed (a) and (b) with the same filters and
   got the same numbers. Both counts read only the per-row file's own fields (V, side,
   person id, record id, r_line, player key), and no grade, score, label or feature was
   joined to any of its rows at either load. Both revisions also read the `meta` receipt of
   the lane's `snap/xfv_HEAD.json` (the 64bf1bb3 `data/xfv.json`, cited in s0), a file that
   also carries the per-player grades (`by_player`, 9,509 keys); the record does not show
   whether that file and the per-row file were ever open in one process, so this document
   does not claim that either session held no grade file, and it records the round-3
   recompute as a second load of the per-row file, disclosed here. SEAL, from this revision
   on: NO further read of the four files is permitted, by any process, for any purpose,
   including a re-check of these counts; SG_0 step (0) copies them as bytes and compares
   sha256 values, which reads no content; they are never copied into the tree. Their origin is the session folder
   `scratchpad/efv2026/` (a Temp folder that can disappear with the session); SG_0 step (0)
   copies them, sha-verified, to the durable path outside git
   `C:/Users/noah/baseball-projects/_finalpass_2026-09-24/efv2026/sealed/` before this draft
   commits, and that path is the seal of record.

   The counts, `facts_table.md` verbatim (F-LV rows; "count only" marks a debut or MLB count;
   "a / b" is person id / record id unless the row says otherwise):

   | fact (count of F-LV rows) | 2022 hit | 2022 pit | 2023 hit | 2023 pit | 2024 hit | 2024 pit | 2025 hit | 2025 pit | 2026 hit | 2026 pit |
   |---|---|---|---|---|---|---|---|---|---|---|
   | **Frame and identity** | | | | | | | | | | |
   | rows (every row carries a consensus grade) | 652 | 615 | 630 | 643 | 645 | 612 | 655 | 653 | 590 | 617 |
   | record now in timeseries / debuts / inactive | 104 / 317 / 231 | 80 / 337 / 198 | 227 / 255 / 148 | 177 / 320 / 146 | 419 / 215 / 11 | 336 / 258 / 18 | 497 / 155 / 3 | 463 / 185 / 5 | 500 / 79 / 11 | 491 / 94 / 32 |
   | outcome-blind person id (efv_identity, through V-1) | 548 | 528 | 520 | 523 | 517 | 501 | 502 | 511 | 453 | 454 |
   | record mlbam_id present | 614 | 564 | 614 | 616 | 640 | 603 | 651 | 650 | 578 | 577 |
   | debuted before 2026-01-01 (count only) | 286 | 298 | 210 | 259 | 152 | 186 | 80 | 96 | 0 | 0 |
   | debut 2025 or 2026, R-VM-owned (count only) | 73 | 76 | 105 | 120 | 136 | 153 | 155 | 185 | 79 | 94 |
   | MLB debut in 2026 (count only) | 31 | 39 | 45 | 61 | 63 | 72 | 75 | 89 | 79 | 94 |
   | **2026 season lines (final RS), person id / record id** | | | | | | | | | | |
   | any 2026 MiLB line | 282 / 352 | 288 / 345 | 358 / 439 | 344 / 439 | 433 / 550 | 400 / 493 | 458 / 606 | 441 / 566 | 437 / 567 | 410 / 533 |
   | 2026 exposure at or above the eFV floor (50 PA / 60 BF) | 237 / 301 | 222 / 266 | 322 / 399 | 273 / 362 | 404 / 514 | 351 / 436 | 433 / 576 | 404 / 521 | 426 / 549 | 387 / 496 |
   | 2026 exposure 300+ PA / BF (person id) | 121 | 43 | 179 | 65 | 252 | 103 | 306 | 147 | 318 | 182 |
   | 2+ MiLB levels in 2026 | 102 / 133 | 110 / 136 | 148 / 190 | 132 / 180 | 196 / 252 | 185 / 234 | 225 / 297 | 220 / 286 | 237 / 281 | 224 / 298 |
   | reached AA or higher in 2026 (person id) | 269 | 273 | 315 | 313 | 337 | 340 | 314 | 337 | 239 | 291 |
   | reached AAA in 2026 (person id) | 221 | 237 | 234 | 260 | 239 | 258 | 191 | 228 | 121 | 175 |
   | any 2026 MLB line (count only) | 207 / 229 | 187 / 217 | 184 / 209 | 197 / 232 | 161 / 181 | 180 / 202 | 120 / 140 | 142 / 163 | 62 / 78 | 78 / 89 |
   | **Dated level path** | | | | | | | | | | |
   | 2026 game logs cached with 1+ MiLB game (start and end level, dates) | 352 | 341 | 440 | 437 | 550 | 492 | 606 | 565 | 563 | 530 |
   | first-game level differs from last-game level | 92 | 100 | 135 | 131 | 185 | 184 | 239 | 229 | 237 | 253 |
   | record level_changes: promotion within MiLB in 2026 | 141 | 116 | 215 | 165 | 300 | 229 | 388 | 294 | 369 | 341 |
   | record level_changes: demotion in 2026 | 121 | 134 | 151 | 184 | 170 | 202 | 142 | 199 | 92 | 159 |
   | record level_changes: promotion to MLB in 2026 (count only) | 27 | 25 | 18 | 20 | 16 | 14 | 5 | 7 | 3 | 2 |
   | **Level-relative performance (display fields)** | | | | | | | | | | |
   | record career_stats: a 2026 MiLB row | 313 | 295 | 411 | 399 | 530 | 474 | 594 | 558 | 567 | 532 |
   | headline statline 2026 MiLB with level_plus_pct | 252 | 224 | 343 | 312 | 456 | 392 | 526 | 477 | 514 | 474 |
   | current_season_statlines 2026 MiLB row with ops_plus_level or era_minus_level | 313 | 293 | 411 | 397 | 530 | 473 | 594 | 557 | 567 | 531 |
   | **Injured list** | | | | | | | | | | |
   | record injury_history: stint starting in 2026 | 205 | 225 | 221 | 262 | 262 | 303 | 269 | 314 | 223 | 272 |
   | ... of which 30+ IL days across 2026 stints | 95 | 108 | 113 | 134 | 131 | 160 | 134 | 153 | 106 | 138 |
   | DB il_history: 2026 stint (append-only since 2026-06-06) | 71 | 106 | 101 | 146 | 154 | 185 | 174 | 212 | 161 | 212 |
   | league feed IL placement, person id: full season / repo cache | 169 / 137 | 197 / 171 | 173 / 142 | 215 / 193 | 208 / 167 | 239 / 209 | 205 / 162 | 243 / 210 | 186 / 139 | 212 / 176 |
   | **Release, retirement, 40-man** | | | | | | | | | | |
   | DB player_transactions: released in 2026 (record) | 88 | 79 | 77 | 86 | 60 | 57 | 16 | 38 | 4 | 11 |
   | league feed released, person id: full / repo | 75 / 49 | 75 / 55 | 66 / 46 | 80 / 56 | 52 / 37 | 46 / 34 | 13 / 10 | 31 / 23 | 3 / 1 | 10 / 5 |
   | retired in 2026: DB (record) / feed full (person) | 1 / 1 | 3 / 3 | 3 / 3 | 4 / 4 | 3 / 3 | 1 / 1 | 2 / 2 | 3 / 3 | 0 / 0 | 4 / 4 |
   | contract selected or purchased in 2026 (40-man add): DB (record) | 37 | 39 | 34 | 41 | 48 | 42 | 47 | 46 | 46 | 43 |
   | same, league feed person id: full / repo | 35 / 21 | 33 / 24 | 28 / 17 | 31 / 25 | 42 / 25 | 33 / 26 | 40 / 25 | 39 / 25 | 41 / 28 | 36 / 22 |
   | on the 40-man now (roster_status 2026-09-27; includes MLB players) | 315 | 351 | 256 | 326 | 217 | 260 | 156 | 197 | 83 | 109 |
10. **Identity.** ABSENT_IDENTITY is a pre-V attribute (no affiliated line through V-1 on
    the outcome-blind resolver), 4 to 9 percent on V 2011-2016 and 23.2 / 26.4 percent on
    lv_2026, mostly recent signees; an old-cohort coefficient on it would price a different
    population, and V2 imputes no-block rows at the train mean while consensus grades them
    by scouting (the I2 fake-win pattern, `IDEAS.md:27-34`). So it is never an S_idx code,
    its rows are out of the primary, and a pre-V identity route for recent signees (an id
    carried by an acquisition record or list snapshot dated before V-01-01, balance-checked
    like `data/efv_identity_balance.json`) is registered as the only way to bring them in,
    by amendment before S4. ABSENT_KNOWN keys to the person-keyed TJ file only; IL history
    is record-keyed (B4) and sparse historically, so it is descriptive.
11. **The ETA look overlap.** The ETA gate's look, recorded at be53132d (2026-09-30 19:22;
    first run 17:59, crashed after every clause printed; rerun after 6ca2e8f4), scored CH40,
    arm A and arm B against 2026 debut events of V 2024 rows; 212 / 207 of those players sit
    on lv_2026, so the ETA raters' arrival components here are not prospective with respect
    to that look and ride as descriptive raters only, admitted under kill rule 3(ii). This
    lane counted V 2024 debuts BEFORE the look (2026: 63 / 72; 2025-26: 136 / 153;
    `facts2026.json`, 2026-09-30 13:01), with no score joined; ETA s8 carried no disclosure of
    those counts at HEAD 26b446d9, and task SG_A appended it as a dated addendum (commit
    b912d0f243c2fe3ec80504ee534b0409264b4017, 2026-10-08).
12. **The norm flip inside the epoch.** If `FWAR_LABEL_EPOCH_GATE.md` part 9 carries no
    step Z entry by 2026-12-20, the 2027-01-01 flip moves every served 2026 rel-rate inside
    the epoch window (v1, provisional, chips; not the V2 order); OQ4 A carries the owner's
    choice for that case, recorded in `STATUS.md`. The step Z entry was recorded on
    2026-10-03, so the case does not arise.
13. **Re-baseline.** The row, identity and overlap counts printed here were taken on the
    universe snapshot of 2026-09-30 12:45 (built 2026-09-27). Commit 1987b1b2 (2026-10-01
    00:25) split three merged debuted identities (jose_rodriguez, michael_massey,
    carlos_rodriguez) onto seven humans' keys (ids 679563, 800412, 836624, 695602, 677578)
    and stopped `consensus.build_timeseries` merging same-name rows; 87b3b999 then restored
    `data/xfv.json` to its pre-split content, so the receipt cited in s0 is the 64bf1bb3
    one. The counts may move by a handful of rows: SG_4B (SG_4 did not run before step C),
    from the step A snapshot and the universe bundle of Q5 after step Z, re-takes them with
    `build_frame`
    (read-only, never beside the monthly) and, on a mismatch of at most 10 rows and 10
    person ids per side that the split's own keys explain, records the difference, names
    the rows the split touched, and freezes the matched rows (the touched rows excluded and
    counted, a selection on an identity repair, not on an outcome); a larger or unexplained
    mismatch STOPs before the freeze file is written. The registration carries the re-taken
    and matched counts (Q9): 590 / 617 rows and 522 / 570 person ids per side, equal to
    s2.2 as amended by s11.1 (SG_4B, 27b53534, the freeze file's `counts` block); recount
    none; no row excluded (the one split-touched row, michael_massey__sa3037259, is frozen
    like any other).

---

## 9. Forking paths (the denominator every number here is read against)

- Inherited from `EFV_V2_GATE.md` s6: 275 logged probes (about 347 frame-level reads), the
  39 closed v1 arms, one R-LV exposure (B9a), 80 arms and 40 validity probes on the build,
  DS-16 (2 frames), the 2026-09-25 owner-asked lanes (21 outcome probes).
- The 2026-07-24 surrogate-label program (`docs/SURROGATE_LABEL_PROGRAM.md`;
  `data/xfv_surrogate_eval.json`, `_pit.json`): three arms per side (A_KM_baseline,
  B_surrogate, C_oracle), 6 arms, plus one same-day pitcher follow-up prototype, all NO-SHIP.
  WAR-based rather than MiLB-based, but surrogate-vs-label faithfulness reads on the same
  training population; the oracle-vs-KM analog cited in PLAN s2 E1 comes from them.
- This lane: 0 associations with any score, label or feature; outcome counts on V 2022-2026
  frame rows and per-row outcome flags with no grade joined, sealed; two TABULATIONS of 2026
  outcomes by identity route computed from the per-row file on 2026-09-30 (the 123 / 121
  conditional count and the overlap key intersections, s8.9), admitted under kill rule 3(i).
- The ETA FanGraphs-blend look (be53132d): one look, two arms, on V 2024 debut events through
  2026-09-27; 212 / 207 of its players sit on lv_2026 (s8.11), admitted under kill rule
  3(ii).
- Since 2026-10-08 (`EFV_V2_GATE.md` s11): the eFV v3 selection's evaluated steps
  (`data/_labs/efv_v3/efv_v3_select.json`), the reserved reads of R-LV and of R-VM look 1
  (the 2025 cohort) in `efv_v3_confirm.json`, and later re-reads of both spent frames by the
  eFV v4 and wave-2 labs under `data/_labs/` (each artifact's guards block records
  `r_vm_cohort_read` [2025], so none is recorded as reading a 2026-or-later debut cohort).
- The one MiLB surrogate faithfulness read on record: AA2 (E2), spent.
- Draft-time floors (sqrt(n) from the measured lv_dev floor 0.0155 E_cond at n 2,862, 1,753
  players): lv_2026 W3 pooled 0.0187 to 0.0239 at n 1,207, per side 0.0341 / 0.0334; the S4
  primary on id-resolved rows (about 907; 453 / 454 per side) 0.022 to 0.028 pooled and 0.039
  per side; T1 half-width 0.054 in rho near 0.5 per side on 781 / 804 players (all six
  vintages scored leave-one-out), about 0.06 under the s2.1 fallback; T3 difference SE about
  0.035 in z, so its CI rule passes only when the point difference is below about 0.03.
  Replaced by measured floors by dated amendment after S3 (s4).
- The fresh hitter-lean probe C6 (task SG_6, run once on 2026-10-19 under efv2026 OQ5 = A
  with OQ2 = A, after the REGISTERED commit baffcff7; not an early read, since its one
  precondition held). A DESCRIPTIVE probe, not a driver, not a ledger row and not a read of
  this gate, pre-declared at 9c4902ac (`data/_labs/hitter_lean_c6/PREDECLARED.md`, its row
  policy first in `PROBES.jsonl`). It is a SPENT read of the production component (forward
  MiLB ISO_rel over 2025 and 2026 on the pure norms) on the 244 rows whose lines it read
  (220 scored, 24 under 150 PA): FanGraphs 2025report hitters after 77 ABSENT_IDENTITY rows
  (42 of them lv_2026 by key), 275 lv_2026 players and 6 R-VM 2026 debutants left the rows,
  counted; 60 of the scored rows are 2025 debutants released by rvm_look_1 (no MLB stat
  read); 168 of the 220 sat on the 2024 list. No lv_2026 row was read. Primary LEAN
  coefficient (controls + TALL + LEAN) -0.087, CI95 -0.193 to +0.025: the predicted sign, not
  resolved, on a selected subset. Output `data/_labs/hitter_lean_c6/sg6_result.json`.

---

## 10. Sequence

| step | when | reads an outcome? |
|---|---|---|
| the sealed lane files copied to the durable path (SG_0 step 0) | DONE 2026-10-14, before this draft commits | no |
| this DRAFT commits alone; its test in the next commit | 2026-10-14, revised against the REGISTERED `EFV_V2_GATE.md` (EW2-6) and decision EW3-5 | no |
| Q1 the ETA look record (its own gate) | RECORDED, be53132d (2026-09-30) | ETA's, not eFV's |
| Q1 the ETA s8 addendum with this lane's pre-look counts (SG_A) | DONE b912d0f2 (2026-10-08) | no |
| Q2 frozen copy, pins, event-id sets, pure norms, snapshot, `-text` lines (SG_1) | DONE a946cc73 (2026-10-09) | no |
| Q3 the fWAR label freeze (the epoch's step Z entry) | DONE 2026-10-03 | no |
| Q4 guard, builder (SG_2, SG_3) | DONE 0d6e20a7 and 33db18fd; the record source and `blocked_day` amended to this revision at 88e81ff2 (2026-10-15) | no |
| ledger frames (SG_5) | DONE 82393b46 | no |
| Q5 the V 2026 rater freeze (SG_4B; SG_4 did not run before step C) | DONE 27b53534 (2026-10-15), from the step A snapshot and the universe bundle of Q5 | no |
| Q8 R-VM look 1's record (`EFV_V2_GATE.md` s11.1) | DONE 2026-10-08 | not this gate's |
| Q10 the GATE B9b amendment for the cohorts no look owns (OQ6 = A) | DONE b2ed1107 (2026-10-15) | no |
| Q7 the look runner `tools/efv_surrogate_look.py` (built and fixture-tested, never run) | DONE c2e158b7 (2026-10-15) | no |
| REGISTERED commit, alone, s12 empty | DONE 2026-10-15, this commit (Q1 to Q10 all held at HEAD e9fc3a3c); no calendar date | no |
| S3 transfer read | after the REGISTERED commit; no calendar day blocks it (EW3-5); never beside another gate's look | old cohorts and V 2022 only |
| S4 lv_2026 read (OQ2 = B only; void under the recorded OQ2 = A) | only if T1 and T3 pass; after Q1; after R-VM look 2's record, which needs the 2027 season | yes, once |
| SG_10 the `efv_labels` release path (dated amendment with its test) | after OQ6; before RT 2029 | no |
| R3 read (tilted) | RT 2029; whole, only after looks 2 and 3 and the OQ6 release | yes, once |
| W3 read (primary) | RT 2031; whole, only after looks 2 and 3 and the OQ6 release | yes, once |

---

## 11. Pins (taken at Q2 and Q5, re-taken at registration on 2026-10-15)

- `data/milb_season_frozen/2026/{hitting,pitching}_{11,12,13,14,16}.json` (tracked copies of
  the cache files, 2.3 MB in all): sha256 as listed below; rows hitting / pitching AAA 927 / 1,268,
  AA 830 / 1,044, A+ 837 / 1,090, A 979 / 1,328, Rookie 1,602 / 2,062; PA = BF per level
  171,799; 156,270; 151,429; 151,705; 163,736; the cache fetched 2026-09-27 15:50 local and
  identical to the 2026-09-30 refetch. Last scheduled regular-season dates (StatsAPI
  `seasons`, fetched 2026-09-30): AAA 09-20, AA 09-13, A+ and A 09-06, ACL and FCL 07-23,
  DSL 08-18. The gitignored cache is never read by this gate FOR SEASON 2026; other seasons
  are read from it with fetch=False after the canonical hash check below.
- `data/milb_season_frozen/2026/mlb_event_ids_{hitting,pitching}.json`: the sorted set of
  person ids with a regular-season sport-1 line in 2026, per group, sha256 as listed below. No
  sport-1 stat is copied into the tree (the 2026 sport-1 files hold MLB lines of the R-VM
  2026 cohort); the source cache files are pinned in the pins file by a canonical hash over
  their id column only, and the builder's MLB top code reads only these sets (s3).
- Transfer seasons 2010 to 2019 and 2021 to 2025 (2010 for rung_pre of V 2011), sportIds
  11-16 (15 where present) and sport 1 as ids only: canonical content hash (rows sorted by
  person id, sport, league; the field projection the builder reads: id, level or sport,
  league, pa, bf, ab, h, 2b, 3b, hr, bb, so, hbp, sf, ip, g, gs, age, avg, obp, slg, ops,
  era; `league_norms` reads obp, slg, avg, ops and era at `milb_history.py:258-275`, so they
  are in the hash) in `data/efv_surrogate_pins_2026.json` `transfer_seasons` (SG_1, 200 cells),
  re-computed at registration by `tools/milb_season_freeze.transfer_hashes` with fetching
  disabled: 200 of 200 equal, 0 mismatches; the builder verifies before use and reads with
  fetch=False.
- `data/milb_norms_2026_pure.json`: sha256
  493e5f0d30465d5d679031f50649b0c447ee40ddbacb328502e684c985fdeeb8 (derived from the frozen
  copy; equal to the pins file's `pure_norms_sha256`).
- `data/efv_surrogate_frame_2026.json`: sha256
  1c7823316b697dbbf107416379e54711bd1e10dc270a7db6c998ed268b9cf9b8 (rows_sha256
  45d4a81cd7d2fc46b1a5646a233fee893384b09f7c9edd76190c535e140dceac; `frozen_by` SG_4B,
  27b53534; the V2 fold object sha256
  5ebddd8dc88d92a2f370048fb470934ddfa55b82231d32c74217741ac7df9201); row counts 590 / 617 as re-taken
  (s8.13); the V2 fold object's own sha and fold receipt, the twin's scores and the head
  indices inside it; the provider and `career_war` basis it read.
- **Line endings.** `core.autocrlf` is true on the Windows tree, so a sha256 of a tracked
  TEXT file differs between the Windows working tree (CRLF) and the git blob or the Linux
  box: at 26b446d9 `efv_vintage_frame.py` read e7ce2bf6c2595d50ff2636d488881333a1c9a5295a351ff64d3636b75e7c4a5d
  in the tree and fc69897f88bb67ff2d8affbbed6193c6e67fcd298df18061b93e3ce25a315aba as the
  blob. Source files are therefore pinned by git BLOB id (`git rev-parse <commit>:./<path>`,
  or `git diff --quiet 64bf1bb3 -- <path>`): `efv_vintage_frame.py`
  c9d5a29d4dfda710792b854b61983625e9c1367e (identical at 64bf1bb3 and 26b446d9),
  `efv_v2_model.py` 41360330eca6bafa29c129889e7bd5d159d33f6b, `data/efv_v2_assembly.json`
  91b04fa861ec64e9c1978d4fad727fbc00a45fd9; `efv_surrogate.py` (new: no file of that name
  exists at 64bf1bb3 or 26b446d9, `git ls-files`) and `efv_surrogate_guard.py` by blob id at
  first commit. At this revision's commit the three read 09430d3b211c67a480b51aff0dbfb27d8f4ca669
  (changed by 6fd30aee and fc5b9cc0, the latter adding `guard_vm_request`, the R-VM leg of
  the 2026-10-08 read), cd6d142f1c4bb11607ca4c84f163bda5bfa4d570 and
  3c88265353f295e03620ac443ced507a7179cc5b (the P5 weights); every source pin is re-taken
  at registration. Every data file this gate writes gets a `-text` line in `.gitattributes`,
  after the `data/provisional_freeze/** -text` rule at `:7-9`: `data/milb_season_frozen/**`,
  `data/efv_surrogate_*.json`, `data/milb_norms_2026_pure.json`, so its sha256 is the same
  on every machine (the frozen season copies are single-line JSON, `milb_history.py:185`,
  and are unaffected either way).
- V2 at the draft: `efv_v2_model.py` sha256
  f83c94316b701cd59eeea4914cf5f910bbd0f558b891f788dbbee50d348a4d0e (identical in tree and
  blob); `data/efv_v2_assembly.json` 422fc5439253ad13d867320b00b634a178e62a8b291025326056377d6d4436ec
  is the sha256 of the CRLF WORKING-TREE file, the value `EFV_V2_GATE.md:274` pins as its
  draft-time pin (its blob content hashes to
  145cc8dec640c6803780654477f563f39cb64afea4012f40dea95ba089b71507): the weights the fold
  object of s2.2 uses, not a claim that it is the served or registered V2. `EFV_V2_GATE.md`
  s11.2 P4 re-took both pins at its registration (2026-10-08): `efv_v2_model.py` sha256
  3134c039922c463893c0930377d8b85f113f9e1f915137a47cd8537bb35b4929 and
  `data/efv_v2_assembly.json` sha256
  35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823 (the P5 weights). The
  fold object reads neither re-taken file.

- **Re-taken at registration (2026-10-15, HEAD e9fc3a3c).** Every `-text` data file
  below hashes the same on the working tree and on its git blob, and each equals its SG_1 or
  SG_4B pin:
  - `data/milb_season_frozen/2026/`: `hitting_11.json`
    fb60ec2f8d7444578433e3cecd82082961fd61354951e1384dab2af9d6a63d18, `hitting_12.json`
    722b7169bf299108e065d48e420f4cc79e92567f28e852067ac33b31850382f8, `hitting_13.json`
    2c9e81caeac5052cd0f4f5645944aee3029bf394704e6e08f8792e730f115b61, `hitting_14.json`
    59eff07517e39455e767ab952007b02c27790ee530d08f1e6a96a4ad3317783e, `hitting_16.json`
    8d1d073c2e19f0a36633438de19e904f0546786cb0b2fb9d87943b687a0e9dd1, `pitching_11.json`
    c0d1521cb1a1522dadeeff2898f2475d5af42cc5342e295aaa01cbf75ca41b12, `pitching_12.json`
    f293c38c190020f0633b267b3c0150f639a7763eaf84c7d2bf39cee82183e7d2, `pitching_13.json`
    cc6292d4f4594df70c2d2cf7fa0325706309aaff33c18d37199e8cdf2daa5699, `pitching_14.json`
    a392dad18f0ba8408210c060d372a2595c399caf4dfa19181ff948acccd25077, `pitching_16.json`
    5006d93457bccaff7b62cfca2563cbbb2636fb06df17ad83ec46a863f519e2e2.
  - `mlb_event_ids_hitting.json` (751 ids)
    8480bac986770205ab5499e364b8461d02ec054ba1b7539a9aa6ec74b05d0baf and
    `mlb_event_ids_pitching.json` (868 ids)
    e31c000f0f524500ed902573ff70c5d1e620d898b9cd2db7328cae31038ef57f.
  - `data/efv_surrogate_pins_2026.json`
    ffd6f2ae1df606235257d48c52e7ca4ddf3d7249772b925e44549753e5488af5; the norms and the
    frozen frame as above.
  - Source files by git blob id, each clean in the working tree: `efv_vintage_frame.py`
    09430d3b211c67a480b51aff0dbfb27d8f4ca669, `efv_v2_model.py`
    cd6d142f1c4bb11607ca4c84f163bda5bfa4d570, `data/efv_v2_assembly.json`
    3c88265353f295e03620ac443ced507a7179cc5b, `efv_surrogate.py`
    2853ba7c8e17a4ced1ccdb93959db34cf42f2e0c, `efv_surrogate_guard.py`
    ba45dff188a9b3ba9ba79ec96d88db3e6e017022, `tools/efv_surrogate_look.py`
    da07ae8123996cb0dd330f03f8378f64452a66fc. Recorded beside them for audit, not as pins:
    `tools/efv_surrogate_freeze_2026.py` 1cf5d99c5fb8243ec801c31de6ebdf44990cf67b,
    `tools/milb_season_freeze.py` c698b7a43ec4a6021f30528a9c8d8e4971fed399, `efv_labels.py`
    7ccfee59251ee49c769b79306b4e3933f81319aa, `efv_v2_stat.py`
    0a82e0de482c93cd5572fd913d8eac34eb135980, `efv_identity.py`
    04f8b15900b2de94c97aa2968171ec886675736b, `efv_dataset.py`
    59e9c32567d8f40c55ed51d9b3b85946b2df6490, `milb_history.py`
    fd9a9c0a44bb35ea202f5bd12af7e4bdbe5d7b48.
  - The fold object of s2.2 was fitted with the step A head's code (8a1c5b7f), whose blobs
    the freeze file records in its `code` block; S3 reads the transfer frames with the
    blobs pinned above.

### 11.1 Amendment, dated 2026-10-14 (SG4B-Q2 = A; made while this file reads DRAFT): s2.2 and s8.13 re-baselined to the step A head's identity counts

- **What moved and why.** The person-id counts this draft prints for lv_2026 (s2.2, the
  s8.9 table and s9: 453 / 454 of 590 / 617 rows) were taken at 64bf1bb3, before two
  registered pre-step-A changes to the outcome-blind resolver landed: d24a87d1 (2026-10-02
  21:31, the 2019 to 2025 draft classes fetched into `.cache/draft_history`, which
  `efv_identity.build_index` reads; with 64bf1bb3's code alone they move the counts to
  480 / 529) and 6fd30aee (2026-10-02, the resolver's side and recency tiebreaks:
  name_side 16 / 18, name_recency 26 / 23). SG_4B's rule (4) re-take on the identical
  590 / 617 rows (the same player-key sets, sha256-equal at 64bf1bb3 and 8a1c5b7f) with the
  step A head's code 8a1c5b7f resolves 522 / 570 person ids (+69 / +116). The identity split
  1987b1b2 touched 0 / 1 of those rows (michael_massey__sa3037259, id 695602), so the branch
  s8.13 pre-registered (a mismatch of at most 10 that the split's own keys explain) did not
  apply and the first run stopped at 'BLOCKER: SG_4B recount' (2026-10-14 13:47; nothing
  written; the count probes were membership counts only, no label read).
- **The owner's answer (SG4B-Q2 = A, 2026-10-14, DECISIONS_FOR_OWNER.md).** The 522 / 570
  are the step A head's own state and bind. From this amendment: s2.2 reads 522 and 570 rows
  with an outcome-blind person id (68 / 47 rows, 11.5 / 7.6 percent, take ABSENT_IDENTITY
  and are excluded from the S_idx primary as before); the s8.9 identity row for lv_2026
  reads 522 / 570; s8.13's re-take is against 522 / 570 (`tools/efv_surrogate_freeze_2026.py`,
  `S22_COUNTS`, with the draft's 453 / 454 kept beside it as `S22_COUNTS_AT_DRAFT`); and every
  row is frozen with the step A head resolver, no row excluded (the one split-touched row is
  frozen like any other). The s9 draft-time floor for the S4 id-resolved primary is restated
  for about 1,092 rows (522 / 570 per side) by the same sqrt(n) rule from the measured
  lv_dev floor: 0.020 to 0.025 pooled and 0.036 / 0.035 per side (s9's printed
  0.022 to 0.028 and 0.039 stay as the record of what was anticipated at about 907; all of
  them are replaced by measured floors after S3, s4). The row counts 590 / 617 hold; nothing
  else in this draft changes, and the freeze file records both count sets with the
  amendment's name.

### 11.2 Amendment, dated 2026-10-15 (task SG_8, before the S3 look; no outcome read): the runner read against this text

- **What moved and why.** SG_8 reviewed `tools/efv_surrogate_look.py` (blob da07ae81 at
  this file's REGISTERED commit) against s2 to s5 before its one look and found it reading
  the registered rules differently in eight places; 0e7295e4 and 1a00471c make each read
  as written here, and no clause, frame, statistic, threshold or decision rule changes.
  (1) T1 kept label rows of status "ok" only, which dropped every resolved never-reached
  row (L6 0.0) from lv_L6, and read the uncensored partial sum; it now reads
  `l6_censored_target` with `l6_weight` on every row that carries one (s2.1) and prints the
  no-L6 exits (reserved_vm, censored_never, identity_conflict, other) and the
  ABSENT_IDENTITY rows per side and vintage; (2) the W3 secondary of T1 runs; (3) T2's
  u_c is the within-(side, V) consensus percentile, not the raw grade; (4) T2 (a) for the
  MiLB drivers, `V2_ABSENCE_KEY` included, is read on V 2015-2019 rows only; (5) rows
  with no forward g_S (V 2011 and 2012, D10) leave T2 and T3 before T3 picks one row per
  player; (6) T4 is one within statistic per side over V 2017-2019 (E_cond), not one cell
  per vintage, and its incumbent trains on the rows resolved at RT V-1 only (it had been
  handed the true R3 of V-3 to V-1); (7) T5's static clauses are asserted before any
  outcome and its row clauses on the built rows; (8) the driver step attaches the V2
  sidecars (`efv_drivers.protection_for_frame`, `bmi_for_rows`, `pl_revision_for_rows`)
  as every V2 frame builder does, without which the driver-only variance check (Q7, s5
  T2) found `on_40man` and `nov_add` absent in all 12 protection splits; with them every
  driver varies in every scored split, so no driver goes to a variance amendment.
- **The session rule (Q7).** `efv_surrogate_guard.look_session_markers` counts another
  gate's look marker as an open session only when its recorded start falls on the run
  day. The DvM+ runner keeps its marker for good as its spent-look record (started
  2026-10-14T22:30Z, look recorded at f292a03a), so the guard had refused every later
  day, a calendar refusal Q7 does not register. A marker with no readable start still
  refuses.
- **Printed as not computed.** The skill-head version of T2 (g_skill against W3): s3
  registers no g_skill object (inputs, fit or scale), and building one at the read would
  be an unregistered estimator (kill rule 2).
- **The old-cohort analog floor for S4 (s4, s6.1).** Not measured at S3: S4 is void under
  the recorded OQ2 = A (the header; `guard_surrogate_read` refuses `lv2026_surrogate`), so
  the floor has no reader; a later amendment that reopens S4 must measure it first.
- **Pins.** Source blobs after these commits: `tools/efv_surrogate_look.py`
  5a076f1a46a3be5d20fadaedb9e926278a198c6d, `efv_surrogate_guard.py`
  f05c43d69ee03665397defe8e7b8d02c1fffdc13; every other pin of s11 is unchanged. The
  look itself pins its inputs at start and end (Q7).

---

## 12. Results

### 12.1 S3, the transfer read: run 2026-10-15 (task SG_8), an OWNER-WAIVED EARLY READ

- **The run.** One look, `python -u tools/efv_surrogate_look.py --look <task dir>`, teed
  from its first line; gate sha c39b052a (this file at s11.2, REGISTERED); look record
  `rvm_look_1`; marker `.cache/efv_surrogate/look_started.json` written 2026-10-15T20:05:11Z;
  result written to `data/efv_surrogate_gate.json` key `transfer` at 2026-10-15T20:06:53Z;
  input pins equal at start and end; no exception, so the crash protocol did not fire.
  B 2000, seed 20260930. The look is spent (the artifact key and the marker).
- **Early read.** efv2026 OQ1 placed this read after R-VM look 1 and not before 2026-12-01;
  owner decision EW3-5 (2026-10-14) waived every registered date, so it ran on 2026-10-15
  and is recorded as an OWNER-WAIVED EARLY READ (the receipt's `note`). The data it reads
  (V 2011-2019 and V 2022 frames, seasons through 2025, R-VM look 1's record) all existed.
- **Verbatim runner output:**

```text
gate docs/efv-v2/SURROGATE_2026_GATE.md REGISTERED at c39b052a45e06f59dd3b1d0cfb98f65fbac3e481; records ['rvm_look_1']; run day 2026-10-15 (no calendar day blocks, EW3-5)
T5 asserted: no V 2020 or 2021 row is built; V 2011-2019 and V 2022 only
T5 asserted: Q1's record (the ETA look) is present
T5 asserted: efv_vintage_frame.py at the s11 blob 09430d3b211c67a480b51aff0dbfb27d8f4ca669, clean
T5 asserted: the frozen 2026 copy and the event-id sets equal their sha256 pins
T5 asserted: no FV-cell grouping in the runner
T5 asserted: AP+ never imported
T1 EXITS (rows with no L6, and id-unresolved rows out of the primary), per side and vintage:
  hit V 2011: reserved_vm 0, censored_never 0, identity_conflict 0, other 0, absent_identity 2
  hit V 2012: reserved_vm 0, censored_never 0, identity_conflict 0, other 0, absent_identity 3
  hit V 2013: reserved_vm 0, censored_never 2, identity_conflict 0, other 0, absent_identity 8
  hit V 2014: reserved_vm 1, censored_never 1, identity_conflict 0, other 0, absent_identity 9
  hit V 2015: reserved_vm 1, censored_never 4, identity_conflict 0, other 0, absent_identity 12
  hit V 2016: reserved_vm 0, censored_never 4, identity_conflict 0, other 0, absent_identity 20
  pit V 2011: reserved_vm 0, censored_never 0, identity_conflict 0, other 0, absent_identity 3
  pit V 2012: reserved_vm 0, censored_never 3, identity_conflict 0, other 0, absent_identity 3
  pit V 2013: reserved_vm 0, censored_never 5, identity_conflict 0, other 0, absent_identity 8
  pit V 2014: reserved_vm 0, censored_never 3, identity_conflict 0, other 0, absent_identity 5
  pit V 2015: reserved_vm 0, censored_never 4, identity_conflict 0, other 0, absent_identity 13
  pit V 2016: reserved_vm 1, censored_never 6, identity_conflict 0, other 0, absent_identity 12
BOOTSTRAP SDs (every cell, before any point delta):
  T1|hit|L6: sd_player +0.0297 sd_club +0.0308 n 1521
  T1|hit|L6_resolved_only: sd_player NA sd_club NA n 1497
  T1|hit|W3_secondary: sd_player +0.0231 sd_club +0.0254 n 2890
  T1|pit|L6: sd_player +0.0279 sd_club +0.0306 n 1446
  T1|pit|L6_resolved_only: sd_player NA sd_club NA n 1437
  T1|pit|W3_secondary: sd_player +0.0215 sd_club +0.0189 n 2787
  T2a|hit|partial: sd_player +0.0199 sd_club NA n 2648
  T2a|hit|partial_V2015_2019: sd_player +0.0216 sd_club NA n 2137
  T2a|pit|partial: sd_player +0.0222 sd_club NA n 2586
  T2a|pit|partial_V2015_2019: sd_player +0.0241 sd_club NA n 2109
  T4|hit|aug_minus_inc: sd_player +0.0521 sd_club +0.0625 n 1465
  T4|hit|real_minus_twin: sd_player NA sd_club NA n 1465
  T4|pit|aug_minus_inc: sd_player NA sd_club NA n 1397
  T4|pit|real_minus_twin: sd_player NA sd_club NA n 1397
POINTS (one-sided 95 percent bounds beside each):
  T1|hit|L6: point +0.2332 lo95 +0.1833 hi95 +0.2809 lo95_club +0.1822 mde95 +0.0489
  T1|hit|L6_resolved_only: point +0.2378 lo95 NA hi95 NA lo95_club NA mde95 NA
  T1|hit|W3_secondary: point +0.1957 lo95 +0.1581 hi95 +0.2334 lo95_club +0.1530 mde95 +0.0379
  T1|pit|L6: point +0.2355 lo95 +0.1886 hi95 +0.2809 lo95_club +0.1822 mde95 +0.0460
  T1|pit|L6_resolved_only: point +0.2365 lo95 NA hi95 NA lo95_club NA mde95 NA
  T1|pit|W3_secondary: point +0.1772 lo95 +0.1433 hi95 +0.2144 lo95_club +0.1462 mde95 +0.0353
  T2a|hit|partial: point +0.2921 lo95 +0.2595 hi95 +0.3246 lo95_club NA mde95 +0.0327
  T2a|hit|partial_V2015_2019: point +0.2627 lo95 +0.2274 hi95 +0.2975 lo95_club NA mde95 +0.0355
  T2a|pit|partial: point +0.2594 lo95 +0.2232 hi95 +0.2965 lo95_club NA mde95 +0.0365
  T2a|pit|partial_V2015_2019: point +0.2112 lo95 +0.1714 hi95 +0.2510 lo95_club NA mde95 +0.0396
  T4|hit|aug_minus_inc: point -0.3424 lo95 -0.4249 hi95 -0.2574 lo95_club -0.4387 mde95 +0.0858
  T4|hit|real_minus_twin: point NA lo95 NA hi95 NA lo95_club NA mde95 NA
  T4|pit|aug_minus_inc: point NA lo95 NA hi95 NA lo95_club NA mde95 NA
  T4|pit|real_minus_twin: point NA lo95 NA hi95 NA lo95_club NA mde95 NA
DESCRIPTIVE (no verdict):
  T2 hit: n 2648, n V 2015-2019 2137, bypass share +0.6596, g_S increment over E[R3 | rung_pre, age_pre] (partial rho) +0.3748
  T2 pit: n 2586, n V 2015-2019 2109, bypass share +0.7046, g_S increment over E[R3 | rung_pre, age_pre] (partial rho) +0.3120
  T2 failed driver cells (27): hit:age_rel_level:pooled, hit:age_rel_level:2015-2016, hit:age_rel_level:2017-2019, hit:level_rank:pooled, hit:level_rank:2015-2016, hit:level_rank:2017-2019, hit:milb_absent:2015-2016, hit:on_40man:2011-2013, hit:on_40man:2014-2016, hit:on_40man:2017-2019, hit:nov_add:pooled, hit:nov_add:2011-2013, hit:nov_add:2014-2016, hit:nov_add:2017-2019, pit:age_rel_level:2015-2016, pit:level_rank:pooled, pit:level_rank:2015-2016, pit:level_rank:2017-2019, pit:milb_absent:pooled, pit:milb_absent:2017-2019, pit:on_40man:pooled, pit:on_40man:2011-2013, pit:on_40man:2014-2016, pit:on_40man:2017-2019, pit:nov_add:pooled, pit:nov_add:2011-2013, pit:nov_add:2014-2016
  T3: rho_old +0.3914 n 2555; rho_2022 +0.4506 n 1189; z_diff -0.0720 CI95 -0.1408 to -0.0031
  T4 hit: HARM; real beats twin False
  T4 pit: not shown harmful, unpowered; real beats twin False
  T2 skill-head version (g_skill against W3): NOT COMPUTED; s3 registers no g_skill object (no inputs, fit or scale), so none is built at the read (kill rule 2).
T1: FAIL
T2: FAIL (27 driver cells)
T3: STOP
T4: HARM
```

### 12.2 What the read decides (s5, s6.1, s7; nothing ships)

- **T1 FAIL on both sides.** rho(S_idx, L6 percentile), leave-one-vintage-out, reads
  +0.233 (one-sided 95 percent lower bound +0.183) for hitters on 1,521 rows and +0.236
  (+0.189) for pitchers on 1,446 rows, against the 0.50 floor; the club-clustered bounds
  agree (+0.182, +0.182). The no-L6 exits were 2 reserved_vm and 11 censored_never hitter
  rows and 1 and 21 pitcher rows, with 54 and 44 ABSENT_IDENTITY rows out of the primary;
  the resolved-only rho beside it reads +0.238 and +0.237. By kill rule 7, level and
  arrival surrogates are closed as value proxies for eFV permanently; they remain the ETA
  program's outcomes. S4 never runs (it was already void under OQ2 = A).
- **T2 FAIL.** (a) holds on every cell (partial rho lower bounds +0.227 and +0.171 on the
  MiLB rows, +0.260 and +0.223 on all rows); (b) or (c) fails in 27 of 34 driver cells,
  and every one of the five timing candidates fails at least one cell on each side, so all
  five are barred from any head that reads g_S in 2027. Against the s0 prior, `level_rank`
  FAILED (b) as well (hitters pooled: slope given u_c -0.0006 on g_S, +0.0464 on R3), and
  `age_rel_level` failed as expected. Bypass share +0.660 and +0.705.
- **T3 STOP.** rho(g_S, R3) +0.391 on V 2011-2019 (2,555 players) and +0.451 on V 2022
  (1,189 players); Fisher-z difference -0.072, CI95 -0.141 to -0.003, not inside
  (-0.10, +0.10). The auxiliary route closes; by kill rule 9 the lane may return only as a
  new registration disclosing this read.
- **T4.** Hitters HARM: augmented minus incumbent -0.342 (one-sided upper bound -0.257) on
  1,465 rows. Pitchers: no draw produced a defined within statistic for either delta (the
  cell prints NA), so the runner's "not shown harmful, unpowered" is a reading of an
  undefined cell, not evidence; the real-minus-twin delta is undefined on both sides, so g_S
  is not shown to beat its twin and is not admitted. The size of the hitter delta and the
  undefined pitcher cell were not diagnosed: any refit to look would be a second read of
  these frames (kill rule 2).
- **Disclosed gap.** The T2 (a) cells carry the player bootstrap only; the runner passes no
  club clusters there, so s4's club sensitivity is missing for (a). Every (a) lower bound
  is above 0 by at least +0.17, so it decides nothing.
- **What ships:** nothing (s7). The H_T1 and H_T2-4 routes are closed; the frozen V 2026
  frame and its long-run reads of s6.3 (W3 at RT 2031, R3 at RT 2029) are untouched.

### 12.3 Measured floors (dated amendment 2026-10-15, s4 and s9)

The draft-time floors of s9 are replaced by the measured ones (mde95 = 1.645 x the player
bootstrap SD): T1 0.049 hitters and 0.046 pitchers (s9 anticipated a half-width of 0.054);
the W3 secondary 0.038 and 0.035; T2 (a) 0.033 and 0.037 on all rows, 0.036 and 0.040 on
V 2015-2019; T3's SE in z 0.035 (s9: about 0.035); T4 0.086 for hitters (s9 cited the
lv_dev E_cond floor 0.0155) and undefined for pitchers. The old-cohort analog floor for S4
is not measured (s11.2: S4 is void under OQ2 = A).

# EFV_X2_REVEALED_PREFERENCE: results

Read 2026-10-15 under the registration `docs/efv-v2/EFV_X2_REVEALED_PREFERENCE.md`
(committed alone before any number, with amendment A1 also before any number). Artifact:
`data/_labs/efv_x2/efv_x2_revealed.json` (module `efv_x2_revealed.py` at commit 49f958e4,
frozen fWAR label `fwar@2026-10-02-0341299c20ec`, resolved through 2026). Development
frames only. Nothing served moved, and no outcome here can move anything served.

## The short answer

The club decisions we can see are, almost entirely, already priced into PROSPX consensus.
Out of 15 columns, one meets the registered CARRY rule (option usage), two LEAN (Rule 5
selection and trades), and twelve are NULL. All three positive readings are small, about
+0.002 to +0.004 of Spearman rho, well under the 0.017 to 0.030 floors a reserved-frame
claim needs (`docs/efv-v2/PROGRAM.md` s2.5), and with 32 readings about 1.6 intervals
would clear zero by chance alone. Adding all 15 at once makes the ranking worse on both frames (lv_dev
-0.0024, vm_dev -0.0270): a plain least-squares fit over many weak columns overfits. So
EFV_X3 should treat these as weak candidates under a penalty, not as a source of lift.

## What was measured

For each column, inside each fold, a straight-line fit on that fold's earlier training rows
says how much the column moves a player's outcome rank at a given consensus rank. The fold's
test rows are then ordered by consensus plus that adjustment. The reading is how much that
ordering beats consensus alone on the within (side, year) Spearman correlation with the
outcome, with a 95% interval from 2,000 player-level resamples (seed 20261019).

- lv_dev: list vintages 2017 to 2019, 2,862 rows (1,465 hitters, 1,397 pitchers, 1,753
  players), outcome W3 (WAR over the first three big-league seasons, 0 if no debut within
  three seasons). Consensus alone: within rho 0.1792 (hitters 0.1949, pitchers 0.1629).
- vm_dev: the vm2 vintage-matched frame, debut cohorts 2017 to 2023, 830 rows (406
  hitters, 424 pitchers), outcome the six-season label. Consensus alone: within rho 0.3814
  (hitters 0.3954, pitchers 0.3674).
- Liveness: with no column the method reproduces consensus exactly (delta 0.0 on every
  frame and side).

## Every column

Delta is the column's ordering minus consensus, within rho, both sides; CI95 in brackets.

| column | what it is | lv_dev | vm_dev | reading |
|---|---|---|---|---|
| x2_promos_per_season | promotions per season | -0.0027 [-0.0079, +0.0026] | -0.0115 [-0.0302, +0.0058] | NULL |
| x2_promo_age_rel | age at promotion vs level median | -0.0065 [-0.0126, -0.0005] | -0.0081 [-0.0197, +0.0026] | NULL |
| x2_midseason_jumps | in-season moves up | -0.0051 [-0.0114, +0.0012] | +0.0030 [-0.0187, +0.0225] | NULL |
| x2_skipped_levels | levels skipped | -0.0020 [-0.0058, +0.0012] | -0.0125 [-0.0273, +0.0011] | NULL |
| x2_add_before_elig | 40-man add before Rule 5 eligibility | -0.0018 [-0.0054, +0.0016] | +0.0021 [-0.0098, +0.0133] | NULL |
| x2_r5_protect | protected (+1) or exposed (-1) at last eligible draft | -0.0081 [-0.0124, -0.0041] | -0.0023 [-0.0123, +0.0069] | NULL |
| x2_r5_exposed_n | drafts left exposed | -0.0029 [-0.0096, +0.0037] | +0.0025 [-0.0110, +0.0166] | NULL |
| x2_r5_selected | taken in the major league phase | +0.0022 [-0.0018, +0.0074] | +0.0020 [-0.0086, +0.0117] | LEAN |
| x2_r5m_selected | taken in the minor league phase | -0.0002 [-0.0007, +0.0002] | -0.0020 [-0.0102, +0.0030] | NULL |
| x2_options | option transactions | +0.0036 [+0.0002, +0.0069] | +0.0037 [-0.0123, +0.0195] | CARRY |
| x2_release_events | releases, designations, outrights | -0.0013 [-0.0039, +0.0011] | -0.0019 [-0.0124, +0.0074] | NULL |
| x2_trades | times traded | +0.0024 [-0.0091, +0.0143] | +0.0017 [-0.0158, +0.0200] | LEAN |
| x2_trade_principal_mlb | main piece in a trade for a major leaguer | -0.0018 [-0.0060, +0.0025] | -0.0070 [-0.0222, +0.0081] | NULL |
| x2_nri_springs | big-league camp invitations | -0.0009 [-0.0076, +0.0056] | -0.0077 [-0.0261, +0.0104] | NULL |
| x2_bonus_vs_slot | signing bonus over slot | -0.0022 [-0.0079, +0.0032] | -0.0094 [-0.0222, +0.0025] | NULL |
| x2_all | all 15 together | -0.0024 [-0.0180, +0.0142] | -0.0270 [-0.0639, +0.0071] | NULL |

How to read the three non-null columns:

- Option usage (CARRY by the letter of the rule): the lift on lv_dev comes from pitchers
  (+0.0076, CI95 +0.0025 to +0.0129; hitters -0.0002). The fitted direction is negative in
  every fold of both frames: at the same consensus grade, a prospect who has already been
  optioned does worse. That fits the story that a club using options on a prospect is
  shuttling a fringe 40-man arm, not developing a core piece. On vm_dev the interval is
  wide and includes zero.
- Rule 5 selection (LEAN): only 23 lv_dev and 21 vm_dev rows carry it. Too rare to matter
  for most of the board.
- Trades (LEAN): hitters carry it on both frames (+0.0084 and +0.0064, intervals wide);
  the fitted direction is negative (a traded hitter does worse at the same grade).

Two columns read clearly NEGATIVE on lv_dev (Rule 5 protection -0.0081, age at promotion
-0.0065): the slope learned on earlier vintages did not hold on later ones. That is the
same instability that closed the 39-arm feature frontier.

## Coverage on the scored rows

| column family | lv_dev rows with a value | vm_dev rows with a value |
|---|---|---|
| promotion (age at promotion) | 2,652 (2,036) of 2,862 | 823 (808) of 830 |
| 40-man and Rule 5 | 2,682 to 2,710 | 827 to 830 |
| options, releases, trades, invitations | 2,710 | 830 |
| bonus over slot (2017 drafts on) | 425 | 324 |

Non-zero counts per column and per (side, year) are in the artifact (`coverage`).

## Honesty notes

1. No reserved frame was read: list vintages 2020 and 2021 and the 2025 and later debut
   cohorts never entered (guards in the builder and in `check_dev_folds`). No 2026 outcome
   or preseason-2026 list was read; that frame belongs to EFV_2026_HOLDOUT_READ (EW3-13).
2. Every value is dated strictly before the row's read; the latest input any row read is
   2023-04-26, for a read on 2023-04-29. A first run (same day, before the artifact was
   committed) let two inputs see the read's own year: a player's first MiLB season, used
   for Rule 5 eligibility, and a trade return's major league line in the trade season. Both
   were closed before the committed run. Four columns moved, no reading changed:
   x2_add_before_elig lv_dev -0.00158 to -0.00178, vm_dev +0.00203 to +0.00213;
   x2_r5_protect -0.00972 to -0.00813 and -0.00213 to -0.00232; x2_r5_exposed_n -0.00304
   to -0.00287 and +0.00243 to +0.00246; x2_trade_principal_mlb -0.00180 to -0.00183 and
   -0.00522 to -0.00695; the joint arm -0.00373 to -0.00238 and -0.02760 to -0.02695.
3. On vm_dev the player id is the matrix id, which a player tends to gain on reaching the
   majors (bug B4). Training rows without an id never enter a slope fit, so a missing id
   cannot pose as a signal; test rows are all debuted players and carry ids.
4. The 2023 Rule 5 draft is absent from the league feed; it uses 8 December as its draft day
   and its selections come from R5 and R5M codes only (amendment A1). No development read
   can depend on the 2023 draft except vm training rows read after it.
5. The value of a trade return in consensus terms was not measured: grading the returned
   players at the trade date needs their record ids, which are a debut proxy.
6. Big-league camp invitations for 2026: the invitee endpoint now returns empty 2026 lists,
   so the 2026 list is built from the feed's dated invitations (598 people). No
   development read reaches 2026.
7. Bonus over slot exists only for drafts from 2017 (the endpoint carries no money
   before), so it covers 425 lv_dev and 324 vm_dev rows.

## What this means for X3

EFV_X3_POOLED_MODEL can read all 15 columns from this module. The development evidence
says: keep x2_options, x2_r5_selected and x2_trades as candidates and expect each to be
worth at most a few thousandths of rho; give everything a penalty, because the joint
least-squares arm lost on both frames; and do not expect club decisions to supply the
margin over consensus. The graders already watch the same promotions, protections and
invitations.

No served number, flag, grade, copy or progress-ledger row changed.

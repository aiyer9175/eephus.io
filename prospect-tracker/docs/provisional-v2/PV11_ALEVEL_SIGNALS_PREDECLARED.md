# PV-11 pre-declaration: the A-level Statcast / signal_snapshots arm for provisional v2

Written 2026-10-02, with PV-06 (provisional_v2.py). Spec: the research bundle
_finalpass_2026-09-24/provisional/PROVISIONAL_V2.md, section 3 (signals table, row "A-level
Statcast, data/signal_snapshots": PENDING) and section 5 (PV-11).

State at writing: no code in this repository joins data/statcast_alevel_signals.json or any
file under data/signal_snapshots/ to a first-grade label (checked by grep on 2026-10-02:
no module reading either source also reads label-source snapshots). The A-level signals
exist for the 2026 season only, and their retention began 2026-09-25
(tools/snapshot_modern_signals.py). Nothing below may be computed before the dates it names.

## 1. Why it waits

The PG2 lane could not test these signals: historical Statcast covers AAA only, while the
pre-grade population is mostly DSL, CPX and A ball. The 2026 season is the first with A-level
signals, so the first trainable labels are the 2026 Oct anchor's, and they close with its
W12 window on 2027-10-15. A forward test needs a second season: the 2027 Oct anchor.

## 2. Dates (hard)

| Step | Not before | What |
|---|---|---|
| Train | 2027-10-15 (W12 of the 2026 Oct anchor closes) | fit FULL+ALV on the 2026 Oct anchor rows |
| Interim read | 2028-04-15 (W6 of the 2027 Oct anchor) | prints "window open until 2028-10-15"; no verdict |
| Verdict | 2028-10-15 (W12 of the 2027 Oct anchor) | the one read that may admit or reject the arm |

Looking at any label-joined statistic of the ALV group before its row's date disqualifies the
arm for that cycle; it is then re-declared for the next season.

## 3. The arm

- Base: the PV-06 served spec exactly (provisional_v2.FULL, the fixed PG2 LightGBM params,
  seed 7, one model per side, ANY-ungraded universe, label-dating repair, capture guard).
- Group ALV, added to FULL, from data/signal_snapshots/<season>/ only (never the live
  sidecars, which keep the latest season):
  - alevel_signals: whiff_share, whiff_z, fb_velo, velo_z, k_z, k_a_z, n_pitches;
  - zone_metrics (row of the player's feature-season primary level): whiff_pct,
    overall_contact_pct, z_contact_pct, o_swing_pct, z_swing_pct, zone_rate, pitches;
  - statcast_metrics (same level): contact_quality.avg_ev, contact_quality.p90_ev,
    contact_quality.hard_hit_pct, contact_quality.barrel_pct, contact_quality.xwoba_est,
    contact_quality.batted_balls; pitch_movement.stuff_baseline.avg_velo,
    pitch_movement.tracked_pitches.
  - Point in time: only the feature season's file (season y for the Oct anchor of y). The
    MiLB regular season is over before Oct 15, so a row of that season fetched later describes
    the same completed season; a row from any later season's file is never read.
  - Never read: the sabermetrics snapshot (it carries WAR columns), percentiles blocks, any
    WAR, any consensus-FV cell stratum (docs/PROSPECT_ANCHOR_GATE.md).
- Training rows: the 2026 Oct anchor (the only season with ALV); FULL is refit on the same rows
  so the comparison is paired on identical training data.
- Test rows: the 2027 Oct anchor universe, scored once at the verdict date.

## 4. Metrics and the admission rule

- Primary: T1 ANY W12. Secondary (reported, not gating): ANY W6, FG W12, MLBP W12; T2 FG and
  MLBP MAE against the PV-06 ridge.
- Statistics: AUC and AP of FULL+ALV against FULL, paired cluster bootstrap by player,
  B 1,000, seed 7, CI95 percentile; Brier raw and shifted reported, not gated.
- Admit only if both the AUC delta and the AP delta CI95 exclude 0 in the favourable direction
  on the primary. Otherwise reject and keep FULL; the result is recorded either way in
  data/provisional_v2_eval.json under a block named pv11_alevel.
- Coverage is reported: rows of the 2027 anchor with any ALV value, by level. If fewer than
  200 test rows carry ALV, the read is reported as underpowered and the arm is neither
  admitted nor rejected; it is re-declared for the 2028 anchor.

## 5. What it cannot change

The served provisional_v2 heads stay on FULL until the verdict admits ALV. No provisional
number feeds eFV (PROVISIONAL_V2.md section 3, hand-off). The served grade is unchanged.

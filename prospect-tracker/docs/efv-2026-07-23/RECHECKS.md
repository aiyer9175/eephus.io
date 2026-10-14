# Dated re-gate calendar (owner-approved 2026-07-23)

Session schedulers cannot span months; this file is the durable reminder.
Check it at the start of any model session on or after each date.

## 2026-11-15 - pWOBA xwOBA-blend re-gate (likely PASS)
The 2025 -> 2026 outcome pairs complete at season end (harness rule: outcome
season past Nov 15). Run: python tools/pwoba_blend_regate_lab.py (frozen arm
b=0.2, original criterion lo95 > 0, seed 20260715). Preview at 2026-07-23
pooled 931 pairs: gap +0.0107, lo95 +0.0016 - expected to clear. On PASS the
recorded production diff is hitter_export._join_pwoba (blend current-season
est_woba at 0.2 into w). Ledger: data/pwoba_blend_regate_eval.json, registry
pwoba_blend_regate.

## 2026-11-15 - bat-tracking arm B frozen re-run (closest-miss NULL)
Identical frozen protocol per tools/bat_tracking_lab.py header; the 2026
completion adds the missing outcome half of the 2025 -> 2026 fold. At
2026-07-23 arm B read lo95 -0.0009 vs the shipped fwdHEM+ incumbent. No
researcher degrees of freedom: re-run as-is, ship only on lo95 > 0. Savant
gotchas documented in the lab header (seasonStart/End required; csv=true
drops swing-path fields).

## 2026-11-15 - NEW ARMS registered 2026-07-23 (Will's-metrics program, run at the same sitting)
Registered in docs/wills-2026-07-23/GATES.md section W-NOV BEFORE any 2026-outcome
data was seen; bars inherit the parent registrations above; no runs before Nov 15.
- NOV-A (bat_tracking revival, new arm): the vendored Swing+ composite (per-season
  variant from data/swing_plus.json once W6 extends it) replaces the raw bat-tracking
  z-aggregates as the BT leg in both the pWOBA and fwdHEM+ arms. Rationale recorded at
  registration: Swing+ is a validated nonlinear composite of the same fields
  (next-half xwOBAcon r 0.65 vs 0.58 bat-speed-only); arm B's July miss was lo95 -0.0009.
- NOV-B (pwoba revival, new arm): pa_value-style k-blend of observed and swing-model
  xwOBA (k frozen at the vendored swing-plus artifact's fitted values: xwOBA k=250)
  as the est_woba leg, judged under the parent lo95 > 0 criterion.

## ~2027 season end - closed-lane unlock (resolved 2024 cohorts)
Standing from the governance program: every 2024-fold-keyed keep-alive
(E-STUFF trainable fold, K-prior-adjacent lanes stay CLOSED, model-class
sweeps) gets its next new information when 2024 debut cohorts resolve.

## ~2028 folds - sub-AAA Statcast as trained features
S-XLINE-4's validated-but-overlay-unshippable signals (A-ball whiff K-channel,
FB velo) enter eFV properly as trained features when today's A/CPX tracked
cohorts (2023+) resolve into the training matrix. Signal sidecar + frozen
coefficients preserved: statcast_alevel_export.py /
data/statcast_alevel_signals.json / efv_statcast_overlay.py (default-OFF).
Do NOT revive the grade overlay with a loosened ceiling (gate-tuning).

## 2026-10-14 - RESULTS of the 2026-11-15 re-gates (OWNER-WAIVED EARLY READS, appended by NOV15_REGATES)
Registered date 2026-11-15; run on 2026-10-14 under the owner's waiver of look days (EW3-5,
'we don't have to wait for anything') and the explicit season-complete override treating 2026
as complete as of 2026-10-01 (EW3-6; tools/plus_lab_harness.py PLUS_LAB_SEASON_COMPLETE_ASOF,
logged, written into each artifact; the Nov 15 default is unchanged). The 2026 regular season
ended in late September and these labs read regular-season outcomes, so the 2025 -> 2026
pairs existed. Each lab ran once, after a dry run of its reporting path on fixtures with None
values, with stdout and stderr teed before anything else.

- pWOBA xwOBA-blend re-gate: PASS. Frozen arm b=0.2, original criterion, seed 20260715, 2000
  reps, registered pair set n 953 (the original 711 on predictor years 2022-2024, unchanged,
  plus 242 resolved 2025 -> 2026 pairs). output_blend rho 0.5271 vs fa_projection 0.5166
  (xwoba_alone 0.4948, gap_corrected 0.5214); gap v1 mean +0.0108 lo95 +0.0019 hi95 +0.0201;
  v2 companion mean +0.0110 lo95 +0.0024 (pass under both). Train stability check argmax
  matches the frozen b=0.2 / g=0.1. The unregistered 'partial-2026 preview' block of the
  artifact now holds the same 242 complete pairs (its pooled gate double-counts them) and is
  not verdict-bearing. Artifact data/pwoba_blend_regate_eval.json; registry row
  pwoba_blend_regate validated. The recorded production diff (hitter_export._join_pwoba: blend
  current-season est_woba at 0.2 into w) is a served change (plan Part 8 class 3): built behind
  EEPHUS_PWOBA_XWOBA_BLEND, default off, in its own commit; the owner flips it (owner question
  NOV15-PWOBA-FLIP). Nothing served moved here.

# eFV v5 COMBINED: results for the owner (2026-10-15)

Plain language. Every number is copied from `data/_labs/efv5/efv5_combined_fit.json` and
`data/_labs/efv5/efv5_combined_spent.json`; the method and the full tables are in
`docs/efv-v2/EFV_V5_COMBINED.md`. No em-dashes. Nothing here is cut by consensus-FV cell.

## The one-line answer

Every atlas driver was weighted together in one model, and the combination does not beat the served eFV
overall: pitchers gain, hitters lose more, and the pooled difference is below zero. eFV v5 COMBINED does
not ship; the served eFV (V2), the board, the grades and the dollars do not move; the honest claim is
still 'ties consensus'.

## What was built

One model per side with V2's anchor (the consensus order) and V2's registered head weights, in which
every candidate driver the atlas work produced is weighted at once:

- the 28 group drivers of the metric atlas (a statistic that switches on only inside its level, age
  band and role group), each held to the sign the atlas showed;
- the four tool-grade cells of the tool atlas (the slider projection gap of High-A pitchers, the
  fastball future grade of Triple-A pitchers), built as the same kind of group column;
- the 40 new-source columns eFV v4 offered (injured-list history, non-roster invitations,
  pitch-by-pitch discipline, batted balls, the population translation, the rater panel, the scouting
  report extraction), including the pitcher writer-minus-stated field v4 admitted;
- the five wave-2 scouting-grade columns of eFV v3;
- the tracking-era head for pitchers, at the weight its own registration fixed (0.5), on rows whose
  tracked season it never trained on (in the backtest, the 2025 debut cohort's 2024 season).

The weights were estimated jointly, by ridge regression with one shrinkage penalty per head chosen by
nested cross-validation inside each fold's own training years, so the fit could always fall back to
V2 (penalty infinity) when nothing helped. Standard errors sit beside every weight in the document.

## The table (within (side, list year) Spearman, pooled over sides)

| frame | n | v5 COMBINED | served eFV (V2) | consensus | v5c minus V2 | v5c minus consensus | role |
|---|---|---|---|---|---|---|---|
| list years 2017 to 2019 | 2,862 | 0.1685 | 0.1676 | 0.1792 | +0.0009 (-0.0179 to +0.0193) | -0.0107 (-0.0411 to +0.0183) | development, the penalty was chosen on it |
| debut cohorts 2017 to 2023 | 830 | 0.3611 | 0.3713 | 0.3814 | -0.0102 (-0.0306 to +0.0095) | -0.0203 (-0.0528 to +0.0127) | development, the penalty was chosen on it |
| list years 2020 and 2021 | 2,349 | 0.1479 | 0.1511 | 0.1494 | -0.0032 (E_refit -0.0369 to +0.0171) | -0.0015 (E_refit -0.0438 to +0.0218) | spent (held out; read once) |
| the 2025 debut cohort | 147 | 0.3451 | 0.3739 | 0.3333 | -0.0288 (E_refit -0.0744 to +0.0756) | +0.0118 (E_refit -0.0847 to +0.0912) | spent (held out; read once) |

By side, v5c minus V2: list years 2017 to 2019 hitters -0.0115, pitchers +0.0140; debut cohorts 2017 to 2023 hitters -0.0304, pitchers +0.0099; list years 2020 and 2021 hitters +0.0019, pitchers -0.0085; the 2025 debut cohort hitters -0.0486, pitchers -0.0098.

## Ship or not

The owner's rule (EW3-9): ship if the combined model beats served eFV pooled over the four frames by row
count and trails it by no more than 0.005 on either held-out frame. Pooled: -0.0028 over 6,188 rows (not above zero). Held-out: R-LV -0.0032, R-VM -0.0288 (one trails by more than 0.005). **Not.** `EFV_V5_COMBINED_ON` stays False; no served number moves. The two development rows on the Source Comparison page are drawn hollow, as development reads.

- Against consensus on list years 2020 and 2021: -0.0015 (E_refit CI95 [-0.0438, 0.0218]): a tie; the copy may not say beats consensus.
- Against consensus on the 2025 debut cohort: +0.0118 (E_refit CI95 [-0.0847, 0.0912]): a tie; the copy may not say beats consensus.

## Which drivers carried weight (the production fit, what the board would have served)

- hit skill head (lambda 1000.0; 19 non-zero of 28): tool_hit +0.162 (SE 0.040); w4p_pop_hit +0.104 (SE 0.019); w2s_game_pwr_hit +0.045 (SE 0.018); w2r_panel_hit +0.040 (SE 0.020); w2b_pull_h -0.020 (SE 0.020); w2p_swing_h -0.019 (SE 0.018); w2s_posval_hit +0.016 (SE 0.019); g5_hit_A_all_all_slg +0.013 (SE 0.013); .... Zero: g5_hit_A_all_all_k_pct, g5_hit_A_all_all_bb_minus_k, g5_hit_A_young_all_k_pct, g5_hit_A_young_all_bb_minus_k, g5_hit_CPX_all_all_avg, g5_hit_Ap_young_all_pbp_swstr, g5_hit_Ap_young_all_pbp_two_strike_contact, g5_hit_CPX_all_all_ops, g5_hit_CPX_all_all_woba.
- hit timing head (lambda 300.0; 8 non-zero of 16): level_rank +0.144 (SE 0.008); w2i_days_time_hit +0.006 (SE 0.001); w2i_open_time_hit +0.006 (SE 0.002); w2i_sixty_time_hit -0.005 (SE 0.002); w2n_nri_pre_hit +0.003 (SE 0.001); w2n_nri_count_pre_hit +0.002 (SE 0.001); w2i_stints_time_hit +0.001 (SE 0.001); w2i_recur_time_hit +0.001 (SE 0.001). Zero: g5_hit_A_all_all_age, g5_hit_A_young_all_age, rpt_conviction_hit, rpt_hedge_count_hit, rpt_risk_hit, rpt_approach_concern_hit, rpt_writer_minus_stated_hit, rpt_arrival_hit.
- pit skill head (lambda 1000.0; 24 non-zero of 27): w4p_pop_pit +0.081 (SE 0.016); w2s_cmd_pit +0.039 (SE 0.015); w2p_csw_p +0.038 (SE 0.015); w2b_pu_p -0.038 (SE 0.016); w2p_k_resid_p +0.033 (SE 0.015); w2s_brk_pit +0.027 (SE 0.016); t5_pit_Ap_all_all_sl_gap -0.026 (SE 0.016); w2i_days_skill_pit -0.025 (SE 0.013); .... Zero: g5_pit_A_all_all_k_minus_bb, g5_pit_A_young_all_k_minus_bb, t5_pit_Ap_young_all_sl_gap.
- pit timing head (lambda 100.0; 6 non-zero of 9): level_rank +0.006 (SE 0.000); w2n_nri_count_pre_pit -0.001 (SE 0.000); w2i_recur_time_pit +0.000 (SE 0.000); w2i_stints_time_pit +0.000 (SE 0.000); w2i_days_time_pit +0.000 (SE 0.000); w2n_nri_pre_pit +0.000 (SE 0.000). Zero: g5_pit_A_all_all_age, g5_pit_A_all_SP_age, rpt_arrival_pit.

Reading: the largest weights go to the population translation (a KATOH-style line translated to MLB
WAR) on both sides, the game-power and command and breaking-ball scouting grades, the rater panel for
hitters, and for pitchers the called-strike-plus-whiff rate, the K residual and the pop-up rate; most
atlas group drivers end near zero (the Single-A hitter batting lines keep small positive weights, the
Single-A starter strikeout rates small positive ones), and the report-extraction fields and every
complex-league column are zero. The pitcher timing head carries weight 0.020 and barely moves pitchers.

## Why it came out this way, in plain words

- Pitchers gained on the development frames (lv_dev +0.0140, vm_dev +0.0099), because the
  served eFV orders pitchers by consensus alone (no pitcher driver passed V2's admission rule), so any
  pitcher signal that holds its sign is a gain over it. The gain did not hold out: R-LV -0.0085
  (pit|2020 +0.0170, pit|2021 -0.0335; the 2021 list is the same fold where eFV v3's command grade and eFV v4's report field
  lost), and on R-VM the combined pitcher order alone read +0.0095 over V2 while the tracking-head
  blend (47 of 95 pitchers re-ordered at the registered 0.5) turned the pitcher side to -0.0098
  (n 75, E_refit CI95 -0.0921 to +0.0580).
- Hitters lost on three frames of four: lv_dev -0.0115, vm_dev -0.0304, R-LV +0.0019,
  R-VM -0.0486. The hitter head already carries the hit tool and the level reached; the added
  columns (the population translation, game power and the rater panel on the skill head, the
  injured-list and invitation columns on the timing head) move hitters away from the order that
  consensus and V2 agree on, and the frames say that costs more than it earns.
- The folds chose heavy shrinkage (lambda 300 to 1000 on the skill head, three vm_dev hitter folds
  infinity, which is V2 itself), and the atlas's reach-label signals ended at zero or near it; what
  weight survived went to the new-source columns v4 had already read one at a time, and their sum of
  small moves reads as noise against the WAR labels.
- The pooled difference over the four frames is below zero and R-VM trails by more than 0.005: the
  owner's rule fails on both of its parts.

## Questions recorded for the owner (defaults applied, nothing stopped)

1. The tracking head's flip (OWNER-Q TH-1 of EFV5_TRACKING_HEAD). This read adds a held-out datum on
   the long label: on the 2025 pitcher cohort the combined order alone read +0.0095 over V2 and
   -0.0098 with the head blended in (47 of 95 pitchers re-ordered; n 75; every interval spans zero).
   Default taken: the head's own flag untouched (its registration decides). Alternatives: (b) hold the
   flip until the 2024 cohort confirms, as TH-1 (b) says; (c) flip at the quarter weight.
2. The timing head's candidates. Default taken: every candidate at its registered head (the injured-list
   and invitation columns at the hitter timing head, where they took weight and where hitters lost).
   Alternative: a combined model with candidates on the skill head only, which is a new registration
   and a new read on a frame not yet read (none exists until the 2026 list vintage resolves).
3. The population translation column (the largest weight on both sides, +0.104 hitters, +0.081 pitchers,
   in consensus-percentile units, SE 0.019 and 0.016). Default taken: nothing; it stays a candidate.
   Alternative: a registered arm for the 2027 list-vintage frame (EW2-12 approved the population as a
   source), where the v4 single-step read (+0.0103 lv_dev, -0.0147 vm_dev) and this joint read can be
   confirmed or refused on unread rows.


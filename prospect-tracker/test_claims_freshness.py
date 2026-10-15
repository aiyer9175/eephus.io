# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Claims-freshness guards (2026-08-19): ARTIFACTS ARE THE SOURCE OF TRUTH.

copy_lint catches voice; this file catches CLAIM drift, in three layers:

1. PHRASE RATCHET: static claim fragments that were live and contradicted
   on 2026-08-19 may never return to a copy surface. Each fragment in
   BANNED_CLAIM_FRAGMENTS carries its own history.
2. GLOSSARY NUMBER CHECKS: the few glossary entries that legitimately
   hand-quote numbers are pinned to their artifacts via GLOSSARY_CLAIMS.
   Adding a check is one table line.
3. REGISTRY NOTE POLICY: rows whose eval artifacts regenerate nightly rot
   if their notes quote bare undated figures. Such notes must carry a
   dated reading marker ("YYYY-MM-DD reading:") no older than 45 days
   against the artifact's own generated date. One seeded stable-gate
   check pins fa_market's card guarantee figure to data/fa_gate2_eval.json.
4. CODE-CONSTANT PINS (Part 4) and the DISCOUNT RATE (Part 5): copy is held to
   the shipped constant it describes, and the Gate-2 note to the rate its own
   table was priced at.

Import-safe and deterministic: no network, no rebuilds, every file read
happens inside a test function.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Part 1: phrase ratchet.
# Every fragment below was a LIVE, artifact-contradicted static claim on
# 2026-08-19. A concurrent repair lane removed the occurrences; this ratchet
# is the guarantee they never return. Matching is case-insensitive substring.
BANNED_CLAIM_FRAGMENTS = (
    # SC_HEADLINE_HOLM (owner answers FP3-1, FP3-3, 2026-09-25). The Source
    # Comparison view said no floor covered the AUC leg and that no correction
    # for testing several sources was applied; both became false when the six
    # per-source cells became one Holm family with a floor per cell, and the
    # timing-pinned frame stopped being a candidate when it took the headline.
    "no floor is published for the auc leg",
    "no correction for testing several sources is applied",
    "becomes the headline once the owner has seen it",
    # glossary forward_gate said the Team Outlook forecast "is logged now";
    # nothing freezes it (data/mlb_projections.json is gitignored and rewritten
    # nightly, prospects.db keeps surplus only). M05-10, 2026-09-25.
    "the number is logged now",
    # glossary.js hero copy claimed eFV beat all public sources; the
    # vintage-matched head-to-head (2026-08-13) reads +0.0014 at 0.046x,
    # a tie. Copy may say "indistinguishable", never "better".
    "out-predicts every public source",
    # glossary.js source-comparison strings claimed an out-of-sample rank
    # win over consensus FV; B-L6 (2026-08-10) found the shipped win GONE
    # (NULL both estimators). The AUC_FLOOR_GATE contract bans the claim.
    "out-ranks consensus",
    # glossary.js methodology bullet claimed a clean per-archetype Spearman
    # sweep; the pooled comparison never cleared its own noise floor and
    # the rank-equivalence verdict is UNRESOLVED (must not be cited).
    "ahead on Spearman in every archetype",
    # glossary.js consensus copy claimed the pooled blend beats its best
    # single input; the hardened re-measurement (consensus_weight_eval,
    # ship=False) resolved no such gap.
    "beats its best individual",
    # glossary.json consensus_fv methodology carried the same claim in a
    # second wording, citing data/source_backtest.json past its verdict.
    "still beats the best single source",
    # older hero variant of fragment 1; already scrubbed before 2026-08-19,
    # ratcheted here so it cannot be reintroduced from stale drafts.
    "out-predicts the consensus",
    # glossary.js _methAccuracyChart opened with this as FIXED prose and then
    # printed MLB Pipeline ABOVE eFV in the same sentence: on
    # accuracy.pooled_efv_common_vintage_matched the artifact reads eFV 0.3983
    # against Pipeline 0.3990. Derived on 2026-09-04 (design audit F46) to the
    # same three branches _methHeroBanner already uses.
    "ahead of the field",
    # A-CLAIM-9, added 2026-09-06 as a FORWARD ban rather than a repair: none of
    # the five below has ever appeared on a surface, and the point is that they
    # never do.
    #
    # A Bayesian companion artifact is registered for this claim family, and the
    # moment one exists somebody will want to write the sentence it appears to
    # license: "there is an 85 percent probability that eFV is better than the
    # consensus". That is a posterior over a parameter, and a served surface
    # cannot carry it honestly, for two reasons that hold no matter how good the
    # posterior is.
    #
    # First, the number is only as good as its prior, and this platform has no
    # defensible prior on a rank-correlation gap: every prior it could pick is a
    # choice a reader cannot see and cannot argue with. Second, the whole claim
    # frame here is frequentist and pre-registered, with detection floors and an
    # alpha-spending clause, and mixing a posterior probability into copy written
    # against that frame invites a reader to read one as the other. The measured
    # position on 2026-09-06 is that THREE instruments put eFV and the consensus
    # apart by -0.0071, +0.0145 and -0.0001 and NONE of them resolves, which is
    # the sentence the page is entitled to.
    "probability that efv is better",
    "probability efv is better",
    "chance that efv is better",
    "posterior probability that efv",
    "odds that efv beats",
    # Census X01-02 (2026-09-24). glossary.js printed all three as fixed text on
    # the Source Comparison view while its hero, read off
    # accuracy.head_to_head_verdict, put eFV at 0.406 against consensus 0.413
    # (-0.007, floor 0.030, not resolvable). The first sat on a findings card
    # over the all-vintages frame; the second said eFV led the pooled comparison
    # by less than its floor, false on every published frame; the third
    # promised a lead the page does not measure.
    "best of every grader",
    "leads the pooled ordering",
    "the lead grows",
    # Census M03-04 (2026-09-24). The CollegeSavant pitcher Projections page
    # told readers strikeout rate carried the signal and walk rate washed out,
    # directly above a table that flagged K% (r2 0.03) and not BB% (r2 0.11);
    # the pitcher player-page note and the single_a_equivalent glossary
    # methodology said the same. On the 232 matched pairs pitcher K% ties the
    # predict-the-mean baseline (LOO MAE 4.013 against 3.995) while BB% beats
    # it (3.138 against 3.380). The trust copy is now generated from the eval;
    # the hitter prospects note also quoted a box K% r-squared of 0.47 against
    # a served 0.26.
    "strikeout rate carries the signal here",
    "k% is moderately reliable",
    "k% is the reliable output",
    "k% is the most reliable",
    "r-squared about 0.47",
    # Census X07-01 (2026-09-24). The riv_plus glossary methodology said RIV+
    # tracked relief free-agent pay at least as closely as REM+ (0.58 against
    # 0.51 over 271 name-matched signings). The 2026-09-18 re-gate
    # (data/riv_market_regate_eval.json B1_primary) read 0.5733 against 0.5665
    # on 232 matched signings, gap 0.0052 against an in-run MDE95 of 0.0862,
    # and deprecated the row. The copy now quotes that reading, pinned below.
    "at least as closely as rem+",
    # Census X07-07 (2026-09-24). The fv definition called FV the prospect's
    # projected MLB ceiling while its own methodology, and the FanGraphs scale
    # it maps onto, treat FV 50 as the likely outcome of an average regular.
    "projected mlb ceiling",
    # Census X07-02 (2026-09-24). The /sources/ lede and the glossary
    # attribution note said no source's reports were republished wholesale
    # while the served scout_reports chunks carry 27,461 full write-ups from
    # five sources. The copy now states what the payload carries; see
    # test_sources_copy_names_every_excerpted_report_source.
    "reports are republished wholesale",
    # Owner answer 2026-09-25 (census X07-02 option b): the payloads now serve
    # an excerpt of each report plus a source link (report_excerpt.py,
    # test_report_excerpt.py), so a surface saying the cards or the draft
    # board carry the full report text is wrong again, the other way round.
    "carries the full text of the scouting reports",
    "carry the full text of the scouting reports",
    "carries the full draft reports",
    # Census M06-04 (2026-09-25). The xHEM+ Blend column header on /mlbstats/
    # said it "Beats xwOBA alone on next-year offense out of sample" and the
    # fwdhem_plus glossary methodology said its gap floor sat above zero. The
    # 2026-09-18 re-gate of the SERVED column (data/xhem_served_regate_eval.json
    # A2, rung D4) read 0.4613 against 0.4543, lo95 -0.0012 (v1) and -0.0076
    # (v2), and demoted the row to provisional. The receipt now prints those.
    "beats xwoba alone",
    "gap floor above zero under the pre-registered convention",
    "incumbent forward column",
    # Census M06-01 (2026-09-25). The REM+ scorecard printed "market fit rho
    # 0.5157 vs AAV": the leverage-weighted lab variant on 271 name-matched
    # signings, under REM+'s name. It now prints REM+ on the re-gate's 232.
    "market fit &rho;",
    # RECON_13 (served-number reconciliation, 2026-10-01). RPR12: the eFV
    # example described the v1 ridge (translated walk and strikeout rates) on a
    # board that serves V2. RML06: RPS-Draft+ was called a z against the draft
    # class while draft_export scores fixed anchors (classes average about
    # 109). RML08: HEM+ and SEM+ were anchored on "qualified" players while the
    # code anchors on 50+ PA hitters and 20+ IP starters.
    "contact-and-discipline hitter consensus has at 45",
    "z(college performance vs class)",
    "100+15z vs the draft class",
    "average qualified hitter",
    "average qualified starter",
    # LIBRARY_13_REGISTRY_STALE_FIGURES (2026-10-03, lane finding F6). The
    # Library prints registry metric and notes verbatim. consensus_fv's metric
    # typed AUC 0.7254 vs 0.7130 and Spearman 0.2897 vs 0.2883 while
    # data/source_backtest.json accuracy.consensus_vs_inputs read AUC 0.734 vs
    # 0.7183 and Spearman 0.2836 vs 0.2855 on n 4,319; ewar's metric typed
    # 1,825 pairs while data/ewar_eval.json gate_2_pitcher_persistence.n_pairs
    # reads 1677; betting_game_prob's notes opened by saying the model grades
    # and loses while their newest dated reading (2026-10-01, n 777) has it
    # beating the home-field constant at t 3.371. The metrics now name the
    # artifact keys and the betting readings sit dated, newest first.
    "0.7254 vs 0.7130",
    "0.2897 vs 0.2883",
    "1,825 pairs",
    "it now grades for the first time and loses",
)

# The registry surfaces: data/model_registry.json and the two pages generated
# from it. They are scanned only for the fragments retired from registry prose
# (REGISTRY_RATCHET_FRAGMENTS), because older fragments in the main tuple
# still sit in other rows' dated history or in rows other lanes own.
REGISTRY_RATCHET_SURFACES = (
    "data/model_registry.json",
    "MODEL_REGISTRY.md",
    "models/index.html",
)
REGISTRY_RATCHET_FRAGMENTS = (
    "0.7254 vs 0.7130",
    "0.2897 vs 0.2883",
    "1,825 pairs",
    "it now grades for the first time and loses",
)

# Copy surfaces the ratchet scans. content/*.json is globbed at test time.
CLAIM_SURFACES = (
    "assets/glossary.js",
    "data/glossary.json",
    "index.html",
    "collegesavant/app.js",
    "collegesavant/pitcher_app.js",
    "build_site.py",
    "sources/index.html",
    "assets/mlbstats.js",
    "assets/mlbstats-league.js",
)

# ---------------------------------------------------------------------------
# Part 2: glossary entries that legitimately retain hand-quoted numbers,
# pinned to their artifacts. One line per check:
#   (entry_id, label, pattern, artifact_rel_path, keypath, tol_mode, tol)
# pattern: regex with ONE capture group, run with findall over the entry's
#   definition + methodology text; every match must agree with the artifact.
#   Zero matches fails loudly (the copy changed shape; update the table).
# tol_mode "abs": |claim - actual| <= tol.
# tol_mode "rel": |claim - actual| <= tol * |actual| (copy rounds).
GLOSSARY_CLAIMS = (
    # war_pa_plus quotes its own honest loss: forward Spearman 0.3711 for
    # the rate index vs 0.4058 for plain season WAR (v2 convention, hit
    # pool). Measured on eWAR since the lab's 2026-09-11 re-point (audit
    # F10-01); the batting side reads the same as bWAR, so these two did not
    # move. Tight abs tolerance: these are quoted to four decimals.
    ("war_pa_plus", "hit rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_pa_plus", "hit war_total baseline (v2)", r"predicts the same thing at (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
    # The pitcher entries and the three 3-year entries quote the same ledger and
    # were unpinned, which is how their bWAR-era figures (0.2688 / 0.0886 and
    # the 0.1335 window read) would have outlived the eWAR re-point that moved
    # them to 0.4726 / 0.2323 / 0.259. Pinned from 2026-09-11.
    ("war_ip_plus_sp", "SP rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_ip_plus_sp", "SP war_total baseline (v2)", r"plain season WAR \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
    ("war_ip_plus_sp", "SP rate baseline (v2)", r"unstandardized \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "results_by_convention", "v2", "rho_baselines", "rate"), "abs", 0.005),
    ("war_ip_plus_rp", "RP rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_ip_plus_rp", "RP war_total baseline (v2)", r"plain season WAR \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
    ("war_ip_plus_rp", "RP rate baseline (v2)", r"unstandardized \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "results_by_convention", "v2", "rho_baselines", "rate"), "abs", 0.005),
    ("war_pa_plus_3yr", "hit 3yr window rho (v2)", r"Spearman correlation of (0\.\d+) against",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "window_gate", "results_by_convention", "v2", "rho_window"), "abs", 0.005),
    ("war_pa_plus_3yr", "hit one-season rho (v2)", r"against (0\.\d+) for one season",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "window_gate", "results_by_convention", "v2", "rho_one_season"), "abs", 0.005),
    ("war_ip_plus_sp_3yr", "SP 3yr window rho (v2)", r"Spearman correlation of (0\.\d+) against",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "window_gate", "results_by_convention", "v2", "rho_window"), "abs", 0.005),
    ("war_ip_plus_sp_3yr", "SP one-season rho (v2)", r"against (0\.\d+) for one season",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "window_gate", "results_by_convention", "v2", "rho_one_season"), "abs", 0.005),
    ("war_ip_plus_rp_3yr", "RP 3yr window rho (v2)", r"Spearman correlation of (0\.\d+) against",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "window_gate", "results_by_convention", "v2", "rho_window"), "abs", 0.005),
    ("war_ip_plus_rp_3yr", "RP one-season rho (v2)", r"against (0\.\d+) for one season",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "window_gate", "results_by_convention", "v2", "rho_one_season"), "abs", 0.005),
    # milb_translation quotes its LOO validation block. MAE rows use a
    # relative 0.15 band (copy rounds 3.937 to ~4.0). r2 rows use abs 0.02:
    # loose enough for two-decimal rounding (0.32 vs 0.319 passes), tight
    # enough that the observed 0.35-vs-0.319 drift FAILS.
    # The copy phrases these as dated readings ("2026-08 fit: ..."), so the
    # patterns tolerate a date prefix and comma-separated (unparenthesised)
    # validation clauses.
    ("milb_translation", "hit_k r2 (definition)", r"reliable read \([^)]*r2 ~?(0\.\d+)\)",
     "data/milb_translation.json", ("validation", "hit_k", "r2"), "abs", 0.02),
    ("milb_translation", "hit_k LOO MAE", r"K% LOO MAE ~?(\d+\.?\d*)",
     "data/milb_translation.json", ("validation", "hit_k", "mae"), "rel", 0.15),
    ("milb_translation", "hit_k r2 (methodology)", r"K% LOO MAE [^;]*?r2 ~?(0\.\d+)",
     "data/milb_translation.json", ("validation", "hit_k", "r2"), "abs", 0.02),
    ("milb_translation", "hit_bb MAE", r"BB% MAE ~?(\d+\.?\d*)",
     "data/milb_translation.json", ("validation", "hit_bb", "mae"), "rel", 0.15),
    ("milb_translation", "hit_bb r2", r"BB% MAE [^;(]*?r2 ~?(0\.\d+)",
     "data/milb_translation.json", ("validation", "hit_bb", "r2"), "abs", 0.02),
    # ewar quotes its gate record (eWAR epoch 2026-09-03). The four numbers
    # are the basis-decision record: the descriptive loss and the persistence
    # gain must always be printed together, so both sides of each are pinned.
    ("ewar", "gate 1 team wins r (eWAR)", r"team wins over 300 team-seasons, r (0\.\d+)",
     "data/ewar_eval.json", ("gate_1_team_wins", "ewar", "r"), "abs", 0.0005),
    ("ewar", "gate 1 team wins r (bWAR)", r"team-seasons, r 0\.\d+ against bWAR (0\.\d+)",
     "data/ewar_eval.json", ("gate_1_team_wins", "bwar", "r"), "abs", 0.0005),
    ("ewar", "gate 2 persistence (eWAR FIP)", r"\(min 50 IP\), (0\.\d+)",
     "data/ewar_eval.json", ("gate_2_pitcher_persistence", "self_r_ewar_fip"), "abs", 0.0005),
    ("ewar", "gate 2 persistence (bWAR RA)", r"\(min 50 IP\), 0\.\d+ against (0\.\d+)",
     "data/ewar_eval.json", ("gate_2_pitcher_persistence", "self_r_bwar_ra"), "abs", 0.0005),
    # bust_prob names its training size because the provenance IS the claim
    # (design audit F07): the curve is fitted on the Clemens 2025 published
    # percentage tables, not on our resolved cohorts. Integer counts, so the
    # tolerance is sub-unit.
    ("bust_prob", "training_n hitter", r"training_n is (\d+) hitter",
     "data/value_framework_fitted.json", ("training_n", "hitter"), "abs", 0.5),
    ("bust_prob", "training_n pitcher", r"training_n is \d+ hitter and (\d+) pitcher",
     "data/value_framework_fitted.json", ("training_n", "pitcher"), "abs", 0.5),
    # Audit L16-16 (2026-09-11): three unpinned entries had drifted from their
    # artifacts (sem_plus quoted 0.39 / 0.26 / 0.36 against 0.4167 / 0.2843 /
    # 0.3821; riv_plus 0.21 / 0.35 against 0.2023 / 0.3601), and the FV -> WAR
    # EV table quoted FV 40 at 0.09 against a served 0.071. Each quoted number
    # is now held to its artifact. Two-decimal copy, so abs 0.005; the FV 40
    # knot is quoted to three decimals and held tighter.
    ("sem_plus", "forward rho SEM+", r"at a Spearman correlation of (0\.\d+), beating ERA",
     "data/sem_plus_eval.json", ("forward_spearman_vs_RA9_next", "sem_plus"), "abs", 0.005),
    ("sem_plus", "forward rho ERA", r"beating ERA \((0\.\d+)",
     "data/sem_plus_eval.json", ("forward_spearman_vs_RA9_next", "era"), "abs", 0.005),
    ("sem_plus", "forward rho raw FIP", r"raw-FIP parent \((0\.\d+)\)",
     "data/sem_plus_eval.json", ("forward_spearman_vs_RA9_next", "raw_fip"), "abs", 0.005),
    ("riv_plus", "RIV+ year-to-year rho", r"rank correlation is (0\.\d+) against",
     "data/riv_plus_eval.json", ("forward_stability_check", "riv_plus_y_to_y1_rho"), "abs", 0.005),
    ("riv_plus", "REM+ year-to-year rho", r"rank correlation is 0\.\d+ against (0\.\d+) for REM\+",
     "data/riv_plus_eval.json", ("forward_stability_check", "rem_plus_y_to_y1_rho"), "abs", 0.005),
    # Census X07-01 (2026-09-24): the market sentence quotes the 2026-09-18
    # re-gate (B1 primary, v1 convention, the pre-declared primary). Three
    # decimals, so abs 0.0005; the signing count is an integer.
    ("riv_plus", "market n signings", r"on (\d+) matched reliever signings",
     "data/riv_market_regate_eval.json", ("B1_primary", "n_matched_signings"), "abs", 0.5),
    ("riv_plus", "market rho RIV+", r"rank correlation with AAV is (0\.\d+) for RIV\+",
     "data/riv_market_regate_eval.json", ("B1_primary", "v1", "rho_primary"), "abs", 0.0005),
    ("riv_plus", "market rho REM+", r"for RIV\+ against (0\.\d+) for REM\+",
     "data/riv_market_regate_eval.json", ("B1_primary", "v1", "rho_baseline"), "abs", 0.0005),
    ("riv_plus", "market gap", r"a gap of (0\.\d+) inside",
     "data/riv_market_regate_eval.json", ("B1_primary", "v1", "gap_ci", "mean"), "abs", 0.0005),
    ("riv_plus", "market noise floor", r"noise floor of (0\.\d+)",
     "data/riv_market_regate_eval.json", ("B1_primary", "v1", "mde95_in_run"), "abs", 0.0005),
    ("fv_to_war_table", "EV anchor FV 40", r"FV 40 (\d\.\d+)",
     "data/value_framework_fitted.json", ("empirical_anchors", "anchors", "40"), "abs", 0.0005),
    ("fv_to_war_table", "EV anchor FV 50", r"FV 50 (\d\.\d+)",
     "data/value_framework_fitted.json", ("empirical_anchors", "anchors", "50"), "abs", 0.005),
    ("fv_to_war_table", "EV anchor FV 60", r"FV 60 (\d\.\d+)",
     "data/value_framework_fitted.json", ("empirical_anchors", "anchors", "60"), "abs", 0.005),
    # single_a_equivalent names the trusted leg per side as a dated reading
    # (census M03-04, 2026-09-24): the pitcher legs had swapped places while
    # the copy still called K% the reliable output. Two-decimal copy.
    ("single_a_equivalent", "hitter K% r2", r"hitter K% r2 (0\.\d+)",
     "data/college_translation_eval.json", ("factors", "hit_k", "r2"), "abs", 0.01),
    ("single_a_equivalent", "hitter K% LOO MAE", r"hitter K% r2 0\.\d+ \(leave-one-out MAE (\d+\.\d+)",
     "data/college_translation_eval.json", ("factors", "hit_k", "loo", "mae"), "abs", 0.01),
    ("single_a_equivalent", "hitter K% null MAE", r"hitter K% r2 0\.\d+ \(leave-one-out MAE \d+\.\d+ against (\d+\.\d+)",
     "data/college_translation_eval.json", ("factors", "hit_k", "loo", "null_mae"), "abs", 0.01),
    ("single_a_equivalent", "pitcher BB% r2", r"pitcher BB% r2 (0\.\d+)",
     "data/college_translation_eval.json", ("factors", "pit_bb", "r2"), "abs", 0.01),
    ("single_a_equivalent", "pitcher BB% LOO MAE", r"pitcher BB% r2 0\.\d+ \((\d+\.\d+) against",
     "data/college_translation_eval.json", ("factors", "pit_bb", "loo", "mae"), "abs", 0.01),
    ("single_a_equivalent", "pitcher BB% null MAE", r"pitcher BB% r2 0\.\d+ \(\d+\.\d+ against (\d+\.\d+)\)",
     "data/college_translation_eval.json", ("factors", "pit_bb", "loo", "null_mae"), "abs", 0.01),
    ("single_a_equivalent", "pitcher K% r2", r"pitcher K% r2 (0\.\d+)",
     "data/college_translation_eval.json", ("factors", "pit_k", "r2"), "abs", 0.01),
    ("single_a_equivalent", "pitcher K% LOO MAE", r"pitcher K% r2 0\.\d+ \((\d+\.\d+) against",
     "data/college_translation_eval.json", ("factors", "pit_k", "loo", "mae"), "abs", 0.01),
    ("single_a_equivalent", "pitcher K% null MAE", r"pitcher K% r2 0\.\d+ \(\d+\.\d+ against (\d+\.\d+)\)",
     "data/college_translation_eval.json", ("factors", "pit_k", "loo", "null_mae"), "abs", 0.01),
    # Census X07-04 (2026-09-25): four entries had drifted from their
    # artifacts while unpinned (sem_plus_3yr 0.414 / 0.392 against 0.4252 /
    # 0.4098; rem_plus_3yr 0.237 / 0.232 against 0.2615 / 0.252; m_guarantee
    # MAE 10.06 / 11.19 against 9.690 / 11.120; m_years 0.441 / 0.485 against
    # 0.4329 / 0.4871). They and the neighbouring forward-test entries that
    # still agreed (hem_plus, hem_plus_3yr, xhem_plus, pwoba) are held to
    # their artifacts from here. Copy rounds to the quoted decimals.
    ("sem_plus_3yr", "3yr forward rho", r"three-year forward Spearman (0\.\d+) against",
     "data/sem_plus_multiyear_eval.json", ("sem_3yr_forward_rho",), "abs", 0.005),
    ("sem_plus_3yr", "1yr forward rho, same set", r"three-year forward Spearman 0\.\d+ against (0\.\d+) for one year",
     "data/sem_plus_multiyear_eval.json", ("sem_1yr_forward_rho_on_3yr_set",), "abs", 0.005),
    ("rem_plus_3yr", "3yr forward rho", r"three-year forward Spearman (0\.\d+) against",
     "data/rem_plus_multiyear_eval.json", ("rem_3yr_forward_rho",), "abs", 0.005),
    ("rem_plus_3yr", "1yr forward rho, same set", r"three-year forward Spearman 0\.\d+ against (0\.\d+) for one year",
     "data/rem_plus_multiyear_eval.json", ("rem_1yr_forward_rho_on_3yr_set",), "abs", 0.005),
    ("m_guarantee", "Gate 2 guarantee MAE model", r"guarantee MAE (\d+\.\d+) against comps",
     "data/fa_gate2_eval.json", ("pooled", "guarantee", "mae_model"), "abs", 0.005),
    ("m_guarantee", "Gate 2 guarantee MAE comps", r"guarantee MAE \d+\.\d+ against comps (\d+\.\d+)",
     "data/fa_gate2_eval.json", ("pooled", "guarantee", "mae_base"), "abs", 0.005),
    ("m_years", "Gate 2 years MAE model", r"comps baseline (0\.\d+) against",
     "data/fa_gate2_eval.json", ("pooled", "years", "mae_model"), "abs", 0.0005),
    ("m_years", "Gate 2 years MAE comps", r"comps baseline 0\.\d+ against (0\.\d+) MAE",
     "data/fa_gate2_eval.json", ("pooled", "years", "mae_base"), "abs", 0.0005),
    ("hem_plus", "forward rho HEM+", r"next-year wOBA at a Spearman correlation of (0\.\d+), beating",
     "data/hem_plus_eval.json", ("forward_spearman_vs_wOBA_next", "hem_plus"), "abs", 0.005),
    ("hem_plus", "forward rho AVG", r"beating batting average \((0\.\d+)",
     "data/hem_plus_eval.json", ("forward_spearman_vs_wOBA_next", "avg"), "abs", 0.005),
    ("hem_plus", "forward rho raw wOBA", r"raw-wOBA parent \((0\.\d+)\)",
     "data/hem_plus_eval.json", ("forward_spearman_vs_wOBA_next", "raw_woba"), "abs", 0.005),
    ("hem_plus", "forward rho OPS", r"with OPS \((0\.\d+)\)",
     "data/hem_plus_eval.json", ("forward_spearman_vs_wOBA_next", "ops"), "abs", 0.005),
    ("hem_plus_3yr", "3yr forward rho", r"Spearman correlation of (0\.\d+) against",
     "data/hem_plus_multiyear_eval.json", ("hem_3yr_forward_rho",), "abs", 0.005),
    ("hem_plus_3yr", "1yr forward rho, same set", r"against (0\.\d+) for one season",
     "data/hem_plus_multiyear_eval.json", ("hem_1yr_forward_rho_on_3yr_set",), "abs", 0.005),
    # RML07 (served-number reconciliation, 2026-10-01): the xhem_plus headline
    # quoted the eval-normalized construction (0.45 against 0.41) while the
    # registry row's standing rule requires the SERVED construction's number.
    # The headline is pinned to the re-gate's D4 rung; the 0.4543 figure is
    # pinned to the original artifact as the labelled reproduction.
    ("xhem_plus", "n forward pairs", r"ex-2020, (\d+) pairs\)",
     "data/xhem_served_regate_eval.json", ("n_forward_pairs", "A1"), "abs", 0.5),
    ("xhem_plus", "served rho xHEM+", r"as served predicts next-year wOBA at a Spearman correlation of (0\.\d+)",
     "data/xhem_served_regate_eval.json",
     ("arms", "A1_xhem_plus", "ladder", "D4", "v1", "rho_primary"), "abs", 0.005),
    ("xhem_plus", "served rho actual wOBA", r"against (0\.\d+) for actual wOBA",
     "data/xhem_served_regate_eval.json",
     ("arms", "A1_xhem_plus", "ladder", "D4", "v1", "rho_baseline"), "abs", 0.005),
    ("xhem_plus", "served gap lo95", r"gap confidence floor (0\.\d+) above zero",
     "data/xhem_served_regate_eval.json",
     ("arms", "A1_xhem_plus", "ladder", "D4", "v1", "gap_ci", "lo95"), "abs", 0.0005),
    ("xhem_plus", "reproduction rho xwOBA", r"eval-normalized construction reads (0\.\d+) against",
     "data/xhem_plus_eval.json", ("forward_spearman_vs_wOBA_next", "xwoba"), "abs", 0.00005),
    ("xhem_plus", "reproduction rho actual wOBA", r"eval-normalized construction reads 0\.\d+ against (0\.\d+)",
     "data/xhem_plus_eval.json", ("forward_spearman_vs_wOBA_next", "actual_woba"), "abs", 0.00005),
    ("pwoba", "n gate pairs", r"\((\d+) out-of-sample pairs\)",
     "data/phem_marcel_lite_eval.json", ("hitters", "n_gate"), "abs", 0.5),
    ("pwoba", "gate rho projected wOBA", r"Spearman correlation of (0\.\d+) against",
     "data/phem_marcel_lite_eval.json", ("hitters", "gate_rhos_v1", "fa_projection"), "abs", 0.00005),
    ("pwoba", "gate rho incumbent", r"against (0\.\d+) for the best trailing-average incumbent",
     "data/phem_marcel_lite_eval.json", ("hitters", "gate_rhos_v1", "incumbent_3yr_flat"), "abs", 0.00005),
    # The served xwOBA blend (owner flip NOV15-PWOBA-FLIP, 2026-10-14): its re-gate numbers.
    ("pwoba", "blend gate pairs", r"and (\d+) held-out pairs it reads",
     "data/pwoba_blend_regate_eval.json", ("registered_regate", "n"), "abs", 0.5),
    ("pwoba", "blend gate rho", r"it reads a Spearman rho of (0\.\d+) against",
     "data/pwoba_blend_regate_eval.json", ("registered_regate", "rhos_v1", "output_blend"), "abs", 0.00005),
    ("pwoba", "blend gate rho engine", r"against (0\.\d+) for the engine projection alone",
     "data/pwoba_blend_regate_eval.json", ("registered_regate", "rhos_v1", "fa_projection"), "abs", 0.00005),
    ("pwoba", "blend gate lo95 v1", r"floor \+(0\.\d+) above zero",
     "data/pwoba_blend_regate_eval.json", ("registered_regate", "gap_ci_blend_minus_incumbent_v1", "lo95"), "abs", 0.00005),
    ("pwoba", "blend gate lo95 v2", r"\+(0\.\d+) under the player-clustered bootstrap",
     "data/pwoba_blend_regate_eval.json", ("registered_regate", "gap_ci_blend_minus_incumbent_v2", "lo95"), "abs", 0.00005),
)

# ---------------------------------------------------------------------------
# Part 3: registry note policy.
# Rows whose eval artifact regenerates nightly: bare undated performance
# numbers in notes ALWAYS rot. Policy: the notes must carry at least one
# dated reading marker, and the newest marker must sit within
# READING_MAX_AGE_DAYS of the artifact's generated date.
NIGHTLY_NOTE_MODELS = ("betting_game_prob", "betting_elo_benchmark", "stuff_plus_aaa")
READING_RE = re.compile(r"(20\d\d-\d\d-\d\d) reading:")
READING_MAX_AGE_DAYS = 45

# Stable-gate figure pins. One line per check:
#   (model_id, headline label substring, artifact_rel_path, keypath, abs_tol)
# The row's card.headline champion figure must match the gate artifact.
STABLE_GATE_CHECKS = (
    ("fa_market", "guarantee", "data/fa_gate2_eval.json",
     ("pooled", "guarantee", "mae_model"), 0.05),
    # The literal card served 0.63 on /glossary/#view=models while the artifact
    # read 0.574 (2026-08-03) and then 0.5157 (2026-09-23); it is derived now.
    ("fa_projection_marcel", "WAR error", "data/fa_gate1_eval.json",
     ("pooled", "war", "mae_model"), 0.005),
)


# ---------------------------------------------------------------------------
# helpers (pure readers; no file IO at import time)

def _read_json(rel):
    with open(ROOT / rel, encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _dig(obj, keypath):
    for key in keypath:
        obj = obj[key]
    return obj


def _glossary_entry(entry_id):
    entries = _read_json("data/glossary.json")["entries"]
    hits = [e for e in entries if e.get("id") == entry_id]
    assert hits, f"glossary entry missing: {entry_id} (update GLOSSARY_CLAIMS if renamed)"
    return hits[0]


def _entry_text(entry):
    return (entry.get("definition") or "") + "\n" + (entry.get("methodology") or "")


def _registry_row(model_id):
    models = _read_json("data/model_registry.json")["models"]
    hits = [m for m in models if m.get("model_id") == model_id]
    assert hits, f"registry row missing: {model_id}"
    return hits[0]


def _parse_iso_date(stamp):
    """First 10 chars of an ISO stamp ('2026-08-19' or '2026-08-19T19:16:25+00:00')."""
    return date.fromisoformat(str(stamp)[:10])


def _within(claimed, actual, tol_mode, tol):
    if tol_mode == "abs":
        return abs(claimed - actual) <= tol
    if tol_mode == "rel":
        return abs(claimed - actual) <= tol * abs(actual)
    raise ValueError(f"unknown tol_mode {tol_mode!r}")


# ---------------------------------------------------------------------------
# Part 1 tests

def _ratchet_surfaces():
    surfaces = list(CLAIM_SURFACES)
    surfaces += sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in (ROOT / "content").glob("*.json")
    )
    return surfaces


def test_banned_claim_fragments_absent():
    """The ratchet: contradicted static claims never return to a copy surface."""
    violations = []
    for rel in _ratchet_surfaces():
        text = _read_text(rel).lower()
        for frag in BANNED_CLAIM_FRAGMENTS:
            if frag.lower() in text:
                violations.append(f"{rel}: {frag!r}")
    assert not violations, (
        "banned static claim fragment(s) present (each was a live "
        "contradicted claim on 2026-08-19; accuracy copy derives from "
        "artifacts at render time, it is never hand-written): "
        + "; ".join(violations)
    )


def test_ratchet_surfaces_exist():
    """A ratchet over a missing file is a silent no-op; refuse that."""
    for rel in _ratchet_surfaces():
        assert (ROOT / rel).is_file(), f"ratchet surface missing: {rel}"
    for rel in REGISTRY_RATCHET_SURFACES:
        assert (ROOT / rel).is_file(), f"registry ratchet surface missing: {rel}"


def test_registry_prose_carries_no_retired_figure():
    """The registry ratchet: figures retired from registry prose never return
    to the registry or to the pages generated from it, and every one of them
    is also in BANNED_CLAIM_FRAGMENTS with its history."""
    missing = [f for f in REGISTRY_RATCHET_FRAGMENTS if f not in BANNED_CLAIM_FRAGMENTS]
    assert not missing, f"registry fragments without a history line: {missing}"
    violations = []
    for rel in REGISTRY_RATCHET_SURFACES:
        text = _read_text(rel).lower()
        for frag in REGISTRY_RATCHET_FRAGMENTS:
            if frag.lower() in text:
                violations.append(f"{rel}: {frag!r}")
    assert not violations, "retired registry figure(s) present: " + "; ".join(violations)


# ---------------------------------------------------------------------------
# Part 2 tests

def test_glossary_numbers_match_artifacts():
    """Every hand-quoted glossary number in GLOSSARY_CLAIMS agrees with its
    artifact. Zero regex matches is itself a failure: the copy changed shape
    and the table must follow it, not silently stop checking."""
    problems = []
    for entry_id, label, pattern, artifact, keypath, tol_mode, tol in GLOSSARY_CLAIMS:
        text = _entry_text(_glossary_entry(entry_id))
        actual = float(_dig(_read_json(artifact), keypath))
        matches = re.findall(pattern, text)
        if not matches:
            problems.append(
                f"{entry_id}/{label}: pattern {pattern!r} found no number; "
                f"the entry copy changed, update GLOSSARY_CLAIMS"
            )
            continue
        for raw in matches:
            claimed = float(raw)
            if not _within(claimed, actual, tol_mode, tol):
                problems.append(
                    f"{entry_id}/{label}: copy quotes {claimed} but {artifact} "
                    f"{'/'.join(keypath)} = {actual} (tol {tol_mode} {tol})"
                )
    assert not problems, "glossary claim drift: " + "; ".join(problems)


def test_riv_plus_market_gap_sits_inside_its_noise_floor():
    """Census X07-01: the riv_plus copy says the RIV+ minus REM+ market gap is
    inside the noise floor. That wording holds only while the re-gate's gap
    stays inside its in-run MDE95 and resolves neither way."""
    text = _entry_text(_glossary_entry("riv_plus"))
    assert "inside a noise floor" in text, "riv_plus market sentence changed shape"
    v1 = _dig(_read_json("data/riv_market_regate_eval.json"), ("B1_primary", "v1"))
    assert abs(v1["gap_ci"]["mean"]) < v1["mde95_in_run"]
    assert not v1["lo95_gt_0"] and not v1["hi95_lt_0"]


# Payload source key -> the label the copy uses (census X07-02, 2026-09-24).
_REPORT_SOURCE_LABELS = {
    "fangraphs": "FanGraphs",
    "mlb_pipeline": "MLB Pipeline",
    "baseballamerica": "Baseball America",
    "espn": "ESPN",
    "just_baseball": "Just Baseball",
}
_DRAFT_REPORT_SOURCE_LABELS = {
    "fangraphs": "FanGraphs",
    "mlb_pipeline_draft": "MLB Pipeline",
    "baseballamerica_draft": "Baseball America",
}


def test_sources_copy_names_every_excerpted_report_source():
    """Census X07-02: the /sources/ lede and the glossary attribution note
    name every source whose report excerpts the served payloads carry, and
    no source whose text they do not (excerpts since the owner's answer of
    2026-09-25; test_report_excerpt.py holds the length and link rules). The
    payloads are pipeline outputs (gitignored), so a checkout without them
    skips."""
    chunks = sorted(p for p in (ROOT / "data").glob("scout_reports_*.json")
                    if p.stem.rsplit("_", 1)[-1].isdigit())
    draft_path = ROOT / "data" / "draft_timeseries.json"
    if not chunks or not draft_path.is_file():
        pytest.skip("scout report chunks or draft board payload not built here")
    served = set()
    for path in chunks:
        with open(path, encoding="utf-8") as fh:
            for per_source in json.load(fh).values():
                for key, reports in per_source.items():
                    if key.startswith("_") or not isinstance(reports, list):
                        continue
                    if any(isinstance(r, dict) and r.get("text") for r in reports):
                        served.add(key)
    unknown = served - set(_REPORT_SOURCE_LABELS)
    assert not unknown, f"report text from an unlabelled source: {sorted(unknown)}"
    with open(draft_path, encoding="utf-8") as fh:
        draft = json.load(fh)
    draft_served = set()
    for cls in draft.get("classes", []):
        for prospect in cls.get("prospects", []):
            for point in prospect.get("points", []):
                extras = (point.get("tools") or {}).get("_extras") or {}
                if isinstance(extras, dict) and extras.get("report"):
                    draft_served.add(point.get("source"))
    unknown = draft_served - set(_DRAFT_REPORT_SOURCE_LABELS)
    assert not unknown, f"draft report text from an unlabelled source: {sorted(unknown)}"

    import build_site as B
    assert set(B.SCOUT_REPORT_SOURCES) == {_REPORT_SOURCE_LABELS[k] for k in served}
    assert set(B.DRAFT_REPORT_SOURCES) == {_DRAFT_REPORT_SOURCE_LABELS[k] for k in draft_served}
    prospect_names = B._name_series(B.SCOUT_REPORT_SOURCES)
    draft_names = B._name_series(B.DRAFT_REPORT_SOURCES)
    page = B.build_sources()
    assert prospect_names in page, f"/sources/ does not name {prospect_names}"
    assert draft_names in page, f"/sources/ does not name {draft_names}"
    # LIBRARY_5 retired the Methodology view's attribution note; the view
    # points at /sources/, which carries the attribution.
    glossary_js = _read_text("assets/glossary.js")
    assert '<a href="/sources/">Data Sources</a>' in glossary_js


def test_single_a_equivalent_example_matches_live_factor():
    """The single_a_equivalent worked example is a served number (the /glossary/
    card's example line). Census M03-04 found it quoting 19% (band 11-27%) for
    a 12% college K% when the live hit_k factor gave 23.7% (15.2-32.2%); it had
    never matched a committed factor. Recompute it from the eval artifact with
    college_translation's own regression-to-the-mean and P10-P90 band."""
    entry = _glossary_entry("single_a_equivalent")
    m = re.search(r"at a (\d+(?:\.\d+)?)% strikeout rate projects to about (\d+(?:\.\d+)?)% "
                  r"at Single-A, with an 80% band near (\d+)-(\d+)%", entry.get("example") or "")
    assert m, "single_a_equivalent example changed shape; update this test with it"
    x, claimed, lo, hi = (float(g) for g in m.groups())
    f = _read_json("data/college_translation_eval.json")["factors"]["hit_k"]
    pred = f["y_mean"] + f["slope"] * (x - f["x_mean"])
    half = 1.2816 * f["band_sd"]
    assert abs(claimed - pred) <= 0.5, f"example says {claimed}%, live hit_k factor gives {pred:.1f}%"
    assert abs(lo - max(0.0, pred - half)) <= 1.0, f"band low {lo} vs {pred - half:.1f}"
    assert abs(hi - min(100.0, pred + half)) <= 1.0, f"band high {hi} vs {pred + half:.1f}"


def test_collegesavant_trust_copy_reads_the_eval():
    """Both CollegeSavant apps generate the What-to-trust copy from the
    translation eval and flag K% from the per-player low_confidence field, so
    the sentence, the table flag and the player-page flag cannot disagree."""
    for rel, legs in (("collegesavant/pitcher_app.js", '[["pit_k", "strikeout rate"], ["pit_bb", "walk rate"]]'),
                      ("collegesavant/app.js", '[["hit_k", "strikeout rate"], ["hit_bb", "walk rate"], ["hit_ops", "OPS"]]')):
        src = _read_text(rel)
        assert "<strong>What to trust.</strong> ${trustSentence(E, " + legs + ")}" in src, rel
        assert 'sa.k_pct && sa.k_pct.low_confidence ? "low confidence"' in src, rel
        assert "r2 < 0.10" not in src and "r2 < lowSignalR2()" in src, rel


# ---------------------------------------------------------------------------
# Part 3 tests

def test_nightly_registry_notes_carry_dated_readings():
    """Rows over nightly-regenerating artifacts must date-stamp every quoted
    reading and keep the newest stamp within READING_MAX_AGE_DAYS of the
    artifact's generated date."""
    problems = []
    for model_id in NIGHTLY_NOTE_MODELS:
        row = _registry_row(model_id)
        notes = row.get("notes") or ""
        stamps = READING_RE.findall(notes)
        if not stamps:
            problems.append(
                f"{model_id}: notes carry no 'YYYY-MM-DD reading:' marker; "
                f"its eval artifact regenerates nightly, so undated "
                f"performance numbers in notes always rot"
            )
            continue
        newest = max(date.fromisoformat(s) for s in stamps)
        artifact = row.get("eval_artifact")
        assert artifact, f"{model_id}: nightly row with no eval_artifact"
        generated = _parse_iso_date(_read_json(artifact)["generated_at"])
        age = abs((generated - newest).days)
        if age > READING_MAX_AGE_DAYS:
            problems.append(
                f"{model_id}: newest dated reading {newest} is {age} days "
                f"from {artifact} generated_at {generated} "
                f"(max {READING_MAX_AGE_DAYS}); refresh the reading"
            )
    assert not problems, "stale nightly registry notes: " + "; ".join(problems)


def test_stable_gate_figures_match_artifacts():
    """Seeded stable-gate pins: the registry card headline figure must match
    the gate artifact it summarizes."""
    problems = []
    for model_id, label_frag, artifact, keypath, tol in STABLE_GATE_CHECKS:
        row = _registry_row(model_id)
        card = row.get("card") or {}
        headlines = [
            h for h in card.get("headline", [])
            if label_frag.lower() in str(h.get("label", "")).lower()
        ]
        if not headlines:
            problems.append(
                f"{model_id}: no card headline whose label contains "
                f"{label_frag!r}; the gate figure must live on the card"
            )
            continue
        actual = float(_dig(_read_json(artifact), keypath))
        for h in headlines:
            claimed = float(h["champion"])
            if abs(claimed - actual) > tol:
                problems.append(
                    f"{model_id}: card headline {h.get('label')!r} quotes "
                    f"champion {claimed} but {artifact} {'/'.join(keypath)} "
                    f"= {actual} (abs tol {tol})"
                )
    assert not problems, "stable gate figure drift: " + "; ".join(problems)


# ---------------------------------------------------------------------------
# Part 4: code-constant pins (2026-09-04, design audit section 6).
# Layer 2 pins copy to ARTIFACTS. These pin copy to SHIPPED CODE CONSTANTS,
# which is where the two worst stale claims lived: a retired calibration
# described as live, and a borrowed training set described as our own.

# Phrases that only make sense while the served dispersion correction is a LIVE
# affine map. efv_score._DISPERSION_CORRECTION has been identity since
# 2026-08-14 (C-7 revert), so while it is identity none of these may appear on a
# copy surface, and the retirement must be disclosed instead.
LIVE_SLOPE_CLAIMS = (
    "brings the calibration slope to about 1.0",
    "an affine correction fitted out of fold",
    "the affine dispersion correction now",
)
RETIRED_SLOPE_DISCLOSURES = (
    "level calibration, retired 2026-08-14",
    "the served war is the model's war",
)


# The surfaces that state the valuation conventions in prose. assets/fa.js
# joined 2026-09-11 (audit F12-04): its deferral tooltip quoted a 9% rate that
# no pin could see because the file was never scanned. The Gate-2 artifacts
# (data/fa_gate2_eval.json, data/fa_meta.json) are NOT here: they are pipeline
# output, and test_served_gate2_note_names_the_rate_its_table_was_priced_at
# holds them to the rate they were priced at instead.
_VALUATION_COPY_SURFACES = ("data/glossary.json", "assets/glossary.js",
                            "docs/METHODOLOGY.md", "assets/fa.js")


def _copy_text_lower():
    """The valuation copy surfaces, lowercased, one blob."""
    return ("\n".join(_read_text(rel)
                      for rel in _VALUATION_COPY_SURFACES)).lower()


def test_glossary_dispersion_claim_matches_served_constant():
    """The glossary may not describe a live slope correction while
    efv_score._DISPERSION_CORRECTION is identity, and may not describe the
    correction as retired while it is armed. Reads the CONSTANT, not a doc."""
    import efv_score

    corr = efv_score._DISPERSION_CORRECTION
    assert set(corr) == {"hit", "pit"}, f"unexpected correction keys: {sorted(corr)}"
    identity = all(abs(float(a)) <= 1e-12 and abs(float(b) - 1.0) <= 1e-12
                   for a, b in corr.values())
    text = _copy_text_lower()
    live_hits = [f for f in LIVE_SLOPE_CLAIMS if f in text]
    retired_hits = [f for f in RETIRED_SLOPE_DISCLOSURES if f in text]
    if identity:
        assert not live_hits, (
            "efv_score._DISPERSION_CORRECTION is identity "
            f"({corr}) but copy still describes a live slope correction: "
            + "; ".join(repr(f) for f in live_hits)
        )
        assert retired_hits, (
            "efv_score._DISPERSION_CORRECTION is identity but no copy surface "
            "discloses the retirement; one of "
            + "; ".join(repr(f) for f in RETIRED_SLOPE_DISCLOSURES)
            + " must be present so the reader is not left with the pre-revert story"
        )
    else:
        assert not retired_hits, (
            f"efv_score._DISPERSION_CORRECTION is armed ({corr}) but copy still "
            "says the correction is retired / identity: "
            + "; ".join(repr(f) for f in retired_hits)
        )


def test_glossary_platt_constants_match_module():
    """bust_prob quotes the served odds Platt map. Pin it to the module the
    scoring seams actually call."""
    import efv_odds_calibration

    text = _entry_text(_glossary_entry("bust_prob"))
    m = re.search(r"A/B (\d\.\d+)/(\d\.\d+) hitter and (\d\.\d+)/(\d\.\d+) pitcher", text)
    assert m, ("bust_prob no longer quotes the Platt map in the pinned shape; "
               "update this test with the copy")
    claimed = {"hit": (float(m.group(1)), float(m.group(2))),
               "pit": (float(m.group(3)), float(m.group(4)))}
    for side, (a, b) in claimed.items():
        act_a, act_b = efv_odds_calibration._PLATT[side]
        assert abs(a - act_a) <= 5e-4 and abs(b - act_b) <= 5e-4, (
            f"bust_prob quotes {side} Platt ({a}, {b}) but "
            f"efv_odds_calibration._PLATT[{side!r}] = ({act_a}, {act_b})"
        )


# The accuracy verdict under the head-to-head bars is DERIVED from the backtest
# artifact at render time. A hard-coded accuracy NUMBER in that template is the
# defect that produced "eFV orders realized WAR ahead of the field" printed
# beside a Pipeline figure above eFV, so the guard is structural: no literal
# with three or more decimals may appear inside the function.
_ACC_FN_RE = re.compile(
    r"function _methAccuracyChart\(bt\) \{(.*?)\n\}\n", re.S)
_HARDCODED_DECIMAL_RE = re.compile(r"\b\d+\.\d{3,}\b")


def test_accuracy_chart_verdict_is_derived():
    js = _read_text("assets/glossary.js")
    m = _ACC_FN_RE.search(js.replace("\r\n", "\n"))
    assert m, "_methAccuracyChart not found in assets/glossary.js (renamed?)"
    body = m.group(1)
    # Strip comments: the block comment ABOVE the copy is allowed to cite the
    # measurement that motivated the fix; the rendered copy is not.
    code = "\n".join(ln for ln in body.split("\n")
                     if not ln.lstrip().startswith("//"))
    bad = _HARDCODED_DECIMAL_RE.findall(code)
    assert not bad, (
        "_methAccuracyChart carries hard-coded accuracy constant(s) "
        f"{bad}; the verdict must be derived from the backtest artifact "
        "(banned-experiment ledger item 9)"
    )
    assert "bestPub" in code and "reduce(" in code, (
        "_methAccuracyChart no longer derives the best public rater by "
        "max over the rater list; the three-branch verdict depends on it"
    )


# Census X01-02 (2026-09-24): the Source Comparison findings strip must not
# carry a ranking or AUC card off a frame other than the verdict's. The strip's
# comparative cards read pooled_efv_common (the all-vintages regression
# control) beside a hero on the vintage-matched verdict. The guard is
# structural: the function may not read any pooled_* accuracy block, and the
# honesty caveat's head-to-head bullet must come from the derived helper.
_FINDINGS_FN_RE = re.compile(
    r"function _methEfvFindings\(bt\) \{(.*?)\n\}\n", re.S)


def test_findings_strip_reads_no_pooled_frame():
    js = _read_text("assets/glossary.js").replace("\r\n", "\n")
    m = _FINDINGS_FN_RE.search(js)
    assert m, "_methEfvFindings not found in assets/glossary.js (renamed?)"
    code = "\n".join(ln for ln in m.group(1).split("\n")
                     if not ln.lstrip().startswith("//"))
    assert not re.search(r"\.pooled\w*", code), (
        "_methEfvFindings reads a pooled accuracy block; the head-to-head "
        "ranking belongs to the hero on head_to_head_verdict's basis")
    assert not re.search(r"\bauc\b", code), (
        "_methEfvFindings prints an AUC figure; no floor on the page covers "
        "it (do-not-reopen item 3)")
    assert not _HARDCODED_DECIMAL_RE.findall(code), (
        "_methEfvFindings carries a hard-coded accuracy constant")
    assert "${_methCaveatHeadToHead(bt)}" in js, (
        "the honesty caveat's head-to-head bullet is no longer derived from "
        "head_to_head_verdict")


# Control-window and discount copy must track the ACTIVE valuation set, not the
# base config. The shipped set is clemens_2026 (7 control years, net 7%); the
# base config still carries the legacy 6 / 9% and copy kept quoting those.
_CONTROL_PHRASES = (
    "control years", "controlled seasons", "years of team control",
    "cost-controlled years",
)
_NUMWORD = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
            8: "eight", 9: "nine", 10: "ten"}

# Every phrasing that binds a number to THE platform discount rate. Until
# 2026-09-11 the pin below matched only "net N percent", so it saw three correct
# 7s and none of the stale 9s phrased without the word "net" (audit F12-04):
# "discounts at 9%", "the platform 9% rate", "the platform's 9% rate", "the same
# 9% NPV currency", "(1+0.09)^years-out". Each pattern captures ONE number:
# "pct" rows a percent, "dec" rows a decimal rate. test_the_discount_ratchet_
# sees_every_retired_phrasing proves every retired string trips it.
#
# Deliberately NOT matched, because each is true on the current copy: "a 10
# percent discount rate minus 3 percent annual win-cost growth" (the gross rate
# the net one is built from), "the base config's 6 control years and 9 percent
# discount are the legacy prospx_current values" and "discount_rate: 0.09" (the
# disclosed legacy value), and "the CBT's ~4.4% statutory rate" (a different
# rate, named as one).
_PCT = r"(\d+(?:\.\d+)?)\s*(?:%|percent)"
DISCOUNT_RATE_PATTERNS = (
    ("net N%", "pct", r"\bnet " + _PCT),
    ("platform N%", "pct",
     r"\bplatform(?:'s)?\s+(?:configured\s+)?(?:net\s+)?" + _PCT),
    ("discounts at N%", "pct",
     r"\bdiscount(?:s|ed|ing)?\s+at\s+(?:the\s+)?(?:platform(?:'s)?\s+)?"
     r"(?:configured\s+)?(?:net\s+)?" + _PCT),
    ("N% NPV", "pct", _PCT + r"\s+npv\b"),
    ("N% platform rate", "pct", _PCT + r"\s+platform\s+rate\b"),
    ("(1+r)^t literal", "dec", r"\(\s*1\s*\+\s*(0\.\d+)\s*\)\s*\^"),
    ("net rate decimal", "dec", r"\bnet[ _]rate:?\s+(0\.\d+)"),
)


def _discount_rate_claims(text):
    """[(pattern label, claimed rate in percent, snippet)] over LOWERCASED text."""
    out = []
    for label, kind, pat in DISCOUNT_RATE_PATTERNS:
        for m in re.finditer(pat, text):
            v = float(m.group(1)) * (100.0 if kind == "dec" else 1.0)
            out.append((label, v, text[max(0, m.start() - 40):m.end() + 20]))
    return out


def test_control_window_and_discount_copy_match_valuation_set():
    import value_framework

    cfg = value_framework._config()
    control_years = int(cfg["service_time"]["control_years"])
    discount_pct = float(cfg["discount_rate"]) * 100
    text = _copy_text_lower()

    wrong = []
    for n, word in _NUMWORD.items():
        if n == control_years:
            continue
        for phrase in _CONTROL_PHRASES:
            if f"{word} {phrase}" in text:
                wrong.append(f"{word} {phrase}")
    assert not wrong, (
        f"the active valuation set serves {control_years} control years "
        f"(value_framework._config service_time.control_years) but copy says: "
        + "; ".join(sorted(set(wrong)))
    )

    claims = _discount_rate_claims(text)
    nets = [c for c in claims if c[0] == "net N%"]
    assert nets, ("no copy surface states the net discount rate; the surplus "
                  "copy must name it so this pin has something to check")
    off = [c for c in claims if abs(c[1] - discount_pct) > 0.05]
    assert not off, (
        f"the active valuation set discounts at {discount_pct:g} percent "
        f"(value_framework._config discount_rate) but copy quotes: "
        + "; ".join(f"{label} -> {v:g} in {snip!r}" for label, v, snip in off)
    )


def test_the_forward_bans_actually_fire(tmp_path, monkeypatch):
    """A ratchet nobody has tripped is a ratchet nobody has tested, and the five
    A-CLAIM-9 fragments are FORWARD bans: none has ever appeared on a surface, so
    unlike the rest of the tuple they have no history proving they match.

    This writes each one into a scratch surface and asserts the scan catches it.
    """
    surf = tmp_path / "fake_surface.js"
    forward = ("probability that eFV is better",
               "probability eFV is better",
               "chance that eFV is better",
               "posterior probability that eFV",
               "odds that eFV beats")
    for frag in forward:
        surf.write_text(f"var hero = 'There is an 85% {frag} the consensus';",
                        encoding="utf-8")
        text = surf.read_text(encoding="utf-8").lower()
        hits = [f for f in BANNED_CLAIM_FRAGMENTS if f.lower() in text]
        assert hits, f"the ratchet does not catch {frag!r}"


def test_a_posterior_claim_is_banned_even_though_no_posterior_exists_yet():
    """The ban is deliberately AHEAD of the artifact it constrains. The Bayesian
    companion is registered and unbuilt, and the sentence it appears to license
    is the one a served surface must never carry: the number is only as good as
    a prior a reader cannot see, and the rest of this claim frame is
    pre-registered and frequentist."""
    joined = " ".join(BANNED_CLAIM_FRAGMENTS).lower()
    assert "probability that efv is better" in joined
    assert "posterior probability that efv" in joined


# ---------------------------------------------------------------------------
# Part 5: the discount rate (audit F12-01 to F12-04, 2026-09-09).
#
# value_framework._config()["discount_rate"] is 0.07 under clemens_2026. Six
# served strings quoted the legacy 9 percent beside it, one of them on the Free
# Agency Model Accountability page over a 1,199-row table priced at 7, and the
# deferral_npv card named an Ohtani figure ($197M) that was the 9 percent rate
# AND a retired count-from-1 offset at once. No test compared any of them with
# the engine. These do.

# Verbatim retired strings (lowercased), one per surface they lived on.
_RETIRED_DISCOUNT_PHRASINGS = (
    "each control season still escalates with $/war inflation and discounts at 9%.",
    "schedules in the curated deferral ledger discount at the platform 9% rate",
    "because rational value and pick values share the same 9% npv currency",
    "escalated per season and discounted at the platform's 9% rate",
    "contract dollars discounted for deferral schedules at the platform 9% rate",
    "npv = sum of scheduled payments / (1+0.09)^years-out",
    "the 9% platform rate is deliberately harsher than the cbt's ~4.4% statutory rate",
    "seasons and discounts at the platform 9%; arb/pre-arb seasons",
    'title="deferral-adjusted npv at the platform 9% rate - the basis the prediction speaks"',
    "guarantee/aav in $m npv (deferral-adjusted at the platform 9% rate; "
    "no-schedule deals keep sticker)",
)
# True sentences that sit next to a discount rate and must NOT trip it.
_TRUE_RATE_NEIGHBOURS = (
    "a 10 percent discount rate minus 3 percent annual win-cost growth",
    "a 10% discount rate minus 3% annual win-cost growth",
    "the base config's 6 control years and 9 percent discount are the legacy "
    "prospx_current values",
    "the base config's 6 years / 9% are the legacy prospx_current values",
    "`discount_rate: 0.09` and `dollars_per_war_inflation: 0.05`",
    "harsher than the cbt's ~4.4% statutory rate",
    "a 97%-deferred sticker is not the same liability as level cash",
)


def test_the_discount_ratchet_sees_every_retired_phrasing():
    """A ratchet nobody has tripped is a ratchet nobody has tested. Every string
    the net-only pin let through must now produce a 9, and every true neighbour
    must produce nothing, or the pin turns red on correct copy."""
    for s in _RETIRED_DISCOUNT_PHRASINGS:
        vals = [v for _, v, _ in _discount_rate_claims(s)]
        assert vals and all(abs(v - 9.0) < 1e-9 for v in vals), (s, vals)
    for s in _TRUE_RATE_NEIGHBOURS:
        assert not _discount_rate_claims(s), (s, _discount_rate_claims(s))


def test_deferral_npv_ohtani_figure_matches_the_engine():
    """The card's worked example is a served number, so it is held to the
    function the payload calls, at the configured rate."""
    import fa_market as fm

    text = _entry_text(_glossary_entry("deferral_npv")).lower()
    quoted = re.findall(r"ohtani's \$700m prices as ~?\$(\d+(?:\.\d+)?)m", text)
    assert quoted, ("deferral_npv no longer quotes Ohtani's present liability in "
                    "the pinned shape; update this test with the copy")
    npv, had = fm.npv_guarantee_usd("shohei_ohtani", 2024, 700_000_000)
    assert had, "the deferral ledger lost Ohtani's schedule; the example has nothing under it"
    for raw in quoted:
        assert abs(float(raw) - npv / 1e6) <= 0.05, (
            f"deferral_npv says Ohtani prices at ${raw}M but "
            f"fa_market.npv_guarantee_usd reads ${npv / 1e6:.1f}M at "
            f"{fm._discount_rate():g}")


def test_deferral_npv_rescale_clause_describes_the_serving_path(monkeypatch):
    """The audit proposed deleting "schedules rescaled to the sticker total" as a
    rescale the code does not do, measuring deferral_npv_usd alone. The serving
    path is npv_guarantee_usd, and it rescales. This keeps the clause and the
    behaviour together: if the rescale is ever removed, the clause goes too."""
    import fa_market as fm

    text = _entry_text(_glossary_entry("deferral_npv")).lower()
    assert "rescaled to the sticker total" in text
    fake = {"x:2030": {"schedule": [{"year_offset": 0, "amount_usd": 60_000_000},
                                    {"year_offset": 5, "amount_usd": 60_000_000}]}}
    monkeypatch.setattr(fm, "_deferral_ledger", lambda: fake)
    npv, had = fm.npv_guarantee_usd("x", 2030, 100_000_000)
    r = fm._discount_rate()
    want = int(50_000_000 + 50_000_000 / (1 + r) ** 5)   # 120M nominal -> 100M sticker
    assert had and abs(npv - want) <= 1, (npv, want)


def test_no_copy_surface_types_a_fallback_discount_rate():
    """A missing rate renders as words, never as a legacy number: the surplus
    walk in assets/glossary.js printed 9%/yr whenever the payload lacked one."""
    bad = []
    for rel in ("assets/glossary.js", "assets/fa.js"):
        for m in re.finditer(r"discount_rate\s*(?:\|\||\?\?)\s*\d*\.\d+", _read_text(rel)):
            bad.append(f"{rel}: {m.group(0)!r}")
    assert not bad, "typed fallback discount rate(s): " + "; ".join(bad)


def test_gate2_npv_note_is_interpolated_from_the_rate_it_is_given():
    """The SOURCE half of F12-01. fa_backtest used to type "platform 9% rate"
    into the Gate-2 notes; the note must now move with the rate, and the
    production call must hand it the engine's own rate and stamp it."""
    import inspect

    import fa_backtest as fb

    for rate in (0.07, 0.09, 0.075):
        npv_notes = [n for n in fb.gate2_notes(rate) if "deferral-adjusted" in n]
        assert len(npv_notes) == 1, fb.gate2_notes(rate)
        vals = [v for _, v, _ in _discount_rate_claims(npv_notes[0].lower())]
        assert vals and all(abs(v - rate * 100) < 1e-6 for v in vals), (rate, npv_notes, vals)
    src = inspect.getsource(fb.run_market_gate)
    for needle in ("disc_rate = fm._discount_rate()", '"discount_rate": disc_rate',
                   '"notes": gate2_notes(disc_rate)'):
        assert needle in src, f"run_market_gate no longer carries {needle!r}"
    assert not re.search(r"platform(?:'s)?\s+\d+(?:\.\d+)?\s*%", src), (
        "run_market_gate types a platform rate again")


def _gate2_ohtani_rows(g):
    return [m for k in ("biggest_misses", "biggest_misses_years", "biggest_misses_aav")
            for m in (g.get(k) or [])
            if m.get("player") == "Shohei Ohtani" and m.get("winter") == 2024]


def test_gate2_table_is_priced_at_the_configured_discount_rate():
    """The table the note describes, checked from inside. Ohtani's 2024 signing
    is a deferral-scheduled actual, so its NPV names the rate the table was
    priced at: 274.8 at 7 percent, 214.9 at 9. This is what shows the note was
    wrong and the table right, and it goes red if the engine's rate moves
    without a Gate-2 regen."""
    import fa_market as fm

    g = _read_json("data/fa_gate2_eval.json")
    rows = _gate2_ohtani_rows(g)
    if not rows:
        pytest.skip("Ohtani's 2024 signing is not among the published misses, so "
                    "no row inside the table names its rate")
    npv, had = fm.npv_guarantee_usd("shohei_ohtani", 2024, 700_000_000)
    assert had
    for m in rows:
        assert abs(float(m["actual_guar_mm"]) - npv / 1e6) <= 0.051, (
            f"Gate-2 prices Ohtani's actual at ${m['actual_guar_mm']}M; the engine "
            f"reads ${npv / 1e6:.1f}M at {fm._discount_rate():g}. Regenerate Gate 2.")


_GATE2_SURFACES = (("data/fa_gate2_eval.json", ()), ("data/fa_meta.json", ("gate2",)))


def test_served_gate2_note_names_the_rate_its_table_was_priced_at():
    """The SERVED half of F12-01. assets/fa.js renders gate2.notes verbatim.

    An artifact written before the source fix carries no discount_rate stamp
    and still holds the typed literal; that is a regen owed, not a new defect,
    so it xfails (the repo's stamp-gated pattern, as in
    test_trade_board_coverage.py) and turns into a real assertion the first
    time Gate 2 is re-persisted."""
    import value_framework

    engine_pct = float(value_framework._config()["discount_rate"]) * 100
    problems, owed = [], []
    for rel, keypath in _GATE2_SURFACES:
        g = _dig(_read_json(rel), keypath)
        if not g:
            continue                      # fa_meta written with no Gate-2 artifact
        claims = [c for n in (g.get("notes") or []) for c in _discount_rate_claims(n.lower())]
        stamp = g.get("discount_rate")
        if stamp is None:
            owed.append(f"{rel} (generated {g.get('generated_at')}) quotes "
                        f"{sorted({v for _, v, _ in claims})}")
            continue
        stamp_pct = float(stamp) * 100
        if abs(stamp_pct - engine_pct) > 1e-6:
            problems.append(f"{rel}: table priced at {stamp_pct:g}% but the engine "
                            f"discounts at {engine_pct:g}%; regenerate Gate 2")
        if not claims:
            problems.append(f"{rel}: no note names the discount rate")
        for label, v, snip in claims:
            if abs(v - stamp_pct) > 1e-6:
                problems.append(f"{rel}: note says {v:g}% ({label}: {snip!r}) over a "
                                f"table priced at {stamp_pct:g}%")
    assert not problems, "Gate-2 discount note drift: " + "; ".join(problems)
    if owed:
        pytest.xfail(
            "Gate-2 artifact predates the discount_rate stamp (audit F12-01), so "
            "its NPV note is still the literal the source used to type: "
            + "; ".join(owed)
            + ". Regen owed: python -c \"import fa_backtest as fb; "
              "fb.run_market_gate(persist=True, persist_dpw=False)\", then the "
              "nightly fa_export carries it into fa_meta.json")


_DPW_TIER_SHAPES = (("lt_1", r"\$(\d+\.\d+)m \(0-1 war\)"),
                    ("1_to_2", r"\$(\d+\.\d+)m \(1-2\)"),
                    ("2plus", r"\$(\d+\.\d+)m \(2\+\)"))


def test_dpw_tier_rates_match_the_valuation_set():
    """The second half of F12-04: the four published $/WAR rates were pinned to
    nothing. They are held to the engine's loaded config (clemens_2026
    win_cost.rates_musd), and any two-decimal $M figure on the card must be one
    of the configured rates."""
    import value_framework

    dpw = value_framework._config()["dollars_per_war"]
    rates = {k: float(v) / 1e6 for k, v in dpw["tiered"]["rates"].items()}
    flat = float(dpw["flat"]) / 1e6
    entry = _glossary_entry("dpw_tier")
    formula = (entry.get("formula") or "").lower()
    problems = []
    for key, pat in _DPW_TIER_SHAPES:
        got = re.findall(pat, formula)
        if not got:
            problems.append(f"formula no longer quotes the {key} tier in the pinned shape")
        problems += [f"formula quotes ${raw}M for {key}; engine {rates[key]:.2f}"
                     for raw in got if abs(float(raw) - rates[key]) > 0.005]
    problems += [f"formula quotes ${raw}M overall; engine {flat:.2f}"
                 for raw in re.findall(r"\$(\d+\.\d+)m overall", formula)
                 if abs(float(raw) - flat) > 0.005]
    allowed = list(rates.values()) + [flat]
    # VAL_1 (owner answer FP2-1, 2026-09-30): the card also quotes the published FanGraphs shape it rescales
    # (the checksummed clemens_2026 win_cost figures) and the winter the level is carried
    # from (pricing.anchor_usd of the one written series). Both are derived, not typed.
    import valuation_sets as vs
    wc = vs.load("clemens_2026")["params"]["win_cost"]
    allowed += [float(v) for v in wc["rates_musd"].values()] + [float(wc["flat_musd"])]
    series = json.loads((Path(value_framework._HERE) / "data" / "fa_dpw_series.json")
                        .read_text(encoding="utf-8"))
    anchor = (series.get("pricing") or {}).get("anchor_usd")
    if anchor:
        allowed.append(float(anchor) / 1e6)
    every = " ".join(v for v in entry.values() if isinstance(v, str)).lower()
    problems += [f"dpw_tier quotes ${raw}M, none of the configured rates {sorted(allowed)}"
                 for raw in re.findall(r"\$(\d+\.\d\d)m\b", every)
                 if not any(abs(float(raw) - a) <= 0.005 for a in allowed)]
    assert not problems, "dpw_tier rate drift: " + "; ".join(problems)


# ---------------------------------------------------------------------------
# M05-09 (2026-09-25): the /projections/ methodology copy described an engine
# that does not serve (the Marcel engine for veterans, escalating $/WAR,
# empirical residual-quantile bands), the accountability banner printed the
# registry's schema date as if it dated the verdicts, and the prospect-path
# registry row quoted a calibration shift, slope, bias and MAE the eval
# artifact no longer reads (0.2673 / 0.726 / +0.11 / 1.384 against 0.1924 /
# 0.633 / 0.037 / 1.362).

def test_projection_copy_describes_the_served_engine():
    import value_framework

    e = _glossary_entry("mlb_projections")
    text = _entry_text(e) + " " + (e.get("formula") or "")
    assert "same Marcel engine" not in text
    assert "proj_lgbm_v1" in text, "the served veteran engine is not named"
    if not float(value_framework._config().get("dollars_per_war_inflation", 0.05)):
        assert "escalating per season" not in text
        assert "escalated per season" not in _read_text("proj_export.py")
    js = _read_text("assets/projections.js")
    assert "empirical residual quantiles" not in js
    assert "model registry ${" not in js, "the registry schema date is not a verdict date"
    assert "Gate-1-validated Marcel engine" not in _read_text("proj_export.py")


def _numbers(obj, out):
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    return out


def test_prospect_path_registry_row_quotes_only_artifact_figures():
    """Every decimal the row's prose quotes must be a number in its eval
    artifact at the quoted precision. The row is rendered on the Model
    Accountability card, so a figure the artifact does not carry is a served
    claim nothing backs."""
    row = _registry_row("mlb_projections_prospects")
    orphans = _orphan_figures(row, ("predicts", "champion", "baseline", "metric", "notes"))
    assert not orphans, f"figures with no source in {row['eval_artifact']}: {orphans}"


def _orphan_figures(row, fields, counts=False):
    """Figures in the row's prose that its eval artifact does not carry: every
    decimal at its quoted precision and, with counts=True, every comma-grouped
    count (1,825) as an integer."""
    have = _numbers(_read_json(row["eval_artifact"]), [])
    text = " ".join(str(row.get(k) or "") for k in fields)
    orphans = []
    for tok in re.findall(r"(?<![\w.])[-+]?\d*\.\d+", text):
        v = float(tok)
        half = 0.5 * 10 ** -len(tok.split(".")[1])
        if not any(abs(abs(v) - abs(h)) <= half + 1e-9 for h in have):
            orphans.append(tok)
    if counts:
        for tok in re.findall(r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?![\d.])", text):
            v = float(tok.replace(",", ""))
            if not any(abs(v - h) <= 0.5 for h in have):
                orphans.append(tok)
    return orphans


# LIBRARY_13_REGISTRY_STALE_FIGURES (2026-10-03): the same rule on the two
# flagship rows whose metric the Library printed with figures the artifact no
# longer carried (consensus_fv AUC 0.7254 vs 0.7130 and Spearman 0.2897 vs
# 0.2883; ewar 1,825 pairs). Their metric now names the artifact key. The
# notes are not scanned: they hold dated readings of superseded artifacts
# (the 2026-06-11 weighted-vs-equal A/B, the 2026-08-04 gate record), which
# the policy keeps as history.
@pytest.mark.parametrize("model_id", ["consensus_fv", "ewar"])
def test_flagship_registry_metric_quotes_only_artifact_figures(model_id):
    row = _registry_row(model_id)
    orphans = _orphan_figures(row, ("predicts", "champion", "baseline", "metric"),
                              counts=True)
    assert not orphans, f"{model_id}: figures with no source in {row['eval_artifact']}: {orphans}"


# ---------------------------------------------------------------------------
# X02-03 (2026-09-25): five entries described the $/WAR bases wrongly. The FA
# rational value called itself "the same NPV currency as PROSPX" while it
# prices a win at the winter level ($17.1M) against the prospect set's flat
# $11.74M; rational value and mGuarantee said the winter level carries at a
# "flat 5%" while fa_export escalates at the series trend (dpw_infl 0.0416),
# and quoted forecast MAPEs (0.122 / 0.132 against 0.102) the eval artifact no
# longer holds; value_framework and surplus_value priced realized value as
# career WAR x a flat $11.74M while PROSPX prices each season at its tier.
# VAL_1 (owner decision FP2-1, same day) then put prospect surplus on the
# winter level too, so the rational_value sentence now states ONE level and the
# tier figures below are the live (rescaled) rates.

def _all_text(entry):
    return " ".join(v for v in entry.values() if isinstance(v, str))


def _money_mm(text):
    return [float(x) for x in re.findall(r"\$(\d+\.\d+)M", text)]


def test_dpw_basis_copy_matches_the_served_bases():
    import value_framework

    cfg = value_framework._config()["dollars_per_war"]
    flat = float(cfg["flat"]) / 1e6
    tiers = [float(v) / 1e6 for v in cfg["tiered"]["rates"].values()]
    fa = _read_json("data/fa_class.json")
    cy = int(fa["class_year"])
    winter = f"{cy - 1}-{cy % 100:02d} winter"
    level = float(fa["dpw_usd"]) / 1e6
    infl_pct = float(fa["dpw_infl"]) * 100
    ev = _read_json("data/dpw_forecast_eval.json")["summary"]
    problems = []

    rv = _all_text(_glossary_entry("rational_value"))
    mg = _all_text(_glossary_entry("m_guarantee"))
    for eid, text in (("rational_value", rv), ("m_guarantee", mg)):
        if re.search(r"flat 5%", text):
            problems.append(f"{eid} still says the winter level carries at a flat 5%")
        for raw in re.findall(r"\((\d+\.\d)%(?: a year)? for the ", text):
            if abs(float(raw) - infl_pct) > 0.05:
                problems.append(f"{eid} quotes a {raw}% carry; fa_class dpw_infl {infl_pct:.2f}%")
        if winter not in text:
            problems.append(f"{eid} does not name the {winter}")
    if "Same NPV currency as PROSPX" in rv:
        problems.append("rational_value claims the prospect surplus currency")
    if "prospect surplus prices at the clemens_2026 set's flat" in rv:
        problems.append("rational_value still discloses a second (prospect) level")
    got = re.findall(r"prices a win at \$(\d+\.\d)M, and since 2026-09-25 prospect surplus "
                     r"and /projections/ price every season at that level too", rv)
    if not got:
        problems.append("rational_value level sentence changed shape")
    for w in got:
        if abs(float(w) - level) > 0.05:
            problems.append(f"rational_value winter level ${w}M; fa_class {level:.3f}")
        if abs(float(w) - flat) > 0.05:
            problems.append(f"rational_value level ${w}M; prospect engine level {flat:.2f}")
    dt = _all_text(_glossary_entry("dpw_tier"))
    if f"${flat:.2f}M" not in dt:
        problems.append(f"dpw_tier does not state the ${flat:.2f}M overall level")
    m = re.search(r"carry[^.]*?MAPE (0\.\d+), a log-linear trend (0\.\d+) and the trend "
                  r"with a CBT covariate (0\.\d+)", mg)
    if not m:
        problems.append("m_guarantee forecast sentence changed shape")
    else:
        for raw, key in zip(m.groups(), ("flat5", "trend", "trend_cbt")):
            if abs(float(raw) - float(ev[key]["mape"])) > 0.0005:
                problems.append(f"m_guarantee {key} MAPE {raw}; artifact {ev[key]['mape']}")

    # CAL_KNOTS_REFIT_17M: the calibration's remeasure label names the level the
    # held-out figures were read at, the published FanGraphs flat the clemens_2026
    # set checksums (derived from the set, as the dpw_tier card already allows it).
    import valuation_sets as vs
    published_flat = float(vs.load("clemens_2026")["params"]["win_cost"]["flat_musd"])
    for eid in ("value_framework", "surplus_value"):
        text = _all_text(_glossary_entry(eid))
        if re.search(r"\$/WAR_overall", text):
            problems.append(f"{eid} prices realized value at a flat $/WAR_overall")
        allowed = tiers + [flat, published_flat]
        for v in _money_mm(text):
            if v < 20 and not any(abs(v - a) <= 0.005 for a in allowed):
                problems.append(f"{eid} quotes ${v}M/WAR, none of the configured rates")
        for t in tiers:
            if f"${t:.2f}M" not in text:
                problems.append(f"{eid} does not state the ${t:.2f}M tier")
    assert not problems, "$/WAR basis copy drift: " + "; ".join(problems)


# SC_HEADLINE_HOLM (owner answers FP3-1 and FP3-3, 2026-09-25). The Source
# Comparison headline moved to the timing-pinned frame vm2 and every surface
# reads it from ONE key: accuracy.head_to_head_verdict, followed through its
# `basis`. And the per-source cells print a verdict word only after a Holm
# correction across the six cells, with the family and alpha on the page.
def test_source_comparison_reads_one_headline_key():
    js = _read_text("assets/glossary.js").replace("\r\n", "\n")
    code = "\n".join(ln for ln in js.split("\n") if not ln.lstrip().startswith("//"))
    for block in ("pooled_efv_common_vintage_matched", "pooled_efv_common_vintage_matched_vm2",
                  "common_n_efv_vintage_matched"):
        assert not re.search(r"\." + re.escape(block) + r"\b", code), (
            f"assets/glossary.js reads accuracy.{block} directly; the headline is "
            "head_to_head_verdict and its basis")
    assert re.search(r"function _hhBlock\(bt\) \{[^}]*acc\[hh\.basis\]", js), (
        "_hhBlock no longer follows head_to_head_verdict.basis")


def test_per_source_verdict_words_come_from_the_holm_family():
    """The per-source table prints the artifact's word or "interval only", and
    the note states the family size and alpha from the artifact, never typed."""
    js = _read_text("assets/glossary.js").replace("\r\n", "\n")
    m = re.search(r"function _methPerSourceCells\(bt\) \{(.*?)\n\}\n", js, re.S)
    assert m, "_methPerSourceCells not found in assets/glossary.js (renamed?)"
    code = "\n".join(ln for ln in m.group(1).split("\n")
                     if not ln.lstrip().startswith("//"))
    assert "leg.verdict" in code and "interval only" in code
    assert "h.k" in code and "h.alpha" in code
    assert not _HARDCODED_DECIMAL_RE.findall(code), (
        "_methPerSourceCells carries a hard-coded accuracy constant")
    bt_path = ROOT / "data" / "source_backtest.json"
    if not bt_path.exists():
        return
    import json as _json
    acc = (_json.loads(bt_path.read_text(encoding="utf-8")).get("accuracy") or {})
    vs = acc.get("head_to_head_vs_sources") or {}
    if not vs.get("holm"):
        return
    assert vs["basis"] == (acc.get("head_to_head_verdict") or {}).get("basis")
    for cell in vs["sources"].values():
        for metric in ("spearman", "auc"):
            leg = cell.get(metric) or {}
            if leg.get("verdict"):
                assert leg["holm"]["reject_holm"] is True, (cell["label"], metric)


# RPR11 (served-number reconciliation, 2026-10-01). The Source Comparison hero
# printed eFV against the best public source (MLB Pipeline on vm2) and then the
# 0.030 floor head_to_head_verdict publishes for eFV against PROSPX CONSENSUS;
# that pair's own floor is 0.0235. The floor printed after a pair's estimate is
# now that pair's floor, so the clause is called with the pair's key, and the
# consensus sentence is called with consensus's key.
# test_source_comparison_hero_floor.py runs the banner on the served artifact.
def test_hero_floor_names_the_pair_it_belongs_to():
    js = _read_text("assets/glossary.js").replace("\r\n", "\n")
    m = re.search(r"function _methHeroBanner\(bt\) \{(.*?)\n\}\n", js, re.S)
    assert m, "_methHeroBanner not found in assets/glossary.js (renamed?)"
    code = "\n".join(ln for ln in m.group(1).split("\n")
                     if not ln.lstrip().startswith("//"))
    assert re.search(r"for the best public source \(\$\{escapeHtml\(bestPub\[0\]\)\}\)"
                     r"[^`]*point estimate\$\{_hhFloorClause\(bt, bestKey\)\}", code), (
        "the hero's best-source estimate is not followed by that pair's floor")
    assert re.search(r"Against PROSPX consensus[^`]*point estimate"
                     r"\$\{_hhFloorClause\(bt, \"prospx_consensus\"\)\}", code), (
        "the consensus sentence is not followed by the consensus floor")
    assert "_hhPairFloor(bt, bestKey)" in code, (
        "the hero's resolvability is not read from the best pair's floor")
    f = re.search(r"function _hhPairFloor\(bt, key\) \{(.*?)\n\}\n", js, re.S)
    assert f, "_hhPairFloor not found in assets/glossary.js (renamed?)"
    assert "head_to_head_vs_sources" in f.group(1) and "vs.basis !== hh.basis" in f.group(1)
    assert not _HARDCODED_DECIMAL_RE.findall(f.group(1)), (
        "_hhPairFloor carries a hard-coded accuracy constant")


# RECON_13 (served-number reconciliation, 2026-10-01): five glossary formulas
# and definitions held to the served artifact or the code constant they
# describe. Each test reads the served file, so the copy cannot drift from the
# object it names without a failure here.

def _admitted_drivers(side_receipt):
    """Driver keys that move a side's order index on the served fit."""
    if not side_receipt or side_receipt.get("consensus_only"):
        return []
    keys = []
    for head, w in (("skill", "w_skill"), ("timing", "w_time")):
        h = side_receipt.get(head) or {}
        if (side_receipt.get(w) or 0) > 0:
            keys += [k for k in h.get("keys") or []
                     if ((h.get("admission") or {}).get(k) or {}).get("admitted", True)]
    return keys


def test_efv_formula_states_the_v2_order_rule_and_the_served_drivers():
    """RPR12. The served board grade is eFV V2 (grade_basis efv_v2): the
    consensus value of the side at the V2 order index. The formula names that
    rule and lists exactly the drivers data/xfv.json's receipt admits; the v1
    formula survives only labelled as the graduates' locked grade."""
    e = _glossary_entry("xfv")
    formula = e["formula"]
    meta = _read_json("data/xfv.json")["meta"]
    assert meta["served_model"]["grade_basis"] == "efv_v2"
    assert "consensus FV value" in formula and "order_idx" in formula
    receipt = meta["served_model"]["receipt"]
    # eFV v5 COMBINED (EW3-10, 2026-10-15) keys carry digits and capitals
    # (scr_g5_hit_A_all_all_k_pct), and the pitcher list ends at a semicolon.
    m = re.search(r"admitted drivers on the served fit \(data/xfv\.json "
                  r"meta\.served_model\.receipt\): hitters ([A-Za-z0-9_, ]+); "
                  r"pitchers ([A-Za-z0-9_, ]+?);", formula)
    assert m, "the eFV formula no longer lists the receipt's admitted drivers"

    def _listed(txt):
        txt = txt.strip()
        return [] if txt == "none" else [k.strip() for k in txt.split(",")]

    assert _listed(m.group(1)) == _admitted_drivers(receipt["hit"]), (
        m.group(1), _admitted_drivers(receipt["hit"]))
    assert _listed(m.group(2)) == _admitted_drivers(receipt["pit"]), (
        m.group(2), _admitted_drivers(receipt["pit"]))
    v1_at = formula.find("outcome_implied_fv")
    assert v1_at > formula.find("GRADUATES AND BUSTS, eFV v1") >= 0, (
        "the v1 formula must sit under its graduates label")


def test_xhem_headline_quotes_the_served_regate_to_two_decimals():
    """RML07. The headline is the served construction (rung D4, v1), quoted to
    two decimals, and the re-gate artifact is named."""
    text = _glossary_entry("xhem_plus")["methodology"]
    d4 = _read_json("data/xhem_served_regate_eval.json")["arms"]["A1_xhem_plus"]["ladder"]["D4"]["v1"]
    m = re.search(r"as served predicts next-year wOBA at a Spearman correlation of "
                  r"(0\.\d\d) against (0\.\d\d) for actual wOBA", text)
    assert m, "xhem_plus headline sentence changed shape"
    assert float(m.group(1)) == round(d4["rho_primary"], 2)
    assert float(m.group(2)) == round(d4["rho_baseline"], 2)
    assert "data/xhem_served_regate_eval.json" in text
    assert "labelled reproduction" in text


def test_hem_and_sem_anchor_copy_names_the_code_pool():
    """RML08. 100 is the pool the code anchors on, not 'qualified' players."""
    import hem_plus
    import sem_plus
    hem = _glossary_entry("hem_plus")["definition"]
    sem = _glossary_entry("sem_plus")["definition"]
    m = re.search(r"hitters with (\d+)\+ plate appearances", hem)
    assert m and float(m.group(1)) == hem_plus.POOL_MIN_PA, hem[:200]
    m = re.search(r"starters with (\d+)\+ innings", sem)
    assert m and float(m.group(1)) == sem_plus.POOL_MIN_IP, sem[:200]
    m = re.search(r"starters with (\d+)\+ innings", _glossary_entry("sem_plus")["formula"])
    assert m and float(m.group(1)) == sem_plus.POOL_MIN_IP
    js = _read_text("assets/mlbstats.js")
    assert f"hitters with {int(hem_plus.POOL_MIN_PA)}+ PA" in js
    assert f"starters with {int(sem_plus.POOL_MIN_IP)}+ IP" in js


def test_rps_draft_copy_states_the_fixed_anchors_and_the_served_centre():
    """RML06. RPS-Draft+ scores fixed college anchors, not a class z. The copy
    quotes the anchors draft_export._college_perf_z applies (recovered by
    calling it) and a class centre the served classes actually sit near."""
    import statistics
    import draft_export as dx

    def z(payload, pitcher=False):
        return dx._college_perf_z({"is_pitcher": pitcher, "trail": [{"payload": payload}]})

    # The anchors the copy quotes, checked against the function itself.
    assert z({"wrc_plus": 100.0}) == 0.0 and z({"wrc_plus": 130.0}) == 1.0
    assert z({"ops": 0.850}) == 0.0 and z({"ops": 1.000}) == 1.0
    assert z({"fip": 4.0}, True) == 0.0 and z({"fip": 2.5}, True) == 1.0
    assert z({"era": 2.5}, True) == 1.0
    e = _glossary_entry("rps_plus")
    meth, form = e["methodology"], e["formula"]
    for frag in ("(wRC+ - 100) / 30", "(OPS - 0.850) / 0.150", "(4.00 - FIP) / 1.5"):
        assert frag in meth and frag in form, frag
    centres = []
    for cls in _read_json("data/draft_timeseries.json")["classes"]:
        vals = [p["rps_draft_plus"] for p in cls.get("prospects") or []
                if p.get("rps_draft_plus") is not None]
        if len(vals) >= 30:
            centres.append(statistics.mean(vals))
    assert centres, "no served draft class carries rps_draft_plus"
    m = re.search(r"a class averages about (\d+)", meth)
    assert m, "rps_plus methodology no longer states the class centre"
    assert all(abs(float(m.group(1)) - c) <= 2.0 for c in centres), (m.group(1), centres)


def test_fa_floor_copy_discloses_the_zero_floor():
    """RVA04. /fa/ season P10 is the Gate-1 band decayed through a path that
    stops at zero; while any served season P10 sits at exactly 0.0 the
    glossary formula and the warbar tooltip must say so."""
    members = _read_json("data/fa_class.json").get("members") or []
    if not any(v == 0.0 for m in members for v in (m.get("warPathP10") or [])):
        pytest.skip("no served /fa/ season P10 at exactly 0.0")
    formula = _glossary_entry("proj_buckets")["formula"]
    fa_line = [ln for ln in formula.split("\n") if ln.startswith("/fa/: season floor")]
    assert fa_line and "truncated at 0 WAR" in fa_line[0], fa_line
    js = _read_text("assets/fa.js")
    assert "season P10, floored at 0 WAR" in js
    assert len(formula.split("\n")) == len(set(formula.split("\n"))), "duplicate formula line"

def test_next_to_be_graded_lens_prints_only_the_track_record_figures():
    """Part 8 W04 (2026-10-07). The Dynasty lens Next to be graded prints the
    AUC against its level-rank null, the counts, the freeze date and size, the
    window end and the level-skill figures, all from the claim block the
    exporter copies out of data/provisional_track_eval.json. Each printed
    figure must equal the artifact's own value on the row the block names, and
    the block must be the one the current artifact yields."""
    side_p = ROOT / "data" / "fantasy_next_graded.json"
    if not side_p.exists():
        pytest.skip("the Next to be graded sidecar is not built in this tree")
    import fantasy_export as fe
    side = _read_json("data/fantasy_next_graded.json")
    track = _read_json("data/provisional_track_eval.json")
    claim = side.get("claim") or {}
    assert claim == fe._next_graded_claim(track), "the lens claim block is stale against the artifact"
    rows = {r["run_id"]: r for r in track.get("rows") or []}
    retro, fwd = claim.get("retro") or {}, claim.get("forward") or {}
    assert retro and fwd, claim
    a = rows[retro["run_id"]]["result"]["ANY"]
    assert retro["auc"] == a["selection"]["grade"]["auc"]
    assert retro["auc_null_level"] == a["selection"]["null_level_rank"]["auc"]
    assert (retro["n"], retro["graded"]) == (a["n"], a["graded_in_window"])
    lev = a["level"]["grade"]
    assert (retro["spearman"], retro["mae"], retro["mae_null"], retro["null_const"]) == (
        lev["spearman"], lev["mae"], lev["mae_null_const"], lev["null_const"])
    assert retro["frozen_at"] == rows[retro["run_id"]]["frozen_at"]
    f = rows[fwd["run_id"]]
    assert (fwd["frozen_at"], fwd["window_end"], fwd["n_rows"], fwd["graded"]) == (
        f["frozen_at"], f["window_end"], f["result"]["n_rows"], f["result"]["ANY"]["graded_in_window"])


def test_next_to_be_graded_copy_types_no_figure():
    """The lens copy functions in assets/dynasty.js carry no typed decimal and
    no typed date: every figure in them is read from the payload."""
    src = _read_text("assets/dynasty.js")
    for name in ("nextTrackHTML", "renderNextGraded"):
        m = re.search(r"^  function %s\([^)]*\) \{.*?\n  \}\n" % name, src, re.S | re.M)
        assert m, name
        code = "\n".join(ln for ln in m.group(0).split("\n") if not ln.lstrip().startswith("//"))
        assert not re.findall(r"(?<![\w.#-])\d+\.\d+(?![\w.])", code), name
        assert not re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", code), name
        for n in ("0.826", "0.615", "6.21", "4.54", "6,066", "5,631"):
            assert n not in code, (name, n)


def test_league_tab_coverage_and_fold_copy_type_no_figure():
    """Q8_13a (final-pass plan Part 8 P8.2, LT-08). The League tab's coverage
    sentence and its fold copy print counts, floors, dates and games per club,
    and every one of them is read from the season panel: the functions that
    write them carry no digit at all, so a typed count, floor or season cannot
    hide in them. The one numeral allowed is the + scale's own anchor, which is
    a definition (the page header states it too), not a measurement."""
    src = _read_text("assets/mlbstats-league.js").replace("\r\n", "\n")
    for name in ("coverageHTML", "foldHTML", "seasonNote", "indexNote"):
        m = re.search(r"^  function %s\([^)]*\) \{.*?\n  \}\n" % name, src, re.S | re.M)
        assert m, name
        code = "\n".join(ln for ln in m.group(0).split("\n") if not ln.lstrip().startswith("//"))
        code = code.replace("100 is the average qualified player of that board", "")
        assert not re.search(r"\d", code), (name, re.findall(r".{0,30}\d.{0,10}", code)[:5])
    # the floors, the coverage counts and the reasons come from these payload keys
    for key in ("qualify", "coverage", "n_hand", "n_index", "games_per_team", "left_out", "deferred"):
        assert key in src, key


def test_teams_tab_copy_types_no_figure():
    """Q8_13b (final-pass plan Part 8 P8.2, LT-08, the Teams half). The Teams
    tab's freshness line, basis note, league weighted means, coverage sentence
    and fold print dates, counts and the league's own weighted mean of each
    rollup, and every one of them is read from the Team Stats payload: the
    functions that write them carry no digit, so a typed mean (the lane read
    99.85, 102.09, 101.62, 100.81 at 64bf1bb3) cannot hide in them."""
    src = _read_text("assets/mlbstats-league.js").replace("\r\n", "\n")
    for name in ("tFreshHTML", "tMeansLine", "tBasisNote", "tCoverageHTML", "tFoldHTML"):
        m = re.search(r"^  function %s\([^)]*\) \{.*?\n  \}\n" % name, src, re.S | re.M)
        assert m, name
        code = "\n".join(ln for ln in m.group(0).split("\n") if not ln.lstrip().startswith("//"))
        assert not re.search(r"\d", code), (name, re.findall(r".{0,30}\d.{0,10}", code)[:5])
    for n in ("99.85", "102.09", "101.62", "100.81", "99.87", "102.1", "101.54", "100.79"):
        assert n not in src, n
    # the means and the coverage come from these payload keys
    for key in ("offense_plus_pa_weighted", "rotation_plus_ip_weighted", "bullpen_plus_ip_weighted",
                "team_dem_plus_inn_weighted", "coverage", "offense_pa", "league_ip", "past_seasons"):
        assert key in src, key


def test_pitch_rate_copy_figures_are_derived_or_worked():
    """Q8_06 (owner asks 10 to 12 and 17 of 2026-09-30, the flip of P/IP, P/BF,
    P/PA and PAR). Every figure the new copy prints is either a worked example
    whose arithmetic holds, or the club count read off the served artifact."""
    pip = _glossary_entry("p_ip")
    assert "96 pitches over 18 outs (6 innings) = 16.0 P/IP" in pip["example"]
    assert round(96 / (18 / 3), 1) == 16.0
    assert "a line of 6.1 is 19 outs, 6.33 innings" in pip["methodology"]
    assert round(19 / 3, 2) == 6.33
    pbf = _glossary_entry("p_bf")
    assert "96 pitches to 25 batters = 3.84 P/BF" in pbf["example"]
    assert round(96 / 25, 2) == 3.84
    ppa = _glossary_entry("p_pa")
    assert "2,550 pitches in 650 PA = 3.92 P/PA" in ppa["example"]
    assert round(2550 / 650, 2) == 3.92
    par = _glossary_entry("par")
    m = re.search(r"at ([\d.]+) P/IP in a season when starts averaged ([\d.]+): "
                  r"PAR = 100 x \1 / \2 = (\d+), or ([\d.]+) fewer", par["example"])
    assert m, par["example"]
    rate, anchor, idx, gap = float(m.group(1)), float(m.group(2)), int(m.group(3)), float(m.group(4))
    assert int(100 * rate / anchor + 0.5) == idx
    assert round(anchor - rate, 1) == gap
    # 100 is average and 110 is 10 percent more: the ratio definition itself
    assert "100 is average, 110 is 10 percent more pitches" in par["definition"]


def test_pitch_rate_copy_thirty_clubs_is_the_served_club_count():
    """The glossary, the registry row and the /mlbstats/ team title say Team PAR
    compares a club with "the average of the 30 clubs". Pinned to the served
    artifacts: every unit of the latest season carries 30 clubs whose exact team
    PAR averages 100, and each board's team table stamps 30 clubs."""
    assert "the average of the 30 clubs" in _glossary_entry("par")["methodology"]
    assert "the mean of the 30 club values" in _registry_row("par")["predicts"]
    assert "the average of the 30 clubs" in _read_text("assets/mlbstats.js")
    pr = _read_json("data/pitch_rates.json")
    latest = max(pr["teams"]["mlb"], key=int)
    for unit, clubs in pr["teams"]["mlb"][latest].items():
        exact = [c["par_exact"] for c in clubs.values() if c["par_exact"] is not None]
        assert len(exact) == 30, (unit, len(exact))
        assert abs(sum(exact) / 30 - 100.0) < 1e-2, unit
    for board, key in (("starter_leaderboards", "rot_par"), ("bullpen_leaderboards", "pen_par"),
                       ("hitter_leaderboards", "lineup_par")):
        teams = _read_json(f"data/{board}.json")["teams"]
        assert sum(t.get(key) is not None for t in teams) == 30, board

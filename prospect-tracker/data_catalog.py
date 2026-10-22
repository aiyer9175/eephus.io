# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The public data catalog: what eephus.io publishes under /data/, and how solid it is.

WHY THIS EXISTS
---------------
/diamond/ advertised "data exports and a JSON API on a documented schema" and no
such document existed. The artifacts were already public (the deploy ships
data/*.json to the webroot), so the missing piece was never an endpoint, it was
the documentation: which files are safe to build on, what is in each one, how
often it changes, and which parts can move under you.

WHAT MAKES A CLAIM ON THIS PAGE HONEST
---------------------------------------
Three mechanisms, because a hand-written table of artifacts rots the moment
someone renames a file:

  1. SHIPPING IS VERIFIED, NOT ASSERTED. deploy/data_exclude.txt is the list of
     data files the deploy deliberately withholds from the webroot (model
     internals, pipeline inputs). Anything on that list is dropped from the
     catalog here rather than advertised, so this page cannot point a reader at
     a URL that 404s in production. That is the 2026-07-14 incident class, and
     it is not one we get to repeat on a page whose whole subject is what we
     publish.
  2. PRESENCE IS VERIFIED. A catalog row whose file is not in the tree is
     dropped. A first-run checkout or a retired artifact narrows the table
     instead of publishing a dead link.
  3. THE STABILITY CLAIM CARRIES ITS RECEIPT. `pinned_by` names the test that
     asserts the artifact's shape, and it is only rendered when that file
     exists AND actually mentions the artifact by name. Delete the test and the
     receipt disappears from the page by itself.

THE TWO STABILITY TIERS, STATED THE WAY THE PIPELINE CAN ACTUALLY KEEP THEM
----------------------------------------------------------------------------
  stable       Shipped for months and consumed by a live page, so a rename
               breaks the site before it breaks you. Fields get ADDED without
               warning; existing field names and meanings do not change
               silently. Where a test in this repo pins the shape, the row
               names it. A blank receipt means the habit, not a test, is what
               is holding the field names steady, and the row says so by
               leaving the column empty rather than by claiming a test.
  experimental Model labs, eval sidecars, and anything under active
               construction. The shape can change or the file can disappear on
               any run. Read it, but do not build a product on it.

Deliberately NOT claimed anywhere: a version header, a deprecation window, an
uptime target, or a rate limit. These are static files behind a CDN, written by
a nightly pipeline that sometimes fails. Promising a guarantee the pipeline
cannot keep is the same defect as the unbacked feature card this catalog was
built to retire.
"""

from __future__ import annotations

from pathlib import Path

import ewar_v3 as _ewar_v3_mod

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EXCLUDE_LIST = ROOT / "deploy" / "data_exclude.txt"

STABLE = "stable"
EXPERIMENTAL = "experimental"

# Public base for every row below. The deploy rsyncs data/*.json into the
# webroot verbatim, so the served URL is the repo path with no rewriting.
DATA_BASE_URL = "/data/"

# Groups, in the order the page renders them.
GROUPS = (
    ("prospects", "Prospects and the eFV model"),
    ("mlb", "MLB players, projections and free agency"),
    ("diamond", "Fantasy, DFS and betting"),
    ("reference", "Reference and model accountability"),
)

# THE CATALOG.
#
# `what` is what a consumer gets, not what the model does; the methodology
# lives in /glossary/ and the eval artifacts. `cadence` is the pipeline path
# that writes the file: "daily" = run_monthly.run_daily (every nightly),
# "monthly" = run_monthly.main, "on change" = written only when its input is
# re-staged. `pinned_by` is a test in this repo that asserts the shape; it is
# verified before it is rendered (see catalog_rows).
ARTIFACTS = (
    # ---- prospects -------------------------------------------------------
    {
        "file": "timeseries.json", "group": "prospects",
        "title": "The prospect board",
        "what": ("Every tracked prospect: the consensus FV timeline with per-source grades at "
                 "each snapshot, the de-noised movement block, surplus value, tool grades, "
                 "current statline and org rollups. This is the file the PROSPX board runs on."),
        "cadence": "daily", "stability": STABLE,
        "pinned_by": "test_storage_export.py",
        "note": ("Large. For grades or movement only, use a smaller artifact below."),
    },
    {
        "file": "xfv.json", "group": "prospects",
        "title": "eFV grades",
        "what": ("The eFV model's grade for every player it will grade, keyed by player_key, "
                 "plus the model metadata block. `xfv_grade` is THE board number: the same "
                 "value the board displays, sorts and ranks on."),
        "cadence": "daily", "stability": STABLE,
        "pinned_by": "test_efv_export.py",
        "note": ("Read `xfv_grade`. The older per-side quantile and realized fields are kept "
                 "for compatibility and are not what the board serves."),
    },
    {
        "file": "xfv_history.json", "group": "prospects",
        "title": "eFV trajectory",
        "what": ("Per player, the eFV grade over time as {d, x, c} points (date, eFV, "
                 "consensus), with the grade basis the series was built on stamped at the top."),
        "cadence": "daily", "stability": STABLE,
        "pinned_by": "test_board_basis_coherence.py",
        "note": ("Check `basis` before differencing across a long window: a basis change is a "
                 "grade-scale change, not player movement."),
    },
    {
        "file": "efv_alerts.json", "group": "prospects",
        "title": "eFV movement alerts feed",
        "what": ("The biggest board eFV moves on the latest rebuild, with the driving "
                 "explainer where the movement engine has one, each row flagged for whether an "
                 "endpoint sits on the model floor."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "",
        "note": ("Feed only. `delivery` reads \"not_wired\": nothing is emailed or pushed from "
                 "this file yet."),
    },
    {
        "file": "xfv_ungraded.json", "group": "prospects",
        "title": "Provisional grades (unscouted players)",
        "what": ("Model grades for players no public source has graded, so a breakout with no "
                 "list appearance still carries a number."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ungraded_orphan_routing.py",
        "note": "Provisional by construction. Treated as a floor, not a published grade.",
    },
    {
        "file": "debuts_lite.json", "group": "prospects",
        "title": "Graduated prospects",
        "what": ("Prospects who have debuted, with their board history and what they have done "
                 "in the majors since. The slim companion to the full debuts artifact."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_storage_export.py",
        "note": "",
    },
    {
        "file": "player_links.json", "group": "prospects",
        "title": "Identity map",
        "what": ("The cross-module join: player_key to MLBAM id and back, with the display name "
                 "and current org. Every other artifact keys off one of these two."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_mlb_player_pages.py",
        "note": ("Start here when joining two artifacts. Identity resolution is the binding "
                 "constraint on this data, not volume."),
    },
    {
        "file": "draft_timeseries.json", "group": "prospects",
        "title": "Draft classes",
        "what": "Draft boards by class with pick, bonus, slot value and the post-draft grade path.",
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_lottery_extra_fields.py",
        "note": "",
    },
    {
        "file": "ifa_timeseries.json", "group": "prospects",
        "title": "International amateur classes",
        "what": "IFA signing classes with bonuses and the grade path after signing.",
        "cadence": "monthly", "stability": STABLE, "pinned_by": "test_intl_amateur.py",
        "note": "",
    },
    {
        "file": "overseas_timeseries.json", "group": "prospects",
        "title": "Overseas leagues",
        "what": "NPB, KBO and CPBL players tracked toward a possible MLB move.",
        "cadence": "monthly", "stability": STABLE, "pinned_by": "test_overseas_regression.py",
        "note": "",
    },
    {
        "file": "source_cohort_accuracy.json", "group": "prospects",
        "title": "Source accuracy by cohort",
        "what": ("Per-source accuracy by player type. "
                 "FanGraphs minus MLB Pipeline rank correlation against realized WAR, per "
                 "archetype, side, acquisition path, position group, FV tier and age at grading, "
                 "each cell carrying its own 95 percent minimum detectable effect, plus the "
                 "cohort-weight A/B, its permutation control and its oracle ceiling."),
        "cadence": "monthly", "stability": EXPERIMENTAL,
        "pinned_by": "test_source_cohort_accuracy.py",
        "note": ("Read `mde95` before reading any `d_rho`: most cells cannot resolve a winner and "
                 "say so in `answerable`. No source weight ships from this file."),
    },
    {
        "file": "tool_source_accuracy.json", "group": "prospects",
        "title": "Tool grade accuracy by source",
        "what": ("Look W of the tool-implied production gate, as the Source Accuracy Tools tab "
                 "prints it: per primary tool the equal and accuracy-weighted Spearman rho, "
                 "their difference, the permutation p and the runner's verdict; per source and "
                 "tool the ordering rho, bias (mean regressed tool above grade and mean "
                 "percentile minus 0.5) and error, with n and the not-computable notes."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_source_accuracy_tools_tab.py",
        "note": ("A display copy of the spent look record tool_accuracy_eval.json, written by "
                 "tools/tool_accuracy_lab.py --export-display without a re-run. Accuracy among "
                 "players who reached the majors. No source weight ships from this file."),
    },
    {
        "file": "xfv_side_calibration_eval.json", "group": "prospects",
        "title": "Pitcher and hitter grades at equal FV",
        "what": ("Why eFV ranks few pitchers near the top: the pitcher grade audit. "
                 "It answers with outcomes rather than "
                 "with a comparison to another board, because a source is not over-grading "
                 "pitchers by disagreeing with us, only by disagreeing with what those "
                 "pitchers produced. Mean realized first-six-year WAR by side within each "
                 "grade band, for the served eFV grade and for consensus FV, on the resolved "
                 "pool with players who never reached the majors carried at zero."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_side_calibration_lab.py",
        "note": ("The served eFV grade is retrospective on this pool, so this measures the "
                 "SHIPPED grade map against outcomes and is NOT an out-of-sample forecast. "
                 "Cells under 30 rows a side are reported and not scored; the top pitcher "
                 "cells are thin by construction and that emptiness is the finding rather "
                 "than a cell to score."),
    },
    {
        "file": "xfv_denoised_baseline_eval.json", "group": "prospects",
        "title": "eFV vs a rebuilt consensus",
        "what": ("The fairness control behind the head-to-head claim. eFV is normally compared "
                 "against the consensus AS SERVED, so part of its lead could be eFV beating the "
                 "blending rather than beating the scouts. This rebuilds the consensus from "
                 "measured per-source precision and re-runs the comparison on identical rows, "
                 "under both registered noise-floor estimators, with the decision rule fixed in "
                 "advance and two adversarial reweighting controls."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_denoised_baseline_lab.py",
        "note": ("`basis.vintage_disciplined` is FALSE by construction and the number must never "
                 "be quoted as out of sample: per-source precision is estimable only for board "
                 "years 2023-2026, so the baseline is defined using rows it also scores. Read "
                 "`primary_corrected_amendment_2`, not `primary_as_registered`."),
    },
    {
        "file": "xfv_headtohead_frame_eval.json", "group": "prospects",
        "title": "Which frame the head-to-head is scored on",
        "what": ("eFV carries one grade per player, fitted at that player's decision year, "
                 "while the common set carries a consensus read for every base year. That "
                 "makes the comparison frame a choice, and the choice decides the answer. "
                 "This scores three frames inside the same bootstrap draws: every base year, "
                 "post-debut reads removed, and base year equal to the decision year. Each "
                 "gets its own floor."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_headtohead_frame.py",
        "note": ("The middle frame is the only one that clears a floor and it is deliberately "
                 "not the headline: it removes the rows where the consensus is advantaged "
                 "while keeping those where eFV is, so its margin is partly an artifact of "
                 "that asymmetry. Read `vintage_matched`, which is the symmetric contest and "
                 "reads a tie at the smallest floor of the three."),
    },
    # ---- MLB -------------------------------------------------------------
    {
        "file": "mlb_projections.json", "group": "mlb",
        "title": "MLB projections",
        "what": ("Five-year eWAR paths for every MLB player with floor / mean / ceiling buckets, "
                 "surplus over the whole club control window, and prospects joining at their ETA."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_proj_export.py",
        "note": "",
    },
    {
        "file": "mlb_player_detail.json", "group": "mlb",
        "title": "MLB player detail",
        "what": "Per-player career lines, splits and the context blocks the player cards render.",
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_mlb_player_pages.py",
        "note": "",
    },
    {
        "file": "fa_class.json", "group": "mlb",
        "title": "Free agent class",
        "what": ("The upcoming free-agent class: projected years, guarantee and AAV with "
                 "floor-mean-ceiling bands, rational value against predicted price, and the "
                 "deal verdict."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_fa_edges.py",
        "note": "",
    },
    {
        "file": "xm_players.json", "group": "mlb",
        "title": "xM$ and Fair $ by player",
        "what": ("Every 40-man player priced as if a free agent this winter: xM$ years, "
                 "AAV and NPV guarantee with P10 and P90 from the /fa/ market model, Fair $ "
                 "at the same term, the counterfactual and support-clip flags, and each "
                 "player's market-rate surplus over his priced control seasons. Every board "
                 "prospect shows Fair $ only, the NPV of his eFV WAR path, with xM$ withheld "
                 "as outside the market model's range. Keyed by MLBAM id (40-man) or player "
                 "key (prospect)."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_xm_export.py",
        "note": ("Data only: no page shows it yet. Counterfactual rows carry no accuracy "
                 "claim; a free agent's row copies the /fa/ class board."),
    },
    {
        "file": "xm_clubs.json", "group": "mlb",
        "title": "xM$ club roll-ups",
        "what": ("Per club: the 40-man xM$ AAV sum beside Spotrac's payroll figures (not a "
                 "payroll projection), the market-rate surplus over control (Franchise and "
                 "Trade Machine only, never the Ledger), the farm Fair $ total over every "
                 "board prospect and each Fair $ counterpart, with the player ids every sum "
                 "is taken over."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_xm_export.py",
        "note": ("Data only: no page shows it yet. Every club figure equals the sum of its "
                 "listed player rows; quantiles are never summed."),
    },
    {
        "file": "fa_archive.json", "group": "mlb",
        "title": "Archived winters",
        "what": "Past free-agent winters with the realized-surplus ledger for each signing.",
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_fa_tier1.py",
        "note": "",
    },
    {
        "file": "hitter_leaderboards.json", "group": "mlb",
        "title": "Hitter leaderboards",
        "what": "Season hitter board with HEM+, wRC+ and the team Offense+ rollup.",
        "cadence": "monthly", "stability": STABLE,
        "pinned_by": "test_hitter_export_contract.py", "note": "",
    },
    {
        "file": "starter_leaderboards.json", "group": "mlb",
        "title": "Starter leaderboards",
        "what": "Season starter board with SEM+, RIV+ and the team Rotation+ rollup.",
        "cadence": "monthly", "stability": STABLE,
        "pinned_by": "test_starter_export_contract.py",
        # F05-02: the key cannot be renamed (build_site and assets/fa.js read
        # it), so the catalog says what it holds.
        "note": ("`fip` is Skill FIP, the sample-shrunk FIP with a starter-pool "
                 "constant that SEM+ is built on, not the standard FIP."),
    },
    {
        "file": "bullpen_leaderboards.json", "group": "mlb",
        "title": "Bullpen leaderboards",
        "what": "Season reliever board with REM+, leverage context and the team Bullpen+ rollup.",
        "cadence": "monthly", "stability": STABLE, "pinned_by": "test_bullpen_export.py",
        "note": ("`fip` is Skill FIP, the sample-shrunk FIP with a reliever-pool "
                 "constant that REM+ is built on, not the standard FIP."),
    },
    {
        "file": "defense_leaderboards.json", "group": "mlb",
        "title": "Defense leaderboards",
        "what": ("Season fielder board with DEM+, published fielding and framing runs, "
                 "and the team DEM+ rollup with each club's defensive alignment."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_defense_export_contract.py",
        "note": ("Fielding, framing and positional runs are FanGraphs' published values "
                 "read from MLB's feed; DEM+ is on the 100 + 10z ruler, not the HEM+ "
                 "ratio scale."),
    },
    {
        "file": "baserunning_leaderboards.json", "group": "mlb",
        "title": "Baserunning leaderboards",
        "what": ("Season runner board with eBR and its steal, extra-base and double-play "
                 "parts, official counts, published BsR and Savant values, and the team eBR "
                 "rollup."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_baserunning_export_contract.py",
        "note": ("eBR is descriptive runs above average on the bases from MLB's "
                 "play-by-play; BsR, wSB and Savant's run values are published values "
                 "read, not computed here."),
    },
    {
        "file": "baserunning_history.json", "group": "mlb",
        "title": "Baserunning history",
        "what": "The Baserunning runner board for each completed season with a runner record.",
        "cadence": "monthly", "stability": EXPERIMENTAL,
        "pinned_by": "test_baserunning_export_contract.py",
        "note": "Seasons 2018, 2019 and 2021 to 2025; 2020 has no play-by-play on disk.",
    },
    {
        "file": "ebr.json", "group": "mlb",
        "title": "eBR substrate",
        "what": ("One row per player-season with the five eBR parts, per-club stints, "
                 "league blocks and each season's RE24 cells."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ebr_substrate.py",
        "note": "The numbers the Baserunning board and the MLB player card read; descriptive.",
    },
    {
        "file": "ebr_eval.json", "group": "mlb",
        "title": "eBR evaluation",
        "what": ("Identity receipts, coverage, same-season agreement bands, join rates and "
                 "the registered look's dispositions, guard flags and floors."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ebr_served_eval.py",
        "note": "Carries no correlation against runs or wins.",
    },
    {
        "file": "ewar_v3.json", "group": "mlb",
        "title": "eWAR parts",
        "what": ("Per player-season and side, the parts by which eWAR and eWAR realized depart "
                 "from FanGraphs' published WAR (the ABS challenge part from 2026 in both; "
                 "realized pitching from 2016 in eWAR realized only"
                 + ("; half of the xHEM+ batting part from 2016 in eWAR only, provisional"
                    if _ewar_v3_mod.XHEM_HALF_LIVE else "") + "), with each season's "
                 "identity checks and runs per win. A player-season not listed equals "
                 "FanGraphs WAR."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_ewar_v3.py",
        "note": "Every part sums to zero per season and side; descriptive, no forward claim.",
    },
    {
        "file": "swar_eval.json", "group": "mlb",
        "title": "eWAR skill-part evaluation",
        "what": ("The registered skill look's record for eWAR's candidate skill parts "
                 "(batting, pitching, fielding and the positional ladder): its frame, "
                 "parameters, cells, floors, the holdout block and the guard flags."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "",
        "note": ("A filtered copy of the tracked record in docs/ebr-2026-09-30/; carries no "
                 "correlation against club runs or wins."),
    },
    {
        "file": "ebr_milb.json", "group": "prospects",
        "title": "Level-relative eBR",
        "what": ("Per player, one row per minor-league level and season at 150 or more plate "
                 "appearances: baserunning runs against an average runner at the same level in "
                 "the same season, split into steals, extra bases and double plays."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ebr_milb.py",
        "note": ("Level-relative: not comparable across levels or with the majors. Display only; "
                 "no grade, rank or projection reads it."),
    },
    {
        "file": "ebr_milb_eval.json", "group": "prospects",
        "title": "Level-relative eBR evaluation",
        "what": ("Identity receipts against the official minor-league season lines, each "
                 "level-season's run basis, split-half reliability, cross-level continuity and "
                 "the wild-pitch and passed-ball sub-totals."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ebr_milb.py",
        "note": "Aggregates only; carries no outcome, grade or consensus-FV cell.",
    },
    {
        "file": "prospect_statline.json", "group": "prospects",
        "title": "Prospect arrival line",
        "what": ("Per hitter prospect, the rates projected over his first three MLB seasons if he "
                 "reaches the majors, with P10 and P90, for the stats that passed the one-time "
                 "holdout check, and the tool-implied value of his grade where the stat has one."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_prospect_statline.py",
        "note": ("Conditional on reaching the majors, checked only on players who did. The WAR "
                 "projection and eFV do not read it."),
    },
    {
        "file": "prospect_statline_eval.json", "group": "prospects",
        "title": "Prospect arrival line evaluation",
        "what": ("The one look on debut classes 2022 to 2024: per stat the model's error against "
                 "its best baseline with a bootstrap lower bound and band coverage, and the WAR "
                 "comparison against the FV-anchored path."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_prospect_statline.py",
        "note": "Accuracy among players who reached the majors, not over all prospects.",
    },
    {
        "file": "war_leaderboards.json", "group": "mlb",
        "title": "eWAR leaderboard",
        "what": ("Every player with a season eWAR cell, batting and pitching summed "
                 "before rounding, with the club rollup on two bases: the roster "
                 "today and the club the eWAR was earned for."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_war_board_export_contract.py",
        "note": ("`war` is the only summed value we publish: the five player "
                 "boards each carry one side, because the rate columns beside "
                 "them divide by that side's denominator."),
    },
    {
        "file": "war_seasons.json", "group": "mlb",
        "title": "eWAR per season",
        "what": ("One row per player-season over the whole eWAR window, with the "
                 "batting and pitching sides kept apart and the clubs of "
                 "production beside them. The eWAR board's Current view is this "
                 "file folded at the live season."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_windows.py",
        "note": ("Built in the same run as war_leaderboards.json, so a year "
                 "range and the Current view agree. Rows are positional, by the "
                 "payload's own `fields`; a window sums the two sides unrounded "
                 "and rounds once."),
    },
    {
        "file": "trade_realized.json", "group": "mlb",
        "title": "Trade Audit realized WAR",
        "what": ("Per-stint season eWAR for every player on the Trade Machine board, "
                 "so the PROSPX Transactions Trade Audit can show what each club "
                 "got after a trade, beside the value-today verdict."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_trade_audit_realized.py",
        "note": ("Rows are [season, club, stint, side, war], on the displayed eWAR v2 "
                 "basis, with the flat $/WAR the trade value uses stored beside them. "
                 "A stint frame has no calendar dates, so the page credits a receiving "
                 "club the stints after the sending club's stint in the trade season "
                 "and every later stint. No row means no MLB time, counted as zero."),
    },
    {
        "file": "trade_audit_deals.json", "group": "mlb",
        "title": "Trade Audit deal list",
        "what": ("Every real deal the PROSPX Transactions Trade Audit prices, one row "
                 "per deal with each party's value today and realized-to-date leg, "
                 "for the Trade Machine's Comparable real trades panel."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_trade_comps.py",
        "note": ("Rebuilt by trade_audit_export.py with the audit page's own rules and "
                 "pinned against its served cards. Values are today's trade values, "
                 "not the deal date's; a party with no trade value counts $0 and is "
                 "named. No verdict is stored."),
    },
    {
        "file": "mlbstats_windows.json", "group": "mlb",
        "title": "Multi-year windows (index)",
        "what": ("Which multi-season windows the lab built, what each window's "
                 "index pool is (n, mean, sd), the qualified rule per "
                 "board, and every column's treatment: summed, pooled over a "
                 "named denominator, recomputed as an index, or hidden with its "
                 "reason."),
        "cadence": "monthly", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_windows.py",
        "note": ("A window index is the denominator-weighted mean of the "
                 "per-season index, each season scored against its own pool, "
                 "which is the recipe the shipped three-year columns use. So 100 "
                 "is not this window's average and ten points is not its "
                 "standard deviation: pool_stats says what they are, and no "
                 "value ruler is carried onto a window."),
    },
    {
        "file": "mlbstats_window_l3.json", "group": "mlb",
        "title": "Multi-year window: last 3 seasons",
        "what": ("All six /mlbstats/ boards over the trailing three seasons: "
                 "counts summed, rates pooled once over their own denominator, "
                 "HEM+ / SEM+ / REM+ / RIV+ / DEM+ / WAR-rate recomputed for the "
                 "window with the seasons and denominator behind each value."),
        "cadence": "monthly", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_windows.py",
        "note": ("This is the window the shipped *_3yr columns are already on, "
                 "so the index blocks can be checked against a column that "
                 "ships; the check is on mlbstats_windows.json under "
                 "`reproduction`."),
    },
    {
        "file": "mlbstats_window_l5.json", "group": "mlb",
        "title": "Multi-year window: last 5 seasons",
        "what": "The same six boards over the trailing five seasons.",
        "cadence": "monthly", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_windows.py",
        "note": ("Five is the longest window that contains no 2020, which every "
                 "index lab excludes, and no season outside the feed coverage of "
                 "all six boards."),
    },
    {
        "file": "mlb_league_panel_*.json", "group": "mlb",
        "title": "League Averages, one season",
        "what": ("One row per player-season (2000 on) with the counts, own hand, age, "
                 "role and served index values, plus the pooled League value and the "
                 "player distribution of every group the League tab filters by."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_league_averages_export.py",
        "note": ("Completed seasons are written once; the live season nightly."),
    },
    {
        "file": "mlb_league_series.json", "group": "mlb",
        "title": "League Averages over time",
        "what": ("Every League Averages statistic by season, 2000 on, for the fixed "
                 "over-time cells (positions, own hand, age bands, roles, leagues, the "
                 "role-innings cells and the club mean and SD)."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_league_averages_export.py",
        "note": ("Rebuilt with the season panels. League Trends reads it by series_ref "
                 "and never re-pools it."),
    },
    {
        "file": "mlb_team_stats.json", "group": "mlb",
        "title": "Team Stats, one season",
        "what": ("The thirty clubs with the EM+ team rollups on two club bases (club "
                 "today, copied from the boards; earned, by stint), the record, MLB's "
                 "expected record, pitch counts with team PAR, lineup depth and the "
                 "management club tendencies, plus the completed seasons since 2000."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_team_stats_export.py",
        "note": ("Written nightly right after the F-SCORE step; the completed seasons "
                 "carry the earned basis only."),
    },
    {
        "file": "mlbstats_trends.json", "group": "mlb",
        "title": "Player index by season",
        "what": ("Every player's HEM+, SEM+ or REM+, DEM+ and batter WPA by season, "
                 "2016 on, with the season's plate appearances, innings or position: "
                 "the trend lines of the /mlbstats/ player drawer."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_trends_export.py",
        "note": ("Read from the window lab's season panels, the live boards and the "
                 "qualified history files; refused when a lab panel and a history file "
                 "disagree on a shared player-season."),
    },
    {
        "file": "mlbstats_player_index.json", "group": "mlb",
        "title": "Player game files (index)",
        "what": ("Which live-board players have a game file, how far the play-by-play "
                 "frame reaches (covers_through) against the boards' last game, and how "
                 "the summed games reconcile with each board."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_rolling_export.py",
        "note": ("The game files are refused, keeping the last good ones, only when "
                 "the frame's last game date is more than two days behind the boards' "
                 "last game date: game dates, never build stamps."),
    },
    {
        "file": "mlbstats_player/*.json", "group": "mlb",
        "title": "Player game files",
        "what": ("One file per live-board player: raw counts game by game (hitters "
                 "PA, AB, H, 2B, 3B, HR, BB, HBP, SF, SO, pitches; pitchers GS, BF, "
                 "outs, SO, BB, ER, pitches, entry LI), in first-pitch order, for the "
                 "drawer's rolling windows."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_mlbstats_rolling_export.py",
        "note": ("Built from mlbstats_games.player_game_frame, with the plate "
                 "appearance charged as the official scorer charged it. Gitignored; "
                 "shipped by both deploy consumers."),
    },
    {
        "file": "league_trends.json", "group": "mlb",
        "title": "League Trends",
        "what": ("Changes in a player's own measured mechanics (fastball velocity and "
                 "movement, pitch mix, reliever entry Leverage Index, bat speed and swing "
                 "shape) that clear a calibrated bar against his earlier games, the "
                 "expected number from game-to-game noise beside them, the rotation, "
                 "new-pitch and lineup events, the club rows and the season-over-season "
                 "league cards."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_league_trends_export_contract.py",
        "note": ("Descriptive: as_of is the last game date in the frame, and each "
                 "family's expected false entries a day is its published per-test "
                 "placebo tail times the tests run that day."),
    },
    {
        "file": "league_trends_eval.json", "group": "mlb",
        "title": "League Trends false-trend calibration",
        "what": ("Per family and season, the real tests and the placebo shuffles at every "
                 "bar on the grid, the bar each policy chooses, the held-out check and "
                 "the monthly live check of the current season."),
        "cadence": "monthly", "stability": EXPERIMENTAL,
        "pinned_by": "test_league_trends_export_contract.py",
        "note": ("The bars change only in a reviewed commit after a season completes; "
                 "the monthly step rewrites the live check alone."),
    },
    {
        "file": "pal.json", "group": "mlb",
        "title": "Alchemy Lab conversions",
        "what": "Reliever to starter and starter to reliever fits, with pitch-mix change history.",
        "cadence": "monthly", "stability": STABLE, "pinned_by": "test_pal_smoke.py",
        "note": "",
    },
    {
        "file": "arbitration.json", "group": "mlb",
        "title": "Arbitration projections",
        "what": ("Projected arbitration salaries and the remaining arbitration "
                 "ladder for every player a club still controls."),
        "cadence": "monthly", "stability": STABLE,
        "pinned_by": "test_arb_export.py",
        "note": ("First-year projections come from a gated model; second and "
                 "later years come from an empirical raise multiplier, because "
                 "the model was a measured null there. Seasons past 2026 assume "
                 "the current CBA structure survives its expiry."),
    },
    {
        "file": "arb_history.json", "group": "mlb",
        "title": "Arbitration award history",
        "what": ("Per-season arbitration awards: the actual figure, this model, "
                 "and the MLB Trade Rumors projection, with the market and "
                 "value residuals kept as separate columns."),
        "cadence": "monthly", "stability": STABLE,
        "pinned_by": "test_arb_export.py",
        "note": ("The two residuals are never combined: one sums to roughly "
                 "zero by construction and the other does not."),
    },
    {
        "file": "futures.json", "group": "diamond",
        "title": "Futures board",
        "what": ("Season-long outright probabilities per club: division, playoffs, "
                 "bye, pennant and World Series, with Monte Carlo intervals and the "
                 "win-total band."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_futures_board.py",
        "note": ("Model side only. NO futures price has ever been captured, so "
                 "there is no edge column and the payload names the missing "
                 "capture instead of estimating one."),
    },
    {
        "file": "futures_ledger.json", "group": "diamond",
        "title": "Futures forward record",
        "what": ("What the futures board published each day: the five outright "
                 "probabilities per club, one entry per date, with the board hash "
                 "and simulation count that produced them."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_futures_ledger.py",
        "note": ("A record, not a result. Nothing in it is scored: that needs a "
                 "completed season joined back onto the entries that were live "
                 "through it, and the payload reports n_resolved so the distinction "
                 "cannot be read past. Derived copy; the source of truth sits "
                 "outside /data/."),
    },
    {
        "file": "bracket_sim.json", "group": "diamond",
        "title": "Postseason bracket simulator",
        "what": ("Per postseason club, the probability of winning each remaining "
                 "round, the pennant and the World Series, from the posted bracket "
                 "and every played game, with the state date and the series decided "
                 "so far. Labelled implied, no market."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_bracket_sim.py",
        "note": ("An exact series recursion, so it carries no simulation interval. "
                 "No market price exists for it and none is derived from it: no "
                 "price, edge, slot or record row is taken from these numbers. "
                 "Registered before the first number in "
                 "docs/betting-2026-10/BRACKET_SIM_GATE.md."),
    },
    {
        "file": "bracket_sim_record.json", "group": "diamond",
        "title": "Postseason bracket simulator forward record",
        "what": ("Each day's frozen bracket-simulator output, one entry per date: "
                 "the bracket state, the input of every game, the per-club "
                 "probabilities and the consistency checks, chain-hashed."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_bracket_sim.py",
        "note": ("A record, not a result. Nothing in it is scored before the one "
                 "look after the World Series. Derived copy; the source of truth "
                 "sits outside /data/."),
    },
    {
        "file": "management_board.json", "group": "mlb",
        "title": "In-Game Management board",
        "what": ("Stolen-base decision values by target base and season, the club "
                 "style board, the run-expectancy matrix and the measured "
                 "half-inning-start table."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_mgmt_export.py",
        "note": ("Rendering payload for /management/. Carries NO per-club plus "
                 "metric: the gate battery returned a bounded null and the "
                 "payload states the verdict rather than leaving the omission to "
                 "be noticed. Since 2026-09-23 it also carries the decision "
                 "ledger's summary blocks (decisions, clubs, managers, challenges, "
                 "lineups, shards): realized value per family, never a cross-family "
                 "total."),
    },
    {
        "file": "ledger_board.json", "group": "mlb",
        "title": "Club Ledger board",
        "what": ("Thirty clubs' CBT payroll on both Spotrac bases, the computed tax "
                 "beside Spotrac's estimate, contract dollars on file and projected "
                 "arbitration steps per season, controlled surplus in $M, farm capital "
                 "(pools, bonuses paid vs slot, IFA, the fin_* leaves) and the free "
                 "agency ledger with realized contract value; since 2026-09-24 also "
                 "the per-club reconciliation blocks (farm rows to the fin_active_surplus "
                 "leaf, arbitration rungs by season to the ladder sums, contract strips "
                 "to the NPV leg), a ten-row preview per block and the index of the "
                 "per-club row files."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ledger_export.py",
        "note": ("Descriptive ledger. Carries NO single projected payroll: contract "
                 "dollars on file and projected arbitration steps are two keys and the "
                 "page never sums them. No revenue, attendance, TV or valuation field "
                 "exists."),
    },
    {
        "file": "ledger_clubs/*.json", "group": "mlb",
        "title": "Club Ledger per-club row files (one per club)",
        "what": ("data/ledger_clubs/{CODE}.json: every active prospect of the club with "
                 "its eFV expected surplus, band, bonus, slot and net; every graduate "
                 "with the two debuted-value engines side by side; every arbitration "
                 "rung with its fixed-spread band; the realized arbitration rows with "
                 "the MLBTR figure as a third column; every priced contract's WAR and "
                 "surplus strips; the trade board's debuted rows; and, since "
                 "2026-09-30, the club's snapshot series (trade currency, actives, "
                 "each preview prospect) that the sparklines draw. The club page "
                 "fetches one file on demand; the index (bytes, sha256_16) and a "
                 "receipt naming the moved series live in ledger_board.json under "
                 "shards."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_ledger_export.py",
        "note": ("Written by ledger_export.write_shards from the bytes the board indexed "
                 "(run_monthly d10e, right after the board). About 90-105 KB per file, "
                 "capped at 160 KB by test; tracked in git like mgmt_decisions/. Every "
                 "band prints per row and is never summed; no figure is recomputed "
                 "through value_framework; both deploy consumers ship the directory."),
    },
    {
        "file": "franchise_board.json", "group": "mlb",
        "title": "Franchise board",
        "what": ("Thirty clubs' org-level grade tree: the Franchise Index (the weighted "
                 "mean of three branch scores, ROSTER 0.40 / OUTLOOK 0.30 / FARM 0.30, "
                 "re-standardised to 100 + 10z across the 30) and twelve sections that "
                 "re-serve what every module already publishes for the club, on the "
                 "scale each was computed on, with the deep link back."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_franchise_export.py",
        "note": ("Descriptive rank index, not a forecast: thirty percent rests on the "
                 "provisional team_win_projections row and the root card says so. No "
                 "HoF tile (dark with hof_export's wording), no pennants, no club "
                 "decision-quality grade, no manager skill claim, no revenue or "
                 "valuation. The ODDS section quotes the playoff_odds_sim registry "
                 "verdict (provisional). The writer refuses to publish on fewer than "
                 "30 clubs and leaves the previous file on disk."),
    },
    {
        "file": "franchise_clubs/*.json", "group": "mlb",
        "title": "Franchise per-club files (one per club)",
        "what": ("data/franchise_clubs/{CODE}.json: the club's grade tree (every branch "
                 "and leaf with its basis) and its twelve sections, moved off the board "
                 "on 2026-10-03 so the page reads one club's file instead of all thirty. "
                 "The index (bytes, sha256_16) lives in franchise_board.json under "
                 "shards."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_franchise_export.py",
        "note": ("Written by franchise_export.write in the same pass as the board, files "
                 "first; franchise_export.load joins them back for a Python reader. "
                 "Tracked in git like ledger_clubs/; both deploy consumers ship the "
                 "directory."),
    },
    {
        "file": "fscore.json", "group": "mlb",
        "title": "F-SCORE (seven-season franchise score)",
        "what": ("Thirty clubs' F-SCORE: four pillar z-scores (RESULTS in wins with the "
                 "published postseason ladder, STRENGTH, PIPELINE, OPERATIONS) over the "
                 "seven completed seasons 2020-2026 with a three-season half-life, weighted "
                 "50 / 25 / 20 / 5 and re-standardised to 100 + 10z, with each club's "
                 "season table, counts and the season facts (champion, pennants, division "
                 "champions, byes) the Franchise page and the Teams tab copy."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_fscore_export.py",
        "note": ("Descriptive, not a forecast: registry row franchise_score, provisional, "
                 "measurement only. Written by fscore_export (run_daily 6b7g) before the "
                 "Franchise board (6b7d) that embeds it and the Teams payload (6b7h) that "
                 "copies score, letter and rank. In-game management is shown, not scored. "
                 "The writer refuses on a missing club, a missing completed season, a "
                 "broken bracket or a failed identity and leaves the previous file on disk."),
    },
    {
        "file": "management_decisions.json", "group": "mlb",
        "title": "In-Game Management decision ledger (summary)",
        "what": ("Nine decision families the play corpus can name (pitching change, pinch "
                 "hitter, pinch runner, defensive sub, intentional walk, bunt, steal, mound "
                 "visit, ejection): counts, the realized win-probability change per family "
                 "and per club-season (an endpoint difference over the window each decision "
                 "governed), style z-scores, the chain-break measurement and the shard "
                 "index. The agent is the club-season."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_mgmt_decisions.py",
        "note": ("REALIZED VALUE, NOT SKILL, and the payload says so verbatim. No key on a "
                 "club-season row contains dv or decision; no cross-family total; no plus "
                 "metric. Rebuilt when the play corpus is rebuilt (mgmt_decisions.py, "
                 "nightly step 6b7e)."),
    },
    {
        "file": "management_baseline.json", "group": "mlb",
        "title": "In-Game Management matched-state baseline",
        "what": ("The league mean realized window value per matched state cell (season, "
                 "inning bucket, half, outs, base code, score bucket) for each decision "
                 "family, from every window of the same shape, decision or not; the "
                 "baseline behind decision value above state (DVS) in the drill-down."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_mgmt_decisions.py",
        "note": ("Eval artifact for the registry row mgmt_state_baseline. Thin cells "
                 "(under min_cell windows) are published as excluded; the within-cell "
                 "identity is checked, not asserted. DVS is descriptive and never a "
                 "club-season column."),
    },
    {
        "file": "mgmt_decisions/*.json", "group": "mlb",
        "title": "In-Game Management decision shards (one per club-season)",
        "what": ("data/mgmt_decisions/{season}-{club}.json: every decision of one "
                 "club-season with its window (the plays governed, win probability before "
                 "and after each), realized value, value above state, flags and names. The "
                 "drill-down fetches one shard on demand; the index lives in "
                 "management_board.json under shards."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_mgmt_decisions.py",
        "note": ("Written on corpus rebuild by mgmt_decisions.py through mgmt_shards.py. "
                 "Schema 2 (2026-09-23): array rows under a per-family key legend with a "
                 "game table, a name table keyed by player id and code tables for events, "
                 "kinds and flags; a window play is [event, wp_after] with wp_before only "
                 "where the feed's chain breaks. About 1,250 rows and 170 KB per shard, "
                 "41.5 MB over 240 (schema 1 was 655 KB per shard, 157 MB), so the set can "
                 "be tracked in git; both deploy consumers ship the directory."),
    },
    {
        "file": "management_steal_context.json", "group": "mlb",
        "title": "In-Game Management steal context (runner speed, catcher pop time)",
        "what": ("For every steal row of the decision shards, by season: the runner's "
                 "sprint speed percentile among that season's runners on the Baseball Savant "
                 "sprint speed leaderboard (10 or more competitive runs), and the catcher the "
                 "MLB feed names on the attempt with his pop time to second from the Savant "
                 "catcher throwing leaderboard. Per-season coverage counts and the reason "
                 "templates the page prints beside a blank cell."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_mgmt_steal_context.py",
        "note": ("Context only: the steal's decision value is priced with a league-average "
                 "runner (management.py) and neither DV nor the execution residual reads "
                 "this file. Written by mgmt_steal_context.py at nightly step 9e-pre0f."),
    },
    {
        "file": "hof_board.json", "group": "mlb",
        "title": "Hall of Fame board",
        "what": ("Career WAR, WAR7, JAWS, WAR ink and the public HoF Monitor and "
                 "Standards columns for every ten-season player, in three bands, "
                 "with the induction ledger joined in three states."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_hof_export.py",
        "note": ("Rendering payload for /hof/. Carries its own disclosure copy, "
                 "because four of the page's eight sections are dark and each one "
                 "states its blocker in the payload rather than in the HTML."),
    },
    {
        "file": "awards.json", "group": "mlb",
        "title": "Awards board",
        "what": ("The eephus selection for MVP, Cy Young, Rookie and Manager of the Year "
                 "in each league under a published rule over the site's own numbers, the "
                 "superlatives, the season index and the rule-and-vote table."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_awards_export.py",
        "note": ("Rendering payload for /awards/, the Awards page of Awards / HoF, "
                 "rebuilt nightly. Every WAR-bearing block names its war_provider."),
    },
    {
        "file": "awards_*.json", "group": "mlb",
        "title": "Awards board, closed seasons",
        "what": ("One closed season of the Awards board (2021 on): its cards, rules, "
                 "superlatives and race, written once and byte-stable after."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_awards_export.py",
        "note": ("At data/ depth one because both deploy consumers ship depth-one data "
                 "files only; a season subfolder would 404 on the public site."),
    },
    {
        "file": "awards_candidates_*.json", "group": "mlb",
        "title": "Awards ballot candidates",
        "what": ("My Ballot's candidate pools per award and league for one season: every "
                 "eligible player or club with the rule's metric, the compare metrics and "
                 "the rule's place, with each column's producer and registry row."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_awards_export.py",
        "note": "Loaded only by the ballot chunk; Manager ids are club codes.",
    },
    {
        "file": "awards_eval.json", "group": "mlb",
        "title": "Awards selection eval",
        "what": ("The awards_selection registry row's artifact: reconciliation counts per "
                 "invariant, the rookie test on past Rookie of the Year winners once the "
                 "winners file exists, and the freeze hashes."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_awards_export.py",
        "note": ("First committed by the flip (AWARDS_11); copies its hashes from "
                 "data/_labs/awards/freeze_log.json."),
    },
    {
        "file": "_labs/awards/*.json", "group": "mlb",
        "title": "Awards inputs and records (tracked, unpublished)",
        "what": ("rookies.json (the rookie test per season), award_winners.json (the "
                 "writers' results from MLB's StatsAPI), race_<S>.json (the weekly race), "
                 "frozen_<S>.json (a season's frozen selection, write-once) and "
                 "freeze_log.json (their hashes)."),
        "cadence": "on change", "stability": EXPERIMENTAL,
        "pinned_by": "test_awards_export.py",
        "note": ("data/_labs/ ships in neither deploy consumer; the exporter publishes "
                 "only derived blocks."),
    },
    {
        "file": "milb_park_factors.json", "group": "mlb",
        "title": "MiLB park factors",
        "what": "Per-venue offensive park factors for the minor league parks, with sample sizes.",
        "cadence": "on change", "stability": EXPERIMENTAL, "pinned_by": "",
        "note": "Display reference. The eFV park line that would consume it stays gated off.",
    },
    # ---- Diamond ---------------------------------------------------------
    {
        "file": "fantasy.json", "group": "diamond",
        "title": "Fantasy corpus",
        "what": ("Rest-of-season projections per player in every supported scoring format, the "
                 "streamer and two-start blocks, and the scoring catalog itself."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_fantasy_split.py",
        "note": "",
    },
    {
        "file": "dfs.json", "group": "diamond",
        "title": "DFS slate",
        "what": "Per-game projections for the current slate, by game, with the park and matchup context.",
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "test_fantasy_split.py",
        "note": "Salaries are not included. You bring those from your own site.",
    },
    {
        "file": "betting.json", "group": "diamond",
        "title": "Betting model board",
        "what": ("Model prices for the slate, the pick of the day, and the public record's "
                 "summary: won, lost, net units and ROI on a flat one-unit stake."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_betting.py",
        "note": "Informational and for entertainment. 21+.",
    },
    {
        "file": "betting_preview.json", "group": "diamond",
        "title": "Betting board preview",
        "what": ("The public slice of the board: the slate, the model's fair lines and the "
                 "status block, without the priced sides behind the gate."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_betting.py",
        "note": "The gating seam. Informational and for entertainment. 21+.",
    },
    {
        "file": "betting_record.json", "group": "diamond",
        "title": "Betting public record",
        "what": ("Every pick the site has stood behind, append-only, with the book and the "
                 "price taken. Results are joined from the settlement sidecar on bet_id."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_betting.py",
        "note": ("Append-only by construction: a published row is never edited, and a "
                 "correction is a new row. Two slots a day at most."),
    },
    {
        "file": "betting_shadow.json", "group": "diamond",
        "title": "Betting paper-bet ledger",
        "what": ("Paper bets: what the model would have bet, at the price on the "
                 "board, tagged with the selection rule that chose each row and settled "
                 "against the final score. No money and no recommendation."),
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "test_betting_shadow.py",
        "note": ("Read the `slot` and `tags` fields before aggregating anything. The tags name "
                 "four different selection rules and a pooled ROI across them measures a "
                 "mixture nobody bet."),
    },
    {
        "file": "betting_learning.json", "group": "diamond",
        "title": "Betting learning series",
        "what": ("What the betting module learned since yesterday: the two validation clocks "
                 "with measured arrival rates, the gate table, the calibration bins, the "
                 "closing-move block and the per-market split, plus a capped nightly history."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_betting_learning.py",
        "note": ("Every days_to_need is a measured rate applied forward and says so. History "
                 "rows for past dates are never rewritten, and any counter here may go "
                 "backwards and is rendered going backwards."),
    },
    {
        "file": "betting_clv.json", "group": "diamond",
        "title": "Betting closing-line value",
        "what": ("Per published pick: the price taken against the closing price at the same "
                 "book, as a return percentage and as a probability move."),
        "cadence": "daily", "stability": EXPERIMENTAL,
        "pinned_by": "test_betting_clv_sidecar.py",
        "note": ("Keyed by bet_id against the public record. This is CLV on positions the site "
                 "took, and it is not the calibration ledger's market_move_pct."),
    },
    {
        "file": "betting_status.json", "group": "diamond",
        "title": "Betting job status",
        "what": ("Whether the odds feed is configured, when the last snapshot was captured and "
                 "of which kind, and the credit accounting behind it."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_betting.py",
        "note": "Check this before reading a quiet board as a quiet slate.",
    },
    {
        "file": "betting_model_eval.json", "group": "diamond",
        "title": "Betting model eval",
        "what": ("The run-scoring model graded in every mode it has - in-sample, forward split, "
                 "and the vintage mode, the one out of sample; with the three-gate "
                 "table that decides whether a min-edge threshold may exist at all."),
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "test_betting.py",
        "note": ("Only the `vintage` block is out of sample (its `honest` field says so). "
                 "The other two frames leak; they ship labelled in-sample."),
    },
    {
        "file": "betting_model_context.json", "group": "diamond",
        "title": "Betting model context",
        "what": ("The fitted run-scoring coefficients, the home-field adjustment, the shrink "
                 "and the extra-inning rate the live board prices with."),
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "",
        "note": "Model internals. Unpinned: field names can change.",
    },
    # ---- reference -------------------------------------------------------
    {
        "file": "glossary.json", "group": "reference",
        "title": "Library terms",
        "what": ("Every metric on the site with its definition, scale convention and provenance. "
                 "The tooltip layer reads this file."),
        "cadence": "on change", "stability": STABLE,
        "pinned_by": "test_glossary_provenance.py", "note": "",
    },
    {
        "file": "model_registry.json", "group": "reference",
        "title": "Model registry",
        "what": ("One row per shipped model: what it predicts, its eval artifact, when that eval "
                 "was last refreshed, and the verdict. The index to every accountability file "
                 "on the site."),
        "cadence": "monthly", "stability": STABLE, "pinned_by": "test_model_registry.py",
        "note": ("Each row's eval_artifact names another public data file. Those eval sidecars "
                 "ship on purpose, including the experiments that failed."),
    },
    {
        "file": "ingest_health.json", "group": "reference",
        "title": "Ingest health",
        "what": ("The last pipeline run's per-source status and the RED ledger: which upstreams "
                 "came back empty or failed, and what was kept instead of publishing empty."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_ingest_health.py",
        "note": "Check this before trusting a quiet day in any other artifact.",
    },
)


def excluded_files() -> set:
    """Data files the deploy deliberately withholds from the webroot.

    Parsed from deploy/data_exclude.txt, the same list both deploy consumers
    read. An unreadable list returns EMPTY, which would let a withheld file be
    advertised, so the caller treats a parse failure as a reason to trust the
    tree check alone; in practice the file is committed and read fine."""
    out: set = set()
    try:
        text = EXCLUDE_LIST.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def _vintage(path: Path) -> str:
    """The artifact's own stamped vintage, or "" when it does not carry one.

    Reads the stamp the writer put in the file rather than the filesystem
    mtime: a deploy copy rewrites mtime and would report every artifact as
    fresh. Streams only the head of the file because these run to tens of
    megabytes and the stamp is always in the first object."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return ""
    for key in ("generated_at", "as_of", "checked_at"):
        needle = f'"{key}"'
        i = head.find(needle)
        if i < 0:
            continue
        j = head.find('"', head.find(":", i) + 1)
        k = head.find('"', j + 1)
        if 0 < j < k:
            return head[j + 1:k]
    return ""


def _pin_receipt(test_name: str, artifact: str) -> str:
    """The test that pins this artifact's shape, or "" when the claim cannot be
    backed. Rendered only when the file exists AND names the artifact, so a
    deleted or repurposed test removes the claim from the page automatically
    instead of leaving a citation to nothing."""
    if not test_name:
        return ""
    path = ROOT / test_name
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return test_name if artifact in src else ""


#: The franchise_board.json row's text once F-SCORE is the root score (owner
#: answer FS-Q4 (b), FS_2C_INDEX_REPLACEMENT); catalog_rows() swaps it in only
#: while franchise_export.index_replaced() is True.
FRANCHISE_BOARD_FSCORE = {
    "what": ("Thirty clubs' org-level grade tree under F-SCORE, the root score: seven seasons "
             "and today, re-standardised to 100 + 10z across the 30 and copied from fscore.json. "
             "Beneath it sit the three branch scores (ROSTER and OUTLOOK inside STRENGTH, FARM "
             "inside PIPELINE) and twelve sections that re-serve each module's numbers for the "
             "club on their own scales, with the deep link back."),
    "note": ("Descriptive, not a forecast: one F-SCORE leg, 2027 wins, is a provisional "
             "projection. The Franchise Index was retired by owner answer FS-Q4 and is not "
             "served. Pennants, titles and postseason rounds are served as results; no club "
             "decision-quality grade, no manager skill claim, no revenue or valuation. The ODDS "
             "section quotes the playoff_odds_sim registry verdict (provisional). The writer "
             "refuses to publish on fewer than 30 clubs or without that night's F-SCORE and "
             "leaves the previous file on disk."),
}


def _franchise_root_is_fscore() -> bool:
    try:
        import franchise_export
        return franchise_export.index_replaced()
    except Exception:  # noqa: BLE001
        return False


def catalog_rows() -> list:
    """The catalog, verified against the tree and the deploy exclude list.

    Every returned row describes a file that (a) exists here and (b) is not
    withheld from the webroot, so a rendered row is always a URL a reader can
    actually fetch."""
    withheld = excluded_files()
    rows = []
    for a in ARTIFACTS:
        name = a["file"]
        if name in withheld:
            continue
        path = DATA_DIR / name
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        row = dict(a)
        if name == "franchise_board.json" and _franchise_root_is_fscore():
            row.update(FRANCHISE_BOARD_FSCORE)
        row["url"] = DATA_BASE_URL + name
        row["bytes"] = size
        row["size_label"] = human_size(size)
        row["vintage"] = _vintage(path)
        row["pinned_by"] = _pin_receipt(a.get("pinned_by") or "", name)
        rows.append(row)
    return rows


def rows_by_group() -> list:
    """[(group_key, group_label, [rows])] in GROUPS order, empty groups dropped."""
    rows = catalog_rows()
    out = []
    for key, label in GROUPS:
        block = [r for r in rows if r["group"] == key]
        if block:
            out.append((key, label, block))
    return out


def human_size(n: int) -> str:
    """Byte count as a short label. Whole numbers below 10 MB read as integers
    so a table column of sizes stays scannable."""
    if n <= 0:
        return ""
    if n < 1024:
        return f"{n} B"
    kb = n / 1024.0
    if kb < 1000:
        return f"{kb:.0f} KB"
    mb = kb / 1024.0
    return f"{mb:.1f} MB" if mb < 10 else f"{mb:.0f} MB"


def counts() -> dict:
    """Headline counts for the page intro, computed from the verified rows so
    the sentence cannot drift from the table under it."""
    rows = catalog_rows()
    return {
        "n": len(rows),
        "stable": sum(1 for r in rows if r["stability"] == STABLE),
        "experimental": sum(1 for r in rows if r["stability"] == EXPERIMENTAL),
        "withheld": len(excluded_files()),
    }

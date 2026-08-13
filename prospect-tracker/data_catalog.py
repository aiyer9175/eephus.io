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

import json
from pathlib import Path

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
    ("diamond", "Fantasy, DFS, betting and cards"),
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
        "note": ("Large. Prefer a slimmer artifact below if you only need grades or movement."),
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
                 "for compatibility and are NOT what the board serves."),
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
        "what": ("The biggest genuine board eFV moves on the latest rebuild, with the driving "
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
        "what": ("Is one prospect source more accurate than another for a given kind of player? "
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
        "file": "xfv_side_calibration_eval.json", "group": "prospects",
        "title": "Do pitchers and hitters mean the same thing at the same grade?",
        "what": ("The audit behind the question people actually ask about eFV: why does it "
                 "carry so few pitchers near the top? It answers with outcomes rather than "
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
                 "NOT the headline: it removes the rows where the consensus is advantaged "
                 "while keeping those where eFV is, so its margin is partly an artifact of "
                 "that asymmetry. Read `vintage_matched`, which is the symmetric contest and "
                 "reads a tie at the smallest floor of the three."),
    },
    # ---- MLB -------------------------------------------------------------
    {
        "file": "mlb_projections.json", "group": "mlb",
        "title": "MLB projections",
        "what": ("Five-year bWAR paths for every MLB player with floor / mean / ceiling buckets, "
                 "contract surplus on salary-known seasons, and prospects joining at their ETA."),
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
        "pinned_by": "test_starter_export_contract.py", "note": "",
    },
    {
        "file": "bullpen_leaderboards.json", "group": "mlb",
        "title": "Bullpen leaderboards",
        "what": "Season reliever board with REM+, leverage context and the team Bullpen+ rollup.",
        "cadence": "monthly", "stability": STABLE, "pinned_by": "test_bullpen_export.py",
        "note": "",
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
        "what": ("Model prices for the slate, the pick of the day, and the graded public record "
                 "with each pick's book, odds and closing line."),
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
        "what": ("Every pick the site has stood behind, append-only, with the book, the price "
                 "taken, the closing line and the graded result."),
        "cadence": "daily", "stability": STABLE, "pinned_by": "test_betting.py",
        "note": ("Append-only by construction: a published row is never edited, and a "
                 "correction is a new row. Two slots a day at most."),
    },
    {
        "file": "betting_shadow.json", "group": "diamond",
        "title": "Betting paper-bet ledger",
        "what": ("Paper bets: what the model WOULD have bet, at the price actually on the "
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
                 "and the vintage mode that is actually out of sample - with the three-gate "
                 "table that decides whether a min-edge threshold may exist at all."),
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "test_betting.py",
        "note": ("Only the `vintage` block is honest out of sample, and it says so in its own "
                 "`honest` field. The other two leak and ship anyway, because hiding them "
                 "would leave the flattering numbers unlabelled."),
    },
    {
        "file": "betting_model_context.json", "group": "diamond",
        "title": "Betting model context",
        "what": ("The fitted run-scoring coefficients, the home-field adjustment, the shrink "
                 "and the extra-inning rate the live board prices with."),
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "",
        "note": "Model internals. No test pins this shape, so treat the field names as habit.",
    },
    {
        "file": "card_market.json", "group": "diamond",
        "title": "Card market screen",
        "what": "The hobby price screen: card index, movers, and price against the prospect model.",
        "cadence": "daily", "stability": EXPERIMENTAL, "pinned_by": "test_card_market.py",
        "note": "A screen, not a validated signal. It says so on the page too.",
    },
    # ---- reference -------------------------------------------------------
    {
        "file": "glossary.json", "group": "reference",
        "title": "Glossary",
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


def as_json() -> str:
    """The catalog as JSON. Handy for a consumer who would rather read the
    index than scrape the page."""
    return json.dumps({"artifacts": catalog_rows(), "counts": counts()},
                      ensure_ascii=False, indent=2)

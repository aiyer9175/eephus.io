# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV export (efv_export.py) + dataset as-of leakage guard unit tests.

  1. Headline contract: the exported xfv_grade IS the pure-model (realized) grade
     -- identical to xfv_grade_realized, and DISTINCT from the quantile-blend map
     (xfv_grade_quantile). Driven through _entry with synthetic scored rows, then
     re-checked read-only on the committed artifact.
  2. Golden fingerprint tripwire on data/xfv.json (volatile-key-stripped content
     hash). An intentional eFV ship updates the constant below WITH a changelog note.
  3. _asof_point leakage guard: a future points[] entry (dated after the decision /
     debut date) must NOT change the as-of consensus FV -- future information ignored.

Read-only on committed files; no writes into data/.
"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import efv_export
from efv_export import _entry
from efv_dataset import _asof_point, _prior_features

DATA = Path(efv_export.__file__).parent / "data"


# --------------------------------------------------------------------------
# 1. Headline contract: xfv_grade == realized (pure model), quantile is distinct
# --------------------------------------------------------------------------
def test_entry_headline_is_pure_model_grade():
    # a scored row where the realized grade and the quantile map DIVERGE
    s = {
        "player_key": "test.player", "position": "SS",
        "xfv_grade": 48.3,                    # realized_implied_fv(E[6yr WAR]) -- the headline
        "xfv_grade_display": 55.0,            # rank->consensus-scale quantile map (must differ)
        "consensus_fv": 50.0,
        "xfv_minus_consensus": -1.7,
        "xfv_minus_consensus_display": 5.0,
        "xfv_war_6yr": 6.4, "p_bucket": {"star": 0.1}, "surplus_mm": 12.0,
        "band_p10_mm": -1.0, "band_p90_mm": 40.0, "p_bust": 0.3,
    }
    e = _entry(s, "hit", "active")
    # headline grade IS the pure realized grade (no consensus blend, no quantile remap)
    assert e["xfv_grade"] == 48.3
    assert e["xfv_grade_realized"] == 48.3          # alias -- byte-identical to headline
    assert e["xfv_grade"] == e["xfv_grade_realized"]
    # the quantile-blend value is preserved SEPARATELY and is distinct here
    assert e["xfv_grade_quantile"] == 55.0
    assert e["xfv_grade"] != e["xfv_grade_quantile"]
    # the minus-consensus deltas track their respective grades
    assert e["xfv_minus_consensus"] == -1.7                 # realized - consensus
    assert e["xfv_minus_consensus_quantile"] == 5.0         # quantile - consensus
    assert e["side"] == "H" and e["kind"] == "active"


def test_entry_side_tag_and_optional_fields():
    base = {"player_key": "p", "xfv_grade": 40.0, "xfv_grade_display": 40.0,
            "consensus_fv": 45.0, "xfv_minus_consensus": -5.0,
            "xfv_minus_consensus_display": -5.0}
    assert _entry(base, "pit", "resolved")["side"] == "P"
    # optional blocks appear only when present on the scored row
    assert "injury_factor" not in _entry(base, "hit", "active")
    assert _entry({**base, "injury_factor": 0.7}, "hit", "active")["injury_factor"] == 0.7
    assert _entry({**base, "xfv_provisional": True}, "hit", "active")["xfv_provisional"] is True


def test_committed_artifact_headline_alias_contract():
    """Read-only field contract of the shipped artifact.

    The contract depends on whether the per-side board scale is enabled, so this
    asserts the one that is actually in force rather than hard-coding either.

    Scale DISABLED (the state since 2026-07-29):
      xfv_grade == xfv_grade_realized             a pure alias, board_value is identity
      xfv_grade_model_raw                         absent, nothing stamps it
      xfv_grade_quantile present and distinct     the retired display scale, kept

    Scale ENABLED:
      xfv_grade_model_raw == xfv_grade_realized   the PRE-scale model grade
      xfv_grade           == board_value(record)  the scaled grade the board serves
      xfv_grade_quantile  present and distinct

    History: this test asserted the plain alias until 2026-07-25, when W-SIDESCALE
    rewrote it for the enabled state. The scale was disabled again on 2026-07-29
    because its primary gate never resolved against its own control (perm p 0.259) and
    nothing in the pipeline ever stamped the artifact, so the enabled-only form was
    failing on the first row of a perfectly valid artifact. Parameterising on
    bs.enabled() means neither flip can make a sanctioned state look like drift, which
    is the golden fingerprint's job rather than a field-contract test's.
    """
    import efv_board_scale as bs

    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc["by_player"]
    assert len(bp) > 1000

    both = distinct = scaled_apart = 0
    for key, e in bp.items():
        raw, real = e.get("xfv_grade_model_raw"), e.get("xfv_grade_realized")
        if bs.enabled():
            assert raw is not None, f"{key}: no xfv_grade_model_raw (scale anchor missing)"
        if raw is None:
            # unstamped artifact: the headline IS the pre-scale model grade
            raw = e.get("xfv_grade")
        assert raw == real, f"{key}: model_raw {raw} != realized {real}"

        # the headline must be exactly what the board scale produces for this row.
        # Tolerance is stamping precision only, NOT slack: stamp_doc quantizes to the
        # 0.1 grid (the long-standing eFV grade contract, pinned by
        # test_efv_score::test_committed_grades_carry_the_round_to_nearest_signature),
        # so the stamped headline may sit up to half a grid step from the unrounded
        # board_value and no further.
        g, bv = e.get("xfv_grade"), bs.board_value(e)
        if g is not None and bv is not None:
            assert abs(g - bv) <= 0.05 + 1e-9, f"{key}: headline {g} != board_value {bv}"
            if abs(g - raw) > 1e-9:
                scaled_apart += 1

        if g is not None and e.get("xfv_grade_quantile") is not None:
            both += 1
            if abs(g - e["xfv_grade_quantile"]) > 1e-9:
                distinct += 1

    assert both > 1000
    # the headline and the retired quantile scale are genuinely different numbers
    assert distinct > 0.5 * both
    # and the side scale is actually doing something when it is enabled (if this goes
    # to zero with the flag on, board_value has silently become a passthrough)
    if bs.enabled():
        assert scaled_apart > 0.5 * len(bp), (
            f"side scale enabled but only {scaled_apart}/{len(bp)} rows moved off "
            f"their pre-scale grade")


# --------------------------------------------------------------------------
# 2. Golden fingerprint tripwire
# --------------------------------------------------------------------------
# GOLDEN eFV ARTIFACT FINGERPRINT (volatile-key-stripped content hash of data/xfv.json).
# This is a deliberate tripwire: it goes red when the flagship export changes. An
# INTENTIONAL eFV ship (model/feature/calibration change) updates this constant in the
# SAME commit, alongside a CHANGELOG / memory note describing what moved and why. An
# UNEXPECTED red here means the committed artifact drifted without a sanctioned ship.
# Updated 2026-07-05: eFV flagship correction -- (1) grade map inverts on the model's
#   own 6-season window (exposure_seasons=TARGET_SEASONS) not clemens control_years=7
#   (fixed top-end deflation, jesus_made 61.8->64.9); (2) efv_dataset._season_rates no
#   longer treats a missing level norm as 0 (fixed young/DSL-arm inflation).
# Updated 2026-07-06 (holistic-audit batch): (3) blend_lambda WAG gate raised 0.05->0.10
#   so the now-non-significant hitter WAG defers to the rank gate (hitter lambda
#   0.53->0.70), lifting recent-era OOS blend rho (2019-23 up, small <=2018 give-back);
#   (4) production fit pool now excludes never-MLB recent-bust rows to match the
#   governance eval (removes fringe fit noise, rank-neutral). Grades ~unchanged
#   (jesus_made 65.1, franklin_arias 64.6). The FV-history + provisional-board fixes in
#   this batch do not touch xfv.json.
# Updated 2026-07-06 (eFV consistency batch): surplus_mm + band + surplus fan (dist) now
#   priced on the DISPLAYED quantile grade (xfv_grade_display) instead of the honest
#   realized grade -- owner: eFV surplus must match the 20-80 grade the site shows and the
#   /projections/ surface. p_bucket / p_bust (validated star/bust odds) STAY on the realized
#   grade. Grades (xfv_grade / _quantile) unchanged; only the priced dollars moved (e.g.
#   jayden_dubanewicz surplus 0.5 -> 1.6 at the displayed 40). Ripples into trade_values +
#   the farm Value branch via _active_surplus_net_mm. Also refreshed the meta grade_scale note.
# Updated 2026-07-07 (model bug-sweep batch 2): (1) injury/Statcast WAR tilt made SIGN-AWARE
#   (efv_score._apply_war_tilt) -- a multiplicative haircut on a NEGATIVE xfv_war used to
#   INVERT (an injury RAISED a fringe arm past healthy peers; 153 neg-war+factor rows now
#   correctly move down); (2) prospect_path._fit_ridge now honors the KM observed-fraction
#   sample weight + picks alpha on a seeded representative holdout (was the contiguous
#   last-fifth = oldest busts). OOS eval UNCHANGED (hit 0.3524 / pit 0.2839), so grades shift
#   only trivially (jayden_dubanewicz 32.5 -> 32.4). No accuracy change; correctness only.
# Updated 2026-07-07 (pre-launch pass): (1) M5 SHIP - ops_rel joins the hitter lean
#   feature set under the pre-registered fringe-tier gate (docs/prelaunch-2026-07/
#   GATES.md; FV-45 tier Spearman +0.0237, ~10x the noise floor; pooled/within-tier
#   at the identity noise floor; ledger data/xfv_ops_rel_fringe_eval.json); (2) fresh
#   post-pipeline data vintage folded in by the same regen (run 371 scrapes: consensus
#   live captures, statlines, IL, transactions), so grades carry both the feature ship
#   and the ordinary daily movement. M1 instrumentation (per-cohort/era/tier
#   contributor-AUC + star-AUC, live-lambda provenance hit 0.70 / pit 0.54) landed in
#   the eval artifacts only - xfv.json itself is untouched by M1.
# Updated 2026-07-07 (final pre-launch validation run): the timed full pipeline run
#   (run 372, 33m12s vs the 52m49s baseline = the WS-R cut proven) refreshed every
#   artifact on launch-eve data; ordinary daily movement only, no model change
#   (ops_rel shipped in the prior bump). Rowcount 8843.
# Updated 2026-07-14 (owner full-pipeline run on post-deploy-overhaul code, the
#   first run exercising the 13d7728 chain merges + d9b2 player-detail re-bake):
#   ordinary data movement (draft-week churn + a week of statlines/IL/trades),
#   no model change. Rowcount 8888.
# Updated 2026-07-14b (eFV improvement pass, docs/efv-2026-07-14/GATES.md): FOUR
#   deliberate model changes - E-STALE anchor decay (stale-listed actives fall to
#   their outcome-grounded level, e.g. Hickey 43->35), hit blend-lambda band
#   raised to the 0.90 clamp, absolute-age feature in both lean sets, and the
#   owner-directed live prospect-age penalty (Moore #77 -> #114). All ledgered
#   (xfv_stale_anchor/lambda_band/age_feature evals). Rowcount 8888.
# Updated 2026-07-14c (audit repair pass, GATES.md "Repair pass"): label
#   integrity (41 veteran-debut mislabels dropped, career_war window decay
#   healed - 1,628 payloads refetched 2011-floor), x_era_k double-bad quadrant
#   zeroed (owner-directed), tool imputation at train means, milb_missing
#   availability split, side-routing fix, ~2,200 bust rows re-scored onto the
#   live quantile scale (rowcount 8888 -> 9127), AND the lambda band raise
#   RETRACTED (its evidence did not survive the label repair; hit lambda back
#   to 0.70). Governance evals re-run in the same regen.
# - 2026-07-15: the improvement-program board rebake: performance_ingest
#   grade-normalization fix (106 synthetically inflated pitcher anchors
#   deflated; Pineda #78 -> #204) + the owner-directed reliever-ceiling
#   overlay (second Moore directive; 9 arms, Moore #91 -> #159) on the
#   full-pipeline data refresh.
# Updated 2026-07-15b (2026 draft completion, data change - no model change):
#   post-draft FG board ingested (interval 2026-07-15) + MLB tracker results
#   (613 picks) + the NEW signed-draftee seed (draft_promotion.
#   seed_signed_draftees: 8 current-class signees, e.g. AJ Gracia -> ATL,
#   surface on the board via the synthetic 'draft_signing' source). Rowcount
#   9127 -> 9133.
# Updated 2026-07-15c (production regen_all after the stats<->projections
#   program; data change - no model change): the day's MiLB scrape refresh
#   pulled one new performance_ingest arm (derik_aquino, LAD) into the pool
#   when the matrices rebuilt. Also re-baselines away mid-suite test churn
#   (a test regen under the pinned test valuation set had overwritten
#   xfv.json in place - always re-stamp from a PRODUCTION efv_export run,
#   never from a post-pytest working tree). Rowcount 9133 -> 9134.
# Updated 2026-07-15d (owner-directed MODEL change): the live injury overlay
#   dropped its unconditional is_post_tj x0.85 - post-TJ STATUS alone is not
#   an injury (Kade Anderson: recovered 2022 TJ, zero IL days, was taxed 15%
#   on WAR/grade/rank/surplus; war6 8.21 -> 9.66). 47 healthy post-TJ arms
#   cleared (+1-3 grade pts); live IL components unchanged (623 players still
#   priced). Registry notes on xfv_hitter/xfv_pitcher. Rowcount 9134.
# Updated 2026-07-15e (the 2024-fold unlock, MODEL + LABEL change;
#   docs/efv-2026-07-15/GATES.md): DEBUT_YEARS widened to 2011-2024 (210
#   dated-2024 debuts enter as censored weight-0.333 training rows),
#   career-terminal transactions (lifetime DEI ban / retirement) resolve
#   censored rows at the observed sum (marcano/alu/kirilloff/pint/ridings),
#   and level_rank SHIPPED into the hitter lean set via the pre-registered
#   LR-FRINGE gate (t45 +0.0192). Governance re-runs E-ISO4-path/M3/E-STUFF/
#   BUCKET-AGE-HEAD all FAIL (closes stand); every other keep-alive ledgered
#   as a loss. Evals re-run in the same regen (F-SIDE S5 tripwire recorded
#   tripped). Rowcount 9134.
# Updated 2026-07-16 (DATA refresh, no model change): restamped from the
#   refinement-program rebuild_only production regen (efv_export.regen_all)
#   after a same-day daily data refresh moved stats/IL/rosters. No eFV code
#   or feature change is in this stamp - the 2026-07-16 program's eFV-adjacent
#   edits (efv_ungraded trajectory floor guard) do not touch xfv.json.
#   Rowcount 9134 -> 9148 (ordinary roster churn).
# Updated 2026-07-16b (DB REPAIR, LABEL + POOL change): owner-authorized
#   applies of tools/delete_draft_board_leak.py (936 org-less FG draft-board
#   rows removed from MiLB snapshots; the 2021-2026 board leak) and
#   tools/repair_debut_snapshots_2026.py (41 veteran re-appearance debut
#   snapshots re-dated to true debuts + 2 same-season misdates). Restamped
#   from the immediate post-repair rebuild_only production regen. Rowcount
#   9148 -> 9010 (leak-only identities leave the eFV pool; debut-date labels
#   corrected). Same repairs must run on the deploy box, which then restamps
#   nothing (its golden check runs in EEPHUS_DEPLOY_RUN=1 shape mode).
# 2026-07-17 restamp: owner directive - the live injury penalty no longer
#   applies to currently-healthy players (the Josue Briceno case: activated
#   off a 60-day IL stint the same day, but ~108 trailing IL days still held
#   a x0.90 haircut). _injury_factor now returns 1.0 unless il_on; trailing
#   days/stints only deepen an ACTIVE stint's haircut (efv_score.py). 486
#   currently-on-IL players keep a factor; every healthy player cleared.
#   Restamped from the in-session rebuild_only production regen. Rowcount
#   9010 -> 9040 (daily pool churn since the 07-16 stamp, not the directive).
# 2026-07-24 restamp: eFV holistic program (docs/efv-2026-07-24/GATES.md). FOUR
#   coordinated served-number changes in one regen, restamped from the in-session
#   production efv_export.py --all run:
#   (a) G-BUGS wave-B repairs (data/xfv_bughunt_2026_07_24.json): the P0 that
#       eFV surplus skipped the isotonic calibration layer is fixed (every prospect
#       surplus now prices through it); the P1V3 slot-trust (pick,bonus) collision
#       is gated on acq_year (5 backgrade rows revert); 20 MLB-career players
#       (adolis_garcia/senga/yoshida...) removed from the bust training pool + 24
#       mis-resolved mlbam ids nulled + a resolver vintage guard (training-input
#       change -> matrices moved).
#   (b) W-XLINE-W + W-XISO (verified PASS): S-XLINE hitter blend W_HIT 0.5->0.7 and
#       a fourth capped delta d_iso; ~66 covered AAA hitters de-luck further.
#   (c) W-FSIDE-SHIP (owner-authorized, verified): joint top-band fairness
#       recalibration default ON, whole board (467 movers incl. debuted, max 3.0 FV;
#       kade_anderson 62->59, top-25 pit share 0.37->0.21).
#   (d) W-SURPLUS S1 (owner-authorized, verified): isotonic-real-v4 recalibration to
#       the post-Clemens-re-anchor pool; served FV45-55 surplus +40-120%. The
#       prospx_current base-identity table was re-captured under v4 in the same
#       change (config/valuation_sets/prospx_current.yaml) and test_valuation_sets
#       re-stamped (17.7->31.6).
#   Rowcount 9040 -> 9267 (daily pool churn + FG trade-deadline draftees since 07-23,
#   not the directive). The deploy box re-derives its own artifact under
#   EEPHUS_DEPLOY_RUN shape mode; this dev hash is a session tripwire only.
# 2026-07-24b restamp: eFV accuracy / true-to-model program (docs/efv-2026-07-24/
#   GATES-ACCURACY.md), owner directive to maximize accuracy + remove display caps.
#   Restamped from the in-session production regen. FOUR served-number changes:
#   (A1) blend lambda HIT 0.70->0.85 (the old [0.50,0.70] rank_calibration band was a
#     board-movement cap on the REPAIRED labels; re-select lifts pooled OOS Spearman
#     0.3787->0.3835 and contributor AUC 0.7727->0.7758, both bootstrap-clean; pit held
#     0.61 - raising it lowered AUC). This raises hit accuracy site-wide; grades/board shift.
#   (A4) statcast overlay uncapped + default ON for covered players (whiff/velo/AAA-physics
#     survivors; the 2.0 FV display cap + the 4.0/40 ceiling removed per owner; live-board
#     only, ~405 hit + 228 pit covered, moves up to 5.0 FV; run_live only, resolved OOS
#     unaffected).
#   (B1) surplus calibration isotonic-v4 -> linearmap-v5: v4 clamped the high end; a linear
#     floored-at-0 map is more accurate (held-out slope 0.994 vs 1.104, MAE 13.77 vs 14.21,
#     bootstrap-clean). prospx_current base-identity table re-captured under v5 +
#     test_valuation_sets re-stamped (FV50 31.6->28.2).
#   (C1) provisional (efv_ungraded) soft grade cap REMOVED (true-to-model; OOS-invariant,
#     grade map not in the eval path; top de-compresses hit 48->50.3, pit 37.7->40.1).
#   Rowcount 9267 unchanged. Deploy box re-derives under EEPHUS_DEPLOY_RUN shape mode.
# 2026-07-24c restamp: Wave G site-wide true-to-model sweep. KRP+ 40-160 clamp REMOVED
#   (C2; monotone display de-compression, Kade Anderson 160->189.1, 3 live movers). The
#   only served-number change on data/xfv.json; ranks/grades/surplus unchanged.
# 2026-07-24d restamp: Wave H coordinated recalibration (owner decision queue). THREE changes:
#   (1) reliability shrink K 100/80 -> 50/40 (A3, owner-authorized coordinated rebuild): both
#     matrices rebuilt trusting MiLB rates more. Scoreboard arbiter confirmed NO regression -
#     hit held (Spearman 0.3835->0.3834, AUC 0.7758->0.7762) and pit gained (0.302->0.303,
#     AUC 0.7191->0.7197). n_milb_seasons feature-direction gate = KEEP (negative ridge weight
#     is legitimate collinear work with level_rank, not corruption); lambda re-confirmed hit
#     0.85 / pit dynamic 0.54 on the rebuilt matrix. data/xfv_wave_h_eval.json.
#   (2) KRP+ display decouple (owner: decouple display only): the pill now reads a display-only
#     true-signed raw so 834 doubly-below-average arms spread below 100 by severity instead of
#     pinning at 99.3; the eFV MODEL feature x_era_k stays zeroed (grades/ranks byte-identical).
#   (3) KRP+ display era_rel winsorized +-6 (hygiene: a 1-IP ERA blowup no longer drives an
#     absurd pill; range now 27.6-150.5).
#   Rowcount 9267 -> 9268 (pool churn). krp_plus is the only widespread served change; deploy
#   box shape-checks under EEPHUS_DEPLOY_RUN.
# 2026-07-24e restamp: round-2 MLB Pipeline per-team Top 30 DAILY refresh (owner-explicit
#   data fix). The per-team Top 30s were frozen at 2026-01-22 (Jan preseason); the new
#   scrapers.run_mlb_pipeline_org_live (wired run_monthly d0b-ii) refreshed 900 org rows to
#   today, so ~829 active prospects who sit in a team Top 30 but not the overall Top 100
#   gained a CURRENT-dated Pipeline grade. Those fresh grades flow through consensus into the
#   live eFV board, shifting active-prospect grades. The RESOLVED OOS accuracy is unchanged
#   (scoreboard hit 0.3834/0.7762, pit 0.303/0.7197 - the resolved cohort is historical
#   debuted players, unaffected by the 2026 active-grade refresh). Rowcount 9268.
# 2026-07-29 - DELIBERATELY NOT RESTAMPED, and this entry explains why so the next person
#   does not "fix" it with the wrong hash. The committed artifact currently fingerprints
#   39f9224922d2f6c1b49e5723c4d489ec130a91c88cea52384c87e36723a181b9, so this test is red.
#   Two separate reasons stack, and neither is resolved by stamping that hash:
#   (1) The pin below was last set on 2026-07-24e, which PREDATES the entire 2026-07-25
#       program. The 39f9224 hash is simply the 2026-07-28 pipeline output, i.e. drift that
#       was already committed before this program started.
#   (2) This program then shipped changes that WILL move the artifact on the next production
#       regen: the S2 eta-hazard flip (eta.FORTYMAN_ADJ, 54 rows, 22 ETAs a year earlier, 9
#       surplus moves) and the sub-45 empirical anchors (published ctrl_war at the bottom of
#       the board). Stamping 39f9224 now would record a state that is stale on arrival.
#   The standing convention is that the golden is restamped from a PRODUCTION
#   `efv_export.py --all` run on the box, not from a dev tree. So the restamp is OWED on the
#   next box regen, and at that point the new hash should be recorded here together with the
#   S2 and anchor ships as its cause. Under EEPHUS_DEPLOY_RUN=1 this test shape-checks
#   instead of hashing, so the deploy gate is not blocked meanwhile.
_GOLDEN_XFV_SHA256 = "e975a35d4f79e5c0dbe0793fcab44960253f9c9650efec13de59528741c0b711"

# DEPLOY-MODE baseline (see test_xfv_golden_fingerprint). The nightly deploy box
# regenerates data/xfv.json from FRESH data every run, so the exact-hash tripwire
# above is a DEV-TIME guard, not a deploy gate: on the deploy box it would go red on
# the first night real data moves and freeze publishing. Under EEPHUS_DEPLOY_RUN=1 we
# swap the exact hash for a sane-shape check anchored on this recorded row count
# (data/xfv.json by_player, read 2026-07-16 post-DB-repair regen). The +/-20%
# band tolerates ordinary roster churn while still catching a gross
# truncation / empty-artifact regression.
_GOLDEN_XFV_ROWCOUNT = 9268


def test_efv_grade_map_inverts_on_model_window():
    # The eFV grade map must invert on the MODEL's own target window
    # (efv_dataset.TARGET_SEASONS = 6 seasons), NOT the global clemens control_years
    # (=7). The two were coupled once and a control_years flip for valuation silently
    # deflated top-end eFV grades. Guard: every grade-map call in efv_score passes
    # exposure_seasons=TARGET_SEASONS so it can't happen again.
    #
    # 2026-07-30: efv_score now calls TWO maps per row and this pins both.
    #   vf.outcome_implied_fv  -> xfv_grade, THE board number (pooled outcome curve)
    #   vf.realized_implied_fv -> _odds_grade, which keeps p_bucket / p_bust on the
    #                             basis they were ground-truthed on
    # outcome_implied_fv RAISES on a window other than 6 rather than rescaling (its
    # curve is defined on the 6-season label), so the source pin and the runtime guard
    # now say the same thing from both ends.
    import re
    import efv_dataset
    import value_framework as vf
    assert efv_dataset.TARGET_SEASONS == 6
    src = (Path(efv_export.__file__).parent / "efv_score.py").read_text(encoding="utf-8")
    for fn in ("realized_implied_fv", "outcome_implied_fv"):
        calls = re.findall(re.escape(fn) + r"\((.*?)\)", src, re.DOTALL)
        # Real grade-map calls carry a second arg (a comma); the docstring examples
        # `realized_implied_fv(xfv_war)` / `outcome_implied_fv(xfv_war)` have none.
        grade_calls = [c for c in calls
                       if ("xfv_war" in c or "model_war" in c) and "," in c]
        assert grade_calls, f"no {fn} grade-map calls found in efv_score.py"
        for c in grade_calls:
            assert "exposure_seasons=TARGET_SEASONS" in c, (
                f"an eFV grade-map call ({fn}) is missing exposure_seasons=TARGET_SEASONS "
                f"(a control_years flip would silently re-deflate top-end grades): "
                + " ".join(c.split())[:90])
    # The runtime end of the same guard: the outcome curve IS the 6-season window, so
    # asking it for another one is a category error and must fail loudly, not rescale.
    with pytest.raises(ValueError):
        vf.outcome_implied_fv(5.0, exposure_seasons=7)


def test_board_grade_comes_from_the_outcome_curve_not_the_valuation_core():
    """xfv_grade is the inverse of the EMPIRICAL pooled outcome curve, and every
    efv_score path that writes that field must use the SAME map.

    The defect class: data/xfv.json carries active, debuted and bust rows in one file
    under one field name, so a path left on the retired realized_implied_fv map would
    put part of the board on a second grade basis with nothing to detect it -- the same
    shape as the A2 history defect. Source-pinned because the three writers live in
    three functions (run / run_live / run_backgrade) and a fourth (score_history)."""
    import re
    src = (Path(efv_export.__file__).parent / "efv_score.py").read_text(encoding="utf-8")
    # every assignment to xfv_grade (not xfv_grade_display / _quantile / _realized)
    assigns = re.findall(r"^\s*xfv_grade = (.+)$", src, re.MULTILINE)
    assert len(assigns) >= 3, f"expected the three scoring paths, found {len(assigns)}"
    for a in assigns:
        assert "outcome_implied_fv" in a, (
            "an efv_score path assigns xfv_grade from something other than "
            f"vf.outcome_implied_fv: {a.strip()[:90]}")
    # score_history grades through the same map (Phase 3.2 repoint) so the FV-history
    # tail and the board are one number.
    assert "grade = vf.outcome_implied_fv(model_war" in src, (
        "score_history is not on the board grade map; the eFV history series would be "
        "on a third basis again (see test_board_basis_coherence)")


def test_efv_reliability_grade_map_inverts_on_model_window():
    # The reliability/ECE curves (efv_reliability.py) DIAGNOSE the shipped eFV
    # distribution, so their grade-map call must invert on the same 6yr window the
    # scorer ships (exposure_seasons=TARGET_SEASONS). Omitting it defaulted to
    # control_years=7 and the curves measured a distribution the site never shows.
    # Same source-pin as efv_score above, so it cannot silently regress.
    import re
    import efv_dataset
    assert efv_dataset.TARGET_SEASONS == 6
    src = (Path(efv_export.__file__).parent / "efv_reliability.py").read_text(encoding="utf-8")
    calls = re.findall(r"realized_implied_fv\((.*?)\)", src, re.DOTALL)
    grade_calls = [c for c in calls if ("xfv_war" in c or "model_war" in c) and "," in c]
    assert grade_calls, "no realized_implied_fv grade-map calls found in efv_reliability.py"
    for c in grade_calls:
        assert "exposure_seasons=TARGET_SEASONS" in c, (
            "an efv_reliability grade-map call is missing exposure_seasons=TARGET_SEASONS "
            "(the diagnostic would measure a 7yr-window grade the site never shows): "
            + " ".join(c.split())[:90])


def test_krp_plus_gate_reads_rates_missing_from_milb():
    # KRP+ live-pitcher gate: rates_missing lives in r['milb'] (efv_dataset
    # ._season_rates), NOT in efv_model._vec's output. Reading it off the _vec
    # feature vector always defaulted to 1.0 and gated out EVERY live pitcher
    # (dead pill site-wide). Guard the corrected exposure gate.
    import efv_score
    from efv_model import _vec
    complete = {"milb": {"era_rel": -0.5, "rates_missing": 0.0}}
    missing = {"milb": {"era_rel": -0.5, "rates_missing": 1.0}}
    assert efv_score._krp_eligible(complete, True) is True     # rate-complete -> KRP+
    assert efv_score._krp_eligible(missing, True) is False     # rate-missing -> gated out
    assert efv_score._krp_eligible({"milb": {"rates_missing": 0.0}}, True) is False  # no era_rel
    assert efv_score._krp_eligible({"milb": None}, True) is False                    # no milb
    assert efv_score._krp_eligible(complete, False) is False   # hitter -> never KRP+
    # The bug's root: rates_missing is not a key _vec emits, so the pre-fix
    # feats.get('rates_missing', 1.0) could never be 0.0 for any live pitcher.
    assert "rates_missing" not in _vec(complete, "pit")


def test_score_history_no_track_record_uses_prior_not_ridge(monkeypatch):
    # score_history must route a NO-track-record snapshot through the prior-anchor
    # path (like run_backgrade), NOT the ridge -- the ridge applies the trained
    # milb_missing untracked-bust penalty and fabricates a depressed early eFV point.
    # Resolved (milb-present) snapshots must still use the ridge prediction.
    import efv_score
    monkeypatch.setattr(efv_score, "_provisional_prior_war",
                        lambda cons_war, pick, bonus, **kw: (cons_war - 7.0, ["PRIOR"]))
    ridge_sentinel = lambda: 99.0
    # WITH a MiLB track record -> ridge prediction (resolved snapshots unchanged)
    assert efv_score._history_model_war({"milb": {"era_rel": -0.3}}, 3.0, ridge_sentinel) == 99.0
    # NO track record -> prior-anchored off cons_war, NOT the ridge sentinel
    war = efv_score._history_model_war(
        {"milb": None, "pick_overall": 5, "bonus_usd": 1e6}, 3.0, ridge_sentinel)
    assert war == 3.0 - 7.0


def _load_xfv_doc():
    """Read data/xfv.json, retrying once if the read looks torn (the nightly deploy
    runs this test right after the pipeline has rewritten the artifact, so a rare
    mid-write read can raise on partial JSON)."""
    path = DATA / "xfv.json"
    for attempt in range(2):
        assert path.exists(), "data/xfv.json missing"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            if attempt == 0:
                time.sleep(3)
                continue
            raise


def test_xfv_golden_fingerprint():
    # DEPLOY MODE (EEPHUS_DEPLOY_RUN=1, set by deploy/nightly-build.sh): the nightly
    # build regenerates data/xfv.json with fresh data BEFORE gating on the suite, so the
    # exact-hash tripwire below would go red every night real numbers move and freeze the
    # publish. On the deploy box we therefore assert the artifact is present, parses, has a
    # sane row count, and is freshly stamped -- not that it is byte-identical to the dev
    # golden. The exact hash stays a DEV-TIME tripwire (env unset -> behavior UNCHANGED).
    if os.environ.get("EEPHUS_DEPLOY_RUN") == "1":
        doc = _load_xfv_doc()
        bp = doc.get("by_player")
        assert isinstance(bp, dict) and bp, "data/xfv.json has no by_player rows"
        lo = _GOLDEN_XFV_ROWCOUNT * 0.8
        hi = _GOLDEN_XFV_ROWCOUNT * 1.2
        assert lo <= len(bp) <= hi, (
            f"data/xfv.json by_player count {len(bp)} is outside +/-20% of the recorded "
            f"baseline {_GOLDEN_XFV_ROWCOUNT} -- likely a truncated / partial regen.")
        raw = doc.get("meta", {}).get("generated_at")
        assert raw, "data/xfv.json meta.generated_at missing"
        # generated_at is date.today().isoformat() (date-only); tolerate a full timestamp.
        gen = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        now = datetime.now(gen.tzinfo) if gen.tzinfo else datetime.now()
        assert abs(now - gen) <= timedelta(hours=48), (
            f"data/xfv.json meta.generated_at {raw!r} is not within 48h of now -- the "
            "nightly regen did not refresh the artifact.")
        return

    from tools.pipeline_artifact_diff import fingerprint_file
    fp = fingerprint_file(DATA / "xfv.json", None)   # whole-doc hash, volatile keys stripped
    assert fp is not None and "sha256" in fp, "xfv.json missing/unreadable"
    assert fp["sha256"] == _GOLDEN_XFV_SHA256, (
        "data/xfv.json fingerprint changed. If this is an intentional eFV ship, update "
        "_GOLDEN_XFV_SHA256 in this test + record the change; otherwise the artifact "
        "drifted unexpectedly.")


# --------------------------------------------------------------------------
# 3. _asof_point leakage guard -- future points must be ignored
# --------------------------------------------------------------------------
def _rec(points):
    return {"player_key": "leak.test", "points": points}


def test_asof_point_ignores_future_points():
    cutoff = "2023-01-01"                    # e.g. a debut date / decision date
    past = [
        {"snapshot_date": "2022-02-01", "consensus_fv_raw": 45},
        {"snapshot_date": "2022-08-01", "consensus_fv_raw": 50},
    ]
    future = {"snapshot_date": "2023-08-01", "consensus_fv_raw": 65}   # AFTER the cutoff

    pt_clean = _asof_point(_rec(list(past)), cutoff)
    pt_with_future = _asof_point(_rec(past + [future]), cutoff)
    assert pt_clean is not None and pt_with_future is not None
    # same as-of point selected -> same as-of consensus FV, future entry ignored
    assert pt_clean["snapshot_date"] == "2022-08-01"
    assert pt_with_future["snapshot_date"] == "2022-08-01"
    assert pt_clean["consensus_fv_raw"] == pt_with_future["consensus_fv_raw"] == 50


def test_prior_features_asof_consensus_unaffected_by_future():
    """The downstream feature block reads the as-of consensus FV + a leakage-free
    fv_trend; adding a future snapshot changes neither."""
    cutoff = "2023-01-01"
    past = [
        {"snapshot_date": "2022-02-01", "consensus_fv_raw": 45},
        {"snapshot_date": "2022-08-01", "consensus_fv_raw": 50},
    ]
    future = {"snapshot_date": "2023-08-01", "consensus_fv_raw": 65}

    rec_clean, rec_future = _rec(list(past)), _rec(past + [future])
    pt_clean = _asof_point(rec_clean, cutoff)
    pt_future = _asof_point(rec_future, cutoff)
    f_clean = _prior_features(rec_clean, pt_clean, "hit")
    f_future = _prior_features(rec_future, pt_future, "hit")

    assert f_clean["consensus_fv_raw"] == f_future["consensus_fv_raw"] == 50.0
    # fv_trend is net consensus movement up to AND INCLUDING the decision point only
    assert f_clean["fv_trend"] == f_future["fv_trend"] == pytest.approx(5.0)  # 50 - 45, not 65


def test_asof_point_bust_uses_final_point():
    # cutoff=None (bust path) -> the final snapshot, regardless of ordering in the list
    rec = _rec([
        {"snapshot_date": "2021-05-01", "consensus_fv_raw": 40},
        {"snapshot_date": "2020-05-01", "consensus_fv_raw": 35},
        {"snapshot_date": "2022-05-01", "consensus_fv_raw": 45},
    ])
    assert _asof_point(rec, None)["snapshot_date"] == "2022-05-01"
    assert _asof_point(_rec([]), None) is None


def test_role_factor_semantics():
    """Owner-directed reliever-ceiling overlay (2026-07-15, second Moore
    directive): fires ONLY on RP-designated (SIRP/MIRP/RP/CL, never generic P
    or SP) arms whose MODEL war is enthusiastic (>= 1.5); bounded below by 0.70,
    monotone in age. A policy dial, not a fitted parameter - this pin keeps its
    scope from silently widening.

    UPDATED 2026-07-30 (C3): the age term was a STAIRCASE (1.0 below 25.0, a flat
    0.80 on [25, 26), 0.70 above), so it stepped twenty points of projected WAR at
    exactly 25.0. It is now a continuous ramp through the retired staircase's own tier
    MIDPOINTS - (25.5, 0.80) and (26.5, 0.70) - which is why the two age assertions
    below moved: the SCOPE and the FLOOR are unchanged, the cliff is gone. Shape detail
    and the 12-row measured blast radius: test_efv_age_pipeline.py and
    docs/efv-2026-07-30/EFV_LANE_GATES.md."""
    from efv_score import _role_factor
    assert _role_factor({"position": "SIRP", "age_now": 26.9}, 3.5) == 0.70
    assert _role_factor({"position": "MIRP", "age_now": 26.5}, 3.5) == 0.70   # floor knot
    assert _role_factor({"position": "MIRP", "age_now": 25.5}, 3.5) == 0.80   # midpoint knot
    # the ramp starts 1.5 yr before the retired 25.0 step instead of dropping 0.20 at it
    assert _role_factor({"position": "SIRP", "age_now": 23.5}, 3.5) == 1.0   # young: exempt
    assert _role_factor({"position": "SIRP", "age_now": 24.9}, 3.5) == 0.86
    assert _role_factor({"position": "SIRP", "age_now": 26.9}, 1.2) == 1.0   # no model enthusiasm
    assert _role_factor({"position": "P", "age_now": 26.9}, 3.5) == 1.0     # generic P: exempt
    assert _role_factor({"position": "SP", "age_now": 26.9}, 3.5) == 1.0
    assert _role_factor({"position": None, "age_now": 26.9}, 3.5) == 1.0

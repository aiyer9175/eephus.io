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
# Updated 2026-08-05 (omnibus-2 routing regen): an ATTRIBUTED full run_monthly, taken to
#   activate the fv_synthetic_only routing fix shipped at fbdfb1f. That fix changes no
#   served number by itself - it only stops 2,632 constant-FV-35 players from reading as
#   "scouted" and routes them to efv_ungraded, the model built to grade them. by_player
#   rows 9,268 -> 9,379 (+111) and n_active 4,580 -> 4,584 as the rebuild picked up the
#   day's ingests. Restamped from a DEV tree rather than the box, deliberately: the box
#   runs this test in EEPHUS_DEPLOY_RUN=1 shape mode, so the exact hash is a dev-time
#   tripwire only and a box restamp would not have exercised it.
# Updated 2026-08-05 (org reconciliation regen): a second attributed rebuild_only,
#   taken to land the org-authority fix on the served board. eFV MODEL inputs did not
#   change (same 9,379 rows, same features, same lambda, same calibration); what moved is
#   that 1,492 players are now served on the club MLB's transaction feed reports rather
#   than the club a stale prospect list last printed them under, and org rides inside the
#   hashed payload. The FV-bearing fix underneath it: a fabricated `inferred` trade could
#   outrank MLB's own `mlb_api` record because the display resolver took the newest trade
#   by DATE regardless of SOURCE (the Alexander Frias bug).
# Updated 2026-08-06 (roster-map org layer): the org reconciliation reached the FOURTH
#   and last precedence layer. rosters_by_org is itself a build artifact, so its map was
#   overriding the reconciled org in the display resolver's final fallback and 5 players
#   stayed on a club MLB's feed contradicts. 1,496 players reconciled plus 163 roster-map
#   entries corrected; test_org_authority is green for the first time. No eFV MODEL input
#   moved: same rows, features, lambda and calibration. org rides inside the hashed payload.
# Updated 2026-08-06 (corruption repair). data/timeseries.json was found CORRUPT (a JSON
#   decode error 42.9MB in, from two processes writing it at once: a pytest run and a
#   proj_export overlapping). It is gitignored, so there was nothing to restore from and
#   the only repair is a regen. This restamp is that regen, not a model change: no eFV
#   input moved. WORTH KNOWING: the pipeline has more than one writer of this artifact
#   (export_timeseries_json builds it, _patch_export_run_summary re-serialises it), and
#   nothing serialises the pair, so running an export concurrently with anything that
#   patches the summary can truncate a 74MB served file with no error anywhere.
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
# 2026-07-30 RESTAMP - the owed restamp above, taken. This is the production regen the
#   2026-07-29 entry was waiting for, run per docs/efv-2026-07-30/REGEN_AND_PUSH_RUNBOOK.md
#   and stamped from THAT output before pytest ever touched the tree (a mid-suite test
#   regenerates data/xfv.json under fixtures, and stamping from that records a fixture state
#   as production truth). What moved, and why the hash had to change:
#   (1) The POOLED OUTCOME GRADE MAP (c4adead). xfv_grade is now
#       value_framework.outcome_implied_fv(predicted WAR6), the inverse of the empirical
#       FV-to-outcome curve, replacing the side-neutral realized_implied_fv. Grades carry a
#       new MEANING, not just new values.
#   (2) The age-penalty onset at 23.0 (owner dial D2) reaching served output for the first
#       time, plus the usage-based pitcher roles and position_observed work.
#   (3) The fabricated baseballamerica_statcast_by_age FV removed at the source: 41 rows
#       re-ingested with fv IS NULL, so that invented 40.0 no longer votes in consensus.
#   Board effect, verified against the paired capture in POOLED_OUTCOME_REFIT.md: arias
#   60.4 rank 2, brayden_taylor 48.2 rank 125 and enrique_bradfield_jr 48.2 rank 127 (both
#   out of the top 100, which was the point of the age dial), top-100 side mix 92H/8P inside
#   its band, history basis flipped onto the board basis so the eFV-delta movement signal
#   un-suppresses. Rowcount 9268 -> 9324.
# 2026-07-30b RESTAMP: the E1 repeat-level ship (seasons_at_level added to the PITCHER
#   feature set only, owner decision on docs/efv-2026-07-30/E1_REPEAT_LEVEL_GATE.md).
#   Every pitcher's model WAR moves, so the grade and the board order move with it;
#   hitters are byte-stable by construction because the feature is excluded there.
#   Shipped inside the generic MDE95 on the strength of the feature-specific permutation
#   null (0 of 30 draws beat the real +0.0127, p=0.032). Coordination in the same commit:
#   the board fingerprint now HASHES THE FEATURE SPEC, because until today it could not
#   see a model change at all -- scale, grade map and role mode were all it knew, so a
#   new feature moved the whole board while the fingerprint reported "no change".
#   Rowcount 9324 -> 9334.
# 2026-07-31 RESTAMP: the v6 EV surplus calibration (owner decision on
#   docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md). PRICING LAYER ONLY -- verified, not
#   assumed: across all 9,334 rows, ZERO changed xfv_grade, xfv_grade_quantile or
#   xfv_war_6yr, so the board ORDER is byte-identical and only surplus_mm moved.
#   Every one of the 9,334 prices moved and every one moved UP (min +$0.70M, median
#   +$2.00M, p90 +$8.20M, max +$11.30M); board total $33,660M -> $58,688M (+74.4%).
#   The headline: the 6,271 rows priced at exactly $0 fell to 0. That $0 was a clamp,
#   not a valuation -- the v5 map minimised per-player MAE, which on a population where
#   86-90% of the bottom bins realise nothing is optimised by predicting the median,
#   i.e. zero. Surplus is consumed as a PRICE, and a price is an expectation, so the
#   objective moved to the conditional mean and the clamp went with it.
#   Rowcount 9334 -> 9334 (unchanged).
# 2026-07-31b RESTAMP: the ODDS DISPERSION CALIBRATION wired in (owner decision; gate
#   docs/efv-2026-07-30/ODDS_CALIBRATION_SLOPE_GATE.md, artifact
#   data/xfv_odds_calibration_slope_eval.json). p_bucket_given_fv is fitted on the
#   CONSENSUS-FV scale (sd 6.57) and read at the realized-implied grade (sd 15.54),
#   2.4x wider, so its log-odds ran about 2.7x too steep. One monotone Platt map in
#   log-odds per side fixes the slope.
#   ODDS ONLY -- verified, not assumed: across all 9,334 rows, ZERO changed xfv_grade,
#   xfv_grade_quantile, xfv_war_6yr or surplus_mm. The map is strictly monotone, so
#   board order is invariant by construction rather than by luck.
#   9,320 of 9,334 p_bust values moved, 8,073 by more than 5 points (5,743 down,
#   2,330 up), and every p_bucket vector still sums to 1 (bust mass replaced, the
#   other four rescaled).
#   Gate cleared on every condition: beats the incumbent (Brier +0.0301 CI
#   [+0.0211,+0.0391], log loss +0.0911 CI [+0.0653,+0.1168]) AND a constant base rate
#   (+0.0314 / +0.1018), all four CIs clean of zero, which is the bar two prior odds
#   lanes failed. Label-shuffle control p=0.0 on both; monotone; 6 time splits.
#   Calibration slope 0.6446 -> 1.1351, ECE 0.1528 -> 0.0428.
#   Brayden Taylor p_bust 0.309 -> 0.605 and Bradfield 0.319 -> 0.609, most of the way
#   to their 77.1% outcome-comp cohort rate, reached with ZERO cohort information. The
#   cohort lane that chased this directly was a measured NO-SHIP.
#   Rowcount 9334 -> 9334 (unchanged).
# 2026-08-03 -- FanGraphs 2026 UPDATED BOARD (published 2026-08-02) ingested.
#   1,384 snapshots from the four-CSV set (summary/position/pitching/physical),
#   carrying FV, future tool grades, present grades, physicals and 1,379 scouting
#   reports. This is a DATA refresh, not a basis change: board_basis_fingerprint
#   is untouched and BOARD_RANK_BASIS_EPOCH stays 2026-07-30.
#   Consensus supersedes per source (latest-per-source forward fill), so the new
#   board replaced the 2026-07-23 trade-deadline vote rather than averaging with
#   it. Of the 43 players whose FanGraphs FV actually moved, all 37 with a
#   readable consensus moved the SAME direction, none opposite.
#   Rowcount 9338 -> 9366 (+28); eFV changed on 1,154 of 9,334 common rows and
#   consensus on 1,386 -- both figures also carry the 2026-08-01..03 eFV fixes
#   (the run_backgrade NameError and the resolved-seam Platt no-op) and three
#   days of drift, so they are NOT attributable to the board alone.
#   Jesus Made is the new board #1 (FV 65, eFV 61.0).
#   Identity: the ingest re-merged carlos_castillo (Angels OF onto the Pirates
#   RHP incumbent) because the newcomer carries NO FanGraphs PlayerId, so
#   neither the PID disambiguator nor scrapers._SPLIT_KEYS (MLBAM-keyed) could
#   see him. Fixed forward by fangraphs_csv._FG_ORG_SPLIT_KEYS and repaired in
#   the DB by tools/repair_carlos_castillo_collision.py --apply.
# 2026-08-04 -- NIGHTLY run_monthly REGEN (13:16-14:21 local), not a basis change.
#   The pipeline rebuilt the matrices and re-scored the board on the same
#   grade map; BOARD_RANK_BASIS_EPOCH stays 2026-07-30 and the board basis
#   fingerprint is unchanged. Rowcount 9366 -> 9369 (+3).
#   The one CODE change in the window that reaches this artifact is the pitcher
#   blend-lambda pin (efv_model._BLEND_LAMBDA_RESELECT pit None -> 0.57). That
#   is a stability pin, not an accuracy claim: pooled blend rho spans 0.0025
#   across the whole [0.50, 0.70] selection band, 0.16x the pitcher MDE95, so
#   the dynamic selector was an argmax over noise that moved published grades
#   every rebuild. meta.live_lambda now reads {hit 0.70, pit 0.57} and matches
#   the pin. The hitter side was already pinned and did not move.
#   Restamped deliberately; the eFV eval artifacts and the side-fairness gate
#   were regenerated on the same shipped lambdas in the same session.
# 2026-08-04b -- REBUILD-ONLY after the identity repair. run_monthly --rebuild-only
#   was run so the five merged-identity splits (tools/repair_merged_identities_
#   2026_08_04.py, 26 guarded writes) would reach the board; the audit reads
#   timeseries.json, so a DB-only repair is invisible until the board is rebuilt.
#   Rowcount 9369 -> 9369 (unchanged). Basis epoch stays 2026-07-30. The board
#   fingerprint DID move (feats dbb1bc2a -> b747e1d3) but only because the hitter
#   `age` sign declaration moved -1 -> 0, which binds the eval-only monotone
#   challenger and not the served ridge, so no grade moved because of it.
# 2026-08-04c -- the jack_natili / jackson_natili SPELLING SPLIT collapsed. One
#   human held two ACTIVE keys because the draft-signing feed spells him "Jack"
#   (that is the wording of the 2026-07-20 Rockies transaction) while FanGraphs
#   and MLBAM spell him "Jackson". He was reaching the SERVED board TWICE, at
#   ranks 155 and 320 with grades 45 and 42, and his surplus was DOUBLE COUNTED
#   at $16.7M plus $3.8M. Fixed by adding him to consensus.PLAYER_KEY_ALIASES,
#   the same read-time mechanism that already handles yeremi_cabrera, rather
#   than by re-keying the database: the alias is reversible and re-applies every
#   rebuild, and the DB survey found a key remap would have thrown on 23 of 30
#   rows (both keys hold snapshots on the same dates under PK(player_key,
#   snapshot_date)). See docs/identity-2026-08-04/JACK_NATILI_REMAP_PROPOSAL.md.
#   Rowcount 9369 -> 9368, exactly the one duplicate. identity_collisions
#   critical_active_player_keys ["jack_natili"] -> [] and c3_unresolved_active
#   1 -> 0. One DB write accompanied it, and it was NOT a remap: the $1,097,500
#   signing bonus was stranded on the losing key's acquisitions row, so it was
#   copied onto the canonical row value-guarded (fills a NULL only, verified
#   idempotent, 1.5GB backup taken first). The canonical row's pick_round 3 was
#   kept over the orphan's contradictory 1.
#   Stamped from the run_monthly --rebuild-only output (xfv.json mtime 21:26:42,
#   BEFORE the suite ran) and re-verified outside pytest with
#   tools.pipeline_artifact_diff.fingerprint_file, per the 2026-07-30 note above:
#   a mid-suite test regenerates xfv.json under fixtures, and stamping from that
#   would record a fixture state as production truth.
# RESTAMPED AGAIN 2026-08-06 (tool_provenance added to meta; no served GRADE
# moved, only the meta block gained a field). Prior restamp note follows.
# RESTAMPED 2026-08-06, see CHANGELOG.md for that date. Two owner-decided
# changes moved served values: SCORED_YEARS promoted 4 folds -> 11, and the
# tool gate gained a real paired-bootstrap MDE which failed `hit` where the
# bare `br > gr` had passed it. 178 tool_xfv blocks moved, zero headline xfv.
# RESTAMPED 2026-08-14, the GRADE-BASIS EPOCH. This one moved served grades on
# purpose and at scale, so it is the restamp the ledger above exists for.
# docs/efv-2026-08-13/GRADE_BASIS_EPOCH_GATE.md.
#
# Three changes reached the artifact in one rebuild sequence:
#   1. the Defect A dispersion correction, an affine level fix on xfv_war applied
#      at the grade seam (a_c/b_c hit 0.470359/0.663929, pit 0.493744/0.546915),
#      fitted out of fold on the production frame. 4,585 of 4,664 served grades
#      moved; rows pinned at the -2.0 WAR floor went to ZERO.
#   2. the MLB Pipeline vintage repair, 540 snapshot rows deleted (current-year
#      accretion plus the 2011/2014/2016 wrong-list orphans).
#   3. two split identities merged through consensus.PLAYER_KEY_ALIASES.
#
# Routing is decided on the UNCORRECTED grade, so the routed cohort is preserved:
# 2,400 rows against 2,397 before, verified on this artifact rather than assumed.
#
# Stamped from tools.pipeline_artifact_diff.fingerprint_file OUTSIDE pytest, on the
# xfv.json written at 23:01 by rebuild pass 3, per the 2026-07-30 note above: a
# mid-suite test regenerates xfv.json under fixtures and stamping from that would
# record a fixture state as production truth.
# RESTAMPED AGAIN 2026-08-14, same day, DISPLAY ONLY. The factor explainer gained a
# "Level calibration" chip naming the dispersion correction's own contribution
# (owner: "why is eFV -4 on Jesus Made when all of his drivers are positive?").
# No served grade, WAR, surplus, probability or ordering moved: the chip is inserted
# into factors[] after every number is computed. Made now reads
# Level calibration down 3.59 against five up-chips totalling 1.97, so the sign of
# the delta is finally visible on the card. Prior restamp note follows.
# RESTAMPED 2026-08-14, THE C-4 ERA-FLOOR FLIP. consensus.GRADE_NORM_AS_OF is now
# True and the cutoff is threaded through all six remapper constructions, so a
# pre-2017 grade is normalized against its OWN era instead of a pool reaching
# forward to 2026. Verified in production: the mlb_pipeline hitter 2013 cell now
# estimates from 309 own-era pairs at +4.2880, against 3,949 pooled pairs at
# +4.0567 before, reproducing the 2026-08-13 measurement exactly. In-window cells
# (2019: 395 pairs, +4.1519) are byte-identical either way.
#
# THE SERVED BOARD BARELY MOVES, which is the honest headline and was predicted:
# 2 active rows change consensus_fv (+0.60 each) and 435 change xfv_grade by a
# mean of +0.054. The flip's value is in the HISTORICAL vintages that feed the
# backtests, not on today's board, and C4_ERA_FLOOR_MEASUREMENT.md said in advance
# that nobody should expect it to move a margin.
#
# Dispersion coefficients deliberately NOT re-fitted for this basis change, so this
# hash carries C-4 and nothing else; see the pinning rule at
# efv_score._DISPERSION_CORRECTION. Stamped OUTSIDE pytest from the pass-2
# artifact. Prior restamp note follows.
# Restamped 2026-08-14 for C-6 + C-6b + C-7, three sanctioned ships in one artifact.
# Stamped OUTSIDE pytest from the post-rebuild file, per the standing rule.
#   C-7  the dispersion correction reverts to identity on the owner's decision, so
#        xfv_war_6yr moves on 99.9% of rows and xfv_grade on 33.7%. No dollar and no
#        rank moved. docs/efv-2026-08-13/DISPERSION_REVERT_GATE.md.
#   C-6  xfv_minus_consensus becomes NULL where no comparison exists, and two reason
#        markers are added to the schema.
#   C-6b the same suppression applied at the export funnel, closing the run_backgrade
#        path that reached the board without the seam.
#        docs/efv-2026-08-13/CONSENSUS_DELTA_HONESTY_GATE.md.
# 2026-09-04 RESTAMP: THE eWAR LABEL EPOCH. Stamped from the production
#   `run_monthly.py --rebuild-only` output of the rebuild wave (WAR_BASIS_RUNBOOK steps O
#   through R), read BEFORE pytest touched the tree, per the standing convention above.
#   What moved: career_war was rebased from bWAR to eWAR v2, so the eFV first-6yr training
#   label moved for every debuted row; the pooled FV outcome curve was refit on that label
#   and its hash went outcome_pooled@6dbe8353f3bb -> @1f3fa0a970bd, which changes every
#   served grade because xfv_grade is that curve inverted; the empirical anchors and the
#   survivor curve were refit on the same table. BOARD_RANK_BASIS_EPOCH bumped to
#   2026-09-04 and BOARD_BASIS_FINGERPRINT gained a `label=` term in the same commit, so
#   the movement engine will not publish the one-time re-rank as player movement.
#   Gate: docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md section 9. The swap is an OWNER
#   BASIS decision and NOT an accuracy claim: the measured effect on the eFV margin is
#   +0.00006 on hitters (ruled out as equivalent) and -0.01823 on pitchers (undecided).
#   Rowcount 9379 -> 9502.
# 2026-09-04b RESTAMP: THE INJURY HAIRCUT WENT PITCHER-ONLY (efv_score.INJURY_PENALTY_SIDES,
#   owner decision on measured outcomes; the constant carries the numbers). It lifts the
#   haircut off 225 served hitters at a median x0.738 and leaves 360 pitchers untouched.
#   Grade effect on those 225: 74 up, 150 flat and 1 down, mean +0.31 FV, max +4.6
#   (leo_de_vries 55.5 -> 60.1). The 150 flat are pinned at the FV20 floor, where
#   outcome_implied_fv is constant below 0 WAR. The 1 down is cameron_nelson, whose
#   grade_basis flips provisional_capped -> outcome_pooled as his model WAR crosses zero:
#   pre-existing floor-routing behaviour at a boundary, not a new defect.
#   BOARD_BASIS_FINGERPRINT gained an injsides= term in the same commit, and this rides the
#   SAME BOARD_RANK_BASIS_EPOCH 2026-09-04 as the label epoch.
# 2026-09-25 RESTAMP: DS-02, eFV V2 SERVES (efv_v2_serve; owner answer DS-Q1). Every
#   consensus-graded active row now carries V2's grade (the consensus value at its rank in
#   V2's order inside its side), board_sort_key is the order index, the odds and dollars
#   read that grade, and constant-anchor rows are served by the provisional model. The
#   hash had already drifted from the previous stamp on data alone (a known red); this
#   stamps the committed V2 artifact. Rowcount 9502 -> 9509.
# 2026-10-03 RESTAMP: THE fWAR LABEL EPOCH. Stamped from the production
#   `efv_export.py --all --eval` output of step P (WAR_BASIS_RUNBOOK step V), read BEFORE
#   pytest touched the tree; rebuild passes 2 and 3 (step R, the third after the Spotrac
#   position repair) wrote the identical fingerprint. What moved: career_war was rebased
#   to published fWAR (the training label, frozen vintage 2026-10-02-0341299c20ec) and
#   efv_dataset.RESOLVED_THROUGH moved 2025 -> 2026 in the same rebuild, so the eFV
#   first-6yr label moved for every debuted row and the 2025 debut cohort entered; the
#   pooled FV outcome curve was refit on that label (outcome_pooled@1f3fa0a970bd ->
#   @baa9676f90a6), which changes every served grade; the anchors and the survivor curve
#   were refit at step J. BOARD_RANK_BASIS_EPOCH 2026-10-03 and the fingerprint's
#   label=fwar@2026-10-02-0341299c20ec moved in the step D + U commit. Gate:
#   docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 9. The swap is an OWNER BASIS
#   decision and NOT an accuracy claim (gate clause (l)); the measured dispositions are
#   recorded in part 9's step Z entry. Rowcount 9509 -> 9515.
# 2026-10-04 RESTAMP: THE P5 RE-DERIVATION (owner answer B7-P5, option A; c40c0dd0). eFV
#   v2's DS-08 weights were re-fit once on the frozen fWAR label (hit w_skill 0.599508 ->
#   0.908861, w_time 0.012287 -> 0.202573; pit w_time 0.107279 -> 0.020473), so V2's order
#   index moved and with it the served grade: 947 of 9,515 rows (500 up, 447 down, mean
#   |delta| 1.42, 29 by 5 or more, largest angeibel_gomez -8.1), board_sort_key on 1,055,
#   surplus_mm on 798. Stamped from the POST_EPOCH_REBUILD run (run_monthly --rebuild-only
#   rc 0, then export_trade_values and the ledger/franchise rebuild) on the merged code,
#   read before pytest touched the tree. BOARD_RANK_BASIS_EPOCH 2026-10-04 and the
#   fingerprint's served=efv_v2@bcc9b0dd moved with it. A refit on a new label, not an
#   accuracy claim (gate clause (l)). Rowcount 9515 unchanged.
# 2026-10-09 RESTAMP: M11_PROSPECT_ARB_VIA_MODEL (docs/ARBITRATION_GATE.md section 20).
#   Prospect arbitration seasons price through the award model and the calibration knots
#   were refit, so surplus_mm moves on 1,756 of 4,691 active rows (1,545 up, 211 down) and
#   no grade, quantile, p_bust or WAR field moves. The committed file at HEAD already read
#   65b77ee1... against the 9b21c897... pinned here (stale before this change), and the
#   file stamped here also carries 63 rows of input churn from the 2026-10-09 regen.
# 2026-10-09 INTEGRATION RESTAMP (M11_PROSPECT_ARB_VIA_MODEL merged into the main tree):
#   regenerated on the merged code (arb_export.export, run_monthly --rebuild-only twice,
#   export_trade_values); against the branch's stamped file 505 of 9,515 rows move dist and
#   band_p90_mm (501) and surplus_mm on 23; no grade, quantile, p_bust or WAR field moves.
# 2026-10-16 RESTAMP: EFV_PIT_AUDIT_FIXES (owner decision EW3-36, CON-3). The pitcher popup
#   chip label now says a low popup rate grades up and why, on 298 chips; no grade, order,
#   quantile, p_bust, surplus or WAR field moves (efv_score.run_live pit and efv_export.run;
#   the only other moved value is meta.served_model.disclosures.dark_basis, its read date).
#   The committed file at HEAD already read ff17956c... against the a1270cc3... pinned here
#   (stale before this change). Rowcount 9515 unchanged.
_GOLDEN_XFV_SHA256 = "3c1f0b7d9d8a440d1184a1605e5e45ca3501dba83e146143ca3e0115aaa4eb6a"
# OWED RESTAMP, and it cannot be paid from a dev box. On 2026-08-07 _entry started
# whitelisting three fields efv_score already emitted (grade_basis, board_sort_key,
# factors_more) and efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT flipped True, which
# moves 2,434 served grades. The committed artifact predates all of it, so this hash is
# still correct TODAY and this test still passes. The FIRST regen that writes those
# fields moves the hash, and whoever commits that artifact restamps this constant and
# records it. Not a drift alarm when it happens; it is this ship arriving.
# Ship record: docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SHIP.md.

# DEPLOY-MODE baseline (see test_xfv_golden_fingerprint). The nightly deploy box
# regenerates data/xfv.json from FRESH data every run, so the exact-hash tripwire
# above is a DEV-TIME guard, not a deploy gate: on the deploy box it would go red on
# the first night real data moves and freeze publishing. Under EEPHUS_DEPLOY_RUN=1 we
# swap the exact hash for a sane-shape check anchored on this recorded row count
# (data/xfv.json by_player, read 2026-07-16 post-DB-repair regen). The +/-20%
# band tolerates ordinary roster churn while still catching a gross
# truncation / empty-artifact regression.
_GOLDEN_XFV_ROWCOUNT = 9515


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
    # THE ONE SANCTIONED EXCEPTION, and it is gated. The floor-routing lane serves
    # the PROVISIONAL grade for the fabricated-anchor cohort, whose rows the outcome
    # curve cannot separate at all (it returns its floor knot for every non-positive
    # WAR, which is 73% of actives). That is a deliberate second map on a named
    # subset, so it is allowed by name here and pinned OFF by
    # test_board_basis_coherence; what is still forbidden is a path drifting back
    # onto the RETIRED realized_implied_fv map, which is what this guard exists for.
    routed = 0
    for a in assigns:
        if "_routed" in a:
            routed += 1
            continue
        assert "outcome_implied_fv" in a, (
            "an efv_score path assigns xfv_grade from something other than "
            f"vf.outcome_implied_fv: {a.strip()[:90]}")
    # The routed value must come from the floor-routing predicate and NOT from the
    # retired map. realized_implied_fv is still referenced elsewhere in this module
    # on purpose (it is the pinned basis for _odds_grade, whose p_bucket and p_bust
    # are ground-truthed on it), so the check is on this path, not on the file.
    if routed:
        assert re.search(r"_routed\s*=\s*route_floor_grade\(", src), (
            "a routed xfv_grade path does not come from route_floor_grade")
        assert not re.search(r"_routed\s*=.*realized_implied_fv", src), (
            "the floor-routing path assigns from the RETIRED realized_implied_fv map")
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

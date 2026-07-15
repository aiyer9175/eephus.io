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
    """Read-only: in the shipped artifact, xfv_grade IS xfv_grade_realized for every
    player, and the quantile field is present + differs for the vast majority."""
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc["by_player"]
    assert len(bp) > 1000
    both = 0
    distinct = 0
    for e in bp.values():
        assert e.get("xfv_grade") == e.get("xfv_grade_realized"), "headline != realized alias"
        if e.get("xfv_grade") is not None and e.get("xfv_grade_quantile") is not None:
            both += 1
            if abs(e["xfv_grade"] - e["xfv_grade_quantile"]) > 1e-9:
                distinct += 1
    assert both > 1000
    # the two scales genuinely differ in production (they are not the same number)
    assert distinct > 0.5 * both


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
_GOLDEN_XFV_SHA256 = "f3b9b7d2b1bb8b8721eaeb5bad46f5ff2764e316e8630ee7b99d5e3e72d93eaa"

# DEPLOY-MODE baseline (see test_xfv_golden_fingerprint). The nightly deploy box
# regenerates data/xfv.json from FRESH data every run, so the exact-hash tripwire
# above is a DEV-TIME guard, not a deploy gate: on the deploy box it would go red on
# the first night real data moves and freeze publishing. Under EEPHUS_DEPLOY_RUN=1 we
# swap the exact hash for a sane-shape check anchored on this recorded row count
# (data/xfv.json by_player, read 2026-07-14 post-repair; the bust re-scale
# added ~240 rows net). The +/-20% band tolerates ordinary roster churn while
# still catching a gross truncation / empty-artifact regression.
_GOLDEN_XFV_ROWCOUNT = 9127


def test_efv_grade_map_inverts_on_model_window():
    # The eFV grade map (realized_implied_fv) must invert on the MODEL's own target
    # window (efv_dataset.TARGET_SEASONS = 6 seasons), NOT the global clemens
    # control_years (=7). The two were coupled once and a control_years flip for
    # valuation silently deflated top-end eFV grades. Guard: every grade-map call in
    # efv_score passes exposure_seasons=TARGET_SEASONS so it can't happen again.
    import re
    import efv_dataset
    assert efv_dataset.TARGET_SEASONS == 6
    src = (Path(efv_export.__file__).parent / "efv_score.py").read_text(encoding="utf-8")
    calls = re.findall(r"realized_implied_fv\((.*?)\)", src, re.DOTALL)
    # Real grade-map calls carry the side arg (a comma); the docstring example
    # `realized_implied_fv(xfv_war)` has none -> excluded.
    grade_calls = [c for c in calls if ("xfv_war" in c or "model_war" in c) and "," in c]
    assert grade_calls, "no realized_implied_fv grade-map calls found in efv_score.py"
    for c in grade_calls:
        assert "exposure_seasons=TARGET_SEASONS" in c, (
            "an eFV grade-map call is missing exposure_seasons=TARGET_SEASONS "
            "(a control_years flip would silently re-deflate top-end grades): " + " ".join(c.split())[:90])


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
    or SP) arms age 25+ whose MODEL war is enthusiastic (>= 1.5); bounded
    0.80/0.70, monotone in age. A policy dial, not a fitted parameter - this
    pin keeps its scope from silently widening."""
    from efv_score import _role_factor
    assert _role_factor({"position": "SIRP", "age_now": 26.9}, 3.5) == 0.70
    assert _role_factor({"position": "MIRP", "age_now": 25.4}, 3.5) == 0.80
    assert _role_factor({"position": "SIRP", "age_now": 24.9}, 3.5) == 1.0   # young: exempt
    assert _role_factor({"position": "SIRP", "age_now": 26.9}, 1.2) == 1.0   # no model enthusiasm
    assert _role_factor({"position": "P", "age_now": 26.9}, 3.5) == 1.0     # generic P: exempt
    assert _role_factor({"position": "SP", "age_now": 26.9}, 3.5) == 1.0
    assert _role_factor({"position": None, "age_now": 26.9}, 3.5) == 1.0

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV Pass 3 -- the production seam: turn the hitter model's WAR prediction into
the flagship outputs (grade + 5-bucket distribution + surplus $ + uncertainty),
reusing the existing value_framework engine end to end.

Pipeline per player:
  features -> ridge E[6yr summed bWAR] -> linear calibration (scale) = xfv_war
          -> vf.outcome_implied_fv(xfv_war)             = xfv_grade (20-80, THE board number)
          -> vf.realized_implied_fv(xfv_war)            = _odds_grade (retired map, odds only)
          -> vf.p_bucket_given_fv(_odds_grade)          = 5-bucket distribution
          -> vf.expected_surplus_usd(_odds_grade, ...)  = surplus $ (engine-calibrated)
          -> vf.sv_distribution(_odds_grade, ...)       = uncertainty band
          -> rank_war quantile map                      = xfv_grade_display, and the
                                                          surplus RE-PRICE that overwrites
                                                          the dollars above

TWO GRADE MAPS, on purpose (LANE-P2, 2026-07-30). xfv_grade is now the inverse of the
EMPIRICAL pooled outcome curve (data/fv_outcome_curves_pooled.json): grade G means "the
industry FV whose realized first-6yr outcome distribution matches our prediction". The
outcome ODDS keep the retired realized_implied_fv basis because they are validated
probabilities and nothing in this commit measured a re-key. The consequence to hold in
your head when reading a row: xfv_grade and p_bust are answers to two different questions
and are not two views of one number. docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md 1.3.

xfv_grade is monotone in xfv_war (outcome_implied_fv is a strictly increasing curve's
inverse), which is monotone
in the model prediction -> xfv_grade inherits the model's rank edge over consensus FV
(see data/xfv_eval.json). The surplus reuses the engine's own isotonic calibration,
applied ONCE at this seam (vf.apply_calibration on the raw expected_surplus_usd /
sv_distribution dollars, the same layer surplus_value_mm applies); we do NOT
re-calibrate on top (no double-correction).

Artifacts: data/xfv_scored.json (per-player) + report block. Run: python efv_score.py
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import value_framework as vf
import efv_factor_groups as _fgroups
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman
from efv_model import _prep, _vec, _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from efv_dataset import matrix_path, live_matrix_path, CURRENT_SEASON, TARGET_SEASONS
# Shared no-ETA fallback timing (bughunt F3): both surplus writers (this module +
# storage's consensus payload) must assume the SAME years-to-debut for a prospect
# with no resolvable ETA, or the two adjacent dollar columns diverge on timing.
from storage import PROSPECT_ETA_FALLBACK_YEARS

try:
    # S-XLINE-4 bounded A/CPX live overlay (docs/efv-2026-07-23/GATES.md);
    # default-OFF flags live in the module, absence degrades to a no-op.
    import efv_statcast_overlay as _xoverlay
except Exception:  # pragma: no cover - optional sidecar module
    _xoverlay = None


# P1 V2 clause-2 baseline floor. See the ANCHOR DECOUPLING note in
# _provisional_prior_war._ref_war. The sub-45 empirical anchors were amended on
# 2026-07-29 (0.19 WAR/yr flat -> measured 0.019 at FV35 / 0.086 at FV40), which drags
# vf.expected_six_year_avg_war down with it via _war_scale_for. P1 V2 was gated on the
# pre-amendment scale, so its baseline is pinned here rather than inheriting a change it
# was never re-gated against. These are the pre-amendment WAR/yr values on the shipped
# anchor grid; the table is deliberately explicit rather than a call into the config, so
# that a future --fit cannot move it silently.
_P1_BASELINE_ANCHOR_FLOOR = True
_P1_LEGACY_ANCHOR_WAR_PER_YR = 0.19   # the pre-2026-07-29 constant across FV 20..40


def _p1_legacy_mix6(cons_fv: float, is_pitcher: bool) -> float:
    """The P1 V2 mixture baseline as it stood BEFORE the sub-45 anchor amendment.

    Reproduces vf.expected_six_year_avg_war(cons_fv, is_pitcher) * 6 under the legacy
    flat 0.19 WAR/yr anchor, by rescaling the CURRENT bucket mixture by the ratio of the
    legacy anchor to the amended one. Returns 0.0 if anything is unavailable, which
    degrades this floor to a no-op rather than inventing a number.
    """
    try:
        import value_framework as _vf
        m = _vf.expected_six_year_avg_war(float(cons_fv), bool(is_pitcher))
        cur = _vf.fv_to_6yr_avg_war(float(cons_fv))
    except (TypeError, ValueError, AttributeError):
        return 0.0
    if m is None or not cur or cur <= 0:
        return 0.0
    return float(m) * (_P1_LEGACY_ANCHOR_WAR_PER_YR / float(cur)) * 6.0


def _provisional_prior_war(cons_war: float, pick_overall, bonus_usd,
                           cons_fv=None, is_pitcher=None,
                           acq_year=None) -> tuple[float, list]:
    """P1 V2 (audit B5; docs/efv-provisional-prior/GATES.md V2 registration) - the
    no-MiLB-track-record prior. A bounded, upward-only pedigree CREDIT toward the
    draft-slot first-6 WAR expectation, weighted by pedigree precision (pick tier +
    log-scale bonus). Returns (prior_war, factors). When disabled, or when neither a
    draft pick nor a wired IFA step applies, returns (cons_war, []) - today's
    consensus-only behavior, so gating this OFF is byte-identical.

    Math (V2): prior = cons_war + w * pull,
      pull    = clip(slot_war - ref_war, 0, pull_cap_war)      [Fix A: bounded]
      ref_war = max(cons_war, TARGET_SEASONS *
                    vf.expected_six_year_avg_war(cons_fv, is_pitcher))  [Fix B]
      w       = pedigree / (pedigree + base), pedigree = pick tier + bonus log trust
                (capped) - the V1 weight, untouched.
    Fix A (V1 defect A): pull_cap_war = 1.9 was derived A PRIORI from the display
    grade map's worst-case slope so lam * w_max * cap stays under the 5.0 FV bound
    (see GATES.md V2 derivation; do not retune it post-hoc). Fix B (V1 defect B):
    the consensus OLS floors at 0.0 WAR for the FV 35-38 mass, so the pull baseline
    is the calibrated bucket-mixture expectation (bust-inclusive, FV-monotone,
    ~1.11-1.17 WAR there) instead of that degenerate zero; tiny slot WAR past pick
    75 can no longer dominate. The pull is floored at 0 because a trusted BELOW-
    baseline slot expectation would make the prior decrease in pedigree (a clause-2
    inversion channel V1 carried). Bonus still adds TRUST (a weight), never a WAR
    value - it is dimensionless precision, never summed as WAR.

    IFA step arm (gated separately, ifa_step_enabled; wiring conditional on the P1
    V2 flip): an IFA row (no overall pick) with bonus_usd >= ifa_step_bonus_usd gets
    the same rails with slot_war replaced by ifa_step_war (the validated >= $1M
    first6-basis step mean, data/ifa_step_prior_eval.json) and w from
    ifa_step_precision (0.25, deliberately below draft round-1: a bonus is softer
    information than a pick). Sub-$1M / missing-bonus IFA rows return cons_war
    unchanged - the ifa_pedigree loss ledger showed sub-$1M bonus rank carries
    zero-to-inverted information ("no WAR from a bonus alone" stands, with evidence).

    UNITS INVARIANT (do not break): every term is 6-SEASON-TOTAL WAR. cons_war =
    _pred_ols on the target_censored column, which efv_dataset builds over a
    TARGET_SEASONS=6 window (obs_sum + tail); storage._pick_slot_expected_war returns
    the first6_step_curve; expected_six_year_avg_war is per-season and is multiplied
    by TARGET_SEASONS here; ifa_step_war is frozen on the first6 basis. So the credit
    is on one axis and feeds rank_war/realized_implied_fv unchanged. If any basis
    ever changes to per-season, rescale the others here or grades shift ~6x.

    P1 V3 arms (GATES.md V3 registration 2026-07-23, the Grady Emerson case;
    SHIPPED DEFAULTS: ARM-A ON / ARM-B OFF -- see the flip record below; the
    environment is read at CALL time and overrides in both directions):
      EEPHUS_P1_SLOT_TRUST (ARM-A, correctness class / _TOOL_IMPUTE precedent):
        where bonus_usd is missing AND draft_results carries slot_usd for the pick
        AND the pick IS a current-class selection not yet signed (enforced via the
        threaded acq_year -- bughunt F3 feeds 2026-07-23: the slot lookup keys on
        pick_overall alone, so historical NULL-bonus acquisitions sharing a pick
        number could take the branch; acq_year != CURRENT_SEASON never does now),
        the bonus log-TRUST term consumes slot_usd in place of the bonus. Trust
        only, never a WAR value; upward-only by construction (w rises, pull >= 0).
      EEPHUS_P1_DSPLUS (ARM-B): ped += 0.4 * max(0, (DSplus - 100) / 10), DSplus =
        the class-normalized pre-draft Draft Stock+ (current class joined through
        the draft export payload's rank-consensus DS+; historical classes
        recomputed per class from draft_snapshots). Rows without a computable
        DSplus are unchanged. Scale 0.4 and the /10 normalization are frozen
        a-priori registration constants; max_pedigree_precision still caps.
    IDENTITY APPROXIMATION (documented in data/xfv_provisional_prior_eval.json v3):
    this function only sees (pick_overall, bonus_usd), so both lookups key on that
    pair; a missing-bonus key resolves to the CURRENT class's unsigned pick, and
    any cross-class key whose mapped values disagree is dropped (row unchanged)."""
    import math
    cfg = (vf._config().get("efv_provisional_prior") or {})
    if not cfg.get("enabled"):
        return cons_war, []
    import storage

    # P1 V3 shipped defaults (flip record: docs/efv-provisional-prior/GATES.md V3
    # RESULTS, 2026-07-23): ARM-A slot-trust PASSED A1-A3 and ships ON (train/serve
    # correctness fix, the _TOOL_IMPUTE class; self-expiring as the class signs).
    # ARM-B/C FAILED B1 and stay OFF. Env overrides win in both directions.
    _p1v3_defaults = {"EEPHUS_P1_SLOT_TRUST": True, "EEPHUS_P1_DSPLUS": False}

    def _v3_env_on(name):
        # V3 flags read the environment AT CALL TIME (registration requirement);
        # unset falls back to the shipped default above.
        import os
        v = os.environ.get(name, "").strip().lower()
        if v in ("1", "true", "on", "yes"):
            return True
        if v in ("0", "false", "off", "no"):
            return False
        return _p1v3_defaults.get(name, False)

    def _v3_cache():
        fn = _provisional_prior_war
        c = getattr(fn, "_p1v3_cache", None)
        if c is None:
            c = {}
            fn._p1v3_cache = c
        return c

    def _v3_slot_trust_usd(pick):
        # ARM-A lookup, sentinel EEPHUS_P1_SLOT_TRUST: current-class picks with
        # signed != 1, NULL bonus and a known slot_usd. Built lazily, once.
        if not _v3_env_on("EEPHUS_P1_SLOT_TRUST"):
            return None
        c = _v3_cache()
        m = c.get("slot_by_pick")
        if m is None:
            m = {}
            try:
                with storage.connect() as con:
                    for r in con.execute(
                            "SELECT pick_overall, slot_usd FROM draft_results "
                            "WHERE draft_year=? AND signed!=1 AND bonus_usd IS NULL "
                            "AND slot_usd IS NOT NULL", (CURRENT_SEASON,)):
                        m[int(r["pick_overall"])] = float(r["slot_usd"])
            except Exception:
                m = {}
            c["slot_by_pick"] = m
        return m.get(pick)

    def _v3_stock_plus(rank, class_ranks):
        # draft_export._stock_plus replica (rank-consensus DS+): float ranks,
        # strictly-better position, exact ties share a position, 70-130 index.
        if rank is None or not class_ranks:
            return None
        n = len(class_ranks)
        if n < 2:
            return 100
        pos = sum(1 for r in class_ranks if r < rank)
        pct = 1.0 - (pos / max(1, n - 1))
        return int(round(70 + pct * 60))

    def _v3_class_dsplus(con, year):
        # Per-class rank-consensus DS+ from draft_snapshots: latest-per-source
        # rank, equal-mean consensus (round 2), class-normalized via
        # _v3_stock_plus. Boards for 2018+ classes are backfilled final
        # PRE-DRAFT vintages (pre-signing information only).
        per_src = {}
        for r in con.execute(
                "SELECT player_key, source, snapshot_date, rank FROM draft_snapshots "
                "WHERE draft_year=? AND rank IS NOT NULL", (year,)):
            k = (r["player_key"], r["source"])
            prev = per_src.get(k)
            if prev is None or (r["snapshot_date"] or "") >= (prev[0] or ""):
                per_src[k] = (r["snapshot_date"], float(r["rank"]))
        ranks = {}
        for (pk, _src), (_d, rk) in per_src.items():
            ranks.setdefault(pk, []).append(rk)
        cons = {pk: round(sum(v) / len(v), 2) for pk, v in ranks.items()}
        lst = sorted(cons.values())
        return {pk: _v3_stock_plus(r, lst) for pk, r in cons.items()}

    def _v3_current_class_dsplus(con):
        # Live class: join DS+ through the served draft export payload
        # (draft_stock_plus_pre_college = the rank-consensus DS+ before the
        # college +-6 boost); recompute from draft_snapshots when absent.
        try:
            doc = json.loads((DATA_DIR / "draft_timeseries.json")
                             .read_text(encoding="utf-8"))
            for cl in (doc.get("classes") or []):
                if cl.get("year") == CURRENT_SEASON:
                    out = {}
                    for pr in (cl.get("prospects") or []):
                        v = pr.get("draft_stock_plus_pre_college")
                        if v is not None and pr.get("player_key"):
                            out[pr["player_key"]] = int(v)
                    if out:
                        return out
        except (OSError, ValueError):
            pass
        return _v3_class_dsplus(con, CURRENT_SEASON)

    def _v3_build_dsplus_map():
        # (pick_overall, bonus-or-None) -> DS+ for the caller population
        # (acquisitions draft rows; draft_results (year, pick) -> draft key).
        # Resolution: a missing-bonus key with a current-class candidate takes
        # the current class's DS+ (the live correctness population); any other
        # key is served only when every candidate class maps to the SAME DS+.
        cand = {}
        try:
            with storage.connect() as con:
                per_class = {}
                for r in con.execute("SELECT DISTINCT draft_year FROM draft_snapshots "
                                     "WHERE draft_year >= 2018"):
                    y = r["draft_year"]
                    per_class[y] = (_v3_current_class_dsplus(con)
                                    if y == CURRENT_SEASON else _v3_class_dsplus(con, y))
                by_pick = {}
                for r in con.execute(
                        "SELECT draft_year, pick_overall, player_key FROM draft_results "
                        "WHERE player_key IS NOT NULL"):
                    ds = (per_class.get(r["draft_year"]) or {}).get(r["player_key"])
                    if ds is not None:
                        by_pick[(r["draft_year"], int(r["pick_overall"]))] = ds
                for r in con.execute(
                        "SELECT year, pick_overall, bonus_usd FROM acquisitions "
                        "WHERE method='draft' AND pick_overall IS NOT NULL"):
                    key = (int(r["pick_overall"]),
                           float(r["bonus_usd"]) if r["bonus_usd"] is not None else None)
                    cand.setdefault(key, []).append(
                        (r["year"], by_pick.get((r["year"], int(r["pick_overall"])))))
        except Exception:
            return {}
        m = {}
        for key, lst in cand.items():
            cur = [ds for (y, ds) in lst if y == CURRENT_SEASON and ds is not None]
            if key[1] is None and cur:
                m[key] = cur[0]
                continue
            vals = {ds for (_y, ds) in lst}
            if len(vals) == 1 and None not in vals:
                m[key] = lst[0][1]
        return m

    def _v3_dsplus(pick, bonus):
        # ARM-B lookup, sentinel EEPHUS_P1_DSPLUS. Built lazily, once.
        if not _v3_env_on("EEPHUS_P1_DSPLUS"):
            return None
        c = _v3_cache()
        m = c.get("dsplus_by_key")
        if m is None:
            m = _v3_build_dsplus_map()
            c["dsplus_by_key"] = m
        return m.get((pick, bonus))

    def _ref_war():
        # Fix B baseline: max(cons_war, bucket-mixture 6yr expectation at cons_fv).
        # Defensive degrade (cons_fv/is_pitcher unavailable): cons_war, i.e. capped
        # V1 baseline. Both production call sites pass them.
        if cons_fv is None or is_pitcher is None:
            return float(cons_war)
        try:
            m = vf.expected_six_year_avg_war(float(cons_fv), bool(is_pitcher))
        except (TypeError, ValueError):
            m = None
        if m is None:
            return float(cons_war)
        mix6 = float(m) * TARGET_SEASONS
        # ANCHOR DECOUPLING 2026-07-29. expected_six_year_avg_war scales by
        # value_framework._war_scale_for, which is pinned to fv_to_6yr_avg_war, so the
        # sub-45 anchor amendment shipped the same day (empirical_anchors 20/25/30/35/40)
        # drags this baseline down with it. That is legitimate for the ANCHOR - the old
        # 0.19 WAR/yr constant really did over-state FV35-40 by 2x to 10x - but it is NOT
        # legitimate here: this baseline is the P1 V2 clause-2 fix, gated and shipped on
        # the OLD scale precisely to stop a zero-floored cons_war letting pick-110s ride
        # the slot curve (the V1 defect-B cell, FV 37.66 hitter, slot 0.776, baseline
        # ~1.17). On the amended anchors that baseline falls to about 0.33 and the defect
        # returns: test_efv_levers::test_p1_mixture_baseline_kills_tiny_slot_pull flipped
        # from a 0.0 pull to 0.2046.
        # Rather than ship an ungated move to served draftee grades as a side effect of a
        # different change, the baseline holds its gated floor. P1 V2 owns this number and
        # only a P1 re-gate may move it.
        # OWED: re-run the P1 V2 battery against the amended anchors and either adopt the
        # lower baseline with fresh clause-2/3/4 evidence or make this floor permanent.
        if _P1_BASELINE_ANCHOR_FLOOR and cons_fv is not None and float(cons_fv) < 45.0:
            mix6 = max(mix6, _p1_legacy_mix6(float(cons_fv), bool(is_pitcher)))
        return max(float(cons_war), mix6)

    def _clamp(prior):
        return max(float(cfg.get("war_floor", -2.0)),
                   min(float(cfg.get("war_ceiling", 20.0)), prior))

    cap = float(cfg.get("pull_cap_war", 1.9))
    base = float(cfg.get("base_precision", 1.0))
    b = None
    try:
        b = float(bonus_usd) if bonus_usd is not None else None
    except (TypeError, ValueError):
        b = None

    slot_war = storage._pick_slot_expected_war(pick_overall)
    if slot_war is None:
        # IFA / no overall pick. Only the validated >= $1M step may move this row
        # (and only when its own gate wired it); everything else stays consensus.
        step_war = cfg.get("ifa_step_war")
        if (not cfg.get("ifa_step_enabled") or step_war is None or b is None
                or b < float(cfg.get("ifa_step_bonus_usd", 1_000_000))):
            return cons_war, []
        ped = float(cfg.get("ifa_step_precision", 0.25))
        w = ped / (ped + base) if (ped + base) > 0 else 0.0
        pull = min(max(float(step_war) - _ref_war(), 0.0), cap)
        prior = _clamp(float(cons_war) + w * pull)
        factors = []
        if abs(prior - cons_war) >= 0.05:
            factors.append({"label": "IFA pedigree prior", "dir": "up",
                            "mag": round(abs(prior - cons_war), 2)})
        return prior, factors

    # pick-tier precision (V1, untouched)
    try:
        p = int(pick_overall)
    except (TypeError, ValueError):
        return cons_war, []
    if p <= 10:
        ped = float(cfg.get("draft_top10_precision", 0.8))
    elif p <= int(cfg.get("round1_last_pick", 30)):
        ped = float(cfg.get("draft_round1_precision", 0.4))
    elif p <= int(cfg.get("round2_last_pick", 70)):
        ped = float(cfg.get("draft_round2_precision", 0.15))
    else:
        ped = float(cfg.get("draft_later_precision", 0.05))
    # bonus adds log-scale precision (each 10x over the floor adds bonus_log_scale)
    if b is not None and b > 0:
        floor = float(cfg.get("bonus_floor_usd", 10000))
        ped += max(0.0, math.log10(max(b, floor) / floor)) * float(cfg.get("bonus_log_scale", 0.5))
    elif b is None:
        # P1 V3 ARM-A (EEPHUS_P1_SLOT_TRUST, shipped ON): a current-class
        # unsigned pick with no posted bonus takes the bonus log-TRUST term on
        # slot_usd instead (train/serve skew fix; trust, never a WAR value).
        # CURRENT-CLASS GATE (bughunt F3 feeds, 2026-07-23): the slot lookup
        # keys on pick_overall ALONE, and 185 historical NULL-bonus draft
        # acquisitions (the dj_davis class) share pick numbers with this
        # year's unsigned picks. Slot trust is a train/serve fix for the
        # CURRENT class only, so the branch requires the threaded acquisition
        # year to equal CURRENT_SEASON; unknown or historical years never
        # take it (they stay on the pick-tier-only pedigree, the flag-OFF
        # value for those rows).
        _is_current_class = False
        try:
            _is_current_class = acq_year is not None and int(acq_year) == CURRENT_SEASON
        except (TypeError, ValueError):
            _is_current_class = False
        _s_usd = _v3_slot_trust_usd(p) if _is_current_class else None
        if _s_usd is not None and _s_usd > 0:
            floor = float(cfg.get("bonus_floor_usd", 10000))
            ped += max(0.0, math.log10(max(_s_usd, floor) / floor)) * float(cfg.get("bonus_log_scale", 0.5))
    # P1 V3 ARM-B (EEPHUS_P1_DSPLUS, default OFF): class-normalized pre-draft
    # Draft Stock+ adds pedigree precision above the class median (frozen
    # registration constants 0.4 and /10); rows without a DS+ are unchanged.
    _dsp = _v3_dsplus(p, b)
    if _dsp is not None:
        ped += 0.4 * max(0.0, (float(_dsp) - 100.0) / 10.0)
    ped = min(ped, float(cfg.get("max_pedigree_precision", 3.0)))
    w = ped / (ped + base) if (ped + base) > 0 else 0.0
    pull = min(max(float(slot_war) - _ref_war(), 0.0), cap)
    prior = _clamp(float(cons_war) + w * pull)
    factors = []
    if abs(prior - cons_war) >= 0.05:
        factors.append({"label": "Draft pedigree prior", "dir": "up" if prior > cons_war else "down",
                        "mag": round(abs(prior - cons_war), 2)})
    return prior, factors

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_BUCKETS = ("bust", "bench", "regular", "good", "star")

# Guarded blend for the HEADLINE grade + board rank: rank_war = (1-lambda)*consensus_war
# + lambda*model_war. eFV still PREDICTS WAR; lambda is the WAG-CALIBRATED trust in its
# adjustment (how much realized WAR-Above-Grade supports eFV's where-consensus-missed edge,
# forward-chained -- see efv_model.wag_calibration). Hitters ~0.8, pitchers shrink harder.
# REALIZED grade + surplus + distribution stay on the pure model (the honest outcome view).


def scored_path(side):
    return DATA_DIR / ("xfv_scored_pitcher.json" if side == "pit" else "xfv_scored.json")


def scored_live_path(side):
    return DATA_DIR / ("xfv_scored_live_pitcher.json" if side == "pit"
                       else "xfv_scored_live.json")


def score_report_path(side):
    return DATA_DIR / ("xfv_score_report_pitcher.json" if side == "pit" else "xfv_score_report.json")


# Human labels for the per-prospect eFV explainer (which signals moved the grade off
# the consensus-FV prior). Keys match the model feature names.
_FACTOR_LABELS = {
    "obp_rel": "On-base vs level", "k_rel": "Contact (K%) vs level",
    "bb_rel": "Walk rate vs level", "iso_rel": "Power (ISO) vs level",
    "age_rel_level": "Age for level", "level_rank": "Level reached",
    "tool_hit": "Hit tool", "tool_speed": "Speed tool", "tool_game_pwr": "Power tool",
    "tool_field": "Field tool", "peak_k_rel": "Peak K rate", "peak_bb_rel": "Peak walk rate",
    "tool_fb": "Fastball", "tool_cmd": "Command", "tool_sl": "Slider",
    "tool_ch": "Changeup", "tool_cb": "Curveball", "era_rel": "ERA vs level",
    "x_era_k": "K-backed run prevention",                 # KRP+: (-era_rel)*k_rel
    "n_sources": "Source coverage", "pick_overall": "Draft pedigree",
    "bonus_log": "Signing bonus",
    # n_milb_seasons: RELABELLED 2026-07-25 (sign-audit D2). It was
    # "Track-record depth", which tells the reader MORE seasons is better. The
    # served weight is -0.2324, so more seasons scores DOWN, and the chip read
    # DOWN on 1,882 of 1,886 live hitter cards (99.8%) - i.e. a hitter with a
    # long record was being told his record was thin. The weight is not a bug:
    # holding level_rank and age fixed, extra MiLB seasons mean extra seasons
    # USED to reach the same level, which is slow progression and is correctly
    # a negative. Only the label was wrong. "Seasons to reach level" makes DOWN
    # read as "he took a lot of them", which is what the model actually says.
    "n_milb_seasons": "Seasons to reach level",
    "fv_stddev": "Source disagreement", "il_stints_pre": "Injury history",
    # ops_rel shipped into the hitter lean set 2026-07-07 without a label, so
    # the raw feature key leaked into the user-facing factors panel.
    "ops_rel": "Production (OPS) vs level",
    "peak_ops_rel": "Peak production (OPS)", "peak_obp_rel": "Peak on-base",
    "peak_iso_rel": "Peak power (ISO)",
    # age shipped into BOTH lean sets 2026-07-14 (owner-directed absolute-age
    # feature) without a label - the ops_rel precedent again: the raw key
    # rendered verbatim on 54.2% of live cards (bughunt SCORE #1, 2026-07-23).
    "age": "Age",
}

# Features excluded from the per-prospect explainer: model-internal recentering,
# not interpretable per-prospect "reasons" a reader can act on.
#   fv                  - the consensus prior itself (the baseline deltas are FROM).
#   milb_missing        - the imputed-production INDICATOR. eFV only grades players
#                         WITH a pro track record, so every live-scored prospect has
#                         milb_missing=0 and the term carries no per-player signal.
#                         REASON CORRECTED 2026-07-25 (sign-audit D8): this used to
#                         say the weight is NEGATIVE and the offset ~+0.7. Both are
#                         wrong. The served weight is +0.0397 (POSITIVE) and with
#                         train mean 0.017 / sd 0.129 the live offset is about
#                         -0.005, not +0.7 - wrong by two orders of magnitude AND in
#                         the opposite direction. The skip itself is still correct
#                         (a constant is not a per-prospect reason), but it was
#                         being justified by arithmetic that does not hold.
#   is_ifa / is_college - acquisition-cohort intercept dummies (a per-cohort baseline
#                         shift), not a scouting/production signal.
_EXPLAINER_SKIP = {"fv", "milb_missing", "is_ifa", "is_college"}

# Side-specific explainer exclusions. Same criterion as _EXPLAINER_SKIP (a term that
# is model-internal rather than an interpretable per-prospect reason), but where that
# is true on ONE side only.
#
#   pit "age" - ADDED 2026-07-25 (sign-audit D1, and the owner's "why is Ryan Sloan
#       receiving an age penalty at 20 in Double-A?"). _FEATURES_PIT carries NO
#       level_rank, so on the pitcher side `age` is the only term that can absorb how
#       far a pitcher has climbed, and it does: its served weight is +0.0589 against a
#       declared -1, while its marginal correlation with realized WAR is -0.0543, i.e.
#       the declaration is true unconditionally and the fitted sign is an
#       omitted-variable artifact. age_rel_level cannot offset it (served weight
#       -0.0076, effectively zero).
#       The user-visible consequence: a pitcher YOUNGER than the 22.54 training mean
#       gets a NEGATIVE contribution, so the "Age" chip read DOWN on 1,058 of 2,393
#       live pitcher cards (44.2%), telling young arms their youth hurt them. Sloan at
#       20 in Double-A is one of the 1,058, not a one-off.
#       This is a DISPLAY fix and deliberately not a model change: the two sweep lanes
#       disagree on whether the declaration should become 0 or stay -1 with an
#       omitted-variable note, no rank gain is available either way (every arm
#       measured sub-floor), and a confounded coefficient should not be narrated to a
#       reader as that player's age either way. The hitter side keeps its Age chip:
#       there `age` fits -0.0619, agreeing with its declaration, alongside level_rank.
_EXPLAINER_SKIP_SIDE = {"pit": {"age"}}


def _factors(ridge, feats, top: int = 4, side: str = "hit") -> list:
    """Per-prospect explainer: the non-FV ridge contributions (weight * standardized
    feature, in raw ridge units) that moved eFV off the consensus-FV prior, largest
    first. DOCSTRING CORRECTED 2026-07-14 (audit): the mags are DIRECTIONAL raw-model
    contributions, NOT an exact decomposition of the headline delta - the headline
    passes through the linear calibration (a + b*pred), the -2 floor, the blend
    lambda, and the live overlays, so these do not sum to xfv_minus_consensus.
    Returns [{label, dir, mag}].

    COLLINEAR-GROUP FIX 2026-07-25 (owner: "why is Arias punished for contact when
    he has great contact?"). k_rel and peak_k_rel are the same statistic over two
    windows (live r = +0.76 hit / +0.68 pit) and the ridge split them with opposite
    signs (+0.229 / -0.160), so per player the two terms largely cancel. Reporting
    them SEPARATELY and then keeping the top-N by magnitude let one half reach the
    card while its offsetting partner was dropped - a plus-contact hitter was told
    his contact hurt him. efv_factor_groups sums each declared collinear group
    FIRST, so the reported direction is the group's NET direction and the top-N cut
    operates on groups (shown or hidden whole). DISPLAY ONLY: the model prediction,
    grade, WAR, surplus and every ordering are untouched."""
    skip = _EXPLAINER_SKIP | _EXPLAINER_SKIP_SIDE.get(side, set())
    contribs = []
    for k, m, s, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        if k in skip:
            continue
        contribs.append((k, w * ((feats.get(k, 0.0) - m) / (s or 1.0))))
    return _fgroups.collapse(contribs, side, lambda k: _FACTOR_LABELS.get(k, k),
                             min_mag=0.05, top=top)


def _age_at(birth_date, year):
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date[:10])
        return round((date(int(year), 4, 1) - b).days / 365.25, 1)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Live prospect-age ramp (C3, 2026-07-30)
# ---------------------------------------------------------------------------
# The ONSET is the owner's policy dial (master plan D2). It is a named constant so
# that changing the policy is a one-line edit with a measured table behind it, and
# it is DEFAULTED TO THE INCUMBENT 25.0, so this commit is output-neutral: at 25.0
# the ramp below is arithmetically identical to the retired hard gate.
#
# The slope and floor are deliberately HELD FIXED while the onset moves, so the dial
# has exactly one meaning ("how early does age start costing a prospect"). Measured
# board effect of each candidate onset is tabled in docs/efv-2026-07-30/EFV_LANE_GATES.md.
# Do not pick an onset here from an accuracy metric: the debuted-only eval pool is
# survivorship-censored against the never-debut old-prospect class this ramp exists to
# price, which is why it shipped owner-directed rather than fitted in the first place.
# OWNER DECISION TAKEN 2026-07-30: onset 23.0. The owner was shown the measured table
# (22.0 / 23.0 / 24.0 / 25.0) and chose 23.0 to move enrique_bradfield_jr out of the
# top 100 - a 24.7-year-old repeating AAA on a .664 OPS who paid NOTHING under the old
# hard gate at exactly 25.0, and who sits at the top-100 EDGE under onset 24.0. The
# owner was also shown that onset 22.0 would cost two pitchers out of the top 100,
# because 366 of the 489 rows pinned at the age_rel_level cap are pitchers, so an early
# onset taxes exactly the side the rest of this program is trying not to under-rate.
# This is a POLICY dial, not a fitted parameter: see the note above on why the
# debuted-only eval pool cannot adjudicate it.
_AGE_PENALTY_ONSET = 23.0    # OWNER DIAL (D2), chosen 2026-07-30. Measured: 22.0/23.0/24.0/25.0
_AGE_PENALTY_PER_YR = 0.10   # haircut per year past the onset
_AGE_PENALTY_FLOOR = 0.75    # reached at onset + 2.5 yr


def _age_ramp(age, onset: float = None, per_yr: float = None, floor: float = None) -> float:
    """Continuous, monotone non-increasing age haircut. 1.0 at and below the onset,
    then -per_yr per year, floored. Pure function of age so the gate lab can sweep the
    onset without touching the module state."""
    if age is None:
        return 1.0
    onset = _AGE_PENALTY_ONSET if onset is None else onset
    per_yr = _AGE_PENALTY_PER_YR if per_yr is None else per_yr
    floor = _AGE_PENALTY_FLOOR if floor is None else floor
    return round(max(floor, min(1.0, 1.0 - per_yr * (float(age) - onset))), 3)


def _age_factor(r) -> float:
    """Owner-directed live prospect-age penalty (2026-07-14, the Andrew Moore
    directive: a 26.9yo AA reliever must not rank top-100). A multiplicative
    haircut on the eFV WAR projection for OLD active prospects, mirroring the
    injury-penalty overlay: LIVE board only, never the resolved eval.

    Why an overlay and not a bigger model coefficient: the trained age
    coefficient is honest but small because the debuted-only training pool is
    survivorship-censored - the 26yo org arms who never got a shot are not in
    it, so the data cannot support the penalty the owner (correctly) wants
    priced. Ramp: 1.0 through _AGE_PENALTY_ONSET, -_AGE_PENALTY_PER_YR/yr after,
    floored at _AGE_PENALTY_FLOOR. Transparent via the "Prospect age penalty" chip."""
    age = r.get("age_now")
    if age is None:
        age = (r.get("milb") or {}).get("age")
    return _age_ramp(age)


_RP_DESIGNATIONS = {"SIRP", "MIRP", "RP", "CL"}
# Reliever-ceiling ramp (C3). Derived, not tuned: with the shared -0.10/yr slope, the
# offset that makes the ramp pass through the retired staircase's tier midpoints
# (25.5 -> 0.80, 26.5 -> 0.70) is -1.5 yr from the age-penalty onset. Floor 0.70 is
# the retired staircase's own floor.
_ROLE_RAMP_OFFSET_YR = -1.5
# FROZEN, not derived from the live age dial (decoupled 2026-07-30 - see _role_factor).
# 25.0 is the reliever-ceiling directive's OWN onset (2026-07-15, "RP-designated AND
# age >= 25 AND model_war >= 1.5"), not the prospect-age dial's current setting. The
# two were briefly the same number and briefly shared a constant; they are different
# policies and only coincidentally agreed.
_ROLE_RAMP_ONSET = 25.0 + _ROLE_RAMP_OFFSET_YR      # 23.5
_ROLE_PENALTY_FLOOR = 0.70


def _role_factor(r, model_war: float) -> float:
    """Owner-directed live RELIEVER-CEILING penalty (2026-07-15, the second
    Andrew Moore directive: a near-27yo single-inning reliever must not rank
    top-100). List-time RP-DESIGNATED prospects (SIRP/MIRP/RP/CL - generic "P"
    excluded) realized 0.17 mean WAR, 2.8% contributor and 0% star across the
    284 resolved training rows, a class prior the model cannot learn: the pit
    ridge has no role feature, the FV45+ RP label cells are n<=3, and the
    never-debuted old-reliever busts are survivorship-censored out of the
    debuted eval pool (the same argument as _age_factor, which shipped
    owner-directed for the same reason). Bounded multiplicative haircut on the
    MODEL leg, LIVE board only, never the resolved eval; surfaced as a
    "Reliever ceiling" factor chip. Triggers ONLY on model enthusiasm
    (model_war >= 1.5) for RP-designated arms age 25+, so the blast radius is
    the Moore class, not every bullpen prospect. Honestly labeled a policy
    dial, not an accuracy claim; forward-adjudicated by the F-WATCH C-RP
    cohort kill rule (data/xfv_promo_watch.json) and bounded by the F-SIDE S4
    anti-blanket-penalty gate (mid-board pitcher outperformance must not
    flip).

    C3 2026-07-30: the retired form was a STAIRCASE - 1.0 below 25.0, then a flat
    0.80 on [25, 26) and 0.70 above - so it stepped TWENTY points of projected WAR at
    exactly age 25.0 and another ten at 26.0. Two arms an hour apart in birth date
    could land two tiers apart. It is now the same SHAPE as _age_factor: same
    -_AGE_PENALTY_PER_YR/yr slope, onset _ROLE_RAMP_ONSET, so it passes through the
    retired staircase's own tier MIDPOINTS - (25.5, 0.80) and (26.5, 0.70) - which is
    what keeps each tier's central tendency where the owner directive put it instead of
    re-tuning the policy under cover of a shape fix. Floor stays 0.70.

    DECOUPLED 2026-07-30. This ramp used to derive its onset from
    _AGE_PENALTY_ONSET + _ROLE_RAMP_OFFSET_YR, i.e. it MOVED WITH the prospect-age
    dial. When the owner moved that dial to 23.0 - a decision taken about a
    24.7-year-old HITTER repeating AAA - the coupling silently dragged the reliever
    ceiling's onset from 23.5 to 21.5, taxing 22-year-old relief prospects under a
    directive that was written about arms at 25 and up. Two different owner directives
    with two different rationales must not share one dial. The offset survives as the
    DERIVATION of the frozen constant (25.0 - 1.5 = 23.5), not as a live link.

    Blast radius, measured on the live board before the change: the staircase bound
    only 7 rows, all at grade <= 42.6 and none inside the top 300, so this is a
    correctness fix on a tiny population, not a re-pricing of the bullpen."""
    pos = str(r.get("position") or "").upper()
    if pos not in _RP_DESIGNATIONS or model_war < 1.5:
        return 1.0
    age = r.get("age_now")
    if age is None:
        age = (r.get("milb") or {}).get("age")
    return _age_ramp(age, onset=_ROLE_RAMP_ONSET, floor=_ROLE_PENALTY_FLOOR)


# ---------------------------------------------------------------------------
# Live IL severity dispatch (B1, 2026-07-30)
# ---------------------------------------------------------------------------
# MiLB carries only TWO IL designations, and neither maps onto MLB's:
#   "7-day"       the DEFAULT landing spot for ANY minor-league injury, a jammed
#                 thumb and a torn UCL alike. It is a roster mechanic, not a
#                 severity read, and it is 62% of the live board's IL rows.
#   "full-season" out for the year.
# MLB uses 10-day / 15-day / 60-day. The pre-2026-07-30 dispatch was
# "60" -> 0.70, "15"/"10" -> 0.82, ELSE -> 0.90, which shipped two live defects:
#   1. a 7-day stint priced at 0.90, i.e. IDENTICALLY to an unclassified serious
#      injury. Measured: seth_hernandez, il_type "7-day", FOUR trailing IL days,
#      one stint -> 0.90 -> -1.25 FV -> 18 board spots.
#   2. the MiLB FULL-SEASON IL also fell to that else-branch at 0.90, so a
#      season-ending injury was priced MILDER than an MLB 60-day stint.
# The dispatch below keeps a type-based severity wherever the type is informative,
# and prices the UNINFORMATIVE types (7-day, plus anything unrecognized) on DAYS
# ACTUALLY MISSED: a ramp from _IL_MILD_DAY0 at day 0 to _IL_MILD_FLOOR (the old
# flat else-value) once the absence is real. The ramp SATURATES at
# _IL_MILD_FULL_DAYS, strictly below the 60/120-day chronicity modifiers, so days
# are never counted twice -- every row those modifiers can reach is already
# pinned at the floor, exactly where the old code put it.
_IL_MILD_DAY0 = 0.99        # active short/unclassified stint, nothing missed yet
_IL_MILD_FLOOR = 0.90       # ... and once a month is gone (the old flat else-value)
_IL_MILD_FULL_DAYS = 30.0   # a-priori: one month of a ~5-month MiLB season
_IL_SEVERE = 0.70           # MLB 60-day IL (unchanged)
_IL_MODERATE = 0.82         # MLB 15-day / 10-day IL (unchanged)
# OWNER DECISION TAKEN 2026-07-30 (B1b, registered in docs/efv-2026-07-30/EFV_LANE_GATES.md).
# "full-season" has its OWN branch, because leaving it in the days-aware else would
# RELIEVE season-ending injuries that have not yet accumulated trailing days (a
# full-season row at 7 days would read 0.97) -- a new defect, worse than the one B1
# fixes. On severity it belongs with the 60-day stint: out for the year cannot be
# milder than out for two months. The lane measured that setting, recommended it, and
# PINNED the incumbent pending authorization; the owner has now authorized it.
# Measured when the lane tabled it: 64 factors down, 21 grades (max -2.3 FV), 674
# ranks, NO top-100 churn. This is a POLICY decision about what an injury means, not a
# fitted accuracy claim, and it ships as one.
_IL_FULL_SEASON = _IL_SEVERE
_IL_SEVERE_TYPES = ("60",)              # 60-day IL
_IL_MODERATE_TYPES = ("15", "10")       # MLB 15-day / 10-day IL
_IL_FULL_SEASON_TYPES = ("full-season", "full season")   # MiLB full-season IL


def _il_mild_factor(days: float) -> float:
    """Days-scaled haircut for an IL type that carries no severity information.
    Linear from _IL_MILD_DAY0 (day 0) to _IL_MILD_FLOOR (_IL_MILD_FULL_DAYS+)."""
    frac = min(1.0, max(0.0, days) / _IL_MILD_FULL_DAYS)
    return _IL_MILD_DAY0 - (_IL_MILD_DAY0 - _IL_MILD_FLOOR) * frac


def _injury_factor(r) -> float:
    """Owner-directed live injury penalty: a multiplicative haircut on the eFV WAR
    projection (so it flows to the grade, the rank, AND surplus) for prospects who
    are CURRENTLY on the IL. An active injury costs near-term WAR and carries
    setback risk that scout FV under-prices; eFV penalizes it harder. Applied
    only to the LIVE board (resolved players' outcomes already embed their injuries).

    Owner directive 2026-07-15: post-TJ STATUS alone is NOT an injury and carries
    no penalty. The old unconditional is_post_tj x0.85 taxed fully recovered arms
    forever (Kade Anderson: zero IL days in 12 months, elite AA season, but a
    2022 college TJ cost him 15% of WAR/grade/rank/surplus).

    Owner directive 2026-07-17: a currently-HEALTHY player carries NO penalty at
    all. The old trailing-12-month component kept taxing players after activation
    (Josue Briceno: back from a 60-day stint, but ~108 trailing IL days held a
    x0.90 haircut on his card the day he returned). Trailing IL days/stints now
    only DEEPEN the haircut while the player is actually on the IL; the moment
    il_on clears, the penalty clears with it.

    B1 2026-07-30: the type dispatch is now DAYS-AWARE for the IL designations that
    carry no severity information (the MiLB 7-day, and anything unrecognized), and
    the MiLB full-season IL is classified as severe instead of falling to the mild
    else-branch. See the _IL_* block above for the mechanism and the measured case."""
    if not r.get("il_on"):
        return 1.0
    t = str(r.get("il_type") or "").lower()
    days = float(r.get("il_days_12mo") or 0.0)
    stints = float(r.get("il_stints_12mo") or 0.0)
    # An ACTIVE stint contributing ZERO trailing days AND ZERO trailing stints can
    # only mean the placement predates the 12-month window: storage._health_profile
    # counts open stints with their elapsed days, so the only way an on-IL player
    # scores 0/0 is a `since` older than the 365-day cutoff (measured: 29 live rows,
    # placed 2025-03 to 2025-07 and still on the IL). Those are the LONGEST absences
    # on the board and a naive days ramp would hand them a free pass, so the mild
    # branch reads them at the saturated floor. A player placed TODAY has stints=1,
    # days=0 and is correctly treated as day 0. `days` itself is left alone so the
    # 60/120-day chronicity modifiers keep their exact prior behaviour on these rows.
    mild_days = days if (days > 0.0 or stints > 0.0) else _IL_MILD_FULL_DAYS
    if any(k in t for k in _IL_SEVERE_TYPES):
        f = _IL_SEVERE
    elif any(k in t for k in _IL_FULL_SEASON_TYPES):
        f = _IL_FULL_SEASON
    elif any(k in t for k in _IL_MODERATE_TYPES):
        f = _IL_MODERATE
    else:
        f = _il_mild_factor(mild_days)
    if days >= 120:
        f *= 0.82
    elif days >= 60:
        f *= 0.90
    if stints >= 3:
        f *= 0.92
    return round(max(0.5, f), 3)


# Statcast+ live-tilt slope, CALIBRATED from the measured forward-r (data/statcast_plus_eval.json)
# rather than a hand-set constant. SC+ is a 100+10z index, so a PERFECTLY-predictive SC+ would
# justify 0.01 / point (= 10% per 1σ); the actual, weak forward-r (~0.12 pit / ~0.15 hit) scales
# that down so the tilt is evidence-sized, not a WAG. Per side; the +/-18% clamp stays (it now
# rarely binds, because the calibrated slope is far gentler than the old 0.008).
_SC_TILT_PER_PT_AT_R1 = 0.01


def _sc_forward_r() -> dict:
    try:
        e = json.loads((DATA_DIR / "statcast_plus_eval.json").read_text(encoding="utf-8"))
        return {"hit": float(e["hitters"]["r_sc_vs_mlb_ops"]),
                "pit": float(e["pitchers"]["r_sc_vs_mlb_era_inv"])}
    except Exception:
        return {"hit": 0.15, "pit": 0.12}


_SC_FWD_R = _sc_forward_r()


def _statcast_factor(r, side: str = "hit") -> float:
    """Live Statcast+ overlay tilt: nudge the eFV WAR projection by batted-ball quality / Stuff+
    (100 = average). Current-state, upper-level only -> a provisional tilt (no historical Statcast
    to OOS-validate), bounded +/-18%. The slope is the per-side forward-r times the
    perfect-predictor slope (_SC_TILT_PER_PT_AT_R1), so a weak signal gets a small tilt. Players
    without a Statcast+ (lower levels) are untouched (factor 1.0)."""
    sc = r.get("statcast_plus")
    if sc is None:
        return 1.0
    try:
        sc = float(sc)
    except (TypeError, ValueError):
        return 1.0
    slope = max(0.0, _SC_FWD_R.get(side, 0.13)) * _SC_TILT_PER_PT_AT_R1
    return round(min(1.18, max(0.82, 1.0 + (sc - 100.0) * slope)), 3)


def _apply_war_tilt(war: float, factor: float) -> float:
    """Apply a multiplicative injury/Statcast tilt to a (possibly NEGATIVE) WAR
    projection in the INTENDED direction: a penalty (factor<1) always LOWERS the
    projection, a boost (factor>1) always RAISES it. For war>=0 that is war*factor;
    for war<0, war*factor INVERTS (a penalty on a negative war moves it toward zero =
    UP, so an injured fringe arm leapfrogs his healthy peers and the factors chip
    reads backwards), so divide instead -- symmetric and monotone across the sign
    boundary. Floored at the model floor -2.0."""
    if factor == 1.0 or war is None:
        return war
    adj = war * factor if war >= 0 else war / factor
    return max(-2.0, adj)


def _cal_mm(v_mm, grade, is_pit: bool):
    """bughunt F1 (P0, 2026-07-23): pass a raw engine $M figure through the
    engine's OWN isotonic calibration layer (vf.apply_calibration), exactly the
    layer surplus_value_mm applies to its point estimate. eFV surplus used to
    ship the RAW expected_surplus_usd / sv_distribution dollars next to
    calibrated consensus columns (max_clark 65.5 vs 72.9 on one card).
    Percentile use is sound: isotonic calibration is MONOTONE nondecreasing, so
    percentiles commute through it pointwise (flat isotonic segments can
    collapse adjacent percentiles - acceptable, and honest: the calibrated
    distribution genuinely has that mass point). The BACKTEST path deliberately
    fits against the RAW engine outputs (apply_calibration docstring contract)
    and reads vf directly - it does not pass through here. None-safe."""
    if v_mm is None:
        return None
    return vf.apply_calibration(float(v_mm), grade, is_pit)


def _grade_map_age(age, eta_to_debut) -> float | None:
    """bughunt F5 (P3, 2026-07-23): age placement for the WAR->grade inversion.
    vf.expected_war defines debut_age = age - exposure_seasons (its `age` is the
    age AFTER the exposure - a debuted-player contract), so passing a pre-debut
    age placed the aging curve at debut_age = current_age - TARGET_SEASONS
    (jesus_made: 13.2). Pass (expected debut age) + TARGET_SEASONS instead, so
    the inversion's debut_age equals the age the player is actually EXPECTED to
    debut at. `eta_to_debut` is the years from the age's measurement point to
    debut: the real/fallback ETA for live rows (age = current age), 0.0 where
    the age is already measured at the debut season (resolved matrix rows,
    backgraded graduates). Systematic direction: slight grade deflation at the
    top (jesus_made 65.2 -> 64.9)."""
    if age is None:
        return None
    return float(age) + float(eta_to_debut) + TARGET_SEASONS


def _reprice_surplus_on_display(s: dict, is_pit: bool, pos, age=None, eta=None) -> None:
    """Re-price the surplus DOLLARS (surplus_mm + band + the surplus fan) off the DISPLAYED
    20-80 grade (xfv_grade_display) instead of the honestly-deflated realized grade, so the
    dollars a prospect shows match the eFV grade the site displays and the /projections/
    surface (owner: eFV surplus must be consistent site-wide). Dollars price through the
    engine's isotonic calibration at this seam (bughunt F1; _cal_mm, percentiles pointwise).
    The OUTCOME ODDS (p_bucket and p_bust -- the validated star/bust odds) STAY on the
    realized grade: they are probabilities, not a dollar value, and were ground-truthed on
    that basis. No-op when the display grade or a priced surplus is unavailable (e.g. a
    provisional cohort).

    INVARIANT AMENDED 2026-07-25 (owner-authorized). This function's rule is unchanged:
    the display re-pricing still never touches the odds. But the standing site-wide claim
    that p_bucket / p_bust are NEVER touched now reads NEVER TOUCHED EXCEPT BY THE
    THIN-SAMPLE CONDITIONAL. What changed and why: the vf.p_bucket_given_fv curve is
    fitted on the Clemens published-list population (source-graded prospects with a pro
    track record), so keying it on the grade alone was wrong for a PROVISIONAL row graded
    off as little as 80 plate appearances of DSL production. Measured on 19,812 rebuilt
    player-seasons of that exact population (four cohort years, outcomes resolved), the
    served odds were 0.13 to 0.17 too low at grade 35+ and an 87-PA DSL bat printed
    P(bust) 51%. efv_ungraded.thin_sample_p_bust now replaces p_bust on provisional rows
    and renormalizes p_bucket's non-bust mass to match it. SCOPE: efv_ungraded's
    provisional rows ONLY. Every row on THIS module's paths keeps the incumbent odds
    byte-identical, including efv_score's own xfv_provisional (prior-anchored,
    no-track-record) rows: those carry a real source grade, which places them in a
    population the thin-sample cohort deliberately EXCLUDED, so extending the conditional
    to them would be extrapolation and was not measured. Gates, controls and the loss
    ledger: efv_ungraded.py (the block above _LEVEL_ETA), data/xfv_thin_pbust_eval.json,
    lab in tools/pbust_thin/."""
    gq = s.get("xfv_grade_display")
    if gq is None:
        return
    kw = {}
    if age is not None:
        kw["age"] = age
    if eta is not None:
        kw["eta_years"] = eta
    sq = vf.expected_surplus_usd(gq, is_pit, pos, **kw)
    dq = vf.sv_distribution(gq, is_pit, pos, **kw) or {}
    pq = dq.get("percentiles") or {}
    _r1 = lambda v: round(float(v), 1) if v is not None else None
    _cq = lambda v: _cal_mm(v, gq, is_pit)
    # `is not None` (not truthiness): a legitimate $0.0 surplus must serve as 0.0,
    # not null out (bughunt F6 truthiness fix).
    s["surplus_mm"] = _r1(_cq(sq / 1e6)) if sq is not None else None
    s["band_p10_mm"] = _r1(_cq(pq.get("p10")))
    s["band_p90_mm"] = _r1(_cq(pq.get("p90")))
    if s.get("dist") is not None:
        # Surplus fan follows the displayed grade; keep the realized p_bust already on the row.
        # mean maps through apply_calibration exactly as surplus_value_mm calibrates its mean.
        s["dist"] = {"p10_mm": _r1(_cq(pq.get("p10"))), "p25_mm": _r1(_cq(pq.get("p25"))),
                     "p50_mm": _r1(_cq(pq.get("p50"))), "p75_mm": _r1(_cq(pq.get("p75"))),
                     "p90_mm": _r1(_cq(pq.get("p90"))), "mean_mm": _r1(_cq(dq.get("mean"))),
                     "p_bust": s.get("p_bust")}


# ---------------------------------------------------------------------------
# F-SIDE-FIX -- joint cross-side TOP-BAND display recalibration (2026-07-23)
# ---------------------------------------------------------------------------
# Owner-authorized OUTPUT-CHANGING fairness fix, registered in
# docs/efv-2026-07-23/GATES.md ("F-SIDE-FIX gate registration") BEFORE the gate
# run. Mechanism: the per-side rank-preserving quantile display map lets each
# side fill the joint board's top slots at its own consensus-FV-distribution
# rate, which over-promotes pitchers into the top joint slots (F-SIDE,
# data/xfv_side_fairness_eval.json: top-25 pit share 0.37 display vs 0.11 raw,
# hit-minus-pit realized +4.07 WAR CI90 [1.64, 6.46]). The fix re-anchors ONLY
# the TOP BAND (per-side display grade >= SFF_KNEE_RAW, the display-55 knee):
# band rows from BOTH sides are joint-ordered by the ARM-2-style expected-WAR
# crosswalk (per-side unweighted PAVA of realized first-6yr WAR over the
# labeled pool's rank_war quantiles, read at each row's within-side rank
# quantile) and the band's OWN display-value multiset is reassigned in that
# order -- so the served grade distribution is invariant, the knee is a fixed
# point, rows below the knee are byte-identical, and within-side order is
# preserved (weakly) by construction. Each row's move is bounded by the
# a-priori SFF_MOVE_CAP_FV cap (= the standing served-move ceiling; the
# S-XLINE cap precedent: a round bound, not tuned to any metric).
# rank_war / xfv_grade (realized) / p_bucket / p_bust are NEVER touched BY THIS
# HOOK (they live upstream of the display map); surplus is repriced off the
# corrected display AFTER this hook, exactly as it was off the incumbent map.
# INVARIANT AMENDED 2026-07-25 (owner-authorized): the site-wide "p_bucket /
# p_bust are never touched" claim now reads NEVER TOUCHED EXCEPT BY THE
# THIN-SAMPLE CONDITIONAL. F-SIDE-FIX itself is unaffected (it is a display-grade
# reordering and still leaves the odds alone), and no row on any efv_score path
# changes: the conditional applies to efv_ungraded's PROVISIONAL rows only, where
# the grade-only Clemens curve was measured to be 0.13 to 0.17 too optimistic at
# grade 35+. Full statement of what changed, the measured population, the gates
# and the scope limit is in _reprice_surplus_on_display's docstring and in
# efv_ungraded.py (the block above _LEVEL_ETA).
# Flag: default-OFF module constant, env-overridable (EEPHUS_SIDE_FAIRNESS_FIX
# "1"/"0", the efv_statcast_line pattern) so the gate lab can toggle within
# one process. Flip the default only on the registered ALL-PASS.
SIDE_FAIRNESS_FIX_DEFAULT = True   # W-FSIDE-SHIP gate ALL-PASS 2026-07-24 (owner-authorized, independently verified): top-band pit over-representation share 0.37->0.21, G1' lo95 -0.0014, max move 3.0 FV
SFF_KNEE_RAW = 52.5      # display-55 knee (F-SIDE 55_plus_binding boundary)
SFF_MOVE_CAP_FV = 3.0    # a-priori per-row move bound == standing served ceiling
_SFF_MIN_CURVE_N = 20    # crosswalk needs a real labeled pool behind it


def _sff_flag() -> bool:
    import os
    env = os.environ.get("EEPHUS_SIDE_FAIRNESS_FIX")
    if env is not None:
        return env.strip() == "1"
    return SIDE_FAIRNESS_FIX_DEFAULT


def _sff_pava(ys):
    """Unweighted pool-adjacent-violators (nondecreasing) fit of `ys` in the
    given order -- the ARM-2 crosswalk smoother, verbatim mechanics."""
    blocks = []                                   # [sum, n] per block
    for y in ys:
        blocks.append([float(y), 1])
        while len(blocks) > 1 and (blocks[-2][0] / blocks[-2][1]
                                   > blocks[-1][0] / blocks[-1][1]):
            s, n = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
    out = []
    for s, n in blocks:
        out.extend([s / n] * n)
    return out


def _sff_crosswalk_curve(pairs, min_n: int = _SFF_MIN_CURVE_N):
    """ARM-2 expected-WAR-at-rank crosswalk for one side: unweighted PAVA of the
    realized (target-censored) first-6yr WAR over the labeled pool's rank_war
    quantiles. `pairs` = [(rank_war, realized_war)]. Returns (qs, fitted) knots
    for interpolation, or None when the pool is too thin to carry a curve."""
    pts = sorted(((float(rw), float(t)) for rw, t in pairs
                  if rw is not None and t is not None), key=lambda p: p[0])
    if len(pts) < min_n:
        return None
    fit = _sff_pava([t for _rw, t in pts])
    m = len(pts)
    qs = [(i / (m - 1)) if m > 1 else 0.0 for i in range(m)]
    return qs, fit


def _sff_expected_war(curve, q: float) -> float:
    """Read the crosswalk at within-side rank quantile q (interpolated, clamped
    at the ends). Rounded to 6dp so PAVA flat blocks tie exactly and the
    rank_war tiebreak preserves within-side order (the ARM-2 float-ulp fix)."""
    import bisect
    qs, fit = curve
    if q <= qs[0]:
        return round(fit[0], 6)
    if q >= qs[-1]:
        return round(fit[-1], 6)
    i = bisect.bisect_left(qs, q)
    q0, q1 = qs[i - 1], qs[i]
    y0, y1 = fit[i - 1], fit[i]
    if q1 == q0:
        return round(y0, 6)
    return round(y0 + (y1 - y0) * (q - q0) / (q1 - q0), 6)


def joint_band_recal(rows, knee: float = None, cap: float = None) -> dict:
    """PURE F-SIDE-FIX core (shared with tools/efv_side_fairness_fix_lab.py so
    the lab gates the production code path). `rows` carry side ('hit'/'pit'),
    idx (within-side ascending-rank_war position), rank_war, preside (incumbent
    per-side display grade) and ew (expected WAR, 6dp). Rows with preside >=
    knee form the joint band; the band's own preside-value multiset is
    reassigned along the joint order (ew, rank_war, hit-first, idx) and each
    assignment is clamped to preside +- cap. Returns {(side, idx): new_value}
    for band rows. Invariants by construction: values stay within the band's
    original range (nothing crosses the knee in either direction), and
    within-side order is weakly preserved (the crosswalk is monotone within
    side, the tiebreak chain is within-side stable, and clamping by a monotone
    envelope keeps monotonicity)."""
    knee = SFF_KNEE_RAW if knee is None else knee
    cap = SFF_MOVE_CAP_FV if cap is None else cap
    band = [r for r in rows if r["preside"] >= knee]
    if len(band) < 2:
        return {}
    order = sorted(band, key=lambda r: (r["ew"], r["rank_war"],
                                        0 if r["side"] == "hit" else 1, r["idx"]))
    vals = sorted(r["preside"] for r in band)
    out = {}
    for v, r in zip(vals, order):
        out[(r["side"], r["idx"])] = min(r["preside"] + cap,
                                         max(r["preside"] - cap, v))
    return out


def _sff_pool_entries(pool, sd):
    """Deterministic within-side entries for one scored pool: rows sorted by
    (rank_war, player_key) with idx + rank quantile. `preside` reads the
    stamped incumbent (xfv_grade_display_preside) when present -- an ON-regen
    artifact read back on the next regen must key the joint board off the
    INCUMBENT per-side map, never off its own previous output (idempotency)."""
    entries = [r for r in pool
               if r.get("rank_war") is not None and r.get("xfv_grade_display") is not None]
    entries.sort(key=lambda r: (r["rank_war"], r.get("player_key") or ""))
    m = len(entries)
    out = []
    for i, r in enumerate(entries):
        pre = r.get("xfv_grade_display_preside")
        if pre is None:
            pre = r["xfv_grade_display"]
        out.append({"side": sd, "idx": i, "q": (i / (m - 1)) if m > 1 else 0.0,
                    "rank_war": r["rank_war"], "preside": float(pre), "_row": r})
    return out


def _apply_side_fairness_fix(scored, side: str, live: bool) -> int:
    """Serve-time F-SIDE-FIX wrapper: assemble both sides' pools + crosswalk
    curves, run joint_band_recal, apply the result to THIS side's rows in
    place (the other side applies its own share during its own run -- the
    scoring seam is per-side; the other side's inputs are read from its scored
    artifact, which regen_all writes hit-before-pit). Returns rows changed;
    degrades to a no-op (0) whenever any input is unavailable."""
    if not _sff_flag() or not scored:
        return 0
    other = "pit" if side == "hit" else "hit"
    try:
        opool = json.loads(((scored_live_path if live else scored_path)(other))
                           .read_text(encoding="utf-8"))
        self_res = (json.loads(scored_path(side).read_text(encoding="utf-8"))
                    if live else scored)
        other_res = json.loads(scored_path(other).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("F-SIDE-FIX: inputs unavailable (%s) -- per-side map kept", exc)
        return 0
    curves = {}
    for sd, res in ((side, self_res), (other, other_res)):
        curves[sd] = _sff_crosswalk_curve(
            [(r.get("rank_war"), r.get("realized_war_6yr")) for r in res])
    if not (curves[side] and curves[other]):
        log.warning("F-SIDE-FIX: crosswalk pool too thin -- per-side map kept")
        return 0
    rows = []
    for sd, pool in ((side, scored), (other, opool)):
        for e in _sff_pool_entries(pool, sd):
            if e["preside"] >= SFF_KNEE_RAW:
                e["ew"] = _sff_expected_war(curves[sd], e["q"])
                rows.append(e)
    assign = joint_band_recal(rows)
    n = 0
    for e in rows:
        if e["side"] != side:
            continue
        row = e["_row"]
        row["xfv_grade_display_preside"] = round(e["preside"], 1)
        nv = round(assign.get((e["side"], e["idx"]), e["preside"]), 1)
        if nv != row["xfv_grade_display"]:
            row["xfv_grade_display"] = nv
            if row.get("consensus_fv") is not None:
                row["xfv_minus_consensus_display"] = round(nv - row["consensus_fv"], 1)
            n += 1
    if n:
        log.info("F-SIDE-FIX active (%s/%s): %d top-band display grades re-anchored",
                 side, "live" if live else "resolved", n)
    return n


def run(persist: bool = True, side: str = "hit") -> dict:
    keys, _mono = _feature_spec(side)
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    # Match the GOVERNANCE eval pool (efv_model.run): drop never-MLB recent-bust rows
    # so the shipped model is fit on the same population the eval measures. Rank-neutral
    # (those rows are outside every forward-chain fold), just removes fringe fit noise.
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    by_key = {r["player_key"]: r for r in pool}

    # Final model: ridge on the full matrix + linear scale calibration (full-window) +
    # the consensus-FV OLS anchor for the guarded blend.
    ridge = _fit_ridge(data, keys)
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    ols = _fit_ols_fv(data)
    lam = blend_lambda(side)

    scored = []
    _price_ctx = {}                                       # pk -> age, for the post-rank surplus re-price
    _rank_exact = {}                                      # pk -> UNROUNDED rank_war (tie-group display sort)
    for r in data:
        pk = r["player_key"]
        src = by_key[pk]
        xfv_war = max(-2.0, a + b * raw[pk])              # model E[6yr WAR] (honest)
        pos = src.get("position")
        dyear = src.get("debut_year") or 2020
        age = _age_at(src.get("birth_date"), dyear)
        _price_ctx[pk] = age
        # OUTCOME-ANCHORED GRADE (LANE-P2, 2026-07-30). xfv_grade is the inverse of the
        # EMPIRICAL pooled curve E[first-6yr bWAR | consensus FV] (3,037 resolved rows,
        # Clemens-shrunk where thin), not the inverse of this valuation core's own forward
        # map. See vf.outcome_implied_fv and docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md.
        # The window is the model's OWN 6 seasons, never the clemens control_years=7 (a
        # valuation-side flip had silently re-pointed that denominator and deflated the top
        # end); the curve is DEFINED on the 6-season label, so the argument is now checked
        # rather than merely passed.
        _gm_age = _grade_map_age(age, 0.0)
        xfv_grade = vf.outcome_implied_fv(xfv_war, exposure_seasons=TARGET_SEASONS)
        # ODDS BASIS, deliberately NOT re-keyed. p_bucket / p_bust and the dollar seam stay
        # on the retired realized-implied grade: they are validated, ground-truthed
        # probabilities and re-keying them onto the outcome scale is a change nothing in
        # this commit measured. Same rule _reprice_surplus_on_display already states for
        # the display re-price. Registered as a follow-up, with the counterfactual
        # magnitude measured, in POOLED_OUTCOME_REFIT.md section 1.3.
        _odds_grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age, position=pos,
                                             exposure_seasons=TARGET_SEASONS)
        cons_fv = src.get("consensus_fv_raw")
        if xfv_grade is None or _odds_grade is None or cons_fv is None:
            continue
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else xfv_war
        rank_war = (1 - lam) * cons_war + lam * xfv_war   # guarded blend -> headline rank
        _rank_exact[pk] = rank_war                        # unrounded, for the display-map sort
        probs = vf.p_bucket_given_fv(_odds_grade, is_pit) or []
        # bughunt F1: raw engine dollars pass through the engine's isotonic
        # calibration at this seam (_cal_mm; consensus at its own grade), so the
        # eFV and consensus columns share one pricing basis.
        xfv_surplus = vf.expected_surplus_usd(_odds_grade, is_pit, pos, age=age, eta_years=1.0)
        cons_surplus = vf.expected_surplus_usd(cons_fv, is_pit, pos, age=age, eta_years=1.0)
        dist = vf.sv_distribution(_odds_grade, is_pit, pos) or {}
        pcts = dist.get("percentiles") or {}
        _cx = lambda v: _cal_mm(v, _odds_grade, is_pit)
        scored.append({
            "player_key": pk, "kind": src["kind"], "position": pos,
            "consensus_fv": round(cons_fv, 1),
            "xfv_grade": round(xfv_grade, 1),
            "xfv_minus_consensus": round(xfv_grade - cons_fv, 1),
            "xfv_war_6yr": round(xfv_war, 2),
            "rank_war": round(rank_war, 3),
            "p_bucket": {b_: round(p, 3) for b_, p in zip(_BUCKETS, probs)},
            # `is not None`: a legitimate $0.0 surplus serves as 0.0 (bughunt F6).
            "surplus_mm": round(_cx(xfv_surplus / 1e6), 1) if xfv_surplus is not None else None,
            "consensus_surplus_mm": (round(_cal_mm(cons_surplus / 1e6, cons_fv, is_pit), 1)
                                     if cons_surplus is not None else None),
            "band_p10_mm": round(_cx(pcts.get("p10", 0)), 1) if pcts else None,
            "band_p90_mm": round(_cx(pcts.get("p90", 0)), 1) if pcts else None,
            "p_bust": round(dist.get("p_bust"), 3) if dist.get("p_bust") is not None else None,
            "realized_war_6yr": round(r["target"], 2),
            "censored": src.get("censored", False),
        })

    # --- re-anchor the HEADLINE grade onto the familiar 20-80 scale -------
    # The realized_implied_fv grade is honestly deflated (consensus FV is
    # optimistic) but floors at 20 and reads as jarringly low next to consensus.
    # The headline xfv_grade_display is a RANK-PRESERVING quantile map of the
    # GUARDED-BLEND ranking (rank_war) onto the consensus FV distribution of this
    # pool: the ordering is eFV's outcome-grounded ranking (the value-add, now
    # beating consensus OOS), the units match consensus (usable). Surplus/
    # distribution stay on the honest realized grade.
    if scored:
        target = sorted(s["consensus_fv"] for s in scored)
        # Sort on the UNROUNDED rank_war with player_key as the stable tiebreak
        # (bughunt SCORE tie-groups, 2026-07-23): sorting the stored 3dp-rounded
        # value let dict insertion order assign display grades inside tie groups
        # (worst case 2.4 FV apart on identical rank_war; 318 hit + 532 pit
        # groups). The exact value breaks most "ties"; true exact ties get a
        # deterministic key order instead of insertion order.
        order = sorted(range(len(scored)),
                       key=lambda i: (_rank_exact.get(scored[i]["player_key"],
                                                      scored[i]["rank_war"]),
                                      scored[i]["player_key"]))
        m = len(scored)
        for rank_pos, i in enumerate(order):
            p = (rank_pos / (m - 1)) if m > 1 else 0.0
            pos = p * (m - 1)                     # smooth (interpolated) quantile map so
            lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo   # small WAR/tilt moves
            disp = target[lo] * (1 - frac) + target[hi] * frac        # show in the grade
            scored[i]["xfv_grade_display"] = round(disp, 1)
            scored[i]["xfv_minus_consensus_display"] = round(disp - scored[i]["consensus_fv"], 1)

    # --- OD2 TOP-QUANT (2026-07-15): cross-side re-anchor of the PITCHER ---
    # display tail above the display-55 knee. GATED INERT: apply_display_remap
    # is a no-op unless data/xfv_topquant_eval.json stamps a PASSING primary
    # gate AND ship.enabled -- the 2026-07-15 eval REJECTED every fitted
    # candidate (pitcher tail grades carry no realized-WAR gradient), so this
    # hook currently changes nothing (byte-identical output). Placed BEFORE the
    # surplus re-price so an activated remap flows into surplus_mm.
    if scored:
        from efv_topquant import apply_display_remap
        apply_display_remap(scored, is_pit)

    # --- F-SIDE-FIX joint top-band display recalibration (default-OFF flag) --
    # AFTER the per-side map + TOP-QUANT hook (its output is the incumbent this
    # fix re-anchors) and BEFORE the surplus re-price, so surplus_mm follows the
    # corrected displayed grade. No-op while the flag is off.
    if scored:
        _apply_side_fairness_fix(scored, side, live=False)

    # --- re-price SURPLUS DOLLARS on the DISPLAYED (quantile) grade --------
    # Owner: eFV surplus must reflect the 20-80 grade the site shows (consensus-tier
    # market value), consistent with /projections/. Runs AFTER the quantile map since
    # xfv_grade_display is pool-relative. Star/bust odds stay on the realized grade.
    for s in scored:
        _reprice_surplus_on_display(s, is_pit, s.get("position"),
                                    age=_price_ctx.get(s["player_key"]), eta=1.0)

    # --- validation -------------------------------------------------------
    res = [s for s in scored if s["kind"] == "debuted" and not s["censored"]]
    # adjustment direction: does (xfv - consensus) point the same way as
    # (realized - consensus-implied WAR)? in-sample/illustrative.
    adj, miss = [], []
    for s in res:
        cons_implied = (vf.fv_to_6yr_avg_war(s["consensus_fv"]) or 0) * 6
        adj.append(s["xfv_minus_consensus"])
        miss.append(s["realized_war_6yr"] - cons_implied)
    dir_rho = _spearman(adj, miss) if len(adj) >= 8 else None

    ups = sorted(res, key=lambda s: -s["xfv_minus_consensus"])[:6]
    downs = sorted(res, key=lambda s: s["xfv_minus_consensus"])[:6]
    def _ex(s):
        return {"player_key": s["player_key"], "consensus_fv": s["consensus_fv"],
                "xfv_grade": s["xfv_grade"], "delta": s["xfv_minus_consensus"],
                "realized_war_6yr": s["realized_war_6yr"]}

    report = {
        "generated_at": date.today().isoformat(),
        "scope": "PITCHERS" if is_pit else "HITTERS", "n_scored": len(scored),
        "calibration_scale": {"a": round(a, 3), "b": round(b, 3)},
        "headline_grade_divergence_vs_consensus": {
            "scale": "rank-preserving quantile map onto consensus FV distribution",
            "mean_abs_delta": round(statistics.mean(abs(s["xfv_minus_consensus_display"]) for s in scored), 2),
            "max_up": round(max(s["xfv_minus_consensus_display"] for s in scored), 1),
            "max_down": round(min(s["xfv_minus_consensus_display"] for s in scored), 1),
            "share_within_2_grades": round(sum(1 for s in scored if abs(s["xfv_minus_consensus_display"]) <= 2) / len(scored), 3),
        },
        "realized_grade_divergence_vs_consensus": {
            "scale": "realized_implied_fv (honestly deflated; drives surplus + distribution)",
            "mean_abs_delta": round(statistics.mean(abs(s["xfv_minus_consensus"]) for s in scored), 2),
            "max_up": round(max(s["xfv_minus_consensus"] for s in scored), 1),
            "max_down": round(min(s["xfv_minus_consensus"] for s in scored), 1),
        },
        "adjustment_direction_check": {
            "spearman_adj_vs_consensus_miss": dir_rho,
            "n": len(adj),
            "reading": "positive => eFV up/down-adjustments point toward where consensus "
                       "FV under/over-shot realized WAR (illustrative, in-sample).",
        },
        "surplus_totals_mm": {
            "xfv": round(sum(s["surplus_mm"] or 0 for s in scored), 1),
            "consensus": round(sum(s["consensus_surplus_mm"] or 0 for s in scored), 1),
        },
        "example_up_adjustments": [_ex(s) for s in ups],
        "example_down_adjustments": [_ex(s) for s in downs],
        "note": ("xfv_grade is monotone in the model prediction, so it inherits the OOS "
                 "rank edge over consensus FV in data/xfv_eval.json. Surplus reuses the "
                 "engine's isotonic calibration (no double-correction)."),
    }
    if persist:
        sp, rp = scored_path(side), score_report_path(side)
        sp.write_text(json.dumps(scored, indent=0), encoding="utf-8")
        rp.write_text(json.dumps(report, indent=1), encoding="utf-8")
        log.info("wrote %s (%d players) + %s", sp, len(scored), rp)
    return report


def history_path():
    return DATA_DIR / "xfv_history.json"


def _build_grade_map(side: str):
    """Monotone rank_war -> DISPLAY-grade lookup from the current live scored pool.

    Sole consumer since the 2026-07-30 A2 repoint: run_backgrade, which needs a
    xfv_grade_display for graduate / bust rows that never went through run_live's own
    quantile map. score_history used to read it too and no longer does -- it grades through
    the board map now, because this map produces the QUANTILE scale and the board does
    not."""
    try:
        scored = json.loads(scored_live_path(side).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted((s["rank_war"], s["xfv_grade_display"]) for s in scored
                  if s.get("rank_war") is not None and s.get("xfv_grade_display") is not None)


def _map_grade(grade_map, rank_war):
    if not grade_map:
        return None
    import bisect
    xs = [g[0] for g in grade_map]
    i = bisect.bisect_left(xs, rank_war)
    if i <= 0:
        return grade_map[0][1]
    if i >= len(grade_map):
        return grade_map[-1][1]
    (x0, y0), (x1, y1) = grade_map[i - 1], grade_map[i]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (rank_war - x0) / (x1 - x0)


def _history_model_war(row, cons_war, ridge_war_fn, is_pitcher=None):
    """eFV model WAR for ONE historical snapshot (score_history / FV-history chart).
    A snapshot WITH a MiLB track record uses the model prediction (ridge_war_fn); a
    NO-track-record snapshot is prior-anchored via _provisional_prior_war off cons_war
    instead of being scored through the ridge. Scoring a data-less snapshot through the
    ridge applies the trained milb_missing untracked-bust penalty, which fabricates a
    spuriously depressed early eFV point for a player who merely had no pro line yet.
    Mirrors run_backgrade's AUDIT FIX 2026-07-14. ridge_war_fn is deferred so a
    no-track-record snapshot never pays the ridge predict. is_pitcher feeds the P1 V2
    bucket-mixture pull baseline (Fix B); None degrades to the capped-V1 baseline."""
    if row.get("milb"):
        return ridge_war_fn()
    war, _ = _provisional_prior_war(cons_war, row.get("pick_overall"), row.get("bonus_usd"),
                                    cons_fv=row.get("consensus_fv_raw"),
                                    is_pitcher=is_pitcher,
                                    acq_year=row.get("acq_year"))
    return war


def score_history(persist: bool = True) -> dict:
    """Backfill an eFV value at EACH historical board snapshot so the FV-history chart can
    plot eFV over time (not just consensus). For every points[] entry we re-score the as-of
    features (that snapshot's per-source FV + tools + production as-of that year) with the
    shipped model and grade it through THE BOARD'S OWN map (vf.outcome_implied_fv). Honest
    caveat: this is today's model scoring old snapshots (a retrospective), not the grade we
    would have shown then. Writes data/xfv_history.json =
    {basis, basis_epoch, generated_at, by_player: {key: [{d, x, c}]}}.

    A2 REPOINT 2026-07-30: this used to map the guarded blend through run_live's per-side
    QUANTILE display map, which is not the number the board serves -- see the block at the
    grading line. It no longer reads the live scored pool at all, so it no longer has to run
    after run_live for its scale (it still runs after it in regen_all for ordering).

    The artifact is fully REBUILT on every run, never appended, so a basis change rebases
    every point at once and there is no within-series discontinuity to suppress. What DOES
    need suppressing is the window between a code flip and the next production regen, when
    the file on disk is on the previous basis while the board is on the new one; the `basis`
    stamp written below is what lets storage.xfv_history_is_on_board_basis detect that and
    withhold the eFV-delta movement override for that run."""
    from efv_dataset import (_prior_features, _milb_features, _load_sidecars, _cohort_flags,
                             _injury_features, _side_match, _f, CURRENT_SEASON)
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        return {"players": 0}
    players = (json.loads(ts_path.read_text(encoding="utf-8")).get("players")) or []
    fit = {s: _fit_production(s) for s in ("hit", "pit")}
    acq, il = _load_sidecars({p.get("player_key") for p in players if p.get("player_key")})

    out = {}
    for rec in players:
        pk = rec.get("player_key")
        if not pk:
            continue
        side = "pit" if _side_match(rec, "pit") else "hit"
        ridge, a, b, ols, _keys = fit[side]
        pts = sorted((pt for pt in (rec.get("points") or [])
                      if pt.get("snapshot_date") and _f(pt.get("consensus_fv_raw")) is not None),
                     key=lambda pt: pt["snapshot_date"])
        if len(pts) < 2:
            continue
        a_sc = acq.get(pk) or {}
        ilf = _injury_features(il.get(pk), None)
        series = []
        for pt in pts:
            cons_fv = _f(pt.get("consensus_fv_raw"))
            if cons_fv is None:
                continue
            yr = int(pt["snapshot_date"][:4])
            # acq_year rides along for the ARM-A current-class gate (bughunt F3
            # feeds); _vec ignores unknown keys, so it never enters the features.
            row = {"consensus_fv_raw": cons_fv, "pick_overall": a_sc.get("pick_overall"),
                   "bonus_usd": a_sc.get("bonus_usd"), "acq_year": a_sc.get("year"), **ilf}
            row["is_ifa"], row["is_college"] = _cohort_flags(a_sc.get("method"), a_sc.get("year"), rec.get("birth_date"))
            row.update(_prior_features(rec, pt, side))
            row["milb"] = _milb_features(rec.get("mlbam_id"), min(yr, CURRENT_SEASON) + 1,
                                         rec.get("birth_date"), side)
            # cons_war (consensus-anchor WAR) is computed first so a no-track-record
            # snapshot can be prior-anchored off it. ols is always present here
            # (fit_production_stack returns None otherwise and _fit_production raises),
            # so the `else` branch is defensive only.
            cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else 0.0
            # 2026-07-19 FIX: route a NO-track-record snapshot through the prior-anchor
            # path (mirror run_backgrade's 2026-07-14 AUDIT FIX), NOT the ridge. Scoring a
            # data-less snapshot through the ridge applies the trained milb_missing
            # untracked-bust penalty, fabricating a spuriously depressed early eFV point
            # (a fake early dip on the FV-history chart). Resolved/track-record snapshots
            # (milb present) are unchanged.
            model_war = _history_model_war(
                row, cons_war,
                lambda: max(-2.0, a + b * _predict(ridge, _vec(row, side))),
                is_pitcher=(side == "pit"))
            # A2 REPOINT, 2026-07-30 (Phase 3.2). The grade at each snapshot is now the
            # BOARD's own transform -- vf.outcome_implied_fv on that snapshot's model WAR,
            # the identical function run_live uses for xfv_grade -- instead of the guarded
            # blend mapped through the retired per-side quantile scale.
            #
            # The defect this closes: the series was on a THIRD basis. The board serves
            # storage.BOARD_GRADE_FIELD (raw xfv_grade) and this built xfv_grade_display
            # (the rank_war quantile), so 1,504 of 1,568 players with history had a tail
            # that disagreed with the number on their own card (franklin_arias 58.1 vs
            # 64.2, jesus_made 59.0 vs 64.6). It rides in THIS commit precisely because the
            # pooled outcome refit re-scales the board grade anyway: one restamp and one
            # movement-suppression window instead of two.
            #
            # What still separates the tail from the live board, honestly: run_live applies
            # the injury / age / Statcast / reliever-ceiling tilts and the S-XLINE lean to
            # xfv_war before grading, and this path has never had as-of values for any of
            # them. So a TILTED player's last history point sits a little under his board
            # grade. That is a tilt gap, not a basis gap, and it is the same gap the
            # quantile version carried; closing it needs as-of tilt inputs, which do not
            # exist. Measured residual in POOLED_OUTCOME_REFIT.md section 2.6.
            #
            # rank_war is deliberately NOT the argument here. The board grade is a function
            # of the MODEL's WAR, not of the consensus-guarded blend; grading history off
            # the blend is what put it on a different scale in the first place.
            grade = vf.outcome_implied_fv(model_war, exposure_seasons=TARGET_SEASONS)
            if grade is None:
                continue
            series.append({"d": pt["snapshot_date"], "x": round(grade, 1), "c": round(cons_fv, 1)})
        if len(series) >= 2:
            out[pk] = series

    if persist:
        # BASIS STAMP. storage.xfv_history_is_on_board_basis reads it and withholds the
        # eFV-delta movement override while the series belongs to a different board basis
        # than the one being served -- the suppression the BOARD_RANK_BASIS_EPOCH gate on
        # metric_snapshots structurally cannot provide, because it cannot see this file.
        # Written on the artifact rather than inferred, so a stale file is self-describing.
        import storage as _st
        history_path().write_text(json.dumps(
            {"basis": _st.board_basis_fingerprint(),
             "basis_epoch": _st.BOARD_RANK_BASIS_EPOCH,
             "generated_at": date.today().isoformat(),
             "by_player": out}, separators=(",", ":")), encoding="utf-8")
        log.info("wrote %s (%d players)", history_path(), len(out))
    return {"players": len(out)}


def _fit_production(side: str):
    """Fit the shipped model (ridge + linear scale calibration + consensus-FV OLS anchor)
    on the FULL labeled matrix -- the same fit run() uses -- returning (ridge, a, b, ols, keys)."""
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    # ONE shared fit with the lambda selector (efv_model.fit_production_stack):
    # full labeled pool minus never-MLB recent-bust rows, ridge + output
    # calibration + consensus OLS. The selector sizing blend_lambda now measures
    # exactly this stack (E-LAMBDA parity repair 2026-07-15).
    from efv_model import fit_production_stack
    stack = fit_production_stack(rows, side, keys)
    if not stack:
        raise RuntimeError(f"production stack unfittable for side={side}")
    return stack["ridge"], stack["a"], stack["b"], stack["ols"], keys


def _krp_eligible(r, is_pit) -> bool:
    """KRP+ (K-backed Run Prevention) exposure gate for the live pitcher pool.
    A pitcher qualifies only with a real MiLB rate line: era_rel present AND
    rates_missing == 0 (has batters-faced). rates_missing lives in the MiLB
    feature dict (efv_dataset._season_rates), NOT in efv_model._vec's output -
    reading it off the _vec feature vector always defaulted to 1.0 and gated out
    EVERY live pitcher, leaving the KRP+ pill dead site-wide (2026-07-19 fix)."""
    milb = r.get("milb") or {}
    return bool(is_pit and milb.get("era_rel") is not None
                and float(milb.get("rates_missing", 1.0) or 0.0) == 0.0)


def _krp_display_raw(era_rel: float, k_rel: float) -> float:
    """DISPLAY-ONLY KRP+ raw (LANE H2 display decouple, owner-authorized 2026-07-24).

    The eFV MODEL feature efv_model._x_era_k ZEROES the double-bad quadrant
    (era_rel>0 AND k_rel<0) because the sign-flip measured a WORSE eFV cost - that
    zeroing is correct FOR THE FIT and is deliberately NOT touched here. But it
    makes the ~834 doubly-below-average arms (worse-than-level ERA AND below-level
    K-rate) all standardize to a single flat ~99.3, reading as league-average on
    the KRP+ pill and hiding their severity.

    For the PILL ONLY we read the TRUE double-bad signal. The base interaction
    (-era_rel)*k_rel is neg*neg = POSITIVE in that quadrant (a spurious 'K-backed
    run prevention' boost); the honest run-prevention x missing-bats read there is
    BAD, so it must be signed NEGATIVE.

    FROZEN display formula:
        display_raw = (-era_rel)*k_rel                              , outside double-bad
        display_raw = -abs((-era_rel)*k_rel) = -(era_rel*|k_rel|)   , double-bad quadrant
    i.e. IDENTICAL to the model interaction in every quadrant EXCEPT the zeroed
    one, where instead of 0.0 it carries the negatively-signed magnitude so
    severity spreads and the cohort reads below-average. JUSTIFICATION for the
    -abs() sign: era_rel>0 is worse-than-level run prevention and k_rel<0 is
    below-level whiffs; a metric named "K-backed run prevention" must read LOW
    when BOTH legs are bad, and abs() strips the misleading neg*neg positivity
    before the sign is forced negative. This value feeds ONLY the KRP+
    standardization below; the eFV fit keeps _x_era_k's 0.0 (grade/rank unchanged).
    """
    # Display hygiene (H2 side-effect fix, display-only): winsorize era_rel to +-6 so a
    # tiny-IP ERA blowup cannot drive an absurd small-sample pill (true talent, not a 1-IP
    # artifact). This bounds the input, never the output; no eFV number is touched.
    era_rel = max(-6.0, min(6.0, era_rel))
    x = (-era_rel) * k_rel
    if era_rel > 0 and k_rel < 0:
        return -abs(x)
    return x


def run_live(persist: bool = True, side: str = "hit") -> dict:
    """Score the CURRENT active prospect board (efv_dataset.build_live_matrix) with the
    model fit on the full labeled matrix. Same production seam as run() -- grade +
    5-bucket distribution + surplus + uncertainty band via value_framework -- but these
    players have no outcome label yet, so there is no validation block; they ARE the
    grades the site shows next to consensus FV. Surplus/distribution use each player's
    real timing (current age + ETA) so eFV prices on the same basis as the site's
    consensus surplus. Run after build_live + the site export (timeseries.json)."""
    is_pit = side == "pit"
    ridge, a, b, ols, _keys = _fit_production(side)
    lam = blend_lambda(side)
    live = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))

    scored, skipped_no_track = [], 0
    krp_disp_raw = {}                                     # KRP+ DISPLAY pool: player_key -> _krp_display_raw (decoupled from the model's zeroed x_era_k; LANE H2)
    _price_ctx = {}                                       # pk -> (age, eta), for the post-rank surplus re-price
    _rank_exact = {}                                      # pk -> UNROUNDED rank_war (tie-group display sort)
    for r in live:
        try:
            cons_fv = float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            continue
        # eFV is outcome/production-grounded: it ABSTAINS on players with no pro
        # track record. In training, milb_missing tagged untracked busts (large
        # negative weight); applying that to a current draftee/IFA who simply hasn't
        # played a pro season yet would wrongly crush them. Gate on MiLB production.
        if not r.get("milb"):
            skipped_no_track += 1
            continue
        feats = _vec(r, side)
        xfv_war = max(-2.0, a + b * _predict(ridge, feats))
        # E-STALE: the blend's consensus leg prices the DECAYED anchor
        # (fv_effective, efv_dataset._stale_anchor_discount) - the ground-truth
        # study shows a long-unlisted FV45 carries ~FV35 of credible consensus
        # information, and blending toward the raw anchor would hand back what
        # the decayed model feature just took away. Display consensus (cons_fv)
        # stays raw everywhere.
        _fv_eff = r.get("fv_effective")
        _cons_anchor = float(_fv_eff) if _fv_eff is not None else cons_fv
        cons_war = max(0.0, _pred_ols(ols, _cons_anchor)) if ols else xfv_war
        rank_war = (1 - lam) * cons_war + lam * xfv_war   # guarded blend -> headline rank
        factors = _factors(ridge, feats, side=side)       # explainer: why eFV != consensus
        _stale_disc = float(r.get("anchor_stale_discount") or 0.0)
        if _stale_disc > 0:
            # surfaced like the other live overlays so the card explains WHY the
            # grade sits under a stale consensus (the Hickey complaint).
            factors.insert(0, {"label": "Stale list coverage", "dir": "down",
                               "mag": round(_stale_disc / 2.0, 2)})
        inj = _injury_factor(r)                           # owner-directed live injury penalty
        agef = _age_factor(r)                              # owner-directed live prospect-age penalty
        rolef = _role_factor(r, xfv_war)                   # owner-directed reliever-ceiling penalty
        # S-XLINE-4 "A-ball Statcast lean" (docs/efv-2026-07-23/GATES.md): a
        # bounded additive FV lean on the MODEL leg for active A/CPX prospects,
        # frozen-coefficient residual, clamped +-2 FV, default-OFF module flags.
        # Applied below next to the multiplicative tilts; chip mirrors the
        # stale-coverage convention (FV-scale magnitude / 2).
        xov = 0.0
        if _xoverlay is not None:
            try:
                _ov = _xoverlay.overlay_fv(r, side)
            except Exception:
                _ov = None
            if _ov:
                xov = float(_ov[0])
                factors.insert(0, {"label": _ov[1], "dir": "up" if xov > 0 else "down",
                                   "mag": round(abs(xov) / 2.0, 2)})
        sc = _statcast_factor(r, side)                     # live Statcast+ quality tilt (per-side r-calibrated)
        if sc != 1.0:
            factors.insert(0, {"label": "Statcast+ quality", "dir": "up" if sc > 1 else "down",
                               "mag": round(abs(sc - 1) * 6, 2)})
        if inj < 1.0:
            factors.insert(0, {"label": "Injury penalty", "dir": "down",
                               "mag": round((1 - inj) * 6, 2)})
        if agef < 1.0:
            factors.insert(0, {"label": "Prospect age penalty", "dir": "down",
                               "mag": round((1 - agef) * 6, 2)})
        if rolef < 1.0:
            factors.insert(0, {"label": "Reliever ceiling", "dir": "down",
                               "mag": round((1 - rolef) * 6, 2)})
        adj_factor = inj * sc * agef * rolef
        if adj_factor != 1.0:                              # adjust grade, rank, AND surplus
            xfv_war = _apply_war_tilt(xfv_war, adj_factor)  # sign-aware (negative-war safe)
            # Tilt the MODEL term only, then rebuild the blend, so the consensus
            # anchor cons_war is not also haircut. (rank_war *= adj_factor scaled
            # the whole blend, double-penalizing an injured/low-Statcast player.)
            rank_war = (1 - lam) * cons_war + lam * xfv_war
        if xov and ols:
            # S-XLINE-4 lean: the FV-point delta is priced through the blend's
            # own FV->WAR line (the consensus OLS slope), MODEL leg only, then
            # the blend is rebuilt exactly like the multiplicative tilts above.
            xfv_war = max(-2.0, xfv_war + ols["b"] * xov)
            rank_war = (1 - lam) * cons_war + lam * xfv_war
        pos = r.get("position")
        age = r.get("age_now")
        if age is None:
            age = _age_at(r.get("birth_date"), CURRENT_SEASON)
        eta = r.get("eta_years")
        # Shared no-ETA fallback (bughunt F3): same assumed timing as storage's
        # consensus-surplus writer, so the two adjacent columns agree on debut timing.
        eta = float(eta) if eta is not None else PROSPECT_ETA_FALLBACK_YEARS
        _price_ctx[r["player_key"]] = (age, eta)
        # OUTCOME-ANCHORED GRADE + PINNED ODDS BASIS -- see run() for the full statement.
        # This is THE board number (storage.BOARD_GRADE_FIELD): the inverse of the pooled
        # empirical curve E[first-6yr bWAR | consensus FV]. The board re-ranked when this
        # landed, which is why BOARD_RANK_BASIS_EPOCH is 2026-07-30 and why the fingerprint
        # names the curve hash. Nothing priced in dollars moves: surplus re-prices off
        # xfv_grade_display below, which reads rank_war and never this field.
        _gm_age = _grade_map_age(age, eta)
        xfv_grade = vf.outcome_implied_fv(xfv_war, exposure_seasons=TARGET_SEASONS)
        _odds_grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age, position=pos,
                                             exposure_seasons=TARGET_SEASONS)
        if xfv_grade is None or _odds_grade is None:
            continue
        probs = vf.p_bucket_given_fv(_odds_grade, is_pit) or []
        # bughunt F1: raw engine dollars pass through the engine's isotonic
        # calibration at this seam (_cal_mm; percentiles pointwise - monotone).
        xfv_surplus = vf.expected_surplus_usd(_odds_grade, is_pit, pos, age=age, eta_years=eta)
        dist = vf.sv_distribution(_odds_grade, is_pit, pos, age=age, eta_years=eta) or {}
        pcts = dist.get("percentiles") or {}
        _cx = lambda v, _g=_odds_grade: _cal_mm(v, _g, is_pit)
        def _mm(v):
            return round(float(v), 1) if v is not None else None
        # AUDIT FIX 2026-07-14: gate KRP+ on actual exposure, not the product's
        # truthiness - x_era_k == 0.0 also happens when era_rel is exactly 0.0
        # (or in the zeroed double-bad quadrant), and those arms DO have IP.
        # 2026-07-19 FIX: the exposure signal (rates_missing) lives in r['milb']
        # (efv_dataset._season_rates), NOT in _vec's output; reading it off feats
        # always defaulted to 1.0 and gated out EVERY live pitcher. See _krp_eligible.
        # LANE H2 DISPLAY DECOUPLE 2026-07-24: the pill reads _krp_display_raw from
        # the RAW milb rates (NOT feats['x_era_k'], which the model zeroes in the
        # double-bad quadrant). The eFV fit still consumes the zeroed feats['x_era_k']
        # via _predict above, so grade/rank/surplus are byte-identical - only the
        # KRP+ pill changes. Same None->0.0 coercion as _vec's g(), so the display
        # raw equals feats['x_era_k'] in every non-double-bad quadrant.
        if _krp_eligible(r, is_pit):
            _mk = r.get("milb") or {}
            krp_disp_raw[r["player_key"]] = _krp_display_raw(
                float(_mk["era_rel"]) if _mk.get("era_rel") is not None else 0.0,
                float(_mk.get("k_rel")) if _mk.get("k_rel") is not None else 0.0)
        _rank_exact[r["player_key"]] = rank_war           # unrounded, for the display-map sort
        entry = {
            "player_key": r["player_key"], "kind": "active", "position": pos,
            "consensus_fv": round(cons_fv, 1),
            "xfv_grade": round(xfv_grade, 1),                 # realized-implied (deflated)
            "xfv_minus_consensus": round(xfv_grade - cons_fv, 1),
            "xfv_war_6yr": round(xfv_war, 2),
            "rank_war": round(rank_war, 3),
            "p_bucket": {k: round(p, 3) for k, p in zip(_BUCKETS, probs)},
            # `is not None`: a legitimate $0.0 surplus serves as 0.0 (bughunt F6).
            "surplus_mm": _mm(_cx(xfv_surplus / 1e6)) if xfv_surplus is not None else None,
            "consensus_surplus_mm": r.get("consensus_surplus_mm"),
            "dist": {"p10_mm": _mm(_cx(pcts.get("p10"))), "p25_mm": _mm(_cx(pcts.get("p25"))),
                     "p50_mm": _mm(_cx(pcts.get("p50"))), "p75_mm": _mm(_cx(pcts.get("p75"))),
                     "p90_mm": _mm(_cx(pcts.get("p90"))), "mean_mm": _mm(_cx(dist.get("mean"))),
                     "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None},
            "band_p10_mm": _mm(_cx(pcts.get("p10"))),
            "band_p90_mm": _mm(_cx(pcts.get("p90"))),
            "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None,
            "injury_factor": inj if inj < 1.0 else None,
            "statcast_factor": sc if sc != 1.0 else None,
            "factors": factors,
        }
        # S-XLINE measurement annotation (efv_dataset._milb_features, live
        # builds only): a SEPARATE metadata field, deliberately NOT a ranked
        # factor -- it records that the input line was measured (Statcast
        # expected-stat blend), not a model contribution with a magnitude.
        # Uncovered players get no field at all (zero payload).
        _xn = (r.get("milb") or {}).get("xline_note")
        if _xn:
            entry["xline_note"] = _xn
        scored.append(entry)

    # headline grade -- rank-preserving quantile map of the GUARDED-BLEND ranking
    # (rank_war) onto the LIVE pool's consensus FV distribution (units match consensus;
    # order is eFV's outcome-grounded ranking, which beats consensus OOS). Mirrors run();
    # surplus/distribution stay on the honest realized grade.
    if scored:
        target = sorted(s["consensus_fv"] for s in scored)
        # UNROUNDED rank_war + player_key tiebreak -- see run() (bughunt SCORE
        # tie-groups): the stored 3dp rounding let insertion order assign
        # display grades inside tie groups.
        order = sorted(range(len(scored)),
                       key=lambda i: (_rank_exact.get(scored[i]["player_key"],
                                                      scored[i]["rank_war"]),
                                      scored[i]["player_key"]))
        m = len(scored)
        for rank_pos, i in enumerate(order):
            p = (rank_pos / (m - 1)) if m > 1 else 0.0
            pos = p * (m - 1)                     # smooth (interpolated) quantile map so
            lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo   # small WAR/tilt moves
            disp = target[lo] * (1 - frac) + target[hi] * frac        # show in the grade
            scored[i]["xfv_grade_display"] = round(disp, 1)
            scored[i]["xfv_minus_consensus_display"] = round(disp - scored[i]["consensus_fv"], 1)

    # OD2 TOP-QUANT pitcher-tail re-anchor hook -- GATED INERT (see run()): no-op
    # until data/xfv_topquant_eval.json stamps ship.enabled + gate_pass (the
    # 2026-07-15 eval REJECTED the candidate). Before the surplus re-price.
    if scored:
        from efv_topquant import apply_display_remap
        apply_display_remap(scored, is_pit)

    # F-SIDE-FIX joint top-band display recalibration (default-OFF flag) -- see
    # run(): after the per-side map + TOP-QUANT hook, before the surplus re-price.
    if scored:
        _apply_side_fairness_fix(scored, side, live=True)

    # Re-price SURPLUS DOLLARS on the DISPLAYED (quantile) grade (see run()): eFV surplus
    # reflects the 20-80 grade shown, consistent site-wide + with /projections/. Star/bust
    # odds stay on the realized grade.
    for s in scored:
        _age, _eta = _price_ctx.get(s["player_key"], (None, PROSPECT_ETA_FALLBACK_YEARS))
        _reprice_surplus_on_display(s, is_pit, s.get("position"), age=_age, eta=_eta)

    # KRP+ (K-backed Run Prevention) DISPLAY PILL: standardize the DISPLAY raw
    # (_krp_display_raw; LANE H2 decouple) over the live pitcher pool onto the
    # harmonized "+" scale (100 + 10*z, population sigma). High = a below-level ERA
    # that missing bats support; the doubly-below-average quadrant now reads its
    # true NEGATIVE signal instead of the model's zeroed 0.0, so those arms spread
    # by severity and the cohort reads below-average (was a flat ~99.3).
    if is_pit and len(krp_disp_raw) >= 2:
        vals = list(krp_disp_raw.values())
        mu = statistics.mean(vals)
        sd = statistics.pstdev(vals)
        if sd > 0:
            for s in scored:
                x = krp_disp_raw.get(s["player_key"])
                if x is not None:
                    # C2 true-to-model 2026-07-24b: the 40-160 clamp was DISPLAY compression
                    # (monotone, so forward-validation invariant; it only broke boundary ties).
                    # Removed so KRP+ reads the true 100+10z (Kade Anderson 160->189.1). The z
                    # standardization safety guards (len>=2, sd>0) above are kept.
                    s["krp_plus"] = round(100 + 10 * (x - mu) / sd, 1)

    # SAME-BASIS invariant (bughunt F6, 2026-07-23): both totals are CALIBRATED
    # dollars now -- surplus_mm prices through _cal_mm at this module's seam (F1)
    # and consensus_surplus_mm is storage's calibrated surplus_value_mm
    # passthrough -- so xfv_share_of_consensus below is a like-for-like ratio
    # (it used to divide raw eFV dollars by calibrated consensus dollars).
    xfv_tot = round(sum(s["surplus_mm"] or 0 for s in scored), 1)
    cons_tot = round(sum(s["consensus_surplus_mm"] or 0 for s in scored), 1)
    report = {
        "generated_at": date.today().isoformat(),
        "scope": f"LIVE {'PITCHERS' if is_pit else 'HITTERS'} (active board)",
        "n_scored": len(scored),
        "skipped_no_pro_track_record": skipped_no_track,
        "calibration_scale": {"a": round(a, 3), "b": round(b, 3)},
        "realized_grade_divergence_vs_consensus": {
            "mean_abs_delta": round(statistics.mean(abs(s["xfv_minus_consensus"]) for s in scored), 2) if scored else None,
            "mean_signed_delta": round(statistics.mean(s["xfv_minus_consensus"] for s in scored), 2) if scored else None,
        },
        "surplus_totals_mm": {"xfv": xfv_tot, "consensus": cons_tot,
                              "xfv_share_of_consensus": round(xfv_tot / cons_tot, 3) if cons_tot else None},
    }
    if persist:
        scored_live_path(side).write_text(json.dumps(scored, indent=0), encoding="utf-8")
        log.info("wrote %s (%d players)", scored_live_path(side), len(scored))
    return report


def backgrade_path():
    return DATA_DIR / "xfv_backgrade.json"


def run_backgrade(persist: bool = True) -> dict:
    """Backgrade EVERY graded prospect so the WHOLE site carries an eFV, not just the active
    board (run_live) + the labeled-outcome matrix (run). For each universe player -- timeseries
    actives + debuts.json graduates -- score the as-of features with the shipped model and map
    onto the SAME live grade scale the board uses, so a graduate's eFV is directly comparable
    to a current prospect's. Graduates are scored at their final pre-debut snapshot (the grade
    eFV carried into the majors) and keep realized_war for the did-we-nail-it read. Players with
    no pro track record are graded prior-anchored and flagged xfv_provisional. Fills the gap
    run_live (active w/ track record) + run (matrix cohort) leave behind. Run AFTER run_live
    (reuses its scored pool for the grade scale). Writes data/xfv_backgrade.json."""
    from efv_dataset import (_prior_features, _milb_features, _load_sidecars, _cohort_flags,
                             _injury_features, _side_match, _f, CURRENT_SEASON)
    fit = {s: _fit_production(s) for s in ("hit", "pit")}
    lam = {s: blend_lambda(s) for s in ("hit", "pit")}
    gmap = {s: _build_grade_map(s) for s in ("hit", "pit")}
    # Active-board players already have a richer live entry -- don't re-grade them here.
    have_live = set()
    for s in ("hit", "pit"):
        lp = scored_live_path(s)
        if lp.exists():
            have_live |= {r["player_key"] for r in json.loads(lp.read_text(encoding="utf-8"))}

    ts_path, deb_path = DATA_DIR / "timeseries.json", DATA_DIR / "debuts.json"
    actives = ((json.loads(ts_path.read_text(encoding="utf-8")).get("players") or [])
               if ts_path.exists() else [])
    debuted = json.loads(deb_path.read_text(encoding="utf-8")) if deb_path.exists() else []
    if isinstance(debuted, dict):
        debuted = debuted.get("players") or []
    # AUDIT FIX 2026-07-14: bust-kind players (inactive.json, ~2,200) used to
    # keep the RESOLVED pool's quantile scale in xfv.json because this queue
    # only covered graduates + actives - a quarter of the artifact read on a
    # different grade scale than the site. Score them here (anchored at their
    # final snapshot, same as the resolved builder) so the whole site reads
    # on the live scale.
    inact_path = DATA_DIR / "inactive.json"
    inact = json.loads(inact_path.read_text(encoding="utf-8")) if inact_path.exists() else []
    if isinstance(inact, dict):
        inact = inact.get("players") or []
    # Debuted first so a recently-graduated player who lingers in timeseries is tagged debuted.
    queue = ([(rec, "debuted") for rec in debuted]
             + [(rec, "active") for rec in actives]
             + [(rec, "bust") for rec in inact])
    acq, il = _load_sidecars({rec.get("player_key") for rec, _ in queue if rec.get("player_key")})

    def _mm(v):
        return round(float(v), 1) if v is not None else None

    scored, seen = [], set()
    for rec, kind in queue:
        pk = rec.get("player_key")
        if not pk or pk in seen or pk in have_live:
            continue
        pts = sorted((pt for pt in (rec.get("points") or [])
                      if pt.get("snapshot_date") and _f(pt.get("consensus_fv_raw")) is not None),
                     key=lambda pt: pt["snapshot_date"])
        if not pts:
            continue
        side = "pit" if _side_match(rec, "pit") else "hit"
        is_pit = side == "pit"
        ridge, a, b, ols, _keys = fit[side]
        debut_date = rec.get("debut_date") if kind == "debuted" else None
        # as-of point: graduate -> last snapshot before debut; active -> latest snapshot
        cand = [pt for pt in pts if (not debut_date or pt["snapshot_date"] < debut_date)] or pts
        pt = cand[-1]
        # AUDIT FIX 2026-07-14: when EVERY snapshot is post-debut the `or pts`
        # fallback anchors on a post-debut grade (187 graduates) - tag it so
        # realized-vs-grade readouts can exclude these from "the grade eFV
        # carried into the majors".
        postdebut_anchor = bool(debut_date and pt["snapshot_date"] >= debut_date)
        cons_fv = _f(pt.get("consensus_fv_raw"))
        if cons_fv is None:
            continue
        yr = int(pt["snapshot_date"][:4])
        milb_yr = (int(debut_date[:4]) if (kind == "debuted" and debut_date and debut_date[:4].isdigit())
                   else min(yr, CURRENT_SEASON) + 1)
        a_sc = acq.get(pk) or {}
        ilf = _injury_features(il.get(pk), None) if kind == "active" else {}
        row = {"consensus_fv_raw": cons_fv, "pick_overall": a_sc.get("pick_overall"),
               "bonus_usd": a_sc.get("bonus_usd"), **ilf}
        if kind == "active":
            # AUDIT FIX 2026-07-14: _injury_factor reads the LIVE il fields
            # (il_on/il_type/il_days_12mo/is_post_tj), which this row never
            # carried (_injury_features emits the PRE-cutoff training features)
            # - the backgrade injury penalty was dead code. Populate them the
            # same way build_live_matrix does.
            _il_st = rec.get("il_status") or {}
            _hp = rec.get("health_profile") or {}
            row.update({"il_on": 1 if _il_st.get("is_on_il") else 0,
                        "il_type": _il_st.get("type"),
                        "il_days_12mo": _f(_hp.get("il_days_12mo")) or 0.0,
                        "il_stints_12mo": _f(_hp.get("il_stints_12mo")) or 0.0,
                        "is_post_tj": bool(_hp.get("is_post_tj"))})
        row["is_ifa"], row["is_college"] = _cohort_flags(a_sc.get("method"), a_sc.get("year"), rec.get("birth_date"))
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(rec.get("mlbam_id"), milb_yr, rec.get("birth_date"), side)
        feats = _vec(row, side)
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else 0.0
        if row.get("milb"):
            xfv_war = max(-2.0, a + b * _predict(ridge, feats))
            factors = _factors(ridge, feats, side=side)
        else:
            # AUDIT FIX 2026-07-14: honor the docstring's prior-anchored
            # contract - a no-track-record row scored through the ridge eats
            # the trained milb_missing untracked-BUST penalty, which is wrong
            # for a merely data-less graduate. Grade on the consensus prior.
            # P1 (audit B5, gated): fold the draft-slot WAR + bonus pedigree that
            # is already in-row into that prior; reduces to cons_war when the flag
            # is off or no draft pick exists (so OFF is byte-identical). V2 passes
            # cons_fv + side for the bucket-mixture pull baseline (Fix B).
            xfv_war, factors = _provisional_prior_war(
                cons_war, row.get("pick_overall"), row.get("bonus_usd"),
                cons_fv=cons_fv, is_pitcher=is_pit,
                acq_year=a_sc.get("year"))
        rank_war = (1 - lam[side]) * cons_war + lam[side] * xfv_war
        # ── LIVE-OVERLAY COVERAGE ON THIS PATH (B2, audited 2026-07-30) ──────────
        # This path used to apply _injury_factor and nothing else, which read as a
        # coverage gap because the live path stacks inj * statcast * age * role plus
        # the S-XLINE lean and the side-fairness display fix. Audited row by row:
        #
        #  * AGE + ROLE are wired below. Both are OWNER DIRECTIVES about ACTIVE
        #    prospects ("a 26.9yo AA reliever must not rank top-100"), and this path
        #    serves 257 active board rows that run_live abstains on (no pro track
        #    record) - 10 of them inside the served top 100. Leaving the directives
        #    off here left exactly the Andrew Moore hole open on the one cohort the
        #    model cannot see. They were previously unreachable rather than
        #    deliberately exempt: _age_factor reads age_now / milb.age and this row
        #    carries neither, the same dead-code shape the 2026-07-14 IL fix closed.
        #    MEASURED BLAST RADIUS: ZERO. Of the 257 active rows, 8 have a resolvable
        #    age at all and none is over 25.0, and none is RP-designated at 25+, so
        #    every factor is exactly 1.0 and every served grade/rank/dollar is
        #    byte-identical. This wires a directive shut, it does not move the board.
        #  * DEBUTED / BUST rows (4,811 of 5,068) stay exempt BY DESIGN, not by
        #    omission. Both penalties are documented LIVE-board-only ("never the
        #    resolved eval"), and these rows are anchored at a historical snapshot
        #    whose age is the age AT THAT SEASON - taxing a 2016 graduate's as-of-2015
        #    grade with a 2026 age penalty would be a category error.
        #  * The STATCAST tilt and the S-XLINE lean stay exempt: both price a
        #    MODEL-leg production signal, and 2,525 of these rows (1,279 pitchers)
        #    are prior-anchored with no MiLB block at all, so there is no model leg
        #    to tilt - the tilt would land on a consensus/draft-slot anchor instead.
        #    Measured: exactly ONE of the 257 active rows carries a statcast_plus,
        #    tilt 1.007, which cannot move a 0.1-rounded grade. Declined, not
        #    overlooked; overlay level-reliability is separately re-gated in B4.
        #  * SIDE-FAIRNESS stays exempt because it reassigns a per-side SCORED
        #    POOL's top-band display-value multiset, and this path has no pool of its
        #    own: it maps onto run_live's grade scale (_build_grade_map), which the
        #    fix has ALREADY been applied to. Running it again would double-apply.
        #  * TOP-100 ELIGIBILITY is deliberately NOT restricted. The alternative
        #    considered was excluding this path from the top 100; measured, that
        #    deletes 10 of the served top 100 - roch_cholowsky #4, eric_booth_jr #25,
        #    tyler_bell #32, grady_emerson #46, vahn_lackey #47, drew_burress #62,
        #    aj_gracia #71, jackson_flora #77, zion_rose #89, jacob_lombard #92 -
        #    i.e. the entire top of the 2026 draft class, whose only defect is not
        #    having played a pro game yet. A no-track-record row is already flagged
        #    xfv_provisional for every consumer that wants to treat it differently.
        inj = _injury_factor(row) if kind == "active" else 1.0   # graduate prospect-era IL is moot
        agef = rolef = 1.0
        if kind == "active":
            _prow = {"age_now": rec.get("age_now") or _age_at(rec.get("birth_date"), CURRENT_SEASON),
                     "position": rec.get("position")}
            agef = _age_factor(_prow)
            rolef = _role_factor(_prow, xfv_war)
        for _pf, _plabel in ((inj, "Injury penalty"), (agef, "Prospect age penalty"),
                             (rolef, "Reliever ceiling")):
            if _pf < 1.0:
                factors.insert(0, {"label": _plabel, "dir": "down",
                                   "mag": round((1 - _pf) * 6, 2)})
        _pen = inj * agef * rolef
        if _pen != 1.0:
            xfv_war = _apply_war_tilt(xfv_war, _pen)        # sign-aware (negative-war safe)
            # Tilt the model term only, then rebuild the blend (see the live path
            # above): the consensus anchor must not also be haircut.
            rank_war = (1 - lam[side]) * cons_war + lam[side] * xfv_war
        disp = _map_grade(gmap[side], rank_war)
        if disp is None:
            continue
        if kind == "debuted":
            age, eta = _age_at(rec.get("birth_date"), milb_yr), 0.5
        else:
            age = rec.get("age_now") or _age_at(rec.get("birth_date"), CURRENT_SEASON)
            # bughunt F2: eta_years lives at rec["surplus"]["eta_years"] on the
            # timeseries payload, never top-level - the old rec.get("eta_years")
            # read None for every row, pricing all 2,553 non-debuted backgrades
            # at the fallback (fabricio_blanco: eta 1.0 vs real 6.0). Shared
            # fallback (F3) when no priced eta exists (e.g. inactive.json rows).
            _eta_src = (rec.get("surplus") or {}).get("eta_years")
            eta = float(_eta_src) if _eta_src is not None else PROSPECT_ETA_FALLBACK_YEARS
        pos = rec.get("position")
        # OUTCOME-ANCHORED GRADE + PINNED ODDS BASIS -- see run() for the full statement.
        # The backgrade path flips WITH the other two on purpose: data/xfv.json carries
        # active, debuted and bust rows in ONE file under ONE field name, so leaving
        # graduates on the retired map would manufacture exactly the third-basis defect
        # (A2) that this same commit closes for the history series.
        _gm_age = _grade_map_age(age, 0.0 if kind == "debuted" else eta)
        xfv_grade = vf.outcome_implied_fv(xfv_war, exposure_seasons=TARGET_SEASONS)
        _odds_grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age, position=pos,
                                             exposure_seasons=TARGET_SEASONS)
        if xfv_grade is None or _odds_grade is None:
            continue
        probs = vf.p_bucket_given_fv(_odds_grade, is_pit) or []
        # bughunt F1: raw engine dollars pass through the engine's isotonic
        # calibration at this seam (_cal_mm; percentiles pointwise - monotone).
        surplus = vf.expected_surplus_usd(_odds_grade, is_pit, pos, age=age, eta_years=eta)
        dist = vf.sv_distribution(_odds_grade, is_pit, pos, age=age, eta_years=eta) or {}
        pcts = dist.get("percentiles") or {}
        _cx = lambda v, _g=_odds_grade: _cal_mm(v, _g, is_pit)
        entry = {
            "player_key": pk, "side": side, "kind": kind, "position": pos,
            **({"xfv_postdebut_anchor": True} if postdebut_anchor else {}),
            "consensus_fv": round(cons_fv, 1),
            "xfv_grade": round(xfv_grade, 1),
            "xfv_grade_display": round(disp, 1),
            "xfv_minus_consensus_display": round(disp - cons_fv, 1),
            "xfv_minus_consensus": round(xfv_grade - cons_fv, 1),
            "xfv_war_6yr": round(xfv_war, 2),
            "rank_war": round(rank_war, 3),
            "p_bucket": {k: round(p, 3) for k, p in zip(_BUCKETS, probs)},
            # `is not None`: a legitimate $0.0 surplus serves as 0.0 (bughunt F6).
            "surplus_mm": _mm(_cx(surplus / 1e6)) if surplus is not None else None,
            "dist": {"p10_mm": _mm(_cx(pcts.get("p10"))), "p25_mm": _mm(_cx(pcts.get("p25"))),
                     "p50_mm": _mm(_cx(pcts.get("p50"))), "p75_mm": _mm(_cx(pcts.get("p75"))),
                     "p90_mm": _mm(_cx(pcts.get("p90"))), "mean_mm": _mm(_cx(dist.get("mean"))),
                     "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None},
            "band_p10_mm": _mm(_cx(pcts.get("p10"))), "band_p90_mm": _mm(_cx(pcts.get("p90"))),
            "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None,
            "factors": factors,
        }
        # Surplus dollars on the DISPLAYED (quantile) grade, consistent with the live board.
        _reprice_surplus_on_display(entry, is_pit, pos, age=age, eta=eta)
        if not row.get("milb"):
            entry["xfv_provisional"] = True          # prior-anchored (no pro track record)
        if inj < 1.0:
            entry["injury_factor"] = inj
        if kind == "debuted":
            cw = (rec.get("career_war") or {}).get("career_war")
            if cw is not None:
                entry["realized_war"] = round(float(cw), 1)
        scored.append(entry)
        seen.add(pk)

    if persist:
        backgrade_path().write_text(json.dumps({"scored": scored}, separators=(",", ":")),
                                    encoding="utf-8")
        log.info("wrote %s (%d players)", backgrade_path(), len(scored))
    return {"players": len(scored),
            "provisional": sum(1 for s in scored if s.get("xfv_provisional")),
            "debuted": sum(1 for s in scored if s["kind"] == "debuted")}


if __name__ == "__main__":
    import sys as _sys
    if "--live" in _sys.argv:
        for _s in ("hit", "pit"):
            logging.basicConfig(level=logging.INFO, format="%(message)s")
            _rep = run_live(side=_s)
            print(f"\n=== LIVE {_s} ===")
            print("n scored:", _rep["n_scored"], "| skipped (no pro track record):",
                  _rep["skipped_no_pro_track_record"], "| calibration:", _rep["calibration_scale"])
            print("realized divergence vs consensus:", json.dumps(_rep["realized_grade_divergence_vs_consensus"]))
            print("surplus totals ($M):", json.dumps(_rep["surplus_totals_mm"]))
        _sys.exit(0)
    _SIDE = "pit" if "--pit" in _sys.argv else "hit"
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run(side=_SIDE)
    print("n scored:", rep["n_scored"], "| calibration:", rep["calibration_scale"])
    print("headline divergence:", json.dumps(rep["headline_grade_divergence_vs_consensus"]))
    print("realized divergence:", json.dumps(rep["realized_grade_divergence_vs_consensus"]))
    print("adjustment direction check:", json.dumps(rep["adjustment_direction_check"]))
    print("surplus totals ($M):", json.dumps(rep["surplus_totals_mm"]))
    print("\nexample UP adjustments (eFV > consensus):")
    for e in rep["example_up_adjustments"]:
        print(f"  {e['player_key'][:24]:24s} cons={e['consensus_fv']:4} -> xfv={e['xfv_grade']:4} (+{e['delta']}) | realized 6yr WAR={e['realized_war_6yr']}")
    print("example DOWN adjustments (eFV < consensus):")
    for e in rep["example_down_adjustments"]:
        print(f"  {e['player_key'][:24]:24s} cons={e['consensus_fv']:4} -> xfv={e['xfv_grade']:4} ({e['delta']}) | realized 6yr WAR={e['realized_war_6yr']}")

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""S-XLINE-4 bounded live overlay: the "A-ball Statcast lean" dial.

Pre-registered ship rule (docs/efv-2026-07-23/GATES.md, "S-XLINE-4 gate
registration"): the two INC-passing signals become a bounded live overlay on
A/CPX prospects, the reliever-ceiling-dial precedent (efv_score._role_factor)
applied to the model leg of the live blend only - the training matrix has ~no
A-ball-covered resolved rows, so an in-matrix feature ship is impossible
until those cohorts resolve.

  hitters : whiff share beyond the line's own K% (INC-2 K channel, rho
            +0.0965 CI95 [+0.0277, +0.1604], n=788). A HIGH whiff residual is
            strikeout risk the stat line has not paid for yet -> NEGATIVE
            FV lean.
  pitchers: FB velo beyond the line's K%a/BB%a/ERA/age (INC-3, rho +0.1423
            CI95 [+0.0196, +0.2704], n=227). A HIGH velo residual -> POSITIVE
            FV lean.

Mechanism: residual_z = signal_z - (slope * baseline_z + intercept) with the
FROZEN coefficients baked into data/statcast_alevel_signals.json
(statcast_alevel_export.FROZEN_COEFFICIENTS, fit once 2026-07-23 on the lab's
2023-2025 INC pair populations; never refit at serve time). The lean is
delta_fv = clamp(BETA * direction * residual_z, +-DELTA_CAP_FV) with BETA = 0.6
FV per residual-z fixed a priori. The 2.0-FV display cap that was the original
registered ceiling is REMOVED (A4, owner ceiling removal); DELTA_CAP_FV is now
a wide numerical-safety bound that never binds on plausible signal. Applies only
to ACTIVE prospects whose current/most-recent tracked season is A or CPX with
>= 100 pitches of signal exposure; everyone else is untouched (None = no-op).

Flags: default-off module constants, overridable per side by env vars
EEPHUS_XOVERLAY_HIT / EEPHUS_XOVERLAY_PIT ("1"/"0") read at call time so the
gate battery can toggle within one process - the exact efv_statcast_line
pattern. Flip the defaults only on the registered post-flip check PASS.

W-OVERLAY-R revival (docs/efv-2026-07-24/GATES.md Phase 3c, registered before
this extension ran): the pit side gains the W-SCREEN AAA physics survivor legs
(velo / spin / vaa; coefficients FROZEN in data/aaa_physics_screen_eval.json,
feature residualized on the season's astuff_pool, z-scaled by the screen's
resid_sd - never refit at serve). Frozen leg rules (the lab header binds):
  - hit side  : whiff leg only (the existing A/CPX signal), unchanged.
  - pit side  : at most ONE velo-family leg per player (A-ball fb_velo signal
                vs AAA velo residual; prefer the larger recent sample), plus
                spin and vaa legs where covered. AAA legs require the player's
                CURRENT tracked season/level to be AAA with >= MIN_PITCHES
                physics pitches; the vaa leg additionally needs >= 50
                VAA-computable cached pitches for that season.
  - composite : equal-weight mean of available DIRECTED leg z-scores, then the
                built BETA 0.6 (kept); the lean is no longer display-capped
                (A4, owner ceiling removal) - only the wide safety bound remains.
  - sub-AAA W-SCREEN-SUB survivors (ivb / vaa) are NOT wired: 8.3 percent
    tracked-park coverage, and their resid_fit_on_yhat needs a serve-time
    stat-line ridge rebuild = a refit this module structurally forbids.
    Display-only per the handoff note; decision frozen before any battery run.

A4 UNCAPPED SHIP (docs/efv-2026-07-24/GATES-ACCURACY.md, owner ceiling removal):
the board-movement ceilings are GONE. The signals FAILED the earlier post-flip
gates ONLY on a display-space ceiling (first the 2-FV served cap, then the
4.0-FV / 40-rank shadow ceiling), never on signal - the screen validation
stands (AAA velo/spin/vaa survivor legs lo95>0 in data/aaa_physics_screen_eval;
the S-XLINE-4 INC forward reads whiff rho +0.0965 CI [+0.0277,+0.1604] n=788,
fb_velo rho +0.1423 CI [+0.0196,+0.2704] n=227). With the ceiling removed they
ship as a FULL, uncapped live model-leg overlay, default ON for covered
players. DELTA_CAP_FV is now a wide numerical-safety sanity bound, not a
display cap; BETA is KEPT at the screen-calibrated 0.6 (no resolved OOS fold
justifies a raise). OFF-path byte-identity for UNCOVERED players is preserved
(None = no-op) - that invariance is correctness, not a ceiling. Authorization:
these are coverage-limited LIVE signals with no resolved OOS fold; the ship is
authorized by the screen validation + the owner ceiling removal, not a new OOS
gate. Live board move (data/xfv_overlay_uncapped_eval.json): hit 405 covered,
pit 228 covered; unbounded served grade moves up to 5.0 FV / 325 board ranks.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

SIGNALS_PATH = Path(__file__).parent / "data" / "statcast_alevel_signals.json"
AAA_SCREEN_PATH = Path(__file__).parent / "data" / "aaa_physics_screen_eval.json"
AAA_PHYSICS_PATH = Path(__file__).parent / "data" / "aaa_physics.json"
AAA_VAA_DIR = Path(__file__).parent / ".cache" / "aaa_pitches_vaa"

OVERLAY_HIT_DEFAULT = True   # A4 ship: default ON for covered players (owner ceiling removal)
OVERLAY_PIT_DEFAULT = True
BETA_FV_PER_RESID_Z = 0.6    # screen-calibrated, KEPT (no resolved OOS fold justifies a raise)
DELTA_CAP_FV = 12.0          # A4: the 2-FV DISPLAY cap is REMOVED (owner directive); this wide
                             # value is a NUMERICAL-SAFETY sanity bound only (never binds on
                             # plausible signal - max real lean observed 2.36 FV), guarding a
                             # corrupt-cache composite z from producing an absurd lean.
MIN_PITCHES = 100            # signal-exposure floor (zone_metrics qualification)
MIN_VAA_PITCHES = 50         # W-SCREEN vaa row floor (frozen AAA convention)
CHIP_LABEL = "A-ball Statcast lean"
CHIP_LABEL_AAA = "AAA physics lean"
_LEVELS = {"A", "CPX"}
_AAA = "AAA"


def _flag(side: str) -> bool:
    env = os.environ.get("EEPHUS_XOVERLAY_PIT" if side == "pit"
                         else "EEPHUS_XOVERLAY_HIT")
    if env is not None:
        return env.strip() == "1"
    return OVERLAY_PIT_DEFAULT if side == "pit" else OVERLAY_HIT_DEFAULT


@lru_cache(maxsize=1)
def _signals() -> dict:
    """The baked sidecar (frozen coefficients + per-player z legs); {} when
    absent so the overlay degrades to a no-op."""
    try:
        return json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _aaa_survivors() -> dict:
    """W-SCREEN survivor legs {feature: {intercept, slope, resid_sd}} with the
    coefficients FROZEN in the screen artifact (resid_fit_on_astuff + resid_sd,
    fit once 2026-07-24, never refit at serve). {} when absent -> AAA legs off."""
    try:
        doc = json.loads(AAA_SCREEN_PATH.read_text(encoding="utf-8"))
        out = {}
        for feat, c in (doc.get("survivors") or {}).items():
            fit = c.get("resid_fit_on_astuff") or {}
            sd = c.get("resid_sd")
            if fit.get("slope") is None or fit.get("intercept") is None or not sd:
                continue
            out[feat] = {"intercept": float(fit["intercept"]),
                         "slope": float(fit["slope"]), "resid_sd": float(sd)}
        return out
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _aaa_physics() -> dict:
    """data/aaa_physics.json players block (mlbam -> season -> physics);
    {} when absent so the AAA legs degrade to a no-op."""
    try:
        return json.loads(AAA_PHYSICS_PATH.read_text(encoding="utf-8")).get("players") or {}
    except Exception:
        return {}


@lru_cache(maxsize=4096)
def _aaa_vaa_mean(mlbam: int, season: int):
    """Season-mean VAA (deg) over VAA-computable cached pitches from the
    bounded-refetch cache, or None below the MIN_VAA_PITCHES floor / absent
    CSV. Formula = vaa.py calculate_vaa (y0 50ft, plate 17/12), matching the
    frozen W-SCREEN protocol exactly."""
    import csv
    import io
    import math
    path = AAA_VAA_DIR / f"{int(mlbam)}_{int(season)}.csv"
    if not path.exists():
        return None
    vals = []
    try:
        for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
            try:
                vy0, vz0 = float(r["vy0"]), float(r["vz0"])
                ay, az = float(r["ay"]), float(r["az"])
            except (KeyError, TypeError, ValueError):
                continue
            disc = (vy0 * vy0) - (2 * ay * (50.0 - 17.0 / 12.0))
            if disc < 0 or ay == 0:
                continue
            vy_f = -math.sqrt(disc)
            t = (vy_f - vy0) / ay
            vz_f = vz0 + (az * t)
            vals.append(-math.atan(vz_f / vy_f) * (180 / math.pi))
    except OSError:
        return None
    if len(vals) < MIN_VAA_PITCHES:
        return None
    return sum(vals) / len(vals)


def _pit_legs(mlbam, milb, sig):
    """Active pitcher legs [(name, directed_z, n_pitches, chip)] under the
    frozen W-OVERLAY-R leg rules. All pit legs point positive (a HIGH residual
    is stuff the stat line has not paid for yet -> POSITIVE FV lean; every
    screen survivor passed on the same orientation)."""
    a_leg = None
    entry = (sig.get("by_mlbam") or {}).get(str(int(mlbam)))
    if (entry and entry.get("side") == "pit"
            and entry.get("level") in _LEVELS
            and entry.get("level") == milb.get("milb_level")
            and entry.get("season") == milb.get("milb_season")
            and (entry.get("n_pitches") or 0) >= MIN_PITCHES):
        c = (sig.get("frozen_coefficients") or {}).get("pit_velo_on_ka")
        sz, bz = entry.get("velo_z"), entry.get("k_a_z")
        if c and sz is not None and bz is not None:
            rz = float(sz) - (float(c["slope"]) * float(bz) + float(c["intercept"]))
            a_leg = ("fb_velo_a", rz, int(entry.get("n_pitches") or 0), CHIP_LABEL)
    aaa_velo, aaa_rest = None, []
    if milb.get("milb_level") == _AAA and milb.get("milb_season") is not None:
        e = (_aaa_physics().get(str(int(mlbam))) or {}).get(str(milb.get("milb_season")))
        surv = _aaa_survivors()
        if (e and (e.get("n_pitches") or 0) >= MIN_PITCHES
                and e.get("astuff_pool") is not None):
            ast = float(e["astuff_pool"])
            npit = int(e.get("n_pitches") or 0)
            for feat in ("velo", "spin"):
                c = surv.get(feat)
                if c and e.get(feat) is not None:
                    z = (float(e[feat]) - (c["intercept"] + c["slope"] * ast)) / c["resid_sd"]
                    leg = (f"{feat}_aaa", z, npit, CHIP_LABEL_AAA)
                    if feat == "velo":
                        aaa_velo = leg
                    else:
                        aaa_rest.append(leg)
            c = surv.get("vaa")
            if c:
                vm = _aaa_vaa_mean(int(mlbam), int(milb.get("milb_season")))
                if vm is not None:
                    z = (vm - (c["intercept"] + c["slope"] * ast)) / c["resid_sd"]
                    aaa_rest.append(("vaa_aaa", z, npit, CHIP_LABEL_AAA))
    legs = []
    # velo-family rule: at most ONE of {A-ball fb_velo signal, AAA velo
    # residual}; prefer the level with the larger recent sample. (The
    # current-season gates make the two structurally exclusive; the
    # preference is the frozen tiebreak should a future sidecar overlap.)
    if a_leg is not None and aaa_velo is not None:
        legs.append(a_leg if a_leg[2] >= aaa_velo[2] else aaa_velo)
    elif a_leg is not None:
        legs.append(a_leg)
    elif aaa_velo is not None:
        legs.append(aaa_velo)
    legs.extend(aaa_rest)
    return legs


def overlay_fv(row, side: str | None = None):
    """(delta_fv, chip_label) for a live-board row, or None (= untouched).

    `row` is an efv_dataset live-matrix row (needs mlbam_id + the milb
    feature dict). `side` is "hit"/"pit" when the caller knows it (run_live
    does); otherwise it is taken from the signal entry (AAA-physics-only
    pitchers derive "pit"). The delta is in FV points on the MODEL leg; the
    caller prices it through the blend's own FV->WAR line."""
    if side is not None and not _flag(side):
        return None
    mlbam = row.get("mlbam_id")
    milb = row.get("milb") or {}
    if not mlbam or not milb:
        return None
    sig = _signals()
    entry = (sig.get("by_mlbam") or {}).get(str(int(mlbam)))
    if side is None:
        if entry:
            side = "pit" if entry.get("side") == "pit" else "hit"
        elif (milb.get("milb_level") == _AAA
                and str(int(mlbam)) in _aaa_physics()):
            side = "pit"
        else:
            return None
        if not _flag(side):
            return None
    if side == "pit":
        legs = _pit_legs(mlbam, milb, sig)
        if not legs:
            return None
        composite = sum(z for _n, z, _p, _c in legs) / len(legs)
        chip = CHIP_LABEL if all(c == CHIP_LABEL for _n, _z, _p, c in legs) \
            else CHIP_LABEL_AAA
    else:
        # hit side: the whiff leg only (frozen W-OVERLAY-R leg rule), gates
        # exactly as built. ACTIVE A/CPX: the player's most-recent tracked
        # season/level must be the baked signal's.
        if (not entry or entry.get("side") == "pit"
                or entry.get("level") not in _LEVELS
                or entry.get("level") != milb.get("milb_level")
                or entry.get("season") != milb.get("milb_season")
                or (entry.get("n_pitches") or 0) < MIN_PITCHES):
            return None
        c = (sig.get("frozen_coefficients") or {}).get("hit_whiff_on_k")
        sz, bz = entry.get("whiff_z"), entry.get("k_z")
        if not c or sz is None or bz is None:
            return None
        # a HIGH whiff residual is strikeout risk -> NEGATIVE FV lean
        composite = -(float(sz) - (float(c["slope"]) * float(bz) + float(c["intercept"])))
        chip = CHIP_LABEL
    delta = BETA_FV_PER_RESID_Z * composite
    delta = round(max(-DELTA_CAP_FV, min(DELTA_CAP_FV, delta)), 2)
    if delta == 0.0:
        return None
    return delta, chip

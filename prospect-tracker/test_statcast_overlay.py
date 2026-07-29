# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""S-XLINE-4 + W-OVERLAY-R "Statcast lean" overlay pins.

A4 UNCAPPED SHIP (docs/efv-2026-07-24/GATES-ACCURACY.md): the owner removed the
board-movement ceilings. The overlay had FAILED earlier post-flip gates ONLY on
a display-space ceiling, never on signal; with the ceiling gone it ships default
ON for covered players, uncapped (the 2-FV DISPLAY cap removed, only a wide
numerical-safety sanity bound remains). These tests pin the NEW ship decision
(defaults ON), the FLAG-GATED OFF=identity contract (flag explicitly "0" ->
no-op, so an uncovered/disabled path contributes exactly nothing), the removal
of the display clamp (raw lean passes through the wide safety bound), both
registered sign directions, the qualification gates, and that the coefficients
are LOADED frozen (no refit at serve). Fully synthetic - no DB, no
served-artifact regen."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import efv_statcast_overlay as ov

ROOT = Path(__file__).parent

_COEFFS = {
    "hit_whiff_on_k": {"slope": 0.9, "intercept": 0.1},
    "pit_velo_on_ka": {"slope": 0.2, "intercept": -0.1},
}


def _sig(entries):
    return {"frozen_coefficients": _COEFFS, "by_mlbam": entries}


def _hit_row(mlbam=111, level="A", season=2026):
    return {"mlbam_id": mlbam, "milb": {"milb_level": level, "milb_season": season}}


def _hit_entry(**over):
    e = {"level": "A", "season": 2026, "side": "hit",
         "whiff_z": 2.0, "k_z": 0.0, "n_pitches": 250}
    e.update(over)
    return e


def _pit_entry(**over):
    e = {"level": "A", "season": 2026, "side": "pit",
         "velo_z": 2.0, "k_a_z": 0.0, "n_pitches": 400}
    e.update(over)
    return e


# --------------------------------------------------------------------------- #
# ship decision: defaults ON for covered players (A4 owner ceiling removal)
# --------------------------------------------------------------------------- #
def test_defaults_are_on():
    assert ov.OVERLAY_HIT_DEFAULT is True
    assert ov.OVERLAY_PIT_DEFAULT is True


def test_off_is_identity_when_flag_off(monkeypatch):
    # the FLAG-GATED OFF=identity contract: with the flag EXPLICITLY "0" a row
    # that WOULD qualify returns None, so a disabled path contributes exactly
    # nothing. (The default is now ON, so the default-off branch is gone.)
    monkeypatch.setattr(ov, "_signals", lambda: _sig({"111": _hit_entry()}))
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "0")
    assert ov.overlay_fv(_hit_row(), "hit") is None
    # positive control: default ON (env unset) DOES fire for the covered row
    monkeypatch.delenv("EEPHUS_XOVERLAY_HIT", raising=False)
    assert ov.overlay_fv(_hit_row(), "hit") is not None


def test_uncovered_row_is_identity_even_default_on(monkeypatch):
    # OFF-path byte-identity for UNCOVERED players is preserved regardless of
    # the ON default: an unlisted mlbam returns None (no move).
    monkeypatch.setattr(ov, "_signals", lambda: _sig({"111": _hit_entry()}))
    monkeypatch.delenv("EEPHUS_XOVERLAY_HIT", raising=False)
    assert ov.overlay_fv(_hit_row(mlbam=999), "hit") is None


# --------------------------------------------------------------------------- #
# clamp + sign directions (registered a priori: BETA 0.6, cap +-2.0)
# --------------------------------------------------------------------------- #
def test_hitter_high_whiff_residual_is_negative(monkeypatch):
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "1")
    monkeypatch.setattr(ov, "_signals", lambda: _sig({"111": _hit_entry()}))
    delta, label = ov.overlay_fv(_hit_row(), "hit")
    # residual = 2.0 - (0.9*0.0 + 0.1) = 1.9 -> delta = -0.6*1.9 = -1.14
    assert delta == -1.14
    assert label == ov.CHIP_LABEL


def test_pitcher_high_velo_residual_is_positive(monkeypatch):
    monkeypatch.setenv("EEPHUS_XOVERLAY_PIT", "1")
    monkeypatch.setattr(ov, "_signals", lambda: _sig({"222": _pit_entry()}))
    delta, _ = ov.overlay_fv(_hit_row(mlbam=222), "pit")
    # residual = 2.0 - (0.2*0.0 - 0.1) = 2.1 -> delta = +0.6*2.1 = +1.26
    assert delta == 1.26


def test_no_display_clamp_wide_safety_bound(monkeypatch):
    # A4: the 2-FV DISPLAY cap is REMOVED. A raw lean well beyond the old cap
    # now PASSES THROUGH uncapped (true-to-model), bounded only by the wide
    # numerical-safety sanity bound (12.0), which never binds on plausible
    # signal (max real lean observed ~2.4 FV).
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "1")
    monkeypatch.setenv("EEPHUS_XOVERLAY_PIT", "1")
    monkeypatch.setattr(ov, "_signals", lambda: _sig({
        "111": _hit_entry(whiff_z=10.0),         # raw -0.6*9.9 = -5.94 (was clamped to -2.0)
        "222": _pit_entry(velo_z=10.0),          # raw +0.6*10.1 = +6.06 (was clamped to +2.0)
    }))
    assert ov.overlay_fv(_hit_row(), "hit")[0] == -5.94
    assert ov.overlay_fv(_hit_row(mlbam=222), "pit")[0] == 6.06
    assert ov.DELTA_CAP_FV == 12.0              # wide safety bound, not a display cap
    assert ov.BETA_FV_PER_RESID_Z == 0.6        # screen-calibrated, kept


def test_safety_bound_still_clamps_pathological(monkeypatch):
    # the sanity bound guards a corrupt-cache composite z from an absurd lean.
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "1")
    monkeypatch.setattr(ov, "_signals", lambda: _sig({
        "111": _hit_entry(whiff_z=100.0),        # raw -0.6*99.9 = -59.9 -> clamped
    }))
    assert ov.overlay_fv(_hit_row(), "hit")[0] == -ov.DELTA_CAP_FV


# --------------------------------------------------------------------------- #
# qualification gates (active A/CPX current season, >= 100 pitches, side match)
# --------------------------------------------------------------------------- #
def test_qualification_gates(monkeypatch):
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "1")
    monkeypatch.setattr(ov, "_signals", lambda: _sig({
        "1": _hit_entry(n_pitches=99),           # under the exposure floor
        "2": _hit_entry(level="AAA"),            # not an A/CPX signal
        "3": _hit_entry(),                       # season/level must match the row
        "4": _hit_entry(),                       # side mismatch
    }))
    assert ov.overlay_fv(_hit_row(mlbam=1), "hit") is None
    assert ov.overlay_fv(_hit_row(mlbam=2, level="AAA"), "hit") is None
    assert ov.overlay_fv(_hit_row(mlbam=3, season=2025), "hit") is None
    assert ov.overlay_fv(_hit_row(mlbam=3, level="A+"), "hit") is None
    assert ov.overlay_fv(_hit_row(mlbam=4), "pit") is None
    assert ov.overlay_fv({"mlbam_id": None, "milb": {}}, "hit") is None
    # the matching row still passes (control for the gates above)
    assert ov.overlay_fv(_hit_row(mlbam=3), "hit") is not None


# --------------------------------------------------------------------------- #
# frozen coefficients: loaded from the sidecar, never refit at serve
# --------------------------------------------------------------------------- #
def test_frozen_coefficients_loaded_not_refit(monkeypatch):
    # the overlay must price with the sidecar's coefficients verbatim
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "1")
    coeffs = {"hit_whiff_on_k": {"slope": 0.0, "intercept": 0.0},
              "pit_velo_on_ka": {"slope": 0.0, "intercept": 0.0}}
    monkeypatch.setattr(ov, "_signals", lambda: {
        "frozen_coefficients": coeffs,
        "by_mlbam": {"111": _hit_entry(whiff_z=1.0, k_z=5.0)}})
    # slope 0 -> residual ignores k_z entirely: delta = -0.6*1.0
    assert ov.overlay_fv(_hit_row(), "hit")[0] == -0.6


def test_baked_sidecar_matches_exporter_constants():
    import statcast_alevel_export as ex
    baked = json.loads((ROOT / "data" / "statcast_alevel_signals.json")
                       .read_text(encoding="utf-8"))
    assert baked["frozen_coefficients"] == ex.FROZEN_COEFFICIENTS
    for k in ("hit_whiff_on_k", "pit_velo_on_ka"):
        assert set(ex.FROZEN_COEFFICIENTS[k]) >= {"slope", "intercept", "n"}


def test_exporter_has_no_fit_code():
    # the no-refit guarantee is structural: the exporter contains constants
    # only - no regression machinery anywhere in the module.
    import statcast_alevel_export as ex
    src = inspect.getsource(ex)
    for banned in ("polyfit", "lstsq", "corrcoef", "linalg", "OLS(", "np.cov"):
        assert banned not in src, banned


def test_missing_sidecar_degrades_to_noop(monkeypatch):
    monkeypatch.setenv("EEPHUS_XOVERLAY_HIT", "1")
    monkeypatch.setattr(ov, "_signals", lambda: {})
    assert ov.overlay_fv(_hit_row(), "hit") is None

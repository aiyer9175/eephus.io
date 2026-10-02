# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Correction P20 (docs/dpw-2026-09-25/DPW_PATH_GATE.md section 1.1), on
SYNTHETIC histories: inside the playing-time formula only, every 2020 exposure
is scaled by 162/60; rates, the aging curves and every other season are
unchanged; the flag is off by default everywhere, so project_player is
byte-identical without it, and only the dpw_path writer's enrichment sets it."""

from __future__ import annotations

import inspect

import pytest

import fa_market as fm
import fa_projection as fp

_LG = {"woba": 0.315, "r_pa": 0.118, "k_pct": 0.222, "bb_pct": 0.084, "iso": 0.158,
       "babip": 0.291, "hr_pa": 0.031, "fip_constant": 3.13, "lg_fip": 4.16,
       "p_k_pct": 0.222, "p_bb_pct": 0.084, "p_hr_bf": 0.031}
LEAGUE = {y: {"season": y, **_LG} for y in range(2014, 2028)}
NO_CURVES = {"hit": {}, "pit": {}}


def _h(season, pa, target):
    return {"mlbam": 1, "season": season, "age": 29 - (target - season), "role": "H", "pa": pa,
            "k_pct": 0.18, "bb_pct": 0.10, "iso": 0.22, "babip": 0.31, "hr_pa": 0.045, "war": 3.0}


def _p(season, ip, bf, target):
    return {"mlbam": 2, "season": season, "age": 30 - (target - season), "role": "SP", "bf": bf,
            "ip": ip, "k_pct": 0.25, "bb_pct": 0.08, "hr_bf": 0.03, "babip": 0.29, "war": 2.0}


def test_the_scale_is_162_over_60_on_2020_only():
    assert fp.P20_FACTOR == 162.0 / 60.0
    assert fp._p20_scale(230.0, 2020) == pytest.approx(230.0 * 2.7)
    assert fp._p20_scale(230.0, 2019) == 230.0
    assert fp._p20_scale(230.0, 2021) == 230.0


@pytest.mark.parametrize("target,seasons", [(2021, (2020, 2019, 2018)), (2022, (2021, 2020, 2019)),
                                            (2023, (2022, 2021, 2020))])
def test_p20_moves_only_playing_time_when_2020_is_in_the_window(target, seasons):
    hist = [_h(s, 230.0 if s == 2020 else 610.0, target) for s in seasons]
    off = fp.project_player(hist, "hit", target, NO_CURVES, LEAGUE, 29)
    on = fp.project_player(hist, "hit", target, NO_CURVES, LEAGUE, 29, p20=True)
    moved = {k for k in off if off[k] != on[k]}
    assert moved == {"pt_proj"}, moved                     # e1, e2 and e3 (pt_fit "hit")
    ph = [_p(s, 60.0 if s == 2020 else 170.0, 250.0 if s == 2020 else 700.0, target) for s in seasons]
    off = fp.project_player(ph, "pit", target, NO_CURVES, LEAGUE, 30, role="SP")
    on = fp.project_player(ph, "pit", target, NO_CURVES, LEAGUE, 30, role="SP", p20=True)
    moved = {k for k in off if off[k] != on[k]}
    if 2020 in (target - 1, target - 2):                    # ip1, ip2 (ip3 only under pt_fit "both")
        assert moved <= {"pt_proj", "ip_proj"} and "ip_proj" in moved, moved
    else:
        assert moved == set(), moved


def test_p20_does_nothing_outside_the_2020_window():
    hist = [_h(s, 600.0, 2020) for s in (2019, 2018, 2017)]
    assert fp.project_player(hist, "hit", 2020, NO_CURVES, LEAGUE, 29) == \
        fp.project_player(hist, "hit", 2020, NO_CURVES, LEAGUE, 29, p20=True)
    hist = [_h(s, 600.0, 2025) for s in (2024, 2023, 2022)]
    assert fp.project_player(hist, "hit", 2025, NO_CURVES, LEAGUE, 29) == \
        fp.project_player(hist, "hit", 2025, NO_CURVES, LEAGUE, 29, p20=True)


def test_the_flag_defaults_off_everywhere_and_only_the_path_writer_sets_it():
    for fn in (fp.project_player, fm.contract_war_path, fm.enriched_signings):
        assert inspect.signature(fn).parameters["p20"].default is False
    src = inspect.getsource(fm.build_dpw_path_block)
    assert "enriched_signings(DPW_SERIES_FIRST_WINTER, N, p20=True)" in src
    import pathlib
    root = pathlib.Path(fm.__file__).parent
    setters = []
    for p in root.glob("*.py"):
        if p.name.startswith("test_"):
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        if "p20=True" in txt:
            setters.append(p.name)
    assert setters == ["fa_market.py"], setters

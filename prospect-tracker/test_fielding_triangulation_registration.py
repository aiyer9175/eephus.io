# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fielding triangulation registration pins (task EWAR_LADDER, owner decisions
EW3-18, EW3-20 and its UZR amendment, EW3-23, EW3-25, EW3-29).

docs/ewar/FIELDING_TRIANGULATION_GATE.md is committed ALONE, with this file and
EBR_GATE.md amendment 11.5, before any number of its estimands exists. Every clause
is pinned by the sentence that makes it bind. Prose assertions run on a
whitespace-flattened copy so that re-wrapping a paragraph is not a failure. Results
go in part 11 of the document, never above it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar" / "FIELDING_TRIANGULATION_GATE.md"
RESULTS = "## 11. Results"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _above() -> str:
    return _flat(_doc().split(RESULTS, 1)[0])


def test_registered_before_any_number():
    flat = _flat(_doc())
    assert flat.startswith("# Fielding triangulation: SDR, OAA, DRS, UZR and FanGraphs fielding as "
                           "noisy readings of one skill (fielding_triangulation_v1)")
    assert "`test_fielding_triangulation_registration.py`" in flat
    assert "The read runs ONCE (part 5)." in flat
    assert "OWNER-WAIVED EARLY READ (EW3-5)" in flat


def test_the_route_through_the_sdr_gates():
    flat = _above()
    assert "outside the SDR gates G-A and G-B" in flat
    assert "G-B's merge object, a w-grid over eWAR v2's Baseball-Reference fielding, is not run" in flat
    assert "candidate part 6's second arm S3t" in flat


def test_sources_systems_and_nesting():
    flat = _above()
    assert "FanGraphs Fld at the position level is FRP." in flat
    assert "DEM+ is nested, not a separate reading." in flat
    assert "the DRS system is {DRS, UZR}" in flat
    assert "the Statcast system is {OAA, FRP}" in flat
    assert "a season FanGraphs does not publish is a missing reading" in flat
    assert "No fetch is made for it" in flat


def test_the_model_and_its_fit_window():
    flat = _above()
    assert "fit once on data seasons 2016 to 2018, frozen" in flat
    assert "pairs (Y, Y + 1), Y in {2016, 2017}" in flat
    assert "No 2019 row is read by the fit." in flat
    assert "lambda = sqrt(max(e1, 0)) * v1" in flat
    assert "x_s,r * x_t,r = A_st + Psi_st * (1000 / n_r) + error" in flat
    assert "Psi's at 0.001 * trace(Psi) / k" in flat
    assert "T_rate,r = lambda_FRP * lambda_a' Sigma_aa(n_r)^-1 x_a,r" in flat
    assert "nothing is refitted per configuration" in flat
    assert "The read refits nothing." in flat


def test_configurations():
    flat = _above()
    assert "| FULL | SDR, OAA, DRS, UZR, FRP |" in flat
    assert "| X_DRS | SDR without DRS, OAA, FRP |" in flat
    assert "| X_UZR | SDR without DRS, OAA, FRP |" in flat
    assert "| X_SC | SDR without Statcast, DRS, UZR |" in flat


def test_catchers_on_sdr_catcher_components_only():
    flat = _above()
    assert "Catchers are valued on SDR's catcher components" in flat
    assert "K_k = hm * (1 - r_k) / r_k" in flat
    assert "FanGraphs' Statcast blocking (bFRP, 2016 on) stands in" in flat


def test_the_part_and_its_invariants():
    flat = _above()
    assert "g_fldt,i = T_i - (Fld_i + Frm_i if i caught, else Fld_i)" in flat
    assert "d_fldt,i = g_fldt,i - PA_i * (sum_k g_fldt,k) / (sum_k PA_k)" in flat
    assert "(2) d_fldt sums to 0 per season within 1e-9 runs" in flat
    assert "(7) the build never writes `data/ewar.json`" in flat


def test_the_read():
    flat = _above()
    assert "Predictor seasons Y = 2019 to 2025, outcome seasons 2020 to 2026" in flat
    assert "Bootstrap B = 2,000, seed 20261016" in flat
    assert "the twin's permutation seed 20261017" in flat
    assert "MDE95 = 1.645 sd" in flat
    assert "| DRS | DRS per inning | X_DRS | FRP (the base's fielding at the position) |" in flat
    assert "| Statcast | FRP per inning | X_SC | DRS |" in flat
    assert "| UZR | UZR per inning, Y + 1 at most 2024 | X_UZR | FRP |" in flat
    assert "The leg's gap is the mean of the three gaps." in flat
    assert ("L1 passes** when its gap is above 0, LB95 is above 0, Holm (part 5.4) rejects, and its "
            "twin does not pass the same rule.") in flat
    assert "S_c = sum over players of rate_i(Y) * n_ic(Y + 1)" in flat
    assert "gap minus 1.645 sd is above -0.02 under both bootstraps" in flat
    assert "**Holm** across L1 and L2 at alpha 0.05 on the one-sided p." in flat
    assert ("PASS when L1 and L2 both pass; PARTIAL when one does; FAIL when neither does") in flat
    assert ("S3t is scored in the eWAR v3 skill look (EBR_GATE.md 11.5) only when L1 passes AND L2 is "
            "NON-INFERIOR.") in flat


def test_reported_beside_and_claims():
    flat = _above()
    assert "**SDR alone against the triangulation**" in flat
    assert "the equal-weight blend" in flat
    assert "No sentence claims \"better defense metric\", \"true talent\" or \"more accurate WAR\"." in flat
    assert "**Served:** nothing. No page reads T, no exporter writes it, and no flag exists." in flat


def test_the_ladder_half_and_the_scale_defect():
    flat = _above()
    assert "**Not re-read here (DEFERRED to an unseen frame).**" in flat
    assert "No ladder number is computed by this task." in flat
    assert "`positional_fit.POSFIT_ONE_SCALE = True`" in flat


RESULT_PATTERNS = (
    r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]",
    r"\bp\s*=\s*-?0?\.\d",
    r"\brho\s*=\s*-?\d",
    r"\bgap\s*=\s*[-+]?\d",
    r"\bverdict\s*:\s*\w",
    r"\bLB95\s*[-+]?\d",
)


def test_no_result_above_part_11():
    above = _doc().split(RESULTS, 1)[0]
    for pattern in RESULT_PATTERNS:
        m = re.search(pattern, above, re.I)
        assert m is None, f"a result is recorded above part 11: {m.group(0) if m else ''!r}"

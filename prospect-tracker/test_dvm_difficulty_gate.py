# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the DvM+ development-difficulty gate registration
(docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md, DVM-2).

The registration was committed ALONE, before any growth statistic was computed. These
tests pin its CRITERIA as text of the document: the frames, the seeds, the Holm
families, the margins, the clock and the EMPTY results section, plus parity with the
constants the DVM-1 frame module already carries (tools/dvm_difficulty_lab.py) and with
the FV_EXPECTED_WAR table the value credit reads. Nothing here reads a frame row.

Prose assertions run against a whitespace-flattened copy of the document, so a
re-wrapped paragraph is not a failure; an edited criterion is. Sections 0 to 16 are
also pinned by hash: a change there needs a dated amendment in section 17 instead.

When section 18 is filled in, the result pin goes in its own file
(test_dvm_difficulty_gate_result.py): a result pin beside a criterion pin invites
editing the criterion to match the result.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from tools import dvm_difficulty_lab as L

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "dvm-difficulty-2026-09-30" / "DVM_DIFFICULTY_GATE.md"
RESULTS_HEADING = "## 18. Results"
AMENDMENTS_HEADING = "## 17. Amendments"
FROZEN_FROM = "## 0. What was already seen"
#: sha256 of the whitespace-flattened text from section 0 up to section 17's heading,
#: as registered. Changing a criterion changes it; an amendment goes in section 17.
FROZEN_SHA256 = "180779c29c8dc1d83d12fdb79edd505e33e975c45614d675574b1f89bb66a40f"
EVAL_ARTIFACT = ROOT / "data" / "dvm_difficulty_eval.json"
FROZEN_DB_SHA = "7d7e56533e6c62ef3ec3d8400e079974779ea59ca533dbc0e43939f596d6a56e"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_all(text: str, phrases) -> None:
    flat = _flat(text)
    missing = [p for p in phrases if _flat(p) not in flat]
    assert not missing, "registration text no longer carries: " + repr(missing)


def _section(start: str, end: str) -> str:
    d = _doc()
    i = d.index(start)
    return d[i:d.index(end, i)]


def _frozen_text() -> str:
    return _flat(_section(FROZEN_FROM, AMENDMENTS_HEADING))


# ---------------------------------------------------------------------------
# status, path and the growth guard
# ---------------------------------------------------------------------------

def test_status_line_is_registered_alone():
    status = [ln.strip() for ln in _doc().splitlines()
              if ln.strip().startswith("Registration status:")]
    assert status == ["Registration status: REGISTERED"]


def test_lab_points_at_this_document():
    assert (ROOT / L.DVM_GATE_DOC).resolve() == DOC.resolve()


def test_growth_guard_opens_only_on_this_registration():
    L.assert_growth_allowed(dvm_gate_text=_doc())
    with pytest.raises(L.ClockError):
        L.assert_growth_allowed(dvm_gate_text=_doc().replace(
            "Registration status: REGISTERED", "Registration status: DRAFT"))


def test_no_dash_characters():
    d = _doc()
    assert chr(0x2014) not in d and chr(0x2013) not in d


def test_criteria_text_is_frozen():
    got = hashlib.sha256(_frozen_text().encode("utf-8")).hexdigest()
    assert got == FROZEN_SHA256, (
        "sections 0 to 16 changed; file a dated amendment in section 17 instead")


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------

def test_frame_rules_are_registered():
    s = _section("## 2. Frame", "## 3. Outcome")
    _has_all(s, [
        "| F-R1 | any read in list year 2020 or 2021, so any pair with an endpoint in either",
        "the R-LV look record exists in `docs/efv-v2/EFV_V2_GATE.md` part 9 (`## 9. Results`) when the look starts (Q-DVM-1 A)",
        "| F-R2 | any end read that is the debut-year preseason read of a player who debuted in 2025 or later",
        "| not at this look, on any path |",
        "| F-R3 | the lab builds no frame before the ETA look record exists (a VOID counts)",
        "| F-R4 | no WAR, no `career_war`, no label module, no debut, graduation or bust rate by rung, no read of `value_framework.fv_to_6yr_avg_war` | never |",
        "| F-R5 | no eFV input of any kind",
        "FULL: the R-LV record exists when the look starts.",
        "COMPLEMENT: no R-LV record exists and the date is on or after 2027-01-31.",
        "(`MIN_LIST_READS = 100`)",
        FROZEN_DB_SHA,
    ])


def test_frame_constants_match_the_frame_module():
    assert L.RESERVED_LV == frozenset({2020, 2021})
    assert L.R_VM_FIRST_DEBUT_YEAR == 2025
    assert L.MIN_LIST_READS == 100
    assert L.HORIZONS == (1, 2)
    assert L.SOURCES == ("mlb_pipeline", "fangraphs", "baseballamerica")
    assert L.RLV_LOOK_RECORD == "1c73c420ad68bc6a8061859c6e82757589ef20c6"  # amendment A-2
    assert L.PIPELINE_2026_PRESEASON_DECLARED_ABSENT is True
    assert (L.P2_MAX_UNKNOWN_OVERALL, L.P2_MAX_UNKNOWN_CELL) == (0.05, 0.10)
    assert L.RUNGS == ("<=35", "40", "45", "50", "55", "60", "65+")


def test_value_table_matches_storage():
    tree = ast.parse((ROOT / "storage.py").read_text(encoding="utf-8"))
    table = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "FV_EXPECTED_WAR" for t in node.targets):
            table = ast.literal_eval(node.value)
    assert table is not None
    row = ", ".join(f"{k} {float(v):.1f}" for k, v in sorted(table.items()))
    _has_all(_section("## 3. Outcome", "## 4. Covariates"), [row])


# ---------------------------------------------------------------------------
# model, credit, aggregation
# ---------------------------------------------------------------------------

def test_model_shrinkage_and_spread_floor():
    _has_all(_section("## 5. The model", "## 6. Row credit"), [
        "omega_i = 1 / n_sources(p, V, h)",
        "u_hat[c] = n_c / (n_c + k_u) * mean_c(residual of the additive fit) if n_c >= 20",
        "k_u = max(20, s2_eps / tau2_u)",
        "s_hat = sqrt( (nu_c * s2_c + 30 * s2_side) / (nu_c + 30) )",
        "`b[s,side,r]` needs 30 pairs in its cell or it pools across sources",
    ])


def test_row_credit_is_value_above_expected():
    _has_all(_section("## 6. Row credit", "## 7. Club aggregation"), [
        "**DV, value above expected (the owner's choice):** `v_i = w_i - E^W_i`",
        "| today's FV-DvM+ (arithmetic on the table) | 13.0 / 2.5 = 5.2 |",
        "| DV | (13.0 - E^W[60]) / (2.5 - E^W[40]) |",
        "correlate below 0.9",
    ])


def test_club_aggregation_margins():
    _has_all(_section("## 7. Club aggregation", "## 8. Tools"), [
        "N_o = (sum_i tau_io * omega_i)^2 / sum_i (tau_io * omega_i)^2 Kish effective n",
        "bounded to [5, 50], frozen",
        "DvM+_o[W] = 100 + 10 * (D~_o - mean(D~)) / sd(D~)",
        "A club-window publishes only with `N_o >= 10`",
        "the shares of a pair sum to 1",
    ])
    _has_all(_section("## 9. The player index", "## 10. H1"), [
        "shrunk `n / (n + 2)`", "last 3 annual steps", "\"DvM+ (player)\""])


# ---------------------------------------------------------------------------
# hypotheses, seeds, families, power
# ---------------------------------------------------------------------------

def test_h1_families_seed_and_minimum_n():
    assert L.H1_FAMILY == 39
    _has_all(_section("## 10. H1", "## 11. H2"), [
        "B 2000, seed 20261201",
        "13 traits x 3 contrasts = 39 cells each (Theta_total 39, Theta_direct 39)",
        "each compared group needs 100 completed pairs for that side and trait",
        "the same sign under S1 and S2",
        "the same sign on Pipeline and FanGraphs separately",
        "at least two of three eras by start list year (2011-2016, 2017-2019, 2022 on",
        "500 draws, seed 20261201",
    ])


def test_h2_family_minimum_n_and_caveats():
    assert L.H2_FAMILY == 8
    _has_all(_section("## 11. H2", "## 12. Power"), [
        "**Holm family of 8** (2 sides x 4)",
        "fewer than 50 completed pairs at that horizon",
        "the primary, S1 and S2 frames all agree after Holm",
        "the FV scale is bounded",
        "regression to the mean pulls high start grades down",
        "graduation removes the fastest top-rung risers",
        "\"list grades rise less often from higher rungs\", never \"developing talent is harder there\"",
    ])


POWER_ROWS = [
    "| 12m | hit | 702.7 | 130.9 | 0.1067 | 0.1362 | 666.4 / 773.8 / 979.1 | 1.07 / 0.98 / 1.02 |",
    "| 12m | pit | 726.5 | 81.5 | 0.1309 | 0.1671 | 578.2 / 1094.0 / 458.6 | 1.04 / 1.13 / 1.27 |",
    "| 24m | hit | 256.1 | 59.2 | 0.1616 | 0.2063 | 266.3 / 309.5 / 378.9 | 1.70 / 1.56 / 1.62 |",
    "| 24m | pit | 267.5 | 39.1 | 0.1918 | 0.2448 | 233.6 / 440.4 / 171.1 | 1.64 / 1.83 / 2.04 |",
]


def test_power_block_is_registered():
    _has_all(_section("## 12. Power", "## 13. Validation"), POWER_ROWS + [
        "1.5068 sources per player-year",
        "8,020 completed pairs (pooled share 0.5361)",
        "3,205 completed pairs (0.2904)",
    ])
    assert (L.POWER_ASSUMED_P, L.POWER_ASSUMED_SD, L.POWER_ALPHA, L.POWER_TARGET) == (
        0.2, 5.0, 0.05, 0.8)


def _row(hz: str, side: str, blk: dict) -> str:
    s = blk[hz]["by_side"][side]
    h1 = s["h1_effective_pairs_rungs_40_to_55"]
    g = s["h1_detectable_gap_grade_points_holm_strictest"]
    return (f"| {hz} | {side} | {s['h2_effective_pairs_rung40']} | "
            f"{s['h2_effective_pairs_rung60plus']} | {s['h2_detectable_diff_p_unadjusted']} | "
            f"{s['h2_detectable_diff_p_holm_strictest']} | "
            f"{h1['HS']} / {h1['COL']} / {h1['IFA']} | "
            f"{g['HS-COL']:.2f} / {g['IFA-COL']:.2f} / {g['HS-IFA']:.2f} |")


def test_power_block_recomputes_from_the_frozen_counts():
    p = L.CACHE_DIR / "frame_counts.json"
    if not p.exists():
        pytest.skip("no DVM-1 counts on this machine")
    counts = json.loads(p.read_text(encoding="utf-8"))
    if (counts.get("receipt") or {}).get("frozen_db_sha256") != FROZEN_DB_SHA:
        pytest.skip("the cached counts are not the registered frozen store's")
    blk = L.power_block(counts)
    got = [_row(hz, side, blk) for hz in ("12m", "24m") for side in ("hit", "pit")]
    assert got == POWER_ROWS


# ---------------------------------------------------------------------------
# validation and decision rule
# ---------------------------------------------------------------------------

def test_validation_and_decision_rule():
    _has_all(_section("## 13. Validation", "## 14. The clock"), [
        "| V-P1 |", "| V-P2 |", "| V-S |", "| V-C |",
        "Club-clustered bootstrap (resample the 30 clubs with all their years), B 2000, seed 20261201",
        "Holm across DV and D0 within V-P2 (family of 2) and within V-S (family of 2)",
        "each validation year's expectation model is refit leaving out list years Y-1, Y and Y+1",
        "its composition maximum is at most 0.20, or at least 0.10 below C0's",
        "the one-sided 95 percent lower bound of the delta is above -0.05",
        "no Holm-resolved loss to C0 on V-P2 or V-S",
        "A tie on prediction ships under Q-DVM-3 A when 1 to 3 hold.",
        "\"difficulty-adjusted; ties the previous index on prediction\"",
        "FULL frame: Y = 2012 to 2025. COMPLEMENT frame: Y in 2012-2018 and 2023-2025",
        "the flag `storage.DVM_DIFFICULTY_ARM` stays None until the owner flips it",
    ])


# ---------------------------------------------------------------------------
# the clock, the firewall, the results
# ---------------------------------------------------------------------------

def test_clock():
    _has_all(_section("## 14. The clock", "## 15. Isolation"), [
        "on or after the LATER of (a) 2026-12-01, (b) the ETA look record (exists, `be53132d`; a VOID would also count) and (c) the R-LV look record in `docs/efv-v2/EFV_V2_GATE.md` part 9, on the FULL frame",
        "the first run on or after **2027-01-31** on the COMPLEMENT frame",
        "only after the PROSPECT_ANCHOR look record exists in `docs/PROSPECT_ANCHOR_GATE.md` section 18 (`## 18. Results`)",
        "refuses a second scored look",
        "2026-10-23, 11-06, 11-13, 11-20, the eFV reserved-read day, 12-03, 12-08, 12-10, 2027-01-12",
    ])


def test_firewall_and_isolation():
    _has_all(_section("## 15. Isolation", "## 16. Honest priors"), [
        "No output of this lab (tables, residuals, club indices) enters any eFV head, driver or stratum without its own registration naming this artifact in its forking-paths count.",
        "the look aborts if any moves",
    ])


def test_results_empty_until_the_look():
    parts = re.split(r"(?m)^" + re.escape(RESULTS_HEADING) + r"\s*$", _doc())
    assert len(parts) == 2, "exactly one results heading"
    body = parts[1]
    empty = ("**EMPTY AT REGISTRATION.** Nothing is written here before the look. The first "
             "entry is dated, names the commit and the frame (FULL or COMPLEMENT), and "
             "carries the look's verbatim output.")
    if not EVAL_ARTIFACT.exists():
        assert _flat(body) == empty
    else:
        assert _flat(body) != empty, "the look wrote its artifact but no result entry"

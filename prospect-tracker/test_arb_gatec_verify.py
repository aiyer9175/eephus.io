# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE C verification pins (docs/ARBITRATION_GATE.md sections 9-10).

Three families:
  1. the gate_c_verification block scored 2026-08-19 on the shipped pricing
     pass (commit ea9cb564), which the 2026-08-09 ship owed and never ran;
  2. the retained-salary AAV adjudication: the employing-club row serves, the
     retaining club's row never enters the contract set;
  3. the team-outlook serve-vector tripwire computed at write time.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _doc(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    return json.loads(p.read_text("utf-8"))


# --------------------------------------------------------------------------- #
# 1. GATE C verification block
# --------------------------------------------------------------------------- #

def test_gate_c_verification_block_exists_and_passes():
    """The 2026-08-09 ship priced 103 rows and never scored C1-C6. The debt
    was closed 2026-08-19; the artifact carries the verdicts."""
    g = _doc("arbitration_eval.json").get("gate_c_verification")
    assert g, "gate_c_verification block missing from arbitration_eval.json"
    assert g["verdict"] == "PASS"
    for clause in ("c1_per_player_vs_ladders", "c2_surplus_backtest_no_degrade",
                   "c3_blast_radius", "c4_spearman", "c5_monotone_paths",
                   "c6_prospect_clamps"):
        assert g[clause]["verdict"] == "PASS", clause


def test_c1_margin_cleared_both_floors():
    """The served per-player chain beats BOTH ladders by more than the
    player-clustered MDE95 of each contrast (4.98x / 3.51x at scoring)."""
    c1 = _doc("arbitration_eval.json")["gate_c_verification"][
        "c1_per_player_vs_ladders"]
    assert c1["gain_vs_clemens_usd"] >= c1["mde95_onesided_usd"]["vs_clemens"]
    assert c1["gain_vs_fitted_usd"] >= c1["mde95_onesided_usd"]["vs_fitted"]
    assert c1["mae_usd"]["served"] < c1["mae_usd"]["clemens_2026"]
    assert c1["mae_usd"]["served"] < c1["mae_usd"]["fitted"]


def test_c3_blast_radius_inside_bound():
    c3 = _doc("arbitration_eval.json")["gate_c_verification"]["c3_blast_radius"]
    assert c3["M_usd"] <= c3["bound"] * c3["E_const_usd"]


def test_c5_and_c6_are_zero_count_clauses():
    g = _doc("arbitration_eval.json")["gate_c_verification"]
    assert g["c5_monotone_paths"]["violations"] == 0
    assert g["c6_prospect_clamps"]["arb_priced_prospects"] == 0


def test_c4_is_recorded_as_a_guard_not_evidence():
    """Section 0a's rule: Spearman 1.0 across the admissible range means C4
    cannot discriminate; the block must say so rather than cite it."""
    c4 = _doc("arbitration_eval.json")["gate_c_verification"]["c4_spearman"]
    assert c4["spearman_pre_post"] >= 0.97
    assert "regression guard" in c4["note"]


# --------------------------------------------------------------------------- #
# 2. Retained-salary AAV adjudication (section 10)
# --------------------------------------------------------------------------- #

def test_retained_rows_cannot_reach_the_contract_set():
    """The employing-club row serves. A retained row on another club's page
    never competes in build_contracts_by_key's highest-AAV tiebreak, because
    scrape_spotrac_team_contracts never reads the STATUS tables at all."""
    import spotrac
    assert "dataTable-retained" in spotrac.STATUS_TABLE_IDS
    assert "dataTable-retained" not in spotrac.CONTRACT_TABLE_IDS
    # The tiebreak itself, on the two rows the adjudication measured: were the
    # retained row ever admitted, it would WIN and mis-serve the acquirer cost.
    active = {"player_key": "nolan-arenado", "aav_usd": 5_500_000,
              "team_slug": "arizona-diamondbacks"}
    retained = {"player_key": "nolan-arenado", "aav_usd": 27_361_111,
                "team_slug": "st-louis-cardinals"}
    assert spotrac.build_contracts_by_key(
        [active, retained])["nolan-arenado"] is retained
    assert spotrac.build_contracts_by_key(
        [active])["nolan-arenado"] is active


def test_served_aavs_are_the_employing_club_obligation():
    """Pin the two adjudicated cases against the cached pages. Skips when the
    Spotrac cache is absent (it is not committed).

    RE-PINNED 2026-10-04 (docs/ARBITRATION_GATE.md section 12). The 2026-10-03
    refetch is the first with Spotrac's year columns starting at 2027, so the
    2026 column rolled off. Arenado: the ARI row now reads $6,000,000 (the AAV
    over the 2027 column; $5.5M over 2026-2027 at section 10), the STL
    retained row $18,611,113 (was $27,361,111). Castellanos: his 2026-only SD
    dead row ($304,492 at section 10) is gone, so he has no contract row on SD.
    The adjudicated rule is unchanged: the employing club's row serves and a
    retained row never enters the contract set."""
    import spotrac
    from bs4 import BeautifulSoup

    def _parse(slug, table_ids):
        p = ROOT / ".cache" / f"spotrac_team_{slug}.html"
        if not p.exists():
            pytest.skip("spotrac team cache not present")
        soup = BeautifulSoup(p.read_text("utf-8", errors="replace"),
                             "html.parser")
        rows = []
        for tid in table_ids:
            t = soup.find("table", id=tid)
            if t is not None:
                rows.extend(spotrac._parse_team_contract_table(t, slug))
        return rows

    # Arenado: the employing club's (ARI) row, at the figure the parser reads.
    ari = [r for r in _parse("arizona-diamondbacks", spotrac.CONTRACT_TABLE_IDS)
           if "arenado" in r["player_key"]]
    assert ari, "arenado not found on arizona-diamondbacks"
    assert ari[0]["aav_usd"] == 6_000_000, ari[0]["aav_usd"]
    stl_contract = [r for r in _parse("st-louis-cardinals", spotrac.CONTRACT_TABLE_IDS)
                    if "arenado" in r["player_key"]]
    assert not stl_contract, "the STL retained row reached the contract set"
    stl_retained = [r for r in _parse("st-louis-cardinals", spotrac.STATUS_TABLE_IDS)
                    if "arenado" in r["player_key"]]
    for r in stl_retained:
        assert r["aav_usd"] != ari[0]["aav_usd"], "ARI serves the STL retained figure"
    served = spotrac.build_contracts_by_key(ari + stl_contract)["nolan_arenado"]
    assert served["team_slug"] == "arizona-diamondbacks"

    # Castellanos: rolled off SD; the PHI retained row still never competes.
    sd = [r for r in _parse("san-diego-padres", spotrac.CONTRACT_TABLE_IDS)
          if "castellanos" in r["player_key"]]
    assert not sd, ("castellanos is back on SD's contract tables: re-pin", sd)
    phi = [r for r in _parse("philadelphia-phillies", spotrac.CONTRACT_TABLE_IDS)
           if "castellanos" in r["player_key"]]
    assert not phi, "the PHI retained row reached the contract set"


def test_the_adjudication_is_recorded_where_the_flag_was():
    """spotrac.py's OPEN flag resolved in place; the gate doc carries the
    section it points to."""
    src = (ROOT / "spotrac.py").read_text("utf-8")
    assert "ADJUDICATED 2026-08-19" in src
    assert "OPEN, for a future session" not in src
    doc = (ROOT / "docs" / "ARBITRATION_GATE.md").read_text("utf-8")
    assert "## 10. Retained-salary AAV adjudication" in doc


# --------------------------------------------------------------------------- #
# 3. Team-outlook serve-vector tripwire
# --------------------------------------------------------------------------- #

def test_serve_vector_tripwire_is_computed_at_write_time():
    import inspect

    import proj_export as PX
    src = inspect.getsource(PX._write_team_outlook_eval)
    assert "serve_vector_flag" in src and "served_recentered" in src


def test_serve_vector_flag_matches_its_own_retro_block():
    ev = _doc("team_outlook_eval.json")
    hm = ((ev.get("retro_backtest") or {}).get("ship_decision") or {}).get(
        "holdout_mae") or {}
    srv, plain = hm.get("served_recentered"), hm.get("recentered")
    if not isinstance(srv, (int, float)) or not isinstance(plain, (int, float)):
        assert ev.get("serve_vector_flag") is None
    else:
        assert ev.get("serve_vector_flag") == (srv > plain)

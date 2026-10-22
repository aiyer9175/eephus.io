# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR v3's assembly and its provider (docs/ebr-2026-09-30/EBR_GATE.md 9.2, 9.7
and 11.10): the ABS part's identities, the assembler on fixtures, the runs-per-win
guard as an identity, the provider contract and the served artifact's identities.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_ewar_v3 as B  # noqa: E402
import ewar_v3 as V3  # noqa: E402
import war_source  # noqa: E402


# --------------------------------------------------------------------------- #
# the ABS part (11.10.2)
# --------------------------------------------------------------------------- #
def _ch(role, side, cid, pid, o, v, c=0.05):
    return {"role": role, "challenge_side": side, "challenger_id": cid, "pitcher_id": pid,
            "o": o, "v": v, "c": c}


HIT_PA = {1: 500.0, 2: 400.0, 3: 300.0, 4: 0.0}      # 1, 2 catchers; 3 a batter; 4 a pitcher-batter
PIT_IP = {10: 180.0, 11: 60.0, 12: 0.0}
C_INN = {1: 900.0, 2: 300.0}
FRAME = [
    _ch("catcher", "fielding", 1, 10, 1, 0.30),
    _ch("catcher", "fielding", 1, 11, 1, 0.20),
    _ch("catcher", "fielding", 2, 10, 0, 0.25, 0.08),
    _ch("batter", "batting", 3, 10, 1, 0.40),          # his own overturn: already in his batting runs
    _ch("batter", "batting", 3, 11, 0, 0.30, 0.06),
    _ch("pitcher", "fielding", 11, 11, 1, 0.22),       # his own overturn: moves nothing
    _ch("pitcher", "fielding", 10, 10, 0, 0.10, 0.04),
    _ch("unresolved", "fielding", None, 10, 0, 0.10, 0.03),
]


def test_abs_terms_are_zero_sum_per_term_and_side():
    t = V3.abs_terms(FRAME, HIT_PA, PIT_IP, C_INN)
    for side, keys in (("bat", ("move", "cost", "runs")), ("pit", ("charge", "cost", "runs"))):
        for k in keys:
            assert abs(sum(r[k] for r in t[side].values())) < 1e-12, (side, k)
    rec = t["receipt"]
    assert rec["catcher_won_runs"] == pytest.approx(0.50)
    assert rec["sum_move_raw"] == pytest.approx(0.50) and rec["sum_charge_raw"] == pytest.approx(-0.50)
    assert rec["batter_overturned_not_added"] == 1 and rec["pitcher_self_overturned"] == 1
    assert rec["no_challenger"] == 1
    assert rec["failure_cost_runs"] == pytest.approx(0.08 + 0.06 + 0.04)


def test_abs_move_is_against_an_average_catcher_per_inning():
    t = V3.abs_terms(FRAME, HIT_PA, PIT_IP, C_INN)
    rate = 0.50 / 1200.0
    assert t["bat"][1]["move"] == pytest.approx(0.50 - 900.0 * rate)
    assert t["bat"][2]["move"] == pytest.approx(0.0 - 300.0 * rate)
    assert t["bat"][3]["move"] == 0.0               # not a catcher: no move term
    # the batter's own overturn adds nothing: his raw term is his failure cost only
    assert t["bat"][3]["cost_raw"] == pytest.approx(-0.06)
    # the pitchers' charge: catcher-won calls on their pitches, re-centred per IP
    assert t["pit"][10]["charge_raw"] == pytest.approx(-0.30)
    assert t["pit"][11]["charge_raw"] == pytest.approx(-0.20)
    assert t["pit"][10]["charge"] == pytest.approx(-0.30 + 180.0 * 0.50 / 240.0)
    # the pitcher who overturned his own call is neither credited nor charged for it
    assert t["pit"][11]["cost_raw"] == 0.0
    assert t["pit"][10]["cost_raw"] == pytest.approx(-0.04)


def test_abs_terms_null_frame_moves_nothing():
    t = V3.abs_terms([], HIT_PA, PIT_IP, C_INN)
    assert all(r["runs"] == 0.0 for r in t["bat"].values())
    assert all(r["runs"] == 0.0 for r in t["pit"].values())


def test_abs_terms_refuse_a_winning_catcher_without_innings_and_drop_gaps():
    with pytest.raises(V3.EwarV3Refusal):
        V3.abs_terms([_ch("catcher", "fielding", 3, 10, 1, 0.3)], HIT_PA, PIT_IP, C_INN)
    t = V3.abs_terms([_ch("catcher", "fielding", 1, 99, 1, 0.3)], HIT_PA, PIT_IP, C_INN)
    assert t["receipt"]["gap_charge"] == 1 and abs(sum(r["charge"] for r in t["pit"].values())) < 1e-12
    with pytest.raises(V3.EwarV3Refusal):
        V3.abs_terms([_ch("catcher", "fielding", 1, 10, 1, -0.1)], HIT_PA, PIT_IP, C_INN)


def test_recentre_sums_to_zero_and_keeps_a_zero_side():
    d = V3.recentre({1: 3.0, 2: -1.0}, {1: 10.0, 2: 30.0, 3: 0.0})
    assert sum(d.values()) == pytest.approx(0.0) and d[3] == 0.0
    assert V3.recentre({}, {1: 0.0}) == {1: 0.0}


# --------------------------------------------------------------------------- #
# the assembler on fixtures
# --------------------------------------------------------------------------- #
H_FIELDS = ["war", "plateAppearances"]
P_FIELDS = ["war", "outs"]


def _season(hit: dict, pit: dict) -> dict:
    return {"hitting": {"status": "frozen", "fields": H_FIELDS, "rows": {str(k): v for k, v in hit.items()}},
            "pitching": {"status": "frozen", "fields": P_FIELDS, "rows": {str(k): v for k, v in pit.items()}}}


VINTAGE = {"vintage_id": "fixture-vintage", "seasons": {
    "2024": _season({1: [3.0, 500], 2: [1.0, 400], 3: [2.0, 300]}, {10: [4.0, 540], 11: [0.5, 180]}),
    "2026": _season({1: [3.0, 500], 2: [1.0, 400], 3: [2.0, 300], 4: [0.0, 0]},
                    {10: [4.0, 540], 11: [0.5, 180], 12: [0.1, 0]}),
}}


class FixtureInputs(B.Inputs):
    def __init__(self, rpw_status="PRIMARY PASS, GUARD PENDING", abs_seasons=(2026,)):
        self.rpw_status = rpw_status
        self.abs_seasons = abs_seasons

    def vintage(self):
        return VINTAGE

    def challenges(self, season):
        return FRAME if season in self.abs_seasons else []

    def catcher_innings(self, season):
        return C_INN

    def r2(self):
        return ({2024: {10: 0.3, 11: -0.3}, 2026: {10: -0.2, 11: 0.2}},
                {"fwar_vintage_id": "fixture-vintage", "zero_sum": {}, "sha256": None})

    def rpw_fit(self):
        return {"verdict": {"status": self.rpw_status, "candidate": "c",
                            "rpw_by_season": {"2024": 10.5, "2026": 10.5}}}


@pytest.fixture
def built(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)
    return B.build(FixtureInputs(), log=lambda *a: None)


def test_build_carries_abs_from_2026_and_r2_in_realized_only(built):
    p = built
    assert p["meta"]["admitted_by_look"] == []
    assert set(p["meta"]["parts"]) == {"eabs", "r2"}
    b24 = p["players"]["10"]["2024"]
    assert "dh" in b24 and not b24["dh"] and b24["dr"]["pit"] == pytest.approx(0.3)
    b26 = p["players"]["1"]["2026"]
    w = b26["parts"]["abs"]["bat"]["wins"]
    assert b26["dh"]["bat"] == pytest.approx(w) and b26["dr"]["bat"] == pytest.approx(w)
    assert w == pytest.approx(b26["parts"]["abs"]["bat"]["runs"] / 10.5, abs=1e-6)
    p26 = p["players"]["10"]["2026"]
    assert p26["dr"]["pit"] == pytest.approx(p26["dh"]["pit"] - 0.2)


def test_build_departures_sum_to_zero_per_season_and_side(built):
    for s, c in built["checks"].items():
        for k, v in c["sum_departure_wins"].items():
            assert abs(v) < 1e-9, (s, k, v)


def test_rpw_guard_is_an_identity_and_falls_back_when_it_is_not(built, monkeypatch):
    g = built["meta"]["rpw"]
    assert g["form"] == "c" and g["guard"]["status"] == "NON-INFERIOR" and g["guard"]["departure_rows"] == 0
    assert "no WAR sum was related to a club outcome" in g["guard"]["how"]
    # a departure in a guard season breaks the identity: the incumbent stands
    import league_constants as LCM
    monkeypatch.setattr(LCM, "league_totals", lambda s: {"rpw": 9.9})
    p = B.build(FixtureInputs(abs_seasons=(2024, 2026)), log=lambda *a: None)
    # 2024 is below ABS_FIRST_SEASON, so no ABS term exists there and the guard still holds
    assert p["meta"]["rpw"]["form"] == "c"
    monkeypatch.setattr(V3, "ABS_FIRST_SEASON", 2024)
    p1 = B.build(FixtureInputs(abs_seasons=(2024, 2026)), log=lambda *a: None)
    assert p1["meta"]["rpw"]["form"] == "incumbent"
    assert p1["meta"]["rpw"]["guard"]["status"] == "NOT AN IDENTITY" and p1["checks"]["2026"]["rpw"] == 9.9
    monkeypatch.setattr(V3, "ABS_FIRST_SEASON", 2026)
    p2 = B.build(FixtureInputs(rpw_status="INCUMBENT HOLDS"), log=lambda *a: None)
    assert p2["meta"]["rpw"]["form"] == "incumbent" and p2["checks"]["2026"]["rpw"] == 9.9


def test_build_refuses_a_preview_on_another_vintage(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)

    class Other(FixtureInputs):
        def r2(self):
            return {}, {"fwar_vintage_id": "another"}
    with pytest.raises(V3.EwarV3Refusal):
        B.build(Other(), log=lambda *a: None)


# --------------------------------------------------------------------------- #
# the provider contract
# --------------------------------------------------------------------------- #
def test_provider_is_registered_never_default_and_display_follows_the_flag():
    assert "ewar_v3" in war_source.PROVIDERS
    assert war_source.DEFAULT_PROVIDER == "fwar"
    assert war_source.DISPLAY_PROVIDER == ("ewar_v3" if war_source.EWAR_V3_LIVE else "ewar_v2")


def test_ewar_v3_is_refused_on_the_arb_spine_door():
    with pytest.raises(ValueError):
        war_source.refuse_on_door("ewar_v3", "arb_spine")
    war_source.refuse_on_door("ewar_v2", "arb_spine")
    with pytest.raises(ValueError):
        war_source._ewar_v3_frame(None, "bat", door="arb_spine")


def test_row_on_provider_moves_only_vintage_seasons(built):
    V3.set_payload(built)
    try:
        row = {"seasons": {"2024": 2.0, "2025": 1.0, "2026": 3.0}, "career_war": 6.0, "source": "fwar",
               "seasons_ewar_v2": {"2024": 1.9, "2025": 1.1, "2026": 2.8},
               "fwar_coverage": {"mlbam": 1, "fallback_pre_years": [], "fallback_post_years": [2025]}}
        out = war_source.row_on_provider(row, "ewar_v3")
        d = built["players"]["1"]["2026"]["dh"]["bat"]
        assert out["seasons"]["2026"] == round(3.0 + d, 2)
        assert out["seasons"]["2024"] == 2.0 and out["seasons"]["2025"] == 1.0
        assert out["source"] == "ewar_v3" and out["seasons_fwar"] == row["seasons"]
        assert "seasons_ewar_realized" in out
        legacy = {"seasons": {"2024": 1.0}, "source": "ewar_v2"}
        assert war_source.row_on_provider(legacy, "ewar_v3") == legacy
        deps = V3.departures(series="realized")
        assert deps[(10, 2024)]["pit"] == pytest.approx(0.3)
    finally:
        V3.set_payload(None)


# --------------------------------------------------------------------------- #
# the served artifact (present once the flip has run)
# --------------------------------------------------------------------------- #
def _served():
    if not V3.OUT.exists():
        pytest.skip("data/ewar_v3.json is written at the flip (EWAR_V3_LIVE)")
    return json.loads(V3.OUT.read_text(encoding="utf-8"))


def test_served_artifact_identities():
    p = _served()
    assert p["model"] == "ewar_v3" and p["meta"]["admitted_by_look"] == []
    import fwar_vintage
    assert p["fwar_vintage_id"] == fwar_vintage.load().get("vintage_id")
    for s, c in p["checks"].items():
        for k in ("dh_bat", "dh_pit", "dr_bat"):
            assert abs(c["sum_departure_wins"][k]) < 1e-6, (s, k)
        assert abs(c["sum_departure_wins"]["dr_pit"]) <= c["r2_rounding_bound"] + 1e-6
        if int(s) < V3.ABS_FIRST_SEASON:
            assert c["sum_abs_runs"] == {"bat": 0.0, "pit": 0.0}
    r = p["checks"]["2026"]["abs_receipt"]
    assert r["sum_move_raw"] == pytest.approx(-r["sum_charge_raw"])
    assert p["meta"]["rpw"]["guard"]["status"] in ("NON-INFERIOR", "NOT COMPUTED", "NOT AN IDENTITY")


def test_served_artifact_departures_are_listed_parts_only():
    p = _served()
    for mid, by in p["players"].items():
        for s, b in by.items():
            parts = b.get("parts") or {}
            for side, d in (b.get("dh") or {}).items():
                w = ((parts.get("abs") or {}).get(side) or {}).get("wins", 0.0)
                assert d == pytest.approx(w, abs=2e-6), (mid, s, side)
            for side, d in (b.get("dr") or {}).items():
                w = ((parts.get("abs") or {}).get(side) or {}).get("wins", 0.0)
                r2 = parts.get("r2", 0.0) if side == "pit" else 0.0
                assert d == pytest.approx(w + r2, abs=2e-6), (mid, s, side)

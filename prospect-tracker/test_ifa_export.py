# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Tests for the International Amateurs export builder (ifa_export.py).

Exercises the pure `build_ifa_export` against a small fixture of Spotrac-shaped
signing rows + a fake tracked-player map — no network, no DB."""

from __future__ import annotations

from datetime import date

import ifa_export
from ifa_export import build_ifa_export, _bonus_bucket


def _today():
    return date(2026, 6, 1)


# Fixture: a couple of years, a tracked + untracked signing, a stray old year.
SIGNINGS = [
    {"year": 2026, "player_name": "Luis Star", "player_key": "luis_star",
     "position": "SS", "org": "SFG", "country": "Venezuela",
     "bonus_usd": 5_000_000, "pool_pct": 84.2},
    {"year": 2026, "player_name": "Org Filler", "player_key": "org_filler",
     "position": "RHP", "org": "SFG", "country": "Dominican Republic",
     "bonus_usd": 25_000, "pool_pct": 0.4},
    {"year": 2026, "player_name": "Mid Guy", "player_key": "mid_guy",
     "position": "OF", "org": "BAL", "country": "Dominican Republic",
     "bonus_usd": 750_000, "pool_pct": 12.0},
    {"year": 2025, "player_name": "Older Sign", "player_key": "older_sign",
     "position": "C", "org": "BAL", "country": "Cuba",
     "bonus_usd": 1_500_000, "pool_pct": 30.0},
    # Stray pre-2021 row Spotrac sometimes tags — must be excluded.
    {"year": 2019, "player_name": "Ghost", "player_key": "ghost",
     "position": "SS", "org": "NYY", "country": "Mexico",
     "bonus_usd": 100_000, "pool_pct": 2.0},
]

# Tracked map — only luis_star is in our MiLB DB, and he was traded SFG→SDP.
PLAYERS = {
    "luis_star": {"player_key": "luis_star", "fv_close_raw": 55.0,
                  "fv_close_plus": False, "fv_open": 40.0,
                  "overall_rank": 14, "mlbam_id": 815908, "org": "SDP",
                  "position": "SS", "birth_date": "2009-09-01",
                  "tools": {"composite_overall": 58.3},
                  "points": [{"tools_consensus": {"hit": 55, "pwr": 50, "speed": 60}}]},
}


def _build():
    return build_ifa_export(SIGNINGS, PLAYERS, today=_today())


def test_classes_grouped_and_year_filtered():
    out = _build()
    years = [c["year"] for c in out["classes"]]
    assert years == [2026, 2025], "only 2021..today, newest-first; 2019 dropped"


def test_signing_team_is_spotrac_org_not_current():
    cls = _build()["classes"][0]  # 2026
    luis = next(s for s in cls["signings"] if s["player_key"] == "luis_star")
    assert luis["org"] == "SFG"          # SIGNING team
    assert luis["current_org"] == "SDP"  # traded since — shown as a note only
    assert luis["is_tracked"] is True
    assert luis["fv"] == 55.0 and luis["fv_label"] == "55"
    assert luis["overall_rank"] == 14


def test_signing_vs_current_enrichment():
    luis = next(s for s in _build()["classes"][0]["signings"]
                if s["player_key"] == "luis_star")
    # FV at signing (fv_open) distinct from current FV (fv_close).
    assert luis["fv_signing"] == 40.0 and luis["fv"] == 55.0
    assert luis["fv_signing_label"] == "40"
    # Tool composite: signing = mean(55,50,60)=55; current = round(58.3)=58.
    assert luis["tool_signing"] == 55 and luis["tool_current"] == 58
    # Age at Jan-15-2026 signing day from a 2009-09-01 birthdate (~16.4).
    assert 16.0 <= luis["age_at_signing"] <= 16.7


def test_untracked_has_no_signing_fields():
    filler = next(s for s in _build()["classes"][0]["signings"]
                  if s["player_key"] == "org_filler")
    assert filler["fv_signing"] is None and filler["age_at_signing"] is None
    assert filler["tool_signing"] is None and filler["tool_current"] is None


def test_untracked_signing_has_no_enrichment():
    cls = _build()["classes"][0]
    filler = next(s for s in cls["signings"] if s["player_key"] == "org_filler")
    assert filler["is_tracked"] is False
    assert filler["fv"] is None and filler["fv_label"] is None


def test_signings_sorted_by_bonus_desc():
    cls = _build()["classes"][0]
    bonuses = [s["bonus_usd"] for s in cls["signings"]]
    assert bonuses == sorted(bonuses, reverse=True)


def test_org_leaderboard_totals_and_order():
    cls = _build()["classes"][0]  # 2026: SFG 5.025M (2), BAL 0.75M (1)
    lead = cls["org_spending"]
    assert lead[0]["org"] == "SFG" and lead[0]["total_usd"] == 5_025_000
    assert lead[0]["signings"] == 2 and lead[0]["top_player"] == "Luis Star"
    assert lead[1]["org"] == "BAL" and lead[1]["total_usd"] == 750_000
    # pool% summed per org
    assert round(lead[0]["pool_pct_sum"], 1) == 84.6


def test_trends_distribution_and_countries():
    t = _build()["classes"][0]["trends"]
    assert t["n_signings"] == 3 and t["total_usd"] == 5_775_000
    d = t["bonus_distribution"]
    assert d["≥$3M"] == 1 and d["$500k-1M"] == 1 and d["<$100k"] == 1
    # Top markets aggregate by $ then count.
    top = {c["country"]: c for c in t["top_countries"]}
    assert top["Venezuela"]["n"] == 1 and top["Dominican Republic"]["n"] == 2
    assert t["median_bonus"] == 750_000


def test_bonus_bucket_edges():
    assert _bonus_bucket(3_000_000) == "≥$3M"
    assert _bonus_bucket(2_999_999) == "$1-3M"
    assert _bonus_bucket(99_999) == "<$100k"
    assert _bonus_bucket(None) is None


def test_empty_signings_safe():
    out = build_ifa_export([], {}, today=_today())
    assert out == {"classes": []}


def test_lookup_tracked_generational_suffix_alias():
    # The signing tracker keeps "Jr."; StatsAPI-keyed prospects drop it. An
    # exact miss must fall back to the suffix-stripped key, but never invent a
    # match where the base key does not exist.
    pbk = {"angel_nunez": {"player_key": "angel_nunez", "fv_close_raw": 40.0}}
    assert ifa_export._lookup_tracked(pbk, "angel_nunez_jr") is pbk["angel_nunez"]
    assert ifa_export._lookup_tracked(pbk, "angel_nunez") is pbk["angel_nunez"]
    assert ifa_export._lookup_tracked(pbk, "carlos_jr") is None
    assert ifa_export._lookup_tracked(pbk, None) is None


def test_generational_suffix_signing_is_enriched():
    # Regression: Angel Nunez Jr (IFA key `angel_nunez_jr`) is the graded
    # prospect `angel_nunez` - the alias must make him tracked + carry his FV.
    signings = [{"year": 2026, "player_name": "Angel Nunez Jr.",
                 "player_key": "angel_nunez_jr", "position": "CF", "org": "CIN",
                 "country": "Dominican Republic", "bonus_usd": 600_000, "pool_pct": 10.0}]
    pbk = {"angel_nunez": {"player_key": "angel_nunez", "fv_close_raw": 40.0,
                           "fv_close_plus": True, "overall_rank": 465,
                           "mlbam_id": 836585, "org": "CIN", "position": "CF"}}
    s = build_ifa_export(signings, pbk, today=_today())["classes"][0]["signings"][0]
    assert s["is_tracked"] is True
    assert s["fv"] == 40.0 and s["fv_label"] == "40+"
    assert s["overall_rank"] == 465 and s["mlbam_id"] == 836585


def test_efv_floor_flag_rides_through():
    # Census M03-12: an eFV at the outcome map's floor (xfv_grade_is_floor) is
    # the bottom of the scale, not a resolved level. The row must say so, or
    # the page reads "35 -> 20" as a collapse and divides $/FV by 20.
    xfv = {"luis_star": {"xfv_grade": 20.0, "xfv_grade_is_floor": True}}
    out = build_ifa_export(SIGNINGS, PLAYERS, today=_today(), xfv_by_key=xfv)
    luis = next(s for s in out["classes"][0]["signings"] if s["player_key"] == "luis_star")
    assert luis["fv_basis"] == "xfv" and luis["fv"] == 20.0
    assert luis["fv_is_floor"] is True
    big = next(b for b in out["classes"][0]["trends"]["biggest_signings"]
               if b["player_key"] == "luis_star")
    assert big["fv_is_floor"] is True
    # A resolved eFV grade, and every consensus or untracked row, is not a floor.
    xfv2 = {"luis_star": {"xfv_grade": 20.0, "xfv_grade_is_floor": False}}
    out2 = build_ifa_export(SIGNINGS, PLAYERS, today=_today(), xfv_by_key=xfv2)
    assert all(s["fv_is_floor"] is False for c in out2["classes"] for s in c["signings"])
    out3 = _build()
    assert all(s["fv_is_floor"] is False for c in out3["classes"] for s in c["signings"])


def test_served_artifact_marks_every_floor_row():
    import json
    from pathlib import Path
    import pytest
    d = Path(__file__).parent / "data"
    try:
        ifa = json.loads((d / "ifa_timeseries.json").read_text(encoding="utf-8"))
        xfv = json.loads((d / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    except (OSError, ValueError, KeyError):
        pytest.skip("ifa_timeseries.json / xfv.json not built")
    bad = []
    for c in ifa.get("classes") or []:
        for s in c.get("signings") or []:
            if s.get("fv_basis") != "xfv":
                assert not s.get("fv_is_floor"), s["player_key"]
                continue
            tp_key = s["player_key"]
            rec = xfv.get(tp_key) or xfv.get(ifa_export._GEN_SUFFIX.sub("", tp_key)) or {}
            if bool(rec.get("xfv_grade_is_floor") is True) != bool(s.get("fv_is_floor")):
                bad.append((c["year"], tp_key))
    assert not bad, bad[:10]

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for fantasy_scoring.py — Ottoneu points + roto valuation.

Point values are pinned to the cross-checked Ottoneu tables (single = +4.6,
HR = +14.0 net; FGP pitcher IP = +7.4, SABR IP = +5.0; SABR ignores hits)."""
from __future__ import annotations

import fantasy_scoring as fs


def test_hitter_points_identical_across_systems():
    # A single: AB=1, H=1 -> -1.0 + 5.6 = 4.6 (same in FGP and SABR).
    assert fs.score_points({"ab": 1, "h": 1}, "fgp", "hit") == 4.6
    assert fs.score_points({"ab": 1, "h": 1}, "sabr", "hit") == 4.6
    # HR nets 14.0; 2B nets 7.5; 3B nets 10.3 (base H + incremental bonus - AB).
    assert fs.score_points({"ab": 1, "h": 1, "hr": 1}, "fgp", "hit") == 14.0
    assert fs.score_points({"ab": 1, "h": 1, "double": 1}, "fgp", "hit") == 7.5
    assert fs.score_points({"ab": 1, "h": 1, "triple": 1}, "fgp", "hit") == 10.3
    # BB/HBP carry no AB; SB/CS as tabled.
    assert fs.score_points({"bb": 1}, "fgp", "hit") == 3.0
    assert fs.score_points({"hbp": 1}, "fgp", "hit") == 3.0
    assert fs.score_points({"sb": 1}, "fgp", "hit") == 1.9
    assert fs.score_points({"cs": 1}, "fgp", "hit") == -2.8
    # An out (AB, no hit) is -1.0.
    assert fs.score_points({"ab": 1}, "fgp", "hit") == -1.0


def test_pitcher_points_fgp_vs_sabr():
    assert fs.score_points({"ip": 1, "k": 1}, "fgp", "pit") == 9.4    # 7.4 + 2.0
    assert fs.score_points({"ip": 1, "k": 1}, "sabr", "pit") == 7.0   # 5.0 + 2.0
    # FGP penalizes hits (-2.6); SABR (FIP-based) ignores them entirely.
    assert fs.score_points({"ip": 1, "h": 3}, "fgp", "pit") == round(7.4 - 3 * 2.6, 2)
    assert fs.score_points({"ip": 1, "h": 3}, "sabr", "pit") == 5.0
    # HR: -12.3 (FGP) vs -13.0 (SABR).
    assert fs.score_points({"ip": 1, "hr": 1}, "fgp", "pit") == round(7.4 - 12.3, 2)
    assert fs.score_points({"ip": 1, "hr": 1}, "sabr", "pit") == round(5.0 - 13.0, 2)
    assert fs.score_points({"sv": 1}, "fgp", "pit") == 5.0
    assert fs.score_points({"hld": 1}, "fgp", "pit") == 4.0


def test_ip_conversions():
    assert abs(fs.ip_from_outs(19) - (19 / 3)) < 1e-9          # 6⅓
    assert abs(fs.ip_from_decimal_thirds(6.1) - (6 + 1 / 3)) < 1e-9
    assert abs(fs.ip_from_decimal_thirds(6.2) - (6 + 2 / 3)) < 1e-9
    assert fs.ip_from_decimal_thirds(6.0) == 6.0


def test_missing_keys_score_zero():
    assert fs.score_points({}, "fgp", "hit") == 0.0
    assert fs.score_points({}, "sabr", "pit") == 0.0


def test_roto_hitter_ordering():
    pool = [
        {"id": "star",  "pa": 600, "avg": .320, "obp": .400, "slg": .600, "hr": 40, "rbi": 110, "sb": 20, "r": 110},
        {"id": "scrub", "pa": 600, "avg": .230, "obp": .290, "slg": .350, "hr": 8,  "rbi": 40,  "sb": 2,  "r": 45},
    ]
    v5 = fs.roto_valuations(pool, "5x5", "hit")
    v4 = fs.roto_valuations(pool, "4x4", "hit")
    assert v5["star"]["value"] > v5["scrub"]["value"]
    assert v4["star"]["value"] > v4["scrub"]["value"]
    # z-scores of a 2-player pool are symmetric around 0.
    assert abs(v5["star"]["value"] + v5["scrub"]["value"]) < 1e-6


def test_roto_pitcher_era_inversion():
    # Lower ERA/WHIP/HR9 must score HIGHER (sign inversion for lower-is-better).
    pool = [
        {"id": "ace", "ip": 200, "era": 2.50, "whip": 1.00, "hr9": 0.7, "k": 250, "w": 18, "sv": 0},
        {"id": "bad", "ip": 200, "era": 5.50, "whip": 1.55, "hr9": 1.8, "k": 120, "w": 6,  "sv": 0},
    ]
    assert fs.roto_valuations(pool, "5x5", "pit")["ace"]["value"] > fs.roto_valuations(pool, "5x5", "pit")["bad"]["value"]
    assert fs.roto_valuations(pool, "4x4", "pit")["ace"]["value"] > fs.roto_valuations(pool, "4x4", "pit")["bad"]["value"]


def test_weight_tables_serializable():
    t = fs.points_weight_tables()
    assert t["hitter"]["hr"] == 9.4
    assert t["pitcher"]["fgp"]["ip"] == 7.4
    assert t["pitcher"]["sabr"]["ip"] == 5.0
    assert "h" not in t["pitcher"]["sabr"]        # SABR has no hit term
    assert any(s["id"] == "fgp" and s.get("default") for s in fs.SCORING_CATALOG)


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} fantasy_scoring tests PASS")

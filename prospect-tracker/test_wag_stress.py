# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

from storage import _grad_wag


def _hitter_payload(*, war, fv, pa=600, age=24, transactions=None, level="MLB"):
    return {
        "career_war": {"career_war": war},
        "fv_close_raw": fv,
        "position": "C",
        "age": age,
        "current_level": level,
        "career_stats": [{"season": 2026, "level": "MLB", "pa": pa}],
        "transactions": transactions or [],
    }


def _pitcher_payload(*, war, fv, ip=175, pos="SP", age=24, transactions=None, level="MLB"):
    return {
        "career_war": {"career_war": war},
        "fv_close_raw": fv,
        "position": pos,
        "age": age,
        "current_level": level,
        "career_stats": [{"season": 2026, "level": "MLB", "ip": ip}],
        "transactions": transactions or [],
    }


def test_wag_positive_surprise_rewards_current_mlb_production_not_just_low_fv_math():
    # Connor Wong-style shape: low FV and roughly 1 WAR in a full hitter
    # season is a positive surprise, but it should not sort above stronger
    # current MLB outcomes like Bradish / Davis Martin-style pitcher seasons.
    wong_like = _hitter_payload(war=1.0, fv=40, pa=600)
    bradish_like = _pitcher_payload(war=5.0, fv=45, ip=175, pos="SP")
    davis_martin_like = _pitcher_payload(war=2.0, fv=40, ip=140, pos="SP")

    assert _grad_wag(bradish_like) > _grad_wag(wong_like)
    assert _grad_wag(davis_martin_like) > _grad_wag(wong_like)


def test_wag_dampens_dfa_circus_older_current_minors_profile():
    clean = _hitter_payload(war=3.0, fv=40, pa=600, age=24, level="MLB")
    churn = _hitter_payload(
        war=3.0,
        fv=40,
        pa=600,
        age=26.5,
        level="AAA",
        transactions=[
            {"kind": "dfa", "date": "2025-02-01"},
            {"kind": "outrighted", "date": "2025-02-08"},
            {"kind": "dfa", "date": "2026-03-20"},
        ],
    )

    assert _grad_wag(churn) < _grad_wag(clean) * 0.4

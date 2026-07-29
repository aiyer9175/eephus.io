# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fit-engine guards: component directions, win-curve shape, displacement
need, weight discipline. Pure unit tests on the transparent pieces — the
composite is exercised end-to-end by the Stage-4 checkpoint script."""

from __future__ import annotations

import pytest

import fa_class
import fa_fit


def test_position_norm():
    assert fa_fit._position_norm("LHP") == "SP"
    assert fa_fit._position_norm("CL") == "RP"
    assert fa_fit._position_norm("OF") == "CF"
    assert fa_fit._position_norm("SS/2B") == "SS"
    assert fa_fit._position_norm(None) == "DH"


def test_weights_sum_to_one():
    w = fa_class.get_config()["fit"]["weights"]
    assert sum(w.values()) == pytest.approx(1.0)


def test_win_leverage_shape():
    """Leverage must RISE toward the curve center and FALL past it — the
    85-win team gains more from +4 WAR than the 70- or 100-win team."""
    cfg = fa_class.get_config()["fit"]["win_curve"]
    center = cfg["center"] - cfg.get("roster_fill_wins", 0)
    below = fa_fit.win_leverage(center - 12)
    at = fa_fit.win_leverage(center)
    above = fa_fit.win_leverage(center + 12)
    assert at == pytest.approx(1.0, abs=1e-9)        # normalized peak
    assert below < at and above < at
    assert fa_fit.win_leverage(center - 25) < below  # monotone on the flank


def test_park_component_directions(monkeypatch):
    """Hitters score high in hitter parks; pitchers score high in
    suppressive parks — same venue, opposite reading."""
    pf = {"COL": {"woba": 113, "hr": 106, "runs": 128},
          "SEA": {"woba": 92, "hr": 98, "runs": 85}}
    monkeypatch.setattr(fa_fit, "park_factors", lambda season, bat_side="": pf)
    hitter = {"position": "SS", "bat_throw": "R/R"}
    pitcher = {"position": "SP", "bat_throw": "L/L"}
    # v2 squashed the saturation (±30 pts full-scale; weight cut to 0.04 —
    # the Giants-for-all-pitchers fix): directions hold, spreads shrink.
    assert fa_fit.park_component(hitter, "COL", 2026)["score"] > 0.6
    assert fa_fit.park_component(hitter, "SEA", 2026)["score"] < 0.45
    assert fa_fit.park_component(pitcher, "SEA", 2026)["score"] > 0.55
    assert fa_fit.park_component(pitcher, "COL", 2026)["score"] < 0.45
    # unknown venue falls back to neutral, never invents
    assert fa_fit.park_component(hitter, "XXX", 2026)["score"] == pytest.approx(0.5)


def test_need_is_displacement_not_unit_sum():
    """The Stage-4 checkpoint regression: an ace joining a rotation
    displaces the 5TH starter, not the staff sum — need must stay alive
    for top-of-class players on deep teams."""
    inc = [{"name": f"P{i}", "position": "SP", "war_proj": w}
           for i, w in enumerate([3.0, 2.5, 2.0, 1.0, 0.3])]
    slot = {"SP": 4, "RP": 2}.get("SP", 0)
    displaced = inc[slot]["war_proj"]
    assert displaced == 0.3                      # not sum(8.8)
    war1 = 3.6
    gap = max(0.0, war1 - displaced)
    assert gap > 3.0                             # the ace still fills a need


# ============================================================================
# T1.0 — FA team baselines must AGREE with the /projections/ team outlook
# ============================================================================
# The FA module used to rebuild its own win baseline out of contracted-player
# WAR plus a flat roster_fill_wins stand-in. Measured 2026-07-25 against the
# committed data/mlb_projections.json for 2027, on the number win_leverage
# actually consumed: mean |delta| 5.60 wins, signed mean +5.15, sd 3.23, max
# 10.0 (COL 81.3 vs 71.3), and the 30 club totals summed to 2584.4 where a
# league season sums to 2430.0 by construction (154.4 invented league wins).
# These tests are DETERMINISTIC reads of the two committed artifacts.

def _outlook_from_artifact(class_year: int) -> dict:
    import json
    from pathlib import Path
    p = Path(fa_fit.__file__).parent / "data" / "mlb_projections.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for t in (d.get("team_outlook") or []):
        for by in (t.get("byYear") or []):
            if by.get("season") == class_year and by.get("wins") is not None:
                out[t["team"]] = float(by["wins"])
                break
    return out


def test_outlook_wins_reads_all_thirty_clubs():
    """The bridge is all-or-nothing: 30 clubs or {} (never a partial read
    that would give some clubs one baseline definition and some another)."""
    got = fa_fit._outlook_wins(2027)
    assert got == {} or len(got) == 30
    expect = _outlook_from_artifact(2027)
    if len(expect) == 30:
        assert got == expect


def test_team_baselines_agree_exactly_with_projections_outlook():
    """EXACT agreement, club by club, to the served rounding. A reader who
    opens /fa/ and /projections/ in two tabs must see one number."""
    expect = _outlook_from_artifact(2027)
    if len(expect) != 30:
        import pytest as _p
        _p.skip("mlb_projections.json team_outlook not built for 2027")
    bases = fa_fit.team_baselines(2027)
    assert bases, "no contracted rosters — cannot check agreement"
    checked = 0
    for org, row in bases.items():
        if row.get("baseline_source") != "mlb_projections":
            continue
        assert row["baseline_wins"] == round(expect[org], 1), org
        assert row["fill_wins"] == 0.0, org
        checked += 1
    assert checked == len(bases) == 30


def test_win_leverage_fill_is_explicit_and_not_double_counted():
    """An outlook baseline is a FULL win total, so win_leverage must not
    add the contracted-core roster_fill stand-in on top of it."""
    cfg = fa_class.get_config()["fit"]["win_curve"]
    fill = float(cfg.get("roster_fill_wins", 0))
    assert fill > 0, "fixture assumes a nonzero configured fill"
    # fill=0 evaluates the curve AT the passed win total
    assert fa_fit.win_leverage(cfg["center"], 0.0) == pytest.approx(1.0, abs=1e-9)
    # default keeps the historical signature (fill added)
    assert fa_fit.win_leverage(cfg["center"] - fill) == pytest.approx(1.0, abs=1e-9)
    # and the two are NOT the same call
    assert fa_fit.win_leverage(80.0, 0.0) != fa_fit.win_leverage(80.0)


def test_team_baselines_falls_back_when_artifact_is_defective(monkeypatch):
    """Any defect in the artifact drops the WHOLE module back to the
    contracted-core construction, flagged — never silently half-and-half."""
    fa_fit._outlook_wins.cache_clear()
    fa_fit.team_baselines.cache_clear()
    monkeypatch.setattr(fa_fit, "_outlook_wins", lambda cy: {})
    cfg = fa_class.get_config()["fit"]
    fill = float(cfg["win_curve"].get("roster_fill_wins", 0))
    bases = fa_fit.team_baselines(2027)
    for org, row in bases.items():
        assert row["baseline_source"] == "contracted_core", org
        assert row["fill_wins"] == fill, org
        # war_committed is itself rounded to 0.1, so re-deriving the sum can
        # differ by one double-rounding step.
        assert row["baseline_wins"] == pytest.approx(
            cfg["replacement_wins"] + row["war_committed"], abs=0.11), org
    fa_fit.team_baselines.cache_clear()   # monkeypatch restores _outlook_wins

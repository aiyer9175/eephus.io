# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the Statcast+ composite + its pipeline integrations.

Covers:
  - build_pool / compute_statcast_plus core math (hitter + pitcher,
    pool centering, missing-data handling)
  - estimate_eta honoring the new statcast_plus modifier
  - _compute_breakout_flag accepting statcast_plus as a perf gate
"""

from datetime import date, timedelta

import pytest

from statcast_plus import build_pool, compute_statcast_plus


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _hit(player_key, ev, hh, brl, z_con, whiff, chase):
    """Build a hitter mini-payload that build_pool / compute_statcast_plus
    can consume directly. The chase rate serializes as o_swing_pct -- the
    ONLY key production ZoneMetricRow rows carry (chase_pct never existed on
    them, which silently killed the component pre-2026-07-07); fixtures must
    exercise that production path, not the defensive chase_pct fallback."""
    return {
        "player_key": player_key,
        "statline": {"is_pitcher": False, "level": "AA"},
        "statcast_metrics": {
            "contact_quality": {
                "avg_ev": ev,
                "hard_hit_pct": hh,
                "barrel_pct": brl,
            },
        },
        "zone_metrics": {
            "z_contact_pct": z_con,
            "whiff_pct": whiff,
            "o_swing_pct": chase,
        },
    }


def _pit(player_key, velo, whiff, chase, hh_allowed, brl_allowed):
    return {
        "player_key": player_key,
        "statline": {"is_pitcher": True, "level": "AA"},
        "statcast_metrics": {
            "contact_quality": {
                "hard_hit_pct": hh_allowed,
                "barrel_pct": brl_allowed,
            },
            "pitch_movement": {
                "pitch_summary": [{"pitch_type": "FF", "avg_velo": velo}],
            },
        },
        "zone_metrics": {
            "whiff_pct": whiff,
            "o_swing_pct": chase,
        },
    }


# ----------------------------------------------------------------------
# Core composite tests
# ----------------------------------------------------------------------

class TestStatcastPlusCore:
    def test_pool_average_centers_at_100(self):
        pool_players = [
            _hit(f"h{i}", ev=88.0, hh=35.0, brl=6.0, z_con=80.0, whiff=24.0, chase=28.0)
            for i in range(10)
        ]
        pool = build_pool(pool_players)
        avg = compute_statcast_plus(pool_players[0], pool)
        # All players identical → every z=0 → exactly 100
        assert avg == 100

    def test_elite_hitter_scores_above_pool(self):
        pool_players = [
            _hit(f"avg{i}", ev=88.0, hh=35.0, brl=6.0, z_con=80.0, whiff=24.0, chase=28.0)
            for i in range(10)
        ]
        # Spread the pool so z-scores resolve.
        pool_players[0] = _hit("low", ev=84.0, hh=30.0, brl=3.0, z_con=75.0, whiff=28.0, chase=32.0)
        pool_players[1] = _hit("high", ev=92.0, hh=42.0, brl=11.0, z_con=86.0, whiff=20.0, chase=24.0)
        pool = build_pool(pool_players)

        elite = _hit("e", ev=95.0, hh=48.0, brl=14.0, z_con=90.0, whiff=18.0, chase=22.0)
        weak  = _hit("w", ev=82.0, hh=28.0, brl=2.0,  z_con=73.0, whiff=30.0, chase=34.0)

        sp_elite = compute_statcast_plus(elite, pool)
        sp_weak  = compute_statcast_plus(weak, pool)

        assert sp_elite is not None and sp_weak is not None
        assert sp_elite > 120, f"Elite should clear +1σ; got {sp_elite}"
        assert sp_weak  < 85,  f"Weak should sink below pool; got {sp_weak}"
        assert sp_elite > sp_weak

    def test_pitcher_uses_pitcher_pool(self):
        # Hitter rows in the pool should NOT pollute pitcher stats.
        pool_players = (
            [_hit(f"h{i}", ev=88, hh=35, brl=6, z_con=80, whiff=24, chase=28) for i in range(5)]
            + [_pit(f"p{i}", velo=94.0, whiff=28.0, chase=30.0, hh_allowed=33.0, brl_allowed=5.0)
               for i in range(5)]
        )
        # Add variance to the pitcher pool so z-scores resolve.
        pool_players[5] = _pit("p_low", velo=90.0, whiff=22.0, chase=24.0, hh_allowed=40.0, brl_allowed=10.0)
        pool_players[6] = _pit("p_high", velo=98.0, whiff=35.0, chase=36.0, hh_allowed=26.0, brl_allowed=2.0)
        pool = build_pool(pool_players)

        elite_pit = _pit("e_pit", velo=99.0, whiff=38.0, chase=38.0,
                         hh_allowed=24.0, brl_allowed=1.5)
        sp = compute_statcast_plus(elite_pit, pool)
        # v-audit finding 6: SC+ harmonized to 10 pts/σ (was 15), so an elite arm
        # reads clearly above the +1σ top-quintile mark (110) rather than >120.
        assert sp is not None and sp > 113

    def test_missing_data_returns_none(self):
        pool_players = [
            _hit(f"h{i}", ev=88, hh=35, brl=6, z_con=80, whiff=24, chase=28)
            for i in range(5)
        ]
        pool = build_pool(pool_players)
        bare_player = {
            "player_key": "bare",
            "statline": {"is_pitcher": False},
            # No statcast_metrics, no zone_metrics
        }
        assert compute_statcast_plus(bare_player, pool) is None

    def test_partial_data_still_computes(self):
        """A player with only contact_quality (no zone_metrics) still
        gets a Statcast+ score from the components they DO have."""
        pool_players = [
            _hit(f"h{i}", ev=88 + i, hh=35 + i, brl=6 + i*0.5, z_con=80, whiff=24, chase=28)
            for i in range(5)
        ]
        pool = build_pool(pool_players)
        partial = {
            "player_key": "p",
            "statline": {"is_pitcher": False},
            "statcast_metrics": {"contact_quality": {"avg_ev": 95.0,
                                                      "hard_hit_pct": 45.0,
                                                      "barrel_pct": 12.0}},
        }
        sp = compute_statcast_plus(partial, pool)
        assert sp is not None
        # Should still register elite — every contributing component
        # sits above pool mean.
        assert sp > 105


# ----------------------------------------------------------------------
# Chase-component key regression (bug-sweep fix 2026-07-07)
# ----------------------------------------------------------------------

class TestChaseComponentKey:
    """The chase component died silently for ALL production rows because the
    extractors read chase_pct while ZoneMetricRow serializes o_swing_pct.
    These tests pin the resurrected o_swing_pct-first read on both sides, so
    a revert to chase_pct-only fails the suite instead of passing quietly."""

    def test_hitter_o_swing_only_yields_chase_component(self):
        from statcast_plus import _extract_hitter
        player = _hit("h_osw", ev=90.0, hh=40.0, brl=8.0,
                      z_con=82.0, whiff=22.0, chase=27.0)
        comps = _extract_hitter(player)
        # chase is inverted (less chasing is better); None = the pre-fix bug.
        assert comps["chase_inv"] == -27.0

    def test_pitcher_o_swing_only_yields_chase_component(self):
        from statcast_plus import _extract_pitcher
        player = _pit("p_osw", velo=95.0, whiff=28.0, chase=33.0,
                      hh_allowed=32.0, brl_allowed=5.0)
        comps = _extract_pitcher(player)
        assert comps["chase"] == 33.0

    def test_chase_pct_fallback_still_honored(self):
        """chase_pct stays a defensive fallback for alternate payload shapes."""
        from statcast_plus import _extract_hitter, _extract_pitcher
        h = _hit("h_fb", ev=90.0, hh=40.0, brl=8.0,
                 z_con=82.0, whiff=22.0, chase=None)
        h["zone_metrics"].pop("o_swing_pct")
        h["zone_metrics"]["chase_pct"] = 29.0
        assert _extract_hitter(h)["chase_inv"] == -29.0
        p = _pit("p_fb", velo=95.0, whiff=28.0, chase=None,
                 hh_allowed=32.0, brl_allowed=5.0)
        p["zone_metrics"].pop("o_swing_pct")
        p["zone_metrics"]["chase_pct"] = 31.0
        assert _extract_pitcher(p)["chase"] == 31.0

    def test_o_swing_moves_the_composite(self):
        """End-to-end: with everything else identical, a lower chase rate
        (o_swing_pct) must produce a higher hitter Statcast+ -- i.e. the
        component actually reaches the composite from the production key."""
        pool_players = [
            _hit(f"h{i}", ev=88.0, hh=35.0, brl=6.0,
                 z_con=80.0, whiff=24.0, chase=24.0 + i)
            for i in range(8)
        ]
        pool = build_pool(pool_players)
        disciplined = _hit("disc", ev=88.0, hh=35.0, brl=6.0,
                           z_con=80.0, whiff=24.0, chase=20.0)
        chaser = _hit("chase", ev=88.0, hh=35.0, brl=6.0,
                      z_con=80.0, whiff=24.0, chase=36.0)
        sp_disc = compute_statcast_plus(disciplined, pool)
        sp_chase = compute_statcast_plus(chaser, pool)
        assert sp_disc is not None and sp_chase is not None
        assert sp_disc > sp_chase


# ----------------------------------------------------------------------
# ETA integration
# ----------------------------------------------------------------------

class TestETAStatcastPlusModifier:
    def test_top_quintile_shaves_quarter_year(self):
        from eta import estimate_eta
        baseline = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                                statcast_plus=None)
        boosted = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                               statcast_plus=120)
        assert boosted.statcast_plus_adj == -0.25
        assert baseline.statcast_plus_adj == 0.0
        # ETA year should pull in by at most 1 year (or equal — round-to-int
        # bucketing); the underlying total must be lower.
        assert boosted.eta_year is not None and baseline.eta_year is not None
        assert boosted.eta_year <= baseline.eta_year

    def test_elite_tier_shaves_half_year(self):
        from eta import estimate_eta
        r = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                         statcast_plus=135)
        assert r.statcast_plus_adj == -0.50

    def test_bottom_quintile_adds_quarter_year(self):
        from eta import estimate_eta
        r = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                         statcast_plus=70)
        assert r.statcast_plus_adj == +0.25

    def test_none_leaves_modifier_at_zero(self):
        from eta import estimate_eta
        r = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                         statcast_plus=None)
        assert r.statcast_plus_adj == 0.0

    def test_neutral_range_no_modifier(self):
        from eta import estimate_eta
        r = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                         statcast_plus=100)
        assert r.statcast_plus_adj == 0.0


# ----------------------------------------------------------------------
# Breakout gate integration
# ----------------------------------------------------------------------

class TestBreakoutStatcastGate:
    def _payload_with_tool_signal(self, statcast_plus=None,
                                   age=20.0, is_pitcher=False):
        """Build a minimal active payload that satisfies the FV upgrade
        signal (+5 over the window) so the only variable in the test is
        whether a perf gate passes."""
        anchor = (date.today() - timedelta(days=220)).isoformat()
        recent_pts = [
            {"snapshot_date": anchor,                     "consensus_fv": 45.0,
             "consensus_fv_label": "45", "tools_consensus": {"hit": 50}},
            {"snapshot_date": (date.today() - timedelta(days=140)).isoformat(),
             "consensus_fv": 47.0, "consensus_fv_label": "47",
             "tools_consensus": {"hit": 50}},
            {"snapshot_date": (date.today() - timedelta(days=70)).isoformat(),
             "consensus_fv": 50.0, "consensus_fv_label": "50",
             "tools_consensus": {"hit": 50}},
            {"snapshot_date": date.today().isoformat(),    "consensus_fv": 51.0,
             "consensus_fv_label": "51", "tools_consensus": {"hit": 50}},
        ]
        return {
            "status": "active",
            "age": age,
            "position": "RHP" if is_pitcher else "SS",
            "statline": {"is_pitcher": is_pitcher},
            "sabermetrics": {"is_pitcher": is_pitcher},
            "statcast_plus": statcast_plus,
            "points": recent_pts,
        }

    def test_statcast_plus_passes_perf_gate(self):
        from storage import _compute_breakout_flag
        payload = self._payload_with_tool_signal(statcast_plus=120, age=22.0)
        meta = _compute_breakout_flag(payload)
        assert meta is not None
        assert meta["perf_gate"] == "statcast_plus"

    def test_low_statcast_plus_does_not_pass(self):
        from storage import _compute_breakout_flag
        payload = self._payload_with_tool_signal(statcast_plus=100, age=22.0)
        # No other gate satisfied (no RPS+, no Stuff+, no FIP-) → no breakout.
        meta = _compute_breakout_flag(payload)
        assert meta is None

    def test_stat_only_statcast_plus_path(self):
        """Elite Statcast+ on a young prospect triggers the stat-only
        path even without ANY tool/FV velocity signal."""
        from storage import _compute_breakout_flag
        # Tiny window — no tool/FV signal possible.
        payload = {
            "status": "active",
            "age": 21.0,
            "position": "SS",
            "statline": {"is_pitcher": False},
            "sabermetrics": {"is_pitcher": False},
            "statcast_plus": 135,
            "points": [],
        }
        meta = _compute_breakout_flag(payload)
        assert meta is not None
        assert meta["reason"] == "stats"
        assert meta["perf_gate"] == "statcast_plus"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

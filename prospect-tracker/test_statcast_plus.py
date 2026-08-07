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

def _hit(player_key, ev, hh, brl, z_con, whiff, chase, bbe=200, pitches=1500):
    """Build a hitter mini-payload that build_pool / compute_statcast_plus
    can consume directly. The chase rate serializes as o_swing_pct -- the
    ONLY key production ZoneMetricRow rows carry (chase_pct never existed on
    them, which silently killed the component pre-2026-07-07); fixtures must
    exercise that production path, not the defensive chase_pct fallback.

    bbe / pitches default HIGH on purpose. Every component is EB-shrunk by its
    own sample size since 2026-08-07, so a fixture that omitted them would be
    testing the shrink instead of the thing it means to test. Tests that care
    about the shrink pass small values explicitly."""
    return {
        "player_key": player_key,
        "statline": {"is_pitcher": False, "level": "AA"},
        "statcast_metrics": {
            "contact_quality": {
                "batted_balls": bbe,
                "avg_ev": ev,
                "hard_hit_pct": hh,
                "barrel_pct": brl,
            },
        },
        "zone_metrics": {
            "pitches": pitches,
            "z_contact_pct": z_con,
            "whiff_pct": whiff,
            "o_swing_pct": chase,
        },
    }


def _pit(player_key, velo, whiff, chase, hh_allowed, brl_allowed,
         bbe=200, pitches=1500, velo_n=400):
    return {
        "player_key": player_key,
        "statline": {"is_pitcher": True, "level": "AA"},
        "statcast_metrics": {
            "contact_quality": {
                "batted_balls": bbe,
                "hard_hit_pct": hh_allowed,
                "barrel_pct": brl_allowed,
            },
            "pitch_movement": {
                "pitch_summary": [{"pitch_type": "FF", "count": velo_n,
                                   "avg_velo": velo}],
            },
        },
        "zone_metrics": {
            "pitches": pitches,
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
        # Bounds widened 2026-08-07: the composite is now divided by its own
        # pool sd, so a player outside the pool's range lands further from 100
        # than he did on the compressed scale. Both are well past +/-2 sigma.
        assert sp_elite > 130, f"Elite should clear +3σ; got {sp_elite}"
        assert sp_weak  < 80,  f"Weak should sink below pool; got {sp_weak}"
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
        # 10 pts/σ became TRUE on 2026-08-07 (it was 5.9 on the served pitcher
        # pool before), so an elite arm now clears +1σ by a real margin.
        assert sp is not None and sp > 115

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
            "statcast_metrics": {"contact_quality": {"batted_balls": 180,
                                                      "avg_ev": 95.0,
                                                      "hard_hit_pct": 45.0,
                                                      "barrel_pct": 12.0}},
        }
        sp = compute_statcast_plus(partial, pool)
        assert sp is not None
        # Should still register elite: every contributing component sits above
        # the pool mean.
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
    """Cuts re-mapped 2026-08-07 (130/115/85 -> 143/122/77) with the SC+
    re-standardization. The BAND STRUCTURE is what these pin, not the numbers:
    a value just inside each band nudges, a value just outside does not."""

    def test_top_quintile_shaves_quarter_year(self):
        from eta import estimate_eta
        baseline = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                                statcast_plus=None)
        boosted = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                               statcast_plus=125)
        assert boosted.statcast_plus_adj == -0.25
        assert baseline.statcast_plus_adj == 0.0
        # ETA year should pull in by at most 1 year (or equal — round-to-int
        # bucketing); the underlying total must be lower.
        assert boosted.eta_year is not None and baseline.eta_year is not None
        assert boosted.eta_year <= baseline.eta_year

    def test_elite_tier_shaves_half_year(self):
        from eta import estimate_eta
        r = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                         statcast_plus=145)
        assert r.statcast_plus_adj == -0.50

    def test_bottom_quintile_adds_quarter_year(self):
        from eta import estimate_eta
        r = estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                         statcast_plus=70)
        assert r.statcast_plus_adj == +0.25

    def test_bands_are_exclusive_at_their_edges(self):
        """One below each cut gets the WEAKER treatment. This is the pin that
        fails if a future scale change moves the index without moving the
        thresholds with it, which is exactly what happened on 2026-08-07."""
        from eta import estimate_eta
        def adj(sc):
            return estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                                statcast_plus=sc).statcast_plus_adj
        assert adj(143) == -0.50 and adj(142) == -0.25
        assert adj(122) == -0.25 and adj(121) == 0.0
        assert adj(77) == +0.25 and adj(78) == 0.0

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
        payload = self._payload_with_tool_signal(statcast_plus=125, age=22.0)
        meta = _compute_breakout_flag(payload)
        assert meta is not None
        assert meta["perf_gate"] == "statcast_plus"

    def test_low_statcast_plus_does_not_pass(self):
        from storage import _compute_breakout_flag
        payload = self._payload_with_tool_signal(statcast_plus=100, age=22.0)
        # No other gate satisfied (no RPS+, no Stuff+, no FIP-) -> no breakout.
        meta = _compute_breakout_flag(payload)
        assert meta is None

    def test_gates_track_the_shipped_constants(self):
        """The two SC+ breakout bars are DIFFERENT numbers and the prospx chip
        label branches on which one fired. Pin them to the constants so the
        label and the gate cannot drift apart again."""
        import storage
        assert storage._BREAKOUT_STATCAST_PLUS_GATE == 122
        assert storage._BREAKOUT_STAT_STATCAST_PLUS_GATE == 143
        assert (storage._BREAKOUT_STAT_STATCAST_PLUS_GATE
                > storage._BREAKOUT_STATCAST_PLUS_GATE)

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
            "statcast_plus": 145,
            "points": [],
        }
        meta = _compute_breakout_flag(payload)
        assert meta is not None
        assert meta["reason"] == "stats"
        assert meta["perf_gate"] == "statcast_plus"


# ----------------------------------------------------------------------
# Volume floors + EB shrink (docs/SC_PLUS_RECALIBRATION_GATE.md ship 1)
# ----------------------------------------------------------------------

class TestVolumeFloorsAndShrink:
    def _spread_pool(self, n=12, **kw):
        return [_hit(f"h{i}", ev=84.0 + i * 0.8, hh=30.0 + i, brl=3.0 + i * 0.6,
                     z_con=74.0 + i, whiff=30.0 - i, chase=34.0 - i, **kw)
                for i in range(n)]

    def test_sub_floor_batted_balls_drops_the_contact_legs(self):
        """The defect this ships against: a 1-batted-ball player contributed a
        full-magnitude exit-velocity z. Below the floor the leg is dropped, so
        an absurd contact line cannot reach the composite at all."""
        pool = build_pool(self._spread_pool())
        absurd = _hit("absurd", ev=120.0, hh=100.0, brl=100.0,
                      z_con=80.0, whiff=24.0, chase=28.0, bbe=1)
        honest = _hit("honest", ev=88.0, hh=35.0, brl=6.0,
                      z_con=80.0, whiff=24.0, chase=28.0, bbe=1)
        # Identical zone lines, wildly different contact lines, same score:
        # the contact legs never entered.
        assert compute_statcast_plus(absurd, pool) == compute_statcast_plus(honest, pool)

    def test_shrink_pulls_a_thin_sample_toward_the_pool(self):
        """Above the floor but thin, an extreme value still counts less than
        the same value on a full season."""
        pool = build_pool(self._spread_pool())
        thin = _hit("thin", ev=120.0, hh=100.0, brl=100.0,
                    z_con=80.0, whiff=24.0, chase=28.0, bbe=12)
        thick = _hit("thick", ev=120.0, hh=100.0, brl=100.0,
                     z_con=80.0, whiff=24.0, chase=28.0, bbe=400)
        assert compute_statcast_plus(thin, pool) < compute_statcast_plus(thick, pool)

    def test_missing_volume_field_drops_the_leg(self):
        """Production carries the volume on 100% of rows that carry the
        component. A row without one is malformed, and a reliability-weighted
        composite does not take a leg whose reliability is unknown."""
        pool = build_pool(self._spread_pool())
        no_vol = {"player_key": "nv", "statline": {"is_pitcher": False},
                  "statcast_metrics": {"contact_quality": {"avg_ev": 120.0}}}
        assert compute_statcast_plus(no_vol, pool) is None

    def test_pool_columns_come_from_every_row_not_the_first(self):
        """rows[0].keys() dropped a component for the WHOLE pool whenever the
        first row happened to be missing it."""
        players = self._spread_pool()
        players[0]["statcast_metrics"]["contact_quality"] = {"batted_balls": 200}
        pool = build_pool(players)
        for leg in ("avg_ev", "hard_hit_pct", "barrel_pct"):
            assert pool["hit"][leg]["mean"] is not None, leg

    def test_degenerate_column_cannot_produce_an_unbounded_z(self):
        """`sd > 0` passed a near-zero sd through. A pool where one leg is
        constant to within floating-point noise must not hand one row a
        thousand-sigma score."""
        players = [_hit(f"h{i}", ev=88.0 + i * 1e-13, hh=30.0 + i, brl=3.0 + i,
                        z_con=74.0 + i, whiff=30.0 - i, chase=34.0 - i)
                   for i in range(12)]
        pool = build_pool(players)
        for p in players:
            assert 0 < compute_statcast_plus(p, pool) < 200


# ----------------------------------------------------------------------
# Coverage-conditional scale (ship 2)
# ----------------------------------------------------------------------

class TestCoverageConditionalScale:
    def test_pool_is_ten_points_per_sigma(self):
        """The whole point of ship 2. Before it, the served pool moved 6.08
        (hit) / 5.93 (pit) points per sigma against an advertised 10."""
        from statistics import pstdev
        players = [_hit(f"h{i}", ev=84.0 + i * 0.2, hh=30.0 + i * 0.3,
                        brl=3.0 + i * 0.15, z_con=74.0 + i * 0.25,
                        whiff=30.0 - i * 0.2, chase=34.0 - i * 0.22)
                   for i in range(80)]
        pool = build_pool(players)
        served = [compute_statcast_plus(p, pool) for p in players]
        assert 9.0 <= pstdev(served) <= 11.0, pstdev(served)

    def test_thin_coverage_class_borrows_the_side_divisor(self):
        """A class under _MIN_COVERAGE_CELL must not fit its own scale off a
        handful of rows; it falls back rather than inventing a divisor."""
        import statcast_plus as sp
        players = [_hit(f"h{i}", ev=84.0 + i * 0.2, hh=30.0 + i * 0.3,
                        brl=3.0 + i * 0.15, z_con=74.0 + i * 0.25,
                        whiff=30.0 - i * 0.2, chase=34.0 - i * 0.22)
                   for i in range(80)]
        # Three zone-only rows: a real coverage class, far below the cell floor.
        for i in range(3):
            players[i]["statcast_metrics"]["contact_quality"] = {"batted_balls": 200}
        pool = build_pool(players)
        scales = pool["hit"][sp._SCALE_KEY]
        assert all(len(k.split("|")) == 6 for k in scales), scales
        assert compute_statcast_plus(players[0], pool) is not None

    def test_pool_without_scale_raises_instead_of_serving_the_old_index(self):
        """A stale cached pool would otherwise serve the pre-2026-08-07
        compressed composite against the re-mapped thresholds, which reads as a
        site-wide collapse rather than as an error."""
        import statcast_plus as sp
        players = [_hit(f"h{i}", ev=84.0 + i, hh=30.0 + i, brl=3.0 + i,
                        z_con=74.0 + i, whiff=30.0 - i, chase=34.0 - i)
                   for i in range(12)]
        pool = build_pool(players)
        del pool["hit"][sp._SCALE_DEFAULT_KEY]
        with pytest.raises(ValueError):
            compute_statcast_plus(players[0], pool)

    def test_empty_pool_still_returns_none_rather_than_raising(self):
        players = [_hit(f"h{i}", ev=84.0 + i, hh=30.0 + i, brl=3.0 + i,
                        z_con=74.0 + i, whiff=30.0 - i, chase=34.0 - i)
                   for i in range(4)]
        assert compute_statcast_plus(players[0], {}) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

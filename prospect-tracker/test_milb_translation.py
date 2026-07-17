# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""First coverage for milb_translation (MiLB -> first-MLB K%/BB% translation).

Pins the audit-fixed sample gates in _load_pairs:
  - PITCHERS gate on INNINGS (MIN_MLB_IP = 40.0). `games` counts appearances
    for pitchers, so the old games>=40 gate passed almost no starters and
    starved the pit_k / pit_bb fits; a 45-appearance / 20-IP reliever must
    stay OUT, a 45-IP arm is IN.
  - HITTERS gate on games (MIN_MLB_GAMES = 40), never on innings.
Plus a basic build() shape pin on synthetic pairs (fit fields, thin-sample
validation honesty, no persistence).

All fixtures are synthetic and written to tmp_path; milb_translation.DATA is
monkeypatched so the real data/ payloads are never read or written.
"""

import json

import pytest

import milb_translation as mt


def _matrix_row(pk, k_rel=0.0, bb_rel=0.0):
    return {"kind": "debuted", "player_key": pk,
            "milb": {"k_rel": k_rel, "bb_rel": bb_rel}}


def _debut(pk, is_pitcher, k_pct=22.0, bb_pct=8.0, **statline):
    sl = {"is_pitcher": is_pitcher, "k_pct": k_pct, "bb_pct": bb_pct}
    sl.update(statline)
    return {"player_key": pk, "statline": sl}


def _install(tmp_path, monkeypatch, debuts, pit_rows=(), hit_rows=()):
    (tmp_path / "xfv_pitcher_matrix.json").write_text(
        json.dumps(list(pit_rows)), encoding="utf-8")
    (tmp_path / "xfv_hitter_matrix.json").write_text(
        json.dumps(list(hit_rows)), encoding="utf-8")
    (tmp_path / "debuts.json").write_text(json.dumps(debuts), encoding="utf-8")
    monkeypatch.setattr(mt, "DATA", tmp_path)


class TestPitcherIpGate:
    def test_appearances_do_not_qualify_a_pitcher(self, tmp_path, monkeypatch):
        """45 appearances / 20 IP is OUT; 45 IP is IN - the gate is innings,
        not the `games` field (appearances for pitchers)."""
        pit_rows = [_matrix_row("reliever", k_rel=2.0),
                    _matrix_row("workhorse", k_rel=4.0)]
        debuts = [
            _debut("reliever", True, k_pct=30.0, games=45, ip=20.0),
            _debut("workhorse", True, k_pct=25.0, ip=45.0),
        ]
        _install(tmp_path, monkeypatch, debuts, pit_rows=pit_rows)
        pairs = mt._load_pairs()
        assert pairs["pit_k"] == [(4.0, 25.0)]
        assert all((x, y) != (2.0, 30.0) for x, y in pairs["pit_k"])

    def test_ip_gate_boundary(self, tmp_path, monkeypatch):
        assert mt.MIN_MLB_IP == 40.0
        pit_rows = [_matrix_row("at_gate", k_rel=1.0),
                    _matrix_row("under_gate", k_rel=1.5)]
        debuts = [
            _debut("at_gate", True, k_pct=24.0, ip=40.0),     # exactly 40 -> IN
            _debut("under_gate", True, k_pct=26.0, ip=39.9),  # under -> OUT
        ]
        _install(tmp_path, monkeypatch, debuts, pit_rows=pit_rows)
        pairs = mt._load_pairs()
        assert pairs["pit_k"] == [(1.0, 24.0)]

    def test_missing_ip_is_excluded(self, tmp_path, monkeypatch):
        pit_rows = [_matrix_row("no_ip", k_rel=1.0)]
        debuts = [_debut("no_ip", True, k_pct=24.0, games=60)]  # no ip on file
        _install(tmp_path, monkeypatch, debuts, pit_rows=pit_rows)
        pairs = mt._load_pairs()
        assert pairs["pit_k"] == [] and pairs["pit_bb"] == []


class TestHitterGamesGate:
    def test_hitter_gates_on_games_not_innings(self, tmp_path, monkeypatch):
        assert mt.MIN_MLB_GAMES == 40
        hit_rows = [_matrix_row("regular", k_rel=-1.0, bb_rel=2.0),
                    _matrix_row("cup_of_coffee", k_rel=-2.0, bb_rel=1.0)]
        debuts = [
            _debut("regular", False, k_pct=19.0, bb_pct=11.0, games=45),
            _debut("cup_of_coffee", False, k_pct=17.0, bb_pct=9.0, games=39),
        ]
        _install(tmp_path, monkeypatch, debuts, hit_rows=hit_rows)
        pairs = mt._load_pairs()
        assert pairs["hit_k"] == [(-1.0, 19.0)]
        assert pairs["hit_bb"] == [(2.0, 11.0)]

    def test_sides_never_cross(self, tmp_path, monkeypatch):
        """A qualified pitcher lands in pit_* only, a qualified hitter in
        hit_* only - no cross-contamination of the fit substrates."""
        pit_rows = [_matrix_row("arm", k_rel=3.0)]
        hit_rows = [_matrix_row("bat", k_rel=-1.5)]
        debuts = [_debut("arm", True, k_pct=27.0, ip=50.0),
                  _debut("bat", False, k_pct=20.0, games=100)]
        _install(tmp_path, monkeypatch, debuts,
                 pit_rows=pit_rows, hit_rows=hit_rows)
        pairs = mt._load_pairs()
        assert pairs["pit_k"] == [(3.0, 27.0)]
        assert pairs["hit_k"] == [(-1.5, 20.0)]


class TestBuildShape:
    def test_build_emits_fit_and_honest_thin_validation(self, tmp_path, monkeypatch):
        """10 qualified pitcher pairs -> a pit_k fit ships (n >= 8) with the
        regression-factor fields; LOO validation stays None below its n=30
        honesty floor; nothing is persisted; active projections stubbed out."""
        pit_rows, debuts = [], []
        for i in range(10):
            k_rel = float(i)
            pit_rows.append(_matrix_row(f"p{i}", k_rel=k_rel, bb_rel=0.5 * i))
            debuts.append(_debut(f"p{i}", True, k_pct=20.0 + 0.8 * i,
                                 bb_pct=9.0 - 0.2 * i, ip=45.0 + i))
        _install(tmp_path, monkeypatch, debuts, pit_rows=pit_rows)
        monkeypatch.setattr(mt, "_project_actives", lambda fits: {})

        out = mt.build(persist=False)

        assert out["min_mlb_ip"] == 40.0 and out["min_mlb_games"] == 40
        fit = out["fits"]["pit_k"]
        assert fit["n"] == 10
        for field in ("slope", "x_mean", "y_mean", "band_sd", "r2"):
            assert field in fit
        # honest validation: n=10 < 30 -> no LOO block, never a fabricated one
        assert out["validation"]["pit_k"] is None
        assert out["projections"] == {}
        # persist=False must not write the sidecar into the (patched) data dir
        assert not (tmp_path / "milb_translation.json").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

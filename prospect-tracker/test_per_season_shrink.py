"""RC-6 regression guard: the per-season career rows (_current_season_statlines)
must apply the SAME empirical-Bayes shrink as the headline statline, so a
small-sample line no longer re-enables the "OPS+ 374 on 4 AB" blowups the
headline guard was added to kill. See docs/audit/rc6_shrink_impact.md.
"""

import io

from rate_stabilization import K_AB, K_IP


def _src():
    return io.open("storage.py", encoding="utf-8").read()


def test_per_season_ops_era_are_shrunk_not_raw():
    src = _src()
    # The buggy raw forms must be gone.
    assert "round(_ops / _avg_ops * 100)" not in src, "per-season OPS+ reverted to raw (unshrunk)"
    assert "round(_era / _avg_era * 100)" not in src, "per-season ERA- reverted to raw (unshrunk)"
    # The shrink forms must be present.
    assert "_ops_adj = (_ab * _ops + K_AB * _avg_ops) / (_ab + K_AB)" in src
    assert "_era_adj = (_ip * _era + K_IP * _avg_era) / (_ip + K_IP)" in src


def test_shrink_tames_a_tiny_sample_blowup():
    # Mirror the shipped formula: a 3-AB .900-OPS cameo in a .700-OPS level
    # should NOT read OPS+ ~129 raw; the shrink pulls it toward 100.
    ops, ab, avg = 0.900, 3.0, 0.700
    raw = round(ops / avg * 100)
    ops_adj = (ab * ops + K_AB * avg) / (ab + K_AB)
    shrunk = round(ops_adj / avg * 100)
    assert raw >= 125
    assert abs(shrunk - 100) <= 2, f"3-AB cameo should shrink to ~100, got {shrunk}"

    # A qualified 450-AB line barely moves.
    ab_q = 450.0
    ops_adj_q = (ab_q * ops + K_AB * avg) / (ab_q + K_AB)
    shrunk_q = round(ops_adj_q / avg * 100)
    assert shrunk_q >= raw - 15, "qualified sample should move only modestly"

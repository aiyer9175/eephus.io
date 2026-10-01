"""The 2031/2032 seam of the contract tail (owner answer VAL2-Q1, 2026-09-30).

A guarantee past the last projected season prices its later seasons on the
champion's aging curve CHAINED FROM THE SERVED 2031 WAR, the FA module's own
seam (fa_market.chain_aging_tail, which contract_war_path uses for horizons 6+),
so the WAR no longer steps from the ML path's level to the champion's level
between 2031 and 2032 (VAL_2 shipped -3.24 WAR on McGonigle, +2.95 on Soto)."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import fa_market as fm
import proj_export as pe

ROOT = Path(__file__).resolve().parent


def test_chain_scales_the_champion_relative_decay_from_the_last_value():
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0, 0.0]
    out = fm.chain_aging_tail([5.0, 4.8, 4.6, 4.4, 4.0], champ, 5, 8)
    assert out[:5] == [5.0, 4.8, 4.6, 4.4, 4.0]
    # scale 4.0 / 2.0 = 2.0 on the champion's own seasons, floored at 0
    assert out[5:] == [3.0, 2.0, 0.0]


def test_chain_falls_back_to_the_ratio_chain_when_the_anchor_is_about_zero():
    champ = [0.5, 0.3, 0.1, 0.05, 0.04, 0.02, 0.01]
    out = fm.chain_aging_tail([0.9, 0.6, 0.4, 0.3, 0.2], champ, 5, 7)
    # the champion's 2031 is 0.04 (<= 0.05), so the scale is undefined; each
    # prior champion season is at or below 0.05, so each step decays by 0.7
    assert out[5:] == [round(0.2 * 0.7, 2), round(0.2 * 0.7 * 0.7, 2)]


def test_the_fa_module_extends_the_ml_path_with_the_same_function():
    """One seam, never forked: contract_war_path's horizons 6+ are
    chain_aging_tail, which is what proj_export's tail reads."""
    src = inspect.getsource(fm.contract_war_path)
    assert "chain_aging_tail(series_ml, champ_series, H, MAX_PATH_YEARS)" in src


def test_tail_war_reads_the_served_full_path_and_recomputes_with_the_same_rule(monkeypatch):
    monkeypatch.setattr(pe, "TAIL_SEAM", "chained")
    war = [5.0, 4.8, 4.6, 4.4, 4.0]
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0]
    full = fm.chain_aging_tail(war, champ, pe.HORIZON, len(champ))
    assert pe._tail_war(war, champ, full) == ([3.0, 2.0], "served_path")
    # no carrier, or a carrier that does not reproduce the served five seasons:
    # recomputed with chain_aging_tail from the served path, never the level
    assert pe._tail_war(war, champ, None) == ([3.0, 2.0], "recomputed")
    assert pe._tail_war(war, champ, [9.0] * 7) == ([3.0, 2.0], "recomputed")


def test_champion_level_is_the_revert(monkeypatch):
    monkeypatch.setattr(pe, "TAIL_SEAM", "champion_level")
    assert pe._tail_war([5.0] * 5, [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0], None) == (
        [1.5, 1.0], "champion_level")
    monkeypatch.setattr(pe, "TAIL_SEAM", "nonsense")
    with pytest.raises(ValueError):
        pe._tail_war([5.0] * 5, [3.0] * 7, None)


def _served():
    p = ROOT / "data" / "mlb_projections.json"
    if not p.exists():
        pytest.skip("mlb_projections.json not built")
    return json.loads(p.read_text(encoding="utf-8"))


def test_served_tail_has_no_level_step_at_the_seam():
    """On the served artifact the first tail season sits within
    0.5 + 0.35 x the 2031 WAR of 2031. The VAL_2 champion-level tail failed
    this on Soto (4.60 to 1.65), McGonigle (4.12 to 7.36) and Ohtani."""
    d = _served()
    tail = (d.get("accountability") or {}).get("salary_path", {}).get("contract_tail") or {}
    if not tail.get("enabled"):
        pytest.skip("contract tail off")
    if pe.TAIL_SEAM != "chained":
        pytest.skip("seam reverted")
    assert tail.get("seam") == "chained" and tail.get("war_basis") == "chain_aging_tail"
    assert tail.get("seam_served_path", 0) + tail.get("seam_recomputed", 0) == tail["rows"]
    bad = []
    for v in d["vets"]:
        wt = v.get("warTail")
        if not wt or wt[0] is None:
            continue
        w5 = float(v["war"][d["horizon"] - 1])
        if abs(float(wt[0]) - w5) > 0.5 + 0.35 * abs(w5):
            bad.append((v["key"], w5, wt[0]))
        assert all(w is None or w >= 0 for w in wt), v["key"]
    assert not bad, bad

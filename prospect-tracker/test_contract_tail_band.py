"""The contract tail's range (owner answers VAL2-Q3 and VAL2-Q3-REVIEW (b),
2026-09-30).

The trade value's P10-P90 range spans every season its point value prices: a
guarantee past 2031 carries its range to its last season, each tail season on
the 2031 P10/P90 chained along the champion's aging curve
(fa_market.chain_aging_tail, the FA module's anchors 0.6 and 1.4 x the champion
path). The low end is NOT floored at zero: a negative 2031 P10 carries into the
later seasons, so the P10 never steps up to zero at 2032 (the floored build did
that on 30 of 39 rows). The two checks the review kept are pinned here on the
served artifacts: P10 <= point <= P90 on every row and season, and no negative
width. The point value is untouched by the range."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bayes_trade_value as btv
import fa_market as fm
import proj_export as pe

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


# ------------------------------------------------------------- the chain --
def test_the_floor_off_carries_a_negative_last_value_along_the_chain():
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0, 0.0]
    head = [0.5, 0.2, 0.0, -0.1, -0.4]
    # scale -0.4 / 2.0 = -0.2 on the champion's own seasons
    assert fm.chain_aging_tail(head, champ, 5, 8, floor=False)[5:] == [-0.3, -0.2, 0.0]
    # the default keeps the FA module's floor
    assert fm.chain_aging_tail(head, champ, 5, 8)[5:] == [0.0, 0.0, 0.0]


def test_the_floor_off_ratio_chain_decays_a_negative_value_toward_zero():
    champ = [0.5, 0.3, 0.1, 0.05, 0.04, 0.02, 0.01]
    out = fm.chain_aging_tail([0.9, 0.6, 0.4, 0.3, -0.2], champ, 5, 7, floor=False)
    assert out[5:] == [round(-0.2 * 0.7, 2), round(-0.2 * 0.7 * 0.7, 2)]
    assert all(v < 0 for v in out[5:])


def test_no_negative_zero_is_published():
    out = fm.chain_aging_tail([1.0, 1.0, 1.0, 1.0, -0.001], [1.0] * 7, 5, 7, floor=False)
    assert all(str(v) != "-0.0" for v in out[5:])


def test_the_floor_on_is_unchanged_for_every_existing_caller():
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0, 0.0]
    for head in ([5.0, 4.8, 4.6, 4.4, 4.0], [0.5, 0.2, 0.0, -0.1, -0.4], [1.0, 1.0, 1.0, 1.0, 0.0]):
        a = fm.chain_aging_tail(head, champ, 5, 8)
        b = fm.chain_aging_tail(head, champ, 5, 8, floor=True)
        assert a == b and all(v >= 0 for v in a[5:])


# ------------------------------------------------------- proj_export band --
def test_tail_band_recomputes_the_low_end_unfloored(monkeypatch):
    monkeypatch.setattr(pe, "TAIL_SEAM", "chained")
    monkeypatch.setattr(pe, "TAIL_BAND", True)
    monkeypatch.setattr(pe, "TAIL_BAND_P10_FLOOR", False)
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0]
    m = {"warP10": [0.5, 0.2, 0.0, -0.1, -0.4], "warP90": [6.0, 5.8, 5.6, 5.4, 5.0]}
    lo, hi = pe._tail_band(m, champ)
    # P10 anchor 0.6 x champion: -0.4 / 1.2 on 0.9 and 0.6
    assert lo == [-0.3, -0.2]
    # P90 anchor 1.4 x champion: 5.0 / 2.8 on 2.1 and 1.4, floored as before
    assert hi == [3.75, 2.5]


def test_tail_band_floored_low_end_is_the_revert(monkeypatch):
    monkeypatch.setattr(pe, "TAIL_SEAM", "chained")
    monkeypatch.setattr(pe, "TAIL_BAND", True)
    monkeypatch.setattr(pe, "TAIL_BAND_P10_FLOOR", True)
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0]
    m = {"warP10": [0.5, 0.2, 0.0, -0.1, -0.4], "warP90": [6.0, 5.8, 5.6, 5.4, 5.0]}
    assert pe._tail_band(m, champ)[0] == [0.0, 0.0]
    monkeypatch.setattr(pe, "TAIL_BAND", False)
    assert pe._tail_band(m, champ) is None


def test_tail_band_reads_the_open_carrier_when_it_matches_the_served_seasons(monkeypatch):
    monkeypatch.setattr(pe, "TAIL_SEAM", "chained")
    monkeypatch.setattr(pe, "TAIL_BAND", True)
    monkeypatch.setattr(pe, "TAIL_BAND_P10_FLOOR", False)
    champ = [3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0]
    p10 = [0.5, 0.2, 0.0, -0.1, -0.4]
    m = {"warP10": p10, "warP90": [6.0] * 5,
         "_p10Full": p10 + [-0.25, -0.15], "_p90Full": [6.0] * 5 + [3.0, 2.0]}
    assert pe._tail_band(m, champ) == ([-0.25, -0.15], [3.0, 2.0])


def test_the_ml_path_ships_the_open_p10_carrier_beside_the_floored_one():
    import inspect
    src = inspect.getsource(fm.contract_war_path)
    assert '"war_by_year_p10_open": chain_aging_tail(' in src and "floor=False" in src


# ---------------------------------------- the branch is decided once a row --
# POSTEPOCH_9_CONTRACT_TAIL_BAND_SEAM: the 0.05 tests read the UNMULTIPLIED
# champion (branch_champ), so the point and its band take one branch and one
# ratio per season, and P10 <= point <= P90 at 2031 holds on every tail season.
_CAMPBELL_CHAMP = [0.16, 0.16, 0.12, 0.09, 0.04, 0.0, 0.0, 0.0]


def test_the_p90_band_takes_the_points_branch_on_a_near_zero_anchor():
    point = fm.chain_aging_tail([0.08, 0.19, 0.22, 0.13, 0.11], _CAMPBELL_CHAMP, 5, 8)
    assert point[5:] == [0.08, 0.05, 0.04]          # the ratio chain, 0.7 a season
    head = [0.76, 0.79, 1.63, 0.93, 1.03]
    p90_mult = [1.4 * c for c in _CAMPBELL_CHAMP]
    # the old branch read the 1.4 x anchor (0.056 > 0.05): the scale branch on
    # a zero champion tail, a P90 of 0.0 under the point
    assert fm.chain_aging_tail(head, p90_mult, 5, 8)[5:] == [0.0, 0.0, 0.0]
    hi = fm.chain_aging_tail(head, p90_mult, 5, 8, branch_champ=_CAMPBELL_CHAMP)
    assert hi[5:] == [0.72, 0.5, 0.35]
    lo = fm.chain_aging_tail([-0.37, -0.34, -0.14, -0.12, -0.03],
                             [0.6 * c for c in _CAMPBELL_CHAMP], 5, 8, floor=False,
                             branch_champ=_CAMPBELL_CHAMP)
    assert lo[5:] == [-0.02, -0.01, -0.01]
    assert all(a <= w <= b for a, w, b in zip(lo[5:], point[5:], hi[5:]))


def test_the_ratio_chain_test_reads_the_unmultiplied_champion_each_season():
    champ = [1.0, 1.0, 1.0, 1.0, 0.04, 0.07, 0.01, 0.0]
    point = fm.chain_aging_tail([1.0, 1.0, 1.0, 1.0, 0.5], champ, 5, 8)
    assert point[5:] == [0.35, 0.05, 0.03]
    p10_mult = [0.6 * c for c in champ]
    # 0.6 x 0.07 = 0.042 took 0.7 where the point took 0.01 / 0.07: a P10 of
    # 0.2 above a point of 0.05
    old = fm.chain_aging_tail([1.0, 1.0, 1.0, 1.0, 0.4], p10_mult, 5, 8, floor=False)
    assert old[6] > point[6]
    lo = fm.chain_aging_tail([1.0, 1.0, 1.0, 1.0, 0.4], p10_mult, 5, 8, floor=False,
                             branch_champ=champ)
    assert lo[5:] == [0.28, 0.04, 0.03]
    assert all(a <= w for a, w in zip(lo[5:], point[5:]))


def test_an_unmultiplied_caller_is_byte_identical_with_or_without_branch_champ():
    champs = ([3.0, 2.8, 2.6, 2.4, 2.0, 1.5, 1.0, 0.0], _CAMPBELL_CHAMP,
              [1.0, 1.0, 1.0, 1.0, 0.04, 0.07, 0.01, 0.0],
              [0.5, 0.3, 0.1, 0.05, 0.05, 0.06, 0.0, 0.0])
    heads = ([5.0, 4.8, 4.6, 4.4, 4.0], [0.5, 0.2, 0.0, -0.1, -0.4],
             [0.08, 0.19, 0.22, 0.13, 0.11])
    for c in champs:
        for h in heads:
            for fl in (True, False):
                assert (fm.chain_aging_tail(h, c, 5, 8, floor=fl)
                        == fm.chain_aging_tail(h, c, 5, 8, floor=fl, branch_champ=c))


def test_the_ml_path_bands_pass_the_unmultiplied_champion():
    import inspect
    src = inspect.getsource(fm.contract_war_path)
    assert src.count("branch_champ=path") == 3


def test_tail_band_recompute_keeps_the_band_around_the_point(monkeypatch):
    monkeypatch.setattr(pe, "TAIL_SEAM", "chained")
    monkeypatch.setattr(pe, "TAIL_BAND", True)
    monkeypatch.setattr(pe, "TAIL_BAND_P10_FLOOR", False)
    war = [0.08, 0.19, 0.22, 0.13, 0.11]
    m = {"warP10": [-0.37, -0.34, -0.14, -0.12, -0.03],
         "warP90": [0.76, 0.79, 1.63, 0.93, 1.03]}
    lo, hi = pe._tail_band(m, _CAMPBELL_CHAMP)
    point, _ = pe._tail_war(war, _CAMPBELL_CHAMP, None)
    assert hi == [0.72, 0.5, 0.35] and lo == [-0.02, -0.01, -0.01]
    assert all(a <= w <= b for a, w, b in zip(lo, point, hi))


# ------------------------------------------------------ the trade range ----
def _season_value(war, t, dpw):
    # $10M a win, $0 at or below zero WAR (the platform kernel's WAR <= 0 rule)
    return max(0.0, float(war)) * 1e7


def test_the_range_adds_each_priced_tail_season_and_skips_a_declined_option(monkeypatch):
    monkeypatch.setattr(btv, "_proj_season_value_fn", lambda: _season_value)
    base = {"war": [2.0] * 5, "warP10": [1.0] * 5, "warP90": [3.0] * 5,
            "sur": [1.0] * 7, "surTotal": 100e6}
    assert btv._projection_band_mm(dict(base, sur=[1.0] * 5), 1.0, 0.0, 2027) == (50.0, 150.0)
    tail = dict(base, warTail=[2.0, 2.0], warP10Tail=[-1.0, 1.0], warP90Tail=[3.0, 3.0])
    # a season at or below zero WAR is worth $0, so the -1.0 P10 takes the whole
    # $20M mid value off, no more: 50 - 20 - 10 and 150 + 10 + 10
    assert btv._projection_band_mm(tail, 1.0, 0.0, 2027) == (20.0, 170.0)
    # the declined 2033 club option (t = 6) is held at the mean: no range
    decl = dict(tail, salOptDecl=[2033])
    assert btv._projection_band_mm(decl, 1.0, 0.0, 2027) == (30.0, 160.0)


# --------------------------------------------------- served artifacts -----
def _served():
    p = DATA / "mlb_projections.json"
    t = DATA / "trade_values.json"
    if not p.exists() or not t.exists():
        pytest.skip("mlb_projections.json / trade_values.json not built")
    return (json.loads(p.read_text(encoding="utf-8")),
            json.loads(t.read_text(encoding="utf-8")))


def test_served_tail_band_is_ordered_aligned_and_unfloored():
    d, _ = _served()
    tail = (d.get("accountability") or {}).get("salary_path", {}).get("contract_tail") or {}
    if not tail.get("enabled") or not tail.get("band"):
        pytest.skip("contract tail band off")
    assert tail.get("band_p10_floor") is False
    H = d["horizon"]
    rows = [v for v in d["vets"] if v.get("warTail")]
    assert rows and tail.get("band_rows") == len(rows) == tail.get("rows")
    order, step = [], []
    for v in rows:
        wt, lt, ht = v["warTail"], v.get("warP10Tail"), v.get("warP90Tail")
        assert isinstance(lt, list) and isinstance(ht, list) and len(lt) == len(ht) == len(wt), v["key"]
        for i, w in enumerate(wt):
            if w is None:
                assert lt[i] is None and ht[i] is None, v["key"]
                continue
            if not (lt[i] <= w + 1e-9 <= ht[i] + 2e-9):
                order.append((v["key"], i, lt[i], w, ht[i]))
            assert str(lt[i]) != "-0.0", v["key"]
        # THE STEP the owner removed: a negative 2031 P10 never becomes a 2032
        # P10 of zero under a positive point. A chained value that is itself
        # within half a print step of zero prints as 0.0 with no floor at work
        # (xander_bogaerts: -0.04 x 0.015 / 0.133 = -0.0045, printed 0.0), so
        # the step is read where the chain on the served seasons (the scale
        # branch, else the ratio chain's 0.7) prints below -0.01.
        l5 = v["warP10"][H - 1]
        if l5 is not None and l5 < 0 and wt[0] is not None and wt[0] > 0 and lt[0] >= 0:
            c5 = float(v["warChamp"][H - 1])
            ct = (v.get("warChampTail") or [None])[0]
            chained = l5 * float(ct) / c5 if (c5 > 0.05 and ct is not None) else l5 * 0.7
            if chained < -0.01:
                step.append((v["key"], l5, lt[0], wt[0]))
    assert not order, order
    assert not step, step


def test_served_trade_range_brackets_the_value_and_has_no_negative_width():
    d, tv = _served()
    keys = {v["key"] for v in d["vets"] if v.get("warTail")}
    if not keys:
        pytest.skip("no contract tail rows")
    seen, bad = 0, []
    for p in tv["players"]:
        k = p.get("proj_key") or p.get("player_key")
        if p.get("band_basis") != "projection":
            continue
        lo, hi, pt = p.get("trade_value_lo"), p.get("trade_value_hi"), p.get("trade_value_mm")
        if None in (lo, hi, pt):
            continue
        if k in keys:
            seen += 1
        if hi < lo or not (lo <= pt <= hi):
            bad.append((k, lo, pt, hi))
    assert seen >= len(keys) - 2, (seen, len(keys))
    assert not bad, bad

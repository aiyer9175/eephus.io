"""/fa/'s future classes extend a path past the projection on the same curve as
/projections/ (owner answer Q-A (b), 2026-09-30).

A 2028 or 2029 class member's path overlays the projection's champion mean
(warChamp) for the seasons it reaches and, past 2031, now chains along the
projection's champion aging curve (warChamp + warChampTail, the curve
proj_export's contract tail chains on) with fa_market.chain_aging_tail, from
this page's own 2031 value. Before, it decayed the last value at a clamped
last-two-season ratio. P10/P90 chain at the FA module's anchors (0.6 / 1.4 x);
the P10 takes the same no-floor rule as the /projections/ tail range, which is
moot here because the overlaid head is floored at 0.

ONE CURVE, NOT ONE LEVEL. /fa/ prices on the champion mean and /projections/
on the lifted median head, so the two pages already print different WAR for
the same 2027-2031 season (the /fa/ note says so). Chained along one curve, a
season past 2031 differs between the pages in exactly the proportion their
2031 values do: Carlos Correa's 2032 reads 0.00 on /fa/ (his champion 2031 is
0.00) and 0.02 on /projections/ (his served 2031 is 0.03)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fa_export as fe
import fa_market as fm

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _path(n=10):
    champ = [round(3.0 - 0.3 * t, 2) for t in range(n)]
    return {"war_by_year": list(champ), "war_by_year_champ": list(champ),
            "war_by_year_p10": [0.0] * n, "war_by_year_p90": [5.0] * n,
            "war_y1": champ[0], "war_total": sum(champ)}


def _pv():
    return {"warChamp": [4.0, 3.8, 3.6, 3.2, 2.8], "war": [3.9, 3.7, 3.5, 3.1, 2.7],
            "warP10": [2.0, 1.8, 1.5, 1.0, 0.5], "warP90": [6.0, 5.8, 5.6, 5.2, 4.8],
            "warChampTail": [2.4, 2.0, 1.6, 1.2, 0.8, 0.4, 0.2, 0.1, 0.05, 0.0]}


def test_the_chained_tail_is_the_projection_champion_curve(monkeypatch):
    monkeypatch.setattr(fe, "FUTURE_CLASS_TAIL", "chained")
    path, pv = _path(), _pv()
    assert fe._apply_proj_override(path, pv, 2029, 2027)
    champ = pv["warChamp"] + pv["warChampTail"]
    # the head is warChamp from the class year; past 2031 the scale is
    # 2.8 / 2.8 = 1, so the path IS the projection's champion mean
    assert path["war_by_year"][:3] == [3.6, 3.2, 2.8]
    assert path["war_by_year"][3:8] == [2.4, 2.0, 1.6, 1.2, 0.8]
    assert path["war_by_year"] == fm.chain_aging_tail([3.6, 3.2, 2.8], champ[2:12], 3, 10)
    # P10 / P90 at the FA anchors: the spread moved onto the mean, then chained
    p10_head = [round(c + (q - m), 2) for c, q, m in zip(pv["warChamp"], pv["warP10"], pv["war"])][2:]
    assert path["war_by_year_p10"] == fm.chain_aging_tail(
        [max(0.0, x) for x in p10_head], [0.6 * c for c in champ[2:12]], 3, 10, floor=False)
    lo, hi, w = path["war_by_year_p10"], path["war_by_year_p90"], path["war_by_year"]
    assert all(lo[t] <= w[t] <= hi[t] for t in range(10))
    assert path["war_total"] == round(sum(w), 2)


def test_past_the_projection_champion_it_continues_on_this_path_s_champion_ratio(monkeypatch):
    monkeypatch.setattr(fe, "FUTURE_CLASS_TAIL", "chained")
    pv = dict(_pv(), warChampTail=[2.4, 2.2, 2.0, 1.8, 1.6, 1.4, 1.2, 1.0, 0.9, 0.8])
    fc = [round(3.0 * 0.9 ** t, 4) for t in range(15)]
    path = {"war_by_year": list(fc), "war_by_year_champ": list(fc)}
    cs = fe._future_tail_champion(pv, path, 2)
    # 13 projection champion seasons from 2029 (2029-2041), then 2042 and 2043
    # on this path's own champion ratio (0.9 a season)
    assert cs[:13] == [3.6, 3.2, 2.8, 2.4, 2.2, 2.0, 1.8, 1.6, 1.4, 1.2, 1.0, 0.9, 0.8]
    assert cs[13:] == pytest.approx([0.8 * 0.9, 0.8 * 0.9 * 0.9], rel=1e-3)


def test_ratio_is_the_revert_and_a_row_without_the_champion_tail_takes_it(monkeypatch):
    def legacy(seq, n):
        r = max(0.5, min(0.95, seq[-1] / seq[-2]))
        out, last = list(seq), seq[-1]
        while len(out) < n:
            last = round(max(0.0, last * r), 2)
            out.append(last)
        return out
    monkeypatch.setattr(fe, "FUTURE_CLASS_TAIL", "ratio")
    path = _path()
    fe._apply_proj_override(path, _pv(), 2029, 2027)
    assert path["war_by_year"] == legacy([3.6, 3.2, 2.8], 10)
    monkeypatch.setattr(fe, "FUTURE_CLASS_TAIL", "chained")
    pv = _pv()
    pv.pop("warChampTail")
    path = _path()
    fe._apply_proj_override(path, pv, 2029, 2027)
    assert path["war_by_year"] == legacy([3.6, 3.2, 2.8], 10)


# ---------------------------------------------------------- served pages --
def _served():
    files = [DATA / "mlb_projections.json", DATA / "fa_class_2028.json", DATA / "fa_class_2029.json"]
    if not all(f.exists() for f in files):
        pytest.skip("mlb_projections / fa_class_2028 / fa_class_2029 not built")
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def test_served_future_classes_chain_on_the_projection_champion_curve():
    if fe.FUTURE_CLASS_TAIL != "chained":
        pytest.skip("future class tail reverted")
    proj, c28, c29 = _served()
    by_key = {v["key"]: v for v in proj["vets"]}
    first, H = proj["first_season"], proj["horizon"]
    checked, bad = 0, []
    for cls in (c28, c29):
        start = cls["class_year"] - first
        for m in cls["members"]:
            v = by_key.get(m["key"])
            if m.get("warSource") != "mlb_projections" or not v or not v.get("warChampTail"):
                continue
            champ = [float(x) for x in (v["warChamp"] + v["warChampTail"])[start:]]
            head = [max(0.0, float(x)) for x in v["warChamp"][start:]]
            want = fm.chain_aging_tail(head, champ, len(head), len(m["warPath"]))
            got = m["warPath"]
            checked += 1
            if any(abs(a - b) > 0.011 for a, b in zip(got[len(head):], want[len(head):])):
                bad.append((cls["class_year"], m["key"], got, want))
    assert checked > 100, checked
    assert not bad, bad[:5]


def test_correa_2032_one_curve_on_both_pages():
    """THE PIN the owner's question named (Correa, 2029 class, 2032 his last
    guaranteed season). Each page chains its own 2031 along the same champion
    curve with the same function, so each page's 2032 is reproduced from its
    own 2031 on that curve; they agree exactly where the 2031 values agree.
    Today they do not agree at 2031 (champion mean 0.00 on /fa/, served 0.03 on
    /projections/), so 2032 reads 0.00 and 0.02."""
    proj, _, c29 = _served()
    v = next((x for x in proj["vets"] if x["key"] == "carlos_correa"), None)
    m = next((x for x in c29["members"] if x["key"] == "carlos_correa"), None)
    if v is None or m is None or m.get("warSource") != "mlb_projections" or not v.get("warTail"):
        pytest.skip("Correa is not on both pages in this build")
    first, H = proj["first_season"], proj["horizon"]
    start = c29["class_year"] - first                       # 2029 -> 2
    i32 = (first + H) - c29["class_year"]                   # 2032 on /fa/'s path
    champ_curve = [float(x) for x in v["warChamp"] + v["warChampTail"]]
    fa_2031, fa_2032 = m["warPath"][i32 - 1], m["warPath"][i32]
    pj_2031, pj_2032 = v["war"][H - 1], v["warTail"][0]
    # /fa/: its own 2031 on the projection champion curve
    assert fa_2032 == pytest.approx(
        fm.chain_aging_tail([max(0.0, x) for x in v["warChamp"][start:]], champ_curve[start:], H - start, H - start + 1)[-1],
        abs=0.011)
    # /projections/: its own 2031 on its champion curve (the contract tail seam)
    assert pj_2032 == pytest.approx(
        fm.chain_aging_tail([float(x) for x in v["war"]], champ_curve, H, H + 1)[-1], abs=0.011)
    # one curve: where the two 2031 values agree the 2032 values agree; today
    # the whole 2032 gap is the 2031 gap carried along the curve
    if abs(fa_2031 - pj_2031) < 0.005:
        assert fa_2032 == pytest.approx(pj_2032, abs=0.011)
    else:
        assert (fa_2032, pj_2032) != (None, None)
        assert (pj_2032 - fa_2032) * (pj_2031 - fa_2031) >= 0

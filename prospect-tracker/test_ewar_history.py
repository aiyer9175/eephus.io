# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ewar_history: the season stamps, the groups, CORE and FULL and the identities
(docs/ewar/EWAR_HISTORY_GATE.md), on a synthetic vintage, plus the served-artifact
pins (data/ewar_history.json, data/war_seasons.json's components block)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ewar_history as H

ROOT = Path(__file__).resolve().parent
HIT_FIELDS = ["war", "rar", "batting", "baseRunning", "fielding", "positional", "wLeague",
              "replacement", "wSb", "ubr", "wGdp", "plateAppearances"]
PIT_FIELDS = ["war", "rar", "outs"]
RPW = 10.0


def _hit(war_runs, bsr, wsb, ubr, wgdp, frm, pa):
    """A hitting row whose components and RAR are consistent at RPW 10, with a
    framing residual `frm` beyond the listed components."""
    batting, fielding, positional, league, repl = war_runs, 1.0, 2.0, 0.5, 10.0
    comps = batting + bsr + fielding + positional + league + repl
    rar = comps + frm
    return [rar / RPW, rar, batting, bsr, fielding, positional, league, repl, wsb, ubr, wgdp, pa]


def _season(hit_rows: dict, pit_rows: dict) -> dict:
    return {"hitting": {"status": "frozen", "fields": HIT_FIELDS, "rows": hit_rows},
            "pitching": {"status": "frozen", "fields": PIT_FIELDS, "rows": pit_rows}}


def _vintage() -> dict:
    pit = {"9001": [2.0, 20.0, 540], "9002": [1.0, 10.0, 300], "9003": [-0.5, -5.0, 60]}
    seasons = {
        # 2000: steals only, no framing: CORE equals FULL exactly
        "2000": _season({"1": _hit(5.0, 1.0, 1.0, 0.0, 0.0, 0.0002, 600),
                         "2": _hit(-3.0, -0.5, -0.5, 0.0, 0.0, -0.0003, 400),
                         "3": _hit(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 300)}, pit),
        # 2002: UBR and wGDP, no framing
        "2002": _season({"1": _hit(5.0, 2.0, 1.0, 0.6, 0.4, 0.0, 600),
                         "2": _hit(-3.0, -1.0, -0.5, -0.3, -0.2, 0.0, 400),
                         "3": _hit(1.0, 0.3, 0.0, 0.2, 0.1, 0.0, 300)}, pit),
        # 2008: framing on a catcher, BsR not equal to its parts (the other label)
        "2008": _season({"1": _hit(5.0, 2.0, 1.0, 0.1, 0.1, 0.0, 600),
                         "2": _hit(-3.0, -1.0, -0.5, 0.0, 0.0, 0.0, 400),
                         "3": _hit(1.0, 0.3, 0.0, 0.0, 0.0, 8.0, 300)}, pit),
    }
    return {"vintage_id": "test", "seasons": seasons}


def _v3(r2_rows: dict | None = None, dh: dict | None = None) -> dict:
    players: dict = {}
    for (mid, s, side), v in (dh or {}).items():
        blk = players.setdefault(str(mid), {}).setdefault(str(s), {"dh": {}, "dr": {}})
        blk["dh"][side] = v
        blk["dr"][side] = blk["dr"].get(side, 0.0) + v
    for (mid, s), v in (r2_rows or {}).items():
        blk = players.setdefault(str(mid), {}).setdefault(str(s), {"dh": {}, "dr": {}})
        blk["dr"]["pit"] = blk["dr"].get("pit", blk["dh"].get("pit", 0.0)) + v
    checks = {"2000": {}, "2002": {}, "2008": {"r2_rows": len(r2_rows or {}),
                                                "r2_rounding_bound": 1e-6}}
    return {"generated_at": "t", "players": players, "checks": checks}


@pytest.fixture(autouse=True)
def _fresh():
    H.reset()
    yield
    H.reset()


def test_first_season_is_the_vintage_first_accepted_season():
    import fwar_vintage
    assert H.FIRST_SEASON == fwar_vintage.FIRST_ACCEPTED_SEASON == 2000


def test_stamps_are_measured_per_season():
    st = H.stamps(_vintage(), _v3())
    assert "bsr_rest" not in st[2000]["headline"] and "framing" not in st[2000]["headline"]
    assert st[2000]["bsr_label"] is None
    assert "bsr_rest" in st[2002]["headline"] and st[2002]["bsr_label"] == H.BSR_LABEL_UBR
    assert "framing" not in st[2002]["headline"]
    assert "framing" in st[2008]["headline"] and st[2008]["bsr_label"] == H.BSR_LABEL_OTHER
    assert "r2" not in st[2008]["realized"]          # no R2 rows in this fixture
    # rounding residuals below the threshold are not a part (amendment 9.1)
    assert st[2000]["measured"]["framing_rows"] == 0


def test_groups_and_sentences():
    v3 = _v3(r2_rows={(9001, 2008): 0.3, (9002, 2008): -0.2, (9003, 2008): -0.1})
    g = H.season_groups(_vintage(), v3)
    assert [(x["first"], x["last"]) for x in g] == [(2000, 2000), (2002, 2002), (2008, 2008)]
    assert g[0]["missing"] == ["bsr_rest", "framing", "r2"]
    assert "steals only" in g[0]["short"] and "framing" in g[0]["short"]
    assert "carries it from 2008" in g[0]["short"]
    assert g[0]["short_headline"] and "realized" not in g[0]["short_headline"]
    assert g[-1]["missing"] == [] and g[-1]["short"] == ""
    assert g[-1]["text"].endswith("eWAR realized prices pitchers on runs allowed.")
    assert g[0]["text"].endswith("eWAR realized equals eWAR.")
    for x in g:
        assert "—" not in x["text"] and "–" not in x["text"]


def test_merged_shorts_join_neighbouring_groups_with_the_same_gap():
    v3 = _v3(r2_rows={(9001, 2008): 0.3, (9002, 2008): -0.2, (9003, 2008): -0.1})
    g = H.season_groups(_vintage(), v3)
    # 2000 and 2002 both lack R2 but are not neighbours (2001 is absent here)
    assert H.merged_shorts(g, [2002], "realized") == [
        "2002: eWAR realized equals eWAR (its runs-allowed pitching starts in 2008)."]
    assert H.merged_shorts(g, [2008], "realized") == []
    assert len(H.merged_shorts(g, [2000, 2002, 2008], "headline")) == 2
    g2 = [dict(x) for x in g]
    g2[0]["last"] = 2001                         # make 2000-2001 and 2002 neighbours
    assert H.merged_shorts(g2, [2002], "realized") == [
        "2000-2002: eWAR realized equals eWAR (its runs-allowed pitching starts in 2008)."]


def test_eabs_is_never_missing_before_its_first_season():
    vin = _vintage()
    v3 = _v3(dh={(1, 2008, "bat"): 0.05, (2, 2008, "bat"): -0.05})
    v3["checks"]["2008"]["abs_receipt"] = {"challenges": 2}
    g = H.season_groups(vin, v3)
    assert "eabs" in g[-1]["headline"]
    assert all("eabs" not in x["missing"] for x in g)


def test_core_and_full_identities_hold_and_side_sums_are_fwar():
    v3 = _v3(r2_rows={(9001, 2008): 0.3, (9002, 2008): -0.2, (9003, 2008): -0.1})
    pay = H.build(_vintage(), v3, log=lambda *a: None)
    for s, blk in pay["seasons"].items():
        ident = blk["identities"]
        assert ident["max_row_error"]["row_headline"] <= H.TOL_ROW
        for side in ("bat", "pit"):
            assert abs(ident["side_sums"][side]["core_minus_fwar"]) <= H.TOL_SIDE
    assert pay["seasons"]["2000"]["identities"]["core_equals_full_exactly"] is True
    assert pay["seasons"]["2008"]["identities"]["core_equals_full_exactly"] is False
    gap = pay["seasons"]["2008"]["gap"]
    assert set(gap["bat"]) == {"bsr_rest", "framing", "total_headline"}
    assert set(gap["pit"]) == {"r2", "total_headline", "total_realized"}
    # nothing per player is written (gate part 5)
    assert "players" not in pay
    assert all(set(b) == {"stamp", "rpw_fg", "identities", "gap"} for b in pay["seasons"].values())
    assert '"full"' not in json.dumps(pay)


def test_core_removes_the_later_parts_at_fangraphs_rpw():
    cf = H.core_full(2002, _vintage(), _v3())
    assert cf["rpw_fg"] == pytest.approx(RPW)
    rows = cf["bat"]
    # the rest of baserunning is re-centred per PA and taken out of fWAR
    raw = {1: 1.0, 2: -0.5, 3: 0.3}
    pa = {1: 600, 2: 400, 3: 300}
    rate = sum(raw.values()) / sum(pa.values())
    for m in raw:
        assert rows[m]["bsr_rest"] == pytest.approx((raw[m] - pa[m] * rate) / RPW)
        assert rows[m]["core"] == pytest.approx(rows[m]["war"] - rows[m]["bsr_rest"])
        assert rows[m]["full"] == rows[m]["war"]


def test_a_departure_that_breaks_the_side_sum_refuses():
    v3 = _v3(dh={(1, 2002, "bat"): 0.5})       # not zero-sum
    with pytest.raises(H.EwarHistoryRefusal):
        H.build(_vintage(), v3, log=lambda *a: None)


# --- the served artifacts --------------------------------------------------

def _served(name: str) -> dict:
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} is not built here")
    return json.loads(p.read_text(encoding="utf-8"))


def test_served_history_record_covers_2000_to_the_last_vintage_season():
    doc = _served("ewar_history.json")
    assert doc["first_season"] == 2000
    assert doc["registration"] == "docs/ewar/EWAR_HISTORY_GATE.md"
    assert [g["first"] for g in doc["groups"]][0] == 2000
    seasons = sorted(int(s) for s in doc["seasons"])
    assert seasons == list(range(2000, doc["last_season"] + 1))
    for s, blk in doc["seasons"].items():
        assert blk["identities"]["max_row_error"]["row_headline"] <= H.TOL_ROW
    assert "players" not in doc


def test_served_substrate_spans_the_history_with_its_stamps():
    sub = _served("war_seasons.json")
    if sub.get("war_provider") != "ewar_v3":
        pytest.skip("the substrate is not on eWAR")
    assert sub["seasons"][0] == 2000
    comp = sub.get("components") or {}
    assert comp.get("first_season") == 2000
    spans = [(g["first"], g["last"]) for g in comp["groups"]]
    assert spans[0][0] == 2000 and spans[-1][1] == sub["seasons"][-1]
    # a board stamp never names the realized series' part
    assert all("r2" not in g["missing"] for g in comp["groups"])

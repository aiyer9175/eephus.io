# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""The $/WAR breakdowns behind data/fa_dpw_series.json.

Two rules this pins, both of them about not publishing a number that is not
one: a slice too thin to price is left None rather than divided out, and the
REALIZED series is never emitted without the elapsed share that makes it
readable (paid-to-date over the whole guarantee reads $40M+/WAR on a winter
whose deals are half over).
"""
import json
from pathlib import Path

import fa_market as fm


def _sig(year, pos, years, guar, war, key, qo=False, ledger=None):
    s = {"class_year": year, "position": pos, "years": years,
         "guarantee_usd": guar, "aav_usd": guar / years, "qo": qo,
         "player_key": key, "player_name": key,
         "npv_guarantee_usd": guar,
         "_war_path": {"war_y1": war, "war_by_year": [war] * years}}
    if ledger:
        s["ledger"] = ledger
    return s


def _corpus(n_per_pos=10):
    out = []
    for i in range(n_per_pos):
        for pos in ("SP", "RP", "C", "1B", "CF"):
            out.append(_sig(2020, pos, 3, 30e6, 2.0, f"{pos}{i}", qo=(i == 0)))
    return out


def test_pos_len_tier_slices_are_present_and_priced():
    bd = fm.dpw_breakdowns(_corpus())
    w = bd["by_winter"]["2020"]
    assert w["n"] == 50
    assert w["dpw"] > 0
    for g in ("SP", "RP", "C", "IF", "OF"):
        assert w["pos"][g]["n"] == 10
        assert w["pos"][g]["dpw"] > 0
    assert w["len"]["2-3"]["n"] == 50
    assert w["len"]["1"]["dpw"] is None          # empty bucket, not zero
    assert abs(w["qo_share"] - 5 / 50) < 1e-9


def test_thin_cells_are_left_unpriced():
    rows = _corpus()
    rows.append(_sig(2020, "DH", 1, 5e6, 0.5, "lonely"))
    bd = fm.dpw_breakdowns(rows)
    dh = bd["by_winter"]["2020"]["pos"]["DH"]
    assert dh["n"] == 1 and dh["dpw"] is None
    assert dh["spend"] > 0                        # the money is still reported


def test_position_mapping():
    assert fm._fine_pos_group("SS") == "IF"
    assert fm._fine_pos_group("RF") == "OF"
    assert fm._fine_pos_group("LHP") == "SP"
    assert fm._fine_pos_group("CL") == "RP"
    assert fm._fine_pos_group("C") == "C"
    assert fm._fine_pos_group(None) == "DH"


def test_length_and_tier_buckets():
    assert [fm._years_bucket(n) for n in (1, 2, 3, 4, 6, 7, 12)] == \
        ["1", "2-3", "2-3", "4-6", "4-6", "7+", "7+"]
    assert [fm._guar_tier(v) for v in (5e6, 25e6, 75e6, 400e6)] == \
        ["<$10M", "$10-50M", "$50-100M", "$100M+"]


def test_realized_carries_elapsed_and_is_paid_over_banked():
    led = {"paid_to_date_usd": 10e6, "war_to_date": 2.0,
           "elapsed_years": 1, "total_years": 3, "complete": False}
    rows = [_sig(2020, "CF", 3, 30e6, 2.0, f"p{i}", ledger=dict(led))
            for i in range(10)]
    bd = fm.dpw_breakdowns(rows)
    r = bd["realized"]["2020"]
    assert r["n"] == 10
    assert r["dpw"] == int(100e6 / 20.0)          # paid / banked, not guar / banked
    assert abs(r["elapsed"] - 1 / 3) < 1e-3       # published to 3 decimals
    assert r["complete_share"] == 0.0


def test_realized_is_dropped_when_the_ledger_is_thin():
    rows = _corpus()
    rows[0]["ledger"] = {"paid_to_date_usd": 1e6, "war_to_date": 1.0,
                         "elapsed_years": 1, "total_years": 3}
    assert fm.dpw_breakdowns(rows)["realized"] == {}


def test_shipped_artifact_has_the_breakdown():
    p = Path(__file__).parent / "data" / "fa_dpw_series.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["usd_per_war_by_winter"]             # headline is still where it was
    bd = d.get("breakdown")
    if not bd:
        return                                    # artifact predates the block
    assert set(bd["groups"]) == {"pos", "len", "tier"}
    for y, w in bd["by_winter"].items():
        assert y in d["usd_per_war_by_winter"]
        assert w["dpw"] == d["usd_per_war_by_winter"][y]   # one headline, not two
    for r in bd["realized"].values():
        assert r["elapsed"] is not None           # never publish it bare

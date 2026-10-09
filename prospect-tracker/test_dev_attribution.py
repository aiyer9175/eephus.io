# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Development attribution (VAL_4, owner answer FP2-4 2026-09-25).

Credit for a player's development goes to the club that held him when the
growth happened; the signing club is credited with his value at signing; a
graduate's realized value is apportioned by those shares (design:
docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md). These tests pin:

  * a list pair that spans a trade is split by days between the two clubs;
  * a traded prospect's growth is credited to the club where it happened;
  * the shares sum to one; a tenure that lowered the grade earns zero; an
    unaffiliated stretch (released) credits nobody;
  * Tarik Skubal (drafted and developed by DET, traded to LAD 2026-08-02)
    credits DET, not LAD, in the module, on the served debuts rows and in the
    farm grade's graduate leaves;
  * the export credits a graduate's WAR to the club that developed him.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import dev_attribution as DA

ROOT = Path(__file__).resolve().parent
W = {40: 0.5, 45: 1.5, 50: 3.0, 55: 6.0, 60: 12.0}


def _w(fv):
    return W.get(int(fv)) if fv is not None else None


def _tx(d, code, to_id=None, to_name=""):
    return {"date": d, "type_code": code, "to_team_id": to_id, "to_team_name": to_name}


TEAM_ORG = {(116, y): "DET" for y in range(2015, 2027)}
TEAM_ORG.update({(119, y): "LAD" for y in range(2015, 2027)})
TEAM_ORG.update({(582, 2018): "DET", (582, 2019): "DET"})


def test_tenures_follow_signings_and_trades_and_ignore_assignments():
    events = DA.org_events([
        _tx("2018-05-01", "REL", None, "Cotuit Kettleers"),     # amateur side, before any club
        _tx("2018-06-20", "SGN", 116, "Detroit Tigers"),
        _tx("2018-06-28", "ASG", 582, "West Michigan Whitecaps"),
        _tx("2020-07-31", "TR", 119, "Los Angeles Dodgers"),
    ], DA.make_resolver(TEAM_ORG))
    cal = DA.tenures_from_events(events, "2019-01-01", "2021-06-01")
    assert [t.as_list() for t in cal] == [["DET", "2018-06-20", "2020-07-31"],
                                         ["LAD", "2020-07-31", "2021-06-01"]]


def test_a_release_opens_an_unaffiliated_stretch():
    events = DA.org_events([
        _tx("2018-06-20", "SGN", 116, "Detroit Tigers"),
        _tx("2020-03-01", "REL", None, "Detroit Tigers"),
        _tx("2020-06-01", "SFA", 119, "Los Angeles Dodgers"),
    ], DA.make_resolver(TEAM_ORG))
    cal = DA.tenures_from_events(events, "2018-07-01", "2021-01-01")
    assert [t.org for t in cal] == ["DET", None, "LAD"]


def test_a_pair_spanning_a_trade_is_split_by_days():
    cal = [DA.Tenure("DET", "2020-01-01", "2020-04-11"), DA.Tenure("LAD", "2020-04-11", "2021-01-01")]
    parts = dict(DA.split_pair("2020-01-01", "2020-05-21", cal))
    assert parts == pytest.approx({0: 101 / 141, 1: 40 / 141})
    assert dict(DA.split_pair("2020-06-01", "2020-09-01", cal)) == {1: 1.0}


def _attribute(obs, txs, end="2023-01-01", status="active", current="LAD"):
    info = DA.PlayerInfo("p", current, status, end if status == "debuted" else None)
    return DA.attribute_player("p", info, obs, txs, [], None, DA.make_resolver(TEAM_ORG), _w, end)


def test_a_traded_prospects_growth_is_credited_where_it_happened():
    obs = {"fangraphs": [("2019-01-01", 40.0, None), ("2020-01-01", 50.0, None), ("2021-01-01", 55.0, None)],
           "mlb_pipeline": [("2019-02-01", 40.0, None), ("2020-02-01", 50.0, None)]}
    txs = [_tx("2018-06-20", "SGN", 116, "Detroit Tigers"), _tx("2020-07-01", "TR", 119, "Los Angeles Dodgers")]
    pa = _attribute(obs, txs)
    assert pa.basis == "transactions" and pa.signing_org == "DET"
    assert [t.org for t in pa.tenures] == ["DET", "LAD"]
    # FanGraphs 2020-01-01 -> 2021-01-01 (+3.0 WAR scale) spans the trade:
    # 182 of 366 days at DET, 184 at LAD.
    det_fg = 2.5 + 3.0 * 182 / 366
    det_mlb = 2.5
    lad_fg = 3.0 * 184 / 366
    det_g = (det_fg + det_mlb) / 2          # both outlets saw the DET tenure
    lad_g = lad_fg                          # only FanGraphs saw the LAD tenure
    assert pa.growth == pytest.approx([det_g, lad_g])
    total = 0.5 + det_g + lad_g             # V0 = W(40) to the signing club
    shares = dict(pa.shares)
    assert shares["DET"] == pytest.approx((0.5 + det_g) / total, abs=1e-4)
    assert shares["LAD"] == pytest.approx(lad_g / total, abs=1e-4)
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-9)


def test_a_tenure_that_lowered_the_grade_earns_no_share_and_unaffiliated_growth_credits_nobody():
    obs = {"fangraphs": [("2019-01-01", 50.0, None), ("2019-12-01", 45.0, None),
                         ("2020-05-01", 55.0, None), ("2020-12-01", 60.0, None)]}
    txs = [_tx("2018-06-20", "SGN", 116, "Detroit Tigers"), _tx("2019-12-15", "REL", None, "Detroit Tigers"),
           _tx("2020-06-01", "SFA", 119, "Los Angeles Dodgers")]
    pa = _attribute(obs, txs)
    assert [t.org for t in pa.tenures] == ["DET", None, "LAD"]
    assert pa.growth[0] < 0
    shares = dict(pa.shares)
    assert set(shares) == {"DET", "LAD"}                    # DET keeps V0 only
    assert shares["DET"] == pytest.approx(3.0 / (3.0 + pa.growth[2]), abs=1e-4)
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-9)


def test_no_positive_credit_gives_the_signing_club_the_whole_share():
    assert DA.development_shares(0.0, [DA.Tenure("DET", "2019-01-01", "2020-01-01")], [-1.0], "DET") == [("DET", 1.0)]


def test_tool_growth_is_credited_by_tenure():
    obs = {"fangraphs": [("2019-01-01", 45.0, {"hit": 40.0}), ("2020-01-01", 45.0, {"hit": 50.0}),
                         ("2021-01-01", 45.0, {"hit": 55.0})]}
    txs = [_tx("2018-06-20", "SGN", 116, "Detroit Tigers"), _tx("2020-01-01", "TR", 119, "Los Angeles Dodgers")]
    pa = _attribute(obs, txs)
    assert pa.tool_growth["DET"]["hit"] == pytest.approx(2.5)
    assert pa.tool_growth["LAD"]["hit"] == pytest.approx(3.0)


# --------------------------------------------------------------------------
# On the database and the served rows
# --------------------------------------------------------------------------

DB = ROOT / "prospects.db"


def _db():
    if not DB.exists():
        pytest.skip("prospects.db absent")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.execute("SELECT 1 FROM player_transactions LIMIT 1")
    except sqlite3.OperationalError:
        pytest.skip("player_transactions absent")
    return con


def test_tarik_skubal_credits_det_not_lad_in_the_module():
    con = _db()
    info = DA.PlayerInfo("tarik_skubal", "LAD", "debuted", "2020-08-18", "DET")
    att = DA.build([info], con=con)
    pa = att.get("tarik_skubal")
    if pa is None or pa.basis == "none":
        pytest.skip("Skubal has no attribution inputs in this database")
    assert pa.signing_org == "DET"
    assert dict(pa.shares) == {"DET": 1.0}
    assert all(t.org == "DET" for t in pa.tenures)
    assert att.graduate_credit("tarik_skubal", "LAD") == [("DET", 1.0, True)]


def _served(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"{name} absent")
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else (d.get("players") or [])


def test_served_graduate_rows_carry_shares_that_sum_to_one():
    rows = _served("debuts_lite.json")
    with_credit = [g for g in rows if g.get("dev_credit")]
    if not with_credit:
        pytest.skip("debuts_lite.json predates VAL_4")
    for g in with_credit:
        shares = g["dev_credit"]["shares"]
        assert shares and abs(sum(s for _, s in shares) - 1.0) < 1e-6, g["player_key"]
        assert all(s > 0 for _, s in shares), g["player_key"]
    sk = next((g for g in with_credit if g["player_key"] == "tarik_skubal"), None)
    if sk is not None:
        assert sk["dev_credit"]["shares"] == [["DET", 1.0]]
        assert sk["org"] == "LAD"                       # "now with" stays the current club


def test_served_farm_graduate_leaves_credit_the_developing_club():
    """The ledger graduates block lists Skubal under DET with share 1 and now_with
    LAD, and not under LAD."""
    shard_dir = ROOT / "data" / "ledger_clubs"
    if not (shard_dir / "DET.json").exists():
        pytest.skip("ledger shards absent")
    board = json.loads((ROOT / "data" / "ledger_board.json").read_text(encoding="utf-8"))
    cols = board["columns"]["farm.graduates"]
    if "dev_share" not in cols:
        pytest.skip("ledger board predates VAL_4")
    ki, si, ni = cols.index("key"), cols.index("dev_share"), cols.index("now_with")
    det = json.loads((shard_dir / "DET.json").read_text(encoding="utf-8"))["farm"]["graduates"]
    lad = json.loads((shard_dir / "LAD.json").read_text(encoding="utf-8"))["farm"]["graduates"]
    det_rows = {r[ki]: r for r in det}
    if "tarik_skubal" in det_rows:
        assert det_rows["tarik_skubal"][si] == 1.0 and det_rows["tarik_skubal"][ni] == "LAD"
        assert "tarik_skubal" not in {r[ki] for r in lad}


# --------------------------------------------------------------------------
# End to end through the export
# --------------------------------------------------------------------------

def test_the_export_credits_a_graduates_war_to_the_club_that_developed_him(tmp_path, monkeypatch):
    import storage
    from consensus import build_timeseries
    from scrapers import Snapshot

    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()

    def snap(key, d, org, fv, status="active", src="fangraphs"):
        return Snapshot(source=src, snapshot_date=d, interval_label=f"{src} {d}", player_key=key,
                        player_name=key.replace("_", " ").title(), position="SP", org=org,
                        rank=1, fv=fv, status=status)

    rows = [
        # the graduate: developed by DET, debuted 2020-08-18, traded to LAD after his debut
        snap("grad_one", "2019-01-01", "DET", 45.0), snap("grad_one", "2020-02-01", "DET", 55.0),
        snap("grad_one", "2020-08-18", "DET", None, status="debuted", src="auto_detect"),
        # one active prospect per club so both clubs carry a farm entry
        snap("det_kid", "2025-02-01", "DET", 45.0), snap("det_kid", "2026-02-01", "DET", 50.0),
        snap("lad_kid", "2025-02-01", "LAD", 45.0), snap("lad_kid", "2026-02-01", "LAD", 50.0),
    ]
    storage.insert_snapshots(rows)
    storage.upsert_player_transactions({"grad_one": [
        {"date": "2018-06-20", "type_code": "SGN", "to_team_id": 116, "to_team_name": "Detroit Tigers", "id": 1},
        {"date": "2026-08-02", "type_code": "TR", "to_team_id": 119, "to_team_name": "Los Angeles Dodgers", "id": 2},
    ]})
    ts = build_timeseries(storage.load_all_snapshots())
    for p in ts:
        if p.player_key == "grad_one":
            p.org = "LAD"                                # his club today
            p.status = "debuted"
            p.debut_date = "2020-08-18"
    out = tmp_path / "out.json"
    storage.export_timeseries_json(
        ts, out, career_war={"grad_one": {"career_war": 20.0, "war_per_yr": 4.0, "war_seasons_count": 5,
                                          "seasons": {"2021": 4.0, "2022": 4.0, "2023": 4.0, "2024": 4.0, "2025": 4.0}}})
    payload = storage.load_export_unified(out)
    orgs = {o["org"]: o for o in payload["org_summary"]}
    assert {"DET", "LAD"} <= set(orgs)
    det = orgs["DET"]["financial_roi"]["total_career_war_all_grads"]
    lad = orgs["LAD"]["financial_roi"]["total_career_war_all_grads"]
    assert det == pytest.approx(20.0) and lad == pytest.approx(0.0)
    debuts = json.loads((tmp_path / "debuts.json").read_text(encoding="utf-8"))
    g = next(d for d in debuts if d["player_key"] == "grad_one")
    assert g["dev_credit"]["shares"] == [["DET", 1.0]] and g["org"] == "LAD"

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M10_SERVICE_TIME_ENGINE: the CBA service-day count, its validation against
published service time, and the debuted-value engine pricing on it.

Fixtures build transaction tuples in service_time's normalized shape
(date, id, typeCode, lowercased description, from_team_id, to_team_id). Team 147
is an MLB club (New York Yankees), 531 a minor league club.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import service_time as st
import value_framework as vf

ROOT = Path(__file__).parent
MLB, MILB = 147, 531


def tx(d, i, code, desc, frm=None, to=None):
    return (date.fromisoformat(d), i, code, desc.lower(), frm, to)


def _season(y):
    return st.season_calendar()[y]


# --- the day count ---------------------------------------------------------------------
def test_full_season_on_the_active_roster_is_one_year():
    evs = [tx("2023-01-10", 1, "SE", "Yankees selected the contract of RHP A from Scranton.", MILB, MLB)]
    c = st.count(evs, _season(2023)[1])
    assert c["by_season"] == {2023: 172}
    assert c["decimal"] == 1.0 and st.token(c["total_days"]) == "1.000"


def test_injured_list_days_accrue_and_minor_league_il_does_not():
    o, e = _season(2023)
    evs = [tx("2023-01-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB),
           tx("2023-05-01", 2, "SC", "Yankees placed RHP A on the 60-day injured list. Elbow.", None, MLB)]
    assert st.count(evs, e)["by_season"][2023] == 172
    # optioned on 1 May, then hurt in the minors: the minor club's placement is not service
    evs2 = [tx("2023-01-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB),
            tx("2023-05-01", 2, "OPT", "Yankees optioned RHP A to Scranton.", MLB, MILB),
            tx("2023-05-03", 3, "SC", "Scranton placed RHP A on the 7-day injured list.", None, MILB)]
    assert st.count(evs2, e)["by_season"][2023] == (date(2023, 5, 1) - o).days


def test_option_days_do_not_count_unless_under_twenty():
    o, e = _season(2023)
    base = [tx("2023-01-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB)]
    long_opt = base + [tx("2023-06-01", 2, "OPT", "Yankees optioned RHP A to Scranton.", MLB, MILB),
                       tx("2023-07-01", 3, "CU", "Yankees recalled RHP A from Scranton.", MILB, MLB)]
    assert st.count(long_opt, e)["by_season"][2023] == min(172, (e - o).days + 1 - 30)
    short_opt = base + [tx("2023-06-01", 2, "OPT", "Yankees optioned RHP A to Scranton.", MLB, MILB),
                        tx("2023-06-11", 3, "CU", "Yankees recalled RHP A from Scranton.", MILB, MLB)]
    # 10 optioned days < 20: credited back, so the season is full again
    assert st.count(short_opt, e)["by_season"][2023] == 172


def test_offseason_days_never_count_and_a_call_up_late_is_partial():
    o, e = _season(2023)
    late = [tx("2023-09-01", 1, "SE", "Yankees selected the contract of SS B.", MILB, MLB)]
    assert st.count(late, date(2023, 12, 31))["by_season"] == {2023: (e - date(2023, 9, 1)).days + 1}


def test_an_option_ends_with_the_season():
    """Optioned in August 2023 and never recalled: back on the reserve list over the
    winter, so he counts from Opening Day 2024 unless optioned again in spring."""
    o24, e24 = _season(2024)
    evs = [tx("2023-04-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB),
           tx("2023-08-01", 2, "OPT", "Yankees optioned RHP A to Scranton.", MLB, MILB)]
    assert st.count(evs, e24)["by_season"][2024] == 172
    evs.append(tx("2024-03-15", 3, "OPT", "Yankees optioned RHP A to Scranton.", MLB, MILB))
    assert 2024 not in st.count(evs, e24)["by_season"]


def test_outright_release_and_restricted_list_stop_the_clock():
    o, e = _season(2023)
    for desc, code in (("Yankees sent RHP A outright to Scranton.", "OUT"),
                       ("Yankees released RHP A.", "REL"),
                       ("Yankees placed RHP A on the restricted list.", "SC")):
        evs = [tx("2023-01-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB),
               tx("2023-06-01", 2, code, desc, MLB, MILB if code == "OUT" else MLB)]
        assert st.count(evs, e)["by_season"][2023] == (date(2023, 6, 1) - o).days, desc


def test_minor_league_and_generic_duplicate_signings_are_not_major_league_deals():
    o, e = _season(2023)
    prior = [tx("2022-04-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB),
             tx("2022-11-07", 2, "DFA", "RHP A elected free agency.", MLB, None)]
    for desc in ("Mets signed free agent RHP A to a minor league contract.",
                 "Mets signed free agent P A."):
        c = st.count(prior + [tx("2023-01-20", 3, "SFA", desc, None, 121)], e)
        assert 2023 not in c["by_season"], desc
    c = st.count(prior + [tx("2023-01-20", 3, "SFA", "Mets signed free agent RHP A.", None, 121)], e)
    assert c["by_season"][2023] == 172


def test_2020_is_prorated_and_capped():
    o, e = _season(2020)
    full = [tx("2020-07-01", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB)]
    assert st.count(full, e)["by_season"][2020] == 172
    half = [tx("2020-08-27", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB)]
    days = (e - date(2020, 8, 27)).days + 1
    assert st.count(half, e)["by_season"][2020] == round(days * 186 / 67)


def test_token_is_years_and_days_not_a_fraction():
    assert st.token(5 * 172 + 45) == "5.045"
    assert st.token(171) == "0.171"


def test_the_overlay_writes_service_fields_from_feed_and_store(monkeypatch):
    feed = {660000: [tx("2023-01-10", 1, "SE", "Yankees selected the contract of RHP A.", MILB, MLB)]}
    monkeypatch.setattr(st, "league_feed", lambda: (feed, date(2023, 7, 1)))
    store = st.store_from_rows(
        {"a_key": [{"date": "2023-08-01", "id": 2, "type_code": "OPT",
                    "description": "Yankees optioned RHP A to Scranton.",
                    "from_team_id": MLB, "to_team_id": MILB}]},
        {"a_key": "2023-12-01 00:00:00"})
    out, receipt = st.overlay_roster_status({"a_key": {"on_40_man": True}},
                                            {"a_key": 660000, "b_key": 1}, store)
    rs = out["a_key"]
    assert receipt == {"keys_with_ids": 2, "service_written": 1}
    assert rs["on_40_man"] is True
    assert rs["service_as_of"] == "2023-12-01"
    assert rs["service_days"] == (date(2023, 8, 1) - _season(2023)[0]).days
    assert rs["service_years_decimal"] == round(rs["service_days"] / 172, 3)
    assert "b_key" not in out


# --- the engine prices on it -----------------------------------------------------------------
def test_the_debuted_engine_consumes_service_years():
    kw = dict(observed_war=20.0, observed_pa=3000, age=29, draws=1500)
    fresh = vf.debuted_player_value(60, False, "SS", service_time=0.0, **kw)
    mid = vf.debuted_player_value(60, False, "SS", service_time=3.0, **kw)
    done = vf.debuted_player_value(60, False, "SS", service_time=9.0, **kw)
    cy = int(vf._config()["service_time"]["control_years"])
    assert fresh["remaining_control_years"] == cy
    assert mid["remaining_control_years"] == cy - 3
    assert done["remaining_control_years"] == 0
    assert done["trade_value_mm"] == 0.0
    assert fresh["trade_value_mm"] > mid["trade_value_mm"] > done["trade_value_mm"]
    assert done["total_value_mm"] == pytest.approx(done["realized_mm"], abs=0.06)


def test_build_debuted_payload_reads_the_written_field():
    import storage
    cw = {"career_war": 20.0, "seasons": {"2018": 5.0, "2019": 5.0, "2020": 2.0,
                                          "2021": 4.0, "2022": 4.0}}
    a = storage._build_debuted_payload(60, False, "SS", age=29, career_war=cw,
                                       roster_status={"service_years_decimal": 8.4})
    b = storage._build_debuted_payload(60, False, "SS", age=29, career_war=cw,
                                       roster_status={})
    assert a["remaining_control_years"] == 0 and a["trade_value_mm"] == 0.0
    assert b["remaining_control_years"] > 0


def test_the_export_writes_service_time_on_the_identity_join():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert "DEBUTED_SERVICE_TIME = True" in src
    i = src.index("from service_time import overlay_roster_status")
    assert src.index("_ids_for_identity[_k_id] = int(_m_id)") < i
    assert i < src.index("career_war, _cw_screen = screen_career_war_to_ids")


# --- the validation is registered and read on the holdout -------------------------------------
def test_the_eval_passed_the_tolerance_registered_before_the_read():
    ev = json.loads((ROOT / "data" / "service_time_eval.json").read_text(encoding="utf-8"))
    tol = ev["tolerance"]
    assert tol["mae_days_max"] == st.TOL_MAE_DAYS
    assert tol["rounded_year_agreement_min"] == st.TOL_ROUNDED_YEAR_AGREEMENT
    h = ev["holdout"]
    assert h["n"] >= 300
    assert ev["passed"] is (h["mae_days"] <= st.TOL_MAE_DAYS
                            and h["rounded_year_agreement"] >= st.TOL_ROUNDED_YEAR_AGREEMENT)
    assert ev["passed"] is True
    assert ev["verdict"] == "provisional"
    assert not set(st.DEV_CLASSES) & set(st.HOLDOUT_CLASSES)
    # no published third-party figure is republished in the served artifact
    assert all(set(m) == {"mlbam", "class_year", "error_days"} for m in ev["largest_misses"])


def test_the_registry_row_quotes_its_artifact():
    import model_registry as mr
    row = next(m for m in mr.load()["models"] if m["model_id"] == "service_time")
    ev = json.loads((ROOT / "data" / "service_time_eval.json").read_text(encoding="utf-8"))
    assert row["eval_artifact"] == "data/service_time_eval.json"
    assert row["verdict"] == "provisional"
    assert str(ev["holdout"]["mae_days"]) in row["summary"]
    assert str(ev["holdout"]["n"]) in row["summary"]
    assert f"{round(100 * ev['holdout']['rounded_year_agreement'], 1)}%" in row["summary"]


def test_ledger_graduates_are_not_all_priced_on_the_full_window():
    """X03-03 / M09-02: before the engine every graduate priced on the full 7-year
    window. On the served shards a graduate now prices at $0 when his control is
    spent, and more than one distinct value exists per club."""
    zero = 0
    for p in sorted((ROOT / "data" / "ledger_clubs").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        vals = [r[7] for r in d["farm"]["graduates"] if r[7] is not None]
        assert len(set(vals)) > 1, p.name
        zero += sum(1 for v in vals if v == 0.0)
    assert zero > 0

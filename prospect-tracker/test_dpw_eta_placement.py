# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""I6, round 3: the unified path dates the PRICED season from an explicit
origin; every served or read-back ETA and age placement stays on the calendar
origin in both modes. Under a monkeypatched January date (calendar year N + 1),
ON and OFF give identical eta_years, debut_age, odds-grade placement, p_bucket,
p_bust and star_odds_model on synthetic rows; surplus.eta_origin_year is
stamped only ON."""

from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

import pytest

import bayes_trade_value as bt
import dpw_testkit as kit
import efv_score
import storage
import value_framework as vf


class _January(_dt.date):
    @classmethod
    def today(cls):
        return cls(2027, 1, 15)


ROWS = [(55.0, False, "SS", 20.5, SimpleNamespace(eta_year=2029, eta_half="late")),
        (48.0, True, "SP", 22.0, SimpleNamespace(eta_year=2028, eta_half=None)),
        (62.0, False, "CF", 19.0, SimpleNamespace(eta_year=2030, eta_half="early"))]


def _placements():
    out = []
    for fv, is_pit, pos, age, eta in ROWS:
        ey = storage._eta_years_from(eta, storage.date.today().year)
        eb = bt._eta_years_to_debut({"year": eta.eta_year, "half": eta.eta_half})
        debut_age, eta_eff = vf._resolve_timing(age, ey)
        out.append({
            "eta_storage": ey, "eta_bayes": eb, "debut_age": debut_age, "eta_eff": eta_eff,
            "grade_map_age": efv_score._grade_map_age(age, ey),
            "p_bucket": vf.p_bucket_given_fv(fv, is_pit),
            "star_odds_model": vf.star_odds(fv, is_pit, pos, age=age, eta_years=ey,
                                            eta_origin=storage.date.today().year),
            "payload": {k: v for k, v in storage._build_surplus_payload(
                fv, is_pit, pos, age=age, eta_years=ey).items()
                if k in ("eta_years", "star_odds_model", "buckets", "fv_used")},
        })
    return out


def test_placements_are_identical_on_and_off_under_a_january_date(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "date", _January)
    monkeypatch.setattr(bt, "date", _January)
    off = _placements()
    with kit.unified(tmp_path):
        on = _placements()
    assert on == off
    assert off[0]["eta_storage"] == 2.5 and off[0]["eta_bayes"] == 2.5     # from 2027, not N


def test_the_origin_is_stamped_only_while_the_path_serves(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "date", _January)
    off = storage._build_surplus_payload(55.0, False, "SS", age=20.5, eta_years=2.5)
    assert "eta_origin_year" not in off
    with kit.unified(tmp_path):
        on = storage._build_surplus_payload(55.0, False, "SS", age=20.5, eta_years=2.5)
    assert on["eta_origin_year"] == 2027
    assert on["eta_years"] == off["eta_years"]
    assert on["dist"]["p_bust"] == off["dist"]["p_bust"]


def test_efv_score_reads_the_stamped_origin_else_today(monkeypatch):
    monkeypatch.setattr(efv_score, "date", _January)
    assert efv_score._eta_origin_of({"eta_origin_year": 2026}) == 2026
    assert efv_score._eta_origin_of({"surplus": {"eta_origin_year": 2026}}) == 2026
    assert efv_score._eta_origin_of({"eta_years": 2.0}) == 2027
    assert efv_score._eta_origin_of(None) == 2027

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/dpw_blast_radius.py on SYNTHETIC probes and a SYNTHETIC series
(DESIGN_v2 section 10): each stage adds one lever to the previous one and moves
only the surfaces that lever reaches (U1a the prospects' base, x1.07 exactly;
U1c the Trade Machine alone), the bands flag a row only above the $5M base or
past $15M, and the tool writes nothing but its report. It is never run on real
data in the build commit."""

from __future__ import annotations

import datetime as _dt
import json

import pytest

import dpw_testkit as kit
import value_framework as vf
from tools import dpw_blast_radius as br


class _October(_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 2)


def _probes():
    f = vf._flat_rate_usd()
    vet_sal = [{"t": t, "season": 2027 + t, "usd": u, "src": s, "tok": k}
               for t, (u, s, k) in enumerate([(780_000.0, "arb_ladder", "PRE-ARB"),
                                              (6_000_000.0, "arb_ladder", "ARB 1"),
                                              (25_000_000.0, "contract", "signed"),
                                              (25_000_000.0, "contract", "signed")])]
    player = {"current_contract": {"salary_by_year": {"2027": 20_000_000, "2028": 20_000_000}},
              "is_pitcher": False, "position": "SS", "age": 29,
              "roster_status": {"mlb_debut_date": "2018-04-01"}, "player_key": "syn_tm",
              "player_name": "Synthetic TM"}
    return {
        "prospects": [{"id": "p1", "name": "Prospect One", "fv": 55.0, "is_pitcher": False,
                       "position": "SS", "age": 21.0, "eta_years": 2.0, "eta_origin": 2026},
                      {"id": "p2", "name": "Prospect Two", "fv": 45.0, "is_pitcher": True,
                       "position": "SP", "age": 23.0, "eta_years": 1.0, "eta_origin": 2026}],
        "veterans": [{"id": "v1", "name": "Veteran One", "war": [3.5, 3.2, 2.9, 2.5],
                      "salary": vet_sal, "dpw_usd": f}],
        "fa": [{"id": "f1", "name": "Free Agent One", "war_path": [3.0, 2.7, 2.4],
                "class_year": 2027, "dpw_usd": f, "infl": 0.0}],
        "trade_machine": [{"id": "t1", "name": "Synthetic TM", "player": player,
                           "true_talent_war": 3.0, "remaining_years": 3}],
    }


@pytest.fixture
def report(tmp_path, monkeypatch):
    import bayes_trade_value as bt
    monkeypatch.setattr(bt, "date", _October)
    monkeypatch.setattr(bt, "_contract_options", lambda: {})
    series = kit.write_series(tmp_path / "series.json", kit.synthetic_block(level_n=14.0e6))
    return br.run(_probes(), series)


def test_the_stages_add_one_lever_at_a_time():
    seq = br.stage_sequence()
    assert seq[0] == ("OFF", None)
    assert [s for s, _ in seq[1:]] == list(br.STAGES)
    for i in range(2, len(seq)):
        assert set(seq[i][1]) - set(seq[i - 1][1]) == {seq[i][0]}


def test_each_stage_moves_only_the_surfaces_its_lever_reaches(report):
    st = {e["stage"]: e for e in report["stages"]}
    assert list(st) == ["OFF", "U1a", "U1b", "U1c", "U2"]
    u1a = st["U1a"]
    assert u1a["delta_usd"]["veterans"] == pytest.approx(0.0, abs=1e-6)
    assert u1a["delta_usd"]["fa"] == pytest.approx(0.0, abs=1.0)
    assert u1a["delta_usd"]["trade_machine"] == pytest.approx(0.0, abs=1e-6)
    assert u1a["totals_usd"]["prospects"] == pytest.approx(st["OFF"]["totals_usd"]["prospects"] * 1.07,
                                                           rel=1e-9)
    u1c = st["U1c"]
    for s in ("prospects", "veterans", "fa"):
        assert u1c["delta_usd"][s] == pytest.approx(0.0, abs=1e-6), s
    assert u1c["rows_moved"]["trade_machine"] == 1
    u2 = st["U2"]
    for s in ("prospects", "veterans", "fa"):
        assert u2["rows_moved"][s] >= 1, s


def test_the_row_band_counts_only_above_the_five_million_base():
    names = {"a": "A", "b": "B", "c": "C"}
    prev = {"a": 4.0e6, "b": 20.0e6, "c": 100.0e6}
    cur = {"a": 9.0e6, "b": 31.0e6, "c": 114.0e6}             # +125% under the base; +55%; +14%
    moved = {m["id"] for m in br._movers(prev, cur, names)}
    assert moved == {"b"}
    cur["c"] = 116.0e6                                         # +$16M: the dollar band
    assert {m["id"] for m in br._movers(prev, cur, names)} == {"b", "c"}


def test_the_tool_writes_only_its_report(tmp_path, monkeypatch):
    import bayes_trade_value as bt
    monkeypatch.setattr(bt, "date", _October)
    monkeypatch.setattr(bt, "_contract_options", lambda: {})
    series = kit.write_series(tmp_path / "series.json", kit.synthetic_block())
    probes = tmp_path / "probes.json"
    probes.write_text(json.dumps(_probes()), encoding="utf-8")
    out = tmp_path / "blast.json"
    before = {p.name for p in tmp_path.iterdir()}
    assert br.main(["--series", str(series), "--probes", str(probes), "--out", str(out)]) == 0
    assert {p.name for p in tmp_path.iterdir()} - before == {"blast.json"}
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert [e["stage"] for e in doc["stages"]] == ["OFF", "U1a", "U1b", "U1c", "U2"]
    assert vf.dpw_path_active() is False                       # nothing left switched on


def test_a_series_without_the_block_is_refused(tmp_path):
    series = kit.write_series(tmp_path / "series.json", None)
    with pytest.raises(SystemExit):
        br.run(_probes(), series)

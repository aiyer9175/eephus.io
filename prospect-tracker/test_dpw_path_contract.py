# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The dpw_path block contract (DESIGN_v2 sections 2, 4.1, 4.2; I6, I7).

The one writer's block is built here from a SYNTHETIC enrichment into tmp
paths; no real series is read, and the block switch stays off (the block is
built by calling the builder directly). Pinned: the schema and the clock, the
path's anchoring, the literal default R (never recomputed from g_ref), r_net
per form, the basis key and the switch-override refusal, the level-equivalent
G_i, the sticker option equal to the truth, pricing.level_usd = P(B) only while
the unified path serves, the five clock constants, the priced season under a
January date, and the Trade Machine loop's year N + yr_offset under both OD-5
answers.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

import pytest

import dpw_path as dp
import dpw_testkit as kit
import fa_market as fm
import fa_projection as fp
import salary_path as sp
import valuation_sets as vs
import value_framework as vf
from test_gate2_untouched_by_path import _synthetic_enriched

B, N = 2027, 2026


@pytest.fixture
def writer(monkeypatch, tmp_path):
    """The block builder on a synthetic enrichment, every path in tmp."""
    enriched = _synthetic_enriched(last=N)
    monkeypatch.setattr(fm, "enriched_signings", lambda *a, **k: enriched)
    monkeypatch.setattr(fp, "build_corpus", lambda *a, **k: {})
    corpus = tmp_path / "corpus.pkl"
    corpus.write_bytes(b"synthetic corpus")
    monkeypatch.setattr(fp, "CORPUS_CACHE", corpus)
    monkeypatch.setattr(sp, "arb_deflator_series",
                        lambda: {y: 1.022 ** (y - 2015) for y in range(2015, 2027)})
    monkeypatch.setattr(fm, "DPW_SERIES_PATH", tmp_path / "fa_dpw_series.json")
    monkeypatch.setattr(fm, "DPW_OWNER_PATH", tmp_path / "dpw_path_owner.json")
    monkeypatch.setattr(fm, "DPW_EVAL_PATH", tmp_path / "dpw_forecast_eval.json")
    for name in fm.PROJECTION_SWITCHES:
        monkeypatch.delenv(name, raising=False)

    def build(owner_rows=(), gate=None, force=True):
        if owner_rows:
            rows = []
            for r in owner_rows:
                dp.append_chained(rows, {"date": "2026-09-30", **r})
            (tmp_path / "dpw_path_owner.json").write_text(
                json.dumps({"schema": dp.OWNER_SCHEMA, "answers": rows}), encoding="utf-8")
        if gate is not None:
            (tmp_path / "dpw_forecast_eval.json").write_text(
                json.dumps({"dpw_path_gate": gate}), encoding="utf-8")
        return fm.build_dpw_path_block(B, force=force, previous={})
    return build, enriched


def test_the_block_schema_clock_and_path(writer):
    build, enriched = writer
    blk = build()
    for k in ("schema", "generated_at", "enrichment", "truth", "served_level", "clock", "discount",
              "path", "salary_index", "tier_shape", "cba", "options", "gate", "basis_id"):
        assert k in blk, k
    assert blk["schema"] == "dpw_path_v2"
    assert blk["clock"] == {"base_season": B, "last_realized_winter": N,
                            "rule": "B = proj_export.FIRST_SEASON, rolled at the post-season step; N = B - 1"}
    assert blk["enrichment"]["p20"] is True and blk["enrichment"]["use_ml"] is False
    assert blk["enrichment"]["enriched_through"] == N
    assert blk["truth"]["estimator"]["id"] == "sticker_leveleq_r_over_disc_war_r_p20_v1"
    seasons = [int(s) for s in blk["path"]["usd_by_season"]]
    assert seasons == list(range(N, 2046))
    a_n = blk["served_level"]["by_winter"][str(N)]
    g = blk["discount"]["g_ref"]
    assert blk["path"]["usd_by_season"][str(N)] == pytest.approx(a_n)
    assert blk["path"]["usd_by_season"][str(B)] == pytest.approx(a_n * (1 + g))
    assert blk["path"]["kind_by_season"][str(B)] == "convention"
    assert blk["path"]["kind_by_season"]["2032"] == "assumption"
    assert blk["path"]["cba_label"] == "conditional on the expired CBA's structure"
    assert set(blk["gate"]) == {"doc", "verdict_source"}          # the gate sub-block carries no verdict
    assert blk["cba"]["regime_break"] is False and blk["cba"]["new_agreement_encoded"] is False
    # deterministic: the same inputs give the same basis
    assert build()["basis_id"] == blk["basis_id"]


def test_r_is_the_literal_default_and_never_follows_g_ref(writer):
    build, _ = writer
    a = build()
    assert a["discount"]["R_nominal"] == 0.113763
    assert a["discount"]["g_ref"] == 0.0409 and a["discount"]["g_ref_rule"] == "keep_0409"
    gate = {"verdict": "NULL_UNDERPOWERED", "blind_status": "NOT_ARMED",
            "owner_at_amendment": {"OD-6": None, "OD-7": {"option": "remeasure_served_rule",
                                                         "date": "2026-11-01", "row_sha256": "x" * 64}}}
    b = build(gate=gate)
    assert b["discount"]["g_ref_rule"] == "remeasure_served_rule"
    assert b["discount"]["g_ref"] != pytest.approx(0.0409)
    assert b["discount"]["R_nominal"] == 0.113763                 # R does not follow g_ref
    assert b["discount"]["r_net"] == pytest.approx(1.113763 / (1 + b["discount"]["g_ref"]) - 1, rel=1e-12)
    c = build(owner_rows=[{"id": "OD-2", "option": "r_010"}])
    assert c["discount"]["R_nominal"] == 0.10
    assert a["discount"]["r_net"] == pytest.approx(0.07, abs=1e-12)
    assert a["discount"]["form_literal"] == "net_7_flat" and a["discount"]["form_served"] == "net_flat"


def test_the_basis_key_carries_the_switches_and_an_override_is_refused(writer, monkeypatch):
    build, _ = writer
    k0 = build()["basis_key"]
    monkeypatch.setenv("EEPHUS_FA_PTFIT", fp.PT_FIT_DEFAULT)       # raw set, equal to the default
    blk = build()
    assert blk["enrichment"]["projection_switches"]["EEPHUS_FA_PTFIT"] == {
        "raw": fp.PT_FIT_DEFAULT, "resolved": fp.PT_FIT_DEFAULT}
    assert blk["basis_key"] != k0
    monkeypatch.setenv("EEPHUS_FA_PTFIT", "both")                   # an override
    with pytest.raises(fm.DpwPathRefused):
        build()
    monkeypatch.delenv("EEPHUS_FA_PTFIT")
    monkeypatch.setenv("EEPHUS_PT_RISK", "1")
    with pytest.raises(fm.DpwPathRefused):
        build()


def test_the_skip_carries_the_block_forward_and_force_recomputes(writer):
    build, _ = writer
    first = build()
    carried = fm.build_dpw_path_block(B, force=False, previous=first)
    assert carried is first
    recomputed = fm.build_dpw_path_block(B, force=True, previous=first)
    assert recomputed is not first and recomputed["truth"]["sha256"] == first["truth"]["sha256"]


def test_level_equivalent_g_for_a_scheduled_deal_and_the_sticker_option(writer, monkeypatch):
    build, enriched = writer
    s = enriched[-1]
    key = f"{s['player_key']}:{s['class_year']}"
    years = int(s["years"])
    sched = [{"year_offset": t, "amount_usd": s["guarantee_usd"] / (2 * years)} for t in range(years)] + \
            [{"year_offset": t + 10, "amount_usd": s["guarantee_usd"] / (2 * years)} for t in range(years)]
    monkeypatch.setattr(fm, "_deferral_ledger", lambda: {key: {"deferred": True, "schedule": sched}})
    rows = {r["_s"]["player_key"]: r for r in fm._truth_rows(enriched)}
    g = rows[s["player_key"]]["G"]
    level = [(t, s["guarantee_usd"] / years) for t in range(years)]
    want = s["guarantee_usd"] * dp.pv([(x["year_offset"], x["amount_usd"]) for x in sched], 0.07) / \
        dp.pv(level, 0.07)
    assert g == pytest.approx(want, rel=1e-12) and g < s["guarantee_usd"]
    share = fm.scheduled_share_by_winter(enriched)[s["class_year"]]
    assert share["n_scheduled"] == 1 and 0 < share["share"] < 0.1
    sticker = build(owner_rows=[{"id": "OD-1", "option": "sticker"}])
    assert sticker["served_level"]["by_winter"] == sticker["truth"]["by_winter"]
    assert sticker["served_level"]["estimator"]["id"] == sticker["truth"]["estimator"]["id"]
    rt = build(owner_rows=[{"id": "OD-1", "option": "round_trip"}])
    assert rt["served_level"]["basis"] == "round_trip"
    assert rt["served_level"]["estimator"]["id"] == "pv_cash_R_over_disc_war_rnet_p20_v1"


def test_pricing_level_is_p_of_b_only_while_the_path_serves(writer, monkeypatch, tmp_path):
    build, enriched = writer
    blk = build()
    monkeypatch.setattr(fm, "build_dpw_path_block", lambda *a, **k: blk)
    payload = {"pricing": {"class_year": B, "level_usd": 17_143_641}}
    fm._apply_dpw_path_block(payload, B, False)
    assert payload["pricing"]["level_usd"] == 17_143_641 and "source" not in payload["pricing"]
    with kit.unified(tmp_path):
        payload = {"pricing": {"class_year": B, "level_usd": 17_143_641}}
        fm._apply_dpw_path_block(payload, B, False)
    assert payload["pricing"]["level_usd"] == int(round(blk["path"]["usd_by_season"][str(B)]))
    assert payload["pricing"]["source"] == "dpw_path"


def test_discount_form_on_both_committed_sets(monkeypatch):
    assert vs.discount_form_literal("clemens_2026") == "net_7_flat"
    assert vs.discount_form("clemens_2026") == "net_flat"
    assert vs.discount_form("prospx_current") == "rate_minus_growth"
    real = vs.load

    def fake(set_id):
        d = json.loads(json.dumps(real(set_id)))
        d["params"]["discount"]["form"] = "net_8_flat"
        return d
    monkeypatch.setattr(vs, "load", fake)
    with pytest.raises(vs.ValuationSetError):
        vs.discount_form("clemens_2026")


def test_the_five_clock_constants_agree():
    import fa_export
    import franchise_export
    import ledger_export
    import proj_export
    b = proj_export.FIRST_SEASON
    assert b == fa_export.CLASS_YEAR == ledger_export.CLASS_YEAR == franchise_export.CLASS_YEAR
    assert ledger_export.SEASON_NOW == franchise_export.SEASON_NOW == b - 1


class _January(_dt.date):
    @classmethod
    def today(cls):
        return cls(2027, 1, 15)


def test_the_priced_season_does_not_depend_on_the_origin_year(tmp_path, monkeypatch):
    """Under a January date the calendar year is N + 1: storage measures ETA from
    2027, proj_export-style callers from N; one prospect prices the same season."""
    import storage
    monkeypatch.setattr(storage, "date", _January)
    with kit.unified(tmp_path):
        a = vf.expected_surplus_usd(55.0, False, "SS", eta_years=2.0, eta_origin=2027)
        b = vf.expected_surplus_usd(55.0, False, "SS", eta_years=3.0, eta_origin=2026)
        assert a == pytest.approx(b, rel=1e-12)
        with pytest.raises(vf.DpwPathError):
            vf.expected_surplus_usd(55.0, False, "SS", eta_years=2.0)
        pay = storage._build_surplus_payload(55.0, False, "SS", eta_years=2.0)
        assert pay["eta_origin_year"] == 2027 and pay["eta_years"] == 2.0


@pytest.mark.parametrize("od5", ["align", "keep"])
def test_the_trade_machine_loop_starts_at_season_b_under_both_od5_answers(tmp_path, monkeypatch, od5):
    import bayes_trade_value as bt
    monkeypatch.setattr(bt, "date", _January)
    seen = []
    monkeypatch.setattr(bt, "_estimate_salary_mm",
                        lambda player, year, rem, mv: seen.append(year) or 1.0)
    monkeypatch.setattr(bt, "_contract_options", lambda: {})
    player = {"current_contract": {"salary_by_year": {}}, "is_pitcher": False, "position": "SS",
              "age": 28, "roster_status": {"mlb_debut_date": "2021-04-01"}, "player_key": "syn",
              "player_name": "Syn Player"}
    bt._contract_surplus_mm(player, 3.0, 3)
    assert seen[0] == 2028                      # legacy: the calendar year + 1 skips season B
    seen.clear()
    with kit.unified(tmp_path, options={"trade_machine": od5}):
        bt._contract_surplus_mm(player, 3.0, 3)
    assert seen[:3] == [2027, 2028, 2029]

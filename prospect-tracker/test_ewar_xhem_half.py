# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The xHEM+ part of the headline eWAR at half weight (docs/ebr-2026-09-30/EBR_GATE.md
11.11; owner decision EW3-51; task EWAR_XHEM_HALF, built dark).

Pinned:
  (a) the flag defaults off, LAMBDA is 0.5 and the part starts in 2016;
  (b) with the part off the builder writes what it wrote before 11.11 (no xhem key, no dx);
  (c) with it on: x = LAMBDA * d / RPW*_s on the hitting side of the headline only, re-centred
      to zero per season, pitcher-batters 0, eWAR realized and the pitching side unchanged,
      `dx` the headline without the part, the RPW guard still an identity, and the stops;
  (d) departures(exclude=("xhem",)) reads dx, and the frozen eFV label reproduces from a build
      with the part on (11.11.3);
  (e) the site sentence is the owner's, its numbers derived from data/swar_eval.json, and the
      card's tip carries it; copy that names the parts reads as before while the flag is off;
  (f) on the real inputs, when the swar preview is present: the part-on build and the part-off
      build agree on eWAR realized and on the label basis row for row, the history build holds
      its identities, and the core and headline labels reproduce.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

import ewar_v3 as V3

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_ewar_v3 as B  # noqa: E402
from test_ewar_v3 import FixtureInputs  # noqa: E402

OWNER_COPY = ("Provisional. xHEM+ improved next-season prediction in the 2016-2024 test and pointed the "
              "same way on 2025-26 (+0.068, range -0.003 to +0.141). A 2027 read decides whether it stays.")


class XInputs(FixtureInputs):
    """The eWAR v3 fixtures plus a synthetic swar preview xHEM+ arm."""

    def __init__(self, *a, xsrc=None, vintage_id="fixture-vintage", **k):
        super().__init__(*a, **k)
        self._xsrc = xsrc
        self._xvid = vintage_id

    def xhem(self):
        src = self._xsrc if self._xsrc is not None else {
            2024: {"rpw": 10.0, "rows": {1: {"d": 3.0, "pa": 500.0, "arm": "xhem", "pb": False},
                                         2: {"d": -1.0, "pa": 400.0, "arm": "xhem", "pb": False},
                                         3: {"d": -2.0, "pa": 300.0, "arm": "hem", "pb": False}}},
            2026: {"rpw": 9.8, "rows": {1: {"d": -2.0, "pa": 500.0, "arm": "xhem", "pb": False},
                                        2: {"d": 2.5, "pa": 400.0, "arm": "xhem", "pb": False},
                                        3: {"d": 0.4, "pa": 300.0, "arm": "hem", "pb": True},
                                        4: {"d": 0.0, "pa": 0.0, "arm": "hem", "pb": False}}},
        }
        return src, {"fwar_vintage_id": self._xvid, "sha256": None, "seasons": sorted(src)}


@pytest.fixture
def fx(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)
    off = B.build(XInputs(), log=lambda *a: None, xhem=False)
    on = B.build(XInputs(), log=lambda *a: None, xhem=True)
    return off, on


# (a) ------------------------------------------------------------------------
def test_flag_defaults_off_with_a_fixed_half_weight_from_2016():
    assert V3.XHEM_HALF_LIVE is False, "the orchestrator flips this on the owner's authorization"
    assert V3.XHEM_LAMBDA == 0.5
    assert V3.XHEM_FIRST_SEASON == 2016
    assert V3.PART_LABELS["xhem"] == "xHEM+ (expected batting, half weight)"
    assert V3.PREVIEW_XHEM.parent == ROOT / ".cache" / "ewar_v3" / "preview"


# (b) ------------------------------------------------------------------------
def test_part_off_writes_no_xhem_key(fx):
    off, _on = fx
    assert set(off["meta"]["parts"]) == {"eabs", "r2"}
    text = json.dumps(off)
    assert '"xhem' not in text and '"dx"' not in text
    assert "xHEM" not in off["meta"]["fg_components"]


def test_flag_none_follows_the_module_flag(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)
    monkeypatch.setattr(V3, "XHEM_HALF_LIVE", True)
    p = B.build(XInputs(), log=lambda *a: None)
    assert "xhem" in p["meta"]["parts"]
    monkeypatch.setattr(V3, "XHEM_HALF_LIVE", False)
    p = B.build(XInputs(), log=lambda *a: None)
    assert "xhem" not in p["meta"]["parts"]


# (c) ------------------------------------------------------------------------
def test_the_part_is_half_the_recentred_delta_on_the_headline_hitting_side(fx):
    off, on = fx
    # 2024: rows 1 to 3 inside the rule; d sums to 0 already, so x = 0.5 * d / 10
    for mid, d in ((1, 3.0), (2, -1.0), (3, -2.0)):
        blk = on["players"][str(mid)]["2024"]
        assert blk["parts"]["xhem"]["wins"] == pytest.approx(0.5 * d / 10.0, abs=1e-6)
        assert blk["dh"]["bat"] == pytest.approx(0.5 * d / 10.0, abs=1e-6)
        assert blk["parts"]["xhem"]["arm"] == ("hem" if mid == 3 else "xhem")
    # 2026: the pitcher-batter (3) is outside the rule and carries none; 1 and 2 re-centred per PA
    raw = {1: -2.0, 2: 2.5}
    c = sum(raw.values()) / (500.0 + 400.0)
    for mid, pa in ((1, 500.0), (2, 400.0)):
        x = 0.5 * (raw[mid] - pa * c) / 9.8
        blk = on["players"][str(mid)]["2026"]
        assert blk["parts"]["xhem"]["wins"] == pytest.approx(x, abs=1e-6)
        a = blk["parts"].get("abs", {}).get("bat", {}).get("wins", 0.0)
        assert blk["dh"]["bat"] == pytest.approx(a + x, abs=2e-6)
        assert blk.get("dx", {}).get("bat", 0.0) == pytest.approx(a, abs=1e-6)
    assert "xhem" not in (on["players"].get("3", {}).get("2026", {}).get("parts") or {})


def test_the_part_sums_to_zero_and_moves_nothing_else(fx):
    off, on = fx
    for s, c in on["checks"].items():
        for k, v in c["sum_departure_wins"].items():
            assert abs(v) < 1e-9, (s, k, v)
        if "xhem_receipt" in c:
            assert abs(c["xhem_receipt"]["sum_wins"]) < 1e-9
            assert c["xhem_receipt"]["lambda"] == 0.5
    assert V3.departures(off, "realized") == V3.departures(on, "realized")
    for (mid, s), cell in V3.departures(on, "headline").items():
        base = V3.departures(off, "headline").get((mid, s)) or {}
        assert cell.get("pit", 0.0) == pytest.approx(base.get("pit", 0.0), abs=1e-12)


def test_dx_is_the_part_off_headline_row_for_row(fx):
    off, on = fx
    assert V3.departures(on, "headline", exclude=("xhem",)) == V3.departures(off, "headline")
    with pytest.raises(ValueError):
        V3.departures(on, "headline", exclude=("eabs",))


def test_a_season_before_the_first_carries_no_part(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)
    monkeypatch.setattr(V3, "XHEM_FIRST_SEASON", 2025)
    p = B.build(XInputs(), log=lambda *a: None, xhem=True)
    assert all("xhem" not in (b.get("parts") or {}) for by in p["players"].values()
               for s, b in by.items() if int(s) < 2025)
    assert "xhem_receipt" not in p["checks"]["2024"]


def test_the_rpw_guard_stays_an_identity(fx):
    _off, on = fx
    g = on["meta"]["rpw"]
    assert g["form"] == "c" and g["guard"]["status"] == "NON-INFERIOR"
    assert "the xHEM+ part converts at the skill look's own runs per win" in g["guard"]["how"]


def test_the_meta_names_the_owner_decision_and_the_2027_read(fx):
    _off, on = fx
    m = on["meta"]["parts"]["xhem"]
    assert m["series"] == ["headline"] and m["lambda"] == 0.5 and m["first_season"] == 2016
    assert "registered admission rule was not met" in m["how"] and "EW3-51" in m["how"]
    assert "EWAR_XHEM_2027_READ" in m["keep_or_remove"]
    assert m["copy"] == OWNER_COPY
    assert "xHEM+" in on["meta"]["fg_components"]


def test_the_stops(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)
    with pytest.raises(V3.EwarV3Refusal, match="vintage"):
        B.build(XInputs(vintage_id="another"), log=lambda *a: None, xhem=True)
    with pytest.raises(V3.EwarV3Refusal, match="no xHEM\\+ arm"):
        B.build(XInputs(xsrc={2026: {"rpw": 9.8, "rows": {}}}), log=lambda *a: None, xhem=True)
    stray = {2024: {"rpw": 10.0, "rows": {99: {"d": 0.0, "pa": 10.0, "arm": "hem", "pb": False}}},
             2026: {"rpw": 9.8, "rows": {}}}
    with pytest.raises(V3.EwarV3Refusal, match="no hitting row"):
        B.build(XInputs(xsrc=stray), log=lambda *a: None, xhem=True)


def test_the_cli_preview_never_writes_data(tmp_path, monkeypatch):
    assert B.main(["--xhem-preview", "--write"]) == 2
    written = []
    monkeypatch.setattr(B, "build", lambda inp=None, log=print, xhem=None: {"x": xhem})
    monkeypatch.setattr(B, "census", lambda p, log=print: None)
    monkeypatch.setattr(B, "write", lambda p, path: written.append((p, path)))
    assert B.main(["--xhem-preview"]) == 0
    assert written == [({"x": True}, V3.PREVIEW_XHEM)]


# (d) ------------------------------------------------------------------------
def test_the_headline_label_reads_the_part_off_basis(fx):
    import ewar_headline_label as H
    off, on = fx
    a = H.build(v3=on, fwar_vintage_id="fixture-vintage", log=lambda *x, **k: None)
    b = H.build(v3=off, fwar_vintage_id="fixture-vintage", log=lambda *x, **k: None)
    assert a["content_sha256"] == b["content_sha256"]


# (e) ------------------------------------------------------------------------
def test_the_site_sentence_is_the_owners_and_derives_from_the_record():
    assert V3.xhem_copy() == OWNER_COPY
    rec = json.loads(V3.SWAR_EVAL.read_text(encoding="utf-8"))
    cell = rec["holdout"]["block"]["cells"]["batting"]["xHEM+ H-rate"]
    assert (round(cell["gap"], 3), round(cell["lo95"], 3), round(cell["hi95"], 3)) == (0.068, -0.003, 0.141)
    moved = copy.deepcopy(rec)
    moved["holdout"]["block"]["cells"]["batting"]["xHEM+ H-rate"]["gap"] = 0.05
    assert "(+0.050, range" in V3.xhem_copy(moved)
    assert "override" not in OWNER_COPY.lower()


def test_the_card_tip_carries_the_sentence():
    js = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    block = js.split("const EWAR_PARTS = [", 1)[1].split("];", 1)[0]
    assert '{ id: "xhem", label: "xHEM+ (expected batting, half weight)"' in block
    assert OWNER_COPY in block
    assert "override" not in block.lower()


def test_copy_that_names_the_parts_reads_as_before_while_off():
    import awards_core
    import mlb_player_export as mpe
    import pal_export
    assert V3.xhem_suffix(False) == ""
    assert V3.xhem_suffix(True) == " and, provisionally, half of xHEM+ expected batting from 2016"
    assert awards_core.CREDIT_LINES["bref_v3"] == (
        "Rosters by league and club come from Baseball-Reference's WAR file; eWAR starts from "
        "FanGraphs' published WAR, with the site's ABS challenge part from 2026.")
    assert pal_export._WAR_SERIES["ewar_v3"] == (
        "eWAR: FanGraphs' published WAR from the frozen vintage plus the site's named "
        "departures (the ABS challenge part from 2026)")
    assert "plus the ABS challenge part from 2026, data/ewar_v3.json); war_real" in mpe._CAREER_NOTE_V3
    assert "xhem" not in mpe._CAREER_NOTE_V3


def test_the_board_states_the_sentence_only_when_a_season_carries_the_part():
    import war_board_export as wbe
    groups = [{"first": 2008, "last": 2015, "headline": ["batting"], "text_headline": "a.",
               "missing": ["xhem"], "short_headline": "b."},
              {"first": 2016, "last": 2026, "headline": ["batting", "xhem"], "text_headline": "c.",
               "missing": [], "short_headline": ""}]
    blk = wbe._components_block(groups)
    assert blk["xhem"] == {"first_season": 2016, "copy": OWNER_COPY}
    groups[1]["headline"] = ["batting"]
    assert "xhem" not in wbe._components_block(groups)


def test_the_glossary_and_registry_tool_waits_for_the_flag():
    import ewar_xhem_glossary_registry as T
    assert T.main(["--check"]) == 2          # refuses while the flag is off
    row = T.registry_row(json.loads(V3.SWAR_EVAL.read_text(encoding="utf-8")))
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "shipped_partial_measurement"
    assert "REGISTERED ADMISSION RULE WAS NOT MET" in row["notes"]
    assert "EWAR_XHEM_2027_READ" in row["remeasure_pending"]
    ent = T.entry(OWNER_COPY)
    assert OWNER_COPY in ent["definition"] and "override" not in json.dumps(ent).lower()


# (f) ------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real():
    if not B.PREVIEW_SWAR.exists() or not V3.OUT.exists():
        pytest.skip("the swar preview or data/ewar_v3.json is absent in this checkout")
    off = B.build(log=lambda *a: None, xhem=False)
    on = B.build(log=lambda *a: None, xhem=True)
    return off, on


def test_real_build_moves_only_the_headline_hitting_side(real):
    off, on = real
    assert V3.departures(off, "realized") == V3.departures(on, "realized")
    assert V3.departures(on, "headline", exclude=("xhem",)) == V3.departures(off, "headline")
    first = min(int(s) for s, c in on["checks"].items() if "xhem_receipt" in c)
    assert first == 2016
    for s, c in on["checks"].items():
        assert abs(c["sum_departure_wins"]["dh_bat"]) < 1e-6, s


def test_real_labels_and_history_hold_with_the_part_on(real):
    import ewar_core_label as C
    import ewar_headline_label as H
    import ewar_history as EH
    _off, on = real
    if H.available():
        assert H.build(v3=on, log=lambda *a, **k: None)["content_sha256"] == H.load()["content_sha256"]
    vin = EH._inputs()[0]
    if C.available():
        assert C.build(vintage=vin, v3=on, log=lambda *a, **k: None)["content_sha256"] == C.load()["content_sha256"]
    rec = EH.build(vintage=vin, v3=on, log=lambda *a, **k: None)
    st = rec["seasons"]
    assert all(("xhem" in v["stamp"]["headline"]) == (int(s) >= 2016) for s, v in st.items())
    assert all("xhem" not in v["stamp"]["realized"] for v in st.values())
    assert any(p["id"] == "xhem" for p in rec["parts"])
    g = [g for g in rec["groups"] if g["first"] <= 2016 <= g["last"]][0]
    assert "plus half of xHEM+ expected batting (provisional)" in g["text_headline"]
    assert "keeps FanGraphs' batting" in g["text"]
    old = [g for g in rec["groups"] if g["last"] < 2016][-1]
    assert "batting is FanGraphs' alone (the xHEM+ part starts in 2016)" in old["short_headline"]
    EH.reset()

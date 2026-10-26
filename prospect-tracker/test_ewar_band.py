# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR uncertainty band built dark (docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md
parts 2.1 and 10, amendment 13.1; owner decision EW3-50; owner question EWUB-Q1).

What is pinned:
  (a) with ewar_band.BAND_LIVE False (the committed default) no consumer carries a
      band: the player card rows, the Awards rows and the board helper emit what they
      emitted before, and the module writes only its preview;
  (b) with the flag on, the band is the gate's form on the read's recorded constants:
      1.2816 sigma, k_fip on the headline and k_ra on an R2 row of eWAR realized,
      no band below the floors;
  (c) the artifact is built only from a PASS record and copies its constants;
  (d) the flip's glossary and registry tool refuses while the flag is off and, on
      copies with the flag on, is idempotent and writes copy with no banned word;
  (e) the three front-end assets print the +/- only when the payload carries it.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import awards_core as A  # noqa: E402
import ewar_band as EB  # noqa: E402
import ewar_uncertainty_band as U  # noqa: E402
import mlb_player_export as mpe  # noqa: E402
from test_mlb_player_fwar_reference import _maps, lines  # noqa: E402,F401  (fixture)

RECORD = json.loads(EB.RECORD.read_text(encoding="utf-8"))


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setattr(EB, "BAND_LIVE", True)
    EB.set_payload(EB.build(RECORD))
    yield EB.load()
    EB.set_payload(None)


def test_the_flag_is_on():
    # owner EWUB-Q1 2026-10-26
    assert EB.BAND_LIVE is True


def test_flag_is_off_and_nothing_serves(monkeypatch):
    monkeypatch.setattr(EB, "BAND_LIVE", False)
    EB.set_payload(None)
    assert EB.load() is None
    assert EB.half_width(season=2024, pa=600) is None
    assert EB.pm(None) is None


def test_build_refuses_without_a_pass_and_copies_the_constants():
    with pytest.raises(U.BandRefusal):
        EB.build(dict(RECORD, disposition="NOT PASS"))
    blob = EB.build(RECORD)
    assert blob["constants"]["k"] == {k: float(v) for k, v in RECORD["constants"]["k"].items()}
    assert blob["z"] == U.Z80 and blob["nominal"] == 0.8
    assert set(blob["constants"]["m"]) == set(U.TERM_FAMILY)


def test_write_goes_to_the_preview_while_off(tmp_path, monkeypatch):
    monkeypatch.setattr(EB, "BAND_LIVE", False)  # the dark path, pinned explicitly since the EWUB-Q1 flip
    monkeypatch.setattr(EB, "PREVIEW", tmp_path / "preview" / "ewar_band.json")
    monkeypatch.setattr(EB, "OUT", tmp_path / "served" / "ewar_band.json")
    path = EB.write(EB.build(RECORD))
    assert path == tmp_path / "preview" / "ewar_band.json" and path.exists()
    assert not (tmp_path / "served").exists()


def test_band_is_the_registered_form(live):
    import league_constants
    rpw = float(league_constants.league_totals(2024)["rpw"])
    c = RECORD["constants"]
    k, m = c["k"], c["m"]
    b = U.band_index("bat", 600)
    var = (m["bat"][b] ** 2 * k["bat"] * 600 + m["ebr"][b] ** 2 * k["ebr"] * 600) / rpw ** 2 \
        + m["src_bat"][b] ** 2 * k["src_bat"] * 600
    assert EB.half_width(season=2024, pa=600) == pytest.approx(U.Z80 * math.sqrt(var), rel=1e-6)
    p = U.band_index("pit", 180)
    fip = U.Z80 * math.sqrt(m["fip"][p] ** 2 * k["fip"] * 180 / rpw ** 2 + m["src_pit"][p] ** 2 * k["src_pit"] * 180)
    ra = U.Z80 * math.sqrt(m["ra"][p] ** 2 * k["ra"] * 180 / rpw ** 2 + m["src_pit"][p] ** 2 * k["src_pit"] * 180)
    assert EB.half_width(season=2024, ip=180) == pytest.approx(fip, rel=1e-6)
    r2 = next(((mid, s) for (mid, s) in sorted(_r2_rows()) if s == 2024), None)
    if r2 is not None:
        assert EB.half_width(season=2024, ip=180, series="realized", mlbam=r2[0]) == pytest.approx(ra, rel=1e-6)
    assert EB.half_width(season=2024, ip="180.0") == pytest.approx(fip, rel=1e-6)
    assert EB.half_width(season=2024, pa=19) is None and EB.half_width(season=2024, ip=4.2) is None
    with pytest.raises(ValueError):
        EB.half_width(season=2024, pa=600, series="other")


def _r2_rows():
    EB.carries_r2(0, 0)
    return EB._R2 or set()


def test_card_rows_carry_the_band_only_when_live(lines, monkeypatch):  # noqa: F811
    monkeypatch.setattr(EB, "BAND_LIVE", False)  # the dark path, pinned explicitly since the EWUB-Q1 flip
    EB.set_payload(None)
    served, bwar, ref, _provider = _maps()
    real = {mid: {s: dict(c) for s, c in by.items()} for mid, by in served.items()}
    refs = {"real": real, "ewar2": {}}
    off = {(mid, p): mpe._career_rows(mid, p, served, bwar, ref, refs)
           for mid, p in ((545361, False), (660271, True), (694973, True))}
    for rows in off.values():
        assert all("war_pm" not in r and "war_real_pm" not in r for r in rows)
    monkeypatch.setattr(EB, "BAND_LIVE", True)
    EB.set_payload(EB.build(RECORD))
    n_band = 0
    try:
        for (mid, is_pit), before in off.items():
            after = mpe._career_rows(mid, is_pit, served, bwar, ref, refs)
            n_band += sum(1 for a in after if "war_pm" in a)
            for b, a in zip(before, after):
                assert {k: v for k, v in a.items() if k not in ("war_pm", "war_real_pm")} == b
                ex = {"ip": a.get("ip")} if is_pit else {"pa": a.get("pa")}
                want = EB.pm(EB.half_width(season=a["y"], mlbam=mid, **ex))
                if a.get("war") is not None and want is not None:
                    assert a["war_pm"] == want
                else:
                    assert "war_pm" not in a
        assert n_band >= 2
        # no real map (the displayed eWAR is not eWAR v3): no band
        rows = mpe._career_rows(545361, False, served, bwar, ref, {"real": {}, "ewar2": {}})
        assert all("war_pm" not in r for r in rows)
    finally:
        EB.set_payload(None)


def _league_rows():
    return [{"mlbam": 1, "name": "A", "league": "AL", "bat": 6.0, "pit": 0.0, "bat_real": 6.0, "pit_real": 0.0,
             "pa": 650, "ip": 0.0, "g": 150, "clubs": ["NYY"], "war_provider": "ewar_v3"},
            {"mlbam": 2, "name": "B", "league": "AL", "bat": 0.0, "pit": 5.0, "bat_real": 0.0, "pit_real": 4.4,
             "pa": 0, "ip": 190.0, "g": 32, "clubs": ["SEA"], "war_provider": "ewar_v3"}]


def test_awards_rows_carry_the_band_only_when_live(monkeypatch):
    monkeypatch.setattr(EB, "BAND_LIVE", False)  # the dark path, pinned explicitly since the EWUB-Q1 flip
    EB.set_payload(None)
    off = A.mvp_ballot(_league_rows(), "AL", 2024, n=5)
    assert all("realized_pm_display" not in r for r in off["top"])
    cy_off = A.cy_young_ballot(_league_rows(), "AL", 2024, n=5)
    assert all("realized_pm_display" not in r for r in cy_off["top"])
    monkeypatch.setattr(EB, "BAND_LIVE", True)
    EB.set_payload(EB.build(RECORD))
    try:
        on = A.mvp_ballot(_league_rows(), "AL", 2024, n=5)
        for a, b in zip(on["top"], off["top"]):
            assert {k: v for k, v in a.items() if k != "realized_pm_display"} == b
        hitter = next(r for r in on["top"] if r["mlbam"] == 1)
        assert hitter["realized_pm_display"] == A.score_display(EB.half_width(season=2024, pa=650,
                                                                               series="realized", mlbam=1))
        cy = A.cy_young_ballot(_league_rows(), "AL", 2024, n=5)
        arm = next(r for r in cy["top"] if r["mlbam"] == 2)
        assert arm["realized_pm_display"] == A.score_display(EB.half_width(season=2024, ip=190.0,
                                                                            series="realized", mlbam=2))
    finally:
        EB.set_payload(None)


def test_glossary_registry_tool_refuses_while_off_and_is_idempotent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(EB, "BAND_LIVE", False)  # the dark path, pinned explicitly since the EWUB-Q1 flip
    import ewar_band_glossary_registry as G
    assert G.main([]) == 2 and "refusing" in capsys.readouterr().out
    gl, rg, fr = (tmp_path / "glossary.json", tmp_path / "model_registry.json",
                  tmp_path / "test_methodology_freshness.py")
    shutil.copyfile(G.GLOSSARY, gl)
    shutil.copyfile(G.REGISTRY, rg)
    shutil.copyfile(G.FRESHNESS, fr)
    monkeypatch.setattr(EB, "BAND_LIVE", True)
    assert G.main([], glossary=gl, registry=rg, freshness=fr) == 0
    once = (gl.read_bytes(), rg.read_bytes(), fr.read_bytes())
    assert G.main([], glossary=gl, registry=rg, freshness=fr) == 0
    assert (gl.read_bytes(), rg.read_bytes(), fr.read_bytes()) == once
    out = capsys.readouterr().out
    assert "nothing to change" in out
    g = {e["id"]: e for e in json.loads(gl.read_text(encoding="utf-8"))["entries"]}
    r = {m["model_id"]: m for m in json.loads(rg.read_text(encoding="utf-8"))["models"]}
    assert "ewar_band" in g and r["ewar_band"]["verdict"] == "provisional"
    assert r["ewar_band"]["provisional_kind"] == "measurement_only"
    assert '"ewar_band": ["ewar_band", "ewar"],' in fr.read_text(encoding="utf-8")
    text = json.dumps(g["ewar_band"]) + json.dumps(r["ewar_band"])
    assert not re.search("[–—]", text)
    for word in ("leverage", "seamless", "robust", "comprehensive", "powerful", "validated", "proven", " will "):
        assert word not in text.lower(), word
    lo, hi = G._span(RECORD)
    assert f"{lo * 100:.0f} to {hi * 100:.0f} percent" in g["ewar_band"]["definition"]


def test_assets_print_the_band_only_when_carried():
    proj = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "const pmWar = v => (v != null ?" in proj
    assert "fmtWar(r.war) + pmWar(r.war_pm)" in proj and "fmtWar(r.war_real) + pmWar(r.war_real_pm)" in proj
    mlb = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    assert "(r.war_pm != null ? ' <span class=\"ewar-pm\"" in mlb
    aw = (ROOT / "assets" / "awards.js").read_text(encoding="utf-8")
    assert "r.realized_pm_display != null ? \" &plusmn;\"" in aw
    for txt in (proj, mlb, aw):
        assert "It is not a range for talent." in txt or "realized_pm_display" in txt

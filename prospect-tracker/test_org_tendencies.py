# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Organization Tendencies guards: pure helpers (z, labels, cash-direction
parsing, promotion math), the committed sidecar's shape contract (the
farm-detail Tendencies tab renders it blind), and the prospx/glossary
wiring."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import org_tendencies as ot

ROOT = Path(__file__).parent
SIDECAR = ROOT / "data" / "org_tendencies.json"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_z_and_label_bands():
    assert ot._z(12, 10, 2) == 1.0
    assert ot._z(None, 10, 2) is None
    assert ot._z(12, 10, 0) is None                      # degenerate sd
    assert ot._label(0.6, "hi", "lo") == "hi"
    assert ot._label(-0.6, "hi", "lo") == "lo"
    assert ot._label(0.2, "hi", "lo") == "typical"
    assert ot._label(None, "hi", "lo") is None


def test_league_stats_requires_population():
    assert ot._league_stats({"A": 1.0, "B": None})["mean"] is None  # < 8 orgs
    vals = {f"O{i}": float(i) for i in range(10)}
    st = ot._league_stats(vals)
    assert st["mean"] == 4.5 and st["sd"] > 0


def test_cash_direction_parses_receiving_club():
    """'A traded X to B for ... cash' — A received the cash."""
    d = "St. Louis Cardinals traded RF Adolis Garcia to Texas Rangers for cash."
    assert ot.cash_direction(d) == "St. Louis Cardinals"
    d2 = ("Colorado Rockies traded RF Raimel Tapia and 2B Adrian Pinto to "
          "Toronto Blue Jays for RF Randal Grichuk and cash.")
    assert ot.cash_direction(d2) == "Colorado Rockies"
    # no cash in the return → no receiver
    d3 = "Boston Red Sox traded SS Test Player to New York Yankees for RHP Other Guy."
    assert ot.cash_direction(d3) is None


def test_promotion_panel_math():
    """Young-for-level + frequent promotions reads aggressive; the inverse
    reads conservative — on a synthetic 10-org league."""
    today = date(2026, 6, 10)
    mk = lambda diff, promos: {
        "age_vs_level": {"diff": diff},
        "level_changes": [{"kind": "promotion", "date": "2026-01-15"}] * promos,
    }
    by_org = {f"O{i}": [mk(0.0, 1), mk(0.0, 1)] for i in range(8)}
    by_org["AGG"] = [mk(-2.0, 3), mk(-1.5, 2)]
    by_org["CON"] = [mk(2.0, 0), mk(1.5, 0)]
    panel = ot.promotion_panel(by_org, [], today)
    assert panel["orgs"]["AGG"]["label"] == "aggressive"
    assert panel["orgs"]["CON"]["label"] == "conservative"
    assert panel["orgs"]["O0"]["label"] == "typical"


def test_promotion_panel_debut_age():
    """Debut age splits pitchers vs hitters and z's vs league."""
    today = date(2026, 6, 10)
    roster = [{"age_vs_level": {"diff": 0.0}, "level_changes": []}]
    by_org = {f"O{i}": list(roster) for i in range(10)}
    # 3 pitcher + 3 hitter debuts for ORG, league debuts older
    debuts = []
    for i in range(10):
        org = f"O{i}"
        for _ in range(3):
            debuts.append({"org": org, "position": "SP",
                           "birth_date": "2000-01-01", "debut_date": "2025-01-01"})  # age ~25
            debuts.append({"org": org, "position": "SS",
                           "birth_date": "2001-01-01", "debut_date": "2025-01-01"})  # age ~24
    panel = ot.promotion_panel(by_org, debuts, today)
    o0 = panel["orgs"]["O0"]
    assert 24.5 <= o0["debutAgePit"] <= 25.5
    assert 23.5 <= o0["debutAgeHit"] <= 24.5
    assert o0["nDebutPit"] == 3 and o0["nDebutHit"] == 3


def test_filter_mlb30_drops_foreign_codes():
    panel = {"orgs": {"MIL": {}, "KOR": {}, "XXXX": {}}}
    out = ot._filter_mlb30(panel, {"MIL"})
    assert list(out["orgs"]) == ["MIL"]


# ---------------------------------------------------------------------------
# Sidecar shape contract
# ---------------------------------------------------------------------------

def _payload():
    if not SIDECAR.exists():
        pytest.skip("org_tendencies.json not exported on this machine")
    return json.loads(SIDECAR.read_text(encoding="utf-8"))


PANELS = ("promotion", "draftPos", "draftTraits", "slot", "arsenal",
          "toolDev", "ifa", "trades", "health",
          "graduation", "hitterApproach", "similarFarms")


def test_sidecar_covers_all_30_orgs_every_panel():
    d = _payload()
    for panel in PANELS:
        orgs = d[panel]["orgs"]
        assert len(orgs) == 30, f"{panel}: {len(orgs)} orgs"
        assert all(len(o) <= 3 for o in orgs), f"{panel}: non-MLB code leaked"


def test_new_panel_shapes():
    """The expanded panels carry their new fields with sane ranges."""
    d = _payload()
    # draft: college/HS + position buckets sum to ~1
    for org, r in d["draftPos"]["orgs"].items():
        bk = r.get("posBuckets") or {}
        if bk:
            assert abs(sum(bk.values()) - 1.0) < 0.02, org
            assert set(bk) == {"P", "C", "MI", "CI", "OF"}, org
        if r.get("collShare") is not None:
            assert 0 <= r["collShare"] <= 1, org
    # arsenal: blended arm counts + full usage matrix with ratios
    for org, r in d["arsenal"]["orgs"].items():
        assert r["nArms"] == r["nArmsMlb"] + r["nArmsAaa"], org
        for pt, cell in (r.get("usage") or {}).items():
            assert 0 <= cell["share"] <= 1, (org, pt)
    # pitchStuff present when AAA cache exists; shape-check when so
    for org, r in d.get("pitchStuff", {}).get("orgs", {}).items():
        for pt, cell in (r.get("pitches") or {}).items():
            assert cell["n"] >= 1, (org, pt)
    # promotion debut ages in a sane window
    for org, r in d["promotion"]["orgs"].items():
        for k in ("debutAgePit", "debutAgeHit"):
            if r.get(k) is not None:
                assert 20 <= r[k] <= 28, (org, k)
    # graduation hit rate is a rate
    for org, r in d["graduation"]["orgs"].items():
        if r.get("draftHitRate") is not None:
            assert 0 <= r["draftHitRate"] <= 1, org
    # similar farms: top-N descending, scores in [-1, 1]
    for org, r in d["similarFarms"]["orgs"].items():
        scores = [s["score"] for s in r["similar"]]
        assert scores == sorted(scores, reverse=True), org
        assert all(-1.001 <= s <= 1.001 for s in scores), org


def test_sidecar_values_are_sane():
    d = _payload()
    for org, r in d["promotion"]["orgs"].items():
        if r.get("avlDiff") is not None:
            assert -6 <= r["avlDiff"] <= 6, org
        assert r.get("label") in ("aggressive", "conservative", "typical", None)
    for org, r in d["ifa"]["orgs"].items():
        if r.get("top1Share") is not None:
            assert 0 < r["top1Share"] <= 1, org
        if r.get("hhi") is not None:
            assert 0 < r["hhi"] <= 1, org
    for org, r in d["trades"]["orgs"].items():
        assert r["volume"] == r["in"] + r["out"], org
        if r.get("acqTopShare") is not None:
            assert 0 <= r["acqTopShare"] <= 1, org
        assert r.get("cashInvolved", 0) >= r.get("cashReceived", 0), org
    # tool-dev rates are grade points per year — drifts beyond ±10 would be
    # source churn, not development
    for org, r in d["toolDev"]["orgs"].items():
        for k, v in (r.get("tools") or {}).items():
            assert -10 <= v["rate"] <= 10, (org, k)


def test_labels_are_league_relative_not_unanimous():
    """z-based labels can't all fire one way — a league where everyone is
    'aggressive' means the baseline is wrong."""
    d = _payload()
    promo = [r.get("label") for r in d["promotion"]["orgs"].values()]
    assert "typical" in promo
    assert not all(v == "aggressive" for v in promo)


def test_prospx_and_glossary_wiring():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "org-tendencies-mount" in src and "_renderOrgTendencies" in src
    assert '"tendencies"' in src or "'tendencies'" in src
    assert "org_tendencies.json" in src
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    assert any(e["id"] == "org_tendencies" for e in gl["entries"])
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    assert rm.count("org_tendencies import export") >= 2   # monthly + rebuild_only

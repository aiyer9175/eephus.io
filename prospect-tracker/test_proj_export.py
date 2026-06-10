# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Projections module guards: the committed sidecar's shape contract
(assets/projections.js renders it blind), bucket ordering, prospect/vet
source discipline, and the convex season-pricing helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import proj_export as pe

ROOT = Path(__file__).parent
SIDECAR = ROOT / "data" / "mlb_projections.json"


def test_season_value_pricing_is_convex_and_escalates():
    """Season $ value rides the platform tier curve (convex) at the winter
    level, escalating per season — the same pricing as FA rational value."""
    v1 = pe._season_value_usd(1.0, 0, 16_000_000)
    v3 = pe._season_value_usd(3.0, 0, 16_000_000)
    assert v3 > 3 * v1                       # convex: stars cost more per win
    later = pe._season_value_usd(1.0, 3, 16_000_000)
    assert later == pytest.approx(v1 * 1.05 ** 3, rel=1e-9)
    assert pe._season_value_usd(0.0, 0, 16_000_000) == 0.0


def _payload():
    if not SIDECAR.exists():
        pytest.skip("mlb_projections.json not exported on this machine")
    return json.loads(SIDECAR.read_text(encoding="utf-8"))


def test_sidecar_shape_contract():
    d = _payload()
    assert d["first_season"] == pe.FIRST_SEASON and d["horizon"] == pe.HORIZON
    assert d["n_vets"] > 800 and d["n_prospects"] > 100
    assert d["dpw_usd"] > 5_000_000 and 0 < d["dpw_infl"] < 0.2
    for m in d["vets"][:50] + d["prospects"][:50]:
        assert m["key"] and m["name"] and m["src"] in ("vet", "prospect")
        assert len(m["war"]) <= max(pe.HORIZON, 6) and m["war"], m["name"]
        assert m["warTotal"] is not None


def test_bucket_ordering_floor_mean_ceiling():
    d = _payload()
    for m in d["vets"] + d["prospects"]:
        if m.get("warTotalP10") is None:
            continue
        assert m["warTotalP10"] <= m["warTotal"] + 0.11, m["name"]
        assert m["warTotal"] <= m["warTotalP90"] + 0.11, m["name"]


def test_vet_surplus_only_on_contracted_seasons():
    """The module's honesty rule: a veteran surplus claim requires a real
    contract (signed_through + per-season salary)."""
    d = _payload()
    for m in d["vets"]:
        if m.get("surNpv") is not None:
            assert m.get("thru"), f"{m['name']} has surplus but no contract"
        if m.get("sur"):
            assert any(s is not None for s in m["sur"])


def test_prospects_carry_outcome_buckets_and_eta():
    d = _payload()
    order = list(pe._BUCKET_ORDER)
    for m in d["prospects"]:
        assert m["eta"] >= pe.FIRST_SEASON
        assert m.get("fv") is not None and m["fv"] >= 45
        assert m["bucketLo"] in order and m["bucketHi"] in order
        assert order.index(m["bucketLo"]) <= order.index(m["bucketHi"]), m["name"]
        assert 0 <= (m.get("pBust") or 0) <= 1


def test_site_carries_projections_surface():
    site = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert '"/projections/"' in site, "NAV_ITEMS must deep-link /projections/"
    assert "build_projections" in site
    page = ROOT / "projections" / "index.html"
    if page.exists():
        src = page.read_text(encoding="utf-8")
        assert "projections.js" in src and "proj-rows" in src

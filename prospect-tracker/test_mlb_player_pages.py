# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB player pages + Swing+ + CollegeSavant integration pins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _load(rel: str):
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} not generated on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# MLB player detail sidecar
# ---------------------------------------------------------------------------

def test_player_detail_shape_and_coverage():
    d = _load("data/mlb_player_detail.json")
    assert d["n_players"] > 1000
    cov = d["coverage"]
    # the identity join must cover the overwhelming majority
    assert cov["career"] > 0.85 * d["n_players"]
    assert cov["statcast"] > 0.8 * d["n_players"]
    assert cov["arsenal"] > 300            # pitchers only
    # spot a star: hero fields + proj + career + statcast block
    p = d["players"].get("juan_soto")
    assert p and p["mlbam"] and p["career"] and p["sc"]["metrics"]
    assert p["proj"]["warTotal"] is not None


def test_player_detail_fa_members_attached():
    d = _load("data/mlb_player_detail.json")
    fa = [p for p in d["players"].values() if p.get("fa")]
    assert len(fa) > 150
    m = fa[0]["fa"]
    assert "projAav" in m and "verdict" in m


def test_projections_app_has_player_route():
    src = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    for needle in ("renderPlayer", "mlb_player_detail.json", "#player=",
                   "Statcast Percentiles", "Pitch Arsenal"):
        assert needle in src, needle


def test_fa_card_links_full_player_page():
    src = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
    assert "/projections/#player=" in src


# ---------------------------------------------------------------------------
# Swing+ (external model, MLB bat tracking only)
# ---------------------------------------------------------------------------

def test_swing_plus_sidecar_sane():
    d = _load("data/swing_plus.json")
    assert "MLB bat tracking 2024+" in d["data_boundary"]
    vals = [r["swing_plus"] for r in d["players"].values()]
    assert vals, "no scored hitters"
    assert all(40 <= v <= 180 for v in vals)
    assert all(r["n_swings"] > 0 for r in d["players"].values())


def test_swing_plus_registered_honestly():
    import model_registry as mr
    row = next(m for m in mr.load()["models"]
               if m["model_id"] == "swing_plus_external")
    assert row["verdict"] == "unvalidated" and not row["eval_artifact"]
    assert "MiLB" in row["notes"]          # the data boundary is stated


def test_prospx_swing_plus_wiring():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "function getSwingPlus" in src
    assert "swing_plus.json" in src
    assert 'chip("Swing+"' in src


# ---------------------------------------------------------------------------
# CollegeSavant module
# ---------------------------------------------------------------------------

def test_collegesavant_mounted_with_site_chrome():
    for page in ("collegesavant/index.html", "collegesavant/pitcher_index.html"):
        t = (ROOT / page).read_text(encoding="utf-8")
        assert '/assets/site.css' in t
        assert 'class="eephus-nav"' in t
        assert 'href="/collegesavant/" class="is-active"' in t
        assert "eephusToggleTheme" in t


def test_collegesavant_logos_present():
    logos = list((ROOT / "collegesavant" / "logos").glob("*.png"))
    assert len(logos) >= 16


def test_collegesavant_token_bridge():
    css = (ROOT / "collegesavant" / "styles.css").read_text(encoding="utf-8")
    assert "--ink: var(--text-primary" in css
    assert "--paper: var(--bg-primary" in css


def test_nav_order_and_dividers():
    bs = (ROOT / "build_site.py").read_text(encoding="utf-8")
    i_prospx = bs.index('("prospx",')
    i_cs = bs.index('("collegesavant",')
    i_fa = bs.index('("fa",')
    assert i_prospx < i_cs < i_fa, "CollegeSavant sits directly under PROSPX"
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    assert "border-left: 1px solid var(--border)" in css


# ---------------------------------------------------------------------------
# Unified player hub (cross-module identity + share cards)
# ---------------------------------------------------------------------------

def test_player_links_map():
    d = _load("data/player_links.json")
    assert len(d["byKey"]) > 1000 and len(d["byMlbam"]) > 1000
    ex = [r for r in d["byKey"].values() if r.get("prospx")]
    assert len(ex) > 500, "ex-prospect links collapsed"
    assert all(set(r) >= {"key", "mlbam", "fa", "prospx"} for r in ex[:20])


def test_hub_lib_and_strips_wired():
    hub = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
    for needle in ("player_links.json", "stripHTML", "shareCard", "EEPHUS_HUB"):
        assert needle in hub, needle
    assert "eephus-hub.js" in (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert "eephus-hub.js" in (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "px-hub" in (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    fa = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
    assert "fa-hub" in fa and "sharePlayerCard" in fa
    pj = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "mlbp-hub" in pj and "shareMlbCard" in pj


def test_mlb_detail_carries_origin():
    d = _load("data/mlb_player_detail.json")
    org = [p for p in d["players"].values() if p.get("origin")]
    assert len(org) > 500
    assert all(p["origin"].get("prospx") for p in org[:10])

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Drift guard for the GENERATED audit deliverables at the repo root.

MODEL_REGISTRY.md, SITE_MAP.md and DATA_SOURCES.md are written by
tools/gen_audit_docs.py from committed inputs (data/model_registry.json,
build_site.NAV_ITEMS + main(), run_monthly.py's phase structure, the client
apps' payload fetches). Nothing else forces the committed copies to track
those inputs, so a nav change, a new registry row, or a new pipeline phase
would silently strand the docs.

Same pattern as test_collegesavant_nav_in_sync.py: regenerate in memory and
byte-compare against the committed file. The generator is deterministic by
contract (it renders the registry's own stamped freshness fields, never live
mtime ages), so equal inputs mean equal bytes. DATA_SOURCES.md's curated
block round-trips through the generator verbatim, so hand edits BETWEEN the
CURATED sentinels never trip this test; edits anywhere else do. The one
tolerated difference is CRLF vs LF: core.autocrlf=true rewrites checkouts,
so committed bytes are normalized to LF before comparing (the generator
always writes LF).

On failure: run `python tools/gen_audit_docs.py` and commit the result.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parent

_GEN = None


def _gen():
    """Load tools/gen_audit_docs.py once (tools/ is not a package)."""
    global _GEN
    if _GEN is None:
        spec = importlib.util.spec_from_file_location(
            "gen_audit_docs", ROOT / "tools" / "gen_audit_docs.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _GEN = mod
    return _GEN


@pytest.mark.parametrize("name", ["MODEL_REGISTRY.md", "SITE_MAP.md", "DATA_SOURCES.md"])
def test_generated_doc_in_sync(name: str):
    gen = _gen()
    path = ROOT / name
    assert path.exists(), (
        f"{name} is missing - run `python tools/gen_audit_docs.py` and commit it."
    )
    committed = path.read_bytes().replace(b"\r\n", b"\n")
    rendered = gen.render_one(name).encode("utf-8")
    assert rendered.decode("utf-8").startswith(gen.GEN_HEADER)
    assert committed == rendered, (
        f"{name} is out of sync with its generator inputs (nav/registry/pipeline "
        f"changed, or the file was hand-edited) - run `python tools/gen_audit_docs.py` "
        f"and commit the result."
    )


def test_curated_block_present_in_data_sources():
    """The curated prose block must survive regeneration; losing the sentinels
    would silently turn hand-maintained source-risk notes into generator
    output on the next run."""
    gen = _gen()
    text = (ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8")
    assert gen.CURATED_BEGIN in text and gen.CURATED_END in text, (
        "DATA_SOURCES.md lost its CURATED sentinels - restore them (see "
        "tools/gen_audit_docs.py _DEFAULT_CURATED) before regenerating."
    )
    assert text.index(gen.CURATED_BEGIN) < text.index(gen.CURATED_END)


def test_readme_routes_block_in_sync():
    """Census X07-09 (2026-09-25): the README routes table listed 9 of 33
    routes by hand. The block between the ROUTES sentinels is rendered from
    build_site.NAV_ITEMS and build_site.main(); a new page without a
    regeneration fails here."""
    gen = _gen()
    text = (ROOT / "README.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert gen.README_ROUTES_BEGIN in text and gen.README_ROUTES_END in text, (
        "README.md lost its ROUTES sentinels")
    begin = text.index(gen.README_ROUTES_BEGIN)
    end = text.index(gen.README_ROUTES_END) + len(gen.README_ROUTES_END)
    assert text[begin:end] == gen.render_readme_routes(), (
        "README.md routes block is out of sync - run `python tools/gen_audit_docs.py`")


def test_the_site_map_lists_the_scores_page():
    """SCORES_5a_LIVE_FLIP (2026-10-07): main() writes /scores/ by literal, so
    the generated site map and README routes list it with its route note, and
    the registry doc carries its three rows."""
    gen = _gen()
    site_map = gen.render_one("SITE_MAP.md")
    row = next(ln for ln in site_map.splitlines() if ln.startswith("| `/scores/` |"))
    assert "`build_site.build_scores()`" in row and "Scores / Standings" in row
    assert "| `/scores/` | Scores / Standings" in gen.render_readme_routes()
    reg = gen.render_one("MODEL_REGISTRY.md")
    for mid in ("scores_mlb_wp", "scores_stars_rule", "scores_biggest_plays_rule"):
        assert f"`{mid}`" in reg, mid

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""deploy/publish_paths.txt is the ONE list of browser-served paths, consumed
by both deploy paths (deploy/nightly-build.sh rsync and the GitHub workflow's
staging step). Production shipped nav links to 404s for days because the two
hardcoded copies of this list drifted from the actual page dirs - these pins
make that drift a red suite instead of a live outage."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
MANIFEST = ROOT / "deploy" / "publish_paths.txt"

# Build/dev dirs that legitimately live next to the page dirs but must never
# ship. Anything NEW that grows an index.html and isn't listed here must be
# added to the manifest (that is the point of the test).
_NON_PUBLIC = {
    "__pycache__", ".cache", "branding", "config", "content", "data",
    "deploy", "docs", "logs", "model", "news_src", "report_src", "reports",
    "supabase", "test_fixtures", "tools",
}


def _manifest_paths() -> list[str]:
    out = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_manifest_paths_all_exist():
    """A manifest entry that doesn't exist in the tree means a typo or a
    deleted module - either way the deploy would silently ship nothing."""
    missing = [p for p in _manifest_paths() if not (ROOT / p).exists()]
    assert not missing, f"publish manifest lists nonexistent paths: {missing}"


def test_every_page_dir_is_in_manifest():
    """Every top-level dir with an index.html is a public surface and must
    ship. mlbstats/pal/trademachine/news/report 404'd in production because
    they were added as pages but never added to the (then-hardcoded) deploy
    lists."""
    manifest = set(_manifest_paths())
    unshipped = [
        d.name for d in ROOT.iterdir()
        if d.is_dir() and (d / "index.html").exists()
        and d.name not in _NON_PUBLIC and d.name not in manifest
    ]
    assert not unshipped, (
        f"page dirs missing from deploy/publish_paths.txt: {unshipped} - "
        "they will 404 in production")


def test_vendor_ships():
    """prospx references /vendor/*.js at runtime; vendor/ has no index.html
    so the page-dir sweep above doesn't cover it."""
    assert "vendor" in _manifest_paths()


def test_sitemap_surfaces_are_shipped():
    """Every path build_sitemap() advertises to crawlers must resolve on the
    deployed site: its top-level segment must be in the manifest."""
    import build_site
    manifest = set(_manifest_paths())
    sitemap = build_site.build_sitemap([])
    for url in re.findall(r"<loc>([^<]*)</loc>", sitemap):
        loc = url.removeprefix(build_site.SITE_ORIGIN)
        seg = loc.strip("/").split("/")[0]
        if not seg:  # "/" home - index.html ships as a root file
            continue
        assert seg in manifest, (
            f"sitemap advertises {loc} but '{seg}' is not in "
            "deploy/publish_paths.txt - crawlers get a 404")


def test_data_js_ships():
    """data/value_framework.js and the collegesavant data scripts are hard
    <script src> deps under /data/ - json-only data shipping 404'd them in
    production (found 2026-07-14). Both deploy paths must ship data/*.js."""
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "--include='/data/*.js'" in nightly
    workflow = (ROOT.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    assert "-name '*.js'" in workflow


def test_deploy_consumers_read_the_manifest():
    """Both deploy paths must consume the shared manifest, not a hardcoded
    list (drift between two hardcoded lists caused the July 2026 404s)."""
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "publish_paths.txt" in nightly
    assert "data_exclude.txt" in nightly
    workflow = (ROOT.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    assert "publish_paths.txt" in workflow
    assert "data_exclude.txt" in workflow


def _excluded_data_files() -> list[str]:
    out = []
    for line in (ROOT / "deploy" / "data_exclude.txt").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_excluded_data_is_not_fetched_by_any_page():
    """A file in data_exclude.txt never reaches the webroot, so a runtime
    reference to it would 404 in production while working in dev. Quoted
    '/data/<name>' is the fetch()/src= form; bare comment mentions pass.
    (This pin caught xfv_ungraded.json, which looked like an internal but
    IS fetched by the board - it ships.)"""
    pages = []
    for p in [ROOT / "index.html", *ROOT.glob("*/index.html"),
              *ROOT.glob("assets/*.js"),
              ROOT / "collegesavant" / "pitcher_index.html"]:
        if p.exists():
            pages.append((p, p.read_text(encoding="utf-8", errors="replace")))
    for name in _excluded_data_files():
        for path, src in pages:
            for quote in ('"', "'", "`"):
                # '/data/<name>' is the direct fetch()/src= form; the bare
                # '<name>' quoted form catches base-path concatenation
                # (fetch(base + "grpo_scores.json") dodged the old needle).
                for needle in (f"{quote}/data/{name}", f"{quote}{name}{quote}"):
                    assert needle not in src, (
                        f"{path.name} references {name} at runtime but "
                        "deploy/data_exclude.txt stops it from shipping - "
                        "remove it from the exclude list or drop the fetch")


def test_excluded_data_is_not_a_registry_artifact():
    """model_registry.json eval artifacts are publicly hyperlinked from the
    glossary Models & Proofs table (assets/glossary.js renders <a href>
    per row), so excluding one would 404 the site's own proof links."""
    reg = json.loads((ROOT / "data" / "model_registry.json")
                     .read_text(encoding="utf-8"))
    arts: set[str] = set()

    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "eval_artifact" and isinstance(v, str):
                    arts.add(v.removeprefix("data/"))
                else:
                    _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    _walk(reg)
    offenders = [n for n in _excluded_data_files() if n in arts]
    assert not offenders, (
        f"data_exclude.txt lists registry eval artifacts {offenders} - "
        "they are publicly linked from Models & Proofs and must ship")

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


def _slices_dir_shards() -> list[str]:
    """The runtime-fetched shard directories the boot payload advertises under
    storage.py's `_slices_dir` dict literal, extracted by regex over the source
    (no import / no synthetic export needed). Values are the shard dir paths
    (e.g. "pitch_plots/"); dict keys never end in '/', so the quoted strings
    that DO end in '/' are exactly the advertised dirs."""
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    m = re.search(r'"_slices_dir"\s*:\s*\{([^}]*)\}', src)
    assert m, "could not locate the _slices_dir dict literal in storage.py"
    dirs = [v.rstrip("/") for v in re.findall(r'"([^"]+/)"', m.group(1))]
    assert dirs, "no shard directories parsed from storage.py _slices_dir"
    return dirs


def _ships_in_nightly(nightly: str, d: str) -> bool:
    """True if deploy/nightly-build.sh ships shard dir `d`. Robust to quote
    style / glob depth: an rsync `--include=/data/<d>/...` (any quoting) or a
    `cp -r data/<d>` both count."""
    esc = re.escape(d)
    return bool(
        re.search(rf"--include=['\"]?/data/{esc}/", nightly)
        or re.search(rf"cp\s+-r\s+data/{esc}\b", nightly))


def _ships_in_workflow(workflow: str, d: str) -> bool:
    """True if the CI workflow stages shard dir `d` into the webroot. Accepts
    `cp -r data/<d>`, an rsync include, or an explicit `_site/data/<d>` stage -
    robust to the copy mechanism, but requires an actual ship (not a bare
    comment mention)."""
    esc = re.escape(d)
    return bool(
        re.search(rf"cp\s+-r\s+data/{esc}\b", workflow)
        or re.search(rf"--include=['\"]?/data/{esc}/", workflow)
        or re.search(rf"_site/data/{esc}\b", workflow))


def test_slices_dir_shards_ship_in_both_deploy_consumers():
    """Runtime-fetched shard dirs (debuts_full/, player_detail/, pitch_plots/)
    are advertised by storage._slices_dir and fetched by prospx, but shipped by
    SEPARATE hardcoded lines in each deploy consumer with no cross-check. That
    is the A1 root-cause class: debuts_full was advertised + fetched but shipped
    by neither path, so every graduate card silently 404'd to the monolith while
    the whole suite stayed green. Guard the class - every _slices_dir shard must
    ship in BOTH the nightly rsync includes AND the CI staging step."""
    shards = _slices_dir_shards()
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    for d in shards:
        assert _ships_in_nightly(nightly, d), (
            f"storage._slices_dir advertises shard dir '{d}/' but "
            f"deploy/nightly-build.sh never ships /data/{d}/ (no rsync "
            f"--include) - it will 404 in production")
    wf_path = (ROOT.parent / ".github" / "workflows"
               / "deploy-prospect-tracker.yml")
    if wf_path.exists():   # CI workflow lives one dir up; skip if not checked out
        workflow = wf_path.read_text(encoding="utf-8")
        for d in shards:
            assert _ships_in_workflow(workflow, d), (
                f"storage._slices_dir advertises shard dir '{d}/' but the CI "
                f"workflow's staging step never copies data/{d}/ - it will 404 "
                "in production")


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


# Name shapes that carry the label side of a fit: the eFV training matrices
# (canonical, live and any suffixed arm like xfv_hitter_matrix__E0.json), the
# scored frames and the star label view. The withhold list matches exact names,
# so a new file of one of these shapes at data/ depth one ships by default.
_WITHHELD_SHAPES = ("xfv_*matrix*", "*_matrix__*", "xfv_scored*", "star_label*")


def test_label_shaped_data_is_withheld_or_absent():
    """Every top-level data/*.json whose name has a withheld shape is on
    deploy/data_exclude.txt. Both deploy consumers ship data/*.json at depth
    one, so an unlisted label file (the E0 arm matrix, found 2026-09-24) goes
    to the webroot. Arm and lab matrices belong under data/_labs/, which
    neither consumer ships."""
    from fnmatch import fnmatch
    excluded = set(_excluded_data_files())
    shipped = sorted(p.name for p in (ROOT / "data").glob("*.json")
                     if p.is_file() and p.name not in excluded)
    leaks = [n for n in shipped
             if any(fnmatch(n, pat) for pat in _WITHHELD_SHAPES)]
    assert not leaks, (
        f"label-shaped data files ship to the webroot: {leaks}. Add each to "
        "deploy/data_exclude.txt, or move it under data/_labs/")


def test_labs_dir_ships_in_neither_deploy_consumer():
    """data/_labs/ is where arm matrices live because it never ships: the
    rsync takes /data/*.json plus named subdirs, the workflow copies
    data/*.json at maxdepth 1 plus named subdirs. Neither may name _labs."""
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    workflow = (ROOT.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    assert "_labs" not in nightly and "_labs" not in workflow
    assert "--include='/data/*.json'" in nightly
    assert "find data -maxdepth 1" in workflow
    assert "data/_labs" not in _manifest_paths()



def test_mlbtr_arb_ledger_is_a_lab_file_not_a_served_one():
    """Owner answer M23-3 (2026-09-25): the MLB Trade Rumors arbitration
    ledger (2,032 entries, fetched by no page) moved from data/ depth one,
    which both deploy consumers ship, to data/_labs/, which neither ships. It
    is not listed in data_exclude.txt on purpose: rsync --delete removes the
    old webroot copy only while the name is unlisted. The panel loader and
    the ingest tool both point at the lab path."""
    import importlib.util
    import arb_dataset
    assert not (ROOT / "data" / "arb_ledger.json").exists()
    assert "arb_ledger.json" not in _excluded_data_files()
    src = (ROOT / "arb_dataset.py").read_text(encoding="utf-8")
    assert '"data" / "_labs" / "arb_ledger.json"' in src
    assert callable(arb_dataset.load_ledger)
    spec = importlib.util.spec_from_file_location(
        "_ingest_arb_ledger_probe", ROOT / "tools" / "ingest_arbitration_ledger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.LEDGER_PATH == ROOT / "data" / "_labs" / "arb_ledger.json"

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


def test_ledger_clubs_shards_ship_in_both_deploy_consumers():
    """D5 (2026-09-24): the Club Ledger's per-club row files (data/ledger_clubs/
    CODE.json, fetched by /ledger/ on demand) are not a storage._slices_dir
    shard, so the helper test above would never notice them missing. Same
    class of defect, same guard: both consumers must name the directory."""
    d = "ledger_clubs"
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert _ships_in_nightly(nightly, d), "deploy/nightly-build.sh never ships /data/ledger_clubs/"
    wf_path = ROOT.parent / ".github" / "workflows" / "deploy-prospect-tracker.yml"
    if wf_path.exists():
        assert _ships_in_workflow(wf_path.read_text(encoding="utf-8"), d), "the CI workflow never copies data/ledger_clubs/"
    assert "ledger_clubs" in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "ledger.js").read_text(encoding="utf-8")
    assert 'var SHARD_URL = "/data/ledger_clubs/";' in js, "the page fetches the directory both consumers ship"


def test_franchise_clubs_ship_in_both_deploy_consumers():
    """QCLP10 (2026-10-03): the /franchise/ club page fetches its club's tree
    and sections from data/franchise_clubs/CODE.json, so both consumers must
    ship the directory, as with ledger_clubs/ above."""
    d = "franchise_clubs"
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert _ships_in_nightly(nightly, d), "deploy/nightly-build.sh never ships /data/franchise_clubs/"
    wf_path = ROOT.parent / ".github" / "workflows" / "deploy-prospect-tracker.yml"
    if wf_path.exists():
        assert _ships_in_workflow(wf_path.read_text(encoding="utf-8"), d), "the CI workflow never copies data/franchise_clubs/"
    assert "franchise_clubs" in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "franchise.js").read_text(encoding="utf-8")
    assert 'var SHARD_URL = "/data/franchise_clubs/";' in js, "the page fetches the directory both consumers ship"


def test_mlb_events_dir_ships_in_both_deploy_consumers():
    """Q9_22a (2026-10-03): the per-player MLB transaction files (data/mlb_events/
    <mlbam>.json, index.json and recent.json, written by mlb_events.py once
    MLB_EVENTS_LIVE flips) are not a storage._slices_dir shard either, so they get
    the ledger_clubs guard: both consumers name the directory before the flip, so
    the flip only writes files. The directory is gitignored."""
    d = "mlb_events"
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert _ships_in_nightly(nightly, d), "deploy/nightly-build.sh never ships /data/mlb_events/"
    wf_path = ROOT.parent / ".github" / "workflows" / "deploy-prospect-tracker.yml"
    if wf_path.exists():
        assert _ships_in_workflow(wf_path.read_text(encoding="utf-8"), d), "the CI workflow never copies data/mlb_events/"
    assert "mlb_events/" in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    assert "data/mlb_events/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    src = (ROOT / "mlb_events.py").read_text(encoding="utf-8")
    assert 'SERVED_DIR = DATA / "mlb_events"' in src, "the writer fills the directory both consumers ship"

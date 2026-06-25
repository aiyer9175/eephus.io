# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA module's PROSPX contract: READ-ONLY, SEPARATE SURFACE.

Static source guards (cheap, run on every suite pass):
  1. No fa_* module may write to any non-fa table — every storage upsert
     it touches must be an upsert_fa_* accessor, and any raw SQL INSERT/
     UPDATE/DELETE must target fa_* tables only.
  2. The FA module is its own surface (/fa/ via build_site.py::build_fa +
     assets/fa.js): the PROSPX app carries ZERO FA bytes — no render code,
     no sidecar loads, no boot keys, no `_slices` advertisement — and the
     FA app loads nothing from the PROSPX boot payload.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
FA_MODULES = ["fa_sources.py", "fa_cba.py", "fa_class.py", "fa_projection.py",
              "fa_market.py", "fa_fit.py", "fa_export.py", "fa_backtest.py",
              "fa_pipeline.py", "fa_ident.py"]


def test_fa_modules_never_write_prospect_tables():
    for mod in FA_MODULES:
        src = (ROOT / mod).read_text(encoding="utf-8")
        # storage accessor calls: only fa-prefixed upserts allowed
        for call in re.findall(r"\bupsert_(\w+)", src):
            assert call.startswith("fa_") or mod == "fa_backtest.py" and call.startswith("fa_"), \
                f"{mod} calls upsert_{call} — non-FA write"
        # raw SQL: any INSERT/UPDATE/DELETE must hit fa_* tables
        for stmt in re.findall(r"(?i)\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)", src):
            table = stmt[1].lower()
            assert table.startswith("fa_"), f"{mod} raw SQL touches {table}"


def test_fa_storage_accessors_only_touch_fa_tables():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    fa_section = src.split("MLB Free Agency module — storage accessors")[-1]
    for stmt in re.findall(r"(?i)\b(?:INSERT\s+INTO|FROM)\s+\{?([a-z_{}]+)", fa_section):
        t = stmt.strip("{}").lower()
        if t in ("table",):                      # the parameterized helper
            continue
        assert t.startswith("fa_"), f"FA storage section references {t}"


def test_boot_export_carries_no_fa():
    """The FA module adds ZERO bytes to the PROSPX boot payload — no
    top-level keys and (since the /fa/ split) no `_slices` advertisement
    either; assets/fa.js fetches the sidecars from /data/ directly."""
    boot = ROOT / "data" / "timeseries.json"
    if not boot.exists():
        pytest.skip("no boot export on this machine")
    d = json.loads(boot.read_text(encoding="utf-8"))
    for k in ("fa_class", "fa_archive", "fa_meta"):
        assert k not in d, f"{k} leaked into the boot payload"
        assert k not in d.get("_slices", {}), f"{k} still advertised in _slices"


def test_prospx_app_carries_no_fa_code():
    """PROSPX (prospx/index.html) ships no FA surface: no section, no render
    code, no sidecar fetches. The only sanctioned reference is the legacy
    #tab=fa redirect to /fa/."""
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    for marker in ('data-section="fa"', "renderFA", "fa_class", "fa_archive",
                   "fa_meta", "_faRender", "mGuarantee"):
        assert marker not in src, f"PROSPX still carries FA marker {marker!r}"
    assert 'window.location.replace("/fa/")' in src, "legacy #tab=fa redirect missing"


def test_fa_app_is_standalone():
    """assets/fa.js touches only the fa_* sidecars — it never loads the
    PROSPX boot payload or any other PROSPX data file. The class loader
    is year-dynamic since the winter selector (fa_class for the current
    default, fa_class_{Y} for exported future winters)."""
    src = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
    assert 'state.classYear ? `fa_class_${state.classYear}` : "fa_class"' in src, \
        "fa.js lost the year-dynamic class loader"
    assert "load(clsName)" in src, "fa.js never loads the class sidecar"
    for name in ("fa_archive", "fa_meta"):
        assert f'load("{name}")' in src, f"fa.js never loads {name}"
    assert "timeseries.json" not in src, "fa.js must not read the PROSPX boot payload"
    fetches = re.findall(r"fetch\(([^)]+)\)", src)
    assert fetches == ["`/data/${name}.json`, { cache: \"no-cache\" }"], \
        f"unexpected fetch targets in fa.js: {fetches}"


def test_fa_page_generated_and_wired():
    """The /fa/ shell exists (build_site.py::build_fa), mounts the app, and
    the homepage nav points at /fa/ — not at a PROSPX tab."""
    page = ROOT / "fa" / "index.html"
    if not page.exists():
        pytest.skip("fa/index.html not generated on this machine (run build_site.py)")
    src = page.read_text(encoding="utf-8")
    assert "/assets/fa.js?v=" in src and 'class="fa-app"' in src
    site = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert '"/fa/"' in site, "NAV_ITEMS must deep-link /fa/"
    assert not re.search(r"#tab=fa\b", site), \
        "build_site.py still links the retired PROSPX fa tab"


def test_sidecars_exist_and_parse():
    for name in ("fa_class.json", "fa_archive.json", "fa_meta.json"):
        path = ROOT / "data" / name
        if not path.exists():
            pytest.skip(f"{name} not exported on this machine")
        d = json.loads(path.read_text(encoding="utf-8"))
        assert d.get("generated_at")
    cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    assert cls["n_members"] > 150 and cls["n_projected"] > 100
    top = cls["members"][0]
    # the board's two numbers ride every projected member, never conflated
    assert "projGuar" in top and "rational" in top and "surplus" in top
    assert top["surplus"] == top["rational"] - top["projGuar"]
    # v2 surfaces: verdict string + probability buckets on projected members
    assert top.get("verdict") in ("value", "market", "overpay")
    assert top["warTotalP10"] <= top["warTotal"] <= top["warTotalP90"]

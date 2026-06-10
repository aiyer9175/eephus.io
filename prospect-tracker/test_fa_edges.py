# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Stage-7 edge handling: owner overrides, thin-platform disclosure,
source-freshness stamps. Loader logic is unit-tested against temp files;
artifact assertions skip when no export exists on the machine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


# ---- data/fa_overrides.json loader -------------------------------------------

def test_overrides_loader_skips_docs_and_bad_shapes(tmp_path, monkeypatch):
    import fa_export
    monkeypatch.setattr(fa_export, "DATA_DIR", tmp_path)
    (tmp_path / "fa_overrides.json").write_text(json.dumps({
        "_doc": ["ignored"],
        "players": {
            "_example": {"two_way": True},
            "real_guy": {"note": "owner note", "exclude": False},
            "bad_shape": "not-a-dict",
            "gone_guy": {"exclude": True},
        },
    }), encoding="utf-8")
    ovr = fa_export._load_overrides()
    assert set(ovr) == {"real_guy", "gone_guy"}
    assert ovr["real_guy"]["note"] == "owner note"
    assert ovr["gone_guy"]["exclude"] is True


def test_overrides_loader_absent_file_is_empty(tmp_path, monkeypatch):
    import fa_export
    monkeypatch.setattr(fa_export, "DATA_DIR", tmp_path)
    assert fa_export._load_overrides() == {}


def test_shipped_overrides_file_parses():
    import fa_export
    path = ROOT / "data" / "fa_overrides.json"
    assert path.exists(), "data/fa_overrides.json must ship with the repo"
    ovr = fa_export._load_overrides()
    # only documentation entries ship by default — no live overrides yet
    assert all(not k.startswith("_") for k in ovr)


# ---- exported artifact: dedup, thin platform, freshness -----------------------

def _cls():
    path = ROOT / "data" / "fa_class.json"
    if not path.exists():
        pytest.skip("no export on this machine")
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_has_no_duplicate_keys_and_options_win():
    d = _cls()
    keys = [m["key"] for m in d["members"] if m.get("key")]
    assert len(keys) == len(set(keys)), "duplicate player_key in export"
    mc = next((m for m in d["members"] if m["key"] == "ryan_mountcastle"), None)
    if mc is not None:   # only meaningful while he's in the constructed class
        assert mc["type"] != "ufa", "double-listing dedup must keep the option row"


def test_thin_platform_flags_are_disclosed_not_epidemic():
    d = _cls()
    ms = d["members"]
    thin = [m for m in ms if m.get("thinPlatform")]
    projected = [m for m in ms if m.get("warY1") is not None]
    assert thin, "an FA class with zero injury-thin platforms is implausible"
    assert len(thin) <= 0.35 * len(projected), (
        f"{len(thin)}/{len(projected)} thin flags — the role-aware exposure "
        "floor is mis-scaled (relievers measured against an SP season?)")
    # The poster case: a projection riding NO platform season must be flagged.
    for m in ms:
        if m.get("key") == "corbin_burnes" and m.get("warY1") is not None:
            assert m.get("thinPlatform"), "Burnes-type missing-platform must flag"


def test_meta_sources_freshness_stamps():
    path = ROOT / "data" / "fa_meta.json"
    if not path.exists():
        pytest.skip("no export on this machine")
    meta = json.loads(path.read_text(encoding="utf-8"))
    src = meta.get("sources")
    assert src and "class" in src
    for label, day in src.items():
        assert len(day) == 10 and day[4] == "-" and day[7] == "-", (label, day)

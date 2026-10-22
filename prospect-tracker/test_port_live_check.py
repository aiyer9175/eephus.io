# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/port_live_check.py: the read-only origin check of PORT_RUNBOOK.md (Gate B).

Offline: the fetcher is replaced by a fake origin, so the test proves the check
fails on each defect class it exists for (a missing page, a changed asset, a
missing payload, a withheld file served) and passes on a faithful origin."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import port_live_check as plc  # noqa: E402


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "mod"
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "publish_paths.txt").write_text("index.html\nfa\n", encoding="utf-8")
    (root / "deploy" / "data_exclude.txt").write_text("secret.json\n", encoding="utf-8")
    (root / "index.html").write_text("<p>home</p>", encoding="utf-8")
    (root / "fa").mkdir()
    (root / "fa" / "index.html").write_text("<p>fa</p>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "site.css").write_text("a{}", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "a.json").write_text("{}", encoding="utf-8")
    (root / "data" / "secret.json").write_text("{}", encoding="utf-8")
    return root


def _fake(root: Path, override: dict):
    def fetch(url, save, head=False):
        rel = url.split("://x/", 1)[1]
        if rel in override:
            code, body = override[rel]
        elif rel == "data/build_info.json":
            code, body = 200, b'{"git_sha": "abc"}'
        elif rel == "data/secret.json":
            code, body = 404, b""
        else:
            src = root / rel
            code, body = (200, src.read_bytes()) if src.is_file() else (404, b"")
        if save is not None and code == 200:
            save.write_bytes(body)
        return code
    return fetch


def test_targets_follow_the_manifests(tmp_path):
    t = plc.targets(_tree(tmp_path))
    assert t == {"pages": ["fa/index.html", "index.html"], "assets": ["assets/site.css"],
                 "data": ["data/a.json"], "withheld": ["data/secret.json"]}


def test_faithful_origin_passes(tmp_path):
    root = _tree(tmp_path)
    res = plc.check("https://x", root, fetch=_fake(root, {}), workers=1)
    assert res["ok"] and res["build_info"] == {"git_sha": "abc"}


def test_each_defect_class_fails(tmp_path):
    root = _tree(tmp_path)
    bad = {"fa/index.html": (404, b""), "assets/site.css": (200, b"b{}"),
           "data/a.json": (404, b""), "data/secret.json": (200, b"{}")}
    res = plc.check("https://x", root, fetch=_fake(root, bad), workers=1)
    assert not res["ok"]
    assert res["summary"] == {"pages_missing": 1, "pages_differ": 0, "assets_missing": 0,
                              "assets_differ": 1, "data_missing": 1, "withheld_served": 1}
    res = plc.check("https://x", root, fetch=_fake(root, {"assets/site.css": (200, b"b{}")}),
                    stripped=True, workers=1)
    assert res["ok"], "a stripped asset is checked for presence only"

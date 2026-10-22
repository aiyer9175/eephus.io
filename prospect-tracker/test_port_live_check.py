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

# --------------------------------------------------------------------------- #
# Pacing and the 36-hour bundle heartbeat
# --------------------------------------------------------------------------- #
import datetime as _dt  # noqa: E402
import json  # noqa: E402

_NOW = _dt.datetime(2026, 10, 22, 12, 0, 0, tzinfo=_dt.timezone.utc)


def test_pacer_spaces_request_starts():
    t = [0.0]
    slept: list = []

    def sleep(s):
        slept.append(round(s, 3))
        t[0] += s

    p = plc.Pacer(0.5, sleep=sleep, clock=lambda: t[0])
    for _ in range(3):
        p.wait()
    assert slept == [0.5, 0.5]
    t[0] += 2.0
    p.wait()
    assert slept == [0.5, 0.5], "no wait once the gap has passed"
    plc.Pacer(0).wait()


def test_check_paces_every_request(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    waits: list = []
    monkeypatch.setattr(plc.Pacer, "wait", lambda self: waits.append(1))
    res = plc.check("https://x", root, fetch=_fake(root, {}), workers=1, pace=0.1)
    assert res["ok"] and len(waits) == 1 + sum(len(v) for v in plc.targets(root).values())


def _hb_origin(docs: dict):
    def fetch_raw(url):
        rel = url.split("://x/", 1)[1]
        assert rel != "data/build_info.json", "the Go Build heartbeat is never read"
        if rel in docs:
            val = docs[rel]
            if isinstance(val, tuple):
                return val
            return 200, json.dumps(val).encode("utf-8"), {}
        return 404, b"", {}
    return fetch_raw


def test_heartbeat_reads_the_receive_time():
    res = plc.heartbeat("https://x", now=_NOW, fetch_raw=_hb_origin({
        plc.RECEIPT: {"received_at": "2026-10-21T02:00:00Z", "bundle_id": "b1"},
        plc.BUNDLE_INFO: {"built_at": "2026-10-10T00:00:00Z"}}))
    assert res["ok"] and res["source"] == plc.RECEIPT
    assert res["age_hours"] == 34.0 and res["bundle_id"] == "b1"


def test_heartbeat_alarms_past_36_hours():
    res = plc.heartbeat("https://x", now=_NOW, fetch_raw=_hb_origin({
        plc.RECEIPT: {"received_at": "2026-10-20T23:59:00Z"}}))
    assert not res["ok"] and res["age_hours"] == 36.02 and "36.0 h" in res["reason"]


def test_heartbeat_falls_back_to_built_at_and_alarms_on_nothing():
    res = plc.heartbeat("https://x", now=_NOW, fetch_raw=_hb_origin({
        plc.BUNDLE_INFO: {"built_at": "2026-10-22T02:00:00Z", "bundle_id": "b2"}}))
    assert res["ok"] and res["source"] == plc.BUNDLE_INFO and res["age_hours"] == 10.0
    res = plc.heartbeat("https://x", now=_NOW, fetch_raw=_hb_origin({
        plc.RECEIPT: (403, b"<title>Just a moment...</title>", {"cf-mitigated": "challenge"})}))
    assert not res["ok"] and res["source"] is None
    assert res[f"{plc.RECEIPT}_code"] == "403 (challenge)"

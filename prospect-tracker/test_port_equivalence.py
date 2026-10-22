# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/port_equivalence.py: the port's served-payload differ (PORT_SPEC.md Gate C).

Pins the published set to deploy/nightly-build.sh's rsync include lines, the
category ladder (IDENTICAL, TIMESTAMP, FLOAT_REPR, ORDERING, DIFFERENT), and a
positive control: a one-unit change in the last serialized place of one leaf
is reported as exactly that leaf."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import port_equivalence as pe  # noqa: E402


def test_per_player_dirs_match_the_nightly_rsync():
    sh = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    dirs = set(re.findall(r"--include='/data/([a-z_]+)/\*\*\*'", sh))
    assert dirs == set(pe.PER_PLAYER_DIRS)


def test_publish_only_mode_skips_pull_pip_and_pipeline():
    """EEPHUS_SKIP_PIPELINE=1 (the runbook's first publish) guards exactly the
    three steps that would change the seeded tree; the gate and rsync still run."""
    sh = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert ('if [ "$SKIP_PIPELINE" != "1" ]; then\n  git -C "$REPO" checkout -- .\n'
            '  git -C "$REPO" pull --ff-only\nfi') in sh
    assert 'if [ "$SKIP_PIPELINE" != "1" ]; then\n  pip install -q -r requirements.txt\nfi' in sh
    assert 'if [ "$SKIP_PIPELINE" = "1" ]; then\n  echo "--- publish-only' in sh
    tail = sh.split("MODE=publish-only", 1)[1]
    assert tail.index("python run_monthly.py") > tail.index("elif [")
    for step in ("python build_site.py", "EEPHUS_DEPLOY_RUN=1 python -m pytest -q",
                 "rsync -a --delete"):
        assert step in tail


def _mod(tmp_path: Path, name: str, payload: str) -> Path:
    root = tmp_path / name
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "data_exclude.txt").write_text("# x\nsecret.json\n", encoding="utf-8")
    (root / "deploy" / "publish_paths.txt").write_text("index.html\n", encoding="utf-8")
    (root / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (root / "data" / "pitch_plots").mkdir(parents=True)
    (root / "data" / "a.json").write_bytes(payload.encode("utf-8"))  # exact line endings
    (root / "data" / "secret.json").write_text("{}", encoding="utf-8")
    (root / "data" / "pitch_plots" / "p.json").write_text('{"v": [1, 2]}', encoding="utf-8")
    return root


def test_payload_set_follows_the_exclude_list(tmp_path):
    root = _mod(tmp_path, "r", '{"x": 1}')
    assert pe.payload_files(root) == ["data/a.json", "data/pitch_plots/p.json"]


def test_categories(tmp_path):
    ref = pe.snapshot(_mod(tmp_path, "ref", '{"generated_at": "a", "x": 1.0, "l": [1, 2]}'))
    cases = {
        '{"generated_at": "a", "x": 1.0, "l": [1, 2]}': "IDENTICAL",
        '{"generated_at": "b", "x": 1.0, "l": [1, 2]}': "TIMESTAMP",
        '{"generated_at": "b", "x": 1, "l": [1, 2]}': "FLOAT_REPR",
        '{"generated_at": "b", "x": 1, "l": [2, 1]}': "ORDERING",
        '{"generated_at": "a", "x": 1.01, "l": [1, 2]}': "DIFFERENT",
    }
    for i, (payload, want) in enumerate(cases.items()):
        res = pe.compare(ref, _mod(tmp_path, f"t{i}", payload))
        assert "data/a.json" in res["files"].get(want, []), (payload, res["counts"])
        assert "data/pitch_plots/p.json" in res["files"]["IDENTICAL"]
        assert res["ok"] is (want != "DIFFERENT")


def test_crlf_checkout_reads_as_line_endings_not_a_value_change(tmp_path):
    ref = pe.snapshot(_mod(tmp_path, "ref", '{\r\n "x": 1\r\n}\r\n'))
    res = pe.compare(ref, _mod(tmp_path, "t", '{\n "x": 1\n}\n'))
    assert res["files"].get("LINE_ENDINGS") == ["data/a.json"] and res["ok"]
    assert res["pages_differing"] == []


def test_missing_and_extra_fail(tmp_path):
    ref = pe.snapshot(_mod(tmp_path, "ref", '{"x": 1}'))
    t = _mod(tmp_path, "t", '{"x": 1}')
    (t / "data" / "pitch_plots" / "p.json").unlink()
    (t / "data" / "new.json").write_text("{}", encoding="utf-8")
    res = pe.compare(ref, t)
    assert res["files"]["MISSING"] == ["data/pitch_plots/p.json"]
    assert res["files"]["EXTRA"] == ["data/new.json"]
    assert not res["ok"]


def test_positive_control_reports_exactly_one_leaf(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"meta": {"k": "s"}, "rows": [{"v": 0.123}, {"v": 2}]}),
                 encoding="utf-8")
    res = pe.selftest(p)
    assert res["ok"] and res["leaf"] == "$.rows[0].v"
    assert res["before"] == "0.123" and res["after"] == "0.124"


def test_diff_is_exact_with_no_tolerance(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text('{"x": 0.30000000000000004, "y": [1]}', encoding="utf-8")
    b.write_text('{"x": 0.3, "y": [1, 2]}', encoding="utf-8")
    rows = pe.diff_files(a, b)
    assert [r[0] for r in rows] == ["$.x", "$.y.length"]

# --------------------------------------------------------------------------- #
# compare-http: the published webroot against the frozen snapshot, offline
# --------------------------------------------------------------------------- #
import datetime as _dt  # noqa: E402

import port_bundle as pb  # noqa: E402
import port_live_check as plc  # noqa: E402

_CF_BEACON = (b'<script defer src="https://static.cloudflareinsights.com/beacon.min.js/v8" '
              b'data-cf-beacon=\'{"token": "t"}\'></script>\n')
_CF_INLINE = (b"<script>(function(){var s=document.createElement('script');"
              b"s.src='/cdn-cgi/challenge-platform/scripts/jsd/main.js';})();</script>")


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bmod"
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "publish_paths.txt").write_text("index.html\nfa\nassets\n", encoding="utf-8")
    (root / "deploy" / "data_exclude.txt").write_text("secret.json\n", encoding="utf-8")
    (root / "index.html").write_bytes(b"<html><body><script src=\"/assets/a.js\"></script>"
                                      b"<p>home</p></body></html>\n")
    (root / "fa").mkdir()
    (root / "fa" / "index.html").write_bytes(b"<p>fa</p>\n<p>two</p>\n")   # LF bytes
    (root / "assets").mkdir()
    (root / "assets" / "a.js").write_bytes(b"var a = 1;\n")
    (root / "data" / "player_detail").mkdir(parents=True)
    (root / "data" / "a.json").write_text('{"generated_at": "x", "rows": [{"v": 1.5}]}',
                                          encoding="utf-8")
    (root / "data" / "b.json").write_text('{"v": 2}', encoding="utf-8")
    (root / "data" / "c.json").write_text('{"v": 3}', encoding="utf-8")
    (root / "data" / "d.json").write_text('{"v": 4}', encoding="utf-8")
    (root / "data" / "player_detail" / "p.json").write_text('{"v": 5}', encoding="utf-8")
    info = pb.build_served(root, tmp_path / "out", strip=False,
                           now=_dt.datetime(2026, 10, 22, tzinfo=_dt.timezone.utc),
                           strips=lambda site: {})
    return Path(info["path"])


def _origin(site: Path, override: dict, calls: list | None = None):
    def fetch_raw(url):
        rel = url.split("://x/", 1)[1]
        if calls is not None:
            calls.append(rel)
        if rel in override:
            return override[rel]
        p = site / rel
        return (200, p.read_bytes(), {}) if p.is_file() else (404, b"", {})
    return fetch_raw


def test_strip_cdn_drops_only_the_injected_scripts():
    page = (b"<html><head><script src=\"/assets/a.js\"></script></head><body><p>x</p>"
            + _CF_INLINE + _CF_BEACON + b"</body></html>")
    out = pe.strip_cdn(page)
    assert out == (b"<html><head><script src=\"/assets/a.js\"></script></head>"
                   b"<body><p>x</p></body></html>")


def test_http_faithful_origin_is_identical(tmp_path):
    bundle = _bundle(tmp_path)
    calls: list = []
    res = pe.compare_http("https://x", bundle=bundle, pace=0,
                          fetch_raw=_origin(bundle / "site", {}, calls))
    assert res["ok"] and set(res["counts"]) == {"IDENTICAL"}
    assert res["checked"] == len(pe.read_bundle_manifest(bundle)) == len(calls)
    assert "data/bundle_info.json" in calls and "data/bundle_receipt.json" not in calls


def test_http_names_each_difference(tmp_path):
    bundle = _bundle(tmp_path)
    site = bundle / "site"
    idx = (site / "index.html").read_bytes()
    over = {
        "index.html": (200, idx.replace(b"</body>", _CF_BEACON + b"</body>"), {}),
        "fa/index.html": (200, b"<p>fa</p>\n<p>TWO</p>\n", {}),
        "assets/a.js": (200, b"var a = 1;\r\n", {}),
        "data/a.json": (200, b'{"generated_at": "y", "rows": [{"v": 1.5}]}', {}),
        "data/b.json": (200, b'{"v": 2.5}', {}),
        "data/c.json": (404, b"", {}),
        "data/d.json": (403, b"<html><title>Just a moment...</title></html>",
                        {"cf-mitigated": "challenge"}),
        "data/player_detail/p.json": (200, b'{"v": 6}', {}),
    }
    explained = [("data/player_detail/*", "headshot URLs through the box's proxy")]
    res = pe.compare_http("https://x", bundle=bundle, pace=0, explained=explained,
                          fetch_raw=_origin(site, over))
    f = res["files"]
    assert f["CDN_INJECTED"] == ["index.html"]
    assert f["LINE_ENDINGS"] == ["assets/a.js"]
    assert f["TIMESTAMP"] == ["data/a.json"]
    assert f["DIFFERENT"] == ["data/b.json", "fa/index.html"]
    assert res["details"]["data/b.json"] == [{"leaf": "$.v", "ref": "2", "live": "2.5"}]
    assert res["details"]["fa/index.html"] == {"line": 2, "ref": "<p>two</p>",
                                               "live": "<p>TWO</p>"}
    assert f["MISSING"] == ["data/c.json"] and res["codes"]["data/c.json"] == 404
    assert f["BLOCKED"] == ["data/d.json"]
    assert f["EXPLAINED"] == ["data/player_detail/p.json"]
    assert res["explained"]["data/player_detail/p.json"].startswith("headshot")
    assert not res["ok"]


def test_http_filters_and_paces(tmp_path):
    bundle = _bundle(tmp_path)
    calls: list = []
    waits: list = []

    class _P:
        def wait(self):
            waits.append(1)

    res = pe.compare_http("https://x", bundle=bundle, only=("data/",), every=2,
                          pacer=_P(), fetch_raw=_origin(bundle / "site", {}, calls))
    data_rows = [r for r in pe.read_bundle_manifest(bundle) if r.startswith("data/")]
    assert calls == data_rows[::2] and len(waits) == len(calls) == res["checked"]


def test_http_against_a_snapshot(tmp_path):
    root = _mod(tmp_path, "ref", '{"x": 1}')
    ref = pe.snapshot(root)
    over = {"data/a.json": (200, b'{"x": 1.0}', {}), "index.html": (200, b"<p>y</p>", {})}
    res = pe.compare_http("https://x", ref_doc=ref, pace=0, fetch_raw=_origin(root, over))
    assert res["files"]["FLOAT_REPR"] == ["data/a.json"]
    assert res["files"]["IDENTICAL"] == ["data/pitch_plots/p.json"]
    assert res["files"]["DIFFERENT"] == ["index.html"] and not res["ok"]


def test_compare_http_cli_reads_an_explained_file(tmp_path):
    p = tmp_path / "explained.tsv"
    p.write_text("# named differences\nforums/*\tthe accounts layer\n\nno tab line\n",
                 encoding="utf-8")
    assert pe.read_explained(p) == [("forums/*", "the accounts layer")]
    assert plc.is_challenge(503, {}, b"<title>Just a moment...</title>")
    assert not plc.is_challenge(404, {}, b"not found")

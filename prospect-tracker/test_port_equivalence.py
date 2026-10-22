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
    (root / "data" / "a.json").write_text(payload, encoding="utf-8")
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

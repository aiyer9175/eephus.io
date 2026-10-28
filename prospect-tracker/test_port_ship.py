# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/port_ship.py and the PC-side schedule (port Strategy D, docs/port/PORT_BUNDLE.md).

Offline and on fixtures: no test opens a connection or runs rsync. The runner is
replaced, so the tests pin what a ship would run (two rsync calls over ssh with
the key, batch mode and strict host checking; READY alone and last; a
--link-dest to the last shipped bundle), that an unverified bundle never
leaves, that nothing is recorded unless both calls succeed, that the config is
refused inside a git work tree, and the shape of the Task Scheduler XML and the
nightly script it runs (not installed). The remote commands a ship makes rsync
send are pinned to the box's bin/shipgate fixture byte for byte."""

import datetime as _dt
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import port_bundle as pb  # noqa: E402
import port_ship as ps  # noqa: E402

_T0 = _dt.datetime(2026, 10, 22, 7, 0, 0, tzinfo=_dt.timezone.utc)


def _bundle(tmp_path: Path, day: int = 0) -> Path:
    root = tmp_path / "mod"
    if not root.exists():
        (root / "deploy").mkdir(parents=True)
        (root / "deploy" / "publish_paths.txt").write_text("index.html\n", encoding="utf-8")
        (root / "deploy" / "data_exclude.txt").write_text("secret.json\n", encoding="utf-8")
        (root / "index.html").write_text("<p>x</p>", encoding="utf-8")
        (root / "data").mkdir()
        (root / "data" / "a.json").write_text('{"x": 1}', encoding="utf-8")
    info = pb.build_served(root, tmp_path / "bundles", strip=False,
                           now=_T0 + _dt.timedelta(days=day), strips=lambda s: {})
    return Path(info["path"])


def _conf(tmp_path: Path, **extra) -> dict:
    lines = ["# filled by the owner", "EEPHUS_SHIP_HOST=203.0.113.7",
             "export EEPHUS_SHIP_USER='eephus-artifacts'",
             'EEPHUS_SHIP_KEY="C:\\Users\\o\\.ssh\\eephus_ship"',
             f"EEPHUS_SHIP_STATE_DIR={tmp_path / 'state'}"]
    lines += [f"{k}={v}" for k, v in extra.items()]
    p = tmp_path / "cfg" / "port_ship.conf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ps.load_config(p)


def test_config_parses_quotes_exports_and_defaults(tmp_path):
    conf = _conf(tmp_path)
    assert conf["EEPHUS_SHIP_USER"] == "eephus-artifacts"
    assert conf["EEPHUS_SHIP_KEY"] == "C:\\Users\\o\\.ssh\\eephus_ship"
    assert conf["EEPHUS_SHIP_REMOTE_DIR"] == "/opt/eephus/artifacts/incoming"
    assert conf["EEPHUS_SHIP_PORT"] == "22" and conf["EEPHUS_SHIP_PATH_STYLE"] == "native"


def test_config_refuses_the_unfilled_template_and_any_in_repo_file(tmp_path):
    example = ROOT / "deploy" / "port_ship.conf.example"
    with pytest.raises(ps.ShipError, match="inside a git work tree"):
        ps.load_config(example)
    copy = tmp_path / "port_ship.conf"
    copy.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ps.ShipError, match="EEPHUS_SHIP_HOST, EEPHUS_SHIP_USER, EEPHUS_SHIP_KEY"):
        ps.load_config(copy)
    with pytest.raises(ps.ShipError, match="no ship config"):
        ps.load_config(tmp_path / "absent.conf")


def test_local_path_styles():
    p = "C:\\Users\\o\\b\\20261022T070000Z-abc"
    assert ps.local_path(p, "native") == "C:/Users/o/b/20261022T070000Z-abc"
    assert ps.local_path(p, "cygdrive") == "/cygdrive/c/Users/o/b/20261022T070000Z-abc"
    assert ps.local_path(p, "msys") == "/c/Users/o/b/20261022T070000Z-abc"
    assert ps.local_path(p, "wsl") == "/mnt/c/Users/o/b/20261022T070000Z-abc"
    assert ps.local_path("/home/o/b", "cygdrive") == "/home/o/b"


def test_commands_ship_ready_last_over_a_strict_ssh(tmp_path):
    conf = _conf(tmp_path, EEPHUS_SHIP_PATH_STYLE="cygdrive", EEPHUS_SHIP_PORT="2222")
    bundle = _bundle(tmp_path)
    first, second = ps.commands(conf, bundle, bundle.name, link_from="20261021T070000Z-aaaaaaaaaaaa")
    e = first[first.index("-e") + 1]
    for part in ("ssh", "-i /cygdrive/c/Users/o/.ssh/eephus_ship", "-p 2222", "BatchMode=yes",
                 "IdentitiesOnly=yes", "StrictHostKeyChecking=yes"):
        assert part in e
    assert "--exclude=/READY" in first
    assert "--chmod=D775,F664" in first and "--chmod=D775,F664" in second, \
        "group-writable, so the box's receive step (group eephus) can mark, swap and prune"
    assert "--link-dest=../20261021T070000Z-aaaaaaaaaaaa" in first
    assert first[-1] == f"eephus-artifacts@203.0.113.7:/opt/eephus/artifacts/incoming/{bundle.name}/"
    assert first[-2].endswith(f"/{bundle.name}/") and first[-2].startswith("/")
    assert second[-2].endswith("/READY") and second[-1].endswith(f"/{bundle.name}/READY")
    assert "--delete" not in " ".join(first + second), "a ship never deletes on the box"


FIXTURE = ROOT / "test_fixtures" / "port_ship" / "remote_commands.txt"
# The bytes committed as internal/shipgate/testdata/port_ship_remote_commands.txt
# in the webmaster's repository (port PR 7); bin/shipgate's tests accept them verbatim.
FIXTURE_SHA256 = "137e017b071cf51fa92390cfc726414e4120aad984061b4b39fc24ec97ca23d8"


def test_remote_commands_are_the_gates_fixture(capsys):
    import hashlib
    raw = FIXTURE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, \
        "the fixture changed: copy it to the gate's testdata in the same PR set"
    want = [x for x in raw.decode("ascii").splitlines() if x and not x.startswith("#")]
    got: list[str] = []
    for argv in (["--print-remote", "20261023T001053Z-6f82911d5778"],
                 ["--print-remote", "20261024T031000Z-0123456789ab",
                  "--link-from", "20261023T001053Z-6f82911d5778"],
                 ["--print-remote", "20261025T031000Z-abcdef012345",
                  "--link-from", "20261024T031000Z-0123456789ab", "--bwlimit", "20000"]):
        assert ps.main(argv) == 0
        got += capsys.readouterr().out.splitlines()
    assert got == want


def test_remote_dir_must_be_the_inbox_spelled_as_the_pin_spells_it(tmp_path):
    for bad in (".", "incoming", "/opt/eephus/artifacts/incoming/", "/opt/eephus/../x",
                "/opt/eephus artifacts"):
        with pytest.raises(ps.ShipError, match="EEPHUS_SHIP_REMOTE_DIR"):
            _conf(tmp_path, EEPHUS_SHIP_REMOTE_DIR=bad)
    assert ps.main(["--print-remote", "not-an-id"]) == 1


def test_dry_run_runs_and_writes_nothing(tmp_path):
    conf = _conf(tmp_path)
    bundle = _bundle(tmp_path)

    def runner(cmd):
        raise AssertionError("dry run ran a command")

    res = ps.ship(bundle, conf, dry_run=True, runner=runner)
    assert res["ok"] and res["dry_run"] and len(res["commands"]) == 2
    assert res["remote"] == [
        f"rsync --server -rte.iLsfxCIvu --partial . /opt/eephus/artifacts/incoming/{bundle.name}/",
        f"rsync --server -rte.iLsfxCIvu --partial . /opt/eephus/artifacts/incoming/{bundle.name}/READY"]
    assert not (tmp_path / "state").exists()


def test_ship_records_and_the_next_ship_links_against_it(tmp_path):
    conf = _conf(tmp_path)
    calls: list = []
    b1 = _bundle(tmp_path, 0)
    res = ps.ship(b1, conf, runner=lambda c: calls.append(c) or 0, now=_T0)
    assert res["ok"] and len(calls) == 2
    assert calls[1][-1].endswith("/READY") and not any("--link-dest" in x for x in calls[0])
    rec = json.loads((tmp_path / "state" / "last_ship.json").read_text(encoding="utf-8"))
    assert rec["bundle_id"] == b1.name and rec["shipped_at"] == "2026-10-22T07:00:00Z"
    b2 = _bundle(tmp_path, 1)
    calls.clear()
    ps.ship(b2, conf, runner=lambda c: calls.append(c) or 0, now=_T0)
    assert f"--link-dest=../{b1.name}" in calls[0]
    log = (tmp_path / "state" / "ship_log.tsv").read_text(encoding="utf-8").splitlines()
    assert [row.split("\t")[1] for row in log] == [b1.name, b2.name]


def test_a_failed_rsync_records_nothing_and_ready_never_goes(tmp_path):
    conf = _conf(tmp_path)
    calls: list = []
    with pytest.raises(ps.ShipError, match="step 1 of 2 exited 12"):
        ps.ship(_bundle(tmp_path), conf, runner=lambda c: calls.append(c) or 12)
    assert len(calls) == 1 and not (tmp_path / "state").exists()


def test_an_unverified_bundle_never_leaves(tmp_path):
    conf = _conf(tmp_path)
    bundle = _bundle(tmp_path)
    (bundle / "site" / "index.html").write_text("<p>changed</p>", encoding="utf-8")

    def runner(cmd):
        raise AssertionError("an unverified bundle was shipped")

    with pytest.raises(ps.ShipError, match="does not verify"):
        ps.ship(bundle, conf, runner=runner)


def test_a_real_ship_checks_the_key_before_any_rsync(tmp_path, monkeypatch):
    conf = _conf(tmp_path)
    bundle = _bundle(tmp_path)
    monkeypatch.setattr(ps.subprocess, "run", lambda *a, **k: pytest.fail("rsync ran"))
    with pytest.raises(ps.ShipError, match="no key file"):
        ps.ship(bundle, conf)
    key = tmp_path / "key"
    key.write_text("k", encoding="utf-8")
    conf["EEPHUS_SHIP_KEY"] = str(key)
    conf["EEPHUS_SHIP_RSYNC"] = "rsync-not-installed-here"
    with pytest.raises(ps.ShipError, match="not on PATH"):
        ps.ship(bundle, conf)
    assert not (tmp_path / "state").exists()


def test_latest_bundle_is_the_newest_id(tmp_path):
    _bundle(tmp_path, 0)
    newest = _bundle(tmp_path, 2)
    (tmp_path / "bundles" / "zz_not_a_bundle").mkdir()
    assert ps.latest_bundle(tmp_path / "bundles") == newest


def test_wrappers_call_the_python_tool():
    ps1 = (ROOT / "tools" / "port_ship.ps1").read_text(encoding="utf-8")
    sh = (ROOT / "tools" / "port_ship.sh").read_bytes()
    assert 'Join-Path $PSScriptRoot "port_ship.py"' in ps1 and "exit $code" in ps1
    assert b'"$HERE/port_ship.py" "$@"' in sh and b"\r\n" not in sh


def test_task_xml_runs_the_nightly_and_is_not_installed():
    xml = ROOT / "deploy" / "port-nightly-task.xml"
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    task = ET.parse(xml).getroot()
    assert task.find("t:Settings/t:MultipleInstancesPolicy", ns).text == "IgnoreNew"
    assert task.find("t:Settings/t:StartWhenAvailable", ns).text == "true"
    start = task.find("t:Triggers/t:CalendarTrigger/t:StartBoundary", ns).text
    assert start.endswith("T03:10:00")
    assert task.find("t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval", ns).text == "1"
    args = task.find("t:Actions/t:Exec/t:Arguments", ns).text
    assert args.endswith('prospect-tracker\\deploy\\port-nightly.ps1"')
    assert "NOT INSTALLED" in xml.read_text(encoding="utf-8")


def test_nightly_script_keeps_the_box_order():
    s = (ROOT / "deploy" / "port-nightly.ps1").read_text(encoding="utf-8")
    s = s[s.index("$code = 0"):]          # the body, past the header's usage notes
    order = ["tools\\port_live_check.py --heartbeat", "run_monthly\\.py|pytest",
             "run_monthly.py --daily", "build_site.py", "-m pytest -q",
             "tools\\port_bundle.py --served-bundle", "tools\\port_ship.py --latest"]
    at = [s.index(step) for step in order]
    assert at == sorted(at), dict(zip(order, at))
    assert 'Invoke-Step "test gate"' in s and "$code = 1" in s

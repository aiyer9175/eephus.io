# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Ship a verified served bundle to the box over a restricted SSH user (port Strategy D).

    python tools/port_ship.py --bundle OUT_ROOT/<bundle-id> [--dry-run]
    python tools/port_ship.py --latest OUT_ROOT [--dry-run]
    python tools/port_ship.py --print-config
    python tools/port_ship.py --print-remote <bundle-id> [--link-from <id>]

tools/port_ship.ps1 and tools/port_ship.sh are thin wrappers around this file,
for the Windows Task Scheduler and for a POSIX shell.

What a ship does, in order (docs/port/PORT_BUNDLE.md):
  1. verifies the bundle against its own manifest (port_bundle.verify_served);
     an unverified bundle never leaves the PC;
  2. rsync over ssh, everything but READY, into
     <EEPHUS_SHIP_REMOTE_DIR>/<bundle-id>/ (default /opt/eephus/artifacts/incoming),
     with --link-dest=../<last shipped id> so unchanged files are hard links on
     the box and only changed bytes cross the wire, and --chmod=D775,F664 so
     the box's receive step (group eephus) can write the receipt, rename READY
     and prune;
  3. rsync READY alone, last, so the box's receive step never sees a bundle
     that is still arriving (it acts only on a directory that holds READY, and
     then checks SHA256SUMS with sha256sum -c);
  4. records the ship (bundle id, time, counts) in the state directory, which
     the next ship reads for --link-dest.

The connection settings live in a local file the owner fills and that is
never committed: EEPHUS_PORT_SHIP_CONF, else ~/.eephus/port_ship.conf. The tool
refuses a config file inside a git work tree. The template is
deploy/port_ship.conf.example. KEY=VALUE lines:

    EEPHUS_SHIP_HOST          the box's address (an address that does not go
                              through Cloudflare: Cloudflare Free proxies no SSH)
    EEPHUS_SHIP_USER          the restricted user (its key forces bin/shipgate)
    EEPHUS_SHIP_KEY           path to the private key for that user
    EEPHUS_SHIP_PORT          default 22
    EEPHUS_SHIP_REMOTE_DIR    default /opt/eephus/artifacts/incoming: the box's
                              inbox spelled exactly as its pin's paths.incoming
                              (bin/shipgate accepts no other spelling)
    EEPHUS_SHIP_RSYNC         rsync command, default "rsync" (cwRsync, MSYS2 or
                              "wsl rsync" on Windows: the PC has none by default)
    EEPHUS_SHIP_SSH           ssh command for rsync -e, default "ssh"
    EEPHUS_SHIP_PATH_STYLE    native | cygdrive | msys | wsl: how this rsync
                              spells a Windows path (C:\\x -> /cygdrive/c/x,
                              /c/x or /mnt/c/x); default native
    EEPHUS_SHIP_KNOWN_HOSTS   optional known_hosts file (StrictHostKeyChecking
                              stays yes either way)
    EEPHUS_SHIP_BWLIMIT       optional rsync --bwlimit, KiB/s
    EEPHUS_SHIP_STATE_DIR     default <module>/.cache/port_ship

--dry-run prints the commands and runs nothing, writes nothing. The tool never
deletes anything on the box; the box keeps its own retention.

The box side is the forced command on the ship user's key (bin/shipgate in
the webmaster's repository, internal/shipgate). It reads the remote command
rsync sends (SSH_ORIGINAL_COMMAND) and accepts exactly the two calls above:
"rsync --server <options> . <inbox>/<bundle-id>/" with --partial, an optional
--bwlimit and --link-dest=../<id>, then the same into <inbox>/<bundle-id>/READY,
only after the body's MANIFEST.tsv, SHA256SUMS, BUNDLE.json and site/ have
arrived, never into a bundle that already carries a marker, and never when the
box's disk is under its floor. --print-remote prints the remote commands this
tool's calls produce; the gate's test fixture
(internal/shipgate/testdata/port_ship_remote_commands.txt) is that output, and
test_port_ship.py pins the copy under test_fixtures/port_ship/ to the same bytes.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

REQUIRED = ("EEPHUS_SHIP_HOST", "EEPHUS_SHIP_USER", "EEPHUS_SHIP_KEY")
DEFAULTS = {
    "EEPHUS_SHIP_PORT": "22",
    "EEPHUS_SHIP_REMOTE_DIR": "/opt/eephus/artifacts/incoming",
    "EEPHUS_SHIP_RSYNC": "rsync",
    "EEPHUS_SHIP_SSH": "ssh",
    "EEPHUS_SHIP_PATH_STYLE": "native",
    "EEPHUS_SHIP_KNOWN_HOSTS": "",
    "EEPHUS_SHIP_BWLIMIT": "",
    "EEPHUS_SHIP_STATE_DIR": str(ROOT / ".cache" / "port_ship"),
}
PLACEHOLDER = re.compile(r"^<.*>$|^(CHANGE_ME|example\.invalid)$", re.I)
# The two calls' file modes on the box: group-writable, so bin/receive (group
# eephus, under bin/shipgate's umask 002) can mark, swap and prune a bundle.
CHMOD = "--chmod=D775,F664"
# The server option cluster rsync 3.2's client sends for "-rt" (protocol 31:
# the option letters, then "e" and the capability letters). bin/shipgate
# accepts any cluster of the letters it allows, so a client of another rsync
# version that adds capability letters still passes; this is the spelling the
# shared fixture records.
REMOTE_SHORT = "-rte.iLsfxCIvu"
REMOTE_DIR_RE = re.compile(r"^/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


class ShipError(RuntimeError):
    pass


def default_config_path() -> Path:
    env = os.environ.get("EEPHUS_PORT_SHIP_CONF")
    return Path(env) if env else Path.home() / ".eephus" / "port_ship.conf"


def _inside_git_worktree(path: Path) -> bool:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / ".git").exists():
            return True
    return False


def load_config(path: Path) -> dict:
    """KEY=VALUE lines (# comments, optional quotes); refuses an in-repo file."""
    path = path.resolve()
    if not path.is_file():
        raise ShipError(f"no ship config at {path}: copy deploy/port_ship.conf.example "
                        "there (outside any git checkout) and fill it")
    if _inside_git_worktree(path):
        raise ShipError(f"{path} is inside a git work tree; keep the ship config "
                        "outside every checkout so it is never committed")
    conf = dict(DEFAULTS)
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            raise ShipError(f"{path}:{n}: not a KEY=VALUE line")
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        conf[k.strip()] = v
    bad = [k for k in REQUIRED if not conf.get(k) or PLACEHOLDER.match(conf[k])]
    if bad:
        raise ShipError(f"{path}: fill {', '.join(bad)}")
    if conf["EEPHUS_SHIP_PATH_STYLE"] not in ("native", "cygdrive", "msys", "wsl"):
        raise ShipError("EEPHUS_SHIP_PATH_STYLE must be native, cygdrive, msys or wsl")
    if not conf["EEPHUS_SHIP_PORT"].isdigit():
        raise ShipError("EEPHUS_SHIP_PORT must be a number")
    remote = conf["EEPHUS_SHIP_REMOTE_DIR"]
    if not REMOTE_DIR_RE.match(remote) or "/../" in remote + "/" or "/./" in remote + "/":
        raise ShipError("EEPHUS_SHIP_REMOTE_DIR must be the box's inbox as an absolute "
                        "path with no trailing slash (the pin's paths.incoming), "
                        f"got {remote!r}")
    conf["_path"] = str(path)
    return conf


def local_path(p: Path | str, style: str) -> str:
    """Spell a local path the way the configured rsync and ssh read it."""
    s = str(p).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    if style == "native" or not m:
        return s
    drive, rest = m.group(1).lower(), m.group(2)
    prefix = {"cygdrive": "/cygdrive/", "msys": "/", "wsl": "/mnt/"}[style]
    return f"{prefix}{drive}/{rest}"


def ssh_command(conf: dict) -> str:
    style = conf["EEPHUS_SHIP_PATH_STYLE"]
    parts = shlex.split(conf["EEPHUS_SHIP_SSH"]) + [
        "-i", local_path(conf["EEPHUS_SHIP_KEY"], style),
        "-p", conf["EEPHUS_SHIP_PORT"],
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
    ]
    if conf.get("EEPHUS_SHIP_KNOWN_HOSTS"):
        parts += ["-o", "UserKnownHostsFile=" + local_path(conf["EEPHUS_SHIP_KNOWN_HOSTS"], style)]
    return " ".join(shlex.quote(x) for x in parts)


def remote_target(conf: dict, bundle_id: str, leaf: str = "") -> str:
    base = conf["EEPHUS_SHIP_REMOTE_DIR"].rstrip("/") or "/"
    return f"{conf['EEPHUS_SHIP_USER']}@{conf['EEPHUS_SHIP_HOST']}:{base}/{bundle_id}/{leaf}"


def state_file(conf: dict) -> Path:
    return Path(conf["EEPHUS_SHIP_STATE_DIR"]) / "last_ship.json"


def last_shipped(conf: dict) -> str | None:
    try:
        return json.loads(state_file(conf).read_text(encoding="utf-8")).get("bundle_id")
    except (OSError, ValueError):
        return None


def commands(conf: dict, bundle: Path, bundle_id: str,
             link_from: str | None = None) -> list[list[str]]:
    """The two rsync calls: the bundle without READY, then READY alone."""
    style = conf["EEPHUS_SHIP_PATH_STYLE"]
    rsync = shlex.split(conf["EEPHUS_SHIP_RSYNC"])
    common = ["-rt", "--partial", CHMOD, "-e", ssh_command(conf)]
    if conf.get("EEPHUS_SHIP_BWLIMIT"):
        common.append(f"--bwlimit={conf['EEPHUS_SHIP_BWLIMIT']}")
    first = rsync + common + ["--exclude=/READY"]
    if link_from and link_from != bundle_id:
        first.append(f"--link-dest=../{link_from}")
    first += [local_path(bundle, style).rstrip("/") + "/", remote_target(conf, bundle_id)]
    second = rsync + common + [local_path(bundle / "READY", style),
                               remote_target(conf, bundle_id, "READY")]
    return [first, second]


def remote_commands(conf: dict, bundle_id: str, link_from: str | None = None) -> list[str]:
    """The remote commands the two calls make rsync send over ssh, the ones
    bin/shipgate reads from SSH_ORIGINAL_COMMAND: the receiving side's options
    (--chmod and --exclude stay on the client), ".", and the destination."""
    base = conf["EEPHUS_SHIP_REMOTE_DIR"].rstrip("/")
    head = ["rsync", "--server", REMOTE_SHORT, "--partial"]
    if conf.get("EEPHUS_SHIP_BWLIMIT"):
        head.append(f"--bwlimit={conf['EEPHUS_SHIP_BWLIMIT']}")
    first = list(head)
    if link_from and link_from != bundle_id:
        first.append(f"--link-dest=../{link_from}")
    first += [".", f"{base}/{bundle_id}/"]
    second = head + [".", f"{base}/{bundle_id}/READY"]
    return [" ".join(first), " ".join(second)]


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode


def preflight(conf: dict) -> None:
    """Before a real ship: the key file exists and the rsync command resolves."""
    import shutil
    if not Path(conf["EEPHUS_SHIP_KEY"]).expanduser().is_file():
        raise ShipError(f"no key file at {conf['EEPHUS_SHIP_KEY']}")
    exe = shlex.split(conf["EEPHUS_SHIP_RSYNC"])[0]
    if shutil.which(exe) is None:
        raise ShipError(f"{exe!r} is not on PATH: install cwRsync, MSYS2 rsync or use "
                        "WSL, and set EEPHUS_SHIP_RSYNC and EEPHUS_SHIP_PATH_STYLE")


def ship(bundle: Path, conf: dict, dry_run: bool = False, runner=_run,
         now: _dt.datetime | None = None, verify=None) -> dict:
    import port_bundle as pb
    bundle = bundle.resolve()
    res = (verify or pb.verify_served)(bundle)
    if not res.get("ok"):
        raise ShipError(f"bundle {bundle} does not verify: "
                        + json.dumps({k: res.get(k) for k in
                                      ("missing", "mismatched", "extra", "problems")}))
    bundle_id = res["bundle_id"]
    info = json.loads((bundle / "BUNDLE.json").read_text(encoding="utf-8"))
    link_from = last_shipped(conf)
    cmds = commands(conf, bundle, bundle_id, link_from)
    out = {"bundle_id": bundle_id, "files": info.get("files"), "bytes": info.get("bytes"),
           "host": conf["EEPHUS_SHIP_HOST"], "dry_run": dry_run,
           "commands": [" ".join(shlex.quote(c) for c in cmd) for cmd in cmds],
           "remote": remote_commands(conf, bundle_id, link_from)}
    if dry_run:
        out["ok"] = True
        return out
    if runner is _run:
        preflight(conf)
    for i, cmd in enumerate(cmds, 1):
        rc = runner(cmd)
        if rc != 0:
            raise ShipError(f"rsync step {i} of {len(cmds)} exited {rc}; "
                            "nothing recorded, the box ignores a bundle without READY")
    now = (now or _dt.datetime.now(_dt.timezone.utc)).astimezone(_dt.timezone.utc)
    record = {"bundle_id": bundle_id, "shipped_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "host": conf["EEPHUS_SHIP_HOST"], "files": info.get("files"),
              "bytes": info.get("bytes"), "manifest_sha256": info.get("manifest_sha256")}
    sf = state_file(conf)
    sf.parent.mkdir(parents=True, exist_ok=True)
    tmp = sf.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, sf)
    with open(sf.parent / "ship_log.tsv", "a", encoding="utf-8", newline="\n") as log:
        log.write("\t".join(str(record[k]) for k in
                            ("shipped_at", "bundle_id", "host", "files", "bytes")) + "\n")
    out.update(ok=True, shipped_at=record["shipped_at"])
    return out


def latest_bundle(out_root: Path) -> Path:
    import port_bundle as pb
    ids = sorted(p.name for p in out_root.iterdir()
                 if p.is_dir() and pb.BUNDLE_ID_RE.match(p.name)) if out_root.is_dir() else []
    if not ids:
        raise ShipError(f"no bundle under {out_root}")
    return out_root / ids[-1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bundle", type=Path, help="the bundle directory to ship")
    g.add_argument("--latest", type=Path, metavar="OUT_ROOT",
                   help="ship the newest bundle under OUT_ROOT")
    g.add_argument("--print-config", action="store_true",
                   help="print the parsed config (paths only) and exit")
    g.add_argument("--print-remote", metavar="BUNDLE_ID",
                   help="print the two remote commands bin/shipgate reads for a ship "
                        "of BUNDLE_ID, one per line, and exit (no config needed)")
    ap.add_argument("--link-from", metavar="ID", help="with --print-remote: the previous bundle id")
    ap.add_argument("--remote-dir", default=DEFAULTS["EEPHUS_SHIP_REMOTE_DIR"],
                    help="with --print-remote: the box's inbox")
    ap.add_argument("--bwlimit", default="", help="with --print-remote: an rsync --bwlimit")
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    a = ap.parse_args(argv)
    if a.print_remote:
        import port_bundle as pb
        ids = [a.print_remote] + ([a.link_from] if a.link_from else [])
        if not all(pb.BUNDLE_ID_RE.match(i) for i in ids) or not REMOTE_DIR_RE.match(a.remote_dir):
            print("!!! port ship: --print-remote takes bundle ids and an absolute inbox",
                  file=sys.stderr)
            return 1
        conf = {"EEPHUS_SHIP_REMOTE_DIR": a.remote_dir, "EEPHUS_SHIP_BWLIMIT": a.bwlimit}
        # Bytes, so the lines are LF on every platform: the gate's fixture is LF.
        sys.stdout.buffer.write("".join(line + "\n" for line in remote_commands(
            conf, a.print_remote, a.link_from)).encode("ascii"))
        return 0
    try:
        conf = load_config(a.config or default_config_path())
        if a.print_config:
            print(json.dumps({k: v for k, v in sorted(conf.items())}, indent=1))
            return 0
        bundle = a.bundle if a.bundle else latest_bundle(a.latest.resolve())
        res = ship(bundle, conf, dry_run=a.dry_run)
    except ShipError as exc:
        print(f"!!! port ship: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

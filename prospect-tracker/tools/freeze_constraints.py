# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Write constraints-local.txt: the exact versions of every declared dependency
and everything it pulls in, as installed in the interpreter that runs this.

requirements.txt and requirements-dev.txt hold floors (what the code needs).
This file records what one machine actually ran, so two machines that produce a
different Swing+ or Stuff+ from the same bytes can be compared by version rather
than guessed at. It is re-measured, never typed: run

    python tools/freeze_constraints.py            # rewrite constraints-local.txt
    python tools/freeze_constraints.py --check    # exit 1 if it would change

Only the declared tree is pinned (declared names plus their non-extra
requirements, walked to closure), not every package in the interpreter, so an
unrelated local install never lands in the lock.

Install against it with `pip install -r requirements.txt -c constraints-local.txt`.
The box and CI do not do that yet (owner question X04-04): they run Python 3.12
and resolve the floors at install time.
"""
from __future__ import annotations

import argparse
import platform
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ_FILES = ("requirements.txt", "requirements-dev.txt")
OUT = ROOT / "constraints-local.txt"


def canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_names(root: Path = ROOT) -> list[str]:
    """Distribution names named by the requirement files (floors, comments and
    -r includes skipped)."""
    out: list[str] = []
    for fn in REQ_FILES:
        p = root / fn
        if not p.exists():
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.split("#", 1)[0].strip()
            if not ln or ln.startswith("-"):
                continue
            m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", ln)
            if m:
                out.append(m.group(0))
    return out


def _requires(dist: metadata.Distribution) -> list[str]:
    names = []
    for r in dist.requires or []:
        head, _, marker = r.partition(";")
        if "extra" in marker:
            continue
        if marker.strip():
            env = {"sys_platform": sys.platform, "python_version":
                   f"{sys.version_info[0]}.{sys.version_info[1]}",
                   "platform_system": platform.system(), "os_name": "nt" if sys.platform == "win32" else "posix",
                   "implementation_name": sys.implementation.name,
                   "platform_python_implementation": platform.python_implementation()}
            try:
                from packaging.markers import Marker
                if not Marker(marker.strip()).evaluate(env):
                    continue
            except Exception:
                pass
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", head.strip())
        if m:
            names.append(m.group(0))
    return names


def closure(names: list[str]) -> dict[str, tuple[str, str]]:
    """canonical name -> (distribution name as installed, version). Missing
    distributions are left out; `missing` in render() names them."""
    seen: dict[str, tuple[str, str]] = {}
    todo = list(names)
    while todo:
        n = todo.pop()
        c = canon(n)
        if c in seen:
            continue
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            continue
        seen[c] = (d.metadata["Name"], d.version)
        todo.extend(_requires(d))
    return seen


def render() -> str:
    names = declared_names()
    pins = closure(names)
    missing = sorted(n for n in names if canon(n) not in pins)
    lines = [
        "# Written by tools/freeze_constraints.py; do not edit by hand.",
        "# Exact versions of the declared dependency tree as installed on the",
        f"# machine that last ran it: Python {platform.python_version()} on {sys.platform}.",
        "# Use: pip install -r requirements.txt -c constraints-local.txt",
    ]
    if missing:
        lines.append("# Declared but not installed here: " + ", ".join(missing))
    for c in sorted(pins):
        name, ver = pins[c]
        lines.append(f"{name}=={ver}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = render()
    if a.check:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if old.replace("\r\n", "\n") != text:
            print("constraints-local.txt is out of date with this interpreter")
            return 1
        print("constraints-local.txt matches this interpreter")
        return 0
    OUT.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    print(f"wrote {OUT} ({text.count('==')} pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

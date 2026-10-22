# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Read-only check of a served origin against this tree (PORT_RUNBOOK.md, Gate B).

    python tools/port_live_check.py --origin https://eephus.io --out live_check.json

For every page this tree publishes (deploy/publish_paths.txt, HTML at depth two
or less), every asset under assets/, every published data payload at data/
depth one, and every withheld name in deploy/data_exclude.txt, it asks the
origin for the file and records the status and, for pages and assets, whether
the bytes equal this tree's. It also reads data/build_info.json.

It fetches through curl with a full browser user agent because Cloudflare
answers scripted TLS clients with a challenge (deploy/README.md). It never
writes to the origin. Exit 1 when a published file is missing, a withheld file
is served, or a page or asset differs, so it doubles as the post-cutover gate.

Pages and assets are compared byte for byte, which assumes the origin serves
the sources: the nightly strips comments from prospx/index.html and from
assets/*.css and *.js on the webroot copy, so on a box that runs the strips
pass --stripped to record those files as served-or-not only.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def _lines(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


def _lf_digest(raw: bytes) -> str:
    """CRLF reads as LF, so a Windows checkout compares equal to the box's LF copy."""
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def curl_fetch(url: str, save: Path | None, head: bool = False) -> int:
    cmd = ["curl", "-s", "-m", "120", "-A", UA, "--compressed",
           "-o", str(save) if save else os.devnull, "-w", "%{http_code}"]
    if head:
        cmd.insert(1, "-I")
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return int(r.stdout.strip() or -1)
    except (subprocess.SubprocessError, ValueError):
        return -1


def targets(root: Path) -> dict[str, list[str]]:
    pages: list[str] = []
    for e in _lines(root / "deploy" / "publish_paths.txt"):
        p = root / e
        if p.is_dir():
            pages += [f.relative_to(root).as_posix() for f in sorted(p.rglob("*.html"))
                      if f.relative_to(root).as_posix().count("/") <= 2]
        elif p.is_file():
            pages.append(e)
    excl = _lines(root / "deploy" / "data_exclude.txt")
    data = [f"data/{p.name}" for p in sorted((root / "data").iterdir())
            if p.is_file() and p.suffix in (".json", ".js") and p.name not in excl]
    assets = [f"assets/{p.name}" for p in sorted((root / "assets").iterdir()) if p.is_file()]
    return {"pages": sorted(set(pages)), "assets": assets, "data": data,
            "withheld": [f"data/{n}" for n in excl if "*" not in n]}


def check(origin: str, root: Path, fetch=curl_fetch, stripped: bool = False,
          workers: int = 4) -> dict:
    origin = origin.rstrip("/")
    t = targets(root)
    strip_set = {"prospx/index.html"} | {a for a in t["assets"]
                                         if a.endswith((".css", ".js"))}
    out: dict = {"origin": origin, "pages": {}, "assets": {}, "data": {}, "withheld": {}}
    with tempfile.TemporaryDirectory() as td:
        def body(rel: str):
            save = Path(td) / rel.replace("/", "__")
            code = fetch(f"{origin}/{rel}", save)
            same = None
            if code == 200 and save.exists() and not (stripped and rel in strip_set):
                same = _lf_digest(save.read_bytes()) == _lf_digest((root / rel).read_bytes())
            return rel, {"code": code, "same_bytes": same}

        def head(rel: str):
            return rel, {"code": fetch(f"{origin}/{rel}", None, True)}

        with cf.ThreadPoolExecutor(workers) as ex:
            for kind, fn in (("pages", body), ("assets", body), ("data", head),
                             ("withheld", head)):
                for rel, rec in ex.map(fn, t[kind]):
                    out[kind][rel] = rec
        bi = Path(td) / "build_info.json"
        out["build_info_code"] = fetch(f"{origin}/data/build_info.json", bi)
        out["build_info"] = (json.loads(bi.read_text(encoding="utf-8"))
                             if out["build_info_code"] == 200 and bi.exists() else None)
    fails = {
        "pages_missing": [r for r, v in out["pages"].items() if v["code"] != 200],
        "pages_differ": [r for r, v in out["pages"].items() if v["same_bytes"] is False],
        "assets_missing": [r for r, v in out["assets"].items() if v["code"] != 200],
        "assets_differ": [r for r, v in out["assets"].items() if v["same_bytes"] is False],
        "data_missing": [r for r, v in out["data"].items() if v["code"] != 200],
        "withheld_served": [r for r, v in out["withheld"].items() if v["code"] == 200],
    }
    out["summary"] = {k: len(v) for k, v in fails.items()}
    out["failures"] = fails
    out["ok"] = not any(fails.values())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--origin", default="https://eephus.io")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stripped", action="store_true",
                    help="do not byte-compare the files the nightly strips")
    a = ap.parse_args(argv)
    res = check(a.origin, a.root.resolve(), stripped=a.stripped)
    if a.out:
        a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({"origin": res["origin"], "build_info": res["build_info"],
                      "summary": res["summary"], "ok": res["ok"]}, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

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

--pace SECONDS spaces the requests (at least that long between two starts,
across all workers), so a full pass does not read as a burst to Cloudflare.

    python tools/port_live_check.py --heartbeat --origin https://eephus.io

The 36-hour heartbeat (docs/port/PORT_BUNDLE.md): reads the time the box
RECEIVED the served bundle, data/bundle_receipt.json (received_at, written by
the box's receive step), and alarms (exit 1) when it is missing or older than
--max-age-hours (36). Without a receipt it falls back to the bundle's own
data/bundle_info.json (built_at), an upper bound on the receive age, and says
which one it read. It never reads the Go Build's data/build_info.json: a box
that keeps building its own numbers while our bundle stops arriving must
alarm.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
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


HEARTBEAT_HOURS = 36.0
RECEIPT = "data/bundle_receipt.json"      # written by the box's receive step
BUNDLE_INFO = "data/bundle_info.json"     # carried inside every served bundle


class Pacer:
    """At least `seconds` between the starts of two requests, across threads."""

    def __init__(self, seconds: float = 0.0, sleep=time.sleep, clock=time.monotonic):
        self.seconds = max(0.0, float(seconds))
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()
        self._next = None

    def wait(self) -> None:
        if self.seconds <= 0:
            return
        with self._lock:
            now = self._clock()
            if self._next is not None and now < self._next:
                self._sleep(self._next - now)
                now = self._next
            self._next = now + self.seconds


def paced(fetch, pacer: Pacer):
    """Wrap a fetch(url, save, head=False) so every call waits its turn."""
    def call(url, save, head=False):
        pacer.wait()
        return fetch(url, save, head)
    return call


def is_challenge(code: int, headers: dict, body: bytes | None) -> bool:
    """A Cloudflare challenge page, not the origin's answer."""
    if str(headers.get("cf-mitigated", "")).lower() == "challenge":
        return True
    if code in (403, 429, 503) and body:
        head = body[:4096].lower()
        return b"just a moment" in head or b"challenge-platform" in head
    return False


def curl_fetch_raw(url: str) -> tuple[int, bytes | None, dict]:
    """(status, body, lower-cased headers) through curl with the browser UA."""
    with tempfile.TemporaryDirectory() as td:
        body_p, head_p = Path(td) / "body", Path(td) / "head"
        cmd = ["curl", "-s", "-m", "120", "-A", UA, "--compressed",
               "-D", str(head_p), "-o", str(body_p), "-w", "%{http_code}", url]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            code = int(r.stdout.strip() or -1)
        except (subprocess.SubprocessError, ValueError):
            return -1, None, {}
        headers: dict = {}
        if head_p.exists():
            for line in head_p.read_text(encoding="latin-1").splitlines():
                if ":" in line and not line.startswith("HTTP/"):
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
        body = body_p.read_bytes() if body_p.exists() else None
        return code, body, headers


def _parse_utc(stamp: str) -> _dt.datetime | None:
    try:
        t = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def heartbeat(origin: str, fetch_raw=curl_fetch_raw, now: _dt.datetime | None = None,
              max_hours: float = HEARTBEAT_HOURS) -> dict:
    """The 36-hour alarm on the bundle's RECEIVE time (receipt, else built_at)."""
    origin = origin.rstrip("/")
    now = now or _dt.datetime.now(_dt.timezone.utc)
    out: dict = {"origin": origin, "max_age_hours": max_hours, "source": None,
                 "stamp": None, "age_hours": None, "bundle_id": None}
    for rel, key in ((RECEIPT, "received_at"), (BUNDLE_INFO, "built_at")):
        code, body, headers = fetch_raw(f"{origin}/{rel}")
        out[f"{rel}_code"] = code
        if is_challenge(code, headers, body):
            out[f"{rel}_code"] = f"{code} (challenge)"
            continue
        if code != 200 or not body:
            continue
        try:
            doc = json.loads(body.decode("utf-8"))
        except ValueError:
            continue
        t = _parse_utc(doc.get(key, "")) if isinstance(doc, dict) else None
        if t is None:
            continue
        out.update(source=rel, stamp=doc[key], bundle_id=doc.get("bundle_id"),
                   age_hours=round((now - t).total_seconds() / 3600.0, 2))
        break
    out["ok"] = out["age_hours"] is not None and out["age_hours"] <= max_hours
    if out["source"] is None:
        out["reason"] = "no receipt and no bundle_info answered with a stamp"
    elif not out["ok"]:
        out["reason"] = f"the last bundle is {out['age_hours']} h old (limit {max_hours} h)"
    return out


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
          workers: int = 4, pace: float = 0.0) -> dict:
    origin = origin.rstrip("/")
    if pace > 0:
        fetch = paced(fetch, Pacer(pace))
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
    ap.add_argument("--pace", type=float, default=0.0, metavar="SECONDS",
                    help="space request starts by at least this long")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--heartbeat", action="store_true",
                    help="only the 36-hour bundle receive-time alarm")
    ap.add_argument("--max-age-hours", type=float, default=HEARTBEAT_HOURS)
    a = ap.parse_args(argv)
    if a.heartbeat:
        hb = heartbeat(a.origin, max_hours=a.max_age_hours)
        if a.out:
            a.out.write_text(json.dumps(hb, indent=1), encoding="utf-8")
        print(json.dumps(hb, indent=1))
        if not hb["ok"]:
            print(f"!!! BUNDLE HEARTBEAT: {hb.get('reason')}", file=sys.stderr)
        return 0 if hb["ok"] else 1
    res = check(a.origin, a.root.resolve(), stripped=a.stripped,
                workers=a.workers, pace=a.pace)
    if a.out:
        a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({"origin": res["origin"], "build_info": res["build_info"],
                      "summary": res["summary"], "ok": res["ok"]}, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

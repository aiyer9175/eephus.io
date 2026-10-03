# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One URL for the vendored html2canvas (bloat finding AS19, 2026-10-03).

PROSPX's lazy loader and eephus-export.js's private loader used to fetch
/vendor/html2canvas.min.js under two spellings (one with a date stamp, one
bare), which a browser caches as two entries, so a reader who exported on
PROSPX and on any other module downloaded the 194 KB file twice. Both now
name the same string, stamped with the file's content hash (md5 of its LF
bytes, first 8 hex, so the stamp does not depend on a checkout's line
endings), and nothing else in the tree loads it under a third spelling.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor" / "html2canvas.min.js"
URL_RE = re.compile(r"/vendor/html2canvas\.min\.js(?:\?v=[0-9A-Za-z]+)?")


def _expected_url() -> str:
    lf = VENDOR.read_bytes().replace(b"\r\n", b"\n")
    return f"/vendor/html2canvas.min.js?v={hashlib.md5(lf).hexdigest()[:8]}"


def test_both_loaders_name_the_same_content_stamped_url():
    want = _expected_url()
    prospx = URL_RE.findall((ROOT / "prospx" / "index.html").read_text(encoding="utf-8"))
    export = URL_RE.findall((ROOT / "assets" / "eephus-export.js").read_text(encoding="utf-8"))
    assert prospx == [want], prospx
    assert export == [want], export


def test_no_other_shipped_file_loads_it_under_another_spelling():
    files = subprocess.run(["git", "ls-files", "*.html", "*.js"], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
    want = _expected_url()
    for rel in files:
        if rel.startswith("vendor/"):
            continue
        p = ROOT / rel
        if not p.exists():
            continue
        for url in URL_RE.findall(p.read_text(encoding="utf-8", errors="replace")):
            assert url == want, f"{rel} loads {url}"

"""SML01: the Download CSV bar counts only the rows the CSV holds.

assets/eephus-csv.js prints "N rows" on the bar and in its aria-label. The file
is written by EephusExport.scrape, which drops every row carrying
data-export-skip (the season line /mlbstats/ opens under a player, the detail
line /fa/ opens under a free agent). The count must apply the same rule, or
opening a line reads 929 rows over a 928 row file.

The check loads the shipped asset under a JS runtime (node, or the VS Code
Electron binary run as node) on a stub table of three rows with one skipped,
and expects 2. With no runtime on the box it reads the source for the same
rule instead.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET = ROOT / "assets" / "eephus-csv.js"

_STUB = r"""
globalThis.window = globalThis;
globalThis.document = { body: null, addEventListener: function () {} };
var fs = require("fs");
eval(fs.readFileSync(process.argv[process.argv.length - 1], "utf8"));
function row(skip) {
  return { getAttribute: function (n) { return (skip && n === "data-export-skip") ? "" : null; } };
}
var table = { tBodies: [{ rows: [row(false), row(true), row(false)] }] };
process.stdout.write(JSON.stringify(window.EephusCSV.rowCount(table)));
"""


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


def _count_under_runtime():
    cmd, extra = _runtime()
    if cmd is None:
        return None
    env = dict(os.environ, **extra)
    out = subprocess.run(cmd + ["-e", _STUB, str(ASSET)], capture_output=True, text=True,
                         env=env, timeout=60)
    return json.loads(out.stdout.strip())


def test_data_row_count_excludes_export_skip_rows():
    counted = _count_under_runtime()
    if counted is None:
        src = ASSET.read_text(encoding="utf-8")
        body = src[src.index("function dataRowCount"):src.index("// ---- CSV text")]
        counted = 2 if (re.search(r'data-export-skip', src[src.index("function isSkipRow"):])
                        and "isSkipRow(rows[i])" in body) else None
    assert counted == 2

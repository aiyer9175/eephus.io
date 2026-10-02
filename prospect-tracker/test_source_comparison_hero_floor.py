# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""RPR11: the hero floor belongs to the pair whose estimate it sits beside.

On 2026-10-01 the /glossary/#view=source-comparison hero read "0.393 against
0.398 for the best public source (MLB Pipeline), a -0.005 point estimate that
does NOT clear its noise floor of 0.030 (carried from the vm1 frame)". The
0.030 is head_to_head_verdict.mde95, the E_refit floor of eFV against PROSPX
CONSENSUS; the eFV against MLB Pipeline floor is the in-run E_cond figure at
head_to_head_vs_sources.sources.mlb_pipeline.spearman.mde95 (0.0235).

This runs the shipped _methHeroBanner under a JS runtime (node, or the VS Code
Electron binary run as node) on the served data/source_backtest.json and reads
the floor printed right after the best-source estimate. It must equal that
pair's own floor: head_to_head_verdict.mde95 when the best source is PROSPX
consensus, the source's Spearman cell mde95 otherwise. Synthetic copies of the
artifact (only the best-source ordering changed) cover the other branches.
Nothing here computes a statistic; every expected number is read off the file.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "glossary.js"
DATA = ROOT / "data" / "source_backtest.json"

_FUNCS = ("_hhVerdict", "_hhBlock", "_hhPairFloor", "_hhFloorClause",
          "_hhPopulationClause", "_methHeroBanner")

_STUB = r"""
var fs = require("fs");
function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
var args = process.argv.slice(-2);
eval(fs.readFileSync(args[0], "utf8"));
var docs = JSON.parse(fs.readFileSync(args[1], "utf8"));
process.stdout.write(JSON.stringify(docs.map(function (d) { return _methHeroBanner(d); })));
"""


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


def _fn_src(js: str, name: str) -> str:
    m = re.search(r"^function " + re.escape(name) + r"\([^)]*\) \{.*?\n\}\n", js, re.S | re.M)
    assert m, f"{name} not found at module level in assets/glossary.js (renamed?)"
    return m.group(0)


def _artifact() -> dict:
    if not DATA.exists():
        pytest.skip("data/source_backtest.json absent (gitignored build artifact)")
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    acc = doc.get("accuracy") or {}
    hh = acc.get("head_to_head_verdict") or {}
    if not hh or not (acc.get(hh.get("basis")) or {}).get("xfv"):
        pytest.skip("source_backtest.json carries no head-to-head verdict block")
    return doc


def _banners(docs: list[dict], tmp_path: Path) -> list[str]:
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    js = JS.read_text(encoding="utf-8").replace("\r\n", "\n")
    src = tmp_path / "hero.js"
    src.write_text("\n".join(_fn_src(js, n) for n in _FUNCS), encoding="utf-8")
    payload = tmp_path / "docs.json"
    payload.write_text(json.dumps(docs), encoding="utf-8")
    out = subprocess.run(cmd + ["-e", _STUB, str(src), str(payload)], capture_output=True,
                         text=True, env=dict(os.environ, **extra), timeout=60)
    assert out.returncode == 0, out.stderr
    return [re.sub(r"<[^>]+>", "", h) for h in json.loads(out.stdout)]


_LABELS = {"prospx_consensus": "PROSPX consensus", "mlb_pipeline": "MLB Pipeline",
           "fangraphs": "FanGraphs"}
_BEST = re.compile(r"for the best public source \(([^)]+)\), a ([+-]?\d+\.\d{3}) point "
                   r"estimate[^.]*?noise floor of (\d+\.\d{3})")


def _best_key(doc: dict) -> str:
    acc = doc["accuracy"]
    blk = acc[acc["head_to_head_verdict"]["basis"]]
    keys = [k for k in _LABELS if (blk.get(k) or {}).get("spearman") is not None]
    return max(keys, key=lambda k: blk[k]["spearman"])


def _pair_floor(doc: dict, key: str) -> float:
    acc = doc["accuracy"]
    if key == "prospx_consensus":
        return acc["head_to_head_verdict"]["mde95"]
    return acc["head_to_head_vs_sources"]["sources"][key]["spearman"]["mde95"]


def _with_best(doc: dict, key: str) -> dict:
    """A copy whose verdict block puts `key` above every other public source."""
    d = json.loads(json.dumps(doc))
    blk = d["accuracy"][d["accuracy"]["head_to_head_verdict"]["basis"]]
    top = max(blk[k]["spearman"] for k in _LABELS if (blk.get(k) or {}).get("spearman") is not None)
    blk[key]["spearman"] = round(top + 0.002, 4)
    return d


def _check(doc: dict, text: str) -> None:
    key = _best_key(doc)
    m = _BEST.search(text)
    assert m, f"hero names no best public source with a floor:\n{text}"
    assert m.group(1) == _LABELS[key], (m.group(1), key)
    want = f"{_pair_floor(doc, key):.3f}"
    assert m.group(3) == want, (
        f"hero prints a floor of {m.group(3)} beside eFV against {m.group(1)}; that "
        f"pair's floor is {want}")
    hh = doc["accuracy"]["head_to_head_verdict"]
    if key == "prospx_consensus":
        assert "Against PROSPX consensus" not in text
    else:
        # The consensus pair is stated too, with its own floor.
        cm = re.search(r"Against PROSPX consensus,.*?point estimate[^.]*?noise floor of "
                       r"(\d+\.\d{3})", text)
        assert cm and cm.group(1) == f"{hh['mde95']:.3f}", text


def test_hero_floor_is_the_best_pairs_floor_on_the_served_artifact(tmp_path):
    doc = _artifact()
    (text,) = _banners([doc], tmp_path)
    _check(doc, text)


def test_hero_floor_follows_the_best_source_in_every_branch(tmp_path):
    doc = _artifact()
    vs = doc["accuracy"].get("head_to_head_vs_sources") or {}
    if vs.get("basis") != doc["accuracy"]["head_to_head_verdict"]["basis"]:
        pytest.skip("per-source cells are on another basis")
    keys = [k for k in _LABELS if k in (vs.get("sources") or {}) or k == "prospx_consensus"]
    docs = [_with_best(doc, k) for k in keys]
    for d, text in zip(docs, _banners(docs, tmp_path)):
        _check(d, text)

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The three MLB surfaces must speak ONE number vocabulary.

PROSPX owns `formatMetric` (types fv/plus/war/wag/netfv/rate/surplusM/permil/
pct/int, integer for the +-family, the null token, and the -0 collapse). The
module surfaces deliberately keep LOCAL MIRRORS rather than importing the
2.4MB PROSPX script - fa.js documents that choice and this file pins the
consequence: a mirror that drifts is worse than no mirror, because the numbers
then disagree silently.

They HAD drifted (2026-08-03). /projections/ carried its own one-off `fmtWar`
and `money` instead of a mirror, and the two `money` implementations disagreed
on negatives: projections rendered "-$1.6M" while fa.js's `moneyM` dropped the
sign and rendered "$1.6M". Harmless on /fa/, where moneyM only ever sees
guarantees and AAVs, and a serious misread on /projections/, which prices
SURPLUS through the same type - negatives became common there the day
rest-of-season control pricing shipped. A liability displayed as an asset.

`moneyM` now carries a minus but never a plus: the leading "+" belongs to
surplusM, where direction is the point, and is noise on a contract guarantee.

RVA10 (2026-10-01): the -0 collapse only caught an exact -0. A tiny negative
such as -0.01 still printed "-0.0" through toFixed, which is how 218 /projections/
board season cells (george_springer 2031 among them) printed a signed zero. Every
mirror, PROSPX included, now prints a value that ROUNDS to zero at its type's
precision as the unsigned zero. The behavioural tests below run the shipped
function bodies under a JS runtime (node, or the VS Code Electron binary run as
node) and skip only when the box has neither.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
MIRRORS = ["assets/fa.js", "assets/projections.js", "assets/mlbstats.js"]
PROSPX = "prospx/index.html"


def _extract(js: str, name: str = "formatMetric") -> str:
    """The body of `function <name>(...) { ... }`, brace-matched."""
    start = js.index(f"function {name}(")
    depth, end = 0, -1
    for i in range(js.index("{", start), len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end > 0, f"unbalanced braces in {name}"
    return js[start:end]


def _normalize(src: str) -> str:
    """Strip comments and collapse whitespace, so the copies may be commented
    differently but must behave the same."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"\s+", " ", src).strip()


def _bodies() -> dict[str, str]:
    return {p: _normalize(_extract((ROOT / p).read_text(encoding="utf-8")))
            for p in MIRRORS}


def test_every_surface_has_a_format_metric_mirror():
    for path, body in _bodies().items():
        assert "switch" in body, f"{path}: formatMetric is not the shared shape"


def test_the_mirrors_are_identical():
    bodies = _bodies()
    ref_path, ref = next(iter(bodies.items()))
    for path, body in bodies.items():
        assert body == ref, (
            f"{path} has drifted from {ref_path}. These are deliberate mirrors "
            "of one contract, so a difference means two surfaces now format the "
            "same number two ways.\n\n"
            f"{ref_path}:\n  {ref}\n\n{path}:\n  {body}")


def test_money_keeps_the_minus_and_drops_the_plus():
    """The defect that started this, pinned in both copies.

    A negative dollar figure must not render as a positive one, and a contract
    guarantee must not sprout a leading '+'.
    """
    for path, body in _bodies().items():
        m = re.search(r'case "moneyM":\s*return ([^;]+);', body)
        assert m, f"{path}: moneyM case missing"
        expr = m.group(1)
        assert "z < 0" in expr, (
            f"{path}: moneyM must carry the minus for negative dollars "
            "(/projections/ prices surplus through this type)")
        assert not re.search(r"\bsign\b", expr), (
            f"{path}: moneyM must not use `sign`, which prefixes '+' to every "
            "positive - that belongs to surplusM, not to a guarantee")


def test_null_token_is_shared_and_is_not_a_real_em_dash():
    """All three surfaces render an absent value the same way, and it is a
    spaced hyphen: real em-dashes are banned in user-facing copy and
    tools/strip_emdashes.py lints assets/*.js."""
    for path in MIRRORS + ["assets/mlbstats.js"]:
        js = (ROOT / path).read_text(encoding="utf-8")
        m = re.search(r'EM_DASH\s*=\s*(["\'])(.*?)\1', js)
        assert m, f"{path}: no EM_DASH null token"
        assert m.group(2) == " - ", (
            f"{path}: null token is {m.group(2)!r}, expected ' - '")
        assert "—" not in m.group(2) and "–" not in m.group(2)


# --- behaviour: a value that rounds to zero prints the unsigned zero ---------

_STUB = r"""
var fs = require("fs");
var EM_DASH = " - ";
var args = process.argv.slice(-2);
eval(fs.readFileSync(args[0], "utf8"));
var cases = JSON.parse(fs.readFileSync(args[1], "utf8"));
process.stdout.write(JSON.stringify(cases.map(function (c) { return formatMetric(c[0], c[1]); })));
"""


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


def _run(path: str, cases: list, tmp_path: Path) -> list[str]:
    """formatMetric(value, type) for every case, from the SHIPPED body in `path`."""
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    js = (ROOT / path).read_text(encoding="utf-8")
    tag = re.sub(r"\W", "_", path)
    src = tmp_path / f"{tag}.js"
    src.write_text(_extract(js), encoding="utf-8")
    payload = tmp_path / f"{tag}.json"
    payload.write_text(json.dumps(cases), encoding="utf-8")
    out = subprocess.run(cmd + ["-e", _STUB, str(src), str(payload)], capture_output=True,
                         text=True, env=dict(os.environ, **extra), timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# Values that round to zero at each type's printed precision (the three the
# audit named, plus the positive twins), and the unsigned zero each must print.
_ONE_DP = [-0.01, -0.049, -0.0004, 0.01, 0.049, 0.0004, -0.0]
_TWO_DP = [-0.0004, -0.0049, -0.004, 0.0004, 0.0049, -0.0]
_INT = [-0.4, -0.049, -0.0004, 0.4, 0.0004, -0.0]
_ZERO = {
    "war": (_ONE_DP, "0.0"), "pct": (_ONE_DP, "0.0%"), "surplusM": (_ONE_DP, "$0.0M"),
    "moneyM": (_ONE_DP, "$0.0M"), "rate": (_TWO_DP, "0.00"), "int": (_INT, "0"),
}
_ZERO_PROSPX = {
    "war": (_ONE_DP, "0.0"), "pct": (_ONE_DP, "0.0%"), "surplusM": (_ONE_DP, "$0.0M"),
    "rate": (_TWO_DP, "0.00"), "wag": (_TWO_DP, "0.00"), "int": (_INT, "0"),
    "plus": (_INT, "0"), "netfv": (_INT, "0"), "fv": ([-0.4, -0.0004, -0.0], "0"),
}
# A figure that does NOT round to zero keeps its sign: the repair must not eat
# a real negative (moneyM carrying the minus is the defect this file began with).
_SIGNED = [(-0.06, "war", "-0.1"), (-0.049, "rate", "-0.05"), (-0.006, "rate", "-0.01"),
           (0.006, "rate", "+0.01"), (-0.06, "surplusM", "-$0.1M"), (0.06, "surplusM", "+$0.1M"),
           (-0.06, "pct", "-0.1%"), (-1.25, "war", "-1.3"), (-0.6, "int", "-1")]
_SIGNED_MODULE = _SIGNED + [(-0.06, "moneyM", "-$0.1M"), (-150, "moneyM", "-$150M"),
                            (0.06, "moneyM", "$0.1M")]
_SIGNED_PROSPX = _SIGNED + [(-0.006, "wag", "-0.01"), (-0.6, "netfv", "-1"), (0.6, "netfv", "+1")]


def _zero_cases(table):
    return [(v, t, want) for t, (vals, want) in table.items() for v in vals]


@pytest.mark.parametrize("path", MIRRORS + [PROSPX])
def test_a_value_that_rounds_to_zero_prints_the_unsigned_zero(path, tmp_path):
    table = _ZERO_PROSPX if path == PROSPX else _ZERO
    cases = _zero_cases(table)
    got = _run(path, [[v, t] for v, t, _ in cases], tmp_path)
    bad = [(v, t, g, w) for (v, t, w), g in zip(cases, got) if g != w]
    assert not bad, f"{path}: (value, type, printed, expected) {bad}"


@pytest.mark.parametrize("path", MIRRORS + [PROSPX])
def test_a_real_negative_keeps_its_sign(path, tmp_path):
    cases = _SIGNED_PROSPX if path == PROSPX else _SIGNED_MODULE
    got = _run(path, [[v, t] for v, t, _ in cases], tmp_path)
    bad = [(v, t, g, w) for (v, t, w), g in zip(cases, got) if g != w]
    assert not bad, f"{path}: (value, type, printed, expected) {bad}"


def test_prospx_and_the_mirrors_print_the_shared_types_alike(tmp_path):
    vals = [-123.456, -1.25, -0.06, -0.049, -0.01, -0.0049, -0.0004, -0.0, 0, 0.0004,
            0.01, 0.049, 0.06, 1.25, 123.456, None, "", "x"]
    cases = [[v, t] for t in ("int", "war", "rate", "surplusM", "pct") for v in vals]
    ref = _run(PROSPX, cases, tmp_path)
    for path in MIRRORS:
        assert _run(path, cases, tmp_path) == ref, path


def test_projections_board_prints_no_signed_zero_season_cell(tmp_path):
    """The served path: every board season cell the /projections/ board can
    print (the first `horizon` seasons of each row's expected path), formatted
    by the shipped projections.js formatMetric, holds no "-0.0"."""
    data = ROOT / "data" / "mlb_projections.json"
    if not data.exists():
        pytest.skip("data/mlb_projections.json absent (gitignored build artifact)")
    doc = json.loads(data.read_text(encoding="utf-8"))
    h = int(doc.get("horizon") or 5)
    cells = [(m["key"], doc["first_season"] + t, w)
             for grp in ("vets", "prospects") for m in doc.get(grp) or []
             for t, w in enumerate((m.get("war") or [])[:h]) if w is not None]
    got = _run("assets/projections.js", [[w, "war"] for _, _, w in cells], tmp_path)
    signed = [(k, s, w, g) for (k, s, w), g in zip(cells, got) if g in ("-0.0", "+0.0")]
    assert not signed, f"{len(signed)} board cells print a signed zero, e.g. {signed[:5]}"
    spr = [g for (k, s, w), g in zip(cells, got) if k == "george_springer" and -0.05 < w < 0]
    for g in spr:
        assert g == "0.0", g

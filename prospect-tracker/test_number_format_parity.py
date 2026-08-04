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
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
MIRRORS = ["assets/fa.js", "assets/projections.js"]


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

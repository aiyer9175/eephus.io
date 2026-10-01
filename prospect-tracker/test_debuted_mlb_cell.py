# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Debuted "MLB stats" cell names the level of any non-MLB line.

WHY THIS EXISTS (census M02-13, 2026-09-25). makeGradMilbCell printed the debuted row's
statline under the "MLB stats" header with no level, so a AAA slash line sat under an
MLB wRC+ chip built on a handful of MLB at-bats (bj_murray: wRC+ -57 on 5 MLB AB above
a .294/.395 AAA line). 826 of 2,764 served debuted rows carry a non-MLB statline.

Contract pinned here, over every served debuted row:
  * a statline whose level is not MLB prints its level tag;
  * the wRC+ / xFIP chip is hidden when the MLB sample on file is under the
    100 PA / 30 IP floor (owner answer M8-4, 2026-09-25; PA is AB x 1.1 when the row
    carries no PA), and names the sample when shown.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    m = re.search(r"^const GRAD_MLB_CHIP_FLOOR = .*?;$", src, re.M)
    assert m, "GRAD_MLB_CHIP_FLOOR not found"
    ctx = mr.MiniRacer()
    ctx.eval("function escapeHtml(s) { return String(s); }"
             " function gradCurrentWarHTML(p) { return ''; }"
             " function gradCareerWarHTML(p) { return ''; }")
    ctx.eval(m.group(0))
    for fn in ("mlbSabermetricSample", "headlineStatHTML", "makeGradMilbCell"):
        ctx.eval(_function_source(src, fn))
    return ctx


def _cell(js, row) -> str:
    return js.eval("makeGradMilbCell(%s)" % json.dumps(row))


def test_fixture_aaa_line_under_tiny_mlb_sample(js):
    row = {"statline": {"level": "AAA", "season": 2026, "is_prior_season": False, "is_pitcher": False,
                        "avg": ".294", "obp": ".395", "slg": ".500", "hr": 12, "sb": 3},
           "sabermetrics": {"season": 2026, "is_pitcher": False, "wrc_plus": -57.0},
           "career_stats": [{"season": 2026, "level": "MLB", "ab": 5}]}
    html = _cell(js, row)
    assert 'class="prior-season-tag"' in html and ">AAA<" in html
    assert "wRC+" not in html  # 5 MLB AB is under the 100 PA floor
    row["career_stats"][0]["ab"] = 90   # about 99 PA: still under the floor
    assert "wRC+" not in _cell(js, row)
    row["career_stats"][0]["ab"] = 91   # about 100 PA: the chip shows
    assert "wRC+" in _cell(js, row)
    row["career_stats"][0]["ab"] = 180
    html = _cell(js, row)
    assert "wRC+" in html and "2026 MLB 180 AB, about 198 PA" in html
    row["career_stats"][0]["pa"] = 120  # a measured PA wins over the AB estimate
    assert "2026 MLB 120 PA" in _cell(js, row)


def test_pitcher_chip_needs_thirty_innings(js):
    row = {"statline": {"level": "MLB", "season": 2026, "is_prior_season": False, "is_pitcher": True,
                        "era": 3.1, "ip": 29.0},
           "sabermetrics": {"season": 2026, "is_pitcher": True, "xfip": 3.4},
           "career_stats": [{"season": 2026, "level": "MLB", "ip": 29.0}]}
    assert "xFIP" not in _cell(js, row)
    row["career_stats"][0]["ip"] = 30.0
    html = _cell(js, row)
    assert "xFIP" in html and "2026 MLB 30 IP" in html


def test_floor_constant_is_the_owner_answer():
    m = re.search(r"^const GRAD_MLB_CHIP_FLOOR = (.*?);$", _src(), re.M)
    assert m and m.group(1).replace(" ", "") == "{PA:100,IP:30}", m and m.group(1)


def test_every_served_non_mlb_line_is_tagged(js):
    from conftest import load_data_doc
    rows = load_data_doc("debuts_lite.json")
    if not rows:
        pytest.skip("data/debuts_lite.json not built")
    rows = rows if isinstance(rows, list) else (rows.get("players") or [])
    n_non_mlb = 0
    for r in rows:
        sl = r.get("statline")
        if not sl:
            continue
        html = _cell(js, {k: r.get(k) for k in ("statline", "sabermetrics", "career_stats")})
        if sl.get("level") and sl["level"] != "MLB":
            n_non_mlb += 1
            assert f">{sl['level']}" in html, (r.get("player_key"), sl["level"])
        sm = r.get("sabermetrics") or {}
        chip = ("wRC+" in html) or ("xFIP" in html)
        cs = [c for c in (r.get("career_stats") or [])
              if c.get("level") == "MLB" and c.get("season") == sm.get("season")]
        if cs and chip:
            c = cs[0]
            if sm.get("is_pitcher"):
                n = c.get("ip")
            else:
                n = c.get("pa") if c.get("pa") is not None else (
                    c["ab"] * 1.1 if c.get("ab") is not None else None)
            if n is not None:
                assert n >= (30 if sm.get("is_pitcher") else 100), (r.get("player_key"), n)
    assert n_non_mlb > 0

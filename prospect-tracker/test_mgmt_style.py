# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The style z-scores on the club-season rows: signed z, mean zero and sd one across
the clubs of a season, labelled style and not skill, never a 100 + 10z index and never
a tier colour. The hook z's sign is stated on the column (a negative z is an earlier
hook)."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import mgmt_decisions as MD  # noqa: E402

ART = ROOT / "data" / "management_decisions.json"
JS = ROOT / "assets" / "management.js"
CSS = ROOT / "assets" / "management.css"
GL = ROOT / "data" / "glossary.json"
Z_KEYS = ("z_hook", "z_pen", "z_bench", "z_ibb", "z_visit")


@pytest.fixture(scope="module")
def rows():
    if not ART.exists():
        pytest.skip("run python mgmt_decisions.py")
    d = json.loads(ART.read_text(encoding="utf-8"))
    if d.get("status") != "built":
        pytest.skip(d.get("status"))
    return d["clubs"]["rows"], d


def test_style_z_scores_have_mean_zero_sd_one_across_thirty_clubs_per_season(rows):
    rs, _ = rows
    by = {}
    for r in rs:
        by.setdefault(r["season"], []).append(r)
    for season, grp in by.items():
        assert len(grp) == 30, (season, len(grp))
        for k in Z_KEYS:
            xs = [r[k] for r in grp if r.get(k) is not None]
            if k == "z_visit" and not xs:
                # mound visits enter the feed in 2023; before that the column is
                # null for every club of the season, never a fabricated zero
                assert sum(r["n_mound_visit"] for r in grp) == 0, season
                continue
            assert len(xs) == 30, (season, k)
            m = sum(xs) / len(xs)
            sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
            assert abs(m) < 0.02, (season, k, m)
            assert abs(sd - 1.0) < 0.03, (season, k, sd)
    z = MD.style_z({"a": 1.0, "b": 2.0, "c": 3.0})
    assert z["a"] == pytest.approx(-1.22, abs=0.01) and z["b"] == 0.0 and z["c"] == pytest.approx(1.22, abs=0.01)
    assert MD.style_z({"a": 5.0, "b": 5.0}) == {"a": 0.0, "b": 0.0}


def test_hook_z_sign_is_stated_on_the_column(rows):
    rs, _ = rows
    js = JS.read_text(encoding="utf-8")
    assert "Hook z (negative = earlier)" in js
    g = json.loads(GL.read_text(encoding="utf-8"))
    hook = next(e for e in g["entries"] if e["id"] == "hook_z")
    assert "NEGATIVE z is an earlier hook" in hook["definition"]
    # sign as measured: the club with the lowest median hook pitch count carries
    # the lowest z_hook in its season, and the highest the highest
    by = {}
    for r in rs:
        if r.get("hook_median_pitches") is not None:
            by.setdefault(r["season"], []).append(r)
    for season, grp in by.items():
        lo = min(grp, key=lambda r: r["hook_median_pitches"])
        hi = max(grp, key=lambda r: r["hook_median_pitches"])
        assert lo["z_hook"] == min(r["z_hook"] for r in grp), season
        assert hi["z_hook"] == max(r["z_hook"] for r in grp), season
        assert lo["z_hook"] < 0 < hi["z_hook"], season


def test_style_columns_are_labelled_style_not_skill_and_carry_no_plus_sign(rows):
    rs, d = rows
    assert d["style_sentence"].startswith("Style, not skill")
    assert "no plus sign" in d["style_sentence"]
    assert d["clubs"]["style_sentence"] == d["style_sentence"]
    for r in rs:
        for k in r:
            assert "plus" not in k.lower(), k
    js = JS.read_text(encoding="utf-8")
    assert 'mgmt-th-tag">style' in js, "the board's z columns carry the style header tag"
    assert "mgmt-zchip" in js and "style_sentence" in js
    g = json.loads(GL.read_text(encoding="utf-8"))
    for slug in ("hook_z", "pen_z", "bench_z", "ibb_z", "visit_z"):
        e = next(x for x in g["entries"] if x["id"] == slug)
        assert "not an index, not skill" in e["definition"], slug
        assert "management" in e["module"]


def test_no_style_figure_is_100_plus_10z_and_none_takes_a_tier(rows):
    rs, _ = rows
    for r in rs:
        for k in Z_KEYS:
            v = r.get(k)
            if v is not None:
                assert -6 < v < 6, (k, v, "a 100 + 10z index would sit near 100")
    js = JS.read_text(encoding="utf-8")
    assert "EephusTiers" not in js
    assert "EEPHUS_TIERS" not in js
    css = CSS.read_text(encoding="utf-8")
    assert "--tier" not in css and "eephus-tier" not in css
    # colour classes exist for the SIGN of a realized number only
    assert ".mgmt-pos" in css and ".mgmt-neg" in css
    assert "mgmt-zchip" in css

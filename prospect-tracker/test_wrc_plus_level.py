# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Phase D2: the MiLB level chip is wRC+ vs level, not OPS+ vs level.

Two things changed together and they are separable on purpose:

  METRIC    OPS -> a linear-weight wOBA (fixed FanGraphs 2013 shape, rescaled per
            level-season so the pool's mean wOBA equals its OBP).
  BASELINE  level_norms.avg_ops was an UNWEIGHTED mean of the prospects this site
            happens to TRACK, over a two-season window. The new pool is
            PA-WEIGHTED, single-season, and the WHOLE league.

The baseline half is the bigger mover of the printed number and carries no ordering
information (a per-level recentering); the metric half is the one that reorders.

The component feed is the part that had to be built. wrc_rates.py previously read
.cache/milb_full_stats/, a tree with ONE reader and NO writer anywhere in the repo,
already stale on 53.3% of rows. milb_history fetches the identical StatsAPI response
and now keeps the components, so the maintained cache is the live path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _board():
    p = ROOT / "data" / "timeseries.json"
    if not p.exists():
        pytest.skip("timeseries.json not built")
    return json.loads(p.read_text(encoding="utf-8"))


def _hitter_statlines():
    return [p["statline"] for p in _board()["players"]
            if (p.get("statline") or {}) and not p["statline"].get("is_pitcher")]


def test_milb_history_keeps_the_woba_components():
    """The whole lane rests on these seven counts riding along in the lean row.
    They are COUNTS, not rates, so nothing downstream can reconstruct them from
    ops/obp/slg if they are dropped again."""
    src = (ROOT / "milb_history.py").read_text(encoding="utf-8")
    for key in ('"h": st.get("hits")', '"doubles": st.get("doubles")',
                '"triples": st.get("triples")', '"ibb": st.get("intentionalWalks")',
                '"hbp": st.get("hitByPitch")', '"sf": st.get("sacFlies")',
                '"sb": st.get("stolenBases")'):
        assert key in src, f"lean hitting row lost {key}; wRC+ vs level cannot be computed"


def test_component_cache_self_heals_rather_than_needing_a_manual_delete():
    """Past seasons cache FOREVER, so a pure TTL would never migrate a cache written
    before the components existed. A component-less hitting row must mark the file
    stale so the refetch happens once, per box, without anyone remembering to clear
    the deploy box by hand."""
    src = (ROOT / "milb_history.py").read_text(encoding="utf-8")
    assert 'group == "hitting"' in src and 'probe.get("h") is None' in src, (
        "the schema-migration probe is gone; a stale lean cache would persist forever")


def test_wrc_rates_prefers_the_maintained_cache_over_the_orphan_tree():
    """.cache/milb_full_stats/ has no producer in this repo. It may still be READ as
    a fallback, but it must not be the primary path again."""
    src = (ROOT / "wrc_rates.py").read_text(encoding="utf-8")
    assert "_live_rows" in src and "milb_history" in src, (
        "wrc_rates no longer reads the maintained cache")
    # Check the CALL ORDER inside load_rows, not the definition order in the file
    # (the earlier version compared a def to a call and always failed).
    body = src[src.index("def load_rows("):]
    call = "_live_rows(sport, season) or _legacy_rows(sport, season)"
    assert call in body, (
        "load_rows no longer prefers the maintained cache with the orphan tree as "
        f"fallback; expected {call!r}")


def test_served_hitters_all_carry_the_new_chip():
    """Coverage was the main cost of this swap and it is now zero: the level-label
    fallback (the board says CPX where the feed says DSL on 124 rows) closed the
    entire gap, 93.8% -> 100%."""
    sls = _hitter_statlines()
    assert len(sls) > 1000
    have_ops = [s for s in sls if s.get("ops_plus_level") is not None]
    have_wrc = [s for s in sls if s.get("wrc_plus_level") is not None]
    assert len(have_wrc) >= len(have_ops), (
        f"wRC+ chip covers {len(have_wrc)} of {len(have_ops)} rows that carry the "
        "retired OPS chip; the swap must not lose coverage")


def test_the_new_chip_is_a_different_number_from_the_old_one():
    """If these ever agree everywhere, the producer has silently fallen back to the
    OPS chip and the lane is a no-op wearing a new field name."""
    sls = [s for s in _hitter_statlines()
           if s.get("wrc_plus_level") is not None and s.get("ops_plus_level") is not None]
    assert len(sls) > 500
    moved = [s for s in sls if s["wrc_plus_level"] != s["ops_plus_level"]]
    assert len(moved) > 0.5 * len(sls), (
        f"only {len(moved)}/{len(sls)} rows differ; the wRC+ chip looks like a copy")


def test_the_new_chip_is_tighter_than_the_old_one():
    """The true league baseline plus the PA shrink narrows the spread. Measured:
    OPS+ sd 6.97 against wRC+ sd 6.06. A WIDER chip would mean the shrink or the
    pool anchor broke."""
    import statistics as st
    sls = [s for s in _hitter_statlines()
           if s.get("wrc_plus_level") is not None and s.get("ops_plus_level") is not None]
    o = st.pstdev([s["ops_plus_level"] for s in sls])
    w = st.pstdev([s["wrc_plus_level"] for s in sls])
    assert w < o, f"wRC+ sd {w:.2f} is not tighter than OPS+ sd {o:.2f}"


def test_every_consumer_reads_through_one_accessor():
    """Five model sites and twelve display sites read this chip. They go through
    _level_plus (python) and _lvlPlus (js) so the fallback lives in ONE place; a
    direct read would silently keep a surface on the retired metric."""
    btv = (ROOT / "bayes_trade_value.py").read_text(encoding="utf-8")
    assert btv.count('get("ops_plus_level")') <= 1, (
        "a bayes_trade_value site reads ops_plus_level directly instead of _level_plus")
    px = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "function _lvlPlus(sl)" in px, "the js accessor is gone"
    # Only the accessor's own fallback may name the retired field in live code.
    def _code(ln):
        """Strip a trailing // comment so a line that only MENTIONS the retired field
        in prose does not read as a live consumer."""
        i = ln.find("//")
        return ln[:i] if i >= 0 else ln
    live = [ln for ln in px.splitlines() if "ops_plus_level" in _code(ln)]
    assert len(live) <= 1, f"{len(live)} live js sites still read ops_plus_level: {live[:3]}"

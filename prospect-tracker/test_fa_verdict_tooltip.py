# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A verdict chip and the sentence explaining it must describe the same band.

MEASURED 2026-09-06: 60 of the 232 served FA chips carried a Deal+ that their own
tooltip's numbers put in a DIFFERENT bucket. Sandy Alcantara at Deal+ 191 was
chipped VALUE beside a sentence saying value starts at 223; Kevin Gausman at 101
was chipped MARKET beside a sentence saying overpay ends at 109.

The chips were right. The tooltip hardcoded the POOLED terciles 109/223, which are
wrong twice over: the board has banded verdicts PER POSITION GROUP since
2026-07-30 (owner decision, fa_market.VERDICT_BAND_MODE = "group"), and the pooled
edges themselves were re-cut 109/223 -> 89/198 on 2026-08-19. Re-running the
shipped fa_market.deal_verdict over the served rows reproduces all 232 exactly.

The tooltip is now DERIVED from data/fa_meta.json gate2.verdict_edges. This file
pins the three seams that derivation depends on: the artifact must agree with the
Python constants, the JS position-group mapping must agree with _pos_group, and
no renderer may go back to a literal band.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import fa_market as fm

HERE = Path(__file__).parent
DATA = HERE / "data"


def _json(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def _edges():
    e = (_json("fa_meta.json").get("gate2") or {}).get("verdict_edges")
    if not e:
        pytest.skip("fa_meta.json carries no gate2.verdict_edges")
    return e


def test_the_artifact_edges_match_the_shipped_constants():
    """The tooltip reads the artifact, so the artifact must be the served rule."""
    e = _edges()
    assert e.get("band_mode") == fm.VERDICT_BAND_MODE, (
        f"fa_meta says band_mode={e.get('band_mode')!r} but fa_market ships "
        f"{fm.VERDICT_BAND_MODE!r}; the tooltip would describe the wrong basis"
    )
    got = {k: tuple(v) for k, v in (e.get("group") or {}).items()}
    assert got == {k: tuple(v) for k, v in fm.VERDICT_GROUP_EDGES.items()}, (
        f"group edges drifted: artifact {got} vs shipped {fm.VERDICT_GROUP_EDGES}"
    )
    pooled = e.get("pooled") or {}
    assert pooled.get("overpay_max") == fm.VERDICT_OVERPAY_MAX
    assert pooled.get("value_min") == fm.VERDICT_VALUE_MIN


def test_the_glossary_edge_list_is_the_shipped_rule():
    """deal_plus in data/glossary.json types the per-group edges in its formula
    and methodology. They were cut again on 2026-10-08 (owner answer M14-2), so
    the copy is pinned to the constants rather than trusted to follow them."""
    gl = _json("glossary.json")
    ent = next(e for e in gl["entries"] if e.get("id") == "deal_plus")
    for g, (lo, hi) in fm.VERDICT_GROUP_EDGES.items():
        assert f"{g} {lo}/{hi}" in ent["formula"], (g, ent["formula"])
    m = re.search(r"SP overpay < (\d+) / value \u2265 (\d+), RP (\d+) / (\d+), "
                  r"C (\d+) / (\d+), other position players (\d+) / (\d+)",
                  ent["methodology"])
    assert m, "deal_plus methodology no longer lists the per-group edges"
    got = [int(x) for x in m.groups()]
    want = [v for g in ("SP", "RP", "C", "POS") for v in fm.VERDICT_GROUP_EDGES[g]]
    assert got == want, (got, want)


def test_the_js_position_grouping_matches_pos_group():
    """_faPosGroup in fa.js is a hand copy of fa_market._pos_group. Pin it."""
    assert fm.POS_GROUP_MODE == "v1", (
        "POS_GROUP_MODE moved off v1, which splits POS into POSP/POSC. Those are "
        "not keys in VERDICT_GROUP_EDGES, so the server would silently fall back "
        "to pooled edges for every non-C non-pitcher and the JS copy would not"
    )
    js = (HERE / "assets" / "fa.js").read_text(encoding="utf-8")
    body = js[js.index("function _faPosGroup("):]
    body = body[:body.index("\n  }") + 4]
    for group, listed in (("SP", re.search(r'\["SP".*?\]', body)),
                          ("RP", re.search(r'\["RP".*?\]', body))):
        assert listed, f"the {group} bucket list is gone from _faPosGroup"
        heads = re.findall(r'"([A-Z0-9]+)"', listed.group(0))
        for h in heads:
            assert fm._pos_group(h) == group, (
                f"fa.js puts {h!r} in {group} but fa_market._pos_group says "
                f"{fm._pos_group(h)!r}"
            )
    # and the buckets the JS does NOT list must not be pitcher/catcher buckets
    for head in ("SP", "SP2", "P", "LHP", "RHP", "RP", "CL", "SIRP", "MIRP", "C",
                 "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", ""):
        assert re.search(rf'"{head}"', body) or fm._pos_group(head) == "POS", (
            f"fa_market._pos_group({head!r}) is {fm._pos_group(head)!r} but fa.js "
            f"does not list it, so the JS would fall through to POS"
        )


def test_no_served_chip_contradicts_the_band_it_is_cut_on():
    cls = _json("fa_class.json")
    e = _edges()
    group = {k: tuple(v) for k, v in (e.get("group") or {}).items()}
    pooled = (e.get("pooled") or {})
    bad = []
    for m in cls.get("members") or []:
        v, dp = m.get("verdict"), m.get("dealPlus")
        if v is None or dp is None:
            continue
        lo, hi = pooled.get("overpay_max"), pooled.get("value_min")
        if e.get("band_mode") == "group":
            lo, hi = group.get(fm._pos_group(m.get("pos")), (lo, hi))
        implied = "value" if dp >= hi else ("overpay" if dp < lo else "market")
        if implied != v:
            bad.append((m.get("name"), m.get("pos"), dp, v, implied))
    assert not bad, (
        f"{len(bad)} served chip(s) contradict the band the tooltip states: {bad[:5]}"
    )


def test_the_served_verdicts_are_what_the_shipped_rule_produces():
    cls = _json("fa_class.json")
    bad = [(m.get("name"), m.get("pos"), m.get("dealPlus"), m.get("verdict"))
           for m in (cls.get("members") or [])
           if m.get("verdict") is not None and m.get("dealPlus") is not None
           and fm.deal_verdict(m["dealPlus"], m.get("pos")) != m["verdict"]]
    assert not bad, f"{len(bad)} served verdict(s) the shipped rule disagrees with: {bad[:5]}"


def test_the_tooltip_carries_no_literal_band():
    """No RENDERED string may name a tercile edge.

    Comments may, and one does: the block above the helper records exactly which
    retired constants this replaced, and that history is the point of keeping it.
    So the scan runs over code with `//` line comments stripped, not over the raw
    file.
    """
    js = (HERE / "assets" / "fa.js").read_text(encoding="utf-8")
    assert "_faVerdictBand" in js, "the derived-band helper is gone"
    code = "\n".join(re.sub(r"^\s*//.*$", "", ln) for ln in js.splitlines())
    for stale in ("109-223", "\u2265223", "<109", "109/223"):
        assert stale not in code, (
            f"fa.js hardcodes the retired pooled tercile {stale!r} again; those "
            f"edges were re-cut on 2026-08-19 and the board has not used pooled "
            f"bands since 2026-07-30"
        )

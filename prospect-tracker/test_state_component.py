# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T5 of the pixel system (final-pass plan 5.7.4): the state component.

assets/eephus-state.js draws four kinds (loading, empty, unmeasured, failed)
in the ballpark lamp idiom (owner answer PX-Q1). This file pins:

  - the component itself: four kinds, role=alert on failed, role=status on
    loading, the art aria-hidden, the caller's message carried verbatim;
  - that it loads in the page head, before any module script paints;
  - every listed site (plan 5.7.2 table 2.2, PX-12) routes through it, keeps
    its original message string, and a failed site keeps its Retry control;
  - every module helper delegates to window.EephusState;
  - the build-time copies of the art (build_site.py) and the static PROSPX
    boot loader are byte-equal to what the component draws;
  - the old markup is gone (no .state-message.is-loading, no raw
    load-error div, no hard-coded feed colour).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
STATE_JS = (ASSETS / "eephus-state.js").read_text(encoding="utf-8")


def _js(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def _ctx():
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    ctx = MiniRacer()
    ctx.eval("var window = this;")
    ctx.eval(STATE_JS)
    return ctx


def _html(ctx, kind, msg, opts=None):
    import json
    return ctx.eval(f"window.EephusState.html({json.dumps(kind)}, {json.dumps(msg)}, {json.dumps(opts)})")


# ---- the component -----------------------------------------------------------

def test_the_component_draws_four_kinds_with_their_roles():
    ctx = _ctx()
    assert ctx.eval("JSON.stringify(window.EephusState.kinds)") == '["loading","empty","unmeasured","failed"]'
    load = _html(ctx, "loading", "Loading the board")
    assert load.startswith('<div class="px-state is-loading" role="status" aria-live="polite">')
    assert '<span class="px-lob" aria-hidden="true">' in load
    assert load.count("<rect ") == 16 and load.count('class="f r"') == 1, "16 frames, one still frame"
    assert load.endswith('<div class="px-state-msg">Loading the board</div></div>')
    fail = _html(ctx, "failed", 'Gone. <button id="x-retry">Retry</button>', "x-load-error")
    assert fail.startswith('<div class="px-state is-failed x-load-error" role="alert">')
    assert '<button id="x-retry">Retry</button>' in fail
    for kind in ("empty", "unmeasured"):
        h = _html(ctx, kind, "Nothing here.")
        assert h.startswith(f'<div class="px-state is-{kind}">'), h[:80]
        assert "role=" not in h.split("<svg", 1)[0]
        assert '<svg class="px-art" aria-hidden="true"' in h
    status = _html(ctx, "failed", "x", {"cls": "dfs-empty is-broken", "role": "status"})
    assert status.startswith('<div class="px-state is-failed dfs-empty is-broken" role="status">')
    # an unknown kind falls back to the empty scene, never to no box at all
    assert _html(ctx, "nope", "x").startswith('<div class="px-state is-empty">')


def test_render_writes_the_box_into_the_element():
    ctx = _ctx()
    out = ctx.eval("var el = {innerHTML: ''}; window.EephusState.render(el, 'empty', 'No rows.'); el.innerHTML")
    assert out == _html(ctx, "empty", "No rows.")


def test_the_component_uses_no_frame_loop_and_no_colour():
    assert "requestAnimationFrame" not in STATE_JS and "setInterval" not in STATE_JS
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", STATE_JS)
    assert ".json" not in STATE_JS, "a JS comment naming a data file lands in SITE_MAP.md"


def test_static_scenes_fit_the_budget_and_draw_in_tokens_only():
    for kind, art in build_site._PX_STATE_ART.items():
        assert len(art.encode()) <= 1600, (kind, len(art.encode()))
        assert 'shape-rendering="crispEdges"' in art and 'aria-hidden="true"' in art
        assert "fill=" not in art and "style=" not in art, "colour rides the .s / .k classes"


def test_build_site_art_is_byte_equal_to_the_component():
    for kind, art in build_site._PX_STATE_ART.items():
        assert f"{kind}: '{art}'" in STATE_JS, kind


def test_the_component_loads_in_the_head_before_any_module_script():
    page = build_site.page("t", "", '<script src="/assets/fa.js" defer></script>')
    head, body = page.split("</head>", 1)
    assert f'<script src="/assets/eephus-state.js?v={build_site._STATE_VER}" defer></script>' in head
    assert "eephus-state.js" not in body


# ---- every listed site -------------------------------------------------------
# (file, kind, the original message string kept verbatim). A Retry control the
# site had is part of the message string, so its id survives with it.
SITES = [
    # loading
    ("franchise.js", "loading", 'esc("Loading Franchises.")'),
    ("ledger.js", "loading", 'esc("Loading Club Ledger.")'),
    ("hof.js", "loading", '"Loading Hall of Fame board."'),
    ("parks.js", "loading", '"Loading venues..."'),
    ("management.js", "loading", '"Loading the decisions of "'),
    ("management.js", "loading", '"Loading In-Game Management."'),
    ("fa.js", "loading", '"Loading free-agency data&hellip;"'),
    ("fa_dpw.js", "loading", '"Loading the $/WAR series&hellip;"'),
    ("projections.js", "loading", '"Loading player."'),
    ("projections.js", "loading", '"Loading projections."'),
    ("arbitration.js", "loading", '"Loading the arbitration board"'),
    ("arbitration.js", "loading", '"Loading arbitration history"'),
    ("dynasty.js", "loading", '"Loading the Fantasy Rank."'),
    ("pal.js", "loading", 'esc("Loading the position-fit model…")'),
    ("mlbstats.js", "loading", '"Loading the eWAR board."'),
    # filtered to zero
    ("fa.js", "empty", '"No free agents match these filters."'),
    ("hof.js", "empty", '"No players match these filters."'),
    ("parks.js", "empty", '"No venue matches that filter."'),
    ("projections.js", "empty", '"No players match these filters."'),
    ("dynasty.js", "empty", 'opts.emptyKind || "empty"'),
    ("betting.js", "empty", '"<strong>" + esc(title) + "</strong>"'),
    ("betting.js", "empty", "Nothing qualifies today</div>"),
    ("dfs.js", "empty", 'esc(k ? k.head : "No slate to price")'),
    # not measured / not built
    ("betting.js", "unmeasured", '": not measured yet.</strong> " + esc(why)'),
    ("arbitration.js", "unmeasured", '"The arbitration board is not built yet. Check back shortly."'),
    ("management.js", "unmeasured", '"No club-season row for "'),
    ("management.js", "unmeasured", "esc(SHARD.error)"),
    ("pal.js", "unmeasured", 'esc("The Alchemy Lab is being computed from Statcast arsenals'),
    ("mlbstats.js", "unmeasured", '"eWAR board not built yet on this deploy; the nightly build writes it."'),
    ("mlbstats.js", "unmeasured", '"Defense board not built yet on this deploy; the nightly build writes it."'),
    # failed (Retry kept where it existed)
    ("fa.js", "failed", '<button class="chip" id="fa-retry" type="button">Retry</button>'),
    ("fa_dpw.js", "failed", "failed to load. <a href=\"#view=board\">Back to the board</a>."),
    ("projections.js", "failed", '<button class="chip" id="mlbp-detail-retry" type="button">Retry</button>'),
    ("projections.js", "failed", '<button class="chip" id="proj-retry" type="button">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-war-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-history-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-starter-history-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-hitter-history-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-leverage-history-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-defense-history-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-starter-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-hitter-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-leverage-retry">Retry</button>'),
    ("mlbstats.js", "failed", '<button type="button" class="chip" id="mlbstats-defense-retry">Retry</button>'),
    ("mlbstats.js", "failed", "Back to Current</button>"),
    ("pal.js", "failed", '<button type="button" class="chip" id="pf-retry">Retry</button>'),
    ("pal.js", "failed", '<button type="button" class="chip" id="pal-retry">Retry</button>'),
    ("dynasty.js", "failed", '<button type="button" id="dyn-retry" class="dyn-btn">Retry</button>'),
    ("dynasty.js", "failed", '"<strong>The Fantasy Rank failed to load.</strong> "'),
    ("redraft.js", "failed", '<button type="button" id="rd-retry" class="rd-scorebtn">Retry</button>'),
    ("ledger.js", "failed", 'esc(copy("shard_failed"))'),
    ("ledger.js", "failed", "esc(LOAD_ERROR)"),
    ("management.js", "failed", "esc(LOAD_ERROR)"),
    ("franchise.js", "failed", "esc(LOAD_ERROR)"),
    ("hof.js", "failed", "esc(LOAD_ERROR)"),
    ("parks.js", "failed", '<button type="button" class="chip" id="pk-retry">Retry</button>'),
    ("arbitration.js", "failed", '<button type="button" class="chip" id="arb-retry">Retry</button>'),
    ("arbitration.js", "failed", '"The history data failed to load."'),
    ("betting.js", "failed", '<button type="button" id="bt-retry" class="bt-btn">retry</button>'),
    ("dfs.js", "failed", 'class="dfs-btn">Retry</button>'),
    ("eephus-ui.js", "failed", '"Could not load the discussion."'),
]


@pytest.mark.parametrize("name,kind,msg", SITES, ids=[f"{s[0]}:{s[1]}:{i}" for i, s in enumerate(SITES)])
def test_each_listed_site_routes_through_the_component(name, kind, msg):
    src = _js(name)
    assert msg in src, f"{name}: the original message {msg!r} is gone"
    # the message sits inside a call whose first argument names this kind
    # (a literal, or a choice such as opts.emptyKind || "empty"), with no other
    # state call between the two
    call = r'(?:pxState|\.html)\([^,]*?"' + kind + r'"'
    pat = call + r"(?:(?!pxState\(|EephusState\.html\().){0,700}?" + re.escape(msg)
    if msg.startswith("opts.emptyKind"):
        pat = r"pxState\(" + re.escape(msg)
    assert re.search(pat, src, re.S), f"{name}: {msg!r} is not drawn by a {kind} state"


MODULES = sorted({s[0] for s in SITES} - {"eephus-ui.js"})


@pytest.mark.parametrize("name", MODULES)
def test_each_module_helper_delegates_to_the_component(name):
    src = _js(name)
    i = src.index("function pxState(kind, msg, opts)")
    body = src[i:src.index("\n  }", i)]
    assert 'window.EephusState' in body and "S.html(kind, msg, opts)" in body
    # the harness fallback still carries the alert role and the hook class
    assert 'role="alert"' in body and "cls" in body


def test_the_frozen_fantasy_parity_file_is_not_a_site():
    """assets/fantasy.js is FROZEN and no page loads it (build_site.py, the
    _FANTASY_VER note): it is the pre-split parity reference for redraft.js,
    so plan 5.7.2's fantasy.js:807 row is not a served site and stays as is."""
    assert "pxState" not in _js("fantasy.js")
    assert '<div class="fantasy-error" role="alert"><strong>Data failed to load.</strong> ' in _js("fantasy.js")


def test_the_old_state_markup_is_gone():
    for p in ASSETS.glob("*.js"):
        src = p.read_text(encoding="utf-8")
        assert "state-message is-loading" not in src, p.name
        assert 'class="mlbstats-empty mlbstats-load-error"' not in src, p.name
        assert 'class="mlbstats-empty pal-load-error"' not in src, p.name
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert "#6f8a76" not in src.lower(), "the feed's hard-coded colour is gone"


# ---- build-time pages ---------------------------------------------------------

def test_the_homepage_empty_states_are_px_states():
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert '_px_state("empty", "No recent activity.")' in src
    # HOME_4: the lead runs only on a fresh article, so its "No articles yet"
    # box went with it; the site strip's Articles card links /articles/.
    assert '_px_state("empty", "<strong>No articles yet</strong>")' not in src
    box = build_site._px_state("empty", "No recent activity.")
    assert box == ('<div class="px-state is-empty">' + build_site._PX_STATE_ART["empty"]
                   + '<div class="px-state-msg">No recent activity.</div></div>')
    assert build_site._px_state("failed", "x").startswith('<div class="px-state is-failed" role="alert">')


def test_the_python_box_matches_the_component():
    ctx = _ctx()
    for kind in ("empty", "unmeasured", "failed"):
        assert build_site._px_state(kind, "Same words.") == _html(ctx, kind, "Same words."), kind


def test_the_prospx_boot_loader_is_the_component_loading_kind():
    page = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    expect = _html(_ctx(), "loading", "Loading prospect data…")
    assert expect in page, "the static boot loader drifted from eephus-state.js"
    assert 'document.querySelector("#content .px-state.is-loading .px-state-msg")' in page
    assert '<script src="/assets/eephus-state.js?v=' in page

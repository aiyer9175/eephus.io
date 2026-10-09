# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PX_SYSTEM_SWEEP (owner ask 2026-10-02): every served logo, glyph and
animation is on the pixel system or carries a written reason not to be.

The inventory is docs/pixel/PX_SWEEP_2026-10.md (one row per item, a
disposition each). This file pins the served side of it:

  - no served page or runtime still draws a glyph, emoji or vector mark the
    inventory converted or retired (each pinned by the exact markup it used);
  - no served stylesheet, page or script defines a keyframe the inventory
    retired (prospx-spin, state-pulse, gfx-spin);
  - the converted motions carry their stepped timing in the source;
  - every converted control draws from the sprite, and every symbol it names
    is drawn;
  - the inventory's count line matches its own table.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "pixel" / "PX_SWEEP_2026-10.md"


def _served_files() -> list[Path]:
    dirs = [ln.strip() for ln in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    out: list[Path] = []
    for d in dirs:
        p = ROOT / d
        if p.is_file() and p.suffix in (".html", ".js", ".css"):
            out.append(p)
        elif p.is_dir() and d != "vendor":
            out += [f for f in p.rglob("*") if f.suffix in (".html", ".js", ".css")]
    return out


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# (file, markup the inventory converted or retired). Each string is the exact
# served markup before the sweep; none may come back.
GONE = [
    ("build_site.py", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("assets/eephus-gfx.js", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("assets/fa.js", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("assets/projections.js", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("assets/scores.js", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("collegesavant/app.js", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("collegesavant/pitcher_app.js", '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>'),
    ("collegesavant/app.js", "&#8681; share card"),
    ("collegesavant/pitcher_app.js", "&#8681; share card"),
    ("prospx/index.html", "\U0001F4CA"),
    ("prospx/index.html", "\\u{1F4CA}"),
    ("prospx/index.html", "\U0001F517"),
    ("prospx/index.html", "\U0001F512"),
    ("prospx/index.html", "⏳"),
    ("prospx/index.html", "↺ Reset"),
    ("prospx/index.html", '? "★" : "☆"'),
    ("prospx/index.html", "Star a prospect (☆)"),
    ("prospx/index.html", 'aria-label="Close">✕</button>'),
    ("prospx/index.html", '<span aria-hidden="true">⇆</span>'),
    ("prospx/index.html", 'content: "⚐";'),
    ("prospx/index.html", 'content: "!";'),
    ("prospx/index.html", "⚕</span>"),
    ("prospx/index.html", 'signal">⚠ ${label}'),
    ("prospx/index.html", 'el.textContent = "⚠ " + msg;'),
    ("prospx/index.html", 'class="state-message is-loading"'),
    ("prospx/index.html", "gfxBallSeam"),
    ("prospx/index.html", "gfxSeam"),
    ("prospx/index.html", 'class="gfx-busy-spin"'),
    ("assets/eephus-nav.js", '<span aria-hidden="true">☰</span>'),
    ("assets/eephus-ui.js", '<span aria-hidden="true">◔</span>'),
    ("assets/eephus-export.js", 'd="M10 1H3a1 1 0 0 0-1 1v9h1.5V2.5H10V1z'),
    ("assets/eephus-hub.js", 'glyph: "Δ"'),
    ("assets/eephus-hub.js", '<span class="hub-glyph">${m.glyph}</span>'),
    ("assets/trademachine.js", "⚕</span>"),
    ("assets/trademachine.js", 'signal">⚠ ${label}'),
    ("assets/fa.js", "&#9888;"),
    ("assets/glossary.js", '<div class="meth-caveats-title">⚠ Read'),
    ("assets/glossary.js", '<div class="meth-caveats-title">&#9888; Read'),
    ("assets/projections.js", '"}">⇄</button>'),
    ("assets/projections.js", "&#8646; Trade Machine"),
    ("assets/fa.js", '<span class="chip-glyph" aria-hidden="true">§</span>'),
    ("assets/projections.js", '<span class="chip-glyph" aria-hidden="true">§</span>'),
    ("prospx/index.html", "✕ clear</button>"),
    ("build_site.py", '"◆ Diamond preview"'),
    ("build_site.py", "◆ Live"),
    ("build_site.py", "◆ Upcoming"),
    ("build_site.py", '<span class="glyph">◆</span> {NEWS_LABEL}'),
    ("build_site.py", "&#10005;</button>"),
    ("build_site.py", 'M12 2a10 10 0 1 0 0 20'),
    ("build_site.py", 'M20 4H4c-1.1 0-1.99.9-1.99 2L2 18'),
]


@pytest.mark.parametrize("rel,old", GONE, ids=[f"{r}:{o[:24]!r}" for r, o in GONE])
def test_a_converted_glyph_does_not_come_back(rel, old):
    assert old not in _src(rel), f"{rel} still draws {old!r}"


# The served generated pages carry the same: no page ships the retired chip
# glyph, the Diamond chip sigil or the trade board's text close.
@pytest.mark.parametrize("old", [
    '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>',
    "◆ Diamond preview", '<span class="cal-tag">◆', "font-size:16px;\">&#10005;</button>",
])
def test_no_generated_page_ships_a_retired_glyph(old):
    hits = [str(p.relative_to(ROOT)) for p in _served_files() if p.suffix == ".html"
            and old in p.read_text(encoding="utf-8")]
    assert not hits, hits


RETIRED_KEYFRAMES = ("prospx-spin", "state-pulse", "gfx-spin")


def test_no_served_file_defines_a_retired_keyframe():
    pat = re.compile(r"@keyframes\s+(" + "|".join(RETIRED_KEYFRAMES) + r")\b")
    hits = [f"{p.relative_to(ROOT)}: {m.group(1)}" for p in _served_files()
            for m in pat.finditer(p.read_text(encoding="utf-8"))]
    assert not hits, hits


# The converted motions, as declared (the browser harness reads them computed:
# test_px_sweep_motion_runs.py).
STEPPED = [
    ("prospx/index.html", "animation: fvIndicatorPulse 2.4s step-end infinite;"),
    ("prospx/index.html", "fvBreakoutColor 2s step-end infinite;"),
    ("prospx/index.html", "animation: grb-pulse 2s step-end infinite;"),
    ("prospx/index.html", "@keyframes grb-pulse { 50% { opacity: 0.25; } }"),
    ("prospx/index.html", "animation: freshPulse 2.4s step-end infinite;"),
    ("prospx/index.html", "@keyframes freshPulse { 50% { opacity: 0.25; } }"),
    ("prospx/index.html", "foil-shift 8s steps(32, end) infinite"),
    ("prospx/index.html", "chrome-shimmer 4.2s steps(16, end) infinite"),
    ("prospx/index.html", "holo-shift 6s steps(24, end) infinite"),
    ("prospx/index.html", "holo-shift 5s steps(20, end) infinite"),
    ("prospx/index.html", "holo-shift 3s steps(12, end) infinite"),
    ("prospx/index.html", "legendary-shift 3s steps(12, end) infinite"),
    ("prospx/index.html", "chrome-headshot-pulse 2s step-end infinite"),
    ("prospx/index.html", "holo-headshot-pulse 2s step-end infinite"),
    ("prospx/index.html", "legendary-headshot-pulse 2s step-end infinite"),
    ("prospx/index.html", "animation: glossary-highlight 1.8s steps(4, end);"),
    ("prospx/index.html", '"animation-timing-function", "steps(" + Math.max(1, Math.round(oneCopy)) + ", end)"'),
    ("assets/site.css", "animation: glossary-highlight 1.8s steps(4, end); }"),
    ("assets/site.css", "transition: opacity .2s steps(4, start); }"),
    ("assets/eephus-export.js", "transition:opacity .15s steps(4,start),transform .15s steps(4,start);"),
    ("assets/eephus-export.js", "transition:opacity .12s steps(3,start),color .12s steps(3,start),border-color .12s steps(3,start);"),
]


@pytest.mark.parametrize("rel,decl", STEPPED, ids=[d[:40] for _r, d in STEPPED])
def test_a_converted_motion_is_stepped(rel, decl):
    assert decl in _src(rel)


def test_no_prospx_rarity_or_pulse_motion_is_continuous():
    css = _src("prospx/index.html")
    for name in ("foil-shift", "chrome-shimmer", "holo-shift", "legendary-shift", "fvIndicatorPulse",
                 "fvBreakoutColor", "grb-pulse", "freshPulse", "headshot-pulse", "glossary-highlight"):
        for m in re.finditer(name + r"\s+[\d.]+m?s\s+([a-z-]+(?:\([^)]*\))?)", css):
            assert m.group(1).startswith(("steps(", "step-end")), (name, m.group(0))


# Every control the sweep converted draws from the sprite through the helpers.
def test_the_converted_controls_draw_sprite_icons():
    assert 'window.EephusIco("menu", 16)' in _src("assets/eephus-nav.js")
    assert 'window.EephusIco("account", 12)' in _src("assets/eephus-ui.js")
    assert 'window.EephusIco("export", 12)' in _src("assets/eephus-export.js")
    assert "window.EephusIco(m.ico, 12)" in _src("assets/eephus-hub.js")
    px = _src("prospx/index.html")
    for k in ("gfx", "link", "close", "reset", "compare", "hourglass", "lock", "warn", "ev-il", "watch-off"):
        assert f"#i-{k}" in px or f'pxIcoHTML("{k}"' in px or f'"{k}"' in px, k
    assert "function pxWatchIco(on)" in px and "function pxLoadingHTML(msg)" in px
    assert "function _gfxPxMark(px)" in px and "${_gfxPxMark(22)}" in px and "${_gfxPxMark(s)}" in px
    tm = B._TRADE_MACHINE_BODY.replace("{_ICO_CLOSE}", B._ico("close", 12))
    assert "#i-close" in tm
    assert B._SOC_SVG["web"] == B._ico("web", 12) and B._SOC_SVG["mail"] == B._ico("mail", 12)


def test_the_eephus_ico_helper_matches_build_site_markup():
    """window.EephusIco and build_site._ico emit the same markup for a key."""
    js = _src("assets/eephus-nav.js")
    assert '[12, 16, 24, 32].indexOf(size) < 0' in js
    assert 'core ? "2 2 12 12" : "0 0 16 16"' in js
    py12 = B._ico("menu", 12)
    assert 'viewBox="2 2 12 12"' in py12 and 'width="16" height="16"' in py12


def test_the_inventory_counts_match_its_table():
    text = DOC.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if re.match(r"\| [GMR]\d\d \|", ln)]
    disp = [ln.split("|")[4].strip() for ln in rows]
    conv = [d for d in disp if d.startswith("CONVERT")]
    fu = [d for d in disp if d.startswith("CONVERT (FU")]
    keep = [d for d in disp if d == "KEEP"]
    retire = [d for d in disp if d == "RETIRE"]
    assert len(conv) + len(keep) + len(retire) == len(rows)
    m = re.search(r"Counts: (\d+) rows\. CONVERT (\d+) \((\d+) built here, G36 built by HOME_8, (\d+) by "
                  r"follow-up specs\), KEEP (\d+), RETIRE (\d+)\.", text)
    assert m, "count line"
    total, c, here, f, k, r = map(int, m.groups())
    assert (total, c, f, k, r) == (len(rows), len(conv), len(fu), len(keep), len(retire))
    assert here == len(conv) - len(fu) - 1


def test_the_retire_list_in_the_inventory_is_the_tested_list():
    text = DOC.read_text(encoding="utf-8")
    named = set(re.findall(r"\| R\d\d \| `@keyframes ([\w-]+)`", text))
    assert named == set(RETIRED_KEYFRAMES)

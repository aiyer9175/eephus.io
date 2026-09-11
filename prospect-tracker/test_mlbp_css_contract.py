# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every mlbp-* class the MLB player-page renderers emit has a rule in site.css.

THE DEFECT (D3-01, found 2026-09-11). Commit adc7a8d0 (2026-08-03) stripped the
inline layout and dimming off the player-page tab buttons and wrote, in a code
comment, that the selected state now lived in the stylesheet. No rule was ever
added: 19 of the 54 mlbp-* classes shipped with no selector, the selected tab was
drawn exactly like the unselected ones on /projections/ and on the /fa/ market
card (which reuses the strip), and nothing failed. This is the test that would
have caught it.

Ids (mlbp-back, mlbp-hub, ...) and data-mlbp-* attribute names are not classes
and are excluded; everything else spelled mlbp-* in the two renderers is.
Also pinned: the glossary slugs the player page links resolve, because a
[data-gl] whose slug is absent renders a term that looks linked and is not.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
EMITTERS = ("assets/projections.js", "assets/fa.js")
SITE_CSS = ROOT / "assets" / "site.css"

# a token starts at a non-word, non-dash boundary, so data-mlbp-tab never
# yields "mlbp-tab", and it ends on a letter or digit
_TOKEN = re.compile(r"(?<![\w-])(mlbp-[a-z0-9-]*[a-z0-9])")
_ID_CTX = re.compile(r"""(?:\bid=\\?["'`]|getElementById\(\s*["'`]|["'`]#)(mlbp-[a-z0-9-]*[a-z0-9])""")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SELECTOR_CLASS = re.compile(r"\.(mlbp-[a-z0-9-]*[a-z0-9])(?![\w-])")


def _emitted() -> dict[str, set[str]]:
    out = {}
    for rel in EMITTERS:
        src = (ROOT / rel).read_text(encoding="utf-8")
        ids = set(_ID_CTX.findall(src))
        out[rel] = set(_TOKEN.findall(src)) - ids
    return out


def _styled() -> set[str]:
    css = _CSS_COMMENT.sub("", SITE_CSS.read_text(encoding="utf-8"))
    return set(_SELECTOR_CLASS.findall(css))


def test_extractor_finds_the_renderers_classes():
    """Non-vacuity: a regex change that finds nothing would pass the contract."""
    em = _emitted()
    assert len(em["assets/projections.js"]) >= 40, sorted(em["assets/projections.js"])
    for cls in ("mlbp-tabs", "mlbp-tab", "mlbp-tabpanel", "mlbp-tile", "mlbp-slider"):
        assert cls in em["assets/projections.js"], cls
    assert {"mlbp-tabs", "mlbp-tab", "mlbp-tabpanel"} <= em["assets/fa.js"]
    # ids and data attributes are not classes
    for not_a_class in ("mlbp-back", "mlbp-hub", "mlbp-gfx", "mlbp-detail-retry", "mlbp-panel"):
        assert not_a_class not in em["assets/projections.js"], not_a_class


def test_every_emitted_mlbp_class_has_a_site_css_rule():
    styled = _styled()
    missing = {rel: sorted(classes - styled) for rel, classes in _emitted().items()}
    missing = {rel: m for rel, m in missing.items() if m}
    assert not missing, (
        "mlbp-* classes emitted with no selector in assets/site.css (the adc7a8d0 "
        f"defect class): {missing}")


def test_the_selected_tab_has_a_visible_rule():
    """The strip's selected state is keyed on aria-selected, the only state the
    renderers write. A rule on .active would never match."""
    css = _CSS_COMMENT.sub("", SITE_CSS.read_text(encoding="utf-8"))
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    sel = [body for head, body in rules
           if ".mlbp-tab" in head and 'aria-selected="true"' in head]
    assert sel, 'no .mlbp-tab[aria-selected="true"] rule in site.css'
    assert any("background" in b for b in sel), "the selected tab rule sets no background"


def test_player_page_glossary_slugs_exist():
    """Every data-gl slug the player page names resolves in data/glossary.json.
    Explanations moved off the page and behind these links (owner copy rule,
    2026-09-11), so a dead slug is a term with no explanation anywhere."""
    src = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    slugs = set(re.findall(r'data-gl="([a-z0-9_]+)"', src))
    slugs |= set(re.findall(r'\bgl:\s*"([a-z0-9_]+)"', src))
    slugs |= set(re.findall(r'\bterm\("([a-z0-9_]+)"', src))
    slugs |= set(re.findall(r'\bcell\([^;]*?,\s*"([a-z0-9_]+)"\)', src))
    slugs |= set(re.findall(r'"(war_ip_plus_(?:rp|sp)(?:_adj|_3yr)?)"', src))
    assert {"dem_plus", "fielding_runs", "framing_runs", "positional_adjustment",
            "hem_plus", "war_pa_plus", "wpa"} <= slugs, sorted(slugs)
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    known = {e["id"] for e in gl.get("entries") or []}
    assert not sorted(slugs - known), f"unknown glossary slugs: {sorted(slugs - known)}"
